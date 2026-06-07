from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from smart_video_cut.voice_adapters import (
    generate_system_tts_preview,
    legacy_moss_voiceover_result,
    list_system_tts_voices,
    prepare_voiceover,
)


def test_voice_none_disables_text_and_renderer_inputs(tmp_path: Path) -> None:
    result = prepare_voiceover(
        provider="none",
        voice_mode="none",
        execute_real_render=True,
        allow_edge_tts=True,
        voiceover_text="不应使用",
        voice_settings={},
        artifact_root=tmp_path,
        default_voiceover_text="默认旁白",
    )

    assert result["ok"] is True
    assert result["adapter_id"] == "voice.none"
    assert result["voiceover_text"] == ""
    assert result["renderer_allow_edge_tts"] is False
    assert result["renderer_voiceover_audio_input"] is None
    assert legacy_moss_voiceover_result(result)["reason"] == "provider_not_selected_or_plan_only"


def test_edge_tts_adapter_delegates_to_toolkit_when_allowed(tmp_path: Path) -> None:
    result = prepare_voiceover(
        provider="edge_tts",
        voice_mode="generated_male_ad_copy",
        execute_real_render=True,
        allow_edge_tts=True,
        voiceover_text="这是一段旁白",
        voice_settings={},
        artifact_root=tmp_path,
    )

    assert result["adapter_id"] == "voice.edge_tts"
    assert result["ok"] is True
    assert result["reason"] == "delegated_to_toolkit_edge_tts"
    assert result["renderer_allow_edge_tts"] is True
    assert result["renderer_voiceover_audio_input"] is None


def test_moss_adapter_skips_generation_in_plan_only(tmp_path: Path) -> None:
    result = prepare_voiceover(
        provider="moss_tts_nano",
        voice_mode="generated_male_ad_copy",
        execute_real_render=False,
        allow_edge_tts=True,
        voiceover_text="计划模式旁白",
        voice_settings={},
        artifact_root=tmp_path,
    )

    assert result["adapter_id"] == "voice.moss_tts_nano"
    assert result["ok"] is True
    assert result["skipped"] is True
    assert result["renderer_voiceover_audio_input"] is None
    assert legacy_moss_voiceover_result(result)["skipped"] is True


def test_moss_adapter_generates_audio_for_real_render(tmp_path: Path) -> None:
    captured = {}

    def fake_synthesizer(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "audio_path": str(kwargs["output_audio_path"]),
            "voice": kwargs["voice"],
        }

    prompt = tmp_path / "prompt.wav"
    prompt.write_bytes(b"prompt")
    result = prepare_voiceover(
        provider="moss_tts_nano",
        voice_mode="generated_male_ad_copy",
        execute_real_render=True,
        allow_edge_tts=False,
        voiceover_text="真实渲染旁白",
        voice_settings={
            "moss_voice": "Zhiming",
            "prompt_audio_path": str(prompt),
            "sample_mode": "greedy",
            "text_temperature": 0.4,
            "audio_temperature": 0.5,
            "seed": 7,
        },
        artifact_root=tmp_path / "artifacts",
        moss_synthesizer=fake_synthesizer,
    )

    assert captured["text"] == "真实渲染旁白"
    assert captured["output_audio_path"] == tmp_path / "artifacts" / "_moss_tts_voiceover" / "voiceover.wav"
    assert captured["prompt_audio_path"] == prompt
    assert captured["voice"] == "Zhiming"
    assert result["ok"] is True
    assert result["audio_path"] == str(captured["output_audio_path"])
    assert result["renderer_voiceover_audio_input"] == str(captured["output_audio_path"])
    assert legacy_moss_voiceover_result(result)["ok"] is True


def test_fixture_adapter_generates_deterministic_wav_for_real_render(tmp_path: Path) -> None:
    result = prepare_voiceover(
        provider="fixture",
        voice_mode="generated_male_ad_copy",
        execute_real_render=True,
        allow_edge_tts=False,
        voiceover_text="fixture 旁白",
        voice_settings={"fixture_duration_seconds": 0.2, "fixture_sample_rate": 8000},
        artifact_root=tmp_path / "artifacts",
    )

    audio_path = Path(result["audio_path"])
    assert result["adapter_id"] == "voice.fixture"
    assert result["ok"] is True
    assert result["reason"] == "fixture_silence_wav"
    assert result["renderer_voiceover_audio_input"] == str(audio_path)
    assert audio_path.is_file()
    assert audio_path.stat().st_size > 44
    assert result["fixture_result"]["sample_rate"] == 8000


