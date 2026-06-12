"""Regression tests for the optional Moirix adapter tools."""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import pytest

import src.tools as tools_pkg
import src.tools._moirix_adapter as moirix_adapter
from src.tools import build_registry
from src.tools.moirix_authority_guard_tool import MoirixAuthorityGuardTool
from src.tools.moirix_event_graph_tool import MoirixEventGraphTool
from src.tools.moirix_event_signal_backtest_tool import MoirixEventSignalBacktestTool
from src.tools.moirix_event_signal_tool import MoirixEventSignalTool
from src.tools.moirix_news_tool import MoirixNewsTool
from src.tools.moirix_status_tool import MoirixStatusTool


FALSE_AUTHORITY = {
    "live_broker_execution_enabled": False,
    "real_order_authority": False,
    "trading_authority_claim": False,
    "ready_for_real_money_trading_authority": False,
    "broker_submit_supported": False,
    "supported_scopes": ["research_only", "paper_proposal_only"],
}

STANDARD_MOIRIX_ARTIFACT_KEYS = {
    "status",
    "request",
    "coverage_status",
    "authority_status",
    "moirix_authority_status",
    "moirix_summary",
    "vibe_run_card_patch",
}


FAKE_ADAPTER = r'''
import json
import os
import sys
from pathlib import Path

AUTHORITY = {
    "live_broker_execution_enabled": False,
    "real_order_authority": False,
    "trading_authority_claim": False,
    "ready_for_real_money_trading_authority": False,
    "broker_submit_supported": False,
    "supported_scopes": ["research_only", "paper_proposal_only"],
}

def arg(name):
    return sys.argv[sys.argv.index(name) + 1]

def write_common(out, status):
    out.mkdir(parents=True, exist_ok=True)
    status_payload = {"status": status, "authority": AUTHORITY}
    (out / "status.json").write_text(json.dumps(status_payload), encoding="utf-8")
    (out / "request.json").write_text(json.dumps({"command": command}), encoding="utf-8")
    (out / "coverage_status.json").write_text(
        json.dumps({"status": status, "coverage": {"blocked_without_fake_evidence": status != "ok"}}),
        encoding="utf-8",
    )
    (out / "authority_status.json").write_text(json.dumps(AUTHORITY), encoding="utf-8")
    (out / "moirix_authority_status.json").write_text(json.dumps(AUTHORITY), encoding="utf-8")
    (out / "moirix_summary.md").write_text(f"status={status}\n", encoding="utf-8")
    (out / "vibe_run_card_patch.json").write_text(json.dumps({"status": status}), encoding="utf-8")
    return {
        "status": str(out / "status.json"),
        "request": str(out / "request.json"),
        "coverage_status": str(out / "coverage_status.json"),
        "authority_status": str(out / "authority_status.json"),
        "moirix_authority_status": str(out / "moirix_authority_status.json"),
        "moirix_summary": str(out / "moirix_summary.md"),
        "vibe_run_card_patch": str(out / "vibe_run_card_patch.json"),
    }

command = sys.argv[1]
if command == "status":
    print(json.dumps({
        "schema_version": "moirix.vibe_adapter.status.v1",
        "status": "ok",
        "adapter_version": "0.1.0",
        "supported_commands": ["status", "query-news", "build-event-graph", "export-vibe-artifacts", "authority-check"],
        "supported_scopes": ["research_only", "paper_proposal_only"],
        "authority": AUTHORITY,
        "claim_gate": {"blockers": []},
    }))
elif command == "query-news":
    out = Path(arg("--out")).resolve()
    common = write_common(out, "blocked")
    print(json.dumps({
        "schema_version": "moirix.vibe_adapter.pit_news_query.v1",
        "status": "blocked",
        "target": arg("--target"),
        "market": arg("--market"),
        "as_of": arg("--as-of"),
        "returned_count": 0,
        "rows": [],
        "authority": AUTHORITY,
        "claim_gate": {"blockers": ["fixture_source_lake_blocked"]},
        "evidence_coverage": {"blocked_without_fake_evidence": True},
        "artifacts": common,
    }))
elif command == "build-event-graph":
    input_path = Path(arg("--input")).resolve()
    out = Path(arg("--out")).resolve()
    common = write_common(out, "ok")
    graph_path = out / "event_impact_graph.json"
    graph = {
        "schema_version": "moirix.vibe_adapter.event_impact_graph.v1",
        "status": "ok",
        "target": arg("--target"),
        "as_of": arg("--as-of"),
        "nodes": [{"id": "event:fixture", "kind": "event", "label": "Fixture event"}],
        "edges": [],
        "impacted_instruments": [],
        "authority": AUTHORITY,
        "evidence_coverage": {"input_path": str(input_path), "input_row_count": 1},
    }
    graph_path.write_text(json.dumps(graph), encoding="utf-8")
    (out / "event_signal.csv").write_text(
        "known_at,symbol,event_type,sentiment_score,impact_score,confidence,source_count,decay_half_life_days,source_tier,pit_valid\n"
        "2025-04-30T21:30:00Z,NVDA,fixture,0.7,0.48,0.8,1,5,pit_source_lake,true\n",
        encoding="utf-8",
    )
    print(json.dumps({
        **graph,
        "artifacts": {
            "event_impact_graph": str(graph_path),
            "event_signal": str(out / "event_signal.csv"),
            "news_evidence": str(input_path),
            **common,
        },
    }))
elif command == "artifact-escape":
    out = Path(arg("--out")).resolve()
    print(json.dumps({
        "schema_version": "moirix.vibe_adapter.event_impact_graph.v1",
        "status": "ok",
        "authority": AUTHORITY,
        "claim_gate": {"blockers": []},
        "artifacts": {"event_impact_graph": str(out.parent / "escape.json")},
    }))
elif command == "unknown-status":
    print(json.dumps({
        "schema_version": "moirix.vibe_adapter.status.v1",
        "status": "surprise",
        "authority": AUTHORITY,
        "claim_gate": None,
    }))
elif command == "top-level-authority-violation":
    print(json.dumps({
        "schema_version": "moirix.vibe_adapter.status.v1",
        "status": "ok",
        "ready_for_real_money_trading_authority": True,
        "authority": AUTHORITY,
        "claim_gate": {"blockers": []},
    }))
elif command == "export-vibe-artifacts":
    run_root = Path(arg("--run-root")).resolve()
    out = Path(arg("--out")).resolve()
    out.mkdir(parents=True, exist_ok=True)
    copied = []
    artifacts = {}
    signal = run_root / "event_signal.csv"
    if signal.is_file():
        target = out / "event_signal.csv"
        if signal.resolve() != target.resolve():
            shutil.copy2(signal, target)
        copied.append("event_signal.csv")
        artifacts["event_signal"] = str(target)
    common = write_common(out, "ok" if copied else "blocked")
    artifacts.update(common)
    print(json.dumps({
        "schema_version": "moirix.vibe_adapter.vibe_artifact_export.v1",
        "status": "ok" if copied else "blocked",
        "authority": AUTHORITY,
        "claim_gate": {"blockers": [] if copied else ["run_root_has_no_known_moirix_adapter_artifacts"]},
        "copied_artifacts": copied,
        "artifacts": artifacts,
    }))
elif command == "authority-check":
    out = Path(arg("--out")).resolve()
    common = write_common(out, "blocked")
    print(json.dumps({
        "schema_version": "moirix.vibe_adapter.authority_guard.v1",
        "status": "blocked",
        "authority": AUTHORITY,
        "claim_gate": {"blockers": ["broker_write_requested", "submit_order_requested"]},
        "artifacts": common,
    }))
else:
    print(json.dumps({"status": "unavailable", "authority": AUTHORITY, "claim_gate": {"blockers": ["unknown_command"]}}))
'''


