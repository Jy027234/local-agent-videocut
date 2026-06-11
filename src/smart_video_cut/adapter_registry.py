from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from smart_video_cut.external_handoff_compat import (
    LEGACY_EXPORT_ADAPTER_ID,
    LEGACY_EXPORT_FILENAME,
    LEGACY_SUBTITLE_ADAPTER_ID,
    LEGACY_SUBTITLE_ARTIFACT_DIR,
    is_external_subtitle_mode,
)
from smart_video_cut.models import LocalVisibleSettings


ADAPTER_REGISTRY_SCHEMA = "smart_video_cut.local.adapter_registry.v0"
ADAPTER_SELECTION_SCHEMA = "smart_video_cut.local.adapter_selection.v0"
ADAPTER_CATEGORIES = ("voice", "subtitle", "bgm", "material_analysis", "export")


@dataclass(slots=True)
class AdapterDefinition:
    adapter_id: str
    name: str
    category: str
    description: str
    status: str = "ready"  # ready | requires_setup | planned | disabled
    local_first: bool = True
    built_in: bool = True
    priority: int = 100
    capabilities: list[str] = field(default_factory=list)
    settings_keys: list[str] = field(default_factory=list)
    input_contract: str = ""
    output_contract: str = ""
    setup_hint: str = ""
    risk_warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AdapterRegistry:
    """Local-first adapter catalog used by UI, Agent tools, and runtime traces."""

    def __init__(self) -> None:
        self._adapters: dict[str, AdapterDefinition] = {}

    def register(self, adapter: AdapterDefinition) -> None:
        self._adapters[adapter.adapter_id] = adapter

    def list_adapters(self, category: str = "", status: str = "") -> list[dict[str, Any]]:
        adapters = sorted(self._adapters.values(), key=lambda item: (item.category, item.priority, item.adapter_id))
        if category:
            adapters = [adapter for adapter in adapters if adapter.category == category]
        if status:
            adapters = [adapter for adapter in adapters if adapter.status == status]
        return [adapter.to_dict() for adapter in adapters]

    def get_adapter(self, adapter_id: str) -> dict[str, Any] | None:
        adapter = self._adapters.get(adapter_id)
        return adapter.to_dict() if adapter else None

    def require_adapter(self, adapter_id: str) -> AdapterDefinition:
        adapter = self._adapters.get(adapter_id)
        if adapter is None:
            raise KeyError(f"adapter_not_found: {adapter_id}")
        return adapter

    def to_manifest(self, category: str = "", status: str = "") -> dict[str, Any]:
        adapters = self.list_adapters(category=category, status=status)
        return {
            "schema": ADAPTER_REGISTRY_SCHEMA,
            "adapter_count": len(adapters),
            "categories": list(ADAPTER_CATEGORIES),
            "filters": {"category": category, "status": status},
            "adapters": adapters,
        }


def build_default_adapter_registry() -> AdapterRegistry:
    registry = AdapterRegistry()
    for adapter in _default_adapters():
        registry.register(adapter)
    return registry


def list_default_adapters(category: str = "", status: str = "") -> dict[str, Any]:
    return build_default_adapter_registry().to_manifest(category=category, status=status)


def resolve_adapter_selection(settings: Mapping[str, Any] | None = None) -> dict[str, Any]:
    """Resolve visible settings into the adapter IDs this run should prefer."""
    normalized = _normalized_settings(settings)
    selected_ids = {
        "voice": [_voice_adapter_id(normalized)],
        "subtitle": [_subtitle_adapter_id(normalized)],
        "bgm": [_bgm_adapter_id(normalized)],
        "material_analysis": _material_adapter_ids(normalized),
        "export": ["export.local_mp4", "export.project_pack", LEGACY_EXPORT_ADAPTER_ID],
    }
    registry = build_default_adapter_registry()
    selected_adapters = {
        category: [registry.require_adapter(adapter_id).to_dict() for adapter_id in adapter_ids]
        for category, adapter_ids in selected_ids.items()
    }
    warnings = _selection_warnings(normalized, selected_adapters)
    return {
        "schema": ADAPTER_SELECTION_SCHEMA,
        "selected_adapter_ids": selected_ids,
        "selected_adapters": selected_adapters,
        "warnings": warnings,
    }


