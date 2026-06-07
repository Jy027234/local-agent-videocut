from __future__ import annotations

import math
import wave
from pathlib import Path
from typing import Any, Mapping

from smart_video_cut.bgm_library import select_bgm_from_library


BGM_ADAPTER_RESULT_SCHEMA = "smart_video_cut.local.bgm_adapter_result.v0"


def prepare_bgm(
    *,
    audio_settings: Mapping[str, Any] | None,
    execute_real_render: bool,
    artifact_root: str | Path | None = None,
) -> dict[str, Any]:
    """Prepare BGM inputs for the renderer through a plugin-style adapter."""
    settings = dict(audio_settings or {})
    adapter_id = _adapter_id(settings)
    bgm_style = str(settings.get("bgm_style") or "upbeat_instrumental")
    start_seconds = _safe_float(settings.get("bgm_start_seconds"), default=0.0)
    volume_db = _safe_float(settings.get("bgm_volume_db"), default=-18.0, allow_negative=True)
    local_audio_path = _optional_existing_path(settings.get("bgm_audio_path"))
    requested_audio_path = str(settings.get("bgm_audio_path") or "").strip()
    result = {
        "schema": BGM_ADAPTER_RESULT_SCHEMA,
        "adapter_id": adapter_id,
        "bgm_style": bgm_style,
        "ok": True,
        "skipped": False,
        "reason": "",
        "warnings": [],
        "local_bgm_audio_path": str(local_audio_path) if local_audio_path else None,
        "requested_bgm_audio_path": requested_audio_path,
        "bgm_start_seconds": start_seconds,
        "bgm_volume_db": volume_db,
        "renderer_bgm_enabled": adapter_id != "bgm.none",
        "renderer_bgm_audio_input": None,
        "renderer_bgm_start_seconds": start_seconds,
    }

    if adapter_id == "bgm.none":
        result.update({
            "skipped": True,
            "reason": "bgm_disabled",
            "renderer_bgm_enabled": False,
        })
        return result
    if adapter_id == "bgm.local_generated":
        generated_result = generate_local_bgm(
            audio_settings=settings,
            execute_real_render=execute_real_render,
            artifact_root=Path(artifact_root) if artifact_root is not None else None,
        )
        audio_path = generated_result.get("audio_path")
        result.update({
            "ok": generated_result.get("ok") is True or generated_result.get("skipped") is True,
            "skipped": generated_result.get("skipped") is True,
            "reason": str(generated_result.get("reason") or ""),
            "local_bgm_audio_path": audio_path,
            "renderer_bgm_enabled": True,
            "renderer_bgm_audio_input": audio_path if generated_result.get("ok") is True else None,
            "local_generated_bgm_result": generated_result,
        })
        if generated_result.get("warning"):
            result["warnings"] = [generated_result["warning"]]
        return result
    if adapter_id == "bgm.local_music_model":
        model_result = generate_local_music_model_bgm(
            audio_settings=settings,
            execute_real_render=execute_real_render,
            artifact_root=Path(artifact_root) if artifact_root is not None else None,
        )
        audio_path = model_result.get("audio_path")
        result.update({
            "ok": model_result.get("ok") is True or model_result.get("skipped") is True,
            "skipped": model_result.get("skipped") is True,
            "reason": str(model_result.get("reason") or ""),
            "local_bgm_audio_path": audio_path,
            "renderer_bgm_enabled": True,
            "renderer_bgm_audio_input": audio_path if model_result.get("ok") is True else None,
            "local_music_model_result": model_result,
        })
        if model_result.get("warning"):
            result["warnings"] = [model_result["warning"]]
        return result
    if adapter_id == "bgm.library":
        library_result = select_bgm_from_library(
            library_dir=settings.get("bgm_library_dir") or settings.get("library_dir") or "",
            query=str(settings.get("bgm_library_query") or settings.get("library_query") or ""),
            style=bgm_style,
        )
        audio_path = library_result.get("audio_path")
        result.update({
            "ok": library_result.get("ok") is True,
            "skipped": False,
            "reason": str(library_result.get("reason") or ""),
            "local_bgm_audio_path": audio_path,
            "renderer_bgm_enabled": True,
            "renderer_bgm_audio_input": audio_path if execute_real_render and library_result.get("ok") is True else None,
            "library_bgm_result": library_result,
        })
        if library_result.get("ok") is not True:
            result["warnings"] = [{
                "code": "bgm_library_audio_missing",
                "message": "未能从本地 BGM 素材库选出可用音频。",
                "path": str(settings.get("bgm_library_dir") or settings.get("library_dir") or ""),
            }]
        return result
    if adapter_id == "bgm.local_audio":
        if local_audio_path:
            result.update({
                "reason": "local_audio_ready" if execute_real_render else "local_audio_plan_only",
                "renderer_bgm_audio_input": str(local_audio_path) if execute_real_render else None,
            })
            return result
        result["reason"] = "local_audio_missing"
        result["warnings"] = [{
            "code": "missing_bgm_audio_path",
            "message": "选择了本地 BGM，但 bgm_audio_path 为空或文件不可读。",
            "path": requested_audio_path,
        }]
        return result
    result["reason"] = "bgm_style_policy_only"
    return result


