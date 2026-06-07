from __future__ import annotations

import os
import json
from pathlib import Path
from typing import Any
import urllib.error
import urllib.request

from starlette.applications import Starlette
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse
from starlette.routing import Mount, Route
from starlette.staticfiles import StaticFiles

from . import __version__
from .service import (
    approve_clip_asset,
    create_reference_asset,
    approve_planning_draft,
    approve_planning_shot,
    approve_image_asset,
    delete_clip_asset,
    delete_image_asset,
    delete_project_asset,
    export_edit_pack,
    generate_project_clips,
    generate_project_images,
    generate_planning_draft,
    get_clip_review_state,
    get_image_review_state,
    get_planning_version,
    get_planning_review_state,
    regenerate_clip_asset,
    regenerate_image_asset,
    regenerate_planning_shot,
    reorder_project_shots,
    run_generation_task_with_provider,
    run_model_pipeline_probe,
    save_planning_draft,
    scan_prompt,
    smoke_test_provider,
    update_reference_bindings,
)
from .store import ApprovalRequiredError, FilmStore, NotFoundError


def create_app(
    *,
    db_path: str | Path | None = None,
    data_dir: str | Path | None = None,
) -> Starlette:
    resolved_data_dir = Path(data_dir or os.environ.get("AIFILM_STUDIO_HOME") or Path.cwd() / "var" / "aifilm_studio")
    resolved_db_path = Path(db_path or resolved_data_dir / "studio.sqlite3")
    static_dir = Path(__file__).with_name("static")
    store = FilmStore(resolved_db_path, data_dir=resolved_data_dir)
    app = Starlette(
        debug=True,
        routes=[
            Route("/", index, methods=["GET"]),
            Mount("/static", StaticFiles(directory=static_dir), name="static"),
            Route("/health", health, methods=["GET"]),
            Route("/api/bootstrap", bootstrap, methods=["GET"]),
            Route("/api/prompt-risk", prompt_risk, methods=["POST"]),
            Route("/api/projects", list_projects, methods=["GET"]),
            Route("/api/projects", create_project, methods=["POST"]),
            Route("/api/projects/{project_id}", get_project, methods=["GET"]),
            Route("/api/projects/{project_id}", update_project, methods=["PATCH"]),
            Route("/api/projects/{project_id}/workflow/advance", advance_project, methods=["POST"]),
            Route("/api/projects/{project_id}/workflow/{step_key}/approve", approve_workflow_step, methods=["POST"]),
            Route("/api/projects/{project_id}/shots", create_shot, methods=["POST"]),
            Route("/api/projects/{project_id}/shots/reorder", reorder_shots, methods=["POST"]),
            Route("/api/projects/{project_id}/assets", create_asset, methods=["POST"]),
            Route("/api/projects/{project_id}/references", create_reference, methods=["POST"]),
            Route("/api/projects/{project_id}/references/{asset_id}/bindings", update_reference_binding, methods=["PATCH"]),
            Route("/api/projects/{project_id}/generation-tasks", create_generation_task, methods=["POST"]),
            Route("/api/projects/{project_id}/edit-pack", create_edit_pack, methods=["POST"]),
            Route("/api/projects/{project_id}/planning", get_planning, methods=["GET"]),
            Route("/api/projects/{project_id}/planning/generate", generate_planning, methods=["POST"]),
            Route("/api/projects/{project_id}/planning/save", save_planning, methods=["POST"]),
            Route("/api/projects/{project_id}/planning/approve", approve_planning, methods=["POST"]),
            Route("/api/projects/{project_id}/planning/versions/{asset_id}", get_planning_version_route, methods=["GET"]),
            Route("/api/projects/{project_id}/planning/shots/{position:int}/regenerate", regenerate_planning_shot_route, methods=["POST"]),
            Route("/api/projects/{project_id}/planning/shots/{position:int}/approve", approve_planning_shot_route, methods=["POST"]),
            Route("/api/projects/{project_id}/images", get_images, methods=["GET"]),
            Route("/api/projects/{project_id}/images/generate", generate_images, methods=["POST"]),
            Route("/api/projects/{project_id}/images/{asset_id}/approve", approve_image_route, methods=["POST"]),
            Route("/api/projects/{project_id}/images/{asset_id}/regenerate", regenerate_image_route, methods=["POST"]),
            Route("/api/projects/{project_id}/images/{asset_id}", delete_image_route, methods=["DELETE"]),
            Route("/api/projects/{project_id}/clips", get_clips, methods=["GET"]),
            Route("/api/projects/{project_id}/clips/generate", generate_clips, methods=["POST"]),
            Route("/api/projects/{project_id}/clips/{asset_id}/approve", approve_clip_route, methods=["POST"]),
            Route("/api/projects/{project_id}/clips/{asset_id}/regenerate", regenerate_clip_route, methods=["POST"]),
            Route("/api/projects/{project_id}/clips/{asset_id}", delete_clip_route, methods=["DELETE"]),
            Route("/api/projects/{project_id}/assets/{asset_id}", delete_asset_route, methods=["DELETE"]),
            Route("/api/smart-video-cut/defaults", smart_video_cut_defaults, methods=["GET"]),
            Route("/api/smart-video-cut/edit-pack/preview", proxy_smart_video_cut_preview, methods=["POST"]),
            Route("/api/smart-video-cut/edit-brief", proxy_smart_video_cut_edit_brief, methods=["POST"]),
            Route("/api/shots/{shot_id}", update_shot, methods=["PATCH"]),
            Route("/api/providers", list_providers, methods=["GET"]),
            Route("/api/providers", upsert_provider, methods=["POST"]),
            Route("/api/providers/{provider_id}/smoke-test", provider_smoke_test, methods=["POST"]),
            Route("/api/model-pipeline/config", get_model_pipeline_config, methods=["GET"]),
            Route("/api/model-pipeline/config", update_model_pipeline_config, methods=["POST"]),
            Route("/api/model-pipeline/probe", model_pipeline_probe, methods=["POST"]),
            Route("/api/assets/{asset_id}/file", get_asset_file, methods=["GET"]),
            Route("/api/generation-tasks/{task_id}/approve", approve_generation_task, methods=["POST"]),
            Route("/api/generation-tasks/{task_id}/run", run_generation_task, methods=["POST"]),
        ],
    )
    app.state.film_store = store
    app.state.data_dir = resolved_data_dir
    app.state.db_path = resolved_db_path
    app.state.project_root = Path(__file__).resolve().parents[2]
    app.state.smart_video_cut_url = os.environ.get("SMART_VIDEO_CUT_URL", "http://127.0.0.1:8769").rstrip("/")
    return app