def _default_adapters() -> list[AdapterDefinition]:
    return [
        AdapterDefinition(
            adapter_id="voice.none",
            name="不生成配音",
            category="voice",
            description="关闭旁白生成，仅保留原视频/字幕/BGM策略。",
            capabilities=["disable_voiceover"],
            settings_keys=["voice.mode=none", "voice.provider=none"],
            output_contract="No voiceover audio path is passed to the renderer.",
            priority=10,
        ),
        AdapterDefinition(
            adapter_id="voice.edge_tts",
            name="Edge TTS 配音",
            category="voice",
            description="使用 toolkit 内置 Edge TTS 路径生成中文广告旁白。",
            capabilities=["text_to_speech", "worker_real_render"],
            settings_keys=["voice.provider=edge_tts"],
            input_contract="voiceover_text + allow_edge_tts=true when real rendering.",
            output_contract="Renderer receives generated voiceover through the toolkit contract.",
            setup_hint="真实渲染时需要用户显式允许 allow_edge_tts。",
            priority=20,
        ),
        AdapterDefinition(
            adapter_id="voice.moss_tts_nano",
            name="MOSS-TTS-Nano 本地配音",
            category="voice",
            description="使用本地 MOSS-TTS-Nano ONNX 运行时生成旁白音频。",
            status="requires_setup",
            capabilities=["local_text_to_speech", "voice_profile_prompt"],
            settings_keys=["voice.provider=moss_tts_nano"],
            input_contract="voiceover_text + MOSS runtime + optional prompt_audio_path.",
            output_contract="_smart_video_cut_artifacts/_moss_tts_voiceover/voiceover.wav",
            setup_hint="先通过 /api/moss-tts/status 和 /api/moss-tts/setup 完成运行时准备。",
            priority=30,
        ),
        AdapterDefinition(
            adapter_id="voice.system_tts",
            name="系统 TTS",
            category="voice",
            description="使用 Windows System.Speech 生成本机 WAV 配音。",
            capabilities=["local_text_to_speech"],
            settings_keys=["voice.provider=system_tts"],
            input_contract="voiceover_text + Windows System.Speech runtime.",
            output_contract="_smart_video_cut_artifacts/_system_tts_voiceover/voiceover.wav",
            setup_hint="仅在 Windows 本机可用；失败时会返回 system_tts_failed。",
            priority=40,
        ),
        AdapterDefinition(
            adapter_id="voice.fixture",
            name="Fixture 配音",
            category="voice",
            description="测试/演示用静音 WAV 配音适配器，避免真实 TTS 依赖。",
            capabilities=["test_fixture_audio"],
            settings_keys=["voice.provider=fixture"],
            output_contract="_smart_video_cut_artifacts/_fixture_voiceover/voiceover.wav",
            priority=50,
        ),
        AdapterDefinition(
            adapter_id="subtitle.none",
            name="无内容字幕",
            category="subtitle",
            description="关闭新字幕生成，可继续保留画面原有文字。",
            capabilities=["disable_subtitle_overlay"],
            settings_keys=["subtitle.enabled=false", "subtitle.mode=none"],
            priority=10,
        ),
        AdapterDefinition(
            adapter_id="subtitle.auto_prompt",
            name="自动字幕提示",
            category="subtitle",
            description="根据用户设置和剪辑 brief 生成字幕文本提示。",
            capabilities=["subtitle_prompt_generation"],
            settings_keys=["subtitle.mode=auto"],
            priority=20,
        ),
        AdapterDefinition(
            adapter_id="subtitle.custom_text",
            name="自定义字幕文本",
            category="subtitle",
            description="使用用户填写的字幕文案、位置或提示词作为字幕输入。",
            capabilities=["custom_subtitle_text"],
            settings_keys=["subtitle.custom_prompt", "subtitle.location_info"],
            priority=30,
        ),
        AdapterDefinition(
            adapter_id=LEGACY_SUBTITLE_ADAPTER_ID,
            name="外部字幕交接",
            category="subtitle",
            description="生成可供外部流程读取的本地字幕轨/字幕文案交接文件。",
            capabilities=["external_subtitle_handoff", "subtitle_handoff_file"],
            input_contract="subtitle settings + optional custom_prompt/location_info.",
            output_contract=f"_smart_video_cut_artifacts/{LEGACY_SUBTITLE_ARTIFACT_DIR}/subtitle_handoff.json",
            priority=40,
        ),
        AdapterDefinition(
            adapter_id="bgm.none",
            name="无 BGM",
            category="bgm",
            description="关闭背景音乐。",
            capabilities=["disable_bgm"],
            settings_keys=["audio.bgm_style=none"],
            priority=10,
        ),
        AdapterDefinition(
            adapter_id="bgm.local_audio",
            name="用户本地 BGM",
            category="bgm",
            description="使用用户指定的本地音频文件作为 BGM。",
            capabilities=["local_audio_input"],
            settings_keys=["audio.bgm_audio_path", "audio.bgm_style=local_audio"],
            input_contract="audio.bgm_audio_path points to a readable audio file.",
            output_contract="worker_bgm_audio_input passed to renderer when real rendering.",
            priority=20,
        ),
        AdapterDefinition(
            adapter_id="bgm.library",
            name="本地 BGM 素材库",
            category="bgm",
            description="扫描用户指定目录并按风格/关键词推荐本地音乐文件。",
            capabilities=["local_audio_library_search", "bgm_recommendation"],
            settings_keys=["audio.bgm_style=library", "audio.bgm_library_dir", "audio.bgm_library_query"],
            input_contract="audio.bgm_library_dir points to a local directory containing audio files.",
            output_contract="Recommended local audio path passed to renderer when real rendering.",
            priority=25,
        ),
        AdapterDefinition(
            adapter_id="bgm.generated_placeholder",
            name="内置 BGM 策略占位",
            category="bgm",
            description="保留 upbeat/ambient 等 BGM 风格意图，等待后续本地生成或素材库适配器实现。",
            capabilities=["bgm_style_policy"],
            settings_keys=["audio.bgm_style"],
            output_contract="Render plan records BGM intent; no local audio file is required.",
            priority=30,
        ),
        AdapterDefinition(
            adapter_id="bgm.local_generated",
            name="本地生成 BGM",
            category="bgm",
            description="使用本地程序化音频生成可循环 WAV 背景音乐。",
            capabilities=["local_music_generation", "procedural_wav_bgm"],
            settings_keys=["audio.bgm_style=local_generated"],
            input_contract="audio.generated_mood / generated_duration_seconds are optional.",
            output_contract="_smart_video_cut_artifacts/_local_generated_bgm/bgm.wav",
            priority=40,
        ),
        AdapterDefinition(
            adapter_id="bgm.local_music_model",
            name="本地音乐模型 BGM",
            category="bgm",
            description="通过本地音乐模型适配器生成 BGM；当前先使用可执行的程序化模型占位。",
            capabilities=["local_music_model_adapter", "replaceable_music_generation"],
            settings_keys=["audio.bgm_style=local_music_model", "audio.local_music_model_id"],
            input_contract="audio.local_music_model_id selects an installed local music model when available.",
            output_contract="_smart_video_cut_artifacts/_local_generated_bgm/bgm.wav",
            priority=45,
        ),
        AdapterDefinition(
            adapter_id="material.order_fallback",
            name="顺序素材规划",
            category="material_analysis",
            description="当视觉分析不可用时，按用户添加素材顺序分配镜头角色。",
            capabilities=["order_based_role_assignment"],
            settings_keys=["material_analysis.enable_visual_analysis=false"],
            priority=10,
        ),
        AdapterDefinition(
            adapter_id="material.ffmpeg_probe",
            name="FFmpeg 抽帧素材分析",
            category="material_analysis",
            description="本地抽帧并计算视觉指标，用于规划全貌、细节、环境等素材角色。",
            capabilities=["local_frame_probe", "thumbnail_generation", "role_assignment", "visual_quality_tuning"],
            settings_keys=[
                "material_analysis.visual_quality_preset",
                "material_analysis.frame_sample_count",
                "material_analysis.thumbnail_max_side",
                "material_analysis.role_confidence_threshold",
            ],
            input_contract="Readable input video files + bundled FFmpeg.",
            output_contract="material_plan.visual_analysis + role_source_map.",
            priority=20,
        ),
        AdapterDefinition(
            adapter_id="material.multimodal_review",
            name="多模态素材复核",
            category="material_analysis",
            description="在用户允许上传抽帧/截图时，用多模态模型复核素材角色。",
            status="requires_setup",
            local_first=False,
            capabilities=["vision_llm_review", "role_assignment_review", "ui_privacy_consent_hint"],
            settings_keys=["model_route.allow_media_upload_to_llm=true"],
            risk_warnings=["可能向模型服务发送抽帧缩略图，必须由用户显式允许。"],
            setup_hint="需要配置具备 vision/multimodal 能力的 LLM 路由。",
            priority=30,
        ),
        AdapterDefinition(
            adapter_id="export.local_mp4",
            name="本地 MP4 导出",
            category="export",
            description="真实渲染成功后复制 final.mp4 到项目输出目录。",
            capabilities=["local_video_export"],
            output_contract="output_dir/final.mp4 when render artifact exists.",
            priority=10,
        ),
        AdapterDefinition(
            adapter_id="export.project_pack",
            name="ProjectPack 导出",
            category="export",
            description="将项目清单、时间线、版本历史和素材引用导出为可迁移项目包。",
            capabilities=["project_pack_export", "local_migration"],
            output_contract="project_pack.json + referenced artifacts.",
            priority=20,
        ),
        AdapterDefinition(
            adapter_id=LEGACY_EXPORT_ADAPTER_ID,
            name="外部导出交接",
            category="export",
            description="生成可供外部流程读取的本地导出交接 JSON。",
            capabilities=["external_project_handoff", "handoff_file_export"],
            output_contract=f"output_dir/{LEGACY_EXPORT_FILENAME}",
            priority=30,
        ),
    ]


