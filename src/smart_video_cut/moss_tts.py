from __future__ import annotations

import os
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
DEFAULT_MOSS_REPO_CANDIDATES = (
    ROOT_DIR / "MOSS-TTS-Nano",
    ROOT_DIR / "models" / "MOSS-TTS-Nano",
)
DEFAULT_SAMPLE_TEXT = "这是一段本地智能剪辑软件生成的男声样音。"
DEFAULT_VOICE = "Zhiming"
MOSS_TTS_MODEL_DIR_NAME = "MOSS-TTS-Nano-100M-ONNX"
MOSS_CODEC_MODEL_DIR_NAME = "MOSS-Audio-Tokenizer-Nano-ONNX"
MOSS_REQUIRED_TTS_FILES = (
    "browser_poc_manifest.json",
    "tts_browser_onnx_meta.json",
    "tokenizer.model",
    "moss_tts_prefill.onnx",
    "moss_tts_decode_step.onnx",
    "moss_tts_global_shared.data",
    "moss_tts_local_shared.data",
)
MOSS_REQUIRED_CODEC_FILES = (
    "codec_browser_onnx_meta.json",
    "moss_audio_tokenizer_encode.onnx",
    "moss_audio_tokenizer_decode_full.onnx",
)


def resolve_moss_repo(install_dir: str | Path | None = None) -> Path:
    if install_dir:
        return Path(install_dir).expanduser().resolve()
    for candidate in DEFAULT_MOSS_REPO_CANDIDATES:
        if (candidate / "infer_onnx.py").is_file():
            return candidate.resolve()
    return DEFAULT_MOSS_REPO_CANDIDATES[0].resolve()


def moss_venv_python(repo_dir: str | Path | None = None) -> Path:
    repo = resolve_moss_repo(repo_dir)
    return repo / ".venv" / "Scripts" / "python.exe"


def check_moss_tts_status(install_dir: str | Path | None = None) -> dict[str, Any]:
    repo = resolve_moss_repo(install_dir)
    venv_python = moss_venv_python(repo)
    repo_found = (repo / "infer_onnx.py").is_file() and (repo / "pyproject.toml").is_file()
    deps = _dependency_status(venv_python) if venv_python.is_file() else _missing_dependency_status()
    model_assets = _model_assets_status(repo)
    sample_audio = repo / "assets" / "audio" / "zh_1.wav"
    return {
        "schema": "smart_video_cut.local.moss_tts_status.v0",
        "repo_dir": str(repo),
        "repo_found": repo_found,
        "venv_python": str(venv_python),
        "venv_exists": venv_python.is_file(),
        "dependencies": deps,
        "model_assets": model_assets,
        "sample_audio": str(sample_audio),
        "sample_audio_exists": sample_audio.is_file(),
        "builtin_voices": _builtin_voices(repo),
        "ready": repo_found and venv_python.is_file() and deps["ok"] is True,
        "can_synthesize_now": repo_found and venv_python.is_file() and deps["ok"] is True,
        "will_download_onnx_on_first_run": model_assets["ready"] is not True,
        "setup_command": _setup_command(repo),
    }


def install_moss_tts_runtime(install_dir: str | Path | None = None) -> dict[str, Any]:
    repo = resolve_moss_repo(install_dir)
    if not (repo / "pyproject.toml").is_file():
        raise FileNotFoundError(f"MOSS-TTS-Nano repo not found: {repo}")
    venv_python = moss_venv_python(repo)
    if not venv_python.is_file():
        _run(["py", "-3.12", "-m", "venv", str(repo / ".venv")], cwd=repo, timeout_seconds=300)
    _run([str(venv_python), "-m", "pip", "install", "--upgrade", "pip", "setuptools", "wheel"], cwd=repo, timeout_seconds=600)
    _run([str(venv_python), "-m", "pip", "install", "-e", ".", "soundfile"], cwd=repo, timeout_seconds=3600)
    status = check_moss_tts_status(repo)
    return {"ok": status["ready"], "status": status}


