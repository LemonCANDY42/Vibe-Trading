#!/usr/bin/env python3
"""Create an explicit Moirix paper-execution approval artifact.

This helper is intentionally not an Agent BaseTool. It is an operator/surface
action that binds a human approval phrase to the exact trade_proposal.json hash.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path


APPROVAL_PHRASE = "APPROVE PAPER EXECUTION"
APPROVAL_SCHEMA_VERSION = "vibe.paper_execution_approval.v2"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", required=True, help="Vibe run directory containing artifacts/moirix/trade_proposal.json")
    parser.add_argument("--proposal", help="Optional proposal path. Defaults to <run-dir>/artifacts/moirix/trade_proposal.json")
    parser.add_argument("--out", help="Optional output path. Defaults to <run-dir>/artifacts/moirix/execution_approval.json")
    parser.add_argument("--approved-by", required=True, help="Operator/user id recorded in the approval artifact")
    parser.add_argument("--reason", required=True, help="Reason for paper execution approval")
    parser.add_argument("--phrase", required=True, help=f"Must equal {APPROVAL_PHRASE!r}")
    parser.add_argument("--connection", required=True, help="Paper trading connector profile id approved for execution")
    parser.add_argument("--account", default="", help="Optional account code bound to this approval")
    parser.add_argument("--max-notional", type=float, required=True, help="Maximum approved notional exposure for this paper execution")
    parser.add_argument("--expires-minutes", type=int, default=30, help="Approval expiry in minutes from now")
    parser.add_argument(
        "--estimated-price",
        action="append",
        default=[],
        metavar="SYMBOL=PRICE",
        help="Estimated price used for market quantity orders. May be supplied multiple times.",
    )
    parser.add_argument("--approval-id", help="Optional approval id. Defaults to a fresh UUID-backed id.")
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
    proposal_payload = json.loads(proposal_bytes.decode("utf-8"))
    if not isinstance(proposal_payload, dict):
        raise SystemExit("proposal must be a JSON object")
    proposal_sha256 = hashlib.sha256(proposal_bytes).hexdigest()
    estimated_prices = _parse_estimated_prices(args.estimated_price)
    request = _canonical_request(
        connection=args.connection,
        account=args.account,
        proposal_sha256=proposal_sha256,
        orders=proposal_payload.get("orders") if isinstance(proposal_payload.get("orders"), list) else [],
    )
    now = datetime.now(timezone.utc).replace(microsecond=0)
    approval_id = args.approval_id or f"mpa_{uuid.uuid4().hex}"
    payload = {
        "schema_version": APPROVAL_SCHEMA_VERSION,
        "approval_id": approval_id,
        "approved": True,
        "scope": "paper",
        "execution_mode": "paper",
        "connection": args.connection,
        "account": args.account or "",
        "approved_by": args.approved_by,
        "approved_at": now.isoformat(),
        "expires_at": (now + timedelta(minutes=max(1, args.expires_minutes))).isoformat(),
        "reason": args.reason,
        "proposal_path": str(proposal),
        "proposal_sha256": proposal_sha256,
        "request": request,
        "request_sha256": _sha256_json(request),
        "max_notional": float(args.max_notional),
        "estimated_prices": estimated_prices,
        "authority": {
            "paper_trade_proposal_allowed": True,
            "broker_submit_allowed": True,
            "ready_for_real_money_trading_authority": False,
        },
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        json.dumps(
            {
                "status": "ok",
                "approval_path": str(out),
                "approval_id": approval_id,
                "proposal_sha256": proposal_sha256,
                "request_sha256": payload["request_sha256"],
                "expires_at": payload["expires_at"],
            },
            ensure_ascii=False,
        )
    )
    return 0


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
        return True
    except ValueError:
        return False


def _canonical_request(
    *,
    connection: str,
    account: str,
    proposal_sha256: str,
    orders: list[object],
) -> dict[str, object]:
    return {
        "operation": "moirix_execute_trade_proposal",
        "execution_mode": "paper",
        "connection": connection.strip(),
        "account": account.strip(),
        "actions": orders,
        "proposal_sha256": proposal_sha256,
    }


def _sha256_json(payload: object) -> str:
    data = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _parse_estimated_prices(values: list[str]) -> dict[str, float]:
    prices: dict[str, float] = {}
    for value in values:
        if "=" not in value:
            raise SystemExit(f"--estimated-price must use SYMBOL=PRICE, got {value!r}")
        symbol, price = value.split("=", 1)
        symbol = symbol.strip().upper()
        if not symbol:
            raise SystemExit("--estimated-price symbol cannot be blank")
        try:
            parsed = float(price)
        except ValueError as exc:
            raise SystemExit(f"--estimated-price price must be numeric, got {value!r}") from exc
        if parsed <= 0:
            raise SystemExit(f"--estimated-price price must be positive, got {value!r}")
        prices[symbol] = parsed
    return prices


if __name__ == "__main__":
    raise SystemExit(main())
