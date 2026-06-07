from __future__ import annotations

from smart_video_cut.agent_tools import build_default_registry
from smart_video_cut.director_agent import DIRECTOR_CHAT_SCHEMA, chat_with_director
from smart_video_cut.web_app import create_app


def test_director_chat_extracts_intent_and_settings() -> None:
    result = chat_with_director(
        "先做时间线，剪成15秒 9:16，不加字幕，用系统 TTS，BGM 用素材库音乐。",
        context={
            "style_package": "packages/door",
            "input_videos": ["door.mp4"],
            "output_dir": "out",
            "user_request": "防盗门快闪广告",
        },
    )

    assert result["schema"] == DIRECTOR_CHAT_SCHEMA
    assert result["intent"] == "timeline"
    assert result["settings_overrides"]["video"]["target_duration_seconds"] == 15
    assert result["settings_overrides"]["video"]["aspect_ratio"] == "9:16"
    assert result["settings_overrides"]["subtitle"]["mode"] == "none"
    assert result["settings_overrides"]["voice"]["provider"] == "system_tts"
    assert result["settings_overrides"]["audio"]["bgm_style"] == "library"
    assert any(action["action_id"] == "generate_timeline" for action in result["suggested_actions"])


def test_director_chat_reports_missing_inputs_before_actions() -> None:
    result = chat_with_director("开始剪辑", context={})

    assert result["intent"] == "run_cut"
    assert [item["field"] for item in result["missing_inputs"]] == [
        "style_package",
        "input_video",
        "output_dir",
        "user_request",
    ]
    assert result["suggested_actions"][0]["action_id"] == "complete_required_inputs"


def test_director_chat_hybrid_mode_uses_llm_client_and_memory() -> None:
    captured = {}

    def fake_llm_client(**kwargs):
        captured.update(kwargs)
        return {
            "schema": "smart_video_cut.local.director_llm_response.v0",
            "ok": True,
            "reason": "llm_response",
            "assistant_message": "LLM 已结合本地记忆给出下一步：先生成时间线。",
        }

    result = chat_with_director(
        "先做时间线",
        history=[{"role": "user", "content": "我喜欢快节奏。"}],
        context={
            "director_mode": "hybrid",
            "style_package": "packages/door",
            "input_video": "door.mp4",
            "output_dir": "out",
            "user_request": "防盗门快闪广告",
        },
        llm_client=fake_llm_client,
        memory_context="本地记忆：字幕要大，节奏要快。",
    )

    assert captured["message"] == "先做时间线"
    assert captured["memory_context"] == "本地记忆：字幕要大，节奏要快。"
    assert result["mode"] == "hybrid_llm_director"
    assert result["assistant_message"].startswith("LLM 已结合本地记忆")
    assert result["memory_context_applied"] is True
    assert result["llm_result"]["ok"] is True


def test_director_chat_api_and_agent_tool() -> None:
    client = create_app().test_client() if hasattr(create_app(), "test_client") else None
    if client is None:
        from fastapi.testclient import TestClient

        client = TestClient(create_app())

    response = client.post(
        "/api/director/chat",
        json={
            "message": "我要复剪上一版，不加配音，不加 BGM",
            "context": {
                "style_package": "packages/door",
                "input_video": "door.mp4",
                "output_dir": "out",
                "user_request": "防盗门广告",
            },
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["intent"] == "re_edit"
    assert payload["settings_overrides"]["voice"]["provider"] == "none"
    assert payload["settings_overrides"]["audio"]["bgm_style"] == "none"

    registry = build_default_registry()
    tool_result = registry.invoke(
        "chat_director",
        message="FilmGen 交接，16:9 1920x1080",
        context={
            "style_package": "packages/door",
            "input_video": "door.mp4",
            "output_dir": "out",
            "user_request": "防盗门广告",
        },
    )

    assert tool_result["ok"] is True
    assert tool_result["intent"] == "filmgen"
    assert tool_result["settings_overrides"]["video"]["resolution"] == "1920x1080"
