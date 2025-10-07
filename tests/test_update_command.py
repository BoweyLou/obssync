import builtins
from unittest.mock import MagicMock

import pytest

from obs_sync.commands.update import UpdateCommand


@pytest.fixture()
def update_command():
    return UpdateCommand(config=MagicMock(), verbose=False)


def test_handle_untracked_changes_proceeds_by_default(monkeypatch, update_command):
    monkeypatch.setattr(builtins, "input", lambda prompt="": "")
    assert update_command._handle_uncommitted_changes(["?? test_file.py"])


def test_handle_untracked_changes_can_cancel(monkeypatch, update_command):
    monkeypatch.setattr(builtins, "input", lambda prompt="": "n")
    assert update_command._handle_uncommitted_changes(["?? test_file.py"]) is False


def test_handle_tracked_changes_requires_confirmation(monkeypatch, update_command):
    monkeypatch.setattr(builtins, "input", lambda prompt="": "")
    assert update_command._handle_uncommitted_changes([" M obs_sync/main.py"]) is False


def test_handle_tracked_changes_can_continue(monkeypatch, update_command):
    monkeypatch.setattr(builtins, "input", lambda prompt="": "y")
    assert update_command._handle_uncommitted_changes(["M  obs_sync/main.py"])
