from __future__ import annotations

import csv
import base64
import json
import mimetypes
import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from .models import utc_now
from .provider_adapters import ProviderAdapterError, ProviderAdapterPending, probe_model_pipeline, provider_with_slot_settings, run_provider_task, smoke_test_provider_models
from .store import FilmStore


RISK_RULES: tuple[dict[str, object], ...] = (
    {
        "code": "copyright_style",
        "label": "版权风格引用",
        "severity": "medium",
        "terms": ("宫崎骏", "新海诚", "诺兰", "昆汀", "迪士尼", "漫威", "吉卜力", "某导演风格"),
        "suggestion": "改写为可授权的视觉语言，例如色彩、镜头、光线和构图描述。",
    },
    {
        "code": "celebrity_or_identity",
        "label": "真人/名人肖像",
        "severity": "high",
        "terms": ("明星", "名人", "真人肖像", "刘德华", "周杰伦", "易烊千玺", "奥巴马"),
        "suggestion": "替换为原创角色设定，并记录参考来源授权。",
    },
    {
        "code": "political_sensitive",
        "label": "政治敏感内容",
        "severity": "high",
        "terms": ("政治", "竞选", "国家领导人", "政府宣传"),
        "suggestion": "进入人工复核，确认用途、地区和发布渠道。",
    },
    {
        "code": "brand_or_logo",
        "label": "品牌/商标",
        "severity": "medium",
        "terms": ("logo", "商标", "品牌露出", "耐克", "苹果公司", "可口可乐"),
        "suggestion": "使用虚构品牌或确认商用授权。",
    },
)

PLANNING_ISSUE_HINTS = {
    "story_off": ("故事偏离", "把镜头目标重新对齐到项目 logline，并明确这一镜头推动的剧情信息。"),
    "character_unclear": ("角色不清晰", "补充角色动作、身份线索和可见特征，让后续人物图更稳定。"),
    "scene_unclear": ("场景不清晰", "补充空间层次、时间、光线和关键道具，让文生图更容易落地。"),
    "weak_camera": ("镜头太弱", "强化镜头运动、景别和节奏变化，让图生视频有更明确的动态目标。"),
}

IMAGE_ISSUE_HINTS = {
    "character_mismatch": ("人物不像", "强化角色外观、服装、年龄气质和表情，减少身份漂移。"),
    "scene_mismatch": ("场景不对", "强化地点、时间、光线、背景层次和关键道具。"),
    "composition_wrong": ("构图不对", "明确主体位置、景别、视线方向和画面重心。"),
    "style_inconsistent": ("风格不统一", "补充统一的电影感光线、色彩和镜头质感。"),
    "artifact": ("有瑕疵", "强调自然手部、真实面部、无畸形、无错误文字、无多余肢体。"),
}

VIDEO_ISSUE_HINTS = {
    "stiff_motion": ("动作僵硬", "让人物动作更自然、幅度更小，避免突然跳变。"),
    "camera_wrong": ("镜头运动错误", "明确镜头运动方向、速度和起止构图。"),
    "identity_drift": ("人物漂移", "强调参考图中的人物、服装、发型和场景连续性。"),
    "duration_wrong": ("时长不对", "按分镜时长完成一个清晰动作，不要提前结束或拖长。"),
    "flicker": ("画面闪烁", "保持光照、脸部、手部和背景稳定，减少伪影。"),
}


def scan_prompt(prompt: str) -> dict[str, Any]:
    text = (prompt or "").lower()
    flags: list[dict[str, str]] = []
    for rule in RISK_RULES:
        for term in rule["terms"]:  # type: ignore[index]
            if str(term).lower() in text:
                flags.append(
                    {
                        "code": str(rule["code"]),
                        "label": str(rule["label"]),
                        "severity": str(rule["severity"]),
                        "term": str(term),
                        "suggestion": str(rule["suggestion"]),
                    }
                )
                break
    if any(flag["severity"] == "high" for flag in flags):
        risk_level = "high"
    elif flags:
        risk_level = "medium"
    else:
        risk_level = "low"
    return {
        "risk_level": risk_level,
        "flags": flags,
        "approval_required": risk_level != "low",
    }


def write_mock_task_output(store: FilmStore, task: dict[str, Any]) -> Path:
    provider = store.get_provider(str(task["provider_id"]))
    return run_provider_task(store=store, task=task, provider=provider).output_file


def run_generation_task_with_provider(store: FilmStore, task: dict[str, Any]) -> dict[str, Any]:
    provider = store.get_provider(str(task["provider_id"]))
    if task.get("model_slot"):
        provider = provider_with_slot_settings(provider, _model_slot(store, str(task["model_slot"])))
    result = run_provider_task(store=store, task=task, provider=provider)
    project = store.complete_generation_task(task["id"], result={
        "output_file": result.output_file,
        "asset_type": result.asset_type,
        "title": result.title,
        "actual_cost": result.actual_cost,
        "request_ref": result.request_ref,
        "response_ref": result.response_ref,
        "metadata": result.metadata,
    })
    return {
        "output_file": str(result.output_file),
        "adapter": result.metadata.get("adapter") or "",
        "model_family": result.metadata.get("model_family") or "",
        "project": project,
    }


def get_image_review_state(store: FilmStore, project_id: str) -> dict[str, Any]:
    project = store.get_project(project_id)
    image_assets = _image_assets(project)
    return {
        "schema": "aifilm-studio.image-review-state.v1",
        "project_id": project_id,
        "slot": _model_slot(store, "text_to_image_model"),
        "status": _image_review_status(project, image_assets),
        "items": [_image_review_item(project, shot, image_assets) for shot in project.get("shots") or []],
        "project": project,
    }


