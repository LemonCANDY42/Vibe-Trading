"""Grounding checks for Kenny's Moirix evidence-to-decision workflow."""

from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any


_DATE_ONLY = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_SHORT_TZ = re.compile(r"([+-]\d{2})$")
_INVALID_EVIDENCE_STATES = {
    "blocked",
    "unavailable",
    "error",
    "invalid",
    "rejected",
    "fake",
    "synthetic",
}


def validate_event_thesis_grounding(out_dir: Path, thesis: dict[str, Any]) -> list[str]:
    """Validate that an Agent thesis is grounded in nonblocked PIT evidence."""
    errors: list[str] = []
    evidence_path = out_dir / "news_evidence.jsonl"
    request = _load_json(out_dir / "request.json", errors, "request.json")
    status = _load_json(out_dir / "status.json", errors, "status.json")
    coverage = _load_json(out_dir / "coverage_status.json", errors, "coverage_status.json")
    evidence_rows = _load_jsonl(evidence_path, errors)

    if errors:
        return errors
    if not evidence_rows:
        errors.append("news_evidence.jsonl must contain at least one PIT evidence row")

    if str(request.get("command") or "").strip() != "query-news":
        errors.append("request.json.command must be query-news for canonical thesis grounding")

    _require_nonblocked_status(errors, status, "status.json")
    _require_nonblocked_status(errors, coverage, "coverage_status.json")
    if _truthy(_dig(coverage, "coverage", "blocked_without_fake_evidence")) or _truthy(
        coverage.get("blocked_without_fake_evidence")
    ):
        errors.append("coverage_status reports blocked_without_fake_evidence")

    expected = _request_identity(request, status)
    _match_identity(errors, thesis, expected, label="thesis")

    thesis_as_of = _parse_dt(thesis.get("as_of"), end_of_day=True)
    if thesis_as_of is None:
        errors.append("thesis.as_of must be a parseable date or timestamp")

    evidence_by_id: dict[str, dict[str, Any]] = {}
    for index, row in enumerate(evidence_rows):
        event_id = _event_id(row)
        if not event_id:
            errors.append(f"news_evidence.jsonl row {index} is missing event_id")
            continue
        state = str(row.get("validation_state") or row.get("status") or "").strip().lower()
        if state in _INVALID_EVIDENCE_STATES:
            errors.append(f"evidence row {event_id} has invalid state {state!r}")
        evidence_by_id[event_id] = row

    referenced = _referenced_event_ids(thesis)
    missing = sorted(event_id for event_id in referenced if event_id not in evidence_by_id)
    if missing:
        errors.append(f"thesis references event ids not present in PIT evidence: {', '.join(missing[:10])}")

    if thesis_as_of is not None:
        for event_id in sorted(referenced):
            row = evidence_by_id.get(event_id)
            if row is None:
                continue
            visible_at = _parse_dt(row.get("visible_at") or row.get("published_at") or row.get("created_at"))
            if visible_at is None:
                errors.append(f"evidence row {event_id} is missing parseable visible_at")
                continue
            if visible_at > thesis_as_of:
                errors.append(f"evidence row {event_id} visible_at is after thesis.as_of")

    return errors


def validate_position_decision_grounding(out_dir: Path, decision: dict[str, Any]) -> list[str]:
    """Validate that a position decision is grounded in ok thesis and context artifacts."""
    errors: list[str] = []
    thesis = _load_json(out_dir / "event_thesis_graph.json", errors, "event_thesis_graph.json")
    context = _load_json(out_dir / "event_decision_context.json", errors, "event_decision_context.json")
    if errors:
        return errors

    _require_nonblocked_status(errors, thesis, "event_thesis_graph.json")
    _require_nonblocked_status(errors, context, "event_decision_context.json")
    _require_no_blockers(errors, thesis, "event_thesis_graph.json")
    _require_no_blockers(errors, context, "event_decision_context.json")
    _match_identity(errors, decision, thesis, label="decision vs thesis")
    _match_identity(errors, decision, context, label="decision vs context")

    authority = context.get("authority") if isinstance(context.get("authority"), dict) else {}
    if authority.get("broker_submit_allowed") is True or authority.get("ready_for_real_money_trading_authority") is True:
        errors.append("event_decision_context authority must remain broker-submit and real-money false")
    if context.get("positions") is None or not isinstance(context.get("positions"), list):
        errors.append("event_decision_context.positions must be present as a list, even when empty")
    return errors


