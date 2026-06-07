from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any


EXPORT_ADAPTER_RESULT_SCHEMA = "smart_video_cut.local.export_adapter_result.v0"
EXPORT_PROJECT_PACK_RESULT_SCHEMA = "smart_video_cut.local.export_project_pack_result.v0"
EXPORT_FILMGEN_HANDOFF_LEGACY_SCHEMA = "smart_video_cut.local.export_filmgen_handoff.v0"
EXPORT_FILMGEN_HANDOFF_SCHEMA = "smart_video_cut.local.export_filmgen_handoff.v1"


def run_runtime_exports(
    *,
    summary: dict[str, Any],
    artifact_store: Any,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Run export adapters that are safe to execute during a render pipeline."""
    output_path = Path(output_dir)
    local_mp4 = export_local_mp4(
        summary=summary,
        artifact_store=artifact_store,
        output_dir=output_path,
    )
    project_pack = project_pack_export_status(output_dir=output_path)
    filmgen_handoff = filmgen_handoff_export_status(
        output_dir=output_path,
        summary=summary,
        local_mp4=local_mp4,
        project_pack=project_pack,
    )
    completed = []
    if local_mp4.get("ok") is True and local_mp4.get("copied_output_video"):
        completed.append("export.local_mp4")
    if filmgen_handoff.get("ok") is True and filmgen_handoff.get("handoff_path"):
        completed.append("export.filmgen_handoff")
    return {
        "schema": EXPORT_ADAPTER_RESULT_SCHEMA,
        "ok": local_mp4.get("ok") is True,
        "selected_adapter_ids": ["export.local_mp4", "export.project_pack", "export.filmgen_handoff"],
        "completed_adapter_ids": completed,
        "copied_output_video": local_mp4.get("copied_output_video"),
        "exports": {
            "local_mp4": local_mp4,
            "project_pack": project_pack,
            "filmgen_handoff": filmgen_handoff,
        },
        "warnings": _runtime_export_warnings(local_mp4),
    }


def export_local_mp4(
    *,
    summary: dict[str, Any],
    artifact_store: Any,
    output_dir: str | Path,
) -> dict[str, Any]:
    """Copy toolkit final_render artifact into output_dir/final.mp4 when present."""
    output_path = Path(output_dir)
    source_refs = summary.get("source_artifact_refs")
    if not isinstance(source_refs, dict):
        return _local_mp4_result(reason="missing_source_artifact_refs")
    final_ref = source_refs.get("final_render")
    if not isinstance(final_ref, dict):
        return _local_mp4_result(reason="missing_final_render_ref")
    artifact_id = final_ref.get("artifact_id")
    if not isinstance(artifact_id, str) or not artifact_id.strip():
        return _local_mp4_result(reason="missing_final_render_artifact_id")
    local_path = artifact_store.open_local_path(artifact_id)
    if local_path is None:
        return _local_mp4_result(reason="artifact_store_path_not_found", artifact_id=artifact_id)
    source_path = Path(local_path)
    if not source_path.is_file():
        return _local_mp4_result(reason="final_render_file_not_found", artifact_id=artifact_id, source_path=str(source_path))
    output_path.mkdir(parents=True, exist_ok=True)
    copied_path = output_path / "final.mp4"
    shutil.copy2(source_path, copied_path)
    return _local_mp4_result(
        ok=True,
        reason="copied_final_render",
        artifact_id=artifact_id,
        source_path=str(source_path),
        copied_output_video=str(copied_path),
    )


def export_project_pack_adapter(
    *,
    output_dir: str | Path,
    package_dir: str | Path,
    name: str = "",
    material_pack_ref: str = "",
    style_pack_ref: str = "",
    project_settings_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Export a ProjectPack through the adapter layer."""
    from smart_video_cut.pack_manager import export_project_pack_from_output

    pack = export_project_pack_from_output(
        output_dir=output_dir,
        package_dir=package_dir,
        name=name,
        material_pack_ref=material_pack_ref,
        style_pack_ref=style_pack_ref,
        project_settings_overrides=project_settings_overrides or {},
    )
    return {
        "schema": EXPORT_PROJECT_PACK_RESULT_SCHEMA,
        "ok": True,
        "adapter_id": "export.project_pack",
        "status": "completed",
        "pack": pack,
        "project_pack_path": str(Path(package_dir) / "project_pack.json"),
    }


def project_pack_export_status(*, output_dir: str | Path) -> dict[str, Any]:
    return {
        "adapter_id": "export.project_pack",
        "ok": True,
        "status": "available",
        "executed": False,
        "reason": "available_via_project_pack_export_endpoint",
        "output_dir": str(output_dir),
        "api_endpoint": "/api/packs/project/export",
        "cli_command": "export-project-pack",
        "agent_tool": "export_project_pack",
    }


def filmgen_handoff_export_status(
    *,
    output_dir: str | Path,
    summary: dict[str, Any] | None = None,
    local_mp4: dict[str, Any] | None = None,
    project_pack: dict[str, Any] | None = None,
) -> dict[str, Any]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    handoff_path = output_path / "filmgen_handoff.json"
    payload = _filmgen_handoff_payload(
        output_dir=output_path,
        summary=summary or {},
        local_mp4=local_mp4 or {},
        project_pack=project_pack or project_pack_export_status(output_dir=output_path),
        handoff_path=handoff_path,
    )
    handoff_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return {
        "adapter_id": "export.filmgen_handoff",
        "ok": handoff_path.is_file(),
        "status": "completed" if handoff_path.is_file() else "failed",
        "executed": True,
        "reason": "filmgen_handoff_file_written" if handoff_path.is_file() else "filmgen_handoff_write_failed",
        "output_dir": str(output_path),
        "handoff_path": str(handoff_path),
        "handoff": payload,
    }


def _local_mp4_result(
    *,
    ok: bool = True,
    reason: str,
    artifact_id: str = "",
    source_path: str = "",
    copied_output_video: str | None = None,
) -> dict[str, Any]:
    return {
        "adapter_id": "export.local_mp4",
        "ok": ok,
        "status": "completed" if copied_output_video else "skipped",
        "executed": copied_output_video is not None,
        "reason": reason,
        "artifact_id": artifact_id,
        "source_path": source_path,
        "copied_output_video": copied_output_video,
    }


def _runtime_export_warnings(local_mp4: dict[str, Any]) -> list[dict[str, str]]:
    if local_mp4.get("copied_output_video"):
        return []
    return [{
        "code": "final_render_not_copied",
        "adapter_id": "export.local_mp4",
        "message": str(local_mp4.get("reason") or "本次未发现可复制的 final_render artifact。"),
    }]


def _filmgen_handoff_payload(
    *,
    output_dir: Path,
    summary: dict[str, Any],
    local_mp4: dict[str, Any],
    project_pack: dict[str, Any],
    handoff_path: Path,
) -> dict[str, Any]:
    copied_output = local_mp4.get("copied_output_video")
    return {
        "schema": EXPORT_FILMGEN_HANDOFF_SCHEMA,
        "schema_version": 1,
        "adapter_id": "export.filmgen_handoff",
        "handoff_kind": "smart_video_cut_to_filmgen_export",
        "status": "ready",
        "handoff_path": str(handoff_path),
        "output_dir": str(output_dir),
        "final_video": {
            "ready": bool(copied_output),
            "path": str(copied_output or ""),
            "local_mp4_export": local_mp4,
        },
        "project_pack_export": {
            "status": project_pack.get("status"),
            "api_endpoint": project_pack.get("api_endpoint"),
            "cli_command": project_pack.get("cli_command"),
            "agent_tool": project_pack.get("agent_tool"),
        },
        "toolkit_summary": _handoff_summary(summary),
        "source_artifact_refs": summary.get("source_artifact_refs") if isinstance(summary.get("source_artifact_refs"), dict) else {},
        "assets": [
            {
                "asset_id": "smart-video-cut-final",
                "type": "final_video",
                "path": str(copied_output or ""),
                "ready": bool(copied_output),
                "role": "primary_import_candidate",
            }
        ],
        "filmgen_contract": {
            "input_kind": "smart_video_cut_local_export",
            "recommended_next_step": "Load final_video.path when ready, or resolve ProjectPack for full timeline/material context.",
            "supports_plan_only": True,
            "reader_endpoint": "/api/filmgen/export-handoff/validate",
            "preview_endpoint": "/api/filmgen/edit-pack/preview",
            "required_fields": ["schema", "handoff_path", "output_dir", "final_video", "filmgen_contract"],
            "import_steps": [
                "Validate schema and handoff_kind.",
                "Use final_video.path as the preferred FilmGen input when it exists.",
                "If final_video is not ready, keep output_dir/project_pack_export as plan-only context.",
            ],
        },
        "compatibility": {
            "previous_schemas": [EXPORT_FILMGEN_HANDOFF_LEGACY_SCHEMA],
            "current_schema": EXPORT_FILMGEN_HANDOFF_SCHEMA,
        },
    }


def _handoff_summary(summary: dict[str, Any]) -> dict[str, Any]:
    keys = (
        "ok",
        "workflow_kind",
        "execution_mode",
        "project_id",
        "target_duration_seconds",
        "creative_objective",
        "voiceover_mode",
        "timeline_evidence_state",
    )
    return {key: summary.get(key) for key in keys if key in summary}
