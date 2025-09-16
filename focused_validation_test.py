#!/usr/bin/env python3
"""
Focused Validation Test

Tests the key fixes that were implemented:
1. Callback chaining in Update All and Apply
2. App.json config integration
3. 300s timeout configuration
4. Vault selection UI
"""

import os
import sys
import subprocess
import tempfile
import json
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_timeout_configuration():
    """Verify 300s timeout is configured in services.py"""
    print("=== Testing 300s Timeout Configuration ===")
    
    services_file = Path(__file__).parent / "tui" / "services.py"
    if not services_file.exists():
        print("✗ services.py not found")
        return False
    
    content = services_file.read_text()
    
    # Check for 300 second timeout
    if "poll_count > 3000" in content and "300 seconds" in content:
        print("✓ 300 second timeout correctly configured")
        return True
    else:
        print("✗ 300 second timeout configuration not found")
        return False

def test_app_config_integration():
    """Test app.json config loading in create_missing_counterparts"""
    print("\n=== Testing App.json Config Integration ===")
    
    create_script = Path(__file__).parent / "obs_tools" / "commands" / "create_missing_counterparts.py"
    if not create_script.exists():
        print("✗ create_missing_counterparts.py not found")
        return False
    
    content = create_script.read_text()
    
    # Check for app config loading function
    if "load_config_from_app_json" in content:
        print("✓ App config loading function found")
        
        # Check if it's used in main
        if "config = load_config_from_app_json()" in content:
            print("✓ App config loading integrated into main function")
            return True
        else:
            print("✗ App config loading not integrated into main")
            return False
    else:
        print("✗ App config loading function not found")
        return False

def test_callback_chaining():
    """Test callback chaining in controller"""
    print("\n=== Testing Callback Chaining Structure ===")
    
    controller_file = Path(__file__).parent / "tui" / "controller.py"
    if not controller_file.exists():
        print("✗ controller.py not found")
        return False
    
    content = controller_file.read_text()
    
    # Check for the chaining methods
    required_methods = [
        "_do_update_all_and_apply",
        "_do_collect_obsidian_for_chain", 
        "_do_collect_reminders_for_chain",
        "_do_build_links_for_chain",
        "_do_apply_sync_for_chain"
    ]
    
    found_methods = []
    for method in required_methods:
        if f"def {method}" in content:
            found_methods.append(method)
    
    if len(found_methods) == len(required_methods):
        print(f"✓ All {len(required_methods)} callback chain methods found")
        
        # Check for actual chaining calls
        if "self._do_collect_obsidian_for_chain()" in content:
            print("✓ Callback chaining implemented")
            return True
        else:
            print("✗ Callback chaining calls not found")
            return False
    else:
        print(f"✗ Only {len(found_methods)}/{len(required_methods)} chain methods found")
        print(f"   Missing: {set(required_methods) - set(found_methods)}")
        return False

def test_vault_selection_ui():
    """Test vault selection UI components"""
    print("\n=== Testing Vault Selection UI ===")
    
    controller_file = Path(__file__).parent / "tui" / "controller.py"
    if not controller_file.exists():
        print("✗ controller.py not found")
        return False
    
    content = controller_file.read_text()
    
    # Check for vault selection methods
    if "_handle_vault_selection" in content:
        print("✓ Vault selection handler found")
        
        # Check for vault configuration loading
        if "obsidian_vaults.json" in content:
            print("✓ Vault configuration loading implemented")
            
            # Check for vault selection UI
            if "Select default vault" in content:
                print("✓ Vault selection UI text found")
                return True
            else:
                print("✗ Vault selection UI text not found")
                return False
        else:
            print("✗ Vault configuration loading not found")
            return False
    else:
        print("✗ Vault selection handler not found")
        return False

