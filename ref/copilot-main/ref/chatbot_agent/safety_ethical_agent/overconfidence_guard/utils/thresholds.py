"""
Threshold values for Overconfidence Guard
"""

# Example: if confidence > 0.85, mark as overconfident
CONFIDENCE_THRESHOLD = 0.85
def get_confidence_threshold() -> float:
    """
    Returns the confidence threshold for overconfidence detection
    """
    return CONFIDENCE_THRESHOLD
