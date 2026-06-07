from __future__ import annotations

import json
import re
from collections.abc import Mapping
from pathlib import Path
from typing import Any


LOCAL_PATH_PATTERN = re.compile(
    r"(?<![A-Za-z])[A-Za-z]:[\\/]|\\\\|file://|local-artifact://|(?<![A-Za-z0-9_])/(Users|home|var|tmp|private|mnt)/",
    re.IGNORECASE,
)

FORBIDDEN_PUBLIC_KEYS = {
    "authorization",
    "token",
    "secret",
    "password",
    "api_key",
    "private_key",
    "client_secret",
    "storage_uri",
    "local_path",
    "file_path",
    "filesystem_path",
    "worker_path",
    "internal_path",
    "raw_command",
    "raw_shell",
    "ffmpeg_command",
    "internal_worker_url",
}


def write_json(path: str | Path, payload: Mapping[str, Any]) -> None:
    selected = Path(path)
    selected.parent.mkdir(parents=True, exist_ok=True)
    selected.write_text(json.dumps(public_safe(payload), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def caller_safe(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): caller_safe(item) for key, item in value.items()}
    if isinstance(value, list):
        return [caller_safe(item) for item in value]
    if isinstance(value, tuple):
        return [caller_safe(item) for item in value]
    if isinstance(value, str):
        return LOCAL_PATH_PATTERN.sub("[redacted-path]", value)
    return value


def public_safe(value: Any) -> Any:
    return strip_forbidden_public_keys(caller_safe(value))


def strip_forbidden_public_keys(value: Any) -> Any:
    if isinstance(value, Mapping):
        safe: dict[str, Any] = {}
        for key, item in value.items():
            key_string = str(key)
            if key_string.lower() in FORBIDDEN_PUBLIC_KEYS:
                continue
            safe[key_string] = strip_forbidden_public_keys(item)
        return safe
    if isinstance(value, list):
        return [strip_forbidden_public_keys(item) for item in value]
    if isinstance(value, tuple):
        return [strip_forbidden_public_keys(item) for item in value]
    return value


def safe_id(value: Any, *, default: str) -> str:
    if not isinstance(value, str):
        return default
    rendered = "".join(char if char.isalnum() or char in {"_", "-", "."} else "_" for char in value.strip())
    rendered = rendered.strip("._-")[:96]
    return rendered or default


def mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
