from __future__ import annotations

import json
from pathlib import Path

from smart_video_cut.template_analysis import analyze_template_video


class Completed:
    def __init__(self, stdout: str = "", returncode: int = 0) -> None:
        self.stdout = stdout
        self.returncode = returncode


def test_template_analysis_uses_ffprobe_metadata_and_extracts_cover(tmp_path: Path) -> None:
    video = tmp_path / "reference.mp4"
    video.write_bytes(b"video")

    probe_payload = {
        "format": {"duration": "12.4"},
        "streams": [
            {"codec_type": "video", "width": 1920, "height": 1080, "avg_frame_rate": "30/1"},
            {"codec_type": "audio", "sample_rate": "48000", "channels": 2},
            {"codec_type": "subtitle", "codec_name": "mov_text"},
        ],
    }

    def ffprobe_runner(args: list[str], timeout: int) -> Completed:
        return Completed(stdout=json.dumps(probe_payload), returncode=0)

    def ffmpeg_runner(args: list[str], timeout: int) -> Completed:
        Path(args[-1]).write_bytes(b"jpg")
        return Completed(returncode=0)

    result = analyze_template_video(
        video,
        output_dir=tmp_path / "analysis",
        ffprobe_runner=ffprobe_runner,
        ffmpeg_runner=ffmpeg_runner,
    )

    assert result["schema"] == "smart_video_cut.local.template_video_analysis.v0"
    assert result["ok"] is True
    assert result["video"]["aspect_ratio"] == "16:9"
    assert result["video"]["duration_seconds"] == 12.4
    assert result["subtitles"]["embedded_subtitle_streams"] == 1
    assert result["bgm"]["has_audio"] is True
    assert result["cover"]["extracted_frame_path"]
    assert Path(result["cover"]["extracted_frame_path"]).is_file()
    assert result["timeline_template"]["segment_blueprint"]


def test_template_analysis_falls_back_when_probe_fails(tmp_path: Path) -> None:
    video = tmp_path / "fake.mp4"
    video.write_bytes(b"not a real mp4")

    result = analyze_template_video(video)

    assert result["ok"] is True
    assert result["reason"] == "heuristic_analysis_completed"
    assert result["video"]["duration_seconds"] == 20.0
    assert result["style_suggestions"]["video"]["aspect_ratio"] == "9:16"
    assert any(item["code"] == "ffprobe_unavailable_or_failed" for item in result["warnings"])
