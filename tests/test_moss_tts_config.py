from __future__ import annotations

from pathlib import Path

from smart_video_cut import moss_tts


def test_moss_status_detects_repo_without_venv(tmp_path: Path) -> None:
    repo = tmp_path / "MOSS-TTS-Nano"
    repo.mkdir()
    (repo / "infer_onnx.py").write_text("", encoding="utf-8")
    (repo / "pyproject.toml").write_text("", encoding="utf-8")

    status = moss_tts.check_moss_tts_status(repo)

    assert status["repo_found"] is True
    assert status["venv_exists"] is False
    assert status["ready"] is False
    assert "py -3.12 -m venv" in status["setup_command"]


def test_moss_status_lists_builtin_voices_when_manifest_exists(tmp_path: Path) -> None:
    repo = tmp_path / "MOSS-TTS-Nano"
    manifest_dir = repo / "models" / moss_tts.MOSS_TTS_MODEL_DIR_NAME
    manifest_dir.mkdir(parents=True)
    (repo / "infer_onnx.py").write_text("", encoding="utf-8")
    (repo / "pyproject.toml").write_text("", encoding="utf-8")
    (manifest_dir / "browser_poc_manifest.json").write_text(
        '{"builtin_voices":[{"voice":"Zhiming","display_name":"CN 京味胡同闲聊","group":"Chinese Male"}]}',
        encoding="utf-8",
    )

    status = moss_tts.check_moss_tts_status(repo)

    assert status["builtin_voices"][0]["voice"] == "Zhiming"


def test_moss_synthesize_blocks_when_runtime_missing(tmp_path: Path) -> None:
    repo = tmp_path / "MOSS-TTS-Nano"
    repo.mkdir()
    (repo / "infer_onnx.py").write_text("", encoding="utf-8")
    (repo / "pyproject.toml").write_text("", encoding="utf-8")

    result = moss_tts.synthesize_moss_tts(
        text="测试",
        output_audio_path=tmp_path / "out.wav",
        install_dir=repo,
    )

    assert result["ok"] is False
    assert result["reason"] == "moss_tts_runtime_not_ready"


def test_moss_synthesize_passes_generation_controls(tmp_path: Path, monkeypatch) -> None:
    repo = tmp_path / "MOSS-TTS-Nano"
    repo.mkdir()
    output = tmp_path / "sample.wav"
    captured: list[list[str]] = []

    monkeypatch.setattr(moss_tts, "resolve_moss_repo", lambda install_dir=None: repo)
    monkeypatch.setattr(moss_tts, "moss_venv_python", lambda repo_dir=None: repo / ".venv" / "Scripts" / "python.exe")
    monkeypatch.setattr(moss_tts, "_ensure_runtime_model_dir", lambda repo_dir: repo / "models")
    monkeypatch.setattr(
        moss_tts,
        "check_moss_tts_status",
        lambda install_dir=None: {"can_synthesize_now": True, "ready": True},
    )

    def fake_run(command: list[str], *, cwd: Path, timeout_seconds: int) -> dict[str, object]:
        captured.append(command)
        output.write_bytes(b"0" * 1200)
        return {"returncode": 0, "stdout": "", "stderr": ""}

    monkeypatch.setattr(moss_tts, "_run", fake_run)

    result = moss_tts.synthesize_moss_tts(
        text="测试",
        output_audio_path=output,
        voice="Zhiming",
        sample_mode="greedy",
        text_temperature=0.7,
        audio_temperature=0.5,
        seed=2026,
    )

    command = captured[0]
    assert result["ok"] is True
    assert command[command.index("--voice") + 1] == "Zhiming"
    assert command[command.index("--sample-mode") + 1] == "greedy"
    assert command[command.index("--do-sample") + 1] == "0"
    assert command[command.index("--text-temperature") + 1] == "0.7"
    assert command[command.index("--audio-temperature") + 1] == "0.5"
    assert command[command.index("--seed") + 1] == "2026"
