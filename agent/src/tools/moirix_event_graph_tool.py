"""Optional Moirix event-impact graph tool."""

from __future__ import annotations

import json
from typing import Any

from src.agent.tools import BaseTool
from src.tools._moirix_adapter import adapter_artifact_dir, call_adapter, resolve_news_input


class MoirixEventGraphTool(BaseTool):
    """Build a candidate event-impact graph through the local Moirix adapter."""

    name = "moirix_build_event_graph"
    description = (
        "Build a Moirix candidate event-impact graph from PIT news evidence or an "
        "allowed uploaded event file. Writes event_impact_graph.json and related "
        "Moirix artifacts under the current run's artifacts/moirix directory. "
        "Graph output is hypothesis evidence only, not a trading order."
    )
    parameters = {
        "type": "object",
        "properties": {
            "target": {"type": "string", "description": "Target symbol or instrument, e.g. NVDA."},
            "as_of": {"type": "string", "description": "PIT cutoff date/time, e.g. 2025-05-01."},
            "input_path": {
                "type": "string",
                "description": (
                    "Optional news JSON/JSONL path under the current run or an allowed "
                    "import root. Defaults to artifacts/moirix/news_evidence.jsonl."
                ),
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Adapter subprocess timeout in seconds (default 120).",
                "default": 120,
            },
        },
        "required": ["target", "as_of"],
    }
    repeatable = True
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        run_dir = kwargs.get("run_dir")
        if not run_dir:
            return json.dumps(
                {
                    "status": "error",
                    "error": "run_dir is required for moirix_build_event_graph artifacts",
                },
                ensure_ascii=False,
            )

        try:
            out_dir = adapter_artifact_dir(str(run_dir))
            input_path, error = resolve_news_input(kwargs.get("input_path"), str(run_dir))
        except ValueError as exc:
            return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)

        if error is not None:
            return json.dumps(error, ensure_ascii=False)
        if input_path is None:
            return json.dumps(
                {"status": "error", "error": "input_path could not be resolved"},
                ensure_ascii=False,
            )

        target = str(kwargs.get("target", "")).strip()
        as_of = str(kwargs.get("as_of", "")).strip()
        timeout = int(kwargs.get("timeout_seconds") or 120)
        if not target or not as_of:
            return json.dumps(
                {"status": "error", "error": "target and as_of are required"},
                ensure_ascii=False,
            )

        payload = call_adapter(
            [
                "build-event-graph",
                "--input",
                str(input_path),
                "--target",
                target,
                "--as-of",
                as_of,
                "--out",
                str(out_dir),
            ],
            out_dir=out_dir,
            timeout_seconds=timeout,
        )
        return json.dumps(payload, ensure_ascii=False, default=str)
