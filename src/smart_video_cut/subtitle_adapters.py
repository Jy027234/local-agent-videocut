from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

from smart_video_cut.external_handoff_compat import (
    EXTERNAL_SUBTITLE_RESULT_KEY,
    LEGACY_SUBTITLE_ADAPTER_ID,
    LEGACY_SUBTITLE_ARTIFACT_DIR,
    LEGACY_SUBTITLE_MODE,
    LEGACY_SUBTITLE_RESULT_KEY,
    is_external_subtitle_mode,
    normalize_legacy_subtitle_mode,
)

SUBTITLE_ADAPTER_RESULT_SCHEMA = "smart_video_cut.local.subtitle_adapter_result.v0"
FILMGEN_SUBTITLE_HANDOFF_SCHEMA = "smart_video_cut.local.filmgen_subtitle_handoff.v0"
FILMGEN_SUBTITLE_HANDOFF_PREVIEW_SCHEMA = "smart_video_cut.local.filmgen_subtitle_handoff_preview.v0"


def prepare_subtitles(
    *,
    subtitle_settings: Mapping[str, Any] | None,
    artifact_root: str | Path | None = None,
) -> dict[str, Any]:
    """Prepare subtitle inputs for the renderer through a plugin-style adapter."""
    settings = dict(subtitle_settings or {})
    adapter_id = _adapter_id(settings)
    onscreen_text_policy = (
        "preserve_existing"
        if settings.get("preserve_onscreen_text", True) is True
        else "allow_regenerate"
    )
    result = {
        "schema": SUBTITLE_ADAPTER_RESULT_SCHEMA,
        "adapter_id": adapter_id,
        "mode": str(settings.get("mode") or "auto"),
        "enabled": adapter_id != "subtitle.none",
        "ok": True,
        "skipped": False,
        "reason": "",
        "subtitle_texts": [],
        "onscreen_text_policy": onscreen_text_policy,
        "renderer_subtitle_enabled": adapter_id != "subtitle.none",
        "renderer_subtitle_texts": [],
        "handoff_path": None,
        LEGACY_SUBTITLE_RESULT_KEY: None,
        EXTERNAL_SUBTITLE_RESULT_KEY: None,
    }

    if adapter_id == "subtitle.none":
        result.update({
            "skipped": True,
            "reason": "subtitle_disabled",
            "renderer_subtitle_enabled": False,
        })
        return result
    if adapter_id == LEGACY_SUBTITLE_ADAPTER_ID:
        handoff = build_filmgen_subtitle_handoff(
            subtitle_settings=settings,
            onscreen_text_policy=onscreen_text_policy,
        )
        handoff_path = _write_filmgen_subtitle_handoff(
            handoff=handoff,
            artifact_root=Path(artifact_root) if artifact_root is not None else None,
        )
        if handoff_path is not None:
            handoff["handoff_path"] = str(handoff_path)
        result.update({
            "ok": True,
            "skipped": False,
            "reason": "filmgen_subtitle_handoff",
            "subtitle_texts": handoff["subtitle_texts"],
            "renderer_subtitle_enabled": False,
            "handoff_path": str(handoff_path) if handoff_path is not None else None,
            LEGACY_SUBTITLE_RESULT_KEY: handoff,
            EXTERNAL_SUBTITLE_RESULT_KEY: handoff,
        })
        return result

    subtitle_texts = subtitle_texts_from_settings(settings)
    result.update({
        "reason": "custom_subtitle_text"
        if adapter_id == "subtitle.custom_text"
        else "auto_subtitle_prompt",
        "subtitle_texts": subtitle_texts,
        "renderer_subtitle_texts": subtitle_texts,
    })
    return result


def build_filmgen_subtitle_handoff(
    *,
    subtitle_settings: Mapping[str, Any] | None,
    onscreen_text_policy: str = "preserve_existing",
) -> dict[str, Any]:
    settings = dict(subtitle_settings or {})
    return {
        "schema": FILMGEN_SUBTITLE_HANDOFF_SCHEMA,
        "adapter_id": LEGACY_SUBTITLE_ADAPTER_ID,
        "mode": normalize_legacy_subtitle_mode(settings.get("mode"), default=LEGACY_SUBTITLE_MODE),
        "status": "ready",
        "handoff_path": None,
        "subtitle_texts": subtitle_texts_from_settings(settings),
        "source_settings": {
            "custom_prompt": str(settings.get("custom_prompt") or ""),
            "location_info": str(settings.get("location_info") or ""),
            "preserve_onscreen_text": settings.get("preserve_onscreen_text", True) is True,
        },
        "style": {
            "font_size": _optional_int(settings.get("font_size")) or 44,
            "font_color": str(settings.get("font_color") or "white"),
            "outline_color": str(settings.get("outline_color") or "black"),
            "outline_width": _optional_int(settings.get("outline_width")) or 2,
            "position": str(settings.get("position") or "bottom_center"),
        },
        "track_request": {
            "format": str(settings.get("filmgen_format") or "timeline_text"),
            "language": str(settings.get("language") or "zh-CN"),
            "target": "external_filmgen_subtitle_track",
        },
        "renderer_contract": {
            "current_renderer_subtitle_enabled": False,
            "onscreen_text_policy": onscreen_text_policy,
            "reason": "Subtitle track is handed off to an external flow instead of being rendered by the current toolkit.",
        },
    }


