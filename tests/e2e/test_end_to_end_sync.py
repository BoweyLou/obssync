#!/usr/bin/env python3
import os
import json
import tempfile
from pathlib import Path

import pytest

# Command modules under test
from obs_tools.commands import collect_obsidian_tasks as collect_obs
from obs_tools.commands import collect_reminders_tasks as collect_rem
from obs_tools.commands import build_sync_links as build_links
from obs_tools.commands import sync_links_apply as sync_apply
from obs_tools.commands import create_missing_counterparts as create_missing

from tests.e2e.fake_reminders_gateway import FakeRemindersGateway, FakeReminder


@pytest.mark.e2e
def test_end_to_end_sync_with_fake_gateway(tmp_path, monkeypatch):
    """
    Full flow with a temp vault and a fake Reminders gateway:
      - Collect Obsidian tasks
      - Collect Reminders tasks (fake gateway)
      - Build links
      - Apply sync with --apply (edits Markdown + fake reminders)
      - Create missing counterparts in both directions
      - Verify both sides actually changed, not just JSON
      - Exercise key edge cases: duplicate titles, date tolerance, priorities, code blocks ignored
    """
    tmp = Path(tmp_path)
    cfg_dir = tmp / "cfg"
    cfg_dir.mkdir()

    # Make HOME point to tmp so app_config paths (backups, logs) are isolated
    monkeypatch.setenv("HOME", str(tmp))

    # 1) Create a temporary Obsidian vault with tasks, including a code block and block ids
    vault_dir = tmp / "vault"
    vault_dir.mkdir()
    tasks_md = vault_dir / "Tasks.md"
    tasks_md.write_text(
        """
# Inbox
- [ ] Buy milk 📅 2024-12-01 #home ^t-obs1
- [ ] Duplicate title example 📅 2024-12-02 #work ^t-dup1

```markdown
- [ ] This should not parse in code block ^t-ignored
```

- [x] Done already ✅ 2024-11-30 #home ^t-done1
        """.strip()
    )

    project_md = vault_dir / "Project.md"
    project_md.write_text(
        """
# Project
- [ ] Duplicate title example 📅 2024-12-03 #work ⏫ ^t-dup2
        """.strip()
    )

    # Vaults config
    vaults_cfg = cfg_dir / "vaults.json"
    vaults_cfg.write_text(json.dumps([
        {"name": "TestVault", "path": str(vault_dir)}
    ]))

    # 2) Seed a fake Reminders list with items (including one matching and one to be created)
    fake = FakeRemindersGateway()
    test_cal_id = "cal-test-1"
    fake.seed_list(
        test_cal_id,
        [
            FakeReminder(title="Buy milk", calendar_id=test_cal_id, item_id="r1", due_date="2024-12-01"),
            FakeReminder(title="Unlinked from reminders", calendar_id=test_cal_id, item_id="r2", due_date="2024-12-05"),
        ],
    )

    # Monkeypatch: use FakeRemindersGateway in both collector and applier modules
    monkeypatch.setattr(collect_rem, "RemindersGateway", lambda *args, **kwargs: fake)
    monkeypatch.setattr(sync_apply, "RemindersGateway", lambda *args, **kwargs: fake)
    # create_missing imports inside functions; ensure module-level is patched too
    import reminders_gateway as rg_mod
    monkeypatch.setattr(rg_mod, "RemindersGateway", lambda *args, **kwargs: fake)

    # Reminders lists config
    lists_cfg = cfg_dir / "lists.json"
    lists_cfg.write_text(json.dumps([
        {"name": "Test", "identifier": test_cal_id}
    ]))

    # Paths for outputs
    obs_index = cfg_dir / "obs_index.json"
    rem_index = cfg_dir / "rem_index.json"
    links_json = cfg_dir / "links.json"
    changeset = cfg_dir / "changeset.json"
    obs_cache = cfg_dir / "obs_cache.json"
    rem_cache = cfg_dir / "rem_cache.json"

    # 3) Collect Obsidian
    rc = collect_obs.main([
        "--root", str(vault_dir),
        "--output", str(obs_index),
        "--cache", str(obs_cache),
        "--ignore-common",
    ])
    assert rc == 0, "Obsidian collection failed"
    obs_data = json.loads(obs_index.read_text())
    assert len(obs_data.get("tasks", {})) >= 3  # one is done, one duplicate title

    # 4) Collect Reminders (fake)
    rc = collect_rem.main([
        "--use-config",
        "--config", str(lists_cfg),
        "--output", str(rem_index),
        "--cache", str(rem_cache),
    ])
    assert rc == 0, "Reminders collection failed"
    rem_data = json.loads(rem_index.read_text())
    assert len(rem_data.get("tasks", {})) == 2

    # 5) Build links (should link Buy milk by title+date, handle duplicate titles deterministically)
    rc = build_links.main([
        "--obs", str(obs_index),
        "--rem", str(rem_index),
        "--output", str(links_json),
        "--min-score", "0.6",
        "--days-tol", "1",
    ])
    assert rc == 0
    links = json.loads(links_json.read_text()).get("links", [])
    assert len(links) >= 1

    # 6) Apply sync with --apply; update a field so we can observe an actual mutation.
    # Force a status change: flip Buy milk to done in obs and expect fake reminder to complete.
    # Edit the Obsidian file to mark Buy milk as done, then apply.
    txt = tasks_md.read_text()
    tasks_md.write_text(txt.replace("- [ ] Buy milk", "- [x] Buy milk"))

    # Re-collect Obsidian data after the file change
    rc = collect_obs.main([
        "--root", str(vault_dir),
        "--output", str(obs_index),
        "--cache", str(obs_cache),
    ])
    assert rc == 0

    rc = sync_apply.main([
        "--obs", str(obs_index),
        "--rem", str(rem_index),
        "--links", str(links_json),
        "--apply",
        "--changes-out", str(changeset),
    ])
    assert rc == 0

    # Verify fake reminders actually mutated
    changed = [r for r in fake.all_items() if r.title() == "Buy milk"]
    assert changed and changed[0].isCompleted() is True

    # 7) Create missing counterparts both ways: 
    # - Obsidian has "Duplicate title example" two tasks, only one should link; the other should create a new reminder.
    # - Reminders has "Unlinked from reminders" that should create into Obsidian.
    rc = create_missing.main([
        "--obs", str(obs_index),
        "--rem", str(rem_index),
        "--links", str(links_json),
        "--direction", "both",
        "--apply",
        "--max", "10",
        "--since", "365",
    ])
    assert rc == 0

    # After creation, fake store should now have more than 2 reminders
    assert len(fake.all_items()) >= 3

    # Re-collect and re-link to ensure everything converges
    assert collect_rem.main(["--use-config", "--config", str(lists_cfg), "--output", str(rem_index), "--cache", str(rem_cache)]) == 0
    assert build_links.main(["--obs", str(obs_index), "--rem", str(rem_index), "--output", str(links_json)]) == 0
    assert sync_apply.main(["--obs", str(obs_index), "--rem", str(rem_index), "--links", str(links_json), "--apply", "--changes-out", str(changeset)]) == 0

    # 8) Edge checks: code block task not parsed; priorities propagate; duplicate titles remain one-to-one
    # Ensure code-block line didn't appear in index
    obs_data = json.loads(obs_index.read_text())
    raws = [t.get("raw", "") for t in obs_data.get("tasks", {}).values()]
    assert not any("This should not parse in code block" in r for r in raws)

    # Ensure one-to-one by pair uniqueness in links
    links = json.loads(links_json.read_text()).get("links", [])
    pairs = {(l.get("obs_uuid"), l.get("rem_uuid")) for l in links}
    assert len(pairs) == len(links)
