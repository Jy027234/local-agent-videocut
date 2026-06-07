from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping

from smart_video_cut.protocol_dropbox import (
    PROTOCOL_DROPBOX_FILENAME,
    PROTOCOL_DROPBOX_HISTORY_FILENAME,
    PROTOCOL_DROPBOX_RUN_SCHEMA,
    initialize_protocol_dropbox,
    run_protocol_dropbox_once,
)


PROTOCOL_DROPBOX_MONITOR_SCHEMA = "smart_video_cut.local.protocol_dropbox_monitor.v0"
PROTOCOL_DROPBOX_MONITOR_FILENAME = "dropbox_monitor.json"

_RECENT_RUN_LIMIT = 12
_MONITOR_HANDLES: dict[str, "_MonitorHandle"] = {}
_MONITOR_LOCK = threading.Lock()


@dataclass(slots=True)
class _MonitorHandle:
    thread: threading.Thread
    stop_event: threading.Event


def run_protocol_dropbox_monitor_loop(
    *,
    dropbox_dir: str | Path = "",
    interval_seconds: float = 15.0,
    max_cycles: int = 0,
    default_execute_real_render: bool = False,
    stop_on_error: bool = False,
    max_retries: int = 0,
    dry_run: bool = False,
    stop_event: threading.Event | None = None,
    on_update: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
    if interval_seconds < 0:
        raise ValueError("interval_seconds must be >= 0")
    if max_cycles < 0:
        raise ValueError("max_cycles must be >= 0")
    manifest = initialize_protocol_dropbox(dropbox_dir=dropbox_dir)
    root = Path(manifest["dropbox_dir"])
    monitor_path = root / PROTOCOL_DROPBOX_MONITOR_FILENAME
    status = _default_monitor_payload(
        manifest=manifest,
        interval_seconds=float(interval_seconds),
        max_cycles=int(max_cycles),
        default_execute_real_render=default_execute_real_render,
        stop_on_error=stop_on_error,
        max_retries=max_retries,
        dry_run=dry_run,
    )
    started_at = time.time()
    status["status"] = "running"
    status["running"] = True
    status["started_at"] = started_at
    status["finished_at"] = None
    status["elapsed_seconds"] = 0.0
    _emit_status(monitor_path, status, on_update=on_update)

    try:
        while True:
            if stop_event is not None and stop_event.is_set():
                status["status"] = "stopped"
                status["stop_requested"] = True
                break
            if max_cycles > 0 and int(status["completed_cycles"]) >= max_cycles:
                status["status"] = "completed_with_errors" if status["ok"] is not True else "completed"
                break

            cycle_index = int(status["completed_cycles"]) + 1
            status["current_cycle"] = cycle_index
            status["last_cycle_started_at"] = time.time()
            status["last_cycle_finished_at"] = None
            status["next_poll_at"] = None
            _emit_status(monitor_path, status, on_update=on_update)

            run_result = run_protocol_dropbox_once(
                dropbox_dir=root,
                default_execute_real_render=default_execute_real_render,
                stop_on_error=stop_on_error,
                max_retries=max_retries,
                dry_run=dry_run,
            )
            cycle_summary = _cycle_summary(cycle_index=cycle_index, run_result=run_result)
            status["last_run"] = cycle_summary
            recent_runs = list(status.get("recent_runs") or [])
            recent_runs.append(cycle_summary)
            status["recent_runs"] = recent_runs[-_RECENT_RUN_LIMIT:]
            status["completed_cycles"] = cycle_index
            status["current_cycle"] = cycle_index
            status["last_cycle_finished_at"] = time.time()
            status["last_run_status_path"] = run_result.get("status_path") or ""
            status["history_path"] = run_result.get("history_path") or status.get("history_path") or ""
            status["active_alerts"] = list(run_result.get("alerts") or [])
            status["alert_count"] = int(run_result.get("alert_count") or 0)
            status["last_alert_level"] = str(run_result.get("alert_level") or "ok")
            status["totals"] = _merge_totals(_mapping(status.get("totals")), run_result)
            if run_result.get("ok") is not True:
                status["ok"] = False
            _emit_status(monitor_path, status, on_update=on_update)

            if max_cycles > 0 and cycle_index >= max_cycles:
                status["status"] = "completed_with_errors" if status["ok"] is not True else "completed"
                break
            if stop_on_error and run_result.get("ok") is not True:
                status["status"] = "stopped_on_error"
                break

            next_poll_at = time.time() + max(0.0, float(interval_seconds))
            status["next_poll_at"] = next_poll_at
            _emit_status(monitor_path, status, on_update=on_update)

            if stop_event is not None:
                if stop_event.wait(max(0.0, float(interval_seconds))):
                    status["status"] = "stopped"
                    status["stop_requested"] = True
                    break
            elif interval_seconds > 0:
                time.sleep(float(interval_seconds))
    except KeyboardInterrupt:
        status["status"] = "stopped"
        status["stop_requested"] = True
    finally:
        status["running"] = False
        status["finished_at"] = time.time()
        status["elapsed_seconds"] = round(float(status["finished_at"]) - started_at, 3)
        status["next_poll_at"] = None
        _emit_status(monitor_path, status, on_update=on_update)
    return status


def start_protocol_dropbox_monitor(
    *,
    dropbox_dir: str | Path = "",
    interval_seconds: float = 15.0,
    max_cycles: int = 0,
    default_execute_real_render: bool = False,
    stop_on_error: bool = False,
    max_retries: int = 0,
    dry_run: bool = False,
) -> dict[str, Any]:
    manifest = initialize_protocol_dropbox(dropbox_dir=dropbox_dir)
    root = Path(manifest["dropbox_dir"])
    root_key = str(root.resolve())
    with _MONITOR_LOCK:
        existing = _MONITOR_HANDLES.get(root_key)
        if existing and existing.thread.is_alive():
            status = get_protocol_dropbox_monitor_status(dropbox_dir=root)
            status["already_running"] = True
            return status
        stop_event = threading.Event()
        monitor_path = root / PROTOCOL_DROPBOX_MONITOR_FILENAME
        starting_payload = _default_monitor_payload(
            manifest=manifest,
            interval_seconds=float(interval_seconds),
            max_cycles=int(max_cycles),
            default_execute_real_render=default_execute_real_render,
            stop_on_error=stop_on_error,
            max_retries=max_retries,
            dry_run=dry_run,
        )
        starting_payload["status"] = "starting"
        starting_payload["running"] = True
        _write_monitor_status(monitor_path, starting_payload)

        def runner() -> None:
            try:
                run_protocol_dropbox_monitor_loop(
                    dropbox_dir=root,
                    interval_seconds=interval_seconds,
                    max_cycles=max_cycles,
                    default_execute_real_render=default_execute_real_render,
                    stop_on_error=stop_on_error,
                    max_retries=max_retries,
                    dry_run=dry_run,
                    stop_event=stop_event,
                )
            finally:
                with _MONITOR_LOCK:
                    current = _MONITOR_HANDLES.get(root_key)
                    if current and current.stop_event is stop_event:
                        _MONITOR_HANDLES.pop(root_key, None)

        thread = threading.Thread(
            target=runner,
            name=f"protocol_dropbox_monitor_{root.name}",
            daemon=True,
        )
        _MONITOR_HANDLES[root_key] = _MonitorHandle(thread=thread, stop_event=stop_event)
        thread.start()
    status = get_protocol_dropbox_monitor_status(dropbox_dir=root)
    status["already_running"] = False
    return status


def stop_protocol_dropbox_monitor(
    *,
    dropbox_dir: str | Path = "",
) -> dict[str, Any]:
    manifest = initialize_protocol_dropbox(dropbox_dir=dropbox_dir)
    root = Path(manifest["dropbox_dir"])
    root_key = str(root.resolve())
    with _MONITOR_LOCK:
        handle = _MONITOR_HANDLES.get(root_key)
    if not handle or not handle.thread.is_alive():
        status = get_protocol_dropbox_monitor_status(dropbox_dir=root)
        status["already_stopped"] = True
        status["running"] = False
        return status
    handle.stop_event.set()
    handle.thread.join(timeout=0.5)
    status = get_protocol_dropbox_monitor_status(dropbox_dir=root)
    status["already_stopped"] = False
    status["stop_requested"] = True
    if handle.thread.is_alive():
        status["status"] = "stopping"
        status["running"] = True
    return status


def get_protocol_dropbox_monitor_status(
    *,
    dropbox_dir: str | Path = "",
) -> dict[str, Any]:
    manifest = initialize_protocol_dropbox(dropbox_dir=dropbox_dir)
    root = Path(manifest["dropbox_dir"])
    monitor_path = root / PROTOCOL_DROPBOX_MONITOR_FILENAME
    payload = _read_monitor_status(monitor_path) or _default_monitor_payload(
        manifest=manifest,
        interval_seconds=15.0,
        max_cycles=0,
        default_execute_real_render=False,
        stop_on_error=False,
        max_retries=0,
        dry_run=False,
    )
    root_key = str(root.resolve())
    with _MONITOR_LOCK:
        handle = _MONITOR_HANDLES.get(root_key)
        running = bool(handle and handle.thread.is_alive())
        stop_requested = bool(handle and handle.stop_event.is_set())
    payload["running"] = running
    payload["stop_requested"] = stop_requested or bool(payload.get("stop_requested"))
    return payload


def _default_monitor_payload(
    *,
    manifest: Mapping[str, Any],
    interval_seconds: float,
    max_cycles: int,
    default_execute_real_render: bool,
    stop_on_error: bool,
    max_retries: int,
    dry_run: bool,
) -> dict[str, Any]:
    dropbox_dir = str(manifest.get("dropbox_dir") or "")
    root = Path(dropbox_dir)
    return {
        "schema": PROTOCOL_DROPBOX_MONITOR_SCHEMA,
        "ok": True,
        "status": "idle",
        "running": False,
        "stop_requested": False,
        "dropbox_dir": dropbox_dir,
        "manifest_path": str(manifest.get("manifest_path") or (root / PROTOCOL_DROPBOX_FILENAME)),
        "monitor_path": str(root / PROTOCOL_DROPBOX_MONITOR_FILENAME),
        "status_path": str(root / "dropbox_status.json"),
        "history_path": str(manifest.get("history_path") or (root / PROTOCOL_DROPBOX_HISTORY_FILENAME)),
        "interval_seconds": float(interval_seconds),
        "max_cycles": int(max_cycles),
        "completed_cycles": 0,
        "current_cycle": 0,
        "default_execute_real_render": default_execute_real_render,
        "stop_on_error": stop_on_error,
        "max_retries": int(max_retries),
        "dry_run": dry_run,
        "queue_count": int(manifest.get("queue_count") or 0),
        "queue_order": list(manifest.get("queue_order") or []),
        "started_at": None,
        "finished_at": None,
        "elapsed_seconds": 0.0,
        "last_cycle_started_at": None,
        "last_cycle_finished_at": None,
        "next_poll_at": None,
        "last_run_status_path": "",
        "last_run": {},
        "recent_runs": [],
        "active_alerts": [],
        "alert_count": 0,
        "last_alert_level": "ok",
        "totals": {
            "file_count": 0,
            "queued_count": 0,
            "processed_count": 0,
            "failed_count": 0,
            "error_count": 0,
        },
    }


def _cycle_summary(*, cycle_index: int, run_result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "cycle_index": int(cycle_index),
        "ok": run_result.get("ok") is True,
        "status": str(run_result.get("status") or ""),
        "dropbox_dir": str(run_result.get("dropbox_dir") or ""),
        "status_path": str(run_result.get("status_path") or ""),
        "file_count": int(run_result.get("file_count") or 0),
        "queued_count": int(run_result.get("queued_count") or 0),
        "processed_count": int(run_result.get("processed_count") or 0),
        "failed_count": int(run_result.get("failed_count") or 0),
        "error_count": int(run_result.get("error_count") or 0),
        "alert_count": int(run_result.get("alert_count") or 0),
        "alert_level": str(run_result.get("alert_level") or "ok"),
        "alerts": list(run_result.get("alerts") or []),
        "elapsed_seconds": float(run_result.get("elapsed_seconds") or 0.0),
        "queues": list(run_result.get("queues") or []),
        "finished_at": time.time(),
    }


def _merge_totals(current: Mapping[str, Any], run_result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "file_count": int(current.get("file_count") or 0) + int(run_result.get("file_count") or 0),
        "queued_count": int(current.get("queued_count") or 0) + int(run_result.get("queued_count") or 0),
        "processed_count": int(current.get("processed_count") or 0) + int(run_result.get("processed_count") or 0),
        "failed_count": int(current.get("failed_count") or 0) + int(run_result.get("failed_count") or 0),
        "error_count": int(current.get("error_count") or 0) + int(run_result.get("error_count") or 0),
    }


def _emit_status(
    monitor_path: Path,
    status: Mapping[str, Any],
    *,
    on_update: Callable[[dict[str, Any]], None] | None = None,
) -> None:
    payload = dict(status)
    _write_monitor_status(monitor_path, payload)
    if on_update is not None:
        on_update(payload)


def _write_monitor_status(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(
        json.dumps(dict(payload), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _read_monitor_status(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _mapping(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}