async def index(request: Request) -> FileResponse:
    return FileResponse(Path(__file__).with_name("static") / "index.html")


async def health(request: Request) -> JSONResponse:
    return JSONResponse(
        {
            "status": "ok",
            "version": __version__,
            "data_dir": str(request.app.state.data_dir),
            "db_path": str(request.app.state.db_path),
        }
    )


async def bootstrap(request: Request) -> JSONResponse:
    return _json(_store(request).bootstrap())


async def prompt_risk(request: Request) -> JSONResponse:
    payload = await _read_json(request)
    return _json(scan_prompt(str(payload.get("prompt") or "")))


async def list_projects(request: Request) -> JSONResponse:
    return _json({"projects": _store(request).list_projects()})


async def create_project(request: Request) -> JSONResponse:
    payload = await _read_json(request)
    return _json(_store(request).create_project(payload), status_code=201)


async def get_project(request: Request) -> JSONResponse:
    try:
        return _json(_store(request).get_project(request.path_params["project_id"]))
    except NotFoundError:
        return _error("not_found", "Project not found", 404)


async def update_project(request: Request) -> JSONResponse:
    payload = await _read_json(request)
    try:
        project = _store(request).update_project(request.path_params["project_id"], payload)
        return _json(project)
    except NotFoundError:
        return _error("not_found", "Project not found", 404)


