from __future__ import annotations

import json
from pathlib import Path

from smart_video_cut.worker_protocol import (
    WORKER_COMPLETION_SCHEMA,
    WORKER_TASK_PACKAGE_SCHEMA,
    create_worker_task_package,
    load_worker_task_package,
    run_worker_task_package,
)


def test_create_worker_task_package_writes_package_file(tmp_path: Path) -> None:
    result = create_worker_task_package(
        package_dir=tmp_path / "worker-job",
        package_name="door_worker",
        style_package="packages/door",
        input_video="input.mp4",
        input_videos=["input.mp4", "detail.mp4"],
        output_dir=str(tmp_path / "out"),
        user_request="防盗门快闪广告",
        execute_real_render=False,
        confirmed_brief="保留门体开合节奏，突出金属质感",
        task_id="task_worker_001",
    )

    package_path = Path(result["package_path"])
    assert result["ok"] is True
    assert result["schema"] == WORKER_TASK_PACKAGE_SCHEMA
    assert package_path.is_file()

    payload = json.loads(package_path.read_text(encoding="utf-8"))
    assert payload["schema"] == WORKER_TASK_PACKAGE_SCHEMA
    assert payload["package_id"] == "door_worker"
    assert payload["task"]["input_videos"] == ["input.mp4", "detail.mp4"]
    assert payload["task"]["confirmed_brief"] == "保留门体开合节奏，突出金属质感"
    assert payload["task"]["task_id"] == "task_worker_001"


def test_load_worker_task_package_reads_completion_when_present(tmp_path: Path) -> None:
    created = create_worker_task_package(
        package_dir=tmp_path / "worker-job",
        style_package="packages/door",
        input_video="input.mp4",
        output_dir=str(tmp_path / "out"),
        user_request="防盗门快闪广告",
    )
    completion_path = Path(created["package_dir"]) / "completion.json"
    completion_path.write_text(
        json.dumps({"schema": WORKER_COMPLETION_SCHEMA, "status": "completed"}, ensure_ascii=False),
        encoding="utf-8",
    )

    loaded = load_worker_task_package(created["package_path"])

    assert loaded["ok"] is True
    assert loaded["completion"]["status"] == "completed"


def test_run_worker_task_package_executes_and_writes_completion(tmp_path: Path) -> None:
    created = create_worker_task_package(
        package_dir=tmp_path / "worker-job",
        style_package="packages/door",
        input_video="input.mp4",
        output_dir=str(tmp_path / "out"),
        user_request="防盗门快闪广告",
        execute_real_render=True,
    )

    def fake_run_edit(task):
        task.output_dir.mkdir(parents=True, exist_ok=True)
        (task.output_dir / "local_studio_result.json").write_text("{}", encoding="utf-8")
        return {
            "ok": True,
            "toolkit_status": "worker_real_render",
            "copied_output_video": str(task.output_dir / "final.mp4"),
            "current_version": 3,
        }

    completion = run_worker_task_package(created["package_path"], run_edit=fake_run_edit)

    assert completion["ok"] is True
    assert completion["schema"] == WORKER_COMPLETION_SCHEMA
    assert completion["execution_mode"] == "worker_real_render"
    assert Path(completion["completion_path"]).is_file()