def subtitle_texts_from_settings(subtitle_settings: Mapping[str, Any] | None) -> list[str]:
    settings = dict(subtitle_settings or {})
    if settings.get("enabled", True) is False:
        return []
    values: list[str] = []
    location = str(settings.get("location_info") or "").strip()
    custom_prompt = str(settings.get("custom_prompt") or "").strip()
    if location:
        values.append(location)
    if custom_prompt:
        for part in custom_prompt.replace("；", "\n").replace("。", "\n").replace("，", "\n").splitlines():
            text = part.strip(" ：:，,。；;")
            if text and text not in values:
                values.append(text)
    return values[:8]


def load_filmgen_subtitle_handoff(path: str | Path) -> dict[str, Any]:
    handoff_path = Path(path)
    if not handoff_path.is_file():
        return {
            "schema": FILMGEN_SUBTITLE_HANDOFF_PREVIEW_SCHEMA,
            "ok": False,
            "reason": "subtitle_handoff_not_found",
            "handoff_path": str(handoff_path),
            "validation": {"valid": False, "errors": [{"code": "file_not_found", "message": "subtitle_handoff.json 不存在"}], "warnings": []},
        }
    payload = json.loads(handoff_path.read_text(encoding="utf-8"))
    validation = validate_filmgen_subtitle_handoff(payload)
    return {
        "schema": FILMGEN_SUBTITLE_HANDOFF_PREVIEW_SCHEMA,
        "ok": validation["valid"],
        "reason": "subtitle_handoff_ready" if validation["valid"] else "subtitle_handoff_invalid",
        "handoff_path": str(handoff_path),
        "handoff": payload,
        "validation": validation,
        "subtitle_text_count": len(payload.get("subtitle_texts") or []) if isinstance(payload, Mapping) else 0,
        "import_contract": {
            "accepted_schema": FILMGEN_SUBTITLE_HANDOFF_SCHEMA,
            "external_center": "External subtitle generation hub or compatible tool",
            "next_step": "Generate an external subtitle track from subtitle_texts/style/track_request, then return subtitle assets to ProjectPack or the final render pipeline.",
        },
    }


def validate_filmgen_subtitle_handoff(handoff: Mapping[str, Any] | None) -> dict[str, Any]:
    payload = dict(handoff or {})
    errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    if payload.get("schema") != FILMGEN_SUBTITLE_HANDOFF_SCHEMA:
        errors.append({
            "code": "unsupported_schema",
            "message": f"期望 schema={FILMGEN_SUBTITLE_HANDOFF_SCHEMA}",
        })
    if not isinstance(payload.get("subtitle_texts"), list) or not payload.get("subtitle_texts"):
        warnings.append({"code": "subtitle_texts_empty", "message": "字幕文本为空，外部中枢可能需要自行生成文案。"})
    if not isinstance(payload.get("style"), Mapping):
        errors.append({"code": "style_missing", "message": "缺少字幕样式 style。"})
    if not isinstance(payload.get("track_request"), Mapping):
        errors.append({"code": "track_request_missing", "message": "缺少外部字幕轨请求 track_request。"})
    renderer_contract = payload.get("renderer_contract")
    if not isinstance(renderer_contract, Mapping):
        warnings.append({"code": "renderer_contract_missing", "message": "缺少 renderer_contract，无法确认本地渲染器是否应关闭字幕。"})
    elif renderer_contract.get("current_renderer_subtitle_enabled") is not False:
        warnings.append({"code": "renderer_subtitle_not_disabled", "message": "外部字幕交接模式建议关闭本地字幕渲染。"})
    return {
        "valid": not errors,
        "errors": errors,
        "warnings": warnings,
    }


def _adapter_id(settings: Mapping[str, Any]) -> str:
    mode = str(settings.get("mode") or "auto").strip().casefold()
    if settings.get("enabled", True) is False or mode == "none":
        return "subtitle.none"
    if is_external_subtitle_mode(mode):
        return LEGACY_SUBTITLE_ADAPTER_ID
    if str(settings.get("custom_prompt") or "").strip() or str(settings.get("location_info") or "").strip():
        return "subtitle.custom_text"
    return "subtitle.auto_prompt"


def _write_filmgen_subtitle_handoff(
    *,
    handoff: dict[str, Any],
    artifact_root: Path | None,
) -> Path | None:
    if artifact_root is None:
        return None
    handoff_path = artifact_root / LEGACY_SUBTITLE_ARTIFACT_DIR / "subtitle_handoff.json"
    handoff_path.parent.mkdir(parents=True, exist_ok=True)
    handoff["handoff_path"] = str(handoff_path)
    handoff_path.write_text(
        json.dumps(handoff, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return handoff_path


def _optional_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
