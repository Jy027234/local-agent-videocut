from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient

from smart_video_cut.material_calibration import calibrate_visual_role_thresholds, load_material_calibration_samples
from smart_video_cut.web_app import create_app


def test_default_door_scene_calibration_recommends_threshold() -> None:
    result = calibrate_visual_role_thresholds()

    assert result["schema"] == "smart_video_cut.local.material_visual_calibration.v0"
    assert result["ok"] is True
    assert result["source"] == "default_door_scene_samples"
    assert result["sample_set"] == "door_scene"
    assert any(item["id"] == "ecommerce_product" for item in result["available_sample_sets"])
    assert result["sample_count"] >= 3
    assert result["accuracy"] > 0
    assert 0 <= result["recommended_tuning"]["role_confidence_threshold"] <= 1
    assert "opening_hero" in result["role_metrics"]


def test_builtin_industry_sample_set_can_be_selected() -> None:
    result = calibrate_visual_role_thresholds(sample_set="ecommerce_product", baseline_threshold=0.45)

    assert result["ok"] is True
    assert result["source"] == "default_ecommerce_product_samples"
    assert result["sample_set"] == "ecommerce_product"
    assert result["sample_set_label"] == "电商商品 / 产品展示"
    assert result["sample_count"] >= 6
    assert result["recommended_tuning"]["visual_quality_preset"] == "calibrated"


def test_calibration_loads_json_sample_set(tmp_path: Path) -> None:
    sample_set = tmp_path / "door_samples.json"
    sample_set.write_text(
        json.dumps(
            {
                "samples": [
                    {
                        "sample_id": "lock",
                        "expected_role": "product_body_and_detail",
                        "scores": {
                            "opening_hero": 0.2,
                            "product_body_and_detail": 0.9,
                            "site_context": 0.1,
                        },
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    loaded = load_material_calibration_samples(sample_set)
    result = calibrate_visual_role_thresholds(sample_set_path=sample_set, baseline_threshold=0.6)

    assert loaded[0]["sample_id"] == "lock"
    assert result["source"] == "sample_set_path"
    assert result["usable_sample_count"] == 1
    assert result["samples"][0]["correct"] is True
    assert result["baseline_threshold"] == 0.6


def test_material_calibration_api_accepts_inline_samples() -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/material/calibration",
        json={
            "baseline_threshold": 0.55,
            "samples": [
                {
                    "sample_id": "corridor",
                    "expected_role": "site_context",
                    "scores": {
                        "opening_hero": 0.3,
                        "product_body_and_detail": 0.2,
                        "site_context": 0.8,
                    },
                }
            ],
        },
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["schema"] == "smart_video_cut.local.material_visual_calibration.v0"
    assert payload["source"] == "provided_samples"
    assert payload["accuracy"] == 1.0


def test_material_calibration_api_accepts_builtin_sample_set() -> None:
    client = TestClient(create_app(), raise_server_exceptions=False)

    response = client.post(
        "/api/material/calibration",
        json={"sample_set": "real_estate_space", "baseline_threshold": 0.52},
    )
    payload = response.json()

    assert response.status_code == 200
    assert payload["source"] == "default_real_estate_space_samples"
    assert payload["sample_set"] == "real_estate_space"
    assert payload["sample_count"] >= 6
