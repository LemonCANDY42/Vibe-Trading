"""Write Vibe-loader market context for Moirix thesis runs."""

from __future__ import annotations

import json
import math
from datetime import date, datetime, timedelta, timezone
from typing import Any

from src.agent.tools import BaseTool
from src.market_data import detect_source
from src.tools._moirix_adapter import adapter_artifact_dir


SCHEMA_VERSION = "vibe.moirix_market_context.v1"


class MoirixMarketContextTool(BaseTool):
    """Persist market/technical context without writing Moirix evidence state."""

    name = "moirix_market_context"
    description = (
        "Create artifacts/moirix/market_context.json from Vibe market-data loaders. "
        "This supplements Moirix PIT evidence with price-window, technical, source, "
        "and benchmark context. It is not Moirix source-lake evidence, not a broker "
        "order, and by default does not fetch after as_of."
    )
    parameters = {
        "type": "object",
        "properties": {
            "target": {"type": "string", "description": "Target symbol, e.g. NVDA.US or 000001.SZ."},
            "market": {"type": "string", "description": "Market label, e.g. US, HK, A-share."},
            "as_of": {"type": "string", "description": "PIT cutoff date in YYYY-MM-DD format."},
            "lookback_days": {
                "type": "integer",
                "description": "Calendar-day lookback window for market context.",
                "default": 90,
            },
            "source": {
                "type": "string",
                "description": "Requested loader source. Use auto for normal fallback behavior.",
                "default": "auto",
            },
            "benchmark": {
                "type": "string",
                "description": "Optional benchmark symbol, e.g. SPY.US, 000300.SH, or ^HSI.",
            },
            "benchmark_source": {
                "type": "string",
                "description": "Optional benchmark source. Defaults to auto.",
                "default": "auto",
            },
            "pre_as_of_days": {
                "type": "integer",
                "description": "Days before as_of for event-window return.",
                "default": 5,
            },
            "post_as_of_days": {
                "type": "integer",
                "description": (
                    "Optional post-as_of days for retrospective validation only. "
                    "Defaults to 0 to avoid future leakage."
                ),
                "default": 0,
            },
            "interval": {"type": "string", "description": "Bar interval. Defaults to 1D.", "default": "1D"},
        },
        "required": ["target", "market", "as_of"],
    }
    repeatable = True
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        run_dir = kwargs.get("run_dir")
        if not run_dir:
            return json.dumps(
                {"status": "error", "error": "run_dir is required for moirix_market_context artifacts"},
                ensure_ascii=False,
            )

        target = str(kwargs.get("target") or "").strip()
        market = str(kwargs.get("market") or "").strip()
        as_of_text = str(kwargs.get("as_of") or "").strip()
        if not target or not market or not as_of_text:
            return json.dumps(
                _blocked(
                    "moirix_market_context_target_market_as_of_required",
                    "target, market, and as_of are required",
                ),
                ensure_ascii=False,
            )

        as_of_date = _parse_date(as_of_text)
        if as_of_date is None:
            return json.dumps(_blocked("moirix_market_context_invalid_as_of", "as_of must be parseable"), ensure_ascii=False)

        try:
            out_dir = adapter_artifact_dir(str(run_dir))
        except ValueError as exc:
            return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)

        lookback_days = max(1, int(kwargs.get("lookback_days") or 90))
        pre_days = max(1, int(kwargs.get("pre_as_of_days") or 5))
        post_days = max(0, int(kwargs.get("post_as_of_days") or 0))
        interval = str(kwargs.get("interval") or "1D").strip() or "1D"
        source = str(kwargs.get("source") or "auto").strip() or "auto"
        benchmark = str(kwargs.get("benchmark") or "").strip()
        benchmark_source = str(kwargs.get("benchmark_source") or "auto").strip() or "auto"
        normalized_target = _normalize_symbol_for_market(target, market)
        normalized_benchmark = _normalize_symbol_for_market(benchmark, market) if benchmark else ""

        start_date = as_of_date - timedelta(days=lookback_days)
        end_date = as_of_date + timedelta(days=post_days)
        payload = _base_payload(
            target=target,
            normalized_target=normalized_target,
            market=market,
            as_of=as_of_date.isoformat(),
            lookback_days=lookback_days,
            pre_as_of_days=pre_days,
            post_as_of_days=post_days,
            interval=interval,
        )

        target_result = _fetch_series(
            symbol=normalized_target,
            requested_source=source,
            start_date=start_date.isoformat(),
            end_date=end_date.isoformat(),
            interval=interval,
        )
        payload["source"] = target_result["source"]
        if target_result["status"] != "ok":
            payload.update(
                _blocked_fields(
                    "moirix_market_context_price_unavailable",
                    target_result.get("error") or "target market data unavailable",
                )
            )
            payload["market_context"] = target_result
            _write_payload(out_dir, payload)
            return json.dumps(payload, ensure_ascii=False, default=str)

        rows = target_result["rows"]
        payload["status"] = "ok"
        payload["claim_gate"] = {"blockers": []}
        payload["market_context"] = {
            "symbol": normalized_target,
            "raw_target": target,
            "row_count": len(rows),
            "start_date": start_date.isoformat(),
            "end_date": end_date.isoformat(),
            "retrospective_validation": post_days > 0,
            "future_leakage_warning": (
                "post_as_of_days was requested; use this only for retrospective validation, not daily decision input"
                if post_days > 0
                else None
            ),
        }
        payload["series_summary"] = _series_summary(rows)
        payload["technical_summary"] = _technical_summary(rows)
        payload["event_window"] = _event_window(rows, as_of_date=as_of_date, pre_days=pre_days, post_days=post_days)

        if benchmark:
            benchmark_result = _fetch_series(
                symbol=normalized_benchmark,
                requested_source=benchmark_source,
                start_date=start_date.isoformat(),
                end_date=end_date.isoformat(),
                interval=interval,
            )
            payload["benchmark"] = {
                "symbol": normalized_benchmark,
                "raw_benchmark": benchmark,
                "source": benchmark_result.get("source"),
                "status": benchmark_result.get("status"),
            }
            if benchmark_result.get("status") == "ok":
                benchmark_summary = _series_summary(benchmark_result["rows"])
                payload["benchmark"]["series_summary"] = benchmark_summary
                payload["benchmark_comparison"] = _benchmark_comparison(payload["series_summary"], benchmark_summary)
            else:
                payload["benchmark"]["error"] = benchmark_result.get("error")

        _write_payload(out_dir, payload)
        return json.dumps(payload, ensure_ascii=False, default=str)


