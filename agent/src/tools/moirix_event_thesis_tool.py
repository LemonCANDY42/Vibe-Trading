"""Write Agent-synthesized Moirix event thesis artifacts."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from src.agent.tools import BaseTool
from src.tools._moirix_adapter import adapter_artifact_dir
from src.tools.moirix_grounding import validate_event_thesis_grounding


SCHEMA_VERSION = "vibe.moirix_event_thesis.v1"
FORBIDDEN_THESIS_KEYS = {"strength", "weight", "confidence", "impact_score", "edge_weight"}
TRUTH_STATUSES = {"verified", "likely", "uncertain", "disputed", "superseded"}
SOURCE_QUALITIES = {"high", "medium", "low", "unknown"}
TARGET_RELEVANCE = {"direct", "indirect", "sector", "macro", "none"}
IMPACT_PATHS = {
    "revenue",
    "margin",
    "valuation",
    "liquidity",
    "sentiment",
    "supply_chain",
    "policy",
    "unknown",
}
IMPACT_DIRECTIONS = {"positive", "negative", "mixed", "neutral", "uncertain"}
IMPACT_HORIZONS = {"intraday", "days", "weeks", "months", "unknown"}
RELATION_TYPES = {
    "supports",
    "contradicts",
    "supersedes",
    "updates",
    "duplicates",
    "weakens",
    "confirms",
    "causal_chain",
}
STANCES = {"bullish", "bearish", "mixed", "neutral", "blocked"}
ACTIONABILITY = {"actionable", "watch", "not_actionable", "blocked"}
FALSE_AUTHORITY_FIELDS = (
    "paper_trade_proposal_allowed",
    "broker_submit_allowed",
    "ready_for_real_money_trading_authority",
)


class MoirixEventThesisTool(BaseTool):
    """Persist an Agent-generated event thesis as canonical Moirix artifacts."""

    name = "moirix_write_event_thesis"
    description = (
        "Validate and write the canonical Agent-driven Moirix event thesis artifacts. "
        "The thesis must be based on existing PIT evidence under artifacts/moirix/news_evidence.jsonl, "
        "use semantic event relations instead of edge weights, and keep all trading authority fail-closed. "
        "Writes event_thesis_graph.json, event_thesis_report.md, authority_status.json, and "
        "vibe_run_card_patch.json under artifacts/moirix. This tool never submits orders."
    )
    parameters = {
        "type": "object",
        "properties": {
            "thesis_json": {
                "type": "string",
                "description": "Event thesis JSON string using schema vibe.moirix_event_thesis.v1.",
            },
            "report_markdown": {
                "type": "string",
                "description": "Optional human-readable thesis report. If omitted, a concise report is generated from thesis_json.",
            },
        },
        "required": ["thesis_json"],
    }
    repeatable = True
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        run_dir = kwargs.get("run_dir")
        if not run_dir:
            return json.dumps(
                {"status": "error", "error": "run_dir is required for moirix_write_event_thesis artifacts"},
                ensure_ascii=False,
            )

        try:
            out_dir = adapter_artifact_dir(str(run_dir))
        except ValueError as exc:
            return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)

        evidence_path = out_dir / "news_evidence.jsonl"
        if not evidence_path.is_file():
            return json.dumps(
                _blocked(
                    "moirix_event_thesis_evidence_missing",
                    "news_evidence.jsonl is required before writing an event thesis",
                ),
                ensure_ascii=False,
            )

        try:
            thesis = _parse_thesis(kwargs.get("thesis_json"))
        except ValueError as exc:
            return json.dumps(_blocked("moirix_event_thesis_invalid_json", str(exc)), ensure_ascii=False)

        errors = _validate_thesis(thesis)
        if errors:
            return json.dumps(
                _blocked(
                    "moirix_event_thesis_schema_invalid",
                    "event thesis did not satisfy the canonical thesis schema",
                    extra={"violations": errors},
                ),
                ensure_ascii=False,
            )

        thesis = _normalize_authority(thesis)
        grounding_errors = validate_event_thesis_grounding(out_dir, thesis)
        if grounding_errors:
            return json.dumps(
                _blocked(
                    "moirix_event_thesis_grounding_invalid",
                    "event thesis is not grounded in matching nonblocked PIT news evidence",
                    extra={"violations": grounding_errors},
                ),
                ensure_ascii=False,
            )

        generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        thesis.setdefault("generated_at", generated_at)
        thesis.setdefault("status", "ok")
        thesis.setdefault("source_artifacts", {})["news_evidence"] = str(evidence_path)

        thesis_path = out_dir / "event_thesis_graph.json"
        report_path = out_dir / "event_thesis_report.md"
        authority_path = out_dir / "authority_status.json"
        run_card_patch_path = out_dir / "vibe_run_card_patch.json"

        report = str(kwargs.get("report_markdown") or "").strip() or _build_report(thesis)
        authority = {
            "schema_version": "vibe.moirix_authority_status.v1",
            "status": "ok",
            "scope": "research_only_event_thesis",
            "authority": thesis["authority"],
            "claim_gate": {
                "blockers": [],
                "ready_for_real_money_trading_authority": False,
                "broker_submit_allowed": False,
            },
        }
        run_card_patch = {
            "schema_version": "vibe.moirix_run_card_patch.v1",
            "status": "ok",
            "moirix_mode": "event_thesis",
            "artifacts": {
                "event_thesis_graph": "artifacts/moirix/event_thesis_graph.json",
                "event_thesis_report": "artifacts/moirix/event_thesis_report.md",
                "authority_status": "artifacts/moirix/authority_status.json",
            },
            "authority": thesis["authority"],
        }

        thesis_path.write_text(json.dumps(thesis, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        report_path.write_text(report.rstrip() + "\n", encoding="utf-8")
        authority_path.write_text(json.dumps(authority, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        run_card_patch_path.write_text(
            json.dumps(run_card_patch, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

        payload = {
            "schema_version": "vibe.moirix_event_thesis_write.v1",
            "status": "ok",
            "target": thesis.get("target"),
            "market": thesis.get("market"),
            "as_of": thesis.get("as_of"),
            "artifacts": {
                "event_thesis_graph": str(thesis_path),
                "event_thesis_report": str(report_path),
                "authority_status": str(authority_path),
                "vibe_run_card_patch": str(run_card_patch_path),
                "news_evidence": str(evidence_path),
            },
            "authority": thesis["authority"],
            "claim_gate": {"blockers": [], "ready_for_real_money_trading_authority": False},
        }
        return json.dumps(payload, ensure_ascii=False, default=str)


def _parse_thesis(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError(f"thesis_json is not valid JSON: {exc}") from exc
    else:
        parsed = value
    if not isinstance(parsed, dict):
        raise ValueError("thesis_json must be a JSON object")
    return dict(parsed)


def _validate_thesis(thesis: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    errors.extend(_find_forbidden_keys(thesis))
    if thesis.get("schema_version") != SCHEMA_VERSION:
        errors.append(f"schema_version must be {SCHEMA_VERSION}")
    for key in ("target", "market", "as_of"):
        if not _nonempty_str(thesis.get(key)):
            errors.append(f"{key} is required")

    evidence_items = thesis.get("evidence_items")
    if not isinstance(evidence_items, list) or not evidence_items:
        errors.append("evidence_items must be a non-empty list")
    elif len(evidence_items) > 200:
        errors.append("evidence_items exceeds the 200 item limit")
    else:
        for index, item in enumerate(evidence_items):
            if not isinstance(item, dict):
                errors.append(f"evidence_items[{index}] must be an object")
                continue
            _require_enum(errors, item, "truth_status", TRUTH_STATUSES, f"evidence_items[{index}]")
            _require_enum(errors, item, "source_quality", SOURCE_QUALITIES, f"evidence_items[{index}]")
            _require_enum(errors, item, "target_relevance", TARGET_RELEVANCE, f"evidence_items[{index}]")
            _require_enum(errors, item, "impact_path", IMPACT_PATHS, f"evidence_items[{index}]")
            _require_enum(errors, item, "impact_direction", IMPACT_DIRECTIONS, f"evidence_items[{index}]")
            _require_enum(errors, item, "impact_horizon", IMPACT_HORIZONS, f"evidence_items[{index}]")
            for key in ("event_id", "summary", "analysis"):
                if not _nonempty_str(item.get(key)):
                    errors.append(f"evidence_items[{index}].{key} is required")
            if not isinstance(item.get("invalidated_by", []), list):
                errors.append(f"evidence_items[{index}].invalidated_by must be a list")

    relations = thesis.get("relations")
    if relations is None:
        thesis["relations"] = []
    elif not isinstance(relations, list):
        errors.append("relations must be a list")
    else:
        for index, relation in enumerate(relations):
            if not isinstance(relation, dict):
                errors.append(f"relations[{index}] must be an object")
                continue
            for key in ("source_event_id", "target_event_id", "explanation"):
                if not _nonempty_str(relation.get(key)):
                    errors.append(f"relations[{index}].{key} is required")
            _require_enum(errors, relation, "relation_type", RELATION_TYPES, f"relations[{index}]")

    current = thesis.get("current_thesis")
    if not isinstance(current, dict):
        errors.append("current_thesis must be an object")
    else:
        _require_enum(errors, current, "stance", STANCES, "current_thesis")
        _require_enum(errors, current, "actionability", ACTIONABILITY, "current_thesis")
        window = current.get("execution_window")
        if not isinstance(window, dict):
            errors.append("current_thesis.execution_window must be an object")
        else:
            for key in ("start", "end", "reason"):
                if not _nonempty_str(window.get(key)):
                    errors.append(f"current_thesis.execution_window.{key} is required")
        for key in ("supporting_events", "contradicting_events", "open_questions", "invalidation_triggers"):
            if not isinstance(current.get(key), list):
                errors.append(f"current_thesis.{key} must be a list")

    authority = thesis.get("authority")
    if authority is not None and not isinstance(authority, dict):
        errors.append("authority must be an object")
    elif isinstance(authority, dict):
        for field in FALSE_AUTHORITY_FIELDS:
            if authority.get(field) is True:
                errors.append(f"authority.{field} must remain false")
        if authority.get("research_only") is False:
            errors.append("authority.research_only must remain true")
    return errors


def _find_forbidden_keys(value: Any, path: str = "$") -> list[str]:
    errors: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            child_path = f"{path}.{key}"
            if key.lower() in FORBIDDEN_THESIS_KEYS:
                errors.append(f"{child_path} uses legacy numeric graph semantics")
            errors.extend(_find_forbidden_keys(child, child_path))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            errors.extend(_find_forbidden_keys(child, f"{path}[{index}]"))
    return errors


def _normalize_authority(thesis: dict[str, Any]) -> dict[str, Any]:
    authority = thesis.get("authority")
    if not isinstance(authority, dict):
        authority = {}
    authority.update(
        {
            "research_only": True,
            "paper_trade_proposal_allowed": False,
            "broker_submit_allowed": False,
            "ready_for_real_money_trading_authority": False,
        }
    )
    thesis["authority"] = authority
    return thesis


def _require_enum(
    errors: list[str],
    item: dict[str, Any],
    key: str,
    allowed: set[str],
    path: str,
) -> None:
    value = item.get(key)
    if value not in allowed:
        errors.append(f"{path}.{key} must be one of {sorted(allowed)}")


def _nonempty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _build_report(thesis: dict[str, Any]) -> str:
    current = thesis.get("current_thesis") if isinstance(thesis.get("current_thesis"), dict) else {}
    window = current.get("execution_window") if isinstance(current.get("execution_window"), dict) else {}
    evidence = thesis.get("evidence_items") if isinstance(thesis.get("evidence_items"), list) else []
    relations = thesis.get("relations") if isinstance(thesis.get("relations"), list) else []
    lines = [
        f"# Moirix Event Thesis: {thesis.get('target', 'unknown')}",
        "",
        f"- Market: `{thesis.get('market', 'unknown')}`",
        f"- As of: `{thesis.get('as_of', 'unknown')}`",
        f"- Stance: `{current.get('stance', 'unknown')}`",
        f"- Actionability: `{current.get('actionability', 'unknown')}`",
        f"- Execution window: `{window.get('start', 'unknown')}` to `{window.get('end', 'unknown')}`",
        "",
        "## Current Thesis",
        "",
        str(current.get("summary") or window.get("reason") or "No thesis summary recorded."),
        "",
        "## Evidence Items",
        "",
    ]
    if evidence:
        lines.extend(
            [
                "| Event | Truth | Relevance | Direction | Horizon | Summary |",
                "|---|---|---|---|---|---|",
            ]
        )
        for item in evidence[:50]:
            if not isinstance(item, dict):
                continue
            lines.append(
                "| "
                + " | ".join(
                    _md_cell(item.get(key))
                    for key in (
                        "event_id",
                        "truth_status",
                        "target_relevance",
                        "impact_direction",
                        "impact_horizon",
                        "summary",
                    )
                )
                + " |"
            )
    else:
        lines.append("No evidence items recorded.")
    lines.extend(["", "## Relations", ""])
    if relations:
        lines.extend(["| Source | Relation | Target | Explanation |", "|---|---|---|---|"])
        for relation in relations[:50]:
            if not isinstance(relation, dict):
                continue
            lines.append(
                "| "
                + " | ".join(
                    _md_cell(relation.get(key))
                    for key in ("source_event_id", "relation_type", "target_event_id", "explanation")
                )
                + " |"
            )
    else:
        lines.append("No explicit event-to-event relations recorded.")
    lines.extend(
        [
            "",
            "## Authority",
            "",
            "Research-only. Broker submission and real-money trading authority are false.",
        ]
    )
    return "\n".join(lines)


def _md_cell(value: Any) -> str:
    return str(value or "").replace("|", "\\|").replace("\n", " ").strip()


def _blocked(blocker: str, message: str, *, extra: dict[str, Any] | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "vibe.moirix_event_thesis_write.v1",
        "status": "blocked",
        "error": message,
        "claim_gate": {
            "blockers": [blocker],
            "ready_for_real_money_trading_authority": False,
            "broker_submit_allowed": False,
        },
        "authority": {
            "research_only": True,
            "paper_trade_proposal_allowed": False,
            "broker_submit_allowed": False,
            "ready_for_real_money_trading_authority": False,
        },
    }
    if extra:
        payload.update(extra)
    return payload
