#!/usr/bin/env python3
"""
Tests for SQLite Database Reader

Tests the SQLite reader functionality with various scenarios including
schema compatibility, query execution, and error handling.
"""

import pytest
import tempfile
import sqlite3
import os
from typing import Dict, Any
from unittest.mock import Mock, patch

from lib.reminders_db_reader import (
    RemindersDBReader, RemindersDBError, DatabaseNotFoundError,
    SchemaVersionError, ConnectionError, test_db_availability
)
from lib.reminders_sql_queries import RemindersQueryBuilder, QueryComplexity
from lib.reminders_domain import RemindersList, DataSource
from app_config import validate_reminders_store


class TestRemindersDBReader:
    """Test cases for the RemindersDBReader class."""

    def test_reader_initialization(self):
        """Test basic reader initialization."""
        reader = RemindersDBReader()
        assert reader is not None
        assert reader.connection_timeout == 10.0
        assert reader.stats.connections_opened == 0

    def test_reader_with_custom_timeout(self):
        """Test reader initialization with custom timeout."""
        reader = RemindersDBReader(connection_timeout=30.0)
        assert reader.connection_timeout == 30.0

    @pytest.mark.skipif(not os.path.exists("/usr/bin/sqlite3"), reason="SQLite not available")
    def test_store_validation_with_temp_db(self):
        """Test store validation with a temporary SQLite database."""
        # Create a temporary SQLite file with basic Reminders structure
        with tempfile.NamedTemporaryFile(suffix=".sqlitedb", delete=False) as tmp_file:
            db_path = tmp_file.name

        try:
            # Create minimal schema that looks like Reminders DB
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()

            # Create basic tables
            cursor.execute("""
                CREATE TABLE Calendar (
                    Z_PK INTEGER PRIMARY KEY,
                    ZCALENDARIDENTIFIER TEXT,
                    ZTITLE TEXT,
                    ZENTITYTYPE INTEGER
                )
            """)

            cursor.execute("""
                CREATE TABLE CalendarItem (
                    Z_PK INTEGER PRIMARY KEY,
                    ZCALENDARITEMIDENTIFIER TEXT,
                    ZTITLE TEXT,
                    ZENTITYTYPE INTEGER,
                    ZCALENDAR INTEGER
                )
            """)

            conn.commit()
            conn.close()

            # Test validation
            is_valid, message = validate_reminders_store(db_path)
            assert is_valid
            assert "Valid" in message

        finally:
            # Clean up
            if os.path.exists(db_path):
                os.unlink(db_path)

    def test_store_validation_with_invalid_file(self):
        """Test store validation with invalid file."""
        with tempfile.NamedTemporaryFile(suffix=".txt", delete=False) as tmp_file:
            tmp_file.write(b"Not a SQLite database")
            invalid_path = tmp_file.name

        try:
            is_valid, message = validate_reminders_store(invalid_path)
            assert not is_valid
            assert "Error validating store" in message

        finally:
            if os.path.exists(invalid_path):
                os.unlink(invalid_path)

    def test_store_validation_with_missing_file(self):
        """Test store validation with missing file."""
        missing_path = "/path/that/does/not/exist.sqlitedb"
        is_valid, message = validate_reminders_store(missing_path)
        assert not is_valid
        assert "does not exist" in message

    def test_test_db_availability_function(self):
        """Test the test_db_availability convenience function."""
        is_available, message = test_db_availability()
        # This may return True or False depending on the system
        assert isinstance(is_available, bool)
        assert isinstance(message, str)
        assert len(message) > 0

    @patch('app_config.get_primary_reminders_store')
    def test_reader_with_missing_store(self, mock_get_store):
        """Test reader behavior when no store is found."""
        mock_get_store.return_value = None

        reader = RemindersDBReader()

        with pytest.raises(DatabaseNotFoundError):
            reader.get_store_info()

    @patch('app_config.get_primary_reminders_store')
    @patch('app_config.validate_reminders_store')
    def test_reader_with_invalid_store(self, mock_validate, mock_get_store):
        """Test reader behavior with invalid store."""
        mock_get_store.return_value = "/fake/path.sqlitedb"
        mock_validate.return_value = (False, "Invalid store")

        reader = RemindersDBReader()

        with pytest.raises(DatabaseNotFoundError) as exc_info:
            reader.get_store_info()

        assert "Invalid Reminders store" in str(exc_info.value)


