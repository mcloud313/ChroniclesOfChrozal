# game/utils.py
"""
General utility functions for the game.
"""
import random
import hashlib
import logging
import math
import config
from typing import Optional, TYPE_CHECKING, Dict, Any
from .definitions import colors as color_defs
if TYPE_CHECKING:
    from game.character import Character # Use relative path if needed '.character'

# You might want other utilities here later (e.g. logging setup, decorators)

log = logging.getLogger(__name__)

# --- Password Hashing ---
# IMPORTANT: These are basic SHA256 hashes for initial development.
# Plan to replace with bcrypt for production.

def get_item_template_from_world(world: 'World', template_id: int) -> Optional[dict]:
    """Gets item template data as a dict, handling potential errors."""
    template_row = world.get_item_template(template_id)
    if not template_row:
        log.error("Could not find template data for ID %d", template_id)
        return None
    return dict(template_row) # Convert row to dict

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

def skill_check(character: 'Character', skill_name: str, dc: int = 10) -> Dict[str, Any]:
    """
    Performs a skill check for a character against a difficulty.
    Rolls d100 <= Skill_Rank + Attribute_Modifier - Difficulty_Modifier

    Args:
        character: The character performing the check.
        skill_name: The name of the skill being used (case-insensitive).
        difficulty_mod: A modifier representing the check's difficulty.
        Positive values make it harder, negative easier.

    Returns:
        A dictionary containing:
        { 'success': bool, 'roll': int, 'target_roll': int, 'skill_value': int }
        Returns {'success': False} if check cannot be performed.
    """
    skill_name = skill_name.lower()
    if not hasattr(character, 'get_skill_modifier'):
        log.error("skill_check: Character object missing get_skill_modifier method.")
        return {'success': False, 'roll': 0, 'target_roll': 0, 'skill_value': 0} # Cannot perform check
    
    skill_value = character.get_skill_modifier(skill_name) # Rank + Attr Mod
    roll = random.randint(1, 20) # d20 roll
    total_check = roll + skill_value # Final result to compare against DC

    # Success if total meets or exceeds DC
    success = (total_check >= dc)

    return {'success': success, 'roll': roll, 'dc': dc, 'skill_value': skill_value, 'total_check': total_check}

def format_coinage(total_talons: int) -> str:
    """Formats total lowest denomination (Talons) into Crowns, Orbs, Shards, Talons."""
    if total_talons < 0: return "{rInvalid Amount{x" # Added color
    if total_talons == 0: return "0 Talons" # Use full name for zero

    # --- Define conversion rates ---
    # Adjust these if your currency system is different (e.g., 100 copper = 1 silver)
    talons_per_shard = 10
    shards_per_orb = 10
    orbs_per_crown = 10 # Assuming 1 Crown = 10 Orbs = 100 Shards = 1000 Talons

    # --- Calculate amounts for each denomination ---
    talons = total_talons % talons_per_shard
    total_shards = total_talons // talons_per_shard
    shards = total_shards % shards_per_orb
    total_orbs = total_shards // shards_per_orb
    orbs = total_orbs % orbs_per_crown
    crowns = total_orbs // orbs_per_crown

    # --- Build the display string with full names and plurals ---
    parts = []
    if crowns > 0:
        parts.append(f"{crowns} {'Crown' if crowns == 1 else 'Crowns'}")
    if orbs > 0:
        parts.append(f"{orbs} {'Orb' if orbs == 1 else 'Orbs'}")
    if shards > 0:
        parts.append(f"{shards} {'Shard' if shards == 1 else 'Shards'}")
    if talons > 0:
        parts.append(f"{talons} {'Talon' if talons == 1 else 'Talons'}")

    # Join the parts with commas and spaces for readability, handle empty case
    return ", ".join(parts) if parts else "0 Talons"

def colorize(text: str) -> str:
    """
    Replaces custom color codes (e.g., {R, {x) in text with ANSI escape codes.
    """
    output = text
    for code, ansi_sequence in color_defs.COLOR_MAP.items():
        output = output.replace(code, ansi_sequence)
    return output
