from __future__ import annotations

from pathlib import Path

from smart_video_cut import local_config


class FakeHttpResponse:
    def __init__(self, payload: str) -> None:
        self.payload = payload.encode("utf-8")

    def __enter__(self) -> "FakeHttpResponse":
        return self

    def __exit__(self, *args) -> None:
        return None

    def read(self) -> bytes:
        return self.payload


def test_llm_config_masks_api_key(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(local_config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(local_config, "LLM_CONFIG_PATH", tmp_path / "llm_config.json")

    saved = local_config.save_llm_config(
        {
            "provider": "openai_compatible",
            "base_url": "https://example.test/v1",
            "model": "test-model",
            "recommendation_profile": "visual_review_recommended",
            "model_capability": "multimodal_text_image",
            "api_key": "secret-token",
        }
    )

    assert saved["ok"] is True
    assert saved["config"]["api_key_set"] is True
    assert saved["config"]["api_key"] == ""
    assert saved["config"]["recommendation_profile"] == "visual_review_recommended"
    assert saved["config"]["model_capability"] == "multimodal_text_image"
    assert local_config.load_llm_config(masked=False)["api_key"] == "secret-token"


def test_local_ollama_config_normalizes_base_url_and_cloud_flags(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(local_config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(local_config, "LLM_CONFIG_PATH", tmp_path / "llm_config.json")

    saved = local_config.save_llm_config(
        {
            "provider": "local_ollama",
            "base_url": "http://127.0.0.1:11434/v1",
            "model": "qwen2.5:7b",
            "api_key": "should-be-cleared",
            "allow_cloud_llm_for_text_only": True,
        }
    )
    raw = local_config.load_llm_config(masked=False)

    assert saved["config"]["provider"] == "local_ollama"
    assert saved["config"]["base_url"] == "http://127.0.0.1:11434/v1"
    assert saved["config"]["api_key_set"] is False
    assert saved["config"]["allow_cloud_llm_for_text_only"] is False
    assert raw["api_key"] == ""


def test_llm_test_preflight_requires_model(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(local_config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(local_config, "LLM_CONFIG_PATH", tmp_path / "llm_config.json")

    result = local_config.test_llm_config(
        {
            "provider": "openai_compatible",
            "base_url": "https://example.test/v1",
            "api_key": "secret-token",
            "model": "",
        }
    )

    assert result["ok"] is False
    assert result["reason"] == "missing_model"


def test_ollama_status_and_model_listing_use_native_api(monkeypatch) -> None:
    def fake_urlopen(request, timeout):
        url = request.full_url
        if url.endswith("/api/version"):
            return FakeHttpResponse('{"version":"0.5.0"}')
        if url.endswith("/api/tags"):
            return FakeHttpResponse(
                '{"models":['
                '{"name":"llama3.2:3b","size":123,"details":{"parameter_size":"3B"}},'
                '{"name":"qwen2.5:7b","size":456,"details":{"parameter_size":"7B"}}'
                ']}'
            )
        raise AssertionError(url)

    monkeypatch.setattr(local_config.urllib.request, "urlopen", fake_urlopen)

    status = local_config.check_ollama_status("http://127.0.0.1:11434/v1")
    models = local_config.list_ollama_models("http://127.0.0.1:11434/v1")

    assert status["ok"] is True
    assert status["base_url"] == "http://127.0.0.1:11434"
    assert status["openai_base_url"] == "http://127.0.0.1:11434/v1"
    assert models["ok"] is True
    assert models["model_count"] == 2
    assert models["selected_model"] == "qwen2.5:7b"
    assert models["models"][0]["name"] == "qwen2.5:7b"


def test_save_ollama_llm_config_writes_local_first_profile(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(local_config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(local_config, "LLM_CONFIG_PATH", tmp_path / "llm_config.json")

    result = local_config.save_ollama_llm_config(
        {
            "model": "llava:7b",
            "base_url": "http://localhost:11434",
        }
    )
    raw = local_config.load_llm_config(masked=False)

    assert result["ok"] is True
    assert raw["provider"] == "local_ollama"
    assert raw["base_url"] == "http://localhost:11434/v1"
    assert raw["model"] == "llava:7b"
    assert raw["recommendation_profile"] == "local_first"
    assert raw["api_key"] == ""


def test_recommended_voice_model_check(tmp_path: Path, monkeypatch) -> None:
    install_dir = tmp_path / "MOSS-TTS-Nano"
    install_dir.mkdir()
    (install_dir / "README.md").write_text("MOSS-TTS-Nano", encoding="utf-8")

    monkeypatch.setattr(local_config, "CONFIG_DIR", tmp_path)
    monkeypatch.setattr(local_config, "VOICE_MODEL_CONFIG_PATH", tmp_path / "voice_model_config.json")

    saved = local_config.save_voice_model_config(
        {
            "provider_id": "moss_tts_nano",
            "display_name": "MOSS-TTS-Nano",
            "repo_url": "https://github.com/OpenMOSS/MOSS-TTS-Nano.git",
            "install_dir": str(install_dir),
            "enabled": True,
        }
    )

    assert saved["ok"] is True
    assert saved["config"]["installed"] is True
    assert "git clone https://github.com/OpenMOSS/MOSS-TTS-Nano.git" in saved["config"]["install_command"]


def test_local_config_summary_exposes_beginner_paths(tmp_path: Path, monkeypatch) -> None:
    workspace_dir = tmp_path / "workspace"
    output_root = workspace_dir / "output"
    packages_dir = tmp_path / "packages"
    voice_samples_dir = workspace_dir / "voice_samples"
    protocol_dropbox_root = workspace_dir / "protocol_dropbox"

    monkeypatch.setattr(local_config, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(local_config, "WORKSPACE_DIR", workspace_dir)
    monkeypatch.setattr(local_config, "CONFIG_DIR", workspace_dir / "config")
    monkeypatch.setattr(local_config, "OUTPUT_ROOT", output_root)
    monkeypatch.setattr(local_config, "PACKAGES_DIR", packages_dir)
    monkeypatch.setattr(local_config, "VOICE_SAMPLES_DIR", voice_samples_dir)
    monkeypatch.setattr(local_config, "PROTOCOL_DROPBOX_ROOT", protocol_dropbox_root)
    monkeypatch.setattr(local_config, "load_llm_config", lambda masked=True: {"provider": "openai_compatible"})
    monkeypatch.setattr(local_config, "check_voice_model", lambda: {"display_name": "MOSS-TTS-Nano"})

    summary = local_config.load_local_config_summary()

    assert summary["paths"]["root_dir"] == str(tmp_path)
    assert summary["paths"]["workspace_dir"] == str(workspace_dir)
    assert summary["paths"]["output_root"] == str(output_root)
    assert summary["paths"]["packages_dir"] == str(packages_dir)
    assert summary["paths"]["voice_samples_dir"] == str(voice_samples_dir)
    assert summary["paths"]["protocol_dropbox_root"] == str(protocol_dropbox_root)
    assert summary["paths"]["default_output_dir"] == str(output_root / "case001")
    assert summary["paths"]["default_protocol_path"] == str((output_root / "case001") / "local_toolkit_protocol.json")
