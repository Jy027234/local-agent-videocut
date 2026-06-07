from __future__ import annotations

import wave
from pathlib import Path

from smart_video_cut.bgm_adapters import prepare_bgm


def test_bgm_none_disables_renderer_inputs() -> None:
    result = prepare_bgm(
        audio_settings={"bgm_style": "none", "bgm_start_seconds": 5},
        execute_real_render=True,
    )

    assert result["schema"] == "smart_video_cut.local.bgm_adapter_result.v0"
    assert result["adapter_id"] == "bgm.none"
    assert result["ok"] is True
    assert result["skipped"] is True
    assert result["renderer_bgm_enabled"] is False
    assert result["renderer_bgm_audio_input"] is None


def test_local_audio_bgm_passes_existing_file_to_renderer(tmp_path: Path) -> None:
    bgm = tmp_path / "music.wav"
    bgm.write_bytes(b"audio")

    result = prepare_bgm(
        audio_settings={
            "bgm_style": "local_audio",
            "bgm_audio_path": str(bgm),
            "bgm_start_seconds": 2.5,
            "bgm_volume_db": -12,
        },
        execute_real_render=True,
    )

    assert result["adapter_id"] == "bgm.local_audio"
    assert result["ok"] is True
    assert result["reason"] == "local_audio_ready"
    assert result["local_bgm_audio_path"] == str(bgm)
    assert result["renderer_bgm_audio_input"] == str(bgm)
    assert result["renderer_bgm_enabled"] is True
    assert result["renderer_bgm_start_seconds"] == 2.5
    assert result["bgm_volume_db"] == -12


def test_library_bgm_selects_recommended_audio_for_real_render(tmp_path: Path) -> None:
    library = tmp_path / "library"
    library.mkdir()
    selected = library / "premium_cinematic.wav"
    selected.write_bytes(b"audio")

    result = prepare_bgm(
        audio_settings={
            "bgm_style": "library",
            "bgm_library_dir": str(library),
            "bgm_library_query": "质感",
        },
        execute_real_render=True,
    )

    assert result["adapter_id"] == "bgm.library"
    assert result["ok"] is True
    assert result["reason"] == "library_audio_selected"
    assert result["local_bgm_audio_path"] == str(selected)
    assert result["renderer_bgm_audio_input"] == str(selected)
    assert result["library_bgm_result"]["library_scan"]["item_count"] == 1


def test_library_bgm_warns_when_no_audio_found(tmp_path: Path) -> None:
    library = tmp_path / "empty"
    library.mkdir()

    result = prepare_bgm(
        audio_settings={"bgm_style": "library", "bgm_library_dir": str(library)},
        execute_real_render=True,
    )

    assert result["adapter_id"] == "bgm.library"
    assert result["ok"] is False
    assert result["renderer_bgm_audio_input"] is None
    assert result["warnings"][0]["code"] == "bgm_library_audio_missing"


def test_local_audio_bgm_keeps_plan_but_warns_when_file_missing(tmp_path: Path) -> None:
    missing = tmp_path / "missing.mp3"

    result = prepare_bgm(
        audio_settings={"bgm_style": "local_audio", "bgm_audio_path": str(missing)},
        execute_real_render=True,
    )

    assert result["adapter_id"] == "bgm.local_audio"
    assert result["ok"] is True
    assert result["reason"] == "local_audio_missing"
    assert result["local_bgm_audio_path"] is None
    assert result["renderer_bgm_enabled"] is True
    assert result["renderer_bgm_audio_input"] is None
    assert result["warnings"][0]["code"] == "missing_bgm_audio_path"


def test_generated_placeholder_bgm_records_style_without_audio_input() -> None:
    result = prepare_bgm(
        audio_settings={"bgm_style": "product_flash"},
        execute_real_render=True,
    )

    assert result["adapter_id"] == "bgm.generated_placeholder"
    assert result["reason"] == "bgm_style_policy_only"
    assert result["renderer_bgm_enabled"] is True
    assert result["renderer_bgm_audio_input"] is None


def test_local_generated_bgm_skips_audio_in_plan_only() -> None:
    result = prepare_bgm(
        audio_settings={"bgm_style": "local_generated"},
        execute_real_render=False,
        artifact_root=None,
    )

    assert result["adapter_id"] == "bgm.local_generated"
    assert result["ok"] is True
    assert result["skipped"] is True
    assert result["reason"] == "local_generated_plan_only"
    assert result["renderer_bgm_enabled"] is True
    assert result["renderer_bgm_audio_input"] is None


def test_local_generated_bgm_writes_wav_for_real_render(tmp_path: Path) -> None:
    result = prepare_bgm(
        audio_settings={
            "bgm_style": "local_generated",
            "generated_duration_seconds": 0.3,
            "generated_sample_rate": 8000,
            "generated_mood": "premium_cinematic",
        },
        execute_real_render=True,
        artifact_root=tmp_path / "artifacts",
    )

    assert result["adapter_id"] == "bgm.local_generated"
    assert result["ok"] is True
    assert result["skipped"] is False
    assert result["reason"] == "local_generated_bgm_wav"
    assert result["renderer_bgm_enabled"] is True
    assert result["renderer_bgm_audio_input"] == result["local_bgm_audio_path"]

    audio_path = Path(result["renderer_bgm_audio_input"])
    assert audio_path.is_file()
    with wave.open(str(audio_path), "rb") as wav:
        assert wav.getnchannels() == 1
        assert wav.getframerate() == 8000
        assert wav.getnframes() >= 1
    assert result["local_generated_bgm_result"]["mood"] == "premium_cinematic"


def test_local_music_model_bgm_uses_replaceable_generation_contract(tmp_path: Path) -> None:
    result = prepare_bgm(
        audio_settings={
            "bgm_style": "local_music_model",
            "local_music_model_id": "demo-music-model",
            "generated_duration_seconds": 0.2,
            "generated_sample_rate": 8000,
        },
        execute_real_render=True,
        artifact_root=tmp_path / "artifacts",
    )

    assert result["adapter_id"] == "bgm.local_music_model"
    assert result["ok"] is True
    assert result["reason"] == "local_music_model_wav"
    assert result["renderer_bgm_audio_input"] == result["local_bgm_audio_path"]
    assert result["local_music_model_result"]["model_id"] == "demo-music-model"
    assert Path(result["renderer_bgm_audio_input"]).is_file()
