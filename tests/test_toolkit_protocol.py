from __future__ import annotations

import json
from pathlib import Path

from smart_video_cut.protocol_dropbox import initialize_protocol_dropbox
from smart_video_cut.protocol_dropbox_monitor import run_protocol_dropbox_monitor_loop
from smart_video_cut.toolkit_protocol import (
    LOCAL_TOOLKIT_PROTOCOL_FILENAME,
    LOCAL_TOOLKIT_PROTOCOL_INSPECTION_SCHEMA,
    LOCAL_TOOLKIT_PROTOCOL_SCHEMA,
    inspect_local_toolkit_path,
    write_local_toolkit_protocol,
)
from smart_video_cut.worker_protocol import create_worker_task_package


def test_write_local_toolkit_protocol_writes_manifest(tmp_path: Path) -> None:
    output_dir = _prepare_output_dir(tmp_path)

    payload = write_local_toolkit_protocol(output_dir=output_dir)

    assert payload["schema"] == LOCAL_TOOLKIT_PROTOCOL_SCHEMA
    assert payload["project_id"] == "demo_project"
    assert Path(payload["protocol_path"]).is_file()
    assert any(item["artifact_id"] == "local_studio_result" and item["ready"] is True for item in payload["artifacts"])
    assert any(item["artifact_id"] == "filmgen_export_handoff" and item["ready"] is True for item in payload["artifacts"])


def test_inspect_local_toolkit_protocol_and_directory(tmp_path: Path) -> None:
    output_dir = _prepare_output_dir(tmp_path)
    payload = write_local_toolkit_protocol(output_dir=output_dir)

    file_inspection = inspect_local_toolkit_path(payload["protocol_path"])
    directory_inspection = inspect_local_toolkit_path(output_dir)

    assert file_inspection["schema"] == LOCAL_TOOLKIT_PROTOCOL_INSPECTION_SCHEMA
    assert file_inspection["ok"] is True
    assert file_inspection["protocol_kind"] == "local_toolkit_protocol"
    assert file_inspection["summary"]["artifact_count"] >= 4
    assert directory_inspection["ok"] is True
    assert directory_inspection["protocol_kind"] == "directory_index"
    assert directory_inspection["recognized_file_count"] >= 3


def test_inspect_worker_task_package_returns_summary(tmp_path: Path) -> None:
    created = create_worker_task_package(
        package_dir=tmp_path / "worker-job",
        package_name="door_worker",
        style_package="packages/door",
        input_video="input.mp4",
        input_videos=["input.mp4", "detail.mp4"],
        output_dir=str(tmp_path / "out"),
        user_request="防盗门快闪广告",
        confirmed_brief="先稳住整体，再切锁芯细节",
    )

    inspection = inspect_local_toolkit_path(created["package_path"])

    assert inspection["schema"] == LOCAL_TOOLKIT_PROTOCOL_INSPECTION_SCHEMA
    assert inspection["ok"] is True
    assert inspection["protocol_kind"] == "worker_task_package"
    assert inspection["summary"]["input_video_count"] == 2
    assert inspection["summary"]["status"] == "pending"


def test_inspect_protocol_dropbox_manifest_and_status(tmp_path: Path) -> None:
    payload = initialize_protocol_dropbox(dropbox_dir=tmp_path / "dropbox")

    manifest_inspection = inspect_local_toolkit_path(payload["manifest_path"])
    status_inspection = inspect_local_toolkit_path(payload["status_path"])

    assert manifest_inspection["schema"] == LOCAL_TOOLKIT_PROTOCOL_INSPECTION_SCHEMA
    assert manifest_inspection["ok"] is True
    assert manifest_inspection["protocol_kind"] == "protocol_dropbox"
    assert manifest_inspection["summary"]["queue_count"] == 5
    assert status_inspection["protocol_kind"] == "protocol_dropbox_run"
    assert status_inspection["summary"]["status"] == "idle"
    run_protocol_dropbox_monitor_loop(
        dropbox_dir=tmp_path / "dropbox",
        interval_seconds=0.0,
        max_cycles=1,
        dry_run=True,
    )
    monitor_inspection = inspect_local_toolkit_path(tmp_path / "dropbox" / "dropbox_monitor.json")
    history_inspection = inspect_local_toolkit_path(tmp_path / "dropbox" / "dropbox_history.json")
    assert monitor_inspection["protocol_kind"] == "protocol_dropbox_monitor"
    assert monitor_inspection["summary"]["completed_cycles"] == 1
    assert history_inspection["protocol_kind"] == "protocol_dropbox_history"
    assert history_inspection["summary"]["run_count"] == 1


