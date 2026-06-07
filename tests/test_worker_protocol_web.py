from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from smart_video_cut.web_app import create_app


def test_worker_package_api_creates_and_runs_completion(tmp_path: Path, monkeypatch) -> None:
    def fake_run_edit(task):
        task.output_dir.mkdir(parents=True, exist_ok=True)
        (task.output_dir / "local_studio_result.json").write_text("{}", encoding="utf-8")
        return {"ok": True, "toolkit_status": "plan_only", "current_version": 1}

    monkeypatch.setattr("smart_video_cut.worker_protocol.run_edit_with_style_package", fake_run_edit)
    client = TestClient(create_app(), raise_server_exceptions=False)

    create_response = client.post(
        "/api/worker/package",
        json={
            "package_dir": str(tmp_path / "worker-job"),
            "style_package": "packages/door",
            "input_video": "input.mp4",
            "output_dir": str(tmp_path / "out"),
            "user_request": "防盗门快闪广告",
            "confirmed_brief": "先稳镜头，再切细节特写",
            "task_id": "web_worker_001",
        },
    )
    created = create_response.json()

    assert create_response.status_code == 200
    assert created["schema"] == "smart_video_cut.local.worker_task_package.v0"
    assert Path(created["package_path"]).is_file()

    load_response = client.post("/api/worker/package/load", json={"package_path": created["package_path"]})
    loaded = load_response.json()

    assert load_response.status_code == 200
    assert loaded["ok"] is True
    assert loaded["task_package"]["task"]["style_package"].replace("\\", "/") == "packages/door"
    assert loaded["task_package"]["task"]["confirmed_brief"] == "先稳镜头，再切细节特写"
    assert loaded["task_package"]["task"]["task_id"] == "web_worker_001"

    run_response = client.post("/api/worker/run", json={"package_path": created["package_path"]})
    completion = run_response.json()

    assert run_response.status_code == 200
    assert completion["schema"] == "smart_video_cut.local.worker_completion.v0"
    assert completion["ok"] is True
    assert completion["task_id"] == "web_worker_001"
    assert Path(completion["completion_path"]).is_file()
