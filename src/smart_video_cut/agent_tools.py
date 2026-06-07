from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable


TOOL_REGISTRY_SCHEMA = "smart_video_cut.local.agent_tool_registry.v0"


@dataclass(slots=True)
class ToolParameter:
    name: str
    type: str  # "string" | "integer" | "float" | "boolean" | "path" | "list" | "dict"
    required: bool = True
    description: str = ""
    default: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ToolDefinition:
    tool_id: str
    name: str
    description: str
    category: str  # "editing" | "voice" | "analysis" | "package" | "project" | "adapter"
    parameters: list[ToolParameter] = field(default_factory=list)
    returns: dict[str, str] = field(default_factory=dict)
    handler: Callable[..., Any] | None = field(default=None, repr=False)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_id": self.tool_id,
            "name": self.name,
            "description": self.description,
            "category": self.category,
            "parameters": [p.to_dict() for p in self.parameters],
            "returns": self.returns,
        }


class AgentToolRegistry:
    """Registry of agent-callable tools with typed parameters."""

    def __init__(self) -> None:
        self._tools: dict[str, ToolDefinition] = {}

    def register(self, tool: ToolDefinition) -> None:
        self._tools[tool.tool_id] = tool

    def list_tools(self, category: str = "") -> list[dict[str, Any]]:
        tools = self._tools.values()
        if category:
            tools = [t for t in tools if t.category == category]
        return [t.to_dict() for t in tools]

    def get_tool(self, tool_id: str) -> dict[str, Any] | None:
        tool = self._tools.get(tool_id)
        return tool.to_dict() if tool else None

    def invoke(self, tool_id: str, **kwargs: Any) -> dict[str, Any]:
        tool = self._tools.get(tool_id)
        if not tool:
            return {"ok": False, "error": f"tool_not_found: {tool_id}"}
        if not tool.handler:
            return {"ok": False, "error": f"tool_has_no_handler: {tool_id}"}
        try:
            result = tool.handler(**kwargs)
            if isinstance(result, dict):
                return {"ok": True, **result}
            return {"ok": True, "result": result}
        except Exception as exc:
            return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}

    def to_manifest(self) -> dict[str, Any]:
        return {
            "schema": TOOL_REGISTRY_SCHEMA,
            "tool_count": len(self._tools),
            "tools": self.list_tools(),
        }


# ---------------------------------------------------------------------------
# Tool handler implementations
# ---------------------------------------------------------------------------


def _tool_create_style_package(
    name: str = "",
    template_video: str = "",
    package_dir: str = "",
    description: str = "",
    duration: int = 20,
    aspect_ratio: str = "9:16",
    **kwargs: Any,
) -> dict[str, Any]:
    from smart_video_cut.style_package import create_style_package, default_settings_from_options
    from smart_video_cut.models import StylePackageRequest

    settings = default_settings_from_options(
        duration=duration,
        aspect_ratio=aspect_ratio,
        resolution=kwargs.get("resolution", "720x1280"),
        quality=kwargs.get("quality", "standard"),
        subtitle_size=kwargs.get("subtitle_size", 44),
        bgm_volume_db=kwargs.get("bgm_volume_db", -18.0),
        voice_provider=kwargs.get("voice_provider", "edge_tts"),
    )
    package = create_style_package(
        StylePackageRequest(
            name=name,
            description=description,
            template_video=Path(template_video),
            package_dir=Path(package_dir),
            settings=settings,
        )
    )
    return {"package": package, "package_dir": package_dir}


