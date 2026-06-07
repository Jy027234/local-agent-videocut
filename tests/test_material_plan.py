from __future__ import annotations

from pathlib import Path

from smart_video_cut.material_plan import build_material_plan
from video_editing_toolkit.creative_edit_runner import _source_index_for_shot_kind


def test_material_plan_assigns_stable_roles_by_input_order() -> None:
    plan = build_material_plan(
        [
            Path("D:/media/no1.mp4"),
            Path("D:/media/no2.mp4"),
            Path("D:/media/no3.mp4"),
            Path("D:/media/no2.mp4"),
        ]
    )

    assert plan["schema"] == "smart_video_cut.local.material_plan.v0"
    assert plan["strategy"] == "order_fallback_role_assignment"
    assert plan["material_count"] == 3
    assert [item["primary_role"] for item in plan["materials"]] == [
        "opening_hero",
        "product_body_and_detail",
        "site_context",
    ]
    assert plan["role_source_map"]["overall_door"] == 0
    assert plan["role_source_map"]["detail"] == 1
    assert plan["role_source_map"]["corridor"] == 2


def test_material_plan_can_use_visual_profiles_to_reorder_roles() -> None:
    plan = build_material_plan(
        [
            Path("D:/media/detail.mp4"),
            Path("D:/media/hero.mp4"),
            Path("D:/media/context.mp4"),
        ],
        visual_profiles=[
            {
                "index": 0,
                "label": "detail.mp4",
                "analysis_ready": True,
                "scores": {
                    "opening_hero": 0.30,
                    "product_body_and_detail": 0.92,
                    "site_context": 0.20,
                },
                "reason": "detail",
            },
            {
                "index": 1,
                "label": "hero.mp4",
                "analysis_ready": True,
                "scores": {
                    "opening_hero": 0.88,
                    "product_body_and_detail": 0.30,
                    "site_context": 0.25,
                },
                "reason": "hero",
            },
            {
                "index": 2,
                "label": "context.mp4",
                "analysis_ready": True,
                "scores": {
                    "opening_hero": 0.25,
                    "product_body_and_detail": 0.20,
                    "site_context": 0.86,
                },
                "reason": "context",
            },
        ],
    )

    assert plan["strategy"] == "ffmpeg_frame_probe_role_assignment"
    assert plan["visual_analysis"]["available"] is True
    assert plan["role_source_map"]["overall_door"] == 1
    assert plan["role_source_map"]["detail"] == 0
    assert plan["role_source_map"]["corridor"] == 2
    assert [item["primary_role"] for item in plan["materials"]] == [
        "product_body_and_detail",
        "opening_hero",
        "site_context",
    ]
    assert "本角色评分" in plan["materials"][0]["assignment_reason"]


def test_material_plan_can_use_multimodal_review_assignments() -> None:
    visual_profiles = [
        {
            "index": 0,
            "label": "first.mp4",
            "analysis_ready": True,
            "scores": {
                "opening_hero": 0.30,
                "product_body_and_detail": 0.92,
                "site_context": 0.20,
            },
        },
        {
            "index": 1,
            "label": "second.mp4",
            "analysis_ready": True,
            "scores": {
                "opening_hero": 0.88,
                "product_body_and_detail": 0.30,
                "site_context": 0.25,
            },
        },
        {
            "index": 2,
            "label": "third.mp4",
            "analysis_ready": True,
            "scores": {
                "opening_hero": 0.25,
                "product_body_and_detail": 0.20,
                "site_context": 0.86,
            },
        },
    ]
    plan = build_material_plan(
        [
            Path("D:/media/first.mp4"),
            Path("D:/media/second.mp4"),
            Path("D:/media/third.mp4"),
        ],
        visual_profiles=visual_profiles,
        multimodal_review={
            "ok": True,
            "status": "completed",
            "assignments": [
                {
                    "index": 0,
                    "role": "site_context",
                    "confidence": 0.91,
                    "reason": "看到较多空间和走廊关系",
                },
                {
                    "index": 1,
                    "role": "opening_hero",
                    "confidence": 0.87,
                    "reason": "门体全貌清楚",
                },
                {
                    "index": 2,
                    "role": "product_body_and_detail",
                    "confidence": 0.83,
                    "reason": "细节更突出",
                },
            ],
        },
    )

    assert plan["strategy"] == "multimodal_thumbnail_role_review"
    assert plan["multimodal_review"]["status"] == "completed"
    assert plan["role_source_map"]["corridor"] == 0
    assert plan["role_source_map"]["overall_door"] == 1
    assert plan["role_source_map"]["detail"] == 2
    assert "多模态复核建议" in plan["materials"][0]["assignment_reason"]


def test_render_source_selection_uses_material_role_map() -> None:
    role_map = {"overall_door": 0, "detail": 1, "corridor": 2}

    assert (
        _source_index_for_shot_kind(
            shot_kind="overall_door",
            fallback_index=8,
            video_count=3,
            material_role_map=role_map,
        )
        == 0
    )
    assert (
        _source_index_for_shot_kind(
            shot_kind="detail",
            fallback_index=8,
            video_count=3,
            material_role_map=role_map,
        )
        == 1
    )
    assert (
        _source_index_for_shot_kind(
            shot_kind="corridor",
            fallback_index=8,
            video_count=3,
            material_role_map=role_map,
        )
        == 2
    )
