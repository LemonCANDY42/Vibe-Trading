"""Event-signal forward-return study for Moirix artifacts."""

from __future__ import annotations

import bisect
import csv
import json
import statistics
from datetime import date
from pathlib import Path
from typing import Any

from src.agent.tools import BaseTool
from src.tools._moirix_adapter import adapter_artifact_dir, resolve_adapter_input
from src.tools.path_utils import safe_path, safe_run_dir

DEFAULT_HORIZONS = (1, 3, 5, 10, 20)


class MoirixEventSignalBacktestTool(BaseTool):
    """Compute forward returns for Moirix event_signal.csv without using news loaders."""

    name = "moirix_event_signal_backtest"
    description = (
        "Run a research-only forward-return study from Moirix event_signal.csv "
        "and an explicit daily close price CSV. This consumes Moirix event "
        "features as Vibe artifacts, writes event_signal_forward_returns.csv "
        "and event_signal_backtest_summary.json under artifacts/moirix, and "
        "does not touch broker, order, or live-trading paths."
    )
    parameters = {
        "type": "object",
        "properties": {
            "event_signal_path": {
                "type": "string",
                "description": "Optional event_signal.csv path. Defaults to artifacts/moirix/event_signal.csv.",
            },
            "price_csv_path": {
                "type": "string",
                "description": (
                    "Daily close CSV under the current run or allowed import roots. "
                    "Expected columns include date, symbol, close."
                ),
            },
            "horizons": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Forward-return horizons in trading rows. Defaults to [1, 3, 5, 10, 20].",
                "default": list(DEFAULT_HORIZONS),
            },
        },
        "required": [],
    }
    repeatable = True
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        run_dir = kwargs.get("run_dir")
        if not run_dir:
            return json.dumps(
                {"status": "error", "error": "run_dir is required for moirix_event_signal_backtest artifacts"},
                ensure_ascii=False,
            )

        try:
            out_dir = adapter_artifact_dir(str(run_dir))
            event_signal_path, signal_error = resolve_adapter_input(
                kwargs.get("event_signal_path"),
                str(run_dir),
                default_relative="artifacts/moirix/event_signal.csv",
                blocker_prefix="moirix_event_signal",
            )
            price_path, price_error = _resolve_price_csv(kwargs.get("price_csv_path"), str(run_dir))
            horizons = _parse_horizons(kwargs.get("horizons"))
        except ValueError as exc:
            return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)

        if signal_error is not None:
            return json.dumps(signal_error, ensure_ascii=False)
        if price_error is not None:
            _write_blocked_summary(out_dir, [price_error["claim_gate"]["blockers"][0]], str(price_error.get("error", "")))
            return json.dumps(price_error, ensure_ascii=False)
        assert event_signal_path is not None
        assert price_path is not None

        payload = run_event_signal_backtest(
            event_signal_path=event_signal_path,
            price_csv_path=price_path,
            out_dir=out_dir,
            horizons=horizons,
        )
        return json.dumps(payload, ensure_ascii=False, default=str)


def run_event_signal_backtest(
    *,
    event_signal_path: Path,
    price_csv_path: Path,
    out_dir: Path,
    horizons: tuple[int, ...] = DEFAULT_HORIZONS,
) -> dict[str, Any]:
    signals = _load_event_signals(event_signal_path)
    prices = _load_price_history(price_csv_path)
    blockers: list[str] = []
    if not signals:
        blockers.append("moirix_event_signal_empty")
    if not prices:
        blockers.append("moirix_event_signal_price_data_empty")

    rows: list[dict[str, Any]] = []
    missing_price_symbols: set[str] = set()
    if not blockers:
        rows, missing_price_symbols = _forward_return_rows(signals, prices, horizons=horizons)
        if not rows:
            blockers.append("moirix_event_signal_no_forward_return_coverage")

    out_dir.mkdir(parents=True, exist_ok=True)
    forward_path = out_dir / "event_signal_forward_returns.csv"
    summary_path = out_dir / "event_signal_backtest_summary.json"
    status = "blocked" if blockers else "ok"
    if rows:
        _write_rows_csv(forward_path, rows)
    summary = _build_summary(
        status=status,
        signals=signals,
        rows=rows,
        horizons=horizons,
        blockers=blockers,
        event_signal_path=event_signal_path,
        price_csv_path=price_csv_path,
        missing_price_symbols=missing_price_symbols,
    )
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    artifacts = {"event_signal_backtest_summary": str(summary_path)}
    if rows:
        artifacts["event_signal_forward_returns"] = str(forward_path)
    return {
        "schema_version": "vibe.moirix_event_signal_backtest.v1",
        "status": status,
        "horizons": list(horizons),
        "summary": summary,
        "artifacts": artifacts,
        "authority": _research_authority(blockers),
        "claim_gate": {
            "ready_for_event_signal_forward_return_study": status == "ok",
            "ready_for_trading_authority": False,
            "ready_for_real_money_trading_authority": False,
            "blockers": blockers,
        },
    }


