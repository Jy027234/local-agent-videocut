from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from smart_video_cut.web_app import create_app


def test_template_analyze_api_returns_reference_analysis(tmp_path: Path) -> None:
    template = tmp_path / "template.mp4"
    template.write_bytes(b"fake mp4")
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/template/analyze",
        json={"template_video": str(template), "output_dir": str(tmp_path / "analysis")},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["schema"] == "smart_video_cut.local.template_video_analysis.v0"
    assert payload["ok"] is True
    assert "subtitles" in payload
    assert "cover" in payload
    assert "bgm" in payload
    assert "rhythm" in payload
    assert "timeline_template" in payload