def _prepare_output_dir(tmp_path: Path) -> Path:
    output_dir = tmp_path / "out"
    output_dir.mkdir(parents=True, exist_ok=True)
    final_video = output_dir / "final.mp4"
    final_video.write_bytes(b"final video")

    subtitle_dir = output_dir / "_smart_video_cut_artifacts" / "_filmgen_subtitle_handoff"
    subtitle_dir.mkdir(parents=True, exist_ok=True)
    subtitle_path = subtitle_dir / "subtitle_handoff.json"
    subtitle_path.write_text(
        json.dumps(
            {
                "schema": "smart_video_cut.local.filmgen_subtitle_handoff.v0",
                "adapter_id": "subtitle.filmgen",
                "mode": "filmgen",
                "status": "ready",
                "subtitle_texts": ["门体展示", "锁芯特写"],
                "style": {"font_size": 44},
                "track_request": {"target": "external_filmgen_subtitle_track"},
                "renderer_contract": {"current_renderer_subtitle_enabled": False},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    filmgen_handoff_path = output_dir / "filmgen_handoff.json"
    filmgen_handoff_path.write_text(
        json.dumps(
            {
                "schema": "smart_video_cut.local.export_filmgen_handoff.v1",
                "schema_version": 1,
                "status": "ready",
                "output_dir": str(output_dir),
                "final_video": {"ready": True, "path": str(final_video)},
                "toolkit_summary": {
                    "project_id": "demo_project",
                    "workflow_kind": "creative_edit_runner",
                    "creative_objective": "防盗门快闪广告",
                },
                "filmgen_contract": {"reader_endpoint": "/api/filmgen/export-handoff/validate"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    result = {
        "schema": "smart_video_cut.local.edit_result.v0",
        "ok": True,
        "task_id": "task_demo_001",
        "output_dir": str(output_dir),
        "input_videos": ["input.mp4", "detail.mp4"],
        "input_video_count": 2,
        "execute_real_render": True,
        "copied_output_video": str(final_video),
        "style_package": {"package_id": "door_style", "name": "Door Style", "path": "packages/door"},
        "subtitle_adapter_result": {"handoff_path": str(subtitle_path)},
        "export_adapter_result": {
            "exports": {
                "project_pack": {
                    "status": "available",
                    "api_endpoint": "/api/packs/project/export",
                    "cli_command": "export-project-pack",
                    "agent_tool": "export_project_pack",
                },
                "filmgen_handoff": {
                    "handoff_path": str(filmgen_handoff_path),
                    "status": "completed",
                    "ok": True,
                },
            }
        },
        "toolkit_summary": {
            "project_id": "demo_project",
            "workflow_kind": "creative_edit_runner",
            "execution_mode": "worker_real_render",
        },
        "current_version": 2,
    }
    (output_dir / "local_studio_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )

    manifest = {
        "schema": "smart_video_cut.local.project_manifest.v0",
        "project_id": "demo_project",
        "output_dir": str(output_dir),
        "input_videos": ["input.mp4", "detail.mp4"],
        "input_video_count": 2,
        "copied_output_video": str(final_video),
        "last_event": "render_completed",
        "latest_result_path": str(output_dir / "local_studio_result.json"),
        "latest_result": result,
        "version_history": {
            "current_version": 2,
            "version_count": 2,
            "versions": [{"version": 1}, {"version": 2}],
        },
    }
    (output_dir / LOCAL_TOOLKIT_PROTOCOL_FILENAME).unlink(missing_ok=True)
    (output_dir / "project_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output_dir
