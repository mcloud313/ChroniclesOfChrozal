# game/utils.py
"""
General utility functions for the game.
"""
import random
import hashlib
import logging
import math
import config
from typing import Optional, TYPE_CHECKING
from .definitions import colors as color_defs
if TYPE_CHECKING:
    from game.character import Character # Use relative path if needed '.character'

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

def _roll_4d6() -> int:
    """Rolls 4 six-sided dice and returns the sum."""
    return sum(random.randint(1, 6) for _ in range(4))

def generate_stat() -> int:
    """
    Generates a single stat (10-35) using a scaled 3d6 roll.
    This creates a bell curve distribution centered in the low 20s,
    making high stats (30+) genuinely rare.
    """
    roll = _roll_4d6() # Result between 3 and 18
    return roll

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
    return math.floor(stat_value / 3)

def xp_needed_for_level(current_level: int) -> int:
    """
    Calculates the total XP required to reach the *next* level.
    Using simple linear formula for V1.

    Args:
        level: The character's current level.

    Returns:
        The total XP needed to attain level (level + 1).
        Returns a very large number for max level to prevent overflow issues.
    """
    max_level = getattr(config, 'MAX_LEVEL', 100)
    if current_level >= max_level:
        return float('inf') # Cannot advance further

    target_level = current_level + 1
    if target_level <= 1: # Should not happen if current_level starts at 1
        return 0 # Level 1 requires 0 XP

    base = getattr(config, 'XP_BASE', 1000)
    exponent = getattr(config, 'XP_EXPONENT', 2.5)

    try:
        # Calculate threshold needed TO REACH target_level
        required = math.floor(base * ((target_level - 1) ** exponent))
        return required
    except OverflowError:
        log.error("XP calculation overflow for target level %d", target_level)
        return float('inf')
    except Exception:
        log.exception("Error calculating XP for target level %d", target_level, exc_info=True)
        return float('inf')

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

def skill_check(character: 'Character', skill_name: str, difficulty_mod: int = 0) -> bool:
    """
    Performs a skill check for a character against a difficulty. 
    Rolls d100 <= Skill_Rank + Attribute_Modifier - Difficulty_Modifier

    Args:
        character: The character performing the check.
        skill_name: The name of the skill being used (case-insensitive).
        difficulty_mod: A modifier representing the check's difficulty.
                        Positive values make it harder, negative easier, Defaults to 0.
    """
    skill_name = skill_name.lower()
    if not hasattr(character, 'get_skill_modifier'):
        log.error("skill_check: Character object missing get_skill_modifier method.")
        return False # Cannot perform check

    # Get the character's total modifier for the skill (Rank + Attr Mod)
    skill_value = character.get_skill_modifier(skill_name)

    # Calculate the target number to roll under/equal to
    target_roll = skill_value - difficulty_mod
    # Ensure there's always a small chance to succeed/fail? Not for V1.
    # Clamp maybe? target_roll = max(1, min(99, target_roll)) # e.g. 1 always fails, 100 always passes

    # Roll d100
    roll = random.randint(1, 100)

    success = (roll <= target_roll)

    log.debug("SKILL CHECK: Char=%s, Skill=%s(%d), DiffMod=%d, TargetRoll=%d, Rolled=%d -> %s",
            character.name, skill_name, skill_value, difficulty_mod, target_roll, roll,
            "SUCCESS" if success else "FAILURE")

    return success

def format_coinage(total_talons: int) -> str:
    """Formats total lowest denomination into Crowns, Orbs, Shards, Talons"""
    if total_talons < 0: return "Invalid Amount"
    if total_talons == 0: return "0t"

    talons_per_shard = 10
    shards_per_orb = 10
    orbs_per_crown = 10

    talons = total_talons % talons_per_shard
    total_shards = total_talons // talons_per_shard
    shards = total_shards % shards_per_orb
    total_orbs = total_shards // shards_per_orb
    orbs = total_orbs % orbs_per_crown
    crowns = total_orbs // orbs_per_crown

    parts = []
    if crowns > 0: parts.append(f"{crowns}c")
    if orbs > 0: parts.append(f"{orbs}o")
    if shards > 0: parts.append(f"{shards}s")
    if talons > 0: parts.append(f"{talons}t")

    return " ".join(parts) if parts else "0t"

def colorize(text: str) -> str:
    """
    Replaces custom color codes (e.g., {R, {x) in text with ANSI escape codes.
    """
    output = text
    for code, ansi_sequence in color_defs.COLOR_MAP.items():
        output = output.replace(code, ansi_sequence)
    return output
