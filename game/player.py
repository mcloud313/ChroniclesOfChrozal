# game/player.py
"""
Represents a Player account in the game.
Holds account-level information, not character data or connection state.
"""
import logging
from . import utils # Import utility functions from utils.py in the same package

log = logging.getLogger(__name__)

class Player:
    """
    Manages player account data (username, email, password hash).
    """
    def __init__(self, dbid: int, username: str, email: str, hashed_password: str):
        """
        Initializes a player account object, typically from database data.

        Args:
            dbid: The unique database ID for the player account.
            username: The account username.
            email: The player's email address.
            hashed_password: the pre-hashed password string from the database.
        """
        self.dbid: int = dbid
        self.username: str = username
        self.email: str = email
        # Store the hash directly as loaded from DB or set by set_password
        self.hashed_password: str = hashed_password
        # Note: No location, writer or character details here.

        log.debug("Player object initialized: %s (ID: %s)", self.username, self.dbid)

    def set_password(self, plain_password: str):
        """
        Hashes a new plaintext password and updates the instance's hashed_password.
        Note: This only updates the object in memory. Saving to DB requires separate call.

        Args:
            plain_password: The new plaintext password to set.
        """
        if not plain_password:
            log.error("Attempted to set an empty password for player %s", self.username)
            # Avoid setting an invalid hash for an empty password
            # or raise ValueError("Password cannot be empty.")
            return # Or raise error
        
        self.hashed_password = utils.hash_password(plain_password)
        log.info("Password hash updated in memory for player %s", self.username)

    def check_password(self, plain_password: str) -> bool:
        """
        Verifies a provided plaintext password against the stored hash,

        Args:
            plain_password: The plaintext password provied by the user.

        Returns:
            True if the password matches the stored hash, False otherwise.
        """
        if not plain_password or not self.hashed_password:
            return False # Can't verify empty passwords or if hash is missing

        # Use the verify_password utility function
        return utils.verify_password(self.hashed_password, plain_password)
    
    def __repr__(self) -> str:
        return f"<Player {self.dbid}: '{self.username}'>"
    
    def __str__(self) -> str:
        return f"Player(id={self.dbid}, username='{self.username}', email='{self.email}')"