def _fetch_series(
    *,
    symbol: str,
    requested_source: str,
    start_date: str,
    end_date: str,
    interval: str,
) -> dict[str, Any]:
    detected_source = None
    errors: list[str] = []
    try:
        detected_source = detect_source(symbol) if requested_source == "auto" else requested_source
        from backtest.loaders.registry import FALLBACK_CHAINS, LOADER_REGISTRY, get_loader_cls_with_fallback

        loader_cls = get_loader_cls_with_fallback(detected_source)
        candidates = _candidate_loaders(detected_source, loader_cls, fallback_chains=FALLBACK_CHAINS, registry=LOADER_REGISTRY)
    except Exception as exc:
        return {
            "status": "unavailable",
            "source": {"requested": requested_source, "detected": detected_source, "effective": None},
            "error": str(exc),
        }

    for loader_cls in candidates:
        effective_source = getattr(loader_cls, "name", "")
        source_payload = _source_payload(requested_source, detected_source, effective_source)
        try:
            loader = loader_cls()
        except Exception as exc:
            errors.append(f"{effective_source or loader_cls.__name__}: construct failed: {exc}")
            continue

        try:
            if not loader.is_available():
                errors.append(f"{effective_source or loader_cls.__name__}: unavailable")
                continue
        except Exception as exc:
            errors.append(f"{effective_source or loader_cls.__name__}: availability check failed: {exc}")
            continue

        try:
            data_map = loader.fetch([symbol], start_date, end_date, interval=interval)
        except Exception as exc:
            errors.append(f"{effective_source or loader_cls.__name__}: fetch failed: {exc}")
            continue

        frame = data_map.get(symbol)
        if frame is None or getattr(frame, "empty", True):
            errors.append(f"{effective_source or loader_cls.__name__}: no bars returned for {symbol}")
            continue

        rows = _frame_rows(frame, start_date=start_date, end_date=end_date)
        if not rows:
            errors.append(f"{effective_source or loader_cls.__name__}: no usable OHLCV rows returned for {symbol} inside requested window")
            continue

        return {
            "status": "ok",
            "source": source_payload,
            "rows": rows,
        }

    return {
        "status": "blocked",
        "source": {"requested": requested_source, "detected": detected_source, "effective": None},
        "error": "; ".join(errors) or f"no usable OHLCV rows returned for {symbol}",
    }


