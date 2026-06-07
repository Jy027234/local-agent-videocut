"""Voice simulation and reusable voice profile contract for the local studio."""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from video_editing_toolkit.runtime_common import caller_safe, write_json
from video_editing_toolkit.storage import ArtifactRef, LocalArtifactStore


SCHEMA = "video_editing_toolkit.voice_simulation.v0"
RESULT_SCHEMA = "video_editing_toolkit.voice_simulation_result.v0"
VOICE_SIMULATION_PACKAGE_SCHEMA = "video_editing_toolkit.voice_simulation_package.v0"
VOICE_SIMULATION_SAMPLE_SCHEMA = "video_editing_toolkit.voice_simulation_sample.v0"
VOICE_SIMULATION_PROFILE_SCHEMA = "video_editing_toolkit.voice_simulation_profile.v0"
VOICE_PROFILE_APPLICATION_CONTRACT_SCHEMA = "video_editing_toolkit.voice_profile_application_contract.v0"
DEFAULT_ARTIFACT_ROOT = Path(".video-toolkit-data") / "voice-simulation-artifacts"

EDGE_TTS_PROVIDER_ID = "edge_tts"
MOSS_TTS_PROVIDER_ID = "moss_tts_nano"
SYSTEM_TTS_PROVIDER_ID = "system_sapi"
FIXTURE_PROVIDER_ID = "fixture_voice"
PROVIDERS = (EDGE_TTS_PROVIDER_ID, SYSTEM_TTS_PROVIDER_ID, MOSS_TTS_PROVIDER_ID, FIXTURE_PROVIDER_ID)
SAMPLE_OUTCOMES = ("approved", "generated_unapproved", "blocked_preflight")
DEFAULT_SAMPLE_TEXT = "客厅门安装记录，同家庄镇张庄村。"


