from __future__ import annotations

import json
from pathlib import Path

from smart_video_cut.export_adapters import (
    export_local_mp4,
    export_project_pack_adapter,
    filmgen_handoff_export_status,
    run_runtime_exports,
)


class FakeArtifactStore:
    def __init__(self, mapping: dict[str, Path]) -> None:
        self.mapping = mapping

    def open_local_path(self, artifact_id: str) -> Path | None:
        return self.mapping.get(artifact_id)


def test_export_local_mp4_copies_final_render_artifact(tmp_path: Path) -> None:
    source = tmp_path / "artifact.mp4"
    source.write_bytes(b"rendered video")
    output_dir = tmp_path / "out"

    result = export_local_mp4(
        summary={"source_artifact_refs": {"final_render": {"artifact_id": "final-1"}}},
        artifact_store=FakeArtifactStore({"final-1": source}),
        output_dir=output_dir,
    )

    assert result["ok"] is True
    assert result["status"] == "completed"
    assert result["copied_output_video"] == str(output_dir / "final.mp4")
    assert (output_dir / "final.mp4").read_bytes() == b"rendered video"


def test_runtime_exports_record_project_pack_and_filmgen_status(tmp_path: Path) -> None:
    result = run_runtime_exports(
        summary={"source_artifact_refs": {}},
        artifact_store=FakeArtifactStore({}),
        output_dir=tmp_path / "out",
    )

    assert result["schema"] == "smart_video_cut.local.export_adapter_result.v0"
    assert result["selected_adapter_ids"] == ["export.local_mp4", "export.project_pack", "export.filmgen_handoff"]
    assert result["completed_adapter_ids"] == ["export.filmgen_handoff"]
    assert result["exports"]["local_mp4"]["status"] == "skipped"
    assert result["exports"]["project_pack"]["status"] == "available"
    assert result["exports"]["filmgen_handoff"]["status"] == "completed"
    handoff_path = Path(result["exports"]["filmgen_handoff"]["handoff_path"])
    payload = json.loads(handoff_path.read_text(encoding="utf-8"))
    assert handoff_path.is_file()
    assert payload["schema"] == "smart_video_cut.local.export_filmgen_handoff.v1"
    assert payload["schema_version"] == 1
    assert payload["final_video"]["ready"] is False
    assert payload["filmgen_contract"]["reader_endpoint"] == "/api/filmgen/export-handoff/validate"
    assert payload["compatibility"]["previous_schemas"] == ["smart_video_cut.local.export_filmgen_handoff.v0"]
    assert result["warnings"][0]["code"] == "final_render_not_copied"


def test_export_project_pack_adapter_wraps_project_pack_export(tmp_path: Path) -> None:
    output_dir = tmp_path / "out"
    output_dir.mkdir()
    (output_dir / "local_studio_result.json").write_text(
        '{"input_videos":["input.mp4"],"timeline_plan":{"segments":[{"segment_id":"seg"}]}}',
        encoding="utf-8",
    )

    result = export_project_pack_adapter(
        output_dir=output_dir,
        package_dir=tmp_path / "pack",
        name="Exported Project",
        style_pack_ref="packages/style",
    )

    assert result["schema"] == "smart_video_cut.local.export_project_pack_result.v0"
    assert result["ok"] is True
    assert result["adapter_id"] == "export.project_pack"
    assert Path(result["project_pack_path"]).is_file()
    assert result["pack"]["name"] == "Exported Project"
    assert result["pack"]["style_pack_ref"] == "packages/style"


def test_filmgen_handoff_export_status_writes_handoff_file(tmp_path: Path) -> None:
    result = filmgen_handoff_export_status(
        output_dir=tmp_path / "out",
        summary={"ok": True, "workflow_kind": "creative_edit_runner"},
        local_mp4={"copied_output_video": str(tmp_path / "out" / "final.mp4")},
    )

    assert result["adapter_id"] == "export.filmgen_handoff"
    assert result["ok"] is True
    assert result["status"] == "completed"
    assert result["executed"] is True
    assert result["reason"] == "filmgen_handoff_file_written"

    handoff_path = Path(result["handoff_path"])
    payload = json.loads(handoff_path.read_text(encoding="utf-8"))
    assert handoff_path.is_file()
    assert payload["schema"] == "smart_video_cut.local.export_filmgen_handoff.v1"
    assert payload["handoff_path"] == str(handoff_path)
    assert payload["final_video"]["ready"] is True
    assert payload["toolkit_summary"]["workflow_kind"] == "creative_edit_runner"
    assert payload["assets"][0]["role"] == "primary_import_candidate"
