from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from smart_video_cut.web_app import create_app


def test_protocol_build_and_inspect_api(tmp_path: Path) -> None:
    output_dir = _prepare_output_dir(tmp_path)
    client = TestClient(create_app(), raise_server_exceptions=False)

    build_response = client.post("/api/protocol/build", json={"output_dir": str(output_dir)})
    built = build_response.json()

    assert build_response.status_code == 200
    assert built["schema"] == "smart_video_cut.local.toolkit_protocol.v0"
    assert Path(built["protocol_path"]).is_file()

    inspect_response = client.post("/api/protocol/inspect", json={"path": built["protocol_path"]})
    inspected = inspect_response.json()

    assert inspect_response.status_code == 200
    assert inspected["schema"] == "smart_video_cut.local.toolkit_protocol_inspection.v0"
    assert inspected["ok"] is True
    assert inspected["protocol_kind"] == "local_toolkit_protocol"
    assert inspected["summary"]["project_id"] == "demo_project"


def test_protocol_run_api(tmp_path: Path, monkeypatch) -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)

    def fake_run_protocol_path(path, **kwargs):
        return {
            "ok": True,
            "schema": "smart_video_cut.local.edit_result.v0",
            "protocol_kind": "project_pack",
            "protocol_runner": "local_edit_task",
            "protocol_source_path": path,
            "output_dir": str(tmp_path / "out"),
        }

    monkeypatch.setattr("smart_video_cut.web_app.run_protocol_path", fake_run_protocol_path)

    response = client.post(
        "/api/protocol/run",
        json={
            "path": str(tmp_path / "project_pack.json"),
            "output_dir": str(tmp_path / "out"),
            "style_package": "packages/filmgen-cinematic-short",
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["protocol_kind"] == "project_pack"
    assert payload["protocol_runner"] == "local_edit_task"


def test_protocol_dropbox_init_and_import_api(tmp_path: Path) -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)
    output_dir = _prepare_output_dir(tmp_path)

    init_response = client.post(
        "/api/protocol/dropbox/init",
        json={"dropbox_dir": str(tmp_path / "dropbox")},
    )
    init_payload = init_response.json()

    assert init_response.status_code == 200
    assert init_payload["schema"] == "smart_video_cut.local.protocol_dropbox.v0"
    assert Path(init_payload["manifest_path"]).is_file()

    import_response = client.post(
        "/api/protocol/dropbox/import",
        json={
            "dropbox_dir": str(tmp_path / "dropbox"),
            "source_path": str(output_dir),
            "label": "web-demo",
        },
    )
    import_payload = import_response.json()

    assert import_response.status_code == 200
    assert import_payload["schema"] == "smart_video_cut.local.protocol_dropbox_import.v0"
    assert import_payload["queue_id"] == "local_edit_tasks"
    assert Path(import_payload["imported_path"]).is_file()


def test_protocol_dropbox_run_api(tmp_path: Path, monkeypatch) -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)

    def fake_run_protocol_dropbox_once(**kwargs):
        return {
            "ok": True,
            "schema": "smart_video_cut.local.protocol_dropbox_run.v0",
            "dropbox_dir": kwargs["dropbox_dir"],
            "status_path": str(tmp_path / "dropbox" / "dropbox_status.json"),
            "queues": [],
            "processed_count": 0,
            "failed_count": 0,
        }

    monkeypatch.setattr("smart_video_cut.web_app.run_protocol_dropbox_once", fake_run_protocol_dropbox_once)

    response = client.post(
        "/api/protocol/dropbox/run",
        json={
            "dropbox_dir": str(tmp_path / "dropbox"),
            "default_execute_real_render": True,
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["schema"] == "smart_video_cut.local.protocol_dropbox_run.v0"


def test_protocol_dropbox_monitor_api(tmp_path: Path, monkeypatch) -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)

    def fake_start_protocol_dropbox_monitor(**kwargs):
        return {
            "ok": True,
            "schema": "smart_video_cut.local.protocol_dropbox_monitor.v0",
            "dropbox_dir": kwargs["dropbox_dir"],
            "monitor_path": str(tmp_path / "dropbox" / "dropbox_monitor.json"),
            "running": True,
            "status": "running",
            "interval_seconds": kwargs["interval_seconds"],
            "max_cycles": kwargs["max_cycles"],
            "totals": {},
        }

    def fake_get_protocol_dropbox_monitor_status(**kwargs):
        return {
            "ok": True,
            "schema": "smart_video_cut.local.protocol_dropbox_monitor.v0",
            "dropbox_dir": kwargs["dropbox_dir"],
            "monitor_path": str(tmp_path / "dropbox" / "dropbox_monitor.json"),
            "running": False,
            "status": "completed",
            "interval_seconds": 15,
            "max_cycles": 1,
            "totals": {"processed_count": 2},
        }

    def fake_stop_protocol_dropbox_monitor(**kwargs):
        return {
            "ok": True,
            "schema": "smart_video_cut.local.protocol_dropbox_monitor.v0",
            "dropbox_dir": kwargs["dropbox_dir"],
            "monitor_path": str(tmp_path / "dropbox" / "dropbox_monitor.json"),
            "running": False,
            "status": "stopped",
            "stop_requested": True,
            "totals": {},
        }

    monkeypatch.setattr("smart_video_cut.web_app.start_protocol_dropbox_monitor", fake_start_protocol_dropbox_monitor)
    monkeypatch.setattr("smart_video_cut.web_app.get_protocol_dropbox_monitor_status", fake_get_protocol_dropbox_monitor_status)
    monkeypatch.setattr("smart_video_cut.web_app.stop_protocol_dropbox_monitor", fake_stop_protocol_dropbox_monitor)

    start_response = client.post(
        "/api/protocol/dropbox/monitor/start",
        json={
            "dropbox_dir": str(tmp_path / "dropbox"),
            "interval_seconds": 5,
            "max_cycles": 3,
        },
    )
    status_response = client.post(
        "/api/protocol/dropbox/monitor/status",
        json={"dropbox_dir": str(tmp_path / "dropbox")},
    )
    stop_response = client.post(
        "/api/protocol/dropbox/monitor/stop",
        json={"dropbox_dir": str(tmp_path / "dropbox")},
    )

    assert start_response.status_code == 200
    assert start_response.json()["running"] is True
    assert status_response.status_code == 200
    assert status_response.json()["status"] == "completed"
    assert stop_response.status_code == 200
    assert stop_response.json()["stop_requested"] is True


def test_protocol_dropbox_history_and_requeue_api(tmp_path: Path, monkeypatch) -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)
    captured = {}

    def fake_get_protocol_dropbox_history(**kwargs):
        captured["history"] = kwargs
        return {
            "ok": True,
            "schema": "smart_video_cut.local.protocol_dropbox_history.v0",
            "dropbox_dir": kwargs["dropbox_dir"],
            "history_path": str(tmp_path / "dropbox" / "dropbox_history.json"),
            "run_count": 3,
            "alert_entry_count": 1,
            "last_alert_level": "warn",
            "entries": [],
        }

    def fake_requeue_protocol_dropbox_failed(**kwargs):
        captured["requeue"] = kwargs
        return {
            "ok": True,
            "schema": "smart_video_cut.local.protocol_dropbox_requeue.v0",
            "dropbox_dir": kwargs["dropbox_dir"],
            "queue_id": kwargs["queue_id"],
            "max_files": kwargs["max_files"],
            "moved_count": 2,
            "queues": [],
            "entries": [],
        }

    monkeypatch.setattr("smart_video_cut.web_app.get_protocol_dropbox_history", fake_get_protocol_dropbox_history)
    monkeypatch.setattr("smart_video_cut.web_app.requeue_protocol_dropbox_failed", fake_requeue_protocol_dropbox_failed)

    history_response = client.post(
        "/api/protocol/dropbox/history",
        json={
            "dropbox_dir": str(tmp_path / "dropbox"),
            "limit": 5,
            "queue_id": "worker_packages",
            "alerts_only": True,
        },
    )
    requeue_response = client.post(
        "/api/protocol/dropbox/requeue-failed",
        json={
            "dropbox_dir": str(tmp_path / "dropbox"),
            "queue_id": "worker_packages",
            "max_files": 3,
        },
    )

    assert history_response.status_code == 200
    assert history_response.json()["schema"] == "smart_video_cut.local.protocol_dropbox_history.v0"
    assert captured["history"]["limit"] == 5
    assert captured["history"]["queue_id"] == "worker_packages"
    assert captured["history"]["alerts_only"] is True
    assert requeue_response.status_code == 200
    assert requeue_response.json()["schema"] == "smart_video_cut.local.protocol_dropbox_requeue.v0"
    assert captured["requeue"]["queue_id"] == "worker_packages"
    assert captured["requeue"]["max_files"] == 3


