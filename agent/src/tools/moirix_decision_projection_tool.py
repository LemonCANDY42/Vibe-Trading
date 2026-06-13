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

        rows = _projection_rows(decision, proposal, projection_mode)
        csv_path = out_dir / "decision_projection.csv"
        json_path = out_dir / "decision_projection.json"
        manifest_path = out_dir / "backtest_projection_manifest.json"

        _write_csv(csv_path, rows)
        json_payload = {
            "schema_version": SCHEMA_VERSION,
            "status": "ok",
            "generated_at": _now(),
            "projection_mode": projection_mode,
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
            "source_artifacts": {
                "position_decision": str(decision_path),
                "trade_proposal": str(proposal_path) if proposal_path.is_file() else None,
            },
            "source_sha256": hashlib.sha256(decision_bytes).hexdigest(),
            "artifacts": {
                "decision_projection_csv": str(csv_path),
                "decision_projection_json": str(json_path),
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


def _projection_rows(decision: dict[str, Any], proposal: dict[str, Any], projection_mode: str) -> list[dict[str, Any]]:
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
        rows.append(
            {
                "known_at": known_at,
                "symbol": symbol,
                "action": action,
                "side": str(order.get("side") or _side_from_action(action) or ""),
                "quantity": order.get("quantity", ""),
                "notional": order.get("notional", ""),
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


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "known_at",
        "symbol",
        "action",
        "side",
        "quantity",
        "notional",
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
