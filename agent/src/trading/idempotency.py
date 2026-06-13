"""Persistent idempotency guard for Agent-facing trading operations."""

from __future__ import annotations

import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from src.config.paths import get_runtime_root

SCHEMA_VERSION = "vibe.trading_idempotency.v1"
_SAFE_KEY = re.compile(r"[^A-Za-z0-9_.:-]+")


def run_once(
    *,
    tool_name: str,
    request: dict[str, Any],
    idempotency_key: str | None,
    execute: Callable[[], dict[str, Any]],
) -> dict[str, Any]:
    """Execute a mutating operation once and replay duplicate attempts.

    Args:
        tool_name: Agent tool name.
        request: Canonical request payload for duplicate detection.
        idempotency_key: Optional caller-supplied key. If omitted, a stable key
            is derived from ``tool_name`` and ``request``.
        execute: Side-effecting operation to run only on first claim.

    Returns:
        The operation response, augmented with an ``idempotency`` envelope.
    """
    normalized_request = _jsonable(request)
    request_hash = _hash_payload({"tool": tool_name, "request": normalized_request})
    key = _normalize_key(idempotency_key) if idempotency_key else request_hash[:32]
    path = _record_path(tool_name, key)
    claimed = _claim(path, tool_name=tool_name, key=key, request_hash=request_hash, request=normalized_request)
    if claimed is not None:
        return claimed

    try:
        response = execute()
    except Exception as exc:  # noqa: BLE001 - broker tools should return envelopes
        response = {"status": "error", "error": str(exc)}

    record = {
        "schema_version": SCHEMA_VERSION,
        "tool": tool_name,
        "idempotency_key": key,
        "request_hash": request_hash,
        "request": normalized_request,
        "status": "completed",
        "response": _jsonable(response),
        "created_at": _utc_now(),
        "completed_at": _utc_now(),
    }
    _atomic_write(path, record)
    return _with_idempotency(response, status="recorded", key=key, request_hash=request_hash, path=path)


def idempotency_schema_property() -> dict[str, Any]:
    """Return the JSON-schema property shared by mutating trading tools."""
    return {
        "type": "string",
        "description": (
            "Optional idempotency key. Reusing the same key with the same request "
            "replays the first result; reusing it with a different request is blocked."
        ),
    }


def _claim(
    path: Path,
    *,
    tool_name: str,
    key: str,
    request_hash: str,
    request: dict[str, Any],
) -> dict[str, Any] | None:
    path.parent.mkdir(parents=True, exist_ok=True)
    initial = {
        "schema_version": SCHEMA_VERSION,
        "tool": tool_name,
        "idempotency_key": key,
        "request_hash": request_hash,
        "request": request,
        "status": "in_progress",
        "created_at": _utc_now(),
    }
    try:
        fd = os.open(str(path), os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    except FileExistsError:
        return _existing(path, key=key, request_hash=request_hash)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        json.dump(initial, handle, ensure_ascii=False, sort_keys=True)
        handle.write("\n")
    return None


def _existing(path: Path, *, key: str, request_hash: str) -> dict[str, Any]:
    try:
        record = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return _blocked("idempotency_record_unreadable", key=key, request_hash=request_hash, path=path, error=str(exc))
    if str(record.get("request_hash") or "") != request_hash:
        return _blocked("idempotency_key_reused_with_different_request", key=key, request_hash=request_hash, path=path)
    if record.get("status") != "completed" or not isinstance(record.get("response"), dict):
        return _blocked("idempotency_request_in_progress_or_unresolved", key=key, request_hash=request_hash, path=path)
    return _with_idempotency(dict(record["response"]), status="replayed", key=key, request_hash=request_hash, path=path)


def _blocked(blocker: str, *, key: str, request_hash: str, path: Path, error: str | None = None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "blocked",
        "claim_gate": {"blockers": [blocker]},
    }
    if error:
        payload["error"] = error
    return _with_idempotency(payload, status="blocked", key=key, request_hash=request_hash, path=path)


def _with_idempotency(
    payload: dict[str, Any],
    *,
    status: str,
    key: str,
    request_hash: str,
    path: Path,
) -> dict[str, Any]:
    result = dict(payload)
    result["idempotency"] = {
        "status": status,
        "key": key,
        "request_hash": request_hash,
        "path": str(path),
    }
    return result


def _record_path(tool_name: str, key: str) -> Path:
    safe_tool = _normalize_key(tool_name)
    safe_key = _normalize_key(key)
    return get_runtime_root() / "trading" / "idempotency" / safe_tool / f"{safe_key}.json"


def _normalize_key(value: str) -> str:
    text = _SAFE_KEY.sub("_", str(value).strip())
    if not text:
        text = "empty"
    if len(text) <= 96:
        return text
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return f"{text[:48]}-{digest[:24]}"


def _hash_payload(payload: Any) -> str:
    data = json.dumps(_jsonable(payload), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(data.encode("utf-8")).hexdigest()


def _jsonable(value: Any) -> Any:
    try:
        json.dumps(value)
        return value
    except TypeError:
        if isinstance(value, dict):
            return {str(k): _jsonable(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [_jsonable(item) for item in value]
        return str(value)


def _atomic_write(path: Path, payload: dict[str, Any]) -> None:
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")
    try:
        tmp.chmod(0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
