"""
Text normalization and similarity utilities.
"""

import re
from typing import List, Optional
from urllib.parse import urlparse


def normalize_text(text: Optional[str]) -> List[str]:
    """
    Normalize text for similarity comparison.
    
    Converts to lowercase, removes punctuation, splits into tokens.
    Preserves URL structure as meaningful tokens.
    
    Args:
        text: Text to normalize
    
    Returns:
        List of normalized tokens
    """
    if not text:
        return []
    
    # Convert to lowercase
    text = text.lower()
    
    # Process URLs to extract meaningful tokens
    # Find all URLs and replace them with tokens
    url_pattern = re.compile(r'(https?://[^\s]+)')
    urls = url_pattern.findall(text)
    
    # Replace URLs with extracted tokens
    for url in urls:
        url_tokens = _url_to_tokens(url)
        # Join tokens with space to maintain text flow
        text = text.replace(url, ' '.join(url_tokens))
    
    # Remove markdown formatting
    text = re.sub(r'[*_~`#]', '', text)
    
    # Remove punctuation but keep alphanumeric and spaces
    text = re.sub(r'[^\w\s]', ' ', text)
    
    # Split into tokens and remove empty ones
    tokens = [t for t in text.split() if t]
    
    return tokens


def _url_to_tokens(url: str) -> List[str]:
    """
    Extract meaningful tokens from a URL.
    
    Drops scheme and query parameters, keeps host and path segments.
    
    Args:
        url: URL string to tokenize
    
    Returns:
        List of URL tokens
    """
    tokens = []
    
    try:
        parsed = urlparse(url)
        
        # Extract host parts (e.g., "example.com" -> ["example", "com"])
        if parsed.netloc:
            # Remove port if present
            host = parsed.netloc.split(':')[0]
            # Split by dots and add as tokens
            host_parts = host.split('.')
            tokens.extend(host_parts)
        
        # Extract path segments (e.g., "/path/to/item" -> ["path", "to", "item"])
        if parsed.path:
            # Remove leading/trailing slashes and split
            path_parts = [p for p in parsed.path.strip('/').split('/') if p]
            tokens.extend(path_parts)
            
        # Note: We intentionally skip query parameters and fragments
        # to allow matching of URLs that differ only in these aspects
        
    except Exception:
        # If URL parsing fails, just return the original URL as a single token
        # Better to have some token than none
        tokens = [url.replace('://', '_').replace('/', '_')]
    
    return tokens


def calculate_similarity(text1: str, text2: str) -> float:
    """
    Calculate Dice coefficient similarity between two texts.
    
    Args:
        text1: First text
        text2: Second text
    
    Returns:
        Similarity score between 0.0 and 1.0
    """
    tokens1 = set(normalize_text(text1))
    tokens2 = set(normalize_text(text2))
    
    if not tokens1 or not tokens2:
        return 0.0
    
    intersection = len(tokens1 & tokens2)
    total = len(tokens1) + len(tokens2)
    
    if total == 0:
        return 0.0
    
    return (2.0 * intersection) / total


def dice_similarity(tokens1: List[str], tokens2: List[str]) -> float:
    """
    Calculate Dice coefficient between two token lists.
    
    Args:
        tokens1: First set of tokens
        tokens2: Second set of tokens
    
    Returns:
        Similarity score between 0.0 and 1.0
    """
    set1 = set(tokens1)
    set2 = set(tokens2)
    
    if not set1 or not set2:
        return 0.0
    
    intersection = len(set1 & set2)
    total = len(set1) + len(set2)
    
    if total == 0:
        return 0.0
    
    return (2.0 * intersection) / total


def normalize_text_for_similarity(text: Optional[str]) -> List[str]:
    """
    Normalize text for similarity calculation.
    
    Args:
        text: Text to normalize
    
    Returns:
        List of normalized tokens
    """
    return normalize_text(text)