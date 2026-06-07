from __future__ import annotations

import json
import subprocess
import hashlib
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]
THUMBNAIL_CACHE_DIR = ROOT_DIR / "workspace" / "cache" / "material_thumbnails"
PROFILE_SCHEMA = "smart_video_cut.local.material_visual_profile.v0"
FRAME_SIZE = 64
RAW_FRAME_BYTES = FRAME_SIZE * FRAME_SIZE * 3


def analyze_material_visual_profiles(paths: list[Path], *, max_frames: int = 3) -> list[dict[str, Any]]:
    """Build lightweight local visual profiles from FFmpeg frame samples.

    This intentionally avoids cloud calls and heavy optional CV dependencies.
    The profile is good enough to choose likely opening/detail/context material,
    and its shape is ready for a later multimodal model to replace the scores.
    """

    ffmpeg = _media_binary("ffmpeg")
    ffprobe = _media_binary("ffprobe")
    profiles = []
    for index, path in enumerate(paths):
        profiles.append(
            _analyze_one_material(
                index=index,
                path=path,
                ffmpeg=ffmpeg,
                ffprobe=ffprobe,
                max_frames=max_frames,
            )
        )
    return profiles


def _analyze_one_material(
    *,
    index: int,
    path: Path,
    ffmpeg: str | None,
    ffprobe: str | None,
    max_frames: int,
) -> dict[str, Any]:
    base: dict[str, Any] = {
        "schema": PROFILE_SCHEMA,
        "index": index,
        "path": str(path),
        "label": path.name,
        "analysis_method": "ffmpeg_raw_rgb_frame_probe",
        "analysis_ready": False,
    }
    if not path.is_file():
        return {**base, "failure_reason": "input_file_not_found"}
    if not ffmpeg or not ffprobe:
        return {**base, "failure_reason": "ffmpeg_or_ffprobe_unavailable"}
    probe = _probe_video(path, ffprobe=ffprobe)
    if not probe.get("ok"):
        return {**base, "probe": probe, "failure_reason": "ffprobe_failed"}
    frames = []
    thumbnail_refs = []
    media_cache_dir = _media_cache_dir(path)
    for sample_index, timestamp in enumerate(
        _sample_timestamps(float(probe.get("duration_seconds") or 0.0), max_frames=max_frames)
    ):
        raw_frame = _extract_raw_frame(path, ffmpeg=ffmpeg, timestamp=timestamp)
        if raw_frame:
            frames.append(_frame_metrics(raw_frame))
        thumbnail_path = _extract_thumbnail(
            path,
            ffmpeg=ffmpeg,
            timestamp=timestamp,
            sample_index=sample_index,
            output_dir=media_cache_dir,
        )
        if thumbnail_path:
            thumbnail_refs.append(
                {
                    "timestamp_seconds": round(timestamp, 3),
                    "thumbnail_path": str(thumbnail_path),
                    "mime_type": "image/jpeg",
                }
            )
    if not frames:
        return {
            **base,
            "probe": probe,
            "thumbnail_refs": thumbnail_refs,
            "failure_reason": "frame_sampling_failed",
        }
    metrics = _aggregate_frame_metrics(frames)
    scores = _role_scores(metrics, probe)
    return {
        **base,
        "analysis_ready": True,
        "probe": probe,
        "frames_sampled": len(frames),
        "thumbnail_refs": thumbnail_refs,
        "metrics": metrics,
        "scores": scores,
        "reason": _profile_reason(metrics, scores),
    }


def _media_binary(name: str) -> str | None:
    try:
        from video_editing_toolkit.creative_edit_runner import _binary_path  # type: ignore
    except ImportError:
        return None
    return _binary_path(name)


