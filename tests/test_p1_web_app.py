from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from smart_video_cut.project_manifest import write_project_manifest
from smart_video_cut.version_history import save_version
from smart_video_cut.web_app import create_app


def test_p1_project_library_and_folder_scan_endpoints(tmp_path: Path) -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)
    output_root = tmp_path / "output"
    output_dir = output_root / "case"
    final_video = output_dir / "final.mp4"
    final_video.parent.mkdir(parents=True)
    final_video.write_bytes(b"video")
    write_project_manifest(
        output_dir=output_dir,
        result={
            "project_id": "p1-case",
            "ok": True,
            "style_package": {"name": "P1 Style"},
            "copied_output_video": str(final_video),
            "input_videos": [str(final_video)],
        },
    )

    rebuild = client.post("/api/projects/rebuild", json={"output_root": str(output_root), "limit": 20})
    projects = client.get("/api/projects", params={"query": "P1 Style"})
    scan = client.post("/api/folders/scan", json={"folder": str(output_root), "scan_type": "output"})

    assert rebuild.status_code == 200
    assert rebuild.json()["indexed_count"] == 1
    assert projects.status_code == 200
    assert any(project["project_id"] == "p1-case" for project in projects.json()["projects"])
    assert scan.status_code == 200
    assert scan.json()["project_count"] == 1


def test_p1_repair_dialogue_endpoint_creates_pending_version(tmp_path: Path) -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)
    output_dir = tmp_path / "repair-case"
    save_version(
        output_dir=output_dir,
        timeline={"schema": "smart_video_cut.local.timeline_plan.v1", "segments": []},
        brief={"user_request": "base"},
        result={"ok": True},
    )
    write_project_manifest(output_dir=output_dir, result={"project_id": "repair-case", "ok": True})

    response = client.post(
        "/api/repair-dialogue",
        json={
            "output_dir": str(output_dir),
            "base_version": 1,
            "user_feedback": "字幕再大一点",
            "timeline_edits": [],
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["status"] == "pending_re_render"
    assert payload["new_version"] == 2
    assert payload["repair_thread"]["user_feedback"] == "字幕再大一点"


def test_p1_deployment_guide_endpoint() -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/api/deployment/guide")
    payload = response.json()

    assert response.status_code == 200
    assert payload["schema"] == "smart_video_cut.local.deployment_guide.v0"
    assert "ffmpeg" in payload
    assert "desktop_shell" in payload
    assert payload["desktop_shell"]["electron"]["ready"] is True
    assert "package:win" in payload["desktop_shell"]["electron"]["package_command"]
