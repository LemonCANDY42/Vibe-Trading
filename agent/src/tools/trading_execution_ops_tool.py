"""High-level trading execution operations.

These tools compose existing trading service primitives. They do not bypass
connector profiles, live mandates, kill switches, approval gates, or audit
logic.
"""

from __future__ import annotations

import json
from typing import Any

from src.agent.tools import BaseTool
from src.trading.idempotency import idempotency_schema_property, run_once
from src.trading.service import cancel_order, get_open_orders, get_positions, place_order


def _json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _connection(value: Any) -> str | None:
    text = "" if value is None else str(value).strip()
    return text or None


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


def _overrides(kwargs: dict[str, Any]) -> dict[str, Any]:
    return {
        "host": _connection(kwargs.get("host")),
        "port": int(kwargs["port"]) if kwargs.get("port") not in (None, "") else None,
        "client_id": int(kwargs["client_id"]) if kwargs.get("client_id") not in (None, "") else None,
        "account": _connection(kwargs.get("account")),
    }


def _order_id(row: dict[str, Any]) -> str | None:
    for key in ("order_id", "id", "orderId"):
        if row.get(key) not in (None, ""):
            return str(row[key])
    order = row.get("order")
    if isinstance(order, dict):
        return _order_id(order)
    return None


def _order_symbol(row: dict[str, Any]) -> str | None:
    for key in ("symbol", "local_symbol"):
        if row.get(key):
            return str(row[key]).upper()
    contract = row.get("contract")
    if isinstance(contract, dict):
        return _order_symbol(contract)
    return None


def _position_symbol(row: dict[str, Any]) -> str | None:
    for key in ("symbol", "local_symbol", "code", "instrument"):
        if row.get(key):
            return str(row[key]).upper()
    contract = row.get("contract")
    if isinstance(contract, dict):
        return _position_symbol(contract)
    return None


def _position_qty(row: dict[str, Any]) -> float:
    for key in ("position", "qty", "quantity", "shares", "available", "net_qty"):
        if row.get(key) not in (None, ""):
            return float(row[key])
    return 0.0


def _planned_order(
    *,
    symbol: str,
    side: str,
    quantity: float | None,
    notional: float | None = None,
    order_type: str = "market",
    limit_price: float | None = None,
    time_in_force: str = "day",
) -> dict[str, Any]:
    return {
        "symbol": symbol.upper(),
        "side": side.lower(),
        "quantity": quantity,
        "notional": notional,
        "order_type": order_type.lower(),
        "limit_price": limit_price,
        "time_in_force": time_in_force.lower(),
    }


def _execute_order(plan: dict[str, Any], connection: str | None, overrides: dict[str, Any]) -> dict[str, Any]:
    return place_order(
        plan["symbol"],
        connection,
        side=plan["side"],
        quantity=plan.get("quantity"),
        notional=plan.get("notional"),
        order_type=plan.get("order_type") or "market",
        limit_price=plan.get("limit_price"),
        time_in_force=plan.get("time_in_force") or "day",
        **overrides,
    )


def _idempotency_key(kwargs: dict[str, Any]) -> str | None:
    return _connection(kwargs.get("idempotency_key"))


