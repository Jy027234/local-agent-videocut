from __future__ import annotations

import json
import re
import time
import urllib.error
import urllib.request
from typing import Callable
from typing import Any


DIRECTOR_CHAT_SCHEMA = "smart_video_cut.local.director_chat.v0"
DIRECTOR_LLM_SCHEMA = "smart_video_cut.local.director_llm_response.v0"

DirectorLlmClient = Callable[..., dict[str, Any]]


_INTENT_KEYWORDS: list[tuple[str, tuple[str, ...]]] = [
    ("run_cut", ("开始剪辑", "确认剪辑", "开始渲染", "渲染", "导出视频", "出片", "生成成片")),
    ("re_edit", ("复剪", "重剪", "返修", "再剪", "修改", "不满意", "调一下", "改一下")),
    ("timeline", ("时间线", "片段", "镜头", "顺序", "节奏", "时长", "拖拽", "替换素材")),
    ("edit_brief", ("剪辑标准", "导演理解", "brief", "需求", "方案", "确认稿")),
    ("material", ("素材", "画面", "门", "锁", "安装", "环境", "镜头来源")),
    ("bgm", ("bgm", "BGM", "音乐", "配乐", "伴奏", "素材库音乐")),
    ("voice", ("配音", "旁白", "人声", "tts", "TTS", "男声", "女声", "音色")),
    ("filmgen", ("filmgen", "FilmGen", "handoff", "交接", "外部生成")),
]


def chat_with_director(
    message: str,
    history: list[dict[str, Any]] | None = None,
    context: dict[str, Any] | None = None,
    llm_client: DirectorLlmClient | None = None,
    memory_context: str | None = None,
) -> dict[str, Any]:
    """Local rule-based director chat entrypoint.

    This is intentionally deterministic: it gives the UI a stable product
    surface today while leaving room for an LLM-backed director later.
    """

    text = str(message or "").strip()
    history = history or []
    context = context or {}
    intent = _detect_intent(text)
    overrides = _infer_settings_overrides(text)
    missing_inputs = _missing_inputs(context)
    actions = _suggest_actions(intent=intent, overrides=overrides, missing_inputs=missing_inputs)
    assistant_message = _assistant_message(intent=intent, overrides=overrides, missing_inputs=missing_inputs)
    project_memory = memory_context if memory_context is not None else _load_project_memory(context)

    result = {
        "schema": DIRECTOR_CHAT_SCHEMA,
        "ok": True,
        "mode": "local_rule_director",
        "intent": intent,
        "assistant_message": assistant_message,
        "suggested_actions": actions,
        "settings_overrides": overrides,
        "missing_inputs": missing_inputs,
        "history_count": len(history),
        "memory_context_applied": bool(project_memory),
        "memory_context_preview": project_memory[:1200],
        "llm_result": None,
        "confidence": _intent_confidence(text=text, intent=intent),
    }
    if _llm_requested(context):
        llm_result = (llm_client or _call_configured_director_llm)(
            message=text,
            history=history,
            context=context,
            base_result=result,
            memory_context=project_memory,
        )
        result["llm_result"] = llm_result
        if llm_result.get("ok") is True and llm_result.get("assistant_message"):
            result["mode"] = "hybrid_llm_director"
            result["assistant_message"] = str(llm_result["assistant_message"])
            result["confidence"] = max(float(result["confidence"]), 0.86)
    return result


def _detect_intent(text: str) -> str:
    normalized = text.casefold()
    for intent, keywords in _INTENT_KEYWORDS:
        if any(keyword.casefold() in normalized for keyword in keywords):
            return intent
    return "clarify"


def _intent_confidence(text: str, intent: str) -> float:
    if not text:
        return 0.0
    if intent == "clarify":
        return 0.35
    return 0.78


