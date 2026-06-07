from __future__ import annotations

import json
from pathlib import Path

from smart_video_cut.models import LOCAL_EDIT_TASK_SCHEMA
from smart_video_cut.protocol_dropbox import (
    PROTOCOL_DROPBOX_FILENAME,
    PROTOCOL_DROPBOX_HISTORY_FILENAME,
    PROTOCOL_DROPBOX_STATUS_FILENAME,
    get_protocol_dropbox_history,
    import_protocol_dropbox_item,
    initialize_protocol_dropbox,
    requeue_protocol_dropbox_failed,
    run_protocol_dropbox_once,
)
from smart_video_cut.worker_protocol import create_worker_task_package


def test_initialize_protocol_dropbox_writes_manifest_and_templates(tmp_path: Path) -> None:
    dropbox_dir = tmp_path / "protocol-dropbox"

    payload = initialize_protocol_dropbox(dropbox_dir=dropbox_dir)

    assert payload["schema"] == "smart_video_cut.local.protocol_dropbox.v0"
    assert Path(payload["manifest_path"]).is_file()
    assert (dropbox_dir / PROTOCOL_DROPBOX_STATUS_FILENAME).is_file()
    assert (dropbox_dir / PROTOCOL_DROPBOX_HISTORY_FILENAME).is_file()
    assert (dropbox_dir / PROTOCOL_DROPBOX_FILENAME).is_file()
    assert (dropbox_dir / "inbox" / "worker_packages").is_dir()
    assert (dropbox_dir / "archive" / "processed" / "worker_packages").is_dir()
    assert (dropbox_dir / "batch_runs" / "local_edit_tasks").is_dir()
    assert Path(payload["templates"]["local_edit_task"]).is_file()
    assert Path(payload["templates"]["readme"]).is_file()


def test_import_protocol_dropbox_normalizes_output_dir_to_local_edit_task(tmp_path: Path) -> None:
    output_dir = _prepare_output_dir(tmp_path)
    dropbox_dir = tmp_path / "protocol-dropbox"

    payload = import_protocol_dropbox_item(
        source_path=output_dir,
        dropbox_dir=dropbox_dir,
        label="demo-output",
    )

    assert payload["schema"] == "smart_video_cut.local.protocol_dropbox_import.v0"
    assert payload["protocol_kind"] == "local_edit_task"
    assert payload["queue_id"] == "local_edit_tasks"
    assert payload["normalized"] is True
    imported = Path(payload["imported_path"])
    assert imported.is_file()
    imported_payload = json.loads(imported.read_text(encoding="utf-8"))
    assert imported_payload["schema"] == LOCAL_EDIT_TASK_SCHEMA
    assert imported_payload["project_id"] == "demo_project"
    assert imported_payload["style_package"] == "packages/door"


def test_run_protocol_dropbox_once_runs_worker_queue(tmp_path: Path, monkeypatch) -> None:
    dropbox_dir = tmp_path / "protocol-dropbox"
    source_dir = tmp_path / "source-worker"
    created = create_worker_task_package(
        package_dir=source_dir,
        package_name="worker_demo",
        style_package="packages/door",
        input_video="input.mp4",
        input_videos=["input.mp4"],
        output_dir=str(tmp_path / "out"),
        user_request="标准投递箱测试",
        project_id="dropbox_worker",
    )
    imported = import_protocol_dropbox_item(
        source_path=created["package_path"],
        dropbox_dir=dropbox_dir,
        label="worker-demo",
    )

    def fake_run_protocol_path(path, **kwargs):
        return {
            "ok": True,
            "schema": "smart_video_cut.local.worker_completion.v0",
            "protocol_kind": "worker_task_package",
            "protocol_runner": "worker_package",
            "completion_path": str(tmp_path / "out" / "completion.json"),
            "output_dir": str(tmp_path / "out"),
            "path": str(path),
        }

    monkeypatch.setattr("smart_video_cut.watch_queue.run_protocol_path", fake_run_protocol_path)

    payload = run_protocol_dropbox_once(dropbox_dir=dropbox_dir)

    assert payload["schema"] == "smart_video_cut.local.protocol_dropbox_run.v0"
    assert payload["ok"] is True
    assert payload["processed_count"] == 1
    assert Path(payload["status_path"]).is_file()
    assert any(
        queue["queue_id"] == "worker_packages" and queue["processed_count"] == 1
        for queue in payload["queues"]
    )
    assert payload["history_entry"]["processed_count"] == 1
    assert not Path(imported["imported_path"]).exists()
    assert any((dropbox_dir / "archive" / "processed" / "worker_packages").glob("*.json"))
    history = get_protocol_dropbox_history(dropbox_dir=dropbox_dir, limit=5)
    assert history["run_count"] == 1
    assert history["entries"][0]["processed_count"] == 1
    assert history["entries"][0]["alert_count"] == 0


def test_requeue_protocol_dropbox_failed_moves_archived_file(tmp_path: Path) -> None:
    dropbox_dir = tmp_path / "protocol-dropbox"
    payload = initialize_protocol_dropbox(dropbox_dir=dropbox_dir)
    failed_dir = Path(payload["queues"]["worker_packages"]["failed_dir"])
    failed_dir.mkdir(parents=True, exist_ok=True)
    failed_file = failed_dir / "failed_worker.json"
    failed_file.write_text(json.dumps({"schema": "demo"}), encoding="utf-8")

    requeued = requeue_protocol_dropbox_failed(
        dropbox_dir=dropbox_dir,
        queue_id="worker_packages",
        max_files=5,
    )

    assert requeued["schema"] == "smart_video_cut.local.protocol_dropbox_requeue.v0"
    assert requeued["moved_count"] == 1
    assert not failed_file.exists()
    assert Path(requeued["entries"][0]["requeued_path"]).is_file()


def _prepare_output_dir(tmp_path: Path) -> Path:
    output_dir = tmp_path / "output-demo"
    output_dir.mkdir(parents=True, exist_ok=True)
    result = {
        "schema": "smart_video_cut.local.edit_result.v0",
        "ok": True,
        "task_id": "task_demo_dropbox",
        "project_id": "demo_project",
        "style_package": {
            "package_id": "door_style",
            "name": "Door Style",
            "path": "packages/door",
        },
        "input_video": "input.mp4",
        "input_videos": ["input.mp4", "detail.mp4"],
        "user_request": "根据现有输出继续生成新版本",
        "confirmed_brief": "先全景，再锁具。",
        "settings_overrides": {
            "video": {"target_duration_seconds": 15},
        },
        "timeline_override": {
            "segments": [{"segment_id": "seg_001", "caption": "门体展示"}],
        },
    }
    manifest = {
        "schema": "smart_video_cut.local.project_manifest.v0",
        "project_id": "demo_project",
        "style_package": {
            "package_id": "door_style",
            "name": "Door Style",
            "path": "packages/door",
        },
        "input_videos": ["input.mp4", "detail.mp4"],
        "latest_result": result,
        "latest_timeline": result["timeline_override"],
        "user_request": result["user_request"],
    }
    (output_dir / "local_studio_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    (output_dir / "project_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output_dir
