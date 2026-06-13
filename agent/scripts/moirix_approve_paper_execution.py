#!/usr/bin/env python3
"""Create an explicit Moirix paper-execution approval artifact.

This helper is intentionally not an Agent BaseTool. It is an operator/surface
action that binds a human approval phrase to the exact trade_proposal.json hash.
"""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


APPROVAL_PHRASE = "APPROVE PAPER EXECUTION"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, help="Vibe run directory containing artifacts/moirix/trade_proposal.json")
    parser.add_argument("--proposal", help="Optional proposal path. Defaults to <run-dir>/artifacts/moirix/trade_proposal.json")
    parser.add_argument("--out", help="Optional output path. Defaults to <run-dir>/artifacts/moirix/execution_approval.json")
    parser.add_argument("--approved-by", required=True, help="Operator/user id recorded in the approval artifact")
    parser.add_argument("--reason", required=True, help="Reason for paper execution approval")
    parser.add_argument("--phrase", required=True, help=f"Must equal {APPROVAL_PHRASE!r}")
    args = parser.parse_args()

    if args.phrase != APPROVAL_PHRASE:
        raise SystemExit(f"approval phrase mismatch; expected {APPROVAL_PHRASE!r}")

    run_dir = Path(args.run_dir).expanduser().resolve()
    moirix_dir = (run_dir / "artifacts" / "moirix").resolve()
    proposal = Path(args.proposal).expanduser().resolve() if args.proposal else moirix_dir / "trade_proposal.json"
    out = Path(args.out).expanduser().resolve() if args.out else moirix_dir / "execution_approval.json"

    if not proposal.is_file():
        raise SystemExit(f"proposal not found: {proposal}")
    if not _is_relative_to(proposal, run_dir):
        raise SystemExit("proposal must be under run-dir")
    if not _is_relative_to(out, run_dir):
        raise SystemExit("approval output must be under run-dir")

    proposal_bytes = proposal.read_bytes()
    payload = {
        "schema_version": "vibe.moirix_paper_execution_approval.v1",
        "approved": True,
        "scope": "paper",
        "approved_by": args.approved_by,
        "approved_at": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "reason": args.reason,
        "proposal_path": str(proposal),
        "proposal_sha256": hashlib.sha256(proposal_bytes).hexdigest(),
        "authority": {
            "paper_trade_proposal_allowed": True,
            "broker_submit_allowed": True,
            "ready_for_real_money_trading_authority": False,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": "ok", "approval_path": str(out), "proposal_sha256": payload["proposal_sha256"]}, ensure_ascii=False))
    return 0


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


if __name__ == "__main__":
    raise SystemExit(main())
