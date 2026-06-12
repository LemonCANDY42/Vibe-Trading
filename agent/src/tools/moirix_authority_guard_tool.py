"""Optional Moirix authority guard tool."""

from __future__ import annotations

import json
from typing import Any

from src.agent.tools import BaseTool
from src.tools._moirix_adapter import adapter_authority_artifact_dir, call_adapter, resolve_adapter_input


class MoirixAuthorityGuardTool(BaseTool):
    """Run a fail-closed Moirix authority check for a research proposal."""

    name = "moirix_authority_guard"
    description = (
        "Check a proposal JSON through the local Moirix authority guard. "
        "Research-only and paper-proposal-only requests may pass; broker writes, "
        "orders, custody actions, live trading, or real-money authority must be "
        "blocked. Authority-check artifacts are isolated under "
        "artifacts/moirix/authority_checks so blocked checks do not overwrite the "
        "run's main Moirix graph/signal artifacts. This tool never submits, "
        "cancels, or modifies orders."
    )
    parameters = {
        "type": "object",
        "properties": {
            "proposal_path": {
                "type": "string",
                "description": "Proposal JSON path under the current run or an allowed import root.",
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Adapter subprocess timeout in seconds (default 120).",
                "default": 120,
            },
        },
        "required": ["proposal_path"],
    }
    repeatable = True
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        run_dir = kwargs.get("run_dir")
        if not run_dir:
            return json.dumps(
                {"status": "error", "error": "run_dir is required for moirix_authority_guard artifacts"},
                ensure_ascii=False,
        )

        try:
            proposal_path, error = resolve_adapter_input(
                kwargs.get("proposal_path"),
                str(run_dir),
                blocker_prefix="moirix_authority_proposal",
            )
        except ValueError as exc:
            return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)

        if error is not None:
            return json.dumps(error, ensure_ascii=False)
        if proposal_path is None:
            return json.dumps({"status": "error", "error": "proposal_path could not be resolved"}, ensure_ascii=False)

        try:
            out_dir = adapter_authority_artifact_dir(str(run_dir), proposal_path)
        except ValueError as exc:
            return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)

        timeout = int(kwargs.get("timeout_seconds") or 120)
        payload = call_adapter(
            [
                "authority-check",
                "--proposal",
                str(proposal_path),
                "--out",
                str(out_dir),
            ],
            out_dir=out_dir,
            timeout_seconds=timeout,
        )
        return json.dumps(payload, ensure_ascii=False, default=str)