async def advance_project(request: Request) -> JSONResponse:
    store = _store(request)
    project_id = request.path_params["project_id"]
    try:
        return _json({"advanced": True, "project": store.advance_project(project_id)})
    except ApprovalRequiredError as exc:
        return _json(
            {
                "advanced": False,
                "error": {
                    "code": "approval_required",
                    "message": "This workflow step requires manual approval before advancing.",
                    "step_key": exc.step_key,
                },
                "project": store.get_project(project_id),
            },
            status_code=409,
        )
    except NotFoundError:
        return _error("not_found", "Project not found", 404)


async def approve_workflow_step(request: Request) -> JSONResponse:
    payload = await _read_json(request)
    try:
        project = _store(request).approve_workflow_step(
            request.path_params["project_id"],
            request.path_params["step_key"],
            payload,
        )
        return _json(project)
    except NotFoundError:
        return _error("not_found", "Workflow step not found", 404)


async def create_shot(request: Request) -> JSONResponse:
    payload = await _read_json(request)
    try:
        project = _store(request).create_shot(request.path_params["project_id"], payload)
        return _json(project, status_code=201)
    except NotFoundError:
        return _error("not_found", "Project not found", 404)


async def update_shot(request: Request) -> JSONResponse:
    payload = await _read_json(request)
    try:
        project = _store(request).update_shot(request.path_params["shot_id"], payload)
        return _json(project)
    except NotFoundError:
        return _error("not_found", "Shot not found", 404)


async def reorder_shots(request: Request) -> JSONResponse:
    payload = await _read_json(request)
    try:
        project = reorder_project_shots(_store(request), request.path_params["project_id"], payload)
        return _json(project)
    except NotFoundError:
        return _error("not_found", "Project not found", 404)
    except ValueError as exc:
        return _error("invalid_shot_order", str(exc), 400)


async def create_asset(request: Request) -> JSONResponse:
    payload = await _read_json(request)
    try:
        project = _store(request).create_asset(request.path_params["project_id"], payload)
        return _json(project, status_code=201)
    except NotFoundError:
        return _error("not_found", "Project not found", 404)


async def create_reference(request: Request) -> JSONResponse:
    payload = await _read_json(request)
    try:
        project = create_reference_asset(_store(request), request.path_params["project_id"], payload)
        return _json(project, status_code=201)
    except NotFoundError:
        return _error("not_found", "Project not found", 404)
    except ValueError as exc:
        return _error("invalid_reference", str(exc), 400)


async def update_reference_binding(request: Request) -> JSONResponse:
    payload = await _read_json(request)
    try:
        project = update_reference_bindings(
            _store(request),
            request.path_params["project_id"],
            request.path_params["asset_id"],
            payload,
        )
        return _json(project)
    except NotFoundError:
        return _error("not_found", "Project not found", 404)
    except ValueError as exc:
        return _error("invalid_reference_binding", str(exc), 400)


async def list_providers(request: Request) -> JSONResponse:
    return _json({"providers": _store(request).list_providers()})


async def upsert_provider(request: Request) -> JSONResponse:
    payload = await _read_json(request)
    return _json(_store(request).upsert_provider(payload), status_code=201)


async def provider_smoke_test(request: Request) -> JSONResponse:
    try:
        return _json(smoke_test_provider(_store(request), request.path_params["provider_id"]))
    except NotFoundError:
        return _error("not_found", "Provider not found", 404)


async def get_model_pipeline_config(request: Request) -> JSONResponse:
    return _json(_store(request).get_model_pipeline_config())


async def update_model_pipeline_config(request: Request) -> JSONResponse:
    payload = await _read_json(request)
    try:
        return _json(_store(request).update_model_pipeline_config(payload))
    except NotFoundError as exc:
        return _error("not_found", f"Provider not found: {exc}", 404)


