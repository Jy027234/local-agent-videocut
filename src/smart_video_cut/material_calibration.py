from __future__ import annotations

import json
import statistics
from pathlib import Path
from typing import Any, Mapping, Sequence


MATERIAL_VISUAL_CALIBRATION_SCHEMA = "smart_video_cut.local.material_visual_calibration.v0"
SUPPORTED_ROLES = ("opening_hero", "product_body_and_detail", "site_context")

DEFAULT_DOOR_SCENE_SAMPLES: list[dict[str, Any]] = [
    {
        "sample_id": "door-overall-front",
        "expected_role": "opening_hero",
        "scores": {"opening_hero": 0.78, "product_body_and_detail": 0.42, "site_context": 0.31},
    },
    {
        "sample_id": "door-lock-detail",
        "expected_role": "product_body_and_detail",
        "scores": {"opening_hero": 0.36, "product_body_and_detail": 0.86, "site_context": 0.22},
    },
    {
        "sample_id": "door-hallway-context",
        "expected_role": "site_context",
        "scores": {"opening_hero": 0.44, "product_body_and_detail": 0.28, "site_context": 0.73},
    },
    {
        "sample_id": "door-installation-wide",
        "expected_role": "opening_hero",
        "scores": {"opening_hero": 0.69, "product_body_and_detail": 0.55, "site_context": 0.45},
    },
    {
        "sample_id": "hinge-and-frame-detail",
        "expected_role": "product_body_and_detail",
        "scores": {"opening_hero": 0.41, "product_body_and_detail": 0.71, "site_context": 0.25},
    },
    {
        "sample_id": "site-transition-corridor",
        "expected_role": "site_context",
        "scores": {"opening_hero": 0.38, "product_body_and_detail": 0.35, "site_context": 0.68},
    },
]

DEFAULT_ECOMMERCE_PRODUCT_SAMPLES: list[dict[str, Any]] = [
    {
        "sample_id": "hero-packshot-front",
        "expected_role": "opening_hero",
        "scores": {"opening_hero": 0.84, "product_body_and_detail": 0.47, "site_context": 0.18},
    },
    {
        "sample_id": "texture-close-up",
        "expected_role": "product_body_and_detail",
        "scores": {"opening_hero": 0.38, "product_body_and_detail": 0.88, "site_context": 0.16},
    },
    {
        "sample_id": "usage-scene-desk",
        "expected_role": "site_context",
        "scores": {"opening_hero": 0.43, "product_body_and_detail": 0.41, "site_context": 0.76},
    },
    {
        "sample_id": "brand-logo-opener",
        "expected_role": "opening_hero",
        "scores": {"opening_hero": 0.73, "product_body_and_detail": 0.52, "site_context": 0.29},
    },
    {
        "sample_id": "button-and-port-detail",
        "expected_role": "product_body_and_detail",
        "scores": {"opening_hero": 0.32, "product_body_and_detail": 0.79, "site_context": 0.21},
    },
    {
        "sample_id": "lifestyle-shelf-context",
        "expected_role": "site_context",
        "scores": {"opening_hero": 0.36, "product_body_and_detail": 0.33, "site_context": 0.71},
    },
]

DEFAULT_REAL_ESTATE_SPACE_SAMPLES: list[dict[str, Any]] = [
    {
        "sample_id": "living-room-wide",
        "expected_role": "opening_hero",
        "scores": {"opening_hero": 0.82, "product_body_and_detail": 0.31, "site_context": 0.56},
    },
    {
        "sample_id": "fixture-and-hardware-detail",
        "expected_role": "product_body_and_detail",
        "scores": {"opening_hero": 0.28, "product_body_and_detail": 0.77, "site_context": 0.44},
    },
    {
        "sample_id": "corridor-to-room-context",
        "expected_role": "site_context",
        "scores": {"opening_hero": 0.45, "product_body_and_detail": 0.28, "site_context": 0.81},
    },
    {
        "sample_id": "bedroom-window-wide",
        "expected_role": "opening_hero",
        "scores": {"opening_hero": 0.74, "product_body_and_detail": 0.35, "site_context": 0.62},
    },
    {
        "sample_id": "cabinet-finish-detail",
        "expected_role": "product_body_and_detail",
        "scores": {"opening_hero": 0.33, "product_body_and_detail": 0.83, "site_context": 0.39},
    },
    {
        "sample_id": "community-exterior-context",
        "expected_role": "site_context",
        "scores": {"opening_hero": 0.39, "product_body_and_detail": 0.18, "site_context": 0.86},
    },
]

