from __future__ import annotations

import json
from pathlib import Path

from smart_video_cut.models import LocalEditTask, StylePackageRequest
from smart_video_cut.style_package import create_style_package, default_settings_from_options
from smart_video_cut.bundled_runtime import ensure_video_toolkit_available, run_edit_with_style_package


def test_uses_bundled_video_editing_toolkit() -> None:
    status = ensure_video_toolkit_available()

    assert status["source"] == "bundled_copy"
    assert "智能剪辑软件" in status["module_file"]
    assert "src\\video_editing_toolkit" in status["bundled_runtime_dir"]


def test_run_edit_with_style_package_reuses_toolkit_plan_only(tmp_path: Path) -> None:
    template = tmp_path / "sample.mp4"
    input_video = tmp_path / "input.mp4"
    input_video_2 = tmp_path / "input_detail.mp4"
    template.write_bytes(b"template bytes")
    input_video.write_bytes(b"input bytes")
    input_video_2.write_bytes(b"detail bytes")
    settings = default_settings_from_options(
        duration=12,
        aspect_ratio="9:16",
        resolution="720x1280",
        quality="standard",
        subtitle_size=44,
        bgm_volume_db=-18,
        voice_provider="edge_tts",
    )
    create_style_package(
        StylePackageRequest(
            name="Door Flash",
            template_video=template,
            package_dir=tmp_path / "pkg",
            settings=settings,
        )
    )

    result = run_edit_with_style_package(
        LocalEditTask(
            style_package=tmp_path / "pkg",
            input_video=input_video,
            input_videos=[input_video_2],
            output_dir=tmp_path / "out",
            user_request="做一个防盗门快闪广告。",
            execute_real_render=False,
            project_id="proj_test",
        )
    )

    assert result["ok"] is True
    assert result["toolkit_summary"]["workflow_kind"] == "creative_edit_runner"
    assert result["input_video_count"] == 2
    assert result["material_plan"]["material_count"] == 2
    assert result["material_plan"]["role_source_map"]["overall_door"] == 0
    assert result["material_plan"]["role_source_map"]["detail"] == 1
    assert result["material_adapter_result"]["schema"] == "smart_video_cut.local.material_adapter_result.v0"
    assert result["material_adapter_result"]["selected_adapter_ids"] == ["material.ffmpeg_probe"]
    assert result["material_adapter_result"]["material_plan"]["strategy"] == result["material_plan"]["strategy"]
    assert result["settings_applied_by_current_toolkit"]["target_duration_seconds"] == 12
    assert result["settings_applied_by_current_toolkit"]["resolution"] == {"width": 720, "height": 1280}
    assert result["settings_applied_by_current_toolkit"]["subtitle_font_size"] == 44
    assert result["settings_applied_by_current_toolkit"]["bgm_volume_db"] == -18
    assert result["voice_adapter_result"]["schema"] == "smart_video_cut.local.voice_adapter_result.v0"
    assert result["voice_adapter_result"]["adapter_id"] == "voice.edge_tts"
    assert result["voice_adapter_result"]["renderer_allow_edge_tts"] is False
    assert result["subtitle_adapter_result"]["schema"] == "smart_video_cut.local.subtitle_adapter_result.v0"
    assert result["subtitle_adapter_result"]["adapter_id"] == "subtitle.auto_prompt"
    assert result["subtitle_adapter_result"]["renderer_subtitle_enabled"] is True
    assert result["subtitle_adapter_result"]["onscreen_text_policy"] == result["settings_applied_by_current_toolkit"]["onscreen_text_policy"]
    assert result["bgm_adapter_result"]["schema"] == "smart_video_cut.local.bgm_adapter_result.v0"
    assert result["bgm_adapter_result"]["adapter_id"] == "bgm.generated_placeholder"
    assert result["bgm_adapter_result"]["renderer_bgm_enabled"] is True
    assert result["bgm_adapter_result"]["renderer_bgm_audio_input"] is None
    assert result["local_bgm_audio_path"] is None
    assert result["export_adapter_result"]["schema"] == "smart_video_cut.local.export_adapter_result.v0"
    assert result["export_adapter_result"]["exports"]["local_mp4"]["status"] == "skipped"
    assert result["export_adapter_result"]["exports"]["project_pack"]["status"] == "available"
    assert result["copied_output_video"] is None
    assert (tmp_path / "out" / "local_studio_result.json").is_file()
    manifest_path = tmp_path / "out" / "project_manifest.json"
    protocol_path = tmp_path / "out" / "local_toolkit_protocol.json"
    assert manifest_path.is_file()
    assert protocol_path.is_file()
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    protocol = json.loads(protocol_path.read_text(encoding="utf-8"))
    assert manifest["schema"] == "smart_video_cut.local.project_manifest.v0"
    assert manifest["input_video_count"] == 2
    assert manifest["version_history"]["current_version"] == 1
    assert result["project_manifest_path"] == str(manifest_path)
    assert result["local_toolkit_protocol_path"] == str(protocol_path)
    assert protocol["schema"] == "smart_video_cut.local.toolkit_protocol.v0"
    assert protocol["project_id"] == "proj_test"


