# game/utils.py
"""
General utility functions for the game.
"""

import hashlib
import logging

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