async def model_pipeline_probe(request: Request) -> JSONResponse:
    payload = await _read_json(request)
    return _json(run_model_pipeline_probe(_store(request), payload))


async def create_generation_task(request: Request) -> JSONResponse:
    payload = await _read_json(request)
    risk = scan_prompt(f"{payload.get('prompt') or ''}\n{payload.get('negative_prompt') or ''}")
    manual_approval = bool(payload.get("approval_required"))
    payload = {
        **payload,
        "risk_level": risk["risk_level"],
        "risk_flags": risk["flags"],
        "approval_required": manual_approval or bool(risk["approval_required"]),
    }
    try:
        project = _store(request).create_generation_task(request.path_params["project_id"], payload)
        return _json({"risk": risk, "project": project}, status_code=201)
    except NotFoundError as exc:
        return _error("not_found", f"Related record not found: {exc}", 404)


async def approve_generation_task(request: Request) -> JSONResponse:
    try:
        return _json(_store(request).approve_generation_task(request.path_params["task_id"]))
    except NotFoundError:
        return _error("not_found", "Generation task not found", 404)


async def run_generation_task(request: Request) -> JSONResponse:
    store = _store(request)
    try:
        task = store.get_task(request.path_params["task_id"])
        return _json(run_generation_task_with_provider(store, task))
    except ApprovalRequiredError:
        return _error("approval_required", "Approve this task before running it.", 409)
    except NotFoundError:
        return _error("not_found", "Generation task not found", 404)
    except RuntimeError as exc:
        return _error("provider_adapter_error", str(exc), 502)


async def create_edit_pack(request: Request) -> JSONResponse:
    try:
        return _json(export_edit_pack(_store(request), request.path_params["project_id"]))
    except NotFoundError:
        return _error("not_found", "Project not found", 404)


async def get_planning(request: Request) -> JSONResponse:
    try:
        return _json(get_planning_review_state(_store(request), request.path_params["project_id"]))
    except NotFoundError:
        return _error("not_found", "Project not found", 404)


async def get_planning_version_route(request: Request) -> JSONResponse:
    try:
        return _json(
            get_planning_version(
                _store(request),
                request.path_params["project_id"],
                request.path_params["asset_id"],
            )
        )
    except NotFoundError:
        return _error("not_found", "Project not found", 404)
    except ValueError as exc:
        return _error("not_found", str(exc), 404)


async def generate_planning(request: Request) -> JSONResponse:
    payload = await _read_json(request)
    try:
        return _json(generate_planning_draft(_store(request), request.path_params["project_id"], payload))
    except NotFoundError:
        return _error("not_found", "Project not found", 404)
    except RuntimeError as exc:
        return _error("provider_adapter_error", str(exc), 502)


async def save_planning(request: Request) -> JSONResponse:
    payload = await _read_json(request)
    try:
        return _json(save_planning_draft(_store(request), request.path_params["project_id"], payload))
    except NotFoundError:
        return _error("not_found", "Project not found", 404)


async def approve_planning(request: Request) -> JSONResponse:
    payload = await _read_json(request)
    try:
        return _json(approve_planning_draft(_store(request), request.path_params["project_id"], payload))
    except NotFoundError:
        return _error("not_found", "Project not found", 404)


async def regenerate_planning_shot_route(request: Request) -> JSONResponse:
    payload = await _read_json(request)
    try:
        return _json(
            regenerate_planning_shot(
                _store(request),
                request.path_params["project_id"],
                int(request.path_params["position"]),
                payload,
            )
        )
    except NotFoundError:
        return _error("not_found", "Project not found", 404)
    except ValueError as exc:
        return _error("not_found", str(exc), 404)


async def approve_planning_shot_route(request: Request) -> JSONResponse:
    payload = await _read_json(request)
    try:
        return _json(
            approve_planning_shot(
                _store(request),
                request.path_params["project_id"],
                int(request.path_params["position"]),
                payload,
            )
        )
    except NotFoundError:
        return _error("not_found", "Project not found", 404)
    except ValueError as exc:
        return _error("not_found", str(exc), 404)


