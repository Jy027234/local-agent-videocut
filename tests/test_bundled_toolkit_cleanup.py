from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TOOLKIT = ROOT / "src" / "video_editing_toolkit"


def test_bundled_toolkit_contains_only_runtime_files() -> None:
    files = {path.relative_to(TOOLKIT).as_posix() for path in TOOLKIT.rglob("*.py")}

    assert files == {
        "__init__.py",
        "creative_edit_runner.py",
        "runtime_common.py",
        "voice_simulation.py",
        "storage/__init__.py",
        "storage/artifacts.py",
        "storage/signed_urls.py",
    }


def test_bundled_toolkit_has_no_stage_script_names() -> None:
    text = "\n".join(path.read_text(encoding="utf-8") for path in TOOLKIT.rglob("*.py"))

    for marker in ("p1_", "p2_", "_smoke", "agentctl", "demo"):
        assert marker not in text
