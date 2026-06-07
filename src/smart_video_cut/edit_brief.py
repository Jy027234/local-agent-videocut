from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from smart_video_cut.edit_settings import apply_visible_settings_overrides
from smart_video_cut.material_plan import build_material_plan
from smart_video_cut.style_package import load_style_package


def build_edit_brief(
    *,
    style_package: str | Path,
    input_video: str | Path,
    input_videos: list[str | Path] | None = None,
    output_dir: str | Path,
    user_request: str,
    settings_overrides: Mapping[str, Any] | None = None,
    voiceover_text: str | None = None,
    execute_real_render: bool = False,
    use_memory: bool = True,
) -> dict[str, Any]:
    package = load_style_package(style_package)
    settings = apply_visible_settings_overrides(package["visible_settings"], settings_overrides)
    selected_inputs = _input_video_list(input_video, input_videos)
    material_plan = build_material_plan(selected_inputs)
    brief_profile = package.get("edit_brief") if isinstance(package.get("edit_brief"), dict) else {}
    video = settings.get("video", {})
    subtitle = settings.get("subtitle", {})
    audio = settings.get("audio", {})
    voice = settings.get("voice", {})
    package_name = str(package.get("name") or Path(style_package).name)
    target = str(user_request or "").strip() or "根据参考风格完成一版短视频剪辑。"
    voice_text = str(voiceover_text or "").strip()
    bgm_path = str(audio.get("bgm_audio_path") or "").strip()
    bgm_desc = (
        f"本地音乐文件 {bgm_path}，从 {audio.get('bgm_start_seconds', 0)} 秒开始采样"
        if bgm_path
        else str(audio.get("bgm_style", "upbeat_instrumental"))
    )
    subtitle_enabled = subtitle.get("enabled", True) is not False
    subtitle_desc = _subtitle_description(subtitle)
    voice_mode = str(voice.get("mode") or "generated_male_ad_copy")
    voice_desc = "不加新配音" if voice_mode == "none" else f"配音 Provider 为 {voice.get('provider', 'edge_tts')}"
    brief_lines = [
        f"剪辑目标：{target}",
        _reference_sentence(brief_profile, package_name),
        _source_sentence(brief_profile, len(selected_inputs)),
        f"素材分工：{_material_plan_summary(material_plan, _role_labels(brief_profile))}",
        (
            "输出规格："
            f"{video.get('target_duration_seconds', 20)} 秒，"
            f"{video.get('aspect_ratio', '9:16')}，"
            f"{video.get('resolution', '720x1280')}，"
            f"{video.get('quality', 'standard')} 质量。"
        ),
        (
            "字幕与画面："
            f"{subtitle_desc}；"
            f"{_visual_priority(brief_profile)}。"
        ),
        (
            "音频策略："
            f"{'去掉原视频人声' if audio.get('remove_original_voice', True) else '保留并优化原视频声音'}，"
            f"背景音乐 {bgm_desc}，"
            f"音量 {audio.get('bgm_volume_db', -18)} dB；"
            f"{voice_desc}。"
        ),
        f"执行方式：{'真实渲染并导出视频' if execute_real_render else '先生成剪辑计划，不执行真实渲染'}。",
        f"记忆使用：{'启用本地记忆辅助理解偏好' if use_memory else '本次不使用本地记忆'}。",
    ]
    if voice_text:
        brief_lines.append(f"指定配音文案：{voice_text}")
    checklist = _checklist(brief_profile)
    if not subtitle_enabled:
        checklist.insert(1, "本次不添加内容字幕，只保留必要画面包装。")
    return {
        "schema": "smart_video_cut.local.edit_brief.v1",
        "ok": True,
        "style_package": {
            "name": package_name,
            "path": str(style_package),
            "reference_label": package.get("reference_template", {}).get("source_label"),
        },
        "input_video": str(selected_inputs[0]) if selected_inputs else str(input_video),
        "input_videos": [str(path) for path in selected_inputs],
        "output_dir": str(output_dir),
        "settings": settings,
        "material_plan": material_plan,
        "brief_text": "\n".join(brief_lines),
        "checklist": checklist,
        "strategy": _build_strategy(
            brief_profile=brief_profile,
            package_name=package_name,
            settings=settings,
            video=video,
            subtitle=subtitle,
            audio=audio,
            voice=voice,
            bgm_desc=bgm_desc,
            voice_mode=voice_mode,
            voice_desc=voice_desc,
        ),
        "risk_warnings": _compute_risk_warnings(settings, material_plan, selected_inputs),
        "ready_for_confirmation": True,
    }