def _probe_video(path: Path, *, ffprobe: str) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            [
                ffprobe,
                "-v",
                "error",
                "-print_format",
                "json",
                "-show_format",
                "-show_streams",
                str(path),
            ],
            capture_output=True,
            check=False,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=12,
        )
    except (OSError, subprocess.SubprocessError):
        return {"ok": False}
    if completed.returncode != 0:
        return {"ok": False, "stderr_tail": completed.stderr[-300:]}
    try:
        data = json.loads(completed.stdout)
    except json.JSONDecodeError:
        return {"ok": False}
    video = next((stream for stream in data.get("streams", []) if stream.get("codec_type") == "video"), {})
    fmt = data.get("format") if isinstance(data.get("format"), dict) else {}
    return {
        "ok": True,
        "duration_seconds": _safe_float(fmt.get("duration") or video.get("duration")),
        "width": _safe_int(video.get("width")),
        "height": _safe_int(video.get("height")),
    }


def _sample_timestamps(duration_seconds: float, *, max_frames: int) -> list[float]:
    frame_count = max(1, min(5, int(max_frames or 3)))
    if duration_seconds <= 0:
        return [0.5 + index for index in range(frame_count)]
    if frame_count == 1:
        return [min(duration_seconds * 0.5, max(0.0, duration_seconds - 0.1))]
    anchors = [0.18, 0.42, 0.68, 0.84, 0.94][:frame_count]
    return [max(0.0, min(duration_seconds * anchor, max(0.0, duration_seconds - 0.12))) for anchor in anchors]


def _extract_raw_frame(path: Path, *, ffmpeg: str, timestamp: float) -> bytes | None:
    try:
        completed = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-nostdin",
                "-ss",
                f"{max(0.0, timestamp):.3f}",
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-vf",
                f"scale={FRAME_SIZE}:{FRAME_SIZE}:force_original_aspect_ratio=decrease,"
                f"pad={FRAME_SIZE}:{FRAME_SIZE}:(ow-iw)/2:(oh-ih)/2:color=black",
                "-f",
                "rawvideo",
                "-pix_fmt",
                "rgb24",
                "-",
            ],
            capture_output=True,
            check=False,
            timeout=18,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0 or len(completed.stdout) < RAW_FRAME_BYTES:
        return None
    return completed.stdout[:RAW_FRAME_BYTES]


