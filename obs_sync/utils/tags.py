"""
Utilities for handling tags in Reminders notes field.
"""

import re
from typing import List, Tuple, Optional

# Delimiter to separate user notes from encoded tags
TAGS_DELIMITER = "\n\n---tags---\n"
TAG_RE = re.compile(r'#([a-zA-Z0-9_\-/]+)')


def encode_tags_in_notes(notes: Optional[str], tags: List[str]) -> str:
    """
    Encode tags into the notes field while preserving user content.
    
    Args:
        notes: Existing notes content (may already contain encoded tags)
        tags: List of tags to encode (with or without # prefix)
        
    Returns:
        Notes string with encoded tags
    """
    # Extract existing user notes (before delimiter)
    user_notes = ""
    if notes:
        if TAGS_DELIMITER in notes:
            user_notes = notes.split(TAGS_DELIMITER)[0]
        else:
            user_notes = notes
    
    # Normalize tags (ensure they have # prefix)
    normalized_tags = []
    for tag in tags:
        if tag and not tag.startswith('#'):
            normalized_tags.append(f"#{tag}")
        elif tag:
            normalized_tags.append(tag)
    
    # If no tags, return just user notes
    if not normalized_tags:
        return user_notes.rstrip() if user_notes else ""
    
    # Combine user notes with tags
    if user_notes and user_notes.strip():
        return f"{user_notes.rstrip()}{TAGS_DELIMITER}{' '.join(normalized_tags)}"
    else:
        # If no user notes, still use delimiter for consistency
        return f"{TAGS_DELIMITER}{' '.join(normalized_tags)}"


def decode_tags_from_notes(notes: Optional[str]) -> Tuple[Optional[str], List[str]]:
    """
    Extract tags and user notes from the combined notes field.
    
    Args:
        notes: Combined notes string potentially containing encoded tags
        
    Returns:
        Tuple of (user_notes, tags_list)
    """
    if not notes:
        return None, []
    
    if TAGS_DELIMITER not in notes:
        # No encoded tags, return notes as-is
        return notes, []
    
    parts = notes.split(TAGS_DELIMITER)
    user_notes = parts[0].rstrip() if parts[0].strip() else None
    
    tags = []
    if len(parts) > 1 and parts[1]:
        # Extract tags from the encoded section
        tag_matches = TAG_RE.findall(parts[1])
        tags = [f"#{tag}" for tag in tag_matches]
    
    return user_notes, tags


def merge_tags(obs_tags: List[str], rem_tags: List[str]) -> List[str]:
    """
    Merge tags from both sources, removing duplicates while preserving order.
    
    Args:
        obs_tags: Tags from Obsidian
        rem_tags: Tags from Reminders
        
    Returns:
        Merged list of unique tags
    """
    # Normalize all tags to have # prefix for comparison
    def normalize(tag):
        return tag if tag.startswith('#') else f"#{tag}"
    
    seen = set()
    result = []
    
    # Add Obsidian tags first (they take precedence for ordering)
    for tag in obs_tags:
        normalized = normalize(tag)
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    
    # Add any unique Reminders tags
    for tag in rem_tags:
        normalized = normalize(tag)
        if normalized not in seen:
            seen.add(normalized)
            result.append(normalized)
    
    return result