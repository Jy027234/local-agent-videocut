from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping


def apply_visible_settings_overrides(
    settings: Mapping[str, Any],
    overrides: Mapping[str, Any] | None,
) -> dict[str, Any]:
    merged = deepcopy(dict(settings))
    for section_name, section_values in dict(overrides or {}).items():
        if not isinstance(section_values, Mapping):
            continue
        section = merged.setdefault(str(section_name), {})
        if not isinstance(section, dict):
            continue
        for key, value in section_values.items():
            if value is None or value == "":
                continue
            section[str(key)] = value
    quality = str(merged.get("video", {}).get("quality") or "")
    if quality:
        merged.setdefault("video", {})["crf"] = quality_to_crf(quality)
    return merged


def quality_to_crf(quality: str) -> int:
    return {
        "draft": 28,
        "standard": 22,
        "high": 18,
    }.get(str(quality), 22)
