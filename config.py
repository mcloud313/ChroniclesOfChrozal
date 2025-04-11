# config.py
"""
Server configuration settings.
"""

HOST = "0.0.0.0"  # Listen on all available network interfaces
PORT = 4000  # Port for clients to connect to
DB_NAME = "chrozal.db"  # Name for our SQLite database file
ENCODING = "utf-8"  # Encoding for network communication

# --- Leveling & XP ---
MAX_LEVEL = 100 # Maximum attainable character level
XP_BASE = 1000 # Base XP for calculation (XP for Level 2)
XP_EXPONENT = 2.5 # Exponent for level curve (e.g. 1.5=Shallow, 2.0 quadratic, 2,5=STEEPER)
XP_ABSORB_RATE_PER_SEC = 1