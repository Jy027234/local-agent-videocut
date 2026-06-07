from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from smart_video_cut.bundled_runtime import run_edit_with_style_package
from smart_video_cut.models import LocalEditTask, STYLE_PACK_SCHEMA
from smart_video_cut.pack_manager import create_project_pack, create_style_pack, resolve_project_pack, validate_pack_references
from smart_video_cut.recent_runs import list_recent_runs
from smart_video_cut.style_package import discover_style_packages, load_style_package
from smart_video_cut.timeline_builder import build_timeline_plan
from smart_video_cut.timeline_model import TimelinePlan, TimelineSegment
from smart_video_cut.web_app import create_app


def test_load_style_pack_v1_is_compatible_with_style_package_workflows(tmp_path: Path) -> None:
    create_style_pack(
        name="V1 Style",
        package_dir=tmp_path / "style",
        visible_settings={"video": {"target_duration_seconds": 9}},
        edit_brief_profile={"visual_priority": "突出主体"},
    )

    loaded = load_style_package(tmp_path / "style")

    assert loaded["schema"] == STYLE_PACK_SCHEMA
    assert loaded["visible_settings"]["video"]["target_duration_seconds"] == 9
    assert loaded["visible_settings"]["subtitle"]["font_size"] == 44
    assert loaded["edit_brief"]["visual_priority"] == "突出主体"
    assert loaded["reference_template"] == {}


def test_discover_style_packages_includes_style_pack_v1(tmp_path: Path) -> None:
    create_style_pack(
        name="Discoverable Style",
        package_dir=tmp_path / "style",
        visible_settings={"video": {"target_duration_seconds": 6}},
    )

    packages = discover_style_packages(base_dir=tmp_path)

    assert len(packages) == 1
    assert packages[0]["name"] == "Discoverable Style"
    assert packages[0]["schema"] == STYLE_PACK_SCHEMA
    assert packages[0]["video"]["target_duration_seconds"] == 6


def test_build_timeline_plan_scales_to_target_duration() -> None:
    plan = build_timeline_plan(
        material_plan={"materials": [{"path": "a.mp4"}], "role_source_map": {}},
        settings={"video": {"target_duration_seconds": 5}},
        style_package={},
    )

    assert plan.total_duration() <= 5.05
    assert not any("exceeds_target" in error for error in plan.validate())


def test_build_timeline_plan_copies_material_thumbnail() -> None:
    plan = build_timeline_plan(
        material_plan={
            "materials": [
                {
                    "path": "a.mp4",
                    "visual_profile": {
                        "thumbnail_refs": [
                            {"thumbnail_path": "thumb-a.jpg", "mime_type": "image/jpeg"}
                        ]
                    },
                }
            ],
            "role_source_map": {"overall_door": 0},
        },
        settings={"video": {"target_duration_seconds": 5}},
        style_package={
            "timeline_template": {
                "segment_blueprint": [
                    {"role": "opening_hero", "duration_seconds": 1, "shot_intent": "overall_door"}
                ]
            }
        },
    )

    assert plan.segments[0].thumbnail_path == "thumb-a.jpg"


def test_timeline_api_supports_style_pack_v1(tmp_path: Path) -> None:
    create_style_pack(
        name="API Style",
        package_dir=tmp_path / "style",
        visible_settings={"video": {"target_duration_seconds": 4}},
        timeline_template={
            "segment_blueprint": [
                {"role": "opening_hero", "duration_seconds": 1.5, "shot_intent": "hero_frame"}
            ]
        },
    )
    input_video = tmp_path / "input.mp4"
    input_video.write_bytes(b"video bytes")
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/timeline",
        json={
            "style_package": str(tmp_path / "style"),
            "input_video": str(input_video),
            "input_videos": [str(input_video)],
            "output_dir": str(tmp_path / "out"),
            "user_request": "做个时间线预览。",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["validation_errors"] == []
    assert payload["timeline"]["segments"][0]["shot_intent"] == "hero_frame"
    assert payload["toolkit_format"]["segments"][0]["shot_intent"] == "hero_frame"


def test_timeline_api_returns_structured_400_for_missing_inputs(tmp_path: Path) -> None:
    create_style_pack(name="API Style", package_dir=tmp_path / "style")
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/timeline",
        json={
            "style_package": str(tmp_path / "style"),
            "output_dir": str(tmp_path / "out"),
            "user_request": "缺素材",
        },
    )

    assert response.status_code == 400
    assert response.json() == {
        "ok": False,
        "error": "input_video or input_videos is required",
    }


