"""
Utility functions for Overconfidence Guard
"""

def check_overconfidence(score: float, threshold: float) -> bool:
    """
    Returns True if the confidence score exceeds threshold
    """
    return score > threshold
