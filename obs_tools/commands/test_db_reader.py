#!/usr/bin/env python3
"""
Test and Monitor SQLite DB Reader

This command tests the availability and performance of the SQLite database
reader for Apple Reminders, providing detailed diagnostics and monitoring
information for troubleshooting and performance optimization.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from typing import Dict, Any

# Import utilities and configuration
try:
    from lib.reminders_db_reader import RemindersDBReader, test_db_availability
    from lib.reminders_sql_queries import RemindersQueryBuilder, QueryComplexity
    from lib.hybrid_reminders_collector import HybridRemindersCollector
    from lib.observability import get_logger, DBMetrics
    from app_config import discover_reminders_sqlite_stores, validate_reminders_store, load_app_config
except ImportError:
    # Fallback for direct script execution
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))
    from lib.reminders_db_reader import RemindersDBReader, test_db_availability
    from lib.reminders_sql_queries import RemindersQueryBuilder, QueryComplexity
    from lib.hybrid_reminders_collector import HybridRemindersCollector
    from lib.observability import get_logger, DBMetrics
    from app_config import discover_reminders_sqlite_stores, validate_reminders_store, load_app_config


def test_store_discovery() -> Dict[str, Any]:
    """Test SQLite store discovery functionality."""
    print("=== Testing SQLite Store Discovery ===")

    try:
        stores = discover_reminders_sqlite_stores()

        result = {
            "discovery_success": True,
            "stores_found": len(stores),
            "stores": []
        }

        for store_path, description in stores:
            print(f"Found: {description}")
            print(f"  Path: {store_path}")

            # Validate each store
            is_valid, validation_msg = validate_reminders_store(store_path)
            print(f"  Valid: {is_valid} - {validation_msg}")

            result["stores"].append({
                "path": store_path,
                "description": description,
                "valid": is_valid,
                "validation_message": validation_msg
            })
            print()

        return result

    except Exception as e:
        print(f"Discovery failed: {e}")
        return {
            "discovery_success": False,
            "error": str(e),
            "stores_found": 0,
            "stores": []
        }


def test_db_connection() -> Dict[str, Any]:
    """Test database connection and basic operations."""
    print("=== Testing Database Connection ===")

    try:
        reader = RemindersDBReader()

        # Test basic availability
        is_available = reader.is_available()
        print(f"DB Reader Available: {is_available}")

        if not is_available:
            return {
                "connection_success": False,
                "error": "DB reader not available"
            }

        # Get store info
        store_info = reader.get_store_info()
        print(f"Store Path: {store_info.path}")
        print(f"Schema Version: {store_info.schema_version.value}")
        print(f"Last Modified: {store_info.last_modified}")

        # Test schema compatibility
        compatibility = reader.get_schema_compatibility()
        print(f"Compatibility Level: {compatibility.get('compatibility_level', 'unknown')}")
        print(f"Required Tables Present: {compatibility.get('all_required_present', False)}")

        # Get connection stats
        stats = reader.get_stats()

        return {
            "connection_success": True,
            "store_path": store_info.path,
            "schema_version": store_info.schema_version.value,
            "compatibility": compatibility,
            "stats": {
                "connections_opened": stats.connections_opened,
                "connections_failed": stats.connections_failed,
                "queries_executed": stats.queries_executed,
                "query_failures": stats.query_failures
            }
        }

    except Exception as e:
        print(f"Connection test failed: {e}")
        return {
            "connection_success": False,
            "error": str(e)
        }


def test_query_performance() -> Dict[str, Any]:
    """Test query performance across different complexity levels."""
    print("=== Testing Query Performance ===")

    try:
        reader = RemindersDBReader()
        query_builder = RemindersQueryBuilder(reader)

        performance_results = {}

        for complexity in QueryComplexity:
            print(f"\nTesting {complexity.value} queries...")

            # Test lists query
            start_time = time.time()
            lists = query_builder.execute_lists_query(complexity)
            lists_time = (time.time() - start_time) * 1000

            print(f"  Lists query: {len(lists)} results in {lists_time:.1f}ms")

            # Test reminders query (limited to first few lists for performance)
            if lists:
                test_calendar_ids = [lst.identifier for lst in lists[:3]]
                start_time = time.time()
                reminders = query_builder.execute_reminders_query(
                    calendar_ids=test_calendar_ids,
                    complexity=complexity,
                    include_completed=False
                )
                reminders_time = (time.time() - start_time) * 1000

                print(f"  Reminders query: {len(reminders)} results in {reminders_time:.1f}ms")
            else:
                reminders_time = 0
                print("  Reminders query: skipped (no lists found)")

            performance_results[complexity.value] = {
                "lists_count": len(lists),
                "lists_time_ms": lists_time,
                "reminders_time_ms": reminders_time
            }

        # Get final stats
        stats = reader.get_stats()

        return {
            "performance_test_success": True,
            "results_by_complexity": performance_results,
            "total_stats": {
                "queries_executed": stats.queries_executed,
                "total_query_time": stats.total_query_time,
                "avg_query_time_ms": (stats.total_query_time * 1000 / stats.queries_executed) if stats.queries_executed > 0 else 0
            }
        }

    except Exception as e:
        print(f"Performance test failed: {e}")
        return {
            "performance_test_success": False,
            "error": str(e)
        }


def test_hybrid_collector() -> Dict[str, Any]:
    """Test the hybrid collector functionality."""
    print("=== Testing Hybrid Collector ===")

    try:
        collector = HybridRemindersCollector()

        # Test availability of both methods
        availability = collector.test_availability()

        print(f"DB Reader: {availability['db_reader']['available']} - {availability['db_reader']['message']}")
        print(f"EventKit: {availability['eventkit']['available']} - {availability['eventkit']['message']}")
        print(f"Recommended Mode: {availability['recommended_mode']}")

        return {
            "hybrid_test_success": True,
            "availability": availability
        }

    except Exception as e:
        print(f"Hybrid collector test failed: {e}")
        return {
            "hybrid_test_success": False,
            "error": str(e)
        }


def test_configuration() -> Dict[str, Any]:
    """Test configuration loading and DB settings."""
    print("=== Testing Configuration ===")

    try:
        prefs, paths = load_app_config()

        print(f"DB Reader Enabled: {prefs.enable_db_reader}")
        print(f"DB Fallback Enabled: {prefs.db_fallback_enabled}")
        print(f"DB Read Timeout: {prefs.db_read_timeout}s")
        print(f"Schema Validation Level: {prefs.schema_validation_level}")
        print(f"Query Complexity: {prefs.db_query_complexity}")

        return {
            "config_test_success": True,
            "db_settings": {
                "enable_db_reader": prefs.enable_db_reader,
                "db_fallback_enabled": prefs.db_fallback_enabled,
                "db_read_timeout": prefs.db_read_timeout,
                "schema_validation_level": prefs.schema_validation_level,
                "db_query_complexity": prefs.db_query_complexity
            }
        }

    except Exception as e:
        print(f"Configuration test failed: {e}")
        return {
            "config_test_success": False,
            "error": str(e)
        }


def main(argv: list[str]) -> int:
    """Main entry point for DB reader testing."""
    parser = argparse.ArgumentParser(
        description="Test and monitor SQLite DB reader functionality"
    )
    parser.add_argument(
        "--test",
        choices=["discovery", "connection", "performance", "hybrid", "config", "all"],
        default="all",
        help="Which test to run"
    )
    parser.add_argument(
        "--output-json",
        help="Output results to JSON file"
    )

    args = parser.parse_args(argv)

    logger = get_logger("test_db_reader")
    run_id = logger.start_run("test_db_reader", {
        "test_type": args.test,
        "output_json": args.output_json
    })

    print(f"=== SQLite DB Reader Testing Tool ===")
    print(f"Run ID: {run_id}")
    print(f"Timestamp: {datetime.now(timezone.utc).isoformat()}")
    print()

    results = {
        "run_id": run_id,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "test_type": args.test
    }

    try:
        if args.test in ["discovery", "all"]:
            results["discovery"] = test_store_discovery()

        if args.test in ["connection", "all"]:
            results["connection"] = test_db_connection()

        if args.test in ["performance", "all"]:
            results["performance"] = test_query_performance()

        if args.test in ["hybrid", "all"]:
            results["hybrid"] = test_hybrid_collector()

        if args.test in ["config", "all"]:
            results["configuration"] = test_configuration()

        # Determine overall success
        all_success = True
        for test_name, test_result in results.items():
            if isinstance(test_result, dict):
                for key, value in test_result.items():
                    if key.endswith("_success") and not value:
                        all_success = False
                        break

        results["overall_success"] = all_success

        # Output results
        if args.output_json:
            with open(args.output_json, 'w') as f:
                json.dump(results, f, indent=2)
            print(f"\nResults written to {args.output_json}")

        print(f"\n=== Test Summary ===")
        print(f"Overall Success: {all_success}")

        logger.end_run(all_success, "DB reader testing completed")

        return 0 if all_success else 1

    except Exception as e:
        logger.error(f"Testing failed: {e}")
        logger.end_run(False, str(e))
        print(f"Testing failed: {e}")
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))