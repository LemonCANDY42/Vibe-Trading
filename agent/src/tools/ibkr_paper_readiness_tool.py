"""IBKR paper account read-only readiness artifact tool."""

from __future__ import annotations

import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from src.agent.tools import BaseTool
from src.tools.path_utils import safe_path, safe_run_dir
from src.trading import service
from src.trading.connectors.ibkr.local import tcp_port_open
from src.trading.profiles import profile_by_id

FORBIDDEN_IBKR_API_CALLS = (
    "placeOrder",
    "cancelOrder",
    "reqGlobalCancel",
)


class IBKRPaperReadinessTool(BaseTool):
    """Create a read-only IBKR paper readiness report."""

    name = "ibkr_paper_readiness"
    description = (
        "Check a local IBKR paper TWS/Gateway session using broker read APIs only "
        "and write artifacts/ibkr/ibkr_paper_readiness.json. This checks "
        "connectivity, account summary, positions, open orders/executions, quote "
        "permission, and historical-data permission. It never places, cancels, "
        "modifies, transmits, or globally cancels orders, and never grants "
        "real-money trading authority."
    )
    parameters = {
        "type": "object",
        "properties": {
            "connection": {
                "type": "string",
                "description": "IBKR local paper profile id. Defaults to ibkr-paper-local.",
                "default": "ibkr-paper-local",
            },
            "host": {
                "type": "string",
                "description": "Optional local TWS/Gateway host override.",
            },
            "port": {
                "type": "integer",
                "description": "Optional local TWS/Gateway port override. IB Gateway paper is usually 4002.",
            },
            "client_id": {
                "type": "integer",
                "description": "Optional local API client id. 0 is rejected to avoid binding manual orders.",
            },
            "account": {
                "type": "string",
                "description": "Optional IBKR paper account filter.",
            },
            "symbol": {
                "type": "string",
                "description": "Symbol used for market/historical data permission checks.",
                "default": "AAPL",
            },
            "exchange": {"type": "string", "default": "SMART"},
            "currency": {"type": "string", "default": "USD"},
            "sec_type": {"type": "string", "default": "STK"},
            "duration": {"type": "string", "default": "5 D"},
            "bar_size": {"type": "string", "default": "1 day"},
            "what_to_show": {"type": "string", "default": "TRADES"},
            "use_rth": {"type": "boolean", "default": True},
        },
        "required": [],
    }
    repeatable = True
    is_readonly = False

    def execute(self, **kwargs: Any) -> str:
        run_dir = kwargs.get("run_dir")
        if not run_dir:
            return json.dumps(
                {"status": "error", "error": "run_dir is required for ibkr_paper_readiness artifacts"},
                ensure_ascii=False,
            )

        try:
            out_dir = _artifact_dir(str(run_dir))
            payload = run_ibkr_paper_readiness(out_dir=out_dir, **kwargs)
        except ValueError as exc:
            return json.dumps({"status": "error", "error": str(exc)}, ensure_ascii=False)
        return json.dumps(_json_safe(payload), ensure_ascii=False, default=str, allow_nan=False)


