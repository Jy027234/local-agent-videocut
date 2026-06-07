from __future__ import annotations

import json
import platform
import shutil
import subprocess
import wave
from pathlib import Path
from typing import Any, Callable, Mapping

from smart_video_cut.moss_tts import synthesize_moss_tts


VOICE_ADAPTER_RESULT_SCHEMA = "smart_video_cut.local.voice_adapter_result.v0"
SYSTEM_TTS_VOICES_SCHEMA = "smart_video_cut.local.system_tts_voices.v0"
SYSTEM_TTS_PREVIEW_SCHEMA = "smart_video_cut.local.system_tts_preview.v0"
DEFAULT_AD_VOICEOVER_TEXT = "这是一段本地智能剪辑生成的广告旁白。"

MossSynthesizer = Callable[..., dict[str, Any]]
SystemTtsSynthesizer = Callable[..., dict[str, Any]]
SystemTtsVoiceCommandRunner = Callable[[list[str], int], Any]


def prepare_voiceover(
    *,
    provider: str,
    voice_mode: str,
    execute_real_render: bool,
    allow_edge_tts: bool,
    voiceover_text: str | None,
    voice_settings: Mapping[str, Any] | None,
    artifact_root: str | Path,
    default_voiceover_text: str = DEFAULT_AD_VOICEOVER_TEXT,
    moss_synthesizer: MossSynthesizer | None = None,
    system_tts_synthesizer: SystemTtsSynthesizer | None = None,
) -> dict[str, Any]:
    """Prepare voiceover inputs for the renderer through a plugin-style adapter."""
    selected_provider = str(provider or "edge_tts").strip()
    selected_mode = str(voice_mode or "generated_male_ad_copy").strip()
    settings = dict(voice_settings or {})
    adapter_id = _adapter_id(provider=selected_provider, voice_mode=selected_mode)
    selected_text = "" if adapter_id == "voice.none" else str(voiceover_text or default_voiceover_text)
    result = _base_result(
        adapter_id=adapter_id,
        provider=selected_provider,
        voice_mode=selected_mode,
        voiceover_text=selected_text,
        execute_real_render=execute_real_render,
    )

    if adapter_id == "voice.none":
        result.update({
            "ok": True,
            "skipped": True,
            "reason": "voice_disabled",
        })
        return result
    if adapter_id == "voice.edge_tts":
        delegated = execute_real_render and allow_edge_tts
        result.update({
            "ok": True,
            "skipped": not delegated,
            "reason": "delegated_to_toolkit_edge_tts"
            if delegated
            else ("plan_only" if not execute_real_render else "edge_tts_not_allowed"),
            "renderer_allow_edge_tts": delegated,
        })
        return result
    if adapter_id == "voice.moss_tts_nano":
        moss_result = generate_moss_voiceover(
            execute_real_render=execute_real_render,
            voiceover_text=selected_text,
            voice_settings=settings,
            artifact_root=Path(artifact_root),
            moss_synthesizer=moss_synthesizer,
        )
        result.update({
            "ok": moss_result.get("ok") is True or moss_result.get("skipped") is True,
            "skipped": moss_result.get("skipped") is True,
            "reason": str(moss_result.get("reason") or moss_result.get("stage") or ""),
            "audio_path": moss_result.get("audio_path"),
            "renderer_voiceover_audio_input": moss_result.get("audio_path") if moss_result.get("ok") is True else None,
            "moss_tts_result": moss_result,
        })
        return result
    if adapter_id == "voice.system_tts":
        system_result = generate_system_tts_voiceover(
            execute_real_render=execute_real_render,
            voiceover_text=selected_text,
            voice_settings=settings,
            artifact_root=Path(artifact_root),
            system_tts_synthesizer=system_tts_synthesizer,
        )
        result.update(_audio_adapter_update(system_result, result_key="system_tts_result"))
        return result
    if adapter_id == "voice.fixture":
        fixture_result = generate_fixture_voiceover(
            execute_real_render=execute_real_render,
            voiceover_text=selected_text,
            voice_settings=settings,
            artifact_root=Path(artifact_root),
        )
        result.update(_audio_adapter_update(fixture_result, result_key="fixture_result"))
        return result
    result.update({
        "ok": False,
        "skipped": True,
        "reason": "adapter_not_executable_yet",
    })
    return result


