from __future__ import annotations

import json
from pathlib import Path

from smart_video_cut import recent_runs
from smart_video_cut.recent_runs import delete_recent_run


def test_delete_recent_run_removes_only_output_child(tmp_path: Path, monkeypatch) -> None:
    output_root = tmp_path / "output"
    run_dir = output_root / "case001"
    run_dir.mkdir(parents=True)
    result_json = run_dir / "local_studio_result.json"
    result_json.write_text(json.dumps({"ok": True}), encoding="utf-8")
    (run_dir / "final.mp4").write_bytes(b"video")
    monkeypatch.setattr(recent_runs, "OUTPUT_ROOT", output_root)

    result = delete_recent_run(result_json=str(result_json))

    assert result["ok"] is True
    assert not run_dir.exists()


def test_delete_recent_run_rejects_outside_output_root(tmp_path: Path, monkeypatch) -> None:
    output_root = tmp_path / "output"
    output_root.mkdir()
    outside = tmp_path / "other" / "local_studio_result.json"
    outside.parent.mkdir()
    outside.write_text("{}", encoding="utf-8")
    monkeypatch.setattr(recent_runs, "OUTPUT_ROOT", output_root)

    result = delete_recent_run(result_json=str(outside))

    assert result["ok"] is False
    assert outside.exists()
