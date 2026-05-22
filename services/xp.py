"""
services/xp.py — XP and level calculations for LevelUp
"""

import math
from datetime import datetime, date


def xp_for_level(level: int) -> int:
    """XP needed to reach this level from zero."""
    return int(100 * (level ** 1.5))


def calculate_level(xp: int) -> int:
    """What level is a given XP amount."""
    level = 1
    while xp >= xp_for_level(level + 1):
        level += 1
        if level > 9999:
            break
    return level


def xp_progress(xp: int, level: int) -> dict:
    """Percentage progress toward next level."""
    current_threshold = xp_for_level(level)
    next_threshold = xp_for_level(level + 1)
    xp_in_level = max(0, xp - current_threshold)
    xp_needed = max(1, next_threshold - current_threshold)
    percentage = min(100, round((xp_in_level / xp_needed) * 100, 1))
    return {
        "percentage": percentage,
        "current": xp_in_level,
        "needed": xp_needed,
    }


def apply_streak_bonus(xp: int, streak: int) -> int:
    """15% bonus XP if streak is 3+ days."""
    if streak >= 3:
        return int(xp * 1.15)
    return xp


def calculate_total_level(physical: int, sharpness: int, wellbeing: int) -> int:
    """Average of the three category levels."""
    return max(1, round((physical + sharpness + wellbeing) / 3))


def update_streak(last_log_date: str, current_streak: int) -> tuple[int, str]:
    """
    Returns (new_streak, today_str).
    - Same day: no change
    - Consecutive day: +1
    - Gap: reset to 1
    """
    today = date.today()
    today_str = today.isoformat()

    if not last_log_date:
        return 1, today_str

    try:
        last = date.fromisoformat(last_log_date[:10])
    except ValueError:
        return 1, today_str

    diff = (today - last).days
    if diff == 0:
        return current_streak, last_log_date  # already logged today
    elif diff == 1:
        return current_streak + 1, today_str
    else:
        return 1, today_str
