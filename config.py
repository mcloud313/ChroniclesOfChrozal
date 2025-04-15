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
XP_EXPONENT = 2.0 # Exponent for level curve (e.g. 1.5=Shallow, 2.0 quadratic, 2,5=STEEPER)
XP_ABSORB_RATE_PER_SEC = 1
SKILL_POINTS_PER_LEVEL = 5

# --- Regen Rates (Points per Second) ---
HP_REGEN_BASE_PER_SEC = 0.02
HP_REGEN_VIT_MULTIPLIER = 0.05
ESSENCE_REGEN_BASE_PER_SEC = 0.08
ESSENCE_REGEN_AURA_MULTIPLIER = 0.04
NODE_REGEN_MULTIPLIER = 2.0
MEDITATE_REGEN_MULTIPLIER = 3.0