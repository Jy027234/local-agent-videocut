from __future__ import annotations

import time
from pathlib import Path

from smart_video_cut.protocol_dropbox_monitor import (
    get_protocol_dropbox_monitor_status,
    run_protocol_dropbox_monitor_loop,
    start_protocol_dropbox_monitor,
    stop_protocol_dropbox_monitor,
)


def test_run_protocol_dropbox_monitor_loop_accumulates_cycles(tmp_path: Path, monkeypatch) -> None:
    calls = {"count": 0}

    def fake_run_protocol_dropbox_once(**kwargs):
        calls["count"] += 1
        return {
            "ok": True,
            "schema": "smart_video_cut.local.protocol_dropbox_run.v0",
            "status": "completed",
            "dropbox_dir": str(tmp_path / "dropbox"),
            "status_path": str(tmp_path / "dropbox" / "dropbox_status.json"),
            "history_path": str(tmp_path / "dropbox" / "dropbox_history.json"),
            "file_count": 1,
            "queued_count": 2,
            "processed_count": 1,
            "failed_count": 0,
            "error_count": 0,
            "alert_count": 0,
            "alert_level": "ok",
            "alerts": [],
            "elapsed_seconds": 0.01,
            "queues": [],
        }

    monkeypatch.setattr(
        "smart_video_cut.protocol_dropbox_monitor.run_protocol_dropbox_once",
        fake_run_protocol_dropbox_once,
    )

    payload = run_protocol_dropbox_monitor_loop(
        dropbox_dir=tmp_path / "dropbox",
        interval_seconds=0.01,
        max_cycles=2,
    )

    assert payload["schema"] == "smart_video_cut.local.protocol_dropbox_monitor.v0"
    assert payload["ok"] is True
    assert payload["status"] == "completed"
    assert payload["completed_cycles"] == 2
    assert payload["totals"]["processed_count"] == 2
    assert payload["history_path"].endswith("dropbox_history.json")
    assert len(payload["recent_runs"]) == 2
    assert calls["count"] == 2


def test_start_and_stop_protocol_dropbox_monitor_updates_status(tmp_path: Path, monkeypatch) -> None:
    def fake_run_protocol_dropbox_once(**kwargs):
        return {
            "ok": True,
            "schema": "smart_video_cut.local.protocol_dropbox_run.v0",
            "status": "completed",
            "dropbox_dir": str(tmp_path / "dropbox"),
            "status_path": str(tmp_path / "dropbox" / "dropbox_status.json"),
            "history_path": str(tmp_path / "dropbox" / "dropbox_history.json"),
            "file_count": 0,
            "queued_count": 0,
            "processed_count": 0,
            "failed_count": 0,
            "error_count": 0,
            "alert_count": 0,
            "alert_level": "ok",
            "alerts": [],
            "elapsed_seconds": 0.0,
            "queues": [],
        }

    monkeypatch.setattr(
        "smart_video_cut.protocol_dropbox_monitor.run_protocol_dropbox_once",
        fake_run_protocol_dropbox_once,
    )

    started = start_protocol_dropbox_monitor(
        dropbox_dir=tmp_path / "dropbox",
        interval_seconds=0.05,
        max_cycles=0,
    )
    time.sleep(0.08)
    running = get_protocol_dropbox_monitor_status(dropbox_dir=tmp_path / "dropbox")
    stopped = stop_protocol_dropbox_monitor(dropbox_dir=tmp_path / "dropbox")
    time.sleep(0.08)
    final = get_protocol_dropbox_monitor_status(dropbox_dir=tmp_path / "dropbox")

    assert started["schema"] == "smart_video_cut.local.protocol_dropbox_monitor.v0"
    assert running["running"] is True
    assert stopped["stop_requested"] is True
    assert final["running"] is False
    assert final["status"] in {"stopped", "completed", "completed_with_errors"}


def test_run_protocol_dropbox_monitor_loop_tracks_alerts(tmp_path: Path, monkeypatch) -> None:
    def fake_run_protocol_dropbox_once(**kwargs):
        return {
            "ok": False,
            "schema": "smart_video_cut.local.protocol_dropbox_run.v0",
            "status": "completed_with_errors",
            "dropbox_dir": str(tmp_path / "dropbox"),
            "status_path": str(tmp_path / "dropbox" / "dropbox_status.json"),
            "history_path": str(tmp_path / "dropbox" / "dropbox_history.json"),
            "file_count": 1,
            "queued_count": 1,
            "processed_count": 0,
            "failed_count": 1,
            "error_count": 1,
            "alert_count": 2,
            "alert_level": "warn",
            "alerts": [
                {"code": "failed_files_detected", "level": "warn"},
                {"code": "worker_packages_failed", "level": "warn"},
            ],
            "elapsed_seconds": 0.02,
            "queues": [],
        }

    monkeypatch.setattr(
        "smart_video_cut.protocol_dropbox_monitor.run_protocol_dropbox_once",
        fake_run_protocol_dropbox_once,
    )

    payload = run_protocol_dropbox_monitor_loop(
        dropbox_dir=tmp_path / "dropbox",
        interval_seconds=0.0,
        max_cycles=1,
    )

    assert payload["status"] == "completed_with_errors"
    assert payload["ok"] is False
    assert payload["alert_count"] == 2
    assert payload["last_alert_level"] == "warn"
    assert len(payload["active_alerts"]) == 2
    assert payload["recent_runs"][0]["alert_count"] == 2
