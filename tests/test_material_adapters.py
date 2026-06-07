from __future__ import annotations

from pathlib import Path
from typing import Any

from smart_video_cut.material_adapters import prepare_material_plan


def test_material_adapter_can_force_order_fallback(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_builder(paths, **kwargs):
        captured.update(kwargs)
        return _plan(paths, strategy="order_fallback_role_assignment", visual_available=False)

    result = prepare_material_plan(
        paths=[tmp_path / "a.mp4", tmp_path / "b.mp4"],
        settings={"material_analysis": {"enable_visual_analysis": False}},
        build_plan_func=fake_builder,
    )

    assert captured["enable_visual_analysis"] is False
    assert captured["enable_multimodal_review"] is False
    assert result["selected_adapter_ids"] == ["material.order_fallback"]
    assert result["completed_adapter_ids"] == ["material.order_fallback"]
    assert result["fallback_adapter_id"] == ""
    assert result["material_count"] == 2


def test_material_adapter_uses_ffmpeg_probe_by_default(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_builder(paths, **kwargs):
        captured.update(kwargs)
        return _plan(paths, strategy="ffmpeg_frame_probe_role_assignment", visual_available=True)

    result = prepare_material_plan(
        paths=[tmp_path / "a.mp4"],
        settings={},
        build_plan_func=fake_builder,
    )

    assert captured["enable_visual_analysis"] is True
    assert captured["enable_multimodal_review"] is False
    assert captured["visual_tuning"]["preset"] == "balanced"
    assert result["selected_adapter_ids"] == ["material.ffmpeg_probe"]
    assert result["completed_adapter_ids"] == ["material.ffmpeg_probe"]
    assert result["warnings"] == []
    assert any(hint["id"] == "material.multimodal_review.needs_consent" for hint in result["ui_hints"])


def test_material_adapter_passes_visual_tuning_to_builder(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_builder(paths, **kwargs):
        captured.update(kwargs)
        plan = _plan(paths, strategy="ffmpeg_frame_probe_role_assignment", visual_available=True)
        plan["visual_analysis"]["tuning"] = dict(kwargs["visual_tuning"])
        return plan

    result = prepare_material_plan(
        paths=[tmp_path / "a.mp4"],
        settings={
            "material_analysis": {
                "visual_quality_preset": "high",
                "frame_sample_count": 99,
                "thumbnail_max_side": 96,
                "role_confidence_threshold": 1.5,
            }
        },
        build_plan_func=fake_builder,
    )

    assert captured["visual_tuning"] == {
        "preset": "high",
        "frame_sample_count": 24,
        "thumbnail_max_side": 128,
        "role_confidence_threshold": 1.0,
    }
    assert result["visual_analysis_tuning"] == captured["visual_tuning"]
    assert result["material_plan"]["visual_analysis"]["tuning"] == captured["visual_tuning"]


def test_material_adapter_preserves_calibrated_visual_preset(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_builder(paths, **kwargs):
        captured.update(kwargs)
        return _plan(paths, strategy="ffmpeg_frame_probe_role_assignment", visual_available=True)

    result = prepare_material_plan(
        paths=[tmp_path / "calibrated.mp4"],
        settings={
            "material_analysis": {
                "visual_quality_preset": "calibrated",
                "role_confidence_threshold": 0.63,
            }
        },
        build_plan_func=fake_builder,
    )

    assert captured["visual_tuning"]["preset"] == "calibrated"
    assert captured["visual_tuning"]["role_confidence_threshold"] == 0.63
    assert result["visual_analysis_tuning"]["preset"] == "calibrated"


def test_material_adapter_enables_multimodal_only_when_media_upload_allowed(tmp_path: Path) -> None:
    captured: dict[str, Any] = {}

    def fake_builder(paths, **kwargs):
        captured.update(kwargs)
        plan = _plan(paths, strategy="multimodal_thumbnail_role_review", visual_available=True)
        plan["multimodal_review"] = {"ok": True, "status": "completed"}
        return plan

    result = prepare_material_plan(
        paths=[tmp_path / "a.mp4", tmp_path / "b.mp4"],
        settings={"model_route": {"allow_media_upload_to_llm": True}},
        build_plan_func=fake_builder,
    )

    assert captured["enable_multimodal_review"] is True
    assert result["selected_adapter_ids"] == ["material.ffmpeg_probe", "material.multimodal_review"]
    assert result["completed_adapter_ids"] == ["material.ffmpeg_probe", "material.multimodal_review"]
    assert any(warning["code"] == "media_upload_to_llm_allowed" for warning in result["warnings"])


def test_material_adapter_records_visual_fallback_warning(tmp_path: Path) -> None:
    def fake_builder(paths, **kwargs):
        return _plan(paths, strategy="order_fallback_role_assignment", visual_available=False)

    result = prepare_material_plan(
        paths=[tmp_path / "a.mp4"],
        settings={},
        build_plan_func=fake_builder,
    )

    assert result["selected_adapter_ids"] == ["material.ffmpeg_probe"]
    assert result["completed_adapter_ids"] == ["material.order_fallback"]
    assert result["fallback_adapter_id"] == "material.order_fallback"
    assert any(warning["code"] == "visual_analysis_unavailable" for warning in result["warnings"])


def test_material_adapter_supports_legacy_builder_without_keyword_args(tmp_path: Path) -> None:
    def legacy_builder(paths):
        return _plan(paths, strategy="order_fallback_role_assignment", visual_available=False)

    result = prepare_material_plan(
        paths=[tmp_path / "legacy.mp4"],
        settings={},
        build_plan_func=legacy_builder,
    )

    assert result["ok"] is True
    assert result["material_plan"]["materials"][0]["label"] == "legacy.mp4"


def _plan(paths, *, strategy: str, visual_available: bool) -> dict[str, Any]:
    materials = [
        {
            "index": index,
            "path": str(path),
            "label": Path(path).name,
            "primary_role": "opening_hero",
            "display_role": "opening_hero",
            "assignment_source": strategy,
        }
        for index, path in enumerate(paths)
    ]
    return {
        "schema": "smart_video_cut.local.material_plan.v0",
        "strategy": strategy,
        "material_count": len(paths),
        "materials": materials,
        "role_source_map": {"overall_door": 0} if paths else {},
        "visual_analysis": {"available": visual_available, "profiles_ready": len(paths) if visual_available else 0},
        "multimodal_review": {"ok": False, "status": "skipped", "skipped_reason": "disabled"},
        "note": "test",
    }
