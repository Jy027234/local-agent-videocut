from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class WorkflowStep:
    key: str
    label: str
    approval_required: bool = False


WORKFLOW_STEPS: tuple[WorkflowStep, ...] = (
    WorkflowStep("idea", "创意立项"),
    WorkflowStep("script_draft", "剧本草稿"),
    WorkflowStep("storyboard_review", "分镜复核", approval_required=True),
    WorkflowStep("keyframe_generation", "关键帧生成"),
    WorkflowStep("keyframe_review", "关键帧复核", approval_required=True),
    WorkflowStep("clip_generation", "视频生成"),
    WorkflowStep("clip_review", "镜头复核", approval_required=True),
    WorkflowStep("edit_assembly", "剪辑装配"),
    WorkflowStep("final_qc", "最终质检", approval_required=True),
    WorkflowStep("archive", "归档"),
)


PROJECT_FORMATS = ("short", "ad", "storyboard", "music_video")
SHOT_STATUSES = ("draft", "ready", "generating", "needs_review", "approved")
ASSET_TYPES = ("script", "storyboard", "keyframe", "video", "audio", "subtitle", "final", "manifest")
TASK_STAGES = ("script", "keyframe", "clip", "audio", "edit_pack")
TASK_STATUSES = ("queued", "blocked", "running", "succeeded", "failed", "cancelled")


MODEL_PIPELINE_SLOTS: tuple[dict[str, object], ...] = (
    {
        "key": "planning_model",
        "label": "编剧策划模型",
        "role": "planning",
        "stage": "script",
        "default_provider_id": "mock-local",
        "default_model": "storyboard-draft-local",
    },
    {
        "key": "text_to_image_model",
        "label": "文生图模型",
        "role": "text_to_image",
        "stage": "keyframe",
        "default_provider_id": "mock-local",
        "default_model": "keyframe-placeholder",
    },
    {
        "key": "image_to_video_model",
        "label": "图生视频模型",
        "role": "image_to_video",
        "stage": "clip",
        "default_provider_id": "mock-local",
        "default_model": "clip-placeholder",
    },
)


DEFAULT_PROVIDERS: tuple[dict[str, object], ...] = (
    {
        "id": "mock-local",
        "name": "Mock Local 回流",
        "kind": "mock",
        "base_url": "",
        "api_key_env": "",
        "enabled": True,
        "model_catalog": {
            "text": ["storyboard-draft-local"],
            "image": ["keyframe-placeholder"],
            "video": ["clip-placeholder"],
        },
        "pricing": {"currency": "CNY", "unit": "task", "default_estimate": 0},
    },
    {
        "id": "wanx",
        "name": "通义万相",
        "kind": "image-video",
        "base_url": "https://dashscope.aliyuncs.com",
        "api_key_env": "DASHSCOPE_API_KEY",
        "enabled": False,
        "model_catalog": {"image": [], "video": []},
        "pricing": {"currency": "CNY", "note": "在控制台维护，不写死价格"},
    },
    {
        "id": "kling",
        "name": "可灵 AI",
        "kind": "video",
        "base_url": "",
        "api_key_env": "KLING_API_KEY",
        "enabled": False,
        "model_catalog": {"video": []},
        "pricing": {"currency": "CNY", "note": "按供应商配置表维护"},
    },
    {
        "id": "doubao",
        "name": "豆包/火山引擎",
        "kind": "text-audio",
        "base_url": "",
        "api_key_env": "ARK_API_KEY",
        "enabled": False,
        "model_catalog": {"text": [], "audio": []},
        "pricing": {"currency": "CNY", "note": "按供应商配置表维护"},
    },
)