def _input_video_list(input_video: str | Path, input_videos: list[str | Path] | None) -> list[Path]:
    paths: list[Path] = []
    for value in [input_video, *(input_videos or [])]:
        text = str(value or "").strip()
        if not text:
            continue
        path = Path(text)
        if path not in paths:
            paths.append(path)
    return paths


def _reference_sentence(brief_profile: Mapping[str, Any], package_name: str) -> str:
    template = str(brief_profile.get("reference_sentence") or "").strip()
    if template:
        return _format_sentence(template, package_name=package_name)
    return f"参考风格：使用《{package_name}》提取的节奏、封面文字、字幕样式和画面组织方式作为参考。"


def _source_sentence(brief_profile: Mapping[str, Any], selected_count: int) -> str:
    template = str(brief_profile.get("source_sentence") or "").strip()
    if template:
        return _format_sentence(template, count=selected_count)
    return f"原始素材：共 {selected_count} 个视频，将按主体全貌、细节、环境和节奏片段进行混剪。"


def _visual_priority(brief_profile: Mapping[str, Any]) -> str:
    return str(brief_profile.get("visual_priority") or "画面优先展示主体全貌、关键细节和安装效果").strip()


def _checklist(brief_profile: Mapping[str, Any]) -> list[str]:
    items = brief_profile.get("checklist")
    if isinstance(items, list):
        cleaned = [str(item).strip() for item in items if str(item or "").strip()]
        if cleaned:
            return cleaned
    return [
        "开头 1-3 秒明确展示主体或结果。",
        "字幕关闭时保持画面干净；字幕开启时不能遮挡主体，字号和描边要保证手机端可读。",
        "配乐不能盖过配音，背景音乐只做节奏和情绪支撑。",
        "成片结束前保留完整效果或关键卖点画面。",
    ]


def _role_labels(brief_profile: Mapping[str, Any]) -> dict[str, str]:
    labels = brief_profile.get("role_labels")
    if not isinstance(labels, Mapping):
        return {}
    return {str(key): str(value).strip() for key, value in labels.items() if str(value or "").strip()}


def _format_sentence(template: str, **values: Any) -> str:
    try:
        return template.format(**values)
    except (KeyError, IndexError, ValueError):
        return template


def _material_plan_summary(material_plan: Mapping[str, Any], role_labels: Mapping[str, str] | None = None) -> str:
    materials = material_plan.get("materials")
    if not isinstance(materials, list) or not materials:
        return "未选择可规划素材。"
    labels = role_labels or {}
    parts = []
    for item in materials:
        if not isinstance(item, Mapping):
            continue
        label = str(item.get("label") or f"素材 {item.get('index', '')}").strip()
        primary_role = str(item.get("primary_role") or "").strip()
        role = str(labels.get(primary_role) or item.get("display_role") or primary_role or "补充镜头").strip()
        source = _assignment_source_label(str(item.get("assignment_source") or ""))
        parts.append(f"{label} 用于 {role}（{source}）")
    return "；".join(parts) if parts else "按素材顺序进行角色规划。"


def _assignment_source_label(source: str) -> str:
    if source == "multimodal_thumbnail_role_review":
        return "多模态复核"
    if source == "ffmpeg_frame_probe_role_assignment":
        return "视觉分析"
    return "顺序规划"


def _subtitle_description(subtitle: Mapping[str, Any]) -> str:
    if subtitle.get("enabled", True) is False:
        return "不添加内容字幕"
    parts = [
        f"字幕 {subtitle.get('font_size', 44)}px",
        f"{subtitle.get('font_color', 'white')} 字",
        f"{subtitle.get('outline_color', 'black')} 描边",
    ]
    location = str(subtitle.get("location_info") or "").strip()
    custom_prompt = str(subtitle.get("custom_prompt") or "").strip()
    if location:
        parts.append(f"位置信息：{location}")
    if custom_prompt:
        parts.append(f"字幕要求：{custom_prompt}")
    return "，".join(parts)


