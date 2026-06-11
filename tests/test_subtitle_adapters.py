from __future__ import annotations

import json
from pathlib import Path

from smart_video_cut.subtitle_adapters import (
    load_filmgen_subtitle_handoff,
    prepare_subtitles,
    subtitle_texts_from_settings,
    validate_filmgen_subtitle_handoff,
)
from smart_video_cut.web_app import create_app


def test_subtitle_none_disables_renderer_inputs() -> None:
    result = prepare_subtitles(subtitle_settings={"enabled": False, "mode": "none"})

    assert result["schema"] == "smart_video_cut.local.subtitle_adapter_result.v0"
    assert result["adapter_id"] == "subtitle.none"
    assert result["ok"] is True
    assert result["skipped"] is True
    assert result["renderer_subtitle_enabled"] is False
    assert result["renderer_subtitle_texts"] == []


def test_custom_subtitle_text_splits_prompt_and_location() -> None:
    settings = {
        "enabled": True,
        "mode": "custom",
        "location_info": "同家庄镇张庄村",
        "custom_prompt": "突出门体安装；强调锁具细节，结尾显示质保",
        "preserve_onscreen_text": False,
    }

    result = prepare_subtitles(subtitle_settings=settings)

    assert result["adapter_id"] == "subtitle.custom_text"
    assert result["subtitle_texts"] == ["同家庄镇张庄村", "突出门体安装", "强调锁具细节", "结尾显示质保"]
    assert result["renderer_subtitle_texts"] == result["subtitle_texts"]
    assert result["renderer_subtitle_enabled"] is True
    assert result["onscreen_text_policy"] == "allow_regenerate"
    assert subtitle_texts_from_settings(settings) == result["subtitle_texts"]


def test_auto_subtitle_prompt_keeps_renderer_enabled_without_extra_text() -> None:
    result = prepare_subtitles(subtitle_settings={"enabled": True, "mode": "auto"})

    assert result["adapter_id"] == "subtitle.auto_prompt"
    assert result["renderer_subtitle_enabled"] is True
    assert result["renderer_subtitle_texts"] == []
    assert result["onscreen_text_policy"] == "preserve_existing"


def test_filmgen_subtitle_adapter_writes_handoff_file(tmp_path: Path) -> None:
    result = prepare_subtitles(
        subtitle_settings={
            "enabled": True,
            "mode": "filmgen",
            "location_info": "同家庄镇张庄村",
            "custom_prompt": "第一幕显示安装环境；第二幕强调锁具细节",
            "font_size": 48,
            "font_color": "yellow",
            "outline_width": 6,
            "preserve_onscreen_text": False,
        },
        artifact_root=tmp_path / "artifacts",
    )

    assert result["adapter_id"] == "subtitle.filmgen"
    assert result["ok"] is True
    assert result["skipped"] is False
    assert result["reason"] == "filmgen_subtitle_handoff"
    assert result["renderer_subtitle_enabled"] is False
    assert result["subtitle_texts"] == ["同家庄镇张庄村", "第一幕显示安装环境", "第二幕强调锁具细节"]

    handoff_path = Path(result["handoff_path"])
    payload = json.loads(handoff_path.read_text(encoding="utf-8"))
    assert handoff_path.is_file()
    assert payload["schema"] == "smart_video_cut.local.filmgen_subtitle_handoff.v0"
    assert payload["handoff_path"] == str(handoff_path)
    assert payload["style"]["font_size"] == 48
    assert payload["style"]["font_color"] == "yellow"
    assert payload["renderer_contract"]["current_renderer_subtitle_enabled"] is False
    assert payload["renderer_contract"]["onscreen_text_policy"] == "allow_regenerate"


def test_filmgen_subtitle_handoff_preview_validates_file(tmp_path: Path) -> None:
    result = prepare_subtitles(
        subtitle_settings={
            "enabled": True,
            "mode": "filmgen",
            "location_info": "同家庄镇张庄村",
            "custom_prompt": "第一幕显示安装环境",
        },
        artifact_root=tmp_path / "artifacts",
    )

    preview = load_filmgen_subtitle_handoff(result["handoff_path"])

    assert preview["schema"] == "smart_video_cut.local.filmgen_subtitle_handoff_preview.v0"
    assert preview["ok"] is True
    assert preview["subtitle_text_count"] == 2
    assert preview["validation"]["valid"] is True
    assert preview["import_contract"]["external_center"].startswith("External")


def test_filmgen_subtitle_handoff_validation_reports_errors() -> None:
    validation = validate_filmgen_subtitle_handoff({"schema": "unknown"})

    assert validation["valid"] is False
    assert any(item["code"] == "unsupported_schema" for item in validation["errors"])
    assert any(item["code"] == "style_missing" for item in validation["errors"])


def test_filmgen_subtitle_handoff_preview_api(tmp_path: Path) -> None:
    result = prepare_subtitles(
        subtitle_settings={"enabled": True, "mode": "filmgen", "custom_prompt": "字幕一"},
        artifact_root=tmp_path / "artifacts",
    )
    client = create_app().test_client() if hasattr(create_app(), "test_client") else None
    if client is None:
        from fastapi.testclient import TestClient

        client = TestClient(create_app())

    response = client.post(
        "/api/filmgen/subtitle-handoff/preview",
        json={"handoff_path": result["handoff_path"]},
    )

    assert response.status_code == 200
    assert response.json()["ok"] is True