def _infer_settings_overrides(text: str) -> dict[str, Any]:
    overrides: dict[str, Any] = {}
    normalized = text.casefold()

    duration = _parse_duration_seconds(text)
    if duration is not None:
        _deep_set(overrides, "video", "target_duration_seconds", duration)

    aspect_ratio = _parse_aspect_ratio(text)
    if aspect_ratio:
        _deep_set(overrides, "video", "aspect_ratio", aspect_ratio)

    resolution = _parse_resolution(text)
    if resolution:
        _deep_set(overrides, "video", "resolution", resolution)

    if _has_any(normalized, ("不加字幕", "不要字幕", "无字幕", "去掉字幕")):
        _deep_set(overrides, "subtitle", "enabled", False)
        _deep_set(overrides, "subtitle", "mode", "none")
    elif _has_any(normalized, ("filmgen 字幕", "filmgen字幕", "字幕交接")):
        _deep_set(overrides, "subtitle", "enabled", True)
        _deep_set(overrides, "subtitle", "mode", "filmgen")

    if _has_any(normalized, ("不加配音", "不要配音", "无配音", "去掉配音")):
        _deep_set(overrides, "voice", "provider", "none")
        _deep_set(overrides, "voice", "mode", "none")
    elif _has_any(normalized, ("系统tts", "系统 tts", "system tts", "system_tts")):
        _deep_set(overrides, "voice", "provider", "system_tts")
    elif _has_any(normalized, ("fixture", "测试占位音", "占位音")):
        _deep_set(overrides, "voice", "provider", "fixture")
    elif _has_any(normalized, ("moss", "moss-tts", "moss_tts")):
        _deep_set(overrides, "voice", "provider", "moss_tts_nano")

    if _has_any(normalized, ("不加音乐", "不要音乐", "无音乐", "不加bgm", "不加 bgm", "不要bgm", "不要 bgm", "无bgm", "无 bgm")):
        _deep_set(overrides, "audio", "bgm_style", "none")
    elif _has_any(normalized, ("本地音乐", "本地bgm", "本地 bgm")):
        _deep_set(overrides, "audio", "bgm_style", "local_audio")
    elif _has_any(normalized, ("素材库音乐", "bgm素材库", "bgm 素材库", "音乐素材库")):
        _deep_set(overrides, "audio", "bgm_style", "library")

    return overrides


def _parse_duration_seconds(text: str) -> int | None:
    match = re.search(r"(\d{1,3})\s*(秒|s|S)", text)
    if not match:
        return None
    value = int(match.group(1))
    return max(1, min(value, 600))


def _parse_aspect_ratio(text: str) -> str:
    for ratio in ("16:9", "9:16", "1:1", "4:5"):
        if ratio in text:
            return ratio
    return ""


def _parse_resolution(text: str) -> str:
    match = re.search(r"(\d{3,4})\s*[xX×]\s*(\d{3,4})", text)
    if not match:
        return ""
    return f"{match.group(1)}x{match.group(2)}"


def _missing_inputs(context: dict[str, Any]) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    if not _truthy(context.get("style_package")):
        missing.append({"field": "style_package", "label": "风格包", "reason": "需要一个参考风格才能生成稳定剪辑方案"})
    if not _truthy(context.get("input_video")) and not _truthy(context.get("input_videos")):
        missing.append({"field": "input_video", "label": "输入素材", "reason": "需要至少一个原视频素材"})
    if not _truthy(context.get("output_dir")):
        missing.append({"field": "output_dir", "label": "输出目录", "reason": "需要保存剪辑结果和版本记录"})
    if not _truthy(context.get("user_request")):
        missing.append({"field": "user_request", "label": "任务要求", "reason": "需要一句话说明成片目标"})
    return missing


def _truthy(value: Any) -> bool:
    if isinstance(value, str):
        return bool(value.strip())
    if isinstance(value, list):
        return any(_truthy(item) for item in value)
    return bool(value)


