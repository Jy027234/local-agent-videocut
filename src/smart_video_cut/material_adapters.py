from __future__ import annotations

from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from smart_video_cut.material_plan import build_material_plan


MATERIAL_ADAPTER_RESULT_SCHEMA = "smart_video_cut.local.material_adapter_result.v0"

MaterialPlanBuilder = Callable[..., dict[str, Any]]


def prepare_material_plan(
    *,
    paths: Sequence[str | Path],
    settings: Mapping[str, Any] | None = None,
    build_plan_func: MaterialPlanBuilder = build_material_plan,
) -> dict[str, Any]:
    """Prepare material role planning through plugin-style analysis adapters."""
    normalized_settings = dict(settings or {})
    material_analysis = _section(normalized_settings, "material_analysis")
    model_route = _section(normalized_settings, "model_route")
    enable_visual_analysis = material_analysis.get("enable_visual_analysis", True) is not False
    allow_media_upload = model_route.get("allow_media_upload_to_llm") is True
    requested_multimodal_review = (
        enable_visual_analysis
        and material_analysis.get("enable_multimodal_review", True) is not False
    )
    enable_multimodal_review = (
        requested_multimodal_review
        and allow_media_upload
    )
    visual_tuning = _visual_analysis_tuning(material_analysis)
    selected_adapter_ids = _selected_adapter_ids(
        enable_visual_analysis=enable_visual_analysis,
        enable_multimodal_review=enable_multimodal_review,
    )
    material_plan = _call_build_plan(
        build_plan_func,
        list(paths),
        enable_visual_analysis=enable_visual_analysis,
        enable_multimodal_review=enable_multimodal_review,
        visual_tuning=visual_tuning,
    )
    completed_adapter_ids = _completed_adapter_ids(material_plan)
    warnings = _warnings(
        material_plan=material_plan,
        selected_adapter_ids=selected_adapter_ids,
        allow_media_upload=allow_media_upload,
        enable_multimodal_review=enable_multimodal_review,
    )
    return {
        "schema": MATERIAL_ADAPTER_RESULT_SCHEMA,
        "ok": isinstance(material_plan, dict) and material_plan.get("schema") == "smart_video_cut.local.material_plan.v0",
        "selected_adapter_ids": selected_adapter_ids,
        "completed_adapter_ids": completed_adapter_ids,
        "fallback_adapter_id": "material.order_fallback"
        if completed_adapter_ids == ["material.order_fallback"] and selected_adapter_ids != ["material.order_fallback"]
        else "",
        "visual_analysis_enabled": enable_visual_analysis,
        "visual_analysis_tuning": visual_tuning,
        "requested_multimodal_review": requested_multimodal_review,
        "multimodal_review_enabled": enable_multimodal_review,
        "allow_media_upload_to_llm": allow_media_upload,
        "material_count": int(material_plan.get("material_count") or 0) if isinstance(material_plan, dict) else 0,
        "strategy": str(material_plan.get("strategy") or "") if isinstance(material_plan, dict) else "",
        "warnings": warnings,
        "ui_hints": _ui_hints(
            material_plan=material_plan,
            enable_visual_analysis=enable_visual_analysis,
            requested_multimodal_review=requested_multimodal_review,
            enable_multimodal_review=enable_multimodal_review,
            allow_media_upload=allow_media_upload,
        ),
        "material_plan": material_plan,
    }


def _call_build_plan(
    build_plan_func: MaterialPlanBuilder,
    paths: list[str | Path],
    *,
    enable_visual_analysis: bool,
    enable_multimodal_review: bool,
    visual_tuning: Mapping[str, Any],
) -> dict[str, Any]:
    try:
        return build_plan_func(
            paths,
            enable_visual_analysis=enable_visual_analysis,
            enable_multimodal_review=enable_multimodal_review,
            visual_tuning=visual_tuning,
        )
    except TypeError as exc:
        message = str(exc)
        if "unexpected keyword" not in message and "positional" not in message:
            raise
    try:
        return build_plan_func(
            paths,
            enable_visual_analysis=enable_visual_analysis,
            enable_multimodal_review=enable_multimodal_review,
        )
    except TypeError as exc:
        message = str(exc)
        if "unexpected keyword" not in message and "positional" not in message:
            raise
        return build_plan_func(paths)


def _selected_adapter_ids(
    *,
    enable_visual_analysis: bool,
    enable_multimodal_review: bool,
) -> list[str]:
    if not enable_visual_analysis:
        return ["material.order_fallback"]
    selected = ["material.ffmpeg_probe"]
    if enable_multimodal_review:
        selected.append("material.multimodal_review")
    return selected


def _completed_adapter_ids(material_plan: Mapping[str, Any]) -> list[str]:
    strategy = str(material_plan.get("strategy") or "")
    if strategy == "multimodal_thumbnail_role_review":
        return ["material.ffmpeg_probe", "material.multimodal_review"]
    if strategy == "ffmpeg_frame_probe_role_assignment":
        return ["material.ffmpeg_probe"]
    return ["material.order_fallback"]


