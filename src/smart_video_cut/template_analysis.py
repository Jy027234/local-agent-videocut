from __future__ import annotations

import json
import math
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Mapping


TEMPLATE_ANALYSIS_SCHEMA = "smart_video_cut.local.template_video_analysis.v0"

Runner = Callable[[list[str], int], Any]


def analyze_template_video(
    video_path: str | Path,
    *,
    output_dir: str | Path = "",
    ffprobe_runner: Runner | None = None,
    ffmpeg_runner: Runner | None = None,
) -> dict[str, Any]:
    source = Path(video_path)
    output_path = Path(output_dir) if output_dir else None
    if not source.is_file():
        return {
            "schema": TEMPLATE_ANALYSIS_SCHEMA,
            "ok": False,
            "reason": "template_video_not_found",
            "video_path": str(source),
            "warnings": [{"code": "file_missing", "message": "参考视频不存在，无法分析。"}],
        }

    probe = _probe_media(source, runner=ffprobe_runner)
    video_stream = _first_stream(probe, "video")
    audio_stream = _first_stream(probe, "audio")
    subtitle_streams = _streams(probe, "subtitle")
    duration = _duration_seconds(probe, video_stream)
    width = _safe_int(video_stream.get("width"), 720) if video_stream else 720
    height = _safe_int(video_stream.get("height"), 1280) if video_stream else 1280
    aspect_ratio = _aspect_ratio(width, height)
    fps = _fps(video_stream)
    rhythm = _rhythm_profile(duration_seconds=duration)
    cover = _cover_profile(
        source=source,
        output_dir=output_path,
        duration_seconds=duration,
        ffmpeg_runner=ffmpeg_runner,
    )

    analysis = {
        "schema": TEMPLATE_ANALYSIS_SCHEMA,
        "ok": True,
        "reason": "ffprobe_analysis_completed" if probe else "heuristic_analysis_completed",
        "video_path": str(source),
        "file": {
            "name": source.name,
            "size_bytes": source.stat().st_size,
            "extension": source.suffix.casefold(),
        },
        "video": {
            "duration_seconds": round(duration, 3),
            "width": width,
            "height": height,
            "fps": fps,
            "aspect_ratio": aspect_ratio,
            "orientation": "vertical" if height > width else "horizontal" if width > height else "square",
            "stream_found": bool(video_stream),
        },
        "subtitles": _subtitle_profile(subtitle_streams=subtitle_streams, height=height),
        "cover": cover,
        "bgm": _bgm_profile(audio_stream=audio_stream, duration_seconds=duration),
        "rhythm": rhythm,
        "timeline_template": _timeline_template_from_rhythm(rhythm, duration_seconds=duration),
        "style_suggestions": _style_suggestions(
            duration_seconds=duration,
            width=width,
            height=height,
            fps=fps,
            subtitle_profile=_subtitle_profile(subtitle_streams=subtitle_streams, height=height),
            bgm_profile=_bgm_profile(audio_stream=audio_stream, duration_seconds=duration),
        ),
        "warnings": _warnings(probe=probe, video_stream=video_stream, audio_stream=audio_stream),
        "raw_probe_available": bool(probe),
    }
    return analysis


def apply_template_analysis_to_settings(
    settings: Mapping[str, Any],
    analysis: Mapping[str, Any],
) -> dict[str, Any]:
    """Return conservative style-package setting suggestions derived from analysis."""
    merged = json.loads(json.dumps(dict(settings), ensure_ascii=False))
    suggestions = analysis.get("style_suggestions") if isinstance(analysis.get("style_suggestions"), Mapping) else {}
    for section_name, values in suggestions.items():
        if not isinstance(values, Mapping):
            continue
        section = merged.setdefault(str(section_name), {})
        if not isinstance(section, dict):
            continue
        for key, value in values.items():
            if value is not None and value != "":
                section[str(key)] = value
    return merged


def _probe_media(path: Path, *, runner: Runner | None = None) -> dict[str, Any]:
    ffprobe = _media_binary("ffprobe")
    if not ffprobe and runner is None:
        return {}
    args = [
        str(ffprobe or "ffprobe"),
        "-v",
        "error",
        "-show_format",
        "-show_streams",
        "-of",
        "json",
        str(path),
    ]
    try:
        completed = runner(args, 12) if runner else subprocess.run(
            args,
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=12,
        )
    except (OSError, subprocess.SubprocessError):
        return {}
    stdout = str(getattr(completed, "stdout", "") or "")
    if int(getattr(completed, "returncode", 1) or 0) != 0 or not stdout.strip():
        return {}
    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _cover_profile(
    *,
    source: Path,
    output_dir: Path | None,
    duration_seconds: float,
    ffmpeg_runner: Runner | None = None,
) -> dict[str, Any]:
    timestamp = _cover_timestamp(duration_seconds)
    extracted_path = ""
    if output_dir:
        output_dir.mkdir(parents=True, exist_ok=True)
        cover_path = output_dir / "reference_cover.jpg"
        if _extract_cover(source=source, output_path=cover_path, timestamp=timestamp, runner=ffmpeg_runner):
            extracted_path = str(cover_path)
    return {
        "enabled": True,
        "suggested_timestamp_seconds": timestamp,
        "extracted_frame_path": extracted_path,
        "title_suggestion": source.stem.replace("_", " ").replace("-", " ")[:40] or "参考视频",
        "label_background": "yellow",
        "reason": "reference_frame_extracted" if extracted_path else "cover_timestamp_suggested",
    }


