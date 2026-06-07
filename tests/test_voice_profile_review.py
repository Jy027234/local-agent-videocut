from __future__ import annotations

import json
from pathlib import Path

from smart_video_cut.voice_profile_review import (
    VOICE_PROFILE_REF_SCHEMA,
    VOICE_PROFILE_REVIEW_SCHEMA,
    confirm_voice_profile_review,
    list_voice_profile_reviews,
)


def test_confirm_voice_profile_review_creates_approved_ref(tmp_path: Path) -> None:
    prompt = tmp_path / "prompt.wav"
    sample = tmp_path / "sample.wav"
    prompt.write_bytes(b"prompt")
    sample.write_bytes(b"sample")

    record = confirm_voice_profile_review(
        output_dir=tmp_path,
        profile_result=_profile_result(provider_id="moss_tts_nano"),
        outcome="approved",
        notes="声音清晰，可用于商品解说。",
        rating=5,
        prompt_audio_path=prompt,
        sample_audio_path=sample,
    )

    assert record["schema"] == VOICE_PROFILE_REVIEW_SCHEMA
    assert record["outcome"] == "approved"
    assert record["can_apply_to_video_task"] is True
    assert record["voice_profile_ref"]["schema"] == VOICE_PROFILE_REF_SCHEMA
    assert record["voice_profile_ref"]["provider_id"] == "moss_tts_nano"
    assert record["voice_profile_ref"]["prompt_audio_path"] == str(prompt)
    assert record["settings_overrides"]["voice"]["provider"] == "moss_tts_nano"
    assert record["settings_overrides"]["voice"]["voice_profile_ref"]["ref_id"]
    assert Path(record["review_record_path"]).is_file()


def test_confirm_voice_profile_review_records_rejection_without_ref(tmp_path: Path) -> None:
    record = confirm_voice_profile_review(
        output_dir=tmp_path,
        profile_result=_profile_result(provider_id="edge_tts"),
        outcome="rejected",
        notes="口吻不适合。",
        rating=2,
    )

    assert record["outcome"] == "rejected"
    assert record["can_apply_to_video_task"] is False
    assert record["voice_profile_ref"] is None
    assert record["settings_overrides"] == {}


def test_list_voice_profile_reviews_reads_saved_records(tmp_path: Path) -> None:
    result_path = tmp_path / "voice_profile_result.json"
    result_path.write_text(json.dumps(_profile_result(provider_id="fixture_voice")), encoding="utf-8")

    confirm_voice_profile_review(
        output_dir=tmp_path,
        profile_result_path=result_path,
        outcome="approved",
        rating=4,
    )
    index = list_voice_profile_reviews(tmp_path)

    assert index["ok"] is True
    assert index["count"] == 1
    assert index["refs"][0]["provider_id"] == "fixture_voice"
    assert index["refs"][0]["voice_profile_ref"]["provider_id"] == "fixture_voice"


def _profile_result(provider_id: str = "moss_tts_nano") -> dict:
    return {
        "schema": "video_editing_toolkit.voice_simulation.v0",
        "voice_profile_ref": {
            "artifact_id": "artifact_profile",
            "artifact_type": "voice_simulation_profile",
            "checksum": "sha256:test",
        },
        "voice_simulation_summary": {
            "provider_id": provider_id,
            "sample_outcome": "approved",
            "sample_approved": True,
            "can_apply_to_video_task": True,
        },
        "application_contract": {
            "provider_id": provider_id,
            "can_apply_to_video_task": True,
            "voice_profile_ref": {
                "artifact_id": "artifact_profile",
                "artifact_type": "voice_simulation_profile",
            },
            "video_task_input_patch": {
                "voice_generation_policy": "use_saved_profile_only",
            },
        },
        "quality_gate": {
            "status": "voice_profile_ready_for_video_task",
            "contract_valid": True,
        },
    }
