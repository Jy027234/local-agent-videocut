from __future__ import annotations

import base64
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from starlette.testclient import TestClient

from aifilm_studio.asgi import create_app
from aifilm_studio.provider_adapters import ProviderAdapterPending


class FilmStudioApiTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = TemporaryDirectory()
        data_dir = Path(self.tmp.name)
        self.client = TestClient(create_app(data_dir=data_dir))
        self.data_dir = data_dir

    def tearDown(self) -> None:
        self.client.close()
        self.tmp.cleanup()

    def test_project_workflow_task_and_edit_pack_flow(self) -> None:
        created = self.client.post(
            "/api/projects",
            json={
                "title": "雨夜便利店",
                "logline": "一个失眠剪辑师在雨夜发现一卷不存在的素材。",
                "target_duration_seconds": 45,
            },
        )
        self.assertEqual(created.status_code, 201)
        project = created.json()
        project_id = project["id"]
        self.assertEqual(project["current_step"], "idea")

        advanced = self.client.post(f"/api/projects/{project_id}/workflow/advance")
        self.assertEqual(advanced.status_code, 200)
        self.assertEqual(advanced.json()["project"]["current_step"], "script_draft")

        advanced = self.client.post(f"/api/projects/{project_id}/workflow/advance")
        self.assertEqual(advanced.status_code, 200)
        self.assertEqual(advanced.json()["project"]["current_step"], "storyboard_review")

        blocked = self.client.post(f"/api/projects/{project_id}/workflow/advance")
        self.assertEqual(blocked.status_code, 409)
        self.assertEqual(blocked.json()["error"]["code"], "approval_required")

        approved = self.client.post(
            f"/api/projects/{project_id}/workflow/storyboard_review/approve",
            json={"approved": True, "note": "分镜通过"},
        )
        self.assertEqual(approved.status_code, 200)
        advanced = self.client.post(f"/api/projects/{project_id}/workflow/advance")
        self.assertEqual(advanced.status_code, 200)
        self.assertEqual(advanced.json()["project"]["current_step"], "keyframe_generation")

        with_shot = self.client.post(
            f"/api/projects/{project_id}/shots",
            json={
                "title": "雨夜街口",
                "summary": "主角撑伞走进便利店灯光。",
                "duration_seconds": 6,
                "camera": "低机位缓慢推进",
                "prompt": "雨夜、霓虹反光、浅景深",
            },
        )
        self.assertEqual(with_shot.status_code, 201)
        shot_id = with_shot.json()["shots"][0]["id"]

        task_result = self.client.post(
            f"/api/projects/{project_id}/generation-tasks",
            json={
                "shot_id": shot_id,
                "stage": "clip",
                "provider_id": "mock-local",
                "model": "clip-placeholder",
                "prompt": "像明星刘德华一样的雨夜便利店镜头",
                "cost_estimate": 1.25,
                "approval_required": False,
            },
        )
        self.assertEqual(task_result.status_code, 201)
        payload = task_result.json()
        self.assertEqual(payload["risk"]["risk_level"], "high")
        task = payload["project"]["tasks"][0]
        self.assertEqual(task["status"], "blocked")

        run_blocked = self.client.post(f"/api/generation-tasks/{task['id']}/run")
        self.assertEqual(run_blocked.status_code, 409)

        approved_task = self.client.post(f"/api/generation-tasks/{task['id']}/approve")
        self.assertEqual(approved_task.status_code, 200)
        run_task = self.client.post(f"/api/generation-tasks/{task['id']}/run")
        self.assertEqual(run_task.status_code, 200)
        run_payload = run_task.json()
        self.assertTrue(Path(run_payload["output_file"]).exists())
        self.assertEqual(run_payload["project"]["tasks"][0]["status"], "succeeded")
        self.assertGreaterEqual(len(run_payload["project"]["assets"]), 1)

        exported = self.client.post(f"/api/projects/{project_id}/edit-pack")
        self.assertEqual(exported.status_code, 200)
        edit_pack = exported.json()["edit_pack"]
        self.assertTrue(Path(edit_pack["manifest_path"]).exists())
        self.assertTrue(Path(edit_pack["handoff_path"]).exists())
        self.assertTrue((Path(edit_pack["directory"]) / "shots.csv").exists())

    def test_smart_video_cut_defaults_and_preview_proxy(self) -> None:
        defaults = self.client.get("/api/smart-video-cut/defaults")
        self.assertEqual(defaults.status_code, 200)
        self.assertEqual(defaults.json()["base_url"], "http://127.0.0.1:8769")
        self.assertEqual(Path(defaults.json()["style_package"]).name, "filmgen-cinematic-short")

        with patch("aifilm_studio.asgi.urllib.request.urlopen") as urlopen:
            response = urlopen.return_value.__enter__.return_value
            response.read.return_value = b'{"schema":"smart_video_cut.local.filmgen_preview.v0","ok":true}'
            proxied = self.client.post(
                "/api/smart-video-cut/edit-pack/preview",
                json={"manifest_path": "workspace/filmgen_studio/edit_packs/demo/manifest.json"},
            )

        self.assertEqual(proxied.status_code, 200)
        self.assertTrue(proxied.json()["ok"])
        request = urlopen.call_args.args[0]
        self.assertTrue(request.full_url.endswith("/api/filmgen/edit-pack/preview"))
        self.assertIn(b"manifest_path", request.data)

    def test_mock_provider_smoke_test_covers_text_image_video(self) -> None:
        response = self.client.post("/api/providers/mock-local/smoke-test")
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["ok"])
        self.assertEqual([row["family"] for row in payload["results"]], ["text", "image", "video"])
        self.assertTrue(all(row["status"] == "succeeded" for row in payload["results"]))
        for row in payload["results"]:
            self.assertTrue(Path(row["output_file"]).exists())

    def test_model_pipeline_config_and_probe_cover_three_product_slots(self) -> None:
        config = self.client.get("/api/model-pipeline/config")
        self.assertEqual(config.status_code, 200)
        slot_keys = [slot["slot_key"] for slot in config.json()["slots"]]
        self.assertEqual(slot_keys, ["planning_model", "text_to_image_model", "image_to_video_model"])

        saved = self.client.post(
            "/api/model-pipeline/config",
            json={
                "slots": [
                    {
                        "slot_key": "planning_model",
                        "provider_id": "mock-local",
                        "model": "storyboard-draft-local",
                        "settings": {
                            "base_url": "https://example.test/v1",
                            "api_key_env": "FILMGEN_TEST_KEY",
                            "api_key_file": "D:\\keys\\filmgen.txt",
                        },
                    },
                    {"slot_key": "text_to_image_model", "provider_id": "mock-local", "model": "keyframe-placeholder"},
                    {"slot_key": "image_to_video_model", "provider_id": "mock-local", "model": "clip-placeholder"},
                ]
            },
        )
        self.assertEqual(saved.status_code, 200)
        planning_slot = saved.json()["slots"][0]
        self.assertEqual(planning_slot["settings"]["api_key_env"], "FILMGEN_TEST_KEY")
        self.assertEqual(planning_slot["settings"]["api_key_file"], "D:\\keys\\filmgen.txt")

        probe = self.client.post("/api/model-pipeline/probe", json=saved.json())
        self.assertEqual(probe.status_code, 200)
        payload = probe.json()
        self.assertTrue(payload["ok"])
        self.assertEqual([row["slot_key"] for row in payload["results"]], slot_keys)
        self.assertEqual([row["role"] for row in payload["results"]], ["planning", "text_to_image", "image_to_video"])
        for row in payload["results"]:
            self.assertEqual(row["status"], "succeeded")
            self.assertTrue(Path(row["output_file"]).exists())

    def test_planning_review_generate_save_and_approve_syncs_storyboard(self) -> None:
        project = self.client.post(
            "/api/projects",
            json={"title": "策划验收短片", "logline": "一个创作者逐级验收 AI 生成结果。"},
        ).json()
        project_id = project["id"]

        initial = self.client.get(f"/api/projects/{project_id}/planning")
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.json()["status"], "not_started")

        generated = self.client.post(f"/api/projects/{project_id}/planning/generate", json={})
        self.assertEqual(generated.status_code, 200)
        generated_payload = generated.json()
        self.assertEqual(generated_payload["status"], "draft")
        self.assertGreaterEqual(len(generated_payload["planning_draft"]["storyboard"]), 3)

        draft = generated_payload["planning_draft"]
        draft["storyboard"] = [
            {
                "position": 1,
                "title": "用户检查策划稿",
                "duration_seconds": 4,
                "summary": "用户确认故事和镜头方向。",
                "location": "工作台",
                "camera": "屏幕录制式推进",
                "image_prompt": "本地工作台，策划稿卡片",
                "video_prompt": "镜头缓慢推进到策划稿确认按钮",
            }
        ]
        saved = self.client.post(f"/api/projects/{project_id}/planning/save", json={"planning_draft": draft})
        self.assertEqual(saved.status_code, 200)
        self.assertEqual(saved.json()["status"], "draft")
        self.assertGreaterEqual(len(saved.json()["versions"]), 2)

        regenerated = self.client.post(
            f"/api/projects/{project_id}/planning/shots/1/regenerate",
            json={"planning_draft": draft, "issue": "weak_camera"},
        )
        self.assertEqual(regenerated.status_code, 200)
        regenerated_shot = regenerated.json()["planning_draft"]["storyboard"][0]
        self.assertEqual(regenerated_shot["status"], "needs_review")
        self.assertIn("镜头动作", regenerated_shot["video_prompt"])

        shot_approved = self.client.post(
            f"/api/projects/{project_id}/planning/shots/1/approve",
            json={"planning_draft": regenerated.json()["planning_draft"]},
        )
        self.assertEqual(shot_approved.status_code, 200)
        self.assertEqual(shot_approved.json()["planning_draft"]["storyboard"][0]["status"], "approved")
        version_id = shot_approved.json()["versions"][0]["asset_id"]
        planning_version = self.client.get(f"/api/projects/{project_id}/planning/versions/{version_id}")
        self.assertEqual(planning_version.status_code, 200)
        self.assertEqual(planning_version.json()["version"]["asset_id"], version_id)
        self.assertEqual(planning_version.json()["planning_draft"]["storyboard"][0]["status"], "approved")

        approved = self.client.post(
            f"/api/projects/{project_id}/planning/approve",
            json={"planning_draft": shot_approved.json()["planning_draft"]},
        )
        self.assertEqual(approved.status_code, 200)
        approved_payload = approved.json()
        self.assertEqual(approved_payload["status"], "approved")
        self.assertIn("用户检查策划稿", approved_payload["project"]["shots"][0]["title"])
        self.assertEqual(approved_payload["project"]["shots"][0]["status"], "approved")
        self.assertEqual(approved_payload["project"]["current_step"], "keyframe_generation")
        storyboard_step = next(step for step in approved_payload["project"]["workflow"] if step["step_key"] == "storyboard_review")
        self.assertEqual(storyboard_step["status"], "completed")
        self.assertTrue(storyboard_step["approved_at"])
        self.assertTrue(
            any(
                asset["metadata"].get("artifact_kind") == "planning_draft"
                and asset["metadata"].get("review_status") == "approved"
                for asset in approved_payload["project"]["assets"]
            )
        )

    def test_mock_adapter_runs_three_model_families_as_generation_tasks(self) -> None:
        project = self.client.post(
            "/api/projects",
            json={"title": "三类模型联调", "logline": "测试文本、关键帧和视频三类生成。"},
        ).json()
        project_id = project["id"]
        shot = self.client.post(
            f"/api/projects/{project_id}/shots",
            json={"title": "工作台", "prompt": "本地生成中枢 UI"},
        ).json()["shots"][0]

        stages = [
            ("script", "storyboard-draft-local", "script"),
            ("keyframe", "keyframe-placeholder", "keyframe"),
            ("clip", "clip-placeholder", "video"),
        ]
        for stage, model, asset_type in stages:
            created = self.client.post(
                f"/api/projects/{project_id}/generation-tasks",
                json={
                    "shot_id": shot["id"],
                    "stage": stage,
                    "provider_id": "mock-local",
                    "model": model,
                    "prompt": f"{stage} smoke prompt",
                },
            )
            self.assertEqual(created.status_code, 201)
            task = next(
                item
                for item in created.json()["project"]["tasks"]
                if item["stage"] == stage and item["status"] == "queued"
            )
            run = self.client.post(f"/api/generation-tasks/{task['id']}/run")
            self.assertEqual(run.status_code, 200)
            self.assertEqual(run.json()["model_family"], {"script": "text", "keyframe": "image", "clip": "video"}[stage])
            assets = run.json()["project"]["assets"]
            self.assertTrue(any(asset["type"] == asset_type for asset in assets))

    def test_image_review_generates_and_approves_keyframe(self) -> None:
        project = self.client.post(
            "/api/projects",
            json={"title": "图片验收短片", "logline": "一个单镜头爱情故事。"},
        ).json()
        project_id = project["id"]
        shot = self.client.post(
            f"/api/projects/{project_id}/shots",
            json={
                "title": "黄昏牵手",
                "summary": "两个人在公园黄昏牵手微笑。",
                "prompt": "夕阳公园，一对原创恋人牵手，电影感",
                "status": "approved",
            },
        ).json()["shots"][0]

        initial = self.client.get(f"/api/projects/{project_id}/images")
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.json()["status"], "not_started")
        self.assertEqual(initial.json()["items"][0]["status"], "missing")

        generated = self.client.post(f"/api/projects/{project_id}/images/generate", json={"shot_id": shot["id"]})
        self.assertEqual(generated.status_code, 200)
        generated_payload = generated.json()
        self.assertEqual(generated_payload["status"], "needs_review")
        asset = generated_payload["items"][0]["latest_asset"]
        self.assertEqual(asset["type"], "keyframe")
        self.assertEqual(asset["metadata"]["review_status"], "needs_review")
        self.assertTrue(Path(asset["file_path"]).exists())

        file_response = self.client.get(f"/api/assets/{asset['id']}/file")
        self.assertEqual(file_response.status_code, 200)

        approved = self.client.post(f"/api/projects/{project_id}/images/{asset['id']}/approve", json={})
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["status"], "approved")
        self.assertEqual(approved.json()["items"][0]["latest_asset"]["metadata"]["review_status"], "approved")

        rejected_regenerate = self.client.post(
            f"/api/projects/{project_id}/images/{asset['id']}/regenerate",
            json={"issue": "artifact"},
        )
        self.assertEqual(rejected_regenerate.status_code, 409)
        self.assertIn("requires a user note", rejected_regenerate.json()["error"]["message"])

        regenerated = self.client.post(
            f"/api/projects/{project_id}/images/{asset['id']}/regenerate",
            json={"issue": "artifact", "note": "手部要自然交握，不要多余手指。"},
        )
        self.assertEqual(regenerated.status_code, 200)
        regenerated_asset = regenerated.json()["items"][0]["latest_asset"]
        self.assertIn("用户具体说明：手部要自然交握", regenerated_asset["prompt"])
        self.assertEqual(regenerated_asset["metadata"]["review_note"], "手部要自然交握，不要多余手指。")

        deleted = self.client.delete(f"/api/projects/{project_id}/images/{regenerated_asset['id']}")
        self.assertEqual(deleted.status_code, 200)
        remaining_ids = [version["id"] for version in deleted.json()["items"][0]["versions"]]
        self.assertNotIn(regenerated_asset["id"], remaining_ids)
        self.assertFalse(Path(regenerated_asset["file_path"]).exists())

    def test_reference_images_feed_keyframes_and_video_context(self) -> None:
        project = self.client.post(
            "/api/projects",
            json={"title": "参考图一致性短片", "logline": "同一对恋人在不同镜头里保持一致。"},
        ).json()
        project_id = project["id"]
        shot = self.client.post(
            f"/api/projects/{project_id}/shots",
            json={
                "title": "公园相视",
                "summary": "两个人在黄昏公园相视微笑。",
                "prompt": "5秒，黄昏公园，原创情侣，电影感",
                "status": "approved",
            },
        ).json()["shots"][0]

        data_url = "data:image/png;base64," + base64.b64encode(b"fake-png").decode("ascii")
        referenced = self.client.post(
            f"/api/projects/{project_id}/references",
            json={
                "kind": "character",
                "name": "女主",
                "visual_prompt": "固定短发白裙，温柔笑容",
                "data_url": data_url,
                "file_name": "heroine.png",
            },
        )
        self.assertEqual(referenced.status_code, 201)
        reference_asset = next(asset for asset in referenced.json()["assets"] if asset["type"] == "reference")
        self.assertTrue(Path(reference_asset["file_path"]).exists())
        self.assertEqual(reference_asset["metadata"]["reference_kind"], "character")

        generated = self.client.post(f"/api/projects/{project_id}/images/generate", json={"shot_id": shot["id"]})
        self.assertEqual(generated.status_code, 200)
        image_asset = generated.json()["items"][0]["latest_asset"]
        self.assertIn(reference_asset["id"], image_asset["metadata"]["reference_asset_ids"])
        self.assertIn("女主", image_asset["metadata"]["reference_names"])
        self.assertIn("固定短发白裙", image_asset["prompt"])
        image_payload = json.loads(Path(image_asset["file_path"]).read_text(encoding="utf-8"))
        self.assertEqual(image_payload["reference_images"], [reference_asset["file_path"]])

        approved_image = self.client.post(f"/api/projects/{project_id}/images/{image_asset['id']}/approve", json={})
        self.assertEqual(approved_image.status_code, 200)
        generated_clip = self.client.post(f"/api/projects/{project_id}/clips/generate", json={"shot_id": shot["id"]})
        self.assertEqual(generated_clip.status_code, 200)
        clip_asset = generated_clip.json()["items"][0]["latest_asset"]
        self.assertEqual(clip_asset["metadata"]["reference_image_asset_id"], image_asset["id"])
        self.assertIn(reference_asset["id"], clip_asset["metadata"]["reference_asset_ids"])
        self.assertIn("视频首帧必须以已批准关键帧", clip_asset["prompt"])

    def test_orchestration_binds_references_to_specific_shots_and_reorders(self) -> None:
        project = self.client.post(
            "/api/projects",
            json={"title": "轻量编排短片", "logline": "参考图按分镜绑定。"},
        ).json()
        project_id = project["id"]
        first = self.client.post(
            f"/api/projects/{project_id}/shots",
            json={"title": "室内相遇", "prompt": "室内暖光", "status": "approved"},
        ).json()["shots"][0]
        second = self.client.post(
            f"/api/projects/{project_id}/shots",
            json={"title": "公园相视", "prompt": "黄昏公园", "status": "approved"},
        ).json()["shots"][1]
        data_url = "data:image/png;base64," + base64.b64encode(b"fake-png").decode("ascii")
        referenced = self.client.post(
            f"/api/projects/{project_id}/references",
            json={
                "kind": "scene",
                "name": "黄昏公园",
                "visual_prompt": "固定草坪、远处楼群、逆光",
                "data_url": data_url,
                "file_name": "park.png",
            },
        )
        self.assertEqual(referenced.status_code, 201)
        reference_asset = next(asset for asset in referenced.json()["assets"] if asset["type"] == "reference")

        reordered = self.client.post(
            f"/api/projects/{project_id}/shots/reorder",
            json={"shot_ids": [second["id"], first["id"]]},
        )
        self.assertEqual(reordered.status_code, 200)
        self.assertEqual([shot["id"] for shot in reordered.json()["shots"]], [second["id"], first["id"]])
        self.assertEqual([shot["position"] for shot in reordered.json()["shots"]], [1, 2])

        bound = self.client.patch(
            f"/api/projects/{project_id}/references/{reference_asset['id']}/bindings",
            json={"scope": "shots", "shot_ids": [second["id"]]},
        )
        self.assertEqual(bound.status_code, 200)
        updated_ref = next(asset for asset in bound.json()["assets"] if asset["id"] == reference_asset["id"])
        self.assertEqual(updated_ref["metadata"]["reference_scope"], "shots")
        self.assertEqual(updated_ref["metadata"]["shot_ids"], [second["id"]])

        first_image = self.client.post(f"/api/projects/{project_id}/images/generate", json={"shot_id": first["id"]}).json()
        first_asset = next(item for item in first_image["items"] if item["shot"]["id"] == first["id"])["latest_asset"]
        self.assertNotIn(reference_asset["id"], first_asset["metadata"]["reference_asset_ids"])

        second_image = self.client.post(f"/api/projects/{project_id}/images/generate", json={"shot_id": second["id"]}).json()
        second_asset = next(item for item in second_image["items"] if item["shot"]["id"] == second["id"])["latest_asset"]
        self.assertIn(reference_asset["id"], second_asset["metadata"]["reference_asset_ids"])

        global_ref = self.client.patch(
            f"/api/projects/{project_id}/references/{reference_asset['id']}/bindings",
            json={"scope": "project", "shot_ids": []},
        )
        self.assertEqual(global_ref.status_code, 200)
        image_after_global = self.client.post(f"/api/projects/{project_id}/images/generate", json={"shot_id": first["id"]}).json()
        global_asset = next(item for item in image_after_global["items"] if item["shot"]["id"] == first["id"])["latest_asset"]
        self.assertIn(reference_asset["id"], global_asset["metadata"]["reference_asset_ids"])

    def test_clip_review_uses_approved_image_and_supports_delete(self) -> None:
        project = self.client.post(
            "/api/projects",
            json={"title": "视频验收短片", "logline": "一个单镜头爱情故事。"},
        ).json()
        project_id = project["id"]
        shot = self.client.post(
            f"/api/projects/{project_id}/shots",
            json={
                "title": "月台告白",
                "summary": "两个人在月台轻轻牵手。",
                "prompt": "5秒，镜头缓慢推进，两人牵手对视，动作自然",
                "status": "approved",
            },
        ).json()["shots"][0]

        waiting = self.client.get(f"/api/projects/{project_id}/clips")
        self.assertEqual(waiting.status_code, 200)
        self.assertEqual(waiting.json()["status"], "waiting_for_images")
        self.assertEqual(waiting.json()["items"][0]["status"], "waiting_for_image")

        image_state = self.client.post(f"/api/projects/{project_id}/images/generate", json={"shot_id": shot["id"]}).json()
        image_asset = image_state["items"][0]["latest_asset"]
        approved_image = self.client.post(f"/api/projects/{project_id}/images/{image_asset['id']}/approve", json={})
        self.assertEqual(approved_image.status_code, 200)

        initial = self.client.get(f"/api/projects/{project_id}/clips")
        self.assertEqual(initial.status_code, 200)
        self.assertEqual(initial.json()["status"], "not_started")
        self.assertEqual(initial.json()["items"][0]["reference_image"]["id"], image_asset["id"])

        generated = self.client.post(f"/api/projects/{project_id}/clips/generate", json={"shot_id": shot["id"]})
        self.assertEqual(generated.status_code, 200)
        clip_asset = generated.json()["items"][0]["latest_asset"]
        self.assertEqual(clip_asset["type"], "video")
        self.assertEqual(clip_asset["metadata"]["review_status"], "needs_review")
        self.assertEqual(clip_asset["metadata"]["reference_image_asset_id"], image_asset["id"])
        self.assertTrue(Path(clip_asset["file_path"]).exists())

        rejected_regenerate = self.client.post(
            f"/api/projects/{project_id}/clips/{clip_asset['id']}/regenerate",
            json={"issue": "stiff_motion"},
        )
        self.assertEqual(rejected_regenerate.status_code, 409)
        self.assertIn("requires a user note", rejected_regenerate.json()["error"]["message"])

        approved = self.client.post(f"/api/projects/{project_id}/clips/{clip_asset['id']}/approve", json={})
        self.assertEqual(approved.status_code, 200)
        self.assertEqual(approved.json()["status"], "approved")
        self.assertEqual(approved.json()["project"]["current_step"], "edit_assembly")

        exported = self.client.post(f"/api/projects/{project_id}/edit-pack")
        self.assertEqual(exported.status_code, 200)
        self.assertEqual(exported.json()["project"]["current_step"], "final_qc")
        manifest = json.loads(Path(exported.json()["edit_pack"]["manifest_path"]).read_text(encoding="utf-8"))
        exported_video_ids = [item["id"] for item in manifest["assets"] if item["type"] == "video"]
        self.assertEqual(exported_video_ids, [clip_asset["id"]])

        deleted = self.client.delete(f"/api/projects/{project_id}/clips/{clip_asset['id']}")
        self.assertEqual(deleted.status_code, 200)
        self.assertEqual(deleted.json()["items"][0]["versions"], [])
        self.assertFalse(Path(clip_asset["file_path"]).exists())

    def test_clip_generation_failure_is_visible_in_review_state(self) -> None:
        project = self.client.post(
            "/api/projects",
            json={"title": "失败可见短片", "logline": "一个单镜头测试。"},
        ).json()
        project_id = project["id"]
        shot = self.client.post(
            f"/api/projects/{project_id}/shots",
            json={"title": "失败镜头", "prompt": "5秒轻微推进", "status": "approved"},
        ).json()["shots"][0]
        image_state = self.client.post(f"/api/projects/{project_id}/images/generate", json={"shot_id": shot["id"]}).json()
        image_asset = image_state["items"][0]["latest_asset"]
        self.client.post(f"/api/projects/{project_id}/images/{image_asset['id']}/approve", json={})

        with patch("aifilm_studio.service.run_generation_task_with_provider", side_effect=RuntimeError("model rejected video request")):
            generated = self.client.post(f"/api/projects/{project_id}/clips/generate", json={"shot_id": shot["id"]})

        self.assertEqual(generated.status_code, 502)
        state = self.client.get(f"/api/projects/{project_id}/clips")
        self.assertEqual(state.status_code, 200)
        self.assertEqual(state.json()["status"], "failed")
        item = state.json()["items"][0]
        self.assertEqual(item["status"], "failed")
        self.assertEqual(item["latest_task"]["status"], "failed")
        self.assertIn("model rejected", item["latest_task"]["error"])

    def test_later_clip_success_clears_global_failed_status(self) -> None:
        project = self.client.post(
            "/api/projects",
            json={"title": "失败后成功短片", "logline": "一个单镜头测试。"},
        ).json()
        project_id = project["id"]
        shot = self.client.post(
            f"/api/projects/{project_id}/shots",
            json={"title": "恢复镜头", "prompt": "5秒轻微推进", "status": "approved"},
        ).json()["shots"][0]
        image_state = self.client.post(f"/api/projects/{project_id}/images/generate", json={"shot_id": shot["id"]}).json()
        image_asset = image_state["items"][0]["latest_asset"]
        self.client.post(f"/api/projects/{project_id}/images/{image_asset['id']}/approve", json={})

        with patch("aifilm_studio.service.run_generation_task_with_provider", side_effect=RuntimeError("first attempt failed")):
            failed = self.client.post(f"/api/projects/{project_id}/clips/generate", json={"shot_id": shot["id"]})
        self.assertEqual(failed.status_code, 502)

        generated = self.client.post(f"/api/projects/{project_id}/clips/generate", json={"shot_id": shot["id"]})
        self.assertEqual(generated.status_code, 200)
        payload = generated.json()
        self.assertEqual(payload["status"], "needs_review")
        self.assertEqual(payload["items"][0]["status"], "needs_review")
        self.assertEqual(payload["items"][0]["latest_task"]["status"], "succeeded")

    def test_clip_generation_pending_does_not_create_fake_video_asset(self) -> None:
        project = self.client.post(
            "/api/projects",
            json={"title": "异步视频短片", "logline": "一个单镜头测试。"},
        ).json()
        project_id = project["id"]
        shot = self.client.post(
            f"/api/projects/{project_id}/shots",
            json={"title": "等待镜头", "prompt": "5秒轻微推进", "status": "approved"},
        ).json()["shots"][0]
        image_state = self.client.post(f"/api/projects/{project_id}/images/generate", json={"shot_id": shot["id"]}).json()
        image_asset = image_state["items"][0]["latest_asset"]
        self.client.post(f"/api/projects/{project_id}/images/{image_asset['id']}/approve", json={})

        pending = ProviderAdapterPending("供应商任务处理中：task-1", provider_task_id="task-1", task_status="PENDING")
        with patch("aifilm_studio.service.run_generation_task_with_provider", side_effect=pending):
            generated = self.client.post(f"/api/projects/{project_id}/clips/generate", json={"shot_id": shot["id"]})

        self.assertEqual(generated.status_code, 200)
        payload = generated.json()
        self.assertEqual(payload["generated_asset_ids"], [])
        self.assertEqual(payload["pending"][0]["message"], "供应商任务处理中：task-1")
        item = payload["items"][0]
        self.assertEqual(item["status"], "running")
        self.assertIsNone(item["latest_asset"])
        self.assertEqual(item["versions"], [])
        self.assertEqual(item["latest_task"]["status"], "running")
        self.assertFalse(any(asset["type"] == "video" for asset in payload["project"]["assets"]))


if __name__ == "__main__":
    unittest.main()
