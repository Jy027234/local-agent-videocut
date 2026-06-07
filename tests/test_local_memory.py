from __future__ import annotations

from pathlib import Path

from smart_video_cut import local_memory


def test_memory_entry_is_saved_and_used_in_context(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(local_memory, "MEMORY_DIR", tmp_path)
    monkeypatch.setattr(local_memory, "MEMORY_PATH", tmp_path / "agent_skill_memory.json")

    saved = local_memory.add_memory_entry(
        memory_type="subtitle_rule",
        title="字幕规则",
        content="字幕要大，必须黑描边。",
        tags=["字幕", "快闪"],
        importance=5,
    )

    assert saved["ok"] is True
    summary = local_memory.memory_summary()
    assert summary["entry_count"] == 1
    assert "字幕要大" in summary["context_preview"]


def test_memory_can_be_applied_to_user_request(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(local_memory, "MEMORY_DIR", tmp_path)
    monkeypatch.setattr(local_memory, "MEMORY_PATH", tmp_path / "agent_skill_memory.json")

    local_memory.add_memory_entry(
        memory_type="brand_rule",
        title="品牌规则",
        content="不要使用夸张虚假承诺。",
        importance=4,
    )

    merged, context = local_memory.apply_memory_to_user_request("做一个防盗门广告。")

    assert "做一个防盗门广告" in merged
    assert "不要使用夸张虚假承诺" in merged
    assert context


def test_disabled_memory_is_not_injected(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setattr(local_memory, "MEMORY_DIR", tmp_path)
    monkeypatch.setattr(local_memory, "MEMORY_PATH", tmp_path / "agent_skill_memory.json")

    local_memory.add_memory_entry(
        memory_type="editing_preference",
        title="禁用偏好",
        content="这条不应注入。",
        enabled=False,
    )

    merged, context = local_memory.apply_memory_to_user_request("保持原要求。")

    assert merged == "保持原要求。"
    assert context == ""
