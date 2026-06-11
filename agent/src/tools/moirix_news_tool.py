"""Optional Moirix PIT news query tool."""

from __future__ import annotations

import json
from typing import Any

from src.agent.tools import BaseTool
from src.tools._moirix_adapter import adapter_artifact_dir, call_adapter


class MoirixNewsTool(BaseTool):
    """Query Moirix point-in-time news evidence through the local adapter."""

    name = "moirix_query_news"
    description = (
        "Query the optional local Moirix adapter for PIT news/source-lake evidence. "
        "Outputs are written under the current run's artifacts/moirix directory. "
        "Blocked or unavailable Moirix states are returned as-is; this tool does not "
        "fabricate news evidence and does not touch broker/order paths."
    )
    parameters = {
        "type": "object",
        "properties": {
            "target": {"type": "string", "description": "Target symbol or instrument, e.g. NVDA."},
            "market": {"type": "string", "description": "Market label, e.g. US, HK, A-share."},
            "as_of": {"type": "string", "description": "PIT cutoff date/time, e.g. 2025-05-01."},
            "lookback_days": {
                "type": "integer",
                "description": "Lookback window in calendar days.",
                "default": 30,
            },
            "timeout_seconds": {
                "type": "integer",
                "description": "Adapter subprocess timeout in seconds (default 120).",
                "default": 120,
            },
        },
        "required": ["target", "market", "as_of"],
    }
    repeatable = True
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        run_dir = kwargs.get("run_dir")
        if not run_dir:
            return json.dumps(
                {
                    "status": "error",
                    "error": "run_dir is required for moirix_query_news artifacts",
                },
                ensure_ascii=False,
            )

        try:
            out_dir = adapter_artifact_dir(str(run_dir))
        except ValueError as exc:
            return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)

        target = str(kwargs.get("target", "")).strip()
        market = str(kwargs.get("market", "")).strip()
        as_of = str(kwargs.get("as_of", "")).strip()
        lookback_days = int(kwargs.get("lookback_days") or 30)
        timeout = int(kwargs.get("timeout_seconds") or 120)
        if not target or not market or not as_of:
            return json.dumps(
                {"status": "error", "error": "target, market, and as_of are required"},
                ensure_ascii=False,
            )

        payload = call_adapter(
            [
                "query-news",
                "--target",
                target,
                "--market",
                market,
                "--as-of",
                as_of,
                "--lookback-days",
                str(lookback_days),
                "--out",
                str(out_dir),
            ],
            out_dir=out_dir,
            timeout_seconds=timeout,
        )
        return json.dumps(payload, ensure_ascii=False, default=str)