def run_ibkr_paper_readiness(*, out_dir: Path, **kwargs: Any) -> dict[str, Any]:
    """Run broker-read-only IBKR paper checks and write the readiness artifact."""
    generated_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    blockers: list[str] = []
    checks: dict[str, Any] = {}
    artifact_path = out_dir / "ibkr_paper_readiness.json"

    try:
        connection, overrides, endpoint = _resolve_profile_and_overrides(kwargs)
    except ValueError as exc:
        blockers.append(str(exc))
        payload = _payload(
            generated_at=generated_at,
            status="blocked",
            connection=str(kwargs.get("connection") or "ibkr-paper-local"),
            endpoint={},
            checks=checks,
            blockers=blockers,
            artifact_path=artifact_path,
        )
        _write_artifact(artifact_path, payload)
        return payload

    common = dict(overrides)
    symbol = str(kwargs.get("symbol") or "AAPL").strip().upper()
    exchange = str(kwargs.get("exchange") or "SMART").strip() or "SMART"
    currency = str(kwargs.get("currency") or "USD").strip().upper() or "USD"
    sec_type = str(kwargs.get("sec_type") or "STK").strip().upper() or "STK"
    duration = str(kwargs.get("duration") or "5 D").strip() or "5 D"
    bar_size = str(kwargs.get("bar_size") or "1 day").strip() or "1 day"
    what_to_show = str(kwargs.get("what_to_show") or "TRADES").strip() or "TRADES"
    use_rth = bool(kwargs.get("use_rth", True))

    checks["connectivity"] = _run_check(
        lambda: service.check_connection(connection, **common),
        unavailable_blocker="ibkr_paper_connectivity_unavailable",
        blocked_blocker="ibkr_paper_connectivity_blocked",
        blockers=blockers,
    )
    if checks["connectivity"]["status"] == "ok":
        checks["account_summary"] = _run_check(
            lambda: service.get_account(connection, **common),
            unavailable_blocker="ibkr_paper_account_summary_unavailable",
            blocked_blocker="ibkr_paper_account_summary_blocked",
            blockers=blockers,
        )
        checks["positions"] = _run_check(
            lambda: service.get_positions(connection, **common),
            unavailable_blocker="ibkr_paper_positions_unavailable",
            blocked_blocker="ibkr_paper_positions_blocked",
            blockers=blockers,
        )
        checks["open_orders_and_executions"] = _run_check(
            lambda: service.get_open_orders(connection, include_executions=True, **common),
            unavailable_blocker="ibkr_paper_orders_executions_unavailable",
            blocked_blocker="ibkr_paper_orders_executions_blocked",
            blockers=blockers,
        )
        checks["market_data_permission"] = _run_check(
            lambda: service.get_quote(
                symbol,
                connection,
                exchange=exchange,
                currency=currency,
                sec_type=sec_type,
                **common,
            ),
            unavailable_blocker="ibkr_paper_market_data_unavailable",
            blocked_blocker="ibkr_paper_market_data_blocked",
            blockers=blockers,
            validator=_validate_quote_snapshot,
        )
        checks["historical_data_permission"] = _run_check(
            lambda: service.get_history(
                symbol,
                connection,
                exchange=exchange,
                currency=currency,
                sec_type=sec_type,
                duration=duration,
                bar_size=bar_size,
                what_to_show=what_to_show,
                use_rth=use_rth,
                **common,
            ),
            unavailable_blocker="ibkr_paper_historical_data_unavailable",
            blocked_blocker="ibkr_paper_historical_data_blocked",
            blockers=blockers,
            validator=_validate_historical_bars,
        )

    status = "ok" if not blockers else _status_from_blockers(blockers)
    payload = _payload(
        generated_at=generated_at,
        status=status,
        connection=connection,
        endpoint=endpoint,
        checks=checks,
        blockers=blockers,
        artifact_path=artifact_path,
    )
    _write_artifact(artifact_path, payload)
    return payload


def _resolve_profile_and_overrides(kwargs: dict[str, Any]) -> tuple[str, dict[str, Any], dict[str, Any]]:
    connection = _clean_str(kwargs.get("connection")) or "ibkr-paper-local"
    profile = profile_by_id(connection)
    if profile.connector != "ibkr" or profile.transport != "local_tws" or profile.environment != "paper":
        raise ValueError("ibkr_paper_readiness_requires_ibkr_paper_local_profile")

    host = _clean_str(kwargs.get("host")) or str(profile.config.get("host") or "127.0.0.1")
    configured_port = int(profile.config.get("port") or 7497)
    requested_port = _int_or_none(kwargs.get("port"))
    port = requested_port or _select_paper_port(host, configured_port)
    client_id = _int_or_none(kwargs.get("client_id"))
    if client_id is None:
        client_id = int(profile.config.get("client_id") or 77)
    if client_id == 0:
        raise ValueError("ibkr_client_id_zero_rejected")
    account = _clean_str(kwargs.get("account"))
    auto_selected = requested_port is None and port != configured_port
    endpoint = {
        "host": host,
        "port": port,
        "profile_default_port": configured_port,
        "auto_selected_gateway_paper_port": auto_selected,
        "client_id": client_id,
        "account_filter": account,
    }
    return connection, {"host": host, "port": port, "client_id": client_id, "account": account}, endpoint


def _select_paper_port(host: str, configured_port: int) -> int:
    if tcp_port_open(host, configured_port):
        return configured_port
    gateway_paper_port = 4002
    if configured_port != gateway_paper_port and tcp_port_open(host, gateway_paper_port):
        return gateway_paper_port
    return configured_port


