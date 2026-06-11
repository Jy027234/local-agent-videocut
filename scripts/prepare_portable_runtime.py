from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import sysconfig
import tomllib
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare a bundled portable Python runtime for Local Studio releases.")
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--runtime-dir", required=True)
    parser.add_argument("--extras", nargs="*", default=["web", "analysis", "tts"])
    parser.add_argument("--exclude-dependency", action="append", default=[])
    parser.add_argument("--metadata-path", default="")
    parser.add_argument("--verify-import", action="append", default=[])
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_root = Path(args.project_root).resolve()
    runtime_dir = Path(args.runtime_dir).resolve()
    pyproject = project_root / "pyproject.toml"
    if not pyproject.is_file():
        raise FileNotFoundError(f"pyproject.toml not found: {pyproject}")

    specs = load_dependency_specs(
        pyproject_path=pyproject,
        extras=args.extras,
        excluded=args.exclude_dependency,
    )
    copy_runtime_tree(source_root=Path(sys.base_prefix), runtime_dir=runtime_dir)
    site_packages = runtime_dir / "Lib" / "site-packages"
    site_packages.mkdir(parents=True, exist_ok=True)
    install_dependencies(
        python_executable=Path(sys.executable),
        target_site_packages=site_packages,
        specs=specs,
    )
    verify_runtime(
        runtime_python=runtime_dir / "python.exe",
        runtime_dir=runtime_dir,
        project_src=project_root / "src",
        extra_imports=args.verify_import,
    )
    if args.metadata_path:
        write_metadata(
            metadata_path=Path(args.metadata_path).resolve(),
            runtime_dir=runtime_dir,
            specs=specs,
            extras=args.extras,
            excluded=args.exclude_dependency,
        )
    print(json.dumps({
        "ok": True,
        "runtime_dir": str(runtime_dir),
        "python_executable": str(runtime_dir / "python.exe"),
        "dependency_count": len(specs),
        "dependencies": specs,
    }, ensure_ascii=False, indent=2))
    return 0


def load_dependency_specs(
    *,
    pyproject_path: Path,
    extras: Iterable[str],
    excluded: Iterable[str],
) -> list[str]:
    data = tomllib.loads(pyproject_path.read_text(encoding="utf-8"))
    project = data.get("project") or {}
    dependencies = list(project.get("dependencies") or [])
    optional = dict(project.get("optional-dependencies") or {})
    for extra in extras:
        dependencies.extend(optional.get(extra, []))

    excluded_names = {_normalize_requirement_name(item) for item in excluded if item}
    selected: list[str] = []
    seen: set[str] = set()
    for spec in dependencies:
        name = _normalize_requirement_name(spec)
        if not name or name in excluded_names or name in seen:
            continue
        selected.append(str(spec))
        seen.add(name)
    return selected


def copy_runtime_tree(*, source_root: Path, runtime_dir: Path) -> None:
    if runtime_dir.exists():
        shutil.rmtree(runtime_dir)

    def _ignore(path: str, names: list[str]) -> set[str]:
        current = Path(path)
        ignored: set[str] = set()
        if current == source_root:
            ignored.update({"Scripts", "Tools", "share", "include", "libs", "__pycache__"})
        if current.name == "Lib":
            ignored.update({"site-packages", "test", "tkinter", "turtledemo", "idlelib", "__pycache__"})
        return ignored

    shutil.copytree(source_root, runtime_dir, ignore=_ignore)
    (runtime_dir / "Lib" / "site-packages").mkdir(parents=True, exist_ok=True)


def install_dependencies(
    *,
    python_executable: Path,
    target_site_packages: Path,
    specs: list[str],
) -> None:
    if not specs:
        return
    cmd = [
        str(python_executable),
        "-m",
        "pip",
        "install",
        "--upgrade",
        "--disable-pip-version-check",
        "--no-warn-script-location",
        "--target",
        str(target_site_packages),
        *specs,
    ]
    subprocess.run(cmd, check=True)


def verify_runtime(
    *,
    runtime_python: Path,
    runtime_dir: Path,
    project_src: Path,
    extra_imports: Iterable[str],
) -> None:
    imports = [
        "fastapi",
        "uvicorn",
        "pydantic",
        "numpy",
        "cv2",
        "onnxruntime",
        "smart_video_cut.web_app",
        *[item for item in extra_imports if item],
    ]
    script = "\n".join([
        "import importlib",
        "import sys",
        f"mods = {imports!r}",
        "failed = []",
        "print(sys.executable)",
        "print(sys.prefix)",
        "print(sys.path[0])",
        "for name in mods:",
        "    try:",
        "        importlib.import_module(name)",
        "    except Exception as exc:",
        "        failed.append((name, repr(exc)))",
        "if failed:",
        "    raise SystemExit('runtime_verify_failed:' + repr(failed))",
        "print('portable-runtime-ok')",
    ])
    env = os.environ.copy()
    env["PYTHONHOME"] = str(runtime_dir)
    env["PYTHONPATH"] = str(project_src)
    env.setdefault("PYTHONIOENCODING", "utf-8")
    subprocess.run(
        [str(runtime_python), "-c", script],
        check=True,
        env=env,
        cwd=project_src.parent,
    )


def write_metadata(
    *,
    metadata_path: Path,
    runtime_dir: Path,
    specs: list[str],
    extras: Iterable[str],
    excluded: Iterable[str],
) -> None:
    payload = {
        "schema": "smart_video_cut.release_portable_runtime.v0",
        "built_at": datetime.now(timezone.utc).isoformat(),
        "builder_python": {
            "executable": sys.executable,
            "base_prefix": sys.base_prefix,
            "version": sys.version,
        },
        "runtime_dir": str(runtime_dir),
        "extras": list(extras),
        "excluded_dependencies": list(excluded),
        "dependency_specs": specs,
        "stdlib": sysconfig.get_path("stdlib"),
        "site_packages_target": str(runtime_dir / "Lib" / "site-packages"),
    }
    metadata_path.parent.mkdir(parents=True, exist_ok=True)
    metadata_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _normalize_requirement_name(spec: str) -> str:
    text = str(spec or "").strip()
    if not text:
        return ""
    match = re.match(r"([A-Za-z0-9_.-]+)", text)
    if not match:
        return ""
    return match.group(1).replace("_", "-").replace(".", "-").casefold()


if __name__ == "__main__":
    raise SystemExit(main())
