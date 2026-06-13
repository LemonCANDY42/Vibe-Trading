"""Write read-only portfolio context for Moirix event thesis decisions."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.agent.tools import BaseTool
from src.tools._moirix_adapter import adapter_artifact_dir, resolve_adapter_input


class MoirixPortfolioContextTool(BaseTool):
    """Persist portfolio context without calling broker write APIs."""

    name = "moirix_portfolio_context"
    description = (
        "Create artifacts/moirix/event_decision_context.json from an existing read-only "
        "portfolio or IBKR paper readiness artifact. The tool never calls broker write APIs "
        "and never fabricates positions; missing portfolio evidence returns blocked/unavailable "
        "context with empty positions."
    )
    parameters = {
        "type": "object",
        "properties": {
            "target": {"type": "string", "description": "Target symbol or instrument, e.g. NVDA."},
            "market": {"type": "string", "description": "Market label, e.g. US, HK, A-share."},
            "as_of": {"type": "string", "description": "Point-in-time cutoff date/time."},
            "portfolio_snapshot_path": {
                "type": "string",
                "description": "Optional JSON portfolio snapshot path under the current run or allowed import roots.",
            },
            "ibkr_readiness_path": {
                "type": "string",
                "description": (
                    "Optional IBKR paper readiness JSON path. Defaults to "
                    "artifacts/ibkr/ibkr_paper_readiness.json under the current run."
                ),
            },
        },
        "required": ["target", "market", "as_of"],
    }
    repeatable = True
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        run_dir = kwargs.get("run_dir")
        if not run_dir:
            return json.dumps(
                {"status": "error", "error": "run_dir is required for moirix_portfolio_context artifacts"},
                ensure_ascii=False,
            )

        target = str(kwargs.get("target") or "").strip()
        market = str(kwargs.get("market") or "").strip()
        as_of = str(kwargs.get("as_of") or "").strip()
        if not target or not market or not as_of:
            return json.dumps(
                _context_payload(
                    status="blocked",
                    target=target,
                    market=market,
                    as_of=as_of,
                    blockers=["moirix_portfolio_context_target_market_as_of_required"],
                    source={"type": "none", "status": "blocked"},
                ),
                ensure_ascii=False,
            )

        try:
            out_dir = adapter_artifact_dir(str(run_dir))
        except ValueError as exc:
            return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)

        payload = self._build_context(kwargs, str(run_dir), target=target, market=market, as_of=as_of)
        path = out_dir / "event_decision_context.json"
        payload["artifacts"] = {"event_decision_context": str(path)}
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        return json.dumps(payload, ensure_ascii=False, default=str)

    def _build_context(self, kwargs: dict[str, Any], run_dir: str, *, target: str, market: str, as_of: str) -> dict[str, Any]:
        snapshot_path = str(kwargs.get("portfolio_snapshot_path") or "").strip()
        if snapshot_path:
            path, error = resolve_adapter_input(
                snapshot_path,
                run_dir,
                blocker_prefix="moirix_portfolio_snapshot",
            )
            if error is not None or path is None:
                return _context_payload(
                    status="blocked",
                    target=target,
                    market=market,
                    as_of=as_of,
                    blockers=_blockers(error, "moirix_portfolio_snapshot_missing"),
                    source={"type": "portfolio_snapshot", "status": "blocked", "path": snapshot_path},
                )
            return _context_from_snapshot(path, target=target, market=market, as_of=as_of)

        readiness_path = str(kwargs.get("ibkr_readiness_path") or "").strip()
        if readiness_path:
            path, error = resolve_adapter_input(
                readiness_path,
                run_dir,
                blocker_prefix="moirix_ibkr_readiness",
            )
        else:
            path, error = resolve_adapter_input(
                None,
                run_dir,
                default_relative="artifacts/ibkr/ibkr_paper_readiness.json",
                blocker_prefix="moirix_ibkr_readiness",
            )
        if error is not None or path is None:
            return _context_payload(
                status="blocked",
                target=target,
                market=market,
                as_of=as_of,
                blockers=_blockers(error, "moirix_portfolio_context_unavailable"),
                source={"type": "ibkr_paper_readiness", "status": "unavailable"},
            )
        return _context_from_ibkr_readiness(path, target=target, market=market, as_of=as_of)


def _context_from_snapshot(path: Path, *, target: str, market: str, as_of: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _context_payload(
            status="blocked",
            target=target,
            market=market,
            as_of=as_of,
            blockers=["moirix_portfolio_snapshot_invalid_json"],
            source={"type": "portfolio_snapshot", "status": "blocked", "path": str(path), "error": str(exc)},
        )
    if not isinstance(data, dict):
        return _context_payload(
            status="blocked",
            target=target,
            market=market,
            as_of=as_of,
            blockers=["moirix_portfolio_snapshot_invalid_shape"],
            source={"type": "portfolio_snapshot", "status": "blocked", "path": str(path)},
        )
    positions = data.get("positions") if isinstance(data.get("positions"), list) else []
    return _context_payload(
        status="ok",
        target=target,
        market=market,
        as_of=as_of,
        blockers=[],
        source={"type": "portfolio_snapshot", "status": "ok", "path": str(path)},
        account_summary=data.get("account_summary") if isinstance(data.get("account_summary"), dict) else {},
        positions=[item for item in positions if isinstance(item, dict)],
        open_orders=data.get("open_orders") if isinstance(data.get("open_orders"), list) else [],
        executions=data.get("executions") if isinstance(data.get("executions"), list) else [],
    )


def _context_from_ibkr_readiness(path: Path, *, target: str, market: str, as_of: str) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _context_payload(
            status="blocked",
            target=target,
            market=market,
            as_of=as_of,
            blockers=["moirix_ibkr_readiness_invalid_json"],
            source={"type": "ibkr_paper_readiness", "status": "blocked", "path": str(path), "error": str(exc)},
        )
    if not isinstance(data, dict):
        return _context_payload(
            status="blocked",
            target=target,
            market=market,
            as_of=as_of,
            blockers=["moirix_ibkr_readiness_invalid_shape"],
            source={"type": "ibkr_paper_readiness", "status": "blocked", "path": str(path)},
        )

    checks = data.get("checks") if isinstance(data.get("checks"), dict) else {}
    summary_rows = _payload_rows(checks, "account_summary", "summary")
    positions = _payload_rows(checks, "positions", "positions")
    open_orders = _payload_rows(checks, "open_orders_and_executions", "open_orders")
    executions = _payload_rows(checks, "open_orders_and_executions", "executions")
    account_summary = _account_summary(summary_rows)
    blockers = list(data.get("claim_gate", {}).get("blockers", [])) if isinstance(data.get("claim_gate"), dict) else []
    source_status = str(data.get("status") or "unknown")
    has_context = bool(summary_rows or positions or open_orders or executions)
    status = "ok" if has_context else "blocked"
    if not has_context:
        blockers.append("moirix_ibkr_readiness_has_no_portfolio_context")
    return _context_payload(
        status=status,
        target=target,
        market=market,
        as_of=as_of,
        blockers=blockers,
        source={"type": "ibkr_paper_readiness", "status": source_status, "path": str(path)},
        account_summary=account_summary,
        positions=positions,
        open_orders=open_orders,
        executions=executions,
    )


def _payload_rows(checks: dict[str, Any], check_name: str, row_key: str) -> list[dict[str, Any]]:
    check = checks.get(check_name)
    if not isinstance(check, dict):
        return []
    payload = check.get("payload")
    if not isinstance(payload, dict):
        return []
    rows = payload.get(row_key)
    if not isinstance(rows, list):
        return []
    return [row for row in rows if isinstance(row, dict)]


def _account_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    wanted = {
        "AvailableFunds",
        "BuyingPower",
        "EquityWithLoanValue",
        "ExcessLiquidity",
        "GrossPositionValue",
        "NetLiquidation",
        "TotalCashValue",
    }
    summary: dict[str, Any] = {}
    for row in rows:
        tag = row.get("tag")
        if tag in wanted:
            key = str(tag)
            currency = str(row.get("currency") or "")
            if currency:
                key = f"{key}_{currency}"
            summary[key] = row.get("value")
    return summary


def _context_payload(
    *,
    status: str,
    target: str,
    market: str,
    as_of: str,
    blockers: list[str],
    source: dict[str, Any],
    account_summary: dict[str, Any] | None = None,
    positions: list[dict[str, Any]] | None = None,
    open_orders: list[dict[str, Any]] | None = None,
    executions: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    return {
        "schema_version": "vibe.moirix_event_decision_context.v1",
        "status": status,
        "generated_at": generated_at,
        "target": target,
        "market": market,
        "as_of": as_of,
        "portfolio_source": source,
        "account_summary": account_summary or {},
        "positions": positions or [],
        "open_orders": open_orders or [],
        "executions": executions or [],
        "position_counts": {
            "positions": len(positions or []),
            "open_orders": len(open_orders or []),
            "executions": len(executions or []),
        },
        "claim_gate": {
            "blockers": blockers,
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


def _blockers(error: dict[str, Any] | None, fallback: str) -> list[str]:
    if isinstance(error, dict):
        claim_gate = error.get("claim_gate")
        if isinstance(claim_gate, dict) and isinstance(claim_gate.get("blockers"), list):
            return [str(item) for item in claim_gate["blockers"]]
    return [fallback]