def generate_moss_voiceover(
    *,
    execute_real_render: bool,
    voiceover_text: str,
    voice_settings: Mapping[str, Any] | None,
    artifact_root: Path,
    moss_synthesizer: MossSynthesizer | None = None,
) -> dict[str, Any]:
    """Generate MOSS voiceover audio when the MOSS adapter is selected."""
    if not execute_real_render:
        return {"ok": False, "skipped": True, "reason": "provider_not_selected_or_plan_only"}
    settings = dict(voice_settings or {})
    output_path = artifact_root / "_moss_tts_voiceover" / "voiceover.wav"
    synthesizer = moss_synthesizer or synthesize_moss_tts
    return synthesizer(
        text=voiceover_text,
        output_audio_path=output_path,
        voice=str(settings.get("moss_voice") or "Zhiming"),
        prompt_audio_path=_optional_existing_path(settings.get("prompt_audio_path")),
        cpu_threads=4,
        max_new_frames=375,
        sample_mode=str(settings.get("sample_mode") or "fixed"),
        text_temperature=_safe_float(settings.get("text_temperature"), default=0.8),
        audio_temperature=_safe_float(settings.get("audio_temperature"), default=0.6),
        seed=_optional_int(settings.get("seed")),
    )


def generate_system_tts_voiceover(
    *,
    execute_real_render: bool,
    voiceover_text: str,
    voice_settings: Mapping[str, Any] | None,
    artifact_root: Path,
    system_tts_synthesizer: SystemTtsSynthesizer | None = None,
) -> dict[str, Any]:
    """Generate voiceover audio through the host operating system TTS."""
    if not execute_real_render:
        return {"ok": False, "skipped": True, "reason": "provider_not_selected_or_plan_only"}
    settings = dict(voice_settings or {})
    output_path = artifact_root / "_system_tts_voiceover" / "voiceover.wav"
    synthesizer = system_tts_synthesizer or _synthesize_system_tts
    return synthesizer(
        text=voiceover_text,
        output_audio_path=output_path,
        voice_name=str(settings.get("system_voice") or settings.get("voice_name") or ""),
        rate=_safe_int(settings.get("system_rate")),
        volume=_safe_int(settings.get("system_volume")),
        timeout_seconds=int(settings.get("system_timeout_seconds") or 60),
    )


def list_system_tts_voices(
    *,
    command_runner: SystemTtsVoiceCommandRunner | None = None,
    timeout_seconds: int = 15,
) -> dict[str, Any]:
    """List installed host TTS voices for UI selection."""
    if command_runner is None:
        system = platform.system().casefold()
        if system == "darwin":
            return _list_macos_say_voices(timeout_seconds=timeout_seconds)
        if system == "linux":
            return _list_espeak_voices(timeout_seconds=timeout_seconds)

    command = _system_tts_voice_list_command()
    runner = command_runner or _run_system_tts_voice_list_command
    try:
        completed = runner(_powershell_command_args(command), max(5, int(timeout_seconds or 15)))
    except FileNotFoundError:
        return _system_tts_voices_result(ok=False, reason="powershell_not_found")
    except Exception as exc:
        return _system_tts_voices_result(ok=False, reason=exc.__class__.__name__, detail=str(exc)[-1000:])

    returncode = int(getattr(completed, "returncode", 1) or 0)
    stdout = str(getattr(completed, "stdout", "") or "")
    stderr = str(getattr(completed, "stderr", "") or "")
    if returncode != 0:
        return _system_tts_voices_result(
            ok=False,
            reason="system_tts_voice_list_failed",
            returncode=returncode,
            stderr_tail=stderr[-1200:],
        )
    try:
        payload = json.loads(_extract_json_payload(stdout))
    except json.JSONDecodeError as exc:
        return _system_tts_voices_result(
            ok=False,
            reason="system_tts_voice_json_parse_failed",
            detail=str(exc),
            stdout_tail=stdout[-1200:],
        )

    raw_voices = payload.get("voices") if isinstance(payload, Mapping) else []
    if isinstance(raw_voices, Mapping):
        raw_voices = [raw_voices]
    voices = [_normalize_system_tts_voice(voice) for voice in raw_voices if isinstance(voice, Mapping)]
    default_voice = str(payload.get("default_voice") or "") if isinstance(payload, Mapping) else ""
    return _system_tts_voices_result(
        ok=True,
        reason="system_tts_voices_ready",
        voices=voices,
        default_voice=default_voice,
        returncode=returncode,
        platform_name=_system_tts_platform_name(),
    )


