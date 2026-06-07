from __future__ import annotations

from pathlib import Path

from fastapi.testclient import TestClient

from smart_video_cut.bgm_library import build_bgm_library_playlist, scan_bgm_library
from smart_video_cut.web_app import create_app


def test_scan_bgm_library_recommends_matching_audio(tmp_path: Path) -> None:
    library = tmp_path / "music"
    library.mkdir()
    (library / "door_flash_upbeat.wav").write_bytes(b"audio")
    (library / "ambient_soft.mp3").write_bytes(b"audio")
    (library / "notes.txt").write_text("ignore", encoding="utf-8")

    result = scan_bgm_library(library_dir=library, query="快闪", style="product_flash")

    assert result["schema"] == "smart_video_cut.local.bgm_library.v0"
    assert result["ok"] is True
    assert result["item_count"] == 2
    assert result["recommended"]["name"] == "door_flash_upbeat.wav"
    assert "matched_terms" in result["recommended"]["match_reason"]


def test_scan_bgm_library_reports_missing_dir(tmp_path: Path) -> None:
    result = scan_bgm_library(library_dir=tmp_path / "missing")

    assert result["ok"] is False
    assert result["reason"] == "library_dir_not_found"
    assert result["items"] == []


def test_bgm_library_api(tmp_path: Path) -> None:
    library = tmp_path / "music"
    library.mkdir()
    (library / "clean_vlog.wav").write_bytes(b"audio")
    client = TestClient(create_app(), raise_server_exceptions=False)

    payload = client.post(
        "/api/bgm/library",
        json={"library_dir": str(library), "style": "clean_vlog"},
    ).json()

    assert payload["schema"] == "smart_video_cut.local.bgm_library.v0"
    assert payload["ok"] is True
    assert payload["recommended"]["name"] == "clean_vlog.wav"


def test_bgm_library_playlist_writes_batch_preview_manifest(tmp_path: Path) -> None:
    library = tmp_path / "music"
    library.mkdir()
    (library / "door_flash_upbeat.wav").write_bytes(b"audio")
    playlist_path = tmp_path / "playlist.json"

    payload = build_bgm_library_playlist(
        library_dir=library,
        query="快闪",
        style="product_flash",
        output_path=playlist_path,
    )

    assert payload["schema"] == "smart_video_cut.local.bgm_library_playlist.v0"
    assert payload["ok"] is True
    assert payload["playlist_path"] == str(playlist_path)
    assert payload["items"][0]["selected"] is True
    assert payload["items"][0]["preview_api"].startswith("/api/media-preview")
    assert playlist_path.is_file()


def test_bgm_library_playlist_api(tmp_path: Path) -> None:
    library = tmp_path / "music"
    library.mkdir()
    (library / "premium.wav").write_bytes(b"audio")
    client = TestClient(create_app(), raise_server_exceptions=False)

    payload = client.post(
        "/api/bgm/library/playlist",
        json={"library_dir": str(library), "style": "premium", "limit": 4},
    ).json()

    assert payload["schema"] == "smart_video_cut.local.bgm_library_playlist.v0"
    assert payload["ok"] is True
    assert payload["recommended"]["name"] == "premium.wav"
