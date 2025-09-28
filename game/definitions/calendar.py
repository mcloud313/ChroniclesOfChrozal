# game/definitions/calendar.py
"""Defines the in-game calendar, time constants, and related data."""

#--- Time Progression ratio ---
# 1.0 means 1 real second = 1 game minute. A 24-hour day passes in 24 real minutes
SECONDS_PER_GAME_MINUTE: float = 6.0

# --- Calendar structure ---
MINUTES_PER_HOUR: int = 60
HOURS_PER_DAY: int = 26  # Your world has a longer day, which is great!
DAYS_PER_WEEK: int = 10
WEEKS_PER_MONTH: int = 3
MONTHS_PER_YEAR: int = 12

DAYS_PER_MONTH: int = DAYS_PER_WEEK * WEEKS_PER_MONTH
DAYS_PER_YEAR: int = MONTHS_PER_YEAR * DAYS_PER_MONTH

# --- Day/Night Cycle ---
# These were the missing variables causing the server to crash.
# Based on a 26-hour day, we can set dawn and dusk accordingly.
DAWN_HOUR: int = 7      # 7:00 AM
DUSK_HOUR: int = 21     # 9:00 PM

# --- Starting Date ---
STARTING_YEAR: int = 218
STARTING_MONTH: int = 5
STARTING_DAY: int = 1
STARTING_HOUR: int = 7  # Start at the new dawn time

# --- NEW: Lore-Aligned Month and Day Names ---
# Month names tied to the seasons and culture of Chrozal.
MONTH_NAMES = [
    "First Thaw",       # Month 1: Winter's grip loosens.
    "Seedfall",         # Month 2: A time of planting, sacred to Terra-Matra.
    "Green-Tide",       # Month 3: Spring growth explodes across the land.
    "Star-Weaver",      # Month 4: Clear spring nights, sacred to Celestria. [cite: 48]
    "Sun's Crest",      # Month 5: The longest days of the year.
    "Ember-Fall",       # Month 6: The heat of high summer.
    "Harvester's Moon", # Month 7: The primary harvest season.
    "Fade-Leaf",        # Month 8: Autumn colors spread through the Oldwood.
    "Stone-Sleep",      # Month 9: A Dwarven term for when the earth begins to harden. [cite: 11]
    "Frostwind",        # Month 10: The first true cold of winter arrives.
    "Silent Night",     # Month 11: Commemorating the beginning of the Great Silence. [cite: 108, 152]
    "Year's Turning"    # Month 12: A time of reflection and renewal.
]

# Day names tied to the Pantheon and core concepts of the world. [cite: 43]
DAY_NAMES = [
    "Forgeday",    # For Valerius, the Forgemaster; a day of craft. [cite: 46]
    "Heartday",    # For Terra-Matra, the World-Mother; a day for nature. [cite: 53]
    "Starday",     # For Celestria, the Star-Weaver; a day for magic. [cite: 48]
    "Wayday",      # For Orian, the Wayfinder; a day for travel and commerce. [cite: 60, 65]
    "Wrathday",    # For Kharn, the Unbroken; a day of martial prowess for the Grak. [cite: 68]
    "Veilday",     # For Kael, the Silent Step; a day for quiet dealings. [cite: 50]
    "Chainsday",   # A somber day, remembering the binding of Malakor. [cite: 56, 148]
    "Songday",     # Remembering the Song of Shaping that created the world. [cite: 111]
    "Tidesday",    # A day for the fishermen and sailors of Port Valis. [cite: 160]
    "Hearthday"    # A day of community, rest, and family.
]

def get_season(month: int) -> str:
    """
    Returns the name of the season for a given month number (1-12).
    """
    if month in [12, 1, 2]:
        return "Winter"
    elif month in [3, 4, 5]:
        return "Spring"
    elif month in [6, 7, 8]:
        return "Summer"
    else:  # months 9, 10, 11
        return "Autumn"