def run_voice_simulation(
    *,
    artifact_root: str | Path | None = None,
    result_json: str | Path | None = None,
    tenant_id: str = "local_studio_tenant",
    user_id: str = "local_user",
    project_id: str = "local_voice_profile",
    platform_job_id: str = "local_voice_profile_job",
    provider_id: str = EDGE_TTS_PROVIDER_ID,
    voice_gender: str = "male",
    voice_style: str = "warm_vlog_narrator",
    sample_text: str = DEFAULT_SAMPLE_TEXT,
    sample_outcome: str = "approved",
) -> dict[str, Any]:
    """Build a caller-safe voice simulation package and optional voice profile ref."""

    if provider_id not in PROVIDERS:
        raise ValueError(f"provider_id must be one of: {', '.join(PROVIDERS)}")
    if sample_outcome not in SAMPLE_OUTCOMES:
        raise ValueError(f"sample_outcome must be one of: {', '.join(SAMPLE_OUTCOMES)}")

    selected_root = Path(artifact_root) if artifact_root is not None else DEFAULT_ARTIFACT_ROOT
    artifact_store = LocalArtifactStore(selected_root)
    provider_contract = _provider_contract(provider_id)
    sample_payload = _voice_sample_payload(
        project_id=project_id,
        platform_job_id=platform_job_id,
        provider_contract=provider_contract,
        voice_gender=voice_gender,
        voice_style=voice_style,
        sample_text=sample_text,
        sample_outcome=sample_outcome,
    )
    artifact_refs = _materialize_voice_artifacts(
        artifact_store=artifact_store,
        tenant_id=tenant_id,
        user_id=user_id,
        project_id=project_id,
        platform_job_id=platform_job_id,
        provider_contract=provider_contract,
        sample_payload=sample_payload,
        sample_outcome=sample_outcome,
    )
    profile_ref = artifact_refs.get("voice_profile_ref")
    application_contract = _application_contract(
        project_id=project_id,
        platform_job_id=platform_job_id,
        sample_outcome=sample_outcome,
        profile_ref=profile_ref,
        provider_contract=provider_contract,
    )
    if sample_outcome == "approved":
        artifact_refs["voice_profile_application_contract"] = _put_json_artifact(
            artifact_store=artifact_store,
            tenant_id=tenant_id,
            created_by_run_id=f"{user_id}_voice_simulation",
            artifact_type="voice_profile_application_contract",
            filename="voice_profile_application_contract.json",
            payload=application_contract,
        )
    package = _voice_simulation_package(
        tenant_id=tenant_id,
        user_id=user_id,
        project_id=project_id,
        platform_job_id=platform_job_id,
        provider_contract=provider_contract,
        sample_payload=sample_payload,
        sample_outcome=sample_outcome,
        profile_ref=profile_ref,
        application_contract=application_contract,
        artifact_refs=artifact_refs,
    )

    package_ref = artifact_store.put_bytes(
        content=json.dumps(
            caller_safe(package),
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ).encode("utf-8"),
        artifact_type="voice_simulation_package",
        owner_tenant_id=tenant_id,
        created_by_run_id=f"{user_id}_voice_simulation",
        filename="voice_simulation_package.json",
        mime_type="application/json",
        access_policy={"scope": "tenant_project", "handoff": "voice_simulation_package"},
    )

    summary = caller_safe(
        {
            "schema": SCHEMA,
            "contract": "voice_simulation.v0",
            "ok": package["quality_gate"]["contract_valid"] is True,
            "workflow_kind": "voice_simulation",
            "voice_simulation_package_artifact_id": package_ref.artifact_id,
            "voice_simulation_package_artifact_ref": package_ref.to_public_dict(),
            "voice_simulation_summary": package["summary"],
            "voice_profile_ref": profile_ref,
            "application_contract": package["application_contract"],
            "quality_gate": package["quality_gate"],
            "provider_contract": package["provider_contract"],
            "platform_boundary": package["platform_boundary"],
            "artifact_ref_count": package["summary"]["artifact_ref_count"],
            "can_apply_to_video_task": package["summary"]["can_apply_to_video_task"],
            "next_recommended_step": package["summary"]["next_recommended_step"],
        }
    )

    if result_json is not None:
        write_json(
            result_json,
            {
                "schema": RESULT_SCHEMA,
                "summary": summary,
                "voice_simulation_package": package,
                "voice_simulation_package_artifact_ref": package_ref.to_public_dict(),
            },
        )
        summary["result_json_written"] = True

    return summary


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the voice simulation profile contract.",
    )
    parser.add_argument("--artifact-root", default=str(DEFAULT_ARTIFACT_ROOT))
    parser.add_argument("--result-json")
    parser.add_argument("--tenant-id", default="local_studio_tenant")
    parser.add_argument("--user-id", default="local_user")
    parser.add_argument("--project-id", default="local_voice_profile")
    parser.add_argument("--platform-job-id", default="local_voice_profile_job")
    parser.add_argument("--provider-id", choices=PROVIDERS, default=EDGE_TTS_PROVIDER_ID)
    parser.add_argument("--voice-gender", default="male")
    parser.add_argument("--voice-style", default="warm_vlog_narrator")
    parser.add_argument("--sample-text", default=DEFAULT_SAMPLE_TEXT)
    parser.add_argument("--sample-outcome", choices=SAMPLE_OUTCOMES, default="approved")
    args = parser.parse_args(argv)

    try:
        summary = run_voice_simulation(
            artifact_root=args.artifact_root,
            result_json=args.result_json,
            tenant_id=args.tenant_id,
            user_id=args.user_id,
            project_id=args.project_id,
            platform_job_id=args.platform_job_id,
            provider_id=args.provider_id,
            voice_gender=args.voice_gender,
            voice_style=args.voice_style,
            sample_text=args.sample_text,
            sample_outcome=args.sample_outcome,
        )
    except ValueError as exc:
        summary = {
            "schema": SCHEMA,
            "ok": False,
            "error_code": "voice_simulation.invalid_request",
            "error_message": str(exc),
        }
        print(json.dumps(caller_safe(summary), ensure_ascii=False, sort_keys=True))
        return 2

    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if summary.get("ok") is True else 2