def generate_local_music_model_bgm(
    *,
    audio_settings: Mapping[str, Any] | None,
    execute_real_render: bool,
    artifact_root: Path | None,
) -> dict[str, Any]:
    settings = dict(audio_settings or {})
    model_id = str(settings.get("local_music_model_id") or settings.get("music_model_id") or "procedural_music_model_v0")
    generated = generate_local_bgm(
        audio_settings={
            **settings,
            "generated_mood": settings.get("generated_mood") or settings.get("bgm_style") or "product_flash",
        },
        execute_real_render=execute_real_render,
        artifact_root=artifact_root,
    )
    generated.update({
        "adapter_id": "bgm.local_music_model",
        "model_id": model_id,
        "reason": "local_music_model_plan_only" if generated.get("skipped") else "local_music_model_wav",
    })
    return generated


def generate_local_bgm(
    *,
    audio_settings: Mapping[str, Any] | None,
    execute_real_render: bool,
    artifact_root: Path | None,
) -> dict[str, Any]:
    """Generate a deterministic local WAV bed for the local_generated adapter."""
    settings = dict(audio_settings or {})
    if not execute_real_render:
        return {"ok": False, "skipped": True, "reason": "local_generated_plan_only"}
    if artifact_root is None:
        return {
            "ok": False,
            "skipped": False,
            "reason": "artifact_root_required",
            "warning": {
                "code": "artifact_root_required",
                "message": "生成本地 BGM 需要 artifact_root 才能写入 WAV 文件。",
            },
        }
    duration = _safe_float(settings.get("generated_duration_seconds"), default=12.0)
    sample_rate = max(8000, _safe_int(settings.get("generated_sample_rate")) or 22050)
    mood = str(settings.get("generated_mood") or settings.get("bgm_generated_mood") or "upbeat_instrumental")
    output_path = artifact_root / "_local_generated_bgm" / "bgm.wav"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_procedural_bgm_wav(
        output_path,
        duration_seconds=max(1.0, min(duration, 120.0)),
        sample_rate=sample_rate,
        mood=mood,
    )
    return {
        "ok": output_path.is_file() and output_path.stat().st_size > 44,
        "skipped": False,
        "reason": "local_generated_bgm_wav",
        "audio_path": str(output_path),
        "size_bytes": output_path.stat().st_size if output_path.is_file() else 0,
        "duration_seconds": max(1.0, min(duration, 120.0)),
        "sample_rate": sample_rate,
        "mood": mood,
    }


def _adapter_id(settings: Mapping[str, Any]) -> str:
    bgm_style = str(settings.get("bgm_style") or "upbeat_instrumental").strip().casefold()
    if bgm_style == "none":
        return "bgm.none"
    if bgm_style in {"local_audio", "user_music", "custom_audio"} or str(settings.get("bgm_audio_path") or "").strip():
        return "bgm.local_audio"
    if bgm_style in {"library", "local_library", "material_library"} or str(settings.get("bgm_library_dir") or "").strip():
        return "bgm.library"
    if bgm_style in {"local_music_model", "music_model"}:
        return "bgm.local_music_model"
    if bgm_style in {"local_generated", "generated_music", "ai_music"}:
        return "bgm.local_generated"
    return "bgm.generated_placeholder"


def _optional_existing_path(value: Any) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    path = Path(text)
    return path if path.is_file() else None


def _safe_float(value: Any, *, default: float, allow_negative: bool = False) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return default
    if allow_negative:
        return parsed
    return max(0.0, parsed)


def _safe_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _write_procedural_bgm_wav(
    path: Path,
    *,
    duration_seconds: float,
    sample_rate: int,
    mood: str,
) -> None:
    frame_count = max(1, int(duration_seconds * sample_rate))
    frequencies = _mood_frequencies(mood)
    bpm = 118.0 if "upbeat" in mood or "flash" in mood else 82.0
    beat_seconds = 60.0 / bpm
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        for index in range(frame_count):
            t = index / sample_rate
            beat_index = int(t / beat_seconds) % len(frequencies)
            freq = frequencies[beat_index]
            phase = t % beat_seconds
            envelope = 0.35 + 0.65 * max(0.0, 1.0 - phase / beat_seconds)
            lead = math.sin(2.0 * math.pi * freq * t) * 0.15 * envelope
            pad = math.sin(2.0 * math.pi * (freq / 2.0) * t) * 0.08
            kick = math.sin(2.0 * math.pi * 58.0 * phase) * math.exp(-18.0 * phase) * 0.22
            sample = max(-0.85, min(0.85, lead + pad + kick))
            wav.writeframesraw(int(sample * 32767).to_bytes(2, byteorder="little", signed=True))


def _mood_frequencies(mood: str) -> tuple[float, float, float, float]:
    normalized = mood.strip().casefold()
    if "ambient" in normalized or "calm" in normalized:
        return (220.0, 277.18, 329.63, 277.18)
    if "premium" in normalized or "cinematic" in normalized:
        return (196.0, 246.94, 293.66, 392.0)
    return (261.63, 329.63, 392.0, 523.25)
