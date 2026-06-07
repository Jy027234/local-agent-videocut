from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
import json
from pathlib import Path
import sqlite3
from typing import Any
from uuid import uuid4

from .models import DEFAULT_PROVIDERS, MODEL_PIPELINE_SLOTS, WORKFLOW_STEPS, utc_now


class NotFoundError(KeyError):
    pass


class ApprovalRequiredError(RuntimeError):
    def __init__(self, step_key: str) -> None:
        super().__init__("approval_required")
        self.step_key = step_key


class FilmStore:
    def __init__(self, db_path: str | Path, *, data_dir: str | Path | None = None) -> None:
        self.db_path = Path(db_path)
        self.data_dir = Path(data_dir) if data_dir is not None else self.db_path.parent
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.initialize()

    def initialize(self) -> None:
        with self._connection() as conn:
            conn.executescript(
                """
                PRAGMA foreign_keys = ON;

                CREATE TABLE IF NOT EXISTS projects (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    logline TEXT NOT NULL DEFAULT '',
                    format TEXT NOT NULL DEFAULT 'short',
                    target_duration_seconds INTEGER NOT NULL DEFAULT 60,
                    state TEXT NOT NULL DEFAULT 'idea',
                    current_step TEXT NOT NULL DEFAULT 'idea',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    archived_at TEXT
                );

                CREATE TABLE IF NOT EXISTS workflow_steps (
                    project_id TEXT NOT NULL,
                    step_key TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    label TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'pending',
                    approval_required INTEGER NOT NULL DEFAULT 0,
                    approved_at TEXT,
                    note TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (project_id, step_key),
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS shots (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    position INTEGER NOT NULL,
                    title TEXT NOT NULL,
                    summary TEXT NOT NULL DEFAULT '',
                    duration_seconds INTEGER NOT NULL DEFAULT 5,
                    location TEXT NOT NULL DEFAULT '',
                    camera TEXT NOT NULL DEFAULT '',
                    prompt TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'draft',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE
                );

                CREATE TABLE IF NOT EXISTS assets (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    shot_id TEXT,
                    type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    file_path TEXT NOT NULL DEFAULT '',
                    provider TEXT NOT NULL DEFAULT '',
                    model TEXT NOT NULL DEFAULT '',
                    prompt TEXT NOT NULL DEFAULT '',
                    seed TEXT NOT NULL DEFAULT '',
                    cost REAL NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'registered',
                    metadata_json TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    FOREIGN KEY (shot_id) REFERENCES shots(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS providers (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    kind TEXT NOT NULL,
                    base_url TEXT NOT NULL DEFAULT '',
                    api_key_env TEXT NOT NULL DEFAULT '',
                    model_catalog_json TEXT NOT NULL DEFAULT '{}',
                    pricing_json TEXT NOT NULL DEFAULT '{}',
                    enabled INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS model_pipeline_config (
                    slot_key TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    role TEXT NOT NULL,
                    stage TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    model TEXT NOT NULL DEFAULT '',
                    enabled INTEGER NOT NULL DEFAULT 1,
                    settings_json TEXT NOT NULL DEFAULT '{}',
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (provider_id) REFERENCES providers(id)
                );

                CREATE TABLE IF NOT EXISTS generation_tasks (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    shot_id TEXT,
                    stage TEXT NOT NULL,
                    provider_id TEXT NOT NULL,
                    model TEXT NOT NULL DEFAULT '',
                    prompt TEXT NOT NULL DEFAULT '',
                    negative_prompt TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'queued',
                    approval_required INTEGER NOT NULL DEFAULT 0,
                    risk_level TEXT NOT NULL DEFAULT 'low',
                    risk_flags_json TEXT NOT NULL DEFAULT '[]',
                    cost_estimate REAL NOT NULL DEFAULT 0,
                    output_asset_id TEXT,
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    FOREIGN KEY (shot_id) REFERENCES shots(id) ON DELETE SET NULL,
                    FOREIGN KEY (provider_id) REFERENCES providers(id),
                    FOREIGN KEY (output_asset_id) REFERENCES assets(id) ON DELETE SET NULL
                );

                CREATE TABLE IF NOT EXISTS api_call_ledger (
                    id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL,
                    task_id TEXT,
                    provider_id TEXT NOT NULL,
                    model TEXT NOT NULL DEFAULT '',
                    operation TEXT NOT NULL,
                    status TEXT NOT NULL,
                    estimated_cost REAL NOT NULL DEFAULT 0,
                    actual_cost REAL NOT NULL DEFAULT 0,
                    request_ref TEXT NOT NULL DEFAULT '',
                    response_ref TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    FOREIGN KEY (project_id) REFERENCES projects(id) ON DELETE CASCADE,
                    FOREIGN KEY (task_id) REFERENCES generation_tasks(id) ON DELETE SET NULL,
                    FOREIGN KEY (provider_id) REFERENCES providers(id)
                );
                """
            )
            now = utc_now()
            for provider in DEFAULT_PROVIDERS:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO providers (
                        id, name, kind, base_url, api_key_env,
                        model_catalog_json, pricing_json, enabled, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        provider["id"],
                        provider["name"],
                        provider["kind"],
                        provider.get("base_url", ""),
                        provider.get("api_key_env", ""),
                        _json_dumps(provider.get("model_catalog", {})),
                        _json_dumps(provider.get("pricing", {})),
                        1 if provider.get("enabled") else 0,
                        now,
                        now,
                    ),
                )
            for slot in MODEL_PIPELINE_SLOTS:
                conn.execute(
                    """
                    INSERT OR IGNORE INTO model_pipeline_config (
                        slot_key, label, role, stage, provider_id, model,
                        enabled, settings_json, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, 1, '{}', ?)
                    """,
                    (
                        slot["key"],
                        slot["label"],
                        slot["role"],
                        slot["stage"],
                        slot["default_provider_id"],
                        slot["default_model"],
                        now,
                    ),
                )

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        conn = self._connect()
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def bootstrap(self) -> dict[str, Any]:
        projects = self.list_projects()
        active_project = self.get_project(projects[0]["id"]) if projects else None
        return {
            "projects": projects,
            "active_project": active_project,
            "providers": self.list_providers(),
            "workflow_template": [step.__dict__ for step in WORKFLOW_STEPS],
        }

    def list_projects(self) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT
                    p.*,
                    (SELECT COUNT(*) FROM shots s WHERE s.project_id = p.id) AS shot_count,
                    (SELECT COUNT(*) FROM assets a WHERE a.project_id = p.id) AS asset_count,
                    (SELECT COALESCE(SUM(l.actual_cost), 0) FROM api_call_ledger l WHERE l.project_id = p.id) AS actual_cost
                FROM projects p
                ORDER BY p.updated_at DESC
                """
            ).fetchall()
        return [_project_row_to_dict(row) for row in rows]

    def get_project(self, project_id: str) -> dict[str, Any]:
        with self._connection() as conn:
            project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            if project is None:
                raise NotFoundError(project_id)
            payload = _row_to_dict(project)
            payload["workflow"] = [_row_to_dict(row) for row in conn.execute(
                "SELECT * FROM workflow_steps WHERE project_id = ? ORDER BY position",
                (project_id,),
            )]
            payload["shots"] = [_row_to_dict(row) for row in conn.execute(
                "SELECT * FROM shots WHERE project_id = ? ORDER BY position, created_at",
                (project_id,),
            )]
            payload["assets"] = [_asset_row_to_dict(row) for row in conn.execute(
                "SELECT * FROM assets WHERE project_id = ? ORDER BY created_at DESC, rowid DESC",
                (project_id,),
            )]
            payload["tasks"] = [_task_row_to_dict(row) for row in conn.execute(
                "SELECT * FROM generation_tasks WHERE project_id = ? ORDER BY created_at DESC",
                (project_id,),
            )]
            payload["ledger"] = [_row_to_dict(row) for row in conn.execute(
                "SELECT * FROM api_call_ledger WHERE project_id = ? ORDER BY created_at DESC LIMIT 100",
                (project_id,),
            )]
        payload["totals"] = self.project_totals(project_id)
        return payload

    def project_totals(self, project_id: str) -> dict[str, Any]:
        with self._connection() as conn:
            row = conn.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM shots WHERE project_id = ?) AS shot_count,
                    (SELECT COUNT(*) FROM assets WHERE project_id = ?) AS asset_count,
                    (SELECT COUNT(*) FROM generation_tasks WHERE project_id = ?) AS task_count,
                    (SELECT COALESCE(SUM(actual_cost), 0) FROM api_call_ledger WHERE project_id = ?) AS actual_cost,
                    (SELECT COALESCE(SUM(cost_estimate), 0) FROM generation_tasks WHERE project_id = ?) AS estimated_cost
                """,
                (project_id, project_id, project_id, project_id, project_id),
            ).fetchone()
        return _row_to_dict(row) if row is not None else {}

    def create_project(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        project_id = str(payload.get("id") or uuid4())
        title = str(payload.get("title") or "未命名短片").strip()
        logline = str(payload.get("logline") or "").strip()
        project_format = str(payload.get("format") or "short").strip() or "short"
        target_duration = _int_value(payload.get("target_duration_seconds"), default=60, minimum=5)
        with self._connection() as conn:
            conn.execute(
                """
                INSERT INTO projects (
                    id, title, logline, format, target_duration_seconds,
                    state, current_step, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, 'idea', 'idea', ?, ?)
                """,
                (project_id, title, logline, project_format, target_duration, now, now),
            )
            for position, step in enumerate(WORKFLOW_STEPS):
                status = "in_progress" if position == 0 else "pending"
                conn.execute(
                    """
                    INSERT INTO workflow_steps (
                        project_id, step_key, position, label, status,
                        approval_required, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        project_id,
                        step.key,
                        position,
                        step.label,
                        status,
                        1 if step.approval_required else 0,
                        now,
                    ),
                )
        return self.get_project(project_id)

    def update_project(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = ("title", "logline", "format", "target_duration_seconds")
        assignments: list[str] = []
        values: list[Any] = []
        for key in allowed:
            if key in payload:
                assignments.append(f"{key} = ?")
                values.append(payload[key])
        if assignments:
            assignments.append("updated_at = ?")
            values.append(utc_now())
            values.append(project_id)
            with self._connection() as conn:
                conn.execute(f"UPDATE projects SET {', '.join(assignments)} WHERE id = ?", values)
        return self.get_project(project_id)

    def advance_project(self, project_id: str) -> dict[str, Any]:
        now = utc_now()
        with self._connection() as conn:
            project = conn.execute("SELECT * FROM projects WHERE id = ?", (project_id,)).fetchone()
            if project is None:
                raise NotFoundError(project_id)
            current_key = str(project["current_step"])
            steps = conn.execute(
                "SELECT * FROM workflow_steps WHERE project_id = ? ORDER BY position",
                (project_id,),
            ).fetchall()
            current_index = next((index for index, row in enumerate(steps) if row["step_key"] == current_key), None)
            if current_index is None:
                raise NotFoundError(current_key)
            current = steps[current_index]
            if current["approval_required"] and not current["approved_at"]:
                conn.execute(
                    "UPDATE workflow_steps SET status = 'blocked', updated_at = ? WHERE project_id = ? AND step_key = ?",
                    (now, project_id, current_key),
                )
                raise ApprovalRequiredError(current_key)
            conn.execute(
                "UPDATE workflow_steps SET status = 'completed', updated_at = ? WHERE project_id = ? AND step_key = ?",
                (now, project_id, current_key),
            )
            if current_index + 1 >= len(steps):
                conn.execute(
                    """
                    UPDATE projects
                    SET state = 'archive', current_step = 'archive', archived_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (now, now, project_id),
                )
            else:
                next_step = steps[current_index + 1]
                conn.execute(
                    """
                    UPDATE workflow_steps
                    SET status = 'in_progress', updated_at = ?
                    WHERE project_id = ? AND step_key = ?
                    """,
                    (now, project_id, next_step["step_key"]),
                )
                conn.execute(
                    "UPDATE projects SET state = ?, current_step = ?, updated_at = ? WHERE id = ?",
                    (next_step["step_key"], next_step["step_key"], now, project_id),
                )
        return self.get_project(project_id)

    def approve_workflow_step(self, project_id: str, step_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        approved = _bool_value(payload.get("approved"), default=True)
        note = str(payload.get("note") or "").strip()
        with self._connection() as conn:
            row = conn.execute(
                "SELECT * FROM workflow_steps WHERE project_id = ? AND step_key = ?",
                (project_id, step_key),
            ).fetchone()
            if row is None:
                raise NotFoundError(step_key)
            status = "in_progress" if row["status"] == "blocked" and approved else row["status"]
            conn.execute(
                """
                UPDATE workflow_steps
                SET approved_at = ?, note = ?, status = ?, updated_at = ?
                WHERE project_id = ? AND step_key = ?
                """,
                (now if approved else None, note, status, now, project_id, step_key),
            )
        return self.get_project(project_id)

    def sync_workflow_progress(
        self,
        project_id: str,
        *,
        completed_steps: set[str],
        current_step: str,
        approval_notes: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        now = utc_now()
        approval_notes = approval_notes or {}
        with self._connection() as conn:
            steps = conn.execute(
                "SELECT * FROM workflow_steps WHERE project_id = ? ORDER BY position",
                (project_id,),
            ).fetchall()
            if not steps:
                raise NotFoundError(project_id)
            known_steps = {str(row["step_key"]) for row in steps}
            if current_step not in known_steps:
                raise NotFoundError(current_step)
            for row in steps:
                step_key = str(row["step_key"])
                status = "completed" if step_key in completed_steps else "in_progress" if step_key == current_step else "pending"
                approved_at = now if step_key in approval_notes and not row["approved_at"] else row["approved_at"]
                note = approval_notes.get(step_key, row["note"] or "")
                conn.execute(
                    """
                    UPDATE workflow_steps
                    SET status = ?, approved_at = ?, note = ?, updated_at = ?
                    WHERE project_id = ? AND step_key = ?
                    """,
                    (status, approved_at, note, now, project_id, step_key),
                )
            conn.execute(
                "UPDATE projects SET state = ?, current_step = ?, updated_at = ? WHERE id = ?",
                (current_step, current_step, now, project_id),
            )
        return self.get_project(project_id)

    def create_shot(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        shot_id = str(payload.get("id") or uuid4())
        with self._connection() as conn:
            if conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
                raise NotFoundError(project_id)
            position = payload.get("position")
            if position is None:
                position = conn.execute(
                    "SELECT COALESCE(MAX(position), 0) + 1 FROM shots WHERE project_id = ?",
                    (project_id,),
                ).fetchone()[0]
            conn.execute(
                """
                INSERT INTO shots (
                    id, project_id, position, title, summary, duration_seconds,
                    location, camera, prompt, status, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    shot_id,
                    project_id,
                    _int_value(position, default=1, minimum=1),
                    str(payload.get("title") or f"镜头 {position}").strip(),
                    str(payload.get("summary") or "").strip(),
                    _int_value(payload.get("duration_seconds"), default=5, minimum=1),
                    str(payload.get("location") or "").strip(),
                    str(payload.get("camera") or "").strip(),
                    str(payload.get("prompt") or "").strip(),
                    str(payload.get("status") or "draft").strip() or "draft",
                    now,
                    now,
                ),
            )
            conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
        return self.get_project(project_id)

    def update_shot(self, shot_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        allowed = ("position", "title", "summary", "duration_seconds", "location", "camera", "prompt", "status")
        assignments: list[str] = []
        values: list[Any] = []
        now = utc_now()
        project_id = None
        with self._connection() as conn:
            row = conn.execute("SELECT project_id FROM shots WHERE id = ?", (shot_id,)).fetchone()
            if row is None:
                raise NotFoundError(shot_id)
            project_id = row["project_id"]
            for key in allowed:
                if key in payload:
                    assignments.append(f"{key} = ?")
                    values.append(payload[key])
            if assignments:
                assignments.append("updated_at = ?")
                values.append(now)
                values.append(shot_id)
                conn.execute(f"UPDATE shots SET {', '.join(assignments)} WHERE id = ?", values)
                conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
        return self.get_project(str(project_id))

    def replace_project_shots(self, project_id: str, shots: list[dict[str, Any]]) -> dict[str, Any]:
        now = utc_now()
        with self._connection() as conn:
            if conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
                raise NotFoundError(project_id)
            conn.execute("DELETE FROM shots WHERE project_id = ?", (project_id,))
            for index, shot in enumerate(shots, start=1):
                position = _int_value(shot.get("position"), default=index, minimum=1)
                conn.execute(
                    """
                    INSERT INTO shots (
                        id, project_id, position, title, summary, duration_seconds,
                        location, camera, prompt, status, created_at, updated_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        str(shot.get("id") or uuid4()),
                        project_id,
                        position,
                        str(shot.get("title") or f"镜头 {position}").strip(),
                        str(shot.get("summary") or "").strip(),
                        _int_value(shot.get("duration_seconds"), default=5, minimum=1),
                        str(shot.get("location") or "").strip(),
                        str(shot.get("camera") or "").strip(),
                        str(shot.get("prompt") or shot.get("video_prompt") or shot.get("image_prompt") or "").strip(),
                        str(shot.get("status") or "approved").strip() or "approved",
                        now,
                        now,
                    ),
                )
            conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
        return self.get_project(project_id)

    def create_asset(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        asset = self._insert_asset(project_id, payload)
        return self.get_project(project_id)

    def get_asset(self, asset_id: str) -> dict[str, Any]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
        if row is None:
            raise NotFoundError(asset_id)
        return _asset_row_to_dict(row)

    def update_asset(self, asset_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
            if row is None:
                raise NotFoundError(asset_id)
            project_id = str(row["project_id"])
            metadata = _json_loads(row["metadata_json"], {})
            incoming_metadata = payload.get("metadata")
            if isinstance(incoming_metadata, dict):
                metadata.update(incoming_metadata)
            allowed = ("title", "file_path", "prompt", "status")
            assignments: list[str] = []
            values: list[Any] = []
            for key in allowed:
                if key in payload:
                    assignments.append(f"{key} = ?")
                    values.append(str(payload.get(key) or "").strip())
            if isinstance(incoming_metadata, dict):
                assignments.append("metadata_json = ?")
                values.append(_json_dumps(metadata))
            if assignments:
                values.append(asset_id)
                conn.execute(f"UPDATE assets SET {', '.join(assignments)} WHERE id = ?", values)
                conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
        return self.get_project(project_id)

    def delete_asset(self, asset_id: str) -> dict[str, Any]:
        now = utc_now()
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM assets WHERE id = ?", (asset_id,)).fetchone()
            if row is None:
                raise NotFoundError(asset_id)
            asset = _asset_row_to_dict(row)
            project_id = str(row["project_id"])
            conn.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
            conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
        return asset

    def _insert_asset(self, project_id: str, payload: dict[str, Any], conn: sqlite3.Connection | None = None) -> str:
        owns_conn = conn is None
        conn = conn or self._connect()
        try:
            if conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
                raise NotFoundError(project_id)
            now = utc_now()
            asset_id = str(payload.get("id") or uuid4())
            conn.execute(
                """
                INSERT INTO assets (
                    id, project_id, shot_id, type, title, file_path, provider,
                    model, prompt, seed, cost, status, metadata_json, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    asset_id,
                    project_id,
                    _empty_to_none(payload.get("shot_id")),
                    str(payload.get("type") or "manifest").strip(),
                    str(payload.get("title") or "未命名资产").strip(),
                    str(payload.get("file_path") or "").strip(),
                    str(payload.get("provider") or "").strip(),
                    str(payload.get("model") or "").strip(),
                    str(payload.get("prompt") or "").strip(),
                    str(payload.get("seed") or "").strip(),
                    float(payload.get("cost") or 0),
                    str(payload.get("status") or "registered").strip(),
                    _json_dumps(payload.get("metadata") or {}),
                    now,
                ),
            )
            conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
            if owns_conn:
                conn.commit()
            return asset_id
        finally:
            if owns_conn:
                conn.close()

    def list_providers(self) -> list[dict[str, Any]]:
        with self._connection() as conn:
            rows = conn.execute("SELECT * FROM providers ORDER BY enabled DESC, name").fetchall()
        return [_provider_row_to_dict(row) for row in rows]

    def get_provider(self, provider_id: str) -> dict[str, Any]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM providers WHERE id = ?", (provider_id,)).fetchone()
        if row is None:
            raise NotFoundError(provider_id)
        return _provider_row_to_dict(row)

    def get_model_pipeline_config(self) -> dict[str, Any]:
        with self._connection() as conn:
            rows = conn.execute(
                """
                SELECT c.*, p.name AS provider_name, p.kind AS provider_kind
                FROM model_pipeline_config c
                LEFT JOIN providers p ON p.id = c.provider_id
                ORDER BY
                    CASE c.slot_key
                        WHEN 'planning_model' THEN 1
                        WHEN 'text_to_image_model' THEN 2
                        WHEN 'image_to_video_model' THEN 3
                        ELSE 99
                    END
                """
            ).fetchall()
        return {
            "schema": "aifilm-studio.model-pipeline-config.v1",
            "slots": [_model_slot_row_to_dict(row) for row in rows],
        }

    def update_model_pipeline_config(self, payload: dict[str, Any]) -> dict[str, Any]:
        slot_defs = {str(slot["key"]): slot for slot in MODEL_PIPELINE_SLOTS}
        incoming = payload.get("slots") or []
        if not isinstance(incoming, list):
            incoming = []
        now = utc_now()
        with self._connection() as conn:
            for item in incoming:
                if not isinstance(item, dict):
                    continue
                slot_key = str(item.get("slot_key") or item.get("key") or "").strip()
                slot_def = slot_defs.get(slot_key)
                if slot_def is None:
                    continue
                provider_id = str(item.get("provider_id") or slot_def["default_provider_id"]).strip()
                if conn.execute("SELECT 1 FROM providers WHERE id = ?", (provider_id,)).fetchone() is None:
                    raise NotFoundError(provider_id)
                conn.execute(
                    """
                    UPDATE model_pipeline_config
                    SET provider_id = ?, model = ?, enabled = ?, settings_json = ?, updated_at = ?
                    WHERE slot_key = ?
                    """,
                    (
                        provider_id,
                        str(item.get("model") or "").strip(),
                        1 if _bool_value(item.get("enabled"), default=True) else 0,
                        _json_dumps(item.get("settings") or {}),
                        now,
                        slot_key,
                    ),
                )
        return self.get_model_pipeline_config()

    def upsert_provider(self, payload: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        provider_id = str(payload.get("id") or uuid4()).strip()
        with self._connection() as conn:
            existing = conn.execute("SELECT 1 FROM providers WHERE id = ?", (provider_id,)).fetchone()
            params = (
                str(payload.get("name") or provider_id).strip(),
                str(payload.get("kind") or "custom").strip(),
                str(payload.get("base_url") or "").strip(),
                str(payload.get("api_key_env") or "").strip(),
                _json_dumps(payload.get("model_catalog") or {}),
                _json_dumps(payload.get("pricing") or {}),
                1 if _bool_value(payload.get("enabled"), default=False) else 0,
                now,
                provider_id,
            )
            if existing:
                conn.execute(
                    """
                    UPDATE providers
                    SET name = ?, kind = ?, base_url = ?, api_key_env = ?,
                        model_catalog_json = ?, pricing_json = ?, enabled = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    params,
                )
            else:
                conn.execute(
                    """
                    INSERT INTO providers (
                        name, kind, base_url, api_key_env, model_catalog_json,
                        pricing_json, enabled, updated_at, id, created_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (*params[:-1], provider_id, now),
                )
        return {"providers": self.list_providers()}

    def create_generation_task(self, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        task_id = str(payload.get("id") or uuid4())
        provider_id = str(payload.get("provider_id") or "mock-local")
        risk_level = str(payload.get("risk_level") or "low")
        approval_required = _bool_value(payload.get("approval_required"), default=(risk_level != "low"))
        status = "blocked" if approval_required else "queued"
        with self._connection() as conn:
            if conn.execute("SELECT 1 FROM projects WHERE id = ?", (project_id,)).fetchone() is None:
                raise NotFoundError(project_id)
            if conn.execute("SELECT 1 FROM providers WHERE id = ?", (provider_id,)).fetchone() is None:
                raise NotFoundError(provider_id)
            conn.execute(
                """
                INSERT INTO generation_tasks (
                    id, project_id, shot_id, stage, provider_id, model, prompt,
                    negative_prompt, status, approval_required, risk_level,
                    risk_flags_json, cost_estimate, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    task_id,
                    project_id,
                    _empty_to_none(payload.get("shot_id")),
                    str(payload.get("stage") or "clip").strip(),
                    provider_id,
                    str(payload.get("model") or "").strip(),
                    str(payload.get("prompt") or "").strip(),
                    str(payload.get("negative_prompt") or "").strip(),
                    status,
                    1 if approval_required else 0,
                    risk_level,
                    _json_dumps(payload.get("risk_flags") or []),
                    float(payload.get("cost_estimate") or 0),
                    now,
                    now,
                ),
            )
            conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
        return self.get_project(project_id)

    def get_task(self, task_id: str) -> dict[str, Any]:
        with self._connection() as conn:
            row = conn.execute("SELECT * FROM generation_tasks WHERE id = ?", (task_id,)).fetchone()
        if row is None:
            raise NotFoundError(task_id)
        return _task_row_to_dict(row)

    def approve_generation_task(self, task_id: str) -> dict[str, Any]:
        now = utc_now()
        with self._connection() as conn:
            row = conn.execute("SELECT project_id FROM generation_tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                raise NotFoundError(task_id)
            conn.execute(
                """
                UPDATE generation_tasks
                SET status = 'queued', approval_required = 0, updated_at = ?
                WHERE id = ?
                """,
                (now, task_id),
            )
            project_id = row["project_id"]
        return self.get_project(str(project_id))

    def fail_generation_task(self, task_id: str, error: str) -> dict[str, Any]:
        return self.set_generation_task_status(task_id, "failed", error)

    def set_generation_task_status(self, task_id: str, status: str, error: str = "") -> dict[str, Any]:
        now = utc_now()
        with self._connection() as conn:
            row = conn.execute("SELECT project_id FROM generation_tasks WHERE id = ?", (task_id,)).fetchone()
            if row is None:
                raise NotFoundError(task_id)
            project_id = str(row["project_id"])
            conn.execute(
                """
                UPDATE generation_tasks
                SET status = ?, error = ?, updated_at = ?
                WHERE id = ?
                """,
                (str(status or "failed").strip(), str(error or "").strip(), now, task_id),
            )
            conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
        return self.get_project(project_id)

    def complete_generation_task(self, task_id: str, *, result: dict[str, Any]) -> dict[str, Any]:
        now = utc_now()
        with self._connection() as conn:
            task = conn.execute("SELECT * FROM generation_tasks WHERE id = ?", (task_id,)).fetchone()
            if task is None:
                raise NotFoundError(task_id)
            if task["status"] == "blocked":
                raise ApprovalRequiredError(str(task["stage"]))
            project_id = str(task["project_id"])
            conn.execute(
                "UPDATE generation_tasks SET status = 'running', updated_at = ? WHERE id = ?",
                (now, task_id),
            )
            asset_id = self._insert_asset(
                project_id,
                {
                    "shot_id": task["shot_id"],
                    "type": str(result.get("asset_type") or _asset_type_for_stage(str(task["stage"]))),
                    "title": str(result.get("title") or f"{task['stage']} output"),
                    "file_path": str(result.get("output_file") or ""),
                    "provider": task["provider_id"],
                    "model": task["model"],
                    "prompt": task["prompt"],
                    "cost": float(result.get("actual_cost") if result.get("actual_cost") is not None else task["cost_estimate"] or 0),
                    "status": "generated",
                    "metadata": {"source_task_id": task_id, **dict(result.get("metadata") or {})},
                },
                conn=conn,
            )
            ledger_id = str(uuid4())
            conn.execute(
                """
                INSERT INTO api_call_ledger (
                    id, project_id, task_id, provider_id, model, operation, status,
                    estimated_cost, actual_cost, request_ref, response_ref, created_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'succeeded', ?, ?, ?, ?, ?)
                """,
                (
                    ledger_id,
                    project_id,
                    task_id,
                    task["provider_id"],
                    task["model"],
                    task["stage"],
                    float(task["cost_estimate"] or 0),
                    float(result.get("actual_cost") if result.get("actual_cost") is not None else task["cost_estimate"] or 0),
                    str(result.get("request_ref") or task["prompt"]),
                    str(result.get("response_ref") or result.get("output_file") or ""),
                    now,
                ),
            )
            conn.execute(
                """
                UPDATE generation_tasks
                SET status = 'succeeded', output_asset_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (asset_id, now, task_id),
            )
            conn.execute("UPDATE projects SET updated_at = ? WHERE id = ?", (now, project_id))
        return self.get_project(project_id)

    def complete_mock_task(self, task_id: str, *, output_file: Path) -> dict[str, Any]:
        return self.complete_generation_task(
            task_id,
            result={
                "output_file": output_file,
                "title": "mock output",
                "metadata": {"mock": True},
            },
        )


def _row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    return {key: row[key] for key in row.keys()}


def _project_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = _row_to_dict(row)
    for key in ("shot_count", "asset_count"):
        data[key] = int(data.get(key) or 0)
    data["actual_cost"] = float(data.get("actual_cost") or 0)
    return data


def _provider_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = _row_to_dict(row)
    data["enabled"] = bool(data.get("enabled"))
    data["model_catalog"] = _json_loads(data.pop("model_catalog_json", "{}"), {})
    data["pricing"] = _json_loads(data.pop("pricing_json", "{}"), {})
    return data


def _model_slot_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = _row_to_dict(row)
    data["enabled"] = bool(data.get("enabled"))
    data["settings"] = _json_loads(data.pop("settings_json", "{}"), {})
    return data


def _asset_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = _row_to_dict(row)
    data["metadata"] = _json_loads(data.pop("metadata_json", "{}"), {})
    return data


def _task_row_to_dict(row: sqlite3.Row) -> dict[str, Any]:
    data = _row_to_dict(row)
    data["approval_required"] = bool(data.get("approval_required"))
    data["risk_flags"] = _json_loads(data.pop("risk_flags_json", "[]"), [])
    return data


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def _json_loads(value: str, default: Any) -> Any:
    try:
        return json.loads(value)
    except (TypeError, ValueError):
        return default


def _int_value(value: Any, *, default: int, minimum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, parsed)


def _bool_value(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"1", "true", "yes", "on", "y"}


def _empty_to_none(value: Any) -> Any:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _asset_type_for_stage(stage: str) -> str:
    if stage == "keyframe":
        return "keyframe"
    if stage == "clip":
        return "video"
    if stage == "audio":
        return "audio"
    if stage == "script":
        return "script"
    return "manifest"
