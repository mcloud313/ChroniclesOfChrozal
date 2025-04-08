# game/utils.py
"""
General utility functions for the game.
"""
import random
import hashlib
import logging
import math
from typing import Optional

# You might want other utilities here later (e.g. logging setup, decorators)

log = logging.getLogger(__name__)

# --- Password Hashing ---
# IMPORTANT: These are basic SHA256 hashes for initial development.
# Plan to replace with bcrypt for production.

def hash_password(password: str) -> str:
    """
    Hashes a password using SHA256

    Args:
        password: the plaintext password.

    returns: 
        A string containing the hexadecimal SHA256 hash.

    TODO: Replace with bcrypt later for proper salting and adaptive hashing.
    """
    if not password:
        log.warning("Attempted to hash an empty password.")
        # Decide on handling: raise error or return specific non-matching hash?
        # Returning a known non-matching hash might be slightly safer than erroring.
        return "invalid_empty_password_hash"
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def verify_password(stored_hash: str, provided_password: str) -> bool:
    """
    Verifies a provided password against a stored SHA256 hash.

    Args:
        stored_hash: The hash retrieved from the database.
        provided_password: The plaintext password entered by the user.

    Returns:
        True if the passwords match, False otherwise.
    TODO: Replace with bcrypt checkpw later.
    """
    if not provided_password or not stored_hash:
        return False # Cannot verify empty or missing components
    # Compare the hash of the provided password with the stored hash
    return stored_hash == hash_password(provided_password)

def generate_stat() -> int:
    """
    Generates a single stat (10-35) weighted towards lower/mid values,
    with increasing rarity for high values.
    Based on user-defined probability bands.
    """
    roll = random.random() # 0.0 <= roll < 1.0

    if roll < 0.30:  # 30% chance
        return random.randint(10, 14) # Range: 10-14
    elif roll < 0.55: # 25% chance (0.55 - 0.30)
        return random.randint(15, 19) # Range: 15-19
    elif roll < 0.75: # 20% chance (0.75 - 0.55)
        return random.randint(20, 24) # Range: 20-24
    elif roll < 0.90: # 15% chance (0.90 - 0.75)
        return random.randint(25, 29) # Range: 25-29
    elif roll < 0.97: # 7% chance (0.97 - 0.90)
        return random.randint(30, 33) # Range: 30-33
    elif roll < 0.99: # 2% chance (0.99 - 0.97)
        return 34                 # Value: 34 (randint(34,34))
    else:             # 1% chance (1.00 - 0.99)
        return 35                 # Value: 35

def generate_stat_set() -> list[int]:
    """Generates a set of 6 stats."""
    return sorted([generate_stat() for _ in range(6)], reverse=True)

def calculate_modifier(stat_value: int) -> int:
    """
    Calculates the D&D-like modifier for a given stat value.
    Using formula: floor(Stat / 5) based on user example ( 35 -> 7).
    Note: This gives +2 for stats 10-14.
    """
    if stat_value < 1: # Handle potential invalid stats
        return -5 # Or some other default for very low stats
    return math.floor(stat_value / 5)

def xp_to_next_level(level: int) -> int:
    """
    Calculates the total XP required to reach the *next* level.
    Using simple linear formula for V1.

    Args:
        level: The character's current level.

    Returns:
        The total XP needed to attain level (level + 1).
        Returns a very large number for max level to prevent overflow issues.
    """
    if level < 1:
        return 1000 # XP for level 1
    # TODO: Define MAX_LEVEL in config later
    max_level = 100 # Example max level
    if level >= max_level:
        return float('inf') # Or sys.maxsize

    # Linear formula: 1->1000, 2->2000, etc. total XP needed *for that level*
    # Often XP tables represent TOTAL XP accumulated. Let's assume this function
    # returns the amount needed to *gain* the next level.
    # Example: Level 1 needs 1000 XP (to reach L2). Level 2 needs 2000 more XP (to reach L3).
    # Simpler: Total XP needed for level L = L * 1000
    # Amount needed to GAIN next level (L+1) = (L+1)*1000 - L*1000 = 1000? No, that's flat.
    # Let's use XP required for *current* level L = L * 1000. Player needs xp_total >= L*1000 to advance.
    required = level * 1000
    return required

def get_pronouns(sex: Optional[str]) -> tuple[str, str, str, str, str]:
    """
    Returns a tuple of pronouns based on sex string.

    Args:
        sex: The sex string ('Male', 'Female', 'They/Them', or None).

    Returns:
        Tuple: (subject, object, possessive, verb_is, verb_has)
            e.g., ('He', 'him', 'his', 'is', 'has') or ('They', 'them', 'their', 'are', 'have')
    """
    if sex == "Male":
        return "He", "him", "his", "is", "has"
    elif sex == "Female":
        return "She", "her", "her", "is", "has"
    else: # Default to They/Them for None or other values
        return "They", "them", "their", "are", "have"

def get_article(word: str) -> str:
    """Returns 'an' if word starts with a vowel sound, else 'a'."""
    if not word:
        return "a" # Default if empty string passed
    # Simple check for common vowel sounds (lowercase)
    return "an" if word.lower()[0] in 'aeiou' else "a"