def _extract_thumbnail(
    path: Path,
    *,
    ffmpeg: str,
    timestamp: float,
    sample_index: int,
    output_dir: Path,
) -> Path | None:
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"sample_{sample_index + 1}.jpg"
    try:
        completed = subprocess.run(
            [
                ffmpeg,
                "-hide_banner",
                "-nostdin",
                "-y",
                "-ss",
                f"{max(0.0, timestamp):.3f}",
                "-i",
                str(path),
                "-frames:v",
                "1",
                "-vf",
                "scale=360:-2",
                "-q:v",
                "4",
                str(output_path),
            ],
            capture_output=True,
            check=False,
            timeout=18,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0 or not output_path.is_file() or output_path.stat().st_size <= 0:
        return None
    return output_path


def _media_cache_dir(path: Path) -> Path:
    try:
        stat = path.stat()
        marker = f"{path.resolve()}::{stat.st_mtime_ns}::{stat.st_size}"
    except OSError:
        marker = str(path)
    digest = hashlib.sha256(marker.encode("utf-8", errors="ignore")).hexdigest()[:20]
    return THUMBNAIL_CACHE_DIR / digest


def _frame_metrics(raw_frame: bytes) -> dict[str, float]:
    lumas: list[float] = []
    saturations: list[float] = []
    center_lumas: list[float] = []
    border_lumas: list[float] = []
    for y in range(FRAME_SIZE):
        for x in range(FRAME_SIZE):
            offset = (y * FRAME_SIZE + x) * 3
            r = raw_frame[offset] / 255.0
            g = raw_frame[offset + 1] / 255.0
            b = raw_frame[offset + 2] / 255.0
            luma = (0.2126 * r) + (0.7152 * g) + (0.0722 * b)
            saturation = max(r, g, b) - min(r, g, b)
            lumas.append(luma)
            saturations.append(saturation)
            if 18 <= x < 46 and 18 <= y < 46:
                center_lumas.append(luma)
            elif x < 8 or x >= 56 or y < 8 or y >= 56:
                border_lumas.append(luma)
    edge_total = 0.0
    edge_count = 0
    for y in range(FRAME_SIZE):
        row = y * FRAME_SIZE
        for x in range(FRAME_SIZE):
            luma = lumas[row + x]
            if x + 1 < FRAME_SIZE:
                edge_total += abs(luma - lumas[row + x + 1])
                edge_count += 1
            if y + 1 < FRAME_SIZE:
                edge_total += abs(luma - lumas[row + x + FRAME_SIZE])
                edge_count += 1
    return {
        "avg_luma": _mean(lumas),
        "avg_saturation": _mean(saturations),
        "edge_density": edge_total / max(1, edge_count),
        "center_contrast": abs(_mean(center_lumas) - _mean(border_lumas)),
    }


def _aggregate_frame_metrics(frames: list[dict[str, float]]) -> dict[str, float]:
    avg_lumas = [frame["avg_luma"] for frame in frames]
    return {
        "avg_luma": _mean(avg_lumas),
        "avg_saturation": _mean([frame["avg_saturation"] for frame in frames]),
        "edge_density": _mean([frame["edge_density"] for frame in frames]),
        "center_contrast": _mean([frame["center_contrast"] for frame in frames]),
        "frame_luma_variation": max(avg_lumas) - min(avg_lumas) if avg_lumas else 0.0,
    }


def _role_scores(metrics: dict[str, float], probe: dict[str, Any]) -> dict[str, float]:
    luma_quality = _clamp(1.0 - abs(metrics["avg_luma"] - 0.52) / 0.52)
    edge_strength = _clamp(metrics["edge_density"] * 8.0)
    center_strength = _clamp(metrics["center_contrast"] * 5.0)
    saturation = _clamp(metrics["avg_saturation"] * 2.0)
    motion_proxy = _clamp(metrics["frame_luma_variation"] * 4.0)
    width = max(1, int(probe.get("width") or 1))
    height = max(1, int(probe.get("height") or 1))
    aspect = width / height
    vertical_fit = _clamp(1.0 - abs(aspect - (9 / 16)) / 1.2)
    detail_score = (edge_strength * 0.62) + (center_strength * 0.28) + (saturation * 0.10)
    opening_score = (luma_quality * 0.44) + (vertical_fit * 0.20) + (center_strength * 0.20) + (
        _clamp(1.0 - abs(edge_strength - 0.48)) * 0.16
    )
    context_score = (_clamp(1.0 - edge_strength) * 0.38) + (motion_proxy * 0.24) + (
        luma_quality * 0.22
    ) + (_clamp(1.0 - center_strength) * 0.16)
    return {
        "opening_hero": round(opening_score, 4),
        "product_body_and_detail": round(detail_score, 4),
        "site_context": round(context_score, 4),
    }


def _profile_reason(metrics: dict[str, float], scores: dict[str, float]) -> str:
    strongest = max(scores, key=lambda key: scores[key])
    labels = {
        "opening_hero": "画面亮度和中心构图更适合作为开头/全貌",
        "product_body_and_detail": "边缘和中心细节更明显，适合产品主体或细节",
        "site_context": "画面结构更松，适合环境或过渡镜头",
    }
    return (
        f"{labels.get(strongest, '按视觉特征自动评分')}；"
        f"亮度 {metrics['avg_luma']:.2f}，边缘 {metrics['edge_density']:.2f}，"
        f"中心对比 {metrics['center_contrast']:.2f}。"
    )


def _safe_float(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return parsed if parsed > 0 else 0.0


def _safe_int(value: Any) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return 0
    return parsed if parsed > 0 else 0


def _mean(values: list[float]) -> float:
    return sum(values) / len(values) if values else 0.0


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, float(value)))
