from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

from smart_video_cut.adapter_registry import resolve_adapter_selection
from smart_video_cut.bgm_adapters import prepare_bgm
from smart_video_cut.edit_settings import apply_visible_settings_overrides
from smart_video_cut.export_adapters import export_local_mp4, run_runtime_exports
from smart_video_cut.models import LocalEditTask
from smart_video_cut.local_memory import apply_memory_to_user_request
from smart_video_cut.material_adapters import prepare_material_plan
from smart_video_cut.material_plan import build_material_plan
from smart_video_cut.moss_tts import synthesize_moss_tts
from smart_video_cut.style_package import load_style_package, reference_template_path
from smart_video_cut.subtitle_adapters import prepare_subtitles, subtitle_texts_from_settings
from smart_video_cut.voice_adapters import (
    generate_moss_voiceover,
    legacy_moss_voiceover_result,
    prepare_voiceover,
)


def ensure_video_toolkit_available() -> dict[str, Any]:
    """Import the bundled video-editing-toolkit copy shipped with this app."""

    import video_editing_toolkit  # type: ignore

    module_file = Path(str(getattr(video_editing_toolkit, "__file__", ""))).resolve()
    bundled_root = Path(__file__).resolve().parents[1] / "video_editing_toolkit"
    if bundled_root.resolve() not in {module_file.parent, *module_file.parents}:
        raise RuntimeError(
            "smart-video-cut must use its bundled video_editing_toolkit package, "
            f"but imported {module_file}."
        )
    return {
        "available": True,
        "source": "bundled_copy",
        "module_file": str(module_file),
        "bundled_runtime_dir": str(bundled_root),
        "media_tools": _media_tool_status(),
    }


def _media_tool_status() -> dict[str, Any]:
    from video_editing_toolkit.creative_edit_runner import _binary_path  # type: ignore

    ffmpeg = _binary_tool_status("ffmpeg", resolver=_binary_path)
    ffprobe = _binary_tool_status("ffprobe", resolver=_binary_path)
    return {
        "ready": ffmpeg["available"] is True and ffprobe["available"] is True,
        "ffmpeg": ffmpeg,
        "ffprobe": ffprobe,
    }


def _binary_tool_status(name: str, *, resolver: Any) -> dict[str, Any]:
    path = resolver(name)
    if not path:
        return {"available": False, "path": None, "version": None}
    return {
        "available": True,
        "path": str(path),
        "version": _binary_version(path),
    }


