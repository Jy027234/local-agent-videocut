from __future__ import annotations

import json
from pathlib import Path

from smart_video_cut import cli
from smart_video_cut.agent_tools import build_default_registry
from smart_video_cut.batch_runner import run_batch_edits
from smart_video_cut.watch_queue import run_watch_queue_once


def test_batch_runner_writes_status_file(tmp_path: Path, monkeypatch) -> None:
    def fake_run_edit(task):
        task.output_dir.mkdir(parents=True, exist_ok=True)
        (task.output_dir / "local_studio_result.json").write_text("{}", encoding="utf-8")
        return {"ok": True, "toolkit_status": "plan_only", "current_version": 1}

    monkeypatch.setattr("smart_video_cut.batch_runner.run_edit_with_style_package", fake_run_edit)

    result = run_batch_edits(
        tasks=[
            {
                "name": "case 1",
                "style_package": "style",
                "input_video": "input.mp4",
                "output_dir": str(tmp_path / "out1"),
                "user_request": "批量测试",
            }
        ],
        batch_dir=tmp_path / "batch",
        batch_id="batch_test",
    )

    assert result["ok"] is True
    assert result["completed_count"] == 1
    status_path = tmp_path / "batch" / "batch_status.json"
    assert status_path.is_file()
    status = json.loads(status_path.read_text(encoding="utf-8"))
    assert status["tasks"][0]["status"] == "completed"
    assert status["tasks"][0]["result_path"].endswith("local_studio_result.json")


def test_batch_runner_retries_failed_task(tmp_path: Path, monkeypatch) -> None:
    calls = {"count": 0}

    def flaky_run_edit(task):
        calls["count"] += 1
        if calls["count"] == 1:
            return {"ok": False, "reason": "temporary_failure"}
        task.output_dir.mkdir(parents=True, exist_ok=True)
        (task.output_dir / "local_studio_result.json").write_text("{}", encoding="utf-8")
        return {"ok": True, "toolkit_status": "plan_only", "current_version": 2}

    monkeypatch.setattr("smart_video_cut.batch_runner.run_edit_with_style_package", flaky_run_edit)

    result = run_batch_edits(
        tasks=[
            {
                "name": "flaky",
                "style_package": "style",
                "input_video": "input.mp4",
                "output_dir": str(tmp_path / "out-flaky"),
                "user_request": "重试测试",
            }
        ],
        batch_dir=tmp_path / "batch-retry",
        max_retries=1,
    )

    assert result["ok"] is True
    assert result["retry_count"] == 1
    task = result["tasks"][0]
    assert task["status"] == "completed"
    assert task["attempt_count"] == 2
    assert task["retry_count"] == 1
    assert task["attempts"][0]["error"] == "temporary_failure"
    assert task["attempts"][1]["status"] == "completed"


def test_agent_registry_exposes_headless_project_tools(tmp_path: Path) -> None:
    registry = build_default_registry()
    manifest = registry.to_manifest()
    tool_ids = {tool["tool_id"] for tool in manifest["tools"]}

    assert "re_edit_version" in tool_ids
    assert "batch_run_edit" in tool_ids
    assert "export_project_pack" in tool_ids
    assert "validate_project" in tool_ids
    assert "watch_queue_once" in tool_ids
    assert "chat_director" in tool_ids
    assert "orchestrate_local_agents" in tool_ids
    assert "build_worker_task_package" in tool_ids
    assert "run_worker_task_package" in tool_ids
    assert "build_local_toolkit_protocol" in tool_ids
    assert "inspect_local_toolkit_protocol" in tool_ids
    assert "run_protocol_path" in tool_ids
    assert "init_protocol_dropbox" in tool_ids
    assert "import_protocol_dropbox_item" in tool_ids
    assert "run_protocol_dropbox_once" in tool_ids
    assert "run_protocol_dropbox_monitor" in tool_ids
    assert "start_protocol_dropbox_monitor" in tool_ids
    assert "stop_protocol_dropbox_monitor" in tool_ids
    assert "get_protocol_dropbox_monitor_status" in tool_ids
    assert "get_protocol_dropbox_history" in tool_ids
    assert "requeue_protocol_dropbox_failed" in tool_ids

    result = registry.invoke("validate_project", output_dir=str(tmp_path / "missing"))

    assert result["ok"] is True
    assert result["valid"] is True
    assert any(item["code"] == "project_manifest_not_found" for item in result["warnings"])

    missing_watch_dir = registry.invoke("watch_queue_once")

    assert missing_watch_dir["ok"] is False
    assert "watch_dir is required" in missing_watch_dir["error"]