async def get_images(request: Request) -> JSONResponse:
    try:
        return _json(get_image_review_state(_store(request), request.path_params["project_id"]))
    except NotFoundError:
        return _error("not_found", "Project not found", 404)


async def generate_images(request: Request) -> JSONResponse:
    payload = await _read_json(request)
    try:
        return _json(generate_project_images(_store(request), request.path_params["project_id"], payload))
    except NotFoundError as exc:
        return _error("not_found", f"Related record not found: {exc}", 404)
    except ValueError as exc:
        return _error("invalid_state", str(exc), 409)
    except RuntimeError as exc:
        return _error("provider_adapter_error", str(exc), 502)


async def approve_image_route(request: Request) -> JSONResponse:
    payload = await _read_json(request)
    try:
        return _json(approve_image_asset(_store(request), request.path_params["project_id"], request.path_params["asset_id"], payload))
    except NotFoundError:
        return _error("not_found", "Project not found", 404)
    except ValueError as exc:
        return _error("not_found", str(exc), 404)


async def regenerate_image_route(request: Request) -> JSONResponse:
    payload = await _read_json(request)
    try:
        return _json(regenerate_image_asset(_store(request), request.path_params["project_id"], request.path_params["asset_id"], payload))
    except NotFoundError as exc:
        return _error("not_found", f"Related record not found: {exc}", 404)
    except ValueError as exc:
        return _error("invalid_state", str(exc), 409)
    except RuntimeError as exc:
        return _error("provider_adapter_error", str(exc), 502)


async def delete_image_route(request: Request) -> JSONResponse:
    try:
        return _json(delete_image_asset(_store(request), request.path_params["project_id"], request.path_params["asset_id"]))
    except NotFoundError:
        return _error("not_found", "Project not found", 404)
    except ValueError as exc:
        return _error("not_found", str(exc), 404)


async def get_clips(request: Request) -> JSONResponse:
    try:
        return _json(get_clip_review_state(_store(request), request.path_params["project_id"]))
    except NotFoundError:
        return _error("not_found", "Project not found", 404)


async def generate_clips(request: Request) -> JSONResponse:
    payload = await _read_json(request)
    try:
        return _json(generate_project_clips(_store(request), request.path_params["project_id"], payload))
    except NotFoundError as exc:
        return _error("not_found", f"Related record not found: {exc}", 404)
    except ValueError as exc:
        return _error("invalid_state", str(exc), 409)
    except RuntimeError as exc:
        return _error("provider_adapter_error", str(exc), 502)


async def approve_clip_route(request: Request) -> JSONResponse:
    payload = await _read_json(request)
    try:
        return _json(approve_clip_asset(_store(request), request.path_params["project_id"], request.path_params["asset_id"], payload))
    except NotFoundError:
        return _error("not_found", "Project not found", 404)
    except ValueError as exc:
        return _error("not_found", str(exc), 404)


async def regenerate_clip_route(request: Request) -> JSONResponse:
    payload = await _read_json(request)
    try:
        return _json(regenerate_clip_asset(_store(request), request.path_params["project_id"], request.path_params["asset_id"], payload))
    except NotFoundError as exc:
        return _error("not_found", f"Related record not found: {exc}", 404)
    except ValueError as exc:
        return _error("invalid_state", str(exc), 409)
    except RuntimeError as exc:
        return _error("provider_adapter_error", str(exc), 502)


async def delete_clip_route(request: Request) -> JSONResponse:
    try:
        return _json(delete_clip_asset(_store(request), request.path_params["project_id"], request.path_params["asset_id"]))
    except NotFoundError:
        return _error("not_found", "Project not found", 404)
    except ValueError as exc:
        return _error("not_found", str(exc), 404)


