from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
try:
    from fastapi import Request
    from fastapi.staticfiles import StaticFiles
except ImportError:  # pragma: no cover
    Request = Any  # type: ignore[assignment]
    StaticFiles = Any  # type: ignore[assignment,misc]

from smart_video_cut.adapter_registry import list_default_adapters, resolve_adapter_selection
from smart_video_cut.agent_orchestrator import orchestrate_local_agents
from smart_video_cut.agent_tools import build_default_registry
from smart_video_cut.edit_brief import build_edit_brief
from smart_video_cut.edit_settings import apply_visible_settings_overrides
from smart_video_cut.deployment_guide import local_deployment_guide
from smart_video_cut.external_bridge import (
    build_edit_brief_from_external_pack,
    build_local_edit_task_from_external_pack,
    load_external_edit_pack,
    load_external_subtitle_handoff,
    validate_external_export_handoff_import,
)
from smart_video_cut.folder_scanner import scan_media_folder, scan_output_folder
from smart_video_cut.local_files import list_local_paths
from smart_video_cut.models import LocalEditTask, StylePackageRequest
from smart_video_cut.pack_manager import (
    create_material_pack,
    create_project_pack,
    create_style_pack,
    discover_packs,
    load_pack,
    resolve_project_pack,
    validate_pack_references,
)
from smart_video_cut.export_adapters import export_project_pack_adapter
from smart_video_cut.project_manifest import read_project_manifest, write_project_manifest
from smart_video_cut.project_library import (
    get_project_from_library,
    list_project_library,
    list_repair_threads,
    rebuild_project_library,
    record_repair_thread,
)
from smart_video_cut.protocol_dropbox import (
    get_protocol_dropbox_history,
    import_protocol_dropbox_item,
    initialize_protocol_dropbox,
    requeue_protocol_dropbox_failed,
    run_protocol_dropbox_once,
)
from smart_video_cut.protocol_dropbox_monitor import (
    get_protocol_dropbox_monitor_status,
    start_protocol_dropbox_monitor,
    stop_protocol_dropbox_monitor,
)
from smart_video_cut.protocol_runner import run_protocol_path
from smart_video_cut.recent_runs import delete_recent_run, list_recent_runs
from smart_video_cut.release_preflight import collect_release_preflight
from smart_video_cut.style_package import (
    create_style_package,
    default_settings_from_options,
    discover_style_packages,
    load_style_package,
)
from smart_video_cut.bundled_runtime import (
    ensure_video_toolkit_available,
    run_edit_with_style_package,
    run_voice_profile_contract,
)
from smart_video_cut.bgm_library import build_bgm_library_playlist, scan_bgm_library
from smart_video_cut.director_agent import chat_with_director
from smart_video_cut.task_status import (
    get_task_status,
    generate_task_id,
    list_task_statuses,
)
from smart_video_cut.toolkit_protocol import inspect_local_toolkit_path, write_local_toolkit_protocol
from smart_video_cut.timeline_builder import (
    apply_user_edits,
    build_timeline_plan,
    timeline_to_toolkit_format,
)
from smart_video_cut.timeline_model import TimelinePlan
from smart_video_cut.template_analysis import analyze_template_video
from smart_video_cut.version_history import (
    get_version,
    get_version_history,
    revert_to_version,
    save_version,
)
from smart_video_cut.voice_profile_review import (
    confirm_voice_profile_review,
    list_voice_profile_reviews,
)
from smart_video_cut.local_config import (
    check_ollama_status,
    check_voice_model,
    list_ollama_models,
    load_local_config_summary,
    recommend_ollama_llm_config,
    save_llm_config,
    save_ollama_llm_config,
    save_voice_model_config,
    test_llm_config,
)
from smart_video_cut.local_memory import (
    add_memory_entry,
    add_task_feedback_memory,
    memory_summary,
)
from smart_video_cut.material_calibration import calibrate_visual_role_thresholds
from smart_video_cut.moss_tts import (
    check_moss_tts_status,
    install_moss_tts_runtime,
    synthesize_moss_tts,
)
from smart_video_cut.voice_adapters import generate_system_tts_preview, list_system_tts_voices
from smart_video_cut.worker_protocol import (
    create_worker_task_package,
    load_worker_task_package,
    run_worker_task_package,
)


STATIC_DIR = Path(__file__).resolve().parent / "static"
INDEX_PATH = STATIC_DIR / "index.html"


class PackageRequest(BaseModel):
    name: str
    template_video: str
    package_dir: str
    description: str = ""
    duration: int = 20
    aspect_ratio: str = "9:16"
    resolution: str = "720x1280"
    quality: str = "standard"
    subtitle_size: int = 44
    bgm_volume_db: float = -18.0
    voice_provider: str = "edge_tts"


class TemplateAnalysisRequest(BaseModel):
    template_video: str
    output_dir: str = ""


class CutRequest(BaseModel):
    style_package: str
    input_video: str = ""
    input_videos: list[str] = Field(default_factory=list)
    output_dir: str
    user_request: str
    project_id: str = "local_project"
    execute_real_render: bool = False
    allow_edge_tts: bool = False
    voiceover_text: str | None = None
    use_memory: bool = True
    confirmed_brief: str | None = None
    settings_overrides: dict[str, Any] = Field(default_factory=dict)
    timeline_override: dict[str, Any] | None = None
    task_id: str | None = None


class WorkerTaskPackageRequest(CutRequest):
    package_dir: str
    package_name: str = ""


class WorkerTaskRunRequest(BaseModel):
    package_path: str


class ToolkitProtocolBuildRequest(BaseModel):
    output_dir: str


class ToolkitProtocolInspectRequest(BaseModel):
    path: str


class ToolkitProtocolRunRequest(BaseModel):
    path: str
    output_dir: str = ""
    style_package: str = ""
    user_request: str = ""
    voiceover_text: str | None = None
    use_memory: bool | None = None
    confirmed_brief: str | None = None
    execute_real_render: bool | None = None
    allow_edge_tts: bool | None = None


class ProtocolDropboxInitRequest(BaseModel):
    dropbox_dir: str = ""


class ProtocolDropboxImportRequest(BaseModel):
    dropbox_dir: str = ""
    source_path: str
    label: str = ""


class ProtocolDropboxRunRequest(BaseModel):
    dropbox_dir: str = ""
    default_execute_real_render: bool = False
    stop_on_error: bool = False
    max_retries: int = 0
    dry_run: bool = False


class ProtocolDropboxMonitorRequest(BaseModel):
    dropbox_dir: str = ""
    interval_seconds: float = 15.0
    max_cycles: int = 0
    default_execute_real_render: bool = False
    stop_on_error: bool = False
    max_retries: int = 0
    dry_run: bool = False


class ProtocolDropboxMonitorStatusRequest(BaseModel):
    dropbox_dir: str = ""


class ProtocolDropboxHistoryRequest(BaseModel):
    dropbox_dir: str = ""
    limit: int = 20
    queue_id: str = ""
    alerts_only: bool = False


