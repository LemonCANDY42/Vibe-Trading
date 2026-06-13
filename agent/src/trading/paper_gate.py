"""Fail-closed approval gate for Agent-facing paper trading mutations."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from src.live.halt import halt_flag_set
from src.tools.path_utils import safe_user_path
from src.trading.profiles import profile_by_id
from src.trading.types import TradingProfile


APPROVAL_SCHEMA_VERSION = "vibe.paper_execution_approval.v2"
_DATE_TZ = re.compile(r"([+-]\d{2})$")


@dataclass(frozen=True)
class PaperGateResult:
    """Validated paper gate result."""

    allowed: bool
    blockers: list[str]
    request_hash: str
    idempotency_key: str
    approval: dict[str, Any]
    approval_path: Path | None
    profile: TradingProfile | None
    estimated_notional: float

    def decision(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "blockers": self.blockers,
            "request_sha256": self.request_hash,
            "approval_id": self.approval.get("approval_id"),
            "approval_path": str(self.approval_path) if self.approval_path else None,
            "estimated_notional": self.estimated_notional,
        }


def canonical_request_hash(payload: Any) -> str:
    """Return a stable SHA256 hash for an approval-bound request payload."""
    data = json.dumps(_jsonable(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def build_paper_request(
    *,
    operation: str,
    connection: str | None,
    account: str | None,
    actions: list[dict[str, Any]],
    proposal_sha256: str | None = None,
) -> dict[str, Any]:
    """Build the canonical request envelope bound by a paper approval artifact."""
    payload: dict[str, Any] = {
        "operation": str(operation or "").strip(),
        "execution_mode": "paper",
        "connection": str(connection or "").strip(),
        "account": str(account or "").strip(),
        "actions": _jsonable(actions),
    }
    if proposal_sha256:
        payload["proposal_sha256"] = str(proposal_sha256).strip().lower()
    return payload


def validate_paper_gate(
    *,
    approval_path: str | Path | None,
    request: dict[str, Any],
    required_capabilities: Iterable[str],
    allow_missing_approval: bool = False,
    allowed_roots: Iterable[Path] | None = None,
) -> PaperGateResult:
    """Validate an explicit paper approval artifact against request/profile bounds."""
    blockers: list[str] = []
    request_hash = canonical_request_hash(request)
    resolved: Path | None = None
    approval: dict[str, Any] = {}
    if not approval_path:
        if not allow_missing_approval:
            blockers.append("paper_execution_approval_missing")
    else:
        try:
            resolved = _resolve_approval_path(approval_path, allowed_roots=allowed_roots)
            approval = _load_approval(resolved)
        except (OSError, ValueError, json.JSONDecodeError) as exc:
            blockers.append("paper_execution_approval_unreadable")
            approval = {"error": str(exc)}

    connection = str(request.get("connection") or "").strip()
    account = str(request.get("account") or "").strip()
    profile: TradingProfile | None = None
    if not connection:
        blockers.append("paper_execution_connection_required")
    else:
        try:
            profile = profile_by_id(connection)
        except ValueError:
            blockers.append("paper_execution_unknown_connection")

    if profile is not None:
        if profile.environment != "paper":
            blockers.append("paper_execution_profile_not_paper")
        if profile.readonly:
            blockers.append("paper_execution_profile_readonly")
        missing = [cap for cap in required_capabilities if cap not in profile.capabilities]
        for cap in missing:
            blockers.append(f"paper_execution_profile_lacks_{cap.replace('.', '_')}")
        if halt_flag_set(profile.connector):
            blockers.append("paper_execution_kill_switch_tripped")
        if profile.connector == "ibkr" and profile.transport == "local_tws" and _request_uses_client_id_zero(request):
            blockers.append("paper_execution_ibkr_client_id_zero_blocked")

    estimated_notional, notional_blockers = estimate_request_notional(request, approval)
    blockers.extend(notional_blockers)

    if approval:
        if approval.get("schema_version") != APPROVAL_SCHEMA_VERSION:
            blockers.append("paper_execution_approval_schema_invalid")
        if approval.get("approved") is not True:
            blockers.append("paper_execution_approval_not_true")
        if str(approval.get("scope") or "").strip().lower() != "paper":
            blockers.append("paper_execution_approval_scope_not_paper")
        if str(approval.get("execution_mode") or "").strip().lower() != "paper":
            blockers.append("paper_execution_approval_mode_not_paper")
        if str(approval.get("connection") or "").strip() != connection:
            blockers.append("paper_execution_approval_connection_mismatch")
        if str(approval.get("account") or "").strip() != account:
            blockers.append("paper_execution_approval_account_mismatch")
        if str(approval.get("request_sha256") or "").strip().lower() != request_hash:
            blockers.append("paper_execution_approval_request_hash_mismatch")
        if not str(approval.get("approval_id") or "").strip():
            blockers.append("paper_execution_approval_id_missing")
        expires_at = _parse_dt(approval.get("expires_at"))
        if expires_at is None:
            blockers.append("paper_execution_approval_expiry_missing_or_invalid")
        elif expires_at <= datetime.now(timezone.utc):
            blockers.append("paper_execution_approval_expired")
        authority = approval.get("authority") if isinstance(approval.get("authority"), dict) else approval
        if authority.get("paper_trade_proposal_allowed") is not True:
            blockers.append("paper_execution_approval_missing_paper_authority")
        if authority.get("broker_submit_allowed") is not True:
            blockers.append("paper_execution_approval_missing_broker_submit_authority")
        if authority.get("ready_for_real_money_trading_authority") is True:
            blockers.append("paper_execution_approval_claims_real_money_authority")
        max_notional = _float_or_none(approval.get("max_notional"))
        if max_notional is None or max_notional <= 0:
            blockers.append("paper_execution_approval_max_notional_missing")
        elif estimated_notional > max_notional:
            blockers.append("paper_execution_estimated_notional_exceeds_approval")

    approval_id = str(approval.get("approval_id") or "").strip()
    idempotency_key = f"paper:{approval_id}:{request_hash[:16]}" if approval_id else f"paper:{request_hash[:32]}"
    return PaperGateResult(
        allowed=not blockers,
        blockers=blockers,
        request_hash=request_hash,
        idempotency_key=idempotency_key,
        approval=approval,
        approval_path=resolved,
        profile=profile,
        estimated_notional=estimated_notional,
    )


def estimate_request_notional(request: dict[str, Any], approval: dict[str, Any] | None = None) -> tuple[float, list[str]]:
    """Estimate maximum paper exposure for approval-bound actions."""
    blockers: list[str] = []
    approval = approval or {}
    prices = approval.get("estimated_prices") if isinstance(approval.get("estimated_prices"), dict) else {}
    prices = {str(key).strip().upper(): value for key, value in prices.items()}
    actions = request.get("actions") if isinstance(request.get("actions"), list) else []
    total = 0.0
    for index, action in enumerate(actions):
        if not isinstance(action, dict):
            continue
        action_type = str(action.get("type") or "").strip()
        if action_type and action_type not in {"place_order"}:
            continue
        notional = _float_or_none(action.get("notional"))
        if notional is not None and notional > 0:
            total += abs(notional)
            continue
        quantity = _float_or_none(action.get("quantity"))
        if quantity is None or quantity <= 0:
            continue
        price = _float_or_none(action.get("limit_price")) or _float_or_none(action.get("estimated_price"))
        if price is None or price <= 0:
            symbol = str(action.get("symbol") or "").strip().upper()
            price = _float_or_none(prices.get(symbol))
        if price is None or price <= 0:
            blockers.append(f"paper_execution_action_{index}_estimated_price_required")
            continue
        total += abs(quantity * price)
    return total, blockers


def _request_uses_client_id_zero(request: dict[str, Any]) -> bool:
    top = request.get("overrides") if isinstance(request.get("overrides"), dict) else {}
    if top.get("client_id") == 0:
        return True
    actions = request.get("actions") if isinstance(request.get("actions"), list) else []
    for action in actions:
        if not isinstance(action, dict):
            continue
        overrides = action.get("overrides") if isinstance(action.get("overrides"), dict) else {}
        if overrides.get("client_id") == 0:
            return True
    return False


def _load_approval(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("approval artifact must be a JSON object")
    return value


def _resolve_approval_path(path: str | Path, *, allowed_roots: Iterable[Path] | None = None) -> Path:
    candidate = Path(path).expanduser().resolve()
    for root in allowed_roots or []:
        resolved_root = Path(root).expanduser().resolve()
        if candidate.is_relative_to(resolved_root):
            return candidate
    return safe_user_path(str(path))


def _parse_dt(value: Any) -> datetime | None:
    text = "" if value is None else str(value).strip()
    if not text:
        return None
    candidate = text.replace("Z", "+00:00")
    if _DATE_TZ.search(candidate):
        candidate = f"{candidate}:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _float_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(key): _jsonable(item) for key, item in value.items()}
        if isinstance(value, (list, tuple)):
            return [_jsonable(item) for item in value]
        return str(value)
