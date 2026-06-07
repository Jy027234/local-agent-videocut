from __future__ import annotations

import copy
from typing import Any, Mapping

from smart_video_cut.timeline_model import (
    SOURCE_SELECTION_POLICY_DEFAULT,
    TIMELINE_SCHEMA,
    TRANSITION_POLICY_DEFAULT,
    TimelinePlan,
    TimelineSegment,
)


# Default segment blueprint when no timeline_template is in style package.
DEFAULT_SEGMENT_BLUEPRINT: list[dict[str, Any]] = [
    {"role": "opening_hero", "duration_seconds": 2.2, "shot_intent": "wide_product_hero", "caption": "cover"},
    {"role": "product_body_and_detail", "duration_seconds": 1.4, "shot_intent": "door_body", "caption": ""},
    {"role": "product_body_and_detail", "duration_seconds": 1.2, "shot_intent": "product_detail", "caption": ""},
    {"role": "product_body_and_detail", "duration_seconds": 1.4, "shot_intent": "door_body", "caption": ""},
    {"role": "site_context", "duration_seconds": 1.6, "shot_intent": "corridor_context", "caption": ""},
    {"role": "site_context", "duration_seconds": 1.5, "shot_intent": "corridor_context", "caption": ""},
    {"role": "product_body_and_detail", "duration_seconds": 1.4, "shot_intent": "overall_door", "caption": ""},
    {"role": "product_body_and_detail", "duration_seconds": 1.2, "shot_intent": "product_detail", "caption": ""},
    {"role": "product_body_and_detail", "duration_seconds": 1.5, "shot_intent": "overall_door", "caption": ""},
    {"role": "product_body_and_detail", "duration_seconds": 1.5, "shot_intent": "overall_door", "caption": ""},
    {"role": "product_body_and_detail", "duration_seconds": 1.3, "shot_intent": "door_body", "caption": ""},
    {"role": "product_body_and_detail", "duration_seconds": 0.0, "shot_intent": "overall_door", "caption": "final_hold"},
]


def build_timeline_plan(
    *,
    material_plan: Mapping[str, Any],
    settings: Mapping[str, Any],
    style_package: Mapping[str, Any],
    timeline_kind: str = "advertising_flash_montage",
) -> TimelinePlan:
    """Build a dynamic TimelinePlan from material_plan + style_package settings."""

    video_settings = settings.get("video", {}) if isinstance(settings, Mapping) else {}
    target_duration = int(video_settings.get("target_duration_seconds", 20))

    # Prefer timeline_template from style package, else use default blueprint
    template = style_package.get("timeline_template") if isinstance(style_package, Mapping) else None
    if isinstance(template, Mapping) and template.get("segment_blueprint"):
        blueprint = list(template["segment_blueprint"])
        transition_policy = template.get("transition_policy", dict(TRANSITION_POLICY_DEFAULT))
        source_policy = template.get("source_selection_policy", dict(SOURCE_SELECTION_POLICY_DEFAULT))
        kind = str(template.get("timeline_kind", timeline_kind))
    else:
        blueprint = list(DEFAULT_SEGMENT_BLUEPRINT)
        transition_policy = dict(TRANSITION_POLICY_DEFAULT)
        source_policy = dict(SOURCE_SELECTION_POLICY_DEFAULT)
        kind = timeline_kind

    # Build role → material index mapping from material_plan
    role_source_map = material_plan.get("role_source_map") or {}
    materials = material_plan.get("materials") or []

    durations = _segment_durations(blueprint=blueprint, target_duration=target_duration)

    # Generate segments from blueprint
    segments: list[TimelineSegment] = []
    current_time = 0.0
    for i, (item, duration) in enumerate(zip(blueprint, durations, strict=False)):
        role = str(item.get("role", "product_body_and_detail"))
        shot_intent = str(item.get("shot_intent", role))
        caption = str(item.get("caption", ""))
        source_index = _resolve_source_index(role, role_source_map, materials, i)
        source_file = ""
        if source_index is not None and source_index < len(materials):
            source_file = str(materials[source_index].get("path", ""))
            thumbnail_path = _material_thumbnail_path(materials[source_index])
        else:
            thumbnail_path = ""

        segment_id = f"seg_{i+1:03d}_{shot_intent}"
        segment = TimelineSegment(
            segment_id=segment_id,
            timeline_start_seconds=round(current_time, 3),
            duration_seconds=round(duration, 3),
            shot_intent=shot_intent,
            source_material_index=source_index,
            source_file=source_file,
            thumbnail_path=thumbnail_path,
            caption=caption,
        )
        segments.append(segment)
        current_time += duration

    plan = TimelinePlan(
        target_duration_seconds=target_duration,
        timeline_kind=kind,
        segments=segments,
        transition_policy=transition_policy,
        source_selection_policy=source_policy,
        version=1,
    )
    plan.recompute_start_times()
    return plan