class TradingReplaceOrderTool(BaseTool):
    """Cancel an existing order and place a replacement order."""

    name = "trading_replace_order"
    description = (
        "Replace an order by canceling an existing order id and placing a new "
        "order through the same trading connector. Defaults to dry_run=true."
    )
    parameters = {
        "type": "object",
        "properties": {
            "connection": {"type": "string"},
            "host": {"type": "string"},
            "port": {"type": "integer"},
            "client_id": {"type": "integer"},
            "account": {"type": "string"},
            "order_id": {"type": "string"},
            "symbol": {"type": "string"},
            "side": {"type": "string", "enum": ["buy", "sell"]},
            "quantity": {"type": "number"},
            "notional": {"type": "number"},
            "order_type": {"type": "string", "enum": ["market", "limit"], "default": "market"},
            "limit_price": {"type": "number"},
            "time_in_force": {"type": "string", "enum": ["day", "gtc"], "default": "day"},
            "dry_run": {"type": "boolean", "default": True},
            "idempotency_key": idempotency_schema_property(),
        },
        "required": ["order_id", "symbol", "side"],
    }
    repeatable = False
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        connection = _connection(kwargs.get("connection"))
        dry_run = _bool(kwargs.get("dry_run"), default=True)
        overrides = _overrides(kwargs)
        replacement = _planned_order(
            symbol=str(kwargs["symbol"]),
            side=str(kwargs["side"]),
            quantity=_num_or_none(kwargs.get("quantity")),
            notional=_num_or_none(kwargs.get("notional")),
            order_type=str(kwargs.get("order_type") or "market"),
            limit_price=_num_or_none(kwargs.get("limit_price")),
            time_in_force=str(kwargs.get("time_in_force") or "day"),
        )
        plan = {
            "operation": "replace_order",
            "dry_run": dry_run,
            "actions": [
                {"type": "cancel_order", "order_id": str(kwargs["order_id"])},
                {"type": "place_order", **replacement},
            ],
        }
        if dry_run:
            return _json({"status": "dry_run", **plan})
        def _execute() -> dict[str, Any]:
            cancel = cancel_order(str(kwargs["order_id"]), connection, symbol=replacement["symbol"], **overrides)
            if str(cancel.get("status") or "").lower() != "ok":
                return {"status": "blocked", **plan, "cancel_result": cancel}
            placed = _execute_order(replacement, connection, overrides)
            status = "ok" if str(placed.get("status") or "").lower() == "ok" else "blocked"
            return {"status": status, **plan, "cancel_result": cancel, "place_result": placed}

        return _json(run_once(tool_name=self.name, request=plan, idempotency_key=_idempotency_key(kwargs), execute=_execute))


class TradingCancelAllOrdersTool(BaseTool):
    """Cancel all open orders for a connector, optionally filtered by symbol."""

    name = "trading_cancel_all_orders"
    description = "Cancel all open orders for a trading connector. Defaults to dry_run=true."
    parameters = {
        "type": "object",
        "properties": {
            "connection": {"type": "string"},
            "host": {"type": "string"},
            "port": {"type": "integer"},
            "client_id": {"type": "integer"},
            "account": {"type": "string"},
            "symbol": {"type": "string", "description": "Optional symbol filter."},
            "dry_run": {"type": "boolean", "default": True},
            "idempotency_key": idempotency_schema_property(),
        },
        "required": [],
    }
    repeatable = False
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        connection = _connection(kwargs.get("connection"))
        dry_run = _bool(kwargs.get("dry_run"), default=True)
        overrides = _overrides(kwargs)
        symbol_filter = _connection(kwargs.get("symbol"))
        target_symbol = symbol_filter.upper() if symbol_filter else None
        orders_payload = get_open_orders(connection, **overrides)
        rows = orders_payload.get("open_orders") if isinstance(orders_payload, dict) else None
        if not isinstance(rows, list):
            return _json({"status": "blocked", "operation": "cancel_all_orders", "reason": "open orders unavailable", "source": orders_payload})
        actions = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            oid = _order_id(row)
            sym = _order_symbol(row)
            if not oid:
                continue
            if target_symbol and sym and sym != target_symbol:
                continue
            actions.append({"type": "cancel_order", "order_id": oid, "symbol": sym})
        if dry_run:
            return _json({"status": "dry_run", "operation": "cancel_all_orders", "dry_run": True, "actions": actions})
        request = {"operation": "cancel_all_orders", "dry_run": False, "connection": connection, "actions": actions, "overrides": overrides}
        def _execute() -> dict[str, Any]:
            results = [cancel_order(item["order_id"], connection, symbol=item.get("symbol"), **overrides) for item in actions]
            ok = all(str(item.get("status") or "").lower() == "ok" for item in results)
            return {"status": "ok" if ok else "blocked", "operation": "cancel_all_orders", "dry_run": False, "actions": actions, "results": results}

        return _json(run_once(tool_name=self.name, request=request, idempotency_key=_idempotency_key(kwargs), execute=_execute))


