from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from smart_video_cut import cli
from smart_video_cut.adapter_registry import list_default_adapters, resolve_adapter_selection
from smart_video_cut.agent_tools import build_default_registry
from smart_video_cut.models import LocalEditTask, StylePackageRequest
from smart_video_cut.style_package import create_style_package, default_settings_from_options
from smart_video_cut.bundled_runtime import run_edit_with_style_package
from smart_video_cut.web_app import create_app


def test_default_adapter_manifest_groups_plugin_categories() -> None:
    manifest = list_default_adapters()
    ids = {adapter["adapter_id"] for adapter in manifest["adapters"]}

    assert manifest["schema"] == "smart_video_cut.local.adapter_registry.v0"
    assert set(manifest["categories"]) == {"voice", "subtitle", "bgm", "material_analysis", "export"}
    assert "voice.edge_tts" in ids
    assert "subtitle.auto_prompt" in ids
    assert "bgm.local_audio" in ids
    assert "material.ffmpeg_probe" in ids
    assert "export.project_pack" in ids


def test_resolve_adapter_selection_from_visible_settings() -> None:
    selection = resolve_adapter_selection({
        "voice": {"provider": "moss_tts_nano"},
        "subtitle": {"enabled": False},
        "audio": {"bgm_style": "local_audio"},
        "model_route": {"allow_media_upload_to_llm": True},
    })

    assert selection["selected_adapter_ids"]["voice"] == ["voice.moss_tts_nano"]
    assert selection["selected_adapter_ids"]["subtitle"] == ["subtitle.none"]
    assert selection["selected_adapter_ids"]["bgm"] == ["bgm.local_audio"]
    assert selection["selected_adapter_ids"]["material_analysis"] == [
        "material.ffmpeg_probe",
        "material.multimodal_review",
    ]
    codes = {warning["code"] for warning in selection["warnings"]}
    assert "adapter_requires_setup" in codes
    assert "missing_bgm_audio_path" in codes


def test_resolve_adapter_selection_marks_system_tts_and_fixture_as_executable() -> None:
    system_selection = resolve_adapter_selection({"voice": {"provider": "system_tts"}})
    fixture_selection = resolve_adapter_selection({"voice": {"provider": "fixture"}})
    legacy_fixture_selection = resolve_adapter_selection({"voice": {"provider": "fixture_voice"}})

    assert system_selection["selected_adapter_ids"]["voice"] == ["voice.system_tts"]
    assert fixture_selection["selected_adapter_ids"]["voice"] == ["voice.fixture"]
    assert legacy_fixture_selection["selected_adapter_ids"]["voice"] == ["voice.fixture"]
    for selection in (system_selection, fixture_selection, legacy_fixture_selection):
        assert not any(
            warning["code"] == "adapter_planned_not_executable"
            for warning in selection["warnings"]
        )


def test_resolve_adapter_selection_marks_filmgen_subtitle_as_executable_handoff() -> None:
    selection = resolve_adapter_selection({"subtitle": {"enabled": True, "mode": "filmgen"}})

    assert selection["selected_adapter_ids"]["subtitle"] == ["subtitle.filmgen"]
    assert not any(
        warning["code"] == "adapter_planned_not_executable"
        for warning in selection["warnings"]
    )


def test_resolve_adapter_selection_marks_local_generated_bgm_as_executable() -> None:
    selection = resolve_adapter_selection({"audio": {"bgm_style": "local_generated"}})

    assert selection["selected_adapter_ids"]["bgm"] == ["bgm.local_generated"]
    assert not any(
        warning["code"] == "adapter_planned_not_executable"
        for warning in selection["warnings"]
    )


def test_resolve_adapter_selection_supports_bgm_library() -> None:
    selection = resolve_adapter_selection({"audio": {"bgm_style": "library", "bgm_library_dir": "D:/music"}})

    assert selection["selected_adapter_ids"]["bgm"] == ["bgm.library"]
    assert not any(
        warning["code"] == "adapter_planned_not_executable"
        for warning in selection["warnings"]
    )


def test_resolve_adapter_selection_can_disable_material_visual_analysis() -> None:
    selection = resolve_adapter_selection({"material_analysis": {"enable_visual_analysis": False}})

    assert selection["selected_adapter_ids"]["material_analysis"] == ["material.order_fallback"]


def test_resolve_adapter_selection_can_disable_material_multimodal_review() -> None:
    selection = resolve_adapter_selection({
        "material_analysis": {"enable_multimodal_review": False},
        "model_route": {"allow_media_upload_to_llm": True},
    })

    assert selection["selected_adapter_ids"]["material_analysis"] == ["material.ffmpeg_probe"]