def apply_user_edits(
    *,
    base_timeline: TimelinePlan,
    edits: list[dict[str, Any]],
) -> TimelinePlan:
    """Apply user edit operations and return a new version of the timeline."""

    new_data = copy.deepcopy(base_timeline.to_dict())
    new_plan = TimelinePlan.from_dict(new_data)

    for edit in edits:
        op = str(edit.get("op", ""))
        segment_id = str(edit.get("segment_id", ""))

        if op == "delete":
            new_plan.segments = [s for s in new_plan.segments if s.segment_id != segment_id]

        elif op == "move":
            new_position = edit.get("new_position")
            if new_position is not None:
                seg = next((s for s in new_plan.segments if s.segment_id == segment_id), None)
                if seg:
                    new_plan.segments = [s for s in new_plan.segments if s.segment_id != segment_id]
                    insert_at = max(0, min(int(new_position), len(new_plan.segments)))
                    new_plan.segments.insert(insert_at, seg)

        elif op == "resize":
            new_duration = edit.get("duration_seconds")
            if new_duration is not None:
                seg = new_plan.segment_by_id(segment_id)
                if seg:
                    seg.duration_seconds = max(0.3, float(new_duration))

        elif op == "replace_source":
            new_source = edit.get("source_material_index")
            new_file = edit.get("source_file", "")
            new_thumbnail = edit.get("thumbnail_path")
            if new_source is not None:
                seg = new_plan.segment_by_id(segment_id)
                if seg:
                    seg.source_material_index = int(new_source)
                    if new_file:
                        seg.source_file = str(new_file)
                    if new_thumbnail is not None:
                        seg.thumbnail_path = str(new_thumbnail)

        elif op == "update_caption":
            caption = str(edit.get("caption", ""))
            seg = new_plan.segment_by_id(segment_id)
            if seg:
                seg.caption = caption

        elif op == "insert":
            new_seg_data = edit.get("segment", {})
            if isinstance(new_seg_data, dict):
                position = int(edit.get("position", len(new_plan.segments)))
                new_seg = TimelineSegment.from_dict(new_seg_data)
                insert_at = max(0, min(position, len(new_plan.segments)))
                new_plan.segments.insert(insert_at, new_seg)

    new_plan.recompute_start_times()
    new_plan.version = base_timeline.version + 1
    new_plan.parent_version = base_timeline.version
    return new_plan


def timeline_to_toolkit_format(timeline_plan: TimelinePlan) -> dict[str, Any]:
    """Convert TimelinePlan to the format expected by creative_edit_runner._timeline_plan()."""

    segments = []
    for seg in timeline_plan.segments:
        segments.append({
            "segment_id": seg.segment_id,
            "timeline_start_seconds": round(seg.timeline_start_seconds, 3),
            "duration_seconds": round(seg.duration_seconds, 3),
            "shot_intent": seg.shot_intent,
            "onscreen_text_policy": seg.onscreen_text_policy,
        })

    return {
        "schema": "video_editing_toolkit.creative_edit_timeline.v0",
        "contract": "creative_edit_timeline.v0",
        "target_duration_seconds": timeline_plan.target_duration_seconds,
        "timeline_kind": timeline_plan.timeline_kind,
        "source_selection_policy": timeline_plan.source_selection_policy,
        "segments": segments,
        "transition_policy": timeline_plan.transition_policy,
    }


def _segment_durations(*, blueprint: list[dict[str, Any]], target_duration: int) -> list[float]:
    if not blueprint:
        return []

    raw_durations: list[float] = []
    used_duration = 0.0
    for i, item in enumerate(blueprint):
        duration = float(item.get("duration_seconds", 1.4))
        if i == len(blueprint) - 1 and duration <= 0:
            duration = max(0.5, target_duration - used_duration)
        duration = max(0.1, duration)
        raw_durations.append(duration)
        used_duration += duration

    total_duration = sum(raw_durations)
    if target_duration > 0 and total_duration > target_duration:
        scale = target_duration / total_duration
        scaled = [max(0.1, round(duration * scale, 3)) for duration in raw_durations]
        adjusted_total = round(sum(scaled), 3)
        scaled[-1] = round(max(0.1, scaled[-1] + (target_duration - adjusted_total)), 3)
        return scaled

    return [round(duration, 3) for duration in raw_durations]


def _resolve_source_index(
    role: str,
    role_source_map: Mapping[str, Any],
    materials: list[Any],
    fallback_index: int,
) -> int | None:
    # Direct role match in role_source_map
    if role in role_source_map:
        try:
            return int(role_source_map[role])
        except (TypeError, ValueError):
            pass
    # Try shot_intent aliases
    aliases = {
        "opening_hero": ("overall_door", "cover", "final_hold"),
        "product_body_and_detail": ("door_body", "detail", "product_detail"),
        "site_context": ("corridor", "site_context"),
    }
    for alias in aliases.get(role, ()):
        if alias in role_source_map:
            try:
                return int(role_source_map[alias])
            except (TypeError, ValueError):
                pass
    return fallback_index % max(1, len(materials))


def _material_thumbnail_path(material: Any) -> str:
    if not isinstance(material, Mapping):
        return ""
    direct = str(material.get("thumbnail_path") or "").strip()
    if direct:
        return direct
    profile = material.get("visual_profile")
    if not isinstance(profile, Mapping):
        return ""
    refs = profile.get("thumbnail_refs")
    if not isinstance(refs, list):
        return ""
    for ref in refs:
        if isinstance(ref, Mapping):
            path = str(ref.get("thumbnail_path") or "").strip()
            if path:
                return path
    return ""
