from __future__ import annotations

from pathlib import Path

from smart_video_cut.web_app import list_moss_tts_samples, save_voice_sample


def test_save_voice_sample_rejects_empty_upload() -> None:
    result = save_voice_sample(data=b"", filename="empty.webm")

    assert result["ok"] is False
    assert result["reason"] == "empty_audio_upload"


def test_list_moss_tts_samples_reads_sidecar_metadata(tmp_path: Path) -> None:
    audio = tmp_path / "moss_tts_sample_20260518_120000_001_Zhiming_stable.wav"
    audio.write_bytes(b"0" * 1200)
    audio.with_suffix(".json").write_text(
        '{"created_at": 1779086400, "voice": "Zhiming", "profile": "stable_clear", "text_preview": "测试文本"}',
        encoding="utf-8",
    )

    samples = list_moss_tts_samples(tmp_path)

    assert samples[0]["audio_path"] == str(audio)
    assert samples[0]["voice"] == "Zhiming"
    assert samples[0]["profile"] == "stable_clear"