def _warnings(
    *,
    material_plan: Mapping[str, Any],
    selected_adapter_ids: list[str],
    allow_media_upload: bool,
    enable_multimodal_review: bool,
) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    visual = material_plan.get("visual_analysis") if isinstance(material_plan.get("visual_analysis"), Mapping) else {}
    if "material.ffmpeg_probe" in selected_adapter_ids and visual.get("available") is not True:
        warnings.append({
            "code": "visual_analysis_unavailable",
            "adapter_id": "material.ffmpeg_probe",
            "message": "FFmpeg 抽帧素材分析未产出可用视觉档案，已按顺序规划素材角色。",
        })
    review = material_plan.get("multimodal_review") if isinstance(material_plan.get("multimodal_review"), Mapping) else {}
    if enable_multimodal_review and review.get("ok") is not True:
        reason = str(review.get("skipped_reason") or review.get("failure_reason") or "unknown")
        warnings.append({
            "code": "multimodal_review_unavailable",
            "adapter_id": "material.multimodal_review",
            "message": f"多模态素材复核未完成：{reason}。",
        })
    if allow_media_upload:
        warnings.append({
            "code": "media_upload_to_llm_allowed",
            "adapter_id": "material.multimodal_review",
            "message": "用户设置允许将抽帧缩略图发送给多模态模型复核。",
        })
    return warnings


def _visual_analysis_tuning(material_analysis: Mapping[str, Any]) -> dict[str, Any]:
    preset = str(material_analysis.get("visual_quality_preset") or "balanced").strip().casefold()
    preset_defaults = {
        "draft": {"frame_sample_count": 4, "thumbnail_max_side": 256, "role_confidence_threshold": 0.42},
        "balanced": {"frame_sample_count": 6, "thumbnail_max_side": 384, "role_confidence_threshold": 0.50},
        "high": {"frame_sample_count": 10, "thumbnail_max_side": 512, "role_confidence_threshold": 0.58},
        "calibrated": {"frame_sample_count": 6, "thumbnail_max_side": 384, "role_confidence_threshold": 0.50},
    }
    defaults = preset_defaults.get(preset, preset_defaults["balanced"])
    return {
        "preset": preset if preset in preset_defaults else "balanced",
        "frame_sample_count": _safe_int(
            material_analysis.get("frame_sample_count"),
            default=defaults["frame_sample_count"],
            minimum=1,
            maximum=24,
        ),
        "thumbnail_max_side": _safe_int(
            material_analysis.get("thumbnail_max_side"),
            default=defaults["thumbnail_max_side"],
            minimum=128,
            maximum=1024,
        ),
        "role_confidence_threshold": _safe_float(
            material_analysis.get("role_confidence_threshold"),
            default=defaults["role_confidence_threshold"],
            minimum=0.0,
            maximum=1.0,
        ),
    }


def _ui_hints(
    *,
    material_plan: Mapping[str, Any],
    enable_visual_analysis: bool,
    requested_multimodal_review: bool,
    enable_multimodal_review: bool,
    allow_media_upload: bool,
) -> list[dict[str, str]]:
    hints: list[dict[str, str]] = []
    visual = material_plan.get("visual_analysis") if isinstance(material_plan.get("visual_analysis"), Mapping) else {}
    review = material_plan.get("multimodal_review") if isinstance(material_plan.get("multimodal_review"), Mapping) else {}
    if not enable_visual_analysis:
        hints.append({
            "id": "material.visual_analysis.disabled",
            "level": "info",
            "message": "视觉分析已关闭，素材角色会按添加顺序规划。",
        })
    elif visual.get("available") is not True:
        hints.append({
            "id": "material.visual_analysis.fallback",
            "level": "warning",
            "message": "本地抽帧视觉分析不可用，已回退为顺序素材规划。",
        })
    else:
        hints.append({
            "id": "material.visual_analysis.ready",
            "level": "success",
            "message": f"本地视觉分析已完成，可用素材档案 {visual.get('profiles_ready', 0)} 个。",
        })
    if requested_multimodal_review and not allow_media_upload:
        hints.append({
            "id": "material.multimodal_review.needs_consent",
            "level": "warning",
            "message": "多模态复核需要用户允许上传抽帧/截图；未授权时只使用本地分析。",
        })
    elif enable_multimodal_review:
        status = "success" if review.get("ok") is True else "warning"
        hints.append({
            "id": "material.multimodal_review.enabled",
            "level": status,
            "message": "已允许上传抽帧缩略图用于多模态素材复核。",
        })
    return hints


def _section(settings: Mapping[str, Any], name: str) -> dict[str, Any]:
    section = settings.get(name)
    return dict(section) if isinstance(section, Mapping) else {}


def _safe_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _safe_float(value: Any, *, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))