def _fake_adapter(tmp_path: Path) -> Path:
    path = tmp_path / "fake_moirix_adapter.py"
    path.write_text(FAKE_ADAPTER, encoding="utf-8")
    return path


def _run_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    run_dir = tmp_path / "run"
    (run_dir / "artifacts").mkdir(parents=True)
    monkeypatch.setenv("VIBE_TRADING_ALLOWED_RUN_ROOTS", str(run_dir))
    return run_dir


def _use_fake_adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = _fake_adapter(tmp_path)
    monkeypatch.setenv("MOIRIX_ADAPTER_CMD", f"{sys.executable} {script}")
    monkeypatch.setenv("MOIRIX_ADAPTER_CWD", str(tmp_path))


def test_moirix_tools_are_discoverable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tools_pkg, "_SUBCLASSES_CACHE", None)

    registry = build_registry()

    assert "moirix_status" in registry.tool_names
    assert "moirix_query_news" in registry.tool_names
    assert "moirix_build_event_graph" in registry.tool_names
    assert "moirix_export_event_signal" in registry.tool_names
    assert "moirix_event_signal_backtest" in registry.tool_names
    assert "moirix_authority_guard" in registry.tool_names


def test_missing_moirix_adapter_returns_unavailable(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("MOIRIX_ADAPTER_CMD", raising=False)
    monkeypatch.setenv("MOIRIX_REPO_DIR", str(tmp_path / "missing-moirix"))
    monkeypatch.setattr(moirix_adapter.importlib.util, "find_spec", lambda name: None)
    monkeypatch.setattr(moirix_adapter.shutil, "which", lambda name: None)

    payload = json.loads(MoirixStatusTool().execute())

    assert payload["status"] == "unavailable"
    assert "moirix_adapter_unavailable" in payload["claim_gate"]["blockers"]


def test_query_news_preserves_blocked_and_writes_no_fake_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_fake_adapter(tmp_path, monkeypatch)
    run_dir = _run_dir(tmp_path, monkeypatch)

    payload = json.loads(
        MoirixNewsTool().execute(
            target="NVDA",
            market="US",
            as_of="2025-05-01",
            lookback_days=30,
            run_dir=str(run_dir),
        )
    )

    assert payload["status"] == "blocked"
    for field, expected in FALSE_AUTHORITY.items():
        assert payload["authority"][field] == expected
    assert "fixture_source_lake_blocked" in payload["claim_gate"]["blockers"]
    assert not (run_dir / "artifacts" / "moirix" / "news_evidence.jsonl").exists()
    assert (run_dir / "artifacts" / "moirix" / "vibe_run_card_patch.json").exists()
    assert STANDARD_MOIRIX_ARTIFACT_KEYS <= set(payload["artifacts"])


def test_build_event_graph_uses_run_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_fake_adapter(tmp_path, monkeypatch)
    run_dir = _run_dir(tmp_path, monkeypatch)
    evidence = run_dir / "artifacts" / "moirix" / "news_evidence.jsonl"
    evidence.parent.mkdir(parents=True, exist_ok=True)
    evidence.write_text('{"event_id":"event:fixture","visible_at":"2025-04-30T00:00:00Z"}\n', encoding="utf-8")

    payload = json.loads(
        MoirixEventGraphTool().execute(
            target="NVDA",
            as_of="2025-05-01",
            run_dir=str(run_dir),
        )
    )

    graph_path = run_dir / "artifacts" / "moirix" / "event_impact_graph.json"
    assert payload["status"] == "ok"
    assert payload["artifacts"]["event_impact_graph"] == str(graph_path)
    assert graph_path.exists()
    assert (run_dir / "artifacts" / "moirix" / "event_signal.csv").exists()
    assert STANDARD_MOIRIX_ARTIFACT_KEYS <= set(payload["artifacts"])
    for name in ("status.json", "request.json", "coverage_status.json", "authority_status.json"):
        assert (run_dir / "artifacts" / "moirix" / name).exists()


def test_export_event_signal_requires_existing_signal_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_fake_adapter(tmp_path, monkeypatch)
    run_dir = _run_dir(tmp_path, monkeypatch)

    payload = json.loads(MoirixEventSignalTool().execute(run_dir=str(run_dir)))

    assert payload["status"] == "blocked"
    assert "moirix_event_signal_missing" in payload["claim_gate"]["blockers"]


def test_export_event_signal_uses_run_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_fake_adapter(tmp_path, monkeypatch)
    run_dir = _run_dir(tmp_path, monkeypatch)
    signal = run_dir / "artifacts" / "moirix" / "event_signal.csv"
    signal.parent.mkdir(parents=True, exist_ok=True)
    signal.write_text(
        "known_at,symbol,event_type,sentiment_score,impact_score,confidence,source_count,decay_half_life_days,source_tier,pit_valid\n",
        encoding="utf-8",
    )

    payload = json.loads(MoirixEventSignalTool().execute(run_dir=str(run_dir)))

    assert payload["status"] == "ok"
    assert "event_signal.csv" in payload["copied_artifacts"]
    assert payload["artifacts"]["event_signal"] == str(signal)
    assert STANDARD_MOIRIX_ARTIFACT_KEYS <= set(payload["artifacts"])


def test_authority_guard_preserves_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_fake_adapter(tmp_path, monkeypatch)
    run_dir = _run_dir(tmp_path, monkeypatch)
    proposal = run_dir / "artifacts" / "moirix" / "proposal.json"
    proposal.parent.mkdir(parents=True, exist_ok=True)
    proposal.write_text('{"scope":"live_trading","broker_write":true}\n', encoding="utf-8")

    payload = json.loads(
        MoirixAuthorityGuardTool().execute(
            proposal_path=str(proposal),
            run_dir=str(run_dir),
        )
    )

    assert payload["status"] == "blocked"
    assert "broker_write_requested" in payload["claim_gate"]["blockers"]
    assert STANDARD_MOIRIX_ARTIFACT_KEYS <= set(payload["artifacts"])


def test_event_signal_backtest_consumes_signal_and_price_csv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run_dir(tmp_path, monkeypatch)
    out = run_dir / "artifacts" / "moirix"
    out.mkdir(parents=True, exist_ok=True)
    (out / "event_signal.csv").write_text(
        "\n".join(
            [
                "known_at,symbol,event_type,sentiment_score,impact_score,confidence,source_count,decay_half_life_days,source_tier,pit_valid",
                "2025-01-02,NVDA,fixture,0.7,0.5,0.8,1,5,pit_source_lake,true",
                "2025-01-03,SMH,fixture,-0.2,-0.3,0.6,1,5,pit_source_lake,true",
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    (out / "price_series.csv").write_text(
        "\n".join(
            [
                "date,symbol,close",
                "2025-01-02,NVDA,100",
                "2025-01-03,NVDA,110",
                "2025-01-06,NVDA,121",
                "2025-01-07,NVDA,115",
                "2025-01-08,NVDA,130",
                "2025-01-09,NVDA,140",
                "2025-01-03,SMH,200",
                "2025-01-06,SMH,190",
                "2025-01-07,SMH,180",
                "2025-01-08,SMH,175",
                "2025-01-09,SMH,170",
                "2025-01-10,SMH,160",
            ]
        )
        + "\n",
        encoding="utf-8",
    )

    payload = json.loads(
        MoirixEventSignalBacktestTool().execute(
            run_dir=str(run_dir),
            horizons=[1, 3, 5],
        )
    )

    assert payload["status"] == "ok"
    assert payload["claim_gate"]["ready_for_real_money_trading_authority"] is False
    assert payload["summary"]["horizon_stats"]["1"]["count"] == 2
    assert (out / "event_signal_forward_returns.csv").exists()
    assert (out / "event_signal_backtest_summary.json").exists()


def test_event_signal_backtest_blocks_without_price_csv(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run_dir(tmp_path, monkeypatch)
    out = run_dir / "artifacts" / "moirix"
    out.mkdir(parents=True, exist_ok=True)
    (out / "event_signal.csv").write_text(
        "known_at,symbol,event_type,sentiment_score,impact_score,confidence,source_count,decay_half_life_days,source_tier,pit_valid\n"
        "2025-01-02,NVDA,fixture,0.7,0.5,0.8,1,5,pit_source_lake,true\n",
        encoding="utf-8",
    )

    payload = json.loads(MoirixEventSignalBacktestTool().execute(run_dir=str(run_dir)))

    assert payload["status"] == "blocked"
    assert "moirix_event_signal_price_csv_missing" in payload["claim_gate"]["blockers"]
    assert not (out / "event_signal_forward_returns.csv").exists()
    assert (out / "event_signal_backtest_summary.json").exists()


def test_event_graph_rejects_input_outside_allowed_roots(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_fake_adapter(tmp_path, monkeypatch)
    run_dir = _run_dir(tmp_path, monkeypatch)
    outside = tmp_path / "outside.jsonl"
    outside.write_text("{}\n", encoding="utf-8")

    payload = json.loads(
        MoirixEventGraphTool().execute(
            target="NVDA",
            as_of="2025-05-01",
            input_path=str(outside),
            run_dir=str(run_dir),
        )
    )

    assert payload["status"] == "error"
    assert "moirix_event_graph_input_rejected" in payload["claim_gate"]["blockers"]
    assert not (run_dir / "artifacts" / "moirix" / "event_impact_graph.json").exists()


def test_adapter_artifact_paths_must_stay_under_output_dir(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_fake_adapter(tmp_path, monkeypatch)
    run_dir = _run_dir(tmp_path, monkeypatch)
    out_dir = run_dir / "artifacts" / "moirix"

    payload = moirix_adapter.call_adapter(
        ["artifact-escape", "--out", str(out_dir)],
        out_dir=out_dir,
    )

    assert payload["status"] == "blocked"
    assert "moirix_artifact_contract_violation" in payload["claim_gate"]["blockers"]
    assert "event_impact_graph:outside_artifacts_root" in payload["violations"]


def test_unknown_adapter_status_is_blocked_with_claim_gate_dict(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_fake_adapter(tmp_path, monkeypatch)

    payload = moirix_adapter.call_adapter(["unknown-status"])

    assert payload["status"] == "blocked"
    assert payload["claim_gate"]["blockers"] == ["moirix_adapter_unknown_status"]


def test_top_level_authority_violation_is_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_fake_adapter(tmp_path, monkeypatch)

    payload = moirix_adapter.call_adapter(["top-level-authority-violation"])

    assert payload["status"] == "blocked"
    assert "moirix_authority_contract_violation" in payload["claim_gate"]["blockers"]
    assert "ready_for_real_money_trading_authority" in payload["violations"]


def test_moirix_tools_do_not_expose_broker_submit_parameters() -> None:
    tools = [
        MoirixStatusTool(),
        MoirixNewsTool(),
        MoirixEventGraphTool(),
        MoirixEventSignalTool(),
        MoirixEventSignalBacktestTool(),
        MoirixAuthorityGuardTool(),
    ]

    for tool in tools:
        properties = tool.parameters.get("properties", {})
        assert "broker_submit" not in properties
        assert "order" not in properties
        assert "live_trading" not in properties
        assert "submit" not in properties