def _provider_contract(provider_id: str) -> dict[str, Any]:
    contracts = {
        EDGE_TTS_PROVIDER_ID: {
            "provider_id": EDGE_TTS_PROVIDER_ID,
            "display_name": "Edge TTS",
            "provider_kind": "licensed_synthetic_voice",
            "execution_adapter": "audio.tts.generate_voiceover",
            "model_connector": "edge_tts_cli",
            "network_access": "requires_explicit_opt_in",
            "offline_supported": False,
            "voice_clone_supported": False,
            "model_execution_enabled_in_this_runtime": False,
            "current_integration_status": "available_when_edge_tts_dependency_and_policy_opt_in_exist",
        },
        SYSTEM_TTS_PROVIDER_ID: {
            "provider_id": SYSTEM_TTS_PROVIDER_ID,
            "display_name": "System SAPI",
            "provider_kind": "local_system_synthetic_voice",
            "execution_adapter": "audio.tts.generate_voiceover",
            "model_connector": "windows_sapi",
            "network_access": "disabled_by_contract",
            "offline_supported": True,
            "voice_clone_supported": False,
            "model_execution_enabled_in_this_runtime": False,
            "current_integration_status": "available_on_supported_windows_hosts_with_policy_opt_in",
        },
        MOSS_TTS_PROVIDER_ID: {
            "provider_id": MOSS_TTS_PROVIDER_ID,
            "display_name": "MOSS-TTS-Nano",
            "provider_kind": "local_or_cloud_model_adapter",
            "execution_adapter": "audio.tts.generate_voiceover",
            "model_connector": "moss_tts_nano_onnx_cpu",
            "network_access": "disabled_by_contract",
            "offline_supported": True,
            "voice_clone_supported": False,
            "model_execution_enabled_in_this_runtime": False,
            "current_integration_status": "preflight_ready_future_execution_adapter",
            "future_model_support": {
                "supports_moss_tts_nano_adapter": True,
                "required_bundles": [
                    "MOSS-TTS-Nano-100M-ONNX",
                    "MOSS-Audio-Tokenizer-Nano-ONNX",
                ],
                "required_preflight": "audio.tts.generate_voiceover with synthesis_mode=preflight_only",
                "sample_generation_requires_model_preflight": True,
            },
        },
        FIXTURE_PROVIDER_ID: {
            "provider_id": FIXTURE_PROVIDER_ID,
            "display_name": "Fixture Voice",
            "provider_kind": "deterministic_contract_fixture",
            "execution_adapter": "fixture.voice_simulation",
            "model_connector": "fixture_audio_stub",
            "network_access": "disabled_by_contract",
            "offline_supported": True,
            "voice_clone_supported": False,
            "model_execution_enabled_in_this_runtime": False,
            "current_integration_status": "contract_test_only",
        },
    }
    return dict(contracts[provider_id])


def _voice_sample_payload(
    *,
    project_id: str,
    platform_job_id: str,
    provider_contract: Mapping[str, Any],
    voice_gender: str,
    voice_style: str,
    sample_text: str,
    sample_outcome: str,
) -> dict[str, Any]:
    sample_generated = sample_outcome in {"approved", "generated_unapproved"}
    return caller_safe(
        {
            "schema": VOICE_SIMULATION_SAMPLE_SCHEMA,
            "contract": "voice_simulation_sample.v0",
            "project_id": project_id,
            "platform_job_id": platform_job_id,
            "sample_status": "generated" if sample_generated else "blocked",
            "sample_outcome": sample_outcome,
            "provider_id": provider_contract["provider_id"],
            "model_connector": provider_contract["model_connector"],
            "voice_gender": _safe_label(voice_gender, default="unknown"),
            "voice_style": _safe_label(voice_style, default="neutral"),
            "sample_text_preview": _safe_preview(sample_text),
            "sample_audio_kind": "contract_sample_audio_stub" if sample_generated else None,
            "contains_voice_clone": False,
            "contains_reference_voiceprint": False,
            "requires_user_approval_before_profile_save": True,
            "user_approved_sample": sample_outcome == "approved",
            "sample_generation_notes": _sample_generation_notes(sample_outcome, provider_contract),
        }
    )