def _resolve_price_csv(input_path: str | None, run_dir: str) -> tuple[Path | None, dict[str, Any] | None]:
    if input_path:
        return resolve_adapter_input(
            input_path,
            run_dir,
            blocker_prefix="moirix_event_signal_price_csv",
        )

    run_root = safe_run_dir(run_dir)
    for relative in (
        "artifacts/moirix/price_series.csv",
        "artifacts/moirix/prices.csv",
        "artifacts/price_series.csv",
    ):
        candidate = safe_path(relative, run_root)
        if candidate.exists():
            return candidate, None
    return None, {
        "status": "blocked",
        "error": "No price CSV found. Provide price_csv_path or write artifacts/moirix/price_series.csv.",
        "claim_gate": {"blockers": ["moirix_event_signal_price_csv_missing"]},
    }


def _parse_horizons(value: Any) -> tuple[int, ...]:
    if value is None or value == "":
        return DEFAULT_HORIZONS
    if isinstance(value, str):
        raw_items = [item.strip() for item in value.split(",") if item.strip()]
    elif isinstance(value, (list, tuple)):
        raw_items = list(value)
    else:
        raise ValueError("horizons must be an array of positive integers or a comma-separated string")
    horizons = sorted({int(item) for item in raw_items})
    if not horizons or any(item <= 0 or item > 252 for item in horizons):
        raise ValueError("horizons must contain integers from 1 to 252")
    return tuple(horizons)


def _load_event_signals(path: Path) -> list[dict[str, Any]]:
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return [row for row in rows if row.get("known_at") and row.get("symbol")]


def _load_price_history(path: Path) -> dict[str, list[tuple[date, float]]]:
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        rows = list(reader)
        fieldnames = set(reader.fieldnames or [])
    date_field = _first_existing(fieldnames, ("date", "trade_date", "timestamp", "datetime"))
    close_field = _first_existing(fieldnames, ("close", "adj_close", "Close", "close_price"))
    symbol_field = _first_existing(fieldnames, ("symbol", "code", "ticker", "instrument"))
    if date_field is None or close_field is None or symbol_field is None:
        return {}
    by_symbol: dict[str, dict[date, float]] = {}
    for row in rows:
        symbol = str(row.get(symbol_field) or "").strip().upper()
        current_date = _parse_date(row.get(date_field))
        close = _parse_float(row.get(close_field))
        if not symbol or current_date is None or close is None or close <= 0:
            continue
        by_symbol.setdefault(symbol, {})[current_date] = close
    return {
        symbol: sorted(points.items(), key=lambda item: item[0])
        for symbol, points in by_symbol.items()
        if points
    }


def _forward_return_rows(
    signals: list[dict[str, Any]],
    prices: dict[str, list[tuple[date, float]]],
    *,
    horizons: tuple[int, ...],
) -> tuple[list[dict[str, Any]], set[str]]:
    rows: list[dict[str, Any]] = []
    missing_price_symbols: set[str] = set()
    for index, signal in enumerate(signals):
        symbol = str(signal.get("symbol") or "").strip().upper()
        known_date = _parse_date(signal.get("known_at"))
        history = prices.get(symbol)
        if known_date is None or not history:
            if symbol:
                missing_price_symbols.add(symbol)
            continue
        dates = [item[0] for item in history]
        entry_idx = bisect.bisect_left(dates, known_date)
        if entry_idx >= len(history):
            missing_price_symbols.add(symbol)
            continue
        entry_date, entry_close = history[entry_idx]
        impact_score = _parse_float(signal.get("impact_score")) or 0.0
        for horizon in horizons:
            exit_idx = entry_idx + horizon
            if exit_idx >= len(history):
                continue
            exit_date, exit_close = history[exit_idx]
            forward_return = (exit_close / entry_close) - 1.0
            rows.append(
                {
                    "event_index": str(index),
                    "known_at": str(signal.get("known_at") or ""),
                    "symbol": symbol,
                    "event_type": str(signal.get("event_type") or "other"),
                    "impact_score": _format_float(impact_score),
                    "confidence": _format_float(_parse_float(signal.get("confidence")) or 0.0),
                    "source_tier": str(signal.get("source_tier") or "unknown"),
                    "pit_valid": str(signal.get("pit_valid") or "unknown"),
                    "entry_date": entry_date.isoformat(),
                    "entry_close": _format_float(entry_close),
                    "horizon_days": str(horizon),
                    "exit_date": exit_date.isoformat(),
                    "exit_close": _format_float(exit_close),
                    "forward_return": _format_float(forward_return),
                    "directional_hit": "true" if impact_score * forward_return > 0 else "false",
                }
            )
    return rows, missing_price_symbols


