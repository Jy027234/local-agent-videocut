from __future__ import annotations

from pathlib import Path

from video_editing_toolkit.creative_edit_runner import (
    WorkerRenderRequest,
    WorkerRenderResult,
    _ffmpeg_filter_complex,
    run_creative_edit_runner,
)


def test_worker_render_request_receives_renderer_settings(tmp_path: Path) -> None:
    captured: dict[str, WorkerRenderRequest] = {}
    media = tmp_path / "input.mp4"
    media.write_bytes(b"fake media")

    def fake_executor(request: WorkerRenderRequest) -> WorkerRenderResult:
        captured["request"] = request
        return WorkerRenderResult(
            state="completed",
            evidence={"renderer_settings_seen": True},
            media_decode_or_render_performed=True,
        )

    summary = run_creative_edit_runner(
        artifact_root=tmp_path / "artifacts",
        execution_mode="worker_real_render",
        execute_real_render=True,
        worker_media_input=media,
        worker_render_width=1920,
        worker_render_height=1080,
        worker_render_aspect_ratio="16:9",
        worker_render_fps=60,
        worker_video_crf=18,
        worker_subtitle_font_size=58,
        worker_subtitle_font_color="yellow",
        worker_subtitle_outline_color="black",
        worker_subtitle_outline_width=7,
        worker_bgm_volume_db=-12,
        worker_voice_volume_db=-3,
        render_executor=fake_executor,
    )

    request = captured["request"]
    assert summary["ok"] is True
    assert request.render_width == 1920
    assert request.render_height == 1080
    assert request.render_aspect_ratio == "16:9"
    assert request.render_fps == 60
    assert request.video_crf == 18
    assert request.subtitle_font_size == 58
    assert request.subtitle_font_color == "yellow"
    assert request.subtitle_outline_width == 7
    assert request.bgm_volume_db == -12
    assert request.voice_volume_db == -3


def test_ffmpeg_filter_uses_dynamic_resolution_subtitle_and_volume() -> None:
    filter_complex = _ffmpeg_filter_complex(
        target_duration_seconds=9,
        include_voice=True,
        render_width=1920,
        render_height=1080,
        render_fps=60,
        subtitle_font_size=58,
        subtitle_font_color="yellow",
        subtitle_outline_color="black",
        subtitle_outline_width=7,
        bgm_volume_db=-12,
        voice_volume_db=-3,
    )

    assert "crop=1920:1080" in filter_complex
    assert "fps=60" in filter_complex
    assert "fontsize=58:fontcolor=yellow:borderw=7:bordercolor=black" in filter_complex
    assert "volume=0.251189[bgm]" in filter_complex
    assert "volume=0.707946[voice]" in filter_complex
