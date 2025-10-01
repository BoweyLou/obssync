"""
Date parsing and formatting utilities.
"""

from datetime import date, datetime
from typing import Optional


def parse_date(date_str: Optional[str]) -> Optional[date]:
    """
    Parse a date string into a date object.
    
    Handles various formats:
    - ISO format (YYYY-MM-DD)
    - ISO datetime (YYYY-MM-DDTHH:MM:SS)
    
    Args:
        date_str: Date string to parse
    
    Returns:
        Parsed date object or None if invalid
    """
    if not date_str:
        return None
    
    # Take only date part if it's a datetime string
    if 'T' in date_str:
        date_str = date_str.split('T')[0]
    
    # Remove timezone if present
    date_str = date_str.split('+')[0].split('Z')[0]
    
    try:
        # Try ISO format
        return datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        pass
    
    try:
        # Try with single digit month/day
        parts = date_str.split('-')
        if len(parts) == 3:
            year = int(parts[0])
            month = int(parts[1])
            day = int(parts[2])
            return date(year, month, day)
    except (ValueError, IndexError):
        pass
    
    return None


def format_date(d: Optional[date]) -> Optional[str]:
    """
    Format a date object as ISO string (YYYY-MM-DD).
    
    Args:
        d: Date object to format
    
    Returns:
        ISO formatted date string or None
    """
    if not d:
        return None
    
    return d.strftime('%Y-%m-%d')


def dates_equal(date1: Optional[date], date2: Optional[date], tolerance_days: int = 0) -> bool:
    """
    Check if two dates are equal within a tolerance.
    
    Args:
        date1: First date
        date2: Second date
        tolerance_days: Number of days tolerance (0 for exact match)
    
    Returns:
        True if dates are equal within tolerance
    """
    # Both None
    if date1 is None and date2 is None:
        return True
    
    # One is None
    if date1 is None or date2 is None:
        return False
    
    # Check within tolerance
    diff = abs((date1 - date2).days)
    return diff <= tolerance_days