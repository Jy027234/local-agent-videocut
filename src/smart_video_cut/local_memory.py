from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from uuid import uuid4


ROOT_DIR = Path(__file__).resolve().parents[2]
MEMORY_DIR = ROOT_DIR / "workspace" / "memory"
MEMORY_PATH = MEMORY_DIR / "agent_skill_memory.json"
MEMORY_SCHEMA = "smart_video_cut.local.agent_skill_memory.v0"

MEMORY_TYPES = {
    "editing_preference": "剪辑偏好",
    "brand_rule": "品牌规范",
    "subtitle_rule": "字幕规则",
    "voice_rule": "配音规则",
    "style_rule": "样板风格",
    "negative_preference": "不要这样做",
    "task_feedback": "任务反馈",
}


def _now() -> int:
    return int(time.time())


def _default_store() -> dict[str, Any]:
    return {
        "schema": MEMORY_SCHEMA,
        "updated_at": None,
        "entries": [],
    }


def load_memory_store() -> dict[str, Any]:
    if not MEMORY_PATH.exists():
        return _default_store()
    payload = json.loads(MEMORY_PATH.read_text(encoding="utf-8"))
    store = _default_store()
    store.update(payload if isinstance(payload, dict) else {})
    if not isinstance(store.get("entries"), list):
        store["entries"] = []
    return store


def save_memory_store(store: dict[str, Any]) -> dict[str, Any]:
    store["schema"] = MEMORY_SCHEMA
    store["updated_at"] = _now()
    MEMORY_PATH.parent.mkdir(parents=True, exist_ok=True)
    MEMORY_PATH.write_text(json.dumps(store, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return store


def add_memory_entry(
    *,
    memory_type: str,
    title: str,
    content: str,
    tags: list[str] | None = None,
    source: str = "manual",
    importance: int = 3,
    enabled: bool = True,
) -> dict[str, Any]:
    normalized_type = memory_type if memory_type in MEMORY_TYPES else "editing_preference"
    cleaned_title = " ".join(str(title or "").split())[:120] or MEMORY_TYPES[normalized_type]
    cleaned_content = str(content or "").strip()
    if not cleaned_content:
        raise ValueError("memory content is required")
    now = _now()
    entry = {
        "id": f"mem_{uuid4().hex[:12]}",
        "type": normalized_type,
        "type_label": MEMORY_TYPES[normalized_type],
        "title": cleaned_title,
        "content": cleaned_content[:2000],
        "tags": _clean_tags(tags or []),
        "source": " ".join(str(source or "manual").split())[:80],
        "importance": max(1, min(5, int(importance or 3))),
        "enabled": bool(enabled),
        "created_at": now,
        "updated_at": now,
    }
    store = load_memory_store()
    store["entries"].append(entry)
    save_memory_store(store)
    return {"ok": True, "entry": entry, "store": memory_summary()}


def add_task_feedback_memory(
    *,
    project_id: str,
    output_dir: str,
    feedback: str,
    rating: int = 3,
) -> dict[str, Any]:
    title = f"任务反馈：{project_id or 'local_project'}"
    content = (
        f"用户对输出目录 {output_dir or '未填写'} 的剪辑反馈：{feedback.strip()}\n"
        f"满意度评分：{max(1, min(5, int(rating or 3)))} / 5。"
    )
    return add_memory_entry(
        memory_type="task_feedback",
        title=title,
        content=content,
        tags=["task_feedback", str(project_id or "local_project")],
        source="user_feedback",
        importance=max(1, min(5, int(rating or 3))),
        enabled=True,
    )


def memory_summary() -> dict[str, Any]:
    store = load_memory_store()
    entries = [_normalize_entry(entry) for entry in store["entries"] if isinstance(entry, dict)]
    enabled = [entry for entry in entries if entry.get("enabled") is True]
    return {
        "schema": store["schema"],
        "path": str(MEMORY_PATH),
        "updated_at": store.get("updated_at"),
        "entry_count": len(entries),
        "enabled_count": len(enabled),
        "entries": entries,
        "context_preview": build_memory_context(),
    }


def build_memory_context(*, limit: int = 12) -> str:
    store = load_memory_store()
    entries = [_normalize_entry(entry) for entry in store["entries"] if isinstance(entry, dict)]
    enabled = [entry for entry in entries if entry.get("enabled") is True and entry.get("content")]
    if not enabled:
        return ""
    selected = sorted(
        enabled,
        key=lambda item: (int(item.get("importance") or 3), int(item.get("updated_at") or 0)),
        reverse=True,
    )[:limit]
    lines = [
        "本地长期记忆（用于帮助总导演 Agent 和剪辑 Skill 保持用户偏好一致）：",
    ]
    for index, entry in enumerate(selected, start=1):
        lines.append(
            f"{index}. [{entry['type_label']}/重要度{entry['importance']}] "
            f"{entry['title']}：{entry['content']}"
        )
    return "\n".join(lines)


def apply_memory_to_user_request(user_request: str, *, use_memory: bool = True) -> tuple[str, str]:
    context = build_memory_context() if use_memory else ""
    if not context:
        return user_request, ""
    return (
        f"{user_request}\n\n"
        f"{context}\n"
        "请在不违背用户本次明确要求的前提下优先使用这些本地记忆；"
        "如果本次要求与记忆冲突，以本次要求为准。",
        context,
    )


def _normalize_entry(entry: dict[str, Any]) -> dict[str, Any]:
    memory_type = str(entry.get("type") or "editing_preference")
    if memory_type not in MEMORY_TYPES:
        memory_type = "editing_preference"
    return {
        "id": str(entry.get("id") or ""),
        "type": memory_type,
        "type_label": MEMORY_TYPES[memory_type],
        "title": str(entry.get("title") or MEMORY_TYPES[memory_type]),
        "content": str(entry.get("content") or ""),
        "tags": _clean_tags(entry.get("tags") if isinstance(entry.get("tags"), list) else []),
        "source": str(entry.get("source") or "manual"),
        "importance": max(1, min(5, int(entry.get("importance") or 3))),
        "enabled": entry.get("enabled") is not False,
        "created_at": int(entry.get("created_at") or 0),
        "updated_at": int(entry.get("updated_at") or entry.get("created_at") or 0),
    }


def _clean_tags(tags: list[Any]) -> list[str]:
    cleaned: list[str] = []
    for tag in tags:
        rendered = " ".join(str(tag).replace("，", ",").split()).strip(" ,")
        if rendered and rendered not in cleaned:
            cleaned.append(rendered[:40])
    return cleaned[:12]