DEFAULT_INDUSTRY_SAMPLE_SETS: dict[str, list[dict[str, Any]]] = {
    "door_scene": DEFAULT_DOOR_SCENE_SAMPLES,
    "ecommerce_product": DEFAULT_ECOMMERCE_PRODUCT_SAMPLES,
    "real_estate_space": DEFAULT_REAL_ESTATE_SPACE_SAMPLES,
}

DEFAULT_INDUSTRY_SAMPLE_SET_LABELS = {
    "door_scene": "门类安装 / 家装现场",
    "ecommerce_product": "电商商品 / 产品展示",
    "real_estate_space": "房产空间 / 室内外看房",
}

DEFAULT_INDUSTRY_SAMPLE_SET_SOURCES = {
    "door_scene": "default_door_scene_samples",
    "ecommerce_product": "default_ecommerce_product_samples",
    "real_estate_space": "default_real_estate_space_samples",
}


def load_material_calibration_samples(path: str | Path) -> list[dict[str, Any]]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    if isinstance(payload, list):
        return [dict(item) for item in payload if isinstance(item, Mapping)]
    samples = payload.get("samples") if isinstance(payload, Mapping) else []
    return [dict(item) for item in samples if isinstance(item, Mapping)]


def calibrate_visual_role_thresholds(
    *,
    samples: Sequence[Mapping[str, Any]] | None = None,
    sample_set_path: str | Path = "",
    sample_set: str = "door_scene",
    baseline_threshold: float = 0.5,
) -> dict[str, Any]:
    selected_samples = list(samples or [])
    source = "provided_samples"
    selected_sample_set = "inline_samples" if selected_samples else _normalize_sample_set(sample_set)
    if sample_set_path:
        selected_samples = load_material_calibration_samples(sample_set_path)
        source = "sample_set_path"
        selected_sample_set = "custom_path"
    if not selected_samples:
        selected_sample_set = _normalize_sample_set(sample_set)
        selected_samples = DEFAULT_INDUSTRY_SAMPLE_SETS[selected_sample_set]
        source = DEFAULT_INDUSTRY_SAMPLE_SET_SOURCES[selected_sample_set]

    evaluated = [_evaluate_sample(sample) for sample in selected_samples]
    usable = [item for item in evaluated if item["usable"]]
    correct = [item for item in usable if item["correct"]]
    margins = [item["margin"] for item in usable]
    correct_scores = [item["expected_score"] for item in correct]
    recommended_threshold = _recommended_threshold(
        correct_scores=correct_scores,
        margins=margins,
        baseline_threshold=baseline_threshold,
    )
    return {
        "schema": MATERIAL_VISUAL_CALIBRATION_SCHEMA,
        "ok": bool(usable),
        "source": source,
        "sample_set": selected_sample_set,
        "sample_set_label": DEFAULT_INDUSTRY_SAMPLE_SET_LABELS.get(selected_sample_set, "自定义样本"),
        "available_sample_sets": available_industry_sample_sets(),
        "sample_count": len(selected_samples),
        "usable_sample_count": len(usable),
        "accuracy": round(len(correct) / len(usable), 4) if usable else 0.0,
        "baseline_threshold": round(_clamp(baseline_threshold), 4),
        "recommended_tuning": {
            "visual_quality_preset": "calibrated",
            "role_confidence_threshold": recommended_threshold,
        },
        "role_metrics": _role_metrics(usable),
        "low_confidence_samples": [
            item for item in usable if item["expected_score"] < recommended_threshold or item["margin"] < 0.08
        ],
        "samples": evaluated,
    }


