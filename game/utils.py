# game/utils.py
"""
General utility functions for the game.
"""
import random
import hashlib
import logging
import math
import config
import argon2 # <-- Import Argon2
from typing import Optional, TYPE_CHECKING, List, Dict, Any
from .definitions import colors as color_defs

if TYPE_CHECKING:
    from game.character import Character # Use relative path if needed '.character'
    from game.world import World # Added World for get_item_template_from_world

log = logging.getLogger(__name__)

# --- Argon2 Setup ---
# This creates a PasswordHasher instance with default secure settings.
ph = argon2.PasswordHasher()

# --- Password Hashing ---

VALID_DIRECTIONS: set[str] = {
    "north", "n",
    "south", "s",
    "east", "e",
    "west", "w",
    "up", "u",
    "down", "d",
    "northeast", "ne",
    "southeast", "se",
    "southwest", "sw",
    "northwest", "nw",
}

OPPOSITE_DIRECTIONS: Dict[str, str] = {
    "north": "south", "n": "s",
    "south": "north", "s": "n",
    "east": "west", "e": "w",
    "west": "east", "w": "e",
    "up": "down", "u": "d",
    "down": "up", "d": "u",
    "northeast": "southwest", "ne": "sw",
    "southeast": "northwest", "se": "nw",
    "southwest": "northeast", "sw": "ne",
    "northwest": "southeast", "nw": "se",
}

CANONICAL_DIRECTIONS_MAP = {
    "north": "n", "n": "n",
    "south": "s", "s": "s",
    "east": "e", "e": "e",
    "west": "w", "w": "w",
    "up": "u", "u": "u",
    "down": "d", "d": "d",
    "northeast": "ne", "ne": "ne",
    "northwest": "nw", "nw": "nw",
    "southeast": "se", "se": "se",
    "southwest": "sw", "sw": "sw",
}

def get_canonical_direction(direction: str) -> Optional[str]:
    """Returns the canonical (short) form of a direction string (lowercase)."""
    if direction is None:
        return None
    return CANONICAL_DIRECTIONS_MAP.get(direction.lower())

def get_opposite_direction(direction: str) -> Optional[str]:
    """Returns the opposite direction for a given direction string (lowercase)."""
    return OPPOSITE_DIRECTIONS.get(direction.lower())

def get_item_template_from_world(world: 'World', template_id: int) -> Optional[dict]:
    """Gets item template data as a dict, handling potential errors."""
    template_row = world.get_item_template(template_id)
    if not template_row:
        log.error("Could not find template data for ID %d", template_id)
        return None
    return dict(template_row) # Convert row to dict

def hash_password(password: str) -> str:
    """
    Hashes a password using the secure Argon2 algorithm.

    Args:
        password: The plaintext password.

    Returns:
        A string containing the Argon2 hash.
    """
    if not password:
        log.warning("Attempted to hash an empty password.")
        # Argon2 will raise an error on empty password, so we handle it.
        # We can return a known non-matching hash.
        return "invalid_empty_password_hash"
    # The ph.hash method handles salting automatically.
    return ph.hash(password)

def verify_password(stored_hash: str, provided_password: str) -> bool:
    """
    Verifies a provided password against a stored Argon2 hash.

    Args:
        stored_hash: The hash retrieved from the database.
        provided_password: The plaintext password entered by the user.

    Returns:
        True if the passwords match, False otherwise.
    """
    if not provided_password or not stored_hash:
        return False
    try:
        # ph.verify will check the password and the hash format.
        # It raises an exception on mismatch.
        ph.verify(stored_hash, provided_password)
        return True
    except argon2.exceptions.VerifyMismatchError:
        # This is the expected exception for a wrong password.
        return False
    except argon2.exceptions.InvalidHash:
        # This occurs if the stored_hash is not a valid Argon2 hash (e.g., our old SHA256).
        # We'll handle this case in the Player class, not here.
        log.debug("verify_password encountered an invalid Argon2 hash. Legacy check required.")
        return False
    except Exception:
        # Catch any other unexpected Argon2 verification errors.
        log.exception("An unexpected error occurred during Argon2 verification.")
        return False

def check_needs_rehash(stored_hash: str) -> bool:
    """
    Checks if an Argon2 hash uses outdated parameters and should be updated.
    """
    try:
        return ph.check_needs_rehash(stored_hash)
    except argon2.exceptions.InvalidHash:
        # If it's not an Argon2 hash at all, it definitely needs to be "rehashed".
        return True

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
    """Cumulative XP to advance; level 75 needs 600 hours of node soaking.

    Hunting/travel add time. After 75 the per-level cost grows 18% each level.
    QA accelerates elapsed time in tests, never the production curve.
    """
    if current_level >= config.MAX_LEVEL:
        return float('inf')
    if current_level < 1:
        return 0
    if current_level <= 9:
        return [0,150,400,800,1400,2200,3300,4700,6500,9000][current_level]
    target = current_level + 1
    if target <= 75:
        return round(9000 + (config.XP_LEVEL_75_TOTAL-9000)*((target-10)/65)**2.2)
    final_step = config.XP_LEVEL_75_TOTAL - xp_needed_for_level(73)
    return config.XP_LEVEL_75_TOTAL + sum(round(final_step * config.XP_AFTER_75_GROWTH**n) for n in range(1,target-74))


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

