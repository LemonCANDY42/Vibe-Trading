"""Regression tests for the optional Moirix adapter tools."""

from __future__ import annotations

import json
import sys
import hashlib
import subprocess
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

import src.tools as tools_pkg
import src.tools._moirix_adapter as moirix_adapter
from src.tools import build_registry
from src.tools.moirix_authority_guard_tool import MoirixAuthorityGuardTool
from src.tools.moirix_decision_projection_tool import MoirixDecisionProjectionTool
from src.tools.moirix_event_thesis_tool import MoirixEventThesisTool
from src.tools.moirix_news_tool import MoirixNewsTool
from src.tools.moirix_portfolio_context_tool import MoirixPortfolioContextTool
from src.tools.moirix_position_decision_tool import MoirixPositionDecisionTool
from src.tools.moirix_status_tool import MoirixStatusTool
from src.tools.moirix_trade_execution_tool import MoirixTradeExecutionTool
from src.trading.paper_gate import APPROVAL_SCHEMA_VERSION, build_paper_request, canonical_request_hash


FALSE_AUTHORITY = {
    "live_broker_execution_enabled": False,
    "real_order_authority": False,
    "trading_authority_claim": False,
    "ready_for_real_money_trading_authority": False,
    "broker_submit_supported": False,
    "supported_scopes": ["research_only", "paper_proposal_only"],
}

