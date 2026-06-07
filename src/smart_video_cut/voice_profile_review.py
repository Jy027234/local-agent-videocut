from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path
from typing import Any, Mapping


VOICE_PROFILE_REVIEW_SCHEMA = "smart_video_cut.local.voice_profile_review.v0"
VOICE_PROFILE_REF_SCHEMA = "smart_video_cut.local.voice_profile_ref.v0"
VOICE_PROFILE_REVIEW_INDEX_SCHEMA = "smart_video_cut.local.voice_profile_review_index.v0"

REVIEW_DIRNAME = "_voice_profile_reviews"
DEFAULT_REVIEW_ROOT = Path(__file__).resolve().parents[2] / "workspace" / "voice_profiles"
APPROVAL_OUTCOMES = {"approved", "rejected", "needs_retry"}


def confirm_voice_profile_review(
    *,
    output_dir: str | Path = "",
    profile_result_path: str | Path = "",
    profile_result: Mapping[str, Any] | None = None,
    outcome: str = "approved",
    notes: str = "",
    rating: int | float | None = None,
    prompt_audio_path: str | Path = "",
    sample_audio_path: str | Path = "",
) -> dict[str, Any]:
    """Persist a local review decision and return a reusable voice_profile_ref."""

    normalized_outcome = _normalize_outcome(outcome)
    result_path = _resolve_profile_result_path(output_dir=output_dir, profile_result_path=profile_result_path)
    result = _load_profile_result(result_path=result_path, profile_result=profile_result)
    summary = _summary_from_profile_result(result)
    provider_id = _provider_id(summary=summary, result=result)
    sample_audio = _first_text(
        str(sample_audio_path or ""),
        _nested_text(result, "moss_tts_sample_generation", "audio_path"),
        _nested_text(result, "moss_tts_sample_generation", "output_audio_path"),
        _nested_text(summary, "moss_tts_sample_generation", "audio_path"),
        _nested_text(summary, "moss_tts_sample_generation", "output_audio_path"),
        _nested_text(result, "generated_voiceover", "audio_path"),
        _nested_text(summary, "generated_voiceover", "audio_path"),
        _nested_text(result, "audio_path"),
        _nested_text(summary, "audio_path"),
    )
    prompt_audio = _first_text(
        str(prompt_audio_path or ""),
        _nested_text(result, "prompt_audio_path"),
        _nested_text(summary, "prompt_audio_path"),
        _nested_text(result, "voice_simulation_package", "voice_sample", "prompt_audio_path"),
    )
    source_voice_profile_ref = _extract_voice_profile_ref(summary=summary, result=result)
    application_contract = _extract_application_contract(summary=summary, result=result)
    created_at = time.time()
    review_dir = _review_dir(output_dir)
    ref_id = _make_ref_id(
        provider_id=provider_id,
        source_voice_profile_ref=source_voice_profile_ref,
        profile_result_path=str(result_path) if result_path else "",
        sample_audio_path=sample_audio,
        created_at=created_at,
    )
    review_path = review_dir / f"{ref_id}.json"

    approved = normalized_outcome == "approved"
    voice_profile_ref = _build_voice_profile_ref(
        ref_id=ref_id,
        created_at=created_at,
        provider_id=provider_id,
        outcome=normalized_outcome,
        rating=rating,
        notes=notes,
        result_path=str(result_path) if result_path else "",
        review_path=str(review_path),
        prompt_audio_path=prompt_audio,
        sample_audio_path=sample_audio,
        source_voice_profile_ref=source_voice_profile_ref,
        application_contract=application_contract,
        summary=summary,
    ) if approved else None
    settings_overrides = _settings_overrides(
        provider_id=provider_id,
        voice_profile_ref=voice_profile_ref,
        prompt_audio_path=prompt_audio,
    ) if approved else {}
    review_record = {
        "schema": VOICE_PROFILE_REVIEW_SCHEMA,
        "ok": True,
        "created_at": created_at,
        "outcome": normalized_outcome,
        "can_apply_to_video_task": approved,
        "provider_id": provider_id,
        "rating": rating,
        "notes": str(notes or "")[:1000],
        "profile_result_path": str(result_path) if result_path else "",
        "prompt_audio_path": prompt_audio,
        "sample_audio_path": sample_audio,
        "voice_profile_ref": voice_profile_ref,
        "settings_overrides": settings_overrides,
        "review_record_path": str(review_path),
        "source": {
            "voice_profile_ref": source_voice_profile_ref,
            "application_contract": application_contract,
            "quality_gate": _first_mapping(summary.get("quality_gate"), result.get("quality_gate")),
            "voice_simulation_summary": _first_mapping(
                summary.get("voice_simulation_summary"),
                _nested_mapping(result, "voice_simulation_package", "summary"),
            ),
            "voice_simulation_package_artifact_ref": _first_mapping(
                summary.get("voice_simulation_package_artifact_ref"),
                result.get("voice_simulation_package_artifact_ref"),
            ),
        },
        "warnings": _review_warnings(
            approved=approved,
            source_voice_profile_ref=source_voice_profile_ref,
            sample_audio_path=sample_audio,
            prompt_audio_path=prompt_audio,
        ),
    }
    review_dir.mkdir(parents=True, exist_ok=True)
    review_path.write_text(
        json.dumps(review_record, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return review_record


def list_voice_profile_reviews(output_dir: str | Path = "") -> dict[str, Any]:
    """List saved local voice profile review decisions."""

    review_dir = _review_dir(output_dir)
    records: list[dict[str, Any]] = []
    if review_dir.exists():
        for path in review_dir.glob("*.json"):
            record = _read_json_file(path)
            if record.get("schema") != VOICE_PROFILE_REVIEW_SCHEMA:
                continue
            records.append(_review_list_item(record=record, path=path))
    records.sort(key=lambda item: float(item.get("created_at") or 0.0), reverse=True)
    return {
        "schema": VOICE_PROFILE_REVIEW_INDEX_SCHEMA,
        "ok": True,
        "output_dir": str(output_dir or ""),
        "review_dir": str(review_dir),
        "count": len(records),
        "refs": records,
    }


def _review_dir(output_dir: str | Path) -> Path:
    if output_dir:
        return Path(output_dir) / REVIEW_DIRNAME
    return DEFAULT_REVIEW_ROOT


def _resolve_profile_result_path(*, output_dir: str | Path, profile_result_path: str | Path) -> Path | None:
    if profile_result_path:
        return Path(profile_result_path)
    if output_dir:
        candidate = Path(output_dir) / "voice_profile_result.json"
        if candidate.is_file():
            return candidate
    return None


def _load_profile_result(
    *,
    result_path: Path | None,
    profile_result: Mapping[str, Any] | None,
) -> dict[str, Any]:
    if result_path and result_path.is_file():
        return _read_json_file(result_path)
    if isinstance(profile_result, Mapping) and profile_result:
        return dict(profile_result)
    return {}


def _summary_from_profile_result(result: Mapping[str, Any]) -> dict[str, Any]:
    summary = result.get("summary")
    if isinstance(summary, Mapping):
        return dict(summary)
    return dict(result)


def _provider_id(*, summary: Mapping[str, Any], result: Mapping[str, Any]) -> str:
    return _first_text(
        _nested_text(summary, "voice_simulation_summary", "provider_id"),
        _nested_text(summary, "application_contract", "provider_id"),
        _nested_text(summary, "provider_contract", "provider_id"),
        _nested_text(result, "voice_simulation_package", "summary", "provider_id"),
        _nested_text(result, "voice_simulation_package", "provider_contract", "provider_id"),
        _nested_text(result, "provider_id"),
    ) or "unknown"


def _extract_voice_profile_ref(*, summary: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    return _first_mapping(
        summary.get("voice_profile_ref"),
        _nested_mapping(summary, "application_contract", "voice_profile_ref"),
        _nested_mapping(summary, "application_contract", "video_task_input_patch", "voice_profile_ref"),
        _nested_mapping(result, "voice_profile_ref"),
        _nested_mapping(result, "voice_simulation_package", "voice_profile_ref"),
        _nested_mapping(result, "voice_simulation_package", "artifact_refs", "voice_profile_ref"),
        _nested_mapping(result, "summary", "voice_profile_ref"),
        _nested_mapping(result, "summary", "application_contract", "voice_profile_ref"),
    )


def _extract_application_contract(*, summary: Mapping[str, Any], result: Mapping[str, Any]) -> dict[str, Any]:
    return _first_mapping(
        summary.get("application_contract"),
        _nested_mapping(result, "application_contract"),
        _nested_mapping(result, "summary", "application_contract"),
        _nested_mapping(result, "voice_simulation_package", "application_contract"),
    )


def _build_voice_profile_ref(
    *,
    ref_id: str,
    created_at: float,
    provider_id: str,
    outcome: str,
    rating: int | float | None,
    notes: str,
    result_path: str,
    review_path: str,
    prompt_audio_path: str,
    sample_audio_path: str,
    source_voice_profile_ref: Mapping[str, Any],
    application_contract: Mapping[str, Any],
    summary: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": VOICE_PROFILE_REF_SCHEMA,
        "ref_id": ref_id,
        "artifact_type": "local_reviewed_voice_profile_ref",
        "provider_id": provider_id,
        "created_at": created_at,
        "review_outcome": outcome,
        "rating": rating,
        "notes": str(notes or "")[:1000],
        "can_apply_to_video_task": True,
        "voice_generation_policy": "use_saved_profile_only",
        "profile_result_path": result_path,
        "review_record_path": review_path,
        "prompt_audio_path": prompt_audio_path,
        "sample_audio_path": sample_audio_path,
        "sample_text_preview": _first_text(
            _nested_text(summary, "voice_simulation_package", "voice_sample", "sample_text_preview"),
            _nested_text(summary, "voice_sample", "sample_text_preview"),
        ),
        "source_voice_profile_ref": dict(source_voice_profile_ref),
        "source_application_contract": dict(application_contract),
    }


def _settings_overrides(
    *,
    provider_id: str,
    voice_profile_ref: Mapping[str, Any] | None,
    prompt_audio_path: str,
) -> dict[str, Any]:
    provider = _settings_provider(provider_id)
    voice_settings: dict[str, Any] = {
        "provider": provider,
        "voice_profile_ref": dict(voice_profile_ref or {}),
        "require_saved_profile": True,
    }
    if prompt_audio_path:
        voice_settings["prompt_audio_path"] = prompt_audio_path
    return {"voice": voice_settings}


def _settings_provider(provider_id: str) -> str:
    if provider_id == "fixture_voice":
        return "fixture"
    if provider_id in {"moss_tts_nano", "edge_tts", "system_tts", "fixture"}:
        return provider_id
    return provider_id or "none"


def _review_warnings(
    *,
    approved: bool,
    source_voice_profile_ref: Mapping[str, Any],
    sample_audio_path: str,
    prompt_audio_path: str,
) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    if approved and not source_voice_profile_ref:
        warnings.append({
            "code": "local_ref_without_toolkit_profile_ref",
            "message": "本地已记录试听批准，但源合约未提供 toolkit voice_profile_ref。",
        })
    if approved and not sample_audio_path and not prompt_audio_path:
        warnings.append({
            "code": "no_playable_audio_path",
            "message": "确认记录中没有可直接播放的本地音频路径。",
        })
    return warnings


def _review_list_item(*, record: Mapping[str, Any], path: Path) -> dict[str, Any]:
    voice_profile_ref = _first_mapping(record.get("voice_profile_ref"))
    return {
        "schema": VOICE_PROFILE_REVIEW_SCHEMA,
        "created_at": record.get("created_at") or 0.0,
        "outcome": record.get("outcome") or "",
        "can_apply_to_video_task": bool(record.get("can_apply_to_video_task")),
        "provider_id": record.get("provider_id") or "",
        "rating": record.get("rating"),
        "notes": record.get("notes") or "",
        "profile_result_path": record.get("profile_result_path") or "",
        "prompt_audio_path": record.get("prompt_audio_path") or "",
        "sample_audio_path": record.get("sample_audio_path") or "",
        "voice_profile_ref": voice_profile_ref,
        "review_record_path": str(path),
    }


def _normalize_outcome(outcome: str) -> str:
    normalized = str(outcome or "approved").strip().lower()
    return normalized if normalized in APPROVAL_OUTCOMES else "needs_retry"


def _make_ref_id(
    *,
    provider_id: str,
    source_voice_profile_ref: Mapping[str, Any],
    profile_result_path: str,
    sample_audio_path: str,
    created_at: float,
) -> str:
    fingerprint = json.dumps(
        {
            "provider_id": provider_id,
            "source_voice_profile_ref": dict(source_voice_profile_ref),
            "profile_result_path": profile_result_path,
            "sample_audio_path": sample_audio_path,
            "created_at": created_at,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:16]
    return f"voice_profile_review_{int(created_at)}_{digest}"


def _read_json_file(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _first_text(*values: Any) -> str:
    for value in values:
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _first_mapping(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _nested_text(data: Mapping[str, Any], *keys: str) -> str:
    value: Any = data
    for key in keys:
        if not isinstance(value, Mapping):
            return ""
        value = value.get(key)
    return str(value or "").strip() if value is not None else ""


def _nested_mapping(data: Mapping[str, Any], *keys: str) -> dict[str, Any]:
    value: Any = data
    for key in keys:
        if not isinstance(value, Mapping):
            return {}
        value = value.get(key)
    return dict(value) if isinstance(value, Mapping) else {}
