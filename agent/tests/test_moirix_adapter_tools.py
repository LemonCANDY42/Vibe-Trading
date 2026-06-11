"""Regression tests for the optional Moirix adapter tools."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

import src.tools as tools_pkg
import src.tools._moirix_adapter as moirix_adapter
from src.tools import build_registry
from src.tools.moirix_event_graph_tool import MoirixEventGraphTool
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
    (out / "moirix_authority_status.json").write_text(json.dumps(AUTHORITY), encoding="utf-8")
    (out / "moirix_summary.md").write_text(f"status={status}\n", encoding="utf-8")
    (out / "vibe_run_card_patch.json").write_text(json.dumps({"status": status}), encoding="utf-8")

command = sys.argv[1]
if command == "status":
    print(json.dumps({
        "schema_version": "moirix.vibe_adapter.status.v1",
        "status": "ok",
        "adapter_version": "0.1.0",
        "supported_commands": ["status", "query-news", "build-event-graph"],
        "supported_scopes": ["research_only", "paper_proposal_only"],
        "authority": AUTHORITY,
        "claim_gate": {"blockers": []},
    }))
elif command == "query-news":
    out = Path(arg("--out")).resolve()
    write_common(out, "blocked")
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
        "artifacts": {
            "moirix_authority_status": str(out / "moirix_authority_status.json"),
            "moirix_summary": str(out / "moirix_summary.md"),
            "vibe_run_card_patch": str(out / "vibe_run_card_patch.json"),
        },
    }))
elif command == "build-event-graph":
    input_path = Path(arg("--input")).resolve()
    out = Path(arg("--out")).resolve()
    write_common(out, "ok")
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
    print(json.dumps({
        **graph,
        "artifacts": {
            "event_impact_graph": str(graph_path),
            "news_evidence": str(input_path),
            "moirix_authority_status": str(out / "moirix_authority_status.json"),
            "moirix_summary": str(out / "moirix_summary.md"),
            "vibe_run_card_patch": str(out / "vibe_run_card_patch.json"),
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
    tools = [MoirixStatusTool(), MoirixNewsTool(), MoirixEventGraphTool()]

    for tool in tools:
        properties = tool.parameters.get("properties", {})
        assert "broker_submit" not in properties
        assert "order" not in properties
        assert "live_trading" not in properties
