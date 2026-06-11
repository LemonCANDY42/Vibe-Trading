"""Optional Moirix local adapter status tool."""

from __future__ import annotations

import json
from typing import Any

from src.agent.tools import BaseTool
from src.tools._moirix_adapter import call_adapter


class MoirixStatusTool(BaseTool):
    """Report availability and authority state for the local Moirix adapter."""

    name = "moirix_status"
    description = (
        "Check the optional local Moirix adapter for PIT news/event-graph research. "
        "Returns adapter availability, supported scopes, source-lake readiness, and "
        "fail-closed trading authority fields. No broker or order actions."
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
    is_readonly = True

    def execute(self, **kwargs: Any) -> str:
        timeout = int(kwargs.get("timeout_seconds") or 120)
        payload = call_adapter(["status"], timeout_seconds=timeout)
        return json.dumps(payload, ensure_ascii=False, default=str)
