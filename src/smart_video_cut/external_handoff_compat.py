from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

# Legacy contract names are kept for backwards compatibility with previously
# generated JSON files, saved UI drafts, tests, and older automation flows.
# New user-facing code should prefer the "external" wording.
LEGACY_SUBTITLE_MODE = "filmgen"
EXTERNAL_SUBTITLE_MODE = "external"
LEGACY_SUBTITLE_MODE_ALIASES = frozenset({
    LEGACY_SUBTITLE_MODE,
    "filmgen_handoff",
    "handoff",
    EXTERNAL_SUBTITLE_MODE,
    "external_handoff",
})

LEGACY_EXPORT_RESULT_KEY = "filmgen_handoff"
LEGACY_SUBTITLE_RESULT_KEY = "filmgen_handoff"
EXTERNAL_EXPORT_RESULT_KEY = "external_handoff"
EXTERNAL_SUBTITLE_RESULT_KEY = "external_handoff"

LEGACY_EXPORT_ADAPTER_ID = "export.filmgen_handoff"
LEGACY_SUBTITLE_ADAPTER_ID = "subtitle.filmgen"

LEGACY_EXPORT_FILENAME = "filmgen_handoff.json"
LEGACY_SUBTITLE_ARTIFACT_DIR = "_filmgen_subtitle_handoff"

LEGACY_EXPORT_QUEUE_ID = "filmgen_handoffs"
EXTERNAL_EXPORT_QUEUE_ID = "external_handoffs"

LEGACY_EXTERNAL_PROTOCOL_KIND = "filmgen_edit_pack"
EXTERNAL_PROTOCOL_KIND = "external_edit_pack"

LOCAL_EXPORT_HANDOFF_SCHEMAS = frozenset({
    "smart_video_cut.local.export_filmgen_handoff.v0",
    "smart_video_cut.local.export_filmgen_handoff.v1",
})

EXTERNAL_EDIT_PACK_SCHEMAS = frozenset({
    "aifilm-studio.smart-video-cut-handoff.v1",
    "aifilm-studio.edit-pack.v1",
    *LOCAL_EXPORT_HANDOFF_SCHEMAS,
})

DEFAULT_EXTERNAL_STYLE_PACKAGES = (
    "filmgen-cinematic-short",
    "door-flash-reference",
)


def is_external_subtitle_mode(mode: Any) -> bool:
    return str(mode or "").strip().casefold() in LEGACY_SUBTITLE_MODE_ALIASES


def normalize_legacy_subtitle_mode(mode: Any, default: str = "auto") -> str:
    text = str(mode or "").strip()
    if not text:
        return default
    return LEGACY_SUBTITLE_MODE if is_external_subtitle_mode(text) else text


def normalize_legacy_export_queue_id(queue_id: Any) -> str:
    text = str(queue_id or "").strip()
    if text.casefold() == EXTERNAL_EXPORT_QUEUE_ID:
        return LEGACY_EXPORT_QUEUE_ID
    return text


def with_alias(
    payload: Mapping[str, Any],
    *,
    legacy_key: str,
    alias_key: str,
) -> dict[str, Any]:
    result = dict(payload)
    if alias_key not in result and legacy_key in result:
        result[alias_key] = result[legacy_key]
    return result


def preferred_external_handoff_path(output_dir: str | Path) -> Path:
    return Path(output_dir) / LEGACY_EXPORT_FILENAME


def default_external_style_package_candidates(root: Path) -> tuple[Path, ...]:
    return tuple(root / "packages" / name for name in DEFAULT_EXTERNAL_STYLE_PACKAGES)