def test_cli_batch_run_uses_tasks_json(tmp_path: Path, monkeypatch, capsys) -> None:
    tasks_json = tmp_path / "tasks.json"
    tasks_json.write_text(
        json.dumps({"tasks": [{"name": "case", "style_package": "style"}]}, ensure_ascii=False),
        encoding="utf-8",
    )
    captured = {}

    def fake_batch_run(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "batch_id": "batch_cli", "tasks": [], "completed_count": 0, "failed_count": 0}

    monkeypatch.setattr(cli, "run_batch_edits", fake_batch_run)

    exit_code = cli.main([
        "batch-run",
        "--tasks-json",
        str(tasks_json),
        "--batch-dir",
        str(tmp_path / "batch"),
        "--batch-id",
        "batch_cli",
        "--max-retries",
        "2",
    ])

    assert exit_code == 0
    assert captured["tasks"][0]["name"] == "case"
    assert captured["batch_id"] == "batch_cli"
    assert captured["max_retries"] == 2
    assert "batch_cli" in capsys.readouterr().out


def test_cli_worker_pack_and_run(tmp_path: Path, monkeypatch, capsys) -> None:
    captured_create = {}

    def fake_create_worker_task_package(**kwargs):
        captured_create.update(kwargs)
        return {
            "ok": True,
            "package_path": str(tmp_path / "worker_task_package.json"),
            "task_package": {"package_id": "worker_cli"},
        }

    def fake_run_worker_task_package(package_path):
        return {
            "ok": True,
            "schema": "smart_video_cut.local.worker_completion.v0",
            "package_path": package_path,
            "completion_path": str(tmp_path / "completion.json"),
        }

    monkeypatch.setattr(cli, "create_worker_task_package", fake_create_worker_task_package)
    monkeypatch.setattr(cli, "run_worker_task_package", fake_run_worker_task_package)

    pack_exit = cli.main([
        "worker-pack",
        "--package-dir",
        str(tmp_path / "worker"),
        "--style-package",
        "packages/door",
        "--input-video",
        "input.mp4",
        "--input-video",
        "detail.mp4",
        "--output-dir",
        str(tmp_path / "out"),
        "--user-request",
        "防盗门快闪广告",
        "--confirmed-brief",
        "先出全景再切锁芯细节",
    ])
    run_exit = cli.main([
        "worker-run",
        "--package-path",
        str(tmp_path / "worker" / "worker_task_package.json"),
    ])

    assert pack_exit == 0
    assert run_exit == 0
    assert captured_create["input_videos"] == ["input.mp4", "detail.mp4"]
    assert captured_create["confirmed_brief"] == "先出全景再切锁芯细节"
    output = capsys.readouterr().out
    assert "worker_cli" in output
    assert "completion.json" in output


def test_cli_protocol_build_and_inspect(tmp_path: Path, monkeypatch, capsys) -> None:
    captured = {}

    def fake_write_local_toolkit_protocol(output_dir):
        captured["output_dir"] = output_dir
        return {
            "ok": True,
            "schema": "smart_video_cut.local.toolkit_protocol.v0",
            "protocol_path": str(tmp_path / "out" / "local_toolkit_protocol.json"),
        }

    def fake_inspect_local_toolkit_path(path):
        captured["inspect_path"] = path
        return {
            "ok": True,
            "schema": "smart_video_cut.local.toolkit_protocol_inspection.v0",
            "protocol_kind": "local_toolkit_protocol",
            "path": path,
        }

    monkeypatch.setattr(cli, "write_local_toolkit_protocol", fake_write_local_toolkit_protocol)
    monkeypatch.setattr(cli, "inspect_local_toolkit_path", fake_inspect_local_toolkit_path)

    build_exit = cli.main([
        "protocol-build",
        "--output-dir",
        str(tmp_path / "out"),
    ])
    inspect_exit = cli.main([
        "protocol-inspect",
        "--path",
        str(tmp_path / "out" / "local_toolkit_protocol.json"),
    ])

    assert build_exit == 0
    assert inspect_exit == 0
    assert captured["output_dir"] == str(tmp_path / "out")
    assert captured["inspect_path"] == str(tmp_path / "out" / "local_toolkit_protocol.json")
    output = capsys.readouterr().out
    assert "local_toolkit_protocol.json" in output
    assert "local_toolkit_protocol" in output