def _normalized_settings(settings: Mapping[str, Any] | None) -> dict[str, Any]:
    defaults = LocalVisibleSettings().to_dict()
    if not isinstance(settings, Mapping):
        return defaults
    normalized = dict(defaults)
    for section, values in settings.items():
        if not isinstance(values, Mapping):
            continue
        base = normalized.setdefault(str(section), {})
        if isinstance(base, dict):
            base.update(dict(values))
    return normalized


def _voice_adapter_id(settings: Mapping[str, Any]) -> str:
    voice = _section(settings, "voice")
    mode = str(voice.get("mode") or "").strip().casefold()
    provider = str(voice.get("provider") or "edge_tts").strip().casefold()
    if mode == "none" or provider == "none":
        return "voice.none"
    if provider in {"moss_tts_nano", "moss", "moss-tts-nano"}:
        return "voice.moss_tts_nano"
    if provider in {"system_tts", "system"}:
        return "voice.system_tts"
    if provider in {"fixture", "fixture_voice"}:
        return "voice.fixture"
    return "voice.edge_tts"


def _subtitle_adapter_id(settings: Mapping[str, Any]) -> str:
    subtitle = _section(settings, "subtitle")
    mode = str(subtitle.get("mode") or "auto").strip().casefold()
    if subtitle.get("enabled", True) is False or mode == "none":
        return "subtitle.none"
    if is_external_subtitle_mode(mode):
        return LEGACY_SUBTITLE_ADAPTER_ID
    if str(subtitle.get("custom_prompt") or "").strip() or str(subtitle.get("location_info") or "").strip():
        return "subtitle.custom_text"
    return "subtitle.auto_prompt"


