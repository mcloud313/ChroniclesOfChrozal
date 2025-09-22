# config.py
"""
Server configuration settings.
"""

HOST = "0.0.0.0"  # Listen on all available network interfaces
PORT = 4000       # Port for clients to connect to
DB_NAME = "chrozal.db" # Name for our SQLite database file
ENCODING = "utf-8" # Encoding for network communication

# --- Game Loop & Save ---
TICKER_INTERVAL_SECONDS = 1.0     # How often the main game loop runs.
AUTOSAVE_INTERVAL_SECONDS = 300   # 300 seconds = 5 minutes

# --- Leveling & XP ---
MAX_LEVEL = 100
XP_BASE = 1000
XP_EXPONENT = 2.2
XP_ABSORB_RATE_PER_SEC = 10.0 # Increased for better feel
SKILL_POINTS_PER_LEVEL = 5

# --- Regen Rates (Points per Second) ---
HP_REGEN_BASE_PER_SEC = 0.01
HP_REGEN_VIT_MULTIPLIER = 0.02
ESSENCE_REGEN_BASE_PER_SEC = 0.04
ESSENCE_REGEN_AURA_MULTIPLIER = 0.02
NODE_REGEN_MULTIPLIER = 2.0
MEDITATE_REGEN_MULTIPLIER = 3.0

BASE_CARRY_WEIGHT = 20.0
CARRY_WEIGHT_MIGHT_MULTIPLIER = 1.5

# --- Gameplay ---
DEFAULT_RESPAWN_ROOM_ID = 44  # FIX: Changed to 1 to match the default created room.
FALLBACK_RESPAWN_ROOM_ID = 1
STARTING_COINAGE = 125

# --- Input ---
MAX_INPUT_LENGTH = 512