def test_cli_protocol_run(tmp_path: Path, monkeypatch, capsys) -> None:
    captured = {}

    def fake_run_protocol_path(path, **kwargs):
        captured["path"] = path
        captured.update(kwargs)
        return {
            "ok": True,
            "schema": "smart_video_cut.local.edit_result.v0",
            "protocol_kind": "project_pack",
            "protocol_runner": "local_edit_task",
            "output_dir": str(tmp_path / "out"),
        }

    monkeypatch.setattr(cli, "run_protocol_path", fake_run_protocol_path)

    exit_code = cli.main([
        "protocol-run",
        "--path",
        str(tmp_path / "project_pack.json"),
        "--output-dir",
        str(tmp_path / "out"),
        "--style-package",
        "packages/filmgen-cinematic-short",
        "--user-request",
        "电影感复用",
        "--execute-real-render",
    ])

    assert exit_code == 0
    assert captured["path"] == str(tmp_path / "project_pack.json")
    assert captured["output_dir"] == str(tmp_path / "out")
    assert captured["style_package"] == "packages/filmgen-cinematic-short"
    assert captured["user_request"] == "电影感复用"
    assert captured["execute_real_render"] is True
    output = capsys.readouterr().out
    assert "project_pack" in output


def test_cli_protocol_dropbox_commands(tmp_path: Path, monkeypatch, capsys) -> None:
    captured = {}

    def fake_initialize_protocol_dropbox(**kwargs):
        captured["init"] = kwargs
        return {
            "ok": True,
            "schema": "smart_video_cut.local.protocol_dropbox.v0",
            "dropbox_dir": str(tmp_path / "dropbox"),
            "manifest_path": str(tmp_path / "dropbox" / "protocol_dropbox.json"),
        }

    def fake_import_protocol_dropbox_item(**kwargs):
        captured["import"] = kwargs
        return {
            "ok": True,
            "schema": "smart_video_cut.local.protocol_dropbox_import.v0",
            "queue_id": "local_edit_tasks",
            "imported_path": str(tmp_path / "dropbox" / "inbox" / "local_edit_tasks" / "task.json"),
        }

    def fake_run_protocol_dropbox_once(**kwargs):
        captured["run"] = kwargs
        return {
            "ok": True,
            "schema": "smart_video_cut.local.protocol_dropbox_run.v0",
            "dropbox_dir": str(tmp_path / "dropbox"),
            "processed_count": 1,
            "failed_count": 0,
        }

    monkeypatch.setattr(cli, "initialize_protocol_dropbox", fake_initialize_protocol_dropbox)
    monkeypatch.setattr(cli, "import_protocol_dropbox_item", fake_import_protocol_dropbox_item)
    monkeypatch.setattr(cli, "run_protocol_dropbox_once", fake_run_protocol_dropbox_once)

    init_exit = cli.main([
        "protocol-dropbox-init",
        "--dropbox-dir",
        str(tmp_path / "dropbox"),
    ])
    import_exit = cli.main([
        "protocol-dropbox-import",
        "--dropbox-dir",
        str(tmp_path / "dropbox"),
        "--source-path",
        str(tmp_path / "out"),
        "--label",
        "demo-case",
    ])
    run_exit = cli.main([
        "protocol-dropbox-run",
        "--dropbox-dir",
        str(tmp_path / "dropbox"),
        "--default-execute-real-render",
        "--dry-run",
    ])

    assert init_exit == 0
    assert import_exit == 0
    assert run_exit == 0
    assert captured["init"]["dropbox_dir"] == str(tmp_path / "dropbox")
    assert captured["import"]["source_path"] == str(tmp_path / "out")
    assert captured["import"]["label"] == "demo-case"
    assert captured["run"]["default_execute_real_render"] is True
    assert captured["run"]["dry_run"] is True
    output = capsys.readouterr().out
    assert "protocol_dropbox.json" in output
    assert "local_edit_tasks" in output