def generate_system_tts_preview(
    *,
    text: str,
    output_dir: str | Path,
    voice_name: str = "",
    rate: int | None = None,
    volume: int | None = None,
    synthesizer: SystemTtsSynthesizer | None = None,
) -> dict[str, Any]:
    """Generate a short local System TTS preview audio file for the web UI."""
    root = Path(output_dir) if output_dir else Path.cwd() / "workspace" / "system-tts-preview"
    output_path = root / "system_tts_preview.wav"
    selected_synthesizer = synthesizer or _synthesize_system_tts
    result = selected_synthesizer(
        text=text or "这是一段系统 TTS 试听语音。",
        output_audio_path=output_path,
        voice_name=voice_name,
        rate=rate,
        volume=volume,
        timeout_seconds=60,
    )
    return {
        "schema": SYSTEM_TTS_PREVIEW_SCHEMA,
        "ok": result.get("ok") is True,
        "reason": result.get("reason") or "",
        "audio_path": result.get("audio_path"),
        "platform": result.get("platform") or _system_tts_platform_name(),
        "voice_name": result.get("voice_name") or voice_name,
        "text_preview": str(text or "")[:120],
        "synthesizer_result": result,
    }


def generate_fixture_voiceover(
    *,
    execute_real_render: bool,
    voiceover_text: str,
    voice_settings: Mapping[str, Any] | None,
    artifact_root: Path,
) -> dict[str, Any]:
    """Generate deterministic fixture audio without external TTS dependencies."""
    if not execute_real_render:
        return {"ok": False, "skipped": True, "reason": "provider_not_selected_or_plan_only"}
    settings = dict(voice_settings or {})
    duration = _safe_float(settings.get("fixture_duration_seconds"), default=1.0)
    sample_rate = max(8000, _safe_int(settings.get("fixture_sample_rate")) or 16000)
    output_path = artifact_root / "_fixture_voiceover" / "voiceover.wav"
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_silence_wav(output_path, duration_seconds=duration, sample_rate=sample_rate)
    return {
        "ok": output_path.is_file() and output_path.stat().st_size > 44,
        "stage": "synthesize",
        "reason": "fixture_silence_wav",
        "audio_path": str(output_path),
        "size_bytes": output_path.stat().st_size if output_path.is_file() else 0,
        "duration_seconds": duration,
        "sample_rate": sample_rate,
        "text_preview": str(voiceover_text or "")[:120],
    }


def legacy_moss_voiceover_result(voice_adapter_result: Mapping[str, Any]) -> dict[str, Any]:
    value = voice_adapter_result.get("moss_tts_result")
    if isinstance(value, dict):
        return value
    return {"ok": False, "skipped": True, "reason": "provider_not_selected_or_plan_only"}


def _audio_adapter_update(adapter_result: Mapping[str, Any], *, result_key: str) -> dict[str, Any]:
    return {
        "ok": adapter_result.get("ok") is True or adapter_result.get("skipped") is True,
        "skipped": adapter_result.get("skipped") is True,
        "reason": str(adapter_result.get("reason") or adapter_result.get("stage") or ""),
        "audio_path": adapter_result.get("audio_path"),
        "renderer_voiceover_audio_input": adapter_result.get("audio_path") if adapter_result.get("ok") is True else None,
        result_key: dict(adapter_result),
    }


