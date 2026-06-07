from __future__ import annotations

import json
import shutil
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


VERSION_HISTORY_SCHEMA = "smart_video_cut.local.version_history.v0"

VERSIONS_DIRNAME = "_versions"
HISTORY_FILENAME = "history.json"


@dataclass(slots=True)
class VersionEntry:
    version: int
    created_at: float
    timeline_path: str
    brief_path: str
    result_path: str
    user_feedback: str = ""
    edit_operations: list[dict[str, Any]] = field(default_factory=list)
    status: str = "completed"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class VersionHistory:
    output_dir: str
    schema: str = VERSION_HISTORY_SCHEMA
    current_version: int = 0
    versions: list[VersionEntry] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "output_dir": self.output_dir,
            "current_version": self.current_version,
            "versions": [v.to_dict() for v in self.versions],
        }


def _versions_root(output_dir: str | Path) -> Path:
    return Path(output_dir) / VERSIONS_DIRNAME


def _history_path(output_dir: str | Path) -> Path:
    return _versions_root(output_dir) / HISTORY_FILENAME


def _version_dir(output_dir: str | Path, version: int) -> Path:
    return _versions_root(output_dir) / f"v{version}"


def _load_history(output_dir: str | Path) -> VersionHistory:
    path = _history_path(output_dir)
    if not path.is_file():
        return VersionHistory(output_dir=str(output_dir))
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return VersionHistory(output_dir=str(output_dir))
    versions_data = data.get("versions") or []
    versions: list[VersionEntry] = []
    for v in versions_data:
        if isinstance(v, dict):
            versions.append(VersionEntry(
                version=int(v.get("version", 0)),
                created_at=float(v.get("created_at", 0.0)),
                timeline_path=str(v.get("timeline_path", "")),
                brief_path=str(v.get("brief_path", "")),
                result_path=str(v.get("result_path", "")),
                user_feedback=str(v.get("user_feedback", "")),
                edit_operations=v.get("edit_operations") or [],
                status=str(v.get("status", "completed")),
            ))
    return VersionHistory(
        output_dir=str(data.get("output_dir", str(output_dir))),
        schema=str(data.get("schema", VERSION_HISTORY_SCHEMA)),
        current_version=int(data.get("current_version", 0)),
        versions=versions,
    )


def _save_history(history: VersionHistory) -> None:
    path = _history_path(history.output_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(history.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _write_json_snapshot(directory: Path, filename: str, data: dict[str, Any] | None) -> str:
    if data is None:
        return ""
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / filename
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return str(path)


def save_version(
    *,
    output_dir: str | Path,
    timeline: dict[str, Any] | None = None,
    brief: dict[str, Any] | None = None,
    result: dict[str, Any] | None = None,
    user_feedback: str = "",
    edit_operations: list[dict[str, Any]] | None = None,
    status: str = "completed",
) -> VersionEntry:
    history = _load_history(output_dir)
    new_version = history.current_version + 1
    v_dir = _version_dir(output_dir, new_version)
    v_dir.mkdir(parents=True, exist_ok=True)

    timeline_path = _write_json_snapshot(v_dir, "timeline.json", timeline)
    brief_path = _write_json_snapshot(v_dir, "brief.json", brief)
    result_path = _write_json_snapshot(v_dir, "result.json", result)

    entry = VersionEntry(
        version=new_version,
        created_at=time.time(),
        timeline_path=timeline_path,
        brief_path=brief_path,
        result_path=result_path,
        user_feedback=user_feedback,
        edit_operations=edit_operations or [],
        status=status,
    )
    history.versions.append(entry)
    history.current_version = new_version
    _save_history(history)
    return entry


def get_version_history(output_dir: str | Path) -> dict[str, Any]:
    return _load_history(output_dir).to_dict()


def get_version(output_dir: str | Path, version: int) -> dict[str, Any] | None:
    history = _load_history(output_dir)
    for entry in history.versions:
        if entry.version == version:
            result = entry.to_dict()
            result["timeline"] = _read_json_file(entry.timeline_path)
            result["brief"] = _read_json_file(entry.brief_path)
            result["result"] = _read_json_file(entry.result_path)
            return result
    return None


def revert_to_version(output_dir: str | Path, version: int) -> dict[str, Any]:
    history = _load_history(output_dir)
    target = None
    for entry in history.versions:
        if entry.version == version:
            target = entry
            break
    if target is None:
        return {"ok": False, "error": f"version_{version}_not_found"}

    timeline = _read_json_file(target.timeline_path)
    brief = _read_json_file(target.brief_path)

    new_entry = save_version(
        output_dir=output_dir,
        timeline=timeline,
        brief=brief,
        result=None,
        user_feedback=f"reverted_from_v{history.current_version}_to_v{version}",
        edit_operations=[{"op": "revert", "source_version": version}],
        status="reverted",
    )
    return {
        "ok": True,
        "reverted_to_version": version,
        "new_version": new_entry.version,
        "timeline": timeline,
        "brief": brief,
    }


def _read_json_file(path: str) -> dict[str, Any] | None:
    if not path:
        return None
    p = Path(path)
    if not p.is_file():
        return None
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else None
    except (OSError, json.JSONDecodeError):
        return None
