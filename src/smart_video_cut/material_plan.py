from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from smart_video_cut.material_analysis import analyze_material_visual_profiles
from smart_video_cut.material_multimodal import review_material_roles_with_multimodal


ROLE_TEMPLATES = (
    {
        "primary_role": "opening_hero",
        "display_role": "开头封面 / 主体全貌 / 结尾定格",
        "shot_kinds": ("overall_door", "cover", "final_hold"),
    },
    {
        "primary_role": "product_body_and_detail",
        "display_role": "门体主体 / 锁具五金 / 快闪细节",
        "shot_kinds": ("door_body", "detail"),
    },
    {
        "primary_role": "site_context",
        "display_role": "现场环境 / 过渡镜头 / 空间关系",
        "shot_kinds": ("corridor", "site_context"),
    },
    {
        "primary_role": "alternate_cutaway",
        "display_role": "补充细节 / 节奏切片 / 备用镜头",
        "shot_kinds": ("alternate",),
    },
)


def build_material_plan(
    paths: list[str | Path],
    *,
    visual_profiles: list[Mapping[str, Any]] | None = None,
    multimodal_review: Mapping[str, Any] | None = None,
    enable_visual_analysis: bool = True,
    enable_multimodal_review: bool = True,
    visual_tuning: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    unique_paths = _unique_paths(paths)
    profiles = _visual_profiles(unique_paths, visual_profiles, enable_visual_analysis=enable_visual_analysis)
    review = _multimodal_review(
        unique_paths,
        profiles,
        multimodal_review,
        enable_multimodal_review=enable_multimodal_review,
    )
    role_assignments = _role_assignments(unique_paths, profiles, review)
    materials = []
    role_source_map: dict[str, int] = {}
    for index, path in enumerate(unique_paths):
        template = _template_for_role(role_assignments["index_to_role"].get(index), index)
        profile = profiles[index] if index < len(profiles) else {}
        material = {
            "index": index,
            "path": str(path),
            "label": path.name,
            "primary_role": template["primary_role"],
            "display_role": template["display_role"],
            "recommended_shot_kinds": list(template["shot_kinds"]),
            "assignment_source": role_assignments["strategy"],
            "assignment_reason": _assignment_reason(
                template,
                profile,
                role_assignments["strategy"],
                role_assignments.get("index_reasons", {}).get(index),
            ),
        }
        if profile:
            material["visual_profile"] = _public_profile(profile)
        materials.append(material)
        for shot_kind in template["shot_kinds"]:
            role_source_map.setdefault(str(shot_kind), index)
    if unique_paths:
        role_source_map.setdefault("overall_door", 0)
        role_source_map.setdefault("cover", 0)
        role_source_map.setdefault("final_hold", 0)
        role_source_map.setdefault("door_body", min(1, len(unique_paths) - 1))
        role_source_map.setdefault("detail", min(1, len(unique_paths) - 1))
        role_source_map.setdefault("corridor", min(2, len(unique_paths) - 1))
        role_source_map.setdefault("site_context", min(2, len(unique_paths) - 1))
    return {
        "schema": "smart_video_cut.local.material_plan.v0",
        "strategy": role_assignments["strategy"],
        "material_count": len(unique_paths),
        "materials": materials,
        "role_source_map": role_source_map,
        "visual_analysis": {
            "available": any(profile.get("analysis_ready") is True for profile in profiles),
            "profiles_ready": sum(1 for profile in profiles if profile.get("analysis_ready") is True),
            "tuning": dict(visual_tuning or {}),
            "profiles": [_public_profile(profile) for profile in profiles],
        },
        "multimodal_review": _public_multimodal_review(review),
        "note": _plan_note(role_assignments["strategy"]),
    }


def _unique_paths(paths: list[str | Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[str] = set()
    for value in paths:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        unique.append(Path(text))
    return unique


def _visual_profiles(
    paths: list[Path],
    visual_profiles: list[Mapping[str, Any]] | None,
    *,
    enable_visual_analysis: bool,
) -> list[dict[str, Any]]:
    if visual_profiles is not None:
        return [dict(profile) for profile in visual_profiles]
    if not enable_visual_analysis or not paths:
        return []
    return analyze_material_visual_profiles(paths)


def _multimodal_review(
    paths: list[Path],
    profiles: list[Mapping[str, Any]],
    multimodal_review: Mapping[str, Any] | None,
    *,
    enable_multimodal_review: bool,
) -> dict[str, Any]:
    if multimodal_review is not None:
        return dict(multimodal_review)
    if not enable_multimodal_review or not paths:
        return {"ok": False, "status": "skipped", "skipped_reason": "disabled"}
    return review_material_roles_with_multimodal(paths=paths, visual_profiles=profiles)


def _role_assignments(
    paths: list[Path],
    profiles: list[Mapping[str, Any]],
    multimodal_review: Mapping[str, Any],
) -> dict[str, Any]:
    local_assignments = _local_role_assignments(paths, profiles)
    review_assignments = _assignments_from_multimodal_review(paths, multimodal_review, local_assignments)
    if review_assignments:
        return review_assignments
    return local_assignments


def _local_role_assignments(paths: list[Path], profiles: list[Mapping[str, Any]]) -> dict[str, Any]:
    path_count = len(paths)
    ready_profiles = [profile for profile in profiles if profile.get("analysis_ready") is True]
    if path_count == 0:
        return {"strategy": "empty_material_plan", "index_to_role": {}, "index_reasons": {}}
    if len(ready_profiles) < min(2, path_count):
        return {
            "strategy": "order_fallback_role_assignment",
            "index_to_role": {
                index: ROLE_TEMPLATES[min(index, len(ROLE_TEMPLATES) - 1)]["primary_role"]
                for index in range(path_count)
            },
            "index_reasons": {},
        }
    available = list(range(path_count))
    index_to_role: dict[int, str] = {}
    opening_index = _best_index_for_role("opening_hero", profiles, available, default=0)
    index_to_role[opening_index] = "opening_hero"
    available = [index for index in available if index != opening_index] or list(range(path_count))
    detail_index = _best_index_for_role("product_body_and_detail", profiles, available, default=min(1, path_count - 1))
    index_to_role[detail_index] = "product_body_and_detail"
    available = [index for index in available if index != detail_index] or list(range(path_count))
    context_index = _best_index_for_role("site_context", profiles, available, default=min(2, path_count - 1))
    index_to_role[context_index] = "site_context"
    for index in range(path_count):
        index_to_role.setdefault(index, "alternate_cutaway")
    return {
        "strategy": "ffmpeg_frame_probe_role_assignment",
        "index_to_role": index_to_role,
        "index_reasons": {},
    }


def _assignments_from_multimodal_review(
    paths: list[Path],
    multimodal_review: Mapping[str, Any],
    local_assignments: Mapping[str, Any],
) -> dict[str, Any] | None:
    assignments = multimodal_review.get("assignments")
    if multimodal_review.get("ok") is not True or not isinstance(assignments, list):
        return None
    material_count = len(paths)
    local_index_to_role = local_assignments.get("index_to_role")
    if not isinstance(local_index_to_role, Mapping):
        local_index_to_role = {}
    role_to_best: dict[str, dict[str, Any]] = {}
    index_reasons: dict[int, str] = {}
    for item in assignments:
        if not isinstance(item, Mapping):
            continue
        try:
            index = int(item.get("index"))
        except (TypeError, ValueError):
            continue
        if index < 0 or index >= material_count:
            continue
        role = str(item.get("role") or "")
        if role not in {"opening_hero", "product_body_and_detail", "site_context", "alternate_cutaway"}:
            continue
        confidence = _safe_score(item.get("confidence"))
        current = role_to_best.get(role)
        if current is None or confidence > _safe_score(current.get("confidence")):
            role_to_best[role] = {
                "index": index,
                "confidence": confidence,
                "reason": str(item.get("reason") or "").strip(),
            }

    index_to_role: dict[int, str] = {}
    used: set[int] = set()
    for role in ("opening_hero", "product_body_and_detail", "site_context"):
        selected = role_to_best.get(role)
        if selected and selected["index"] not in used:
            index = int(selected["index"])
            index_to_role[index] = role
            used.add(index)
            index_reasons[index] = _multimodal_reason(role, selected)
            continue
        fallback_index = _first_local_index_for_role(local_index_to_role, role, material_count, used)
        if fallback_index is not None:
            index_to_role[fallback_index] = role
            used.add(fallback_index)
            index_reasons[fallback_index] = "多模态复核未给出该角色的唯一素材，使用本地视觉分析补位。"

    for index in range(material_count):
        if index in index_to_role:
            continue
        index_to_role[index] = "alternate_cutaway"
        matching = next(
            (
                item
                for item in assignments
                if isinstance(item, Mapping)
                and _safe_int(item.get("index")) == index
                and str(item.get("reason") or "").strip()
            ),
            None,
        )
        if matching:
            index_reasons[index] = f"多模态复核：{str(matching.get('reason')).strip()}"
    return {
        "strategy": "multimodal_thumbnail_role_review",
        "index_to_role": index_to_role,
        "index_reasons": index_reasons,
    }


def _best_index_for_role(
    role: str,
    profiles: list[Mapping[str, Any]],
    available: list[int],
    *,
    default: int,
) -> int:
    best_index = max(0, min(default, max(0, len(profiles) - 1)))
    best_score = -1.0
    for index in available:
        if index >= len(profiles) or profiles[index].get("analysis_ready") is not True:
            continue
        scores = profiles[index].get("scores")
        if not isinstance(scores, Mapping):
            continue
        score = _safe_score(scores.get(role))
        # Tiny order bias makes ties deterministic and keeps user order meaningful.
        score -= index * 0.0001
        if score > best_score:
            best_score = score
            best_index = index
    return best_index


def _template_for_role(role: str | None, index: int) -> Mapping[str, Any]:
    if role:
        for template in ROLE_TEMPLATES:
            if template["primary_role"] == role:
                return template
    return ROLE_TEMPLATES[min(index, len(ROLE_TEMPLATES) - 1)]


def _public_profile(profile: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {
        "schema",
        "index",
        "label",
        "analysis_method",
        "analysis_ready",
        "frames_sampled",
        "thumbnail_refs",
        "probe",
        "metrics",
        "scores",
        "reason",
        "failure_reason",
    }
    return {key: value for key, value in profile.items() if key in allowed}


def _public_multimodal_review(review: Mapping[str, Any]) -> dict[str, Any]:
    allowed = {
        "schema",
        "ok",
        "status",
        "skipped_reason",
        "failure_reason",
        "provider",
        "model",
        "elapsed_ms",
        "assignments",
        "response_summary",
        "allow_media_upload_to_llm",
    }
    return {key: value for key, value in review.items() if key in allowed}


def _assignment_reason(
    template: Mapping[str, Any],
    profile: Mapping[str, Any],
    strategy: str,
    assigned_reason: Any = None,
) -> str:
    role = str(template.get("primary_role") or "")
    labels = {
        "opening_hero": "用于开头/全貌，因为该素材在全貌构图评分中更适合承担主视觉",
        "product_body_and_detail": "用于主体/细节，因为该素材在边缘、中心对比等细节指标中更适合做产品镜头",
        "site_context": "用于环境/过渡，因为该素材更适合补充空间关系和转场节奏",
        "alternate_cutaway": "用于补充镜头，作为节奏切片或备用素材",
    }
    if strategy == "multimodal_thumbnail_role_review":
        reason = str(assigned_reason or "").strip()
        return reason or "根据抽帧缩略图经多模态模型复核后确定该素材分工。"
    if strategy != "ffmpeg_frame_probe_role_assignment":
        return "抽帧分析不可用，按用户添加顺序规划。"
    if profile.get("analysis_ready") is not True:
        reason = str(profile.get("failure_reason") or "visual_analysis_unavailable")
        return f"该素材抽帧分析不可用，原因：{reason}。"
    scores = profile.get("scores")
    if isinstance(scores, Mapping):
        score = _safe_score(scores.get(role))
        return f"{labels.get(role, '按视觉特征规划')}，本角色评分 {score:.2f}。"
    return labels.get(role, "按视觉特征规划。")


def _plan_note(strategy: str) -> str:
    if strategy == "multimodal_thumbnail_role_review":
        return "已使用本地抽帧缩略图和多模态模型复核规划素材角色；仅在用户允许上传抽帧/截图时启用。"
    if strategy == "ffmpeg_frame_probe_role_assignment":
        return "已使用本地 FFmpeg 抽帧视觉分析规划素材角色；后续可接多模态模型进一步识别门体、锁具和环境。"
    if strategy == "empty_material_plan":
        return "未选择可规划素材。"
    return "当前素材无法完成抽帧分析，已回退为按素材添加顺序规划。"


def _safe_score(value: Any) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return -1


def _first_local_index_for_role(
    local_index_to_role: Mapping[Any, Any],
    role: str,
    material_count: int,
    used: set[int],
) -> int | None:
    for raw_index, raw_role in local_index_to_role.items():
        try:
            index = int(raw_index)
        except (TypeError, ValueError):
            continue
        if 0 <= index < material_count and index not in used and raw_role == role:
            return index
    for index in range(material_count):
        if index not in used:
            return index
    return None


def _multimodal_reason(role: str, selected: Mapping[str, Any]) -> str:
    labels = {
        "opening_hero": "开头/全貌",
        "product_body_and_detail": "主体/细节",
        "site_context": "环境/过渡",
    }
    reason = str(selected.get("reason") or "").strip()
    confidence = _safe_score(selected.get("confidence"))
    prefix = f"多模态复核建议用于{labels.get(role, role)}，置信度 {confidence:.2f}"
    return f"{prefix}；{reason}" if reason else f"{prefix}。"
