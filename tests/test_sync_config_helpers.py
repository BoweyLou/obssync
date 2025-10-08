"""
Tests for SyncConfig helper methods (obs_sync/core/models.py).

Validates tag routing, vault mapping, and removal impact analysis.
"""

import pytest
from obs_sync.core.models import SyncConfig, Vault, RemindersList


class TestSyncConfigTagRouting:
    """Test suite for tag routing helpers."""
    
    def test_get_tag_route(self):
        """Test retrieving a tag route."""
        config = SyncConfig(
            vaults=[Vault(name="Work", path="/work", vault_id="v1")],
            tag_routes={
                "v1": {
                    "urgent": {"calendar_id": "cal-1", "import_mode": "all"}
                }
            }
        )
        
        route = config.get_tag_route("v1", "urgent")
        assert route == "cal-1"
    
    def test_get_tag_route_nonexistent(self):
        """Test retrieving non-existent tag route returns None."""
        config = SyncConfig(
            vaults=[Vault(name="Work", path="/work", vault_id="v1")]
        )
        
        route = config.get_tag_route("v1", "nonexistent")
        assert route is None
    
    def test_set_tag_route(self):
        """Test setting a new tag route."""
        config = SyncConfig(
            vaults=[Vault(name="Work", path="/work", vault_id="v1")]
        )
        
        config.set_tag_route("v1", "urgent", "cal-1")
        
        route = config.get_tag_route("v1", "urgent")
        assert route == "cal-1"
    
    def test_set_tag_route_with_import_mode(self):
        """Test setting tag route with import mode."""
        config = SyncConfig(
            vaults=[Vault(name="Work", path="/work", vault_id="v1")]
        )
        
        config.set_tag_route("v1", "project", "cal-2", import_mode="existing_only")
        
        mode = config.get_tag_route_import_mode("v1", "project")
        assert mode == "existing_only"
    
    def test_set_tag_route_import_mode(self):
        """Test updating import mode for existing route."""
        config = SyncConfig(
            vaults=[Vault(name="Work", path="/work", vault_id="v1")],
            tag_routes={
                "v1": {
                    "urgent": {"calendar_id": "cal-1", "import_mode": "existing_only"}
                }
            }
        )
        
        config.set_tag_route_import_mode("v1", "urgent", "all")
        
        mode = config.get_tag_route_import_mode("v1", "urgent")
        assert mode == "all"
    
    def test_remove_tag_route(self):
        """Test removing a tag route."""
        config = SyncConfig(
            vaults=[Vault(name="Work", path="/work", vault_id="v1")],
            tag_routes={
                "v1": {
                    "urgent": {"calendar_id": "cal-1", "import_mode": "all"}
                }
            }
        )
        
        config.remove_tag_route("v1", "urgent")
        
        route = config.get_tag_route("v1", "urgent")
        assert route is None
    
    def test_get_tag_routes_for_vault(self):
        """Test retrieving all tag routes for a vault."""
        config = SyncConfig(
            vaults=[Vault(name="Work", path="/work", vault_id="v1")],
            tag_routes={
                "v1": {
                    "urgent": {"calendar_id": "cal-1", "import_mode": "all"},
                    "project": {"calendar_id": "cal-2", "import_mode": "existing_only"}
                }
            }
        )
        
        routes = config.get_tag_routes_for_vault("v1")
        
        assert len(routes) == 2
        assert any(r["tag"] == "urgent" for r in routes)
        assert any(r["tag"] == "project" for r in routes)
    
    def test_get_route_tag_for_calendar(self):
        """Test reverse lookup of tag by calendar ID."""
        config = SyncConfig(
            vaults=[Vault(name="Work", path="/work", vault_id="v1")],
            tag_routes={
                "v1": {
                    "urgent": {"calendar_id": "cal-1", "import_mode": "all"}
                }
            }
        )
        
        tag = config.get_route_tag_for_calendar("v1", "cal-1")
        assert tag == "urgent"
    
    def test_tag_normalization(self):
        """Test that tags are normalized (hash prefix optional)."""
        config = SyncConfig(
            vaults=[Vault(name="Work", path="/work", vault_id="v1")]
        )
        
        # Set with hash
        config.set_tag_route("v1", "#urgent", "cal-1")
        
        # Retrieve without hash
        route = config.get_tag_route("v1", "urgent")
        assert route == "cal-1"
        
        # Retrieve with hash
        route = config.get_tag_route("v1", "#urgent")
        assert route == "cal-1"


class TestSyncConfigVaultMapping:
    """Test suite for vault mapping helpers."""
    
    def test_get_vault_mapping(self):
        """Test retrieving vault mapping."""
        config = SyncConfig(
            vaults=[Vault(name="Work", path="/work", vault_id="v1")],
            vault_mappings={"v1": "cal-1"}
        )
        
        mapping = config.get_vault_mapping("v1")
        assert mapping == "cal-1"
    
    def test_set_vault_mapping(self):
        """Test setting vault mapping."""
        config = SyncConfig(
            vaults=[Vault(name="Work", path="/work", vault_id="v1")]
        )
        
        config.set_vault_mapping("v1", "cal-1")
        
        mapping = config.get_vault_mapping("v1")
        assert mapping == "cal-1"
    
    def test_get_all_vault_mappings(self):
        """Test retrieving all vault mappings."""
        v1 = Vault(name="Work", path="/work", vault_id="v1")
        v2 = Vault(name="Personal", path="/personal", vault_id="v2")
        
        config = SyncConfig(
            vaults=[v1, v2],
            vault_mappings={"v1": "cal-1", "v2": "cal-2"}
        )
        
        mappings = config.get_all_vault_mappings()
        
        assert len(mappings) == 2
        assert (v1, "cal-1") in mappings
        assert (v2, "cal-2") in mappings


