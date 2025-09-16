#!/usr/bin/env python3
"""
Test script to verify title sync functionality works as expected.
"""

import sys
import os
sys.path.append(os.path.dirname(__file__))

from obs_tools.commands.sync_links_apply import edit_task_line

def test_title_replacement():
    """Test that edit_task_line correctly handles title changes."""
    
    # Test case: original task line
    original_line = "- [ ] **Speaker 1** to arrange QDev license for evaluation and home use ⏫ #reminders ^t-f6b04fafae8f"
    
    # New description from Reminders
    new_description = "**Speaker 1** to arrange QDev llllicense for evaluation and home use $$$"
    
    # Test title replacement while preserving other elements
    result = edit_task_line(
        raw=original_line,
        new_status=None,
        new_due=None,
        new_priority=None,
        new_description=new_description
    )
    
    print(f"Original: {original_line}")
    print(f"Result:   {result}")
    
    # Verify the title changed
    assert "llllicense" in result, "Title should be updated"
    assert "$$$" in result, "New title content should be present"
    
    # Verify tags are preserved
    assert "#reminders" in result, "Tags should be preserved"
    
    # Verify block ID is preserved
    assert "^t-f6b04fafae8f" in result, "Block ID should be preserved"
    
    # Verify priority is removed (will be re-added if needed)
    # Since we didn't specify new_priority, existing priority tokens should be cleaned
    
    print("✅ Title replacement test passed!")

def test_safety_checks():
    """Test safety validation for new descriptions."""
    
    original_line = "- [ ] Test task #tag ^block-id"
    
    # Test line break rejection
    result1 = edit_task_line(original_line, None, None, None, "Title with\nline break")
    assert result1 == original_line, "Should reject descriptions with line breaks"
    
    # Test empty description rejection
    result2 = edit_task_line(original_line, None, None, None, "   ")
    assert result2 == original_line, "Should reject empty descriptions"
    
    # Test long description truncation
    long_desc = "A" * 600
    result3 = edit_task_line(original_line, None, None, None, long_desc)
    assert "..." in result3, "Should truncate long descriptions"
    assert len(result3) < len(original_line) + 600, "Should be truncated"
    
    print("✅ Safety checks test passed!")

if __name__ == "__main__":
    test_title_replacement()
    test_safety_checks()
    print("🎉 All tests passed!")