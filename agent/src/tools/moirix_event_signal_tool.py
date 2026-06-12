"""Optional Moirix event-signal export tool."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.agent.tools import BaseTool
from src.tools._moirix_adapter import adapter_artifact_dir, call_adapter


class MoirixEventSignalTool(BaseTool):
    """Expose Moirix event_signal.csv as a Vibe run artifact."""

    name = "moirix_export_event_signal"
    description = (
        "Export the Moirix event_signal.csv artifact for later Vibe backtesting. "
        "This wraps the local Moirix export-vibe-artifacts command and requires an "
        "existing event_signal.csv under artifacts/moirix. It does not create fake "
        "event signals and does not touch broker/order paths."
    )
    parameters = {
        "type": "object",
        "properties": {
            "timeout_seconds": {
                "type": "integer",
                "description": "Adapter subprocess timeout in seconds (default 120).",
                "default": 120,
            },
        },
        "required": [],
    }
    repeatable = True
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        run_dir = kwargs.get("run_dir")
        if not run_dir:
            return json.dumps(
                {"status": "error", "error": "run_dir is required for moirix_export_event_signal artifacts"},
                ensure_ascii=False,
            )

        try:
            out_dir = adapter_artifact_dir(str(run_dir))
        except ValueError as exc:
            return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)

        timeout = int(kwargs.get("timeout_seconds") or 120)
        payload = call_adapter(
            [
                "export-vibe-artifacts",
                "--run-root",
                str(out_dir),
                "--out",
                str(out_dir),
            ],
            out_dir=out_dir,
            timeout_seconds=timeout,
        )
        signal_path = out_dir / "event_signal.csv"
        if not signal_path.exists():
            payload = _blocked_missing_event_signal(payload, signal_path)
        return json.dumps(payload, ensure_ascii=False, default=str)


def _blocked_missing_event_signal(payload: dict[str, Any], signal_path: Path) -> dict[str, Any]:
    result = dict(payload)
    result["status"] = "blocked"
    result["error"] = "Moirix event_signal.csv was not present after export-vibe-artifacts"
    claim_gate = result.get("claim_gate")
    if not isinstance(claim_gate, dict):
        claim_gate = {}
        result["claim_gate"] = claim_gate
    blockers = claim_gate.get("blockers")
    if not isinstance(blockers, list):
        blockers = []
        claim_gate["blockers"] = blockers
    blockers.append("moirix_event_signal_missing")
    result["event_signal_path"] = str(signal_path)
    return result
