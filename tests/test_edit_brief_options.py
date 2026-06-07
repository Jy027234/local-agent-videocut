from __future__ import annotations

import json
from pathlib import Path

from smart_video_cut.edit_brief import build_edit_brief
from smart_video_cut.models import StylePackageRequest
from smart_video_cut.style_package import create_style_package


def test_edit_brief_supports_no_subtitle_and_no_voice(tmp_path: Path) -> None:
    template = tmp_path / "sample.mp4"
    source = tmp_path / "input.mp4"
    template.write_bytes(b"sample")
    source.write_bytes(b"input")
    create_style_package(
        StylePackageRequest(
            name="Test Style",
            template_video=template,
            package_dir=tmp_path / "pkg",
        )
    )

    brief = build_edit_brief(
        style_package=tmp_path / "pkg",
        input_video=source,
        output_dir=tmp_path / "out",
        user_request="不要字幕，不要配音。",
        settings_overrides={
            "subtitle": {"enabled": False, "mode": "none"},
            "voice": {"provider": "none", "mode": "none"},
        },
    )

    assert "不添加内容字幕" in brief["brief_text"]
    assert "不加新配音" in brief["brief_text"]
    assert any("本次不添加内容字幕" in item for item in brief["checklist"])


def test_edit_brief_includes_custom_subtitle_prompt_and_location(tmp_path: Path) -> None:
    template = tmp_path / "sample.mp4"
    source = tmp_path / "input.mp4"
    template.write_bytes(b"sample")
    source.write_bytes(b"input")
    create_style_package(
        StylePackageRequest(
            name="Test Style",
            template_video=template,
            package_dir=tmp_path / "pkg",
        )
    )

    brief = build_edit_brief(
        style_package=tmp_path / "pkg",
        input_video=source,
        output_dir=tmp_path / "out",
        user_request="按位置做字幕。",
        settings_overrides={
            "subtitle": {
                "enabled": True,
                "mode": "custom",
                "custom_prompt": "突出客厅门安装记录",
                "location_info": "同家庄镇张庄村",
            }
        },
    )

    assert "字幕要求：突出客厅门安装记录" in brief["brief_text"]
    assert "位置信息：同家庄镇张庄村" in brief["brief_text"]


def test_edit_brief_uses_package_specific_filmgen_copy(tmp_path: Path) -> None:
    template = tmp_path / "sample.mp4"
    source = tmp_path / "input.mp4"
    template.write_bytes(b"sample")
    source.write_bytes(b"input")
    create_style_package(
        StylePackageRequest(
            name="FilmGen Test Style",
            template_video=template,
            package_dir=tmp_path / "pkg",
        )
    )
    package_json = tmp_path / "pkg" / "style_package.json"
    payload = json.loads(package_json.read_text(encoding="utf-8"))
    payload["edit_brief"] = {
        "reference_sentence": "参考风格：使用《{package_name}》服务分镜情绪。",
        "source_sentence": "原始素材：共 {count} 个已批准视频，将按关键动作和情绪节奏组织。",
        "visual_priority": "画面优先保持人物关系和动作连贯",
        "role_labels": {"opening_hero": "开场情绪 / 主要动作 / 结尾停留"},
        "checklist": ["人物关系要自然。"],
    }
    package_json.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

    brief = build_edit_brief(
        style_package=tmp_path / "pkg",
        input_video=source,
        output_dir=tmp_path / "out",
        user_request="5秒爱情镜头。",
    )

    assert "关键动作和情绪节奏" in brief["brief_text"]
    assert "开场情绪 / 主要动作 / 结尾停留" in brief["brief_text"]
    assert "安装效果" not in brief["brief_text"]
    assert brief["checklist"] == ["人物关系要自然。"]
