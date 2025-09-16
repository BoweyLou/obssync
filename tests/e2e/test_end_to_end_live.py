#!/usr/bin/env python3
import os
import json
from pathlib import Path
from datetime import datetime, timedelta

import pytest

from obs_tools.commands import collect_obsidian_tasks as collect_obs
from obs_tools.commands import collect_reminders_tasks as collect_rem
from obs_tools.commands import build_sync_links as build_links
from obs_tools.commands import sync_links_apply as sync_apply
from obs_tools.commands import create_missing_counterparts as create_missing


@pytest.mark.e2e_live
@pytest.mark.macos
@pytest.mark.eventkit
def test_end_to_end_live_against_reminders(tmp_path, monkeypatch):
    """
    Live E2E against a dedicated Apple Reminders list (macOS only).

    Safety:
      - Requires env var E2E_REMINDERS_LIST_ID with a dedicated test list identifier.
      - Uses a temp HOME so that configs/backups/logs are isolated.
      - Creates uniquely-prefixed test items and does not delete existing ones.
    """
    list_id = os.environ.get("E2E_REMINDERS_LIST_ID")
    if not list_id:
        pytest.skip("E2E_REMINDERS_LIST_ID not set; provide a dedicated Reminders list identifier")

    # Isolate all paths under a temp HOME
    monkeypatch.setenv("HOME", str(tmp_path))

    # Prepare temp directories
    cfg_dir = Path(tmp_path) / ".config" / "obs-tools"
    cfg_dir.mkdir(parents=True, exist_ok=True)

    # Prepare Obsidian vault
    vault_dir = Path(tmp_path) / "vault"
    vault_dir.mkdir()
    inbox_file = vault_dir / "Inbox.md"
    inbox_file.write_text("# Inbox\n\n")

    # Write app.json to direct Reminders->Obsidian creations into our temp vault
    app_json = {
        "min_score": 0.7,
        "days_tolerance": 1,
        "include_done": False,
        "ignore_common": True,
        "prune_days": -1,
        "creation_defaults": {
            "obs_inbox_file": str(inbox_file),
            "rem_default_calendar_id": list_id,
            "max_creates_per_run": 10,
            "since_days": 365,
            "include_done": False
        },
        "obs_to_rem_rules": [],
        "rem_to_obs_rules": [
            {"list_name": "", "target_file": str(inbox_file)}
        ]
    }
    (Path(tmp_path) / ".config" / "obs-tools" / "app.json").write_text(json.dumps(app_json, indent=2))

    # Create Obsidian content with one matchable task and one duplicate-title case + code block
    today = datetime.now().date()
    due_str = (today + timedelta(days=3)).isoformat()
    prefix = f"[E2E {datetime.now().strftime('%Y%m%d%H%M%S')}]"

    tasks_md = vault_dir / "Tasks.md"
    tasks_md.write_text(
        f"""
# Tasks
- [ ] {prefix} Buy milk 📅 {due_str} #home ^t-obs1
- [ ] {prefix} Duplicate title example 📅 {due_str} #work ^t-dup1

```markdown
- [ ] Should not parse in code block ^t-ignored
```
        """.strip()
    )

    # Write reminders lists config
    lists_cfg = Path(tmp_path) / ".config" / "reminders_lists.json"
    lists_cfg.write_text(json.dumps([{"name": "E2E", "identifier": list_id}]))

    # Seed one live Reminders item that should link and one unlinked
    # Use RemindersGateway directly
    from reminders_gateway import RemindersGateway
    gw = RemindersGateway()
    created1 = gw.create_reminder(title=f"{prefix} Buy milk", calendar_id=list_id, properties={"due_date": due_str})
    created2 = gw.create_reminder(title=f"{prefix} Unlinked from reminders", calendar_id=list_id, properties={"due_date": due_str})
    assert created1 and created2

    # Prepare paths for JSON artifacts
    obs_index = Path(tmp_path) / ".config" / "obsidian_tasks_index.json"
    rem_index = Path(tmp_path) / ".config" / "reminders_tasks_index.json"
    links_json = Path(tmp_path) / ".config" / "sync_links.json"
    obs_cache = Path(tmp_path) / ".config" / "obsidian_tasks_cache.json"
    rem_cache = Path(tmp_path) / ".config" / "reminders_snapshot_cache.json"
    changeset = Path(tmp_path) / ".config" / "obs-tools" / "backups" / "sync_changeset.json"

    # Collect Obsidian
    assert collect_obs.main(["--root", str(vault_dir), "--output", str(obs_index), "--cache", str(obs_cache), "--ignore-common"]) == 0

    # Collect Reminders (live)
    assert collect_rem.main(["--use-config", "--config", str(lists_cfg), "--output", str(rem_index), "--cache", str(rem_cache)]) == 0

    # Build links; expect the Buy milk pair to be suggested
    assert build_links.main(["--obs", str(obs_index), "--rem", str(rem_index), "--output", str(links_json), "--min-score", "0.6", "--days-tol", "1"]) == 0
    links = json.loads(links_json.read_text()).get("links", [])
    assert any(prefix in (l.get("fields", {}).get("obs_title", "") + l.get("fields", {}).get("rem_title", "")) for l in links)

    # Flip the Obsidian task to done and apply; expect live reminder completion
    txt = tasks_md.read_text()
    tasks_md.write_text(txt.replace(f"- [ ] {prefix} Buy milk", f"- [x] {prefix} Buy milk"))
    assert sync_apply.main(["--obs", str(obs_index), "--rem", str(rem_index), "--links", str(links_json), "--apply", "--changes-out", str(changeset)]) == 0

    # Verify live reminder completion
    reminders, cal_cache = gw.get_reminders_from_lists([{"identifier": list_id}])
    completed = [r for r in reminders if (r.title() or "").startswith(f"{prefix} Buy milk") and r.isCompleted()]
    assert completed, "Expected the matched reminder to be completed via apply"

    # Create missing both ways and apply
    assert create_missing.main(["--obs", str(obs_index), "--rem", str(rem_index), "--links", str(links_json), "--direction", "both", "--apply", "--max", "5", "--since", "365"]) == 0

    # Verify a new live reminder was created for the duplicate-title obs task (count grew)
    reminders_after, _ = gw.get_reminders_from_lists([{"identifier": list_id}])
    assert len(reminders_after) >= len(reminders) + 1

    # Verify Obsidian counterpart created for the previously unlinked live reminder into inbox file
    inbox_text = inbox_file.read_text()
    assert prefix in inbox_text and "Unlinked from reminders" in inbox_text

    # Edge assertions: code-block 'task' never indexed
    obs_data = json.loads(obs_index.read_text())
    raws = [t.get("raw", "") for t in obs_data.get("tasks", {}).values()]
    assert not any("Should not parse in code block" in r for r in raws)

