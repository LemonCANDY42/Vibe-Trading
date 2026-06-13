"""Idempotency tests for Agent-facing trading operations."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.tools.moirix_trade_execution_tool import MoirixTradeExecutionTool
from src.tools.trading_connector_tool import TradingPlaceOrderTool
from src.tools.trading_execution_ops_tool import TradingReplaceOrderTool
from src.trading import idempotency

pytestmark = pytest.mark.unit


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
        "idempotency_key": "place-aapl-1",
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
        "idempotency_key": "replace-123",
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
    approval_path.write_text(
        json.dumps(
            {
                "approved": True,
                "scope": "paper",
                "proposal_sha256": proposal_hash,
                "authority": {
                    "paper_trade_proposal_allowed": True,
                    "broker_submit_allowed": True,
                    "ready_for_real_money_trading_authority": False,
                },
            }
        ),
        encoding="utf-8",
    )
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
