from __future__ import annotations

import hashlib
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from smart_video_cut.edit_settings import apply_visible_settings_overrides, quality_to_crf
from smart_video_cut.models import (
    LocalVisibleSettings,
    STYLE_PACK_SCHEMA,
    STYLE_PACKAGE_SCHEMA,
    StylePackageRequest,
)
from smart_video_cut.template_analysis import analyze_template_video


STYLE_PACKAGE_FILENAME = "style_package.json"
STYLE_PACK_FILENAME = "style_pack.json"
STYLE_FILENAMES = (STYLE_PACKAGE_FILENAME, STYLE_PACK_FILENAME)
ASSETS_DIRNAME = "assets"
REFERENCE_TEMPLATE_FILENAME = "reference_template.mp4"


def create_style_package(request: StylePackageRequest) -> dict[str, Any]:
    """Create a self-contained local style package from a user reference video."""

    template = request.template_video
    if not template.is_file():
        raise ValueError("template_video must point to a readable file")

    package_dir = request.package_dir
    assets_dir = package_dir / ASSETS_DIRNAME
    package_dir.mkdir(parents=True, exist_ok=True)
    assets_dir.mkdir(parents=True, exist_ok=True)

    copied_template = assets_dir / REFERENCE_TEMPLATE_FILENAME
    shutil.copy2(template, copied_template)
    payload = _package_payload(
        request=request,
        copied_template=copied_template,
        source_template=template,
    )
    package_json = package_dir / STYLE_PACKAGE_FILENAME
    package_json.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return payload


