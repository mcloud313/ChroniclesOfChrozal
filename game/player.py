# game/player.py
"""
Represents a Player account in the game.
Holds account-level information, not character data or connection state.
"""
import logging
import argon2
from typing import Tuple
from . import utils

log = logging.getLogger(__name__)

class Player:
    """
    Manages player account data (username, email, password hash).
    """
    # FIX: The __init__ signature now accepts 'id' to match the database column name.
    def __init__(self, id: int, username: str, email: str, hashed_password: str, is_admin: bool = False, **kwargs):
        """
        Initializes a player account object, typically from database data.
        """
        self.dbid: int = id  # Internally, we still call it dbid for clarity.
        self.username: str = username
        self.email: str = email
        self.hashed_password: str = hashed_password
        self.is_admin: bool = bool(is_admin)

    def set_password(self, plain_password: str):
        """
        Hashes a new plaintext password using Argon2 and updates the instance's hash.
        """
        if not plain_password:
            return
        self.hashed_password = utils.hash_password(plain_password)
        log.info("Password hash updated in memory for player %s.", self.username)

    def check_password(self, plain_password: str) -> Tuple[bool, bool]:
        """
        Verifies a password against the stored hash, handling both new and legacy formats.
        """
        if not plain_password or not self.hashed_password:
            return False, False

        try:
            is_match = utils.verify_password(self.hashed_password, plain_password)
            if is_match:
                needs_rehash = utils.check_needs_rehash(self.hashed_password)
                return True, needs_rehash
            else:
                return False, False
        except argon2.exceptions.InvalidHash:
            is_legacy_match = (self.hashed_password == utils._legacy_hash_password_sha256(plain_password))
            if is_legacy_match:
                return True, True
            else:
                return False, False
    
    def __repr__(self) -> str:
        return f"<Player {self.dbid}: '{self.username}'>"