"""Fail-closed execution gate for Moirix trade proposals."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.agent.tools import BaseTool
from src.tools._moirix_adapter import adapter_artifact_dir, resolve_adapter_input
from src.trading.idempotency import run_once
from src.trading.paper_audit import write_paper_action
from src.trading.paper_gate import build_paper_request, validate_paper_gate
from src.trading.service import place_order


class MoirixTradeExecutionTool(BaseTool):
    """Execute an explicitly approved paper trade proposal, fail-closed."""

    name = "moirix_execute_trade_proposal"
    description = (
        "Read artifacts/moirix/trade_proposal.json and, only when an explicit "
        "execution approval artifact references the exact proposal hash and grants "
        "paper execution authority, submit paper orders through an existing Vibe "
        "trading connector. Live execution is blocked in this Moirix v1 gate. "
        "Without approval this writes blocked execution_status.json and never "
        "calls a broker."
    )
    parameters = {
        "type": "object",
        "properties": {
            "execution_mode": {
                "type": "string",
                "enum": ["paper", "live"],
                "description": "Requested execution mode. v1 allows only paper when explicitly approved.",
                "default": "paper",
            },
            "approval_path": {
                "type": "string",
                "description": "Explicit execution approval JSON path under the current run or allowed import roots.",
            },
            "proposal_path": {
                "type": "string",
                "description": "Optional proposal path. Defaults to artifacts/moirix/trade_proposal.json.",
            },
            "connection": {
                "type": "string",
                "description": "Trading connector profile id. Must be a non-readonly paper profile with orders.place.",
            },
            "account": {
                "type": "string",
                "description": "Optional account code bound to the approval artifact and broker request.",
            },
            "dry_run": {
                "type": "boolean",
                "description": "When true, validates and writes execution_status.json without placing orders.",
                "default": True,
            },
        },
        "required": ["approval_path"],
    }
    repeatable = False
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        run_dir = kwargs.get("run_dir")
        if not run_dir:
            return json.dumps(
                {"status": "error", "error": "run_dir is required for moirix_execute_trade_proposal artifacts"},
                ensure_ascii=False,
            )

        try:
            out_dir = adapter_artifact_dir(str(run_dir))
        except ValueError as exc:
            return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)

        proposal_path, proposal_error = self._resolve_proposal(kwargs, str(run_dir))
        if proposal_error is not None or proposal_path is None:
            payload = _blocked("moirix_trade_proposal_missing", "trade proposal could not be resolved", proposal_error)
            return _write_and_return(out_dir, payload)

        approval_path, approval_error = resolve_adapter_input(
            kwargs.get("approval_path"),
            str(run_dir),
            blocker_prefix="moirix_execution_approval",
        )
        if approval_error is not None or approval_path is None:
            payload = _blocked("moirix_execution_approval_missing", "explicit execution approval is required", approval_error)
            return _write_and_return(out_dir, payload)

        try:
            proposal_bytes = proposal_path.read_bytes()
            proposal = json.loads(proposal_bytes.decode("utf-8"))
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            payload = _blocked("moirix_execution_invalid_json", f"proposal JSON is invalid: {exc}")
            return _write_and_return(out_dir, payload)
        if not isinstance(proposal, dict):
            payload = _blocked("moirix_execution_invalid_shape", "proposal must be a JSON object")
            return _write_and_return(out_dir, payload)

        proposal_hash = hashlib.sha256(proposal_bytes).hexdigest()
        execution_mode = str(kwargs.get("execution_mode") or "paper").strip().lower()
        dry_run = bool(kwargs.get("dry_run", True))
        blockers = _execution_blockers(
            proposal=proposal,
            execution_mode=execution_mode,
        )
        request = build_paper_request(
            operation=self.name,
            connection=str(kwargs.get("connection") or "").strip(),
            account=str(kwargs.get("account") or "").strip(),
            actions=proposal.get("orders") if isinstance(proposal.get("orders"), list) else [],
            proposal_sha256=proposal_hash,
        )
        gate = validate_paper_gate(
            approval_path=approval_path,
            request=request,
            required_capabilities=("orders.place",),
            allowed_roots=[Path(run_dir)],
        )
        blockers.extend(gate.blockers)
        if blockers:
            payload = _blocked(
                "moirix_execution_gate_blocked",
                "trade proposal did not pass the execution gate",
                extra={"blockers": blockers, "proposal_sha256": proposal_hash, "gate_decision": gate.decision()},
            )
            _audit(
                payload,
                request=request,
                gate=gate.decision(),
                tool_name=self.name,
                run_dir=str(run_dir),
                outcome="blocked",
            )
            return _write_and_return(out_dir, payload)

        if dry_run:
            payload = _status(
                status="dry_run",
                proposal_hash=proposal_hash,
                execution_mode=execution_mode,
                connection=str(kwargs.get("connection") or "").strip(),
                gate_decision=gate.decision(),
                broker_results=[],
            )
            _audit(
                payload,
                request=request,
                gate=gate.decision(),
                tool_name=self.name,
                run_dir=str(run_dir),
                outcome="dry_run",
            )
            return _write_and_return(out_dir, payload)

        def _execute() -> dict[str, Any]:
            broker_results = []
            for order in proposal.get("orders", []):
                if not isinstance(order, dict):
                    continue
                result = place_order(
                    str(order.get("symbol") or ""),
                    str(kwargs.get("connection") or "").strip(),
                    side=str(order.get("side") or ""),
                    quantity=_num_or_none(order.get("quantity")),
                    notional=_num_or_none(order.get("notional")),
                    order_type=str(order.get("order_type") or "market"),
                    limit_price=_num_or_none(order.get("limit_price")),
                    time_in_force=str(order.get("time_in_force") or "day"),
                    account=str(kwargs.get("account") or "").strip() or None,
                )
                broker_results.append(result)
                if str(result.get("status") or "").lower() == "error":
                    break
            status = "ok" if broker_results and all(str(item.get("status") or "").lower() != "error" for item in broker_results) else "blocked"
            payload = _status(
                status=status,
                proposal_hash=proposal_hash,
                execution_mode=execution_mode,
                connection=str(kwargs.get("connection") or "").strip(),
                gate_decision=gate.decision(),
                broker_results=broker_results,
            )
            if status != "ok":
                payload["claim_gate"]["blockers"].append("moirix_execution_broker_rejected_or_unavailable")
            _audit(
                payload,
                request=request,
                gate=gate.decision(),
                tool_name=self.name,
                run_dir=str(run_dir),
                outcome="accepted" if status == "ok" else "blocked",
            )
            return payload

        payload = run_once(
            tool_name=self.name,
            request=request,
            idempotency_key=gate.idempotency_key,
            execute=_execute,
        )
        return _write_and_return(out_dir, payload)

    def _resolve_proposal(self, kwargs: dict[str, Any], run_dir: str) -> tuple[Path | None, dict[str, Any] | None]:
        proposal_path = str(kwargs.get("proposal_path") or "").strip()
        if proposal_path:
            return resolve_adapter_input(
                proposal_path,
                run_dir,
                blocker_prefix="moirix_trade_proposal",
            )
        return resolve_adapter_input(
            None,
            run_dir,
            default_relative="artifacts/moirix/trade_proposal.json",
            blocker_prefix="moirix_trade_proposal",
        )


def _execution_blockers(
    *,
    proposal: dict[str, Any],
    execution_mode: str,
) -> list[str]:
    blockers: list[str] = []
    if execution_mode != "paper":
        blockers.append("moirix_live_execution_blocked_in_v1")
    authority = proposal.get("authority") if isinstance(proposal.get("authority"), dict) else {}
    if authority.get("paper_trade_proposal_allowed") is True:
        blockers.append("moirix_proposal_claims_paper_execution_authority")
    if authority.get("broker_submit_allowed") is True:
        blockers.append("moirix_proposal_claims_broker_submit_authority")
    if authority.get("ready_for_real_money_trading_authority") is True:
        blockers.append("moirix_proposal_claims_real_money_authority")
    orders = proposal.get("orders")
    if not isinstance(orders, list) or not orders:
        blockers.append("moirix_proposal_has_no_orders")
    return blockers


def _status(
    *,
    status: str,
    proposal_hash: str,
    execution_mode: str,
    connection: str,
    gate_decision: dict[str, Any],
    broker_results: list[dict[str, Any]],
) -> dict[str, Any]:
    return {
        "schema_version": "vibe.moirix_trade_execution_status.v1",
        "status": status,
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "proposal_sha256": proposal_hash,
        "execution_mode": execution_mode,
        "connection": connection,
        "broker_results": broker_results,
        "gate_decision": gate_decision,
        "claim_gate": {
            "blockers": [],
            "ready_for_real_money_trading_authority": False,
            "broker_submit_allowed": status == "ok",
        },
        "authority": {
            "research_only": status != "ok",
            "paper_trade_proposal_allowed": status in {"ok", "dry_run"},
            "broker_submit_allowed": status == "ok",
            "ready_for_real_money_trading_authority": False,
        },
    }


def _blocked(blocker: str, message: str, detail: dict[str, Any] | None = None, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "vibe.moirix_trade_execution_status.v1",
        "status": "blocked",
        "generated_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "error": message,
        "detail": detail or {},
        "claim_gate": {
            "blockers": [blocker],
            "ready_for_real_money_trading_authority": False,
            "broker_submit_allowed": False,
        },
        "authority": {
            "research_only": True,
            "paper_trade_proposal_allowed": False,
            "broker_submit_allowed": False,
            "ready_for_real_money_trading_authority": False,
        },
    }
    if extra:
        payload.update(extra)
        if isinstance(extra.get("blockers"), list):
            payload["claim_gate"]["blockers"].extend(str(item) for item in extra["blockers"])
    return payload


def _write_and_return(out_dir: Path, payload: dict[str, Any]) -> str:
    path = out_dir / "execution_status.json"
    payload.setdefault("artifacts", {})["execution_status"] = str(path)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return json.dumps(payload, ensure_ascii=False, default=str)


def _audit(
    payload: dict[str, Any],
    *,
    request: dict[str, Any],
    gate: dict[str, Any],
    tool_name: str,
    run_dir: str,
    outcome: str,
) -> None:
    try:
        record = write_paper_action(
            kind="moirix_trade_execution",
            outcome=outcome,
            profile_id=str(request.get("connection") or "") or None,
            request=request,
            response=payload,
            gate_decision=gate,
            approval_id=str(gate.get("approval_id") or "") or None,
            tool_name=tool_name,
            run_dir=run_dir,
        )
        payload.setdefault("artifacts", {})["paper_audit_id"] = str(record.get("audit_id") or "")
    except Exception as exc:  # noqa: BLE001 - failed audit must be visible and fail closed
        payload.setdefault("claim_gate", {}).setdefault("blockers", []).append("paper_audit_write_failed")
        payload["audit_error"] = str(exc)


def _num_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)