class TradingClosePositionTool(BaseTool):
    """Close or reduce one open position."""

    name = "trading_close_position"
    description = "Close or reduce a position by placing the opposite-side order. Defaults to dry_run=true."
    parameters = {
        "type": "object",
        "properties": {
            "connection": {"type": "string"},
            "host": {"type": "string"},
            "port": {"type": "integer"},
            "client_id": {"type": "integer"},
            "account": {"type": "string"},
            "symbol": {"type": "string"},
            "percent": {"type": "number", "default": 100},
            "order_type": {"type": "string", "enum": ["market", "limit"], "default": "market"},
            "limit_price": {"type": "number"},
            "time_in_force": {"type": "string", "enum": ["day", "gtc"], "default": "day"},
            "dry_run": {"type": "boolean", "default": True},
            "idempotency_key": idempotency_schema_property(),
        },
        "required": ["symbol"],
    }
    repeatable = False
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        connection = _connection(kwargs.get("connection"))
        dry_run = _bool(kwargs.get("dry_run"), default=True)
        overrides = _overrides(kwargs)
        symbol = str(kwargs["symbol"]).upper()
        positions = get_positions(connection, **overrides)
        rows = positions.get("positions") if isinstance(positions, dict) else None
        if not isinstance(rows, list):
            return _json({"status": "blocked", "operation": "close_position", "reason": "positions unavailable", "source": positions})
        match = next((row for row in rows if isinstance(row, dict) and _position_symbol(row) == symbol), None)
        qty = _position_qty(match or {})
        if qty == 0:
            return _json({"status": "blocked", "operation": "close_position", "reason": "position not found or already flat", "symbol": symbol})
        percent = max(0.0, min(100.0, float(kwargs.get("percent") or 100)))
        close_qty = abs(qty) * percent / 100.0
        plan = _planned_order(
            symbol=symbol,
            side="sell" if qty > 0 else "buy",
            quantity=close_qty,
            order_type=str(kwargs.get("order_type") or "market"),
            limit_price=_num_or_none(kwargs.get("limit_price")),
            time_in_force=str(kwargs.get("time_in_force") or "day"),
        )
        if dry_run:
            return _json({"status": "dry_run", "operation": "close_position", "dry_run": True, "actions": [{"type": "place_order", **plan}]})
        request = {"operation": "close_position", "dry_run": False, "connection": connection, "actions": [{"type": "place_order", **plan}], "overrides": overrides}
        def _execute() -> dict[str, Any]:
            result = _execute_order(plan, connection, overrides)
            return {"status": "ok" if str(result.get("status") or "").lower() == "ok" else "blocked", "operation": "close_position", "dry_run": False, "actions": [{"type": "place_order", **plan}], "result": result}

        return _json(run_once(tool_name=self.name, request=request, idempotency_key=_idempotency_key(kwargs), execute=_execute))


class TradingFlattenAccountTool(BaseTool):
    """Close all non-zero positions."""

    name = "trading_flatten_account"
    description = "Flatten all non-zero positions by placing opposite-side orders. Defaults to dry_run=true."
    parameters = {
        "type": "object",
        "properties": {
            "connection": {"type": "string"},
            "host": {"type": "string"},
            "port": {"type": "integer"},
            "client_id": {"type": "integer"},
            "account": {"type": "string"},
            "order_type": {"type": "string", "enum": ["market", "limit"], "default": "market"},
            "time_in_force": {"type": "string", "enum": ["day", "gtc"], "default": "day"},
            "dry_run": {"type": "boolean", "default": True},
            "idempotency_key": idempotency_schema_property(),
        },
        "required": [],
    }
    repeatable = False
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        connection = _connection(kwargs.get("connection"))
        dry_run = _bool(kwargs.get("dry_run"), default=True)
        overrides = _overrides(kwargs)
        positions = get_positions(connection, **overrides)
        rows = positions.get("positions") if isinstance(positions, dict) else None
        if not isinstance(rows, list):
            return _json({"status": "blocked", "operation": "flatten_account", "reason": "positions unavailable", "source": positions})
        actions = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            sym = _position_symbol(row)
            qty = _position_qty(row)
            if not sym or qty == 0:
                continue
            actions.append({"type": "place_order", **_planned_order(symbol=sym, side="sell" if qty > 0 else "buy", quantity=abs(qty), order_type=str(kwargs.get("order_type") or "market"), time_in_force=str(kwargs.get("time_in_force") or "day"))})
        if dry_run:
            return _json({"status": "dry_run", "operation": "flatten_account", "dry_run": True, "actions": actions})
        request = {"operation": "flatten_account", "dry_run": False, "connection": connection, "actions": actions, "overrides": overrides}
        def _execute() -> dict[str, Any]:
            results = [_execute_order({k: v for k, v in action.items() if k != "type"}, connection, overrides) for action in actions]
            ok = all(str(item.get("status") or "").lower() == "ok" for item in results)
            return {"status": "ok" if ok else "blocked", "operation": "flatten_account", "dry_run": False, "actions": actions, "results": results}

        return _json(run_once(tool_name=self.name, request=request, idempotency_key=_idempotency_key(kwargs), execute=_execute))


