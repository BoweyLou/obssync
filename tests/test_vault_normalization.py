#!/usr/bin/env python3
"""Test vault path normalization and deterministic ID generation."""

import os
import sys
import tempfile
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from obs_sync.core.models import normalize_vault_path, deterministic_vault_id, Vault


def test_normalize_vault_path():
    """Test comprehensive vault path normalization."""
    print("\n=== Testing Vault Path Normalization ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        # Test 1: User home expansion
        home_path = "~/test_vault"
        expanded = os.path.expanduser(home_path)
        result = normalize_vault_path(home_path)
        assert result.startswith(os.path.expanduser("~")), "Should expand user home"
        print(f"✓ User home expansion: {home_path} -> {result}")
        
        # Test 2: Trailing slash removal
        vault_path = Path(tmpdir) / "TestVault"
        vault_path.mkdir()
        
        with_slash = str(vault_path) + "/"
        without_slash = str(vault_path)
        
        result1 = normalize_vault_path(with_slash)
        result2 = normalize_vault_path(without_slash)
        
        assert result1 == result2, "Trailing slash should be normalized"
        assert not result1.endswith("/"), "Should remove trailing slash"
        print(f"✓ Trailing slash removal: {with_slash} -> {result1}")
        
        # Test 3: Relative to absolute conversion
        rel_path = "./test_vault"
        result = normalize_vault_path(rel_path)
        assert os.path.isabs(result), "Should convert to absolute path"
        print(f"✓ Relative to absolute: {rel_path} -> {result}")
        
        # Test 4: Symlink resolution
        real_path = Path(tmpdir) / "real_vault"
        real_path.mkdir()
        symlink_path = Path(tmpdir) / "symlink_vault"
        
        try:
            symlink_path.symlink_to(real_path)
            result = normalize_vault_path(str(symlink_path))
            expected = normalize_vault_path(str(real_path))
            assert result == expected, "Should resolve symlinks"
            print(f"✓ Symlink resolution: {symlink_path} -> {result}")
        except OSError:
            print("⚠️  Symlink test skipped (no permissions)")
        
        # Test 5: Empty path handling
        try:
            normalize_vault_path("")
            assert False, "Should raise error for empty path"
        except ValueError as e:
            assert "empty" in str(e).lower()
            print(f"✓ Empty path handling: Raised ValueError")
        
        # Test 6: Root directory handling
        root = os.sep
        result = normalize_vault_path(root)
        assert result == root, "Should preserve root directory"
        print(f"✓ Root directory preserved: {root}")


def test_deterministic_vault_id():
    """Test deterministic vault ID generation."""
    print("\n=== Testing Deterministic Vault ID Generation ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir) / "TestVault"
        vault_path.mkdir()
        
        # Test 1: Format verification
        normalized = normalize_vault_path(str(vault_path))
        vault_id = deterministic_vault_id(normalized)
        
        assert vault_id.startswith("vault-"), f"Should start with 'vault-': {vault_id}"
        assert len(vault_id) == 18, f"Should be 18 chars (vault- + 12): {len(vault_id)}"
        assert "-" in vault_id, "Should use dash separator"
        print(f"✓ Correct format: {vault_id}")
        
        # Test 2: Consistency
        id1 = deterministic_vault_id(normalized)
        id2 = deterministic_vault_id(normalized)
        assert id1 == id2, "Should generate same ID for same path"
        print(f"✓ Consistent generation: {id1} == {id2}")
        
        # Test 3: Different paths produce different IDs
        other_path = Path(tmpdir) / "OtherVault"
        other_path.mkdir()
        other_normalized = normalize_vault_path(str(other_path))
        other_id = deterministic_vault_id(other_normalized)
        
        assert vault_id != other_id, "Different paths should produce different IDs"
        print(f"✓ Different paths: {vault_id} != {other_id}")
        
        # Test 4: Empty path handling
        try:
            deterministic_vault_id("")
            assert False, "Should raise error for empty path"
        except ValueError as e:
            assert "empty" in str(e).lower()
            print(f"✓ Empty path handling: Raised ValueError")


def test_vault_class_integration():
    """Test Vault class with new normalization."""
    print("\n=== Testing Vault Class Integration ===")
    
    with tempfile.TemporaryDirectory() as tmpdir:
        vault_path = Path(tmpdir) / "TestVault"
        vault_path.mkdir()
        
        # Test 1: New vault gets deterministic ID
        vault1 = Vault(
            name="TestVault",
            path=str(vault_path)
        )
        
        assert vault1.vault_id.startswith("vault-"), "Should have deterministic ID"
        assert len(vault1.vault_id) == 18, "Should have correct length"
        print(f"✓ New vault ID: {vault1.vault_id}")
        
        # Test 2: Legacy UUID preservation
        legacy_uuid = "550e8400-e29b-41d4-a716-446655440000"
        vault2 = Vault(
            name="LegacyVault",
            path=str(vault_path),
            vault_id=legacy_uuid
        )
        
        assert vault2.vault_id == legacy_uuid, "Should preserve legacy UUID"
        print(f"✓ Legacy UUID preserved: {vault2.vault_id}")
        
        # Test 3: Path normalization in Vault
        with_slash = str(vault_path) + "/"
        vault3 = Vault(
            name="TestVault",
            path=with_slash
        )
        
        assert vault3.path == vault1.path, "Paths should be normalized identically"
        assert vault3.vault_id == vault1.vault_id, "Should generate same ID for same normalized path"
        print(f"✓ Path normalization: {vault3.vault_id} == {vault1.vault_id}")


def run_all_tests():
    """Run all normalization tests."""
    print("=" * 60)
    print("VAULT NORMALIZATION TESTS")
    print("=" * 60)
    
    try:
        test_normalize_vault_path()
        test_deterministic_vault_id()
        test_vault_class_integration()
        
        print("\n" + "=" * 60)
        print("🎉 ALL TESTS PASSED!")
        print("=" * 60)
        return True
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        import traceback
        traceback.print_exc()
        return False
    except Exception as e:
        print(f"\n❌ UNEXPECTED ERROR: {e}")
        import traceback
        traceback.print_exc()
        return False


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)