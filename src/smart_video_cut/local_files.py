from __future__ import annotations

import string
from pathlib import Path
from typing import Any


ROOT_DIR = Path(__file__).resolve().parents[2]


def list_local_paths(
    *,
    path: str = "",
    mode: str = "file",
    extensions: str = "",
) -> dict[str, Any]:
    base = _base_path(path)
    ext_set = _extension_set(extensions)
    items: list[dict[str, Any]] = []
    try:
        children = sorted(
            base.iterdir(),
            key=lambda item: (not item.is_dir(), item.name.casefold()),
        )
    except OSError:
        children = []
    for child in children:
        is_dir = child.is_dir()
        if not is_dir and ext_set and child.suffix.casefold() not in ext_set:
            continue
        if not is_dir and mode == "directory":
            continue
        items.append(
            {
                "name": child.name,
                "path": str(child),
                "is_dir": is_dir,
                "selectable": is_dir if mode == "directory" else not is_dir,
                "size_bytes": child.stat().st_size if child.is_file() else None,
            }
        )
    return {
        "cwd": str(base),
        "parent": str(base.parent) if base.parent != base else None,
        "mode": mode,
        "extensions": sorted(ext_set),
        "drives": _drives(),
        "shortcuts": _shortcuts(),
        "items": items,
    }


def _base_path(path: str) -> Path:
    if path:
        candidate = Path(path).expanduser()
        if candidate.is_file():
            return candidate.parent.resolve()
        if candidate.exists():
            return candidate.resolve()
    return ROOT_DIR.resolve()


def _extension_set(value: str) -> set[str]:
    return {
        item if item.startswith(".") else f".{item}"
        for item in (part.strip().casefold() for part in value.split(","))
        if item
    }


def _shortcuts() -> list[dict[str, str]]:
    candidates = [
        ("软件根目录", ROOT_DIR),
        ("风格包", ROOT_DIR / "packages"),
        ("输出目录", ROOT_DIR / "workspace" / "output"),
        ("项目缓存", ROOT_DIR / "workspace" / "projects"),
        ("常用视频素材", Path(r"D:\app\video")),
    ]
    return [{"label": label, "path": str(path)} for label, path in candidates if path.exists()]


def _drives() -> list[str]:
    drives: list[str] = []
    for letter in string.ascii_uppercase:
        drive = Path(f"{letter}:\\")
        if drive.exists():
            drives.append(str(drive))
    return drives
