from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


TIMELINE_SCHEMA = "smart_video_cut.local.timeline.v1"
TIMELINE_SEGMENT_SCHEMA = "smart_video_cut.local.timeline_segment.v1"

TRANSITION_POLICY_DEFAULT: dict[str, Any] = {
    "style": "hard_cuts_with_light_flash_accents",
    "max_single_shot_seconds": 4.0,
}

SOURCE_SELECTION_POLICY_DEFAULT: dict[str, Any] = {
    "prefer": ["door_front", "lock_or_hardware_detail", "door_frame", "site_context"],
    "avoid": ["blank_wall_closeup", "dark_unreadable_surface", "long_static_repetition"],
}


@dataclass(slots=True)
class TimelineSegment:
    """A single clip segment on the card-style timeline."""

    segment_id: str
    timeline_start_seconds: float
    duration_seconds: float
    shot_intent: str
    onscreen_text_policy: str = "use_existing_locked_text_family"
    source_material_index: int | None = None
    source_file: str = ""
    thumbnail_path: str = ""
    caption: str = ""
    locked: bool = False

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TimelineSegment:
        valid_fields = {f.name for f in cls.__dataclass_fields__.values()}
        filtered = {k: v for k, v in data.items() if k in valid_fields}
        return cls(**filtered)


@dataclass(slots=True)
class TimelinePlan:
    """A complete card-style timeline plan with version tracking."""

    target_duration_seconds: int = 20
    timeline_kind: str = "advertising_flash_montage"
    segments: list[TimelineSegment] = field(default_factory=list)
    transition_policy: dict[str, Any] = field(default_factory=lambda: dict(TRANSITION_POLICY_DEFAULT))
    source_selection_policy: dict[str, Any] = field(default_factory=lambda: dict(SOURCE_SELECTION_POLICY_DEFAULT))
    version: int = 1
    parent_version: int | None = None
    schema: str = TIMELINE_SCHEMA

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "target_duration_seconds": self.target_duration_seconds,
            "timeline_kind": self.timeline_kind,
            "segments": [s.to_dict() for s in self.segments],
            "transition_policy": self.transition_policy,
            "source_selection_policy": self.source_selection_policy,
            "version": self.version,
            "parent_version": self.parent_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TimelinePlan:
        segments_data = data.get("segments") or []
        segments = [
            TimelineSegment.from_dict(s) if isinstance(s, dict) else s
            for s in segments_data
        ]
        return cls(
            target_duration_seconds=int(data.get("target_duration_seconds", 20)),
            timeline_kind=str(data.get("timeline_kind", "advertising_flash_montage")),
            segments=segments,
            transition_policy=data.get("transition_policy") or dict(TRANSITION_POLICY_DEFAULT),
            source_selection_policy=data.get("source_selection_policy") or dict(SOURCE_SELECTION_POLICY_DEFAULT),
            version=int(data.get("version", 1)),
            parent_version=data.get("parent_version"),
            schema=str(data.get("schema", TIMELINE_SCHEMA)),
        )

    def total_duration(self) -> float:
        return sum(s.duration_seconds for s in self.segments)

    def segment_by_id(self, segment_id: str) -> TimelineSegment | None:
        return next((s for s in self.segments if s.segment_id == segment_id), None)

    def recompute_start_times(self) -> None:
        """Recalculate timeline_start_seconds so segments are contiguous."""
        current = 0.0
        for segment in self.segments:
            segment.timeline_start_seconds = round(current, 3)
            current += segment.duration_seconds

    def validate(self) -> list[str]:
        """Return a list of validation error messages (empty if valid)."""
        errors: list[str] = []
        if not self.segments:
            errors.append("timeline_has_no_segments")
        total = self.total_duration()
        if total > self.target_duration_seconds + 1.0:
            errors.append(
                f"total_duration_{total:.1f}_exceeds_target_{self.target_duration_seconds}"
            )
        if total < self.target_duration_seconds * 0.3:
            errors.append(
                f"total_duration_{total:.1f}_too_short_for_target_{self.target_duration_seconds}"
            )
        seen_ids: set[str] = set()
        for segment in self.segments:
            if segment.segment_id in seen_ids:
                errors.append(f"duplicate_segment_id_{segment.segment_id}")
            seen_ids.add(segment.segment_id)
            if segment.duration_seconds <= 0:
                errors.append(f"segment_{segment.segment_id}_has_non_positive_duration")
        return errors