class TestSyncConfigRemoval:
    """Test suite for vault/list removal helpers."""
    
    def test_remove_vault(self):
        """Test removing a vault."""
        config = SyncConfig(
            vaults=[
                Vault(name="Work", path="/work", vault_id="v1"),
                Vault(name="Personal", path="/personal", vault_id="v2")
            ],
            vault_mappings={"v1": "cal-1", "v2": "cal-2"}
        )
        
        removed = config.remove_vault("v1")
        
        assert removed is True
        assert len(config.vaults) == 1
        assert config.vaults[0].vault_id == "v2"
        assert "v1" not in config.vault_mappings
    
    def test_remove_vault_clears_tag_routes(self):
        """Test that removing vault also removes its tag routes."""
        config = SyncConfig(
            vaults=[Vault(name="Work", path="/work", vault_id="v1")],
            tag_routes={
                "v1": {
                    "urgent": {"calendar_id": "cal-1", "import_mode": "all"}
                }
            }
        )
        
        config.remove_vault("v1")
        
        assert "v1" not in config.tag_routes
    
    def test_remove_vault_updates_default(self):
        """Test that removing default vault clears default_vault_id."""
        config = SyncConfig(
            vaults=[Vault(name="Work", path="/work", vault_id="v1")],
            default_vault_id="v1"
        )
        
        config.remove_vault("v1")
        
        assert config.default_vault_id is None
    
    def test_remove_nonexistent_vault(self):
        """Test removing non-existent vault returns False."""
        config = SyncConfig(
            vaults=[Vault(name="Work", path="/work", vault_id="v1")]
        )
        
        removed = config.remove_vault("nonexistent")
        assert removed is False
    
    def test_remove_reminders_list(self):
        """Test removing a reminders list."""
        config = SyncConfig(
            reminders_lists=[
                RemindersList(name="Work", identifier="cal-1", source_name="iCloud", source_type="Local"),
                RemindersList(name="Home", identifier="cal-2", source_name="iCloud", source_type="Local")
            ],
            calendar_ids=["cal-1", "cal-2"],
            default_calendar_id="cal-1"
        )
        
        removed = config.remove_reminders_list("cal-1")
        
        assert removed is True
        assert len(config.reminders_lists) == 1
        assert config.reminders_lists[0].identifier == "cal-2"
        assert "cal-1" not in config.calendar_ids
        assert config.default_calendar_id != "cal-1"
    
    def test_get_vault_removal_impact(self):
        """Test analyzing vault removal impact."""
        config = SyncConfig(
            vaults=[Vault(name="Work", path="/work", vault_id="v1")],
            default_vault_id="v1",
            vault_mappings={"v1": "cal-1"},
            tag_routes={
                "v1": {
                    "urgent": {"calendar_id": "cal-1", "import_mode": "all"}
                }
            }
        )
        
        impact = config.get_vault_removal_impact("v1")
        
        assert impact["will_clear_default"] is True
        assert impact["has_vault_mapping"] is True
        assert impact["tag_routes_count"] == 1
    
    def test_get_list_removal_impact(self):
        """Test analyzing list removal impact."""
        config = SyncConfig(
            vaults=[Vault(name="Work", path="/work", vault_id="v1")],
            reminders_lists=[
                RemindersList(name="Work", identifier="cal-1", source_name="iCloud", source_type="Local")
            ],
            default_calendar_id="cal-1",
            vault_mappings={"v1": "cal-1"},
            tag_routes={
                "v1": {
                    "urgent": {"calendar_id": "cal-1", "import_mode": "all"}
                }
            }
        )
        
        impact = config.get_list_removal_impact("cal-1")
        
        assert impact["will_clear_default"] is True
        assert len(impact["affected_vault_mappings"]) == 1
        assert len(impact["affected_tag_routes"]) == 1


class TestSyncConfigDefaults:
    """Test suite for default vault/calendar helpers."""
    
    def test_default_vault_property(self):
        """Test default_vault property."""
        v1 = Vault(name="Work", path="/work", vault_id="v1")
        config = SyncConfig(
            vaults=[v1],
            default_vault_id="v1"
        )
        
        default = config.default_vault
        assert default == v1
    
    def test_default_vault_path_property(self):
        """Test default_vault_path property."""
        config = SyncConfig(
            vaults=[Vault(name="Work", path="/work", vault_id="v1")],
            default_vault_id="v1"
        )
        
        path = config.default_vault_path
        assert path == "/work"
    
    def test_has_vaults(self):
        """Test has_vaults helper."""
        config = SyncConfig()
        assert config.has_vaults is False
        
        config.vaults = [Vault(name="Work", path="/work", vault_id="v1")]
        assert config.has_vaults is True
    
    def test_has_reminder_lists(self):
        """Test has_reminder_lists helper."""
        config = SyncConfig()
        assert config.has_reminder_lists is False
        
        config.reminders_lists = [
            RemindersList(name="Work", identifier="cal-1", source_name="iCloud", source_type="Local")
        ]
        assert config.has_reminder_lists is True
    
    def test_reminder_list_ids(self):
        """Test reminder_list_ids property."""
        config = SyncConfig(
            reminders_lists=[
                RemindersList(name="Work", identifier="cal-1", source_name="iCloud", source_type="Local"),
                RemindersList(name="Home", identifier="cal-2", source_name="iCloud", source_type="Local")
            ]
        )
        
        ids = config.reminder_list_ids
        assert ids == ["cal-1", "cal-2"]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
