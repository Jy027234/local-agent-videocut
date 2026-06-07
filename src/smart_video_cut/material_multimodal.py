from __future__ import annotations

import base64
import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Callable, Mapping

from smart_video_cut.local_config import load_llm_config


REVIEW_SCHEMA = "smart_video_cut.local.material_multimodal_review.v0"
ALLOWED_ROLES = {
    "opening_hero",
    "product_body_and_detail",
    "site_context",
    "alternate_cutaway",
}

HttpPoster = Callable[[str, dict[str, str], dict[str, Any], int], dict[str, Any]]


def review_material_roles_with_multimodal(
    *,
    paths: list[Path],
    visual_profiles: list[Mapping[str, Any]],
    config: Mapping[str, Any] | None = None,
    http_post: HttpPoster | None = None,
) -> dict[str, Any]:
    llm_config = dict(config or load_llm_config(masked=False))
    preflight = _preflight(llm_config, visual_profiles)
    if not preflight["ok"]:
        return {
            "schema": REVIEW_SCHEMA,
            "ok": False,
            "status": "skipped",
            "skipped_reason": preflight["reason"],
            "provider": llm_config.get("provider"),
            "model": llm_config.get("model"),
            "allow_media_upload_to_llm": bool(llm_config.get("allow_media_upload_to_llm")),
        }

    base_url = str(llm_config.get("base_url") or "").rstrip("/")
    url = f"{base_url}/chat/completions"
    timeout = int(llm_config.get("timeout_seconds") or 20)
    headers = {"Content-Type": "application/json"}
    api_key = str(llm_config.get("api_key") or "").strip()
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    body = {
        "model": str(llm_config.get("model") or "").strip(),
        "messages": _messages(paths, visual_profiles),
        "temperature": float(llm_config.get("temperature") if llm_config.get("temperature") is not None else 0.2),
        "max_tokens": 900,
    }
    started = time.perf_counter()
    try:
        response = (http_post or _post_json)(url, headers, body, timeout)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        return _failed(llm_config, "http_error", detail=detail, status_code=exc.code)
    except Exception as exc:  # pragma: no cover - network and provider dependent
        return _failed(llm_config, exc.__class__.__name__, detail=str(exc))

    content = _message_content(response)
    parsed = _parse_json_object(content)
    if not isinstance(parsed, Mapping):
        return _failed(llm_config, "invalid_json_response", detail=content[:1000])
    assignments = _clean_assignments(parsed.get("assignments") or parsed.get("materials"), len(paths))
    if not assignments:
        return _failed(llm_config, "missing_valid_assignments", detail=content[:1000])
    return {
        "schema": REVIEW_SCHEMA,
        "ok": True,
        "status": "completed",
        "provider": llm_config.get("provider"),
        "model": llm_config.get("model"),
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "assignments": assignments,
        "response_summary": str(parsed.get("summary") or "").strip()[:500],
    }


def _preflight(config: Mapping[str, Any], visual_profiles: list[Mapping[str, Any]]) -> dict[str, Any]:
    if config.get("allow_media_upload_to_llm") is not True:
        return {"ok": False, "reason": "media_upload_not_allowed"}
    capability = str(config.get("model_capability") or "").casefold()
    if "multimodal" not in capability and "vision" not in capability:
        return {"ok": False, "reason": "model_capability_not_multimodal"}
    if not str(config.get("base_url") or "").strip():
        return {"ok": False, "reason": "missing_base_url"}
    if not str(config.get("model") or "").strip():
        return {"ok": False, "reason": "missing_model"}
    if str(config.get("provider") or "") != "local_ollama" and not str(config.get("api_key") or "").strip():
        return {"ok": False, "reason": "missing_api_key"}
    if not any(_thumbnail_paths(profile) for profile in visual_profiles):
        return {"ok": False, "reason": "missing_thumbnail_refs"}
    return {"ok": True}