def strip_article(item_name: str) -> str:
    """Removes a leading 'a ' or 'an ' from an item name."""
    name_lower = item_name.lower()
    if name_lower.startswith("a "):
        return item_name[2:]
    if name_lower.startswith("an "):
        return item_name[3:]
    return item_name

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

    return ", ".join(parts) if parts else "0 Talons"

def colorize(text: str) -> str:
    """
    Replaces custom color codes (e.g., {R, {x) in text with ANSI escape codes.
    """
    output = text
    for code, ansi_sequence in color_defs.COLOR_MAP.items():
        output = output.replace(code, ansi_sequence)
    return output

def parse_quoted_args(args_str: str, min_args: int, max_args: int) -> Optional[List[str]]:
    """Parses args respecting quotes. Limited version for create commands."""
    args = []
    current_arg = ""
    in_quotes = False
    i = 0
    while i < len(args_str):
        char = args_str[i]
        if char == '"':
            in_quotes = not in_quotes
        elif char == ' ' and not in_quotes:
            if current_arg:
                args.append(current_arg)
                current_arg = ""
        else:
            current_arg += char
        i += 1
    if current_arg:
        args.append(current_arg)

    if in_quotes:
        log.debug("Parse error: Mismatched quotes in input '%s'", args_str)
        return None
    if not (min_args <= len(args) <= max_args):
        log.debug("Parse error: Incorrect number of args (%d) for '%s'", len(args), args_str)
        return None
    return args

def get_condition_desc(condition: int) -> str:
    """Returns a descriptive string for an item's condition level."""
    if condition >= 100:
        return "It is in perfect condition."
    elif condition >= 90:
        return "It shows signs of light use."
    elif condition >= 70:
        return "It is moderately worn."
    elif condition >= 50:
        return "It is heavily worn and battered."
    elif condition >= 30:
        return "It is in poor condition, with visible wear and tear."
    elif condition >= 10:
        return "It is on the verge of disrepair."
    elif condition >= 1:
        return "It looks like it could fall apart at any moment."
    else:
        return "It is completely broken."

def format_playtime(total_seconds: int) -> str:
    """Formats total seconds into a readable Days, Hours, Minutes string."""
    if total_seconds < 60:
        return f"{total_seconds}s"

    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    days, hours = divmod(hours, 24)

    parts = []
    if days > 0: parts.append(f"{days}d")
    if hours > 0: parts.append(f"{hours}h")
    if minutes > 0: parts.append(f"{minutes}m")

    return " ".join(parts) if parts else "0m"

def get_health_desc(character: 'Character') -> str:
    """Returns a descriptive string for a character's health percentage."""
    percent = (character.hp / character.max_hp) * 100
    name = character.first_name

    if percent >= 100:
        return f"{name} is in perfect health."
    elif percent >= 90:
        return f"{name} has a few scratches."
    elif percent >= 70:
        return f"{name} has some minor wounds."
    elif percent >= 50:
        return f"{name} is noticeably injured."
    elif percent >= 30:
        return f"{name} is bleeding and badly wounded."
    elif percent >= 10:
        return f"{name} is in critical condition."
    else:
        return f"{name} is on the verge of death."
    
def format_departure_message(character_name: str, direction: str) -> str:
    """Formats a grammatically correct departure message."""
    # Directions that don't need a preposition (e.g., "leaves north")
    simple_directions = {
        "north", "south", "east", "west", "up", "down",
        "northeast", "southeast", "southwest", "northwest"
    }
    
    # Special cases with unique phrasing
    if direction.lower() == "out":
        return f"\r\n{character_name} leaves.\r\n"
    if direction.lower() == "in":
        return f"\r\n{character_name} goes inside.\r\n"

    # Check for simple directions (and their abbreviations)
    if get_canonical_direction(direction):
        return f"\r\n{character_name} leaves {direction.lower()}.\r\n"
    
    # Default for complex exits like "portal", "door", "fissure"
    return f"\r\n{character_name} leaves through the {direction.lower()}.\r\n"

def format_hunger_status(character: 'Character') -> str:
    """Returns a descriptive string for the character's hunger level."""
    percent = (character.hunger / 100) * 100
    if percent >= 95: return "<g>Satiated<x>"
    if percent >= 70: return "<g>Content<x>"
    if percent >= 40: return "<Y>Peckish<x>"
    if percent >= 15: return "<Y>Hungry<x>"
    return "<R>Starving<x>"

def format_thirst_status(character: 'Character') -> str:
    """Returns a descriptive string for the character's thirst level."""
    percent = (character.thirst / 100) * 100
    if percent >= 95: return "<c>Sated<x>"
    if percent >= 70: return "<c>Quenched<x>"
    if percent >= 40: return "<y>Thirsty<x>"
    if percent >= 15: return "<y>Parched<x>"
    return "<r>Dehydrated<x>"