def test_fixture_adapter_accepts_legacy_fixture_voice_alias(tmp_path: Path) -> None:
    result = prepare_voiceover(
        provider="fixture_voice",
        voice_mode="generated_male_ad_copy",
        execute_real_render=False,
        allow_edge_tts=False,
        voiceover_text="legacy fixture alias",
        voice_settings={},
        artifact_root=tmp_path,
    )

    assert result["adapter_id"] == "voice.fixture"
    assert result["ok"] is True
    assert result["skipped"] is True


def test_system_tts_adapter_uses_injected_synthesizer(tmp_path: Path) -> None:
    captured = {}

    def fake_system_tts(**kwargs):
        captured.update(kwargs)
        output_path = Path(kwargs["output_audio_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"RIFF" + (b"\x00" * 80))
        return {
            "ok": True,
            "reason": "system_tts_wav",
            "audio_path": str(output_path),
            "voice_name": kwargs["voice_name"],
        }

    result = prepare_voiceover(
        provider="system_tts",
        voice_mode="generated_male_ad_copy",
        execute_real_render=True,
        allow_edge_tts=False,
        voiceover_text="系统语音旁白",
        voice_settings={"system_voice": "Microsoft Huihui Desktop", "system_rate": 1, "system_volume": 80},
        artifact_root=tmp_path / "artifacts",
        system_tts_synthesizer=fake_system_tts,
    )

    assert captured["text"] == "系统语音旁白"
    assert captured["output_audio_path"] == tmp_path / "artifacts" / "_system_tts_voiceover" / "voiceover.wav"
    assert captured["voice_name"] == "Microsoft Huihui Desktop"
    assert captured["rate"] == 1
    assert captured["volume"] == 80
    assert result["adapter_id"] == "voice.system_tts"
    assert result["ok"] is True
    assert result["renderer_voiceover_audio_input"] == str(captured["output_audio_path"])
    assert result["system_tts_result"]["reason"] == "system_tts_wav"


def test_system_tts_adapter_skips_in_plan_only(tmp_path: Path) -> None:
    result = prepare_voiceover(
        provider="system_tts",
        voice_mode="generated_male_ad_copy",
        execute_real_render=False,
        allow_edge_tts=False,
        voiceover_text="计划模式",
        voice_settings={},
        artifact_root=tmp_path,
    )

    assert result["adapter_id"] == "voice.system_tts"
    assert result["ok"] is True
    assert result["skipped"] is True
    assert result["renderer_voiceover_audio_input"] is None


def test_generate_system_tts_preview_uses_injected_synthesizer(tmp_path: Path) -> None:
    captured = {}

    def fake_synthesizer(**kwargs):
        captured.update(kwargs)
        output_path = Path(kwargs["output_audio_path"])
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_bytes(b"RIFF" + (b"\x00" * 80))
        return {
            "ok": True,
            "reason": "system_tts_wav",
            "audio_path": str(output_path),
            "voice_name": kwargs["voice_name"],
            "platform": "windows",
        }

    result = generate_system_tts_preview(
        text="试听系统语音",
        output_dir=tmp_path,
        voice_name="Microsoft Huihui Desktop",
        rate=2,
        volume=70,
        synthesizer=fake_synthesizer,
    )

    assert result["schema"] == "smart_video_cut.local.system_tts_preview.v0"
    assert result["ok"] is True
    assert result["audio_path"] == str(tmp_path / "system_tts_preview.wav")
    assert captured["text"] == "试听系统语音"
    assert captured["voice_name"] == "Microsoft Huihui Desktop"
    assert captured["rate"] == 2
    assert captured["volume"] == 70


def test_list_system_tts_voices_parses_powershell_json() -> None:
    def fake_runner(args, timeout_seconds):
        assert timeout_seconds >= 5
        assert any("System.Speech" in str(arg) for arg in args)
        return SimpleNamespace(
            returncode=0,
            stdout='noise before json\n{"ok":true,"default_voice":"Microsoft Huihui Desktop","voices":[{"name":"Microsoft Huihui Desktop","culture":"zh-CN","gender":"Female","age":"Adult","enabled":true,"description":"Chinese voice"}]}',
            stderr="",
        )

    result = list_system_tts_voices(command_runner=fake_runner)

    assert result["schema"] == "smart_video_cut.local.system_tts_voices.v0"
    assert result["ok"] is True
    assert result["available"] is True
    assert result["default_voice"] == "Microsoft Huihui Desktop"
    assert result["voice_count"] == 1
    assert result["voices"][0]["culture"] == "zh-CN"
    assert result["platform"]


def test_list_system_tts_voices_handles_command_failure() -> None:
    def fake_runner(args, timeout_seconds):
        return SimpleNamespace(returncode=1, stdout="", stderr="System.Speech unavailable")

    result = list_system_tts_voices(command_runner=fake_runner)

    assert result["ok"] is False
    assert result["available"] is False
    assert result["reason"] == "system_tts_voice_list_failed"
    assert "System.Speech unavailable" in result["stderr_tail"]
