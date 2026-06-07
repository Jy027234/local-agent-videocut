from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from smart_video_cut.moss_tts import check_moss_tts_status


ROOT_DIR = Path(__file__).resolve().parents[2]
WORKSPACE_DIR = ROOT_DIR / "workspace"
CONFIG_DIR = ROOT_DIR / "workspace" / "config"
OUTPUT_ROOT = WORKSPACE_DIR / "output"
PACKAGES_DIR = ROOT_DIR / "packages"
VOICE_SAMPLES_DIR = WORKSPACE_DIR / "voice_samples"
PROTOCOL_DROPBOX_ROOT = WORKSPACE_DIR / "protocol_dropbox"
LLM_CONFIG_PATH = CONFIG_DIR / "llm_config.json"
VOICE_MODEL_CONFIG_PATH = CONFIG_DIR / "voice_model_config.json"

LLM_CONFIG_SCHEMA = "smart_video_cut.local.llm_config.v0"
VOICE_MODEL_CONFIG_SCHEMA = "smart_video_cut.local.voice_model_config.v0"
OLLAMA_STATUS_SCHEMA = "smart_video_cut.local.ollama_status.v0"
OLLAMA_MODELS_SCHEMA = "smart_video_cut.local.ollama_models.v0"
OLLAMA_CONFIG_SCHEMA = "smart_video_cut.local.ollama_config_recommendation.v0"

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_OPENAI_BASE_URL = f"{DEFAULT_OLLAMA_BASE_URL}/v1"

DEFAULT_RECOMMENDED_VOICE_MODEL = {
    "provider_id": "moss_tts_nano",
    "display_name": "MOSS-TTS-Nano",
    "repo_url": "https://github.com/OpenMOSS/MOSS-TTS-Nano.git",
    "install_dir": str(ROOT_DIR / "MOSS-TTS-Nano"),
    "enabled": True,
    "adapter_status": "reserved_for_next_runtime_adapter",
    "purpose": "本地人声模拟/后续音色模型接入",
}


def _now() -> int:
    return int(time.time())


