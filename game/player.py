# game/player.py
"""
Represents a Player account in the game.
Holds account-level information, not character data or connection state.
"""
import logging
import argon2
from typing import Tuple
from . import utils # Import utility functions from utils.py in the same package

log = logging.getLogger(__name__)

class Player:
    """
    Manages player account data (username, email, password hash).
    """
    def __init__(self, dbid: int, username: str, email: str, hashed_password: str, is_admin: bool = False):
        """
        Initializes a player account object, typically from database data.

        Args:
            dbid: The unique database ID for the player account.
            username: The account username.
            email: The player's email address.
            hashed_password: the pre-hashed password string from the database.
            is_admin: Flag indicating if the player has admin privileges.
        """
        self.dbid: int = dbid
        self.username: str = username
        self.email: str = email
        self.hashed_password: str = hashed_password
        self.is_admin: bool = bool(is_admin)

        log.debug("Player object initialized: %s (ID: %s)", self.username, self.dbid)

    def set_password(self, plain_password: str):
        """
        Hashes a new plaintext password using Argon2 and updates the instance's hash.
        Note: This only updates the object in memory. Saving to DB requires a separate call.

        Args:
            plain_password: The new plaintext password to set.
        """
        if not plain_password:
            log.error("Attempted to set an empty password for player %s", self.username)
            return
        
        self.hashed_password = utils.hash_password(plain_password)
        log.info("Password hash updated in memory for player %s using Argon2.", self.username)

    def check_password(self, plain_password: str) -> Tuple[bool, bool]:
        """
        Verifies a password against the stored hash, handling both new and legacy formats.

        Args:
            plain_password: The plaintext password provided by the user.

        Returns:
            A tuple (is_match: bool, needs_rehash: bool).
            - (True, True) if legacy password matches and needs upgrading.
            - (True, False) if modern password matches and is up-to-date.
            - (False, False) if password does not match.
        """
        if not plain_password or not self.hashed_password:
            return False, False

        try:
            # First, try to verify using the modern Argon2 method.
            is_match = utils.verify_password(self.hashed_password, plain_password)
            if is_match:
                # If it's a match, check if the Argon2 parameters are outdated.
                needs_rehash = utils.check_needs_rehash(self.hashed_password)
                return True, needs_rehash
            else:
                # It was a valid Argon2 hash, but the password was wrong.
                return False, False
        except argon2.exceptions.InvalidHash:
            # The stored hash is NOT a valid Argon2 hash. This means it's likely a legacy SHA256 hash.
            log.debug("Invalid Argon2 hash for user %s; attempting legacy SHA256 verification.", self.username)
            is_legacy_match = (self.hashed_password == utils._legacy_hash_password_sha256(plain_password))
            
            if is_legacy_match:
                log.info("Legacy SHA256 password matched for %s. Flagging for rehash.", self.username)
                # The password is correct, and it DEFINITELY needs to be rehashed.
                return True, True
            else:
                # It was a legacy hash, and the password was wrong.
                return False, False
    
    def __repr__(self) -> str:
        return f"<Player {self.dbid}: '{self.username}'>"
    
    def __str__(self) -> str:
        return f"Player(id={self.dbid}, username='{self.username}', email='{self.email}')"