class ProtocolDropboxRequeueRequest(BaseModel):
    dropbox_dir: str = ""
    queue_id: str = "all"
    max_files: int = 20


class EditBriefRequest(BaseModel):
    style_package: str
    input_video: str = ""
    input_videos: list[str] = Field(default_factory=list)
    output_dir: str
    user_request: str
    voiceover_text: str | None = None
    execute_real_render: bool = False
    use_memory: bool = True
    settings_overrides: dict[str, Any] = Field(default_factory=dict)


class ExternalEditPackRequest(BaseModel):
    manifest_path: str
    style_package: str = ""
    input_video: str = ""
    input_videos: list[str] = Field(default_factory=list)
    output_dir: str = ""
    user_request: str = ""
    execute_real_render: bool = False
    allow_edge_tts: bool = False
    use_memory: bool = True
    confirmed_brief: str | None = None
    settings_overrides: dict[str, Any] = Field(default_factory=dict)


class ExternalSubtitleHandoffRequest(BaseModel):
    handoff_path: str


class ExternalExportHandoffValidationRequest(BaseModel):
    handoff_path: str


class MaterialCalibrationRequest(BaseModel):
    sample_set: str = "door_scene"
    sample_set_path: str = ""
    samples: list[dict[str, Any]] = Field(default_factory=list)
    baseline_threshold: float = 0.5


class BgmLibraryRequest(BaseModel):
    library_dir: str
    query: str = ""
    style: str = ""
    limit: int = 20
    output_path: str = ""


class DirectorChatRequest(BaseModel):
    message: str
    history: list[dict[str, Any]] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    director_mode: str = "local_rule"


class AgentOrchestrationRequest(BaseModel):
    message: str = ""
    history: list[dict[str, Any]] = Field(default_factory=list)
    context: dict[str, Any] = Field(default_factory=dict)
    director_mode: str = "local_rule"


class VoiceProfileRequest(BaseModel):
    output_dir: str
    provider_id: str = "edge_tts"
    voice_gender: str = "male"
    voice_style: str = "warm_vlog_narrator"
    sample_text: str = "这是一段本地智能剪辑的男声样音。"
    sample_outcome: str = "approved"


class VoiceProfileConfirmRequest(BaseModel):
    output_dir: str = ""
    profile_result_path: str = ""
    profile_result: dict[str, Any] | None = None
    outcome: str = "approved"
    notes: str = ""
    rating: int | float | None = None
    prompt_audio_path: str = ""
    sample_audio_path: str = ""


class SystemTtsPreviewRequest(BaseModel):
    text: str = "这是一段系统 TTS 试听语音。"
    output_dir: str = ""
    voice_name: str = ""
    rate: int = 0
    volume: int = 100


class AdapterSelectionRequest(BaseModel):
    settings: dict[str, Any] = Field(default_factory=dict)
    style_package: str = ""
    settings_overrides: dict[str, Any] = Field(default_factory=dict)


class LlmConfigRequest(BaseModel):
    provider: str = "openai_compatible"
    base_url: str = "https://api.openai.com/v1"
    model: str = ""
    recommendation_profile: str = "visual_review_recommended"
    model_capability: str = "multimodal_text_image"
    api_key: str = ""
    timeout_seconds: int = 20
    temperature: float = 0.2
    allow_cloud_llm_for_text_only: bool = True
    allow_media_upload_to_llm: bool = False


class OllamaApplyRequest(BaseModel):
    model: str = ""
    base_url: str = ""
    model_capability: str = ""


class VoiceModelConfigRequest(BaseModel):
    provider_id: str = "moss_tts_nano"
    display_name: str = "MOSS-TTS-Nano"
    repo_url: str = "https://github.com/OpenMOSS/MOSS-TTS-Nano.git"
    install_dir: str = ""
    enabled: bool = True


class MossTtsTestRequest(BaseModel):
    text: str = "这是一段本地智能剪辑软件生成的男声样音。"
    output_dir: str = ""
    voice: str = "Zhiming"
    profile: str = "stable_clear"
    prompt_audio_path: str | None = None
    cpu_threads: int = 4
    max_new_frames: int = 375
    sample_mode: str = "fixed"
    text_temperature: float = 0.8
    audio_temperature: float = 0.6
    seed: int | None = 2026


class MemoryEntryRequest(BaseModel):
    memory_type: str = "editing_preference"
    title: str = ""
    content: str
    tags: list[str] = []
    source: str = "manual"
    importance: int = 3
    enabled: bool = True


class MemoryFeedbackRequest(BaseModel):
    project_id: str = "local_project"
    output_dir: str = ""
    feedback: str
    rating: int = 3


class TimelineRequest(BaseModel):
    style_package: str
    input_video: str = ""
    input_videos: list[str] = Field(default_factory=list)
    output_dir: str
    user_request: str = ""
    settings_overrides: dict[str, Any] = Field(default_factory=dict)


class TimelineEditRequest(BaseModel):
    base_timeline: dict[str, Any]
    edits: list[dict[str, Any]] = Field(default_factory=list)
    output_dir: str = ""
    user_feedback: str = ""


class TimelineValidateRequest(BaseModel):
    timeline: dict[str, Any]


class FolderScanRequest(BaseModel):
    folder: str
    scan_type: str = "input"
    recursive: bool = True
    limit: int = 200


class ProjectLibraryRebuildRequest(BaseModel):
    output_root: str = ""
    limit: int = 500


class ReEditRequest(BaseModel):
    output_dir: str
    base_version: int
    user_feedback: str = ""
    timeline_edits: list[dict[str, Any]] = Field(default_factory=list)
    settings_overrides: dict[str, Any] = Field(default_factory=dict)
    execute_real_render: bool = False


class MaterialPackRequest(BaseModel):
    name: str
    package_dir: str
    reference_video_path: str = ""
    description: str = ""
    thumbnail_paths: list[str] = Field(default_factory=list)


class StylePackRequest(BaseModel):
    name: str
    package_dir: str
    visible_settings: dict[str, Any] = Field(default_factory=dict)
    timeline_template: dict[str, Any] | None = None
    edit_brief_profile: dict[str, Any] = Field(default_factory=dict)
    render_overrides: dict[str, Any] = Field(default_factory=dict)
    description: str = ""


class ProjectPackRequest(BaseModel):
    name: str
    package_dir: str
    material_pack_ref: str = ""
    style_pack_ref: str = ""
    input_videos: list[str] = Field(default_factory=list)
    output_dir: str = ""
    project_settings_overrides: dict[str, Any] = Field(default_factory=dict)
    source_output_dir: str = ""
    project_manifest: dict[str, Any] = Field(default_factory=dict)
    timeline_plan: dict[str, Any] = Field(default_factory=dict)
    version_history: dict[str, Any] = Field(default_factory=dict)
    artifact_refs: dict[str, Any] = Field(default_factory=dict)


