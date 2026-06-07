from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


TASK_STATUS_SCHEMA = "smart_video_cut.local.task_status.v0"

STATUS_ROOT = Path(__file__).resolve().parents[2] / "workspace" / "task_status"

STAGE_PENDING = "pending"
STAGE_RUNNING = "running"
STAGE_COMPLETED = "completed"
STAGE_FAILED = "failed"
STAGE_SKIPPED = "skipped"

TASK_PENDING = "pending"
TASK_RUNNING = "running"
TASK_COMPLETED = "completed"
TASK_FAILED = "failed"

DEFAULT_STAGES: list[tuple[str, str]] = [
    ("load_style_package", "加载风格包"),
    ("build_material_plan", "分析素材分工"),
    ("build_edit_brief", "生成导演确认稿"),
    ("build_timeline", "规划时间线"),
    ("generate_voiceover", "生成配音"),
    ("execute_render", "执行渲染"),
    ("quality_check", "质量检查"),
    ("write_result", "写入结果"),
]


@dataclass(slots=True)
class TaskStage:
    stage_id: str
    label: str
    status: str = STAGE_PENDING
    started_at: float | None = None
    completed_at: float | None = None
    outputs: list[str] = field(default_factory=list)
    agent_observations: list[str] = field(default_factory=list)
    error_message: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class TaskStatus:
    task_id: str
    project_id: str
    status: str = TASK_PENDING
    created_at: float = 0.0
    updated_at: float = 0.0
    stages: list[TaskStage] = field(default_factory=list)
    current_stage: str = ""
    progress_percent: int = 0
    result_path: str = ""
    schema: str = TASK_STATUS_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "task_id": self.task_id,
            "project_id": self.project_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "stages": [s.to_dict() for s in self.stages],
            "current_stage": self.current_stage,
            "progress_percent": self.progress_percent,
            "result_path": self.result_path,
        }


def _status_file(task_id: str) -> Path:
    return STATUS_ROOT / f"{task_id}.json"


def _save_status(status: TaskStatus) -> None:
    STATUS_ROOT.mkdir(parents=True, exist_ok=True)
    path = _status_file(status.task_id)
    path.write_text(
        json.dumps(status.to_dict(), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _load_status(task_id: str) -> TaskStatus | None:
    path = _status_file(task_id)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    stages_data = data.get("stages") or []
    stages = []
    for s in stages_data:
        if isinstance(s, dict):
            stages.append(TaskStage(
                stage_id=str(s.get("stage_id", "")),
                label=str(s.get("label", "")),
                status=str(s.get("status", STAGE_PENDING)),
                started_at=s.get("started_at"),
                completed_at=s.get("completed_at"),
                outputs=s.get("outputs") or [],
                agent_observations=s.get("agent_observations") or [],
                error_message=str(s.get("error_message", "")),
            ))
    return TaskStatus(
        task_id=str(data.get("task_id", task_id)),
        project_id=str(data.get("project_id", "")),
        status=str(data.get("status", TASK_PENDING)),
        created_at=float(data.get("created_at", 0.0)),
        updated_at=float(data.get("updated_at", 0.0)),
        stages=stages,
        current_stage=str(data.get("current_stage", "")),
        progress_percent=int(data.get("progress_percent", 0)),
        result_path=str(data.get("result_path", "")),
        schema=str(data.get("schema", TASK_STATUS_SCHEMA)),
    )


def create_task_status(task_id: str, project_id: str) -> TaskStatus:
    now = time.time()
    stages = [TaskStage(stage_id=sid, label=label) for sid, label in DEFAULT_STAGES]
    status = TaskStatus(
        task_id=task_id,
        project_id=project_id,
        status=TASK_RUNNING,
        created_at=now,
        updated_at=now,
        stages=stages,
    )
    _save_status(status)
    return status


def update_stage(
    task_id: str,
    stage_id: str,
    *,
    status: str | None = None,
    error_message: str = "",
    outputs: list[str] | None = None,
) -> None:
    task = _load_status(task_id)
    if task is None:
        return
    now = time.time()
    for stage in task.stages:
        if stage.stage_id == stage_id:
            if status is not None:
                stage.status = status
            if status == STAGE_RUNNING and stage.started_at is None:
                stage.started_at = now
            if status in {STAGE_COMPLETED, STAGE_FAILED, STAGE_SKIPPED}:
                stage.completed_at = now
            if error_message:
                stage.error_message = error_message
            if outputs is not None:
                stage.outputs = outputs
            task.current_stage = stage_id
            break
    task.updated_at = now
    task.progress_percent = _compute_progress(task)
    if status == STAGE_FAILED:
        task.status = TASK_FAILED
    elif all(s.status in {STAGE_COMPLETED, STAGE_SKIPPED} for s in task.stages):
        task.status = TASK_COMPLETED
    else:
        task.status = TASK_RUNNING
    _save_status(task)


def add_observation(task_id: str, stage_id: str, observation: str) -> None:
    task = _load_status(task_id)
    if task is None:
        return
    for stage in task.stages:
        if stage.stage_id == stage_id:
            stage.agent_observations.append(observation)
            break
    task.updated_at = time.time()
    _save_status(task)


def complete_task(task_id: str, *, result_path: str = "") -> None:
    task = _load_status(task_id)
    if task is None:
        return
    task.status = TASK_COMPLETED
    task.progress_percent = 100
    task.updated_at = time.time()
    if result_path:
        task.result_path = result_path
    _save_status(task)


def fail_task(task_id: str, *, error_message: str = "") -> None:
    task = _load_status(task_id)
    if task is None:
        return
    task.status = TASK_FAILED
    task.updated_at = time.time()
    if error_message and task.current_stage:
        for stage in task.stages:
            if stage.stage_id == task.current_stage and not stage.error_message:
                stage.error_message = error_message
                break
    _save_status(task)


def get_task_status(task_id: str) -> dict[str, Any] | None:
    status = _load_status(task_id)
    return status.to_dict() if status else None


def list_task_statuses(project_id: str = "", limit: int = 50) -> list[dict[str, Any]]:
    if not STATUS_ROOT.exists():
        return []
    files = sorted(STATUS_ROOT.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    results: list[dict[str, Any]] = []
    for path in files[:max(1, limit)]:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if project_id and str(data.get("project_id", "")) != project_id:
            continue
        results.append(data)
    return results


def _compute_progress(task: TaskStatus) -> int:
    if not task.stages:
        return 0
    total = len(task.stages)
    done = sum(1 for s in task.stages if s.status in {STAGE_COMPLETED, STAGE_SKIPPED})
    running = sum(1 for s in task.stages if s.status == STAGE_RUNNING)
    return min(100, int(((done + running * 0.5) / total) * 100))


def generate_task_id(project_id: str = "local_project") -> str:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    millis = int((time.time() % 1) * 1000)
    return f"task_{project_id}_{timestamp}_{millis:03d}"
