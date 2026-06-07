from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any, Mapping

from smart_video_cut.version_history import get_version_history


PROJECT_MANIFEST_SCHEMA = "smart_video_cut.local.project_manifest.v0"
PROJECT_MANIFEST_FILENAME = "project_manifest.json"


def manifest_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / PROJECT_MANIFEST_FILENAME


def read_project_manifest(output_dir: str | Path) -> dict[str, Any] | None:
    path = manifest_path(output_dir)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def write_project_manifest(
    *,
    output_dir: str | Path,
    result: Mapping[str, Any] | None = None,
    timeline: Mapping[str, Any] | None = None,
    event: str = "updated",
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    previous = read_project_manifest(output_path) or {}
    history = get_version_history(output_path)
    result_data = dict(result or previous.get("latest_result") or {})
    timeline_data = dict(timeline or result_data.get("timeline_plan") or previous.get("latest_timeline") or {})
    style_package = _mapping(result_data.get("style_package") or previous.get("style_package"))
    input_videos = _input_videos(result_data, previous)

    manifest = {
        "schema": PROJECT_MANIFEST_SCHEMA,
        "project_id": str(result_data.get("project_id") or previous.get("project_id") or "local_project"),
        "output_dir": str(output_path),
        "updated_at": time.time(),
        "last_event": event,
        "style_package": {
            "name": style_package.get("name"),
            "path": style_package.get("path"),
            "package_id": style_package.get("package_id"),
        },
        "input_videos": input_videos,
        "input_video_count": len(input_videos),
        "latest_result_path": str(output_path / "local_studio_result.json")
        if (output_path / "local_studio_result.json").is_file()
        else str(previous.get("latest_result_path") or ""),
        "copied_output_video": result_data.get("copied_output_video") or previous.get("copied_output_video"),
        "execute_real_render": result_data.get("execute_real_render", previous.get("execute_real_render", False)) is True,
        "user_request": str(result_data.get("user_request") or previous.get("user_request") or ""),
        "latest_timeline": timeline_data,
        "latest_result": result_data,
        "version_history": {
            "current_version": history.get("current_version", 0),
            "version_count": len(history.get("versions") or []),
            "versions": history.get("versions") or [],
        },
    }
    manifest_path(output_path).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    try:
        from smart_video_cut.project_library import index_project_manifest

        index_project_manifest(output_dir=output_path, manifest=manifest)
    except Exception:
        # Project manifest writes are the source of truth; SQLite indexing is a convenience layer.
        pass
    return manifest


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _input_videos(result: Mapping[str, Any], previous: Mapping[str, Any]) -> list[str]:
    values = result.get("input_videos")
    if not values:
        values = previous.get("input_videos")
    if not values and result.get("input_video"):
        values = [result.get("input_video")]
    return [str(item) for item in values or [] if str(item or "").strip()]