STANDARD_MOIRIX_ARTIFACT_KEYS = {
    "adapter_call_status",
    "status",
    "request",
    "coverage_status",
    "authority_status",
    "moirix_authority_status",
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
    (out / "vibe_run_card_patch.json").write_text(json.dumps({"status": status}), encoding="utf-8")
    return {
        "status": str(out / "status.json"),
        "request": str(out / "request.json"),
        "coverage_status": str(out / "coverage_status.json"),
        "authority_status": str(out / "authority_status.json"),
        "moirix_authority_status": str(out / "moirix_authority_status.json"),
        "vibe_run_card_patch": str(out / "vibe_run_card_patch.json"),
    }

command = sys.argv[1]
if command == "status":
    print(json.dumps({
        "schema_version": "moirix.vibe_adapter.status.v1",
        "status": "ok",
        "adapter_version": "0.1.0",
        "supported_commands": ["status", "query-news", "authority-check"],
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
elif command == "artifact-escape":
    out = Path(arg("--out")).resolve()
    print(json.dumps({
        "schema_version": "moirix.vibe_adapter.status.v1",
        "status": "ok",
        "authority": AUTHORITY,
        "claim_gate": {"blockers": []},
        "artifacts": {"event_thesis_graph": str(out.parent / "escape.json")},
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
elif command == "sleep":
    out = Path(arg("--out")).resolve()
    write_common(out, "ok")
    import time
    time.sleep(2)
    print(json.dumps({"status": "ok", "authority": AUTHORITY, "claim_gate": {"blockers": []}}))
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
    monkeypatch.setenv("VIBE_TRADING_ALLOWED_FILE_ROOTS", str(run_dir))
    return run_dir


def _use_fake_adapter(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    script = _fake_adapter(tmp_path)
    monkeypatch.setenv("MOIRIX_ADAPTER_CMD", f"{sys.executable} {script}")
    monkeypatch.setenv("MOIRIX_ADAPTER_CWD", str(tmp_path))


def _valid_thesis() -> dict[str, object]:
    return {
        "schema_version": "vibe.moirix_event_thesis.v1",
        "target": "NVDA",
        "market": "US",
        "as_of": "2025-05-01",
        "evidence_items": [
            {
                "event_id": "event:fixture",
                "summary": "Fixture event affected AI accelerator demand expectations.",
                "truth_status": "likely",
                "source_quality": "medium",
                "target_relevance": "direct",
                "impact_path": "revenue",
                "impact_direction": "positive",
                "impact_horizon": "weeks",
                "invalidated_by": ["company filing contradicts demand claim"],
                "analysis": "The event supports a short-term demand thesis but still needs filing confirmation.",
            }
        ],
        "relations": [
            {
                "source_event_id": "event:fixture",
                "target_event_id": "event:fixture",
                "relation_type": "confirms",
                "explanation": "Single fixture event anchors the initial thesis.",
            }
        ],
        "current_thesis": {
            "stance": "bullish",
            "actionability": "watch",
            "summary": "Evidence supports a watch-only bullish thesis.",
            "execution_window": {
                "start": "2025-05-01",
                "end": "2025-05-20",
                "reason": "Potential repricing window before next company update.",
            },
            "supporting_events": ["event:fixture"],
            "contradicting_events": [],
            "open_questions": ["Is the demand signal already priced?"],
            "invalidation_triggers": ["newer verified report contradicts demand"],
        },
        "authority": {
            "research_only": True,
            "paper_trade_proposal_allowed": False,
            "broker_submit_allowed": False,
            "ready_for_real_money_trading_authority": False,
        },
    }


def _valid_decision() -> dict[str, object]:
    return {
        "schema_version": "vibe.moirix_position_decision.v1",
        "target": "NVDA",
        "market": "US",
        "as_of": "2025-05-01",
        "action": "add",
        "rationale": "Thesis remains watch-only bullish, but a small paper add would test execution discipline.",
        "execution_window": {
            "start": "2025-05-02",
            "end": "2025-05-10",
            "reason": "Use the next liquidity window after evidence visibility.",
        },
        "risk_sizing": {
            "max_position_notional": 2500,
            "max_loss_notional": 250,
            "portfolio_impact": "small incremental exposure",
        },
        "risk_notes": ["paper-only sizing", "stop if thesis is contradicted"],
        "invalidation_triggers": ["new verified report supersedes demand signal"],
        "proposed_orders": [
            {
                "symbol": "NVDA",
                "side": "buy",
                "order_type": "limit",
                "quantity": 1,
                "limit_price": 100,
                "time_in_force": "day",
            }
        ],
        "authority": {
            "research_only": True,
            "paper_trade_proposal_allowed": False,
            "broker_submit_allowed": False,
            "ready_for_real_money_trading_authority": False,
        },
    }


def _write_thesis_and_context(run_dir: Path) -> None:
    out = run_dir / "artifacts" / "moirix"
    out.mkdir(parents=True, exist_ok=True)
    thesis = _valid_thesis()
    thesis["status"] = "ok"
    thesis["claim_gate"] = {"blockers": []}
    (out / "event_thesis_graph.json").write_text(json.dumps(thesis), encoding="utf-8")
    (out / "event_decision_context.json").write_text(
        json.dumps(
            {
                "schema_version": "vibe.moirix_event_decision_context.v1",
                "status": "ok",
                "target": "NVDA",
                "market": "US",
                "as_of": "2025-05-01",
                "positions": [{"symbol": "NVDA", "position": 10, "avg_cost": 90.0}],
                "account_summary": {"AvailableFunds_USD": "100000.00"},
                "claim_gate": {"blockers": []},
                "authority": {
                    "research_only": True,
                    "broker_submit_allowed": False,
                    "ready_for_real_money_trading_authority": False,
                },
            }
        ),
        encoding="utf-8",
    )


def _write_query_news_artifacts(
    run_dir: Path,
    *,
    target: str = "NVDA",
    market: str = "US",
    as_of: str = "2025-05-01",
    rows: list[dict[str, object]] | None = None,
) -> None:
    out = run_dir / "artifacts" / "moirix"
    out.mkdir(parents=True, exist_ok=True)
    rows = rows or [{"event_id": "event:fixture", "visible_at": "2025-04-30T00:00:00Z", "validation_state": "valid"}]
    (out / "news_evidence.jsonl").write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )
    (out / "request.json").write_text(
        json.dumps({"command": "query-news", "request": {"target": target, "market": market, "as_of": as_of}}),
        encoding="utf-8",
    )
    (out / "status.json").write_text(
        json.dumps({"status": "ok", "target": target, "market": market, "as_of": as_of}),
        encoding="utf-8",
    )
    (out / "coverage_status.json").write_text(
        json.dumps({"status": "ok", "coverage": {"row_count": len(rows), "blocked_without_fake_evidence": False}}),
        encoding="utf-8",
    )


def _write_execution_approval(
    path: Path,
    *,
    proposal_path: Path,
    connection: str,
    account: str = "",
    authority: dict[str, object] | None = None,
    max_notional: float = 10_000,
    estimated_prices: dict[str, float] | None = None,
) -> dict[str, object]:
    proposal = json.loads(proposal_path.read_text(encoding="utf-8"))
    proposal_hash = hashlib.sha256(proposal_path.read_bytes()).hexdigest()
    request = build_paper_request(
        operation="moirix_execute_trade_proposal",
        connection=connection,
        account=account,
        actions=proposal.get("orders", []),
        proposal_sha256=proposal_hash,
    )
    payload = {
        "schema_version": APPROVAL_SCHEMA_VERSION,
        "approval_id": "pytest-approval",
        "approved": True,
        "scope": "paper",
        "execution_mode": "paper",
        "connection": connection,
        "account": account,
        "request": request,
        "request_sha256": canonical_request_hash(request),
        "proposal_sha256": proposal_hash,
        "max_notional": max_notional,
        "estimated_prices": estimated_prices or {},
        "expires_at": (datetime.now(timezone.utc) + timedelta(minutes=30)).replace(microsecond=0).isoformat(),
        "authority": authority
        if authority is not None
        else {
            "paper_trade_proposal_allowed": True,
            "broker_submit_allowed": True,
            "ready_for_real_money_trading_authority": False,
        },
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    return payload


def test_moirix_tools_are_discoverable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(tools_pkg, "_SUBCLASSES_CACHE", None)

    registry = build_registry()

    assert "moirix_status" in registry.tool_names
    assert "moirix_query_news" in registry.tool_names
    assert "moirix_write_event_thesis" in registry.tool_names
    assert "moirix_portfolio_context" in registry.tool_names
    assert "moirix_write_position_decision" in registry.tool_names
    assert "moirix_export_decision_projection" in registry.tool_names
    assert "moirix_execute_trade_proposal" in registry.tool_names
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
    adapter_status = json.loads((run_dir / "artifacts" / "moirix" / "adapter_call_status.json").read_text())
    assert adapter_status["schema_version"] == "vibe.moirix_adapter_call_status.v1"
    assert adapter_status["phase"] == "completed"
    assert adapter_status["status"] == "blocked"
    assert adapter_status["fail_closed"] is True
    assert "fixture_source_lake_blocked" in adapter_status["blockers"]


def test_adapter_call_status_records_timeout_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_fake_adapter(tmp_path, monkeypatch)
    run_dir = _run_dir(tmp_path, monkeypatch)
    out_dir = run_dir / "artifacts" / "moirix"
    out_dir.mkdir(parents=True, exist_ok=True)

    started = time.monotonic()
    payload = moirix_adapter.call_adapter(["sleep", "--out", str(out_dir)], out_dir=out_dir, timeout_seconds=1)
    elapsed = time.monotonic() - started

    assert elapsed < 3
    assert payload["status"] == "unavailable"
    assert "moirix_adapter_timeout" in payload["claim_gate"]["blockers"]
    adapter_status = json.loads((out_dir / "adapter_call_status.json").read_text())
    assert adapter_status["status"] == "unavailable"
    assert adapter_status["phase"] == "completed"
    assert adapter_status["timeout_seconds"] == 1
    assert adapter_status["fail_closed"] is True
    assert "moirix_adapter_timeout" in adapter_status["blockers"]


def test_write_event_thesis_requires_pit_evidence(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run_dir(tmp_path, monkeypatch)

    payload = json.loads(
        MoirixEventThesisTool().execute(
            run_dir=str(run_dir),
            thesis_json=_valid_thesis(),
        )
    )

    assert payload["status"] == "blocked"
    assert "moirix_event_thesis_evidence_missing" in payload["claim_gate"]["blockers"]
    assert not (run_dir / "artifacts" / "moirix" / "event_thesis_graph.json").exists()


def test_write_event_thesis_persists_canonical_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run_dir(tmp_path, monkeypatch)
    _write_query_news_artifacts(run_dir)

    payload = json.loads(
        MoirixEventThesisTool().execute(
            run_dir=str(run_dir),
            thesis_json=_valid_thesis(),
        )
    )

    out = run_dir / "artifacts" / "moirix"
    thesis_path = out / "event_thesis_graph.json"
    report_path = out / "event_thesis_report.md"
    authority_path = out / "authority_status.json"
    assert payload["status"] == "ok"
    assert payload["artifacts"]["event_thesis_graph"] == str(thesis_path)
    assert thesis_path.exists()
    assert report_path.exists()
    assert authority_path.exists()
    thesis = json.loads(thesis_path.read_text(encoding="utf-8"))
    assert thesis["current_thesis"]["stance"] == "bullish"
    assert thesis["authority"]["broker_submit_allowed"] is False
    assert "strength" not in json.dumps(thesis)


def test_write_event_thesis_rejects_legacy_numeric_graph_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run_dir(tmp_path, monkeypatch)
    _write_query_news_artifacts(run_dir)
    thesis = _valid_thesis()
    assert isinstance(thesis["evidence_items"], list)
    thesis["evidence_items"][0]["confidence"] = 0.8  # type: ignore[index]

    payload = json.loads(
        MoirixEventThesisTool().execute(
            run_dir=str(run_dir),
            thesis_json=thesis,
        )
    )

    assert payload["status"] == "blocked"
    assert "moirix_event_thesis_schema_invalid" in payload["claim_gate"]["blockers"]
    assert any("confidence" in item for item in payload["violations"])
    assert not (run_dir / "artifacts" / "moirix" / "event_thesis_graph.json").exists()


def test_write_event_thesis_rejects_ungrounded_future_or_missing_events(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run_dir(tmp_path, monkeypatch)
    _write_query_news_artifacts(
        run_dir,
        rows=[{"event_id": "event:other", "visible_at": "2025-05-02T00:00:00Z", "validation_state": "valid"}],
    )

    payload = json.loads(MoirixEventThesisTool().execute(run_dir=str(run_dir), thesis_json=_valid_thesis()))

    assert payload["status"] == "blocked"
    assert "moirix_event_thesis_grounding_invalid" in payload["claim_gate"]["blockers"]
    assert any("not present" in item or "after thesis.as_of" in item for item in payload["violations"])


def test_portfolio_context_blocks_without_readonly_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run_dir(tmp_path, monkeypatch)

    payload = json.loads(
        MoirixPortfolioContextTool().execute(
            run_dir=str(run_dir),
            target="NVDA",
            market="US",
            as_of="2025-05-01",
        )
    )

    assert payload["status"] == "blocked"
    assert "moirix_ibkr_readiness_missing" in payload["claim_gate"]["blockers"]
    assert payload["positions"] == []
    assert (run_dir / "artifacts" / "moirix" / "event_decision_context.json").exists()


def test_portfolio_context_uses_ibkr_readiness_artifact(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run_dir(tmp_path, monkeypatch)
    readiness = run_dir / "artifacts" / "ibkr" / "ibkr_paper_readiness.json"
    readiness.parent.mkdir(parents=True, exist_ok=True)
    readiness.write_text(
        json.dumps(
            {
                "schema_version": "vibe.ibkr_paper_readiness.v1",
                "status": "blocked",
                "claim_gate": {"blockers": ["ibkr_paper_market_data_blocked"]},
                "checks": {
                    "account_summary": {
                        "payload": {
                            "summary": [
                                {"tag": "AvailableFunds", "currency": "USD", "value": "1000000.00"},
                                {"tag": "BuyingPower", "currency": "USD", "value": "4000000.00"},
                            ]
                        }
                    },
                    "positions": {
                        "payload": {
                            "positions": [
                                {"symbol": "NVDA", "position": 10, "avg_cost": 100.0},
                            ]
                        }
                    },
                    "open_orders_and_executions": {"payload": {"open_orders": [], "executions": []}},
                },
            }
        ),
        encoding="utf-8",
    )

    payload = json.loads(
        MoirixPortfolioContextTool().execute(
            run_dir=str(run_dir),
            target="NVDA",
            market="US",
            as_of="2025-05-01",
        )
    )

    assert payload["status"] == "ok"
    assert payload["account_summary"]["AvailableFunds_USD"] == "1000000.00"
    assert payload["positions"][0]["symbol"] == "NVDA"
    assert payload["authority"]["broker_submit_allowed"] is False


def test_write_position_decision_requires_thesis_and_context(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run_dir(tmp_path, monkeypatch)

    payload = json.loads(
        MoirixPositionDecisionTool().execute(
            run_dir=str(run_dir),
            decision_json=json.dumps(_valid_decision()),
        )
    )

    assert payload["status"] == "blocked"
    assert "moirix_position_decision_inputs_missing" in payload["claim_gate"]["blockers"]
    assert not (run_dir / "artifacts" / "moirix" / "position_decision.json").exists()


def test_write_position_decision_persists_research_only_proposal(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run_dir(tmp_path, monkeypatch)
    _write_thesis_and_context(run_dir)

    payload = json.loads(
        MoirixPositionDecisionTool().execute(
            run_dir=str(run_dir),
            decision_json=json.dumps(_valid_decision()),
        )
    )

    out = run_dir / "artifacts" / "moirix"
    assert payload["status"] == "ok"
    assert (out / "position_decision.json").exists()
    assert (out / "trade_proposal.json").exists()
    assert (out / "risk_sizing_report.json").exists()
    assert (out / "portfolio_adjustment_plan.md").exists()
    decision = json.loads((out / "position_decision.json").read_text(encoding="utf-8"))
    proposal = json.loads((out / "trade_proposal.json").read_text(encoding="utf-8"))
    assert decision["action"] == "add"
    assert proposal["orders"][0]["symbol"] == "NVDA"
    assert proposal["execution_gate"]["requires_explicit_approval"] is True
    assert proposal["authority"]["paper_trade_proposal_allowed"] is False
    assert proposal["authority"]["broker_submit_allowed"] is False
    assert proposal["authority"]["ready_for_real_money_trading_authority"] is False


def test_write_position_decision_blocks_when_context_is_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run_dir(tmp_path, monkeypatch)
    _write_thesis_and_context(run_dir)
    context = run_dir / "artifacts" / "moirix" / "event_decision_context.json"
    payload_context = json.loads(context.read_text(encoding="utf-8"))
    payload_context["status"] = "blocked"
    payload_context["claim_gate"] = {"blockers": ["positions_unavailable"]}
    context.write_text(json.dumps(payload_context), encoding="utf-8")

    payload = json.loads(
        MoirixPositionDecisionTool().execute(run_dir=str(run_dir), decision_json=json.dumps(_valid_decision()))
    )

    assert payload["status"] == "blocked"
    assert "moirix_position_decision_grounding_invalid" in payload["claim_gate"]["blockers"]
    assert any("event_decision_context" in item for item in payload["violations"])


def test_write_position_decision_rejects_legacy_numeric_fields_and_empty_action_orders(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run_dir(tmp_path, monkeypatch)
    _write_thesis_and_context(run_dir)
    decision = _valid_decision()
    decision["impact_score"] = 0.5
    decision["proposed_orders"] = []

    payload = json.loads(
        MoirixPositionDecisionTool().execute(
            run_dir=str(run_dir),
            decision_json=json.dumps(decision),
        )
    )

    assert payload["status"] == "blocked"
    assert "moirix_position_decision_schema_invalid" in payload["claim_gate"]["blockers"]
    assert any("impact_score" in item for item in payload["violations"])
    assert "proposed_orders must be non-empty for actionable decisions" in payload["violations"]
    assert not (run_dir / "artifacts" / "moirix" / "trade_proposal.json").exists()


def test_execute_trade_proposal_blocks_without_explicit_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run_dir(tmp_path, monkeypatch)
    _write_thesis_and_context(run_dir)
    MoirixPositionDecisionTool().execute(run_dir=str(run_dir), decision_json=json.dumps(_valid_decision()))

    payload = json.loads(
        MoirixTradeExecutionTool().execute(
            run_dir=str(run_dir),
            connection="ibkr-paper-local",
            dry_run=True,
        )
    )

    assert payload["status"] == "blocked"
    assert "moirix_execution_approval_missing" in payload["claim_gate"]["blockers"]
    assert (run_dir / "artifacts" / "moirix" / "execution_status.json").exists()


def test_export_decision_projection_writes_backtest_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run_dir(tmp_path, monkeypatch)
    _write_thesis_and_context(run_dir)
    MoirixPositionDecisionTool().execute(run_dir=str(run_dir), decision_json=json.dumps(_valid_decision()))

    payload = json.loads(
        MoirixDecisionProjectionTool().execute(
            run_dir=str(run_dir),
            projection_mode="window",
        )
    )

    out = run_dir / "artifacts" / "moirix"
    assert payload["status"] == "ok"
    assert payload["row_count"] == 1
    assert (out / "decision_projection.csv").exists()
    assert (out / "decision_projection.json").exists()
    assert (out / "backtest_projection_manifest.json").exists()
    assert (out / "decision_projection_signal_engine.py").exists()
    csv_text = (out / "decision_projection.csv").read_text(encoding="utf-8")
    assert "NVDA" in csv_text
    assert "broker_submit_allowed" in csv_text
    assert "target_weight" in csv_text
    assert "0.025" in csv_text
    manifest = json.loads((out / "backtest_projection_manifest.json").read_text(encoding="utf-8"))
    assert manifest["usage"].startswith("Backtest projection only")
    assert manifest["vibe_backtest_consumer"]["type"] == "signal_engine_template"
    assert manifest["projection_context"]["sizing_mode"] == "risk_sizing_target_weight"
    assert manifest["projection_context"]["portfolio_base"] == 100000.0
    assert manifest["authority"]["broker_submit_allowed"] is False

    import pandas as pd
    from backtest.runner import _load_module_from_file

    code_path = run_dir / "code" / "signal_engine.py"
    code_path.parent.mkdir(parents=True)
    code_path.write_text((out / "decision_projection_signal_engine.py").read_text(encoding="utf-8"), encoding="utf-8")
    module = _load_module_from_file(code_path, "projection_signal_engine_test")
    index = pd.to_datetime(["2025-05-01", "2025-05-03", "2025-05-11"])
    signals = module.SignalEngine().generate({"NVDA": pd.DataFrame({"close": [1.0, 1.1, 1.2]}, index=index)})
    assert list(signals["NVDA"]) == [0.0, 0.025, 0.0]


def test_export_decision_projection_accepts_explicit_target_weight_without_max_notional(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run_dir(tmp_path, monkeypatch)
    _write_thesis_and_context(run_dir)
    decision = _valid_decision()
    decision["risk_sizing"] = {
        "target_weight": 0.15,
        "max_loss_notional": 250,
        "portfolio_impact": "explicit 15 percent target exposure",
    }

    write_payload = json.loads(
        MoirixPositionDecisionTool().execute(run_dir=str(run_dir), decision_json=json.dumps(decision))
    )
    assert write_payload["status"] == "ok"
    payload = json.loads(MoirixDecisionProjectionTool().execute(run_dir=str(run_dir), projection_mode="window"))

    out = run_dir / "artifacts" / "moirix"
    assert payload["status"] == "ok"
    csv_text = (out / "decision_projection.csv").read_text(encoding="utf-8")
    assert "0.15" in csv_text
    assert "risk_sizing.target_weight" in csv_text
    manifest = json.loads((out / "backtest_projection_manifest.json").read_text(encoding="utf-8"))
    assert manifest["projection_context"]["sizing_mode"] == "explicit_target_weight"
    assert manifest["projection_context"]["weight_basis"] == "risk_sizing.target_weight"


def test_export_decision_projection_trim_uses_current_position_weight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run_dir(tmp_path, monkeypatch)
    _write_thesis_and_context(run_dir)
    decision = _valid_decision()
    decision["action"] = "trim"
    decision["risk_sizing"] = {
        "max_position_notional": 400,
        "max_loss_notional": 100,
        "portfolio_impact": "trim current exposure by four tenths of one percent",
    }
    decision["proposed_orders"] = [
        {
            "symbol": "NVDA",
            "side": "sell",
            "order_type": "market",
            "notional": 400,
            "time_in_force": "day",
        }
    ]
    MoirixPositionDecisionTool().execute(run_dir=str(run_dir), decision_json=json.dumps(decision))
    payload = json.loads(MoirixDecisionProjectionTool().execute(run_dir=str(run_dir), projection_mode="window"))

    out = run_dir / "artifacts" / "moirix"
    assert payload["status"] == "ok"
    rows = json.loads((out / "decision_projection.json").read_text(encoding="utf-8"))["rows"]
    assert rows[0]["target_weight"] == pytest.approx(0.005)

    import pandas as pd
    from backtest.runner import _load_module_from_file

    code_path = run_dir / "code" / "signal_engine.py"
    code_path.parent.mkdir(parents=True, exist_ok=True)
    code_path.write_text((out / "decision_projection_signal_engine.py").read_text(encoding="utf-8"), encoding="utf-8")
    module = _load_module_from_file(code_path, "projection_signal_engine_trim_test")
    index = pd.to_datetime(["2025-05-01", "2025-05-03", "2025-05-11"])
    signals = module.SignalEngine().generate({"NVDA": pd.DataFrame({"close": [1.0, 1.1, 1.2]}, index=index)})
    assert list(signals["NVDA"]) == pytest.approx([0.0, 0.005, 0.0])


def test_export_decision_projection_trim_without_position_value_does_not_fake_weight(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run_dir(tmp_path, monkeypatch)
    _write_thesis_and_context(run_dir)
    context_path = run_dir / "artifacts" / "moirix" / "event_decision_context.json"
    context = json.loads(context_path.read_text(encoding="utf-8"))
    context["positions"] = [{"symbol": "NVDA", "position": 10}]
    context_path.write_text(json.dumps(context), encoding="utf-8")
    decision = _valid_decision()
    decision["action"] = "trim"
    decision["proposed_orders"] = [
        {
            "symbol": "NVDA",
            "side": "sell",
            "order_type": "market",
            "notional": 400,
            "time_in_force": "day",
        }
    ]
    MoirixPositionDecisionTool().execute(run_dir=str(run_dir), decision_json=json.dumps(decision))
    payload = json.loads(MoirixDecisionProjectionTool().execute(run_dir=str(run_dir), projection_mode="window"))

    out = run_dir / "artifacts" / "moirix"
    assert payload["status"] == "ok"
    rows = json.loads((out / "decision_projection.json").read_text(encoding="utf-8"))["rows"]
    assert rows[0]["target_weight"] == ""
    assert rows[0]["weight_basis"] == "current_position_required"


def test_execute_trade_proposal_blocks_readonly_paper_connection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run_dir(tmp_path, monkeypatch)
    _write_thesis_and_context(run_dir)
    MoirixPositionDecisionTool().execute(run_dir=str(run_dir), decision_json=json.dumps(_valid_decision()))
    proposal_path = run_dir / "artifacts" / "moirix" / "trade_proposal.json"
    approval_path = run_dir / "artifacts" / "moirix" / "execution_approval.json"
    _write_execution_approval(approval_path, proposal_path=proposal_path, connection="ibkr-paper-local")

    payload = json.loads(
        MoirixTradeExecutionTool().execute(
            run_dir=str(run_dir),
            approval_path=str(approval_path),
            connection="ibkr-paper-local",
            dry_run=True,
        )
    )

    assert payload["status"] == "blocked"
    assert "paper_execution_profile_readonly" in payload["claim_gate"]["blockers"]
    assert "paper_execution_profile_lacks_orders_place" in payload["claim_gate"]["blockers"]


def test_execute_trade_proposal_requires_approval_authority(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run_dir(tmp_path, monkeypatch)
    _write_thesis_and_context(run_dir)
    MoirixPositionDecisionTool().execute(run_dir=str(run_dir), decision_json=json.dumps(_valid_decision()))
    proposal_path = run_dir / "artifacts" / "moirix" / "trade_proposal.json"
    approval_path = run_dir / "artifacts" / "moirix" / "execution_approval.json"
    _write_execution_approval(approval_path, proposal_path=proposal_path, connection="ibkr-paper-local", authority={})

    payload = json.loads(
        MoirixTradeExecutionTool().execute(
            run_dir=str(run_dir),
            approval_path=str(approval_path),
            connection="ibkr-paper-local",
            dry_run=True,
        )
    )

    assert payload["status"] == "blocked"
    assert "paper_execution_approval_missing_paper_authority" in payload["claim_gate"]["blockers"]
    assert "paper_execution_approval_missing_broker_submit_authority" in payload["claim_gate"]["blockers"]


def test_execute_trade_proposal_dry_run_passes_with_explicit_paper_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run_dir(tmp_path, monkeypatch)
    _write_thesis_and_context(run_dir)
    MoirixPositionDecisionTool().execute(run_dir=str(run_dir), decision_json=json.dumps(_valid_decision()))
    proposal_path = run_dir / "artifacts" / "moirix" / "trade_proposal.json"
    approval_path = run_dir / "artifacts" / "moirix" / "execution_approval.json"
    _write_execution_approval(approval_path, proposal_path=proposal_path, connection="alpaca-paper-trade")

    payload = json.loads(
        MoirixTradeExecutionTool().execute(
            run_dir=str(run_dir),
            approval_path=str(approval_path),
            connection="alpaca-paper-trade",
            dry_run=True,
        )
    )

    assert payload["status"] == "dry_run"
    assert payload["claim_gate"]["blockers"] == []
    assert payload["broker_results"] == []
    assert payload["authority"]["paper_trade_proposal_allowed"] is True
    assert payload["authority"]["broker_submit_allowed"] is False
    assert payload["authority"]["ready_for_real_money_trading_authority"] is False


def test_operator_approval_helper_generates_execution_approval(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    run_dir = _run_dir(tmp_path, monkeypatch)
    _write_thesis_and_context(run_dir)
    MoirixPositionDecisionTool().execute(run_dir=str(run_dir), decision_json=json.dumps(_valid_decision()))
    helper = Path(__file__).resolve().parents[1] / "scripts" / "moirix_approve_paper_execution.py"

    result = subprocess.run(
        [
            sys.executable,
            str(helper),
            "--run-dir",
            str(run_dir),
            "--approved-by",
            "pytest",
            "--reason",
            "paper dry-run test",
            "--phrase",
            "APPROVE PAPER EXECUTION",
            "--connection",
            "alpaca-paper-trade",
            "--max-notional",
            "10000",
        ],
        check=True,
        text=True,
        capture_output=True,
    )
    helper_payload = json.loads(result.stdout)
    approval_path = Path(helper_payload["approval_path"])

    payload = json.loads(
        MoirixTradeExecutionTool().execute(
            run_dir=str(run_dir),
            approval_path=str(approval_path),
            connection="alpaca-paper-trade",
            dry_run=True,
        )
    )

    assert approval_path.exists()
    assert payload["status"] == "dry_run"


def test_authority_guard_preserves_blocked(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _use_fake_adapter(tmp_path, monkeypatch)
    run_dir = _run_dir(tmp_path, monkeypatch)
    main_status = run_dir / "artifacts" / "moirix" / "status.json"
    main_status.parent.mkdir(parents=True, exist_ok=True)
    main_status.write_text('{"status":"main_graph_ok"}\n', encoding="utf-8")
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
    status_path = Path(payload["artifacts"]["status"])
    assert status_path.parent.parent == run_dir / "artifacts" / "moirix" / "authority_checks"
    assert status_path.parent.name.startswith("proposal-")
    for artifact_path in payload["artifacts"].values():
        assert "/artifacts/moirix/authority_checks/" in artifact_path
    assert json.loads(main_status.read_text(encoding="utf-8"))["status"] == "main_graph_ok"


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
    assert "event_thesis_graph:outside_artifacts_root" in payload["violations"]


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
        MoirixEventThesisTool(),
        MoirixPortfolioContextTool(),
        MoirixPositionDecisionTool(),
        MoirixDecisionProjectionTool(),
        MoirixAuthorityGuardTool(),
    ]

    for tool in tools:
        properties = tool.parameters.get("properties", {})
        assert "broker_submit" not in properties
        assert "order" not in properties
        assert "live_trading" not in properties
        assert "submit" not in properties