def _binary_version(path: str) -> str | None:
    try:
        completed = subprocess.run(
            [path, "-version"],
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=10,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    first_line = completed.stdout.splitlines()[0] if completed.stdout.splitlines() else ""
    return first_line or None


def run_edit_with_style_package(task: LocalEditTask) -> dict[str, Any]:
    """Run a local edit with the bundled video-editing-toolkit creative runner.

    Integrates task_status tracking, timeline_builder, and version_history.
    """
    from smart_video_cut.task_status import (
        create_task_status,
        update_stage,
        add_observation,
        complete_task,
        fail_task,
        generate_task_id,
    )
    from smart_video_cut.toolkit_protocol import write_local_toolkit_protocol
    from smart_video_cut.timeline_builder import build_timeline_plan, timeline_to_toolkit_format
    from smart_video_cut.version_history import save_version

    selected_task_id = task.task_id or generate_task_id(task.project_id)
    create_task_status(selected_task_id, task.project_id)
    current_stage = "load_style_package"

    try:
        # Stage 1: Load style package
        update_stage(selected_task_id, "load_style_package", status="running")
        toolkit_status = ensure_video_toolkit_available()
        from video_editing_toolkit.creative_edit_runner import (  # type: ignore
            DEFAULT_AD_VOICEOVER_TEXT,
            run_creative_edit_runner,
        )
        from video_editing_toolkit.storage import LocalArtifactStore  # type: ignore

        package = load_style_package(task.style_package)
        settings = apply_visible_settings_overrides(package["visible_settings"], task.settings_overrides)
        adapter_selection = resolve_adapter_selection(settings)
        update_stage(selected_task_id, "load_style_package", status="completed")

        # Stage 2: Build material plan
        current_stage = "build_material_plan"
        update_stage(selected_task_id, "build_material_plan", status="running")
        voice_settings = settings["voice"]
        audio_settings = settings["audio"]
        video_settings = settings["video"]
        subtitle_settings = settings["subtitle"]
        task.output_dir.mkdir(parents=True, exist_ok=True)
        artifact_root = task.output_dir / "_smart_video_cut_artifacts"
        result_json = task.output_dir / "local_studio_toolkit_result.json"
        reference_path = reference_template_path(task.style_package, package)
        voice_provider = str(voice_settings.get("provider") or "")
        voice_mode = str(voice_settings.get("mode") or "generated_male_ad_copy")
        subtitle_adapter_result = prepare_subtitles(
            subtitle_settings=subtitle_settings,
            artifact_root=artifact_root,
        )
        subtitle_enabled = subtitle_adapter_result.get("renderer_subtitle_enabled") is True
        subtitle_texts = list(subtitle_adapter_result.get("renderer_subtitle_texts") or [])
        bgm_adapter_result = prepare_bgm(
            audio_settings=audio_settings,
            execute_real_render=task.execute_real_render,
            artifact_root=artifact_root,
        )
        bgm_enabled = bgm_adapter_result.get("renderer_bgm_enabled") is True
        bgm_audio_path = bgm_adapter_result.get("renderer_bgm_audio_input")
        local_bgm_audio_path = bgm_adapter_result.get("local_bgm_audio_path")
        bgm_start_seconds = _safe_float(bgm_adapter_result.get("renderer_bgm_start_seconds"), default=0.0, minimum=0.0)
        render_width, render_height = _renderer_dimensions(video_settings)
        render_fps = _safe_int(video_settings.get("fps"), default=30, minimum=12, maximum=120)
        render_crf = _safe_int(video_settings.get("crf"), default=22, minimum=14, maximum=35)
        subtitle_font_size = _safe_int(subtitle_settings.get("font_size"), default=44, minimum=8, maximum=180)
        subtitle_outline_width = _safe_int(subtitle_settings.get("outline_width"), default=5, minimum=0, maximum=24)
        bgm_volume_db = _safe_float(audio_settings.get("bgm_volume_db"), default=-18.0, minimum=-80.0, maximum=6.0)
        voice_volume_db = _safe_float(audio_settings.get("voice_volume_db"), default=0.0, minimum=-80.0, maximum=12.0)
        input_video_paths = _selected_input_videos(task)
        material_adapter_result = prepare_material_plan(
            paths=input_video_paths,
            settings=settings,
            build_plan_func=build_material_plan,
        )
        material_plan = material_adapter_result["material_plan"]
        add_observation(selected_task_id, "build_material_plan",
                        f"素材计划策略: {material_plan.get('strategy', 'unknown')}, 素材数: {material_plan.get('material_count', 0)}")
        update_stage(selected_task_id, "build_material_plan", status="completed")

        if not input_video_paths:
            raise ValueError("input_video must point to a readable file")

        # Stage 3: Build edit brief
        current_stage = "build_edit_brief"
        update_stage(selected_task_id, "build_edit_brief", status="running")
        remembered_request, memory_context = apply_memory_to_user_request(
            task.user_request,
            use_memory=task.use_memory,
        )
        user_request = _merge_user_request(
            user_request=remembered_request,
            package=package,
            settings=settings,
        )
        if task.confirmed_brief:
            user_request = f"{user_request}\n\n[客户已确认剪辑标准]\n{task.confirmed_brief.strip()}"
        update_stage(selected_task_id, "build_edit_brief", status="completed")

        # Stage 4: Build timeline
        current_stage = "build_timeline"
        update_stage(selected_task_id, "build_timeline", status="running")
        timeline_plan = build_timeline_plan(
            material_plan=material_plan,
            settings=settings,
            style_package=package,
        )
        # If user provided a timeline override, use it
        if task.timeline_override:
            from smart_video_cut.timeline_model import TimelinePlan as _TP
            timeline_plan = _TP.from_dict(task.timeline_override)
            add_observation(selected_task_id, "build_timeline",
                            f"使用用户编辑的时间线 v{timeline_plan.version}")
        else:
            add_observation(selected_task_id, "build_timeline",
                            f"自动生成时间线: {len(timeline_plan.segments)} 个片段, 总时长 {timeline_plan.total_duration():.1f}s")
        update_stage(selected_task_id, "build_timeline", status="completed")
        toolkit_timeline = timeline_to_toolkit_format(timeline_plan)

        # Stage 5: Generate voiceover
        current_stage = "generate_voiceover"
        update_stage(selected_task_id, "generate_voiceover", status="running")
        voice_adapter_result = prepare_voiceover(
            provider=voice_provider,
            voice_mode=voice_mode,
            execute_real_render=task.execute_real_render,
            allow_edge_tts=task.allow_edge_tts,
            voiceover_text=task.voiceover_text,
            voice_settings=voice_settings,
            artifact_root=artifact_root,
            default_voiceover_text=DEFAULT_AD_VOICEOVER_TEXT,
        )
        selected_voiceover_text = str(voice_adapter_result.get("voiceover_text") or "")
        moss_voiceover = legacy_moss_voiceover_result(voice_adapter_result)
        update_stage(selected_task_id, "generate_voiceover", status="completed")

        # Stage 6: Execute render
        current_stage = "execute_render"
        update_stage(selected_task_id, "execute_render", status="running")
        summary = run_creative_edit_runner(
            user_request=user_request,
            voiceover_text=selected_voiceover_text,
            timeline=toolkit_timeline,
            artifact_root=artifact_root,
            result_json=result_json,
            tenant_id="local_studio_tenant",
            user_id="local_user",
            project_id=task.project_id,
            platform_job_id=f"{task.project_id}_job",
            platform_run_id=f"{task.project_id}_run",
            worker_id="local_studio_worker",
            backend_id="user_local_device",
            test_media_label=_media_label(input_video_paths),
            reference_template_label=str(package.get("name") or task.style_package.name),
            target_duration_seconds=int(video_settings["target_duration_seconds"]),
            creative_objective=str(package.get("name") or "local_style_package_edit"),
            onscreen_text_policy=str(subtitle_adapter_result.get("onscreen_text_policy") or "preserve_existing"),
            voiceover_mode=voice_mode,
            execution_mode="worker_real_render" if task.execute_real_render else "plan_only",
            execute_real_render=task.execute_real_render,
            worker_media_input=input_video_paths[0] if task.execute_real_render else None,
            worker_media_inputs=input_video_paths if task.execute_real_render else None,
            worker_material_role_map=material_plan["role_source_map"] if task.execute_real_render else None,
            worker_subtitle_enabled=subtitle_enabled,
            worker_subtitle_texts=subtitle_texts,
            worker_reference_template_input=reference_path if task.execute_real_render and reference_path else None,
            worker_voiceover_audio_input=voice_adapter_result.get("renderer_voiceover_audio_input"),
            worker_bgm_audio_input=bgm_audio_path,
            worker_bgm_enabled=bgm_enabled,
            worker_bgm_start_seconds=bgm_start_seconds,
            worker_render_width=render_width,
            worker_render_height=render_height,
            worker_render_aspect_ratio=str(video_settings.get("aspect_ratio") or "9:16"),
            worker_render_fps=render_fps,
            worker_video_crf=render_crf,
            worker_subtitle_font_size=subtitle_font_size,
            worker_subtitle_font_color=str(subtitle_settings.get("font_color") or "white"),
            worker_subtitle_outline_color=str(subtitle_settings.get("outline_color") or "black"),
            worker_subtitle_outline_width=subtitle_outline_width,
            worker_bgm_volume_db=bgm_volume_db,
            worker_voice_volume_db=voice_volume_db,
            timeline_evidence_state="ready",
            allow_edge_tts=voice_adapter_result.get("renderer_allow_edge_tts") is True,
        )
        update_stage(selected_task_id, "execute_render", status="completed")

        # Stage 7: Quality check
        current_stage = "quality_check"
        update_stage(selected_task_id, "quality_check", status="running")
        export_adapter_result = run_runtime_exports(
            summary=summary,
            artifact_store=LocalArtifactStore(artifact_root),
            output_dir=task.output_dir,
        )
        copied_output = export_adapter_result.get("copied_output_video")
        update_stage(selected_task_id, "quality_check", status="completed")

        # Stage 8: Write result
        current_stage = "write_result"
        update_stage(selected_task_id, "write_result", status="running")
        local_result = {
            "schema": "smart_video_cut.local.edit_result.v0",
            "ok": summary.get("ok") is True,
            "task_id": selected_task_id,
            "toolkit_status": toolkit_status,
            "project_id": task.project_id,
            "style_package": {
                "package_id": package.get("package_id"),
                "name": package.get("name"),
                "path": str(task.style_package),
            },
            "input_video": str(input_video_paths[0]),
            "input_videos": [str(path) for path in input_video_paths],
            "input_video_count": len(input_video_paths),
            "material_plan": material_plan,
            "material_adapter_result": material_adapter_result,
            "export_adapter_result": export_adapter_result,
            "timeline_plan": timeline_plan.to_dict(),
            "toolkit_timeline_plan": toolkit_timeline,
            "output_dir": str(task.output_dir),
            "user_request": task.user_request,
            "confirmed_brief": task.confirmed_brief,
            "settings_overrides": task.settings_overrides,
            "execute_real_render": task.execute_real_render,
            "memory_context_applied": bool(memory_context),
            "memory_context_preview": memory_context,
            "voice_provider": voice_provider,
            "voice_mode": voice_mode,
            "adapter_selection": adapter_selection,
            "bgm_adapter_result": bgm_adapter_result,
            "subtitle_adapter_result": subtitle_adapter_result,
            "voice_adapter_result": voice_adapter_result,
            "moss_tts_voiceover": moss_voiceover,
            "local_bgm_audio_path": local_bgm_audio_path,
            "local_bgm_start_seconds": bgm_start_seconds,
            "settings_applied_by_current_toolkit": {
                "target_duration_seconds": video_settings["target_duration_seconds"],
                "aspect_ratio": video_settings.get("aspect_ratio"),
                "resolution": {"width": render_width, "height": render_height},
                "fps": render_fps,
                "video_crf": render_crf,
                "subtitle_enabled": subtitle_enabled,
                "subtitle_texts": subtitle_texts,
                "subtitle_font_size": subtitle_font_size,
                "subtitle_font_color": subtitle_settings.get("font_color"),
                "subtitle_outline_color": subtitle_settings.get("outline_color"),
                "subtitle_outline_width": subtitle_outline_width,
                "bgm_volume_db": bgm_volume_db,
                "voice_volume_db": voice_volume_db,
                "onscreen_text_policy": subtitle_adapter_result.get("onscreen_text_policy"),
                "voiceover_mode": voice_settings.get("mode"),
                "reference_template": reference_path is not None,
            },
            "settings_reserved_for_next_renderer_adapter": {
                "quality": video_settings.get("quality"),
                "subtitle_custom_prompt": subtitle_settings.get("custom_prompt"),
                "subtitle_location_info": subtitle_settings.get("location_info"),
                "moss_voice": voice_settings.get("moss_voice"),
                "moss_profile": voice_settings.get("moss_profile"),
                "moss_sample_mode": voice_settings.get("sample_mode"),
            },
            "copied_output_video": str(copied_output) if copied_output else None,
            "toolkit_summary": summary,
        }
        result_path = task.output_dir / "local_studio_result.json"
        result_path.write_text(
            json.dumps(local_result, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        # Save version snapshot
        version_entry = save_version(
            output_dir=task.output_dir,
            timeline=timeline_plan.to_dict(),
            brief={"user_request": task.user_request, "confirmed_brief": task.confirmed_brief},
            result=local_result,
        )
        from smart_video_cut.project_manifest import write_project_manifest

        local_result["project_manifest_path"] = str(task.output_dir / "project_manifest.json")
        local_result["current_version"] = version_entry.version
        result_path.write_text(
            json.dumps(local_result, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        write_project_manifest(
            output_dir=task.output_dir,
            result={**local_result, "version": version_entry.version},
            timeline=timeline_plan.to_dict(),
            event="render_completed" if local_result["ok"] else "render_failed",
        )
        protocol_manifest = write_local_toolkit_protocol(
            output_dir=task.output_dir,
            result=local_result,
        )
        local_result["local_toolkit_protocol_path"] = protocol_manifest["protocol_path"]
        result_path.write_text(
            json.dumps(local_result, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        update_stage(selected_task_id, "write_result", status="completed",
                     outputs=[str(result_path)])
        complete_task(selected_task_id, result_path=str(result_path))
        return local_result

    except Exception as exc:
        fail_task(selected_task_id, error_message=str(exc))
        raise


def _maybe_generate_moss_voiceover(
    *,
    provider: str,
    execute_real_render: bool,
    voiceover_text: str,
    voice_settings: dict[str, Any],
    artifact_root: Path,
) -> dict[str, Any]:
    if provider != "moss_tts_nano" or not execute_real_render:
        return {"ok": False, "skipped": True, "reason": "provider_not_selected_or_plan_only"}
    return generate_moss_voiceover(
        execute_real_render=execute_real_render,
        voiceover_text=voiceover_text,
        voice_settings=voice_settings,
        artifact_root=artifact_root,
    )


def _selected_input_videos(task: LocalEditTask) -> list[Path]:
    paths: list[Path] = []
    for path in [task.input_video, *task.input_videos]:
        if path and path.is_file() and path not in paths:
            paths.append(path)
    return paths


def _media_label(paths: list[Path]) -> str:
    if len(paths) == 1:
        return paths[0].name
    return ", ".join(path.name for path in paths[:3]) + (f" 等 {len(paths)} 个素材" if len(paths) > 3 else "")


def _safe_float(
    value: Any,
    *,
    default: float,
    minimum: float | None = None,
    maximum: float | None = None,
) -> float:
    try:
        selected = float(value)
    except (TypeError, ValueError):
        selected = default
    if minimum is not None:
        selected = max(minimum, selected)
    if maximum is not None:
        selected = min(maximum, selected)
    return selected


def _safe_int(
    value: Any,
    *,
    default: int,
    minimum: int | None = None,
    maximum: int | None = None,
) -> int:
    try:
        selected = int(value)
    except (TypeError, ValueError):
        selected = default
    if minimum is not None:
        selected = max(minimum, selected)
    if maximum is not None:
        selected = min(maximum, selected)
    return selected


def _renderer_dimensions(video_settings: dict[str, Any]) -> tuple[int, int]:
    resolution = str(video_settings.get("resolution") or "").strip().lower().replace("×", "x")
    if "x" in resolution:
        left, right = resolution.split("x", 1)
        width = _safe_int(left.strip(), default=0, minimum=0, maximum=7680)
        height = _safe_int(right.strip(), default=0, minimum=0, maximum=7680)
        if width >= 144 and height >= 144:
            return width, height
    return {
        "16:9": (1280, 720),
        "1:1": (1080, 1080),
        "4:5": (1080, 1350),
    }.get(str(video_settings.get("aspect_ratio") or "9:16"), (720, 1280))


def run_voice_profile_contract(
    *,
    output_dir: Path,
    provider_id: str = "edge_tts",
    voice_gender: str = "male",
    voice_style: str = "warm_vlog_narrator",
    sample_text: str = "这是一段本地智能剪辑的男声样音。",
    sample_outcome: str = "approved",
) -> dict[str, Any]:
    """Use the bundled toolkit voice simulation contract as the local voice entry."""

    ensure_video_toolkit_available()
    from video_editing_toolkit.voice_simulation import (  # type: ignore
        run_voice_simulation,
    )

    selected_provider_id = "fixture_voice" if provider_id == "fixture" else provider_id
    output_dir.mkdir(parents=True, exist_ok=True)
    result_json_path = output_dir / "voice_profile_result.json"
    summary = run_voice_simulation(
        artifact_root=output_dir / "_voice_profile_artifacts",
        result_json=result_json_path,
        tenant_id="local_studio_tenant",
        user_id="local_user",
        project_id="local_voice_profile",
        platform_job_id="local_voice_profile_job",
        provider_id=selected_provider_id,
        voice_gender=voice_gender,
        voice_style=voice_style,
        sample_text=sample_text,
        sample_outcome=sample_outcome,
    )
    if selected_provider_id == "moss_tts_nano" and sample_outcome != "blocked_preflight":
        moss_sample_path = output_dir / "moss_tts_sample.wav"
        moss_result = synthesize_moss_tts(
            text=sample_text,
            output_audio_path=moss_sample_path,
            voice="Zhiming",
            cpu_threads=4,
            max_new_frames=375,
            sample_mode="fixed",
            text_temperature=0.8,
            audio_temperature=0.6,
            seed=2026,
        )
        if moss_sample_path.is_file() and not moss_result.get("audio_path"):
            moss_result["audio_path"] = str(moss_sample_path)
        summary["moss_tts_sample_generation"] = moss_result
    summary["result_json_path"] = str(result_json_path)
    summary["output_dir"] = str(output_dir)
    return summary


def _copy_final_render_if_present(
    *,
    summary: dict[str, Any],
    artifact_store: Any,
    output_dir: Path,
) -> Path | None:
    result = export_local_mp4(
        summary=summary,
        artifact_store=artifact_store,
        output_dir=output_dir,
    )
    copied = result.get("copied_output_video")
    return Path(str(copied)) if copied else None


def _subtitle_texts(subtitle_settings: dict[str, Any]) -> list[str]:
    return subtitle_texts_from_settings(subtitle_settings)


def _merge_user_request(
    *,
    user_request: str,
    package: dict[str, Any],
    settings: dict[str, Any],
) -> str:
    video = settings["video"]
    subtitle = settings["subtitle"]
    audio = settings["audio"]
    subtitle_desc = (
        "不加内容字幕"
        if subtitle.get("enabled", True) is False
        else f"字幕字号 {subtitle['font_size']}；字幕要求 {subtitle.get('custom_prompt') or '按风格包默认'}；位置信息 {subtitle.get('location_info') or '未填写'}"
    )
    return (
        f"{user_request}\n\n"
        "本地用户已选择的固定剪辑设置："
        f"时长 {video['target_duration_seconds']} 秒；"
        f"比例 {video['aspect_ratio']}；"
        f"分辨率 {video['resolution']}；"
        f"质量 {video['quality']}；"
        f"{subtitle_desc}；"
        f"BGM 音量 {audio['bgm_volume_db']} dB；"
        f"参考样板包 {package.get('name')}。"
        "这些设置优先于 Agent 自由发挥。"
    )
