# game/definitions/calendar.py
"""Defines the in-game calendar, time constants, and related data."""

#--- Time Progression ratio ---
# 1.0 means 1 real second = 1 game minute. A 24-hour day passes in 24 real minutes
SECONDS_PER_GAME_MINUTE: float = 6.0

# --- Calendar structure ---
MINUTES_PER_HOUR: int = 60
HOURS_PER_DAY: int = 26
DAYS_PER_WEEK: int = 10
WEEKS_PER_MONTH: int = 3
MONTHS_PER_YEAR: int = 12

DAYS_PER_MONTH: int = DAYS_PER_WEEK * WEEKS_PER_MONTH
DAYS_PER_YEAR: int = MONTHS_PER_YEAR * DAYS_PER_MONTH

# --- Starting Date ---
STARTING_YEAR: int = 218
STARTING_MONTH: int = 5
STARTING_DAY: int = 1
STARTING_HOUR: int = 6

MONTH_NAMES = [
    "Winter's End", "The Thawing", "New Growth", "Spring's Bloom",
    "Sun's Height", "Long Day", "The Harvest", "Fading Light",
    "First Frost", "Deep Winter", "The Sleeping Moon", "Year's Turning"
]

DAY_NAMES = [
    "Moonday", "Tidesday", "Windsday", "Oathsday", "Sunsday",
    "Starsday", "Soulsday", "Godsday", "Fatesday", "Kingsday"
]