class TradingRebalanceTargetsTool(BaseTool):
    """Generate or execute quantity-based target-position orders."""

    name = "trading_rebalance_targets"
    description = "Rebalance to target quantities by placing delta orders. Defaults to dry_run=true."
    parameters = {
        "type": "object",
        "properties": {
            "connection": {"type": "string"},
            "host": {"type": "string"},
            "port": {"type": "integer"},
            "client_id": {"type": "integer"},
            "account": {"type": "string"},
            "targets": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {"symbol": {"type": "string"}, "target_quantity": {"type": "number"}},
                    "required": ["symbol", "target_quantity"],
                },
            },
            "order_type": {"type": "string", "enum": ["market", "limit"], "default": "market"},
            "time_in_force": {"type": "string", "enum": ["day", "gtc"], "default": "day"},
            "dry_run": {"type": "boolean", "default": True},
            "idempotency_key": idempotency_schema_property(),
        },
        "required": ["targets"],
    }
    repeatable = False
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        connection = _connection(kwargs.get("connection"))
        dry_run = _bool(kwargs.get("dry_run"), default=True)
        overrides = _overrides(kwargs)
        positions = get_positions(connection, **overrides)
        rows = positions.get("positions") if isinstance(positions, dict) else None
        if not isinstance(rows, list):
            return _json({"status": "blocked", "operation": "rebalance_targets", "reason": "positions unavailable", "source": positions})
        current = {_position_symbol(row): _position_qty(row) for row in rows if isinstance(row, dict) and _position_symbol(row)}
        actions = []
        for target in kwargs.get("targets") or []:
            if not isinstance(target, dict):
                continue
            sym = str(target.get("symbol") or "").upper()
            if not sym:
                continue
            delta = float(target.get("target_quantity") or 0) - float(current.get(sym, 0.0))
            if delta == 0:
                continue
            actions.append({"type": "place_order", **_planned_order(symbol=sym, side="buy" if delta > 0 else "sell", quantity=abs(delta), order_type=str(kwargs.get("order_type") or "market"), time_in_force=str(kwargs.get("time_in_force") or "day"))})
        if dry_run:
            return _json({"status": "dry_run", "operation": "rebalance_targets", "dry_run": True, "actions": actions})
        request = {"operation": "rebalance_targets", "dry_run": False, "connection": connection, "actions": actions, "overrides": overrides}
        def _execute() -> dict[str, Any]:
            results = [_execute_order({k: v for k, v in action.items() if k != "type"}, connection, overrides) for action in actions]
            ok = all(str(item.get("status") or "").lower() == "ok" for item in results)
            return {"status": "ok" if ok else "blocked", "operation": "rebalance_targets", "dry_run": False, "actions": actions, "results": results}

        return _json(run_once(tool_name=self.name, request=request, idempotency_key=_idempotency_key(kwargs), execute=_execute))


class TradingAdvancedOrderProposalTool(BaseTool):
    """Describe advanced orders without pretending every broker supports them."""

    name = "trading_advanced_order_proposal"
    description = (
        "Create a proposal for bracket/OCO/stop-loss/take-profit/trailing-stop "
        "orders. This does not place orders; connector-native support must be "
        "implemented and tested per broker before execution."
    )
    parameters = {
        "type": "object",
        "properties": {
            "symbol": {"type": "string"},
            "side": {"type": "string", "enum": ["buy", "sell"]},
            "quantity": {"type": "number"},
            "entry_order_type": {"type": "string", "enum": ["market", "limit"], "default": "market"},
            "entry_limit_price": {"type": "number"},
            "take_profit_price": {"type": "number"},
            "stop_loss_price": {"type": "number"},
            "trailing_percent": {"type": "number"},
            "time_in_force": {"type": "string", "enum": ["day", "gtc"], "default": "day"},
        },
        "required": ["symbol", "side", "quantity"],
    }
    repeatable = True
    is_readonly = True

    def execute(self, **kwargs: Any) -> str:
        return _json(
            {
                "status": "proposal_only",
                "operation": "advanced_order_proposal",
                "reason": "connector-native bracket/OCO/trailing-stop execution is not enabled generically",
                "proposal": dict(kwargs),
                "execution_supported": False,
            }
        )
