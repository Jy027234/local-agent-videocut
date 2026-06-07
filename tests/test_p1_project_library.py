from __future__ import annotations

from pathlib import Path

from smart_video_cut.folder_scanner import scan_media_folder, scan_output_folder
from smart_video_cut.project_library import (
    index_project_manifest,
    list_project_library,
    record_repair_thread,
    rebuild_project_library,
)
from smart_video_cut.project_manifest import write_project_manifest


def test_project_library_indexes_manifest_and_rebuilds(tmp_path: Path) -> None:
    db_path = tmp_path / "studio.sqlite3"
    output_dir = tmp_path / "output" / "case-1"
    manifest = write_project_manifest(
        output_dir=output_dir,
        result={
            "project_id": "case-1",
            "ok": True,
            "style_package": {"name": "Door Flash", "path": "packages/door"},
            "input_videos": ["a.mp4", "b.mp4"],
            "copied_output_video": str(output_dir / "final.mp4"),
            "user_request": "防盗门快闪",
            "execute_real_render": True,
        },
        event="test",
    )

    indexed = index_project_manifest(output_dir=output_dir, manifest=manifest, db_path=db_path)
    listed = list_project_library(db_path=db_path, query="Door")
    rebuilt = rebuild_project_library(output_root=tmp_path / "output", db_path=db_path)

    assert indexed["ok"] is True
    assert listed["project_count"] == 1
    assert listed["projects"][0]["style_package_name"] == "Door Flash"
    assert listed["projects"][0]["input_video_count"] == 2
    assert rebuilt["indexed_count"] == 1


def test_repair_thread_is_recorded_in_project_library(tmp_path: Path) -> None:
    db_path = tmp_path / "studio.sqlite3"

    result = record_repair_thread(
        output_dir=tmp_path / "out",
        base_version=2,
        user_feedback="字幕更大",
        result={"ok": True, "new_version": 3, "status": "pending_re_render"},
        db_path=db_path,
    )

    assert result["ok"] is True
    assert result["repair_thread"]["base_version"] == 2
    assert result["repair_thread"]["version"] == 3


def test_folder_scanner_finds_input_media_and_output_projects(tmp_path: Path) -> None:
    media_dir = tmp_path / "media"
    media_dir.mkdir()
    (media_dir / "a.mp4").write_bytes(b"video")
    (media_dir / "b.wav").write_bytes(b"audio")
    (media_dir / "c.png").write_bytes(b"image")
    input_scan = scan_media_folder(folder=media_dir)

    output_dir = tmp_path / "output" / "case"
    write_project_manifest(
        output_dir=output_dir,
        result={"project_id": "case", "ok": True, "style_package": {"name": "Style"}},
    )
    output_scan = scan_output_folder(folder=tmp_path / "output")

    assert input_scan["ok"] is True
    assert input_scan["category_counts"]["video"] == 1
    assert input_scan["category_counts"]["audio"] == 1
    assert input_scan["category_counts"]["image"] == 1
    assert output_scan["project_count"] == 1
    assert output_scan["projects"][0]["project_id"] == "case"
