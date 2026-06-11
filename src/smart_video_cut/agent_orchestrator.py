from __future__ import annotations

import hashlib
import json
import time
from typing import Any, Mapping

from smart_video_cut.director_agent import chat_with_director
from smart_video_cut.external_handoff_compat import is_external_subtitle_mode


AGENT_ORCHESTRATION_SCHEMA = "smart_video_cut.local.agent_orchestration.v0"


def orchestrate_local_agents(
    *,
    message: str = "",
    context: Mapping[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
    director_mode: str = "local_rule",
    memory_context: str | None = None,
) -> dict[str, Any]:
    """Build a deterministic local multi-agent plan for one edit task."""

    context_dict = dict(context or {})
    user_message = str(message or context_dict.get("user_request") or "").strip()
    director_context = {**context_dict, "director_mode": director_mode}
    director = chat_with_director(
        user_message,
        history=history or [],
        context=director_context,
        memory_context=memory_context,
    )
    settings = _settings(context_dict, director.get("settings_overrides"))
    base_missing = _base_missing_inputs(context_dict)
    agents = [
        _director_agent(director),
        _material_agent(context_dict, base_missing),
        _timeline_agent(context_dict, base_missing),
        _subtitle_agent(context_dict, settings, base_missing),
        _audio_agent(context_dict, settings, base_missing),
        _voice_agent(context_dict, settings, base_missing),
        _qc_agent(context_dict, settings, base_missing),
    ]
    sequence = _execution_sequence(agents)
    warnings = _risk_warnings(agents)
    summary = _summary(agents=agents, sequence=sequence)
    created_at = time.time()
    return {
        "schema": AGENT_ORCHESTRATION_SCHEMA,
        "ok": True,
        "created_at": created_at,
        "orchestration_id": _orchestration_id(
            created_at=created_at,
            message=user_message,
            context=context_dict,
        ),
        "mode": "local_rule_multi_agent",
        "director_mode": director_mode,
        "director_result": director,
        "settings_overrides": director.get("settings_overrides") or {},
        "agents": agents,
        "execution_sequence": sequence,
        "summary": summary,
        "risk_warnings": warnings,
    }


def _director_agent(director: Mapping[str, Any]) -> dict[str, Any]:
    actions = [
        _action(
            action_id=item.get("action_id") or "",
            label=item.get("label") or "执行导演建议",
            api_endpoint=item.get("api_endpoint") or "",
            tool_id=_tool_for_action(item.get("action_id") or ""),
            requires_confirmation=bool(item.get("requires_confirmation")),
            reason="总导演识别出的下一步动作。",
        )
        for item in director.get("suggested_actions") or []
        if isinstance(item, Mapping)
    ]
    missing = director.get("missing_inputs") if isinstance(director.get("missing_inputs"), list) else []
    return _agent(
        agent_id="director",
        name="总导演 Agent",
        role="理解用户目标，统一剪辑策略，并把自然语言转成可执行动作。",
        status="blocked" if missing else "ready",
        responsibilities=["识别意图", "提取参数覆盖", "排序下一步动作"],
        findings=[director.get("assistant_message") or "已生成导演理解。"],
        required_inputs=missing,
        tool_plan=actions,
        handoff={
            "produces": ["settings_overrides", "suggested_actions", "missing_inputs"],
            "consumes": ["user_request", "current_form_state", "local_memory"],
        },
        confidence=float(director.get("confidence") or 0.0),
    )


def _material_agent(context: Mapping[str, Any], base_missing: list[dict[str, str]]) -> dict[str, Any]:
    missing = _filter_missing(base_missing, {"input_video"})
    input_count = len(_input_videos(context))
    findings = [
        f"已识别 {input_count} 个输入素材。" if input_count else "还没有可分析的输入素材。",
    ]
    if input_count > 1:
        findings.append("多素材任务建议先做素材角色分工，再生成时间线。")
    return _agent(
        agent_id="material_analyst",
        name="素材分析 Agent",
        role="检查输入素材可用性、角色分工和视觉分析策略。",
        status="blocked" if missing else "ready",
        responsibilities=["素材存在性检查", "主素材/补充素材分工", "视觉分析适配器选择"],
        findings=findings,
        required_inputs=missing,
        tool_plan=[
            _action(
                action_id="analyze_materials",
                label="分析素材角色",
                api_endpoint="/api/agent/tools/analyze_materials/invoke",
                tool_id="analyze_materials",
                reason="给时间线和剪辑标准提供素材分工依据。",
            )
        ] if not missing else [],
        handoff={
            "produces": ["material_plan", "role_source_map"],
            "consumes": ["input_videos", "material_analysis_settings"],
        },
        confidence=0.82 if not missing else 0.4,
    )


def _timeline_agent(context: Mapping[str, Any], base_missing: list[dict[str, str]]) -> dict[str, Any]:
    missing = _filter_missing(base_missing, {"style_package", "input_video", "output_dir", "user_request"})
    has_override = bool(context.get("has_timeline_override") or context.get("timeline_override"))
    findings = [
        "已有手工时间线，可优先尊重用户编辑。" if has_override else "尚未锁定时间线，建议生成片段卡片预览。",
    ]
    return _agent(
        agent_id="timeline_editor",
        name="时间线剪辑 Agent",
        role="把素材和风格转换成可编辑片段卡片，管理顺序、时长和替换素材。",
        status="blocked" if missing else "ready",
        responsibilities=["生成时间线预览", "校验片段连续性", "接收用户编辑后的 timeline_override"],
        findings=findings,
        required_inputs=missing,
        tool_plan=[
            _action(
                action_id="generate_timeline",
                label="生成时间线预览",
                api_endpoint="/api/timeline",
                tool_id="get_timeline",
                reason="先生成可视化片段卡片，再进入真实渲染更稳。",
            )
        ] if not missing else [],
        handoff={
            "produces": ["timeline_plan", "toolkit_timeline_format"],
            "consumes": ["material_plan", "style_package", "settings"],
        },
        confidence=0.84 if not missing else 0.42,
    )


def _subtitle_agent(
    context: Mapping[str, Any],
    settings: Mapping[str, Any],
    base_missing: list[dict[str, str]],
) -> dict[str, Any]:
    subtitle = _section(settings, "subtitle")
    mode = str(subtitle.get("mode") or "auto")
    enabled = subtitle.get("enabled", True) is not False and mode != "none"
    missing: list[dict[str, str]] = []
    if enabled and is_external_subtitle_mode(mode) and not _truthy(context.get("subtitle_handoff_path")):
        missing.append({
            "field": "subtitle_handoff_path",
            "label": "外部字幕交接文件",
            "reason": "选择外部字幕交接模式时需要先提供 handoff 文件。",
        })
    status = "disabled" if not enabled else "blocked" if missing else "ready"
    readable_mode = "外部交接" if enabled and is_external_subtitle_mode(mode) else mode
    return _agent(
        agent_id="subtitle_designer",
        name="字幕 Agent",
        role="规划字幕来源、样式、安全边距和外部字幕交接。",
        status=status,
        responsibilities=["字幕模式选择", "字号/描边/位置检查", "外部字幕交接验收"],
        findings=[f"当前字幕模式：{'关闭' if not enabled else readable_mode}。"],
        required_inputs=missing,
        tool_plan=[
            _action(
                action_id="generate_edit_brief",
                label="刷新字幕剪辑标准",
                api_endpoint="/api/edit-brief",
                tool_id="build_edit_brief",
                reason="让字幕策略进入导演确认稿。",
            )
        ] if enabled and not missing and not base_missing else [],
        handoff={
            "produces": ["subtitle_settings", "subtitle_handoff_validation"],
            "consumes": ["user_request", "settings.subtitle"],
        },
        confidence=0.8 if not missing else 0.46,
    )


def _audio_agent(
    context: Mapping[str, Any],
    settings: Mapping[str, Any],
    base_missing: list[dict[str, str]],
) -> dict[str, Any]:
    audio = _section(settings, "audio")
    bgm_style = str(audio.get("bgm_style") or "upbeat_instrumental")
    missing: list[dict[str, str]] = []
    if bgm_style == "library" and not _truthy(audio.get("bgm_library_dir")):
        missing.append({"field": "bgm_library_dir", "label": "BGM 素材库目录", "reason": "素材库音乐需要先选择本地音乐目录。"})
    if bgm_style == "local_audio" and not _truthy(audio.get("bgm_audio_path")):
        missing.append({"field": "bgm_audio_path", "label": "本地 BGM 文件", "reason": "本地音乐模式需要指定音频文件。"})
    disabled = bgm_style == "none"
    status = "disabled" if disabled else "blocked" if missing else "ready"
    tool_plan = []
    if not disabled and not missing and not base_missing:
        tool_plan.append(_action(
            action_id="generate_edit_brief",
            label="刷新音乐剪辑标准",
            api_endpoint="/api/edit-brief",
            tool_id="build_edit_brief",
            reason="把 BGM 风格和音量策略写入确认稿。",
        ))
    return _agent(
        agent_id="audio_mixer",
        name="音频/BGM Agent",
        role="选择 BGM 来源、音量策略和原声保留方式。",
        status=status,
        responsibilities=["BGM 来源选择", "音量平衡", "原视频人声处理"],
        findings=[f"当前 BGM 策略：{bgm_style}。"],
        required_inputs=missing,
        tool_plan=tool_plan,
        handoff={
            "produces": ["audio_settings", "bgm_selection"],
            "consumes": ["settings.audio", "local_bgm_library"],
        },
        confidence=0.79 if not missing else 0.48,
    )


def _voice_agent(
    context: Mapping[str, Any],
    settings: Mapping[str, Any],
    base_missing: list[dict[str, str]],
) -> dict[str, Any]:
    voice = _section(settings, "voice")
    provider = str(voice.get("provider") or "edge_tts")
    missing: list[dict[str, str]] = []
    if voice.get("require_saved_profile") is True and not isinstance(voice.get("voice_profile_ref"), Mapping):
        missing.append({
            "field": "voice_profile_ref",
            "label": "已确认 voice_profile_ref",
            "reason": "启用保存音色时必须先完成真实试听确认。",
        })
    disabled = provider == "none"
    status = "disabled" if disabled else "blocked" if missing else "ready"
    tool_plan = []
    if not disabled and not missing and not base_missing:
        tool_plan.append(_action(
            action_id="generate_edit_brief",
            label="刷新配音剪辑标准",
            api_endpoint="/api/edit-brief",
            tool_id="build_edit_brief",
            reason="把配音供应商、旁白文案和音色约束写入确认稿。",
        ))
    if missing:
        tool_plan.append(_action(
            action_id="confirm_voice_profile",
            label="去设置页试听并确认 voice_profile_ref",
            api_endpoint="/api/voice-profile/confirm",
            tool_id="",
            requires_confirmation=True,
            reason="防止未试听音色直接进入成片。",
        ))
    return _agent(
        agent_id="voice_director",
        name="配音 Agent",
        role="管理旁白文本、人声供应商、试听确认和 voice_profile_ref 绑定。",
        status=status,
        responsibilities=["配音模式选择", "voice_profile_ref 检查", "旁白文本交接"],
        findings=[f"当前配音 Provider：{provider}。"],
        required_inputs=missing,
        tool_plan=tool_plan,
        handoff={
            "produces": ["voice_settings", "voiceover_text", "voice_profile_ref"],
            "consumes": ["settings.voice", "voiceoverText"],
        },
        confidence=0.81 if not missing else 0.5,
    )


def _qc_agent(
    context: Mapping[str, Any],
    settings: Mapping[str, Any],
    base_missing: list[dict[str, str]],
) -> dict[str, Any]:
    findings = ["计划模式下先检查输入、时间线、字幕、音频和版本记录。"]
    required = list(base_missing)
    if context.get("execute_real_render") is True and not _truthy(context.get("confirmed_brief")):
        findings.append("真实渲染前建议先确认 brief，减少返修成本。")
    return _agent(
        agent_id="qc_supervisor",
        name="QC Agent",
        role="做最终开剪门禁，确认风险、版本记录和可回退性。",
        status="blocked" if required else "ready",
        responsibilities=["缺口汇总", "渲染前确认", "版本/回退检查"],
        findings=findings,
        required_inputs=required,
        tool_plan=[
            _action(
                action_id="generate_edit_brief",
                label="生成剪辑标准",
                api_endpoint="/api/edit-brief",
                tool_id="build_edit_brief",
                reason="先形成可确认的任务标准。",
            ),
            _action(
                action_id="run_cut",
                label="确认后开始剪辑",
                api_endpoint="/api/cut",
                tool_id="run_edit",
                requires_confirmation=True,
                reason="真实渲染会写入输出目录和版本记录。",
            ),
        ] if not required else [],
        handoff={
            "produces": ["ready_to_render_gate", "risk_warnings"],
            "consumes": ["all_agent_outputs", "confirmed_brief", "timeline_override"],
        },
        confidence=0.86 if not required else 0.45,
    )


def _agent(
    *,
    agent_id: str,
    name: str,
    role: str,
    status: str,
    responsibilities: list[str],
    findings: list[Any],
    required_inputs: list[dict[str, Any]],
    tool_plan: list[dict[str, Any]],
    handoff: dict[str, Any],
    confidence: float,
) -> dict[str, Any]:
    return {
        "agent_id": agent_id,
        "name": name,
        "role": role,
        "status": status,
        "confidence": round(max(0.0, min(confidence, 1.0)), 3),
        "responsibilities": responsibilities,
        "findings": [str(item) for item in findings if str(item or "").strip()],
        "required_inputs": required_inputs,
        "tool_plan": tool_plan,
        "handoff": handoff,
        "next_step": _next_step(status=status, required_inputs=required_inputs, tool_plan=tool_plan),
    }


def _action(
    *,
    action_id: str,
    label: str,
    api_endpoint: str,
    tool_id: str,
    reason: str,
    requires_confirmation: bool = False,
) -> dict[str, Any]:
    return {
        "action_id": action_id,
        "label": label,
        "api_endpoint": api_endpoint,
        "tool_id": tool_id,
        "requires_confirmation": requires_confirmation,
        "reason": reason,
    }


def _summary(*, agents: list[dict[str, Any]], sequence: list[dict[str, Any]]) -> dict[str, Any]:
    blocked = [agent for agent in agents if agent["status"] == "blocked"]
    warning = [agent for agent in agents if agent["status"] == "warning"]
    ready = [agent for agent in agents if agent["status"] == "ready"]
    run_ready = not blocked
    return {
        "agent_count": len(agents),
        "ready_agents": len(ready),
        "blocked_agents": len(blocked),
        "warning_agents": len(warning),
        "run_ready": run_ready,
        "requires_confirmation": any(action.get("requires_confirmation") for action in sequence),
        "recommended_next_action": _recommended_next_action(blocked=blocked, sequence=sequence),
    }


def _recommended_next_action(*, blocked: list[dict[str, Any]], sequence: list[dict[str, Any]]) -> dict[str, Any]:
    if blocked:
        agent = blocked[0]
        missing = agent.get("required_inputs") or []
        label = missing[0].get("label") if missing and isinstance(missing[0], Mapping) else "缺失输入"
        return {
            "action_id": "complete_required_inputs",
            "label": f"先补齐：{label}",
            "agent_id": agent.get("agent_id"),
            "requires_confirmation": False,
        }
    if sequence:
        return dict(sequence[0])
    return {
        "action_id": "review_plan",
        "label": "检查多 Agent 编排结果",
        "requires_confirmation": False,
    }


def _execution_sequence(agents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    sequence: list[dict[str, Any]] = []
    seen: set[str] = set()
    for agent in agents:
        if agent.get("status") != "ready":
            continue
        for action in agent.get("tool_plan") or []:
            action_id = str(action.get("action_id") or "")
            if not action_id or action_id in seen:
                continue
            seen.add(action_id)
            sequence.append({**action, "agent_id": agent.get("agent_id")})
    return sequence


def _risk_warnings(agents: list[dict[str, Any]]) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    for agent in agents:
        for item in agent.get("required_inputs") or []:
            if isinstance(item, Mapping):
                warnings.append({
                    "code": f"{agent.get('agent_id')}_missing_{item.get('field')}",
                    "message": f"{agent.get('name')} 缺少{item.get('label') or item.get('field')}：{item.get('reason') or ''}",
                })
    return warnings


def _base_missing_inputs(context: Mapping[str, Any]) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    if not _truthy(context.get("style_package")):
        missing.append({"field": "style_package", "label": "风格包", "reason": "需要一个参考风格才能生成稳定剪辑方案。"})
    if not _input_videos(context):
        missing.append({"field": "input_video", "label": "输入素材", "reason": "需要至少一个原视频素材。"})
    if not _truthy(context.get("output_dir")):
        missing.append({"field": "output_dir", "label": "输出目录", "reason": "需要保存剪辑结果和版本记录。"})
    if not _truthy(context.get("user_request")):
        missing.append({"field": "user_request", "label": "任务要求", "reason": "需要一句话说明成片目标。"})
    return missing


def _filter_missing(items: list[dict[str, str]], fields: set[str]) -> list[dict[str, str]]:
    return [item for item in items if item.get("field") in fields]


def _settings(context: Mapping[str, Any], director_overrides: Any) -> dict[str, Any]:
    merged = _deep_copy_mapping(context.get("settings_overrides"))
    if isinstance(director_overrides, Mapping):
        merged = _deep_merge(merged, director_overrides)
    return merged


def _section(settings: Mapping[str, Any], section: str) -> dict[str, Any]:
    value = settings.get(section)
    return dict(value) if isinstance(value, Mapping) else {}


def _deep_copy_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return json.loads(json.dumps(dict(value), ensure_ascii=False))


def _deep_merge(base: dict[str, Any], patch: Mapping[str, Any]) -> dict[str, Any]:
    for key, value in patch.items():
        if isinstance(value, Mapping) and isinstance(base.get(key), dict):
            base[key] = _deep_merge(dict(base[key]), value)
        elif isinstance(value, Mapping):
            base[key] = dict(value)
        else:
            base[key] = value
    return base


def _input_videos(context: Mapping[str, Any]) -> list[str]:
    videos = [str(item).strip() for item in context.get("input_videos") or [] if str(item).strip()]
    primary = str(context.get("input_video") or "").strip()
    if primary and primary not in videos:
        videos.insert(0, primary)
    return videos


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_truthy(item) for item in value)
    if isinstance(value, Mapping):
        return bool(value)
    return bool(value)


def _next_step(
    *,
    status: str,
    required_inputs: list[dict[str, Any]],
    tool_plan: list[dict[str, Any]],
) -> str:
    if status == "disabled":
        return "当前模块已关闭，无需动作。"
    if required_inputs:
        return f"先补齐：{required_inputs[0].get('label') or required_inputs[0].get('field')}。"
    if tool_plan:
        return str(tool_plan[0].get("label") or "执行建议动作")
    return "等待上游 Agent 交接。"


def _tool_for_action(action_id: str) -> str:
    return {
        "generate_timeline": "get_timeline",
        "generate_edit_brief": "build_edit_brief",
        "run_cut": "run_edit",
        "apply_settings_overrides": "",
        "open_version_center": "get_version_history",
    }.get(action_id, "")


def _orchestration_id(*, created_at: float, message: str, context: Mapping[str, Any]) -> str:
    raw = json.dumps(
        {
            "created_at": created_at,
            "message": message,
            "style_package": context.get("style_package"),
            "input_videos": _input_videos(context),
            "output_dir": context.get("output_dir"),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"local_agents_{int(created_at)}_{digest}"
