from __future__ import annotations

from dataclasses import dataclass
import base64
import json
import mimetypes
import os
import re
import time
from pathlib import Path
from typing import Any, Mapping
import urllib.error
import urllib.request
from uuid import uuid4

from .models import MODEL_PIPELINE_SLOTS, utc_now


MODEL_SMOKE_FAMILIES = ("text", "image", "video")
PIPELINE_SLOT_DEFINITIONS = {str(slot["key"]): slot for slot in MODEL_PIPELINE_SLOTS}

STAGE_MODEL_FAMILY = {
    "script": "text",
    "edit_pack": "text",
    "keyframe": "image",
    "clip": "video",
    "audio": "audio",
}

STAGE_ASSET_TYPE = {
    "script": "script",
    "edit_pack": "manifest",
    "keyframe": "keyframe",
    "clip": "video",
    "audio": "audio",
}

SMOKE_STAGE_BY_FAMILY = {
    "text": "script",
    "image": "keyframe",
    "video": "clip",
}


class ProviderAdapterError(RuntimeError):
    pass


class ProviderAdapterPending(ProviderAdapterError):
    def __init__(
        self,
        message: str,
        *,
        provider_task_id: str = "",
        task_status: str = "",
        response_ref: str = "",
    ) -> None:
        super().__init__(message)
        self.provider_task_id = provider_task_id
        self.task_status = task_status
        self.response_ref = response_ref


@dataclass(frozen=True)
class ProviderRunResult:
    output_file: Path
    asset_type: str
    title: str
    actual_cost: float
    request_ref: str
    response_ref: str
    metadata: dict[str, Any]


class ProviderAdapter:
    adapter_id = "base"

    def run_task(self, *, store: Any, task: Mapping[str, Any], provider: Mapping[str, Any]) -> ProviderRunResult:
        raise NotImplementedError


class MockLocalAdapter(ProviderAdapter):
    adapter_id = "mock-local"

    def run_task(self, *, store: Any, task: Mapping[str, Any], provider: Mapping[str, Any]) -> ProviderRunResult:
        family = model_family_for_stage(str(task.get("stage") or "clip"))
        output_dir = Path(store.data_dir) / "assets" / str(task.get("project_id") or "_provider_smoke_test")
        output_dir.mkdir(parents=True, exist_ok=True)
        output_file = output_dir / f"{task.get('id')}-{family}.json"
        payload = {
            "schema": "aifilm-studio.provider-output.mock.v1",
            "task_id": task.get("id"),
            "project_id": task.get("project_id"),
            "shot_id": task.get("shot_id"),
            "model_slot": task.get("model_slot"),
            "model_role": task.get("model_role"),
            "stage": task.get("stage"),
            "model_family": family,
            "provider": provider.get("id") or task.get("provider_id"),
            "model": task.get("model") or default_model_for_family(provider, family),
            "prompt": task.get("prompt") or "",
            "negative_prompt": task.get("negative_prompt") or "",
            "reference_images": list(task.get("reference_images") or []),
            "reference_image": task.get("image_url") or task.get("reference_image_url") or task.get("reference_image") or "",
            "generated_at": utc_now(),
            "note": "Mock output for local adapter validation. Replace this provider with a real adapter for cloud generation.",
        }
        output_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        actual_cost = float(task.get("cost_estimate") or 0)
        return ProviderRunResult(
            output_file=output_file,
            asset_type=asset_type_for_stage(str(task.get("stage") or "clip")),
            title=f"{family} output",
            actual_cost=actual_cost,
            request_ref=str(task.get("prompt") or ""),
            response_ref=str(output_file),
            metadata={
                "adapter": self.adapter_id,
                "mock": True,
                "model_slot": task.get("model_slot") or "",
                "model_role": task.get("model_role") or "",
                "model_family": family,
                "artifact_kind": "image_candidate" if family == "image" else "",
                "review_status": "needs_review" if family == "image" else "",
                "provider_kind": provider.get("kind") or "mock",
            },
        )