def _synthesize_system_tts(
    *,
    text: str,
    output_audio_path: str | Path,
    voice_name: str = "",
    rate: int | None = None,
    volume: int | None = None,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    system = platform.system().casefold()
    if system == "windows":
        return _synthesize_windows_system_tts(
            text=text,
            output_audio_path=output_audio_path,
            voice_name=voice_name,
            rate=rate,
            volume=volume,
            timeout_seconds=timeout_seconds,
        )
    if system == "darwin":
        return _synthesize_macos_say_tts(
            text=text,
            output_audio_path=output_audio_path,
            voice_name=voice_name,
            rate=rate,
            volume=volume,
            timeout_seconds=timeout_seconds,
        )
    if system == "linux":
        return _synthesize_espeak_tts(
            text=text,
            output_audio_path=output_audio_path,
            voice_name=voice_name,
            rate=rate,
            volume=volume,
            timeout_seconds=timeout_seconds,
        )
    return {
        "ok": False,
        "stage": "preflight",
        "reason": "system_tts_platform_not_supported",
        "platform": _system_tts_platform_name(),
        "audio_path": None,
    }


def _synthesize_windows_system_tts(
    *,
    text: str,
    output_audio_path: str | Path,
    voice_name: str = "",
    rate: int | None = None,
    volume: int | None = None,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    output_path = Path(output_audio_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "text": str(text or DEFAULT_AD_VOICEOVER_TEXT),
        "output": str(output_path),
        "voice": voice_name,
        "rate": rate,
        "volume": volume,
    }
    command = _system_tts_powershell_command(payload)
    try:
        completed = subprocess.run(
            _powershell_command_args(command),
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(5, int(timeout_seconds or 60)),
        )
    except FileNotFoundError:
        return {
            "ok": False,
            "stage": "preflight",
            "reason": "powershell_not_found",
            "audio_path": None,
        }
    except Exception as exc:
        return {
            "ok": False,
            "stage": "synthesize",
            "reason": exc.__class__.__name__,
            "detail": str(exc)[-1000:],
            "audio_path": None,
        }
    output_ok = completed.returncode == 0 and output_path.is_file() and output_path.stat().st_size > 44
    return {
        "ok": output_ok,
        "stage": "synthesize",
        "reason": "system_tts_wav" if output_ok else "system_tts_failed",
        "audio_path": str(output_path) if output_ok else None,
        "size_bytes": output_path.stat().st_size if output_path.is_file() else 0,
        "command_returncode": completed.returncode,
        "stdout_tail": completed.stdout[-800:],
        "stderr_tail": completed.stderr[-1200:],
        "text_preview": str(text or "")[:120],
        "voice_name": voice_name,
        "platform": "windows",
    }


def _synthesize_macos_say_tts(
    *,
    text: str,
    output_audio_path: str | Path,
    voice_name: str = "",
    rate: int | None = None,
    volume: int | None = None,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    executable = shutil.which("say")
    if not executable:
        return {"ok": False, "stage": "preflight", "reason": "macos_say_not_found", "platform": "darwin", "audio_path": None}
    output_path = Path(output_audio_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    args = [executable]
    if voice_name:
        args.extend(["-v", voice_name])
    if rate is not None:
        args.extend(["-r", str(max(90, min(300, 180 + int(rate) * 12)))])
    args.extend(["-o", str(output_path), str(text or DEFAULT_AD_VOICEOVER_TEXT)])
    return _run_system_tts_command(
        args=args,
        output_path=output_path,
        reason_ok="macos_say_audio",
        reason_failed="macos_say_failed",
        voice_name=voice_name,
        platform_name="darwin",
        timeout_seconds=timeout_seconds,
    )


def _synthesize_espeak_tts(
    *,
    text: str,
    output_audio_path: str | Path,
    voice_name: str = "",
    rate: int | None = None,
    volume: int | None = None,
    timeout_seconds: int = 60,
) -> dict[str, Any]:
    executable = shutil.which("espeak") or shutil.which("espeak-ng")
    if not executable:
        return {"ok": False, "stage": "preflight", "reason": "espeak_not_found", "platform": "linux", "audio_path": None}
    output_path = Path(output_audio_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    args = [executable, "-w", str(output_path)]
    if voice_name:
        args.extend(["-v", voice_name])
    if rate is not None:
        args.extend(["-s", str(max(80, min(320, 175 + int(rate) * 12)))])
    if volume is not None:
        args.extend(["-a", str(max(0, min(200, int(volume) * 2)))])
    args.append(str(text or DEFAULT_AD_VOICEOVER_TEXT))
    return _run_system_tts_command(
        args=args,
        output_path=output_path,
        reason_ok="espeak_wav",
        reason_failed="espeak_failed",
        voice_name=voice_name,
        platform_name="linux",
        timeout_seconds=timeout_seconds,
    )


def _run_system_tts_command(
    *,
    args: list[str],
    output_path: Path,
    reason_ok: str,
    reason_failed: str,
    voice_name: str,
    platform_name: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            args,
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(5, int(timeout_seconds or 60)),
        )
    except Exception as exc:
        return {
            "ok": False,
            "stage": "synthesize",
            "reason": exc.__class__.__name__,
            "platform": platform_name,
            "detail": str(exc)[-1000:],
            "audio_path": None,
        }
    output_ok = completed.returncode == 0 and output_path.is_file() and output_path.stat().st_size > 44
    return {
        "ok": output_ok,
        "stage": "synthesize",
        "reason": reason_ok if output_ok else reason_failed,
        "platform": platform_name,
        "audio_path": str(output_path) if output_ok else None,
        "size_bytes": output_path.stat().st_size if output_path.is_file() else 0,
        "command_returncode": completed.returncode,
        "stdout_tail": completed.stdout[-800:],
        "stderr_tail": completed.stderr[-1200:],
        "voice_name": voice_name,
    }


def _system_tts_powershell_command(payload: Mapping[str, Any]) -> str:
    json_payload = json.dumps(dict(payload), ensure_ascii=False)
    return f"""
$ErrorActionPreference = 'Stop'
$payload = '{_escape_single_quoted(json_payload)}' | ConvertFrom-Json
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {{
  if ($payload.voice) {{
    $synth.SelectVoice([string]$payload.voice)
  }}
  if ($null -ne $payload.rate) {{
    $synth.Rate = [Math]::Max(-10, [Math]::Min(10, [int]$payload.rate))
  }}
  if ($null -ne $payload.volume) {{
    $synth.Volume = [Math]::Max(0, [Math]::Min(100, [int]$payload.volume))
  }}
  $synth.SetOutputToWaveFile([string]$payload.output)
  $synth.Speak([string]$payload.text)
}} finally {{
  $synth.Dispose()
}}
"""


def _list_macos_say_voices(*, timeout_seconds: int) -> dict[str, Any]:
    executable = shutil.which("say")
    if not executable:
        return _system_tts_voices_result(ok=False, reason="macos_say_not_found", platform_name="darwin")
    try:
        completed = subprocess.run(
            [executable, "-v", "?"],
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(5, int(timeout_seconds or 15)),
        )
    except Exception as exc:
        return _system_tts_voices_result(ok=False, reason=exc.__class__.__name__, detail=str(exc)[-1000:], platform_name="darwin")
    if completed.returncode != 0:
        return _system_tts_voices_result(
            ok=False,
            reason="macos_say_voice_list_failed",
            returncode=completed.returncode,
            stderr_tail=completed.stderr[-1200:],
            platform_name="darwin",
        )
    voices = []
    for line in completed.stdout.splitlines():
        parts = line.split()
        if len(parts) < 2:
            continue
        voices.append({
            "name": parts[0],
            "culture": parts[1],
            "gender": "",
            "age": "",
            "enabled": True,
            "description": " ".join(parts[2:]).strip("# "),
        })
    return _system_tts_voices_result(
        ok=True,
        reason="system_tts_voices_ready",
        voices=voices,
        platform_name="darwin",
    )


def _list_espeak_voices(*, timeout_seconds: int) -> dict[str, Any]:
    executable = shutil.which("espeak") or shutil.which("espeak-ng")
    if not executable:
        return _system_tts_voices_result(ok=False, reason="espeak_not_found", platform_name="linux")
    try:
        completed = subprocess.run(
            [executable, "--voices"],
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=max(5, int(timeout_seconds or 15)),
        )
    except Exception as exc:
        return _system_tts_voices_result(ok=False, reason=exc.__class__.__name__, detail=str(exc)[-1000:], platform_name="linux")
    if completed.returncode != 0:
        return _system_tts_voices_result(
            ok=False,
            reason="espeak_voice_list_failed",
            returncode=completed.returncode,
            stderr_tail=completed.stderr[-1200:],
            platform_name="linux",
        )
    voices = []
    for line in completed.stdout.splitlines()[1:]:
        parts = line.split()
        if len(parts) < 4:
            continue
        voices.append({
            "name": parts[3],
            "culture": parts[1],
            "gender": parts[2],
            "age": "",
            "enabled": True,
            "description": " ".join(parts[4:]),
        })
    return _system_tts_voices_result(
        ok=True,
        reason="system_tts_voices_ready",
        voices=voices,
        platform_name="linux",
    )


def _system_tts_voice_list_command() -> str:
    return """
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Speech
$synth = New-Object System.Speech.Synthesis.SpeechSynthesizer
try {
  $voices = @($synth.GetInstalledVoices() | ForEach-Object {
    $info = $_.VoiceInfo
    [pscustomobject]@{
      name = [string]$info.Name
      culture = [string]$info.Culture.Name
      gender = [string]$info.Gender
      age = [string]$info.Age
      enabled = [bool]$_.Enabled
      description = [string]$info.Description
    }
  })
  [pscustomobject]@{
    ok = $true
    available = $true
    default_voice = [string]$synth.Voice.Name
    voices = $voices
  } | ConvertTo-Json -Depth 5 -Compress
} finally {
  $synth.Dispose()
}
"""


def _run_system_tts_voice_list_command(args: list[str], timeout_seconds: int) -> Any:
    return subprocess.run(
        args,
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
    )


def _powershell_command_args(command: str) -> list[str]:
    for executable in ("powershell.exe", "powershell", "pwsh.exe", "pwsh"):
        if shutil.which(executable):
            return [executable, "-NoProfile", "-NonInteractive", "-Command", command]
    return ["powershell", "-NoProfile", "-NonInteractive", "-Command", command]


def _escape_single_quoted(value: str) -> str:
    return value.replace("'", "''")


def _extract_json_payload(stdout: str) -> str:
    text = str(stdout or "").strip()
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return text


def _normalize_system_tts_voice(voice: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "name": str(voice.get("name") or ""),
        "culture": str(voice.get("culture") or ""),
        "gender": str(voice.get("gender") or ""),
        "age": str(voice.get("age") or ""),
        "enabled": voice.get("enabled") is not False,
        "description": str(voice.get("description") or ""),
    }


def _system_tts_voices_result(
    *,
    ok: bool,
    reason: str,
    voices: list[dict[str, Any]] | None = None,
    default_voice: str = "",
    returncode: int | None = None,
    stderr_tail: str = "",
    stdout_tail: str = "",
    detail: str = "",
    platform_name: str = "",
) -> dict[str, Any]:
    voice_list = voices or []
    return {
        "schema": SYSTEM_TTS_VOICES_SCHEMA,
        "ok": ok,
        "available": ok,
        "reason": reason,
        "platform": platform_name or _system_tts_platform_name(),
        "default_voice": default_voice,
        "voice_count": len(voice_list),
        "voices": voice_list,
        "returncode": returncode,
        "stderr_tail": stderr_tail,
        "stdout_tail": stdout_tail,
        "detail": detail,
    }


def _system_tts_platform_name() -> str:
    return platform.system().casefold() or "unknown"


def _write_silence_wav(path: Path, *, duration_seconds: float, sample_rate: int) -> None:
    frame_count = max(1, int(sample_rate * max(0.1, duration_seconds)))
    silence = b"\x00\x00" * frame_count
    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(silence)


def _base_result(
    *,
    adapter_id: str,
    provider: str,
    voice_mode: str,
    voiceover_text: str,
    execute_real_render: bool,
) -> dict[str, Any]:
    return {
        "schema": VOICE_ADAPTER_RESULT_SCHEMA,
        "adapter_id": adapter_id,
        "provider": provider,
        "voice_mode": voice_mode,
        "execute_real_render": execute_real_render,
        "ok": False,
        "skipped": False,
        "reason": "",
        "voiceover_text": voiceover_text,
        "audio_path": None,
        "renderer_voiceover_audio_input": None,
        "renderer_allow_edge_tts": False,
    }


def _adapter_id(*, provider: str, voice_mode: str) -> str:
    normalized_mode = voice_mode.strip().casefold()
    normalized_provider = provider.strip().casefold()
    if normalized_mode == "none" or normalized_provider == "none":
        return "voice.none"
    if normalized_provider in {"moss_tts_nano", "moss", "moss-tts-nano"}:
        return "voice.moss_tts_nano"
    if normalized_provider in {"system_tts", "system"}:
        return "voice.system_tts"
    if normalized_provider in {"fixture", "fixture_voice"}:
        return "voice.fixture"
    return "voice.edge_tts"


def _optional_existing_path(value: Any) -> Path | None:
    text = str(value or "").strip()
    if not text:
        return None
    path = Path(text)
    return path if path.is_file() else None


def _safe_float(value: Any, *, default: float) -> float:
    try:
        return max(0.0, float(value))
    except (TypeError, ValueError):
        return default


def _optional_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    if value in {None, ""}:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
