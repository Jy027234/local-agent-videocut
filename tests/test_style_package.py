from __future__ import annotations

from pathlib import Path

from smart_video_cut.models import StylePackageRequest
from smart_video_cut.style_package import (
    create_style_package,
    default_settings_from_options,
    load_style_package,
    reference_template_path,
)


def test_create_and_load_style_package(tmp_path: Path) -> None:
    template = tmp_path / "sample.mp4"
    template.write_bytes(b"fake mp4 bytes")
    settings = default_settings_from_options(
        duration=15,
        aspect_ratio="9:16",
        resolution="720x1280",
        quality="high",
        subtitle_size=48,
        bgm_volume_db=-18,
        voice_provider="edge_tts",
    )

    payload = create_style_package(
        StylePackageRequest(
            name="Door Flash",
            template_video=template,
            package_dir=tmp_path / "pkg",
            settings=settings,
        )
    )
    loaded = load_style_package(tmp_path / "pkg")
    ref_path = reference_template_path(tmp_path / "pkg", loaded)

    assert payload["schema"] == "smart_video_cut.local.style_package.v0"
    assert loaded["visible_settings"]["video"]["target_duration_seconds"] == 15
    assert loaded["visible_settings"]["video"]["crf"] == 18
    assert loaded["visible_settings"]["subtitle"]["font_size"] == 48
    assert loaded["reference_analysis"]["schema"] == "smart_video_cut.local.template_video_analysis.v0"
    assert loaded["timeline_template"]["analysis_source"] == "reference_template_video"
    assert loaded["timeline_template"]["target_duration_seconds"] == 15
    assert loaded["reuse_policy"]["do_not_reimplement_toolkit_capabilities"] is True
    assert ref_path is not None
    assert ref_path.read_bytes() == b"fake mp4 bytes"