def _build_summary(
    *,
    status: str,
    signals: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    horizons: tuple[int, ...],
    blockers: list[str],
    event_signal_path: Path,
    price_csv_path: Path,
    missing_price_symbols: set[str],
) -> dict[str, Any]:
    horizon_stats: dict[str, dict[str, Any]] = {}
    for horizon in horizons:
        horizon_rows = [row for row in rows if int(row["horizon_days"]) == horizon]
        returns = [_parse_float(row["forward_return"]) for row in horizon_rows]
        valid_returns = [item for item in returns if item is not None]
        directional_hits = [row for row in horizon_rows if row["directional_hit"] == "true"]
        horizon_stats[str(horizon)] = {
            "count": len(valid_returns),
            "mean_forward_return": _format_float(statistics.fmean(valid_returns)) if valid_returns else None,
            "median_forward_return": _format_float(statistics.median(valid_returns)) if valid_returns else None,
            "positive_ratio": _format_float(sum(1 for item in valid_returns if item > 0) / len(valid_returns))
            if valid_returns
            else None,
            "directional_hit_ratio": _format_float(len(directional_hits) / len(horizon_rows)) if horizon_rows else None,
        }
    return {
        "schema_version": "vibe.moirix_event_signal_backtest_summary.v1",
        "status": status,
        "event_signal_path": str(event_signal_path),
        "price_csv_path": str(price_csv_path),
        "signal_count": len(signals),
        "forward_return_row_count": len(rows),
        "horizons": list(horizons),
        "horizon_stats": horizon_stats,
        "missing_price_symbols": sorted(missing_price_symbols),
        "blockers": blockers,
        "evidence_tiers": _count_by(signals, "source_tier"),
        "pit_valid_counts": _count_by(signals, "pit_valid"),
        "notes": [
            "Forward returns are outcome labels for research, not features available at known_at.",
            "The tool consumes event_signal.csv and explicit price CSV artifacts; it does not load or route news through market-data loaders.",
            "No broker, order, or real-money trading authority is granted.",
        ],
    }


def _write_blocked_summary(out_dir: Path, blockers: list[str], message: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": "vibe.moirix_event_signal_backtest_summary.v1",
        "status": "blocked",
        "blockers": blockers,
        "error": message,
    }
    (out_dir / "event_signal_backtest_summary.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _write_rows_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "event_index",
        "known_at",
        "symbol",
        "event_type",
        "impact_score",
        "confidence",
        "source_tier",
        "pit_valid",
        "entry_date",
        "entry_close",
        "horizon_days",
        "exit_date",
        "exit_close",
        "forward_return",
        "directional_hit",
    ]
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _count_by(rows: list[dict[str, Any]], key: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for row in rows:
        value = str(row.get(key) or "unknown")
        counts[value] = counts.get(value, 0) + 1
    return counts


def _first_existing(fieldnames: set[str], candidates: tuple[str, ...]) -> str | None:
    lowered = {field.lower(): field for field in fieldnames}
    for candidate in candidates:
        if candidate in fieldnames:
            return candidate
        if candidate.lower() in lowered:
            return lowered[candidate.lower()]
    return None


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 8 and text.isdigit():
        text = f"{text[:4]}-{text[4:6]}-{text[6:]}"
    else:
        text = text[:10]
    try:
        return date.fromisoformat(text)
    except ValueError:
        return None


def _parse_float(value: Any) -> float | None:
    try:
        parsed = float(str(value).strip())
    except (TypeError, ValueError):
        return None
    if parsed != parsed:
        return None
    return parsed


def _format_float(value: float) -> str:
    return f"{value:.8g}"


def _research_authority(blockers: list[str]) -> dict[str, Any]:
    return {
        "scope": "research_only",
        "live_broker_execution_enabled": False,
        "real_order_authority": False,
        "trading_authority_claim": False,
        "ready_for_real_money_trading_authority": False,
        "broker_submit_supported": False,
        "blockers": blockers,
    }