class OpenAICompatTextAdapter(ProviderAdapter):
    adapter_id = "openai-compatible-text"

    def run_task(self, *, store: Any, task: Mapping[str, Any], provider: Mapping[str, Any]) -> ProviderRunResult:
        model = str(task.get("model") or default_model_for_family(provider, "text")).strip()
        if not model:
            raise ProviderAdapterError("No text model configured.")
        url = _provider_endpoint(provider, "/chat/completions")
        headers = _auth_headers(provider)
        body = {
            "model": model,
            "messages": task.get("messages") if isinstance(task.get("messages"), list) else _text_messages(task),
            "temperature": float(task.get("temperature") if task.get("temperature") is not None else 0.4),
            "max_tokens": int(task.get("max_tokens") or 1800),
        }
        if isinstance(task.get("response_format"), Mapping):
            body["response_format"] = dict(task["response_format"])  # type: ignore[index]
        started = time.perf_counter()
        response = _post_json(url, headers, body, timeout=int(task.get("timeout_seconds") or 60))
        content = _message_content(response)
        output_file = _write_provider_payload(
            store,
            task,
            "text",
            {
                "schema": "aifilm-studio.provider-output.openai-text.v1",
                "provider": provider.get("id") or task.get("provider_id"),
                "model": model,
                "content": content,
                "raw_response": response,
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
                "generated_at": utc_now(),
            },
        )
        return ProviderRunResult(
            output_file=output_file,
            asset_type=asset_type_for_stage(str(task.get("stage") or "script")),
            title="text output",
            actual_cost=float(task.get("cost_estimate") or 0),
            request_ref=str(task.get("prompt") or ""),
            response_ref=str(output_file),
            metadata={
                "adapter": self.adapter_id,
                "model_family": "text",
                "provider_kind": provider.get("kind") or "",
                "elapsed_ms": int((time.perf_counter() - started) * 1000),
            },
        )


class OpenAICompatImageAdapter(ProviderAdapter):
    adapter_id = "openai-compatible-image"

    def run_task(self, *, store: Any, task: Mapping[str, Any], provider: Mapping[str, Any]) -> ProviderRunResult:
        model = str(task.get("model") or default_model_for_family(provider, "image")).strip()
        if not model:
            raise ProviderAdapterError("No image model configured.")
        prompt = str(task.get("prompt") or "").strip()
        if not prompt:
            raise ProviderAdapterError("Image prompt is empty.")
        response = _post_json(
            _provider_endpoint(provider, "/images/generations"),
            _auth_headers(provider),
            _image_generation_body(task, model=model, prompt=prompt, provider=provider),
            timeout=int(task.get("timeout_seconds") or 120),
        )
        output_file, response_file = _materialize_media_response(store, task, response, family="image")
        return ProviderRunResult(
            output_file=output_file,
            asset_type="keyframe",
            title="image output",
            actual_cost=float(task.get("cost_estimate") or 0),
            request_ref=prompt,
            response_ref=str(response_file),
            metadata={
                "adapter": self.adapter_id,
                "model_family": "image",
                "artifact_kind": "image_candidate",
                "review_status": "needs_review",
                "model_slot": task.get("model_slot") or "text_to_image_model",
                "model_role": task.get("model_role") or "text_to_image",
                "provider_kind": provider.get("kind") or "",
                "response_file": str(response_file),
                "reference_images": list(task.get("reference_images") or []),
            },
        )


class OpenAICompatVideoAdapter(ProviderAdapter):
    adapter_id = "openai-compatible-video"

    def run_task(self, *, store: Any, task: Mapping[str, Any], provider: Mapping[str, Any]) -> ProviderRunResult:
        model = str(task.get("model") or default_model_for_family(provider, "video")).strip()
        if not model:
            raise ProviderAdapterError("No video model configured.")
        prompt = str(task.get("prompt") or "").strip()
        if not prompt:
            raise ProviderAdapterError("Video prompt is empty.")
        image_ref = _image_reference(task.get("image_url") or task.get("reference_image_url") or task.get("reference_image"))
        body = _video_generation_body(provider, model=model, prompt=prompt, image_ref=image_ref, duration=int(task.get("duration") or 5))
        response = _post_json(
            _provider_endpoint(provider, "/videos/generations"),
            _auth_headers(provider),
            body,
            timeout=int(task.get("timeout_seconds") or 180),
        )
        output_file, response_file = _materialize_media_response(store, task, response, family="video")
        if output_file == response_file or not _is_video_file(output_file):
            polled_response, polled_file = _poll_video_task(store, task, provider, response, timeout_seconds=int(task.get("poll_timeout_seconds") or 150))
            if polled_response is not None:
                response = polled_response
                output_file, response_file = _materialize_media_response(store, task, polled_response, family="video")
            if polled_file:
                response_file = polled_file
        if output_file == response_file or not _is_video_file(output_file):
            task_info = _video_task_info(response)
            status = task_info.get("status") or ""
            provider_task_id = task_info.get("task_id") or ""
            if status in {"PENDING", "RUNNING", "PROCESSING", "QUEUED", "running", "pending", "processing", "queued"}:
                raise ProviderAdapterPending(
                    f"视频任务已提交到供应商，状态 {status}，任务 ID：{provider_task_id or 'unknown'}。尚未返回可播放视频文件。",
                    provider_task_id=provider_task_id,
                    task_status=status,
                    response_ref=str(response_file),
                )
            raise ProviderAdapterError(_video_failure_message(response) or "Video provider did not return a playable video file.")
        return ProviderRunResult(
            output_file=output_file,
            asset_type="video",
            title="video output",
            actual_cost=float(task.get("cost_estimate") or 0),
            request_ref=prompt,
            response_ref=str(response_file),
            metadata={
                "adapter": self.adapter_id,
                "model_family": "video",
                "provider_kind": provider.get("kind") or "",
                "response_file": str(response_file),
                "reference_image": str(task.get("image_url") or task.get("reference_image_url") or task.get("reference_image") or ""),
            },
        )


