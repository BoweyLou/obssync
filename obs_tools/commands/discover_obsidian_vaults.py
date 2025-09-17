#!/usr/bin/env python3
"""
Discover Obsidian vaults across common locations, confirm with the user,
and save the results. On subsequent runs, confirm the saved list or reset
and re-discover.

Behavior:
  - First run: searches common locations for vaults, lists them, asks to accept,
    search deeper, or manually add paths. On accept, writes to config file.
  - Later runs: reads the config file, shows the saved vaults, and asks to
    confirm. If not correct, clears the file and re-runs discovery.

Definition of a vault:
  - A directory containing a ".obsidian" subdirectory.
  - If manually added, the script will still allow saving even if the marker
    is missing (you will be warned).

Config file location:
  - Default: ~/.config/obsidian_vaults.json
  - Override with: --config /path/to/file.json

Notes:
  - "Search deeper" increases the recursion depth within common locations.
  - Common locations include iCloud Obsidian folder (macOS), Documents, Desktop,
    Dropbox/OneDrive/Google Drive default macOS paths, and the Home folder
    (limited depth).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Iterable, List, Optional, Set, Tuple

# Add the project root to the path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

# Import centralized path configuration
from app_config import get_path
from lib.vault_organization import generate_stable_vault_id


@dataclass(frozen=True)
class Vault:
    name: str
    path: str
    # Vault-based organization fields
    vault_id: str  # Stable UUID for the vault
    is_default: bool = False  # Primary vault for catch-all
    associated_list_id: Optional[str] = None  # Reminders list UUID
    catch_all_file_path: Optional[str] = None  # Full path to OtherAppleReminders.md


def path_is_vault(path: str) -> bool:
    return os.path.isdir(os.path.join(path, ".obsidian"))


def human_list(vaults: List[Vault]) -> str:
    if not vaults:
        return "(none)"
    lines = []
    for i, v in enumerate(vaults, 1):
        suffix = " [default]" if v.is_default else ""
        lines.append(f"{i}. {v.name}  —  {v.path}{suffix}")
    return "\n".join(lines)


def default_candidate_roots() -> List[str]:
    home = os.path.expanduser("~")
    candidates = [
        # macOS iCloud Obsidian location
        os.path.join(home, "Library", "Mobile Documents", "iCloud~md~obsidian", "Documents"),
        # Common personal folders
        os.path.join(home, "Documents"),
        os.path.join(home, "Desktop"),
        os.path.join(home, "Obsidian"),
        # Dropbox/OneDrive/Google Drive typical macOS paths
        os.path.join(home, "Dropbox"),
        os.path.join(home, "Library", "CloudStorage", "Dropbox"),
        os.path.join(home, "Library", "CloudStorage", "OneDrive*"),
        os.path.join(home, "Library", "CloudStorage", "GoogleDrive*"),
        # Fallback to HOME (scanned with shallow depth by default)
        home,
    ]
    # Expand any globs like OneDrive*/GoogleDrive*
    expanded: List[str] = []
    import glob

    for c in candidates:
        if any(ch in c for ch in ["*", "?", "["]):
            expanded.extend(glob.glob(c))
        else:
            expanded.append(c)

    # Deduplicate while preserving order
    seen: Set[str] = set()
    result: List[str] = []
    for p in expanded:
        ap = os.path.abspath(os.path.expanduser(p))
        if ap not in seen and os.path.isdir(ap):
            seen.add(ap)
            result.append(ap)
    return result


def find_vaults(roots: List[str], max_depth: int = 2) -> List[Vault]:
    found: List[Vault] = []
    seen_paths: Set[str] = set()

    def walk_dir(base: str, depth: int) -> None:
        if depth < 0:
            return
        try:
            with os.scandir(base) as it:
                entries = list(it)
        except (PermissionError, FileNotFoundError):
            return

        # Check base itself
        if path_is_vault(base):
            ap = os.path.abspath(base)
            if ap not in seen_paths:
                seen_paths.add(ap)
                found.append(Vault(
                    name=os.path.basename(ap) or ap,
                    path=ap,
                    vault_id=generate_stable_vault_id(ap)
                ))
            # Do not descend into a vault further
            return

        if depth == 0:
            return

        for e in entries:
            if not e.is_dir(follow_symlinks=False):
                continue
            name = e.name
            # skip typical noisy dirs
            if name.startswith('.') and name != '.obsidian':
                continue
            if name in {"node_modules", "venv", "__pycache__", "target", "build"}:
                continue
            walk_dir(os.path.join(base, name), depth - 1)

    for r in roots:
        walk_dir(r, max_depth)

    # Sort by path for stable display
    found.sort(key=lambda v: v.path.lower())
    return found


def prompt(msg: str, default: str | None = None) -> str:
    suffix = f" [{default}]" if default else ""
    try:
        val = input(f"{msg}{suffix}: ").strip()
    except EOFError:
        print("\nInput stream closed. Exiting.")
        sys.exit(1)
    if not val and default is not None:
        return default
    return val


def save_config(vaults: List[Vault], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)

    default_vault_id: Optional[str] = None
    payload_vaults = []
    for v in vaults:
        vault_id = v.vault_id or generate_stable_vault_id(v.path)
        if v.is_default and not default_vault_id:
            default_vault_id = vault_id

        payload_vaults.append({
            "name": v.name,
            "path": v.path,
            "vault_id": vault_id,
            "is_default": v.is_default,
            "associated_list_id": v.associated_list_id,
            "catch_all_file_path": v.catch_all_file_path,
        })

    payload = {
        "version": 2,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "vaults": payload_vaults,
    }
    if default_vault_id:
        payload["default_vault_id"] = default_vault_id

    with open(path, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"Saved {len(vaults)} vault(s) to {path}")


def load_config(path: str) -> List[Vault] | None:
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        vault_entries: List[dict]
        default_vault_id: Optional[str] = None

        if isinstance(data, dict):
            vault_entries = data.get("vaults", [])
            default_vault_id = data.get("default_vault_id")
        elif isinstance(data, list):
            vault_entries = data
        else:
            return None

        vaults: List[Vault] = []
        for entry in vault_entries:
            if not isinstance(entry, dict) or "path" not in entry:
                continue

            path = os.path.abspath(os.path.expanduser(str(entry["path"])))
            name = str(entry.get("name") or os.path.basename(path))
            vault_id = entry.get("vault_id") or generate_stable_vault_id(path)
            is_default = bool(entry.get("is_default", False))
            if default_vault_id and vault_id == default_vault_id:
                is_default = True

            vaults.append(Vault(
                name=name,
                path=path,
                vault_id=vault_id,
                is_default=is_default,
                associated_list_id=entry.get("associated_list_id"),
                catch_all_file_path=entry.get("catch_all_file_path"),
            ))

        return vaults
    except Exception as e:
        print(f"Warning: failed to read config {path}: {e}")
        return None


def confirm_saved(vaults: List[Vault]) -> bool:
    print("Found saved vaults:")
    print(human_list(vaults))
    ans = prompt("Use these vaults? (Y)es/(N)o", default="Y").lower()
    return ans in ("y", "yes", "")


def interactive_discovery(config_path: str, initial_depth: int) -> None:
    roots = default_candidate_roots()
    depth = initial_depth
    while True:
        print("")
        print(f"Scanning common locations (depth {depth})…")
        vaults = find_vaults(roots, max_depth=depth)
        if not vaults:
            print("No vaults found yet.")
        else:
            print("Discovered vaults:")
            print(human_list(vaults))

        print("")
        print("Options: [A]ccept, [D]eeper search, [M]anually add, [R]escan, [Q]uit")
        choice = prompt("Choose", default="A").strip().lower()

        if choice in ("a", ""):
            if not vaults:
                print("Nothing to save. Please search deeper or add manually.")
                continue
            save_config(vaults, config_path)
            return
        elif choice == "d":
            d_str = prompt("Set new max depth (current {depth})", default=str(depth))
            try:
                depth = max(0, int(d_str))
            except ValueError:
                print("Please enter a valid integer for depth.")
        elif choice == "m":
            print("Enter absolute folder paths for vaults. Blank line to finish.")
            manual: List[Vault] = []
            while True:
                p = input().strip()
                if not p:
                    break
                ap = os.path.abspath(os.path.expanduser(p))
                if not os.path.isdir(ap):
                    print(f"  Skipping (not a folder): {ap}")
                    continue
                nm = os.path.basename(ap) or ap
                if not path_is_vault(ap):
                    print(f"  Warning: {ap} does not contain a .obsidian folder (saving anyway).")
                manual.append(Vault(name=nm, path=ap, vault_id=generate_stable_vault_id(ap)))
            # merge and dedupe by path
            combined = {v.path: v for v in (vaults + manual)}
            vaults = list(combined.values())
            print("Updated vault list:")
            print(human_list(vaults))
        elif choice == "r":
            # re-run discovery with same depth
            continue
        elif choice == "q":
            print("Aborted by user.")
            sys.exit(0)
        else:
            print("Unrecognized choice.")


def main(argv: List[str]) -> int:
    parser = argparse.ArgumentParser(description="Discover Obsidian vaults and save them to a config file.")
    parser.add_argument("--config", default=get_path("obsidian_vaults"), help="Config JSON file path (default: ~/.config/obsidian_vaults.json)")
    parser.add_argument("--depth", type=int, default=2, help="Initial search depth for discovery (default: 2)")
    args = parser.parse_args(argv)

    cfg_path = os.path.abspath(os.path.expanduser(args.config))

    existing = load_config(cfg_path)
    if existing:
        if confirm_saved(existing):
            print("Confirmed. Nothing to do.")
            return 0
        else:
            try:
                os.remove(cfg_path)
            except OSError:
                pass
            print("Cleared saved config. Starting fresh discovery…")

    interactive_discovery(cfg_path, initial_depth=args.depth)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
