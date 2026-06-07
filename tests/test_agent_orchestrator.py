from __future__ import annotations

from fastapi.testclient import TestClient

from smart_video_cut.agent_orchestrator import AGENT_ORCHESTRATION_SCHEMA, orchestrate_local_agents
from smart_video_cut.agent_tools import build_default_registry
from smart_video_cut.web_app import create_app


def test_orchestrate_local_agents_builds_ready_multi_agent_plan() -> None:
    result = orchestrate_local_agents(
        message="先生成时间线，剪成15秒 9:16，用系统 TTS。",
        context={
            "style_package": "packages/door",
            "input_videos": ["door-a.mp4", "door-b.mp4"],
            "output_dir": "out",
            "user_request": "防盗门快闪广告",
            "settings_overrides": {
                "audio": {"bgm_style": "none"},
                "voice": {"provider": "system_tts"},
            },
        },
    )

    assert result["schema"] == AGENT_ORCHESTRATION_SCHEMA
    assert result["ok"] is True
    assert result["summary"]["agent_count"] == 7
    assert result["summary"]["blocked_agents"] == 0
    assert result["summary"]["run_ready"] is True
    assert {agent["agent_id"] for agent in result["agents"]} == {
        "director",
        "material_analyst",
        "timeline_editor",
        "subtitle_designer",
        "audio_mixer",
        "voice_director",
        "qc_supervisor",
    }
    assert any(action["action_id"] == "generate_timeline" for action in result["execution_sequence"])


def test_orchestrate_local_agents_blocks_on_missing_inputs() -> None:
    result = orchestrate_local_agents(message="开始剪辑", context={})

    assert result["summary"]["run_ready"] is False
    assert result["summary"]["blocked_agents"] >= 1
    assert result["summary"]["recommended_next_action"]["action_id"] == "complete_required_inputs"
    assert any(item["code"].endswith("missing_style_package") for item in result["risk_warnings"])


def test_orchestrate_local_agents_requires_saved_voice_profile_when_requested() -> None:
    result = orchestrate_local_agents(
        message="使用已确认音色开始剪辑",
        context={
            "style_package": "packages/door",
            "input_video": "door.mp4",
            "output_dir": "out",
            "user_request": "防盗门广告",
            "settings_overrides": {
                "voice": {
                    "provider": "moss_tts_nano",
                    "require_saved_profile": True,
                },
            },
        },
    )

    voice_agent = next(agent for agent in result["agents"] if agent["agent_id"] == "voice_director")

    assert voice_agent["status"] == "blocked"
    assert voice_agent["required_inputs"][0]["field"] == "voice_profile_ref"
    assert voice_agent["tool_plan"][0]["action_id"] == "confirm_voice_profile"


def test_agent_orchestration_api_and_tool_registry() -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)
    response = client.post(
        "/api/agent/orchestrate",
        json={
            "message": "先给我时间线",
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
    assert payload["schema"] == AGENT_ORCHESTRATION_SCHEMA
    assert payload["summary"]["agent_count"] == 7

    registry = build_default_registry()
    tool_result = registry.invoke(
        "orchestrate_local_agents",
        message="先给我时间线",
        context={
            "style_package": "packages/door",
            "input_video": "door.mp4",
            "output_dir": "out",
            "user_request": "防盗门广告",
        },
    )

    assert tool_result["ok"] is True
    assert tool_result["schema"] == AGENT_ORCHESTRATION_SCHEMA
    assert tool_result["summary"]["agent_count"] == 7