def test_renderer_settings_are_applied_to_toolkit_render_plan(tmp_path: Path) -> None:
    template = tmp_path / "sample.mp4"
    input_video = tmp_path / "input.mp4"
    template.write_bytes(b"template bytes")
    input_video.write_bytes(b"input bytes")
    settings = default_settings_from_options(
        duration=9,
        aspect_ratio="9:16",
        resolution="720x1280",
        quality="standard",
        subtitle_size=44,
        bgm_volume_db=-18,
        voice_provider="edge_tts",
    )
    create_style_package(
        StylePackageRequest(
            name="Renderer Settings",
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
            user_request="做一个横版高清广告。",
            execute_real_render=False,
            project_id="proj_renderer",
            settings_overrides={
                "video": {
                    "aspect_ratio": "16:9",
                    "resolution": "1920x1080",
                    "quality": "high",
                    "fps": 60,
                },
                "subtitle": {
                    "font_size": 58,
                    "font_color": "yellow",
                    "outline_color": "black",
                    "outline_width": 7,
                },
                "audio": {
                    "bgm_volume_db": -12,
                    "voice_volume_db": -3,
                },
            },
        )
    )

    applied = result["settings_applied_by_current_toolkit"]
    render_plan_ref = result["toolkit_summary"]["source_artifact_refs"]["render_plan"]
    render_plan_path = (
        tmp_path / "out" / "_smart_video_cut_artifacts" / render_plan_ref["artifact_id"] / "render_plan.json"
    )
    render_plan = json.loads(render_plan_path.read_text(encoding="utf-8"))

    assert applied["aspect_ratio"] == "16:9"
    assert applied["resolution"] == {"width": 1920, "height": 1080}
    assert applied["fps"] == 60
    assert applied["video_crf"] == 18
    assert applied["subtitle_font_size"] == 58
    assert applied["bgm_volume_db"] == -12
    assert applied["voice_volume_db"] == -3
    assert render_plan["orientation"] == "horizontal"
    assert render_plan["resolution"] == {"width": 1920, "height": 1080}
    assert render_plan["fps"] == 60
    assert render_plan["video_crf"] == 18
    assert render_plan["text_layer"]["font_size"] == 58
    assert render_plan["text_layer"]["font_color"] == "yellow"
    assert render_plan["text_layer"]["outline_width"] == 7
    assert render_plan["audio"]["bgm_volume_db"] == -12
    assert render_plan["audio"]["voice_volume_db"] == -3
    assert "subtitle_font_size" not in result["settings_reserved_for_next_renderer_adapter"]


def test_run_edit_with_filmgen_subtitle_mode_writes_handoff(tmp_path: Path) -> None:
    template = tmp_path / "template.mp4"
    input_video = tmp_path / "input.mp4"
    template.write_bytes(b"template bytes")
    input_video.write_bytes(b"input bytes")
    settings = default_settings_from_options(
        duration=10,
        aspect_ratio="9:16",
        resolution="720x1280",
        quality="standard",
        subtitle_size=46,
        bgm_volume_db=-18,
        voice_provider="edge_tts",
    )
    settings.subtitle.mode = "filmgen"
    settings.subtitle.custom_prompt = "突出施工环境；强调门锁细节"
    settings.subtitle.location_info = "同家庄镇张庄村"
    create_style_package(
        StylePackageRequest(
            name="External Subtitle Case",
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
            user_request="生成外部字幕交接。",
            execute_real_render=False,
            project_id="filmgen_subtitle_case",
        )
    )

    subtitle_result = result["subtitle_adapter_result"]
    handoff_path = Path(subtitle_result["handoff_path"])
    payload = json.loads(handoff_path.read_text(encoding="utf-8"))

    assert result["adapter_selection"]["selected_adapter_ids"]["subtitle"] == ["subtitle.filmgen"]
    assert subtitle_result["ok"] is True
    assert subtitle_result["reason"] == "filmgen_subtitle_handoff"
    assert subtitle_result["renderer_subtitle_enabled"] is False
    assert handoff_path.is_file()
    assert payload["subtitle_texts"] == ["同家庄镇张庄村", "突出施工环境", "强调门锁细节"]
    assert payload["style"]["font_size"] == 46
    assert payload["renderer_contract"]["current_renderer_subtitle_enabled"] is False

    stored = json.loads((tmp_path / "out" / "local_studio_result.json").read_text(encoding="utf-8"))
    assert stored["subtitle_adapter_result"]["handoff_path"] == str(handoff_path)
