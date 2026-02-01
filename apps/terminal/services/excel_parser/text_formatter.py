"""Text formatting utilities for Excel data."""

import re


def format_title_case(text: str) -> str:
    """
    Format text to Title Case (first letter of each word uppercase, rest lowercase).
    
    Handles Spanish text properly, including common prepositions and articles
    that should remain lowercase in the middle of names.
    
    Args:
        text: Input text (may be in uppercase, lowercase, or mixed)
    
    Returns:
        Formatted text in Title Case
    """
    if not text or not text.strip():
        return text
    
    # Spanish prepositions and articles that should remain lowercase
    # (unless they're the first word)
    lowercase_words = {
        'de', 'del', 'la', 'el', 'las', 'los', 'y', 'e', 'o', 'u',
        'en', 'con', 'por', 'para', 'sin', 'sobre', 'entre', 'hasta'
    }
    
    # Convert to lowercase first, then split by spaces
    words = text.lower().strip().split()
    
    if not words:
        return text
    
    # Capitalize first word always
    formatted_words = [words[0].capitalize()]
    
    # For remaining words, capitalize unless it's a lowercase word
    for word in words[1:]:
        # Remove any punctuation for comparison, but keep it in the word
        word_clean = re.sub(r'[^\w]', '', word.lower())
        if word_clean in lowercase_words:
            formatted_words.append(word.lower())
        else:
            formatted_words.append(word.capitalize())
    
    return ' '.join(formatted_words)

