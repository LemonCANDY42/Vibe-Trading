"""Tests for connector-first trading profile operations."""

from __future__ import annotations

import json
import math
from types import SimpleNamespace

import pytest

from src.trading import profiles, service
from src.tools import build_registry
from src.tools.ibkr_paper_readiness_tool import IBKRPaperReadinessTool
from src.tools.trading_connector_tool import TradingSelectConnectionTool

pytestmark = pytest.mark.unit


def _agent_config(server) -> SimpleNamespace:
    return SimpleNamespace(mcp_servers={"robinhood": server})


def test_remote_call_requires_enabled_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generic remote reads must respect the operator MCP allowlist."""
    server = SimpleNamespace(
        url="https://agent.robinhood.com/mcp/trading",
        enabled_tools=["get_account"],
        auth=SimpleNamespace(cache_dir="/tmp/vibe-no-token"),
    )
    monkeypatch.setattr("src.config.loader.load_agent_config", lambda: _agent_config(server))
    monkeypatch.setattr("src.live.registry.has_cached_oauth_token", lambda *_: True)

    result = service.get_positions("robinhood-live-mcp")

    assert result["status"] == "error"
    assert "not enabled" in result["error"]


def test_remote_call_requires_cached_oauth(monkeypatch: pytest.MonkeyPatch) -> None:
    """Generic remote reads must not trigger OAuth from tool/API/MCP paths."""
    server = SimpleNamespace(
        url="https://agent.robinhood.com/mcp/trading",
        enabled_tools=["get_positions"],
        auth=SimpleNamespace(cache_dir="/tmp/vibe-no-token"),
    )
    monkeypatch.setattr("src.config.loader.load_agent_config", lambda: _agent_config(server))
    monkeypatch.setattr("src.live.registry.has_cached_oauth_token", lambda *_: False)

    result = service.get_positions("robinhood-live-mcp")

    assert result["status"] == "not_authorized"
    assert "connector authorize robinhood-live-mcp" in result["error"]


def test_ibkr_official_profile_does_not_advertise_unknown_generic_reads() -> None:
    """IBKR official MCP stays honest until stable remote tool names are known."""
    profile = profiles.profile_by_id("ibkr-live-official-mcp-readonly")

    assert profile.capabilities == ("mcp.read.discovery",)
    result = service.get_account(profile.id)
    assert result["status"] == "error"
    assert "does not support" in result["error"]


def test_ibkr_paper_trade_profile_exposes_paper_orders_only() -> None:
    profile = profiles.profile_by_id("ibkr-paper-trade")
    live = profiles.profile_by_id("ibkr-live-local-readonly")

    assert profile.connector == "ibkr"
    assert profile.environment == "paper"
    assert profile.transport == "local_tws"
    assert profile.readonly is False
    assert "orders.place" in profile.capabilities
    assert live.readonly is True
    assert "orders.place" not in live.capabilities


def test_connector_profile_id_for_broker_prefers_live_remote_mcp() -> None:
    """Broker on-ramps should resolve through the centralized profile registry."""
    assert service.connector_profile_id_for_broker("robinhood") == "robinhood-live-mcp"
    assert service.connector_profile_id_for_broker("ibkr") == "ibkr-live-official-mcp-readonly"
    assert service.connector_profile_id_for_broker("futurebroker") == "futurebroker-live-mcp"


def test_select_connection_tool_returns_canonical_profile_id(
    monkeypatch: pytest.MonkeyPatch, tmp_path
) -> None:
    """Selecting a profile should persist and return the canonical id."""
    monkeypatch.setattr(profiles, "get_runtime_root", lambda: tmp_path)

    result = TradingSelectConnectionTool().execute(connection="IBKR-PAPER-LOCAL")

    assert result
    payload = json.loads(result)
    assert payload["status"] == "ok"
    assert payload["selected_profile"] == "ibkr-paper-local"
    assert profiles.load_selected_profile_id() == "ibkr-paper-local"


def test_live_broker_mcp_wrappers_are_hidden_from_agent_registry(monkeypatch: pytest.MonkeyPatch) -> None:
    """Connector-first registry must not expose broker-specific mcp_* tools."""
    server = SimpleNamespace(
        url="https://agent.robinhood.com/mcp/trading",
        enabled_tools=["get_positions"],
        auth=SimpleNamespace(cache_dir="/tmp/vibe-token"),
    )
    agent_config = SimpleNamespace(mcp_servers={"robinhood": server})
    monkeypatch.setattr("src.live.registry.is_live_broker", lambda *_: True)
    monkeypatch.setattr("src.live.registry.should_register_live_channel", lambda **_: True)

    def fail_build_wrappers(*_, **__):
        raise AssertionError("live broker wrappers should not be registered directly")

    monkeypatch.setattr("src.tools.mcp.build_mcp_tool_wrappers", fail_build_wrappers)

    registry = build_registry(agent_config=agent_config, include_shell_tools=False)

    assert "trading_positions" in registry.tool_names
    assert not any(name.startswith("mcp_robinhood_") for name in registry.tool_names)


def test_ibkr_paper_readiness_writes_readonly_artifact(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """IBKR paper readiness should use read APIs only and write a run artifact."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    monkeypatch.setenv("VIBE_TRADING_ALLOWED_RUN_ROOTS", str(tmp_path))
    monkeypatch.setattr(
        "src.tools.ibkr_paper_readiness_tool.tcp_port_open",
        lambda _host, port: int(port) == 4002,
    )
    calls: list[tuple[str, str, dict]] = []

    def _record(name: str, payload: dict):
        def inner(profile_id: str, **kwargs):
            calls.append((name, profile_id, kwargs))
            return {"status": "ok", **payload}

        return inner

    monkeypatch.setattr(
        "src.tools.ibkr_paper_readiness_tool.service.check_connection",
        _record("check", {"sdk": {"installed": True}, "target": {"open": True}}),
    )
    monkeypatch.setattr(
        "src.tools.ibkr_paper_readiness_tool.service.get_account",
        _record("account", {"accounts": ["DU12345"], "summary": []}),
    )
    monkeypatch.setattr(
        "src.tools.ibkr_paper_readiness_tool.service.get_positions",
        _record("positions", {"positions": []}),
    )

    def _orders(profile_id: str, *, include_executions: bool = False, **kwargs):
        calls.append(("orders", profile_id, {**kwargs, "include_executions": include_executions}))
        return {"status": "ok", "open_orders": [], "executions": []}

    def _quote(symbol: str, profile_id: str, **kwargs):
        calls.append(("quote", profile_id, {**kwargs, "symbol": symbol}))
        return {"status": "ok", "quote": {"last": 100.0}}

    def _history(symbol: str, profile_id: str, **kwargs):
        calls.append(("history", profile_id, {**kwargs, "symbol": symbol}))
        return {"status": "ok", "bars": [{"date": "2026-06-11", "close": 100.0}]}

    monkeypatch.setattr("src.tools.ibkr_paper_readiness_tool.service.get_open_orders", _orders)
    monkeypatch.setattr("src.tools.ibkr_paper_readiness_tool.service.get_quote", _quote)
    monkeypatch.setattr("src.tools.ibkr_paper_readiness_tool.service.get_history", _history)

    payload = json.loads(IBKRPaperReadinessTool().execute(run_dir=str(run_dir), symbol="AAPL"))

    assert payload["status"] == "ok"
    assert payload["endpoint"]["port"] == 4002
    assert payload["endpoint"]["profile_default_port"] == 4002
    assert payload["endpoint"]["auto_selected_gateway_paper_port"] is False
    assert payload["read_only_contract"]["no_order_api_calls"] is True
    assert payload["authority"]["ready_for_real_money_trading_authority"] is False
    assert payload["claim_gate"]["ready_for_real_money_trading_authority"] is False
    assert (run_dir / "artifacts" / "ibkr" / "ibkr_paper_readiness.json").exists()
    assert {call[0] for call in calls} == {"check", "account", "positions", "orders", "quote", "history"}
    assert all(call[1] == "ibkr-paper-local" for call in calls)