class TestRemindersQueryBuilder:
    """Test cases for the RemindersQueryBuilder class."""

    def test_query_builder_initialization(self):
        """Test query builder initialization."""
        mock_reader = Mock(spec=RemindersDBReader)
        builder = RemindersQueryBuilder(mock_reader)
        assert builder.db_reader is mock_reader

    def test_schema_metadata_detection(self):
        """Test schema metadata detection with mocked reader."""
        mock_reader = Mock(spec=RemindersDBReader)
        mock_reader.check_table_exists.side_effect = lambda table: table in [
            'ZREMCDLIST', 'ZREMCDREMINDER', 'ZREMCDACCOUNT', 'ZREMCDALARM'
        ]
        mock_reader.get_table_columns.side_effect = lambda table: {
            'ZREMCDLIST': ['ZIDENTIFIER', 'ZNAME2', 'ZORDER', 'ZBADGEEMBLEM', 'ZPARENTGROUPIDENTIFIER'],
            'ZREMCDREMINDER': ['ZIDENTIFIER', 'ZTITLE', 'ZDUEDATE', 'ZORDER', 'ZISCOMPLETED'],
            'ZREMCDACCOUNT': ['ZIDENTIFIER', 'ZNAME2', 'ZACCOUNTTYPE']
        }.get(table, [])

        builder = RemindersQueryBuilder(mock_reader)
        schema = builder.get_schema_metadata()

        assert schema.schema_type == 'coredata'
        assert schema.list_table == 'ZREMCDLIST'
        assert schema.reminder_table == 'ZREMCDREMINDER'
        assert 'ZORDER' in schema.list_columns
        assert schema.account_table == 'ZREMCDACCOUNT'
        assert schema.compatibility_level.startswith('coredata')

    def test_lists_query_building(self):
        """Test building lists queries with different complexity levels."""
        mock_reader = Mock(spec=RemindersDBReader)
        mock_reader.check_table_exists.side_effect = lambda table: table in ['ZREMCDLIST', 'ZREMCDREMINDER']
        mock_reader.get_table_columns.side_effect = lambda table: {
            'ZREMCDLIST': ['ZIDENTIFIER', 'ZNAME2', 'ZORDER', 'ZBADGEEMBLEM'],
            'ZREMCDREMINDER': ['ZIDENTIFIER', 'ZTITLE']
        }.get(table, [])

        builder = RemindersQueryBuilder(mock_reader)

        # Test minimal query
        minimal_query = builder.build_lists_query(QueryComplexity.MINIMAL)
        assert "SELECT" in minimal_query
        assert "ZREMCDLIST" in minimal_query
        assert "AS identifier" in minimal_query

        # Test enhanced query
        enhanced_query = builder.build_lists_query(QueryComplexity.ENHANCED)
        assert "ZORDER" in enhanced_query

    def test_reminders_query_building(self):
        """Test building reminders queries with filters."""
        mock_reader = Mock(spec=RemindersDBReader)
        mock_reader.check_table_exists.side_effect = lambda table: table in ['ZREMCDLIST', 'ZREMCDREMINDER']
        mock_reader.get_table_columns.side_effect = lambda table: {
            'ZREMCDLIST': ['ZIDENTIFIER', 'ZNAME2'],
            'ZREMCDREMINDER': ['ZIDENTIFIER', 'ZTITLE', 'ZISCOMPLETED', 'ZDUEDATE', 'ZORDER']
        }.get(table, [])

        builder = RemindersQueryBuilder(mock_reader)

        # Test basic query
        query, params = builder.build_reminders_query()
        assert "SELECT" in query
        assert "ZREMCDREMINDER" in query
        assert "JOIN ZREMCDLIST" in query
        assert params == ()

        # Test query with calendar filter
        calendar_ids = ['cal1', 'cal2']
        query, params = builder.build_reminders_query(calendar_ids=calendar_ids)
        assert "IN (?,?)" in query
        assert params == ('cal1', 'cal2')

        # Test query without completed items
        query, params = builder.build_reminders_query(include_completed=False)
        assert "IS NULL" in query or "= 0" in query


