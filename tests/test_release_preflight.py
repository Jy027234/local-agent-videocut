from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from smart_video_cut.release_preflight import RELEASE_PREFLIGHT_SCHEMA, collect_release_preflight
from smart_video_cut.web_app import create_app


def _create_minimal_release_tree(root: Path) -> None:
    (root / "src" / "smart_video_cut" / "static").mkdir(parents=True, exist_ok=True)
    (root / "src" / "video_editing_toolkit").mkdir(parents=True, exist_ok=True)
    (root / "packages" / "ffmpeg" / "bin").mkdir(parents=True, exist_ok=True)
    (root / "workspace" / "config").mkdir(parents=True, exist_ok=True)
    (root / "workspace" / "output").mkdir(parents=True, exist_ok=True)
    (root / "workspace" / "projects").mkdir(parents=True, exist_ok=True)
    (root / "workspace" / "voice_samples").mkdir(parents=True, exist_ok=True)
    (root / ".runtime" / "python").mkdir(parents=True, exist_ok=True)

    (root / "src" / "smart_video_cut" / "web_app.py").write_text("app = object()\n", encoding="utf-8")
    (root / "src" / "smart_video_cut" / "static" / "index.html").write_text("<html>Local Studio</html>", encoding="utf-8")
    (root / "src" / "smart_video_cut" / "static" / "app.js").write_text("console.log('ok')\n", encoding="utf-8")
    (root / "src" / "smart_video_cut" / "static" / "app.css").write_text("body{}\n", encoding="utf-8")
    (root / "src" / "video_editing_toolkit" / "__init__.py").write_text("__all__ = []\n", encoding="utf-8")
    (root / "packages" / "ffmpeg" / "bin" / "ffmpeg.exe").write_bytes(b"ffmpeg")
    (root / "packages" / "ffmpeg" / "bin" / "ffprobe.exe").write_bytes(b"ffprobe")
    (root / ".runtime" / "python" / "python.exe").write_bytes(b"python")
    (root / "MOSS-TTS-Nano").mkdir(parents=True, exist_ok=True)


def test_preflight_detects_missing_release_files(tmp_path: Path) -> None:
    payload = collect_release_preflight(
        root=tmp_path,
        expect_portable_runtime=True,
        required_imports=[],
        optional_imports=[],
    )
    assert payload["ok"] is False
    codes = {item["code"] for item in payload["errors"]}
    assert "required_path_missing" in codes
    assert "portable_runtime_missing" in codes


def test_preflight_accepts_minimal_release_tree(tmp_path: Path) -> None:
    _create_minimal_release_tree(tmp_path)
    payload = collect_release_preflight(
        root=tmp_path,
        expect_portable_runtime=True,
        required_imports=[],
        optional_imports=[],
    )
    assert payload["ok"] is True
    assert payload["portable_runtime"]["exists"] is True


def test_preflight_reports_port_conflict(tmp_path: Path) -> None:
    import socket

    _create_minimal_release_tree(tmp_path)
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.bind(("127.0.0.1", 0))
    sock.listen(1)
    port = sock.getsockname()[1]
    try:
        payload = collect_release_preflight(
            root=tmp_path,
            port=port,
            expect_portable_runtime=True,
            require_port_available=True,
            required_imports=[],
            optional_imports=[],
        )
    finally:
        sock.close()
    assert payload["ok"] is False
    assert any(item["code"] == "port_in_use" for item in payload["errors"])


def test_preflight_api_returns_payload() -> None:
    client = TestClient(create_app())
    response = client.get("/api/preflight")
    assert response.status_code == 200
    payload = response.json()
    assert payload["schema"] == RELEASE_PREFLIGHT_SCHEMA
    assert "required_paths" in payload