class AdapterNotConfigured(ProviderAdapter):
    adapter_id = "not-configured"

    def run_task(self, *, store: Any, task: Mapping[str, Any], provider: Mapping[str, Any]) -> ProviderRunResult:
        raise ProviderAdapterError(
            f"Provider {provider.get('id') or task.get('provider_id')} has no runnable local adapter yet."
        )


def adapter_for_provider(provider: Mapping[str, Any]) -> ProviderAdapter:
    provider_id = str(provider.get("id") or "")
    kind = str(provider.get("kind") or "")
    if provider_id == "mock-local" or kind == "mock":
        return MockLocalAdapter()
    if kind in {"deepseek", "openai-compatible-text"}:
        return OpenAICompatTextAdapter()
    if kind in {"openai-compatible-image", "model-router-image"}:
        return OpenAICompatImageAdapter()
    if kind in {"openai-compatible-video", "model-router-video", "openai-compatible-i2v"}:
        return OpenAICompatVideoAdapter()
    return AdapterNotConfigured()


def run_provider_task(*, store: Any, task: Mapping[str, Any], provider: Mapping[str, Any]) -> ProviderRunResult:
    return adapter_for_provider(provider).run_task(store=store, task=task, provider=provider)


def smoke_test_provider_models(*, store: Any, provider: Mapping[str, Any]) -> dict[str, Any]:
    adapter = adapter_for_provider(provider)
    root = Path(store.data_dir) / "provider_smoke_tests" / str(provider.get("id") or "provider") / utc_now().replace(":", "")
    results = []
    for family in MODEL_SMOKE_FAMILIES:
        model = default_model_for_family(provider, family)
        if not model:
            results.append(
                {
                    "family": family,
                    "status": "skipped",
                    "reason": "no_model_configured",
                    "model": "",
                    "output_file": "",
                }
            )
            continue
        task = {
            "id": f"smoke-{family}-{uuid4()}",
            "project_id": "_provider_smoke_test",
            "shot_id": None,
            "stage": SMOKE_STAGE_BY_FAMILY[family],
            "provider_id": provider.get("id") or "",
            "model": model,
            "prompt": f"FilmGen local smoke test for {family} model family.",
            "negative_prompt": "",
            "cost_estimate": 0,
        }
        try:
            task_result = adapter.run_task(store=_SmokeStore(store, root), task=task, provider=provider)
        except Exception as exc:
            results.append(
                {
                    "family": family,
                    "status": "failed",
                    "reason": str(exc),
                    "model": model,
                    "output_file": "",
                }
            )
            continue
        results.append(
            {
                "family": family,
                "status": "succeeded",
                "reason": "",
                "model": model,
                "output_file": str(task_result.output_file),
                "asset_type": task_result.asset_type,
                "adapter": task_result.metadata.get("adapter") or adapter.adapter_id,
            }
        )
    return {
        "schema": "aifilm-studio.provider-smoke-test.v1",
        "provider_id": provider.get("id") or "",
        "provider_name": provider.get("name") or provider.get("id") or "",
        "adapter": adapter.adapter_id,
        "ok": all(result["status"] == "succeeded" for result in results),
        "results": results,
    }