def load_style_package(path: str | Path) -> dict[str, Any]:
    selected = Path(path)
    if selected.is_dir():
        for filename in STYLE_FILENAMES:
            candidate = selected / filename
            if candidate.is_file():
                selected = candidate
                break
    if not selected.is_file():
        raise ValueError("style package must be a directory or style_package.json/style_pack.json file")
    payload = json.loads(selected.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("style package JSON must contain an object")
    schema = str(payload.get("schema", ""))
    if schema == STYLE_PACKAGE_SCHEMA:
        normalized = dict(payload)
        normalized["visible_settings"] = _normalize_visible_settings(normalized.get("visible_settings"))
        return normalized
    if schema == STYLE_PACK_SCHEMA:
        return _normalize_style_pack_payload(payload)
    raise ValueError(
        f"style package schema must be {STYLE_PACKAGE_SCHEMA} or {STYLE_PACK_SCHEMA}"
    )


def style_package_dir(path: str | Path) -> Path:
    selected = Path(path)
    return selected if selected.is_dir() else selected.parent


def reference_template_path(path: str | Path, payload: dict[str, Any] | None = None) -> Path | None:
    package_dir = style_package_dir(path)
    package = payload or load_style_package(path)
    rel = str(package.get("reference_template", {}).get("local_package_path") or "")
    if not rel:
        return None
    candidate = (package_dir / rel).resolve()
    package_root = package_dir.resolve()
    if package_root not in {candidate, *candidate.parents}:
        raise ValueError("reference template resolves outside style package")
    return candidate if candidate.is_file() else None


def discover_style_packages(base_dir: str | Path | None = None) -> list[dict[str, Any]]:
    root = Path(base_dir) if base_dir else Path(__file__).resolve().parents[2] / "packages"
    if not root.exists():
        return []
    packages: list[dict[str, Any]] = []
    package_jsons: list[Path] = []
    for filename in STYLE_FILENAMES:
        package_jsons.extend(root.rglob(filename))
    for package_json in sorted(package_jsons):
        try:
            payload = load_style_package(package_json)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        settings = payload.get("visible_settings") if isinstance(payload.get("visible_settings"), dict) else {}
        reference = payload.get("reference_template") if isinstance(payload.get("reference_template"), dict) else {}
        packages.append(
            {
                "name": payload.get("name") or package_json.parent.name,
                "package_id": payload.get("package_id") or package_json.parent.name,
                "path": str(package_json.parent),
                "json_path": str(package_json),
                "schema": payload.get("schema"),
                "description": payload.get("description") or "",
                "created_at": payload.get("created_at"),
                "reference_label": reference.get("source_label"),
                "video": settings.get("video", {}),
                "subtitle": settings.get("subtitle", {}),
                "audio": settings.get("audio", {}),
                "voice": settings.get("voice", {}),
            }
        )
    packages.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    return packages


def default_settings_from_options(
    *,
    duration: int,
    aspect_ratio: str,
    resolution: str,
    quality: str,
    subtitle_size: int,
    bgm_volume_db: float,
    voice_provider: str,
) -> LocalVisibleSettings:
    settings = LocalVisibleSettings()
    settings.video.target_duration_seconds = duration
    settings.video.aspect_ratio = aspect_ratio
    settings.video.resolution = resolution
    settings.video.quality = quality
    settings.video.crf = _quality_to_crf(quality)
    settings.subtitle.font_size = subtitle_size
    settings.audio.bgm_volume_db = bgm_volume_db
    settings.voice.provider = voice_provider
    return settings


def _package_payload(
    *,
    request: StylePackageRequest,
    copied_template: Path,
    source_template: Path,
) -> dict[str, Any]:
    settings = request.settings.to_dict()
    reference_analysis = analyze_template_video(
        copied_template,
        output_dir=copied_template.parent / "reference_analysis",
    )
    payload: dict[str, Any] = {
        "schema": STYLE_PACKAGE_SCHEMA,
        "package_id": _safe_id(request.name),
        "name": request.name,
        "description": request.description,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "reference_template": {
            "source_label": source_template.name,
            "local_package_path": f"{ASSETS_DIRNAME}/{REFERENCE_TEMPLATE_FILENAME}",
            "checksum": _sha256_file(copied_template),
            "size_bytes": copied_template.stat().st_size,
            "media_kind": "reference_template_video",
        },
        "reference_analysis": reference_analysis,
        "visible_settings": settings,
        "agent_load_reduction": {
            "user_controls_duration": True,
            "user_controls_aspect_ratio": True,
            "user_controls_quality": True,
            "user_controls_subtitle_style": True,
            "user_controls_audio_mix": True,
            "agent_focus": [
                "understand user intent",
                "choose shots",
                "write voiceover copy",
                "request repair when QC fails",
            ],
        },
        "reuse_policy": {
            "editing_engine": "bundled video_editing_toolkit.creative_edit_runner",
            "voice_profile_contract": "bundled video_editing_toolkit.voice_simulation",
            "local_protocol_contract": "bundled local studio worker contract",
            "do_not_reimplement_toolkit_capabilities": True,
        },
    }
    # Optional timeline_template: preset segment blueprint for timeline_builder
    timeline_template = _build_timeline_template_from_reference(settings, reference_analysis)
    if timeline_template:
        payload["timeline_template"] = timeline_template
    return payload


def _build_timeline_template_from_reference(settings: dict[str, Any], analysis: dict[str, Any]) -> dict[str, Any]:
    template = analysis.get("timeline_template") if isinstance(analysis.get("timeline_template"), dict) else {}
    if not template:
        return _build_default_timeline_template(settings)
    result = dict(template)
    video = settings.get("video", {}) if isinstance(settings, dict) else {}
    target_duration = int(video.get("target_duration_seconds", result.get("target_duration_seconds", 20)))
    result["target_duration_seconds"] = target_duration
    result["analysis_source"] = "reference_template_video"
    return result


def _build_default_timeline_template(settings: dict[str, Any]) -> dict[str, Any]:
    """Build a default timeline_template from visible_settings for timeline_builder.

    The template embeds a segment_blueprint so that timeline_builder can
    generate a timeline without relying solely on the hard-coded default.
    """
    from smart_video_cut.timeline_builder import DEFAULT_SEGMENT_BLUEPRINT

    video = settings.get("video", {}) if isinstance(settings, dict) else {}
    target_duration = int(video.get("target_duration_seconds", 20))

    return {
        "timeline_kind": "advertising_flash_montage",
        "target_duration_seconds": target_duration,
        "transition_policy": {
            "style": "hard_cuts_with_light_flash_accents",
            "max_single_shot_seconds": 4.0,
        },
        "source_selection_policy": {
            "prefer": ["door_front", "lock_or_hardware_detail", "door_frame", "site_context"],
            "avoid": ["blank_wall_closeup", "dark_unreadable_surface", "long_static_repetition"],
        },
        "segment_blueprint": list(DEFAULT_SEGMENT_BLUEPRINT),
    }


def _normalize_style_pack_payload(payload: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(payload)
    normalized["visible_settings"] = _normalize_visible_settings(normalized.get("visible_settings"))
    normalized["timeline_template"] = (
        dict(normalized["timeline_template"])
        if isinstance(normalized.get("timeline_template"), dict)
        else {}
    )
    edit_brief_profile = normalized.get("edit_brief_profile")
    normalized["edit_brief"] = dict(edit_brief_profile) if isinstance(edit_brief_profile, dict) else {}
    normalized["reference_template"] = (
        dict(normalized["reference_template"])
        if isinstance(normalized.get("reference_template"), dict)
        else {}
    )
    normalized.setdefault("package_id", _safe_id(str(normalized.get("name", ""))))
    return normalized


def _normalize_visible_settings(raw_settings: Any) -> dict[str, Any]:
    defaults = LocalVisibleSettings().to_dict()
    if not isinstance(raw_settings, dict):
        return defaults
    return apply_visible_settings_overrides(defaults, raw_settings)


def _quality_to_crf(quality: str) -> int:
    return quality_to_crf(quality)


def _safe_id(value: str) -> str:
    rendered = "".join(ch if ch.isalnum() or ch in {"_", "-"} else "_" for ch in value.strip())
    rendered = "_".join(part for part in rendered.split("_") if part)
    return rendered[:80] or "style_package"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)
            if not chunk:
                break
            digest.update(chunk)
    return f"sha256:{digest.hexdigest()}"