def _extract_cover(
    *,
    source: Path,
    output_path: Path,
    timestamp: float,
    runner: Runner | None = None,
) -> bool:
    ffmpeg = _media_binary("ffmpeg")
    if not ffmpeg and runner is None:
        return False
    args = [
        str(ffmpeg or "ffmpeg"),
        "-y",
        "-ss",
        str(max(0.0, timestamp)),
        "-i",
        str(source),
        "-frames:v",
        "1",
        "-q:v",
        "3",
        str(output_path),
    ]
    try:
        completed = runner(args, 20) if runner else subprocess.run(
            args,
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return False
    return int(getattr(completed, "returncode", 1) or 0) == 0 and output_path.is_file() and output_path.stat().st_size > 0


def _subtitle_profile(*, subtitle_streams: list[dict[str, Any]], height: int) -> dict[str, Any]:
    font_size = max(28, min(64, round(height * 0.038)))
    return {
        "embedded_subtitle_streams": len(subtitle_streams),
        "mode": "preserve_or_extract" if subtitle_streams else "auto",
        "style": {
            "font_size": font_size,
            "font_color": "white",
            "outline_color": "black",
            "outline_width": max(3, round(font_size * 0.12)),
            "position": "bottom_center",
        },
        "extraction_strategy": "ffmpeg_subtitle_stream" if subtitle_streams else "no_embedded_subtitles_detected",
    }


def _bgm_profile(*, audio_stream: dict[str, Any], duration_seconds: float) -> dict[str, Any]:
    has_audio = bool(audio_stream)
    sample_rate = _safe_int(audio_stream.get("sample_rate"), 0) if has_audio else 0
    channels = _safe_int(audio_stream.get("channels"), 0) if has_audio else 0
    rhythm = _rhythm_profile(duration_seconds=duration_seconds)
    return {
        "has_audio": has_audio,
        "sample_rate": sample_rate,
        "channels": channels,
        "bgm_style": "product_flash" if rhythm["tempo_label"] == "fast" else "clean_vlog",
        "bgm_volume_db": -18.0 if has_audio else -20.0,
        "original_audio_policy": "analyze_reference_audio_then_replace" if has_audio else "generate_or_select_bgm",
    }


def _rhythm_profile(*, duration_seconds: float) -> dict[str, Any]:
    duration = duration_seconds if duration_seconds > 0 else 20.0
    if duration <= 18:
        cut_interval = 1.15
        tempo_label = "fast"
    elif duration <= 35:
        cut_interval = 1.55
        tempo_label = "medium"
    else:
        cut_interval = 2.15
        tempo_label = "slow"
    segment_count = max(3, min(14, round(duration / cut_interval)))
    beat_interval = max(0.5, round(cut_interval / 2.0, 3))
    return {
        "tempo_label": tempo_label,
        "estimated_bpm": int(round(60.0 / beat_interval)),
        "cut_interval_seconds": round(cut_interval, 3),
        "beat_interval_seconds": beat_interval,
        "suggested_segment_count": segment_count,
        "beat_markers_seconds": [round(index * beat_interval, 3) for index in range(0, min(32, math.ceil(duration / beat_interval)))],
    }


def _timeline_template_from_rhythm(rhythm: Mapping[str, Any], *, duration_seconds: float) -> dict[str, Any]:
    segment_count = int(rhythm.get("suggested_segment_count") or 6)
    target_duration = max(5, min(60, round(duration_seconds or 20)))
    duration_each = round(target_duration / max(1, segment_count), 2)
    roles = ["opening_hero", "product_body_and_detail", "site_context", "product_body_and_detail"]
    blueprint = []
    for index in range(segment_count):
        role = roles[index % len(roles)]
        blueprint.append({
            "role": role,
            "duration_seconds": duration_each,
            "caption_hint": _caption_hint(role, index=index),
        })
    return {
        "timeline_kind": f"reference_{rhythm.get('tempo_label', 'medium')}_template",
        "target_duration_seconds": target_duration,
        "transition_policy": {
            "style": "reference_rhythm_hard_cuts",
            "max_single_shot_seconds": max(1.2, min(4.0, duration_each + 0.6)),
        },
        "source_selection_policy": {
            "prefer": ["opening_hero", "product_body_and_detail", "site_context"],
            "avoid": ["long_static_repetition", "dark_unreadable_surface"],
        },
        "segment_blueprint": blueprint,
        "rhythm": dict(rhythm),
    }


def _style_suggestions(
    *,
    duration_seconds: float,
    width: int,
    height: int,
    fps: int,
    subtitle_profile: Mapping[str, Any],
    bgm_profile: Mapping[str, Any],
) -> dict[str, Any]:
    subtitle_style = subtitle_profile.get("style") if isinstance(subtitle_profile.get("style"), Mapping) else {}
    return {
        "video": {
            "target_duration_seconds": max(5, min(60, round(duration_seconds or 20))),
            "aspect_ratio": _aspect_ratio(width, height),
            "resolution": _resolution(width, height),
            "fps": fps,
        },
        "subtitle": {
            "mode": subtitle_profile.get("mode") or "auto",
            "font_size": subtitle_style.get("font_size"),
            "font_color": subtitle_style.get("font_color"),
            "outline_color": subtitle_style.get("outline_color"),
            "outline_width": subtitle_style.get("outline_width"),
            "position": subtitle_style.get("position"),
        },
        "cover": {
            "enabled": True,
        },
        "audio": {
            "bgm_style": bgm_profile.get("bgm_style"),
            "bgm_volume_db": bgm_profile.get("bgm_volume_db"),
        },
    }


def _warnings(*, probe: Mapping[str, Any], video_stream: Mapping[str, Any], audio_stream: Mapping[str, Any]) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    if not probe:
        warnings.append({"code": "ffprobe_unavailable_or_failed", "message": "未能读取真实媒体信息，已使用启发式样板分析。"})
    if probe and not video_stream:
        warnings.append({"code": "video_stream_missing", "message": "未检测到视频流，风格建议可能不准确。"})
    if probe and not audio_stream:
        warnings.append({"code": "audio_stream_missing", "message": "未检测到音频流，BGM 建议将使用默认策略。"})
    return warnings


def _first_stream(probe: Mapping[str, Any], codec_type: str) -> dict[str, Any]:
    streams = _streams(probe, codec_type)
    return streams[0] if streams else {}


def _streams(probe: Mapping[str, Any], codec_type: str) -> list[dict[str, Any]]:
    values = probe.get("streams") if isinstance(probe, Mapping) else []
    return [dict(item) for item in values or [] if isinstance(item, Mapping) and item.get("codec_type") == codec_type]


def _duration_seconds(probe: Mapping[str, Any], video_stream: Mapping[str, Any]) -> float:
    format_data = probe.get("format") if isinstance(probe.get("format"), Mapping) else {}
    for value in [format_data.get("duration"), video_stream.get("duration")]:
        try:
            parsed = float(value)
        except (TypeError, ValueError):
            continue
        if parsed > 0:
            return parsed
    return 20.0


def _fps(video_stream: Mapping[str, Any]) -> int:
    for key in ("avg_frame_rate", "r_frame_rate"):
        value = str(video_stream.get(key) or "")
        if "/" in value:
            num, den = value.split("/", 1)
            try:
                parsed = float(num) / max(1.0, float(den))
            except ValueError:
                continue
            if parsed > 0:
                return max(1, min(120, round(parsed)))
    return 30


def _aspect_ratio(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return "9:16"
    ratio = width / height
    candidates = {"9:16": 9 / 16, "16:9": 16 / 9, "1:1": 1.0, "4:5": 4 / 5}
    return min(candidates, key=lambda key: abs(candidates[key] - ratio))


def _resolution(width: int, height: int) -> str:
    if width <= 0 or height <= 0:
        return "720x1280"
    return f"{width}x{height}"


def _cover_timestamp(duration_seconds: float) -> float:
    if duration_seconds <= 1:
        return 0.0
    return round(min(max(duration_seconds * 0.16, 1.0), max(0.0, duration_seconds - 0.5)), 3)


def _caption_hint(role: str, *, index: int) -> str:
    if index == 0:
        return "用参考视频开场节奏建立吸引力"
    return {
        "opening_hero": "展示主体完整画面",
        "product_body_and_detail": "强调细节、质感或卖点",
        "site_context": "交代现场环境与使用场景",
    }.get(role, "补充画面信息")


def _safe_int(value: Any, default: int) -> int:
    try:
        return int(float(value))
    except (TypeError, ValueError):
        return default


def _media_binary(name: str) -> str:
    local = Path(__file__).resolve().parents[2] / "packages" / "ffmpeg" / "bin" / f"{name}.exe"
    if local.is_file():
        return str(local)
    return shutil.which(name) or ""
