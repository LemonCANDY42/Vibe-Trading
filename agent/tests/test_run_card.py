"""Tests for Trust Layer run card generation."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd

from backtest.run_card import write_run_card
from src.core.runner import Runner


def test_config_hash_is_deterministic_independent_of_key_order(tmp_path: Path) -> None:
    config_a = {
        "codes": ["AAPL", "MSFT"],
        "start_date": "2025-01-01",
        "end_date": "2025-03-01",
        "interval": "1D",
        "engine": "global_equity",
        "initial_cash": 100000,
        "source": "auto",
        "nested": {"b": 2, "a": 1},
    }
    config_b = {
        "nested": {"a": 1, "b": 2},
        "source": "auto",
        "initial_cash": 100000,
        "engine": "global_equity",
        "interval": "1D",
        "end_date": "2025-03-01",
        "start_date": "2025-01-01",
        "codes": ["AAPL", "MSFT"],
    }

    card_a = write_run_card(tmp_path / "a", config_a, {"sharpe": 1.2})
    card_b = write_run_card(tmp_path / "b", config_b, {"sharpe": 1.2})

    assert card_a["reproducibility"]["config_hash"] == card_b["reproducibility"]["config_hash"]
    assert "nested" not in card_a["backtest"]


def test_strategy_hash_is_included_when_strategy_path_exists(tmp_path: Path) -> None:
    strategy_path = tmp_path / "strategy.py"
    strategy_path.write_text("def signal():\n    return 1\n", encoding="utf-8")

    card = write_run_card(
        tmp_path / "run",
        {"codes": ["BTC-USDT"], "engine": "crypto"},
        {"return_pct": 0.15},
        strategy_path=strategy_path,
    )

    expected_hash = hashlib.sha256(strategy_path.read_bytes()).hexdigest()
    assert card["reproducibility"]["strategy_hash"] == expected_hash


def test_artifact_listing_includes_expected_existing_files(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    (run_dir / "code").mkdir(parents=True)
    (run_dir / "artifacts" / "nested").mkdir(parents=True)
    (run_dir / "config.json").write_text('{"ok": true}\n', encoding="utf-8")
    (run_dir / "code" / "signal_engine.py").write_text("SIGNAL = 1\n", encoding="utf-8")
    (run_dir / "artifacts" / "equity.csv").write_text("date,equity\n", encoding="utf-8")
    (run_dir / "artifacts" / "nested" / "trades.csv").write_text("id,pnl\n", encoding="utf-8")

    card = write_run_card(run_dir, {"codes": ["000001.SZ"]}, {"sharpe": 1.0})

    artifacts = {artifact["path"]: artifact for artifact in card["artifacts"]}
    assert card["reproducibility"]["config_hash"] == hashlib.sha256(
        (run_dir / "config.json").read_bytes()
    ).hexdigest()
    assert list(artifacts) == [
        "artifacts/equity.csv",
        "artifacts/nested/trades.csv",
        "code/signal_engine.py",
        "config.json",
    ]
    for relative_path, artifact in artifacts.items():
        path = run_dir / relative_path
        assert artifact["size_bytes"] == path.stat().st_size
        assert artifact["sha256"] == hashlib.sha256(path.read_bytes()).hexdigest()


def test_json_and_markdown_files_are_written(tmp_path: Path) -> None:
    run_dir = tmp_path / "run"
    metrics = {
        "sharpe": 1.23,
        "max_drawdown": -0.08,
        "validation": {"n_windows": 5, "consistency_rate": 0.8},
        "curve": [1, 2, 3],
    }

    card = write_run_card(
        run_dir,
        {
            "codes": ["AAPL"],
            "start_date": "2025-01-01",
            "end_date": "2025-02-01",
            "interval": "1D",
            "engine": "global_equity",
            "initial_cash": 50000,
            "source": "yfinance",
            "secret": "not copied raw",
        },
        metrics,
        data_sources=["yfinance"],
        warnings=["sample warning"],
    )

    json_path = run_dir / "run_card.json"
    md_path = run_dir / "run_card.md"
    loaded = json.loads(json_path.read_text(encoding="utf-8"))
    markdown = md_path.read_text(encoding="utf-8")

    assert loaded == card
    assert loaded["schema_version"] == "0.1"
    assert loaded["generated_at"].endswith("Z")
    assert loaded["metrics"] == {"max_drawdown": -0.08, "sharpe": 1.23}
    assert loaded["validation"] == {"consistency_rate": 0.8, "n_windows": 5}
    assert "secret" not in json.dumps(loaded)
    assert "# Backtest Run Card" in markdown
    assert "Validation" in markdown
    assert "sample warning" in markdown


def test_api_run_response_includes_run_card(tmp_path: Path) -> None:
    import api_server

    run_dir = tmp_path / "run_001"
    run_dir.mkdir()
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir()
    (run_dir / "state.json").write_text('{"status": "success"}\n', encoding="utf-8")
    run_card = {
        "schema_version": "0.1",
        "generated_at": "2026-05-15T00:00:00Z",
        "run_dir": str(run_dir),
        "backtest": {"codes": ["AAPL"], "source": "yfinance"},
        "reproducibility": {"config_hash": "abc123", "strategy_hash": "def456"},
        "data_sources": ["yfinance"],
        "metrics": {"sharpe": 1.2},
        "warnings": ["sample warning"],
        "artifacts": [{"path": "artifacts/metrics.csv", "size_bytes": 42, "sha256": "feed"}],
    }
    (run_dir / "run_card.json").write_text(json.dumps(run_card), encoding="utf-8")
    llm_usage = {
        "schema_version": "0.1",
        "provider": "openai",
        "model": "gpt-test",
        "input_tokens": 100,
        "output_tokens": 25,
        "total_tokens": 125,
        "calls": 1,
        "iterations": [{"iter": 1, "input_tokens": 100, "output_tokens": 25, "total_tokens": 125}],
    }
    (artifacts_dir / "llm_usage.json").write_text(json.dumps(llm_usage), encoding="utf-8")

    response = api_server._build_response_from_run_dir(run_dir, elapsed=0.0)

    assert response.run_card == run_card
    assert response.llm_usage == llm_usage


def test_api_list_runs_can_include_compact_llm_usage(tmp_path: Path, monkeypatch) -> None:
    import api_server
    from fastapi.testclient import TestClient

    runs_dir = tmp_path / "runs"
    run_dir = runs_dir / "20260612_164752_53_c52ef4"
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text('{"status": "success"}\n', encoding="utf-8")
    usage = {
        "schema_version": "0.1",
        "provider": "minimax",
        "model": "MiniMax-M3",
        "input_tokens": 100,
        "output_tokens": 20,
        "total_tokens": 120,
        "calls": 2,
    }
    (artifacts_dir / "llm_usage.json").write_text(json.dumps(usage), encoding="utf-8")
    monkeypatch.setattr(api_server, "RUNS_DIR", runs_dir)
    monkeypatch.delenv("API_AUTH_KEY", raising=False)
    monkeypatch.setattr(api_server, "_API_KEY", "")

    client = TestClient(api_server.app, client=("127.0.0.1", 50000))
    response = client.get("/runs?limit=100&with_usage=true")

    assert response.status_code == 200
    rows = response.json()
    assert rows[0]["run_id"] == "20260612_164752_53_c52ef4"
    assert rows[0]["llm_usage"]["provider"] == "minimax"
    assert rows[0]["llm_usage"]["total_tokens"] == 120


def test_api_run_response_filters_chart_payload_by_symbol(tmp_path: Path) -> None:
    import api_server

    run_dir = tmp_path / "run_chart_filter"
    artifacts_dir = run_dir / "artifacts"
    artifacts_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text('{"status": "success"}\n', encoding="utf-8")
    (artifacts_dir / "price_series.csv").write_text(
        "timestamp,code,open,high,low,close,volume\n"
        "2026-01-01,AAA,1,2,1,2,100\n"
        "2026-01-02,AAA,2,3,2,3,120\n"
        "2026-01-01,BBB,4,5,4,5,200\n",
        encoding="utf-8",
    )
    (artifacts_dir / "trades.csv").write_text(
        "timestamp,code,side,price,qty,reason\n"
        "2026-01-02,AAA,BUY,3,10,test\n"
        "2026-01-02,BBB,SELL,5,10,test\n",
        encoding="utf-8",
    )

    default_response = api_server._build_response_from_run_dir(
        run_dir,
        elapsed=0.0,
        include_analysis=True,
    )
    summary_response = api_server._build_response_from_run_dir(
        run_dir,
        elapsed=0.0,
        include_analysis=True,
        chart_payload="summary",
    )
    response = api_server._build_response_from_run_dir(
        run_dir,
        elapsed=0.0,
        include_analysis=True,
        chart_symbol="AAA",
    )

    assert default_response.chart_symbols == ["AAA", "BBB"]
    assert set(default_response.price_series or {}) == {"AAA", "BBB"}
    assert {marker["code"] for marker in default_response.trade_markers or []} == {"AAA", "BBB"}
    assert default_response.artifacts_trades_csv is not None
    assert summary_response.chart_symbols == ["AAA", "BBB"]
    assert summary_response.price_series == {}
    assert summary_response.trade_markers == []
    assert summary_response.artifacts_trades_csv is None
    assert response.chart_symbols == ["AAA", "BBB"]
    assert set(response.price_series or {}) == {"AAA"}
    assert response.artifacts_trades_csv is None
    assert response.trade_markers == [
        {
            "time": "2026-01-02",
            "timestamp": "2026-01-02",
            "code": "AAA",
            "side": "BUY",
            "price": 3.0,
            "qty": 10.0,
            "reason": "test",
            "text": "BUY AAA",
        }
    ]
    assert response.artifacts_trades_csv is None
    assert response.artifacts_equity_csv is None


def test_api_run_response_surfaces_moirix_artifact_previews(tmp_path: Path) -> None:
    import api_server

    run_dir = tmp_path / "run_moirix"
    moirix_dir = run_dir / "artifacts" / "moirix"
    moirix_dir.mkdir(parents=True)
    authority_check_dir = moirix_dir / "authority_checks" / "proposal-abc12345"
    authority_check_dir.mkdir(parents=True)
    (run_dir / "state.json").write_text('{"status": "success"}\n', encoding="utf-8")
    (moirix_dir / "status.json").write_text('{"status":"ok"}\n', encoding="utf-8")
    (moirix_dir / "coverage_status.json").write_text('{"coverage":{"row_count":1}}\n', encoding="utf-8")
    (moirix_dir / "authority_status.json").write_text(
        '{"authority":{"ready_for_real_money_trading_authority":false}}\n',
        encoding="utf-8",
    )
    (moirix_dir / "moirix_summary.md").write_text("# Moirix\n\nStatus: `ok`\n", encoding="utf-8")
    (moirix_dir / "event_signal.csv").write_text(
        "known_at,symbol,event_type,pit_valid\n2025-01-02,NVDA,fixture,true\n",
        encoding="utf-8",
    )
    (authority_check_dir / "status.json").write_text('{"status":"blocked"}\n', encoding="utf-8")
    (authority_check_dir / "request.json").write_text('{"proposal_scope":"live_trading"}\n', encoding="utf-8")
    (authority_check_dir / "moirix_authority_status.json").write_text(
        '{"claim_gate":{"blockers":["broker_write_requested"]}}\n',
        encoding="utf-8",
    )

    response = api_server._build_response_from_run_dir(run_dir, elapsed=0.0)

    artifact_names = {artifact.name for artifact in response.artifacts}
    assert "moirix/status.json" in artifact_names
    assert "moirix/event_signal.csv" in artifact_names
    assert "moirix/authority_checks/proposal-abc12345/status.json" in artifact_names
    assert response.moirix_artifacts is not None
    assert response.moirix_artifacts["status"]["status"] == "ok"
    assert response.moirix_artifacts["event_signal_preview"][0]["symbol"] == "NVDA"
    assert response.moirix_artifacts["moirix_summary_markdown"].startswith("# Moirix")
    assert response.moirix_artifacts["authority_checks"][0]["id"] == "proposal-abc12345"
    assert response.moirix_artifacts["authority_checks"][0]["status"]["status"] == "blocked"


def test_runner_artifact_spec_surfaces_run_card_paths() -> None:
    runner = Runner()

    assert runner.artifact_entries["run_card_json"]["path"] == "run_card.json"
    assert runner.artifact_entries["run_card_json"]["required"] is False
    assert runner.artifact_entries["run_card_md"]["path"] == "run_card.md"
    assert runner.artifact_entries["run_card_md"]["required"] is False


def test_options_backtest_writes_run_card(tmp_path: Path) -> None:
    from backtest.engines.options_portfolio import run_options_backtest

    dates = pd.bdate_range("2025-01-01", periods=4)
    bars = pd.DataFrame(
        {
            "open": [100.0, 101.0, 102.0, 103.0],
            "high": [101.0, 102.0, 103.0, 104.0],
            "low": [99.0, 100.0, 101.0, 102.0],
            "close": [100.5, 101.5, 102.5, 103.5],
            "volume": [1000, 1100, 1200, 1300],
        },
        index=dates,
    )

    class FakeLoader:
        name = "yfinance"

        def fetch(self, codes, start_date, end_date):
            return {"SPY": bars.copy()}

    class SignalEngine:
        def generate(self, data_map):
            return [
                {
                    "date": "2025-01-01",
                    "action": "open",
                    "underlying": "SPY",
                    "legs": [{"type": "call", "strike": 101.0, "expiry": "2025-03-21", "qty": 1}],
                },
                {
                    "date": "2025-01-03",
                    "action": "close",
                    "underlying": "SPY",
                    "legs": [{"type": "call", "strike": 101.0, "expiry": "2025-03-21", "qty": 1}],
                },
            ]

    run_options_backtest(
        {
            "codes": ["SPY"],
            "start_date": "2025-01-01",
            "end_date": "2025-01-06",
            "source": "yfinance",
            "engine": "options",
            "initial_cash": 100_000,
        },
        FakeLoader(),
        SignalEngine(),
        tmp_path,
    )

    card = json.loads((tmp_path / "run_card.json").read_text(encoding="utf-8"))
    assert card["backtest"]["engine"] == "options"
    assert card["data_sources"] == ["yfinance"]
    assert "greeks.csv" in {Path(artifact["path"]).name for artifact in card["artifacts"]}
    assert (tmp_path / "run_card.md").exists()