def test_cli_protocol_dropbox_monitor_commands(tmp_path: Path, monkeypatch, capsys) -> None:
    captured = {}

    def fake_run_protocol_dropbox_monitor_loop(**kwargs):
        captured["monitor"] = kwargs
        return {
            "ok": True,
            "schema": "smart_video_cut.local.protocol_dropbox_monitor.v0",
            "dropbox_dir": str(tmp_path / "dropbox"),
            "status": "completed",
            "completed_cycles": 2,
        }

    def fake_get_protocol_dropbox_monitor_status(**kwargs):
        captured["status"] = kwargs
        return {
            "ok": True,
            "schema": "smart_video_cut.local.protocol_dropbox_monitor.v0",
            "dropbox_dir": str(tmp_path / "dropbox"),
            "status": "idle",
            "running": False,
        }

    monkeypatch.setattr(cli, "run_protocol_dropbox_monitor_loop", fake_run_protocol_dropbox_monitor_loop)
    monkeypatch.setattr(cli, "get_protocol_dropbox_monitor_status", fake_get_protocol_dropbox_monitor_status)

    monitor_exit = cli.main([
        "protocol-dropbox-monitor",
        "--dropbox-dir",
        str(tmp_path / "dropbox"),
        "--interval-seconds",
        "5",
        "--max-cycles",
        "2",
        "--dry-run",
    ])
    status_exit = cli.main([
        "protocol-dropbox-monitor-status",
        "--dropbox-dir",
        str(tmp_path / "dropbox"),
    ])

    assert monitor_exit == 0
    assert status_exit == 0
    assert captured["monitor"]["interval_seconds"] == 5.0
    assert captured["monitor"]["max_cycles"] == 2
    assert captured["monitor"]["dry_run"] is True
    assert captured["status"]["dropbox_dir"] == str(tmp_path / "dropbox")
    output = capsys.readouterr().out
    assert "completed_cycles" in output
    assert "idle" in output


def test_cli_protocol_dropbox_history_and_requeue_commands(tmp_path: Path, monkeypatch, capsys) -> None:
    captured = {}

    def fake_get_protocol_dropbox_history(**kwargs):
        captured["history"] = kwargs
        return {
            "ok": True,
            "schema": "smart_video_cut.local.protocol_dropbox_history.v0",
            "dropbox_dir": str(tmp_path / "dropbox"),
            "history_path": str(tmp_path / "dropbox" / "dropbox_history.json"),
            "run_count": 2,
            "alert_entry_count": 1,
            "entries": [],
        }

    def fake_requeue_protocol_dropbox_failed(**kwargs):
        captured["requeue"] = kwargs
        return {
            "ok": True,
            "schema": "smart_video_cut.local.protocol_dropbox_requeue.v0",
            "dropbox_dir": str(tmp_path / "dropbox"),
            "queue_id": kwargs["queue_id"],
            "moved_count": 1,
            "queues": [],
            "entries": [],
        }

    monkeypatch.setattr(cli, "get_protocol_dropbox_history", fake_get_protocol_dropbox_history)
    monkeypatch.setattr(cli, "requeue_protocol_dropbox_failed", fake_requeue_protocol_dropbox_failed)

    history_exit = cli.main([
        "protocol-dropbox-history",
        "--dropbox-dir",
        str(tmp_path / "dropbox"),
        "--limit",
        "5",
        "--queue-id",
        "worker_packages",
        "--alerts-only",
    ])
    requeue_exit = cli.main([
        "protocol-dropbox-requeue-failed",
        "--dropbox-dir",
        str(tmp_path / "dropbox"),
        "--queue-id",
        "worker_packages",
        "--max-files",
        "3",
    ])

    assert history_exit == 0
    assert requeue_exit == 0
    assert captured["history"]["limit"] == 5
    assert captured["history"]["queue_id"] == "worker_packages"
    assert captured["history"]["alerts_only"] is True
    assert captured["requeue"]["queue_id"] == "worker_packages"
    assert captured["requeue"]["max_files"] == 3
    output = capsys.readouterr().out
    assert "dropbox_history.json" in output
    assert "moved_count" in output