def _candidate_loaders(
    detected_source: str,
    first_loader_cls: type,
    *,
    fallback_chains: dict[str, list[str]],
    registry: dict[str, type],
) -> list[type]:
    candidates: list[type] = []
    seen: set[str] = set()

    def add(loader_cls: type | None) -> None:
        if loader_cls is None:
            return
        name = str(getattr(loader_cls, "name", "") or loader_cls.__name__)
        if name in seen:
            return
        seen.add(name)
        candidates.append(loader_cls)

    add(first_loader_cls)
    source_cls = registry.get(detected_source)
    markets = set(getattr(source_cls, "markets", set()) or getattr(first_loader_cls, "markets", set()) or set())
    for market in markets:
        for fallback_name in fallback_chains.get(market, []):
            add(registry.get(fallback_name))
    return candidates


def _frame_rows(frame: Any, *, start_date: str | None = None, end_date: str | None = None) -> list[dict[str, Any]]:
    min_date = _parse_date(start_date) if start_date else None
    max_date = _parse_date(end_date) if end_date else None
    rows: list[dict[str, Any]] = []
    for index, row in frame.sort_index().iterrows():
        row_date_text = _date_text(index)
        row_date = _parse_date(row_date_text)
        if row_date is not None:
            if min_date is not None and row_date < min_date:
                continue
            if max_date is not None and row_date > max_date:
                continue
        item = {
            "date": row_date_text,
            "open": _safe_float(row.get("open")),
            "high": _safe_float(row.get("high")),
            "low": _safe_float(row.get("low")),
            "close": _safe_float(row.get("close")),
            "volume": _safe_float(row.get("volume")),
        }
        if item["date"] and item["close"] is not None:
            rows.append(item)
    return rows


def _series_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [row["close"] for row in rows if isinstance(row.get("close"), (int, float))]
    volumes = [row["volume"] for row in rows if isinstance(row.get("volume"), (int, float))]
    returns = _returns(closes)
    return {
        "first_date": rows[0]["date"] if rows else None,
        "last_date": rows[-1]["date"] if rows else None,
        "bars": len(rows),
        "first_close": closes[0] if closes else None,
        "last_close": closes[-1] if closes else None,
        "total_return": _pct_change(closes[0], closes[-1]) if len(closes) >= 2 else None,
        "return_5d": _trailing_return(closes, 5),
        "return_20d": _trailing_return(closes, 20),
        "volatility_20d_annualized": _annualized_vol(returns[-20:]),
        "max_drawdown": _max_drawdown(closes),
        "avg_volume_20d": _mean(volumes[-20:]),
    }


def _technical_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    closes = [row["close"] for row in rows if isinstance(row.get("close"), (int, float))]
    sma20 = _mean(closes[-20:])
    sma50 = _mean(closes[-50:])
    last_close = closes[-1] if closes else None
    return {
        "sma_20": sma20,
        "sma_50": sma50,
        "last_close_vs_sma20": _pct_change(sma20, last_close) if sma20 and last_close else None,
        "last_close_vs_sma50": _pct_change(sma50, last_close) if sma50 and last_close else None,
        "trend_state": _trend_state(last_close, sma20, sma50),
    }


def _event_window(rows: list[dict[str, Any]], *, as_of_date: date, pre_days: int, post_days: int) -> dict[str, Any]:
    pre_start = as_of_date - timedelta(days=pre_days)
    pre_rows = _rows_between(rows, pre_start, as_of_date)
    post_rows = _rows_between(rows, as_of_date, as_of_date + timedelta(days=post_days)) if post_days > 0 else []
    return {
        "as_of": as_of_date.isoformat(),
        "pre_window_start": pre_start.isoformat(),
        "pre_window_days": pre_days,
        "pre_window_return": _window_return(pre_rows),
        "post_window_days": post_days,
        "post_window_return": _window_return(post_rows) if post_days > 0 else None,
        "retrospective_validation": post_days > 0,
    }


def _benchmark_comparison(target_summary: dict[str, Any], benchmark_summary: dict[str, Any]) -> dict[str, Any]:
    target_return = target_summary.get("total_return")
    benchmark_return = benchmark_summary.get("total_return")
    excess = None
    if isinstance(target_return, (int, float)) and isinstance(benchmark_return, (int, float)):
        excess = target_return - benchmark_return
    return {
        "target_total_return": target_return,
        "benchmark_total_return": benchmark_return,
        "excess_return": excess,
    }


def _base_payload(
    *,
    target: str,
    normalized_target: str,
    market: str,
    as_of: str,
    lookback_days: int,
    pre_as_of_days: int,
    post_as_of_days: int,
    interval: str,
) -> dict[str, Any]:
    return {
        "schema_version": SCHEMA_VERSION,
        "status": "blocked",
        "target": target,
        "normalized_target": normalized_target,
        "market": market,
        "as_of": as_of,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "lookback_days": lookback_days,
        "pre_as_of_days": pre_as_of_days,
        "post_as_of_days": post_as_of_days,
        "interval": interval,
        "usage": "Vibe loader-backed market context only. Not Moirix source-lake evidence and not a broker order.",
        "authority": _false_authority(),
        "claim_gate": {"blockers": ["moirix_market_context_not_yet_loaded"]},
    }