def generate_project_images(store: FilmStore, project_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    project = store.get_project(project_id)
    shots = _selected_image_shots(project, str(payload.get("shot_id") or ""))
    if not shots:
        raise ValueError("Approve planning and sync storyboard before generating images.")
    slot = _model_slot(store, "text_to_image_model")
    if not slot or not slot.get("enabled", True):
        raise ProviderAdapterError("Text-to-image model slot is disabled.")
    provider_id = str(slot.get("provider_id") or "").strip()
    model = str(slot.get("model") or "").strip()
    if not provider_id or not model:
        raise ProviderAdapterError("Text-to-image model slot is not configured.")
    results = []
    for shot in shots:
        task_id = f"image-{uuid4()}"
        base_prompt = str(
            payload.get("prompt")
            or _planned_image_prompt(project, shot)
            or shot.get("image_prompt")
            or shot.get("prompt")
            or shot.get("summary")
            or shot.get("title")
            or ""
        ).strip()
        reference_assets = _reference_assets_for_shot(project, shot)
        prompt = _augment_image_prompt_with_references(project, shot, base_prompt, reference_assets)
        project_after_create = store.create_generation_task(
            project_id,
            {
                "id": task_id,
                "shot_id": shot.get("id"),
                "stage": "keyframe",
                "provider_id": provider_id,
                "model": model,
                "prompt": prompt,
                "negative_prompt": str(payload.get("negative_prompt") or "畸形手指、错误文字、品牌 logo、多人错位、低清、模糊").strip(),
                "approval_required": False,
                "cost_estimate": float(payload.get("cost_estimate") or 0),
            },
        )
        task = store.get_task(task_id)
        task = {
            **task,
            "model_slot": "text_to_image_model",
            "model_role": "text_to_image",
            "reference_images": [_asset_reference_value(asset) for asset in reference_assets],
        }
        run_payload = run_generation_task_with_provider(store, task)
        generated_asset = _task_output_asset(run_payload["project"], task_id)
        if generated_asset:
            store.update_asset(
                generated_asset["id"],
                {
                    "title": f"关键帧图 #{shot.get('position') or ''} {shot.get('title') or ''}".strip(),
                    "status": "generated",
                    "metadata": {
                        "artifact_kind": "image_candidate",
                        "review_status": "needs_review",
                        "model_slot": "text_to_image_model",
                        "model_role": "text_to_image",
                        "shot_position": shot.get("position"),
                        "base_prompt": base_prompt,
                        "reference_asset_ids": [asset.get("id") for asset in reference_assets],
                        "reference_names": [str((asset.get("metadata") or {}).get("reference_name") or asset.get("title") or "") for asset in reference_assets],
                        "source": "generated",
                    },
                },
            )
            results.append(generated_asset["id"])
        project = project_after_create
    state = get_image_review_state(store, project_id)
    state["generated_asset_ids"] = results
    return state


def create_reference_asset(store: FilmStore, project_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    project = store.get_project(project_id)
    kind = str(payload.get("kind") or payload.get("reference_kind") or "character").strip()
    if kind not in {"character", "scene"}:
        raise ValueError("Reference kind must be character or scene.")
    reference_scope = str(payload.get("reference_scope") or payload.get("scope") or "project").strip() or "project"
    if reference_scope not in {"project", "shots"}:
        raise ValueError("Reference scope must be project or shots.")
    shot_ids = _validated_reference_shot_ids(project, payload.get("shot_ids") or [])
    if reference_scope == "project":
        shot_ids = []
    name = str(payload.get("name") or payload.get("title") or ("角色参考" if kind == "character" else "场景参考")).strip()
    visual_prompt = str(payload.get("visual_prompt") or payload.get("description") or "").strip()
    file_path = str(payload.get("file_path") or "").strip().strip('"')
    data_url = str(payload.get("data_url") or "").strip()
    if data_url:
        file_name = str(payload.get("file_name") or f"{kind}-reference.png").strip()
        file_path = str(_save_reference_data_url(store, project_id, data_url, file_name))
    if not file_path:
        raise ValueError("Reference image file is required.")
    if not Path(file_path).is_file():
        raise ValueError("Reference image file does not exist.")
    mime_type = mimetypes.guess_type(file_path)[0] or ""
    if mime_type and not mime_type.startswith("image/"):
        raise ValueError("Reference file must be an image.")
    store.create_asset(
        project_id,
        {
            "type": "reference",
            "title": name,
            "file_path": file_path,
            "status": "approved",
            "prompt": visual_prompt,
            "metadata": {
                "artifact_kind": "reference_image",
                "review_status": "approved",
                "reference_kind": kind,
                "reference_name": name,
                "reference_scope": reference_scope,
                "shot_ids": shot_ids,
                "visual_prompt": visual_prompt,
                "source": "user_reference",
            },
        },
    )
    return store.get_project(project_id)


def update_reference_bindings(store: FilmStore, project_id: str, asset_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    project = store.get_project(project_id)
    asset = _project_asset(project, asset_id)
    if not asset or asset.get("type") != "reference":
        raise ValueError("Reference asset not found")
    metadata = asset.get("metadata") or {}
    reference_scope = str(payload.get("reference_scope") or payload.get("scope") or metadata.get("reference_scope") or "project").strip() or "project"
    if reference_scope not in {"project", "shots"}:
        raise ValueError("Reference scope must be project or shots.")
    shot_ids = _validated_reference_shot_ids(project, payload.get("shot_ids") or [])
    if reference_scope == "project":
        shot_ids = []
    store.update_asset(
        asset_id,
        {
            "metadata": {
                "reference_scope": reference_scope,
                "shot_ids": shot_ids,
            }
        },
    )
    return store.get_project(project_id)


def reorder_project_shots(store: FilmStore, project_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    project = store.get_project(project_id)
    incoming = payload.get("shot_ids") or []
    if not isinstance(incoming, list):
        raise ValueError("shot_ids must be a list.")
    shots = sorted(project.get("shots") or [], key=lambda shot: int(shot.get("position") or 0))
    existing_ids = [str(shot.get("id") or "") for shot in shots if shot.get("id")]
    incoming_ids = [str(item) for item in incoming if str(item)]
    unknown = [shot_id for shot_id in incoming_ids if shot_id not in existing_ids]
    if unknown:
        raise ValueError("Unknown shot id in order.")
    ordered_ids = []
    for shot_id in incoming_ids + existing_ids:
        if shot_id and shot_id not in ordered_ids:
            ordered_ids.append(shot_id)
    updated_project = project
    for position, shot_id in enumerate(ordered_ids, start=1):
        updated_project = store.update_shot(shot_id, {"position": position})
    return updated_project


def approve_image_asset(store: FilmStore, project_id: str, asset_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    asset = _project_asset(store.get_project(project_id), asset_id)
    if not asset or asset.get("type") != "keyframe":
        raise ValueError("Image asset not found")
    store.update_asset(
        asset_id,
        {
            "status": "approved",
            "metadata": {
                "artifact_kind": "image_candidate",
                "review_status": "approved",
                "approved_at": utc_now(),
                "review_note": str(payload.get("note") or "").strip(),
            },
        },
    )
    _sync_review_workflow(store, project_id)
    return get_image_review_state(store, project_id)


def delete_project_asset(store: FilmStore, project_id: str, asset_id: str) -> dict[str, Any]:
    project = store.get_project(project_id)
    asset = _project_asset(project, asset_id)
    if not asset:
        raise ValueError("Asset not found")
    deleted = store.delete_asset(asset_id)
    _delete_local_asset_file(store, deleted)
    return store.get_project(project_id)


def delete_image_asset(store: FilmStore, project_id: str, asset_id: str) -> dict[str, Any]:
    project = store.get_project(project_id)
    asset = _project_asset(project, asset_id)
    if not asset or asset.get("type") != "keyframe":
        raise ValueError("Image asset not found")
    store.delete_asset(asset_id)
    _delete_local_asset_file(store, asset)
    return get_image_review_state(store, project_id)


def regenerate_image_asset(store: FilmStore, project_id: str, asset_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    project = store.get_project(project_id)
    asset = _project_asset(project, asset_id)
    if not asset or asset.get("type") != "keyframe":
        raise ValueError("Image asset not found")
    issue = str(payload.get("issue") or "artifact").strip()
    label, suggestion = IMAGE_ISSUE_HINTS.get(issue, IMAGE_ISSUE_HINTS["artifact"])
    note = str(payload.get("note") or payload.get("description") or "").strip()
    if not note:
        raise ValueError("Image regeneration requires a user note.")
    shot = next((item for item in project.get("shots") or [] if str(item.get("id") or "") == str(asset.get("shot_id") or "")), {})
    metadata = asset.get("metadata") or {}
    base_prompt = str(payload.get("prompt") or _planned_image_prompt(project, shot) or metadata.get("base_prompt") or asset.get("prompt") or "").strip()
    prompt = base_prompt
    if prompt:
        prompt = f"{prompt}\n\n返工问题：{label}。\n通用方向：{suggestion}\n用户具体说明：{note}"
    shot_id = str(asset.get("shot_id") or "")
    state = generate_project_images(store, project_id, {"shot_id": shot_id, "prompt": prompt, "negative_prompt": payload.get("negative_prompt") or ""})
    for generated_asset_id in state.get("generated_asset_ids") or []:
        store.update_asset(
            str(generated_asset_id),
            {
                "metadata": {
                    "base_prompt": base_prompt,
                    "review_note": note,
                    "review_issue": issue,
                    "review_issue_label": label,
                    "regenerated_from_asset_id": asset_id,
                }
            },
        )
    return get_image_review_state(store, project_id)


def get_clip_review_state(store: FilmStore, project_id: str) -> dict[str, Any]:
    project = store.get_project(project_id)
    image_assets = _image_assets(project)
    clip_assets = _clip_assets(project)
    return {
        "schema": "aifilm-studio.clip-review-state.v1",
        "project_id": project_id,
        "slot": _model_slot(store, "image_to_video_model"),
        "status": _clip_review_status(project, image_assets, clip_assets),
        "items": [_clip_review_item(project, shot, image_assets, clip_assets) for shot in project.get("shots") or []],
        "project": project,
    }


def generate_project_clips(store: FilmStore, project_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    project = store.get_project(project_id)
    image_assets = _image_assets(project)
    shots = _selected_clip_shots(project, image_assets, str(payload.get("shot_id") or ""))
    if not shots:
        raise ValueError("Approve a keyframe image before generating video clips.")
    slot = _model_slot(store, "image_to_video_model")
    if not slot or not slot.get("enabled", True):
        raise ProviderAdapterError("Image-to-video model slot is disabled.")
    provider_id = str(slot.get("provider_id") or "").strip()
    model = str(slot.get("model") or "").strip()
    if not provider_id or not model:
        raise ProviderAdapterError("Image-to-video model slot is not configured.")
    results = []
    errors = []
    pending = []
    for shot, reference_image in shots:
        task_id = f"clip-{uuid4()}"
        base_prompt = str(
            payload.get("prompt")
            or _planned_video_prompt(project, shot)
            or shot.get("video_prompt")
            or shot.get("prompt")
            or shot.get("summary")
            or shot.get("title")
            or ""
        ).strip()
        reference_assets = _reference_assets_for_shot(project, shot)
        prompt = _augment_video_prompt_with_references(project, shot, base_prompt, reference_assets, reference_image)
        store.create_generation_task(
            project_id,
            {
                "id": task_id,
                "shot_id": shot.get("id"),
                "stage": "clip",
                "provider_id": provider_id,
                "model": model,
                "prompt": prompt,
                "negative_prompt": str(payload.get("negative_prompt") or "闪烁、变形、人物漂移、手部畸形、错误文字、品牌 logo").strip(),
                "approval_required": False,
                "cost_estimate": float(payload.get("cost_estimate") or 0),
            },
        )
        task = store.get_task(task_id)
        task = {
            **task,
            "model_slot": "image_to_video_model",
            "model_role": "image_to_video",
            "duration": int(shot.get("duration_seconds") or payload.get("duration") or 5),
            "reference_image": reference_image.get("file_path") or "",
            "reference_image_url": _asset_source_media_url(reference_image),
        }
        try:
            run_payload = run_generation_task_with_provider(store, task)
        except ProviderAdapterPending as exc:
            message = str(exc) or "视频任务已提交，等待供应商返回可播放文件。"
            store.set_generation_task_status(task_id, "running", message)
            pending.append({"task_id": task_id, "shot_id": shot.get("id"), "message": message})
            continue
        except RuntimeError as exc:
            message = str(exc) or "Video generation failed."
            store.fail_generation_task(task_id, message)
            errors.append({"task_id": task_id, "shot_id": shot.get("id"), "message": message})
            continue
        generated_asset = _task_output_asset(run_payload["project"], task_id)
        if generated_asset:
            store.update_asset(
                generated_asset["id"],
                {
                    "title": f"视频片段 #{shot.get('position') or ''} {shot.get('title') or ''}".strip(),
                    "status": "generated",
                    "metadata": {
                        "artifact_kind": "clip_candidate",
                        "review_status": "needs_review",
                        "model_slot": "image_to_video_model",
                        "model_role": "image_to_video",
                        "shot_position": shot.get("position"),
                        "duration_seconds": int(shot.get("duration_seconds") or 5),
                        "base_prompt": base_prompt,
                        "reference_image_asset_id": reference_image.get("id"),
                        "reference_image_file_path": reference_image.get("file_path") or "",
                        "reference_asset_ids": [asset.get("id") for asset in reference_assets],
                        "reference_names": [str((asset.get("metadata") or {}).get("reference_name") or asset.get("title") or "") for asset in reference_assets],
                        "source": "generated",
                    },
                },
            )
            results.append(generated_asset["id"])
    state = get_clip_review_state(store, project_id)
    state["generated_asset_ids"] = results
    state["errors"] = errors
    state["pending"] = pending
    if errors and not results:
        raise ProviderAdapterError(errors[0]["message"])
    return state


def approve_clip_asset(store: FilmStore, project_id: str, asset_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    asset = _project_asset(store.get_project(project_id), asset_id)
    if not asset or asset.get("type") != "video":
        raise ValueError("Clip asset not found")
    store.update_asset(
        asset_id,
        {
            "status": "approved",
            "metadata": {
                "artifact_kind": "clip_candidate",
                "review_status": "approved",
                "approved_at": utc_now(),
                "review_note": str(payload.get("note") or "").strip(),
            },
        },
    )
    _sync_review_workflow(store, project_id)
    return get_clip_review_state(store, project_id)


def regenerate_clip_asset(store: FilmStore, project_id: str, asset_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    payload = payload or {}
    project = store.get_project(project_id)
    asset = _project_asset(project, asset_id)
    if not asset or asset.get("type") != "video":
        raise ValueError("Clip asset not found")
    issue = str(payload.get("issue") or "stiff_motion").strip()
    label, suggestion = VIDEO_ISSUE_HINTS.get(issue, VIDEO_ISSUE_HINTS["stiff_motion"])
    note = str(payload.get("note") or payload.get("description") or "").strip()
    if not note:
        raise ValueError("Clip regeneration requires a user note.")
    shot = next((item for item in project.get("shots") or [] if str(item.get("id") or "") == str(asset.get("shot_id") or "")), {})
    metadata = asset.get("metadata") or {}
    base_prompt = str(payload.get("prompt") or _planned_video_prompt(project, shot) or metadata.get("base_prompt") or asset.get("prompt") or "").strip()
    prompt = base_prompt
    if prompt:
        prompt = f"{prompt}\n\n返工问题：{label}。\n通用方向：{suggestion}\n用户具体说明：{note}"
    state = generate_project_clips(store, project_id, {"shot_id": str(asset.get("shot_id") or ""), "prompt": prompt, "negative_prompt": payload.get("negative_prompt") or ""})
    for generated_asset_id in state.get("generated_asset_ids") or []:
        store.update_asset(
            str(generated_asset_id),
            {
                "metadata": {
                    "base_prompt": base_prompt,
                    "review_note": note,
                    "review_issue": issue,
                    "review_issue_label": label,
                    "regenerated_from_asset_id": asset_id,
                }
            },
        )
    return get_clip_review_state(store, project_id)


def delete_clip_asset(store: FilmStore, project_id: str, asset_id: str) -> dict[str, Any]:
    project = store.get_project(project_id)
    asset = _project_asset(project, asset_id)
    if not asset or asset.get("type") != "video":
        raise ValueError("Clip asset not found")
    store.delete_asset(asset_id)
    _delete_local_asset_file(store, asset)
    return get_clip_review_state(store, project_id)


def smoke_test_provider(store: FilmStore, provider_id: str) -> dict[str, Any]:
    return smoke_test_provider_models(store=store, provider=store.get_provider(provider_id))


def run_model_pipeline_probe(store: FilmStore, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    slots = None
    if payload and isinstance(payload.get("slots"), list):
        slots = payload["slots"]
    return probe_model_pipeline(store=store, slots=slots)


def get_planning_review_state(store: FilmStore, project_id: str) -> dict[str, Any]:
    project = store.get_project(project_id)
    draft_asset, draft = _latest_planning_draft(project)
    return {
        "schema": "aifilm-studio.planning-review-state.v1",
        "project_id": project_id,
        "status": _planning_status(draft_asset),
        "draft_asset": draft_asset,
        "versions": _planning_versions(project),
        "planning_draft": draft or _draft_from_project(project, source="current_project"),
        "project": project,
    }


def get_planning_version(store: FilmStore, project_id: str, asset_id: str) -> dict[str, Any]:
    project = store.get_project(project_id)
    for version in _planning_versions(project):
        if str(version.get("asset_id") or "") != str(asset_id):
            continue
        draft = _read_json(Path(str(version.get("file_path") or "")))
        if not draft:
            break
        return {
            "schema": "aifilm-studio.planning-version.v1",
            "project_id": project_id,
            "version": version,
            "planning_draft": draft,
        }
    raise ValueError("Planning version not found")


def generate_planning_draft(store: FilmStore, project_id: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    project = store.get_project(project_id)
    extra_brief = str((payload or {}).get("brief") or "").strip()
    model_result = _generate_planning_draft_with_model(store, project, extra_brief=extra_brief)
    if model_result is not None:
        return model_result
    draft = _draft_from_project(project, source="planning_model_mock", extra_brief=extra_brief)
    return _save_planning_draft(store, project_id, draft, review_status="draft", source="generated")


def save_planning_draft(store: FilmStore, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    project = store.get_project(project_id)
    draft = _normalize_planning_draft(payload.get("planning_draft") or payload, project=project)
    return _save_planning_draft(store, project_id, draft, review_status="draft", source="manual_edit")


def approve_planning_draft(store: FilmStore, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    project = store.get_project(project_id)
    draft = _normalize_planning_draft(payload.get("planning_draft") or payload, project=project)
    approved = _save_planning_draft(store, project_id, draft, review_status="approved", source="approved")
    storyboard = approved["planning_draft"].get("storyboard") or []
    store.replace_project_shots(project_id, [_shot_from_planning_item(item) for item in storyboard])
    _sync_review_workflow(store, project_id)
    return get_planning_review_state(store, project_id)


def regenerate_planning_shot(store: FilmStore, project_id: str, position: int, payload: dict[str, Any]) -> dict[str, Any]:
    project = store.get_project(project_id)
    draft = _normalize_planning_draft(payload.get("planning_draft") or payload, project=project)
    issue = str(payload.get("issue") or "story_off").strip()
    storyboard = list(draft.get("storyboard") or [])
    selected_index = _storyboard_index(storyboard, position)
    if selected_index is None:
        raise ValueError("Planning shot not found")
    storyboard[selected_index] = _regenerated_planning_item(storyboard[selected_index], issue=issue, project=project)
    draft["storyboard"] = storyboard
    return _save_planning_draft(store, project_id, draft, review_status="draft", source=f"shot_regenerated:{issue}")


def approve_planning_shot(store: FilmStore, project_id: str, position: int, payload: dict[str, Any]) -> dict[str, Any]:
    project = store.get_project(project_id)
    draft = _normalize_planning_draft(payload.get("planning_draft") or payload, project=project)
    storyboard = list(draft.get("storyboard") or [])
    selected_index = _storyboard_index(storyboard, position)
    if selected_index is None:
        raise ValueError("Planning shot not found")
    storyboard[selected_index] = {**storyboard[selected_index], "status": "approved"}
    draft["storyboard"] = storyboard
    return _save_planning_draft(store, project_id, draft, review_status="draft", source="shot_approved")


def export_edit_pack(store: FilmStore, project_id: str) -> dict[str, Any]:
    _sync_review_workflow(store, project_id, edit_pack_exported=True)
    project = store.get_project(project_id)
    project_slug = _slug(project["title"]) or project_id[:8]
    output_dir = store.data_dir / "edit_packs" / f"{project_slug}-{project_id[:8]}"
    output_dir.mkdir(parents=True, exist_ok=True)
    export_assets = [asset for asset in project["assets"] if _asset_exportable(asset)]

    manifest = {
        "schema": "aifilm-studio.edit-pack.v1",
        "exported_at": utc_now(),
        "project": {
            "id": project["id"],
            "title": project["title"],
            "logline": project["logline"],
            "format": project["format"],
            "target_duration_seconds": project["target_duration_seconds"],
            "current_step": project["current_step"],
        },
        "workflow": project["workflow"],
        "shots": project["shots"],
        "assets": export_assets,
        "tasks": project["tasks"],
        "ledger": project["ledger"],
    }

    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_csv(output_dir / "shots.csv", project["shots"], [
        "position",
        "title",
        "duration_seconds",
        "location",
        "camera",
        "status",
        "prompt",
    ])
    _write_csv(output_dir / "assets.csv", export_assets, [
        "type",
        "title",
        "shot_id",
        "file_path",
        "provider",
        "model",
        "cost",
        "status",
    ])
    (output_dir / "tasks.json").write_text(
        json.dumps(project["tasks"], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    handoff = _build_smart_video_cut_handoff(manifest, manifest_path=manifest_path)
    handoff_path = output_dir / "smart_video_cut_handoff.json"
    handoff_path.write_text(json.dumps(handoff, ensure_ascii=False, indent=2), encoding="utf-8")

    updated_project = store.create_asset(
        project_id,
        {
            "type": "manifest",
            "title": "剪辑交付包 manifest",
            "file_path": str(manifest_path),
            "status": "exported",
            "metadata": {
                "edit_pack_dir": str(output_dir),
                "schema": manifest["schema"],
                "smart_video_cut_handoff": str(handoff_path),
            },
        },
    )
    return {
        "edit_pack": {
            "directory": str(output_dir),
            "manifest_path": str(manifest_path),
            "handoff_path": str(handoff_path),
            "files": ["manifest.json", "shots.csv", "assets.csv", "tasks.json", "smart_video_cut_handoff.json"],
        },
        "project": updated_project,
    }


def _build_smart_video_cut_handoff(manifest: dict[str, Any], *, manifest_path: Path) -> dict[str, Any]:
    project = dict(manifest.get("project") or {})
    shots = list(manifest.get("shots") or [])
    assets = list(manifest.get("assets") or [])
    video_assets = [
        {
            "asset_id": asset.get("id"),
            "shot_id": asset.get("shot_id"),
            "type": asset.get("type"),
            "title": asset.get("title"),
            "file_path": asset.get("file_path"),
            "provider": asset.get("provider"),
            "model": asset.get("model"),
            "status": asset.get("status"),
        }
        for asset in assets
        if str(asset.get("type") or "") in {"video", "final"}
    ]
    shot_lines = []
    for shot in shots:
        shot_lines.append(
            " / ".join(
                part
                for part in [
                    f"镜头{shot.get('position')}",
                    str(shot.get("title") or "").strip(),
                    str(shot.get("summary") or "").strip(),
                    str(shot.get("prompt") or "").strip(),
                ]
                if part
            )
        )
    request_parts = [
        f"项目：{project.get('title') or project.get('id')}",
        str(project.get("logline") or "").strip(),
        "请根据以下分镜和已生成素材，进入智能剪辑软件完成剪辑标准确认与后续装配。",
        *shot_lines,
    ]
    return {
        "schema": "aifilm-studio.smart-video-cut-handoff.v1",
        "source_schema": manifest.get("schema"),
        "source_manifest_path": str(manifest_path),
        "project": project,
        "recommended_project_id": project.get("id") or "filmgen_project",
        "recommended_user_request": "\n".join(part for part in request_parts if part),
        "recommended_output_dir": str(Path("workspace") / "output" / f"filmgen-{project.get('id') or 'project'}"),
        "shots": shots,
        "video_assets": video_assets,
        "all_assets": assets,
    }


def _asset_exportable(asset: dict[str, Any]) -> bool:
    metadata = asset.get("metadata") or {}
    artifact_kind = str(metadata.get("artifact_kind") or "")
    status = _asset_review_status(asset)
    if str(asset.get("type") or "") == "manifest":
        return False
    if artifact_kind in {"planning_draft", "image_candidate", "clip_candidate"}:
        if artifact_kind == "clip_candidate" and not (_asset_has_playable_video(asset) or metadata.get("mock")):
            return False
        return status == "approved"
    if str(asset.get("type") or "") in {"keyframe", "video"}:
        if str(asset.get("type") or "") == "video" and not (_asset_has_playable_video(asset) or metadata.get("mock")):
            return False
        return status == "approved"
    return str(asset.get("status") or "") != "deleted"


def _image_assets(project: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        asset
        for asset in project.get("assets") or []
        if str(asset.get("type") or "") == "keyframe"
    ]


def _clip_assets(project: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        asset
        for asset in project.get("assets") or []
        if str(asset.get("type") or "") == "video" and (_asset_has_playable_video(asset) or (asset.get("metadata") or {}).get("mock"))
    ]


def _asset_has_playable_video(asset: dict[str, Any]) -> bool:
    return Path(str(asset.get("file_path") or "")).suffix.lower() in {".mp4", ".webm", ".mov", ".m4v"}


def _sync_review_workflow(store: FilmStore, project_id: str, *, edit_pack_exported: bool = False) -> dict[str, Any]:
    project = store.get_project(project_id)
    completed_steps: set[str] = {"idea"}
    approval_notes: dict[str, str] = {}
    current_step = "script_draft"
    shots = project.get("shots") or []
    image_assets = _image_assets(project)
    clip_assets = _clip_assets(project)

    planning_ready = _has_approved_planning(project) or bool(shots)
    if planning_ready:
        completed_steps.update({"script_draft", "storyboard_review"})
        approval_notes["storyboard_review"] = "策划稿已批准" if _has_approved_planning(project) else "分镜已确认"
        current_step = "keyframe_generation"

    if shots and image_assets:
        completed_steps.add("keyframe_generation")
        current_step = "keyframe_review"
    if shots and all(_approved_image_for_shot(image_assets, str(shot.get("id") or "")) for shot in shots):
        completed_steps.update({"keyframe_generation", "keyframe_review"})
        approval_notes["keyframe_review"] = "关键帧已批准"
        current_step = "clip_generation"

    if shots and clip_assets:
        completed_steps.add("clip_generation")
        current_step = "clip_review"
    if shots and all(_approved_clip_for_shot(clip_assets, str(shot.get("id") or "")) for shot in shots):
        completed_steps.update({"clip_generation", "clip_review"})
        approval_notes["clip_review"] = "视频片段已批准"
        current_step = "edit_assembly"
        if edit_pack_exported:
            completed_steps.add("edit_assembly")
            current_step = "final_qc"

    return store.sync_workflow_progress(
        project_id,
        completed_steps=completed_steps,
        current_step=current_step,
        approval_notes=approval_notes,
    )


def _has_approved_planning(project: dict[str, Any]) -> bool:
    return any(
        str(asset.get("type") or "") == "script"
        and (asset.get("metadata") or {}).get("artifact_kind") == "planning_draft"
        and _asset_review_status(asset) == "approved"
        for asset in project.get("assets") or []
    )


def _approved_clip_for_shot(clip_assets: list[dict[str, Any]], shot_id: str) -> dict[str, Any] | None:
    return next(
        (
            asset
            for asset in clip_assets
            if str(asset.get("shot_id") or "") == shot_id and _asset_review_status(asset) == "approved"
        ),
        None,
    )


def _image_review_status(project: dict[str, Any], image_assets: list[dict[str, Any]]) -> str:
    shots = project.get("shots") or []
    if not shots:
        return "waiting_for_planning"
    if not image_assets:
        return "not_started"
    latest_by_shot = {str(item["shot_id"]): item for item in reversed(image_assets) if item.get("shot_id")}
    if all(_asset_review_status(latest_by_shot.get(str(shot.get("id"))) or {}) == "approved" for shot in shots):
        return "approved"
    return "needs_review"


def _image_review_item(project: dict[str, Any], shot: dict[str, Any], image_assets: list[dict[str, Any]]) -> dict[str, Any]:
    shot_assets = [asset for asset in image_assets if str(asset.get("shot_id") or "") == str(shot.get("id") or "")]
    latest = shot_assets[0] if shot_assets else None
    return {
        "shot": shot,
        "status": _asset_review_status(latest or {}) if latest else "missing",
        "planned_image_prompt": _planned_image_prompt(project, shot) or shot.get("image_prompt") or shot.get("prompt") or "",
        "latest_asset": latest,
        "versions": shot_assets[:8],
    }


def _clip_review_status(project: dict[str, Any], image_assets: list[dict[str, Any]], clip_assets: list[dict[str, Any]]) -> str:
    shots = project.get("shots") or []
    if not shots:
        return "waiting_for_planning"
    if not all(_approved_image_for_shot(image_assets, str(shot.get("id") or "")) for shot in shots):
        return "waiting_for_images"
    statuses = [_clip_item_status(project, shot, image_assets, clip_assets) for shot in shots]
    if not any(status != "missing" for status in statuses):
        return "not_started"
    if all(status == "approved" for status in statuses):
        return "approved"
    if any(status == "failed" for status in statuses):
        return "failed"
    if any(status in {"queued", "running"} for status in statuses):
        return "running"
    return "needs_review"


def _clip_item_status(
    project: dict[str, Any],
    shot: dict[str, Any],
    image_assets: list[dict[str, Any]],
    clip_assets: list[dict[str, Any]],
) -> str:
    shot_id = str(shot.get("id") or "")
    latest = next((asset for asset in clip_assets if str(asset.get("shot_id") or "") == shot_id), None)
    reference_image = _approved_image_for_shot(image_assets, shot_id)
    latest_task = _latest_clip_task_for_shot(project, shot_id)
    if latest:
        return _asset_review_status(latest)
    if latest_task and str(latest_task.get("status") or "") in {"failed", "queued", "running"}:
        return str(latest_task.get("status") or "missing")
    return "missing" if reference_image else "waiting_for_image"


def _clip_review_item(
    project: dict[str, Any],
    shot: dict[str, Any],
    image_assets: list[dict[str, Any]],
    clip_assets: list[dict[str, Any]],
) -> dict[str, Any]:
    shot_id = str(shot.get("id") or "")
    shot_assets = [asset for asset in clip_assets if str(asset.get("shot_id") or "") == shot_id]
    latest = shot_assets[0] if shot_assets else None
    reference_image = _approved_image_for_shot(image_assets, shot_id)
    latest_task = _latest_clip_task_for_shot(project, shot_id, latest)
    return {
        "shot": shot,
        "status": _clip_item_status(project, shot, image_assets, clip_assets),
        "planned_video_prompt": _planned_video_prompt(project, shot) or shot.get("video_prompt") or shot.get("prompt") or "",
        "reference_image": reference_image,
        "latest_asset": latest,
        "latest_task": latest_task,
        "versions": shot_assets[:8],
    }


def _latest_clip_task_for_shot(
    project: dict[str, Any],
    shot_id: str,
    latest_asset: dict[str, Any] | None = None,
) -> dict[str, Any] | None:
    tasks = [
        task
        for task in project.get("tasks") or []
        if str(task.get("stage") or "") == "clip" and str(task.get("shot_id") or "") == shot_id
    ]
    if latest_asset:
        source_task_id = str((latest_asset.get("metadata") or {}).get("source_task_id") or "")
        if source_task_id:
            matched = next((task for task in tasks if str(task.get("id") or "") == source_task_id), None)
            if matched:
                return matched
    return next(
        (
            task
            for task in tasks
        ),
        None,
    )


def _approved_image_for_shot(image_assets: list[dict[str, Any]], shot_id: str) -> dict[str, Any] | None:
    return next(
        (
            asset
            for asset in image_assets
            if str(asset.get("shot_id") or "") == shot_id and _asset_review_status(asset) == "approved"
        ),
        None,
    )


def _asset_review_status(asset: dict[str, Any]) -> str:
    metadata = asset.get("metadata") or {}
    return str(metadata.get("review_status") or asset.get("status") or "generated")


def _selected_image_shots(project: dict[str, Any], shot_id: str) -> list[dict[str, Any]]:
    shots = list(project.get("shots") or [])
    if not shot_id:
        return shots
    return [shot for shot in shots if str(shot.get("id") or "") == shot_id]


def _reference_assets_for_shot(project: dict[str, Any], shot: dict[str, Any]) -> list[dict[str, Any]]:
    assets = []
    shot_id = str(shot.get("id") or "")
    for asset in project.get("assets") or []:
        metadata = asset.get("metadata") or {}
        if asset.get("type") != "reference":
            continue
        if _asset_review_status(asset) != "approved":
            continue
        if metadata.get("reference_kind") not in {"character", "scene"}:
            continue
        shot_ids = [str(item) for item in metadata.get("shot_ids") or [] if str(item)]
        reference_scope = str(metadata.get("reference_scope") or "").strip()
        if reference_scope == "shots" or (not reference_scope and shot_ids):
            if shot_id not in shot_ids:
                continue
        assets.append(asset)
    assets.sort(key=lambda asset: (0 if (asset.get("metadata") or {}).get("reference_kind") == "character" else 1, asset.get("created_at") or ""))
    return assets


def _validated_reference_shot_ids(project: dict[str, Any], shot_ids: Any) -> list[str]:
    if not isinstance(shot_ids, list):
        raise ValueError("Reference shot_ids must be a list.")
    valid_ids = {str(shot.get("id") or "") for shot in project.get("shots") or []}
    normalized = []
    for item in shot_ids:
        shot_id = str(item or "").strip()
        if not shot_id:
            continue
        if shot_id not in valid_ids:
            raise ValueError("Reference shot id does not exist.")
        if shot_id not in normalized:
            normalized.append(shot_id)
    return normalized


def _asset_reference_value(asset: dict[str, Any]) -> str:
    return _asset_source_media_url(asset) or str(asset.get("file_path") or "").strip()


def _augment_image_prompt_with_references(
    project: dict[str, Any],
    shot: dict[str, Any],
    prompt: str,
    reference_assets: list[dict[str, Any]],
) -> str:
    parts = [prompt]
    _asset, draft = _latest_planning_draft(project)
    if draft:
        character_lines = [
            _card_prompt_line("角色设定", card)
            for card in draft.get("characters") or []
            if isinstance(card, dict)
        ]
        scene_lines = [
            _card_prompt_line("场景设定", card)
            for card in draft.get("scenes") or []
            if isinstance(card, dict)
        ]
        if character_lines:
            parts.append("固定角色设定：" + "；".join(character_lines))
        if scene_lines:
            parts.append("固定场景设定：" + "；".join(scene_lines))
    reference_lines = []
    for asset in reference_assets:
        metadata = asset.get("metadata") or {}
        kind = "角色参考图" if metadata.get("reference_kind") == "character" else "场景参考图"
        name = str(metadata.get("reference_name") or asset.get("title") or "").strip()
        visual = str(metadata.get("visual_prompt") or asset.get("prompt") or "").strip()
        reference_lines.append("：".join(part for part in [kind, name, visual] if part))
    if reference_lines:
        parts.append("必须保持参考图一致性：" + "；".join(reference_lines))
    parts.append("同一角色的脸型、发型、服装、年龄感和画风在所有分镜中保持一致；同一场景的空间结构、色彩和光线方向保持一致。")
    return "\n".join(part for part in parts if part)


def _augment_video_prompt_with_references(
    project: dict[str, Any],
    shot: dict[str, Any],
    prompt: str,
    reference_assets: list[dict[str, Any]],
    keyframe_asset: dict[str, Any],
) -> str:
    parts = [_augment_image_prompt_with_references(project, shot, prompt, reference_assets)]
    keyframe_title = str(keyframe_asset.get("title") or "").strip()
    if keyframe_title:
        parts.append(f"视频首帧必须以已批准关键帧《{keyframe_title}》为准，人物身份、服装、场景布局和光线不能漂移。")
    else:
        parts.append("视频首帧必须以已批准关键帧为准，人物身份、服装、场景布局和光线不能漂移。")
    return "\n".join(part for part in parts if part)


def _card_prompt_line(prefix: str, card: dict[str, Any]) -> str:
    return "，".join(
        part
        for part in [
            str(card.get("name") or "").strip(),
            str(card.get("description") or "").strip(),
            str(card.get("visual_prompt") or "").strip(),
        ]
        if part
    )


def _selected_clip_shots(
    project: dict[str, Any],
    image_assets: list[dict[str, Any]],
    shot_id: str,
) -> list[tuple[dict[str, Any], dict[str, Any]]]:
    selected = _selected_image_shots(project, shot_id)
    pairs = []
    for shot in selected:
        reference = _approved_image_for_shot(image_assets, str(shot.get("id") or ""))
        if reference:
            pairs.append((shot, reference))
    return pairs


def _task_output_asset(project: dict[str, Any], task_id: str) -> dict[str, Any] | None:
    task = next((item for item in project.get("tasks") or [] if str(item.get("id") or "") == task_id), None)
    asset_id = str((task or {}).get("output_asset_id") or "")
    if not asset_id:
        return None
    return _project_asset(project, asset_id)


def _project_asset(project: dict[str, Any], asset_id: str) -> dict[str, Any] | None:
    return next((asset for asset in project.get("assets") or [] if str(asset.get("id") or "") == str(asset_id)), None)


def _planned_image_prompt(project: dict[str, Any], shot: dict[str, Any]) -> str:
    _asset, draft = _latest_planning_draft(project)
    storyboard = draft.get("storyboard") if draft else []
    if not isinstance(storyboard, list):
        return ""
    shot_position = str(shot.get("position") or "")
    shot_title = str(shot.get("title") or "").strip()
    for item in storyboard:
        if not isinstance(item, dict):
            continue
        if str(item.get("position") or "") == shot_position or str(item.get("title") or "").strip() == shot_title:
            return str(item.get("image_prompt") or item.get("prompt") or "").strip()
    return ""


def _planned_video_prompt(project: dict[str, Any], shot: dict[str, Any]) -> str:
    _asset, draft = _latest_planning_draft(project)
    storyboard = draft.get("storyboard") if draft else []
    if not isinstance(storyboard, list):
        return ""
    shot_position = str(shot.get("position") or "")
    shot_title = str(shot.get("title") or "").strip()
    for item in storyboard:
        if not isinstance(item, dict):
            continue
        if str(item.get("position") or "") == shot_position or str(item.get("title") or "").strip() == shot_title:
            return str(item.get("video_prompt") or item.get("prompt") or "").strip()
    return ""


def _asset_source_media_url(asset: dict[str, Any]) -> str:
    metadata = asset.get("metadata") or {}
    response_file = str(metadata.get("response_file") or "").strip()
    payload = _read_json(Path(response_file)) if response_file else {}
    response = payload.get("response") if isinstance(payload, dict) else {}
    url = _first_url_value(response if isinstance(response, dict) else {})
    return url if url.startswith(("http://", "https://")) else ""


def _first_url_value(value: Any) -> str:
    if isinstance(value, dict):
        for key in ("image", "image_url", "video", "video_url", "media_url", "url"):
            url = str(value.get(key) or "").strip()
            if url.startswith(("http://", "https://")):
                return url
        for item in value.values():
            url = _first_url_value(item)
            if url:
                return url
    if isinstance(value, list):
        for item in value:
            url = _first_url_value(item)
            if url:
                return url
    return ""


def _delete_local_asset_file(store: FilmStore, asset: dict[str, Any]) -> None:
    file_path = str(asset.get("file_path") or "").strip()
    if not file_path:
        return
    path = Path(file_path)
    try:
        resolved = path.resolve()
        data_root = Path(store.data_dir).resolve()
    except OSError:
        return
    try:
        if not resolved.is_relative_to(data_root):
            return
    except ValueError:
        return
    if resolved.is_file():
        try:
            resolved.unlink()
        except OSError:
            pass


def _save_reference_data_url(store: FilmStore, project_id: str, data_url: str, file_name: str) -> Path:
    match = re.match(r"^data:(?P<mime>[-\w.+/]+);base64,(?P<data>.+)$", data_url, flags=re.DOTALL)
    if not match:
        raise ValueError("Reference image must be a data URL.")
    mime_type = match.group("mime")
    if not mime_type.startswith("image/"):
        raise ValueError("Reference file must be an image.")
    try:
        raw = base64.b64decode(match.group("data"), validate=True)
    except ValueError as exc:
        raise ValueError("Reference image data is invalid.") from exc
    suffix = mimetypes.guess_extension(mime_type) or Path(file_name).suffix or ".png"
    safe_stem = re.sub(r"[^A-Za-z0-9._-]+", "-", Path(file_name).stem).strip("-") or "reference"
    output_dir = Path(store.data_dir) / "reference_assets" / project_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{safe_stem}-{uuid4()}{suffix}"
    output_path.write_bytes(raw)
    return output_path


def _write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def _slug(value: str) -> str:
    text = re.sub(r"[^\w\u4e00-\u9fff-]+", "_", value.strip(), flags=re.UNICODE)
    text = re.sub(r"_+", "_", text).strip("_")
    return text[:48]


def _latest_planning_draft(project: dict[str, Any]) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    for asset in project.get("assets") or []:
        metadata = asset.get("metadata") or {}
        if metadata.get("artifact_kind") != "planning_draft":
            continue
        draft = _read_json(Path(str(asset.get("file_path") or "")))
        if draft:
            return asset, draft
    return None, None


def _planning_versions(project: dict[str, Any]) -> list[dict[str, Any]]:
    versions = []
    for asset in project.get("assets") or []:
        metadata = asset.get("metadata") or {}
        if metadata.get("artifact_kind") != "planning_draft":
            continue
        draft = _read_json(Path(str(asset.get("file_path") or ""))) or {}
        versions.append(
            {
                "asset_id": asset.get("id"),
                "title": asset.get("title") or "策划稿",
                "status": metadata.get("review_status") or asset.get("status") or "draft",
                "source": metadata.get("source") or draft.get("source") or "",
                "created_at": asset.get("created_at") or draft.get("updated_at") or "",
                "file_path": asset.get("file_path") or "",
                "storyboard_count": len(draft.get("storyboard") or []),
            }
        )
    return versions[:8]


def _planning_status(asset: dict[str, Any] | None) -> str:
    if not asset:
        return "not_started"
    metadata = asset.get("metadata") or {}
    return str(metadata.get("review_status") or asset.get("status") or "draft")


def _draft_from_project(project: dict[str, Any], *, source: str, extra_brief: str = "") -> dict[str, Any]:
    title = str(project.get("title") or "未命名短片").strip()
    logline = str(project.get("logline") or "").strip()
    shots = list(project.get("shots") or [])
    if not shots:
        shots = _default_storyboard(title=title, logline=logline)
    storyboard = [_planning_item_from_shot(shot, index=index) for index, shot in enumerate(shots, start=1)]
    return {
        "schema": "aifilm-studio.planning-draft.v1",
        "project_id": project.get("id"),
        "title": title,
        "logline": logline,
        "story_outline": _story_outline(title=title, logline=logline, extra_brief=extra_brief),
        "characters": [
            {
                "name": "主角",
                "description": logline or "承载故事目标与行动的人物。",
                "visual_prompt": "原创角色，清晰轮廓，适合连续镜头生成。",
            }
        ],
        "scenes": [
            {
                "name": "核心场景",
                "description": storyboard[0].get("location") or "围绕故事目标展开的主要空间。",
                "visual_prompt": "统一美术风格，具备明确空间层次和可延展细节。",
            }
        ],
        "storyboard": storyboard,
        "source": source,
        "updated_at": utc_now(),
    }


def _generate_planning_draft_with_model(
    store: FilmStore,
    project: dict[str, Any],
    *,
    extra_brief: str,
) -> dict[str, Any] | None:
    slot = _model_slot(store, "planning_model")
    if not slot or not slot.get("enabled", True):
        return None
    provider_id = str(slot.get("provider_id") or "").strip()
    model = str(slot.get("model") or "").strip()
    if not provider_id or provider_id == "mock-local" or not model:
        return None
    provider = provider_with_slot_settings(store.get_provider(provider_id), slot)
    task = {
        "id": f"planning-{uuid4()}",
        "project_id": project["id"],
        "shot_id": None,
        "stage": "script",
        "provider_id": provider_id,
        "model": model,
        "model_slot": "planning_model",
        "model_role": "planning",
        "prompt": _planning_model_prompt(project, extra_brief=extra_brief),
        "system_prompt": "你是专业短片编剧和 AI 视频生成策划，只返回严格 JSON，不要 Markdown。",
        "response_format": {"type": "json_object"},
        "temperature": 0.45,
        "max_tokens": 1600,
        "cost_estimate": 0,
    }
    try:
        result = run_provider_task(store=store, task=task, provider=provider)
    except ProviderAdapterError:
        raise
    output = _read_json(result.output_file) or {}
    parsed = _parse_json_object(output.get("content"))
    if not parsed:
        raise ProviderAdapterError("Planning model did not return a JSON planning draft.")
    draft = _normalize_planning_draft(parsed, project=project)
    draft["source"] = f"planning_model:{provider_id}:{model}"
    return _save_planning_draft(
        store,
        str(project["id"]),
        draft,
        review_status="draft",
        source=f"planning_model:{provider_id}:{model}",
        provider=provider_id,
        model=model,
        request_ref=str(task["prompt"]),
        response_ref=str(result.output_file),
    )


def _model_slot(store: FilmStore, slot_key: str) -> dict[str, Any] | None:
    slots = store.get_model_pipeline_config().get("slots") or []
    for slot in slots:
        if isinstance(slot, dict) and str(slot.get("slot_key") or "") == slot_key:
            return slot
    return None


def _planning_model_prompt(project: dict[str, Any], *, extra_brief: str) -> str:
    title = str(project.get("title") or "5秒爱情镜头").strip()
    logline = str(project.get("logline") or "").strip()
    brief = extra_brief or logline or "单个场景，5秒，一个简单爱情故事镜头。"
    return (
        "请为 FilmGen Studio 生成一个可直接进入文生图和图生视频阶段的结构化策划稿。\n"
        "硬性要求：恰好 1 个场景、恰好 1 个分镜、总时长 5 秒、简单爱情故事、无品牌商标、无真人名人肖像。\n"
        "镜头要适合先生成一张关键帧图片，再用该图片和视频 prompt 生成 5 秒视频。\n"
        f"项目标题：{title}\n"
        f"一句话/补充要求：{brief}\n"
        "只返回 JSON，格式如下：\n"
        "{\n"
        '  "title": "片名",\n'
        '  "logline": "一句话故事",\n'
        '  "story_outline": "简短故事方向",\n'
        '  "characters": [{"name": "角色名", "description": "角色说明", "visual_prompt": "人物视觉提示词"}],\n'
        '  "scenes": [{"name": "场景名", "description": "场景说明", "visual_prompt": "场景视觉提示词"}],\n'
        '  "storyboard": [{\n'
        '    "position": 1,\n'
        '    "title": "镜头标题",\n'
        '    "summary": "画面摘要",\n'
        '    "duration_seconds": 5,\n'
        '    "location": "单个场景地点",\n'
        '    "camera": "景别、机位和运动",\n'
        '    "image_prompt": "用于文生图的中文提示词",\n'
        '    "video_prompt": "用于图生视频的中文提示词，明确 5 秒动作和镜头运动",\n'
        '    "status": "draft"\n'
        "  }]\n"
        "}"
    )


def _default_storyboard(*, title: str, logline: str) -> list[dict[str, Any]]:
    seed = logline or title or "一个短片创意"
    return [
        {
            "position": 1,
            "title": "开场建立",
            "summary": f"用一个清晰画面建立主题：{seed}",
            "duration_seconds": 5,
            "location": "主场景",
            "camera": "稳定推进",
            "prompt": f"{seed}，开场建立镜头，主体清楚，氛围统一",
        },
        {
            "position": 2,
            "title": "行动推进",
            "summary": "展示角色动作、目标和关键变化。",
            "duration_seconds": 6,
            "location": "主场景",
            "camera": "中景跟拍",
            "prompt": f"{seed}，角色行动，镜头连贯，细节明确",
        },
        {
            "position": 3,
            "title": "结果收束",
            "summary": "保留一个能进入剪辑装配的结果画面。",
            "duration_seconds": 5,
            "location": "主场景",
            "camera": "定格或缓慢拉远",
            "prompt": f"{seed}，结果画面，构图稳定，适合收尾",
        },
    ]


def _story_outline(*, title: str, logline: str, extra_brief: str) -> str:
    parts = [
        f"《{title}》围绕一句话创意展开。",
        logline,
        extra_brief,
        "策划稿需要先保证故事方向、角色、场景和镜头意图清楚，再进入图片和视频生成。",
    ]
    return "\n".join(part for part in parts if part)


def _planning_item_from_shot(shot: dict[str, Any], *, index: int) -> dict[str, Any]:
    title = str(shot.get("title") or f"镜头 {index}").strip()
    summary = str(shot.get("summary") or "").strip()
    prompt = str(shot.get("prompt") or "").strip()
    return {
        "position": int(shot.get("position") or index),
        "title": title,
        "summary": summary,
        "duration_seconds": int(shot.get("duration_seconds") or 5),
        "location": str(shot.get("location") or "").strip(),
        "camera": str(shot.get("camera") or "").strip(),
        "image_prompt": prompt,
        "video_prompt": prompt,
        "prompt": prompt,
        "status": str(shot.get("status") or "draft").strip() or "draft",
    }


def _normalize_planning_draft(value: Any, *, project: dict[str, Any]) -> dict[str, Any]:
    source = value if isinstance(value, dict) else {}
    draft = _draft_from_project(project, source=str(source.get("source") or "manual_edit"))
    for key in ("title", "logline", "story_outline"):
        if key in source:
            draft[key] = str(source.get(key) or "").strip()
    draft["characters"] = _normalize_cards(source.get("characters"), fallback=draft["characters"])
    draft["scenes"] = _normalize_cards(source.get("scenes"), fallback=draft["scenes"])
    draft["storyboard"] = _normalize_storyboard(source.get("storyboard"), fallback=draft["storyboard"])
    draft["updated_at"] = utc_now()
    return draft


def _normalize_cards(value: Any, *, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return fallback
    cards = []
    for index, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            continue
        cards.append(
            {
                "name": str(item.get("name") or f"条目 {index}").strip(),
                "description": str(item.get("description") or "").strip(),
                "visual_prompt": str(item.get("visual_prompt") or item.get("prompt") or "").strip(),
            }
        )
    return cards or fallback


def _normalize_storyboard(value: Any, *, fallback: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return fallback
    shots = []
    for index, item in enumerate(value, start=1):
        if isinstance(item, dict):
            shots.append(_shot_from_planning_item({**item, "position": item.get("position") or index}))
    return shots or fallback


def _storyboard_index(storyboard: list[dict[str, Any]], position: int) -> int | None:
    for index, item in enumerate(storyboard):
        try:
            item_position = int(item.get("position") or index + 1)
        except (TypeError, ValueError):
            item_position = index + 1
        if item_position == position:
            return index
    if 1 <= position <= len(storyboard):
        return position - 1
    return None


def _regenerated_planning_item(item: dict[str, Any], *, issue: str, project: dict[str, Any]) -> dict[str, Any]:
    label, suggestion = PLANNING_ISSUE_HINTS.get(issue, PLANNING_ISSUE_HINTS["story_off"])
    title = str(item.get("title") or "镜头").strip()
    summary = str(item.get("summary") or "").strip()
    base_prompt = str(item.get("video_prompt") or item.get("prompt") or item.get("image_prompt") or "").strip()
    logline = str(project.get("logline") or project.get("title") or "").strip()
    return {
        **item,
        "title": title if f"已优化" in title else f"{title}（已优化）",
        "summary": "；".join(part for part in [summary, f"针对“{label}”调整：{suggestion}"] if part),
        "image_prompt": "，".join(
            part
            for part in [
                str(item.get("image_prompt") or base_prompt).strip(),
                "角色、场景和构图信息更明确",
                logline,
            ]
            if part
        ),
        "video_prompt": "，".join(
            part
            for part in [
                base_prompt,
                suggestion,
                "镜头动作和画面目标清晰",
            ]
            if part
        ),
        "prompt": "，".join(part for part in [base_prompt, suggestion] if part),
        "status": "needs_review",
        "review_note": label,
    }


def _shot_from_planning_item(item: dict[str, Any]) -> dict[str, Any]:
    prompt = str(item.get("video_prompt") or item.get("prompt") or item.get("image_prompt") or "").strip()
    return {
        "position": int(item.get("position") or 1),
        "title": str(item.get("title") or "镜头").strip(),
        "summary": str(item.get("summary") or "").strip(),
        "duration_seconds": int(item.get("duration_seconds") or 5),
        "location": str(item.get("location") or "").strip(),
        "camera": str(item.get("camera") or "").strip(),
        "image_prompt": str(item.get("image_prompt") or prompt).strip(),
        "video_prompt": prompt,
        "prompt": prompt,
        "status": str(item.get("status") or "approved").strip() or "approved",
    }


def _save_planning_draft(
    store: FilmStore,
    project_id: str,
    draft: dict[str, Any],
    *,
    review_status: str,
    source: str,
    provider: str = "mock-local",
    model: str = "planning_model",
    request_ref: str = "",
    response_ref: str = "",
) -> dict[str, Any]:
    output_dir = store.data_dir / "planning" / project_id
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"planning-{utc_now().replace(':', '')}-{review_status}-{uuid4().hex[:8]}.json"
    payload = {
        **draft,
        "review_status": review_status,
        "source": source,
        "updated_at": utc_now(),
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    store.create_asset(
        project_id,
        {
            "type": "script",
            "title": f"策划稿 {review_status}",
            "file_path": str(output_path),
            "status": review_status,
            "provider": provider,
            "model": model,
            "prompt": request_ref or payload.get("logline") or "",
            "metadata": {
                "artifact_kind": "planning_draft",
                "review_status": review_status,
                "source": source,
                "model_slot": "planning_model",
                "response_ref": response_ref,
            },
        },
    )
    return get_planning_review_state(store, project_id)


def _parse_json_object(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    text = str(value or "").strip()
    if not text:
        return None
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        start = text.find("{")
        end = text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            parsed = json.loads(text[start : end + 1])
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _read_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None