def _read_json(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _mask_llm_config(config: dict[str, Any]) -> dict[str, Any]:
    masked = dict(config)
    api_key = str(masked.pop("api_key", "") or "")
    masked["api_key_set"] = bool(api_key)
    masked["api_key"] = ""
    return masked


def default_llm_config() -> dict[str, Any]:
    return {
        "schema": LLM_CONFIG_SCHEMA,
        "provider": "openai_compatible",
        "base_url": "https://api.openai.com/v1",
        "model": "",
        "recommendation_profile": "visual_review_recommended",
        "model_capability": "multimodal_text_image",
        "api_key": "",
        "timeout_seconds": 20,
        "temperature": 0.2,
        "allow_cloud_llm_for_text_only": True,
        "allow_media_upload_to_llm": False,
        "updated_at": None,
    }


def ollama_native_base_url(base_url: str = "") -> str:
    value = str(base_url or DEFAULT_OLLAMA_BASE_URL).strip().rstrip("/")
    if value.endswith("/v1"):
        value = value[:-3].rstrip("/")
    return value or DEFAULT_OLLAMA_BASE_URL


def ollama_openai_base_url(base_url: str = "") -> str:
    return f"{ollama_native_base_url(base_url)}/v1"


def load_llm_config(*, masked: bool = True) -> dict[str, Any]:
    config = default_llm_config()
    config.update(_read_json(LLM_CONFIG_PATH))
    return _mask_llm_config(config) if masked else config


def save_llm_config(payload: dict[str, Any]) -> dict[str, Any]:
    current = load_llm_config(masked=False)
    incoming_key = str(payload.get("api_key", "") or "")
    if incoming_key in {"", "********"}:
        payload["api_key"] = current.get("api_key", "")

    provider = str(payload.get("provider") or "openai_compatible").strip()
    base_url = str(payload.get("base_url") or "").strip().rstrip("/")
    if provider == "local_ollama":
        base_url = ollama_openai_base_url(base_url)
        payload["api_key"] = ""

    config = default_llm_config()
    config.update(
        {
            "provider": provider,
            "base_url": base_url,
            "model": str(payload.get("model") or "").strip(),
            "recommendation_profile": str(
                payload.get("recommendation_profile") or "visual_review_recommended"
            ).strip(),
            "model_capability": str(payload.get("model_capability") or "multimodal_text_image").strip(),
            "api_key": str(payload.get("api_key") or "").strip(),
            "timeout_seconds": int(payload.get("timeout_seconds") or 20),
            "temperature": float(payload.get("temperature") if payload.get("temperature") is not None else 0.2),
            "allow_cloud_llm_for_text_only": False if provider == "local_ollama" else bool(payload.get("allow_cloud_llm_for_text_only", True)),
            "allow_media_upload_to_llm": bool(payload.get("allow_media_upload_to_llm", False)),
            "updated_at": _now(),
        }
    )
    _write_json(LLM_CONFIG_PATH, config)
    return {"ok": True, "config": _mask_llm_config(config), "path": str(LLM_CONFIG_PATH)}


def test_llm_config(payload: dict[str, Any] | None = None) -> dict[str, Any]:
    config = load_llm_config(masked=False)
    if payload:
        merged = dict(config)
        merged.update({k: v for k, v in payload.items() if v not in (None, "")})
        if not payload.get("api_key"):
            merged["api_key"] = config.get("api_key", "")
        config = merged

    provider = str(config.get("provider") or "openai_compatible")
    base_url = str(config.get("base_url") or "").rstrip("/")
    model = str(config.get("model") or "").strip()
    api_key = str(config.get("api_key") or "").strip()
    timeout = int(config.get("timeout_seconds") or 20)

    if not base_url:
        return {"ok": False, "stage": "preflight", "reason": "missing_base_url"}
    if not model:
        return {"ok": False, "stage": "preflight", "reason": "missing_model"}
    if provider != "local_ollama" and not api_key:
        return {"ok": False, "stage": "preflight", "reason": "missing_api_key"}

    url = f"{base_url}/chat/completions"
    body = {
        "model": model,
        "messages": [
            {"role": "system", "content": "Reply with exactly: OK"},
            {"role": "user", "content": "connection test"},
        ],
        "temperature": float(config.get("temperature") if config.get("temperature") is not None else 0.2),
        "max_tokens": 8,
    }
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    started = time.perf_counter()
    request = urllib.request.Request(
        url,
        data=json.dumps(body).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            raw = response.read().decode("utf-8", errors="replace")
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            parsed = json.loads(raw)
            content = (
                parsed.get("choices", [{}])[0]
                .get("message", {})
                .get("content", "")
            )
            return {
                "ok": True,
                "stage": "chat_completions",
                "provider": provider,
                "model": model,
                "base_url": base_url,
                "elapsed_ms": elapsed_ms,
                "sample_reply": content,
            }
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:1000]
        return {
            "ok": False,
            "stage": "chat_completions",
            "status_code": exc.code,
            "reason": "http_error",
            "detail": detail,
        }
    except Exception as exc:  # pragma: no cover - network and user config dependent
        return {
            "ok": False,
            "stage": "chat_completions",
            "reason": exc.__class__.__name__,
            "detail": str(exc),
        }


def check_ollama_status(base_url: str = "", timeout_seconds: int = 3) -> dict[str, Any]:
    native_base = ollama_native_base_url(base_url)
    url = f"{native_base}/api/version"
    started = time.perf_counter()
    try:
        payload = _get_json(url, timeout=max(1, int(timeout_seconds or 3)))
    except Exception as exc:
        return {
            "schema": OLLAMA_STATUS_SCHEMA,
            "ok": False,
            "ready": False,
            "provider": "local_ollama",
            "base_url": native_base,
            "openai_base_url": ollama_openai_base_url(native_base),
            "stage": "version_probe",
            "reason": exc.__class__.__name__,
            "detail": str(exc)[-500:],
            "install_hint": "请先安装并启动 Ollama，然后确认 11434 端口可访问。",
        }
    return {
        "schema": OLLAMA_STATUS_SCHEMA,
        "ok": True,
        "ready": True,
        "provider": "local_ollama",
        "base_url": native_base,
        "openai_base_url": ollama_openai_base_url(native_base),
        "stage": "version_probe",
        "version": str(payload.get("version") or ""),
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
    }


def list_ollama_models(base_url: str = "", timeout_seconds: int = 5) -> dict[str, Any]:
    native_base = ollama_native_base_url(base_url)
    status = check_ollama_status(native_base, timeout_seconds=min(max(1, int(timeout_seconds or 5)), 5))
    if not status.get("ok"):
        return {
            "schema": OLLAMA_MODELS_SCHEMA,
            "ok": False,
            "ready": False,
            "provider": "local_ollama",
            "base_url": native_base,
            "openai_base_url": ollama_openai_base_url(native_base),
            "models": [],
            "selected_model": "",
            "status": status,
            "pull_suggestions": ollama_pull_suggestions(),
        }
    try:
        payload = _get_json(f"{native_base}/api/tags", timeout=max(1, int(timeout_seconds or 5)))
    except Exception as exc:
        return {
            "schema": OLLAMA_MODELS_SCHEMA,
            "ok": False,
            "ready": True,
            "provider": "local_ollama",
            "base_url": native_base,
            "openai_base_url": ollama_openai_base_url(native_base),
            "models": [],
            "selected_model": "",
            "status": status,
            "reason": exc.__class__.__name__,
            "detail": str(exc)[-500:],
            "pull_suggestions": ollama_pull_suggestions(),
        }
    models = [_normalize_ollama_model(item) for item in payload.get("models") or [] if isinstance(item, dict)]
    models.sort(key=lambda item: (item["recommended_rank"], item["name"].casefold()))
    selected = _recommended_ollama_model(models)
    return {
        "schema": OLLAMA_MODELS_SCHEMA,
        "ok": True,
        "ready": True,
        "provider": "local_ollama",
        "base_url": native_base,
        "openai_base_url": ollama_openai_base_url(native_base),
        "models": models,
        "model_count": len(models),
        "selected_model": selected.get("name", ""),
        "selected_capability": selected.get("model_capability", "local_text_or_vision") if selected else "local_text_or_vision",
        "status": status,
        "pull_suggestions": ollama_pull_suggestions(),
    }


def recommend_ollama_llm_config(
    *,
    model: str = "",
    base_url: str = "",
    model_capability: str = "",
) -> dict[str, Any]:
    native_base = ollama_native_base_url(base_url)
    model_name = str(model or "").strip()
    capability = str(model_capability or _ollama_model_capability(model_name) or "local_text_or_vision")
    return {
        "schema": OLLAMA_CONFIG_SCHEMA,
        "ok": bool(model_name),
        "provider": "local_ollama",
        "base_url": ollama_openai_base_url(native_base),
        "native_base_url": native_base,
        "model": model_name,
        "recommendation_profile": "local_first",
        "model_capability": capability,
        "api_key": "",
        "timeout_seconds": 30,
        "temperature": 0.2,
        "allow_cloud_llm_for_text_only": False,
        "allow_media_upload_to_llm": capability in {"multimodal_text_image", "local_text_or_vision"} and _looks_like_vision_model(model_name),
        "next_step": "save_llm_config" if model_name else "choose_or_pull_model",
    }


def save_ollama_llm_config(payload: dict[str, Any]) -> dict[str, Any]:
    config = recommend_ollama_llm_config(
        model=str(payload.get("model") or ""),
        base_url=str(payload.get("base_url") or payload.get("native_base_url") or ""),
        model_capability=str(payload.get("model_capability") or ""),
    )
    if not config["model"]:
        return {"ok": False, "reason": "missing_model", "config": config}
    saved = save_llm_config(config)
    return {"ok": saved.get("ok") is True, "config": saved.get("config"), "path": saved.get("path"), "recommendation": config}


def ollama_pull_suggestions() -> list[dict[str, str]]:
    return [
        {
            "model": "qwen2.5:7b",
            "command": "ollama pull qwen2.5:7b",
            "purpose": "中文导演沟通、文案、字幕规划，兼顾速度和质量。",
        },
        {
            "model": "llama3.2:3b",
            "command": "ollama pull llama3.2:3b",
            "purpose": "轻量文本规划，适合显存较小的电脑。",
        },
        {
            "model": "llava:7b",
            "command": "ollama pull llava:7b",
            "purpose": "本地视觉理解候选，用于后续抽帧/缩略图复核。",
        },
    ]


def load_voice_model_config() -> dict[str, Any]:
    config = {
        "schema": VOICE_MODEL_CONFIG_SCHEMA,
        **DEFAULT_RECOMMENDED_VOICE_MODEL,
        "updated_at": None,
    }
    config.update(_read_json(VOICE_MODEL_CONFIG_PATH))
    return config


def save_voice_model_config(payload: dict[str, Any]) -> dict[str, Any]:
    config = load_voice_model_config()
    config.update(
        {
            "provider_id": str(payload.get("provider_id") or config["provider_id"]).strip(),
            "display_name": str(payload.get("display_name") or config["display_name"]).strip(),
            "repo_url": str(payload.get("repo_url") or config["repo_url"]).strip(),
            "install_dir": str(payload.get("install_dir") or config["install_dir"]).strip(),
            "enabled": bool(payload.get("enabled", config.get("enabled", True))),
            "updated_at": _now(),
        }
    )
    _write_json(VOICE_MODEL_CONFIG_PATH, config)
    return {"ok": True, "config": check_voice_model(config), "path": str(VOICE_MODEL_CONFIG_PATH)}


def check_voice_model(config: dict[str, Any] | None = None) -> dict[str, Any]:
    config = dict(config or load_voice_model_config())
    install_dir = Path(str(config.get("install_dir") or ""))
    markers = [
        install_dir / ".git",
        install_dir / "README.md",
        install_dir / "pyproject.toml",
        install_dir / "requirements.txt",
    ]
    installed = install_dir.exists() and any(marker.exists() for marker in markers)
    config.update(
        {
            "installed": installed,
            "install_dir_exists": install_dir.exists(),
            "install_command": f'git clone {config["repo_url"]} "{install_dir}"',
            "next_step": "run_adapter_integration" if installed else "clone_repository_then_install_dependencies",
        }
    )
    if str(config.get("provider_id") or "") == "moss_tts_nano":
        config["runtime_status"] = check_moss_tts_status(install_dir)
    return config


def load_local_config_summary() -> dict[str, Any]:
    return {
        "llm": load_llm_config(masked=True),
        "voice_model": check_voice_model(),
        "paths": {
            "root_dir": str(ROOT_DIR),
            "workspace_dir": str(WORKSPACE_DIR),
            "config_dir": str(CONFIG_DIR),
            "packages_dir": str(PACKAGES_DIR),
            "output_root": str(OUTPUT_ROOT),
            "voice_samples_dir": str(VOICE_SAMPLES_DIR),
            "protocol_dropbox_root": str(PROTOCOL_DROPBOX_ROOT),
            "default_output_dir": str(OUTPUT_ROOT / "case001"),
            "default_protocol_path": str((OUTPUT_ROOT / "case001") / "local_toolkit_protocol.json"),
        },
    }


def _get_json(url: str, *, timeout: int) -> dict[str, Any]:
    request = urllib.request.Request(url, headers={"Content-Type": "application/json"}, method="GET")
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read().decode("utf-8", errors="replace")
    parsed = json.loads(raw)
    return parsed if isinstance(parsed, dict) else {}


def _normalize_ollama_model(item: dict[str, Any]) -> dict[str, Any]:
    name = str(item.get("name") or item.get("model") or "").strip()
    details = item.get("details") if isinstance(item.get("details"), dict) else {}
    capability = _ollama_model_capability(name)
    return {
        "name": name,
        "modified_at": str(item.get("modified_at") or ""),
        "size": int(item.get("size") or 0),
        "digest": str(item.get("digest") or ""),
        "family": str(details.get("family") or ""),
        "parameter_size": str(details.get("parameter_size") or ""),
        "quantization_level": str(details.get("quantization_level") or ""),
        "model_capability": capability,
        "recommended_rank": _ollama_recommend_rank(name),
        "is_vision_model": _looks_like_vision_model(name),
    }


def _recommended_ollama_model(models: list[dict[str, Any]]) -> dict[str, Any]:
    if not models:
        return {}
    return models[0]


def _ollama_recommend_rank(name: str) -> int:
    normalized = name.casefold()
    priority = (
        ("qwen2.5", 10),
        ("qwen3", 12),
        ("llama3.2", 20),
        ("llama3.1", 22),
        ("gemma3", 30),
        ("deepseek-r1", 40),
        ("llava", 50),
        ("minicpm", 55),
        ("moondream", 60),
    )
    for key, rank in priority:
        if key in normalized:
            return rank
    return 100


def _ollama_model_capability(name: str) -> str:
    if _looks_like_vision_model(name):
        return "local_text_or_vision"
    return "text_only"


def _looks_like_vision_model(name: str) -> bool:
    normalized = str(name or "").casefold()
    return any(key in normalized for key in ("llava", "vision", "vl", "minicpm-v", "moondream", "bakllava"))