def test_ibkr_paper_readiness_rejects_client_id_zero(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """Client id zero is rejected because it can bind manually entered orders."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    monkeypatch.setenv("VIBE_TRADING_ALLOWED_RUN_ROOTS", str(tmp_path))

    def fail_if_called(*_args, **_kwargs):
        raise AssertionError("broker checks should not run")

    monkeypatch.setattr("src.tools.ibkr_paper_readiness_tool.service.check_connection", fail_if_called)

    payload = json.loads(IBKRPaperReadinessTool().execute(run_dir=str(run_dir), client_id=0))

    assert payload["status"] == "blocked"
    assert payload["claim_gate"]["blockers"] == ["ibkr_client_id_zero_rejected"]
    assert payload["authority"]["ready_for_real_money_trading_authority"] is False
    assert (run_dir / "artifacts" / "ibkr" / "ibkr_paper_readiness.json").exists()


def test_ibkr_paper_readiness_blocks_empty_quote_snapshot(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path,
) -> None:
    """An all-NaN quote snapshot is a market-data blocker, not readiness success."""
    run_dir = tmp_path / "run"
    run_dir.mkdir()
    monkeypatch.setenv("VIBE_TRADING_ALLOWED_RUN_ROOTS", str(tmp_path))
    monkeypatch.setattr("src.tools.ibkr_paper_readiness_tool.tcp_port_open", lambda *_: True)

    def _ok(payload: dict):
        return lambda *_args, **_kwargs: {"status": "ok", **payload}

    monkeypatch.setattr(
        "src.tools.ibkr_paper_readiness_tool.service.check_connection",
        _ok({"sdk": {"installed": True}, "target": {"open": True}}),
    )
    monkeypatch.setattr(
        "src.tools.ibkr_paper_readiness_tool.service.get_account",
        _ok({"accounts": ["DU12345"], "summary": []}),
    )
    monkeypatch.setattr("src.tools.ibkr_paper_readiness_tool.service.get_positions", _ok({"positions": []}))
    monkeypatch.setattr(
        "src.tools.ibkr_paper_readiness_tool.service.get_open_orders",
        lambda *_args, **_kwargs: {"status": "ok", "open_orders": [], "executions": []},
    )
    monkeypatch.setattr(
        "src.tools.ibkr_paper_readiness_tool.service.get_quote",
        lambda *_args, **_kwargs: {
            "status": "ok",
            "quote": {"bid": math.nan, "ask": math.nan, "last": math.nan, "close": math.nan},
        },
    )
    monkeypatch.setattr(
        "src.tools.ibkr_paper_readiness_tool.service.get_history",
        lambda *_args, **_kwargs: {"status": "ok", "bars": [{"date": "2026-06-11", "close": 100.0}]},
    )

    payload = json.loads(IBKRPaperReadinessTool().execute(run_dir=str(run_dir)))
    artifact_text = (run_dir / "artifacts" / "ibkr" / "ibkr_paper_readiness.json").read_text(encoding="utf-8")

    assert payload["status"] == "blocked"
    assert "ibkr_paper_market_data_blocked" in payload["claim_gate"]["blockers"]
    assert payload["checks"]["market_data_permission"]["status"] == "blocked"
    assert "NaN" not in artifact_text
    assert '"bid": null' in artifact_text


def test_ibkr_paper_readiness_tool_is_discovered() -> None:
    """The paper readiness check should be available through normal registry discovery."""
    registry = build_registry(include_shell_tools=False)

    assert "ibkr_paper_readiness" in registry.tool_names
