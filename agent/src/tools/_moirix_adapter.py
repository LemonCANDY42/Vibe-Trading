"""Shared helpers for the optional local Moirix adapter tools."""

from __future__ import annotations

import importlib.util
import hashlib
import json
import os
import re
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from src.tools.path_utils import safe_path, safe_run_dir, safe_user_path
from src.tools.redaction import redact_internal_paths

_CMD_ENV = "MOIRIX_ADAPTER_CMD"
_REPO_ENV = "MOIRIX_REPO_DIR"
_CWD_ENV = "MOIRIX_ADAPTER_CWD"
_CONDA_EXE_ENV = "MOIRIX_CONDA_EXE"
_CONDA_ENV = "MOIRIX_CONDA_ENV"
_DEFAULT_CONDA_ENV = "moirix"
_ARTIFACT_SUBDIR = "artifacts/moirix"
_AUTHORITY_CHECK_SUBDIR = "authority_checks"
_VALID_STATUSES = {"ok", "blocked", "unavailable"}
_FALSE_AUTHORITY_FIELDS = (
    "live_broker_execution_enabled",
    "real_order_authority",
    "trading_authority_claim",
    "ready_for_real_money_trading_authority",
    "broker_submit_supported",
)


@dataclass(frozen=True)
class AdapterCommand:
    """Resolved Moirix adapter invocation."""

    argv: list[str]
    cwd: Path | None
    source: str


def adapter_artifact_dir(run_dir: str) -> Path:
    """Return the safe Moirix artifact directory for the current Vibe run."""
    run_root = safe_run_dir(run_dir)
    out_dir = safe_path(_ARTIFACT_SUBDIR, run_root)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def adapter_authority_artifact_dir(run_dir: str, proposal_path: Path) -> Path:
    """Return a per-proposal authority-check artifact directory.

    Moirix adapter commands write common files such as ``status.json`` and
    ``coverage_status.json``. Authority checks are intentionally isolated from
    the main thesis/decision artifact directory so a blocked proposal cannot
    overwrite the run's primary Moirix thesis or decision status.
    """
    root = adapter_artifact_dir(run_dir)
    stem = _safe_artifact_segment(proposal_path.stem) or "proposal"
    digest = hashlib.sha256(str(proposal_path.resolve()).encode("utf-8")).hexdigest()[:8]
    out_dir = safe_path(f"{_AUTHORITY_CHECK_SUBDIR}/{stem}-{digest}", root)
    out_dir.mkdir(parents=True, exist_ok=True)
    return out_dir


def _safe_artifact_segment(value: str) -> str:
    segment = re.sub(r"[^a-zA-Z0-9_.-]+", "_", value.strip()).strip("._-").lower()
    return segment[:64]


def resolve_news_input(input_path: str | None, run_dir: str) -> tuple[Path | None, dict[str, Any] | None]:
    """Resolve a caller-provided graph input inside allowed Vibe roots."""
    run_root = safe_run_dir(run_dir)
    if not input_path:
        default_path = safe_path(f"{_ARTIFACT_SUBDIR}/news_evidence.jsonl", run_root)
        if default_path.exists():
            return default_path, None
        return None, _error_payload(
            "moirix_event_graph_input_missing",
            (
                "news_evidence.jsonl was not found under artifacts/moirix. "
                "Run moirix_query_news first or provide input_path from an allowed import root."
            ),
        )

    try:
        resolved = safe_path(input_path, run_root)
        if resolved.exists():
            return resolved, None
    except ValueError:
        resolved = None

    try:
        resolved = safe_user_path(input_path)
    except ValueError as exc:
        return None, _error_payload("moirix_event_graph_input_rejected", str(exc))

    if not resolved.exists():
        return None, _error_payload(
            "moirix_event_graph_input_missing",
            f"input_path {input_path!r} does not exist under allowed roots",
        )
    return resolved, None


def resolve_adapter_input(
    input_path: str | None,
    run_dir: str,
    *,
    default_relative: str | None = None,
    blocker_prefix: str = "moirix_adapter_input",
) -> tuple[Path | None, dict[str, Any] | None]:
    """Resolve an adapter input path inside the run or allowed import roots."""
    run_root = safe_run_dir(run_dir)
    if not input_path and default_relative:
        default_path = safe_path(default_relative, run_root)
        if default_path.exists():
            return default_path, None
        return None, _error_payload(
            f"{blocker_prefix}_missing",
            f"{default_relative} was not found under the current run directory.",
        )
    if not input_path:
        return None, _error_payload(f"{blocker_prefix}_missing", "input_path is required")

    try:
        resolved = safe_path(input_path, run_root)
        if resolved.exists():
            return resolved, None
    except ValueError:
        resolved = None

    try:
        resolved = safe_user_path(input_path)
    except ValueError as exc:
        return None, _error_payload(f"{blocker_prefix}_rejected", str(exc))

    if not resolved.exists():
        return None, _error_payload(
            f"{blocker_prefix}_missing",
            f"input_path {input_path!r} does not exist under allowed roots",
        )
    return resolved, None


