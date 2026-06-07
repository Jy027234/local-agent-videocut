"""Creative edit runner for the standalone local studio."""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
import wave
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from video_editing_toolkit.runtime_common import mapping, public_safe, safe_id, write_json
from video_editing_toolkit.storage import ArtifactRef, LocalArtifactStore


SCHEMA = "video_editing_toolkit.creative_edit_runner.v0"
RESULT_SCHEMA = "video_editing_toolkit.creative_edit_runner_result.v0"
CREATIVE_EDIT_RUNNER_PACKAGE_SCHEMA = "video_editing_toolkit.creative_edit_runner_package.v0"
CREATIVE_EDIT_BRIEF_SCHEMA = "video_editing_toolkit.creative_edit_brief.v0"
CREATIVE_EDIT_TIMELINE_SCHEMA = "video_editing_toolkit.creative_edit_timeline.v0"
CREATIVE_EDIT_RENDER_PLAN_SCHEMA = "video_editing_toolkit.creative_edit_render_plan.v0"
CREATIVE_EDIT_QC_PLAN_SCHEMA = "video_editing_toolkit.creative_edit_qc_plan.v0"
CREATIVE_EDIT_EXECUTION_REPORT_SCHEMA = "video_editing_toolkit.creative_edit_execution_report.v0"
DEFAULT_ARTIFACT_ROOT = Path(".video-toolkit-data") / "p2-21-creative-edit-real-canary-artifacts"

EXECUTION_MODES = ("plan_only", "worker_real_render")
WORKER_EXECUTION_STATES = ("not_requested", "completed", "failed", "blocked")
ONSCREEN_TEXT_POLICIES = ("preserve_existing", "allow_regenerate")
VOICEOVER_MODES = ("generated_male_ad_copy", "provided_text", "none")
HUMAN_REVIEW_STATES = ("pending", "accepted", "rejected")
RESULT_EVIDENCE_STATES = ("missing", "ready")
DEFAULT_VOICEOVER_TEXT = "客厅门安装记录，同家庄镇张庄村。门窗安装完成，整体效果整洁。"
DEFAULT_TEST_MEDIA_LABEL = "no2.mp4"
DEFAULT_REFERENCE_TEMPLATE_LABEL = "sample.mp4"
DEFAULT_TARGET_DURATION_SECONDS = 20
DEFAULT_CREATIVE_OBJECTIVE = "anti_theft_door_product_ad_flash"
DEFAULT_AD_VOICEOVER_TEXT = (
    "一扇好门，是家的第一道防线。看得见的厚实门体，摸得到的扎实做工。"
    "锁具清晰，门框贴合，入户门选得稳，日常住得更安心。"
)
DEFAULT_KEPT_TEXT = (
    "安装记录",
    "入户门安装",
    "现场记录",
    "入户门安装完成",
    "现场走廊环境",
    "整体效果记录",
)


@dataclass(slots=True)
class WorkerRenderRequest:
    media_path: Path
    reference_template_path: Path | None
    target_duration_seconds: int
    voiceover_text: str
    brief: Mapping[str, Any]
    timeline: Mapping[str, Any]
    render_plan: Mapping[str, Any]
    work_dir: Path
    artifact_store: LocalArtifactStore
    tenant_id: str
    created_by_run_id: str
    allow_edge_tts: bool
    media_paths: list[Path] = field(default_factory=list)
    material_role_map: dict[str, int] = field(default_factory=dict)
    subtitle_enabled: bool = True
    subtitle_texts: list[str] = field(default_factory=list)
    voiceover_audio_path: Path | None = None
    bgm_audio_path: Path | None = None
    bgm_enabled: bool = True
    bgm_start_seconds: float = 0.0
    render_width: int = 720
    render_height: int = 1280
    render_aspect_ratio: str = "9:16"
    render_fps: int = 30
    video_crf: int = 22
    subtitle_font_size: int = 44
    subtitle_font_color: str = "white"
    subtitle_outline_color: str = "black"
    subtitle_outline_width: int = 5
    bgm_volume_db: float = -18.0
    voice_volume_db: float = 0.0


@dataclass(slots=True)
class WorkerRenderResult:
    state: str
    artifact_refs: dict[str, dict[str, Any]] = field(default_factory=dict)
    evidence: dict[str, Any] = field(default_factory=dict)
    failure_reason: str | None = None
    media_decode_or_render_performed: bool = False


RenderExecutor = Callable[[WorkerRenderRequest], WorkerRenderResult]