def synthesize_moss_tts(
    *,
    text: str = DEFAULT_SAMPLE_TEXT,
    output_audio_path: str | Path,
    install_dir: str | Path | None = None,
    voice: str = DEFAULT_VOICE,
    prompt_audio_path: str | Path | None = None,
    cpu_threads: int = 4,
    max_new_frames: int = 375,
    sample_mode: str = "fixed",
    text_temperature: float = 0.8,
    audio_temperature: float = 0.6,
    seed: int | None = 2026,
    timeout_seconds: int = 1800,
) -> dict[str, Any]:
    repo = resolve_moss_repo(install_dir)
    status = check_moss_tts_status(repo)
    if status["can_synthesize_now"] is not True:
        return {
            "ok": False,
            "stage": "preflight",
            "reason": "moss_tts_runtime_not_ready",
            "status": status,
        }

    output_path = Path(output_audio_path).expanduser().resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = [
        str(moss_venv_python(repo)),
        "-m",
        "moss_tts_nano",
        "generate",
        "--backend",
        "onnx",
        "--onnx-model-dir",
        str(_ensure_runtime_model_dir(repo)),
        "--output",
        str(output_path),
        "--text",
        str(text or DEFAULT_SAMPLE_TEXT),
        "--voice",
        str(voice or DEFAULT_VOICE),
        "--sample-mode",
        _safe_sample_mode(sample_mode),
        "--cpu-threads",
        str(max(1, int(cpu_threads))),
        "--execution-provider",
        "cpu",
        "--max-new-frames",
        str(max(1, int(max_new_frames))),
        "--text-temperature",
        str(_safe_temperature(text_temperature, default=0.8)),
        "--audio-temperature",
        str(_safe_temperature(audio_temperature, default=0.6)),
    ]
    if _safe_sample_mode(sample_mode) == "greedy":
        command.extend(["--do-sample", "0"])
    if prompt_audio_path:
        command.extend(["--prompt-speech", str(prompt_audio_path)])
    if seed is not None:
        command.extend(["--seed", str(int(seed))])
    started = time.perf_counter()
    try:
        completed = _run(command, cwd=repo, timeout_seconds=timeout_seconds)
    except Exception as exc:
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        return {
            "ok": False,
            "stage": "synthesize",
            "reason": exc.__class__.__name__,
            "detail": str(exc)[-2000:],
            "audio_path": None,
            "elapsed_ms": elapsed_ms,
            "status": check_moss_tts_status(repo),
        }
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    output_ok = output_path.is_file() and output_path.stat().st_size > 1000
    return {
        "ok": output_ok,
        "stage": "synthesize",
        "audio_path": str(output_path) if output_ok else None,
        "size_bytes": output_path.stat().st_size if output_path.is_file() else 0,
        "elapsed_ms": elapsed_ms,
        "voice": voice,
        "sample_mode": _safe_sample_mode(sample_mode),
        "text_temperature": _safe_temperature(text_temperature, default=0.8),
        "audio_temperature": _safe_temperature(audio_temperature, default=0.6),
        "seed": seed,
        "text_preview": str(text or "")[:120],
        "command_returncode": completed["returncode"],
        "stderr_tail": completed["stderr"][-1600:],
        "stdout_tail": completed["stdout"][-1600:],
        "status": check_moss_tts_status(repo),
    }


def _builtin_voices(repo: Path) -> list[dict[str, str]]:
    manifest = repo / "models" / MOSS_TTS_MODEL_DIR_NAME / "browser_poc_manifest.json"
    if not manifest.is_file():
        return []
    try:
        data = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    voices: list[dict[str, str]] = []
    for item in data.get("builtin_voices", []):
        if not isinstance(item, dict) or not item.get("voice"):
            continue
        voices.append(
            {
                "voice": str(item.get("voice") or ""),
                "display_name": str(item.get("display_name") or item.get("voice") or ""),
                "group": str(item.get("group") or ""),
                "audio_file": str(item.get("audio_file") or ""),
            }
        )
    return voices


def _safe_sample_mode(value: str) -> str:
    selected = str(value or "fixed")
    return selected if selected in {"greedy", "fixed", "full"} else "fixed"


def _safe_temperature(value: float, *, default: float) -> float:
    try:
        numeric = float(value)
    except (TypeError, ValueError):
        return default
    return min(2.0, max(0.1, numeric))


def _model_assets_status(repo: Path) -> dict[str, Any]:
    source_model_dir = repo / "models"
    runtime_model_dir = _runtime_model_dir_candidate(repo)
    source_status = _model_assets_status_for_dir(source_model_dir)
    runtime_status = source_status
    if runtime_model_dir != source_model_dir:
        runtime_status = _model_assets_status_for_dir(runtime_model_dir)
    effective_status = runtime_status if runtime_model_dir != source_model_dir else source_status
    return {
        **effective_status,
        "source_model_dir": str(source_model_dir),
        "source_ready": source_status["ready"],
        "runtime_model_dir": str(runtime_model_dir),
        "runtime_ready": runtime_status["ready"],
        "uses_ascii_runtime_cache": runtime_model_dir != source_model_dir,
    }


def _model_assets_status_for_dir(model_dir: Path) -> dict[str, Any]:
    manifest_candidates = (
        model_dir / "browser_poc_manifest.json",
        model_dir / MOSS_TTS_MODEL_DIR_NAME / "browser_poc_manifest.json",
        model_dir / "MOSS-TTS-Nano-ONNX-CPU" / "browser_poc_manifest.json",
    )
    manifest = next((path for path in manifest_candidates if path.is_file()), None)
    required_paths = [
        *(model_dir / MOSS_TTS_MODEL_DIR_NAME / name for name in MOSS_REQUIRED_TTS_FILES),
        *(model_dir / MOSS_CODEC_MODEL_DIR_NAME / name for name in MOSS_REQUIRED_CODEC_FILES),
    ]
    missing_required_files = [
        str(path.relative_to(model_dir)).replace("\\", "/")
        for path in required_paths
        if not path.is_file() or path.stat().st_size <= 0
    ]
    return {
        "model_dir": str(model_dir),
        "model_dir_exists": model_dir.exists(),
        "ready": manifest is not None and not missing_required_files,
        "manifest_path": str(manifest) if manifest else None,
        "missing_required_files": missing_required_files,
    }