def _prepare_output_dir(tmp_path: Path) -> Path:
    output_dir = tmp_path / "out"
    output_dir.mkdir(parents=True, exist_ok=True)
    final_video = output_dir / "final.mp4"
    final_video.write_bytes(b"final")

    result = {
        "schema": "smart_video_cut.local.edit_result.v0",
        "ok": True,
        "task_id": "task_protocol_web",
        "output_dir": str(output_dir),
        "input_videos": ["input.mp4"],
        "input_video_count": 1,
        "copied_output_video": str(final_video),
        "execute_real_render": False,
        "style_package": {"package_id": "door_style", "name": "Door Style", "path": "packages/door"},
        "subtitle_adapter_result": {},
        "export_adapter_result": {
            "exports": {
                "project_pack": {
                    "status": "available",
                    "api_endpoint": "/api/packs/project/export",
                    "cli_command": "export-project-pack",
                    "agent_tool": "export_project_pack",
                }
            }
        },
        "toolkit_summary": {
            "project_id": "demo_project",
            "workflow_kind": "creative_edit_runner",
            "execution_mode": "plan_only",
        },
    }
    (output_dir / "local_studio_result.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    manifest = {
        "schema": "smart_video_cut.local.project_manifest.v0",
        "project_id": "demo_project",
        "output_dir": str(output_dir),
        "input_videos": ["input.mp4"],
        "input_video_count": 1,
        "latest_result_path": str(output_dir / "local_studio_result.json"),
        "copied_output_video": str(final_video),
        "version_history": {"current_version": 1, "version_count": 1, "versions": [{"version": 1}]},
    }
    (output_dir / "project_manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return output_dir
