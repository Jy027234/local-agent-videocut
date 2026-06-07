from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


SCHEMA_PREFIX = "smart_video_cut.local"
STYLE_PACKAGE_SCHEMA = f"{SCHEMA_PREFIX}.style_package.v0"
LOCAL_EDIT_TASK_SCHEMA = f"{SCHEMA_PREFIX}.edit_task.v0"

MATERIAL_PACK_SCHEMA = f"{SCHEMA_PREFIX}.material_pack.v0"
STYLE_PACK_SCHEMA = f"{SCHEMA_PREFIX}.style_pack.v1"
PROJECT_PACK_SCHEMA = f"{SCHEMA_PREFIX}.project_pack.v0"


@dataclass(slots=True)
class VideoOutputSettings:
    target_duration_seconds: int = 20
    aspect_ratio: str = "9:16"
    resolution: str = "720x1280"
    fps: int = 30
    quality: str = "standard"
    crf: int = 22
    video_codec: str = "h264"
    container: str = "mp4"


@dataclass(slots=True)
class ImageQualitySettings:
    stabilize: bool = True
    denoise: bool = False
    sharpen: bool = True
    color_boost: bool = True
    brightness: float = 0.0
    contrast: float = 1.08
    saturation: float = 1.14


@dataclass(slots=True)
class SubtitleSettings:
    enabled: bool = True
    mode: str = "auto"
    custom_prompt: str = ""
    location_info: str = ""
    preserve_onscreen_text: bool = True
    font_size: int = 44
    font_color: str = "white"
    outline_color: str = "black"
    outline_width: int = 5
    position: str = "bottom_center"


@dataclass(slots=True)
class CoverSettings:
    enabled: bool = True
    title: str = "安装记录"
    subtitle_line_1: str = "入户门安装"
    subtitle_line_2: str = "现场记录"
    label_background: str = "yellow"


@dataclass(slots=True)
class AudioSettings:
    remove_original_voice: bool = True
    bgm_style: str = "upbeat_instrumental"
    bgm_audio_path: str = ""
    bgm_start_seconds: float = 0.0
    bgm_volume_db: float = -18.0
    voice_volume_db: float = -3.0
    normalize_loudness: bool = True


@dataclass(slots=True)
class VoiceSettings:
    mode: str = "generated_male_ad_copy"
    provider: str = "edge_tts"
    gender: str = "male"
    style: str = "warm_vlog_narrator"
    prompt_audio_path: str = ""
    moss_voice: str = "Zhiming"
    moss_profile: str = "stable_clear"
    sample_mode: str = "fixed"
    text_temperature: float = 0.8
    audio_temperature: float = 0.6
    seed: int | None = 2026
    voice_profile_ref: dict[str, Any] | None = None
    require_saved_profile: bool = False


@dataclass(slots=True)
class ModelRouteSettings:
    provider: str = "openai_compatible"
    model: str = "user_configured"
    api_key_ref: str = "local_secret_store"
    allow_cloud_llm_for_text_only: bool = True
    allow_media_upload_to_llm: bool = False


@dataclass(slots=True)
class LocalVisibleSettings:
    video: VideoOutputSettings = field(default_factory=VideoOutputSettings)
    image: ImageQualitySettings = field(default_factory=ImageQualitySettings)
    subtitle: SubtitleSettings = field(default_factory=SubtitleSettings)
    cover: CoverSettings = field(default_factory=CoverSettings)
    audio: AudioSettings = field(default_factory=AudioSettings)
    voice: VoiceSettings = field(default_factory=VoiceSettings)
    model_route: ModelRouteSettings = field(default_factory=ModelRouteSettings)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StylePackageRequest:
    name: str
    template_video: Path
    package_dir: Path
    description: str = ""
    settings: LocalVisibleSettings = field(default_factory=LocalVisibleSettings)


@dataclass(slots=True)
class LocalEditTask:
    style_package: Path
    input_video: Path
    output_dir: Path
    user_request: str
    execute_real_render: bool = False
    allow_edge_tts: bool = False
    voiceover_text: str | None = None
    use_memory: bool = True
    project_id: str = "local_project"
    settings_overrides: dict[str, Any] = field(default_factory=dict)
    confirmed_brief: str | None = None
    input_videos: list[Path] = field(default_factory=list)
    timeline_override: dict[str, Any] | None = None
    task_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": LOCAL_EDIT_TASK_SCHEMA,
            "style_package": str(self.style_package),
            "input_video": str(self.input_video),
            "input_videos": [str(path) for path in self.input_videos],
            "output_dir": str(self.output_dir),
            "user_request": self.user_request,
            "execute_real_render": self.execute_real_render,
            "allow_edge_tts": self.allow_edge_tts,
            "voiceover_text": self.voiceover_text,
            "use_memory": self.use_memory,
            "project_id": self.project_id,
            "settings_overrides": self.settings_overrides,
            "confirmed_brief": self.confirmed_brief,
            "task_id": self.task_id,
        }


@dataclass(slots=True)
class MaterialPack:
    """Material pack: reference video and media resources."""

    name: str
    schema: str = MATERIAL_PACK_SCHEMA
    reference_video_path: str = ""
    reference_video_checksum: str = ""
    thumbnail_paths: list[str] = field(default_factory=list)
    description: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class StylePack:
    """Style pack: editing style strategy + visible settings, without media."""

    name: str
    schema: str = STYLE_PACK_SCHEMA
    timeline_template: dict[str, Any] = field(default_factory=dict)
    visible_settings: dict[str, Any] = field(default_factory=dict)
    edit_brief_profile: dict[str, Any] = field(default_factory=dict)
    render_overrides: dict[str, Any] = field(default_factory=dict)
    description: str = ""
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ProjectPack:
    """Project pack: binds concrete materials + style + project config."""

    name: str
    schema: str = PROJECT_PACK_SCHEMA
    material_pack_ref: str = ""
    style_pack_ref: str = ""
    input_videos: list[str] = field(default_factory=list)
    output_dir: str = ""
    project_settings_overrides: dict[str, Any] = field(default_factory=dict)
    source_output_dir: str = ""
    project_manifest: dict[str, Any] = field(default_factory=dict)
    timeline_plan: dict[str, Any] = field(default_factory=dict)
    version_history: dict[str, Any] = field(default_factory=dict)
    artifact_refs: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