def test_watch_queue_dry_run_lists_task_files(tmp_path: Path) -> None:
    watch_dir = tmp_path / "watch"
    watch_dir.mkdir()
    task_file = watch_dir / "job.json"
    task_file.write_text(
        json.dumps({
            "tasks": [
                {"name": "case 1", "style_package": "style", "input_video": "input.mp4"},
                {"name": "case 2", "style_package": "style", "input_video": "input2.mp4"},
            ]
        }, ensure_ascii=False),
        encoding="utf-8",
    )

    result = run_watch_queue_once(
        watch_dir=watch_dir,
        batch_root=tmp_path / "batches",
        dry_run=True,
    )

    assert result["ok"] is True
    assert result["file_count"] == 1
    assert result["queued_count"] == 2
    assert result["processed_count"] == 0
    assert task_file.is_file()
    status = json.loads((watch_dir / "watch_status.json").read_text(encoding="utf-8"))
    assert status["files"][0]["status"] == "queued"


def test_watch_queue_runs_and_archives_task_file(tmp_path: Path, monkeypatch) -> None:
    def fake_run_edit(task):
        task.output_dir.mkdir(parents=True, exist_ok=True)
        (task.output_dir / "local_studio_result.json").write_text("{}", encoding="utf-8")
        return {"ok": True, "toolkit_status": "plan_only", "current_version": 1}

    monkeypatch.setattr("smart_video_cut.batch_runner.run_edit_with_style_package", fake_run_edit)
    watch_dir = tmp_path / "watch"
    watch_dir.mkdir()
    task_file = watch_dir / "job.json"
    task_file.write_text(
        json.dumps({"tasks": [{"name": "queued", "style_package": "style", "input_video": "input.mp4"}]}, ensure_ascii=False),
        encoding="utf-8",
    )

    result = run_watch_queue_once(
        watch_dir=watch_dir,
        batch_root=tmp_path / "batches",
        max_retries=1,
    )

    assert result["ok"] is True
    assert result["processed_count"] == 1
    assert not task_file.exists()
    assert (watch_dir / "_processed" / "job.json").is_file()
    assert (tmp_path / "batches" / "job" / "batch_status.json").is_file()
    batch_status = json.loads((tmp_path / "batches" / "job" / "batch_status.json").read_text(encoding="utf-8"))
    assert batch_status["tasks"][0]["status"] == "completed"


def test_watch_queue_runs_worker_protocol_file(tmp_path: Path, monkeypatch) -> None:
    watch_dir = tmp_path / "watch"
    watch_dir.mkdir()
    worker_file = watch_dir / "worker_task_package.json"
    worker_file.write_text(
        json.dumps(
            {
                "schema": "smart_video_cut.local.worker_task_package.v0",
                "package_id": "worker_case",
                "task": {
                    "style_package": "packages/door",
                    "input_video": "input.mp4",
                    "input_videos": ["input.mp4"],
                    "output_dir": str(tmp_path / "out"),
                    "user_request": "协议队列测试",
                    "project_id": "worker_queue_case",
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
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

    result = run_watch_queue_once(
        watch_dir=watch_dir,
        batch_root=tmp_path / "batches",
    )

    assert result["ok"] is True
    assert result["processed_count"] == 1
    assert result["files"][0]["job_kind"] == "protocol_run"
    assert result["files"][0]["protocol_kind"] == "worker_task_package"
    assert result["files"][0]["result"]["protocol_runner"] == "worker_package"
    assert not worker_file.exists()
    assert (watch_dir / "_processed" / "worker_task_package.json").is_file()


def test_cli_watch_queue_uses_watch_dir(tmp_path: Path, monkeypatch, capsys) -> None:
    captured = {}

    def fake_watch_queue(**kwargs):
        captured.update(kwargs)
        return {"ok": True, "watch_dir": kwargs["watch_dir"], "processed_count": 0, "failed_count": 0}

    monkeypatch.setattr(cli, "run_watch_queue_once", fake_watch_queue)

    exit_code = cli.main([
        "watch-queue",
        "--watch-dir",
        str(tmp_path / "watch"),
        "--batch-root",
        str(tmp_path / "batches"),
        "--pattern",
        "*.task.json",
        "--dry-run",
        "--max-retries",
        "3",
    ])

    assert exit_code == 0
    assert captured["watch_dir"] == str(tmp_path / "watch")
    assert captured["batch_root"] == str(tmp_path / "batches")
    assert captured["pattern"] == "*.task.json"
    assert captured["dry_run"] is True
    assert captured["max_retries"] == 3
    assert "processed_count" in capsys.readouterr().out
