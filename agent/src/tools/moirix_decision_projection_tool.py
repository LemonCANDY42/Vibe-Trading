"""Export Moirix position decisions into backtest projection artifacts."""

from __future__ import annotations

import csv
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.agent.tools import BaseTool
from src.tools._moirix_adapter import adapter_artifact_dir, resolve_adapter_input


SCHEMA_VERSION = "vibe.moirix_decision_projection.v1"
MANIFEST_SCHEMA_VERSION = "vibe.moirix_backtest_projection_manifest.v1"


class MoirixDecisionProjectionTool(BaseTool):
    """Write a research-only backtest projection from a position decision."""

    name = "moirix_export_decision_projection"
    description = (
        "Export artifacts/moirix/position_decision.json and trade_proposal.json into "
        "research-only backtest projection artifacts. This is a Vibe-side projection "
        "for backtesting decisions, not a Moirix evidence output and not an order."
    )
    parameters = {
        "type": "object",
        "properties": {
            "decision_path": {
                "type": "string",
                "description": "Optional decision JSON path. Defaults to artifacts/moirix/position_decision.json.",
            },
            "projection_mode": {
                "type": "string",
                "enum": ["single_day", "window"],
                "description": "single_day emits known_at only; window includes execution_window start/end.",
                "default": "window",
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
                {"status": "error", "error": "run_dir is required for moirix_export_decision_projection artifacts"},
                ensure_ascii=False,
            )

        try:
            out_dir = adapter_artifact_dir(str(run_dir))
        except ValueError as exc:
            return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)

        decision_path, error = self._resolve_decision(kwargs, str(run_dir))
        if error is not None or decision_path is None:
            return json.dumps(
                _blocked("moirix_position_decision_missing", "position decision could not be resolved", error),
                ensure_ascii=False,
            )

        proposal_path = out_dir / "trade_proposal.json"
        try:
            decision_bytes = decision_path.read_bytes()
            decision = json.loads(decision_bytes.decode("utf-8"))
            proposal = _load_json(proposal_path) or {}
            context = _load_decision_context(decision, out_dir) or {}
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            return json.dumps(_blocked("moirix_decision_projection_invalid_json", str(exc)), ensure_ascii=False)

        if not isinstance(decision, dict):
            return json.dumps(_blocked("moirix_decision_projection_invalid_shape", "position decision must be an object"), ensure_ascii=False)
        if _claims_broker_authority(decision) or _claims_broker_authority(proposal):
            return json.dumps(
                _blocked(
                    "moirix_decision_projection_authority_violation",
                    "decision projection requires research-only proposal authority",
                ),
                ensure_ascii=False,
            )

        projection_mode = str(kwargs.get("projection_mode") or "window").strip().lower()
        if projection_mode not in {"single_day", "window"}:
            return json.dumps(_blocked("moirix_decision_projection_invalid_mode", "projection_mode must be single_day or window"), ensure_ascii=False)

        projection_context = _projection_context(decision, context)
        rows = _projection_rows(decision, proposal, projection_mode, projection_context)
        csv_path = out_dir / "decision_projection.csv"
        json_path = out_dir / "decision_projection.json"
        manifest_path = out_dir / "backtest_projection_manifest.json"
        signal_engine_path = out_dir / "decision_projection_signal_engine.py"

        _write_csv(csv_path, rows)
        _write_signal_engine_template(signal_engine_path)
        json_payload = {
            "schema_version": SCHEMA_VERSION,
            "status": "ok",
            "generated_at": _now(),
            "projection_mode": projection_mode,
            "projection_context": projection_context,
            "rows": rows,
            "authority": _false_authority(),
        }
        json_path.write_text(json.dumps(json_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        manifest = {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "status": "ok",
            "generated_at": _now(),
            "projection_mode": projection_mode,
            "row_count": len(rows),
            "projection_context": projection_context,
            "source_artifacts": {
                "position_decision": str(decision_path),
                "trade_proposal": str(proposal_path) if proposal_path.is_file() else None,
                "event_decision_context": projection_context.get("event_decision_context_path"),
            },
            "source_sha256": hashlib.sha256(decision_bytes).hexdigest(),
            "artifacts": {
                "decision_projection_csv": str(csv_path),
                "decision_projection_json": str(json_path),
                "decision_projection_signal_engine": str(signal_engine_path),
            },
            "vibe_backtest_consumer": {
                "type": "signal_engine_template",
                "template_path": str(signal_engine_path),
                "instructions": (
                    "Copy or symlink this template as code/signal_engine.py in a Vibe backtest run "
                    "that also contains artifacts/moirix/decision_projection.csv."
                ),
            },
            "usage": "Backtest projection only. Not a broker order and not Moirix evidence.",
            "authority": _false_authority(),
        }
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        _merge_run_card_patch(out_dir)

        return json.dumps(
            {
                "schema_version": "vibe.moirix_decision_projection_export.v1",
                "status": "ok",
                "row_count": len(rows),
                "projection_mode": projection_mode,
                "artifacts": {
                    "decision_projection_csv": str(csv_path),
                    "decision_projection_json": str(json_path),
                    "backtest_projection_manifest": str(manifest_path),
                    "decision_projection_signal_engine": str(signal_engine_path),
                },
                "authority": _false_authority(),
                "claim_gate": {
                    "blockers": [],
                    "broker_submit_allowed": False,
                    "ready_for_real_money_trading_authority": False,
                },
            },
            ensure_ascii=False,
        )

    def _resolve_decision(self, kwargs: dict[str, Any], run_dir: str) -> tuple[Path | None, dict[str, Any] | None]:
        decision_path = str(kwargs.get("decision_path") or "").strip()
        if decision_path:
            return resolve_adapter_input(decision_path, run_dir, blocker_prefix="moirix_position_decision")
        return resolve_adapter_input(
            None,
            run_dir,
            default_relative="artifacts/moirix/position_decision.json",
            blocker_prefix="moirix_position_decision",
        )


def _projection_rows(
    decision: dict[str, Any],
    proposal: dict[str, Any],
    projection_mode: str,
    projection_context: dict[str, Any],
) -> list[dict[str, Any]]:
    orders = proposal.get("orders") if isinstance(proposal.get("orders"), list) else decision.get("proposed_orders")
    if not isinstance(orders, list):
        orders = []
    if not orders:
        orders = [{}]
    window = decision.get("execution_window") if isinstance(decision.get("execution_window"), dict) else {}
    known_at = str(decision.get("as_of") or window.get("start") or "")
    rows: list[dict[str, Any]] = []
    for order in orders:
        order = order if isinstance(order, dict) else {}
        symbol = str(order.get("symbol") or decision.get("target") or "").strip()
        action = str(decision.get("action") or "watch").strip().lower()
        target_weight = _target_weight(decision, order, action, symbol, projection_context)
        rows.append(
            {
                "known_at": known_at,
                "symbol": symbol,
                "action": action,
                "side": str(order.get("side") or _side_from_action(action) or ""),
                "quantity": order.get("quantity", ""),
                "notional": order.get("notional", ""),
                "target_weight": target_weight if target_weight is not None else "",
                "max_position_notional": _risk_number(decision, "max_position_notional") or "",
                "max_loss_notional": _risk_number(decision, "max_loss_notional") or "",
                "weight_basis": _row_weight_basis(action, target_weight, projection_context),
                "order_type": str(order.get("order_type") or ""),
                "limit_price": order.get("limit_price", ""),
                "time_in_force": str(order.get("time_in_force") or ""),
                "window_start": "" if projection_mode == "single_day" else str(window.get("start") or ""),
                "window_end": "" if projection_mode == "single_day" else str(window.get("end") or ""),
                "projection_mode": projection_mode,
                "research_only": True,
                "paper_trade_proposal_allowed": False,
                "broker_submit_allowed": False,
                "ready_for_real_money_trading_authority": False,
                "source_schema": str(decision.get("schema_version") or ""),
                "rationale": str(decision.get("rationale") or "")[:1000],
            }
        )
    return rows


def _side_from_action(action: str) -> str:
    if action in {"buy", "add", "cover"}:
        return "buy"
    if action in {"sell", "trim", "exit", "short"}:
        return "sell"
    return ""


def _load_decision_context(decision: dict[str, Any], out_dir: Path) -> dict[str, Any] | None:
    source_artifacts = decision.get("source_artifacts") if isinstance(decision.get("source_artifacts"), dict) else {}
    raw_path = source_artifacts.get("event_decision_context")
    candidates = []
    if isinstance(raw_path, str) and raw_path.strip():
        candidates.append(Path(raw_path).expanduser())
    candidates.append(out_dir / "event_decision_context.json")
    for path in candidates:
        try:
            if path.is_file():
                value = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    value["_path"] = str(path)
                    return value
        except (OSError, json.JSONDecodeError):
            continue
    return None


def _projection_context(decision: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    portfolio_base = _portfolio_base(context)
    explicit_target_weight = _risk_number(decision, "target_weight")
    max_position_notional = _risk_number(decision, "max_position_notional")
    if explicit_target_weight is not None:
        sizing_mode = "explicit_target_weight"
        weight_basis = "risk_sizing.target_weight"
    elif portfolio_base and max_position_notional:
        sizing_mode = "risk_sizing_target_weight"
        weight_basis = "max_position_notional/portfolio_base"
    else:
        sizing_mode = "direction_only"
        weight_basis = "direction_only"
    return {
        "sizing_mode": sizing_mode,
        "portfolio_base": portfolio_base,
        "weight_basis": weight_basis,
        "event_decision_context_path": context.get("_path") if isinstance(context.get("_path"), str) else None,
        "positions": _position_snapshots(context),
    }


def _portfolio_base(context: dict[str, Any]) -> float | None:
    summary = context.get("account_summary")
    candidates: list[Any] = []
    if isinstance(summary, dict):
        for key in (
            "NetLiquidation",
            "NetLiquidation_USD",
            "EquityWithLoanValue",
            "EquityWithLoanValue_USD",
            "TotalCashValue",
            "AvailableFunds",
            "AvailableFunds_USD",
            "cash",
            "portfolio_value",
            "equity",
        ):
            candidates.append(summary.get(key))
    for value in candidates:
        number = _float_or_none(value)
        if number is not None and number > 0:
            return number
    return None


def _target_weight(
    decision: dict[str, Any],
    order: dict[str, Any],
    action: str,
    symbol: str,
    projection_context: dict[str, Any],
) -> float | None:
    explicit = _float_or_none((decision.get("risk_sizing") or {}).get("target_weight")) if isinstance(decision.get("risk_sizing"), dict) else None
    if explicit is not None:
        return max(-1.0, min(1.0, explicit))
    portfolio_base = _float_or_none(projection_context.get("portfolio_base"))
    max_notional = _risk_number(decision, "max_position_notional")
    order_notional = _float_or_none(order.get("notional"))
    target_notional = max_notional
    if order_notional is not None and order_notional > 0:
        target_notional = min(order_notional, max_notional) if max_notional else order_notional
    if portfolio_base is None or portfolio_base <= 0 or target_notional is None or target_notional <= 0:
        return None
    magnitude = min(abs(target_notional) / portfolio_base, 1.0)
    if action == "short":
        return -magnitude
    if action in {"buy", "add"}:
        return magnitude
    if action == "exit" or action in {"hold", "watch", "blocked"}:
        return 0.0
    if action in {"sell", "trim"}:
        current_weight = _current_position_weight(symbol, projection_context)
        if current_weight is None or current_weight <= 0:
            return None
        return max(0.0, current_weight - magnitude)
    if action == "cover":
        current_weight = _current_position_weight(symbol, projection_context)
        if current_weight is None or current_weight >= 0:
            return None
        return min(0.0, current_weight + magnitude)
    return None


def _row_weight_basis(action: str, target_weight: float | None, projection_context: dict[str, Any]) -> str:
    if target_weight is not None:
        return str(projection_context.get("weight_basis") or "direction_only")
    if action in {"sell", "trim", "cover"}:
        return "current_position_required"
    return str(projection_context.get("weight_basis") or "direction_only")


def _position_snapshots(context: dict[str, Any]) -> list[dict[str, Any]]:
    rows = context.get("positions")
    if not isinstance(rows, list):
        return []
    snapshots: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        symbol = str(row.get("symbol") or row.get("ticker") or row.get("contract_symbol") or "").strip()
        if not symbol:
            continue
        quantity = _float_or_none(row.get("position") or row.get("qty") or row.get("quantity"))
        market_value = _float_or_none(
            row.get("market_value")
            or row.get("marketValue")
            or row.get("market_value_usd")
            or row.get("position_value")
            or row.get("positionValue")
        )
        avg_cost = _float_or_none(row.get("avg_cost") or row.get("avgCost") or row.get("average_cost"))
        last_price = _float_or_none(row.get("last_price") or row.get("lastPrice") or row.get("market_price"))
        if market_value is None and quantity is not None:
            reference_price = last_price if last_price is not None else avg_cost
            if reference_price is not None:
                market_value = quantity * reference_price
        snapshots.append(
            {
                "symbol": symbol,
                "quantity": quantity,
                "market_value": market_value,
            }
        )
    return snapshots


def _current_position_weight(symbol: str, projection_context: dict[str, Any]) -> float | None:
    portfolio_base = _float_or_none(projection_context.get("portfolio_base"))
    if portfolio_base is None or portfolio_base <= 0:
        return None
    rows = projection_context.get("positions")
    if not isinstance(rows, list):
        return None
    symbol_upper = symbol.upper()
    for row in rows:
        if not isinstance(row, dict):
            continue
        if str(row.get("symbol") or "").upper() != symbol_upper:
            continue
        market_value = _float_or_none(row.get("market_value"))
        if market_value is None:
            return None
        return max(-1.0, min(1.0, market_value / portfolio_base))
    return None


def _risk_number(decision: dict[str, Any], key: str) -> float | None:
    risk = decision.get("risk_sizing") if isinstance(decision.get("risk_sizing"), dict) else {}
    return _float_or_none(risk.get(key))


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "known_at",
        "symbol",
        "action",
        "side",
        "quantity",
        "notional",
        "target_weight",
        "max_position_notional",
        "max_loss_notional",
        "weight_basis",
        "order_type",
        "limit_price",
        "time_in_force",
        "window_start",
        "window_end",
        "projection_mode",
        "research_only",
        "paper_trade_proposal_allowed",
        "broker_submit_allowed",
        "ready_for_real_money_trading_authority",
        "source_schema",
        "rationale",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _write_signal_engine_template(path: Path) -> None:
    path.write_text(
        '''"""Vibe signal engine template for Moirix decision_projection.csv."""

from pathlib import Path

import pandas as pd


PROJECTION_CSV = "artifacts/moirix/decision_projection.csv"


class SignalEngine:
    """Convert research-only Moirix decision projection rows into backtest signals."""

    def generate(self, data_map):
        projection_path = Path(PROJECTION_CSV)
        if not projection_path.is_absolute():
            projection_path = Path(__file__).resolve().parents[1] / projection_path
        projection = pd.read_csv(projection_path)
        output = {}
        for symbol, data in data_map.items():
            index = pd.to_datetime(data.index)
            signal = pd.Series(0.0, index=index)
            rows = projection[projection["symbol"].astype(str).str.upper() == str(symbol).upper()]
            for _, row in rows.iterrows():
                start_raw = row.get("window_start") or row.get("known_at")
                end_raw = row.get("window_end") or row.get("known_at")
                if not start_raw:
                    continue
                start = pd.Timestamp(start_raw)
                end = pd.Timestamp(end_raw) if end_raw else start
                side = str(row.get("side") or "").lower()
                action = str(row.get("action") or "").lower()
                target_weight = pd.to_numeric(pd.Series([row.get("target_weight")]), errors="coerce").iloc[0]
                if pd.notna(target_weight):
                    value = float(target_weight)
                else:
                    if action in {"sell", "trim", "cover"}:
                        continue
                    value = 1.0 if side == "buy" or action in {"buy", "add"} else 0.0
                    if action == "short":
                        value = -1.0
                signal.loc[(index >= start) & (index <= end)] = value
            output[symbol] = signal
        return output
''',
        encoding="utf-8",
    )


def _merge_run_card_patch(out_dir: Path) -> None:
    path = out_dir / "vibe_run_card_patch.json"
    existing: dict[str, Any] = {}
    try:
        if path.is_file():
            loaded = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(loaded, dict):
                existing = loaded
    except (OSError, json.JSONDecodeError):
        existing = {}
    artifacts = existing.get("artifacts") if isinstance(existing.get("artifacts"), dict) else {}
    artifacts.update(
        {
            "decision_projection_csv": "artifacts/moirix/decision_projection.csv",
            "decision_projection_json": "artifacts/moirix/decision_projection.json",
            "backtest_projection_manifest": "artifacts/moirix/backtest_projection_manifest.json",
            "decision_projection_signal_engine": "artifacts/moirix/decision_projection_signal_engine.py",
        }
    )
    existing.update(
        {
            "schema_version": "vibe.moirix_run_card_patch.v1",
            "status": "ok",
            "moirix_mode": "decision_projection",
            "artifacts": artifacts,
            "authority": _false_authority(),
        }
    )
    path.write_text(json.dumps(existing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _load_json(path: Path) -> dict[str, Any] | None:
    try:
        if not path.is_file():
            return None
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return value if isinstance(value, dict) else None


def _claims_broker_authority(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    authority = value.get("authority") if isinstance(value.get("authority"), dict) else value
    return (
        authority.get("paper_trade_proposal_allowed") is True
        or authority.get("broker_submit_allowed") is True
        or authority.get("ready_for_real_money_trading_authority") is True
    )


def _false_authority() -> dict[str, bool]:
    return {
        "research_only": True,
        "paper_trade_proposal_allowed": False,
        "broker_submit_allowed": False,
        "ready_for_real_money_trading_authority": False,
    }


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _blocked(blocker: str, message: str, detail: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "schema_version": "vibe.moirix_decision_projection_export.v1",
        "status": "blocked",
        "error": message,
        "detail": detail or {},
        "claim_gate": {
            "blockers": [blocker],
            "broker_submit_allowed": False,
            "ready_for_real_money_trading_authority": False,
        },
        "authority": _false_authority(),
    }