def _messages(paths: list[Path], visual_profiles: list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    content: list[dict[str, Any]] = [
        {
            "type": "text",
            "text": (
                "你是视频剪辑素材规划复核助手。请根据素材缩略图判断每个原视频更适合的剪辑角色。"
                "只返回 JSON，不要 Markdown。角色只能从 opening_hero、product_body_and_detail、"
                "site_context、alternate_cutaway 中选择。尽量让 opening_hero、"
                "product_body_and_detail、site_context 各有一个最合适素材。"
                "返回格式：{\"assignments\":[{\"index\":0,\"role\":\"opening_hero\","
                "\"confidence\":0.8,\"reason\":\"简短中文原因\"}],\"summary\":\"简短总结\"}。"
            ),
        }
    ]
    for index, path in enumerate(paths):
        profile = visual_profiles[index] if index < len(visual_profiles) else {}
        content.append(
            {
                "type": "text",
                "text": (
                    f"素材 {index}: {path.name}\n"
                    f"本地视觉评分: {json.dumps(profile.get('scores') or {}, ensure_ascii=False)}\n"
                    f"本地指标: {json.dumps(profile.get('metrics') or {}, ensure_ascii=False)}"
                ),
            }
        )
        for thumbnail_path in _thumbnail_paths(profile)[:2]:
            data_url = _image_data_url(thumbnail_path)
            if data_url:
                content.append({"type": "image_url", "image_url": {"url": data_url}})
    return [
        {"role": "system", "content": "你只输出可解析 JSON。"},
        {"role": "user", "content": content},
    ]


def _thumbnail_paths(profile: Mapping[str, Any]) -> list[Path]:
    refs = profile.get("thumbnail_refs")
    if not isinstance(refs, list):
        return []
    paths = []
    for item in refs:
        if not isinstance(item, Mapping):
            continue
        path = Path(str(item.get("thumbnail_path") or ""))
        if path.is_file():
            paths.append(path)
    return paths


def _image_data_url(path: Path) -> str | None:
    try:
        data = path.read_bytes()
    except OSError:
        return None
    if not data:
        return None
    encoded = base64.b64encode(data).decode("ascii")
    return f"data:image/jpeg;base64,{encoded}"


def _post_json(url: str, headers: dict[str, str], body: dict[str, Any], timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
    return json.loads(raw)


def _message_content(response: Mapping[str, Any]) -> str:
    choice = (response.get("choices") or [{}])[0]
    message = choice.get("message") if isinstance(choice, Mapping) else {}
    content = message.get("content") if isinstance(message, Mapping) else ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, Mapping) and isinstance(item.get("text"), str):
                parts.append(item["text"])
        return "\n".join(parts)
    return ""


def _parse_json_object(content: str) -> Any:
    text = content.strip()
    if text.startswith("```"):
        text = text.strip("`")
        if text.startswith("json"):
            text = text[4:].strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start >= 0 and end > start:
            try:
                return json.loads(text[start : end + 1])
            except json.JSONDecodeError:
                return None
    return None


def _clean_assignments(value: Any, material_count: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    cleaned = []
    for item in value:
        if not isinstance(item, Mapping):
            continue
        try:
            index = int(item.get("index"))
        except (TypeError, ValueError):
            continue
        if index < 0 or index >= material_count:
            continue
        role = _normalize_role(str(item.get("role") or ""))
        if role not in ALLOWED_ROLES:
            continue
        cleaned.append(
            {
                "index": index,
                "role": role,
                "confidence": _confidence(item.get("confidence")),
                "reason": str(item.get("reason") or "").strip()[:240],
            }
        )
    return cleaned


def _normalize_role(role: str) -> str:
    normalized = role.strip().casefold()
    aliases = {
        "hero": "opening_hero",
        "cover": "opening_hero",
        "opening": "opening_hero",
        "detail": "product_body_and_detail",
        "product_detail": "product_body_and_detail",
        "door_body": "product_body_and_detail",
        "context": "site_context",
        "environment": "site_context",
        "corridor": "site_context",
        "alternate": "alternate_cutaway",
        "cutaway": "alternate_cutaway",
    }
    return aliases.get(normalized, normalized)


def _confidence(value: Any) -> float:
    try:
        return round(max(0.0, min(1.0, float(value))), 3)
    except (TypeError, ValueError):
        return 0.5


def _failed(
    config: Mapping[str, Any],
    reason: str,
    *,
    detail: str = "",
    status_code: int | None = None,
) -> dict[str, Any]:
    payload = {
        "schema": REVIEW_SCHEMA,
        "ok": False,
        "status": "failed",
        "failure_reason": reason,
        "provider": config.get("provider"),
        "model": config.get("model"),
        "detail": detail,
    }
    if status_code is not None:
        payload["status_code"] = status_code
    return payload