def _materialize_voice_artifacts(
    *,
    artifact_store: LocalArtifactStore,
    tenant_id: str,
    user_id: str,
    project_id: str,
    platform_job_id: str,
    provider_contract: Mapping[str, Any],
    sample_payload: Mapping[str, Any],
    sample_outcome: str,
) -> dict[str, dict[str, Any] | None]:
    created_by_run_id = f"{user_id}_voice_simulation"
    artifact_refs: dict[str, dict[str, Any] | None] = {}
    if sample_outcome == "blocked_preflight":
        artifact_refs["provider_preflight_report"] = _put_json_artifact(
            artifact_store=artifact_store,
            tenant_id=tenant_id,
            created_by_run_id=created_by_run_id,
            artifact_type="voice_simulation_preflight_report",
            filename="voice_simulation_preflight_report.json",
            payload={
                "schema": "video_editing_toolkit.voice_simulation_preflight_report.v0",
                "provider_id": provider_contract["provider_id"],
                "model_connector": provider_contract["model_connector"],
                "status": "blocked",
                "reason_code": "voice_simulation.provider_preflight_blocked",
                "sample_generation_allowed": False,
            },
        )
        artifact_refs["sample_ref"] = None
        artifact_refs["voice_profile_ref"] = None
        return artifact_refs

    sample_ref = _put_json_artifact(
        artifact_store=artifact_store,
        tenant_id=tenant_id,
        created_by_run_id=created_by_run_id,
        artifact_type="voice_simulation_sample",
        filename="voice_simulation_sample.json",
        payload=sample_payload,
    )
    artifact_refs["sample_ref"] = sample_ref
    if sample_outcome != "approved":
        artifact_refs["voice_profile_ref"] = None
        return artifact_refs

    profile_payload = _voice_profile_payload(
        project_id=project_id,
        platform_job_id=platform_job_id,
        provider_contract=provider_contract,
        sample_ref=sample_ref,
        sample_payload=sample_payload,
    )
    artifact_refs["voice_profile_ref"] = _put_json_artifact(
        artifact_store=artifact_store,
        tenant_id=tenant_id,
        created_by_run_id=created_by_run_id,
        artifact_type="voice_simulation_profile",
        filename="voice_simulation_profile.json",
        payload=profile_payload,
    )
    return artifact_refs


def _voice_profile_payload(
    *,
    project_id: str,
    platform_job_id: str,
    provider_contract: Mapping[str, Any],
    sample_ref: Mapping[str, Any],
    sample_payload: Mapping[str, Any],
) -> dict[str, Any]:
    return caller_safe(
        {
            "schema": VOICE_SIMULATION_PROFILE_SCHEMA,
            "contract": "voice_simulation_profile.v0",
            "project_id": project_id,
            "platform_job_id": platform_job_id,
            "profile_status": "approved_for_video_task_binding",
            "provider_id": provider_contract["provider_id"],
            "provider_kind": provider_contract["provider_kind"],
            "model_connector": provider_contract["model_connector"],
            "voice_gender": sample_payload["voice_gender"],
            "voice_style": sample_payload["voice_style"],
            "source_sample_ref": dict(sample_ref),
            "approved_sample_required": True,
            "user_approved_sample": True,
            "can_apply_to_video_task": True,
            "voice_clone": {
                "requested": False,
                "allowed": False,
                "high_sensitivity_gate_required_for_exact_imitation": True,
            },
            "task_binding_policy": {
                "video_task_may_reference_profile": True,
                "video_task_must_not_regenerate_unapproved_voice": True,
                "fallback_requires_explicit_policy": True,
            },
        }
    )


