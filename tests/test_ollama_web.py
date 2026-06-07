from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from smart_video_cut import local_config
from smart_video_cut.web_app import create_app


class FakeHttpResponse:
    def __init__(self, payload: str) -> None:
        self.payload = payload.encode("utf-8")

    def __enter__(self) -> "FakeHttpResponse":
        return self

    def __exit__(self, *args) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def test_ollama_models_api_lists_local_models(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        if request.full_url.endswith("/api/version"):
            return FakeHttpResponse('{"version":"0.5.0"}')
        if request.full_url.endswith("/api/tags"):
            return FakeHttpResponse(
                '{"models":[{"name":"qwen2.5:7b","size":456,"details":{"parameter_size":"7B"}}]}'
            )
        raise AssertionError(request.full_url)

    monkeypatch.setattr(local_config.urllib.request, "urlopen", fake_urlopen)
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.get("/api/ollama/models", params={"base_url": "http://127.0.0.1:11434/v1"})
    payload = response.json()

    assert response.status_code == 200
    assert payload["schema"] == "smart_video_cut.local.ollama_models.v0"
    assert payload["ok"] is True
    assert payload["selected_model"] == "qwen2.5:7b"
    assert payload["openai_base_url"] == "http://127.0.0.1:11434/v1"


def test_ollama_apply_api_saves_local_llm_config(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(local_config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(local_config, "LLM_CONFIG_PATH", tmp_path / "llm_config.json")
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/ollama/apply",
        json={"model": "qwen2.5:7b", "base_url": "http://127.0.0.1:11434"},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["ok"] is True
    assert payload["config"]["provider"] == "local_ollama"
    assert payload["config"]["model"] == "qwen2.5:7b"
    assert payload["config"]["allow_cloud_llm_for_text_only"] is False