def _build_strategy(
    *,
    brief_profile: Mapping[str, Any],
    package_name: str,
    settings: Mapping[str, Any],
    video: Mapping[str, Any],
    subtitle: Mapping[str, Any],
    audio: Mapping[str, Any],
    voice: Mapping[str, Any],
    bgm_desc: str,
    voice_mode: str,
    voice_desc: str,
) -> dict[str, Any]:
    """Build a structured strategy dict for the enhanced edit brief."""
    timeline_kind = str(brief_profile.get("timeline_kind") or "advertising_flash_montage")
    avg_segment = float(brief_profile.get("avg_segment_seconds") or 1.4)
    transition_style = str(
        brief_profile.get("transition_style") or "hard_cuts_with_light_flash_accents"
    )
    return {
        "style": {
            "reference_package": package_name,
            "timeline_kind": timeline_kind,
            "visual_priority": _visual_priority(brief_profile),
            "color_treatment": str(brief_profile.get("color_treatment") or "mild_ad_contrast_saturation_boost"),
        },
        "rhythm": {
            "pacing": str(brief_profile.get("pacing") or "flash_montage"),
            "avg_segment_seconds": avg_segment,
            "transition_style": transition_style,
            "opening_strategy": str(brief_profile.get("opening_strategy") or "immediate_product_hero"),
            "closing_strategy": str(brief_profile.get("closing_strategy") or "final_effect_hold"),
        },
        "subtitle": {
            "enabled": subtitle.get("enabled", True) is not False,
            "font_size": subtitle.get("font_size", 44),
            "style": f"{subtitle.get('font_color', 'white')}_with_{subtitle.get('outline_color', 'black')}_outline",
            "position": str(subtitle.get("position") or "bottom_center"),
            "custom_prompt": str(subtitle.get("custom_prompt") or ""),
        },
        "audio": {
            "remove_original_voice": audio.get("remove_original_voice", True),
            "bgm": bgm_desc,
            "bgm_volume_db": audio.get("bgm_volume_db", -18),
            "voice_mode": voice_mode,
            "voice_provider": str(voice.get("provider") or "edge_tts"),
        },
    }


def _compute_risk_warnings(
    settings: Mapping[str, Any],
    material_plan: Mapping[str, Any],
    inputs: list[Path],
) -> list[dict[str, str]]:
    """Compute risk warnings based on material plan and settings."""
    warnings: list[dict[str, str]] = []
    material_count = int(material_plan.get("material_count", 0))
    video = settings.get("video", {})
    target_duration = int(video.get("target_duration_seconds", 20))

    if material_count < 3 and target_duration > 15:
        warnings.append({
            "level": "warning",
            "category": "material_shortage",
            "message": f"素材仅 {material_count} 个，目标时长 {target_duration} 秒，可能出现重复画面。",
        })

    strategy = str(material_plan.get("strategy", ""))
    if strategy == "order_fallback_role_assignment":
        warnings.append({
            "level": "info",
            "category": "role_assignment_fallback",
            "message": "素材角色分配使用了顺序回退，建议手动确认素材分工。",
        })

    if material_count == 0:
        warnings.append({
            "level": "error",
            "category": "no_materials",
            "message": "未选择任何素材视频，无法执行剪辑。",
        })

    if target_duration > 60:
        warnings.append({
            "level": "info",
            "category": "long_duration",
            "message": f"目标时长 {target_duration} 秒较长，建议确保素材总时长充足。",
        })

    visual_analysis = material_plan.get("visual_analysis")
    if isinstance(visual_analysis, Mapping):
        if visual_analysis.get("available") is not True and material_count > 0:
            warnings.append({
                "level": "info",
                "category": "visual_analysis_unavailable",
                "message": "素材视觉分析不可用，片段选择可能不够精准。",
            })

    return warnings