def available_industry_sample_sets() -> list[dict[str, Any]]:
    return [
        {
            "id": sample_set,
            "label": DEFAULT_INDUSTRY_SAMPLE_SET_LABELS[sample_set],
            "sample_count": len(samples),
        }
        for sample_set, samples in DEFAULT_INDUSTRY_SAMPLE_SETS.items()
    ]


def _evaluate_sample(sample: Mapping[str, Any]) -> dict[str, Any]:
    scores = _scores_from_sample(sample)
    expected_role = str(sample.get("expected_role") or sample.get("role") or "").strip()
    sample_id = str(sample.get("sample_id") or sample.get("id") or sample.get("label") or "")
    if expected_role not in SUPPORTED_ROLES or not scores:
        return {
            "sample_id": sample_id,
            "expected_role": expected_role,
            "predicted_role": "",
            "expected_score": 0.0,
            "margin": 0.0,
            "correct": False,
            "usable": False,
            "reason": "missing_expected_role_or_scores",
        }
    predicted_role = max(SUPPORTED_ROLES, key=lambda role: scores.get(role, 0.0))
    expected_score = _safe_score(scores.get(expected_role))
    other_score = max((_safe_score(scores.get(role)) for role in SUPPORTED_ROLES if role != expected_role), default=0.0)
    return {
        "sample_id": sample_id,
        "expected_role": expected_role,
        "predicted_role": predicted_role,
        "expected_score": round(expected_score, 4),
        "margin": round(expected_score - other_score, 4),
        "correct": predicted_role == expected_role,
        "usable": True,
        "scores": {role: round(_safe_score(scores.get(role)), 4) for role in SUPPORTED_ROLES},
    }


def _scores_from_sample(sample: Mapping[str, Any]) -> dict[str, Any]:
    scores = sample.get("scores")
    if isinstance(scores, Mapping):
        return dict(scores)
    profile = sample.get("visual_profile")
    if isinstance(profile, Mapping) and isinstance(profile.get("scores"), Mapping):
        return dict(profile["scores"])
    return {}


def _recommended_threshold(
    *,
    correct_scores: list[float],
    margins: list[float],
    baseline_threshold: float,
) -> float:
    if not correct_scores:
        return round(_clamp(baseline_threshold), 4)
    median_score = statistics.median(correct_scores)
    positive_margins = [margin for margin in margins if margin > 0]
    median_margin = statistics.median(positive_margins) if positive_margins else 0.0
    conservative = min(median_score, median_score - max(0.0, 0.12 - median_margin))
    return round(_clamp((conservative + _clamp(baseline_threshold)) / 2.0), 4)


def _role_metrics(samples: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    metrics: dict[str, dict[str, Any]] = {}
    for role in SUPPORTED_ROLES:
        role_samples = [sample for sample in samples if sample["expected_role"] == role]
        correct = [sample for sample in role_samples if sample["correct"]]
        metrics[role] = {
            "sample_count": len(role_samples),
            "accuracy": round(len(correct) / len(role_samples), 4) if role_samples else 0.0,
            "avg_expected_score": round(
                sum(sample["expected_score"] for sample in role_samples) / len(role_samples),
                4,
            )
            if role_samples
            else 0.0,
            "avg_margin": round(sum(sample["margin"] for sample in role_samples) / len(role_samples), 4)
            if role_samples
            else 0.0,
        }
    return metrics


def _safe_score(value: Any) -> float:
    try:
        return _clamp(float(value))
    except (TypeError, ValueError):
        return 0.0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))


def _normalize_sample_set(sample_set: str) -> str:
    normalized = str(sample_set or "door_scene").strip().casefold()
    return normalized if normalized in DEFAULT_INDUSTRY_SAMPLE_SETS else "door_scene"