class ProjectPackExportRequest(BaseModel):
    output_dir: str
    package_dir: str
    name: str = ""
    material_pack_ref: str = ""
    style_pack_ref: str = ""
    project_settings_overrides: dict[str, Any] = Field(default_factory=dict)


class ResolvePackRequest(BaseModel):
    project_pack: dict[str, Any]


class PackValidateRequest(BaseModel):
    pack: dict[str, Any]


def create_app() -> Any:
    try:
        from fastapi import FastAPI
        from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("Install web extras with `pip install -e .[web]`.") from exc

    app = FastAPI(title="Smart Video Cut Local Studio")
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    @app.exception_handler(ValueError)
    async def handle_value_error(request: Request, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"ok": False, "error": str(exc)})

    def dump_model(model: Any) -> dict[str, Any]:
        if hasattr(model, "model_dump"):
            return model.model_dump()
        return model.dict()

    def _filmgen_preview_payload(manifest_path: str) -> dict[str, Any]:
        handoff = load_external_edit_pack(manifest_path)
        return {
            "schema": "smart_video_cut.local.filmgen_preview.v0",
            "ok": True,
            "filmgen_handoff": handoff,
            "external_handoff": handoff,
        }

    def _external_preview_payload(manifest_path: str) -> dict[str, Any]:
        handoff = load_external_edit_pack(manifest_path)
        return {
            "schema": "smart_video_cut.local.external_preview.v0",
            "ok": True,
            "external_handoff": handoff,
            "filmgen_handoff": handoff,
        }

    def _external_export_validation_payload(handoff_path: str) -> dict[str, Any]:
        payload = dict(validate_external_export_handoff_import(handoff_path))
        if "external_handoff" not in payload and "filmgen_handoff" in payload:
            payload["external_handoff"] = payload.get("filmgen_handoff")
        return payload

    def _external_edit_brief_payload(body: ExternalEditPackRequest) -> dict[str, Any]:
        payload = build_edit_brief_from_external_pack(
            manifest_path=body.manifest_path,
            style_package=body.style_package,
            input_video=body.input_video,
            input_videos=body.input_videos,
            output_dir=body.output_dir,
            user_request=body.user_request,
            settings_overrides=body.settings_overrides,
            execute_real_render=body.execute_real_render,
            use_memory=body.use_memory,
        )
        if "external_handoff" not in payload and "filmgen_handoff" in payload:
            payload["external_handoff"] = payload.get("filmgen_handoff")
        return payload

    @app.get("/", response_class=HTMLResponse)
    def index() -> str:
        return INDEX_PATH.read_text(encoding="utf-8")

    @app.get("/api/check")
    def check() -> dict[str, Any]:
        return ensure_video_toolkit_available()

    @app.get("/api/preflight")
    def api_preflight() -> dict[str, Any]:
        root = Path(__file__).resolve().parents[2]
        return collect_release_preflight(root=root, port=8769)

    @app.get("/api/adapters")
    def api_adapters(category: str = "", status: str = "") -> dict[str, Any]:
        return list_default_adapters(category=category, status=status)

    @app.post("/api/adapters/selection")
    def api_adapter_selection(body: AdapterSelectionRequest) -> dict[str, Any]:
        settings = body.settings
        if body.style_package:
            package = load_style_package(body.style_package)
            settings = apply_visible_settings_overrides(
                package.get("visible_settings", {}),
                body.settings_overrides,
            )
        return resolve_adapter_selection(settings)

    @app.get("/api/files")
    def api_files(path: str = "", mode: str = "file", extensions: str = "") -> dict[str, Any]:
        return list_local_paths(path=path, mode=mode, extensions=extensions)

    @app.get("/api/local-config")
    def api_local_config() -> dict[str, Any]:
        return load_local_config_summary()

    @app.get("/api/memory")
    def api_memory() -> dict[str, Any]:
        return memory_summary()

    @app.post("/api/memory")
    def api_add_memory(body: MemoryEntryRequest) -> dict[str, Any]:
        return add_memory_entry(**dump_model(body))

    @app.post("/api/memory/feedback")
    def api_add_memory_feedback(body: MemoryFeedbackRequest) -> dict[str, Any]:
        return add_task_feedback_memory(**dump_model(body))

    @app.post("/api/agent/orchestrate")
    def api_agent_orchestrate(body: AgentOrchestrationRequest) -> dict[str, Any]:
        return orchestrate_local_agents(
            message=body.message,
            history=body.history,
            context=body.context,
            director_mode=body.director_mode,
        )

    @app.post("/api/llm-config")
    def api_save_llm_config(body: LlmConfigRequest) -> dict[str, Any]:
        return save_llm_config(dump_model(body))

    @app.post("/api/llm-test")
    def api_test_llm(body: LlmConfigRequest) -> dict[str, Any]:
        return test_llm_config(dump_model(body))

    @app.get("/api/ollama/status")
    def api_ollama_status(base_url: str = "", timeout_seconds: int = 3) -> dict[str, Any]:
        return check_ollama_status(base_url=base_url, timeout_seconds=timeout_seconds)

    @app.get("/api/ollama/models")
    def api_ollama_models(base_url: str = "", timeout_seconds: int = 5) -> dict[str, Any]:
        return list_ollama_models(base_url=base_url, timeout_seconds=timeout_seconds)

    @app.post("/api/ollama/recommend-config")
    def api_ollama_recommend_config(body: OllamaApplyRequest) -> dict[str, Any]:
        return recommend_ollama_llm_config(
            model=body.model,
            base_url=body.base_url,
            model_capability=body.model_capability,
        )

    @app.post("/api/ollama/apply")
    def api_ollama_apply(body: OllamaApplyRequest) -> dict[str, Any]:
        return save_ollama_llm_config(dump_model(body))

    @app.post("/api/voice-model-config")
    def api_save_voice_model_config(body: VoiceModelConfigRequest) -> dict[str, Any]:
        return save_voice_model_config(dump_model(body))

    @app.get("/api/voice-model/check")
    def api_check_voice_model() -> dict[str, Any]:
        return check_voice_model()

    @app.get("/api/moss-tts/status")
    def api_moss_tts_status() -> dict[str, Any]:
        return check_moss_tts_status()

    @app.post("/api/moss-tts/setup")
    def api_moss_tts_setup() -> dict[str, Any]:
        return install_moss_tts_runtime()

    @app.post("/api/moss-tts/test")
    def api_moss_tts_test(body: MossTtsTestRequest) -> dict[str, Any]:
        output_dir = Path(body.output_dir) if body.output_dir else Path("workspace") / "projects" / "moss-tts-test"
        output_dir.mkdir(parents=True, exist_ok=True)
        output_path = _moss_tts_sample_output_path(
            output_dir=output_dir,
            voice=body.voice,
            profile=body.profile,
        )
        result = synthesize_moss_tts(
            text=body.text,
            output_audio_path=output_path,
            voice=body.voice,
            prompt_audio_path=body.prompt_audio_path,
            cpu_threads=body.cpu_threads,
            max_new_frames=body.max_new_frames,
            sample_mode=body.sample_mode,
            text_temperature=body.text_temperature,
            audio_temperature=body.audio_temperature,
            seed=body.seed,
        )
        sample = _write_moss_tts_sample_metadata(output_dir=output_dir, output_path=output_path, body=body, result=result)
        return {
            **result,
            "sample": sample,
            "history": list_moss_tts_samples(output_dir),
        }

    @app.get("/api/moss-tts/history")
    def api_moss_tts_history(output_dir: str = "") -> dict[str, Any]:
        selected_dir = Path(output_dir) if output_dir else Path("workspace") / "projects" / "moss-tts-test"
        return {
            "schema": "smart_video_cut.local.moss_tts_sample_history.v0",
            "output_dir": str(selected_dir),
            "samples": list_moss_tts_samples(selected_dir),
        }

    @app.post("/api/voice-samples")
    async def api_voice_sample_upload(request: Request, filename: str = "voice-sample.webm") -> dict[str, Any]:
        data = await request.body()
        return save_voice_sample(data=data, filename=filename)

    @app.get("/api/style-packages")
    def api_list_style_packages() -> dict[str, Any]:
        return {
            "schema": "smart_video_cut.local.style_package_index.v0",
            "packages": discover_style_packages(),
        }

    @app.post("/api/template/analyze")
    def api_template_analyze(body: TemplateAnalysisRequest) -> dict[str, Any]:
        return analyze_template_video(
            body.template_video,
            output_dir=body.output_dir,
        )

    @app.post("/api/style-packages")
    def api_create_package(body: PackageRequest) -> dict[str, Any]:
        settings = default_settings_from_options(
            duration=body.duration,
            aspect_ratio=body.aspect_ratio,
            resolution=body.resolution,
            quality=body.quality,
            subtitle_size=body.subtitle_size,
            bgm_volume_db=body.bgm_volume_db,
            voice_provider=body.voice_provider,
        )
        package = create_style_package(
            StylePackageRequest(
                name=body.name,
                description=body.description,
                template_video=Path(body.template_video),
                package_dir=Path(body.package_dir),
                settings=settings,
            )
        )
        return {"ok": True, "package_dir": body.package_dir, "package": package}

    @app.post("/api/edit-brief")
    def api_edit_brief(body: EditBriefRequest) -> dict[str, Any]:
        return build_edit_brief(
            style_package=body.style_package,
            input_video=_primary_input_video(body.input_video, body.input_videos),
            input_videos=body.input_videos,
            output_dir=body.output_dir,
            user_request=body.user_request,
            voiceover_text=body.voiceover_text,
            execute_real_render=body.execute_real_render,
            use_memory=body.use_memory,
            settings_overrides=body.settings_overrides,
        )

    @app.post("/api/worker/package")
    def api_worker_package(body: WorkerTaskPackageRequest) -> dict[str, Any]:
        return create_worker_task_package(
            package_dir=body.package_dir,
            package_name=body.package_name,
            style_package=body.style_package,
            input_video=_primary_input_video(body.input_video, body.input_videos),
            input_videos=body.input_videos,
            output_dir=body.output_dir,
            user_request=body.user_request,
            project_id=body.project_id,
            execute_real_render=body.execute_real_render,
            allow_edge_tts=body.allow_edge_tts,
            voiceover_text=body.voiceover_text,
            use_memory=body.use_memory,
            confirmed_brief=body.confirmed_brief,
            settings_overrides=body.settings_overrides,
            timeline_override=body.timeline_override,
            task_id=body.task_id,
        )

    @app.post("/api/worker/package/load")
    def api_worker_package_load(body: WorkerTaskRunRequest) -> dict[str, Any]:
        return load_worker_task_package(body.package_path)

    @app.post("/api/worker/run")
    def api_worker_run(body: WorkerTaskRunRequest) -> dict[str, Any]:
        return run_worker_task_package(body.package_path)

    @app.post("/api/protocol/build")
    def api_protocol_build(body: ToolkitProtocolBuildRequest) -> dict[str, Any]:
        return write_local_toolkit_protocol(output_dir=body.output_dir)

    @app.post("/api/protocol/inspect")
    def api_protocol_inspect(body: ToolkitProtocolInspectRequest) -> dict[str, Any]:
        return inspect_local_toolkit_path(body.path)

    @app.post("/api/protocol/run")
    def api_protocol_run(body: ToolkitProtocolRunRequest) -> dict[str, Any]:
        return run_protocol_path(
            body.path,
            output_dir=body.output_dir,
            style_package=body.style_package,
            user_request=body.user_request,
            voiceover_text=body.voiceover_text,
            use_memory=body.use_memory,
            confirmed_brief=body.confirmed_brief,
            execute_real_render=body.execute_real_render,
            allow_edge_tts=body.allow_edge_tts,
        )

    @app.post("/api/protocol/dropbox/init")
    def api_protocol_dropbox_init(body: ProtocolDropboxInitRequest) -> dict[str, Any]:
        return initialize_protocol_dropbox(dropbox_dir=body.dropbox_dir)

    @app.post("/api/protocol/dropbox/import")
    def api_protocol_dropbox_import(body: ProtocolDropboxImportRequest) -> dict[str, Any]:
        return import_protocol_dropbox_item(
            dropbox_dir=body.dropbox_dir,
            source_path=body.source_path,
            label=body.label,
        )

    @app.post("/api/protocol/dropbox/run")
    def api_protocol_dropbox_run(body: ProtocolDropboxRunRequest) -> dict[str, Any]:
        return run_protocol_dropbox_once(
            dropbox_dir=body.dropbox_dir,
            default_execute_real_render=body.default_execute_real_render,
            stop_on_error=body.stop_on_error,
            max_retries=body.max_retries,
            dry_run=body.dry_run,
        )

    @app.post("/api/protocol/dropbox/monitor/start")
    def api_protocol_dropbox_monitor_start(body: ProtocolDropboxMonitorRequest) -> dict[str, Any]:
        return start_protocol_dropbox_monitor(
            dropbox_dir=body.dropbox_dir,
            interval_seconds=body.interval_seconds,
            max_cycles=body.max_cycles,
            default_execute_real_render=body.default_execute_real_render,
            stop_on_error=body.stop_on_error,
            max_retries=body.max_retries,
            dry_run=body.dry_run,
        )

    @app.post("/api/protocol/dropbox/monitor/stop")
    def api_protocol_dropbox_monitor_stop(body: ProtocolDropboxMonitorStatusRequest) -> dict[str, Any]:
        return stop_protocol_dropbox_monitor(dropbox_dir=body.dropbox_dir)

    @app.post("/api/protocol/dropbox/monitor/status")
    def api_protocol_dropbox_monitor_status(body: ProtocolDropboxMonitorStatusRequest) -> dict[str, Any]:
        return get_protocol_dropbox_monitor_status(dropbox_dir=body.dropbox_dir)

    @app.post("/api/protocol/dropbox/history")
    def api_protocol_dropbox_history(body: ProtocolDropboxHistoryRequest) -> dict[str, Any]:
        return get_protocol_dropbox_history(
            dropbox_dir=body.dropbox_dir,
            limit=body.limit,
            queue_id=body.queue_id,
            alerts_only=body.alerts_only,
        )

    @app.post("/api/protocol/dropbox/requeue-failed")
    def api_protocol_dropbox_requeue_failed(body: ProtocolDropboxRequeueRequest) -> dict[str, Any]:
        return requeue_protocol_dropbox_failed(
            dropbox_dir=body.dropbox_dir,
            queue_id=body.queue_id,
            max_files=body.max_files,
        )

    @app.post("/api/director/chat")
    def api_director_chat(body: DirectorChatRequest) -> dict[str, Any]:
        context = dict(body.context)
        context["director_mode"] = body.director_mode
        return chat_with_director(
            message=body.message,
            history=body.history,
            context=context,
        )

    @app.post("/api/filmgen/edit-pack/preview")
    def api_filmgen_edit_pack_preview(body: ExternalEditPackRequest) -> dict[str, Any]:
        return _filmgen_preview_payload(body.manifest_path)

    @app.post("/api/external/edit-pack/preview")
    def api_external_edit_pack_preview(body: ExternalEditPackRequest) -> dict[str, Any]:
        return _external_preview_payload(body.manifest_path)

    @app.post("/api/filmgen/subtitle-handoff/preview")
    def api_filmgen_subtitle_handoff_preview(body: ExternalSubtitleHandoffRequest) -> dict[str, Any]:
        return load_external_subtitle_handoff(body.handoff_path)

    @app.post("/api/external/subtitle-handoff/preview")
    def api_external_subtitle_handoff_preview(body: ExternalSubtitleHandoffRequest) -> dict[str, Any]:
        return load_external_subtitle_handoff(body.handoff_path)

    @app.post("/api/filmgen/export-handoff/validate")
    def api_filmgen_export_handoff_validate(body: ExternalExportHandoffValidationRequest) -> dict[str, Any]:
        return validate_external_export_handoff_import(body.handoff_path)

    @app.post("/api/external/export-handoff/validate")
    def api_external_export_handoff_validate(body: ExternalExportHandoffValidationRequest) -> dict[str, Any]:
        return _external_export_validation_payload(body.handoff_path)

    @app.post("/api/filmgen/edit-brief")
    def api_filmgen_edit_brief(body: ExternalEditPackRequest) -> dict[str, Any]:
        return build_edit_brief_from_external_pack(
            manifest_path=body.manifest_path,
            style_package=body.style_package,
            input_video=body.input_video,
            input_videos=body.input_videos,
            output_dir=body.output_dir,
            user_request=body.user_request,
            settings_overrides=body.settings_overrides,
            execute_real_render=body.execute_real_render,
            use_memory=body.use_memory,
        )

    @app.post("/api/external/edit-brief")
    def api_external_edit_brief(body: ExternalEditPackRequest) -> dict[str, Any]:
        return _external_edit_brief_payload(body)

    @app.post("/api/filmgen/cut")
    def api_filmgen_cut(body: ExternalEditPackRequest) -> dict[str, Any]:
        return run_edit_with_style_package(
            build_local_edit_task_from_external_pack(
                manifest_path=body.manifest_path,
                style_package=body.style_package,
                input_video=body.input_video,
                input_videos=body.input_videos,
                output_dir=body.output_dir,
                user_request=body.user_request,
                settings_overrides=body.settings_overrides,
                confirmed_brief=body.confirmed_brief,
                execute_real_render=body.execute_real_render,
                allow_edge_tts=body.allow_edge_tts,
                use_memory=body.use_memory,
            )
        )

    @app.post("/api/external/cut")
    def api_external_cut(body: ExternalEditPackRequest) -> dict[str, Any]:
        return run_edit_with_style_package(
            build_local_edit_task_from_external_pack(
                manifest_path=body.manifest_path,
                style_package=body.style_package,
                input_video=body.input_video,
                input_videos=body.input_videos,
                output_dir=body.output_dir,
                user_request=body.user_request,
                settings_overrides=body.settings_overrides,
                confirmed_brief=body.confirmed_brief,
                execute_real_render=body.execute_real_render,
                allow_edge_tts=body.allow_edge_tts,
                use_memory=body.use_memory,
            )
        )

    @app.post("/api/material/calibration")
    def api_material_calibration(body: MaterialCalibrationRequest) -> dict[str, Any]:
        return calibrate_visual_role_thresholds(
            samples=body.samples,
            sample_set_path=body.sample_set_path,
            sample_set=body.sample_set,
            baseline_threshold=body.baseline_threshold,
        )

    @app.post("/api/cut")
    def api_cut(body: CutRequest) -> dict[str, Any]:
        user_request = body.user_request
        primary_input = _primary_input_video(body.input_video, body.input_videos)
        input_videos = _input_video_paths(primary_input, body.input_videos)
        return run_edit_with_style_package(
            LocalEditTask(
                style_package=Path(body.style_package),
                input_video=Path(primary_input),
                input_videos=[Path(path) for path in input_videos],
                output_dir=Path(body.output_dir),
                user_request=user_request,
                project_id=body.project_id,
                execute_real_render=body.execute_real_render,
                allow_edge_tts=body.allow_edge_tts,
                voiceover_text=body.voiceover_text,
                use_memory=body.use_memory,
                settings_overrides=body.settings_overrides,
                confirmed_brief=body.confirmed_brief,
                timeline_override=body.timeline_override,
                task_id=body.task_id,
            )
        )

    @app.get("/api/recent-runs")
    def api_recent_runs(limit: int = 20) -> dict[str, Any]:
        return list_recent_runs(limit=limit)

    @app.delete("/api/recent-runs")
    def api_delete_recent_run(result_json: str) -> dict[str, Any]:
        return delete_recent_run(result_json=result_json)

    @app.get("/api/projects")
    def api_projects(query: str = "", limit: int = 50) -> dict[str, Any]:
        return list_project_library(query=query, limit=limit)

    @app.get("/api/projects/detail")
    def api_project_detail(output_dir: str = "") -> dict[str, Any]:
        if not output_dir:
            return {"ok": False, "error": "output_dir is required"}
        return get_project_from_library(output_dir=output_dir)

    @app.post("/api/projects/rebuild")
    def api_projects_rebuild(body: ProjectLibraryRebuildRequest) -> dict[str, Any]:
        return rebuild_project_library(output_root=body.output_root, limit=body.limit)

    @app.post("/api/folders/scan")
    def api_folder_scan(body: FolderScanRequest) -> dict[str, Any]:
        if body.scan_type == "output":
            return scan_output_folder(folder=body.folder, recursive=body.recursive, limit=body.limit)
        return scan_media_folder(folder=body.folder, recursive=body.recursive, limit=body.limit)

    @app.get("/api/repair-dialogue")
    def api_repair_threads(output_dir: str = "", limit: int = 50) -> dict[str, Any]:
        return list_repair_threads(output_dir=output_dir, limit=limit)

    @app.get("/api/deployment/guide")
    def api_deployment_guide() -> dict[str, Any]:
        return local_deployment_guide()

    @app.get("/api/media-preview")
    def api_media_preview(path: str) -> Any:
        media_path = Path(path)
        if media_path.suffix.casefold() not in {
            ".png",
            ".jpg",
            ".jpeg",
            ".webp",
            ".mp4",
            ".mov",
            ".mkv",
            ".webm",
            ".wav",
            ".mp3",
            ".m4a",
            ".aac",
            ".flac",
            ".ogg",
        }:
            raise ValueError("unsupported preview media type")
        if not media_path.is_file():
            raise ValueError("media file not found")
        return FileResponse(media_path, media_type=_media_type(media_path))

    @app.post("/api/bgm/library")
    def api_bgm_library(body: BgmLibraryRequest) -> dict[str, Any]:
        return scan_bgm_library(
            library_dir=body.library_dir,
            query=body.query,
            style=body.style,
            limit=body.limit,
        )

    @app.post("/api/bgm/library/playlist")
    def api_bgm_library_playlist(body: BgmLibraryRequest) -> dict[str, Any]:
        return build_bgm_library_playlist(
            library_dir=body.library_dir,
            query=body.query,
            style=body.style,
            limit=body.limit,
            output_path=body.output_path,
        )

    @app.post("/api/voice-profile")
    def api_voice_profile(body: VoiceProfileRequest) -> dict[str, Any]:
        return run_voice_profile_contract(
            output_dir=Path(body.output_dir),
            provider_id=body.provider_id,
            voice_gender=body.voice_gender,
            voice_style=body.voice_style,
            sample_text=body.sample_text,
            sample_outcome=body.sample_outcome,
        )

    @app.post("/api/voice-profile/confirm")
    def api_voice_profile_confirm(body: VoiceProfileConfirmRequest) -> dict[str, Any]:
        return confirm_voice_profile_review(
            output_dir=body.output_dir,
            profile_result_path=body.profile_result_path,
            profile_result=body.profile_result,
            outcome=body.outcome,
            notes=body.notes,
            rating=body.rating,
            prompt_audio_path=body.prompt_audio_path,
            sample_audio_path=body.sample_audio_path,
        )

    @app.get("/api/voice-profile/refs")
    def api_voice_profile_refs(output_dir: str = "") -> dict[str, Any]:
        return list_voice_profile_reviews(output_dir=output_dir)

    @app.get("/api/voice/system-tts/voices")
    def api_system_tts_voices() -> dict[str, Any]:
        return list_system_tts_voices()

    @app.post("/api/voice/system-tts/test")
    def api_system_tts_test(body: SystemTtsPreviewRequest) -> dict[str, Any]:
        return generate_system_tts_preview(
            text=body.text,
            output_dir=body.output_dir or str(Path.cwd() / "workspace" / "system-tts-preview"),
            voice_name=body.voice_name,
            rate=body.rate,
            volume=body.volume,
        )

    # -----------------------------------------------------------------------
    # Task 1: Card-style timeline endpoints (3 endpoints)
    # -----------------------------------------------------------------------

    @app.post("/api/timeline")
    def api_timeline(body: TimelineRequest) -> dict[str, Any]:
        """Generate a timeline preview from style package and materials."""
        package = load_style_package(body.style_package)
        brief = build_edit_brief(
            style_package=body.style_package,
            input_video=_primary_input_video(body.input_video, body.input_videos),
            input_videos=body.input_videos,
            output_dir=body.output_dir,
            user_request=body.user_request,
            settings_overrides=body.settings_overrides,
        )
        timeline = build_timeline_plan(
            material_plan=brief.get("material_plan", {}),
            settings=brief.get("settings", {}),
            style_package=package,
        )
        errors = timeline.validate()
        return {
            "ok": len(errors) == 0,
            "timeline": timeline.to_dict(),
            "toolkit_format": timeline_to_toolkit_format(timeline),
            "validation_errors": errors,
        }

    @app.post("/api/timeline/edit")
    def api_timeline_edit(body: TimelineEditRequest) -> dict[str, Any]:
        """Apply user edit operations to a timeline."""
        base = TimelinePlan.from_dict(body.base_timeline)
        updated = apply_user_edits(base_timeline=base, edits=body.edits) if body.edits else base
        errors = updated.validate()
        payload: dict[str, Any] = {
            "ok": len(errors) == 0,
            "timeline": updated.to_dict(),
            "toolkit_format": timeline_to_toolkit_format(updated),
            "validation_errors": errors,
        }
        if body.output_dir:
            entry = save_version(
                output_dir=body.output_dir,
                timeline=updated.to_dict(),
                brief={"source": "timeline_workbench", "user_feedback": body.user_feedback},
                result=None,
                user_feedback=body.user_feedback or "timeline_workbench_edit",
                edit_operations=body.edits,
                status="timeline_edit",
            )
            write_project_manifest(
                output_dir=body.output_dir,
                timeline=updated.to_dict(),
                event="timeline_edit",
            )
            payload["saved_version"] = entry.to_dict()
            payload["project_manifest_path"] = str(Path(body.output_dir) / "project_manifest.json")
        return payload

    @app.post("/api/timeline/validate")
    def api_timeline_validate(body: TimelineValidateRequest) -> dict[str, Any]:
        """Validate a timeline plan."""
        plan = TimelinePlan.from_dict(body.timeline)
        errors = plan.validate()
        return {
            "ok": len(errors) == 0,
            "validation_errors": errors,
            "total_duration": plan.total_duration(),
            "segment_count": len(plan.segments),
        }

    # -----------------------------------------------------------------------
    # Task 3: Task status center endpoints (3 endpoints)
    # -----------------------------------------------------------------------

    @app.get("/api/tasks")
    def api_list_tasks(project_id: str = "", limit: int = 50) -> dict[str, Any]:
        """List task statuses with optional project_id filter."""
        tasks = list_task_statuses(project_id=project_id, limit=limit)
        return {
            "schema": "smart_video_cut.local.task_list.v0",
            "count": len(tasks),
            "tasks": tasks,
        }

    @app.get("/api/tasks/{task_id}")
    def api_task_detail(task_id: str) -> dict[str, Any]:
        """Get task detail by task_id."""
        status = get_task_status(task_id)
        if status is None:
            return {"ok": False, "error": f"task_not_found: {task_id}"}
        return status

    @app.get("/api/tasks/{task_id}/stages/{stage_id}")
    def api_task_stage_detail(task_id: str, stage_id: str) -> dict[str, Any]:
        """Get detail for a specific stage of a task."""
        status = get_task_status(task_id)
        if status is None:
            return {"ok": False, "error": f"task_not_found: {task_id}"}
        stages = status.get("stages") or []
        for stage in stages:
            if stage.get("stage_id") == stage_id:
                return {"ok": True, "task_id": task_id, "stage": stage}
        return {"ok": False, "error": f"stage_not_found: {stage_id}"}

    # -----------------------------------------------------------------------
    # Task 4: Version history endpoints (4 endpoints)
    # -----------------------------------------------------------------------

    @app.get("/api/versions")
    def api_list_versions(output_dir: str = "") -> dict[str, Any]:
        """List version history for an output directory."""
        if not output_dir:
            return {"ok": False, "error": "output_dir is required"}
        return get_version_history(output_dir)

    @app.get("/api/versions/{version}")
    def api_version_detail(version: int, output_dir: str = "") -> dict[str, Any]:
        """Get detail for a specific version."""
        if not output_dir:
            return {"ok": False, "error": "output_dir is required"}
        result = get_version(output_dir, version)
        if result is None:
            return {"ok": False, "error": f"version_not_found: {version}"}
        return result

    @app.post("/api/versions/revert")
    def api_version_revert(output_dir: str = "", version: int = 0) -> dict[str, Any]:
        """Revert to a specific version."""
        if not output_dir:
            return {"ok": False, "error": "output_dir is required"}
        result = revert_to_version(output_dir, version)
        if result.get("ok"):
            write_project_manifest(
                output_dir=output_dir,
                timeline=result.get("timeline") if isinstance(result.get("timeline"), dict) else None,
                event="version_reverted",
            )
            result["project_manifest_path"] = str(Path(output_dir) / "project_manifest.json")
        return result

    @app.get("/api/project-manifest")
    def api_project_manifest(output_dir: str = "") -> dict[str, Any]:
        """Read the project manifest for an output directory."""
        if not output_dir:
            return {"ok": False, "error": "output_dir is required"}
        manifest = read_project_manifest(output_dir)
        if manifest is None:
            return {"ok": False, "error": "project_manifest_not_found"}
        return {"ok": True, "manifest": manifest}

    @app.post("/api/versions/re-edit")
    def api_version_re_edit(body: ReEditRequest) -> dict[str, Any]:
        """Create a new version based on an existing version + user feedback."""
        base = get_version(body.output_dir, body.base_version)
        if base is None:
            return {"ok": False, "error": f"base_version_not_found: {body.base_version}"}

        base_timeline = base.get("timeline") or {}
        if body.timeline_edits and base_timeline:
            plan = TimelinePlan.from_dict(base_timeline)
            updated = apply_user_edits(base_timeline=plan, edits=body.timeline_edits)
            new_timeline = updated.to_dict()
        else:
            new_timeline = base_timeline

        entry = save_version(
            output_dir=body.output_dir,
            timeline=new_timeline,
            brief=base.get("brief"),
            result=None,
            user_feedback=body.user_feedback,
            edit_operations=body.timeline_edits,
            status="pending_re_render",
        )
        write_project_manifest(
            output_dir=body.output_dir,
            timeline=new_timeline if isinstance(new_timeline, dict) else None,
            event="version_re_edit",
        )
        return {
            "ok": True,
            "status": "pending_re_render",
            "new_version": entry.version,
            "timeline": new_timeline,
            "needs_render": True,
            "project_manifest_path": str(Path(body.output_dir) / "project_manifest.json"),
        }

    @app.post("/api/repair-dialogue")
    def api_repair_dialogue(body: ReEditRequest) -> dict[str, Any]:
        """Record a repair dialogue turn and create a pending re-render version."""
        result = api_version_re_edit(body)
        if result.get("ok"):
            result["repair_thread"] = record_repair_thread(
                output_dir=body.output_dir,
                base_version=body.base_version,
                user_feedback=body.user_feedback,
                result=result,
            ).get("repair_thread")
        return result

    # -----------------------------------------------------------------------
    # Task 5: Pack management endpoints (5 endpoints)
    # -----------------------------------------------------------------------

    @app.get("/api/packs")
    def api_list_packs(base_dir: str = "") -> dict[str, Any]:
        """List all packs grouped by type."""
        packs = discover_packs(base_dir=base_dir if base_dir else None)
        return {
            "schema": "smart_video_cut.local.pack_index.v0",
            **packs,
        }

    @app.post("/api/packs/material")
    def api_create_material_pack(body: MaterialPackRequest) -> dict[str, Any]:
        """Create a material pack."""
        pack = create_material_pack(
            name=body.name,
            package_dir=body.package_dir,
            reference_video_path=body.reference_video_path,
            description=body.description,
            thumbnail_paths=body.thumbnail_paths,
        )
        return {"ok": True, "pack": pack}

    @app.post("/api/packs/style")
    def api_create_style_pack(body: StylePackRequest) -> dict[str, Any]:
        """Create a v1 style pack."""
        pack = create_style_pack(
            name=body.name,
            package_dir=body.package_dir,
            visible_settings=body.visible_settings,
            timeline_template=body.timeline_template,
            edit_brief_profile=body.edit_brief_profile,
            render_overrides=body.render_overrides,
            description=body.description,
        )
        return {"ok": True, "pack": pack}

    @app.post("/api/packs/project")
    def api_create_project_pack(body: ProjectPackRequest) -> dict[str, Any]:
        """Create a project pack."""
        pack = create_project_pack(
            name=body.name,
            package_dir=body.package_dir,
            material_pack_ref=body.material_pack_ref,
            style_pack_ref=body.style_pack_ref,
            input_videos=body.input_videos,
            output_dir=body.output_dir,
            project_settings_overrides=body.project_settings_overrides,
            source_output_dir=body.source_output_dir,
            project_manifest=body.project_manifest,
            timeline_plan=body.timeline_plan,
            version_history=body.version_history,
            artifact_refs=body.artifact_refs,
        )
        return {"ok": True, "pack": pack}

    @app.post("/api/packs/project/export")
    def api_export_project_pack(body: ProjectPackExportRequest) -> dict[str, Any]:
        """Export an output directory into a project pack."""
        return export_project_pack_adapter(
            output_dir=body.output_dir,
            package_dir=body.package_dir,
            name=body.name,
            material_pack_ref=body.material_pack_ref,
            style_pack_ref=body.style_pack_ref,
            project_settings_overrides=body.project_settings_overrides,
        )

    @app.get("/api/packs/load")
    def api_load_pack(path: str = "") -> dict[str, Any]:
        """Load a pack JSON from a file or directory."""
        if not path:
            return {"ok": False, "error": "path is required"}
        pack = load_pack(path)
        return {"ok": True, "pack": pack, "validation": validate_pack_references(pack)}

    @app.post("/api/packs/resolve")
    def api_resolve_pack(body: ResolvePackRequest) -> dict[str, Any]:
        """Resolve a project pack into merged configuration."""
        resolved = resolve_project_pack(body.project_pack)
        return {"ok": True, "resolved": resolved}

    @app.post("/api/packs/validate")
    def api_validate_pack(body: PackValidateRequest) -> dict[str, Any]:
        """Validate pack references and schema."""
        return {"ok": True, "validation": validate_pack_references(body.pack)}

    # -----------------------------------------------------------------------
    # Task 6: Agent tool interface endpoints (3 endpoints)
    # -----------------------------------------------------------------------

    @app.get("/api/agent/tools")
    def api_agent_tools_manifest() -> dict[str, Any]:
        """Return the agent tool registry manifest."""
        registry = build_default_registry()
        return registry.to_manifest()

    @app.get("/api/agent/tools/{tool_id}")
    def api_agent_tool_detail(tool_id: str) -> dict[str, Any]:
        """Get detail for a specific agent tool."""
        registry = build_default_registry()
        tool = registry.get_tool(tool_id)
        if tool is None:
            return {"ok": False, "error": f"tool_not_found: {tool_id}"}
        return tool

    @app.post("/api/agent/tools/{tool_id}/invoke")
    def api_agent_tool_invoke(tool_id: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
        """Invoke an agent tool with provided parameters."""
        registry = build_default_registry()
        params = body if isinstance(body, dict) else {}
        return registry.invoke(tool_id, **params)

    return app


def save_voice_sample(*, data: bytes, filename: str) -> dict[str, Any]:
    if not data:
        return {"ok": False, "reason": "empty_audio_upload"}
    root = Path(__file__).resolve().parents[2] / "workspace" / "voice_samples"
    root.mkdir(parents=True, exist_ok=True)
    safe_name = _safe_filename(filename or "voice-sample.webm")
    stem = Path(safe_name).stem or "voice-sample"
    suffix = Path(safe_name).suffix.casefold() or ".webm"
    raw_path = root / f"{int(time.time())}_{stem}{suffix}"
    raw_path.write_bytes(data)
    wav_path = root / f"{raw_path.stem}.wav"
    converted = _convert_voice_sample_to_wav(raw_path, wav_path)
    selected_path = wav_path if converted else raw_path
    return {
        "ok": True,
        "raw_audio_path": str(raw_path),
        "prompt_audio_path": str(selected_path),
        "converted_to_wav": converted,
        "size_bytes": selected_path.stat().st_size if selected_path.is_file() else raw_path.stat().st_size,
        "mime_type": _media_type(selected_path),
    }


def list_moss_tts_samples(output_dir: str | Path) -> list[dict[str, Any]]:
    root = Path(output_dir)
    if not root.exists():
        return []
    samples: list[dict[str, Any]] = []
    for audio_path in root.glob("moss_tts_sample_*.wav"):
        if not audio_path.is_file():
            continue
        metadata_path = audio_path.with_suffix(".json")
        metadata = _read_json_file(metadata_path)
        stat = audio_path.stat()
        created_at = metadata.get("created_at") or stat.st_mtime
        samples.append(
            {
                "audio_path": str(audio_path),
                "filename": audio_path.name,
                "metadata_path": str(metadata_path) if metadata_path.is_file() else None,
                "created_at": created_at,
                "voice": metadata.get("voice") or "",
                "profile": metadata.get("profile") or "",
                "sample_mode": metadata.get("sample_mode") or "",
                "text_preview": metadata.get("text_preview") or "",
                "prompt_audio_path": metadata.get("prompt_audio_path") or "",
                "size_bytes": stat.st_size,
            }
        )
    return sorted(samples, key=lambda item: float(item.get("created_at") or 0), reverse=True)


def _moss_tts_sample_output_path(*, output_dir: Path, voice: str, profile: str) -> Path:
    timestamp = time.strftime("%Y%m%d_%H%M%S")
    millis = int((time.time() % 1) * 1000)
    voice_part = _safe_filename_part(voice or "voice")
    profile_part = _safe_filename_part(profile or "profile")
    return output_dir / f"moss_tts_sample_{timestamp}_{millis:03d}_{voice_part}_{profile_part}.wav"


def _write_moss_tts_sample_metadata(
    *,
    output_dir: Path,
    output_path: Path,
    body: MossTtsTestRequest,
    result: dict[str, Any],
) -> dict[str, Any] | None:
    if result.get("ok") is not True or not output_path.is_file():
        return None
    metadata = {
        "schema": "smart_video_cut.local.moss_tts_sample.v0",
        "created_at": time.time(),
        "audio_path": str(output_path),
        "voice": body.voice,
        "profile": body.profile,
        "sample_mode": body.sample_mode,
        "text_temperature": body.text_temperature,
        "audio_temperature": body.audio_temperature,
        "seed": body.seed,
        "prompt_audio_path": body.prompt_audio_path or "",
        "text_preview": str(body.text or "")[:120],
        "size_bytes": output_path.stat().st_size,
    }
    metadata_path = output_path.with_suffix(".json")
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return {
        **metadata,
        "metadata_path": str(metadata_path),
        "filename": output_path.name,
        "output_dir": str(output_dir),
    }


def _read_json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _safe_filename_part(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "_", str(value or "").strip())[:32] or "item"


def _convert_voice_sample_to_wav(source_path: Path, wav_path: Path) -> bool:
    if source_path.suffix.casefold() == ".wav":
        return False
    try:
        from video_editing_toolkit.creative_edit_runner import _binary_path  # type: ignore

        ffmpeg = _binary_path("ffmpeg")
    except Exception:
        ffmpeg = None
    if not ffmpeg:
        return False
    completed = subprocess.run(
        [
            ffmpeg,
            "-hide_banner",
            "-nostdin",
            "-y",
            "-i",
            str(source_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            str(wav_path),
        ],
        capture_output=True,
        check=False,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=60,
    )
    return completed.returncode == 0 and wav_path.is_file() and wav_path.stat().st_size > 1000


def _safe_filename(value: str) -> str:
    name = Path(value).name
    return re.sub(r"[^A-Za-z0-9._-]+", "_", name)[:80] or "voice-sample.webm"


def main() -> int:
    import uvicorn

    uvicorn.run(create_app(), host="127.0.0.1", port=8769)
    return 0


def _media_type(path: Path) -> str:
    return {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".mp4": "video/mp4",
        ".mov": "video/quicktime",
        ".mkv": "video/x-matroska",
        ".webm": "video/webm",
        ".wav": "audio/wav",
        ".mp3": "audio/mpeg",
        ".m4a": "audio/mp4",
        ".aac": "audio/aac",
        ".flac": "audio/flac",
        ".ogg": "audio/ogg",
    }.get(path.suffix.casefold(), "application/octet-stream")


def _primary_input_video(input_video: str, input_videos: list[str]) -> str:
    text = str(input_video or "").strip()
    if text:
        return text
    for item in input_videos:
        selected = str(item or "").strip()
        if selected:
            return selected
    raise ValueError("input_video or input_videos is required")


def _input_video_paths(input_video: str, input_videos: list[str]) -> list[str]:
    paths: list[str] = []
    for item in [input_video, *input_videos]:
        selected = str(item or "").strip()
        if selected and selected not in paths:
            paths.append(selected)
    return paths


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
