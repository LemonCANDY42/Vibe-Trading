"""Idempotency tests for Agent-facing trading operations."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from src.tools.moirix_trade_execution_tool import MoirixTradeExecutionTool
from src.tools.trading_connector_tool import TradingPlaceOrderTool
from src.tools.trading_execution_ops_tool import TradingReplaceOrderTool
from src.trading import idempotency
from src.trading.paper_gate import APPROVAL_SCHEMA_VERSION, build_paper_request, canonical_request_hash

pytestmark = pytest.mark.unit


def _approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    tool_name: str,
    actions: list[dict[str, object]],
    connection: str = "ibkr-paper-trade",
    account: str = "",
    proposal_sha256: str | None = None,
    estimated_prices: dict[str, float] | None = None,
) -> Path:
    monkeypatch.setenv("VIBE_TRADING_ALLOWED_FILE_ROOTS", str(tmp_path))
    request = build_paper_request(
        operation=tool_name,
        connection=connection,
        account=account,
        actions=actions,
        proposal_sha256=proposal_sha256,
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
                "estimated_prices": estimated_prices or {"AAPL": 100.0},
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


def test_run_once_replays_same_request(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(idempotency, "get_runtime_root", lambda: tmp_path)
    calls = []

    first = idempotency.run_once(
        tool_name="tool",
        request={"symbol": "AAPL", "quantity": 1},
        idempotency_key="k1",
        execute=lambda: calls.append("called") or {"status": "ok", "order_id": "o1"},
    )
    second = idempotency.run_once(
        tool_name="tool",
        request={"symbol": "AAPL", "quantity": 1},
        idempotency_key="k1",
        execute=lambda: calls.append("called-again") or {"status": "ok", "order_id": "o2"},
    )

    assert first["status"] == "ok"
    assert first["idempotency"]["status"] == "recorded"
    assert second["status"] == "ok"
    assert second["order_id"] == "o1"
    assert second["idempotency"]["status"] == "replayed"
    assert calls == ["called"]


def test_run_once_blocks_key_reuse_with_different_request(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(idempotency, "get_runtime_root", lambda: tmp_path)

    idempotency.run_once(
        tool_name="tool",
        request={"symbol": "AAPL"},
        idempotency_key="same",
        execute=lambda: {"status": "ok"},
    )
    second = idempotency.run_once(
        tool_name="tool",
        request={"symbol": "MSFT"},
        idempotency_key="same",
        execute=lambda: {"status": "ok", "should_not": "run"},
    )

    assert second["status"] == "blocked"
    assert second["claim_gate"]["blockers"] == ["idempotency_key_reused_with_different_request"]


def test_trading_place_order_tool_replays_duplicate(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(idempotency, "get_runtime_root", lambda: tmp_path)
    calls = []
    monkeypatch.setattr(
        "src.tools.trading_connector_tool.place_order",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"status": "ok", "order_id": "p1"},
    )

    kwargs = {
        "connection": "ibkr-paper-trade",
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 1,
        "dry_run": False,
        "approval_path": str(
            _approval(
                tmp_path,
                monkeypatch,
                tool_name="trading_place_order",
                actions=[
                    {
                        "type": "place_order",
                        "symbol": "AAPL",
                        "side": "buy",
                        "quantity": 1.0,
                        "notional": None,
                        "order_type": "market",
                        "limit_price": None,
                        "time_in_force": "day",
                        "overrides": {"host": None, "port": None, "client_id": None, "account": None},
                    }
                ],
            )
        ),
    }
    first = json.loads(TradingPlaceOrderTool().execute(**kwargs))
    second = json.loads(TradingPlaceOrderTool().execute(**kwargs))

    assert first["idempotency"]["status"] == "recorded"
    assert second["idempotency"]["status"] == "replayed"
    assert second["order_id"] == "p1"
    assert len(calls) == 1


def test_replace_order_replays_duplicate_execution(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.setattr(idempotency, "get_runtime_root", lambda: tmp_path)
    calls = []
    monkeypatch.setattr(
        "src.tools.trading_execution_ops_tool.cancel_order",
        lambda *args, **kwargs: calls.append(("cancel", args, kwargs)) or {"status": "ok"},
    )
    monkeypatch.setattr(
        "src.tools.trading_execution_ops_tool.place_order",
        lambda *args, **kwargs: calls.append(("place", args, kwargs)) or {"status": "ok", "order_id": "new"},
    )
    kwargs = {
        "connection": "ibkr-paper-trade",
        "order_id": "123",
        "symbol": "AAPL",
        "side": "buy",
        "quantity": 1,
        "dry_run": False,
        "approval_path": str(
            _approval(
                tmp_path,
                monkeypatch,
                tool_name="trading_replace_order",
                actions=[
                    {"type": "cancel_order", "order_id": "123", "overrides": {"host": None, "port": None, "client_id": None, "account": None}},
                    {
                        "type": "place_order",
                        "symbol": "AAPL",
                        "side": "buy",
                        "quantity": 1.0,
                        "notional": None,
                        "order_type": "market",
                        "limit_price": None,
                        "time_in_force": "day",
                        "overrides": {"host": None, "port": None, "client_id": None, "account": None},
                    },
                ],
            )
        ),
    }

    first = json.loads(TradingReplaceOrderTool().execute(**kwargs))
    second = json.loads(TradingReplaceOrderTool().execute(**kwargs))

    assert first["idempotency"]["status"] == "recorded"
    assert second["idempotency"]["status"] == "replayed"
    assert len(calls) == 2


def test_moirix_execution_replays_duplicate_approved_proposal(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    monkeypatch.setattr(idempotency, "get_runtime_root", lambda: tmp_path)
    monkeypatch.setenv("VIBE_TRADING_ALLOWED_RUN_ROOTS", str(tmp_path))
    run_dir = tmp_path / "run"
    artifact_dir = run_dir / "artifacts" / "moirix"
    artifact_dir.mkdir(parents=True)
    proposal = {
        "schema_version": "vibe.moirix_trade_proposal.v1",
        "authority": {"ready_for_real_money_trading_authority": False},
        "orders": [{"symbol": "AAPL", "side": "buy", "quantity": 1, "order_type": "market"}],
    }
    proposal_path = artifact_dir / "trade_proposal.json"
    proposal_path.write_text(json.dumps(proposal), encoding="utf-8")
    import hashlib

    proposal_hash = hashlib.sha256(proposal_path.read_bytes()).hexdigest()
    approval_path = artifact_dir / "execution_approval.json"
    _approval(
        artifact_dir,
        monkeypatch,
        tool_name="moirix_execute_trade_proposal",
        actions=proposal["orders"],
        connection="ibkr-paper-trade",
        proposal_sha256=proposal_hash,
    )
    approval_path = artifact_dir / "moirix_execute_trade_proposal-approval.json"
    calls = []
    monkeypatch.setattr(
        "src.tools.moirix_trade_execution_tool.place_order",
        lambda *args, **kwargs: calls.append((args, kwargs)) or {"status": "ok", "order_id": "m1"},
    )
    kwargs = {
        "run_dir": str(run_dir),
        "approval_path": str(approval_path),
        "connection": "ibkr-paper-trade",
        "dry_run": False,
    }

    first = json.loads(MoirixTradeExecutionTool().execute(**kwargs))
    second = json.loads(MoirixTradeExecutionTool().execute(**kwargs))

    assert first["status"] == "ok"
    assert first["idempotency"]["status"] == "recorded"
    assert second["status"] == "ok"
    assert second["idempotency"]["status"] == "replayed"
    assert len(calls) == 1
