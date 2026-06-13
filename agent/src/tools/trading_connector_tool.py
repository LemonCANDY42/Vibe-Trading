"""Connector-first trading tools.

Tools take an optional ``connection`` profile id. If omitted, they use the
selected profile from ``~/.vibe-trading/trading-connections.json``.
"""

from __future__ import annotations

import json
from typing import Any

from src.agent.tools import BaseTool
from src.trading.idempotency import idempotency_schema_property, run_once
from src.trading.paper_audit import write_paper_action
from src.trading.paper_gate import build_paper_request, validate_paper_gate
from src.trading.profiles import (
    list_profiles,
    load_selected_profile_id,
    profile_by_id,
    save_selected_profile_id,
)
from src.trading.service import (
    cancel_order,
    check_connection,
    get_account,
    get_history,
    get_open_orders,
    get_positions,
    get_quote,
    place_order,
)


def _json_result(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _connection(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _num_or_none(value: Any) -> float | None:
    if value in (None, ""):
        return None
    return float(value)


def _bool(value: Any, *, default: bool) -> bool:
    if value in (None, ""):
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}


TRADING_COMMON_PARAMETERS = {
    "connection": {
        "type": "string",
        "description": "Trading connector profile id, e.g. ibkr-paper-local, ibkr-paper-trade, or robinhood-live-mcp. Defaults to the selected profile.",
    },
    "host": {
        "type": "string",
        "description": "Optional local TWS/Gateway host override for local profiles.",
    },
    "port": {
        "type": "integer",
        "description": "Optional local TWS/Gateway port override for local profiles.",
    },
    "client_id": {
        "type": "integer",
        "description": "Optional local TWS/Gateway client id override for local profiles.",
    },
    "account": {
        "type": "string",
        "description": "Optional account code filter when supported by the connector.",
    },
}


def _overrides(kwargs: dict[str, Any]) -> dict[str, Any]:
    return {
        "host": _connection(kwargs.get("host")),
        "port": _int_or_none(kwargs.get("port")),
        "client_id": _int_or_none(kwargs.get("client_id")),
        "account": _connection(kwargs.get("account")),
    }


class TradingConnectionsTool(BaseTool):
    """List available trading connector profiles."""

    name = "trading_connections"
    description = (
        "List selectable trading connector profiles. Connectors come first; paper/live is a profile attribute."
    )
    parameters = {"type": "object", "properties": {}, "required": []}
    repeatable = True
    is_readonly = True

    def execute(self, **_: Any) -> str:
        """List connector profiles and mark the selected one."""
        try:
            selected = load_selected_profile_id()
            return _json_result(
                {
                    "status": "ok",
                    "selected_profile": selected,
                    "profiles": [profile.to_dict(selected=profile.id == selected) for profile in list_profiles()],
                }
            )
        except Exception as exc:  # noqa: BLE001
            return _json_result({"status": "error", "error": str(exc)})


class TradingSelectConnectionTool(BaseTool):
    """Select the default trading connector profile."""

    name = "trading_select_connection"
    description = "Select the default trading connector profile for subsequent trading_* tool calls."
    parameters = {
        "type": "object",
        "properties": {
            "connection": {
                "type": "string",
                "description": "Profile id to select, e.g. ibkr-paper-local or ibkr-paper-trade.",
            }
        },
        "required": ["connection"],
    }
    repeatable = True
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        """Persist the selected profile id."""
        try:
            profile = profile_by_id(str(kwargs["connection"]).strip())
            path = save_selected_profile_id(profile.id)
            return _json_result({"status": "ok", "selected_profile": profile.id, "path": str(path)})
        except Exception as exc:  # noqa: BLE001
            return _json_result({"status": "error", "error": str(exc)})


class TradingCheckTool(BaseTool):
    """Check a trading connector profile."""

    name = "trading_check"
    description = "Check whether a trading connector profile is configured and reachable. This never places orders."
    parameters = {
        "type": "object",
        "properties": TRADING_COMMON_PARAMETERS,
        "required": [],
    }
    repeatable = True
    is_readonly = True

    def execute(self, **kwargs: Any) -> str:
        """Check connector readiness."""
        try:
            return _json_result(check_connection(_connection(kwargs.get("connection")), **_overrides(kwargs)))
        except Exception as exc:  # noqa: BLE001
            return _json_result({"status": "error", "error": str(exc)})


class TradingAccountTool(BaseTool):
    """Read account summary from a trading connector profile."""

    name = "trading_account"
    description = "Read account summary from the selected trading connector profile. Read-only."
    parameters = TradingCheckTool.parameters
    repeatable = True
    is_readonly = True

    def execute(self, **kwargs: Any) -> str:
        """Read account summary."""
        try:
            return _json_result(get_account(_connection(kwargs.get("connection")), **_overrides(kwargs)))
        except Exception as exc:  # noqa: BLE001
            return _json_result({"status": "error", "error": str(exc)})


class TradingPositionsTool(BaseTool):
    """Read positions from a trading connector profile."""

    name = "trading_positions"
    description = "Read positions from the selected trading connector profile. Read-only."
    parameters = TradingCheckTool.parameters
    repeatable = True
    is_readonly = True

    def execute(self, **kwargs: Any) -> str:
        """Read positions."""
        try:
            return _json_result(get_positions(_connection(kwargs.get("connection")), **_overrides(kwargs)))
        except Exception as exc:  # noqa: BLE001
            return _json_result({"status": "error", "error": str(exc)})


class TradingOrdersTool(BaseTool):
    """Read open orders from a trading connector profile."""

    name = "trading_orders"
    description = "Read open orders from the selected trading connector profile. Read-only."
    parameters = {
        "type": "object",
        "properties": {
            **TRADING_COMMON_PARAMETERS,
            "include_executions": {"type": "boolean", "default": False},
        },
        "required": [],
    }
    repeatable = True
    is_readonly = True

    def execute(self, **kwargs: Any) -> str:
        """Read open orders."""
        try:
            return _json_result(
                get_open_orders(
                    _connection(kwargs.get("connection")),
                    include_executions=bool(kwargs.get("include_executions", False)),
                    **_overrides(kwargs),
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _json_result({"status": "error", "error": str(exc)})


class TradingQuoteTool(BaseTool):
    """Read a quote from a trading connector profile."""

    name = "trading_quote"
    description = "Read a quote snapshot from the selected trading connector profile. Read-only."
    parameters = {
        "type": "object",
        "properties": {
            **TRADING_COMMON_PARAMETERS,
            "symbol": {"type": "string", "description": "Symbol, e.g. AAPL"},
            "exchange": {"type": "string", "default": "SMART"},
            "currency": {"type": "string", "default": "USD"},
            "sec_type": {"type": "string", "default": "STK"},
        },
        "required": ["symbol"],
    }
    repeatable = True
    is_readonly = True

    def execute(self, **kwargs: Any) -> str:
        """Read quote snapshot."""
        try:
            return _json_result(
                get_quote(
                    str(kwargs["symbol"]),
                    _connection(kwargs.get("connection")),
                    exchange=str(kwargs.get("exchange") or "SMART"),
                    currency=str(kwargs.get("currency") or "USD"),
                    sec_type=str(kwargs.get("sec_type") or "STK"),
                    **_overrides(kwargs),
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _json_result({"status": "error", "error": str(exc)})


class TradingHistoryTool(BaseTool):
    """Read historical bars from a trading connector profile."""

    name = "trading_history"
    description = "Read historical bars from the selected trading connector profile. Read-only."
    parameters = {
        "type": "object",
        "properties": {
            **TradingQuoteTool.parameters["properties"],
            "duration": {"type": "string", "default": "30 D", "description": "IBKR (local_tws) duration string."},
            "bar_size": {"type": "string", "default": "1 day", "description": "IBKR (local_tws) bar size."},
            "what_to_show": {"type": "string", "default": "TRADES"},
            "use_rth": {"type": "boolean", "default": True},
            "period": {
                "type": "string",
                "default": "1d",
                "description": "Bar interval for SDK connectors (broker_sdk): 1m/5m/15m/30m/1h/4h/1d/1w/1M.",
            },
            "limit": {"type": "integer", "default": 90, "description": "Number of bars for SDK connectors."},
        },
        "required": ["symbol"],
    }
    repeatable = True
    is_readonly = True

    def execute(self, **kwargs: Any) -> str:
        """Read historical bars."""
        try:
            return _json_result(
                get_history(
                    str(kwargs["symbol"]),
                    _connection(kwargs.get("connection")),
                    exchange=str(kwargs.get("exchange") or "SMART"),
                    currency=str(kwargs.get("currency") or "USD"),
                    sec_type=str(kwargs.get("sec_type") or "STK"),
                    duration=str(kwargs.get("duration") or "30 D"),
                    bar_size=str(kwargs.get("bar_size") or "1 day"),
                    what_to_show=str(kwargs.get("what_to_show") or "TRADES"),
                    use_rth=bool(kwargs.get("use_rth", True)),
                    period=str(kwargs.get("period") or "1d"),
                    limit=int(kwargs.get("limit") or 90),
                    **_overrides(kwargs),
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _json_result({"status": "error", "error": str(exc)})


class TradingPlaceOrderTool(BaseTool):
    """Place an order through a trading connector profile.

    Paper profiles place against the broker's sandbox account. Live profiles
    route through the bounded-autonomy mandate gate (mandate + kill switch +
    fail-closed pre-trade checks + audit) before any order reaches the broker.
    Not read-only; not repeatable (an order must never be silently re-issued).
    """

    name = "trading_place_order"
    description = (
        "Plan or place an order through the selected trading connector profile. "
        "Defaults to dry_run=true. Paper execution requires an explicit approval "
        "artifact bound to this exact request; live profiles are gated by the "
        "existing mandate and kill switch. side is 'buy' or 'sell'; give exactly "
        "one of quantity or notional. IBKR paper orders currently require quantity."
    )
    parameters = {
        "type": "object",
        "properties": {
            **TRADING_COMMON_PARAMETERS,
            "symbol": {"type": "string", "description": "Symbol, e.g. AAPL, BTC-USDT, 700.HK, HK.00700."},
            "side": {"type": "string", "enum": ["buy", "sell"]},
            "quantity": {"type": "number", "description": "Order size in units/shares/contracts. Exactly one of quantity/notional."},
            "notional": {"type": "number", "description": "Order size as an account-currency amount. Exactly one of quantity/notional."},
            "order_type": {"type": "string", "enum": ["market", "limit"], "default": "market"},
            "limit_price": {"type": "number", "description": "Required for limit orders."},
            "time_in_force": {"type": "string", "enum": ["day", "gtc"], "default": "day"},
            "dry_run": {"type": "boolean", "default": True},
            "approval_path": {"type": "string", "description": "Required for paper execution when dry_run=false."},
            "idempotency_key": idempotency_schema_property(),
        },
        "required": ["symbol", "side"],
    }
    repeatable = False
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        """Place an order via the connector profile."""
        try:
            request = {
                "connection": _connection(kwargs.get("connection")),
                "symbol": str(kwargs["symbol"]),
                "side": str(kwargs.get("side") or ""),
                "quantity": _num_or_none(kwargs.get("quantity")),
                "notional": _num_or_none(kwargs.get("notional")),
                "order_type": str(kwargs.get("order_type") or "market"),
                "limit_price": _num_or_none(kwargs.get("limit_price")),
                "time_in_force": str(kwargs.get("time_in_force") or "day"),
                "overrides": _overrides(kwargs),
            }
            action = {
                "type": "place_order",
                "symbol": request["symbol"],
                "side": request["side"],
                "quantity": request["quantity"],
                "notional": request["notional"],
                "order_type": request["order_type"],
                "limit_price": request["limit_price"],
                "time_in_force": request["time_in_force"],
            }
            dry_run = _bool(kwargs.get("dry_run"), default=True)
            if dry_run:
                return _json_result({"status": "dry_run", "operation": "place_order", "dry_run": True, "actions": [action]})

            profile = profile_by_id(request["connection"])
            idempotency_key = _connection(kwargs.get("idempotency_key"))
            gate_request: dict[str, Any] | None = None
            gate_decision: dict[str, Any] | None = None
            if profile.environment == "paper":
                gate_request = build_paper_request(
                    operation=self.name,
                    connection=profile.id,
                    account=_connection(kwargs.get("account")),
                    actions=[{**action, "overrides": request["overrides"]}],
                )
                gate = validate_paper_gate(
                    approval_path=kwargs.get("approval_path"),
                    request=gate_request,
                    required_capabilities=("orders.place",),
                )
                gate_decision = gate.decision()
                if not gate.allowed:
                    payload = {
                        "status": "blocked",
                        "operation": "place_order",
                        "claim_gate": {"blockers": gate.blockers},
                        "gate_decision": gate_decision,
                    }
                    _write_paper_audit_safe(self.name, "order_place", "blocked", profile.id, gate_request, payload, gate_decision)
                    return _json_result(payload)
                idempotency_key = gate.idempotency_key

            def _execute() -> dict[str, Any]:
                result = place_order(
                    str(kwargs["symbol"]),
                    request["connection"],
                    side=str(kwargs.get("side") or ""),
                    quantity=_num_or_none(kwargs.get("quantity")),
                    notional=_num_or_none(kwargs.get("notional")),
                    order_type=str(kwargs.get("order_type") or "market"),
                    limit_price=_num_or_none(kwargs.get("limit_price")),
                    time_in_force=str(kwargs.get("time_in_force") or "day"),
                    **_overrides(kwargs),
                )
                if profile.environment == "paper" and gate_request is not None:
                    outcome = "accepted" if str(result.get("status") or "").lower() == "ok" else "blocked"
                    _write_paper_audit_safe(self.name, "order_place", outcome, profile.id, gate_request, result, gate_decision or {})
                return result

            return _json_result(
                run_once(
                    tool_name=self.name,
                    request=request,
                    idempotency_key=idempotency_key,
                    execute=_execute,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _json_result({"status": "error", "error": str(exc)})


class TradingCancelOrderTool(BaseTool):
    """Cancel an order through a trading connector profile (risk-reducing)."""

    name = "trading_cancel_order"
    description = (
        "Plan or cancel an open order on the selected trading connector profile by order id. "
        "Defaults to dry_run=true. Paper cancellation requires explicit approval when dry_run=false."
    )
    parameters = {
        "type": "object",
        "properties": {
            **TRADING_COMMON_PARAMETERS,
            "order_id": {"type": "string", "description": "Broker order id to cancel."},
            "symbol": {"type": "string", "description": "Symbol (required by some brokers, e.g. OKX/Binance)."},
            "dry_run": {"type": "boolean", "default": True},
            "approval_path": {"type": "string", "description": "Required for paper cancellation when dry_run=false."},
            "idempotency_key": idempotency_schema_property(),
        },
        "required": ["order_id"],
    }
    repeatable = False
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        """Cancel an order via the connector profile."""
        try:
            request = {
                "connection": _connection(kwargs.get("connection")),
                "order_id": str(kwargs["order_id"]),
                "symbol": _connection(kwargs.get("symbol")),
                "overrides": _overrides(kwargs),
            }
            action = {"type": "cancel_order", "order_id": request["order_id"], "symbol": request["symbol"]}
            dry_run = _bool(kwargs.get("dry_run"), default=True)
            if dry_run:
                return _json_result({"status": "dry_run", "operation": "cancel_order", "dry_run": True, "actions": [action]})
            profile = profile_by_id(request["connection"])
            idempotency_key = _connection(kwargs.get("idempotency_key"))
            gate_request: dict[str, Any] | None = None
            gate_decision: dict[str, Any] | None = None
            if profile.environment == "paper":
                gate_request = build_paper_request(
                    operation=self.name,
                    connection=profile.id,
                    account=_connection(kwargs.get("account")),
                    actions=[{**action, "overrides": request["overrides"]}],
                )
                gate = validate_paper_gate(
                    approval_path=kwargs.get("approval_path"),
                    request=gate_request,
                    required_capabilities=("orders.cancel",),
                )
                gate_decision = gate.decision()
                if not gate.allowed:
                    payload = {
                        "status": "blocked",
                        "operation": "cancel_order",
                        "claim_gate": {"blockers": gate.blockers},
                        "gate_decision": gate_decision,
                    }
                    _write_paper_audit_safe(self.name, "order_cancel", "blocked", profile.id, gate_request, payload, gate_decision)
                    return _json_result(payload)
                idempotency_key = gate.idempotency_key

            def _execute() -> dict[str, Any]:
                result = cancel_order(
                    str(kwargs["order_id"]),
                    request["connection"],
                    symbol=_connection(kwargs.get("symbol")),
                    **_overrides(kwargs),
                )
                if profile.environment == "paper" and gate_request is not None:
                    outcome = "accepted" if str(result.get("status") or "").lower() == "ok" else "blocked"
                    _write_paper_audit_safe(self.name, "order_cancel", outcome, profile.id, gate_request, result, gate_decision or {})
                return result

            return _json_result(
                run_once(
                    tool_name=self.name,
                    request=request,
                    idempotency_key=idempotency_key,
                    execute=_execute,
                )
            )
        except Exception as exc:  # noqa: BLE001
            return _json_result({"status": "error", "error": str(exc)})


def _write_paper_audit_safe(
    tool_name: str,
    kind: str,
    outcome: str,
    profile_id: str,
    request: dict[str, Any],
    response: dict[str, Any],
    gate_decision: dict[str, Any],
) -> None:
    try:
        write_paper_action(
            kind=kind,
            outcome=outcome,
            profile_id=profile_id,
            request=request,
            response=response,
            gate_decision=gate_decision,
            approval_id=str(gate_decision.get("approval_id") or "") or None,
            tool_name=tool_name,
        )
    except Exception:
        pass
