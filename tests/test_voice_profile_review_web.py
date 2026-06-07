from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from smart_video_cut.web_app import create_app


def test_voice_profile_confirm_api_persists_review_and_lists_refs(tmp_path: Path) -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.post(
        "/api/voice-profile/confirm",
        json={
            "output_dir": str(tmp_path),
            "profile_result": _profile_result(),
            "outcome": "approved",
            "notes": "试听通过。",
            "rating": 5,
            "prompt_audio_path": str(tmp_path / "prompt.wav"),
            "sample_audio_path": str(tmp_path / "sample.wav"),
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["schema"] == "smart_video_cut.local.voice_profile_review.v0"
    assert payload["voice_profile_ref"]["schema"] == "smart_video_cut.local.voice_profile_ref.v0"
    assert payload["settings_overrides"]["voice"]["voice_profile_ref"]["ref_id"]
    assert Path(payload["review_record_path"]).is_file()

    index_response = client.get("/api/voice-profile/refs", params={"output_dir": str(tmp_path)})
    index = index_response.json()

    assert index_response.status_code == 200
    assert index["schema"] == "smart_video_cut.local.voice_profile_review_index.v0"
    assert index["count"] == 1
    assert index["refs"][0]["voice_profile_ref"]["ref_id"] == payload["voice_profile_ref"]["ref_id"]


def _profile_result() -> dict:
    return {
        "schema": "video_editing_toolkit.voice_simulation.v0",
        "voice_profile_ref": {
            "artifact_id": "artifact_profile",
            "artifact_type": "voice_simulation_profile",
        },
        "voice_simulation_summary": {
            "provider_id": "moss_tts_nano",
            "sample_approved": True,
            "can_apply_to_video_task": True,
        },
        "application_contract": {
            "provider_id": "moss_tts_nano",
            "can_apply_to_video_task": True,
            "voice_profile_ref": {
                "artifact_id": "artifact_profile",
                "artifact_type": "voice_simulation_profile",
            },
        },
    }
