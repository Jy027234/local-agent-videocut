from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from smart_video_cut.external_handoff_compat import LEGACY_EXPORT_FILENAME


FOLDER_SCAN_SCHEMA = "smart_video_cut.local.folder_scan.v0"
VIDEO_EXTENSIONS = {".mp4", ".mov", ".mkv", ".webm", ".avi", ".m4v"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg"}
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
RESULT_FILENAMES = {"local_studio_result.json", "project_manifest.json", LEGACY_EXPORT_FILENAME}


def scan_media_folder(
    *,
    folder: str | Path,
    recursive: bool = True,
    limit: int = 200,
) -> dict[str, Any]:
    root = Path(folder)
    if not root.exists() or not root.is_dir():
        return _base_result(root, ok=False, reason="folder_not_found", items=[])
    files = _iter_files(root, recursive=recursive)
    items: list[dict[str, Any]] = []
    for path in files:
        category = _media_category(path)
        if not category:
            continue
        items.append(_file_item(path, root=root, category=category))
        if len(items) >= max(1, int(limit)):
            break
    return {
        **_base_result(root, ok=True, reason="scan_completed", items=items),
        "recursive": recursive,
        "category_counts": _category_counts(items),
        "recommended_input_videos": [
            item["path"] for item in items if item["category"] == "video"
        ][:20],
    }


def scan_output_folder(
    *,
    folder: str | Path,
    recursive: bool = True,
    limit: int = 200,
) -> dict[str, Any]:
    root = Path(folder)
    if not root.exists() or not root.is_dir():
        return _base_result(root, ok=False, reason="folder_not_found", items=[])
    files = _iter_files(root, recursive=recursive)
    items: list[dict[str, Any]] = []
    projects: list[dict[str, Any]] = []
    for path in files:
        if path.name not in RESULT_FILENAMES and _media_category(path) != "video":
            continue
        item = _file_item(path, root=root, category="result_json" if path.suffix.casefold() == ".json" else "video")
        if path.name == "project_manifest.json":
            project = _project_from_manifest(path)
            if project:
                projects.append(project)
        items.append(item)
        if len(items) >= max(1, int(limit)):
            break
    return {
        **_base_result(root, ok=True, reason="scan_completed", items=items),
        "recursive": recursive,
        "project_count": len(projects),
        "projects": projects,
        "category_counts": _category_counts(items),
    }


def _base_result(root: Path, *, ok: bool, reason: str, items: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema": FOLDER_SCAN_SCHEMA,
        "ok": ok,
        "reason": reason,
        "folder": str(root),
        "item_count": len(items),
        "items": items,
    }


def _iter_files(root: Path, *, recursive: bool) -> list[Path]:
    pattern = "**/*" if recursive else "*"
    try:
        return sorted(
            (item for item in root.glob(pattern) if item.is_file()),
            key=lambda item: item.stat().st_mtime,
            reverse=True,
        )
    except OSError:
        return []


def _media_category(path: Path) -> str:
    suffix = path.suffix.casefold()
    if suffix in VIDEO_EXTENSIONS:
        return "video"
    if suffix in AUDIO_EXTENSIONS:
        return "audio"
    if suffix in IMAGE_EXTENSIONS:
        return "image"
    return ""


def _file_item(path: Path, *, root: Path, category: str) -> dict[str, Any]:
    stat = path.stat()
    return {
        "name": path.name,
        "path": str(path),
        "relative_path": str(path.relative_to(root)) if _is_inside(path, root) else path.name,
        "category": category,
        "extension": path.suffix.casefold(),
        "size_bytes": stat.st_size,
        "modified_at": stat.st_mtime,
        "previewable": category in {"video", "audio", "image"},
    }


def _project_from_manifest(path: Path) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    style = payload.get("style_package") if isinstance(payload.get("style_package"), dict) else {}
    return {
        "project_id": str(payload.get("project_id") or path.parent.name),
        "output_dir": str(path.parent),
        "style_package_name": str(style.get("name") or ""),
        "input_video_count": int(payload.get("input_video_count") or 0),
        "copied_output_video": str(payload.get("copied_output_video") or ""),
        "updated_at": float(payload.get("updated_at") or path.stat().st_mtime),
        "manifest_path": str(path),
    }


def _category_counts(items: list[dict[str, Any]]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for item in items:
        category = str(item.get("category") or "unknown")
        counts[category] = counts.get(category, 0) + 1
    return counts


def _is_inside(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
