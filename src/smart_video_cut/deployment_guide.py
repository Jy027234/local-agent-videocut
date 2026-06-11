from __future__ import annotations

from pathlib import Path
from typing import Any

from smart_video_cut.bundled_runtime import ensure_video_toolkit_available


DEPLOYMENT_GUIDE_SCHEMA = "smart_video_cut.local.deployment_guide.v0"
ROOT_DIR = Path(__file__).resolve().parents[2]


def local_deployment_guide() -> dict[str, Any]:
    try:
        runtime = ensure_video_toolkit_available()
    except Exception as exc:  # pragma: no cover - defensive UI status
        runtime = {"available": False, "error": str(exc), "media_tools": {}}
    media = runtime.get("media_tools") if isinstance(runtime.get("media_tools"), dict) else {}
    ffmpeg = media.get("ffmpeg") if isinstance(media.get("ffmpeg"), dict) else {}
    ffprobe = media.get("ffprobe") if isinstance(media.get("ffprobe"), dict) else {}
    ffmpeg_ready = ffmpeg.get("available") is True and ffprobe.get("available") is True
    electron_dir = ROOT_DIR / "desktop" / "electron"
    electron_ready = (electron_dir / "package.json").is_file() and (electron_dir / "main.js").is_file()
    return {
        "schema": DEPLOYMENT_GUIDE_SCHEMA,
        "ok": True,
        "desktop_shell": {
            "status": "available" if electron_ready else "planned",
            "recommended_path": "Electron 壳会启动本地 8769 服务并打开 Local Studio；Tauri 可后续按同一 API 接入。",
            "tauri": {
                "ready": False,
                "reason": "当前仓库尚未包含 src-tauri 工程。",
            },
            "electron": {
                "ready": electron_ready,
                "path": str(electron_dir),
                "package_command": "cd desktop\\electron; npm install; npm run package:win",
                "reason": "已包含 Electron main/preload/package scaffold。" if electron_ready else "当前仓库尚未包含 electron main/preload 工程。",
            },
        },
        "customer_package": {
            "status": "available",
            "script": str(ROOT_DIR / "scripts" / "build_customer_package.ps1"),
            "portable_runtime_script": str(ROOT_DIR / "scripts" / "prepare_portable_runtime.py"),
            "smoke_test_script": str(ROOT_DIR / "scripts" / "release_smoke_check.py"),
            "launchers": [
                str(ROOT_DIR / "启动本地智能剪辑软件.bat"),
                str(ROOT_DIR / "启动本地智能剪辑软件.ps1"),
            ],
            "preflight_command": 'py -m smart_video_cut.release_preflight --root "<app_root>" --port 8769 --require-port-available --strict --format text',
            "smoke_test_command": 'py scripts/release_smoke_check.py --package-dir "<release_dir>" --port 8769 --timeout-seconds 60',
        },
        "ffmpeg": {
            "ready": ffmpeg_ready,
            "ffmpeg_path": ffmpeg.get("path") or "",
            "ffprobe_path": ffprobe.get("path") or "",
            "install_hint": "优先使用 packages/ffmpeg/bin；缺失时把 ffmpeg.exe 和 ffprobe.exe 放入该目录，或安装到系统 PATH。",
            "expected_dir": str(ROOT_DIR / "packages" / "ffmpeg" / "bin"),
        },
        "runtime": runtime,
    }
