"""Append-only audit ledger for paper trading mutations."""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from src.config.paths import get_runtime_root
from src.tools.redaction import redact_payload


def paper_audit_ledger_path() -> Path:
    """Return the append-only paper trading audit ledger path."""
    return get_runtime_root() / "trading" / "paper" / "audit.jsonl"


def write_paper_action(
    *,
    kind: str,
    outcome: str,
    profile_id: str | None,
    request: dict[str, Any],
    response: dict[str, Any] | None = None,
    gate_decision: dict[str, Any] | None = None,
    approval_id: str | None = None,
    tool_name: str | None = None,
    run_dir: str | None = None,
) -> dict[str, Any]:
    """Append a redacted paper action record and return the record."""
    record = redact_payload(
        {
            "audit_id": f"pa_{uuid.uuid4().hex}",
            "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
            "kind": kind,
            "outcome": outcome,
            "profile_id": profile_id,
            "tool_name": tool_name,
            "run_dir": run_dir,
            "approval_id": approval_id,
            "request": request,
            "response": response or {},
            "gate_decision": gate_decision or {},
        }
    )
    path = paper_audit_ledger_path()
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record
