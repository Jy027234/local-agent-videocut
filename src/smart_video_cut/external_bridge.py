from __future__ import annotations

from pathlib import Path
from typing import Any, Mapping

from smart_video_cut.external_handoff_compat import (
    EXTERNAL_EDIT_PACK_SCHEMAS,
    EXTERNAL_EXPORT_RESULT_KEY,
    EXTERNAL_SUBTITLE_RESULT_KEY,
    LEGACY_EXPORT_RESULT_KEY,
    LEGACY_SUBTITLE_RESULT_KEY,
    LOCAL_EXPORT_HANDOFF_SCHEMAS,
    with_alias,
)
from smart_video_cut.filmgen_bridge import (
    FILMGEN_EXPORT_HANDOFF_IMPORT_VALIDATION_SCHEMA as EXTERNAL_EXPORT_HANDOFF_IMPORT_VALIDATION_SCHEMA,
    build_edit_brief_from_filmgen_pack,
    build_local_edit_task_from_filmgen_pack,
    load_filmgen_edit_pack,
    validate_filmgen_export_handoff_import,
)
from smart_video_cut.subtitle_adapters import (
    FILMGEN_SUBTITLE_HANDOFF_PREVIEW_SCHEMA as EXTERNAL_SUBTITLE_HANDOFF_PREVIEW_SCHEMA,
    FILMGEN_SUBTITLE_HANDOFF_SCHEMA as EXTERNAL_SUBTITLE_HANDOFF_SCHEMA,
    load_filmgen_subtitle_handoff,
)


def load_external_edit_pack(manifest_path: str | Path) -> dict[str, Any]:
    return load_filmgen_edit_pack(manifest_path)


def validate_external_export_handoff_import(handoff_path: str | Path) -> dict[str, Any]:
    payload = validate_filmgen_export_handoff_import(handoff_path)
    return with_alias(
        payload,
        legacy_key=LEGACY_EXPORT_RESULT_KEY,
        alias_key=EXTERNAL_EXPORT_RESULT_KEY,
    )


def build_edit_brief_from_external_pack(
    *,
    manifest_path: str | Path,
    style_package: str | Path,
    input_video: str | Path = "",
    input_videos: list[str | Path] | None = None,
    output_dir: str | Path = "",
    user_request: str = "",
    settings_overrides: Mapping[str, Any] | None = None,
    execute_real_render: bool = False,
    use_memory: bool = True,
) -> dict[str, Any]:
    payload = build_edit_brief_from_filmgen_pack(
        manifest_path=manifest_path,
        style_package=style_package,
        input_video=input_video,
        input_videos=input_videos,
        output_dir=output_dir,
        user_request=user_request,
        settings_overrides=settings_overrides,
        execute_real_render=execute_real_render,
        use_memory=use_memory,
    )
    return with_alias(
        payload,
        legacy_key=LEGACY_EXPORT_RESULT_KEY,
        alias_key=EXTERNAL_EXPORT_RESULT_KEY,
    )


def build_local_edit_task_from_external_pack(
    *,
    manifest_path: str | Path,
    style_package: str | Path,
    input_video: str | Path = "",
    input_videos: list[str | Path] | None = None,
    output_dir: str | Path = "",
    user_request: str = "",
    settings_overrides: Mapping[str, Any] | None = None,
    confirmed_brief: str | None = None,
    execute_real_render: bool = False,
    allow_edge_tts: bool = False,
    use_memory: bool = True,
):
    return build_local_edit_task_from_filmgen_pack(
        manifest_path=manifest_path,
        style_package=style_package,
        input_video=input_video,
        input_videos=input_videos,
        output_dir=output_dir,
        user_request=user_request,
        settings_overrides=settings_overrides,
        confirmed_brief=confirmed_brief,
        execute_real_render=execute_real_render,
        allow_edge_tts=allow_edge_tts,
        use_memory=use_memory,
    )


def load_external_subtitle_handoff(path: str | Path) -> dict[str, Any]:
    payload = load_filmgen_subtitle_handoff(path)
    if LEGACY_SUBTITLE_RESULT_KEY in payload:
        return with_alias(
            payload,
            legacy_key=LEGACY_SUBTITLE_RESULT_KEY,
            alias_key=EXTERNAL_SUBTITLE_RESULT_KEY,
        )
    return payload