def test_run_edit_records_adapter_selection(tmp_path: Path) -> None:
    template = tmp_path / "template.mp4"
    input_video = tmp_path / "input.mp4"
    template.write_bytes(b"template")
    input_video.write_bytes(b"input")
    settings = default_settings_from_options(
        duration=10,
        aspect_ratio="9:16",
        resolution="720x1280",
        quality="standard",
        subtitle_size=44,
        bgm_volume_db=-18,
        voice_provider="edge_tts",
    )
    create_style_package(
        StylePackageRequest(
            name="Adapter Case",
            template_video=template,
            package_dir=tmp_path / "pkg",
            settings=settings,
        )
    )

    result = run_edit_with_style_package(
        LocalEditTask(
            style_package=tmp_path / "pkg",
            input_video=input_video,
            output_dir=tmp_path / "out",
            user_request="生成适配器记录",
            execute_real_render=False,
        )
    )

    assert result["adapter_selection"]["schema"] == "smart_video_cut.local.adapter_selection.v0"
    assert result["adapter_selection"]["selected_adapter_ids"]["voice"] == ["voice.edge_tts"]
    stored = json.loads((tmp_path / "out" / "local_studio_result.json").read_text(encoding="utf-8"))
    assert stored["adapter_selection"]["selected_adapter_ids"]["export"] == [
        "export.local_mp4",
        "export.project_pack",
        "export.filmgen_handoff",
    ]


def test_agent_registry_exposes_adapter_tools() -> None:
    registry = build_default_registry()
    tool_ids = {tool["tool_id"] for tool in registry.to_manifest()["tools"]}

    assert "list_adapters" in tool_ids
    assert "resolve_adapters" in tool_ids

    listed = registry.invoke("list_adapters", category="voice")
    resolved = registry.invoke("resolve_adapters", settings={"voice": {"mode": "none"}})
    bgm_model = resolve_adapter_selection({"audio": {"bgm_style": "local_music_model"}})

    assert listed["ok"] is True
    assert all(adapter["category"] == "voice" for adapter in listed["adapters"])
    assert resolved["ok"] is True
    assert bgm_model["selected_adapter_ids"]["bgm"] == ["bgm.local_music_model"]
    assert resolved["selected_adapter_ids"]["voice"] == ["voice.none"]


def test_cli_adapters_outputs_manifest_and_selection(tmp_path: Path, capsys) -> None:
    settings_json = tmp_path / "settings.json"
    settings_json.write_text(
        json.dumps({"visible_settings": {"subtitle": {"custom_prompt": "只显示产品卖点"}}}, ensure_ascii=False),
        encoding="utf-8",
    )

    exit_code = cli.main(["adapters", "--category", "subtitle", "--settings-json", str(settings_json)])
    output = json.loads(capsys.readouterr().out)

    assert exit_code == 0
    assert output["manifest"]["filters"]["category"] == "subtitle"
    assert output["selection"]["selected_adapter_ids"]["subtitle"] == ["subtitle.custom_text"]


def test_web_adapter_endpoints() -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)

    manifest = client.get("/api/adapters", params={"category": "bgm"}).json()
    selection = client.post(
        "/api/adapters/selection",
        json={"settings": {"audio": {"bgm_style": "none"}}},
    ).json()

    assert manifest["adapter_count"] >= 1
    assert all(adapter["category"] == "bgm" for adapter in manifest["adapters"])
    assert selection["selected_adapter_ids"]["bgm"] == ["bgm.none"]


def test_web_system_tts_voice_endpoint(monkeypatch) -> None:
    from smart_video_cut import web_app

    monkeypatch.setattr(
        web_app,
        "list_system_tts_voices",
        lambda: {
            "schema": "smart_video_cut.local.system_tts_voices.v0",
            "ok": True,
            "available": True,
            "reason": "system_tts_voices_ready",
            "default_voice": "Microsoft Huihui Desktop",
            "voice_count": 1,
            "voices": [{"name": "Microsoft Huihui Desktop", "culture": "zh-CN"}],
        },
    )
    client = TestClient(create_app(), raise_server_exceptions=False)

    payload = client.get("/api/voice/system-tts/voices").json()

    assert payload["schema"] == "smart_video_cut.local.system_tts_voices.v0"
    assert payload["ok"] is True
    assert payload["voice_count"] == 1
    assert payload["voices"][0]["name"] == "Microsoft Huihui Desktop"


def test_web_system_tts_preview_endpoint(monkeypatch) -> None:
    from smart_video_cut import web_app

    monkeypatch.setattr(
        web_app,
        "generate_system_tts_preview",
        lambda **kwargs: {
            "schema": "smart_video_cut.local.system_tts_preview.v0",
            "ok": True,
            "reason": "system_tts_wav",
            "audio_path": str(Path(kwargs["output_dir"]) / "system_tts_preview.wav"),
            "voice_name": kwargs["voice_name"],
        },
    )
    client = TestClient(create_app(), raise_server_exceptions=False)

    payload = client.post(
        "/api/voice/system-tts/test",
        json={
            "text": "试听",
            "output_dir": "out",
            "voice_name": "Microsoft Huihui Desktop",
            "rate": 1,
            "volume": 80,
        },
    ).json()

    assert payload["schema"] == "smart_video_cut.local.system_tts_preview.v0"
    assert payload["ok"] is True
    assert payload["voice_name"] == "Microsoft Huihui Desktop"