def _load_json(path: Path, errors: list[str], label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        errors.append(f"{label} is required")
        return {}
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{label} is not readable JSON: {exc}")
        return {}
    if not isinstance(value, dict):
        errors.append(f"{label} must be a JSON object")
        return {}
    return value


def _load_jsonl(path: Path, errors: list[str]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        errors.append("news_evidence.jsonl is required")
        return rows
    except OSError as exc:
        errors.append(f"news_evidence.jsonl is not readable: {exc}")
        return rows
    for line_no, line in enumerate(raw.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            errors.append(f"news_evidence.jsonl line {line_no} is invalid JSON: {exc}")
            continue
        if not isinstance(value, dict):
            errors.append(f"news_evidence.jsonl line {line_no} must be a JSON object")
            continue
        rows.append(value)
    return rows


def _require_nonblocked_status(errors: list[str], payload: dict[str, Any], label: str) -> None:
    status = str(payload.get("status") or "").strip().lower()
    if status not in {"ok", "partial"}:
        errors.append(f"{label}.status must be ok or partial, got {status or 'missing'}")
    if status in {"blocked", "unavailable", "error"}:
        errors.append(f"{label}.status is blocked/unavailable/error")


def _require_no_blockers(errors: list[str], payload: dict[str, Any], label: str) -> None:
    blockers = _dig(payload, "claim_gate", "blockers")
    if isinstance(blockers, list) and blockers:
        errors.append(f"{label}.claim_gate.blockers must be empty")


def _request_identity(request: dict[str, Any], status: dict[str, Any]) -> dict[str, Any]:
    request_body = request.get("request") if isinstance(request.get("request"), dict) else request
    return {
        "target": request_body.get("target") or status.get("target"),
        "market": request_body.get("market") or status.get("market"),
        "as_of": request_body.get("as_of") or request_body.get("as-of") or status.get("as_of"),
    }


def _match_identity(errors: list[str], left: dict[str, Any], right: dict[str, Any], *, label: str) -> None:
    for key in ("target", "market", "as_of"):
        lval = _normalize_identity(left.get(key), key=key)
        rval = _normalize_identity(right.get(key), key=key)
        if not lval:
            errors.append(f"{label}.{key} is required")
            continue
        if not rval:
            errors.append(f"{label} source {key} is required")
            continue
        if lval != rval:
            errors.append(f"{label}.{key} mismatch: {left.get(key)!r} != {right.get(key)!r}")


def _normalize_identity(value: Any, *, key: str) -> str:
    text = "" if value is None else str(value).strip()
    if not text:
        return ""
    if key == "as_of":
        parsed = _parse_dt(text, end_of_day=True)
        if parsed is None:
            return text
        return parsed.date().isoformat()
    return text.upper()


def _event_id(row: dict[str, Any]) -> str:
    for key in ("event_id", "id", "news_id", "source_event_id"):
        if row.get(key) not in (None, ""):
            return str(row[key]).strip()
    return ""


def _referenced_event_ids(thesis: dict[str, Any]) -> set[str]:
    event_ids: set[str] = set()
    for item in thesis.get("evidence_items") or []:
        if isinstance(item, dict) and item.get("event_id"):
            event_ids.add(str(item["event_id"]).strip())
    for relation in thesis.get("relations") or []:
        if not isinstance(relation, dict):
            continue
        for key in ("source_event_id", "target_event_id"):
            if relation.get(key):
                event_ids.add(str(relation[key]).strip())
    current = thesis.get("current_thesis") if isinstance(thesis.get("current_thesis"), dict) else {}
    for key in ("supporting_events", "contradicting_events"):
        for event_id in current.get(key) or []:
            if event_id not in (None, ""):
                event_ids.add(str(event_id).strip())
    return {event_id for event_id in event_ids if event_id}


def _parse_dt(value: Any, *, end_of_day: bool = False) -> datetime | None:
    text = "" if value is None else str(value).strip()
    if not text:
        return None
    if _DATE_ONLY.match(text):
        parsed_date = date.fromisoformat(text)
        return datetime.combine(parsed_date, time.max if end_of_day else time.min, tzinfo=timezone.utc)
    candidate = text.replace("Z", "+00:00")
    if _SHORT_TZ.search(candidate):
        candidate = f"{candidate}:00"
    try:
        parsed = datetime.fromisoformat(candidate)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _dig(payload: dict[str, Any], *keys: str) -> Any:
    value: Any = payload
    for key in keys:
        if not isinstance(value, dict):
            return None
        value = value.get(key)
    return value


def _truthy(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "y", "on"}
