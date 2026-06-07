from __future__ import annotations

import json
from pathlib import Path
from typing import Any


BGM_LIBRARY_SCHEMA = "smart_video_cut.local.bgm_library.v0"
BGM_LIBRARY_PLAYLIST_SCHEMA = "smart_video_cut.local.bgm_library_playlist.v0"
BGM_LIBRARY_AUDIO_EXTENSIONS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"}

STYLE_KEYWORDS = {
    "upbeat": ("upbeat", "happy", "cheer", "快", "欢快", "活力"),
    "product_flash": ("flash", "ad", "promo", "广告", "快闪", "节奏"),
    "clean_vlog": ("vlog", "clean", "light", "清爽", "轻快"),
    "premium": ("premium", "cinematic", "luxury", "高级", "质感", "电影"),
    "ambient": ("ambient", "calm", "soft", "氛围", "安静"),
}


def scan_bgm_library(
    *,
    library_dir: str | Path,
    query: str = "",
    style: str = "",
    limit: int = 20,
) -> dict[str, Any]:
    root = Path(str(library_dir or "").strip())
    if not root.is_dir():
        return {
            "schema": BGM_LIBRARY_SCHEMA,
            "ok": False,
            "reason": "library_dir_not_found",
            "library_dir": str(root),
            "items": [],
            "recommended": None,
        }
    terms = _terms(query=query, style=style)
    items = []
    for path in root.rglob("*"):
        if not path.is_file() or path.suffix.casefold() not in BGM_LIBRARY_AUDIO_EXTENSIONS:
            continue
        score = _score_path(path, terms=terms, style=style)
        items.append({
            "path": str(path),
            "name": path.name,
            "extension": path.suffix.casefold(),
            "size_bytes": path.stat().st_size,
            "score": score,
            "match_reason": _match_reason(path, terms=terms, score=score),
        })
    ranked = sorted(items, key=lambda item: (-float(item["score"]), item["name"].casefold()))[: max(1, int(limit or 20))]
    return {
        "schema": BGM_LIBRARY_SCHEMA,
        "ok": True,
        "reason": "library_scanned",
        "library_dir": str(root),
        "query": query,
        "style": style,
        "item_count": len(items),
        "items": ranked,
        "recommended": ranked[0] if ranked else None,
    }


def select_bgm_from_library(
    *,
    library_dir: str | Path,
    query: str = "",
    style: str = "",
) -> dict[str, Any]:
    scan = scan_bgm_library(library_dir=library_dir, query=query, style=style, limit=1)
    recommended = scan.get("recommended") if isinstance(scan.get("recommended"), dict) else None
    return {
        "ok": scan.get("ok") is True and recommended is not None,
        "reason": "library_audio_selected" if recommended else str(scan.get("reason") or "library_audio_missing"),
        "audio_path": recommended.get("path") if recommended else None,
        "library_scan": scan,
    }


def build_bgm_library_playlist(
    *,
    library_dir: str | Path,
    query: str = "",
    style: str = "",
    limit: int = 20,
    output_path: str | Path = "",
) -> dict[str, Any]:
    scan = scan_bgm_library(library_dir=library_dir, query=query, style=style, limit=limit)
    items = [
        {
            **item,
            "preview_api": f"/api/media-preview?path={item['path']}",
            "selected": index == 0,
        }
        for index, item in enumerate(scan.get("items") or [])
        if isinstance(item, dict)
    ]
    payload = {
        "schema": BGM_LIBRARY_PLAYLIST_SCHEMA,
        "ok": scan.get("ok") is True,
        "reason": "playlist_ready" if scan.get("ok") is True else scan.get("reason"),
        "library_dir": scan.get("library_dir"),
        "query": query,
        "style": style,
        "item_count": len(items),
        "items": items,
        "recommended": items[0] if items else None,
        "library_scan": scan,
        "playlist_path": "",
    }
    if output_path:
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
        payload["playlist_path"] = str(path)
    return payload


def _terms(*, query: str, style: str) -> tuple[str, ...]:
    raw = [part.strip().casefold() for part in str(query or "").replace("，", " ").replace(",", " ").split()]
    style_terms = STYLE_KEYWORDS.get(str(style or "").strip().casefold(), ())
    return tuple(term for term in [*raw, *style_terms] if term)


def _score_path(path: Path, *, terms: tuple[str, ...], style: str) -> float:
    text = f"{path.stem} {path.parent.name}".casefold()
    score = 0.2
    for term in terms:
        if term and term.casefold() in text:
            score += 0.28
    normalized_style = str(style or "").strip().casefold()
    if normalized_style and normalized_style in text:
        score += 0.2
    return round(min(1.0, score), 4)


def _match_reason(path: Path, *, terms: tuple[str, ...], score: float) -> str:
    text = f"{path.stem} {path.parent.name}".casefold()
    matched = [term for term in terms if term.casefold() in text]
    if matched:
        return "matched_terms: " + ", ".join(matched[:5])
    return "fallback_by_name" if score > 0 else "unscored"
