from __future__ import annotations

import argparse
import importlib
import json
import socket
import sys
from pathlib import Path
from typing import Any, Iterable


RELEASE_PREFLIGHT_SCHEMA = "smart_video_cut.local.release_preflight.v0"


def collect_release_preflight(
    *,
    root: str | Path | None = None,
    port: int = 8769,
    expect_portable_runtime: bool = False,
    require_port_available: bool = False,
    required_imports: Iterable[str] | None = None,
    optional_imports: Iterable[str] | None = None,
) -> dict[str, Any]:
    app_root = Path(root or Path.cwd()).resolve()
    errors: list[dict[str, Any]] = []
    warnings: list[dict[str, Any]] = []

    required_paths = [
        ("src/smart_video_cut/web_app.py", "file", "缺少主 Web 入口"),
        ("src/smart_video_cut/static/index.html", "file", "缺少首页 HTML"),
        ("src/smart_video_cut/static/app.js", "file", "缺少前端脚本"),
        ("src/smart_video_cut/static/app.css", "file", "缺少前端样式"),
        ("src/video_editing_toolkit/__init__.py", "file", "缺少内置剪辑运行时"),
        ("packages/ffmpeg/bin/ffmpeg.exe", "file", "缺少 ffmpeg.exe"),
        ("packages/ffmpeg/bin/ffprobe.exe", "file", "缺少 ffprobe.exe"),
        ("workspace/config", "dir", "缺少配置目录"),
        ("workspace/output", "dir", "缺少输出目录"),
        ("workspace/projects", "dir", "缺少项目目录"),
        ("workspace/voice_samples", "dir", "缺少样音目录"),
    ]
    path_checks = [_path_check(app_root, relative, kind) for relative, kind, _ in required_paths]
    for item, (_, _, message) in zip(path_checks, required_paths):
        if item["exists"] is not True:
            errors.append({
                "code": "required_path_missing",
                "path": item["path"],
                "kind": item["kind"],
                "message": message,
            })

    portable_python = app_root / ".runtime" / "python" / "python.exe"
    portable_runtime = {
        "path": str(portable_python),
        "exists": portable_python.is_file(),
        "expected": expect_portable_runtime,
    }
    if expect_portable_runtime and portable_runtime["exists"] is not True:
        errors.append({
            "code": "portable_runtime_missing",
            "path": portable_runtime["path"],
            "message": "发布包缺少 .runtime/python/python.exe，无法直接启动。",
        })

    write_checks = [
        _write_check(app_root / "workspace" / "config"),
        _write_check(app_root / "workspace" / "output"),
        _write_check(app_root / "workspace" / "projects"),
    ]
    for item in write_checks:
        if item["ok"] is not True:
            errors.append({
                "code": "workspace_not_writable",
                "path": item["path"],
                "message": item["message"],
            })

    default_required_imports = [
        "fastapi",
        "uvicorn",
        "pydantic",
        "smart_video_cut.web_app",
        "video_editing_toolkit",
    ]
    default_optional_imports = [
        "numpy",
        "cv2",
        "onnxruntime",
    ]
    import_checks = _import_checks(list(required_imports or default_required_imports))
    optional_import_checks = _import_checks(list(optional_imports or default_optional_imports))
    for item in import_checks:
        if item["ok"] is not True:
            errors.append({
                "code": "required_import_failed",
                "module": item["module"],
                "message": item["error"],
            })
    for item in optional_import_checks:
        if item["ok"] is not True:
            warnings.append({
                "code": "optional_import_failed",
                "module": item["module"],
                "message": item["error"],
            })

    port_check = _port_check(port)
    if require_port_available and port_check["available"] is not True:
        errors.append({
            "code": "port_in_use",
            "port": port,
            "message": f"端口 {port} 已被占用，请先关闭旧进程后再启动。",
        })

    moss_root = app_root / "MOSS-TTS-Nano"
    if not moss_root.exists():
        warnings.append({
            "code": "moss_runtime_missing",
            "path": str(moss_root),
            "message": "未找到 MOSS-TTS-Nano 目录；如果你要用本地配音，需要补齐该目录。",
        })

    summary_lines = _summary_lines(
        errors=errors,
        warnings=warnings,
        require_port_available=require_port_available,
        expect_portable_runtime=expect_portable_runtime,
    )
    return {
        "schema": RELEASE_PREFLIGHT_SCHEMA,
        "ok": not errors,
        "root": str(app_root),
        "portable_runtime": portable_runtime,
        "port": port_check,
        "required_paths": path_checks,
        "workspace_write_checks": write_checks,
        "imports": import_checks,
        "optional_imports": optional_import_checks,
        "errors": errors,
        "warnings": warnings,
        "summary_lines": summary_lines,
    }


def _path_check(root: Path, relative_path: str, kind: str) -> dict[str, Any]:
    path = root / Path(relative_path)
    exists = path.is_file() if kind == "file" else path.is_dir()
    return {
        "path": str(path),
        "relative_path": relative_path,
        "kind": kind,
        "exists": exists,
    }


def _write_check(path: Path) -> dict[str, Any]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        marker = path / ".release-preflight-write-test"
        marker.write_text("ok", encoding="utf-8")
        marker.unlink(missing_ok=True)
        return {"path": str(path), "ok": True, "message": "ok"}
    except OSError as exc:
        return {"path": str(path), "ok": False, "message": str(exc)}


def _import_checks(module_names: list[str]) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    for name in module_names:
        try:
            importlib.import_module(name)
        except Exception as exc:  # pragma: no cover - importlib error text is environment-specific
            results.append({"module": name, "ok": False, "error": repr(exc)})
        else:
            results.append({"module": name, "ok": True, "error": ""})
    return results


def _port_check(port: int) -> dict[str, Any]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        sock.bind(("127.0.0.1", int(port)))
    except OSError as exc:
        return {"port": int(port), "available": False, "error": str(exc)}
    finally:
        sock.close()
    return {"port": int(port), "available": True, "error": ""}


def _summary_lines(
    *,
    errors: list[dict[str, Any]],
    warnings: list[dict[str, Any]],
    require_port_available: bool,
    expect_portable_runtime: bool,
) -> list[str]:
    lines = []
    if not errors:
        lines.append("启动前预检通过。")
    else:
        lines.append("启动前预检未通过，请先处理以下问题：")
        lines.extend(f"- {item['message']}" for item in errors)
    if warnings:
        lines.append("提示：")
        lines.extend(f"- {item['message']}" for item in warnings)
    if expect_portable_runtime:
        lines.append("当前按正式发布包标准检查，要求 .runtime/python 已随包提供。")
    if require_port_available:
        lines.append("同时检查了本地 8769 端口是否可直接启动。")
    return lines


def _render_text(payload: dict[str, Any]) -> str:
    return "\n".join(str(line) for line in payload.get("summary_lines") or [])


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run Local Studio release/startup preflight checks.")
    parser.add_argument("--root", default="")
    parser.add_argument("--port", type=int, default=8769)
    parser.add_argument("--strict", action="store_true")
    parser.add_argument("--expect-portable-runtime", action="store_true")
    parser.add_argument("--require-port-available", action="store_true")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    payload = collect_release_preflight(
        root=args.root or None,
        port=args.port,
        expect_portable_runtime=args.expect_portable_runtime,
        require_port_available=args.require_port_available,
    )
    if args.format == "json":
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(_render_text(payload))
    if args.strict and payload["ok"] is not True:
        return 1
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main(sys.argv[1:]))