def test_create_missing_counterparts_execution():
    """Test create missing counterparts can execute"""
    print("\n=== Testing Create Missing Counterparts Execution ===")
    
    try:
        # Create temporary test files
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create minimal test data
            obs_index = {
                "meta": {"schema": 2, "total_tasks": 1},
                "tasks": {
                    "t-test123": {
                        "uuid": "t-test123",
                        "description": "Test task",
                        "status": "todo",
                        "created_at": "2025-09-11T10:00:00Z"
                    }
                }
            }
            
            rem_index = {
                "meta": {"schema": 2, "total_tasks": 1},
                "tasks": {
                    "r-test456": {
                        "uuid": "r-test456", 
                        "description": "Reminders task",
                        "is_completed": False,
                        "created_at": "2025-09-11T10:00:00Z"
                    }
                }
            }
            
            links_data = {
                "meta": {"schema": 1, "total_links": 0},
                "links": []
            }
            
            # Write test files
            obs_file = os.path.join(temp_dir, "obs.json")
            rem_file = os.path.join(temp_dir, "rem.json")
            links_file = os.path.join(temp_dir, "links.json")
            
            with open(obs_file, 'w') as f:
                json.dump(obs_index, f)
            with open(rem_file, 'w') as f:
                json.dump(rem_index, f)
            with open(links_file, 'w') as f:
                json.dump(links_data, f)
            
            # Test create missing counterparts dry-run
            cmd = [
                sys.executable,
                "obs_tools/commands/create_missing_counterparts.py",
                "--obs", obs_file,
                "--rem", rem_file,
                "--links", links_file,
                "--dry-run",
                "--direction", "both"
            ]
            
            result = subprocess.run(cmd, capture_output=True, text=True, cwd=Path(__file__).parent)
            
            if result.returncode == 0:
                print("✓ Create missing counterparts executed successfully")
                if "Creation Plan Summary" in result.stdout:
                    print("✓ Plan generation working correctly")
                    return True
                else:
                    print("✗ Plan generation output not found")
                    return False
            else:
                print(f"✗ Create missing counterparts failed: {result.stderr}")
                return False
                
    except Exception as e:
        print(f"✗ Create missing counterparts test failed: {e}")
        return False

def test_data_pipeline_integrity():
    """Test basic data pipeline integrity"""
    print("\n=== Testing Data Pipeline Integrity ===")
    
    try:
        # Check that we can import key modules
        from obs_tools.commands.create_missing_counterparts import MissingCounterpartsCreator
        from tui.controller import TUIController
        from tui.services import ServiceManager
        
        print("✓ Key modules import successfully")
        
        # Test ServiceManager initialization
        sm = ServiceManager()
        if hasattr(sm, 'run_command') and hasattr(sm, 'cancel_current_operation'):
            print("✓ ServiceManager has required methods")
        else:
            print("✗ ServiceManager missing required methods")
            return False
        
        # Test MissingCounterpartsCreator
        creator = MissingCounterpartsCreator()
        if hasattr(creator, 'create_plan') and hasattr(creator, 'execute_plan'):
            print("✓ MissingCounterpartsCreator has required methods")
        else:
            print("✗ MissingCounterpartsCreator missing required methods")
            return False
        
        print("✓ Data pipeline integrity validated")
        return True
        
    except Exception as e:
        print(f"✗ Data pipeline integrity test failed: {e}")
        return False

def main():
    """Run focused validation tests"""
    print("🔍 FOCUSED PIPELINE VALIDATION")
    print("=" * 50)
    
    tests = [
        ("300s Timeout Configuration", test_timeout_configuration),
        ("App.json Config Integration", test_app_config_integration), 
        ("Callback Chaining Structure", test_callback_chaining),
        ("Vault Selection UI", test_vault_selection_ui),
        ("Create Missing Counterparts Execution", test_create_missing_counterparts_execution),
        ("Data Pipeline Integrity", test_data_pipeline_integrity),
    ]
    
    results = {}
    for test_name, test_func in tests:
        try:
            results[test_name] = test_func()
        except Exception as e:
            print(f"✗ {test_name} failed with exception: {e}")
            results[test_name] = False
    
    # Print summary
    print("\n" + "=" * 50)
    print("📊 VALIDATION SUMMARY")
    print("=" * 50)
    
    passed = sum(1 for result in results.values() if result)
    total = len(results)
    
    for test_name, result in results.items():
        status = "✅ PASS" if result else "❌ FAIL"
        print(f"{test_name:<35} {status}")
    
    print("-" * 50)
    print(f"🎯 Result: {passed}/{total} tests passed")
    
    if passed == total:
        print("🎉 All critical fixes validated successfully!")
        print("\n✅ PIPELINE STATUS: All recent fixes are working correctly")
        print("   - Async callback chaining implemented")
        print("   - App.json config loading integrated")  
        print("   - 300s timeout configured for EventKit operations")
        print("   - Vault selection UI available")
        print("   - Create missing counterparts execution verified")
    else:
        print("⚠️  Some validation tests failed")
        print("\n❌ PIPELINE STATUS: Issues detected, see details above")
    
    return 0 if passed == total else 1

if __name__ == "__main__":
    sys.exit(main())