from __future__ import annotations

from pathlib import Path

from smart_video_cut.material_multimodal import review_material_roles_with_multimodal


def test_multimodal_review_skips_when_media_upload_not_allowed() -> None:
    result = review_material_roles_with_multimodal(
        paths=[Path("D:/media/no1.mp4")],
        visual_profiles=[],
        config={
            "provider": "openai_compatible",
            "base_url": "https://api.example.test/v1",
            "model": "vision-model",
            "api_key": "token",
            "model_capability": "multimodal_text_image",
            "allow_media_upload_to_llm": False,
        },
    )

    assert result["status"] == "skipped"
    assert result["skipped_reason"] == "media_upload_not_allowed"


def test_multimodal_review_parses_openai_compatible_response(tmp_path: Path) -> None:
    thumbnail = tmp_path / "thumb.jpg"
    thumbnail.write_bytes(b"fake-jpeg")

    def fake_post(url: str, headers: dict[str, str], body: dict, timeout: int) -> dict:
        assert url == "https://api.example.test/v1/chat/completions"
        assert headers["Authorization"] == "Bearer token"
        assert body["messages"][1]["content"][2]["type"] == "image_url"
        return {
            "choices": [
                {
                    "message": {
                        "content": (
                            '{"assignments":[{"index":0,"role":"opening_hero",'
                            '"confidence":0.9,"reason":"全貌清楚"}],"summary":"ok"}'
                        )
                    }
                }
            ]
        }

    result = review_material_roles_with_multimodal(
        paths=[Path("D:/media/no1.mp4")],
        visual_profiles=[
            {
                "analysis_ready": True,
                "thumbnail_refs": [{"thumbnail_path": str(thumbnail), "mime_type": "image/jpeg"}],
            }
        ],
        config={
            "provider": "openai_compatible",
            "base_url": "https://api.example.test/v1",
            "model": "vision-model",
            "api_key": "token",
            "model_capability": "multimodal_text_image",
            "allow_media_upload_to_llm": True,
            "timeout_seconds": 10,
            "temperature": 0.1,
        },
        http_post=fake_post,
    )

    assert result["ok"] is True
    assert result["status"] == "completed"
    assert result["assignments"][0]["role"] == "opening_hero"
    assert result["assignments"][0]["confidence"] == 0.9