def _application_contract(
    *,
    project_id: str,
    platform_job_id: str,
    sample_outcome: str,
    profile_ref: Mapping[str, Any] | None,
    provider_contract: Mapping[str, Any],
) -> dict[str, Any]:
    can_apply = sample_outcome == "approved" and profile_ref is not None
    return caller_safe(
        {
            "schema": VOICE_PROFILE_APPLICATION_CONTRACT_SCHEMA,
            "contract": "voice_profile_application_contract.v0",
            "project_id": project_id,
            "platform_job_id": platform_job_id,
            "provider_id": provider_contract["provider_id"],
            "can_apply_to_video_task": can_apply,
            "voice_profile_ref": dict(profile_ref) if profile_ref is not None else None,
            "video_task_input_patch": {
                "voice_profile_ref": dict(profile_ref) if can_apply else None,
                "voice_generation_policy": "use_saved_profile_only" if can_apply else "pause_until_profile_approved",
            },
            "blocked_until": [] if can_apply else _blocked_until(sample_outcome),
            "must_not_apply_unapproved_sample": True,
            "must_not_guess_provider_inside_video_task": True,
        }
    )


def _voice_simulation_package(
    *,
    tenant_id: str,
    user_id: str,
    project_id: str,
    platform_job_id: str,
    provider_contract: Mapping[str, Any],
    sample_payload: Mapping[str, Any],
    sample_outcome: str,
    profile_ref: Mapping[str, Any] | None,
    application_contract: Mapping[str, Any],
    artifact_refs: Mapping[str, Mapping[str, Any] | None],
) -> dict[str, Any]:
    quality_gate = _quality_gate(
        sample_outcome=sample_outcome,
        provider_contract=provider_contract,
        sample_payload=sample_payload,
        profile_ref=profile_ref,
        application_contract=application_contract,
    )
    visible_artifact_refs = {key: value for key, value in artifact_refs.items() if value is not None}
    return caller_safe(
        {
            "schema": VOICE_SIMULATION_PACKAGE_SCHEMA,
            "contract": "voice_simulation_package.v0",
            "summary": {
                "package_status": quality_gate["status"],
                "provider_id": provider_contract["provider_id"],
                "model_connector": provider_contract["model_connector"],
                "sample_outcome": sample_outcome,
                "sample_generated": sample_payload["sample_status"] == "generated",
                "sample_approved": sample_payload["user_approved_sample"] is True,
                "voice_profile_saved": profile_ref is not None,
                "can_apply_to_video_task": application_contract["can_apply_to_video_task"] is True,
                "artifact_ref_count": len(visible_artifact_refs),
                "supports_moss_tts_nano_model": provider_contract["provider_id"] == MOSS_TTS_PROVIDER_ID,
                "next_recommended_step": _next_recommended_step(sample_outcome),
            },
            "tenant_id": tenant_id,
            "user_id": user_id,
            "project_id": project_id,
            "platform_job_id": platform_job_id,
            "provider_contract": dict(provider_contract),
            "voice_sample": dict(sample_payload),
            "voice_profile_ref": dict(profile_ref) if profile_ref is not None else None,
            "application_contract": dict(application_contract),
            "artifact_refs": visible_artifact_refs,
            "quality_gate": quality_gate,
            "platform_boundary": _platform_boundary(),
            "local_toolkit_forward_compatibility": _local_toolkit_forward_compatibility(),
        }
    )


def _quality_gate(
    *,
    sample_outcome: str,
    provider_contract: Mapping[str, Any],
    sample_payload: Mapping[str, Any],
    profile_ref: Mapping[str, Any] | None,
    application_contract: Mapping[str, Any],
) -> dict[str, Any]:
    provider_supported = provider_contract.get("provider_id") in PROVIDERS
    sample_generated = sample_payload.get("sample_status") == "generated"
    sample_approved = sample_payload.get("user_approved_sample") is True
    profile_saved = profile_ref is not None
    application_contract_valid = application_contract.get("schema") == VOICE_PROFILE_APPLICATION_CONTRACT_SCHEMA
    can_apply = application_contract.get("can_apply_to_video_task") is True
    contract_valid = provider_supported and application_contract_valid
    if sample_outcome == "approved":
        contract_valid = contract_valid and sample_generated and sample_approved and profile_saved and can_apply
    elif sample_outcome == "generated_unapproved":
        contract_valid = contract_valid and sample_generated and not sample_approved and not profile_saved and not can_apply
    else:
        contract_valid = contract_valid and not sample_generated and not profile_saved and not can_apply
    return {
        "status": _package_status(sample_outcome) if contract_valid else "voice_simulation_contract_blocked",
        "contract_valid": contract_valid,
        "can_apply_to_video_task": can_apply,
        "blocking_reasons": [] if contract_valid else ["voice_simulation_contract_invalid"],
        "checks": {
            "provider_supported": provider_supported,
            "provider_model_connector_declared": bool(provider_contract.get("model_connector")),
            "sample_generated": sample_generated,
            "sample_approved_before_profile_save": sample_approved if sample_outcome == "approved" else False,
            "voice_profile_saved_only_after_approval": profile_saved == sample_approved,
            "video_task_binding_requires_voice_profile_ref": can_apply == (profile_ref is not None),
            "moss_tts_nano_future_model_slot_present": provider_contract.get("provider_id") != MOSS_TTS_PROVIDER_ID
            or bool(provider_contract.get("future_model_support", {}).get("supports_moss_tts_nano_adapter")),
            "voice_clone_not_enabled": provider_contract.get("voice_clone_supported") is False,
        },
    }


