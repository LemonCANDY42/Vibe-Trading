"""Tests for high-level trading execution operation tools."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.trading.paper_gate import APPROVAL_SCHEMA_VERSION, build_paper_request, canonical_request_hash
from src.tools import build_registry
from src.tools.trading_execution_ops_tool import (
    TradingAdvancedOrderProposalTool,
    TradingCancelAllOrdersTool,
    TradingClosePositionTool,
    TradingFlattenAccountTool,
    TradingRebalanceTargetsTool,
    TradingReplaceOrderTool,
)

pytestmark = pytest.mark.unit


def _overrides(account: str | None = None) -> dict[str, object]:
    return {"host": None, "port": None, "client_id": None, "account": account}


def _approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    tool_name: str,
    actions: list[dict[str, object]],
    connection: str = "ibkr-paper-trade",
    account: str = "",
    estimated_prices: dict[str, float] | None = None,
    overrides: dict[str, object] | None = None,
) -> Path:
    monkeypatch.setenv("VIBE_TRADING_ALLOWED_FILE_ROOTS", str(tmp_path))
    request = build_paper_request(
        operation=tool_name,
        connection=connection,
        account=account,
        actions=[{**action, "overrides": overrides or _overrides(account or None)} for action in actions],
    )
    path = tmp_path / f"{tool_name}-approval.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": APPROVAL_SCHEMA_VERSION,
                "approval_id": f"{tool_name}-pytest",
                "approved": True,
                "scope": "paper",
                "execution_mode": "paper",
                "connection": connection,
                "account": account,
                "request": request,
                "request_sha256": canonical_request_hash(request),
                "max_notional": 100000,
                "estimated_prices": estimated_prices or {"AAPL": 100.0, "MSFT": 200.0},
                "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).replace(microsecond=0).isoformat(),
                "authority": {
                    "paper_trade_proposal_allowed": True,
                    "broker_submit_allowed": True,
                    "ready_for_real_money_trading_authority": False,
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def test_execution_ops_tools_are_discovered() -> None:
    names = set(build_registry().tool_names)

    assert "trading_replace_order" in names
    assert "trading_cancel_all_orders" in names
    assert "trading_close_position" in names
    assert "trading_flatten_account" in names
    assert "trading_rebalance_targets" in names
    assert "trading_advanced_order_proposal" in names


def test_replace_order_dry_run_does_not_call_broker(monkeypatch: pytest.MonkeyPatch) -> None:
    def fail(*_, **__):
        raise AssertionError("dry-run should not call broker")

    monkeypatch.setattr("src.tools.trading_execution_ops_tool.cancel_order", fail)
    monkeypatch.setattr("src.tools.trading_execution_ops_tool.place_order", fail)

    payload = json.loads(
        TradingReplaceOrderTool().execute(
            connection="ibkr-paper-trade",
            order_id="123",
            symbol="AAPL",
            side="buy",
            quantity=1,
            order_type="limit",
            limit_price=100,
        )
    )

    assert payload["status"] == "dry_run"
    assert [item["type"] for item in payload["actions"]] == ["cancel_order", "place_order"]


def test_replace_order_executes_cancel_then_place(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    calls = []
    monkeypatch.setattr(
        "src.tools.trading_execution_ops_tool.cancel_order",
        lambda order_id, connection, **kwargs: calls.append(("cancel", order_id, connection, kwargs)) or {"status": "ok"},
    )
    monkeypatch.setattr(
        "src.tools.trading_execution_ops_tool.place_order",
        lambda symbol, connection, **kwargs: calls.append(("place", symbol, connection, kwargs)) or {"status": "ok", "order_id": "new"},
    )

    actions = [
        {"type": "cancel_order", "order_id": "123"},
        {
            "type": "place_order",
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 1.0,
            "notional": None,
            "order_type": "market",
            "limit_price": None,
            "time_in_force": "day",
        },
    ]
    approval = _approval(tmp_path, monkeypatch, tool_name="trading_replace_order", actions=actions)

    payload = json.loads(
        TradingReplaceOrderTool().execute(
            connection="ibkr-paper-trade",
            order_id="123",
            symbol="AAPL",
            side="buy",
            quantity=1,
            dry_run=False,
            approval_path=str(approval),
        )
    )

    assert payload["status"] == "ok"
    assert calls[0][0] == "cancel"
    assert calls[1][0] == "place"


def test_replace_order_blocks_without_paper_approval(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.tools.trading_execution_ops_tool.cancel_order",
        lambda *_args, **_kwargs: {"status": "ok"},
    )
    payload = json.loads(
        TradingReplaceOrderTool().execute(
            connection="ibkr-paper-trade",
            order_id="123",
            symbol="AAPL",
            side="buy",
            quantity=1,
            dry_run=False,
        )
    )

    assert payload["status"] == "blocked"
    assert "paper_execution_approval_missing" in payload["claim_gate"]["blockers"]


def test_replace_order_blocks_ibkr_client_id_zero_at_paper_gate(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    calls = []
    monkeypatch.setattr(
        "src.tools.trading_execution_ops_tool.cancel_order",
        lambda *args, **kwargs: calls.append(("cancel", args, kwargs)) or {"status": "ok"},
    )
    actions = [
        {"type": "cancel_order", "order_id": "123"},
        {
            "type": "place_order",
            "symbol": "AAPL",
            "side": "buy",
            "quantity": 1.0,
            "notional": None,
            "order_type": "market",
            "limit_price": None,
            "time_in_force": "day",
        },
    ]
    approval = _approval(
        tmp_path,
        monkeypatch,
        tool_name="trading_replace_order",
        actions=actions,
        overrides={"host": None, "port": None, "client_id": 0, "account": None},
    )

    payload = json.loads(
        TradingReplaceOrderTool().execute(
            connection="ibkr-paper-trade",
            order_id="123",
            symbol="AAPL",
            side="buy",
            quantity=1,
            client_id=0,
            dry_run=False,
            approval_path=str(approval),
        )
    )

    assert payload["status"] == "blocked"
    assert "paper_execution_ibkr_client_id_zero_blocked" in payload["claim_gate"]["blockers"]
    assert calls == []


def test_cancel_all_orders_filters_symbol(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.tools.trading_execution_ops_tool.get_open_orders",
        lambda *_, **__: {
            "status": "ok",
            "open_orders": [
                {"order": {"order_id": "1"}, "contract": {"symbol": "AAPL"}},
                {"order": {"order_id": "2"}, "contract": {"symbol": "MSFT"}},
            ],
        },
    )
    payload = json.loads(TradingCancelAllOrdersTool().execute(symbol="AAPL"))

    assert payload["status"] == "dry_run"
    assert payload["actions"] == [{"type": "cancel_order", "order_id": "1", "symbol": "AAPL"}]


def test_close_position_builds_opposite_side_order(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.tools.trading_execution_ops_tool.get_positions",
        lambda *_, **__: {"status": "ok", "positions": [{"symbol": "AAPL", "position": 10}]},
    )

    payload = json.loads(TradingClosePositionTool().execute(symbol="AAPL", percent=50))

    assert payload["status"] == "dry_run"
    action = payload["actions"][0]
    assert action["side"] == "sell"
    assert action["quantity"] == 5


def test_flatten_account_builds_orders_for_all_positions(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.tools.trading_execution_ops_tool.get_positions",
        lambda *_, **__: {
            "status": "ok",
            "positions": [
                {"symbol": "AAPL", "position": 10},
                {"symbol": "MSFT", "position": -3},
                {"symbol": "CASH", "position": 0},
            ],
        },
    )

    payload = json.loads(TradingFlattenAccountTool().execute())

    assert payload["status"] == "dry_run"
    assert [(item["symbol"], item["side"], item["quantity"]) for item in payload["actions"]] == [
        ("AAPL", "sell", 10.0),
        ("MSFT", "buy", 3.0),
    ]


def test_rebalance_targets_uses_quantity_delta(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.tools.trading_execution_ops_tool.get_positions",
        lambda *_, **__: {"status": "ok", "positions": [{"symbol": "AAPL", "position": 10}]},
    )

    payload = json.loads(
        TradingRebalanceTargetsTool().execute(
            targets=[{"symbol": "AAPL", "target_quantity": 7}, {"symbol": "MSFT", "target_quantity": 2}]
        )
    )

    assert payload["status"] == "dry_run"
    assert [(item["symbol"], item["side"], item["quantity"]) for item in payload["actions"]] == [
        ("AAPL", "sell", 3.0),
        ("MSFT", "buy", 2.0),
    ]


def test_advanced_order_is_proposal_only() -> None:
    payload = json.loads(
        TradingAdvancedOrderProposalTool().execute(
            symbol="AAPL",
            side="buy",
            quantity=1,
            take_profit_price=150,
            stop_loss_price=120,
        )
    )

    assert payload["status"] == "proposal_only"
    assert payload["execution_supported"] is False