def _suggest_actions(
    intent: str,
    overrides: dict[str, Any],
    missing_inputs: list[dict[str, str]],
) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    if overrides:
        actions.append({
            "action_id": "apply_settings_overrides",
            "label": "应用建议参数",
            "api_endpoint": "",
            "requires_confirmation": False,
        })
    if missing_inputs:
        actions.append({
            "action_id": "complete_required_inputs",
            "label": "补齐风格包、素材和输出目录",
            "api_endpoint": "",
            "requires_confirmation": True,
        })
        return actions

    if intent == "run_cut":
        actions.extend([
            {
                "action_id": "generate_edit_brief",
                "label": "先生成剪辑标准",
                "api_endpoint": "/api/edit-brief",
                "requires_confirmation": False,
            },
            {
                "action_id": "run_cut",
                "label": "确认后开始剪辑",
                "api_endpoint": "/api/cut",
                "requires_confirmation": True,
            },
        ])
    elif intent == "re_edit":
        actions.append({
            "action_id": "open_version_center",
            "label": "到结果页选择版本复剪",
            "api_endpoint": "/api/versions/re-edit",
            "requires_confirmation": True,
        })
    elif intent == "timeline":
        actions.append({
            "action_id": "generate_timeline",
            "label": "生成时间线预览",
            "api_endpoint": "/api/timeline",
            "requires_confirmation": False,
        })
    elif intent == "filmgen":
        actions.append({
            "action_id": "filmgen_handoff",
            "label": "生成 FilmGen 交接文件",
            "api_endpoint": "/api/cut",
            "requires_confirmation": True,
        })
    elif intent in {"bgm", "voice", "material"}:
        actions.append({
            "action_id": "generate_edit_brief",
            "label": "刷新剪辑标准并检查适配器",
            "api_endpoint": "/api/edit-brief",
            "requires_confirmation": False,
        })
    else:
        actions.append({
            "action_id": "generate_edit_brief",
            "label": "生成剪辑标准",
            "api_endpoint": "/api/edit-brief",
            "requires_confirmation": False,
        })
    return actions


def _assistant_message(
    intent: str,
    overrides: dict[str, Any],
    missing_inputs: list[dict[str, str]],
) -> str:
    if missing_inputs:
        labels = "、".join(item["label"] for item in missing_inputs)
        return f"我先帮你卡住风险：还缺 {labels}。补齐后我就能生成剪辑标准或时间线。"

    intent_messages = {
        "run_cut": "可以开始，但我建议先生成剪辑标准，再确认开剪，避免一刀切错方向。",
        "re_edit": "这是复剪诉求，我会优先保留已有版本，并把修改点转成可追踪的版本变更。",
        "timeline": "我会先把需求转成片段卡片，方便你调整顺序、时长和素材分工。",
        "edit_brief": "我会把自然语言需求整理成导演确认稿，先确认目标，再进入剪辑。",
        "material": "我会优先检查素材分工，确保产品主体、安装过程和环境镜头各司其职。",
        "bgm": "我会把音乐偏好转成 BGM 适配器选择，必要时从本地素材库里推荐一首。",
        "voice": "我会把配音要求转成人声适配器配置，再生成或保留旁白文案。",
        "filmgen": "我会按 FilmGen 交接思路组织字幕或导出 handoff，方便外部生成中枢接力。",
        "clarify": "我理解到的是一个剪辑方向，我可以先生成剪辑标准，也可以先做时间线预览。",
    }
    message = intent_messages.get(intent, intent_messages["clarify"])
    if overrides:
        message += " 我还识别到了一组可直接应用的参数建议。"
    return message


def _deep_set(target: dict[str, Any], section: str, key: str, value: Any) -> None:
    target.setdefault(section, {})[key] = value


def _has_any(text: str, keywords: tuple[str, ...]) -> bool:
    return any(keyword.casefold() in text for keyword in keywords)


def _llm_requested(context: dict[str, Any]) -> bool:
    mode = str(context.get("director_mode") or context.get("mode") or "").strip().casefold()
    return mode in {"llm", "hybrid", "llm_hybrid"} or context.get("use_llm_director") is True


def _load_project_memory(context: dict[str, Any]) -> str:
    if context.get("use_memory") is False:
        return ""
    try:
        from smart_video_cut.local_memory import build_memory_context

        return build_memory_context(limit=8)
    except Exception:
        return ""