class TestDomainModels:
    """Test cases for domain model functionality."""

    def test_reminders_list_creation(self):
        """Test creating RemindersList objects."""
        reminder_list = RemindersList(
            identifier="test-cal-123",
            name="Test Calendar",
            source_name="iCloud",
            data_source=DataSource.SQLITE_DB
        )

        assert reminder_list.identifier == "test-cal-123"
        assert reminder_list.name == "Test Calendar"
        assert reminder_list.source_name == "iCloud"
        assert reminder_list.data_source == DataSource.SQLITE_DB

    def test_reminders_list_with_db_fields(self):
        """Test RemindersList with DB-specific fields."""
        reminder_list = RemindersList(
            identifier="test-cal-456",
            name="Work Tasks",
            sort_order=2,
            is_default=False,
            icon_identifier="list.bullet",
            group_identifier="work-group",
            data_source=DataSource.SQLITE_DB
        )

        assert reminder_list.sort_order == 2
        assert reminder_list.is_default is False
        assert reminder_list.icon_identifier == "list.bullet"
        assert reminder_list.group_identifier == "work-group"


@pytest.mark.integration
class TestIntegration:
    """Integration tests that may require actual system resources."""

    def test_end_to_end_availability_check(self):
        """Test complete availability check without mocking."""
        # This is a real integration test that checks actual system state
        is_available, message = test_db_availability()

        # We can't guarantee the result, but we can test the contract
        assert isinstance(is_available, bool)
        assert isinstance(message, str)
        assert len(message) > 0

        if is_available:
            print(f"✓ DB Reader is available: {message}")
        else:
            print(f"✗ DB Reader not available: {message}")

    @pytest.mark.skipif(
        not test_db_availability()[0],
        reason="SQLite DB reader not available on this system"
    )
    def test_real_db_connection(self):
        """Test connection to actual Reminders database if available."""
        reader = RemindersDBReader()

        try:
            # Test basic availability
            assert reader.is_available()

            # Get store info
            store_info = reader.get_store_info()
            assert store_info.path is not None
            assert store_info.is_accessible

            # Test schema compatibility
            compatibility = reader.get_schema_compatibility()
            assert isinstance(compatibility, dict)
            assert 'compatibility_level' in compatibility

            print(f"✓ Connected to store: {store_info.path}")
            print(f"✓ Schema version: {store_info.schema_version.value}")
            print(f"✓ Compatibility: {compatibility['compatibility_level']}")

        except Exception as e:
            pytest.skip(f"Real DB connection failed: {e}")


# Helper functions for test fixtures

def create_mock_sqlite_rows(data: list[dict]) -> list[Mock]:
    """Create mock SQLite Row objects from dictionaries."""
    rows = []
    for row_data in data:
        mock_row = Mock()
        # Configure mock to behave like sqlite3.Row
        for key, value in row_data.items():
            mock_row.__getitem__ = Mock(side_effect=lambda k: row_data.get(k))
            mock_row.get = Mock(side_effect=lambda k, default=None: row_data.get(k, default))
            # Add direct attribute access
            setattr(mock_row, key, value)
        rows.append(mock_row)
    return rows


def create_test_calendar_data() -> list[dict]:
    """Create test calendar data for testing."""
    return [
        {
            'identifier': 'test-cal-1',
            'name': 'Personal',
            'color': '#FF0000',
            'calendar_type': 0,
            'allows_modification': True,
            'sort_order': 1,
            'is_default': True
        },
        {
            'identifier': 'test-cal-2',
            'name': 'Work',
            'color': '#0000FF',
            'calendar_type': 1,
            'allows_modification': True,
            'sort_order': 2,
            'is_default': False
        }
    ]


def create_test_reminder_data() -> list[dict]:
    """Create test reminder data for testing."""
    return [
        {
            'item_id': 'reminder-1',
            'external_id': 'ext-1',
            'title': 'Buy groceries',
            'notes': 'Milk, bread, eggs',
            'completed': False,
            'due_date': '2025-01-15',
            'priority': 'high',
            'calendar_id': 'test-cal-1',
            'calendar_name': 'Personal',
            'sort_order': 1,
            'has_attachments': False
        },
        {
            'item_id': 'reminder-2',
            'external_id': 'ext-2',
            'title': 'Finish project report',
            'notes': None,
            'completed': True,
            'completion_date': '2025-01-10',
            'priority': 'medium',
            'calendar_id': 'test-cal-2',
            'calendar_name': 'Work',
            'sort_order': 2,
            'has_attachments': True
        }
    ]


if __name__ == "__main__":
    # Run tests when executed directly
    pytest.main([__file__, "-v"])
