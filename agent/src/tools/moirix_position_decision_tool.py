"""Write Agent-synthesized Moirix position decision artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from src.agent.tools import BaseTool
from src.tools._moirix_adapter import adapter_artifact_dir
from src.tools.moirix_grounding import validate_position_decision_grounding


SCHEMA_VERSION = "vibe.moirix_position_decision.v1"
PROPOSAL_SCHEMA_VERSION = "vibe.moirix_trade_proposal.v1"
RISK_SCHEMA_VERSION = "vibe.moirix_risk_sizing.v1"
FORBIDDEN_DECISION_KEYS = {"confidence", "impact_score", "strength", "weight", "edge_weight"}
ACTIONS = {"buy", "sell", "short", "cover", "add", "trim", "exit", "hold", "watch", "hedge", "blocked"}
SIDES = {"buy", "sell"}
ORDER_TYPES = {"market", "limit"}
TIME_IN_FORCE = {"day", "gtc"}
FALSE_AUTHORITY_FIELDS = (
    "paper_trade_proposal_allowed",
    "broker_submit_allowed",
    "ready_for_real_money_trading_authority",
)


class MoirixPositionDecisionTool(BaseTool):
    """Persist a portfolio-aware decision and normalized trade proposal."""

    name = "moirix_write_position_decision"
    description = (
        "Validate and write the canonical Moirix position decision artifacts from an "
        "existing event_thesis_graph.json and event_decision_context.json. Writes "
        "position_decision.json, trade_proposal.json, risk_sizing_report.json, and "
        "portfolio_adjustment_plan.md under artifacts/moirix. This tool creates a "
        "research proposal only; it never submits orders."
    )
    parameters = {
        "type": "object",
        "properties": {
            "decision_json": {
                "type": "string",
                "description": "Position decision JSON string using schema vibe.moirix_position_decision.v1.",
            },
            "adjustment_plan_markdown": {
                "type": "string",
                "description": "Optional human-readable portfolio adjustment plan. If omitted, a concise plan is generated.",
            },
        },
        "required": ["decision_json"],
    }
    repeatable = True
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        run_dir = kwargs.get("run_dir")
        if not run_dir:
            return json.dumps(
                {"status": "error", "error": "run_dir is required for moirix_write_position_decision artifacts"},
                ensure_ascii=False,
            )

        try:
            out_dir = adapter_artifact_dir(str(run_dir))
        except ValueError as exc:
            return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)

        thesis_path = out_dir / "event_thesis_graph.json"
        context_path = out_dir / "event_decision_context.json"
        if not thesis_path.is_file() or not context_path.is_file():
            return json.dumps(
                _blocked(
                    "moirix_position_decision_inputs_missing",
                    "event_thesis_graph.json and event_decision_context.json are required before a position decision",
                ),
                ensure_ascii=False,
            )

        try:
            decision = _parse_decision(kwargs.get("decision_json"))
        except ValueError as exc:
            return json.dumps(_blocked("moirix_position_decision_invalid_json", str(exc)), ensure_ascii=False)

        errors = _validate_decision(decision)
        if errors:
            return json.dumps(
                _blocked(
                    "moirix_position_decision_schema_invalid",
                    "position decision did not satisfy the canonical schema",
                    extra={"violations": errors},
                ),
                ensure_ascii=False,
            )

        decision = _normalize_authority(decision)
        grounding_errors = validate_position_decision_grounding(out_dir, decision)
        if grounding_errors:
            return json.dumps(
                _blocked(
                    "moirix_position_decision_grounding_invalid",
                    "position decision is not grounded in ok event thesis and portfolio context artifacts",
                    extra={"violations": grounding_errors},
                ),
                ensure_ascii=False,
            )

        generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        decision.setdefault("generated_at", generated_at)
        decision.setdefault("status", "ok")
        decision.setdefault("source_artifacts", {}).update(
            {
                "event_thesis_graph": str(thesis_path),
                "event_decision_context": str(context_path),
            }
        )

        proposal = _build_trade_proposal(decision)
        risk_sizing = _build_risk_sizing(decision)
        plan = str(kwargs.get("adjustment_plan_markdown") or "").strip() or _build_plan(decision, proposal)

        decision_path = out_dir / "position_decision.json"
        proposal_path = out_dir / "trade_proposal.json"
        risk_path = out_dir / "risk_sizing_report.json"
        plan_path = out_dir / "portfolio_adjustment_plan.md"
        run_card_patch_path = out_dir / "vibe_run_card_patch.json"

        decision_path.write_text(json.dumps(decision, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        proposal_path.write_text(json.dumps(proposal, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        risk_path.write_text(json.dumps(risk_sizing, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        plan_path.write_text(plan.rstrip() + "\n", encoding="utf-8")

        run_card_patch = _merge_run_card_patch(out_dir, decision)
        run_card_patch_path.write_text(
            json.dumps(run_card_patch, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        payload = {
            "schema_version": "vibe.moirix_position_decision_write.v1",
            "status": "ok",
            "target": decision.get("target"),
            "market": decision.get("market"),
            "as_of": decision.get("as_of"),
            "artifacts": {
                "position_decision": str(decision_path),
                "trade_proposal": str(proposal_path),
                "risk_sizing_report": str(risk_path),
                "portfolio_adjustment_plan": str(plan_path),
                "vibe_run_card_patch": str(run_card_patch_path),
            },
            "authority": decision["authority"],
            "claim_gate": {
                "blockers": [],
                "ready_for_real_money_trading_authority": False,
                "broker_submit_allowed": False,
            },
        }
        return json.dumps(payload, ensure_ascii=False, default=str)


def _parse_decision(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"decision_json is not valid JSON: {exc}") from exc
    else:
        parsed = value
    if not isinstance(parsed, dict):
        raise ValueError("decision_json must be a JSON object")
    return dict(parsed)


def _validate_decision(decision: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    errors.extend(_find_forbidden_keys(decision))
    if decision.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    for key in ("target", "market", "as_of"):
        if not _nonempty_str(decision.get(key)):
            errors.append(f"{key} is required")

    action = decision.get("action")
    if action not in ACTIONS:
        errors.append(f"action must be one of {sorted(ACTIONS)}")
    for key in ("rationale", "execution_window", "invalidation_triggers", "risk_notes"):
        if key not in decision:
            errors.append(f"{key} is required")
    if not isinstance(decision.get("invalidation_triggers"), list):
        errors.append("invalidation_triggers must be a list")
    if not isinstance(decision.get("risk_notes"), list):
        errors.append("risk_notes must be a list")
    if not isinstance(decision.get("execution_window"), dict):
        errors.append("execution_window must be an object")
    else:
        for key in ("start", "end", "reason"):
            if not _nonempty_str(decision["execution_window"].get(key)):
                errors.append(f"execution_window.{key} is required")

    risk_sizing = decision.get("risk_sizing")
    if not isinstance(risk_sizing, dict):
        errors.append("risk_sizing must be an object")
    else:
        for key in ("max_position_notional", "max_loss_notional", "portfolio_impact"):
            if key not in risk_sizing:
                errors.append(f"risk_sizing.{key} is required")

    orders = decision.get("proposed_orders")
    if orders is None:
        decision["proposed_orders"] = []
    elif not isinstance(orders, list):
        errors.append("proposed_orders must be a list")
    elif len(orders) > 20:
        errors.append("proposed_orders exceeds the 20 order limit")
    else:
        for index, order in enumerate(orders):
            if not isinstance(order, dict):
                errors.append(f"proposed_orders[{index}] must be an object")
                continue
            if not _nonempty_str(order.get("symbol")):
                errors.append(f"proposed_orders[{index}].symbol is required")
            if order.get("side") not in SIDES:
                errors.append(f"proposed_orders[{index}].side must be one of {sorted(SIDES)}")
            if order.get("order_type", "market") not in ORDER_TYPES:
                errors.append(f"proposed_orders[{index}].order_type must be one of {sorted(ORDER_TYPES)}")
            if order.get("time_in_force", "day") not in TIME_IN_FORCE:
                errors.append(f"proposed_orders[{index}].time_in_force must be one of {sorted(TIME_IN_FORCE)}")
            has_quantity = _positive_number(order.get("quantity"))
            has_notional = _positive_number(order.get("notional"))
            if has_quantity and has_notional:
                errors.append(f"proposed_orders[{index}] must use quantity or notional, not both")
            if decision.get("action") not in {"hold", "watch", "blocked"} and not (has_quantity or has_notional):
                errors.append(f"proposed_orders[{index}] requires positive quantity or notional")
            if order.get("order_type", "market") == "limit" and not _positive_number(order.get("limit_price")):
                errors.append(f"proposed_orders[{index}].limit_price is required for limit orders")
    if decision.get("action") not in {"hold", "watch", "blocked"} and not decision.get("proposed_orders"):
        errors.append("proposed_orders must be non-empty for actionable decisions")

    authority = decision.get("authority")
    if authority is not None and not isinstance(authority, dict):
        errors.append("authority must be an object")
    elif isinstance(authority, dict):
        for field in FALSE_AUTHORITY_FIELDS:
            if authority.get(field) is True:
                errors.append(f"authority.{field} must remain false in position decision output")
        if authority.get("research_only") is False:
            errors.append("authority.research_only must remain true")
    return errors


def _build_trade_proposal(decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": PROPOSAL_SCHEMA_VERSION,
        "status": "proposed",
        "target": decision.get("target"),
        "market": decision.get("market"),
        "as_of": decision.get("as_of"),
        "action": decision.get("action"),
        "orders": decision.get("proposed_orders", []),
        "rationale": decision.get("rationale"),
        "source_artifacts": decision.get("source_artifacts", {}),
        "authority": decision["authority"],
        "execution_gate": {
            "requires_explicit_approval": True,
            "allowed_execution_modes": ["paper"],
            "live_execution_allowed": False,
        },
    }


def _build_risk_sizing(decision: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": RISK_SCHEMA_VERSION,
        "status": "ok",
        "target": decision.get("target"),
        "market": decision.get("market"),
        "as_of": decision.get("as_of"),
        "action": decision.get("action"),
        "risk_sizing": decision.get("risk_sizing", {}),
        "risk_notes": decision.get("risk_notes", []),
        "invalidation_triggers": decision.get("invalidation_triggers", []),
        "authority": decision["authority"],
    }


def _merge_run_card_patch(out_dir: Any, decision: dict[str, Any]) -> dict[str, Any]:
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
            "position_decision": "artifacts/moirix/position_decision.json",
            "trade_proposal": "artifacts/moirix/trade_proposal.json",
            "risk_sizing_report": "artifacts/moirix/risk_sizing_report.json",
            "portfolio_adjustment_plan": "artifacts/moirix/portfolio_adjustment_plan.md",
        }
    )
    existing.update(
        {
            "schema_version": "vibe.moirix_run_card_patch.v1",
            "status": "ok",
            "moirix_mode": "position_decision",
            "artifacts": artifacts,
            "authority": decision["authority"],
        }
    )
    return existing


def _build_plan(decision: dict[str, Any], proposal: dict[str, Any]) -> str:
    window = decision.get("execution_window") if isinstance(decision.get("execution_window"), dict) else {}
    orders = proposal.get("orders") if isinstance(proposal.get("orders"), list) else []
    lines = [
        f"# Moirix Position Decision: {decision.get('target', 'unknown')}",
        "",
        f"- Market: `{decision.get('market', 'unknown')}`",
        f"- As of: `{decision.get('as_of', 'unknown')}`",
        f"- Action: `{decision.get('action', 'unknown')}`",
        f"- Window: `{window.get('start', 'unknown')}` to `{window.get('end', 'unknown')}`",
        "",
        "## Rationale",
        "",
        str(decision.get("rationale") or "No rationale recorded."),
        "",
        "## Proposed Orders",
        "",
    ]
    if orders:
        lines.extend(["| Symbol | Side | Quantity | Notional | Type | Limit | TIF |", "|---|---|---:|---:|---|---:|---|"])
        for order in orders:
            if not isinstance(order, dict):
                continue
            lines.append(
                "| "
                + " | ".join(
                    _md_cell(order.get(key))
                    for key in ("symbol", "side", "quantity", "notional", "order_type", "limit_price", "time_in_force")
                )
                + " |"
            )
    else:
        lines.append("No order proposed.")
    lines.extend(
        [
            "",
            "## Authority",
            "",
            "Research-only proposal. Broker submission and real-money trading authority are false by default.",
        ]
    )
    return "\n".join(lines)


def _find_forbidden_keys(value: Any, path: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key.lower() in FORBIDDEN_DECISION_KEYS:
                errors.append(f"{child_path} uses removed numeric event-ranking semantics")
            errors.extend(_find_forbidden_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(_find_forbidden_keys(child, f"{path}[{index}]"))
    return errors


def _normalize_authority(decision: dict[str, Any]) -> dict[str, Any]:
    authority = decision.get("authority")
    if not isinstance(authority, dict):
        authority = {}
    authority.update(
        {
            "research_only": True,
            "paper_trade_proposal_allowed": False,
            "broker_submit_allowed": False,
            "ready_for_real_money_trading_authority": False,
        }
    )
    decision["authority"] = authority
    return decision


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _positive_number(value: Any) -> bool:
    if value in (None, ""):
        return False
    try:
        return float(value) > 0
    except (TypeError, ValueError):
        return False


def _md_cell(value: Any) -> str:
    if value in (None, ""):
        return ""
    return str(value).replace("|", "\\|").replace("\n", " ").strip()


def _blocked(blocker: str, message: str, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "vibe.moirix_position_decision_write.v1",
        "status": "blocked",
        "error": message,
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
    return payload