def _put_json_artifact(
    *,
    artifact_store: LocalArtifactStore,
    tenant_id: str,
    created_by_run_id: str,
    artifact_type: str,
    filename: str,
    payload: Mapping[str, Any],
) -> dict[str, Any]:
    ref: ArtifactRef = artifact_store.put_bytes(
        content=json.dumps(
            caller_safe(payload),
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


def _platform_boundary() -> dict[str, Any]:
    return {
        "agent_lifecycle_owner": "platform_core",
        "voice_profile_approval_owner": "platform_core",
        "worker_runtime_owner": "video_editing_toolkit",
        "toolkit_creates_agents": False,
        "toolkit_manages_agents": False,
        "toolkit_executes_tts_in_this_runtime": False,
        "toolkit_executes_voice_clone": False,
        "toolkit_applies_profile_to_video_task_directly": False,
        "artifact_ref_only": True,
    }


def _local_toolkit_forward_compatibility() -> dict[str, Any]:
    return {
        "same_contracts_reused_for_local_mode": True,
        "local_execution_backend": "user_local_device",
        "local_dispatch_mode": "local_toolkit_worker",
        "local_moss_tts_nano_bundle_preflight_supported": True,
        "raw_local_locations_exposed": False,
        "sample_playback_local_allowed": True,
        "sample_or_profile_upload_requires_user_approval": True,
    }


def _sample_generation_notes(sample_outcome: str, provider_contract: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "sample_outcome": sample_outcome,
        "provider_id": provider_contract["provider_id"],
        "model_connector": provider_contract["model_connector"],
        "real_audio_generated_in_this_runtime": False,
        "provider_execution_required_for_product": provider_contract["execution_adapter"],
        "moss_tts_nano_preflight_required": provider_contract["provider_id"] == MOSS_TTS_PROVIDER_ID,
    }


def _blocked_until(sample_outcome: str) -> list[str]:
    if sample_outcome == "generated_unapproved":
        return ["user_approves_generated_sample", "voice_profile_ref_saved"]
    return ["provider_preflight_passes", "sample_generated", "user_approves_generated_sample", "voice_profile_ref_saved"]


def _package_status(sample_outcome: str) -> str:
    return {
        "approved": "voice_profile_ready_for_video_task",
        "generated_unapproved": "sample_waiting_for_user_approval",
        "blocked_preflight": "voice_simulation_blocked_by_provider_preflight",
    }[sample_outcome]


def _next_recommended_step(sample_outcome: str) -> str:
    return {
        "approved": "bind_voice_profile_ref_to_video_edit_task",
        "generated_unapproved": "request_user_sample_approval_before_profile_save",
        "blocked_preflight": "repair_provider_preflight_before_generating_sample",
    }[sample_outcome]


def _safe_label(value: Any, *, default: str) -> str:
    if not isinstance(value, str):
        return default
    rendered = "".join(char if char.isalnum() or char in {"_", "-", "."} else "_" for char in value.strip())
    rendered = rendered.strip("._-")[:80]
    return rendered or default


def _safe_preview(value: str) -> str:
    rendered = " ".join(str(value).split())
    return rendered[:120]


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
