from __future__ import annotations

import json
from pathlib import Path

from smart_video_cut.models import PROJECT_PACK_SCHEMA, StylePackageRequest
from smart_video_cut.protocol_runner import prepare_protocol_run, run_protocol_path
from smart_video_cut.style_package import create_style_package, default_settings_from_options
from smart_video_cut.worker_protocol import create_worker_task_package


def test_prepare_protocol_run_from_project_pack(tmp_path: Path) -> None:
    style_dir = _create_style_package(tmp_path)
    input_video = tmp_path / "input.mp4"
    input_video.write_bytes(b"input")
    project_pack_path = tmp_path / "project_pack.json"
    project_pack_path.write_text(
        json.dumps(
            {
                "schema": PROJECT_PACK_SCHEMA,
                "name": "Project Pack Demo",
                "style_pack_ref": str(style_dir),
                "input_videos": [str(input_video)],
                "output_dir": str(tmp_path / "original-out"),
                "project_settings_overrides": {"video": {"target_duration_seconds": 9}},
                "timeline_plan": {"segments": [{"segment_id": "seg-1"}]},
                "project_manifest": {
                    "project_id": "project_pack_demo",
                    "latest_result": {
                        "user_request": "保持节奏，突出锁芯特写",
                        "confirmed_brief": "开头先展示整体，再切细节",
                        "task_id": "task_pack_001",
                    },
                    "style_package": {"path": str(style_dir)},
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    prepared = prepare_protocol_run(project_pack_path, output_dir=str(tmp_path / "protocol-out"))

    assert prepared["ok"] is True
    assert prepared["protocol_kind"] == "project_pack"
    assert prepared["task_payload"]["style_package"] == str(style_dir)
    assert prepared["task_payload"]["output_dir"] == str(tmp_path / "protocol-out")
    assert prepared["task_payload"]["confirmed_brief"] == "开头先展示整体，再切细节"


def test_run_protocol_path_for_worker_package(monkeypatch, tmp_path: Path) -> None:
    created = create_worker_task_package(
        package_dir=tmp_path / "worker-job",
        style_package="packages/door",
        input_video="input.mp4",
        output_dir=str(tmp_path / "out"),
        user_request="防盗门快闪广告",
    )

    def fake_run_worker_task_package(package_path):
        return {
            "ok": True,
            "schema": "smart_video_cut.local.worker_completion.v0",
            "status": "completed",
            "output_dir": str(tmp_path / "out"),
            "completion_path": str(tmp_path / "out" / "completion.json"),
            "package_path": package_path,
        }

    monkeypatch.setattr("smart_video_cut.protocol_runner.run_worker_task_package", fake_run_worker_task_package)

    result = run_protocol_path(created["package_path"])

    assert result["ok"] is True
    assert result["protocol_kind"] == "worker_task_package"
    assert result["protocol_runner"] == "worker_package"
    assert result["protocol_source_path"] == created["package_path"]


def test_prepare_protocol_run_from_filmgen_export_handoff(tmp_path: Path) -> None:
    style_dir = _create_style_package(tmp_path)
    final_video = tmp_path / "final.mp4"
    final_video.write_bytes(b"video")
    handoff_path = tmp_path / "filmgen_handoff.json"
    handoff_path.write_text(
        json.dumps(
            {
                "schema": "smart_video_cut.local.export_filmgen_handoff.v1",
                "schema_version": 1,
                "output_dir": str(tmp_path / "export-out"),
                "final_video": {"ready": True, "path": str(final_video)},
                "toolkit_summary": {
                    "project_id": "filmgen_protocol_case",
                    "creative_objective": "电影感短片",
                    "workflow_kind": "creative_edit_runner",
                },
                "filmgen_contract": {"input_kind": "smart_video_cut_local_export", "supports_plan_only": True},
                "project_pack_export": {"status": "available"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    prepared = prepare_protocol_run(handoff_path, style_package=str(style_dir), output_dir=str(tmp_path / "filmgen-run"))

    assert prepared["ok"] is True
    assert prepared["protocol_kind"] == "filmgen_edit_pack"
    assert prepared["task_payload"]["style_package"] == str(style_dir)
    assert prepared["task_payload"]["input_video"] == str(final_video)
    assert prepared["task_payload"]["output_dir"] == str(tmp_path / "filmgen-run")


def _create_style_package(tmp_path: Path) -> Path:
    template = tmp_path / "template.mp4"
    template.write_bytes(b"template")
    style_dir = tmp_path / "style"
    settings = default_settings_from_options(
        duration=8,
        aspect_ratio="16:9",
        resolution="1280x720",
        quality="standard",
        subtitle_size=40,
        bgm_volume_db=-18,
        voice_provider="edge_tts",
    )
    create_style_package(
        StylePackageRequest(
            name="External Handoff Style",
            template_video=template,
            package_dir=style_dir,
            settings=settings,
        )
    )
    return style_dir