def _bgm_adapter_id(settings: Mapping[str, Any]) -> str:
    audio = _section(settings, "audio")
    bgm_style = str(audio.get("bgm_style") or "upbeat_instrumental").strip().casefold()
    if bgm_style == "none":
        return "bgm.none"
    if bgm_style in {"local_audio", "user_music", "custom_audio"} or str(audio.get("bgm_audio_path") or "").strip():
        return "bgm.local_audio"
    if bgm_style in {"library", "local_library", "material_library"} or str(audio.get("bgm_library_dir") or "").strip():
        return "bgm.library"
    if bgm_style in {"local_music_model", "music_model"}:
        return "bgm.local_music_model"
    if bgm_style in {"local_generated", "generated_music", "ai_music"}:
        return "bgm.local_generated"
    return "bgm.generated_placeholder"


def _material_adapter_ids(settings: Mapping[str, Any]) -> list[str]:
    analysis = _section(settings, "material_analysis")
    model_route = _section(settings, "model_route")
    if analysis.get("enable_visual_analysis") is False:
        return ["material.order_fallback"]
    selected = ["material.ffmpeg_probe"]
    if model_route.get("allow_media_upload_to_llm") is True and analysis.get("enable_multimodal_review", True) is not False:
        selected.append("material.multimodal_review")
    return selected


def _selection_warnings(
    settings: Mapping[str, Any],
    selected_adapters: Mapping[str, list[dict[str, Any]]],
) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = []
    for category, adapters in selected_adapters.items():
        for adapter in adapters:
            if adapter.get("status") == "requires_setup":
                warnings.append({
                    "code": "adapter_requires_setup",
                    "category": category,
                    "adapter_id": str(adapter.get("adapter_id")),
                    "message": str(adapter.get("setup_hint") or "该适配器需要先完成配置。"),
                })
            if adapter.get("status") == "planned":
                warnings.append({
                    "code": "adapter_planned_not_executable",
                    "category": category,
                    "adapter_id": str(adapter.get("adapter_id")),
                    "message": "该适配器仅注册为路线图能力，尚未接入执行层。",
                })
            for warning in adapter.get("risk_warnings") or []:
                warnings.append({
                    "code": "adapter_risk_warning",
                    "category": category,
                    "adapter_id": str(adapter.get("adapter_id")),
                    "message": str(warning),
                })
    audio = _section(settings, "audio")
    if selected_adapters.get("bgm", [{}])[0].get("adapter_id") == "bgm.local_audio":
        if not str(audio.get("bgm_audio_path") or "").strip():
            warnings.append({
                "code": "missing_bgm_audio_path",
                "category": "bgm",
                "adapter_id": "bgm.local_audio",
                "message": "选择了本地 BGM 适配器，但尚未填写 bgm_audio_path。",
            })
    return warnings


def _section(settings: Mapping[str, Any], name: str) -> dict[str, Any]:
    section = settings.get(name)
    return dict(section) if isinstance(section, Mapping) else {}
