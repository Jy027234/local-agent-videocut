from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from fastapi.testclient import TestClient

from smart_video_cut.export_adapters import filmgen_handoff_export_status
from smart_video_cut.external_bridge import (
    build_edit_brief_from_external_pack,
    load_external_edit_pack,
    validate_external_export_handoff_import,
)
from smart_video_cut.filmgen_bridge import (
    build_edit_brief_from_filmgen_pack,
    load_filmgen_edit_pack,
    validate_filmgen_export_handoff_import,
)
from smart_video_cut.models import LocalVisibleSettings, STYLE_PACKAGE_SCHEMA
from smart_video_cut.web_app import create_app


class FilmgenBridgeTest(unittest.TestCase):
    def test_load_manifest_and_build_edit_brief(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            source_video = root / "generated.mp4"
            source_video.write_bytes(b"placeholder video")
            second_video = root / "second.mp4"
            second_video.write_bytes(b"placeholder video")
            style_dir = root / "style"
            style_dir.mkdir()
            (style_dir / "style_package.json").write_text(
                json.dumps(
                    {
                        "schema": STYLE_PACKAGE_SCHEMA,
                        "package_id": "test_style",
                        "name": "测试风格",
                        "visible_settings": LocalVisibleSettings().to_dict(),
                        "reference_template": {"source_label": "none"},
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            manifest = root / "manifest.json"
            manifest.write_text(
                json.dumps(
                    {
                        "schema": "aifilm-studio.edit-pack.v1",
                        "project": {
                            "id": "filmgen-demo",
                            "title": "雨夜便利店",
                            "logline": "一个剪辑师整理 AI 生成镜头。",
                        },
                        "shots": [
                            {
                                "id": "shot-1",
                                "position": 1,
                                "title": "开场",
                                "summary": "主角进入便利店。",
                                "prompt": "雨夜、霓虹、浅景深",
                            },
                            {
                                "id": "shot-2",
                                "position": 2,
                                "title": "结尾",
                                "summary": "主角看向窗外。",
                                "prompt": "雨停、晨光、安静停留",
                            }
                        ],
                        "assets": [
                            {
                                "id": "asset-2",
                                "shot_id": "shot-2",
                                "type": "video",
                                "title": "结尾镜头",
                                "file_path": str(second_video),
                                "status": "generated",
                            },
                            {
                                "id": "asset-1",
                                "shot_id": "shot-1",
                                "type": "video",
                                "title": "开场镜头",
                                "file_path": str(source_video),
                                "status": "generated",
                            }
                        ],
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )

            handoff = load_filmgen_edit_pack(manifest)
            self.assertEqual(handoff["recommended_project_id"], "filmgen-demo")
            self.assertEqual(handoff["input_video_candidates"], [str(source_video), str(second_video)])

            brief = build_edit_brief_from_filmgen_pack(
                manifest_path=manifest,
                style_package=style_dir,
            )
            self.assertTrue(brief["ok"])
            self.assertIn("雨夜便利店", brief["edit_brief"]["brief_text"])

            client = TestClient(create_app())
            preview = client.post("/api/filmgen/edit-pack/preview", json={"manifest_path": str(manifest)})
            self.assertEqual(preview.status_code, 200)
            self.assertEqual(preview.json()["filmgen_handoff"]["recommended_project_id"], "filmgen-demo")

            external_preview = client.post("/api/external/edit-pack/preview", json={"manifest_path": str(manifest)})
            self.assertEqual(external_preview.status_code, 200)
            self.assertEqual(external_preview.json()["external_handoff"]["recommended_project_id"], "filmgen-demo")

            external_handoff = load_external_edit_pack(manifest)
            self.assertEqual(external_handoff["recommended_project_id"], "filmgen-demo")

            external_brief = build_edit_brief_from_external_pack(
                manifest_path=manifest,
                style_package=style_dir,
            )
            self.assertTrue(external_brief["ok"])
            self.assertIn("external_handoff", external_brief)

    def test_load_smart_video_cut_export_handoff(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "out"
            final_video = output_dir / "final.mp4"
            final_video.parent.mkdir(parents=True)
            final_video.write_bytes(b"final video")
            export = filmgen_handoff_export_status(
                output_dir=output_dir,
                summary={
                    "ok": True,
                    "workflow_kind": "creative_edit_runner",
                    "project_id": "svc-project",
                    "creative_objective": "防盗门快闪广告",
                },
                local_mp4={"ok": True, "copied_output_video": str(final_video)},
            )
            handoff_path = Path(export["handoff_path"])

            handoff = load_filmgen_edit_pack(handoff_path)

            self.assertEqual(handoff["source_schema"], "smart_video_cut.local.export_filmgen_handoff.v1")
            self.assertEqual(handoff["source_schema_version"], 1)
            self.assertEqual(handoff["recommended_project_id"], "svc-project")
            self.assertEqual(handoff["recommended_output_dir"], str(output_dir))
            self.assertEqual(handoff["input_video_candidates"], [str(final_video)])
            self.assertEqual(handoff["video_assets"][0]["type"], "final")
            self.assertIn("防盗门快闪广告", handoff["recommended_user_request"])

            validation = validate_filmgen_export_handoff_import(handoff_path)
            self.assertTrue(validation["ok"])
            self.assertEqual(validation["source_schema"], "smart_video_cut.local.export_filmgen_handoff.v1")
            self.assertEqual(validation["input_video_candidate_count"], 1)

            external_validation = validate_external_export_handoff_import(handoff_path)
            self.assertTrue(external_validation["ok"])
            self.assertEqual(external_validation["external_handoff"]["recommended_project_id"], "svc-project")

            client = TestClient(create_app())
            preview = client.post("/api/filmgen/edit-pack/preview", json={"manifest_path": str(handoff_path)})
            self.assertEqual(preview.status_code, 200)
            self.assertEqual(preview.json()["filmgen_handoff"]["input_video_candidates"], [str(final_video)])

            validated = client.post("/api/filmgen/export-handoff/validate", json={"handoff_path": str(handoff_path)})
            self.assertEqual(validated.status_code, 200)
            self.assertTrue(validated.json()["ok"])
            self.assertEqual(validated.json()["input_video_candidate_count"], 1)

            external_validated = client.post("/api/external/export-handoff/validate", json={"handoff_path": str(handoff_path)})
            self.assertEqual(external_validated.status_code, 200)
            self.assertTrue(external_validated.json()["ok"])
            self.assertIn("external_handoff", external_validated.json())

    def test_legacy_local_export_handoff_still_loads_with_warning(self) -> None:
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            output_dir = root / "legacy-out"
            final_video = output_dir / "final.mp4"
            final_video.parent.mkdir(parents=True)
            final_video.write_bytes(b"final video")
            export = filmgen_handoff_export_status(
                output_dir=output_dir,
                summary={"project_id": "legacy-project"},
                local_mp4={"ok": True, "copied_output_video": str(final_video)},
            )
            handoff_path = Path(export["handoff_path"])
            payload = json.loads(handoff_path.read_text(encoding="utf-8"))
            payload["schema"] = "smart_video_cut.local.export_filmgen_handoff.v0"
            payload.pop("schema_version", None)
            handoff_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")

            handoff = load_filmgen_edit_pack(handoff_path)
            validation = validate_filmgen_export_handoff_import(handoff_path)

            self.assertEqual(handoff["source_schema"], "smart_video_cut.local.export_filmgen_handoff.v0")
            self.assertTrue(validation["ok"])
            self.assertTrue(any(item["code"] == "legacy_schema" for item in validation["validation"]["warnings"]))


if __name__ == "__main__":
    unittest.main()
