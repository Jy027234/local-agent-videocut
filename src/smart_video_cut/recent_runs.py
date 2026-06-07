from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from smart_video_cut.project_manifest import read_project_manifest


ROOT_DIR = Path(__file__).resolve().parents[2]
OUTPUT_ROOT = ROOT_DIR / "workspace" / "output"


def list_recent_runs(limit: int = 20) -> dict[str, Any]:
    if not OUTPUT_ROOT.exists():
        return {"schema": "smart_video_cut.local.recent_runs.v0", "runs": []}
    result_files = sorted(
        OUTPUT_ROOT.rglob("local_studio_result.json"),
        key=lambda path: path.stat().st_mtime,
        reverse=True,
    )
    runs: list[dict[str, Any]] = []
    for result_file in result_files[: max(1, int(limit))]:
        try:
            payload = json.loads(result_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        style_package = payload.get("style_package") if isinstance(payload.get("style_package"), dict) else {}
        toolkit_summary = (
            payload.get("toolkit_summary") if isinstance(payload.get("toolkit_summary"), dict) else {}
        )
        project_manifest = read_project_manifest(result_file.parent) or {}
        manifest_versions = (
            project_manifest.get("version_history")
            if isinstance(project_manifest.get("version_history"), dict)
            else {}
        )
        runs.append(
            {
                "ok": payload.get("ok") is True,
                "result_json": str(result_file),
                "output_dir": str(result_file.parent),
                "project_manifest_path": str(result_file.parent / "project_manifest.json")
                if project_manifest
                else "",
                "project_manifest": project_manifest,
                "current_version": manifest_versions.get("current_version") or payload.get("current_version") or 0,
                "version_count": manifest_versions.get("version_count") or 0,
                "input_video": payload.get("input_video"),
                "input_videos": payload.get("input_videos") or [],
                "input_video_count": payload.get("input_video_count") or 1,
                "style_package_path": style_package.get("path"),
                "style_package_name": style_package.get("name"),
                "copied_output_video": payload.get("copied_output_video"),
                "execute_real_render": payload.get("execute_real_render") is True,
                "voice_provider": payload.get("voice_provider"),
                "user_request": payload.get("user_request") or "",
                "confirmed_brief": payload.get("confirmed_brief") or "",
                "timeline_plan": payload.get("timeline_plan") if isinstance(payload.get("timeline_plan"), dict) else {},
                "settings_overrides": payload.get("settings_overrides") or {},
                "workflow_kind": toolkit_summary.get("workflow_kind"),
                "modified_at": result_file.stat().st_mtime,
            }
        )
    return {"schema": "smart_video_cut.local.recent_runs.v0", "runs": runs}


def delete_recent_run(*, result_json: str) -> dict[str, Any]:
    result_path = Path(result_json).resolve()
    output_root = OUTPUT_ROOT.resolve()
    if not _is_inside(result_path, output_root):
        return {"ok": False, "reason": "result_json_outside_output_root"}
    if result_path.name != "local_studio_result.json" or not result_path.is_file():
        return {"ok": False, "reason": "result_json_not_found"}
    output_dir = result_path.parent.resolve()
    if not _is_inside(output_dir, output_root):
        return {"ok": False, "reason": "output_dir_outside_output_root"}
    shutil.rmtree(output_dir)
    return {"ok": True, "deleted_output_dir": str(output_dir)}


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