def run_creative_edit_runner(
    *,
    user_request: str | None = None,
    voiceover_text: str = DEFAULT_VOICEOVER_TEXT,
    timeline: Mapping[str, Any] | None = None,
    artifact_root: str | Path | None = None,
    result_json: str | Path | None = None,
    tenant_id: str = "local_studio_tenant",
    user_id: str = "local_user",
    project_id: str = "local_project",
    platform_job_id: str = "local_creative_edit_job",
    platform_run_id: str = "local_creative_edit_run",
    worker_id: str = "local_studio_worker",
    backend_id: str = "local",
    test_media_label: str = DEFAULT_TEST_MEDIA_LABEL,
    reference_template_label: str = DEFAULT_REFERENCE_TEMPLATE_LABEL,
    target_duration_seconds: int = DEFAULT_TARGET_DURATION_SECONDS,
    creative_objective: str = DEFAULT_CREATIVE_OBJECTIVE,
    onscreen_text_policy: str = "preserve_existing",
    voiceover_mode: str = "generated_male_ad_copy",
    human_review_result: str = "pending",
    result_artifact_state: str = "missing",
    visual_evidence_state: str = "missing",
    audio_evidence_state: str = "missing",
    subtitle_evidence_state: str = "missing",
    timeline_evidence_state: str = "missing",
    qc_report_state: str = "missing",
    execution_mode: str = "plan_only",
    execute_real_render: bool = False,
    worker_media_input: str | Path | None = None,
    worker_media_inputs: Sequence[str | Path] | None = None,
    worker_material_role_map: Mapping[str, int] | None = None,
    worker_subtitle_enabled: bool = True,
    worker_subtitle_texts: Sequence[str] | None = None,
    worker_reference_template_input: str | Path | None = None,
    worker_voiceover_audio_input: str | Path | None = None,
    worker_bgm_audio_input: str | Path | None = None,
    worker_bgm_enabled: bool = True,
    worker_bgm_start_seconds: float = 0.0,
    worker_render_width: int = 720,
    worker_render_height: int = 1280,
    worker_render_aspect_ratio: str = "9:16",
    worker_render_fps: int = 30,
    worker_video_crf: int = 22,
    worker_subtitle_font_size: int = 44,
    worker_subtitle_font_color: str = "white",
    worker_subtitle_outline_color: str = "black",
    worker_subtitle_outline_width: int = 5,
    worker_bgm_volume_db: float = -18.0,
    worker_voice_volume_db: float = 0.0,
    allow_edge_tts: bool = False,
    render_executor: RenderExecutor | None = None,
) -> dict[str, Any]:
    """Build a caller-safe package for a creative canary edit runner.

    The default mode is plan-only. Real media reads and FFmpeg execution are
    only attempted when a worker explicitly asks for ``worker_real_render`` and
    passes ``execute_real_render=True`` with resolved worker inputs.
    """

    _validate_choice("execution_mode", execution_mode, EXECUTION_MODES)
    _validate_choice("onscreen_text_policy", onscreen_text_policy, ONSCREEN_TEXT_POLICIES)
    _validate_choice("voiceover_mode", voiceover_mode, VOICEOVER_MODES)
    _validate_choice("human_review_result", human_review_result, HUMAN_REVIEW_STATES)
    for name, value in {
        "result_artifact_state": result_artifact_state,
        "visual_evidence_state": visual_evidence_state,
        "audio_evidence_state": audio_evidence_state,
        "subtitle_evidence_state": subtitle_evidence_state,
        "timeline_evidence_state": timeline_evidence_state,
        "qc_report_state": qc_report_state,
    }.items():
        _validate_choice(name, value, RESULT_EVIDENCE_STATES)
    if target_duration_seconds <= 0:
        raise ValueError("target_duration_seconds must be greater than 0")

    selected_timeline = mapping(timeline)
    if selected_timeline:
        target_duration_seconds = int(
            selected_timeline.get("target_duration_seconds", target_duration_seconds)
        )
        if target_duration_seconds <= 0:
            raise ValueError("timeline target_duration_seconds must be greater than 0")

    selected_root = Path(artifact_root) if artifact_root is not None else DEFAULT_ARTIFACT_ROOT
    artifact_store = LocalArtifactStore(selected_root)
    created_by_run_id = f"{safe_id(user_id, default='user')}_creative_edit_runner"
    selected_voiceover_text = _selected_voiceover_text(
        voiceover_mode=voiceover_mode,
        voiceover_text=voiceover_text,
    )
    render_settings = _renderer_settings(
        width=worker_render_width,
        height=worker_render_height,
        aspect_ratio=worker_render_aspect_ratio,
        fps=worker_render_fps,
        video_crf=worker_video_crf,
        subtitle_font_size=worker_subtitle_font_size,
        subtitle_font_color=worker_subtitle_font_color,
        subtitle_outline_color=worker_subtitle_outline_color,
        subtitle_outline_width=worker_subtitle_outline_width,
        bgm_volume_db=worker_bgm_volume_db,
        voice_volume_db=worker_voice_volume_db,
    )
    brief = _creative_edit_brief(
        user_request=user_request,
        test_media_label=test_media_label,
        reference_template_label=reference_template_label,
        target_duration_seconds=target_duration_seconds,
        creative_objective=creative_objective,
        onscreen_text_policy=onscreen_text_policy,
        voiceover_mode=voiceover_mode,
        voiceover_text=selected_voiceover_text,
    )
    timeline = selected_timeline or _timeline_plan(target_duration_seconds=target_duration_seconds)
    render_plan = _render_plan(
        target_duration_seconds=target_duration_seconds,
        onscreen_text_policy=onscreen_text_policy,
        voiceover_mode=voiceover_mode,
        render_settings=render_settings,
    )
    qc_plan = _qc_plan(
        target_duration_seconds=target_duration_seconds,
        onscreen_text_policy=onscreen_text_policy,
        render_settings=render_settings,
    )

    source_artifact_refs = {
        "creative_edit_brief": _put_json_artifact(
            artifact_store=artifact_store,
            tenant_id=tenant_id,
            created_by_run_id=created_by_run_id,
            artifact_type="creative_edit_brief",
            filename="creative_edit_brief.json",
            payload=brief,
        ),
        "timeline_plan": _put_json_artifact(
            artifact_store=artifact_store,
            tenant_id=tenant_id,
            created_by_run_id=created_by_run_id,
            artifact_type="creative_edit_timeline",
            filename="timeline.json",
            payload=timeline,
        ),
        "render_plan": _put_json_artifact(
            artifact_store=artifact_store,
            tenant_id=tenant_id,
            created_by_run_id=created_by_run_id,
            artifact_type="creative_edit_render_plan",
            filename="render_plan.json",
            payload=render_plan,
        ),
        "qc_plan": _put_json_artifact(
            artifact_store=artifact_store,
            tenant_id=tenant_id,
            created_by_run_id=created_by_run_id,
            artifact_type="creative_edit_qc_plan",
            filename="qc_plan.json",
            payload=qc_plan,
        ),
    }

    worker_result = _maybe_execute_worker_render(
        execution_mode=execution_mode,
        execute_real_render=execute_real_render,
        worker_media_input=worker_media_input,
        worker_media_inputs=worker_media_inputs,
        worker_material_role_map=worker_material_role_map,
        worker_subtitle_enabled=worker_subtitle_enabled,
        worker_subtitle_texts=worker_subtitle_texts,
        worker_reference_template_input=worker_reference_template_input,
        worker_voiceover_audio_input=worker_voiceover_audio_input,
        worker_bgm_audio_input=worker_bgm_audio_input,
        worker_bgm_enabled=worker_bgm_enabled,
        worker_bgm_start_seconds=worker_bgm_start_seconds,
        render_settings=render_settings,
        target_duration_seconds=target_duration_seconds,
        voiceover_text=selected_voiceover_text,
        brief=brief,
        timeline=timeline,
        render_plan=render_plan,
        selected_root=selected_root,
        artifact_store=artifact_store,
        tenant_id=tenant_id,
        created_by_run_id=created_by_run_id,
        allow_edge_tts=allow_edge_tts,
        render_executor=render_executor,
    )
    execution_report = _execution_report(
        execution_mode=execution_mode,
        execute_real_render=execute_real_render,
        worker_result=worker_result,
        target_duration_seconds=target_duration_seconds,
        result_artifact_state=result_artifact_state,
        visual_evidence_state=visual_evidence_state,
        audio_evidence_state=audio_evidence_state,
        subtitle_evidence_state=subtitle_evidence_state,
        timeline_evidence_state=timeline_evidence_state,
        qc_report_state=qc_report_state,
        human_review_result=human_review_result,
    )
    source_artifact_refs["execution_report"] = _put_json_artifact(
        artifact_store=artifact_store,
        tenant_id=tenant_id,
        created_by_run_id=created_by_run_id,
        artifact_type="creative_edit_execution_report",
        filename="execution_report.json",
        payload=execution_report,
    )
    source_artifact_refs.update(worker_result.artifact_refs)

    decision = _runner_decision(
        execution_report=execution_report,
        human_review_result=human_review_result,
    )
    quality_gate = _quality_gate(
        brief=brief,
        timeline=timeline,
        render_plan=render_plan,
        qc_plan=qc_plan,
        execution_report=execution_report,
        decision=decision,
        source_artifact_refs=source_artifact_refs,
    )
    package = _runner_package(
        tenant_id=tenant_id,
        user_id=user_id,
        project_id=project_id,
        platform_job_id=platform_job_id,
        platform_run_id=platform_run_id,
        worker_id=worker_id,
        backend_id=backend_id,
        brief=brief,
        timeline=timeline,
        render_plan=render_plan,
        qc_plan=qc_plan,
        execution_report=execution_report,
        decision=decision,
        quality_gate=quality_gate,
        source_artifact_refs=source_artifact_refs,
        worker_execution_state=worker_result.state,
    )
    package_ref = artifact_store.put_bytes(
        content=json.dumps(
            public_safe(package),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8"),
        artifact_type="creative_edit_runner_package",
        owner_tenant_id=tenant_id,
        created_by_run_id=created_by_run_id,
        filename="creative_edit_runner_package.json",
        mime_type="application/json",
        access_policy={
            "scope": "tenant_project",
            "handoff": "creative_edit_runner_package",
        },
    )

    summary = public_safe(
        {
            "schema": SCHEMA,
            "contract": "creative_edit_runner.v0",
            "ok": quality_gate["contract_valid"] is True,
            "workflow_kind": "creative_edit_runner",
            "creative_edit_runner_package_artifact_id": package_ref.artifact_id,
            "creative_edit_runner_package_artifact_ref": package_ref.to_public_dict(),
            "creative_edit_runner_summary": package["summary"],
            "creative_edit_brief": brief,
            "execution_report": execution_report,
            "runner_decision": decision,
            "source_artifact_refs": source_artifact_refs,
            "quality_gate": quality_gate,
            "platform_boundary": package["platform_boundary"],
            "next_recommended_step": package["summary"]["next_recommended_step"],
        }
    )

    if result_json is not None:
        write_json(
            result_json,
            {
                "schema": RESULT_SCHEMA,
                "summary": summary,
                "creative_edit_runner_package": package,
                "creative_edit_runner_package_artifact_ref": package_ref.to_public_dict(),
            },
        )
        summary["result_json_written"] = True

    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the creative edit runner.")
    parser.add_argument("--user-request")
    parser.add_argument("--voiceover-text", default=DEFAULT_VOICEOVER_TEXT)
    parser.add_argument("--artifact-root", default=str(DEFAULT_ARTIFACT_ROOT))
    parser.add_argument("--result-json")
    parser.add_argument("--tenant-id", default="local_studio_tenant")
    parser.add_argument("--user-id", default="local_user")
    parser.add_argument("--project-id", default="local_project")
    parser.add_argument("--platform-job-id", default="local_creative_edit_job")
    parser.add_argument("--platform-run-id", default="local_creative_edit_run")
    parser.add_argument("--worker-id", default="local_studio_worker")
    parser.add_argument("--backend-id", default="local")
    parser.add_argument("--test-media-label", default=DEFAULT_TEST_MEDIA_LABEL)
    parser.add_argument("--reference-template-label", default=DEFAULT_REFERENCE_TEMPLATE_LABEL)
    parser.add_argument("--target-duration-seconds", type=int, default=DEFAULT_TARGET_DURATION_SECONDS)
    parser.add_argument("--creative-objective", default=DEFAULT_CREATIVE_OBJECTIVE)
    parser.add_argument("--onscreen-text-policy", choices=ONSCREEN_TEXT_POLICIES, default="preserve_existing")
    parser.add_argument("--voiceover-mode", choices=VOICEOVER_MODES, default="generated_male_ad_copy")
    parser.add_argument("--human-review-result", choices=HUMAN_REVIEW_STATES, default="pending")
    parser.add_argument("--result-artifact-state", choices=RESULT_EVIDENCE_STATES, default="missing")
    parser.add_argument("--visual-evidence-state", choices=RESULT_EVIDENCE_STATES, default="missing")
    parser.add_argument("--audio-evidence-state", choices=RESULT_EVIDENCE_STATES, default="missing")
    parser.add_argument("--subtitle-evidence-state", choices=RESULT_EVIDENCE_STATES, default="missing")
    parser.add_argument("--timeline-evidence-state", choices=RESULT_EVIDENCE_STATES, default="missing")
    parser.add_argument("--qc-report-state", choices=RESULT_EVIDENCE_STATES, default="missing")
    parser.add_argument("--execution-mode", choices=EXECUTION_MODES, default="plan_only")
    parser.add_argument("--execute-real-render", action="store_true")
    parser.add_argument("--worker-media-input")
    parser.add_argument("--worker-reference-template-input")
    parser.add_argument("--worker-render-width", type=int, default=720)
    parser.add_argument("--worker-render-height", type=int, default=1280)
    parser.add_argument("--worker-render-aspect-ratio", default="9:16")
    parser.add_argument("--worker-render-fps", type=int, default=30)
    parser.add_argument("--worker-video-crf", type=int, default=22)
    parser.add_argument("--worker-subtitle-font-size", type=int, default=44)
    parser.add_argument("--worker-subtitle-font-color", default="white")
    parser.add_argument("--worker-subtitle-outline-color", default="black")
    parser.add_argument("--worker-subtitle-outline-width", type=int, default=5)
    parser.add_argument("--worker-bgm-volume-db", type=float, default=-18.0)
    parser.add_argument("--worker-voice-volume-db", type=float, default=0.0)
    parser.add_argument("--allow-edge-tts", action="store_true")
    args = parser.parse_args(argv)

    try:
        summary = run_creative_edit_runner(
            user_request=args.user_request,
            voiceover_text=args.voiceover_text,
            artifact_root=args.artifact_root,
            result_json=args.result_json,
            tenant_id=args.tenant_id,
            user_id=args.user_id,
            project_id=args.project_id,
            platform_job_id=args.platform_job_id,
            platform_run_id=args.platform_run_id,
            worker_id=args.worker_id,
            backend_id=args.backend_id,
            test_media_label=args.test_media_label,
            reference_template_label=args.reference_template_label,
            target_duration_seconds=args.target_duration_seconds,
            creative_objective=args.creative_objective,
            onscreen_text_policy=args.onscreen_text_policy,
            voiceover_mode=args.voiceover_mode,
            human_review_result=args.human_review_result,
            result_artifact_state=args.result_artifact_state,
            visual_evidence_state=args.visual_evidence_state,
            audio_evidence_state=args.audio_evidence_state,
            subtitle_evidence_state=args.subtitle_evidence_state,
            timeline_evidence_state=args.timeline_evidence_state,
            qc_report_state=args.qc_report_state,
            execution_mode=args.execution_mode,
            execute_real_render=args.execute_real_render,
            worker_media_input=args.worker_media_input,
            worker_reference_template_input=args.worker_reference_template_input,
            worker_render_width=args.worker_render_width,
            worker_render_height=args.worker_render_height,
            worker_render_aspect_ratio=args.worker_render_aspect_ratio,
            worker_render_fps=args.worker_render_fps,
            worker_video_crf=args.worker_video_crf,
            worker_subtitle_font_size=args.worker_subtitle_font_size,
            worker_subtitle_font_color=args.worker_subtitle_font_color,
            worker_subtitle_outline_color=args.worker_subtitle_outline_color,
            worker_subtitle_outline_width=args.worker_subtitle_outline_width,
            worker_bgm_volume_db=args.worker_bgm_volume_db,
            worker_voice_volume_db=args.worker_voice_volume_db,
            allow_edge_tts=args.allow_edge_tts,
        )
    except ValueError as exc:
        summary = {
            "schema": SCHEMA,
            "ok": False,
            "error_code": "creative_edit_runner.invalid_request",
            "error_message": str(exc),
        }
        print(json.dumps(public_safe(summary), ensure_ascii=False, sort_keys=True))
        return 2

    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if summary.get("ok") is True else 2


def _creative_edit_brief(
    *,
    user_request: str | None,
    test_media_label: str,
    reference_template_label: str,
    target_duration_seconds: int,
    creative_objective: str,
    onscreen_text_policy: str,
    voiceover_mode: str,
    voiceover_text: str,
) -> dict[str, Any]:
    return public_safe(
        {
            "schema": CREATIVE_EDIT_BRIEF_SCHEMA,
            "contract": "creative_edit_brief.v0",
            "user_request_summary": _safe_summary(
                user_request,
                default="在配字不变的基础上，生成防盗门产品广告感快闪混剪。",
            ),
            "media_fixture": {
                "asset_label": _safe_asset_label(test_media_label),
                "raw_worker_locator_exposed": False,
            },
            "reference_template": {
                "asset_label": _safe_asset_label(reference_template_label),
                "policy": "style_reference_locked",
                "raw_worker_locator_exposed": False,
            },
            "target_duration_seconds": target_duration_seconds,
            "creative_objective": _safe_label(creative_objective, default=DEFAULT_CREATIVE_OBJECTIVE),
            "immutable_requirements": {
                "onscreen_text_policy": onscreen_text_policy,
                "kept_onscreen_text": list(DEFAULT_KEPT_TEXT),
                "subtitle_style": "large_white_text_with_black_outline",
                "cover_style": "yellow_label_plus_large_white_black_outlined_text",
            },
            "allowed_creative_changes": [
                "shot_order",
                "cut_pacing",
                "product_closeups",
                "advertising_voiceover_copy",
                "instrumental_bgm",
                "brightness_contrast_sharpening",
            ],
            "voiceover": {
                "mode": voiceover_mode,
                "preferred_provider": "edge_tts",
                "preferred_voice": "zh-CN-YunyangNeural",
                "text": voiceover_text if voiceover_mode != "none" else "",
            },
            "agent_boundary": {
                "agent_lifecycle_owner": "platform_core",
                "agent_outputs_required": ["edit_brief", "timeline_plan", "render_plan", "qc_plan"],
                "worker_outputs_required": [
                    "final_render",
                    "voiceover_audio",
                    "visual_evidence",
                    "audio_evidence",
                    "qc_report",
                ],
            },
        }
    )


def _timeline_plan(*, target_duration_seconds: int) -> dict[str, Any]:
    segments = [
        ("cover", 0.0, 2.2, "wide_product_hero"),
        ("door_front_flash_1", 2.2, 1.4, "door_body"),
        ("door_close_flash", 3.6, 1.2, "product_detail"),
        ("door_front_flash_2", 4.8, 1.4, "door_body"),
        ("site_context_1", 6.2, 1.6, "corridor_context"),
        ("site_context_2", 7.8, 1.5, "corridor_context"),
        ("overall_effect_1", 9.3, 1.4, "overall_door"),
        ("product_close_flash_2", 10.7, 1.2, "product_detail"),
        ("overall_effect_2", 11.9, 1.5, "overall_door"),
        ("overall_effect_3", 13.4, 1.5, "overall_door"),
        ("door_front_flash_3", 14.9, 1.3, "door_body"),
        ("final_hold", 16.2, max(0.1, target_duration_seconds - 16.2), "overall_door"),
    ]
    return {
        "schema": CREATIVE_EDIT_TIMELINE_SCHEMA,
        "contract": "creative_edit_timeline.v0",
        "target_duration_seconds": target_duration_seconds,
        "timeline_kind": "advertising_flash_montage",
        "source_selection_policy": {
            "prefer": ["door_front", "lock_or_hardware_detail", "door_frame", "site_context"],
            "avoid": ["blank_wall_closeup", "dark_unreadable_surface", "long_static_repetition"],
        },
        "segments": [
            {
                "segment_id": segment_id,
                "timeline_start_seconds": round(start, 3),
                "duration_seconds": round(duration, 3),
                "shot_intent": intent,
                "onscreen_text_policy": "use_existing_locked_text_family",
            }
            for segment_id, start, duration, intent in segments
        ],
        "transition_policy": {
            "style": "hard_cuts_with_light_flash_accents",
            "max_single_shot_seconds": 4.0,
        },
    }


def _renderer_settings(
    *,
    width: int,
    height: int,
    aspect_ratio: str,
    fps: int,
    video_crf: int,
    subtitle_font_size: int,
    subtitle_font_color: str,
    subtitle_outline_color: str,
    subtitle_outline_width: int,
    bgm_volume_db: float,
    voice_volume_db: float,
) -> dict[str, Any]:
    safe_width = _clamp_int(width, default=720, minimum=144, maximum=7680)
    safe_height = _clamp_int(height, default=1280, minimum=144, maximum=7680)
    return {
        "width": safe_width,
        "height": safe_height,
        "aspect_ratio": _safe_aspect_ratio(aspect_ratio, width=safe_width, height=safe_height),
        "fps": _clamp_int(fps, default=30, minimum=12, maximum=120),
        "video_crf": _clamp_int(video_crf, default=22, minimum=14, maximum=35),
        "subtitle_font_size": _clamp_int(subtitle_font_size, default=44, minimum=8, maximum=180),
        "subtitle_font_color": _safe_color(subtitle_font_color, default="white"),
        "subtitle_outline_color": _safe_color(subtitle_outline_color, default="black"),
        "subtitle_outline_width": _clamp_int(subtitle_outline_width, default=5, minimum=0, maximum=24),
        "bgm_volume_db": _clamp_float(bgm_volume_db, default=-18.0, minimum=-80.0, maximum=6.0),
        "voice_volume_db": _clamp_float(voice_volume_db, default=0.0, minimum=-80.0, maximum=12.0),
    }


def _orientation(*, width: int, height: int) -> str:
    if width == height:
        return "square"
    return "horizontal" if width > height else "vertical"


def _safe_aspect_ratio(value: str, *, width: int, height: int) -> str:
    text = str(value or "").strip()
    if text in {"9:16", "16:9", "1:1", "4:5"}:
        return text
    divisor = math.gcd(max(1, width), max(1, height))
    return f"{max(1, width // divisor)}:{max(1, height // divisor)}"


def _clamp_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        selected = int(value)
    except (TypeError, ValueError):
        selected = default
    return max(minimum, min(maximum, selected))


def _clamp_float(value: Any, *, default: float, minimum: float, maximum: float) -> float:
    try:
        selected = float(value)
    except (TypeError, ValueError):
        selected = default
    return max(minimum, min(maximum, selected))


def _safe_color(value: str, *, default: str) -> str:
    text = str(value or "").strip()
    if re.fullmatch(r"[A-Za-z0-9_#@.]+", text):
        return text
    return default


def _render_plan(
    *,
    target_duration_seconds: int,
    onscreen_text_policy: str,
    voiceover_mode: str,
    render_settings: Mapping[str, Any],
) -> dict[str, Any]:
    width = int(render_settings["width"])
    height = int(render_settings["height"])
    return {
        "schema": CREATIVE_EDIT_RENDER_PLAN_SCHEMA,
        "contract": "creative_edit_render_plan.v0",
        "target_duration_seconds": target_duration_seconds,
        "orientation": _orientation(width=width, height=height),
        "aspect_ratio": render_settings["aspect_ratio"],
        "resolution": {"width": width, "height": height},
        "fps": render_settings["fps"],
        "video_crf": render_settings["video_crf"],
        "video_processing": {
            "stabilization": "deshake_when_available",
            "color": "mild_ad_contrast_saturation_boost",
            "sharpen": "mild_product_detail_sharpening",
        },
        "text_layer": {
            "onscreen_text_policy": onscreen_text_policy,
            "must_preserve_text_content": onscreen_text_policy == "preserve_existing",
            "cover_label_color": "yellow",
            "font_size": render_settings["subtitle_font_size"],
            "font_color": render_settings["subtitle_font_color"],
            "outline_color": render_settings["subtitle_outline_color"],
            "outline_width": render_settings["subtitle_outline_width"],
            "rotation_degrees": 0,
        },
        "audio": {
            "voiceover_mode": voiceover_mode,
            "drop_original_source_audio": True,
            "bgm": "instrumental_upbeat_no_vocals",
            "bgm_volume_db": render_settings["bgm_volume_db"],
            "voice_volume_db": render_settings["voice_volume_db"],
        },
        "output_artifacts": [
            "final_render",
            "voiceover_audio",
            "instrumental_bgm",
            "visual_evidence",
            "audio_evidence",
            "qc_report",
        ],
    }


def _qc_plan(
    *,
    target_duration_seconds: int,
    onscreen_text_policy: str,
    render_settings: Mapping[str, Any],
) -> dict[str, Any]:
    width = int(render_settings["width"])
    height = int(render_settings["height"])
    return {
        "schema": CREATIVE_EDIT_QC_PLAN_SCHEMA,
        "contract": "creative_edit_qc_plan.v0",
        "checks": [
            {
                "check_id": "duration_target",
                "acceptance": {"target_duration_seconds": target_duration_seconds, "tolerance_seconds": 1},
            },
            {
                "check_id": "target_resolution",
                "acceptance": {
                    "width": width,
                    "height": height,
                    "aspect_ratio": render_settings["aspect_ratio"],
                },
            },
            {"check_id": "audio_present", "acceptance": {"requires_voice_or_bgm": True}},
            {
                "check_id": "onscreen_text_preserved",
                "acceptance": {"policy": onscreen_text_policy, "rotation_degrees": 0},
            },
            {"check_id": "product_focus", "acceptance": {"door_or_hardware_shot_ratio_min": 0.65}},
            {"check_id": "human_review_hold", "acceptance": {"delivery_publish_allowed": False}},
        ],
        "post_render_evidence_required": [
            "media_probe",
            "keyframe_sheet",
            "audio_level_probe",
            "artifact_refs",
            "human_review_result",
        ],
    }


def _maybe_execute_worker_render(
    *,
    execution_mode: str,
    execute_real_render: bool,
    worker_media_input: str | Path | None,
    worker_media_inputs: Sequence[str | Path] | None,
    worker_material_role_map: Mapping[str, int] | None,
    worker_subtitle_enabled: bool,
    worker_subtitle_texts: Sequence[str] | None,
    worker_reference_template_input: str | Path | None,
    worker_voiceover_audio_input: str | Path | None,
    worker_bgm_audio_input: str | Path | None,
    worker_bgm_enabled: bool,
    worker_bgm_start_seconds: float,
    render_settings: Mapping[str, Any],
    target_duration_seconds: int,
    voiceover_text: str,
    brief: Mapping[str, Any],
    timeline: Mapping[str, Any],
    render_plan: Mapping[str, Any],
    selected_root: Path,
    artifact_store: LocalArtifactStore,
    tenant_id: str,
    created_by_run_id: str,
    allow_edge_tts: bool,
    render_executor: RenderExecutor | None,
) -> WorkerRenderResult:
    if execution_mode == "plan_only":
        return WorkerRenderResult(state="not_requested")
    if not execute_real_render:
        return WorkerRenderResult(
            state="not_requested",
            evidence={"reason_code": "worker_real_render_requires_execute_flag"},
        )
    media_paths = _worker_media_paths(worker_media_input, worker_media_inputs)
    if not media_paths:
        return WorkerRenderResult(
            state="blocked",
            failure_reason="worker_media_input_required_for_real_render",
        )

    reference_path = Path(worker_reference_template_input) if worker_reference_template_input else None
    voiceover_audio_path = Path(worker_voiceover_audio_input) if worker_voiceover_audio_input else None
    bgm_audio_path = Path(worker_bgm_audio_input) if worker_bgm_audio_input else None
    executor = render_executor or _default_real_render_executor
    work_dir = selected_root / "_internal_worker_real_render"
    work_dir.mkdir(parents=True, exist_ok=True)
    request = WorkerRenderRequest(
        media_path=media_paths[0],
        reference_template_path=reference_path,
        target_duration_seconds=target_duration_seconds,
        voiceover_text=voiceover_text,
        brief=brief,
        timeline=timeline,
        render_plan=render_plan,
        work_dir=work_dir,
        artifact_store=artifact_store,
        tenant_id=tenant_id,
        created_by_run_id=created_by_run_id,
        allow_edge_tts=allow_edge_tts,
        media_paths=media_paths,
        material_role_map=_validated_material_role_map(worker_material_role_map, len(media_paths)),
        subtitle_enabled=bool(worker_subtitle_enabled),
        subtitle_texts=_clean_subtitle_texts(worker_subtitle_texts),
        voiceover_audio_path=voiceover_audio_path,
        bgm_audio_path=bgm_audio_path,
        bgm_enabled=bool(worker_bgm_enabled),
        bgm_start_seconds=max(0.0, float(worker_bgm_start_seconds or 0.0)),
        render_width=int(render_settings["width"]),
        render_height=int(render_settings["height"]),
        render_aspect_ratio=str(render_settings["aspect_ratio"]),
        render_fps=int(render_settings["fps"]),
        video_crf=int(render_settings["video_crf"]),
        subtitle_font_size=int(render_settings["subtitle_font_size"]),
        subtitle_font_color=str(render_settings["subtitle_font_color"]),
        subtitle_outline_color=str(render_settings["subtitle_outline_color"]),
        subtitle_outline_width=int(render_settings["subtitle_outline_width"]),
        bgm_volume_db=float(render_settings["bgm_volume_db"]),
        voice_volume_db=float(render_settings["voice_volume_db"]),
    )
    try:
        result = executor(request)
    except (OSError, subprocess.SubprocessError, TimeoutError) as exc:
        return WorkerRenderResult(
            state="failed",
            failure_reason=f"worker_real_render_failed:{type(exc).__name__}",
            media_decode_or_render_performed=True,
        )
    if result.state not in WORKER_EXECUTION_STATES:
        return WorkerRenderResult(
            state="failed",
            failure_reason="worker_render_executor_returned_invalid_state",
            media_decode_or_render_performed=result.media_decode_or_render_performed,
        )
    return result


def _worker_media_paths(
    worker_media_input: str | Path | None,
    worker_media_inputs: Sequence[str | Path] | None,
) -> list[Path]:
    paths: list[Path] = []
    for value in [worker_media_input, *(worker_media_inputs or [])]:
        if value is None:
            continue
        path = Path(value)
        if path not in paths:
            paths.append(path)
    return paths


def _validated_material_role_map(
    material_role_map: Mapping[str, int] | None,
    media_count: int,
) -> dict[str, int]:
    if not material_role_map or media_count <= 0:
        return {}
    validated: dict[str, int] = {}
    for key, value in material_role_map.items():
        try:
            index = int(value)
        except (TypeError, ValueError):
            continue
        validated[str(key)] = max(0, min(media_count - 1, index))
    return validated


def _clean_subtitle_texts(values: Sequence[str] | None) -> list[str]:
    cleaned: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in cleaned:
            cleaned.append(text)
    return cleaned[:8]


def _execution_report(
    *,
    execution_mode: str,
    execute_real_render: bool,
    worker_result: WorkerRenderResult,
    target_duration_seconds: int,
    result_artifact_state: str,
    visual_evidence_state: str,
    audio_evidence_state: str,
    subtitle_evidence_state: str,
    timeline_evidence_state: str,
    qc_report_state: str,
    human_review_result: str,
) -> dict[str, Any]:
    evidence_states = {
        "result_artifact": result_artifact_state,
        "visual_evidence": visual_evidence_state,
        "audio_evidence": audio_evidence_state,
        "subtitle_evidence": subtitle_evidence_state,
        "timeline_evidence": timeline_evidence_state,
        "qc_report": qc_report_state,
    }
    if worker_result.state == "completed":
        evidence_states = {key: "ready" for key in evidence_states}
    return public_safe(
        {
            "schema": CREATIVE_EDIT_EXECUTION_REPORT_SCHEMA,
            "contract": "creative_edit_execution_report.v0",
            "execution_mode": execution_mode,
            "execute_real_render_requested": bool(execute_real_render),
            "worker_execution_state": worker_result.state,
            "target_duration_seconds": target_duration_seconds,
            "media_decode_or_render_performed": worker_result.media_decode_or_render_performed,
            "worker_result_failure_reason": worker_result.failure_reason,
            "worker_evidence": worker_result.evidence,
            "evidence_states": evidence_states,
            "all_required_evidence_ready": all(state == "ready" for state in evidence_states.values()),
            "human_review_result": human_review_result,
            "platform_core_state_mutated": False,
            "delivery_publish_allowed": False,
        }
    )


def _runner_decision(
    *,
    execution_report: Mapping[str, Any],
    human_review_result: str,
) -> dict[str, Any]:
    execution_mode = str(execution_report.get("execution_mode") or "")
    worker_state = str(execution_report.get("worker_execution_state") or "")
    evidence_ready = execution_report.get("all_required_evidence_ready") is True
    if execution_mode == "plan_only":
        status = "creative_edit_runner_plan_ready_for_platform_dispatch"
    elif worker_state == "not_requested":
        status = "creative_edit_runner_waiting_for_worker_execution"
    elif worker_state == "blocked":
        status = "creative_edit_runner_blocked_missing_worker_input"
    elif worker_state == "failed":
        status = "creative_edit_runner_failed"
    elif not evidence_ready:
        status = "creative_edit_runner_blocked_missing_evidence"
    elif human_review_result == "accepted":
        status = "creative_edit_runner_result_ready_for_platform_acceptance"
    elif human_review_result == "rejected":
        status = "creative_edit_runner_result_rejected"
    else:
        status = "creative_edit_runner_result_pending_human_review"
    return {
        "decision_status": status,
        "blocking_check_ids": _blocking_check_ids(status, execution_report),
        "platform_core_may_accept_runner_result": status
        == "creative_edit_runner_result_ready_for_platform_acceptance",
        "platform_core_may_request_repair": status
        in {
            "creative_edit_runner_result_rejected",
            "creative_edit_runner_blocked_missing_evidence",
            "creative_edit_runner_failed",
        },
        "toolkit_publishes_delivery": False,
        "toolkit_mutates_platform_core_state": False,
        "platform_core_repository_mutation_enabled": False,
        "next_recommended_step": _next_recommended_step(status),
    }


def _quality_gate(
    *,
    brief: Mapping[str, Any],
    timeline: Mapping[str, Any],
    render_plan: Mapping[str, Any],
    qc_plan: Mapping[str, Any],
    execution_report: Mapping[str, Any],
    decision: Mapping[str, Any],
    source_artifact_refs: Mapping[str, Any],
) -> dict[str, Any]:
    brief_valid = brief.get("schema") == CREATIVE_EDIT_BRIEF_SCHEMA
    timeline_valid = timeline.get("schema") == CREATIVE_EDIT_TIMELINE_SCHEMA
    render_plan_valid = render_plan.get("schema") == CREATIVE_EDIT_RENDER_PLAN_SCHEMA
    qc_plan_valid = qc_plan.get("schema") == CREATIVE_EDIT_QC_PLAN_SCHEMA
    execution_report_valid = execution_report.get("schema") == CREATIVE_EDIT_EXECUTION_REPORT_SCHEMA
    delivery_not_published = decision.get("toolkit_publishes_delivery") is False
    platform_not_mutated = decision.get("toolkit_mutates_platform_core_state") is False
    source_refs_present = all(
        source_artifact_refs.get(key)
        for key in {
            "creative_edit_brief",
            "timeline_plan",
            "render_plan",
            "qc_plan",
            "execution_report",
        }
    )
    contract_valid = all(
        [
            brief_valid,
            timeline_valid,
            render_plan_valid,
            qc_plan_valid,
            execution_report_valid,
            delivery_not_published,
            platform_not_mutated,
            source_refs_present,
        ]
    )
    return {
        "status": decision["decision_status"] if contract_valid else "creative_edit_runner_contract_blocked",
        "contract_valid": contract_valid,
        "blocking_reasons": [] if contract_valid else ["creative_edit_runner_contract_invalid"],
        "checks": {
            "brief_valid": brief_valid,
            "timeline_valid": timeline_valid,
            "render_plan_valid": render_plan_valid,
            "qc_plan_valid": qc_plan_valid,
            "execution_report_valid": execution_report_valid,
            "toolkit_delivery_publish_disabled": delivery_not_published,
            "platform_core_repository_not_mutated": platform_not_mutated,
            "source_artifact_refs_present": source_refs_present,
        },
    }


def _runner_package(
    *,
    tenant_id: str,
    user_id: str,
    project_id: str,
    platform_job_id: str,
    platform_run_id: str,
    worker_id: str,
    backend_id: str,
    brief: Mapping[str, Any],
    timeline: Mapping[str, Any],
    render_plan: Mapping[str, Any],
    qc_plan: Mapping[str, Any],
    execution_report: Mapping[str, Any],
    decision: Mapping[str, Any],
    quality_gate: Mapping[str, Any],
    source_artifact_refs: Mapping[str, Any],
    worker_execution_state: str,
) -> dict[str, Any]:
    return public_safe(
        {
            "schema": CREATIVE_EDIT_RUNNER_PACKAGE_SCHEMA,
            "contract": "creative_edit_runner_package.v0",
            "summary": {
                "package_status": quality_gate["status"],
                "execution_mode": execution_report.get("execution_mode"),
                "worker_execution_state": worker_execution_state,
                "media_decode_or_render_performed": execution_report.get(
                    "media_decode_or_render_performed"
                ),
                "all_required_evidence_ready": execution_report.get("all_required_evidence_ready"),
                "human_review_result": execution_report.get("human_review_result"),
                "platform_core_may_accept_runner_result": decision[
                    "platform_core_may_accept_runner_result"
                ],
                "platform_core_may_request_repair": decision["platform_core_may_request_repair"],
                "platform_core_state_mutated": False,
                "delivery_publish_allowed": False,
                "next_recommended_step": decision["next_recommended_step"],
            },
            "tenant_id": tenant_id,
            "user_id": user_id,
            "project_id": project_id,
            "platform_job_id": platform_job_id,
            "platform_run_id": platform_run_id,
            "worker_id": worker_id,
            "backend_id": backend_id,
            "creative_edit_brief": dict(brief),
            "timeline_plan": dict(timeline),
            "render_plan": dict(render_plan),
            "qc_plan": dict(qc_plan),
            "execution_report": dict(execution_report),
            "runner_decision": dict(decision),
            "source_artifact_refs": dict(source_artifact_refs),
            "quality_gate": dict(quality_gate),
            "platform_boundary": _platform_boundary(
                execution_report=execution_report,
                decision=decision,
            ),
        }
    )


def _platform_boundary(
    *,
    execution_report: Mapping[str, Any],
    decision: Mapping[str, Any],
) -> dict[str, Any]:
    execution_mode = execution_report.get("execution_mode")
    return {
        "agent_lifecycle_owner": "platform_core",
        "job_state_owner": "platform_core",
        "approval_owner": "platform_core",
        "queue_owner": "local_studio_or_platform",
        "worker_runtime_owner": "video_editing_toolkit",
        "artifact_ref_only": True,
        "raw_worker_locator_exposed": False,
        "toolkit_worker_may_read_resolved_media": execution_mode == "worker_real_render",
        "toolkit_worker_may_execute_real_render": execution_mode == "worker_real_render",
        "toolkit_decodes_or_renders_only_when_worker_explicitly_executes": True,
        "toolkit_posts_production_runspec": False,
        "toolkit_leases_production_jobs": False,
        "toolkit_publishes_delivery": False,
        "toolkit_mutates_platform_core_state": False,
        "platform_core_repository_mutation": False,
        "platform_core_may_accept_runner_result": decision["platform_core_may_accept_runner_result"],
        "platform_core_may_request_repair": decision["platform_core_may_request_repair"],
    }


def _default_real_render_executor(request: WorkerRenderRequest) -> WorkerRenderResult:
    media_paths = [path for path in (request.media_paths or [request.media_path]) if path.is_file()]
    if not media_paths:
        return WorkerRenderResult(
            state="blocked",
            failure_reason="worker_media_input_not_found",
        )
    ffmpeg = _binary_path("ffmpeg")
    ffprobe = _binary_path("ffprobe")
    if ffmpeg is None or ffprobe is None:
        return WorkerRenderResult(
            state="failed",
            failure_reason="ffmpeg_or_ffprobe_unavailable",
        )
    with tempfile.TemporaryDirectory(prefix="vet-p2-21-render-", dir=request.work_dir) as temp_dir:
        temp_root = Path(temp_dir)
        generated_bgm_path = temp_root / "instrumental_bgm.wav"
        bgm_path = generated_bgm_path
        bgm_generated = True
        generated_voice_path = temp_root / "voiceover.mp3"
        voice_path = generated_voice_path
        output_path = temp_root / "creative-edit-final.mp4"
        if not request.bgm_enabled:
            _write_silence_wav(generated_bgm_path, duration_seconds=request.target_duration_seconds)
        elif request.bgm_audio_path is not None and request.bgm_audio_path.is_file():
            bgm_path = request.bgm_audio_path
            bgm_generated = False
        else:
            _write_bgm_wav(generated_bgm_path, duration_seconds=request.target_duration_seconds)
        voice_ready = False
        if request.voiceover_audio_path is not None and request.voiceover_audio_path.is_file():
            voice_path = request.voiceover_audio_path
            voice_ready = True
        elif request.allow_edge_tts and request.voiceover_text.strip():
            try:
                _synthesize_edge_tts(
                    text=request.voiceover_text,
                    output_path=generated_voice_path,
                    timeout_seconds=180,
                )
                voice_path = generated_voice_path
                voice_ready = voice_path.is_file() and voice_path.stat().st_size > 1000
            except (OSError, subprocess.SubprocessError):
                voice_ready = False
        filter_complex = _ffmpeg_filter_complex(
            target_duration_seconds=request.target_duration_seconds,
            include_voice=voice_ready,
            bgm_start_seconds=request.bgm_start_seconds,
            video_input_count=len(media_paths),
            material_role_map=request.material_role_map,
            subtitle_enabled=request.subtitle_enabled,
            subtitle_texts=request.subtitle_texts,
            include_bgm=request.bgm_enabled,
            render_width=request.render_width,
            render_height=request.render_height,
            render_fps=request.render_fps,
            subtitle_font_size=request.subtitle_font_size,
            subtitle_font_color=request.subtitle_font_color,
            subtitle_outline_color=request.subtitle_outline_color,
            subtitle_outline_width=request.subtitle_outline_width,
            bgm_volume_db=request.bgm_volume_db,
            voice_volume_db=request.voice_volume_db,
        )
        inputs: list[str] = []
        for media_path in media_paths:
            inputs.extend(["-i", str(media_path)])
        bgm_input_index = len(media_paths) + (1 if voice_ready else 0)
        if voice_ready:
            inputs.extend(["-i", str(voice_path)])
            if not bgm_generated:
                inputs.extend(["-stream_loop", "-1"])
            inputs.extend(["-i", str(bgm_path)])
        else:
            if not bgm_generated:
                inputs.extend(["-stream_loop", "-1"])
            inputs.extend(["-i", str(bgm_path)])
        command = [
            ffmpeg,
            "-hide_banner",
            "-nostdin",
            "-y",
            *inputs,
            "-filter_complex",
            filter_complex,
            "-map",
            "[v]",
            "-map",
            "[a]",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            str(request.video_crf),
            "-c:a",
            "aac",
            "-b:a",
            "160k",
            "-movflags",
            "+faststart",
            str(output_path),
        ]
        completed = subprocess.run(
            command,
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=360,
        )
        if completed.returncode != 0 or not output_path.is_file():
            return WorkerRenderResult(
                state="failed",
                failure_reason="ffmpeg_render_failed",
                evidence={"stderr_tail": completed.stderr[-500:]},
                media_decode_or_render_performed=True,
            )
        probe = _probe_output(ffprobe, output_path)
        qc_payload = {
            "schema": "video_editing_toolkit.creative_edit_worker_qc_report.v0",
            "duration_seconds": probe.get("duration_seconds"),
            "resolution": probe.get("resolution"),
            "audio_present": probe.get("audio_present"),
            "voiceover_generated": voice_ready,
            "input_video_count": len(media_paths),
            "human_review_required": True,
        }
        qc_path = temp_root / "qc_report.json"
        qc_path.write_text(json.dumps(qc_payload, ensure_ascii=False, indent=2), encoding="utf-8")
        refs: dict[str, dict[str, Any]] = {
            "final_render": request.artifact_store.put_file(
                source_path=output_path,
                artifact_type="creative_edit_final_render",
                owner_tenant_id=request.tenant_id,
                created_by_run_id=request.created_by_run_id,
                filename="creative-edit-final.mp4",
                mime_type="video/mp4",
                access_policy={"scope": "tenant_project", "handoff": "creative_edit_final_render"},
            ).to_public_dict(),
            "instrumental_bgm": request.artifact_store.put_file(
                source_path=bgm_path,
                artifact_type="creative_edit_instrumental_bgm",
                owner_tenant_id=request.tenant_id,
                created_by_run_id=request.created_by_run_id,
                filename=f"instrumental_bgm{bgm_path.suffix or '.wav'}",
                mime_type=_audio_mime_type(bgm_path),
                access_policy={"scope": "tenant_project", "handoff": "creative_edit_instrumental_bgm"},
            ).to_public_dict(),
            "qc_report": request.artifact_store.put_file(
                source_path=qc_path,
                artifact_type="creative_edit_worker_qc_report",
                owner_tenant_id=request.tenant_id,
                created_by_run_id=request.created_by_run_id,
                filename="qc_report.json",
                mime_type="application/json",
                access_policy={"scope": "tenant_project", "handoff": "creative_edit_worker_qc_report"},
            ).to_public_dict(),
        }
        if voice_ready:
            refs["voiceover_audio"] = request.artifact_store.put_file(
                source_path=voice_path,
                artifact_type="creative_edit_voiceover_audio",
                owner_tenant_id=request.tenant_id,
                created_by_run_id=request.created_by_run_id,
                filename="voiceover.mp3",
                mime_type="audio/mpeg",
                access_policy={"scope": "tenant_project", "handoff": "creative_edit_voiceover_audio"},
            ).to_public_dict()
    return WorkerRenderResult(
        state="completed",
        artifact_refs=refs,
        evidence={
            "media_probe": probe,
            "renderer_settings": {
                "resolution": {"width": request.render_width, "height": request.render_height},
                "aspect_ratio": request.render_aspect_ratio,
                "fps": request.render_fps,
                "video_crf": request.video_crf,
                "subtitle_font_size": request.subtitle_font_size,
                "subtitle_font_color": request.subtitle_font_color,
                "subtitle_outline_color": request.subtitle_outline_color,
                "subtitle_outline_width": request.subtitle_outline_width,
                "bgm_volume_db": request.bgm_volume_db,
                "voice_volume_db": request.voice_volume_db,
            },
            "voiceover_generated": voice_ready,
            "input_video_count": len(media_paths),
            "input_videos": [str(path) for path in media_paths],
            "material_role_map": dict(request.material_role_map),
            "bgm_generated": bgm_generated,
            "bgm_source": "disabled_silence" if not request.bgm_enabled else "generated" if bgm_generated else "local_audio_file",
            "bgm_start_seconds": request.bgm_start_seconds,
            "subtitle_enabled": request.subtitle_enabled,
            "subtitle_texts": list(request.subtitle_texts),
            "render_profile": "ffmpeg_h264_aac",
        },
        media_decode_or_render_performed=True,
    )


def _ffmpeg_filter_complex(
    *,
    target_duration_seconds: int,
    include_voice: bool,
    bgm_start_seconds: float = 0.0,
    video_input_count: int = 1,
    material_role_map: Mapping[str, int] | None = None,
    subtitle_enabled: bool = True,
    subtitle_texts: Sequence[str] | None = None,
    include_bgm: bool = True,
    render_width: int = 720,
    render_height: int = 1280,
    render_fps: int = 30,
    subtitle_font_size: int = 44,
    subtitle_font_color: str = "white",
    subtitle_outline_color: str = "black",
    subtitle_outline_width: int = 5,
    bgm_volume_db: float = -18.0,
    voice_volume_db: float = 0.0,
) -> str:
    bgm_start = max(0.0, float(bgm_start_seconds or 0.0))
    video_count = max(1, int(video_input_count or 1))
    width = _clamp_int(render_width, default=720, minimum=144, maximum=7680)
    height = _clamp_int(render_height, default=1280, minimum=144, maximum=7680)
    fps = _clamp_int(render_fps, default=30, minimum=12, maximum=120)
    subtitle_size = _clamp_int(subtitle_font_size, default=44, minimum=8, maximum=180)
    subtitle_color = _safe_color(subtitle_font_color, default="white")
    outline_color = _safe_color(subtitle_outline_color, default="black")
    outline_width = _clamp_int(subtitle_outline_width, default=5, minimum=0, maximum=24)
    bgm_volume = _volume_factor_from_db(bgm_volume_db, default_db=-18.0) if include_bgm else 0.0
    voice_volume = _volume_factor_from_db(voice_volume_db, default_db=0.0)
    segments = [
        (0.2, 2.2, "cover", "overall_door"),
        (3.0, 1.4, "入户门安装完成", "door_body"),
        (45.0, 1.2, "入户门安装完成", "detail"),
        (6.0, 1.4, "入户门安装完成", "door_body"),
        (15.0, 1.6, "现场走廊环境", "corridor"),
        (18.0, 1.5, "现场走廊环境", "corridor"),
        (25.5, 1.4, "整体效果记录", "door_body"),
        (30.0, 1.2, "整体效果记录", "detail"),
        (48.0, 1.5, "整体效果记录", "door_body"),
        (51.0, 1.5, "整体效果记录", "door_body"),
        (0.1, 1.3, "入户门安装完成", "detail"),
        (27.0, max(0.1, target_duration_seconds - 16.2), "整体效果记录", "door_body"),
    ]
    chains: list[str] = []
    subtitle_sequence = _subtitle_sequence(subtitle_texts)
    for index, (start, duration, caption, shot_kind) in enumerate(segments):
        source_index = _source_index_for_shot_kind(
            shot_kind=shot_kind,
            fallback_index=index,
            video_count=video_count,
            material_role_map=material_role_map,
        )
        video_filter = (
            f"[{source_index}:v]trim=start={start}:duration={duration},setpts=PTS-STARTPTS,"
            f"{_crop_filter(shot_kind, width=width, height=height)},setsar=1,fps={fps},deshake,"
            "eq=contrast=1.08:saturation=1.14:brightness=0.016,"
            "unsharp=5:5:0.45:3:3:0.2"
        )
        if index > 0:
            video_filter += ",drawbox=x=0:y=0:w=iw:h=ih:color=white@0.18:t=fill:enable='lt(t,0.08)'"
        if caption == "cover":
            cover_y = max(20, int(height * 0.53))
            cover_box_h = max(64, int(subtitle_size * 1.9))
            cover_box_w = max(260, min(width - 20, int(width * 0.54)))
            video_filter += f",drawbox=x=0:y={cover_y}:w={cover_box_w}:h={cover_box_h}:color=yellow@1:t=fill"
            video_filter += _draw_text(
                "安装记录",
                x=str(max(16, int(width * 0.13))),
                y=str(cover_y + max(8, int(subtitle_size * 0.42))),
                size=max(subtitle_size, int(subtitle_size * 1.28)),
                font_color=subtitle_color,
                outline_color=outline_color,
                outline_width=outline_width,
            )
            video_filter += _draw_text(
                "入户门安装",
                x=str(max(16, int(width * 0.09))),
                y=str(cover_y + cover_box_h + max(26, int(subtitle_size * 0.75))),
                size=max(subtitle_size, int(subtitle_size * 1.28)),
                font_color=subtitle_color,
                outline_color=outline_color,
                outline_width=outline_width,
            )
            video_filter += _draw_text(
                "现场记录",
                x=str(max(16, int(width * 0.09))),
                y=str(cover_y + cover_box_h + max(78, int(subtitle_size * 1.85))),
                size=max(subtitle_size, int(subtitle_size * 1.28)),
                font_color=subtitle_color,
                outline_color=outline_color,
                outline_width=outline_width,
            )
        elif subtitle_enabled:
            video_filter += _draw_text(
                _segment_subtitle(caption, index, subtitle_sequence),
                x="(w-text_w)/2",
                y=f"h-{max(40, int(height * 0.117))}",
                size=subtitle_size,
                font_color=subtitle_color,
                outline_color=outline_color,
                outline_width=outline_width,
            )
        video_filter += f"[v{index}]"
        chains.append(video_filter)
    concat_inputs = "".join(f"[v{index}]" for index in range(len(segments)))
    video_chain = (
        ";".join(chains)
        + f";{concat_inputs}concat=n={len(segments)}:v=1:a=0,"
        + f"trim=duration={target_duration_seconds},setpts=PTS-STARTPTS,format=yuv420p[v]"
    )
    voice_input_index = video_count
    bgm_input_index = video_count + 1 if include_voice else video_count
    if include_voice:
        audio_chain = (
            f";[{voice_input_index}:a]adelay=350|350,apad,atrim=duration={target_duration_seconds},"
            f"asetpts=PTS-STARTPTS,volume={voice_volume:.6f}[voice]"
            f";[{bgm_input_index}:a]atrim=start={bgm_start}:duration={target_duration_seconds},asetpts=PTS-STARTPTS,volume={bgm_volume:.6f}[bgm]"
            f";[voice][bgm]amix=inputs=2:duration=longest:dropout_transition=0,"
            f"loudnorm=I=-16:LRA=9:TP=-1.3,atrim=duration={target_duration_seconds}[a]"
        )
    else:
        audio_chain = (
            f";[{bgm_input_index}:a]atrim=start={bgm_start}:duration={target_duration_seconds},asetpts=PTS-STARTPTS,"
            f"volume={bgm_volume:.6f},loudnorm=I=-18:LRA=9:TP=-1.3[a]"
        )
    return video_chain + audio_chain


def _subtitle_sequence(subtitle_texts: Sequence[str] | None) -> list[str]:
    return [str(text).strip() for text in subtitle_texts or [] if str(text).strip()]


def _segment_subtitle(default_caption: str, index: int, subtitle_texts: Sequence[str]) -> str:
    if not subtitle_texts:
        return default_caption
    return subtitle_texts[(index - 1) % len(subtitle_texts)]


def _source_index_for_shot_kind(
    *,
    shot_kind: str,
    fallback_index: int,
    video_count: int,
    material_role_map: Mapping[str, int] | None,
) -> int:
    aliases = {
        "overall_door": ("overall_door", "cover", "final_hold", "opening_hero"),
        "door_body": ("door_body", "product_body_and_detail"),
        "detail": ("detail", "product_detail", "product_body_and_detail"),
        "corridor": ("corridor", "site_context"),
    }.get(shot_kind, (shot_kind,))
    if material_role_map:
        for key in aliases:
            if key not in material_role_map:
                continue
            try:
                return max(0, min(video_count - 1, int(material_role_map[key])))
            except (TypeError, ValueError):
                continue
    return fallback_index % max(1, video_count)


def _crop_filter(shot_kind: str, *, width: int = 720, height: int = 1280) -> str:
    width = _clamp_int(width, default=720, minimum=144, maximum=7680)
    height = _clamp_int(height, default=1280, minimum=144, maximum=7680)
    zoom = 1.0
    if shot_kind == "detail":
        zoom = 1.25
    elif shot_kind == "corridor":
        zoom = 1.125
    scale_width = max(width, int(math.ceil(width * zoom)))
    scale_height = max(height, int(math.ceil(height * zoom)))
    return (
        f"scale={scale_width}:{scale_height}:force_original_aspect_ratio=increase,"
        f"crop={width}:{height}:x=(iw-{width})/2:y=(ih-{height})/2"
    )


def _draw_text(
    text: str,
    *,
    x: str,
    y: str,
    size: int,
    font_color: str = "white",
    outline_color: str = "black",
    outline_width: int = 5,
) -> str:
    fontfile = _drawtext_fontfile()
    font_part = f"fontfile='{fontfile}':" if fontfile else ""
    safe_size = _clamp_int(size, default=44, minimum=8, maximum=180)
    safe_outline_width = _clamp_int(outline_width, default=5, minimum=0, maximum=24)
    return (
        f",drawtext={font_part}text='{_escape_drawtext(text)}':x={x}:y={y}:"
        f"fontsize={safe_size}:fontcolor={_safe_color(font_color, default='white')}:"
        f"borderw={safe_outline_width}:bordercolor={_safe_color(outline_color, default='black')}"
    )


def _volume_factor_from_db(value: Any, *, default_db: float) -> float:
    db = _clamp_float(value, default=default_db, minimum=-80.0, maximum=12.0)
    return max(0.0, min(4.0, math.pow(10.0, db / 20.0)))


def _drawtext_fontfile() -> str | None:
    windows_font = Path("C:/Windows/Fonts/simhei.ttf")
    if windows_font.is_file():
        return "C\\:/Windows/Fonts/simhei.ttf"
    return None


def _escape_drawtext(text: str) -> str:
    return (
        text.replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
    )


def _write_bgm_wav(path: Path, *, duration_seconds: int) -> None:
    sample_rate = 44100
    total = int(sample_rate * (duration_seconds + 0.2))
    bpm = 126
    beat_seconds = 60.0 / bpm
    melody = (440.0, 494.0, 523.0, 587.0, 659.0, 587.0, 523.0, 494.0)
    pcm = bytearray()
    for index in range(total):
        t = index / sample_rate
        beat_index = int(t / (beat_seconds / 2))
        lead_freq = melody[beat_index % len(melody)]
        envelope = math.exp(-((t % (beat_seconds / 2)) * 8.0))
        lead = 0.13 * envelope * math.sin(2 * math.pi * lead_freq * t)
        chord = 0.05 * math.sin(2 * math.pi * 220.0 * t) + 0.04 * math.sin(2 * math.pi * 330.0 * t)
        beat_phase = t % beat_seconds
        kick = 0.28 * math.exp(-beat_phase * 28.0) * math.sin(2 * math.pi * 82.0 * beat_phase)
        value = max(-1.0, min(1.0, lead + chord + kick))
        pcm.extend(int(value * 24576).to_bytes(2, byteorder="little", signed=True))
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(bytes(pcm))


def _write_silence_wav(path: Path, *, duration_seconds: int) -> None:
    sample_rate = 44100
    total = int(sample_rate * max(0.2, duration_seconds + 0.2))
    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(b"\x00\x00" * total)


def _audio_mime_type(path: Path) -> str:
    return {
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
        ".flac": "audio/flac",
        ".ogg": "audio/ogg",
    }.get(path.suffix.casefold(), "application/octet-stream")


def _synthesize_edge_tts(*, text: str, output_path: Path, timeout_seconds: int | float) -> None:
    command = _edge_tts_command()
    if command is None:
        raise OSError("edge-tts is unavailable")
    subprocess.run(
        [
            *command,
            "--voice",
            "zh-CN-YunyangNeural",
            "--rate",
            "+10%",
            "--text",
            text,
            "--write-media",
            str(output_path),
        ],
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout_seconds,
    )


def _probe_output(ffprobe: str, output_path: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(output_path),
        ],
        capture_output=True,
        check=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    data = json.loads(completed.stdout)
    fmt = mapping(data.get("format"))
    video = next(
        (stream for stream in data.get("streams", []) if mapping(stream).get("codec_type") == "video"),
        {},
    )
    audio_present = any(
        mapping(stream).get("codec_type") == "audio" for stream in data.get("streams", [])
    )
    video_map = mapping(video)
    return {
        "duration_seconds": _safe_float(fmt.get("duration")),
        "resolution": {
            "width": _safe_int(video_map.get("width")),
            "height": _safe_int(video_map.get("height")),
        },
        "audio_present": audio_present,
    }


def _binary_path(name: str) -> str | None:
    local_binary = _local_binary_path(name)
    if local_binary is not None:
        return str(local_binary)
    found = shutil.which(name)
    if found is not None:
        return found
    if os.environ.get("VIDEO_TOOLKIT_USE_STATIC_FFMPEG", "").casefold() not in {
        "1",
        "true",
        "yes",
        "on",
    }:
        return None
    try:
        import static_ffmpeg
    except ImportError:
        return None
    try:
        static_ffmpeg.add_paths()
    except Exception:
        return None
    return shutil.which(name)


def _local_binary_path(name: str) -> Path | None:
    candidates = _local_binary_candidates(name)
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _local_binary_candidates(name: str) -> list[Path]:
    executable_names = [name] if Path(name).suffix else [name, f"{name}.exe"]
    dirs: list[Path] = []
    env_keys = (
        "VIDEO_TOOLKIT_FFMPEG_BIN",
        "VIDEO_TOOLKIT_FFMPEG_DIR",
        "SMART_VIDEO_CUT_FFMPEG_BIN",
        "SMART_VIDEO_CUT_FFMPEG_DIR",
    )
    for key in env_keys:
        value = os.environ.get(key)
        if value:
            dirs.append(Path(value).expanduser())
    project_root = Path(__file__).resolve().parents[2]
    packaged_root = project_root / "packages" / "ffmpeg"
    dirs.extend(
        [
            packaged_root / "bin",
            packaged_root,
            project_root / "ffmpeg" / "bin",
            project_root / "ffmpeg",
        ]
    )
    candidates: list[Path] = []
    for directory in dirs:
        for executable_name in executable_names:
            candidates.append(directory / executable_name)
    if packaged_root.exists():
        for executable_name in executable_names:
            candidates.extend(packaged_root.rglob(executable_name))
    return candidates


def _edge_tts_command() -> list[str] | None:
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        binary = shutil.which("edge-tts") or shutil.which("edge-tts.exe")
        return [binary] if binary else None
    return [sys.executable, "-m", "edge_tts"]


def _selected_voiceover_text(*, voiceover_mode: str, voiceover_text: str) -> str:
    if voiceover_mode == "none":
        return ""
    if voiceover_mode == "provided_text" and voiceover_text.strip():
        return voiceover_text.strip()
    if voiceover_text.strip() and voiceover_text != DEFAULT_VOICEOVER_TEXT:
        return voiceover_text.strip()
    return DEFAULT_AD_VOICEOVER_TEXT


def _blocking_check_ids(status: str, execution_report: Mapping[str, Any]) -> list[str]:
    if status == "creative_edit_runner_blocked_missing_worker_input":
        return ["worker_media_input"]
    if status == "creative_edit_runner_blocked_missing_evidence":
        return [
            key
            for key, value in mapping(execution_report.get("evidence_states")).items()
            if value != "ready"
        ]
    if status == "creative_edit_runner_failed":
        return ["worker_real_render"]
    if status == "creative_edit_runner_result_pending_human_review":
        return ["human_review_hold"]
    if status == "creative_edit_runner_result_rejected":
        return ["human_review_rejected"]
    if status == "creative_edit_runner_waiting_for_worker_execution":
        return ["worker_execution_not_started"]
    return []


def _next_recommended_step(status: str) -> str:
    return {
        "creative_edit_runner_plan_ready_for_platform_dispatch": "dispatch_creative_edit_runner_to_worker_when_approved",
        "creative_edit_runner_waiting_for_worker_execution": "execute_worker_real_render_with_resolved_media",
        "creative_edit_runner_blocked_missing_worker_input": "attach_resolved_worker_media_before_execution",
        "creative_edit_runner_failed": "inspect_worker_render_failure_and_retry",
        "creative_edit_runner_blocked_missing_evidence": "attach_final_render_visual_audio_timeline_and_qc_artifacts",
        "creative_edit_runner_result_pending_human_review": "complete_human_review_before_platform_acceptance",
        "creative_edit_runner_result_rejected": "request_repair_patch_from_edit_agent",
        "creative_edit_runner_result_ready_for_platform_acceptance": "handoff_runner_artifacts_to_platform_acceptance",
    }.get(status, "manual_platform_review_required")


def _put_json_artifact(
    *,
    artifact_store: LocalArtifactStore,
    tenant_id: str,
    created_by_run_id: str,
    artifact_type: str,
    filename: str,
    payload: Mapping[str, Any] | Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    ref: ArtifactRef = artifact_store.put_bytes(
        content=json.dumps(
            public_safe(payload),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8"),
        artifact_type=artifact_type,
        owner_tenant_id=tenant_id,
        created_by_run_id=created_by_run_id,
        filename=filename,
        mime_type="application/json",
        access_policy={"scope": "tenant_project", "handoff": artifact_type},
    )
    return ref.to_public_dict()


def _safe_summary(value: str | None, *, default: str) -> str:
    if not isinstance(value, str) or not value.strip():
        return default
    return _safe_label(value, default=default, max_length=240)


def _safe_label(value: Any, *, default: str, max_length: int = 96) -> str:
    if not isinstance(value, str):
        return default
    cleaned = " ".join(value.replace("\\", "/").split())
    cleaned = cleaned.replace(":", "_")
    return cleaned[:max_length] or default


def _safe_asset_label(value: Any) -> str:
    if not isinstance(value, str):
        return DEFAULT_TEST_MEDIA_LABEL
    label = value.replace("\\", "/").split("/")[-1].strip()
    return label or DEFAULT_TEST_MEDIA_LABEL


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _validate_choice(name: str, value: str, choices: Sequence[str]) -> None:
    if value not in choices:
        raise ValueError(f"{name} must be one of: {', '.join(choices)}")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
