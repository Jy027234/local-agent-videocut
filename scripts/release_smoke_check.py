from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Start a packaged Local Studio release and verify smoke endpoints.")
    parser.add_argument("--package-dir", required=True)
    parser.add_argument("--port", type=int, default=8769)
    parser.add_argument("--timeout-seconds", type=int, default=60)
    parser.add_argument("--report-path", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    package_dir = Path(args.package_dir).resolve()
    runtime_python = package_dir / ".runtime" / "python" / "python.exe"
    if not runtime_python.is_file():
        raise FileNotFoundError(f"Portable runtime missing: {runtime_python}")

    preflight = run_preflight(package_dir=package_dir, runtime_python=runtime_python, port=args.port)
    if preflight["returncode"] != 0:
        payload = {
            "ok": False,
            "reason": "preflight_failed",
            "preflight": preflight,
        }
        write_report(args.report_path, payload)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 1

    log_path = package_dir / ".runtime" / "smoke-server.log"
    env = os.environ.copy()
    env["PYTHONHOME"] = str(package_dir / ".runtime" / "python")
    env["PYTHONPATH"] = str(package_dir / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    with log_path.open("w", encoding="utf-8") as log_file:
        process = subprocess.Popen(
            [str(runtime_python), "-m", "smart_video_cut.web_app"],
            cwd=package_dir,
            env=env,
            stdout=log_file,
            stderr=subprocess.STDOUT,
        )
    try:
        checks = wait_for_server(port=args.port, timeout_seconds=args.timeout_seconds)
        payload = {
            "ok": all(item.get("ok") is True for item in checks),
            "reason": "smoke_check_passed" if all(item.get("ok") is True for item in checks) else "smoke_check_failed",
            "checks": checks,
            "log_path": str(log_path),
        }
    finally:
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=10)

    write_report(args.report_path, payload)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0 if payload["ok"] else 1


def run_preflight(*, package_dir: Path, runtime_python: Path, port: int) -> dict[str, Any]:
    env = os.environ.copy()
    env["PYTHONHOME"] = str(package_dir / ".runtime" / "python")
    env["PYTHONPATH"] = str(package_dir / "src")
    env["PYTHONIOENCODING"] = "utf-8"
    completed = subprocess.run(
        [
            str(runtime_python),
            "-m",
            "smart_video_cut.release_preflight",
            "--root",
            str(package_dir),
            "--port",
            str(port),
            "--expect-portable-runtime",
            "--require-port-available",
            "--strict",
            "--format",
            "json",
        ],
        cwd=package_dir,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    payload = {}
    try:
        payload = json.loads(completed.stdout or "{}")
    except json.JSONDecodeError:
        payload = {}
    return {
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "payload": payload,
    }


def wait_for_server(*, port: int, timeout_seconds: int) -> list[dict[str, Any]]:
    deadline = time.time() + max(5, int(timeout_seconds))
    target = f"http://127.0.0.1:{port}"
    last_error = ""
    while time.time() < deadline:
        try:
            check_payload = fetch_json(f"{target}/api/check")
            guide_payload = fetch_json(f"{target}/api/deployment/guide")
            root_html = fetch_text(f"{target}/")
            return [
                {"name": "/api/check", "ok": bool(check_payload.get("available")), "payload": check_payload},
                {"name": "/api/deployment/guide", "ok": bool(guide_payload.get("ok")), "payload": guide_payload},
                {"name": "/", "ok": "Local Studio" in root_html, "payload": {"contains_local_studio": "Local Studio" in root_html}},
            ]
        except Exception as exc:  # pragma: no cover - depends on local timing
            last_error = repr(exc)
            time.sleep(1)
    return [
        {"name": "startup", "ok": False, "payload": {"error": last_error or "server_timeout"}},
    ]


def fetch_json(url: str) -> dict[str, Any]:
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=5) as response:
        return json.loads(response.read().decode("utf-8"))


def fetch_text(url: str) -> str:
    request = urllib.request.Request(url, method="GET")
    with urllib.request.urlopen(request, timeout=5) as response:
        return response.read().decode("utf-8", errors="replace")


def write_report(path: str, payload: dict[str, Any]) -> None:
    if not path:
        return
    report_path = Path(path).resolve()
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())