def call_adapter(args: list[str], *, out_dir: Path | None = None, timeout_seconds: int = 120) -> dict[str, Any]:
    """Call the Moirix adapter and parse its JSON stdout."""
    command = _resolve_adapter_command()
    if command is None:
        return _unavailable_payload(
            "moirix_adapter_unavailable",
            (
                "Moirix adapter command was not found. Set MOIRIX_ADAPTER_CMD, "
                "install moirix_vibe_adapter, or set MOIRIX_REPO_DIR to a local Moirix checkout."
            ),
            out_dir=out_dir,
        )

    try:
        process = subprocess.run(
            [*command.argv, *args],
            cwd=str(command.cwd) if command.cwd else None,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout_seconds,
            env=_adapter_env(),
        )
    except subprocess.TimeoutExpired:
        return _unavailable_payload(
            "moirix_adapter_timeout",
            f"Moirix adapter timed out after {timeout_seconds}s",
            command=command,
            out_dir=out_dir,
        )
    except Exception as exc:  # noqa: BLE001 - return a clean tool envelope.
        return _unavailable_payload(
            "moirix_adapter_invocation_failed",
            redact_internal_paths(str(exc)),
            command=command,
            out_dir=out_dir,
        )

    if process.returncode != 0:
        return _unavailable_payload(
            "moirix_adapter_nonzero_exit",
            f"Moirix adapter exited with code {process.returncode}",
            command=command,
            out_dir=out_dir,
            extra={
                "exit_code": process.returncode,
                "stderr": redact_internal_paths(process.stderr[-2000:]),
            },
        )

    stdout = process.stdout.strip()
    try:
        payload = json.loads(stdout)
    except (json.JSONDecodeError, ValueError):
        return _unavailable_payload(
            "moirix_adapter_invalid_json",
            "Moirix adapter stdout was not a single JSON object",
            command=command,
            out_dir=out_dir,
            extra={"stdout_preview": stdout[:500]},
        )

    if not isinstance(payload, dict):
        return _unavailable_payload(
            "moirix_adapter_invalid_json_shape",
            "Moirix adapter stdout JSON was not an object",
            command=command,
            out_dir=out_dir,
        )

    violations = _authority_contract_violations(payload)
    if violations:
        return _blocked_payload(
            "moirix_authority_contract_violation",
            "Moirix adapter returned authority fields outside the V0 fail-closed contract",
            command=command,
            out_dir=out_dir,
            extra={"violations": violations, "moirix_payload": payload},
        )

    artifact_violations = _artifact_contract_violations(payload, out_dir)
    if artifact_violations:
        return _blocked_payload(
            "moirix_artifact_contract_violation",
            "Moirix adapter returned artifact paths outside the Vibe run artifact directory",
            command=command,
            out_dir=out_dir,
            extra={"violations": artifact_violations, "moirix_payload": payload},
        )

    status = str(payload.get("status") or "")
    if status not in _VALID_STATUSES:
        payload["status"] = "blocked"
        if not isinstance(payload.get("claim_gate"), dict):
            payload["claim_gate"] = {}
        blockers = payload["claim_gate"].get("blockers")
        if not isinstance(blockers, list):
            blockers = []
            payload["claim_gate"]["blockers"] = blockers
        blockers.append("moirix_adapter_unknown_status")

    payload["moirix_adapter"] = {
        "command_source": command.source,
        "cwd": str(command.cwd) if command.cwd else None,
        "artifacts_root": str(out_dir) if out_dir else None,
    }
    return payload


def _resolve_adapter_command() -> AdapterCommand | None:
    raw_cmd = os.getenv(_CMD_ENV, "").strip()
    repo_dir = _resolve_repo_dir()
    if raw_cmd:
        return AdapterCommand(
            argv=shlex.split(raw_cmd),
            cwd=_resolve_cwd(repo_dir),
            source=_CMD_ENV,
        )

    if importlib.util.find_spec("moirix_vibe_adapter") is not None:
        return AdapterCommand(
            argv=[sys.executable, "-m", "moirix_vibe_adapter"],
            cwd=repo_dir if repo_dir and repo_dir.exists() else None,
            source="python_module",
        )

    conda = _conda_executable()
    if repo_dir and repo_dir.exists() and conda:
        return AdapterCommand(
            argv=[
                str(conda),
                "run",
                "-n",
                os.getenv(_CONDA_ENV, _DEFAULT_CONDA_ENV),
                "python",
                "-m",
                "moirix_vibe_adapter",
            ],
            cwd=repo_dir,
            source="local_moirix_conda",
        )

    return None