def _tool_build_edit_brief(
    style_package: str = "",
    input_video: str = "",
    input_videos: list[str] | None = None,
    output_dir: str = "",
    user_request: str = "",
    voiceover_text: str | None = None,
    execute_real_render: bool = False,
    use_memory: bool = True,
    settings_overrides: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    from smart_video_cut.edit_brief import build_edit_brief

    return build_edit_brief(
        style_package=style_package,
        input_video=input_video,
        input_videos=input_videos,
        output_dir=output_dir,
        user_request=user_request,
        voiceover_text=voiceover_text,
        execute_real_render=execute_real_render,
        use_memory=use_memory,
        settings_overrides=settings_overrides,
    )


def _tool_chat_director(
    message: str = "",
    history: list[dict[str, Any]] | None = None,
    context: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    from smart_video_cut.director_agent import chat_with_director

    return chat_with_director(
        message=message,
        history=history or [],
        context=context or kwargs,
    )


def _tool_orchestrate_local_agents(
    message: str = "",
    history: list[dict[str, Any]] | None = None,
    context: dict[str, Any] | None = None,
    director_mode: str = "local_rule",
    **kwargs: Any,
) -> dict[str, Any]:
    from smart_video_cut.agent_orchestrator import orchestrate_local_agents

    merged_context = dict(context or {})
    for key, value in kwargs.items():
        if key not in {"history"} and key not in merged_context:
            merged_context[key] = value
    return orchestrate_local_agents(
        message=message,
        history=history or [],
        context=merged_context,
        director_mode=director_mode,
    )


def _tool_run_edit(
    style_package: str = "",
    input_video: str = "",
    input_videos: list[str] | None = None,
    output_dir: str = "",
    user_request: str = "",
    project_id: str = "local_project",
    execute_real_render: bool = False,
    allow_edge_tts: bool = False,
    voiceover_text: str | None = None,
    use_memory: bool = True,
    confirmed_brief: str | None = None,
    settings_overrides: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    from smart_video_cut.bundled_runtime import run_edit_with_style_package
    from smart_video_cut.models import LocalEditTask

    primary = input_video or (input_videos[0] if input_videos else "")
    all_videos = list(input_videos or [])
    if primary and primary not in all_videos:
        all_videos.insert(0, primary)

    task = LocalEditTask(
        style_package=Path(style_package),
        input_video=Path(primary),
        input_videos=[Path(p) for p in all_videos],
        output_dir=Path(output_dir),
        user_request=user_request,
        project_id=project_id,
        execute_real_render=execute_real_render,
        allow_edge_tts=allow_edge_tts,
        voiceover_text=voiceover_text,
        use_memory=use_memory,
        settings_overrides=settings_overrides or {},
        confirmed_brief=confirmed_brief,
    )
    return run_edit_with_style_package(task)


def _tool_build_worker_task_package(
    package_dir: str = "",
    package_name: str = "",
    style_package: str = "",
    input_video: str = "",
    input_videos: list[str] | None = None,
    output_dir: str = "",
    user_request: str = "",
    project_id: str = "local_project",
    execute_real_render: bool = False,
    allow_edge_tts: bool = False,
    voiceover_text: str | None = None,
    use_memory: bool = True,
    confirmed_brief: str | None = None,
    settings_overrides: dict[str, Any] | None = None,
    timeline_override: dict[str, Any] | None = None,
    task_id: str | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    from smart_video_cut.worker_protocol import create_worker_task_package

    return create_worker_task_package(
        package_dir=package_dir,
        package_name=package_name,
        style_package=style_package,
        input_video=input_video,
        input_videos=input_videos,
        output_dir=output_dir,
        user_request=user_request,
        project_id=project_id,
        execute_real_render=execute_real_render,
        allow_edge_tts=allow_edge_tts,
        voiceover_text=voiceover_text,
        use_memory=use_memory,
        confirmed_brief=confirmed_brief,
        settings_overrides=settings_overrides,
        timeline_override=timeline_override,
        task_id=task_id,
    )


def _tool_run_worker_task_package(package_path: str = "", **kwargs: Any) -> dict[str, Any]:
    from smart_video_cut.worker_protocol import run_worker_task_package

    return run_worker_task_package(package_path)


def _tool_build_local_toolkit_protocol(output_dir: str = "", **kwargs: Any) -> dict[str, Any]:
    from smart_video_cut.toolkit_protocol import write_local_toolkit_protocol

    return write_local_toolkit_protocol(output_dir=output_dir)


def _tool_inspect_local_toolkit_protocol(path: str = "", **kwargs: Any) -> dict[str, Any]:
    from smart_video_cut.toolkit_protocol import inspect_local_toolkit_path

    return inspect_local_toolkit_path(path)


def _tool_run_protocol_path(
    path: str = "",
    output_dir: str = "",
    style_package: str = "",
    user_request: str = "",
    execute_real_render: bool = False,
    allow_edge_tts: bool = False,
    voiceover_text: str | None = None,
    confirmed_brief: str | None = None,
    use_memory: bool = True,
    **kwargs: Any,
) -> dict[str, Any]:
    from smart_video_cut.protocol_runner import run_protocol_path

    return run_protocol_path(
        path,
        output_dir=output_dir,
        style_package=style_package,
        user_request=user_request,
        execute_real_render=execute_real_render,
        allow_edge_tts=allow_edge_tts,
        voiceover_text=voiceover_text,
        confirmed_brief=confirmed_brief,
        use_memory=use_memory,
    )


def _tool_init_protocol_dropbox(
    dropbox_dir: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    from smart_video_cut.protocol_dropbox import initialize_protocol_dropbox

    return initialize_protocol_dropbox(dropbox_dir=dropbox_dir)


def _tool_import_protocol_dropbox_item(
    source_path: str = "",
    dropbox_dir: str = "",
    label: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    from smart_video_cut.protocol_dropbox import import_protocol_dropbox_item

    return import_protocol_dropbox_item(
        source_path=source_path,
        dropbox_dir=dropbox_dir,
        label=label,
    )


def _tool_run_protocol_dropbox_once(
    dropbox_dir: str = "",
    default_execute_real_render: bool = False,
    stop_on_error: bool = False,
    max_retries: int = 0,
    dry_run: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    from smart_video_cut.protocol_dropbox import run_protocol_dropbox_once

    return run_protocol_dropbox_once(
        dropbox_dir=dropbox_dir,
        default_execute_real_render=default_execute_real_render,
        stop_on_error=stop_on_error,
        max_retries=max_retries,
        dry_run=dry_run,
    )


def _tool_run_protocol_dropbox_monitor(
    dropbox_dir: str = "",
    interval_seconds: float = 15.0,
    max_cycles: int = 0,
    default_execute_real_render: bool = False,
    stop_on_error: bool = False,
    max_retries: int = 0,
    dry_run: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    from smart_video_cut.protocol_dropbox_monitor import run_protocol_dropbox_monitor_loop

    return run_protocol_dropbox_monitor_loop(
        dropbox_dir=dropbox_dir,
        interval_seconds=interval_seconds,
        max_cycles=max_cycles,
        default_execute_real_render=default_execute_real_render,
        stop_on_error=stop_on_error,
        max_retries=max_retries,
        dry_run=dry_run,
    )


def _tool_start_protocol_dropbox_monitor(
    dropbox_dir: str = "",
    interval_seconds: float = 15.0,
    max_cycles: int = 0,
    default_execute_real_render: bool = False,
    stop_on_error: bool = False,
    max_retries: int = 0,
    dry_run: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    from smart_video_cut.protocol_dropbox_monitor import start_protocol_dropbox_monitor

    return start_protocol_dropbox_monitor(
        dropbox_dir=dropbox_dir,
        interval_seconds=interval_seconds,
        max_cycles=max_cycles,
        default_execute_real_render=default_execute_real_render,
        stop_on_error=stop_on_error,
        max_retries=max_retries,
        dry_run=dry_run,
    )


def _tool_stop_protocol_dropbox_monitor(
    dropbox_dir: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    from smart_video_cut.protocol_dropbox_monitor import stop_protocol_dropbox_monitor

    return stop_protocol_dropbox_monitor(dropbox_dir=dropbox_dir)


def _tool_get_protocol_dropbox_monitor_status(
    dropbox_dir: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    from smart_video_cut.protocol_dropbox_monitor import get_protocol_dropbox_monitor_status

    return get_protocol_dropbox_monitor_status(dropbox_dir=dropbox_dir)


def _tool_get_protocol_dropbox_history(
    dropbox_dir: str = "",
    limit: int = 20,
    queue_id: str = "",
    alerts_only: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    from smart_video_cut.protocol_dropbox import get_protocol_dropbox_history

    return get_protocol_dropbox_history(
        dropbox_dir=dropbox_dir,
        limit=limit,
        queue_id=queue_id,
        alerts_only=alerts_only,
    )


def _tool_requeue_protocol_dropbox_failed(
    dropbox_dir: str = "",
    queue_id: str = "all",
    max_files: int = 20,
    **kwargs: Any,
) -> dict[str, Any]:
    from smart_video_cut.protocol_dropbox import requeue_protocol_dropbox_failed

    return requeue_protocol_dropbox_failed(
        dropbox_dir=dropbox_dir,
        queue_id=queue_id,
        max_files=max_files,
    )


def _tool_get_timeline(
    style_package: str = "",
    input_videos: list[str] | None = None,
    settings_overrides: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    from smart_video_cut.edit_brief import build_edit_brief
    from smart_video_cut.style_package import load_style_package
    from smart_video_cut.timeline_builder import build_timeline_plan, timeline_to_toolkit_format

    package = load_style_package(style_package)
    brief = build_edit_brief(
        style_package=style_package,
        input_video=input_videos[0] if input_videos else "",
        input_videos=input_videos,
        output_dir=kwargs.get("output_dir", ""),
        user_request=kwargs.get("user_request", ""),
        settings_overrides=settings_overrides,
    )
    timeline = build_timeline_plan(
        material_plan=brief.get("material_plan", {}),
        settings=brief.get("settings", {}),
        style_package=package,
    )
    return {
        "timeline": timeline.to_dict(),
        "toolkit_format": timeline_to_toolkit_format(timeline),
        "validation_errors": timeline.validate(),
        "brief": brief,
    }


def _tool_analyze_materials(
    input_videos: list[str] | None = None,
    settings: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    from smart_video_cut.material_adapters import prepare_material_plan

    paths = [Path(p) for p in (input_videos or [])]
    result = prepare_material_plan(paths=paths, settings=settings or {})
    material_plan = result.get("material_plan") if isinstance(result.get("material_plan"), dict) else {}
    return {**material_plan, "material_adapter_result": result}


def _tool_list_recent_runs(limit: int = 20, **kwargs: Any) -> dict[str, Any]:
    from smart_video_cut.recent_runs import list_recent_runs

    return list_recent_runs(limit=int(limit))


def _tool_discover_style_packages(**kwargs: Any) -> dict[str, Any]:
    from smart_video_cut.style_package import discover_style_packages

    return {"packages": discover_style_packages()}


def _tool_get_task_status(task_id: str = "", **kwargs: Any) -> dict[str, Any]:
    from smart_video_cut.task_status import get_task_status

    result = get_task_status(task_id)
    if result is None:
        return {"ok": False, "error": f"task_not_found: {task_id}"}
    return result


def _tool_get_version_history(output_dir: str = "", **kwargs: Any) -> dict[str, Any]:
    from smart_video_cut.version_history import get_version_history

    return get_version_history(output_dir)


def _tool_discover_packs(**kwargs: Any) -> dict[str, Any]:
    from smart_video_cut.pack_manager import discover_packs

    return discover_packs()


def _tool_re_edit_version(
    output_dir: str = "",
    base_version: int = 0,
    user_feedback: str = "",
    timeline_edits: list[dict[str, Any]] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    from smart_video_cut.project_manifest import write_project_manifest
    from smart_video_cut.timeline_builder import apply_user_edits
    from smart_video_cut.timeline_model import TimelinePlan
    from smart_video_cut.version_history import get_version, save_version

    base = get_version(output_dir, int(base_version))
    if base is None:
        return {"ok": False, "error": f"base_version_not_found: {base_version}"}
    base_timeline = base.get("timeline") or {}
    if timeline_edits and base_timeline:
        updated = apply_user_edits(
            base_timeline=TimelinePlan.from_dict(base_timeline),
            edits=timeline_edits,
        )
        new_timeline = updated.to_dict()
    else:
        new_timeline = base_timeline
    entry = save_version(
        output_dir=output_dir,
        timeline=new_timeline,
        brief=base.get("brief"),
        result=None,
        user_feedback=user_feedback,
        edit_operations=timeline_edits or [],
        status="pending_re_render",
    )
    write_project_manifest(
        output_dir=output_dir,
        timeline=new_timeline if isinstance(new_timeline, dict) else None,
        event="version_re_edit",
    )
    return {
        "new_version": entry.version,
        "timeline": new_timeline,
        "needs_render": True,
        "project_manifest_path": str(Path(output_dir) / "project_manifest.json"),
    }


def _tool_batch_run_edit(
    tasks: list[dict[str, Any]] | None = None,
    batch_dir: str = "",
    batch_id: str = "",
    default_execute_real_render: bool = False,
    stop_on_error: bool = False,
    max_retries: int = 0,
    **kwargs: Any,
) -> dict[str, Any]:
    from smart_video_cut.batch_runner import run_batch_edits

    return run_batch_edits(
        tasks=tasks or [],
        batch_dir=batch_dir,
        batch_id=batch_id,
        default_execute_real_render=default_execute_real_render,
        stop_on_error=stop_on_error,
        max_retries=max_retries,
    )


def _tool_watch_queue_once(
    watch_dir: str = "",
    batch_root: str = "",
    archive_dir: str = "",
    failed_dir: str = "",
    pattern: str = "*.json",
    default_execute_real_render: bool = False,
    stop_on_error: bool = False,
    max_retries: int = 0,
    dry_run: bool = False,
    **kwargs: Any,
) -> dict[str, Any]:
    from smart_video_cut.watch_queue import run_watch_queue_once

    return run_watch_queue_once(
        watch_dir=watch_dir,
        batch_root=batch_root,
        archive_dir=archive_dir,
        failed_dir=failed_dir,
        pattern=pattern,
        default_execute_real_render=default_execute_real_render,
        stop_on_error=stop_on_error,
        max_retries=max_retries,
        dry_run=dry_run,
    )


def _tool_export_project_pack(
    output_dir: str = "",
    package_dir: str = "",
    name: str = "",
    material_pack_ref: str = "",
    style_pack_ref: str = "",
    project_settings_overrides: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    from smart_video_cut.export_adapters import export_project_pack_adapter

    result = export_project_pack_adapter(
        output_dir=output_dir,
        package_dir=package_dir,
        name=name,
        material_pack_ref=material_pack_ref,
        style_pack_ref=style_pack_ref,
        project_settings_overrides=project_settings_overrides or {},
    )
    return result


def _tool_validate_project(
    output_dir: str = "",
    project_pack_path: str = "",
    project_pack: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    from smart_video_cut.pack_manager import load_pack, validate_pack_references
    from smart_video_cut.project_manifest import read_project_manifest
    from smart_video_cut.version_history import get_version_history

    warnings: list[dict[str, str]] = []
    errors: list[dict[str, str]] = []
    manifest = read_project_manifest(output_dir) if output_dir else None
    version_history = get_version_history(output_dir) if output_dir else {}
    if output_dir and manifest is None:
        warnings.append({
            "code": "project_manifest_not_found",
            "message": "输出目录未找到 project_manifest.json",
            "path": str(Path(output_dir) / "project_manifest.json"),
        })
    if output_dir and not Path(output_dir).exists():
        warnings.append({
            "code": "output_dir_missing",
            "message": "输出目录不存在",
            "path": output_dir,
        })
    selected_pack = project_pack
    if project_pack_path:
        selected_pack = load_pack(project_pack_path)
    pack_validation = validate_pack_references(selected_pack) if isinstance(selected_pack, dict) else {}
    if pack_validation:
        warnings.extend(pack_validation.get("warnings") or [])
        errors.extend(pack_validation.get("errors") or [])
    return {
        "valid": not errors,
        "output_dir": output_dir,
        "manifest": manifest or {},
        "version_history": version_history,
        "pack_validation": pack_validation,
        "warnings": warnings,
        "errors": errors,
    }


def _tool_list_adapters(
    category: str = "",
    status: str = "",
    **kwargs: Any,
) -> dict[str, Any]:
    from smart_video_cut.adapter_registry import list_default_adapters

    return list_default_adapters(category=category, status=status)


def _tool_resolve_adapters(
    settings: dict[str, Any] | None = None,
    style_package: str = "",
    settings_overrides: dict[str, Any] | None = None,
    **kwargs: Any,
) -> dict[str, Any]:
    from smart_video_cut.adapter_registry import resolve_adapter_selection
    from smart_video_cut.edit_settings import apply_visible_settings_overrides
    from smart_video_cut.style_package import load_style_package

    selected_settings = settings or {}
    if style_package:
        package = load_style_package(style_package)
        selected_settings = apply_visible_settings_overrides(
            package.get("visible_settings", {}),
            settings_overrides or {},
        )
    return resolve_adapter_selection(selected_settings)


# ---------------------------------------------------------------------------
# Registry builder
# ---------------------------------------------------------------------------


def build_default_registry() -> AgentToolRegistry:
    registry = AgentToolRegistry()

    registry.register(ToolDefinition(
        tool_id="create_style_package",
        name="创建风格包",
        description="从参考视频提取剪辑风格配置",
        category="package",
        parameters=[
            ToolParameter("name", "string", description="风格包名称"),
            ToolParameter("template_video", "path", description="参考视频路径"),
            ToolParameter("package_dir", "path", description="保存目录"),
            ToolParameter("description", "string", required=False, description="描述"),
            ToolParameter("duration", "integer", required=False, default=20, description="目标时长"),
            ToolParameter("aspect_ratio", "string", required=False, default="9:16", description="画幅比例"),
        ],
        returns={"package": "dict"},
        handler=_tool_create_style_package,
    ))

    registry.register(ToolDefinition(
        tool_id="build_edit_brief",
        name="生成导演确认稿",
        description="根据风格包和素材生成结构化剪辑计划",
        category="editing",
        parameters=[
            ToolParameter("style_package", "path", description="风格包路径"),
            ToolParameter("input_video", "path", required=False, description="主输入视频"),
            ToolParameter("input_videos", "list", required=False, description="输入视频列表"),
            ToolParameter("output_dir", "path", description="输出目录"),
            ToolParameter("user_request", "string", description="用户剪辑需求"),
        ],
        returns={"brief_text": "string", "strategy": "dict", "risk_warnings": "list"},
        handler=_tool_build_edit_brief,
    ))

    registry.register(ToolDefinition(
        tool_id="chat_director",
        name="聊天式总导演",
        description="把用户自然语言剪辑沟通解析为意图、建议动作和可应用参数",
        category="editing",
        parameters=[
            ToolParameter("message", "string", description="用户本轮聊天内容"),
            ToolParameter("history", "list", required=False, description="历史对话消息"),
            ToolParameter("context", "dict", required=False, description="当前项目上下文和表单参数"),
        ],
        returns={"intent": "string", "assistant_message": "string", "suggested_actions": "list"},
        handler=_tool_chat_director,
    ))

    registry.register(ToolDefinition(
        tool_id="orchestrate_local_agents",
        name="本地多 Agent 编排",
        description="把当前剪辑任务拆给总导演、素材、时间线、字幕、音频、配音和 QC Agent，返回可执行顺序和风险门禁",
        category="editing",
        parameters=[
            ToolParameter("message", "string", required=False, description="用户本轮任务说明"),
            ToolParameter("history", "list", required=False, description="历史对话消息"),
            ToolParameter("context", "dict", required=False, description="当前项目上下文和表单参数"),
            ToolParameter("director_mode", "string", required=False, default="local_rule", description="导演推理模式"),
        ],
        returns={"agents": "list", "execution_sequence": "list", "summary": "dict"},
        handler=_tool_orchestrate_local_agents,
    ))

    registry.register(ToolDefinition(
        tool_id="run_edit",
        name="执行剪辑",
        description="使用风格包和素材执行完整的剪辑渲染流程",
        category="editing",
        parameters=[
            ToolParameter("style_package", "path", description="风格包路径"),
            ToolParameter("input_video", "path", required=False, description="主输入视频"),
            ToolParameter("input_videos", "list", required=False, description="输入视频列表"),
            ToolParameter("output_dir", "path", description="输出目录"),
            ToolParameter("user_request", "string", description="用户剪辑需求"),
            ToolParameter("execute_real_render", "boolean", required=False, default=False, description="是否执行真实渲染"),
            ToolParameter("confirmed_brief", "string", required=False, description="已确认的剪辑标准"),
        ],
        returns={"ok": "boolean", "toolkit_summary": "dict"},
        handler=_tool_run_edit,
    ))

    registry.register(ToolDefinition(
        tool_id="build_worker_task_package",
        name="生成 Worker 任务包",
        description="把当前本地剪辑任务写成可离线交接、可脚本执行的 worker_task_package.json",
        category="editing",
        parameters=[
            ToolParameter("package_dir", "path", description="任务包目录"),
            ToolParameter("style_package", "path", description="风格包路径"),
            ToolParameter("input_video", "path", required=False, description="主输入视频"),
            ToolParameter("input_videos", "list", required=False, description="输入视频列表"),
            ToolParameter("output_dir", "path", description="输出目录"),
            ToolParameter("user_request", "string", description="用户剪辑需求"),
            ToolParameter("package_name", "string", required=False, description="任务包名称"),
            ToolParameter("execute_real_render", "boolean", required=False, default=False, description="是否真实渲染"),
        ],
        returns={"package_path": "string", "task_package": "dict"},
        handler=_tool_build_worker_task_package,
    ))

    registry.register(ToolDefinition(
        tool_id="run_worker_task_package",
        name="执行 Worker 任务包",
        description="读取本地 worker_task_package.json 并执行，再写 completion.json",
        category="editing",
        parameters=[
            ToolParameter("package_path", "path", description="worker_task_package.json 或其目录"),
        ],
        returns={"completion_path": "string", "status": "string", "output_dir": "string"},
        handler=_tool_run_worker_task_package,
    ))

    registry.register(ToolDefinition(
        tool_id="get_timeline",
        name="获取时间线预览",
        description="根据风格包和素材生成时间线预览（不执行渲染）",
        category="editing",
        parameters=[
            ToolParameter("style_package", "path", description="风格包路径"),
            ToolParameter("input_videos", "list", required=False, description="输入视频列表"),
        ],
        returns={"timeline": "dict"},
        handler=_tool_get_timeline,
    ))

    registry.register(ToolDefinition(
        tool_id="analyze_materials",
        name="分析素材",
        description="分析输入视频的视觉特征和角色分工",
        category="analysis",
        parameters=[
            ToolParameter("input_videos", "list", description="输入视频路径列表"),
            ToolParameter("settings", "dict", required=False, description="visible_settings 或 material_analysis/model_route 设置"),
        ],
        returns={"materials": "list", "role_source_map": "dict", "material_adapter_result": "dict"},
        handler=_tool_analyze_materials,
    ))

    registry.register(ToolDefinition(
        tool_id="list_recent_runs",
        name="查看历史记录",
        description="列出最近的剪辑任务结果",
        category="project",
        parameters=[
            ToolParameter("limit", "integer", required=False, default=20, description="返回数量上限"),
        ],
        returns={"runs": "list"},
        handler=_tool_list_recent_runs,
    ))

    registry.register(ToolDefinition(
        tool_id="discover_style_packages",
        name="发现风格包",
        description="列出所有可用的风格包",
        category="package",
        parameters=[],
        returns={"packages": "list"},
        handler=_tool_discover_style_packages,
    ))

    registry.register(ToolDefinition(
        tool_id="get_task_status",
        name="获取任务状态",
        description="查询指定任务的执行状态和阶段进度",
        category="project",
        parameters=[
            ToolParameter("task_id", "string", description="任务ID"),
        ],
        returns={"status": "string", "stages": "list", "progress_percent": "integer"},
        handler=_tool_get_task_status,
    ))

    registry.register(ToolDefinition(
        tool_id="get_version_history",
        name="获取版本历史",
        description="查询指定输出目录的版本历史记录",
        category="project",
        parameters=[
            ToolParameter("output_dir", "path", description="输出目录路径"),
        ],
        returns={"versions": "list", "current_version": "integer"},
        handler=_tool_get_version_history,
    ))

    registry.register(ToolDefinition(
        tool_id="discover_packs",
        name="发现所有包",
        description="按类型分组列出素材包、风格包和项目包",
        category="package",
        parameters=[],
        returns={"material_packs": "list", "style_packs": "list", "project_packs": "list"},
        handler=_tool_discover_packs,
    ))

    registry.register(ToolDefinition(
        tool_id="re_edit_version",
        name="基于版本复剪",
        description="基于某个版本创建待复剪的新版本，可附加时间线编辑操作",
        category="project",
        parameters=[
            ToolParameter("output_dir", "path", description="项目输出目录"),
            ToolParameter("base_version", "integer", description="基础版本号"),
            ToolParameter("user_feedback", "string", required=False, description="复剪要求"),
            ToolParameter("timeline_edits", "list", required=False, description="时间线编辑操作"),
        ],
        returns={"new_version": "integer", "timeline": "dict", "needs_render": "boolean"},
        handler=_tool_re_edit_version,
    ))

    registry.register(ToolDefinition(
        tool_id="batch_run_edit",
        name="批量执行剪辑",
        description="按任务列表顺序执行多个剪辑任务，并写入 batch_status.json",
        category="editing",
        parameters=[
            ToolParameter("tasks", "list", description="剪辑任务列表"),
            ToolParameter("batch_dir", "path", required=False, description="批量状态输出目录"),
            ToolParameter("batch_id", "string", required=False, description="批量任务 ID"),
            ToolParameter("default_execute_real_render", "boolean", required=False, default=False, description="默认是否真实渲染"),
            ToolParameter("stop_on_error", "boolean", required=False, default=False, description="失败后是否停止"),
            ToolParameter("max_retries", "integer", required=False, default=0, description="单任务失败后的最大重试次数"),
        ],
        returns={"batch_id": "string", "tasks": "list", "completed_count": "integer", "failed_count": "integer"},
        handler=_tool_batch_run_edit,
    ))

    registry.register(ToolDefinition(
        tool_id="watch_queue_once",
        name="扫描目录自动入队",
        description="单次扫描目录中的任务 JSON 文件，自动批量执行并归档成功/失败文件",
        category="editing",
        parameters=[
            ToolParameter("watch_dir", "path", description="任务 JSON 投递目录"),
            ToolParameter("batch_root", "path", required=False, description="批量运行状态根目录"),
            ToolParameter("archive_dir", "path", required=False, description="成功任务文件归档目录"),
            ToolParameter("failed_dir", "path", required=False, description="失败任务文件归档目录"),
            ToolParameter("pattern", "string", required=False, default="*.json", description="任务文件匹配规则"),
            ToolParameter("default_execute_real_render", "boolean", required=False, default=False, description="默认是否真实渲染"),
            ToolParameter("stop_on_error", "boolean", required=False, default=False, description="遇到失败任务文件后是否停止"),
            ToolParameter("max_retries", "integer", required=False, default=0, description="单任务失败后的最大重试次数"),
            ToolParameter("dry_run", "boolean", required=False, default=False, description="仅扫描不执行和归档"),
        ],
        returns={"files": "list", "processed_count": "integer", "failed_count": "integer", "queued_count": "integer"},
        handler=_tool_watch_queue_once,
    ))

    registry.register(ToolDefinition(
        tool_id="export_project_pack",
        name="导出项目包",
        description="从输出目录导出可迁移 ProjectPack",
        category="package",
        parameters=[
            ToolParameter("output_dir", "path", description="来源输出目录"),
            ToolParameter("package_dir", "path", description="项目包保存目录"),
            ToolParameter("name", "string", required=False, description="项目包名称"),
            ToolParameter("style_pack_ref", "path", required=False, description="风格包引用"),
        ],
        returns={"pack": "dict", "project_pack_path": "path"},
        handler=_tool_export_project_pack,
    ))

    registry.register(ToolDefinition(
        tool_id="validate_project",
        name="校验项目",
        description="校验输出目录、项目清单、版本历史或 ProjectPack 引用",
        category="project",
        parameters=[
            ToolParameter("output_dir", "path", required=False, description="项目输出目录"),
            ToolParameter("project_pack_path", "path", required=False, description="项目包路径"),
            ToolParameter("project_pack", "dict", required=False, description="项目包对象"),
        ],
        returns={"valid": "boolean", "warnings": "list", "errors": "list"},
        handler=_tool_validate_project,
    ))

    registry.register(ToolDefinition(
        tool_id="build_local_toolkit_protocol",
        name="生成本地协议清单",
        description="为一个输出目录生成 local_toolkit_protocol.json，统一记录结果、清单和交接文件",
        category="project",
        parameters=[
            ToolParameter("output_dir", "path", description="项目输出目录"),
        ],
        returns={"protocol_path": "path", "artifacts": "list", "contracts": "dict"},
        handler=_tool_build_local_toolkit_protocol,
    ))

    registry.register(ToolDefinition(
        tool_id="inspect_local_toolkit_protocol",
        name="检查本地协议",
        description="识别并摘要本地协议文件或目录，兼容 Worker、ProjectPack、FilmGen handoff 等",
        category="project",
        parameters=[
            ToolParameter("path", "path", description="文件或目录路径"),
        ],
        returns={"protocol_kind": "string", "summary": "dict", "validation": "dict"},
        handler=_tool_inspect_local_toolkit_protocol,
    ))

    registry.register(ToolDefinition(
        tool_id="run_protocol_path",
        name="按协议执行",
        description="执行可运行的本地协议文件，支持 Worker 任务包、ProjectPack、FilmGen handoff 等",
        category="editing",
        parameters=[
            ToolParameter("path", "path", description="协议文件路径"),
            ToolParameter("output_dir", "path", required=False, description="覆盖输出目录"),
            ToolParameter("style_package", "path", required=False, description="覆盖风格包路径"),
            ToolParameter("user_request", "string", required=False, description="覆盖用户需求"),
            ToolParameter("execute_real_render", "boolean", required=False, default=False, description="是否真实渲染"),
        ],
        returns={"ok": "boolean", "protocol_kind": "string", "protocol_runner": "string"},
        handler=_tool_run_protocol_path,
    ))

    registry.register(ToolDefinition(
        tool_id="init_protocol_dropbox",
        name="初始化协议投递箱",
        description="创建标准投递目录、模板文件、归档目录和 batch_runs 根目录",
        category="project",
        parameters=[
            ToolParameter("dropbox_dir", "path", required=False, description="协议投递箱根目录"),
        ],
        returns={"dropbox_dir": "path", "queues": "dict", "templates": "dict"},
        handler=_tool_init_protocol_dropbox,
    ))

    registry.register(ToolDefinition(
        tool_id="import_protocol_dropbox_item",
        name="投递协议文件到标准队列",
        description="把 Worker、ProjectPack、FilmGen handoff、输出目录或批量任务 JSON 复制到标准投递箱并自动归类",
        category="project",
        parameters=[
            ToolParameter("source_path", "path", description="来源文件或目录"),
            ToolParameter("dropbox_dir", "path", required=False, description="协议投递箱根目录"),
            ToolParameter("label", "string", required=False, description="可选命名标签"),
        ],
        returns={"imported_path": "path", "protocol_kind": "string", "queue_id": "string"},
        handler=_tool_import_protocol_dropbox_item,
    ))

    registry.register(ToolDefinition(
        tool_id="run_protocol_dropbox_once",
        name="执行标准协议投递箱",
        description="顺序扫描标准投递箱的各类 inbox 队列，并调用现有 watch_queue 流程完成批量执行和归档",
        category="editing",
        parameters=[
            ToolParameter("dropbox_dir", "path", required=False, description="协议投递箱根目录"),
            ToolParameter("default_execute_real_render", "boolean", required=False, default=False, description="默认是否真实渲染"),
            ToolParameter("stop_on_error", "boolean", required=False, default=False, description="是否遇错即停"),
            ToolParameter("max_retries", "integer", required=False, default=0, description="单任务最大重试次数"),
            ToolParameter("dry_run", "boolean", required=False, default=False, description="仅扫描不执行"),
        ],
        returns={"processed_count": "integer", "failed_count": "integer", "queues": "list"},
        handler=_tool_run_protocol_dropbox_once,
    ))

    registry.register(ToolDefinition(
        tool_id="run_protocol_dropbox_monitor",
        name="阻塞执行协议投递箱轮询",
        description="在当前进程里按间隔循环执行标准协议投递箱，并持续写入 dropbox_monitor.json",
        category="editing",
        parameters=[
            ToolParameter("dropbox_dir", "path", required=False, description="协议投递箱根目录"),
            ToolParameter("interval_seconds", "number", required=False, default=15.0, description="轮询间隔秒数"),
            ToolParameter("max_cycles", "integer", required=False, default=0, description="最大轮询次数，0 表示持续运行直到中断"),
            ToolParameter("default_execute_real_render", "boolean", required=False, default=False, description="默认是否真实渲染"),
            ToolParameter("stop_on_error", "boolean", required=False, default=False, description="遇错后是否停止后续轮询"),
            ToolParameter("max_retries", "integer", required=False, default=0, description="单任务最大重试次数"),
            ToolParameter("dry_run", "boolean", required=False, default=False, description="仅扫描不执行"),
        ],
        returns={"completed_cycles": "integer", "totals": "dict", "status": "string"},
        handler=_tool_run_protocol_dropbox_monitor,
    ))

    registry.register(ToolDefinition(
        tool_id="start_protocol_dropbox_monitor",
        name="后台启动协议投递箱轮询",
        description="在 Web/本地服务进程中后台启动标准协议投递箱自动轮询",
        category="editing",
        parameters=[
            ToolParameter("dropbox_dir", "path", required=False, description="协议投递箱根目录"),
            ToolParameter("interval_seconds", "number", required=False, default=15.0, description="轮询间隔秒数"),
            ToolParameter("max_cycles", "integer", required=False, default=0, description="最大轮询次数，0 表示持续运行直到停止"),
            ToolParameter("default_execute_real_render", "boolean", required=False, default=False, description="默认是否真实渲染"),
            ToolParameter("stop_on_error", "boolean", required=False, default=False, description="是否遇错即停"),
            ToolParameter("max_retries", "integer", required=False, default=0, description="单任务最大重试次数"),
            ToolParameter("dry_run", "boolean", required=False, default=False, description="仅扫描不执行"),
        ],
        returns={"running": "boolean", "status": "string", "interval_seconds": "number"},
        handler=_tool_start_protocol_dropbox_monitor,
    ))

    registry.register(ToolDefinition(
        tool_id="stop_protocol_dropbox_monitor",
        name="停止协议投递箱轮询",
        description="请求停止当前后台协议投递箱自动轮询，并返回最新监控状态",
        category="editing",
        parameters=[
            ToolParameter("dropbox_dir", "path", required=False, description="协议投递箱根目录"),
        ],
        returns={"running": "boolean", "status": "string", "stop_requested": "boolean"},
        handler=_tool_stop_protocol_dropbox_monitor,
    ))

    registry.register(ToolDefinition(
        tool_id="get_protocol_dropbox_monitor_status",
        name="读取协议投递箱轮询状态",
        description="读取当前 dropbox_monitor.json 与进程内状态，用于看板刷新和脚本检查",
        category="project",
        parameters=[
            ToolParameter("dropbox_dir", "path", required=False, description="协议投递箱根目录"),
        ],
        returns={"running": "boolean", "status": "string", "totals": "dict"},
        handler=_tool_get_protocol_dropbox_monitor_status,
    ))

    registry.register(ToolDefinition(
        tool_id="get_protocol_dropbox_history",
        name="读取协议投递箱运行历史",
        description="读取 dropbox_history.json 中最近运行记录，并支持只看告警条目或某个队列的历史",
        category="project",
        parameters=[
            ToolParameter("dropbox_dir", "path", required=False, description="协议投递箱根目录"),
            ToolParameter("limit", "integer", required=False, default=20, description="返回最近多少条历史"),
            ToolParameter("queue_id", "string", required=False, description="可选过滤队列，如 worker_packages"),
            ToolParameter("alerts_only", "boolean", required=False, default=False, description="是否只返回有告警的历史"),
        ],
        returns={"entries": "list", "run_count": "integer", "alert_entry_count": "integer"},
        handler=_tool_get_protocol_dropbox_history,
    ))

    registry.register(ToolDefinition(
        tool_id="requeue_protocol_dropbox_failed",
        name="回投协议投递箱失败文件",
        description="把 archive/failed 中的协议文件重新放回 inbox 队列，便于人工修正后再跑一轮",
        category="editing",
        parameters=[
            ToolParameter("dropbox_dir", "path", required=False, description="协议投递箱根目录"),
            ToolParameter("queue_id", "string", required=False, default="all", description="指定队列或 all"),
            ToolParameter("max_files", "integer", required=False, default=20, description="最多回投多少个失败文件"),
        ],
        returns={"moved_count": "integer", "queues": "list"},
        handler=_tool_requeue_protocol_dropbox_failed,
    ))

    registry.register(ToolDefinition(
        tool_id="list_adapters",
        name="列出插件适配器",
        description="列出本地优先的配音、字幕、BGM、素材分析和导出适配器清单",
        category="adapter",
        parameters=[
            ToolParameter("category", "string", required=False, description="按适配器类别过滤"),
            ToolParameter("status", "string", required=False, description="按 ready / requires_setup / planned 等状态过滤"),
        ],
        returns={"adapters": "list", "categories": "list"},
        handler=_tool_list_adapters,
    ))

    registry.register(ToolDefinition(
        tool_id="resolve_adapters",
        name="解析适配器选择",
        description="根据 visible_settings 或风格包解析本次剪辑会优先使用的适配器",
        category="adapter",
        parameters=[
            ToolParameter("settings", "dict", required=False, description="visible_settings 对象"),
            ToolParameter("style_package", "path", required=False, description="风格包路径"),
            ToolParameter("settings_overrides", "dict", required=False, description="用户覆盖设置"),
        ],
        returns={"selected_adapter_ids": "dict", "warnings": "list"},
        handler=_tool_resolve_adapters,
    ))

    return registry
