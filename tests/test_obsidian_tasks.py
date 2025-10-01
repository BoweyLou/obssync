#!/usr/bin/env python3
"""Tests for ObsidianTaskManager helpers."""

import os
import tempfile

from obs_sync.obsidian.tasks import ObsidianTaskManager


def _write_markdown(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def test_delete_task_without_block_id() -> None:
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = os.path.join(tmpdir, "Vault")
        os.makedirs(vault_path)
        note_path = os.path.join(vault_path, "Tasks.md")
        _write_markdown(
            note_path,
            "- [ ] Task without block id\n- [ ] Another task\n",
        )

        manager = ObsidianTaskManager()
        tasks = manager.list_tasks(vault_path)
        assert len(tasks) == 2

        target = next(task for task in tasks if task.description == "Task without block id")
        assert not target.block_id

        deleted = manager.delete_task(target)
        assert deleted, "Expected task removal to succeed without block ID"

        with open(note_path, "r", encoding="utf-8") as handle:
            remaining = handle.read()

        assert "Task without block id" not in remaining
        assert "Another task" in remaining


if __name__ == "__main__":
    test_delete_task_without_block_id()
    print("✅ Obsidian task manager tests passed")