def _resolve_repo_dir() -> Path | None:
    raw = os.getenv(_REPO_ENV, "").strip()
    if raw:
        return Path(raw).expanduser().resolve()

    repo_root = Path(__file__).resolve().parents[3]
    sibling = repo_root.parent / "Moirix"
    if sibling.exists():
        return sibling.resolve()
    return None


def _resolve_cwd(repo_dir: Path | None) -> Path | None:
    raw = os.getenv(_CWD_ENV, "").strip()
    if raw:
        return Path(raw).expanduser().resolve()
    if repo_dir and repo_dir.exists():
        return repo_dir
    return None


def _conda_executable() -> Path | None:
    candidates: list[Path] = []
    for raw in (
        os.getenv(_CONDA_EXE_ENV, "").strip(),
        str(Path.home() / "opt" / "miniconda3" / "bin" / "conda"),
        os.getenv("CONDA_EXE", "").strip(),
        shutil.which("conda") or "",
    ):
        if not raw:
            continue
        path = Path(raw).expanduser()
        if path.exists() and path.resolve() not in candidates:
            candidates.append(path.resolve())

    env_name = os.getenv(_CONDA_ENV, _DEFAULT_CONDA_ENV)
    for candidate in candidates:
        if _conda_env_exists(candidate, env_name):
            return candidate
    if candidates:
        return candidates[0]
    return None


def _conda_env_exists(conda: Path, env_name: str) -> bool:
    try:
        process = subprocess.run(
            [str(conda), "env", "list", "--json"],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            timeout=10,
        )
    except Exception:
        return False
    if process.returncode != 0:
        return False
    try:
        payload = json.loads(process.stdout)
    except (json.JSONDecodeError, ValueError):
        return False
    envs = payload.get("envs")
    if not isinstance(envs, list):
        return False
    return any(Path(str(item)).name == env_name for item in envs)


def _adapter_env() -> dict[str, str]:
    env = os.environ.copy()
    env.update(
        {
            "PYTHONUNBUFFERED": "1",
            "PYTHONIOENCODING": "utf-8",
            "PYTHONUTF8": "1",
        }
    )
    return env


def _authority_contract_violations(payload: dict[str, Any]) -> list[str]:
    violations = [field for field in _FALSE_AUTHORITY_FIELDS if payload.get(field) is True]
    authority = payload.get("authority")
    if not isinstance(authority, dict):
        return violations
    violations.extend(f"authority.{field}" for field in _FALSE_AUTHORITY_FIELDS if authority.get(field) is True)
    return violations


def _artifact_contract_violations(payload: dict[str, Any], out_dir: Path | None) -> list[str]:
    if out_dir is None:
        return []
    artifacts = payload.get("artifacts")
    if artifacts is None:
        return []
    if not isinstance(artifacts, dict):
        return ["artifacts_not_object"]

    base = out_dir.resolve()
    violations: list[str] = []
    for name, value in artifacts.items():
        if not isinstance(value, str) or not value.strip():
            violations.append(f"{name}:invalid_path")
            continue
        try:
            resolved = Path(value).expanduser().resolve()
            if not resolved.is_relative_to(base):
                violations.append(f"{name}:outside_artifacts_root")
        except OSError:
            violations.append(f"{name}:invalid_path")
    return violations


def _error_payload(blocker: str, message: str) -> dict[str, Any]:
    return {
        "status": "error",
        "error": message,
        "claim_gate": {"blockers": [blocker]},
    }


def _unavailable_payload(
    blocker: str,
    message: str,
    *,
    command: AdapterCommand | None = None,
    out_dir: Path | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "unavailable",
        "error": message,
        "claim_gate": {"blockers": [blocker]},
        "moirix_adapter": {
            "command_source": command.source if command else None,
            "cwd": str(command.cwd) if command and command.cwd else None,
            "artifacts_root": str(out_dir) if out_dir else None,
        },
    }
    if extra:
        payload.update(extra)
    return payload


def _blocked_payload(
    blocker: str,
    message: str,
    *,
    command: AdapterCommand,
    out_dir: Path | None = None,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "blocked",
        "error": message,
        "claim_gate": {"blockers": [blocker]},
        "moirix_adapter": {
            "command_source": command.source,
            "cwd": str(command.cwd) if command.cwd else None,
            "artifacts_root": str(out_dir) if out_dir else None,
        },
    }
    if extra:
        payload.update(extra)
    return payload