def _ensure_runtime_model_dir(repo: Path) -> Path:
    source_model_dir = repo / "models"
    runtime_model_dir = _runtime_model_dir_candidate(repo)
    if runtime_model_dir == source_model_dir:
        return source_model_dir
    if _is_link(runtime_model_dir):
        _remove_link_if_needed(runtime_model_dir)
    runtime_status = _model_assets_status_for_dir(runtime_model_dir)
    if runtime_status["ready"]:
        return runtime_model_dir
    source_status = _model_assets_status_for_dir(source_model_dir)
    if source_status["ready"]:
        _copy_model_assets(source_model_dir, runtime_model_dir)
        return runtime_model_dir
    _download_model_assets(repo, runtime_model_dir)
    return runtime_model_dir


def _runtime_model_dir_candidate(repo: Path) -> Path:
    source_model_dir = repo / "models"
    if str(source_model_dir).isascii():
        return source_model_dir
    return _ascii_runtime_root(repo) / "models"


def _ascii_runtime_root(repo: Path) -> Path:
    if repo.drive:
        return Path(repo.drive + "\\") / "SmartVideoCutRuntime" / "MOSS-TTS-Nano"
    program_data = Path(os.environ.get("PROGRAMDATA", r"C:\ProgramData"))
    return program_data / "SmartVideoCutRuntime" / "MOSS-TTS-Nano"


def _copy_model_assets(source_model_dir: Path, runtime_model_dir: Path) -> None:
    _remove_link_if_needed(runtime_model_dir)
    runtime_model_dir.mkdir(parents=True, exist_ok=True)
    for source in source_model_dir.rglob("*"):
        relative = source.relative_to(source_model_dir)
        target = runtime_model_dir / relative
        if source.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.is_file() and target.stat().st_size == source.stat().st_size:
            continue
        shutil.copy2(source, target)


def _download_model_assets(repo: Path, runtime_model_dir: Path) -> None:
    _remove_link_if_needed(runtime_model_dir)
    runtime_model_dir.mkdir(parents=True, exist_ok=True)
    script = (
        "from pathlib import Path\n"
        "from onnx_tts_runtime import _download_default_browser_onnx_assets\n"
        f"_download_default_browser_onnx_assets(Path(r'''{runtime_model_dir}'''))\n"
        "print('downloaded')\n"
    )
    _run([str(moss_venv_python(repo)), "-c", script], cwd=repo, timeout_seconds=3600)


def _remove_link_if_needed(path: Path) -> None:
    if not path.exists():
        return
    if _is_link(path):
        path.rmdir() if path.is_dir() else path.unlink()


def _is_link(path: Path) -> bool:
    is_junction = getattr(path, "is_junction", lambda: False)()
    return path.is_symlink() or bool(is_junction)


def _dependency_status(python_exe: Path) -> dict[str, Any]:
    script = (
        "import importlib.util\n"
        "mods=['onnxruntime','sentencepiece','torch','torchaudio','transformers','numpy']\n"
        "missing=[m for m in mods if importlib.util.find_spec(m) is None]\n"
        "print('missing=' + ','.join(missing))\n"
    )
    try:
        completed = _run([str(python_exe), "-c", script], cwd=python_exe.parent, timeout_seconds=60)
    except Exception as exc:
        return {"ok": False, "missing": ["dependency_check_failed"], "detail": str(exc)}
    missing_line = completed["stdout"].strip().splitlines()[-1] if completed["stdout"].strip() else "missing=unknown"
    missing = [item for item in missing_line.replace("missing=", "").split(",") if item]
    return {
        "ok": completed["returncode"] == 0 and not missing,
        "missing": missing,
        "returncode": completed["returncode"],
        "stderr_tail": completed["stderr"][-800:],
    }


def _missing_dependency_status() -> dict[str, Any]:
    return {
        "ok": False,
        "missing": ["venv_not_created"],
        "returncode": None,
        "stderr_tail": "",
    }


def _setup_command(repo: Path) -> str:
    venv_python = moss_venv_python(repo)
    return (
        f'py -3.12 -m venv "{repo / ".venv"}"; '
        f'"{venv_python}" -m pip install --upgrade pip setuptools wheel; '
        f'"{venv_python}" -m pip install -e "{repo}" soundfile'
    )


def _run(command: list[str], *, cwd: Path, timeout_seconds: int) -> dict[str, Any]:
    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONUTF8", "1")
    completed = subprocess.run(
        command,
        cwd=str(cwd),
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
    )
    if completed.returncode != 0:
        raise RuntimeError(
            f"command failed with code {completed.returncode}: {' '.join(command)}\n"
            f"{completed.stderr[-2000:]}"
        )
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
    }