def _call_configured_director_llm(
    *,
    message: str,
    history: list[dict[str, Any]],
    context: dict[str, Any],
    base_result: dict[str, Any],
    memory_context: str,
) -> dict[str, Any]:
    try:
        from smart_video_cut.local_config import load_llm_config

        config = load_llm_config(masked=False)
    except Exception as exc:
        return _llm_error("llm_config_unavailable", detail=str(exc)[-500:])

    provider = str(config.get("provider") or "openai_compatible")
    base_url = str(config.get("base_url") or "").rstrip("/")
    model = str(config.get("model") or "").strip()
    api_key = str(config.get("api_key") or "").strip()
    timeout = int(config.get("timeout_seconds") or 20)
    if not base_url:
        return _llm_error("missing_base_url")
    if not model:
        return _llm_error("missing_model")
    if provider != "local_ollama" and not api_key:
        return _llm_error("missing_api_key")

    payload = {
        "model": model,
        "messages": _director_llm_messages(
            message=message,
            history=history,
            context=context,
            base_result=base_result,
            memory_context=memory_context,
        ),
        "temperature": float(config.get("temperature") if config.get("temperature") is not None else 0.2),
        "max_tokens": 500,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(
        f"{base_url}/chat/completions",
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=max(5, timeout)) as response:
            parsed = json.loads(response.read().decode("utf-8", errors="replace"))
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        return _llm_error("http_error", status_code=exc.code, detail=detail)
    except Exception as exc:  # pragma: no cover - depends on user LLM runtime
        return _llm_error(exc.__class__.__name__, detail=str(exc)[-1000:])

    content = (
        parsed.get("choices", [{}])[0]
        .get("message", {})
        .get("content", "")
    )
    return {
        "schema": DIRECTOR_LLM_SCHEMA,
        "ok": bool(str(content).strip()),
        "reason": "llm_response" if str(content).strip() else "empty_llm_response",
        "provider": provider,
        "model": model,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "assistant_message": _clean_llm_message(content),
    }


def _director_llm_messages(
    *,
    message: str,
    history: list[dict[str, Any]],
    context: dict[str, Any],
    base_result: dict[str, Any],
    memory_context: str,
) -> list[dict[str, str]]:
    system = (
        "你是智能剪辑软件的总导演 Agent。请用简洁中文回复用户，"
        "说明下一步动作、风险和需要补齐的信息。不要承诺已经执行渲染；"
        "必须尊重 base_result 中的 missing_inputs、suggested_actions 和 settings_overrides。"
    )
    recent_history = [
        {
            "role": "assistant" if item.get("role") == "assistant" else "user",
            "content": str(item.get("content") or "")[:1000],
        }
        for item in history[-8:]
        if isinstance(item, dict) and str(item.get("content") or "").strip()
    ]
    prompt = {
        "user_message": message,
        "base_result": {
            "intent": base_result.get("intent"),
            "assistant_message": base_result.get("assistant_message"),
            "suggested_actions": base_result.get("suggested_actions"),
            "settings_overrides": base_result.get("settings_overrides"),
            "missing_inputs": base_result.get("missing_inputs"),
        },
        "project_context": _public_context(context),
        "local_memory": memory_context,
    }
    return [
        {"role": "system", "content": system},
        *recent_history,
        {"role": "user", "content": json.dumps(prompt, ensure_ascii=False, indent=2)},
    ]


def _public_context(context: dict[str, Any]) -> dict[str, Any]:
    allowed = {
        "style_package",
        "input_video",
        "input_videos",
        "output_dir",
        "user_request",
        "settings_overrides",
        "has_timeline_override",
    }
    return {key: context.get(key) for key in allowed if key in context}


def _clean_llm_message(value: Any) -> str:
    text = " ".join(str(value or "").split())
    return text[:1200]


def _llm_error(reason: str, **extra: Any) -> dict[str, Any]:
    return {
        "schema": DIRECTOR_LLM_SCHEMA,
        "ok": False,
        "reason": reason,
        **extra,
    }
