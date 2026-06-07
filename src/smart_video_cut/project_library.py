from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Mapping

from smart_video_cut.project_manifest import read_project_manifest


PROJECT_LIBRARY_SCHEMA = "smart_video_cut.local.project_library.v0"
ROOT_DIR = Path(__file__).resolve().parents[2]
WORKSPACE_DIR = ROOT_DIR / "workspace"
DEFAULT_DB_PATH = WORKSPACE_DIR / "local_studio.sqlite3"
DEFAULT_OUTPUT_ROOT = WORKSPACE_DIR / "output"


def project_library_db_path(path: str | Path = "") -> Path:
    return Path(path) if path else DEFAULT_DB_PATH


def ensure_project_library(db_path: str | Path = "") -> Path:
    path = project_library_db_path(db_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS projects (
                project_id TEXT NOT NULL,
                output_dir TEXT NOT NULL PRIMARY KEY,
                style_package_name TEXT NOT NULL DEFAULT '',
                style_package_path TEXT NOT NULL DEFAULT '',
                user_request TEXT NOT NULL DEFAULT '',
                copied_output_video TEXT NOT NULL DEFAULT '',
                input_video_count INTEGER NOT NULL DEFAULT 0,
                current_version INTEGER NOT NULL DEFAULT 0,
                version_count INTEGER NOT NULL DEFAULT 0,
                execute_real_render INTEGER NOT NULL DEFAULT 0,
                ok INTEGER NOT NULL DEFAULT 0,
                updated_at REAL NOT NULL DEFAULT 0,
                last_event TEXT NOT NULL DEFAULT '',
                manifest_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS repair_threads (
                thread_id TEXT NOT NULL PRIMARY KEY,
                output_dir TEXT NOT NULL,
                base_version INTEGER NOT NULL DEFAULT 0,
                user_feedback TEXT NOT NULL DEFAULT '',
                status TEXT NOT NULL DEFAULT 'pending_re_render',
                created_at REAL NOT NULL DEFAULT 0,
                version INTEGER NOT NULL DEFAULT 0,
                result_json TEXT NOT NULL DEFAULT '{}'
            )
            """
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_projects_updated_at ON projects(updated_at DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_repair_threads_output_dir ON repair_threads(output_dir)")
    return path


def index_project_manifest(
    *,
    output_dir: str | Path,
    manifest: Mapping[str, Any] | None = None,
    db_path: str | Path = "",
) -> dict[str, Any]:
    path = ensure_project_library(db_path)
    output_path = Path(output_dir)
    manifest_data = dict(manifest or read_project_manifest(output_path) or {})
    if not manifest_data:
        return {
            "schema": PROJECT_LIBRARY_SCHEMA,
            "ok": False,
            "reason": "project_manifest_not_found",
            "db_path": str(path),
            "output_dir": str(output_path),
        }

    style_package = manifest_data.get("style_package") if isinstance(manifest_data.get("style_package"), Mapping) else {}
    version_history = (
        manifest_data.get("version_history")
        if isinstance(manifest_data.get("version_history"), Mapping)
        else {}
    )
    latest_result = (
        manifest_data.get("latest_result")
        if isinstance(manifest_data.get("latest_result"), Mapping)
        else {}
    )
    row = {
        "project_id": str(manifest_data.get("project_id") or "local_project"),
        "output_dir": str(output_path),
        "style_package_name": str(style_package.get("name") or ""),
        "style_package_path": str(style_package.get("path") or ""),
        "user_request": str(manifest_data.get("user_request") or ""),
        "copied_output_video": str(manifest_data.get("copied_output_video") or ""),
        "input_video_count": int(manifest_data.get("input_video_count") or 0),
        "current_version": int(version_history.get("current_version") or 0),
        "version_count": int(version_history.get("version_count") or len(version_history.get("versions") or [])),
        "execute_real_render": 1 if manifest_data.get("execute_real_render") is True else 0,
        "ok": 1 if latest_result.get("ok") is True else 0,
        "updated_at": float(manifest_data.get("updated_at") or time.time()),
        "last_event": str(manifest_data.get("last_event") or ""),
        "manifest_json": json.dumps(manifest_data, ensure_ascii=False, sort_keys=True),
    }
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO projects (
                project_id, output_dir, style_package_name, style_package_path, user_request,
                copied_output_video, input_video_count, current_version, version_count,
                execute_real_render, ok, updated_at, last_event, manifest_json
            )
            VALUES (
                :project_id, :output_dir, :style_package_name, :style_package_path, :user_request,
                :copied_output_video, :input_video_count, :current_version, :version_count,
                :execute_real_render, :ok, :updated_at, :last_event, :manifest_json
            )
            ON CONFLICT(output_dir) DO UPDATE SET
                project_id=excluded.project_id,
                style_package_name=excluded.style_package_name,
                style_package_path=excluded.style_package_path,
                user_request=excluded.user_request,
                copied_output_video=excluded.copied_output_video,
                input_video_count=excluded.input_video_count,
                current_version=excluded.current_version,
                version_count=excluded.version_count,
                execute_real_render=excluded.execute_real_render,
                ok=excluded.ok,
                updated_at=excluded.updated_at,
                last_event=excluded.last_event,
                manifest_json=excluded.manifest_json
            """,
            row,
        )
    return {
        "schema": PROJECT_LIBRARY_SCHEMA,
        "ok": True,
        "db_path": str(path),
        "project": _project_from_row(row),
    }


def rebuild_project_library(
    *,
    output_root: str | Path = "",
    db_path: str | Path = "",
    limit: int = 500,
) -> dict[str, Any]:
    path = ensure_project_library(db_path)
    root = Path(output_root) if output_root else DEFAULT_OUTPUT_ROOT
    indexed: list[dict[str, Any]] = []
    skipped: list[dict[str, str]] = []
    manifests = sorted(
        root.rglob("project_manifest.json") if root.exists() else [],
        key=lambda item: item.stat().st_mtime,
        reverse=True,
    )
    for manifest_path in manifests[: max(1, int(limit))]:
        result = index_project_manifest(output_dir=manifest_path.parent, db_path=path)
        if result.get("ok"):
            indexed.append(result["project"])
        else:
            skipped.append({"path": str(manifest_path), "reason": str(result.get("reason") or "unknown")})
    return {
        "schema": PROJECT_LIBRARY_SCHEMA,
        "ok": True,
        "db_path": str(path),
        "output_root": str(root),
        "indexed_count": len(indexed),
        "skipped_count": len(skipped),
        "projects": indexed,
        "skipped": skipped,
    }


def list_project_library(
    *,
    db_path: str | Path = "",
    query: str = "",
    limit: int = 50,
) -> dict[str, Any]:
    path = ensure_project_library(db_path)
    params: list[Any] = []
    where = ""
    if query.strip():
        like = f"%{query.strip()}%"
        where = "WHERE project_id LIKE ? OR output_dir LIKE ? OR style_package_name LIKE ? OR user_request LIKE ?"
        params.extend([like, like, like, like])
    params.append(max(1, int(limit)))
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT * FROM projects
            {where}
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    projects = [_project_from_row(dict(row)) for row in rows]
    return {
        "schema": PROJECT_LIBRARY_SCHEMA,
        "ok": True,
        "db_path": str(path),
        "query": query,
        "project_count": len(projects),
        "projects": projects,
    }


def get_project_from_library(*, output_dir: str | Path, db_path: str | Path = "") -> dict[str, Any]:
    path = ensure_project_library(db_path)
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM projects WHERE output_dir = ?", (str(output_dir),)).fetchone()
    if row is None:
        return {"schema": PROJECT_LIBRARY_SCHEMA, "ok": False, "reason": "project_not_indexed"}
    project = _project_from_row(dict(row))
    return {"schema": PROJECT_LIBRARY_SCHEMA, "ok": True, "project": project}


def record_repair_thread(
    *,
    output_dir: str | Path,
    base_version: int,
    user_feedback: str,
    result: Mapping[str, Any],
    db_path: str | Path = "",
) -> dict[str, Any]:
    path = ensure_project_library(db_path)
    version = int(result.get("new_version") or result.get("version") or 0)
    thread_id = f"repair_{Path(output_dir).name}_{base_version}_{int(time.time() * 1000)}"
    row = {
        "thread_id": thread_id,
        "output_dir": str(output_dir),
        "base_version": int(base_version),
        "user_feedback": str(user_feedback or ""),
        "status": str(result.get("status") or "pending_re_render"),
        "created_at": time.time(),
        "version": version,
        "result_json": json.dumps(dict(result), ensure_ascii=False, sort_keys=True),
    }
    with sqlite3.connect(path) as conn:
        conn.execute(
            """
            INSERT INTO repair_threads (
                thread_id, output_dir, base_version, user_feedback, status, created_at, version, result_json
            )
            VALUES (
                :thread_id, :output_dir, :base_version, :user_feedback, :status, :created_at, :version, :result_json
            )
            """,
            row,
        )
    return {"schema": PROJECT_LIBRARY_SCHEMA, "ok": True, "repair_thread": _repair_thread_from_row(row)}


def list_repair_threads(
    *,
    output_dir: str | Path = "",
    db_path: str | Path = "",
    limit: int = 50,
) -> dict[str, Any]:
    path = ensure_project_library(db_path)
    params: list[Any] = []
    where = ""
    if str(output_dir).strip():
        where = "WHERE output_dir = ?"
        params.append(str(output_dir))
    params.append(max(1, int(limit)))
    with sqlite3.connect(path) as conn:
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            f"""
            SELECT * FROM repair_threads
            {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return {
        "schema": PROJECT_LIBRARY_SCHEMA,
        "ok": True,
        "db_path": str(path),
        "repair_threads": [_repair_thread_from_row(dict(row)) for row in rows],
    }


def _project_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    manifest: dict[str, Any] = {}
    try:
        manifest = json.loads(str(row.get("manifest_json") or "{}"))
    except json.JSONDecodeError:
        manifest = {}
    return {
        "project_id": str(row.get("project_id") or ""),
        "output_dir": str(row.get("output_dir") or ""),
        "style_package_name": str(row.get("style_package_name") or ""),
        "style_package_path": str(row.get("style_package_path") or ""),
        "user_request": str(row.get("user_request") or ""),
        "copied_output_video": str(row.get("copied_output_video") or ""),
        "input_video_count": int(row.get("input_video_count") or 0),
        "current_version": int(row.get("current_version") or 0),
        "version_count": int(row.get("version_count") or 0),
        "execute_real_render": int(row.get("execute_real_render") or 0) == 1,
        "ok": int(row.get("ok") or 0) == 1,
        "updated_at": float(row.get("updated_at") or 0.0),
        "last_event": str(row.get("last_event") or ""),
        "project_manifest_path": str(Path(str(row.get("output_dir") or "")) / "project_manifest.json"),
        "project_manifest": manifest,
    }


def _repair_thread_from_row(row: Mapping[str, Any]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    try:
        result = json.loads(str(row.get("result_json") or "{}"))
    except json.JSONDecodeError:
        result = {}
    return {
        "thread_id": str(row.get("thread_id") or ""),
        "output_dir": str(row.get("output_dir") or ""),
        "base_version": int(row.get("base_version") or 0),
        "user_feedback": str(row.get("user_feedback") or ""),
        "status": str(row.get("status") or ""),
        "created_at": float(row.get("created_at") or 0.0),
        "version": int(row.get("version") or 0),
        "result": result,
    }