def probe_model_pipeline(*, store: Any, slots: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    selected_slots = slots if slots is not None else store.get_model_pipeline_config().get("slots", [])
    root = Path(store.data_dir) / "model_pipeline_probes" / utc_now().replace(":", "")
    results = []
    for slot in _normalized_slots(selected_slots):
        if not slot.get("enabled", True):
            results.append(_slot_result(slot, status="skipped", reason="disabled"))
            continue
        provider_id = str(slot.get("provider_id") or "").strip()
        model = str(slot.get("model") or "").strip()
        if not provider_id:
            results.append(_slot_result(slot, status="skipped", reason="no_provider_configured"))
            continue
        if not model:
            results.append(_slot_result(slot, status="skipped", reason="no_model_configured"))
            continue
        try:
            provider = provider_with_slot_settings(store.get_provider(provider_id), slot)
            adapter = adapter_for_provider(provider)
            task = {
                "id": f"probe-{slot['slot_key']}-{uuid4()}",
                "project_id": "_model_pipeline_probe",
                "shot_id": None,
                "stage": slot["stage"],
                "provider_id": provider_id,
                "model": model,
                "model_slot": slot["slot_key"],
                "model_role": slot["role"],
                "prompt": _probe_prompt(slot),
                "negative_prompt": "",
                "cost_estimate": 0,
            }
            task_result = adapter.run_task(store=_SmokeStore(store, root), task=task, provider=provider)
        except Exception as exc:
            results.append(_slot_result(slot, status="failed", reason=str(exc), provider_id=provider_id, model=model))
            continue
        results.append(
            _slot_result(
                slot,
                status="succeeded",
                provider_id=provider_id,
                model=model,
                output_file=str(task_result.output_file),
                asset_type=task_result.asset_type,
                adapter=str(task_result.metadata.get("adapter") or adapter.adapter_id),
            )
        )
    return {
        "schema": "aifilm-studio.model-pipeline-probe.v1",
        "ok": all(result["status"] == "succeeded" for result in results),
        "results": results,
    }


def model_family_for_stage(stage: str) -> str:
    return STAGE_MODEL_FAMILY.get(stage, "text")


def asset_type_for_stage(stage: str) -> str:
    return STAGE_ASSET_TYPE.get(stage, "manifest")


def default_model_for_family(provider: Mapping[str, Any], family: str) -> str:
    catalog = provider.get("model_catalog") or {}
    if not isinstance(catalog, Mapping):
        return ""
    models = catalog.get(family) or []
    if isinstance(models, str):
        return models
    if isinstance(models, list) and models:
        first = models[0]
        if isinstance(first, Mapping):
            return str(first.get("model") or first.get("id") or "")
        return str(first or "")
    return ""


def _normalized_slots(slots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key = {str(slot.get("slot_key") or slot.get("key") or ""): slot for slot in slots if isinstance(slot, dict)}
    normalized = []
    for definition in MODEL_PIPELINE_SLOTS:
        slot_key = str(definition["key"])
        incoming = dict(by_key.get(slot_key) or {})
        normalized.append(
            {
                "slot_key": slot_key,
                "label": str(definition["label"]),
                "role": str(definition["role"]),
                "stage": str(definition["stage"]),
                "provider_id": str(incoming.get("provider_id") or definition["default_provider_id"]),
                "model": str(incoming.get("model") or definition["default_model"]),
                "enabled": bool(incoming.get("enabled", True)),
                "settings": incoming.get("settings") if isinstance(incoming.get("settings"), Mapping) else {},
            }
        )
    return normalized


def provider_with_slot_settings(provider: Mapping[str, Any], slot: Mapping[str, Any] | None) -> dict[str, Any]:
    merged = dict(provider)
    settings = slot.get("settings") if isinstance(slot, Mapping) else {}
    if not isinstance(settings, Mapping):
        return merged
    base_url = str(settings.get("base_url") or "").strip()
    api_key_env = str(settings.get("api_key_env") or "").strip()
    api_key_file = str(settings.get("api_key_file") or "").strip()
    if base_url:
        merged["base_url"] = base_url
    if api_key_env:
        merged["api_key_env"] = api_key_env
    pricing = dict(merged.get("pricing") or {})
    if api_key_file:
        pricing["api_key_file"] = api_key_file
    merged["pricing"] = pricing
    return merged


def _slot_result(
    slot: Mapping[str, Any],
    *,
    status: str,
    reason: str = "",
    provider_id: str = "",
    model: str = "",
    output_file: str = "",
    asset_type: str = "",
    adapter: str = "",
) -> dict[str, Any]:
    return {
        "slot_key": slot.get("slot_key") or "",
        "label": slot.get("label") or "",
        "role": slot.get("role") or "",
        "stage": slot.get("stage") or "",
        "status": status,
        "reason": reason,
        "provider_id": provider_id or str(slot.get("provider_id") or ""),
        "model": model or str(slot.get("model") or ""),
        "output_file": output_file,
        "asset_type": asset_type,
        "adapter": adapter,
    }


def _probe_prompt(slot: Mapping[str, Any]) -> str:
    role = str(slot.get("role") or "")
    if role == "planning":
        return "根据一句话创意生成结构化剧本、角色、场景和分镜。"
    if role == "text_to_image":
        return "根据角色卡、场景卡和关键帧提示词生成参考图。"
    if role == "image_to_video":
        return "根据已批准参考图和镜头运动提示词生成视频片段。"
    return "FilmGen model pipeline probe."


def _video_generation_body(
    provider: Mapping[str, Any],
    *,
    model: str,
    prompt: str,
    image_ref: str,
    duration: int,
) -> dict[str, Any]:
    provider_id = str(provider.get("id") or "")
    kind = str(provider.get("kind") or "")
    if "happyhorse" in model.lower() or provider_id == "model-router-video" or kind == "model-router-video":
        if not image_ref:
            raise ProviderAdapterError("HappyHorse image-to-video requires an approved reference image.")
        return {
            "model": model,
            "input": {
                "prompt": prompt,
                "media": [{"type": "first_frame", "url": image_ref}],
            },
            "parameters": {
                "duration": max(3, min(15, int(duration or 5))),
                "resolution": "720P",
                "watermark": False,
            },
        }
    body: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "duration": int(duration or 5),
    }
    if image_ref:
        body["image_url"] = image_ref
    return body


def _provider_endpoint(provider: Mapping[str, Any], path: str) -> str:
    base_url = str(provider.get("base_url") or "").rstrip("/")
    if not base_url:
        raise ProviderAdapterError(f"Provider {provider.get('id') or ''} has no base_url configured.")
    normalized_path = "/" + path.strip("/")
    if base_url.endswith(normalized_path):
        return base_url
    return f"{base_url}{normalized_path}"


def _auth_headers(provider: Mapping[str, Any]) -> dict[str, str]:
    api_key = _api_key(provider)
    if not api_key:
        raise ProviderAdapterError(f"Provider {provider.get('id') or ''} has no API key configured.")
    return {
        "Content-Type": "application/json",
        "Accept": "application/json",
        "Authorization": f"Bearer {api_key}",
    }


def _api_key(provider: Mapping[str, Any]) -> str:
    env_name = str(provider.get("api_key_env") or "").strip()
    if env_name and os.environ.get(env_name):
        return str(os.environ[env_name]).strip()
    pricing = provider.get("pricing") or {}
    key_file = str(pricing.get("api_key_file") or "").strip() if isinstance(pricing, Mapping) else ""
    if key_file:
        return _read_api_key_file(Path(key_file))
    return ""


def _read_api_key_file(path: Path) -> str:
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return ""
    match = re.search(r"sk-[A-Za-z0-9._-]+", text)
    return match.group(0).strip() if match else text.strip()


def _post_json(url: str, headers: dict[str, str], body: dict[str, Any], *, timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(
        url,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise ProviderAdapterError(f"Provider returned HTTP {exc.code}: {detail}") from exc
    except OSError as exc:
        raise ProviderAdapterError(str(exc)) from exc
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderAdapterError(f"Provider returned non-JSON response: {raw[:500]}") from exc
    return data if isinstance(data, dict) else {"data": data}


def _get_json(url: str, headers: dict[str, str], *, timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        raise ProviderAdapterError(f"Provider returned HTTP {exc.code}: {detail}") from exc
    except OSError as exc:
        raise ProviderAdapterError(str(exc)) from exc
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ProviderAdapterError(f"Provider returned non-JSON response: {raw[:500]}") from exc
    return data if isinstance(data, dict) else {"data": data}


def _text_messages(task: Mapping[str, Any]) -> list[dict[str, str]]:
    system = str(task.get("system_prompt") or "你是 FilmGen Studio 的编剧策划助手，只输出用户要求的内容。").strip()
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": str(task.get("prompt") or "").strip()},
    ]


def _image_generation_body(
    task: Mapping[str, Any],
    *,
    model: str,
    prompt: str,
    provider: Mapping[str, Any],
) -> dict[str, Any]:
    n = int(task.get("n") or 1)
    provider_id = str(provider.get("id") or "")
    refs = [_image_reference(item) for item in task.get("reference_images") or []]
    refs = [item for item in refs if item]
    if provider_id == "model-router-image" or model.startswith("qwen/"):
        content = [{"text": prompt}]
        content.extend({"image": ref} for ref in refs)
        return {
            "model": model,
            "input": {
                "messages": [{"role": "user", "content": content}],
            },
            "parameters": {
                "n": n,
                "size": str(task.get("size") or "1664*928"),
            },
        }
    body: dict[str, Any] = {
        "model": model,
        "prompt": prompt,
        "n": n,
        "size": str(task.get("size") or "1024x1024"),
    }
    if refs:
        body["reference_images"] = refs
    return body


def _message_content(response: Mapping[str, Any]) -> str:
    choices = response.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""
    first = choices[0]
    if not isinstance(first, Mapping):
        return ""
    message = first.get("message") or {}
    content = message.get("content") if isinstance(message, Mapping) else ""
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, Mapping):
                parts.append(str(item.get("text") or item.get("content") or ""))
        return "\n".join(part for part in parts if part).strip()
    return str(content or "").strip()


def _write_provider_payload(store: Any, task: Mapping[str, Any], family: str, payload: dict[str, Any]) -> Path:
    output_dir = Path(store.data_dir) / "assets" / str(task.get("project_id") or "_provider_task")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / f"{task.get('id') or uuid4()}-{family}.json"
    output_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_file


def _materialize_media_response(
    store: Any,
    task: Mapping[str, Any],
    response: dict[str, Any],
    *,
    family: str,
) -> tuple[Path, Path]:
    response_file = _write_provider_payload(
        store,
        task,
        family,
        {
            "schema": f"aifilm-studio.provider-output.openai-{family}.v1",
            "response": response,
            "generated_at": utc_now(),
        },
    )
    media = _first_media(response)
    if not media:
        return response_file, response_file
    media_dir = response_file.parent
    if media.get("b64_json"):
        suffix = ".png" if family == "image" else ".mp4"
        media_file = media_dir / f"{task.get('id') or uuid4()}-{family}{suffix}"
        media_file.write_bytes(base64.b64decode(str(media["b64_json"])))
        return media_file, response_file
    url = str(media.get("url") or "").strip()
    if url:
        downloaded = _download_media(url, media_dir / f"{task.get('id') or uuid4()}-{family}")
        if downloaded:
            return downloaded, response_file
    return response_file, response_file


def _poll_video_task(
    store: Any,
    task: Mapping[str, Any],
    provider: Mapping[str, Any],
    response: Mapping[str, Any],
    *,
    timeout_seconds: int,
) -> tuple[dict[str, Any] | None, Path | None]:
    task_info = _video_task_info(response)
    provider_task_id = task_info.get("task_id") or ""
    if not provider_task_id:
        return None, None
    status = task_info.get("status") or ""
    if status not in {"PENDING", "RUNNING", "PROCESSING", "QUEUED", "pending", "running", "processing", "queued"}:
        return dict(response), None
    deadline = time.perf_counter() + max(0, timeout_seconds)
    headers = {key: value for key, value in _auth_headers(provider).items() if key.lower() != "content-type"}
    status_url = _provider_task_endpoint(provider, provider_task_id)
    latest: dict[str, Any] = dict(response)
    latest_file: Path | None = None
    while time.perf_counter() < deadline:
        time.sleep(5)
        latest = _get_json(status_url, headers, timeout=30)
        latest_file = _write_provider_payload(
            store,
            task,
            "video",
            {
                "schema": "aifilm-studio.provider-output.openai-video-status.v1",
                "response": latest,
                "generated_at": utc_now(),
            },
        )
        latest_status = _video_task_info(latest).get("status") or ""
        if _first_media(latest) or latest_status in {"SUCCEEDED", "COMPLETED", "succeeded", "completed"}:
            return latest, latest_file
        if latest_status in {"FAILED", "ERROR", "failed", "error"}:
            raise ProviderAdapterError(_video_failure_message(latest) or f"Video task {provider_task_id} failed.")
    raise ProviderAdapterPending(
        f"视频任务已提交到供应商，状态 {(_video_task_info(latest).get('status') or status)}，任务 ID：{provider_task_id}。尚未返回可播放视频文件。",
        provider_task_id=provider_task_id,
        task_status=_video_task_info(latest).get("status") or status,
        response_ref=str(latest_file or ""),
    )


def _provider_task_endpoint(provider: Mapping[str, Any], provider_task_id: str) -> str:
    base_url = str(provider.get("base_url") or "").rstrip("/")
    marker = "/v1/"
    if marker in base_url:
        root = base_url.split(marker, 1)[0]
        return f"{root}/v1/tasks/{provider_task_id}"
    return f"{base_url}/tasks/{provider_task_id}"


def _video_task_info(response: Mapping[str, Any]) -> dict[str, str]:
    output = response.get("output")
    if isinstance(output, Mapping):
        return {
            "task_id": str(output.get("task_id") or output.get("id") or ""),
            "status": str(output.get("task_status") or output.get("status") or ""),
        }
    return {
        "task_id": str(response.get("task_id") or response.get("id") or response.get("request_id") or ""),
        "status": str(response.get("task_status") or response.get("status") or ""),
    }


def _video_failure_message(response: Mapping[str, Any]) -> str:
    output = response.get("output")
    if isinstance(output, Mapping):
        parts = [str(output.get("message") or "").strip(), str(output.get("code") or "").strip()]
        return "；".join(part for part in parts if part)
    parts = [str(response.get("message") or response.get("error") or "").strip(), str(response.get("code") or "").strip()]
    return "；".join(part for part in parts if part)


def _is_video_file(path: Path) -> bool:
    return path.suffix.lower() in {".mp4", ".webm", ".mov", ".m4v"}


def _first_media(response: Mapping[str, Any]) -> dict[str, Any] | None:
    data = response.get("data")
    if isinstance(data, list) and data and isinstance(data[0], Mapping):
        return dict(data[0])
    output = response.get("output")
    if isinstance(output, Mapping):
        media = output.get("media")
        if isinstance(media, list):
            for item in media:
                if isinstance(item, Mapping):
                    url = item.get("url") or item.get("video_url") or item.get("media_url")
                    if url:
                        return {"url": url}
        choices = output.get("choices")
        if isinstance(choices, list):
            for choice in choices:
                if not isinstance(choice, Mapping):
                    continue
                message = choice.get("message")
                if not isinstance(message, Mapping):
                    continue
                content = message.get("content")
                if not isinstance(content, list):
                    continue
                for item in content:
                    if not isinstance(item, Mapping):
                        continue
                    image = item.get("image") or item.get("image_url")
                    video = item.get("video") or item.get("video_url")
                    if image:
                        return {"url": image}
                    if video:
                        return {"url": video}
        for key in ("url", "video_url", "image_url", "media_url", "b64_json"):
            value = output.get(key)
            if value:
                return {"url": value} if key != "b64_json" else {"b64_json": value}
    for key in ("url", "video_url", "image_url", "media_url", "b64_json"):
        value = response.get(key)
        if value:
            return {"url": value} if key != "b64_json" else {"b64_json": value}
    return None


def _download_media(url: str, target_base: Path) -> Path | None:
    try:
        with urllib.request.urlopen(url, timeout=120) as response:
            content_type = response.headers.get("Content-Type", "")
            data = response.read()
    except OSError:
        return None
    suffix = mimetypes.guess_extension(content_type.split(";")[0].strip()) or Path(url).suffix or ".bin"
    target = target_base.with_suffix(suffix)
    target.write_bytes(data)
    return target


def _image_reference(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith(("http://", "https://", "data:")):
        return text
    path = Path(text)
    if not path.is_file():
        return text
    mime_type = mimetypes.guess_type(path.name)[0] or "image/png"
    return f"data:{mime_type};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


class _SmokeStore:
    def __init__(self, store: Any, data_dir: Path) -> None:
        self.db_path = getattr(store, "db_path", None)
        self.data_dir = data_dir