def _write_payload(out_dir: Any, payload: dict[str, Any]) -> None:
    path = out_dir / "market_context.json"
    payload["artifacts"] = {"market_context": str(path)}
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def _blocked(code: str, message: str) -> dict[str, Any]:
    payload = _blocked_fields(code, message)
    payload.update({"schema_version": SCHEMA_VERSION, "status": "blocked"})
    return payload


def _blocked_fields(code: str, message: str) -> dict[str, Any]:
    return {
        "status": "blocked",
        "claim_gate": {"blockers": [code]},
        "blocker": {"code": code, "message": message},
        "authority": _false_authority(),
    }


def _false_authority() -> dict[str, bool]:
    return {
        "research_only": True,
        "paper_trade_proposal_allowed": False,
        "broker_submit_allowed": False,
        "ready_for_real_money_trading_authority": False,
    }


def _source_payload(requested: str, detected: str, effective: str) -> dict[str, Any]:
    return {
        "requested": requested,
        "detected": detected,
        "effective": effective,
        "fallback_used": requested != effective and detected != effective,
    }


def _normalize_symbol_for_market(symbol: str, market: str) -> str:
    text = symbol.strip()
    upper = text.upper()
    market_key = market.strip().lower().replace("_", "-")
    if not upper or "." in upper or "-" in upper or "/" in upper or upper.startswith("^"):
        return upper
    if market_key in {"us", "usa", "us-equity"} and upper.isalpha():
        return f"{upper}.US"
    if market_key in {"hk", "hong-kong", "hk-equity"} and upper.isdigit():
        return f"{upper}.HK"
    return upper


def _returns(closes: list[float]) -> list[float]:
    values: list[float] = []
    for prev, current in zip(closes, closes[1:]):
        if prev:
            values.append((current / prev) - 1.0)
    return values


def _pct_change(start: float | None, end: float | None) -> float | None:
    if start in (None, 0) or end is None:
        return None
    return (end / start) - 1.0


def _trailing_return(closes: list[float], bars: int) -> float | None:
    if len(closes) <= bars:
        return None
    return _pct_change(closes[-bars - 1], closes[-1])


def _annualized_vol(returns: list[float]) -> float | None:
    if len(returns) < 2:
        return None
    mean = sum(returns) / len(returns)
    variance = sum((value - mean) ** 2 for value in returns) / (len(returns) - 1)
    return math.sqrt(variance) * math.sqrt(252)


def _max_drawdown(closes: list[float]) -> float | None:
    if not closes:
        return None
    peak = closes[0]
    max_dd = 0.0
    for close in closes:
        peak = max(peak, close)
        if peak:
            max_dd = min(max_dd, (close / peak) - 1.0)
    return max_dd


def _mean(values: list[float]) -> float | None:
    clean = [value for value in values if isinstance(value, (int, float)) and math.isfinite(value)]
    if not clean:
        return None
    return sum(clean) / len(clean)


def _trend_state(last_close: float | None, sma20: float | None, sma50: float | None) -> str:
    if last_close is None or sma20 is None:
        return "unknown"
    if sma50 is not None and last_close > sma20 > sma50:
        return "uptrend"
    if sma50 is not None and last_close < sma20 < sma50:
        return "downtrend"
    if last_close > sma20:
        return "above_sma20"
    if last_close < sma20:
        return "below_sma20"
    return "neutral"


def _rows_between(rows: list[dict[str, Any]], start: date, end: date) -> list[dict[str, Any]]:
    output = []
    for row in rows:
        row_date = _parse_date(row.get("date"))
        if row_date is not None and start <= row_date <= end:
            output.append(row)
    return output


def _window_return(rows: list[dict[str, Any]]) -> float | None:
    closes = [row["close"] for row in rows if isinstance(row.get("close"), (int, float))]
    if len(closes) < 2:
        return None
    return _pct_change(closes[0], closes[-1])


def _parse_date(value: Any) -> date | None:
    text = "" if value is None else str(value).strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except ValueError:
        try:
            return date.fromisoformat(text[:10])
        except ValueError:
            return None


def _date_text(value: Any) -> str:
    if hasattr(value, "date"):
        try:
            return value.date().isoformat()
        except Exception:
            pass
    if hasattr(value, "isoformat"):
        return value.isoformat()[:10]
    return str(value)[:10]


def _safe_float(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(number):
        return None
    return number