async def delete_asset_route(request: Request) -> JSONResponse:
    try:
        return _json(delete_project_asset(_store(request), request.path_params["project_id"], request.path_params["asset_id"]))
    except NotFoundError:
        return _error("not_found", "Project not found", 404)
    except ValueError as exc:
        return _error("not_found", str(exc), 404)


async def get_asset_file(request: Request) -> FileResponse | JSONResponse:
    try:
        asset = _store(request).get_asset(request.path_params["asset_id"])
    except NotFoundError:
        return _error("not_found", "Asset not found", 404)
    path = Path(str(asset.get("file_path") or ""))
    if not path.is_file():
        return _error("not_found", "Asset file not found", 404)
    return FileResponse(path)


async def smart_video_cut_defaults(request: Request) -> JSONResponse:
    root = Path(request.app.state.project_root)
    filmgen_style_package = root / "packages" / "filmgen-cinematic-short"
    door_flash_style_package = root / "packages" / "door-flash-reference"
    default_style_package = (
        filmgen_style_package
        if (filmgen_style_package / "style_package.json").is_file()
        else door_flash_style_package
    )
    default_input_video = default_style_package / "assets" / "reference_template.mp4"
    return _json(
        {
            "schema": "aifilm-studio.smart-video-cut-defaults.v1",
            "base_url": request.app.state.smart_video_cut_url,
            "style_package": str(default_style_package) if (default_style_package / "style_package.json").is_file() else "",
            "input_video": str(default_input_video) if default_input_video.is_file() else "",
            "output_dir": str(root / "workspace" / "output" / "filmgen-bridge-smoke"),
        }
    )


async def proxy_smart_video_cut_preview(request: Request) -> JSONResponse:
    payload = await _read_json(request)
    return await _proxy_smart_video_cut(request, "/api/filmgen/edit-pack/preview", payload)


async def proxy_smart_video_cut_edit_brief(request: Request) -> JSONResponse:
    payload = await _read_json(request)
    return await _proxy_smart_video_cut(request, "/api/filmgen/edit-brief", payload)


async def _proxy_smart_video_cut(request: Request, path: str, payload: dict[str, Any]) -> JSONResponse:
    base_url = str(request.app.state.smart_video_cut_url).rstrip("/")
    try:
        data = await run_in_threadpool(_post_json, f"{base_url}{path}", payload)
    except urllib.error.HTTPError as exc:
        return _error("smart_video_cut_error", _downstream_error_message(exc), 502)
    except (OSError, TimeoutError, ValueError) as exc:
        return _error(
            "smart_video_cut_unavailable",
            f"Cannot reach Smart Video Cut at {base_url}: {exc}",
            502,
        )
    return _json(data)


def _store(request: Request) -> FilmStore:
    return request.app.state.film_store


async def _read_json(request: Request) -> dict[str, Any]:
    if not request.headers.get("content-type", "").startswith("application/json"):
        return {}
    try:
        payload = await request.json()
    except ValueError:
        return {}
    return payload if isinstance(payload, dict) else {}


def _json(payload: dict[str, Any], *, status_code: int = 200) -> JSONResponse:
    return JSONResponse(payload, status_code=status_code)


def _error(code: str, message: str, status_code: int) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message}}, status_code=status_code)


def _post_json(url: str, payload: dict[str, Any]) -> dict[str, Any]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(req, timeout=45) as response:
        raw = response.read()
    if not raw:
        return {"ok": True}
    decoded = json.loads(raw.decode("utf-8"))
    if not isinstance(decoded, dict):
        raise ValueError("Smart Video Cut returned a non-object JSON response.")
    return decoded


def _downstream_error_message(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read()
    except OSError:
        raw = b""
    if raw:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError):
            payload = {}
        if isinstance(payload, dict):
            detail = payload.get("detail") or payload.get("error")
            if isinstance(detail, dict):
                return str(detail.get("message") or detail)
            if detail:
                return str(detail)
    return f"Smart Video Cut returned HTTP {exc.code}."
