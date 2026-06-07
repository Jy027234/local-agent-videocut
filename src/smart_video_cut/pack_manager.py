from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from smart_video_cut.edit_settings import apply_visible_settings_overrides
from smart_video_cut.models import (
    MATERIAL_PACK_SCHEMA,
    PROJECT_PACK_SCHEMA,
    STYLE_PACK_SCHEMA,
    STYLE_PACKAGE_SCHEMA,
    LocalVisibleSettings,
    MaterialPack,
    ProjectPack,
    StylePack,
)
from smart_video_cut.project_manifest import read_project_manifest
from smart_video_cut.version_history import get_version_history


PACK_FILENAME_MAP: dict[str, str] = {
    MATERIAL_PACK_SCHEMA: "material_pack.json",
    STYLE_PACK_SCHEMA: "style_pack.json",
    PROJECT_PACK_SCHEMA: "project_pack.json",
}

ALL_PACK_SCHEMAS = {MATERIAL_PACK_SCHEMA, STYLE_PACK_SCHEMA, PROJECT_PACK_SCHEMA, STYLE_PACKAGE_SCHEMA}


def create_material_pack(
    *,
    name: str,
    package_dir: str | Path,
    reference_video_path: str = "",
    description: str = "",
    thumbnail_paths: list[str] | None = None,
) -> dict[str, Any]:
    pack = MaterialPack(
        name=name,
        reference_video_path=reference_video_path,
        thumbnail_paths=thumbnail_paths or [],
        description=description,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    return _write_pack(Path(package_dir), "material_pack.json", pack.to_dict())


def create_style_pack(
    *,
    name: str,
    package_dir: str | Path,
    visible_settings: dict[str, Any] | None = None,
    timeline_template: dict[str, Any] | None = None,
    edit_brief_profile: dict[str, Any] | None = None,
    render_overrides: dict[str, Any] | None = None,
    description: str = "",
) -> dict[str, Any]:
    pack = StylePack(
        name=name,
        visible_settings=_normalize_visible_settings(visible_settings),
        timeline_template=timeline_template or {},
        edit_brief_profile=edit_brief_profile or {},
        render_overrides=render_overrides or {},
        description=description,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    return _write_pack(Path(package_dir), "style_pack.json", pack.to_dict())


def create_project_pack(
    *,
    name: str,
    package_dir: str | Path,
    material_pack_ref: str = "",
    style_pack_ref: str = "",
    input_videos: list[str] | None = None,
    output_dir: str = "",
    project_settings_overrides: dict[str, Any] | None = None,
    source_output_dir: str = "",
    project_manifest: dict[str, Any] | None = None,
    timeline_plan: dict[str, Any] | None = None,
    version_history: dict[str, Any] | None = None,
    artifact_refs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    pack = ProjectPack(
        name=name,
        material_pack_ref=material_pack_ref,
        style_pack_ref=style_pack_ref,
        input_videos=input_videos or [],
        output_dir=output_dir,
        project_settings_overrides=project_settings_overrides or {},
        source_output_dir=source_output_dir,
        project_manifest=project_manifest or {},
        timeline_plan=timeline_plan or {},
        version_history=version_history or {},
        artifact_refs=artifact_refs or {},
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    return _write_pack(Path(package_dir), "project_pack.json", pack.to_dict())


def export_project_pack_from_output(
    *,
    output_dir: str | Path,
    package_dir: str | Path,
    name: str = "",
    material_pack_ref: str = "",
    style_pack_ref: str = "",
    project_settings_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    manifest = read_project_manifest(output_path) or {}
    result = _read_json(output_path / "local_studio_result.json") or {}
    version_history = get_version_history(output_path)
    style_package = manifest.get("style_package") if isinstance(manifest.get("style_package"), dict) else {}
    if not style_pack_ref:
        style_pack_ref = str(style_package.get("path") or "")
    input_videos = manifest.get("input_videos") or result.get("input_videos") or []
    timeline = manifest.get("latest_timeline") if isinstance(manifest.get("latest_timeline"), dict) else {}
    if not timeline and isinstance(result.get("timeline_plan"), dict):
        timeline = result["timeline_plan"]
    copied_output = str(manifest.get("copied_output_video") or result.get("copied_output_video") or "")
    artifact_refs = {
        "local_studio_result": str(output_path / "local_studio_result.json")
        if (output_path / "local_studio_result.json").is_file()
        else "",
        "project_manifest": str(output_path / "project_manifest.json")
        if (output_path / "project_manifest.json").is_file()
        else "",
        "copied_output_video": copied_output,
        "version_history_dir": str(output_path / "_versions")
        if (output_path / "_versions").is_dir()
        else "",
    }
    pack_name = name or str(style_package.get("name") or output_path.name or "Local Project")
    return create_project_pack(
        name=pack_name,
        package_dir=package_dir,
        material_pack_ref=material_pack_ref,
        style_pack_ref=style_pack_ref,
        input_videos=[str(item) for item in input_videos if str(item or "").strip()],
        output_dir=str(output_path),
        project_settings_overrides=project_settings_overrides or result.get("settings_overrides") or {},
        source_output_dir=str(output_path),
        project_manifest=manifest,
        timeline_plan=timeline,
        version_history=version_history,
        artifact_refs=artifact_refs,
    )


def load_pack(path: str | Path) -> dict[str, Any]:
    selected = Path(path)
    if selected.is_dir():
        for filename in ("style_pack.json", "material_pack.json", "project_pack.json", "style_package.json"):
            candidate = selected / filename
            if candidate.is_file():
                selected = candidate
                break
    if not selected.is_file():
        raise ValueError(f"pack file not found: {path}")
    data = json.loads(selected.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("pack JSON must contain an object")
    schema = str(data.get("schema", ""))
    if schema not in ALL_PACK_SCHEMAS:
        raise ValueError(f"unknown pack schema: {schema}")
    return data


def resolve_project_pack(project_pack: dict[str, Any]) -> dict[str, Any]:
    """Resolve a project pack into a merged configuration dict.

    Returns a dict with keys: material, style, settings, input_videos, output_dir.
    Falls back gracefully when refs are missing.
    """
    material: dict[str, Any] = {}
    style: dict[str, Any] = {}
    settings: dict[str, Any] = {}

    mat_ref = str(project_pack.get("material_pack_ref", "")).strip()
    if mat_ref:
        try:
            material = load_pack(mat_ref)
        except (ValueError, OSError, json.JSONDecodeError):
            pass

    style_ref = str(project_pack.get("style_pack_ref", "")).strip()
    if style_ref:
        try:
            loaded = load_pack(style_ref)
            style = loaded
            settings, _, _ = resolve_effective_settings(loaded)
        except (ValueError, OSError, json.JSONDecodeError):
            pass

    overrides = project_pack.get("project_settings_overrides")
    if isinstance(overrides, dict) and overrides:
        _deep_merge(settings, overrides)

    validation = validate_pack_references(project_pack)
    return {
        "material": material,
        "style": style,
        "settings": settings,
        "input_videos": project_pack.get("input_videos") or [],
        "output_dir": str(project_pack.get("output_dir", "")),
        "source_output_dir": str(project_pack.get("source_output_dir", "")),
        "project_manifest": project_pack.get("project_manifest") if isinstance(project_pack.get("project_manifest"), dict) else {},
        "timeline_plan": project_pack.get("timeline_plan") if isinstance(project_pack.get("timeline_plan"), dict) else {},
        "version_history": project_pack.get("version_history") if isinstance(project_pack.get("version_history"), dict) else {},
        "artifact_refs": project_pack.get("artifact_refs") if isinstance(project_pack.get("artifact_refs"), dict) else {},
        "validation": validation,
    }


def validate_pack_references(pack: dict[str, Any]) -> dict[str, Any]:
    """Validate pack references without mutating or loading heavy media."""
    schema = str(pack.get("schema", ""))
    warnings: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    if schema not in ALL_PACK_SCHEMAS:
        errors.append({
            "code": "unknown_pack_schema",
            "message": f"未知包 schema：{schema or 'empty'}",
            "path": "",
        })
        return {"ok": False, "schema": schema, "warnings": warnings, "errors": errors}

    if schema == MATERIAL_PACK_SCHEMA:
        _warn_missing_path(
            warnings,
            "reference_video_missing",
            "素材包 reference_video_path 不存在",
            pack.get("reference_video_path"),
        )
        for path in pack.get("thumbnail_paths") or []:
            _warn_missing_path(warnings, "thumbnail_missing", "素材包缩略图不存在", path)

    elif schema == PROJECT_PACK_SCHEMA:
        _warn_missing_path(warnings, "material_pack_ref_missing", "项目包素材包引用不存在", pack.get("material_pack_ref"))
        _warn_missing_path(warnings, "style_pack_ref_missing", "项目包风格包引用不存在", pack.get("style_pack_ref"))
        for path in pack.get("input_videos") or []:
            _warn_missing_path(warnings, "input_video_missing", "项目包输入素材不存在", path)
        _warn_missing_path(warnings, "output_dir_missing", "项目包输出目录不存在", pack.get("output_dir"))
        _warn_missing_path(warnings, "source_output_dir_missing", "项目包来源输出目录不存在", pack.get("source_output_dir"))
        artifact_refs = pack.get("artifact_refs") if isinstance(pack.get("artifact_refs"), dict) else {}
        for key, value in artifact_refs.items():
            if value:
                _warn_missing_path(warnings, f"artifact_{key}_missing", f"项目包 artifact_refs.{key} 不存在", value)
        timeline = pack.get("timeline_plan") if isinstance(pack.get("timeline_plan"), dict) else {}
        if not timeline.get("segments"):
            warnings.append({
                "code": "timeline_plan_empty",
                "message": "项目包未包含可复用的时间线片段",
                "path": "",
            })
        version_history = pack.get("version_history") if isinstance(pack.get("version_history"), dict) else {}
        if not version_history.get("versions"):
            warnings.append({
                "code": "version_history_empty",
                "message": "项目包未包含版本历史明细",
                "path": "",
            })
        manifest = pack.get("project_manifest") if isinstance(pack.get("project_manifest"), dict) else {}
        if not manifest:
            warnings.append({
                "code": "project_manifest_missing",
                "message": "项目包未包含 project_manifest 快照",
                "path": "",
            })

    return {
        "ok": not errors,
        "schema": schema,
        "warnings": warnings,
        "errors": errors,
    }


def resolve_effective_settings(
    style_package: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
    """Return (visible_settings, timeline_template, edit_brief_profile).

    Compatible with both v0 style_package and v1 style_pack schemas.
    """
    schema = str(style_package.get("schema", ""))
    if schema == STYLE_PACK_SCHEMA:
        return (
            style_package.get("visible_settings", {}),
            style_package.get("timeline_template", {}),
            style_package.get("edit_brief_profile", {}),
        )
    # v0 compatibility
    return (
        style_package.get("visible_settings", {}),
        style_package.get("timeline_template", {}),
        style_package.get("edit_brief", {}),
    )


def discover_packs(base_dir: str | Path | None = None) -> dict[str, list[dict[str, Any]]]:
    """Discover all packs under base_dir, grouped by type."""
    root = Path(base_dir) if base_dir else Path(__file__).resolve().parents[2] / "packages"
    result: dict[str, list[dict[str, Any]]] = {
        "material_packs": [],
        "style_packs": [],
        "project_packs": [],
        "legacy_style_packages": [],
    }
    if not root.exists():
        return result

    for json_file in sorted(root.rglob("*.json")):
        try:
            data = json.loads(json_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if not isinstance(data, dict):
            continue
        schema = str(data.get("schema", ""))
        entry = {
            "name": data.get("name", json_file.parent.name),
            "schema": schema,
            "path": str(json_file.parent),
            "json_path": str(json_file),
            "description": data.get("description", ""),
            "created_at": data.get("created_at"),
            "validation": validate_pack_references(data),
        }
        if schema == MATERIAL_PACK_SCHEMA:
            result["material_packs"].append(entry)
        elif schema == STYLE_PACK_SCHEMA:
            result["style_packs"].append(entry)
        elif schema == PROJECT_PACK_SCHEMA:
            result["project_packs"].append(entry)
        elif schema == STYLE_PACKAGE_SCHEMA:
            result["legacy_style_packages"].append(entry)

    return result


def _write_pack(package_dir: Path, filename: str, payload: dict[str, Any]) -> dict[str, Any]:
    package_dir.mkdir(parents=True, exist_ok=True)
    path = package_dir / filename
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return payload


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def _deep_merge(base: dict[str, Any], overrides: dict[str, Any]) -> None:
    """Merge overrides into base in-place."""
    for key, value in overrides.items():
        if key in base and isinstance(base[key], dict) and isinstance(value, dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


def _normalize_visible_settings(visible_settings: dict[str, Any] | None) -> dict[str, Any]:
    defaults = LocalVisibleSettings().to_dict()
    if not isinstance(visible_settings, dict):
        return defaults
    return apply_visible_settings_overrides(defaults, visible_settings)


def _warn_missing_path(
    warnings: list[dict[str, str]],
    code: str,
    message: str,
    value: Any,
) -> None:
    text = str(value or "").strip()
    if not text:
        return
    if not Path(text).exists():
        warnings.append({"code": code, "message": message, "path": text})