def _artifact_dir(run_dir: str) -> Path:
    run_root = safe_run_dir(run_dir)
    out_dir = safe_path("artifacts/ibkr", run_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _run_check(
    fn: Callable[[], dict[str, Any]],
    *,
    unavailable_blocker: str,
    blocked_blocker: str,
    blockers: list[str],
    validator: Callable[[dict[str, Any]], str | None] | None = None,
) -> dict[str, Any]:
    try:
        result = fn()
    except Exception as exc:  # noqa: BLE001 - readiness must fail closed.
        blocker = unavailable_blocker if _looks_unavailable(str(exc)) else blocked_blocker
        blockers.append(blocker)
        return {"status": "unavailable" if blocker == unavailable_blocker else "blocked", "error": str(exc)}

    status = str(result.get("status") or "").lower()
    if status == "ok":
        if validator is not None:
            validation_error = validator(result)
            if validation_error:
                blockers.append(blocked_blocker)
                return {"status": "blocked", "error": validation_error, "payload": _json_safe(result)}
        return {"status": "ok", "payload": _json_safe(result)}
    error = str(result.get("error") or result)
    blocker = unavailable_blocker if _looks_unavailable(error, result) else blocked_blocker
    blockers.append(blocker)
    return {"status": "unavailable" if blocker == unavailable_blocker else "blocked", "payload": _json_safe(result)}


def _validate_quote_snapshot(result: dict[str, Any]) -> str | None:
    quote = result.get("quote")
    if not isinstance(quote, dict):
        return "IBKR quote payload did not include a quote object."
    observable_fields = ("bid", "ask", "last", "close")
    if any(_is_finite_number(quote.get(field)) for field in observable_fields):
        return None
    return "IBKR market-data check returned no finite bid/ask/last/close snapshot."


def _validate_historical_bars(result: dict[str, Any]) -> str | None:
    bars = result.get("bars")
    if not isinstance(bars, list) or not bars:
        return "IBKR historical-data check returned no bars."
    if any(isinstance(bar, dict) and _is_finite_number(bar.get("close")) for bar in bars):
        return None
    return "IBKR historical-data check returned no finite close values."


def _looks_unavailable(error: str, payload: dict[str, Any] | None = None) -> bool:
    lowered = error.lower()
    if payload and payload.get("sdk", {}).get("installed") is False:
        return True
    return any(
        token in lowered
        for token in (
            "not installed",
            "no tws / ib gateway socket",
            "could not connect",
            "connection refused",
            "not listening",
            "timed out",
        )
    )


def _payload(
    *,
    generated_at: str,
    status: str,
    connection: str,
    endpoint: dict[str, Any],
    checks: dict[str, Any],
    blockers: list[str],
    artifact_path: Path,
) -> dict[str, Any]:
    return {
        "schema_version": "vibe.ibkr_paper_readiness.v1",
        "status": status,
        "generated_at": generated_at,
        "connection": connection,
        "endpoint": endpoint,
        "checks": checks,
        "read_only_contract": {
            "broker_api_readonly": True,
            "client_readonly_connect_requested": True,
            "no_order_api_calls": True,
            "forbidden_api_calls": list(FORBIDDEN_IBKR_API_CALLS),
            "local_artifact_write_only": True,
            "ready_for_trading_authority": False,
            "ready_for_real_money_trading_authority": False,
        },
        "authority": {
            "scope": "paper_readiness_read_only",
            "broker_submit_supported": False,
            "live_broker_execution_enabled": False,
            "real_order_authority": False,
            "trading_authority_claim": False,
            "ready_for_real_money_trading_authority": False,
            "blockers": blockers,
        },
        "claim_gate": {
            "ready_for_ibkr_paper_readiness": status == "ok",
            "ready_for_trading_authority": False,
            "ready_for_real_money_trading_authority": False,
            "blockers": blockers,
        },
        "artifacts": {"ibkr_paper_readiness": str(artifact_path)},
    }


def _write_artifact(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    safe_payload = _json_safe(payload)
    path.write_text(
        json.dumps(safe_payload, ensure_ascii=False, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def _status_from_blockers(blockers: list[str]) -> str:
    if any(item.endswith("_unavailable") for item in blockers):
        return "unavailable"
    return "blocked"


def _clean_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _int_or_none(value: Any) -> int | None:
    if value in (None, ""):
        return None
    return int(value)


def _is_finite_number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(float(value))


def _json_safe(value: Any) -> Any:
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(item) for item in value]
    return value
