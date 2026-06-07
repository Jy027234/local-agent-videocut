from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Sequence

from smart_video_cut.adapter_registry import list_default_adapters, resolve_adapter_selection
from smart_video_cut.models import LocalEditTask, StylePackageRequest
from smart_video_cut.style_package import create_style_package, default_settings_from_options
from smart_video_cut.batch_runner import run_batch_edits
from smart_video_cut.bundled_runtime import (
    ensure_video_toolkit_available,
    run_edit_with_style_package,
    run_voice_profile_contract,
)
from smart_video_cut.export_adapters import export_project_pack_adapter
from smart_video_cut.pack_manager import load_pack, validate_pack_references
from smart_video_cut.project_manifest import read_project_manifest
from smart_video_cut.protocol_dropbox import (
    get_protocol_dropbox_history,
    import_protocol_dropbox_item,
    initialize_protocol_dropbox,
    requeue_protocol_dropbox_failed,
    run_protocol_dropbox_once,
)
from smart_video_cut.protocol_dropbox_monitor import (
    get_protocol_dropbox_monitor_status,
    run_protocol_dropbox_monitor_loop,
)
from smart_video_cut.protocol_runner import run_protocol_path
from smart_video_cut.toolkit_protocol import inspect_local_toolkit_path, write_local_toolkit_protocol
from smart_video_cut.version_history import get_version_history
from smart_video_cut.watch_queue import run_watch_queue_once
from smart_video_cut.worker_protocol import create_worker_task_package, run_worker_task_package


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Smart Video Cut Local Studio")
    sub = parser.add_subparsers(dest="command", required=True)

    check = sub.add_parser("check", help="Check local dependencies and toolkit bridge.")
    _ = check

    package = sub.add_parser("create-package", help="Create a local style package from a reference video.")
    package.add_argument("--name", required=True)
    package.add_argument("--template-video", required=True)
    package.add_argument("--package-dir", required=True)
    package.add_argument("--description", default="")
    package.add_argument("--duration", type=int, default=20)
    package.add_argument("--aspect-ratio", default="9:16", choices=("9:16", "16:9", "1:1", "4:5"))
    package.add_argument("--resolution", default="720x1280")
    package.add_argument("--quality", default="standard", choices=("draft", "standard", "high"))
    package.add_argument("--subtitle-size", type=int, default=44)
    package.add_argument("--bgm-volume-db", type=float, default=-18.0)
    package.add_argument("--voice-provider", default="edge_tts")

    voice = sub.add_parser("voice-profile", help="Create a reusable voice profile contract via bundled runtime.")
    voice.add_argument("--output-dir", required=True)
    voice.add_argument("--provider-id", default="edge_tts")
    voice.add_argument("--gender", default="male")
    voice.add_argument("--style", default="warm_vlog_narrator")
    voice.add_argument("--sample-text", default="这是一段本地智能剪辑的男声样音。")
    voice.add_argument("--sample-outcome", default="approved")

    cut = sub.add_parser("cut", help="Cut a new video using a specified local style package.")
    cut.add_argument("--style-package", required=True)
    cut.add_argument("--input-video", required=True)
    cut.add_argument("--output-dir", required=True)
    cut.add_argument("--user-request", required=True)
    cut.add_argument("--project-id", default="local_project")
    cut.add_argument("--voiceover-text")
    cut.add_argument("--execute-real-render", action="store_true")
    cut.add_argument("--allow-edge-tts", action="store_true")

    worker_pack = sub.add_parser("worker-pack", help="Write a local worker task package for script or offline handoff.")
    worker_pack.add_argument("--package-dir", required=True)
    worker_pack.add_argument("--package-name", default="")
    worker_pack.add_argument("--style-package", required=True)
    worker_pack.add_argument("--input-video", dest="input_videos", action="append", required=True, help="Repeat this flag to include multiple input videos.")
    worker_pack.add_argument("--output-dir", required=True)
    worker_pack.add_argument("--user-request", required=True)
    worker_pack.add_argument("--project-id", default="local_project")
    worker_pack.add_argument("--voiceover-text")
    worker_pack.add_argument("--confirmed-brief")
    worker_pack.add_argument("--execute-real-render", action="store_true")
    worker_pack.add_argument("--allow-edge-tts", action="store_true")

    worker_run = sub.add_parser("worker-run", help="Execute a local worker task package and write completion.json.")
    worker_run.add_argument("--package-path", required=True)

    batch = sub.add_parser("batch-run", help="Run multiple edit tasks from a JSON file without the UI.")
    batch.add_argument("--tasks-json", required=True, help="JSON file containing a list of edit task objects or {'tasks': [...]}.")
    batch.add_argument("--batch-dir", default="")
    batch.add_argument("--batch-id", default="")
    batch.add_argument("--default-execute-real-render", action="store_true")
    batch.add_argument("--stop-on-error", action="store_true")
    batch.add_argument("--max-retries", type=int, default=0)

    watch = sub.add_parser("watch-queue", help="Scan a directory once and enqueue task JSON files for batch editing.")
    watch.add_argument("--watch-dir", required=True, help="Directory containing task JSON files.")
    watch.add_argument("--batch-root", default="", help="Root directory for generated batch run folders.")
    watch.add_argument("--archive-dir", default="", help="Directory for successfully processed task files.")
    watch.add_argument("--failed-dir", default="", help="Directory for failed task files.")
    watch.add_argument("--pattern", default="*.json", help="Glob pattern for task files.")
    watch.add_argument("--default-execute-real-render", action="store_true")
    watch.add_argument("--stop-on-error", action="store_true")
    watch.add_argument("--max-retries", type=int, default=0)
    watch.add_argument("--dry-run", action="store_true", help="Only list task files and write watch_status.json.")

    adapters = sub.add_parser("adapters", help="List plugin-style adapters and optionally preview adapter selection.")
    adapters.add_argument("--category", default="", help="Filter by category: voice, subtitle, bgm, material_analysis, export.")
    adapters.add_argument("--status", default="", help="Filter by status: ready, requires_setup, planned, disabled.")
    adapters.add_argument("--settings-json", default="", help="Optional visible_settings JSON file for selection preview.")

    export_pack = sub.add_parser("export-project-pack", help="Export an output directory into a ProjectPack.")
    export_pack.add_argument("--output-dir", required=True)
    export_pack.add_argument("--package-dir", required=True)
    export_pack.add_argument("--name", default="")
    export_pack.add_argument("--style-pack-ref", default="")
    export_pack.add_argument("--material-pack-ref", default="")

    validate_project = sub.add_parser("validate-project", help="Validate a project output directory or ProjectPack.")
    validate_project.add_argument("--output-dir", default="")
    validate_project.add_argument("--project-pack", default="")

    protocol_build = sub.add_parser("protocol-build", help="Write local_toolkit_protocol.json for one output directory.")
    protocol_build.add_argument("--output-dir", required=True)

    protocol_inspect = sub.add_parser("protocol-inspect", help="Inspect a local protocol file or directory.")
    protocol_inspect.add_argument("--path", required=True)

    protocol_run = sub.add_parser("protocol-run", help="Execute a runnable local protocol such as worker package, ProjectPack, or FilmGen handoff.")
    protocol_run.add_argument("--path", required=True)
    protocol_run.add_argument("--output-dir", default="")
    protocol_run.add_argument("--style-package", default="")
    protocol_run.add_argument("--user-request", default="")
    protocol_run.add_argument("--voiceover-text")
    protocol_run.add_argument("--confirmed-brief")
    protocol_run.add_argument("--execute-real-render", action="store_true")
    protocol_run.add_argument("--allow-edge-tts", action="store_true")
    protocol_run.add_argument("--disable-memory", action="store_true")

    protocol_dropbox_init = sub.add_parser("protocol-dropbox-init", help="Create a standard local protocol dropbox with inbox, archive, batch_runs, and templates.")
    protocol_dropbox_init.add_argument("--dropbox-dir", default="")

    protocol_dropbox_import = sub.add_parser("protocol-dropbox-import", help="Copy one protocol file or output directory into the standard protocol dropbox inbox.")
    protocol_dropbox_import.add_argument("--dropbox-dir", default="")
    protocol_dropbox_import.add_argument("--source-path", required=True)
    protocol_dropbox_import.add_argument("--label", default="")

    protocol_dropbox_run = sub.add_parser("protocol-dropbox-run", help="Run all standard protocol dropbox inbox queues once.")
    protocol_dropbox_run.add_argument("--dropbox-dir", default="")
    protocol_dropbox_run.add_argument("--default-execute-real-render", action="store_true")
    protocol_dropbox_run.add_argument("--stop-on-error", action="store_true")
    protocol_dropbox_run.add_argument("--max-retries", type=int, default=0)
    protocol_dropbox_run.add_argument("--dry-run", action="store_true")

    protocol_dropbox_monitor = sub.add_parser("protocol-dropbox-monitor", help="Run protocol dropbox polling in the current process and keep writing dropbox_monitor.json.")
    protocol_dropbox_monitor.add_argument("--dropbox-dir", default="")
    protocol_dropbox_monitor.add_argument("--interval-seconds", type=float, default=15.0)
    protocol_dropbox_monitor.add_argument("--max-cycles", type=int, default=0, help="0 means keep polling until interrupted.")
    protocol_dropbox_monitor.add_argument("--default-execute-real-render", action="store_true")
    protocol_dropbox_monitor.add_argument("--stop-on-error", action="store_true")
    protocol_dropbox_monitor.add_argument("--max-retries", type=int, default=0)
    protocol_dropbox_monitor.add_argument("--dry-run", action="store_true")

    protocol_dropbox_monitor_status = sub.add_parser("protocol-dropbox-monitor-status", help="Read current dropbox_monitor.json summary.")
    protocol_dropbox_monitor_status.add_argument("--dropbox-dir", default="")

    protocol_dropbox_history = sub.add_parser("protocol-dropbox-history", help="Read persisted dropbox_history.json entries and alert summary.")
    protocol_dropbox_history.add_argument("--dropbox-dir", default="")
    protocol_dropbox_history.add_argument("--limit", type=int, default=20)
    protocol_dropbox_history.add_argument("--queue-id", default="")
    protocol_dropbox_history.add_argument("--alerts-only", action="store_true")

    protocol_dropbox_requeue = sub.add_parser("protocol-dropbox-requeue-failed", help="Move failed archived protocol files back into the inbox queue for rerun.")
    protocol_dropbox_requeue.add_argument("--dropbox-dir", default="")
    protocol_dropbox_requeue.add_argument("--queue-id", default="all")
    protocol_dropbox_requeue.add_argument("--max-files", type=int, default=20)

    args = parser.parse_args(argv)
    if args.command == "check":
        print(json.dumps(ensure_video_toolkit_available(), ensure_ascii=False, indent=2))
        return 0
    if args.command == "create-package":
        settings = default_settings_from_options(
            duration=args.duration,
            aspect_ratio=args.aspect_ratio,
            resolution=args.resolution,
            quality=args.quality,
            subtitle_size=args.subtitle_size,
            bgm_volume_db=args.bgm_volume_db,
            voice_provider=args.voice_provider,
        )
        payload = create_style_package(
            StylePackageRequest(
                name=args.name,
                description=args.description,
                template_video=Path(args.template_video),
                package_dir=Path(args.package_dir),
                settings=settings,
            )
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.command == "voice-profile":
        summary = run_voice_profile_contract(
            output_dir=Path(args.output_dir),
            provider_id=args.provider_id,
            voice_gender=args.gender,
            voice_style=args.style,
            sample_text=args.sample_text,
            sample_outcome=args.sample_outcome,
        )
        print(json.dumps(summary, ensure_ascii=False, indent=2))
        return 0 if summary.get("ok") is True else 2
    if args.command == "cut":
        result = run_edit_with_style_package(
            LocalEditTask(
                style_package=Path(args.style_package),
                input_video=Path(args.input_video),
                output_dir=Path(args.output_dir),
                user_request=args.user_request,
                project_id=args.project_id,
                voiceover_text=args.voiceover_text,
                execute_real_render=args.execute_real_render,
                allow_edge_tts=args.allow_edge_tts,
            )
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") is True else 2
    if args.command == "worker-pack":
        input_videos = list(args.input_videos or [])
        result = create_worker_task_package(
            package_dir=args.package_dir,
            package_name=args.package_name,
            style_package=args.style_package,
            input_video=input_videos[0] if input_videos else "",
            input_videos=input_videos,
            output_dir=args.output_dir,
            user_request=args.user_request,
            project_id=args.project_id,
            voiceover_text=args.voiceover_text,
            confirmed_brief=args.confirmed_brief,
            execute_real_render=args.execute_real_render,
            allow_edge_tts=args.allow_edge_tts,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") is True else 2
    if args.command == "worker-run":
        result = run_worker_task_package(args.package_path)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") is True else 2
    if args.command == "batch-run":
        data = json.loads(Path(args.tasks_json).read_text(encoding="utf-8"))
        tasks = data.get("tasks") if isinstance(data, dict) else data
        result = run_batch_edits(
            tasks=list(tasks or []),
            batch_dir=args.batch_dir,
            batch_id=args.batch_id,
            default_execute_real_render=args.default_execute_real_render,
            stop_on_error=args.stop_on_error,
            max_retries=args.max_retries,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") is True else 2
    if args.command == "watch-queue":
        result = run_watch_queue_once(
            watch_dir=args.watch_dir,
            batch_root=args.batch_root,
            archive_dir=args.archive_dir,
            failed_dir=args.failed_dir,
            pattern=args.pattern,
            default_execute_real_render=args.default_execute_real_render,
            stop_on_error=args.stop_on_error,
            max_retries=args.max_retries,
            dry_run=args.dry_run,
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("ok") is True else 2
    if args.command == "adapters":
        payload = {"ok": True, "manifest": list_default_adapters(category=args.category, status=args.status)}
        if args.settings_json:
            data = json.loads(Path(args.settings_json).read_text(encoding="utf-8"))
            settings = data.get("visible_settings") if isinstance(data, dict) and isinstance(data.get("visible_settings"), dict) else data
            payload["selection"] = resolve_adapter_selection(settings if isinstance(settings, dict) else {})
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.command == "export-project-pack":
        payload = export_project_pack_adapter(
            output_dir=args.output_dir,
            package_dir=args.package_dir,
            name=args.name,
            style_pack_ref=args.style_pack_ref,
            material_pack_ref=args.material_pack_ref,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0
    if args.command == "validate-project":
        pack_validation = {}
        if args.project_pack:
            pack_validation = validate_pack_references(load_pack(args.project_pack))
        manifest = read_project_manifest(args.output_dir) if args.output_dir else None
        version_history = get_version_history(args.output_dir) if args.output_dir else {}
        warnings = []
        if args.output_dir and manifest is None:
            warnings.append({
                "code": "project_manifest_not_found",
                "message": "输出目录未找到 project_manifest.json",
                "path": str(Path(args.output_dir) / "project_manifest.json"),
            })
        warnings.extend(pack_validation.get("warnings") or [])
        payload = {
            "ok": not (pack_validation.get("errors") or []),
            "manifest": manifest or {},
            "version_history": version_history,
            "pack_validation": pack_validation,
            "warnings": warnings,
            "errors": pack_validation.get("errors") or [],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload["ok"] else 2
    if args.command == "protocol-build":
        payload = write_local_toolkit_protocol(output_dir=args.output_dir)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("ok") is True else 2
    if args.command == "protocol-inspect":
        payload = inspect_local_toolkit_path(args.path)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("ok") is True else 2
    if args.command == "protocol-run":
        payload = run_protocol_path(
            args.path,
            output_dir=args.output_dir,
            style_package=args.style_package,
            user_request=args.user_request,
            voiceover_text=args.voiceover_text,
            confirmed_brief=args.confirmed_brief,
            execute_real_render=args.execute_real_render,
            allow_edge_tts=args.allow_edge_tts,
            use_memory=False if args.disable_memory else None,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("ok") is True else 2
    if args.command == "protocol-dropbox-init":
        payload = initialize_protocol_dropbox(dropbox_dir=args.dropbox_dir)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("ok") is True else 2
    if args.command == "protocol-dropbox-import":
        payload = import_protocol_dropbox_item(
            dropbox_dir=args.dropbox_dir,
            source_path=args.source_path,
            label=args.label,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("ok") is True else 2
    if args.command == "protocol-dropbox-run":
        payload = run_protocol_dropbox_once(
            dropbox_dir=args.dropbox_dir,
            default_execute_real_render=args.default_execute_real_render,
            stop_on_error=args.stop_on_error,
            max_retries=args.max_retries,
            dry_run=args.dry_run,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("ok") is True else 2
    if args.command == "protocol-dropbox-monitor":
        payload = run_protocol_dropbox_monitor_loop(
            dropbox_dir=args.dropbox_dir,
            interval_seconds=args.interval_seconds,
            max_cycles=args.max_cycles,
            default_execute_real_render=args.default_execute_real_render,
            stop_on_error=args.stop_on_error,
            max_retries=args.max_retries,
            dry_run=args.dry_run,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("ok") is True else 2
    if args.command == "protocol-dropbox-monitor-status":
        payload = get_protocol_dropbox_monitor_status(dropbox_dir=args.dropbox_dir)
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("ok") is True else 2
    if args.command == "protocol-dropbox-history":
        payload = get_protocol_dropbox_history(
            dropbox_dir=args.dropbox_dir,
            limit=args.limit,
            queue_id=args.queue_id,
            alerts_only=args.alerts_only,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("ok") is True else 2
    if args.command == "protocol-dropbox-requeue-failed":
        payload = requeue_protocol_dropbox_failed(
            dropbox_dir=args.dropbox_dir,
            queue_id=args.queue_id,
            max_files=args.max_files,
        )
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if payload.get("ok") is True else 2
    return 2


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