def test_timeline_edit_api_saves_version_snapshot(tmp_path: Path) -> None:
    base = TimelinePlan(
        target_duration_seconds=4,
        segments=[
            TimelineSegment(
                segment_id="seg_save",
                timeline_start_seconds=0.0,
                duration_seconds=1.0,
                shot_intent="save_test",
            )
        ],
    ).to_dict()
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/timeline/edit",
        json={
            "base_timeline": base,
            "output_dir": str(tmp_path / "out"),
            "user_feedback": "时长 1",
            "edits": [
                {"op": "resize", "segment_id": "seg_save", "duration_seconds": 2.0}
            ],
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["timeline"]["segments"][0]["duration_seconds"] == 2.0
    assert payload["saved_version"]["status"] == "timeline_edit"
    history = client.get("/api/versions", params={"output_dir": str(tmp_path / "out")}).json()
    assert history["current_version"] == 1
    detail = client.get("/api/versions/1", params={"output_dir": str(tmp_path / "out")}).json()
    assert detail["timeline"]["segments"][0]["duration_seconds"] == 2.0
    assert detail["edit_operations"][0]["op"] == "resize"
    manifest = client.get("/api/project-manifest", params={"output_dir": str(tmp_path / "out")}).json()
    assert manifest["ok"] is True
    assert manifest["manifest"]["last_event"] == "timeline_edit"
    assert manifest["manifest"]["version_history"]["current_version"] == 1

    revert = client.post(
        "/api/versions/revert",
        params={"output_dir": str(tmp_path / "out"), "version": 1},
    ).json()
    assert revert["ok"] is True
    assert revert["new_version"] == 2
    reverted_manifest = client.get("/api/project-manifest", params={"output_dir": str(tmp_path / "out")}).json()
    assert reverted_manifest["manifest"]["last_event"] == "version_reverted"
    assert reverted_manifest["manifest"]["version_history"]["current_version"] == 2

    re_edit = client.post(
        "/api/versions/re-edit",
        json={
            "output_dir": str(tmp_path / "out"),
            "base_version": 1,
            "user_feedback": "基于 v1 复剪",
            "timeline_edits": [],
        },
    ).json()
    assert re_edit["ok"] is True
    assert re_edit["new_version"] == 3
    assert re_edit["needs_render"] is True
    re_edit_manifest = client.get("/api/project-manifest", params={"output_dir": str(tmp_path / "out")}).json()
    assert re_edit_manifest["manifest"]["last_event"] == "version_re_edit"
    assert re_edit_manifest["manifest"]["version_history"]["current_version"] == 3


def test_project_pack_export_load_and_resolve(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    base = TimelinePlan(
        target_duration_seconds=4,
        segments=[
            TimelineSegment(
                segment_id="seg_pack",
                timeline_start_seconds=0.0,
                duration_seconds=1.0,
                shot_intent="pack_hero",
                source_file="input.mp4",
            )
        ],
    ).to_dict()
    client = TestClient(create_app(), raise_server_exceptions=False)
    edit = client.post(
        "/api/timeline/edit",
        json={
            "base_timeline": base,
            "output_dir": str(output_dir),
            "user_feedback": "项目包导出测试",
            "edits": [],
        },
    )
    assert edit.status_code == 200

    response = client.post(
        "/api/packs/project/export",
        json={
            "name": "迁移项目包",
            "output_dir": str(output_dir),
            "package_dir": str(tmp_path / "packs" / "case001"),
            "style_pack_ref": "packages/style",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert Path(payload["project_pack_path"]).is_file()
    pack = payload["pack"]
    assert pack["schema"] == "smart_video_cut.local.project_pack.v0"
    assert pack["name"] == "迁移项目包"
    assert pack["style_pack_ref"] == "packages/style"
    assert pack["timeline_plan"]["segments"][0]["shot_intent"] == "pack_hero"
    assert pack["version_history"]["current_version"] == 1
    assert pack["artifact_refs"]["project_manifest"].endswith("project_manifest.json")

    loaded = client.get("/api/packs/load", params={"path": str(tmp_path / "packs" / "case001")}).json()
    assert loaded["ok"] is True
    resolved = client.post("/api/packs/resolve", json={"project_pack": loaded["pack"]}).json()
    assert resolved["ok"] is True
    assert resolved["resolved"]["timeline_plan"]["segments"][0]["segment_id"] == "seg_pack"
    assert resolved["resolved"]["version_history"]["current_version"] == 1


def test_project_pack_validation_reports_missing_references(tmp_path: Path) -> None:
    pack = create_project_pack(
        name="Broken Project",
        package_dir=tmp_path / "broken",
        style_pack_ref=str(tmp_path / "missing-style"),
        material_pack_ref=str(tmp_path / "missing-material"),
        input_videos=[str(tmp_path / "missing-input.mp4")],
        output_dir=str(tmp_path / "missing-output"),
    )

    validation = validate_pack_references(pack)
    codes = {item["code"] for item in validation["warnings"]}

    assert validation["ok"] is True
    assert "style_pack_ref_missing" in codes
    assert "material_pack_ref_missing" in codes
    assert "input_video_missing" in codes
    assert "timeline_plan_empty" in codes
    resolved = resolve_project_pack(pack)
    assert resolved["validation"]["warnings"]


def test_pack_validate_api_reports_unknown_schema() -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/packs/validate",
        json={"pack": {"schema": "unknown.schema", "name": "Bad"}},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["validation"]["ok"] is False
    assert payload["validation"]["errors"][0]["code"] == "unknown_pack_schema"


def test_run_edit_forwards_timeline_override_to_runner(tmp_path: Path, monkeypatch) -> None:
    create_style_pack(
        name="Runtime Style",
        package_dir=tmp_path / "style",
        visible_settings={
            "video": {"target_duration_seconds": 3},
            "subtitle": {"enabled": False},
            "voice": {"mode": "none", "provider": "none"},
            "audio": {"bgm_style": "none", "remove_original_voice": False},
        },
    )
    input_video = tmp_path / "input.mp4"
    input_video.write_bytes(b"input bytes")
    captured: dict[str, object] = {}

    monkeypatch.setattr(
        "smart_video_cut.bundled_runtime.ensure_video_toolkit_available",
        lambda: {"available": True, "source": "test"},
    )
    monkeypatch.setattr(
        "smart_video_cut.bundled_runtime.build_material_plan",
        lambda paths: {
            "material_count": len(paths),
            "materials": [
                {
                    "index": i,
                    "path": str(path),
                    "label": f"素材{i + 1}",
                    "primary_role": "opening_hero",
                    "display_role": "opening_hero",
                    "assignment_source": "order_fallback_role_assignment",
                }
                for i, path in enumerate(paths)
            ],
            "role_source_map": {"opening_hero": 0},
            "strategy": "order_fallback_role_assignment",
        },
    )
    monkeypatch.setattr(
        "smart_video_cut.bundled_runtime.apply_memory_to_user_request",
        lambda user_request, use_memory: (user_request, ""),
    )
    monkeypatch.setattr(
        "smart_video_cut.bundled_runtime._maybe_generate_moss_voiceover",
        lambda **kwargs: {"ok": False},
    )

    import video_editing_toolkit.creative_edit_runner as creative_edit_runner

    def fake_run_creative_edit_runner(**kwargs):
        captured.update(kwargs)
        return {
            "ok": True,
            "workflow_kind": "creative_edit_runner",
            "source_artifact_refs": {},
        }

    monkeypatch.setattr(creative_edit_runner, "run_creative_edit_runner", fake_run_creative_edit_runner)

    timeline_override = TimelinePlan(
        target_duration_seconds=3,
        version=3,
        segments=[
            TimelineSegment(
                segment_id="seg_custom",
                timeline_start_seconds=0.0,
                duration_seconds=1.5,
                shot_intent="custom_hero",
                source_material_index=0,
                source_file=str(input_video),
            )
        ],
    ).to_dict()

    result = run_edit_with_style_package(
        LocalEditTask(
            style_package=tmp_path / "style",
            input_video=input_video,
            output_dir=tmp_path / "out",
            user_request="按自定义时间线执行。",
            execute_real_render=False,
            timeline_override=timeline_override,
        )
    )

    forwarded_timeline = captured["timeline"]
    assert isinstance(forwarded_timeline, dict)
    assert forwarded_timeline["segments"][0]["shot_intent"] == "custom_hero"
    assert result["timeline_plan"]["version"] == 3
    assert result["toolkit_timeline_plan"]["segments"][0]["shot_intent"] == "custom_hero"


def test_recent_runs_include_timeline_plan_for_recut(tmp_path: Path, monkeypatch) -> None:
    output_root = tmp_path / "output"
    run_dir = output_root / "case001"
    run_dir.mkdir(parents=True)
    timeline = TimelinePlan(
        target_duration_seconds=4,
        segments=[
            TimelineSegment(
                segment_id="seg_history",
                timeline_start_seconds=0.0,
                duration_seconds=1.0,
                shot_intent="history_hero",
            )
        ],
    ).to_dict()
    (run_dir / "local_studio_result.json").write_text(
        json.dumps(
            {
                "ok": True,
                "style_package": {"path": "packages/style", "name": "历史风格"},
                "input_video": "input.mp4",
                "input_videos": ["input.mp4"],
                "timeline_plan": timeline,
                "toolkit_summary": {"workflow_kind": "creative_edit_runner"},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (run_dir / "project_manifest.json").write_text(
        json.dumps(
            {
                "schema": "smart_video_cut.local.project_manifest.v0",
                "output_dir": str(run_dir),
                "version_history": {"current_version": 3, "version_count": 3, "versions": []},
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr("smart_video_cut.recent_runs.OUTPUT_ROOT", output_root)

    runs = list_recent_runs()["runs"]

    assert runs[0]["timeline_plan"]["segments"][0]["shot_intent"] == "history_hero"
    assert runs[0]["current_version"] == 3
    assert runs[0]["version_count"] == 3
    assert runs[0]["project_manifest_path"].endswith("project_manifest.json")
