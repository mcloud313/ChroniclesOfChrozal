# game/database.py
"""
Handles asynchronous database interactions using aiosqlite
Manages players (accounts), characters, rooms, and areas
"""
import logging
import json
import os
import sys
import hashlib # For password hashing (example)
import asyncio
import aiosqlite
import config
import math
from . import utils
from .definitions import classes as class_defs
from .definitions import skills as skill_defs # Needed for char seeding
from .definitions import abilities as ability_defs # Needed for char seeding

# Assuming config.py exists in the parent directory
try:
    import config
except ModuleNotFoundError:
    # Allow script to load even if config isn't immediately findable
    # (e.g. if path isn't set yet for direct execution attempt)
    config = None
    print("Warning: config.py not found on initial import.")

DATABASE_PATH = getattr(config, 'DB_NAME', 'data/default.db') # safer access

# Configure logging for database operations
log = logging.getLogger(__name__)
# --- Define Constants for Key Room IDs ---
TAVERN_ID = 10
MARKET_ID = 11
DOCKS_ID = 12
TOWNHALL_ID = 13
GATEHOUSE_ID = 14
GRAVEYARD_ID = 15 # Designated Respawn Room
GRAVEYARD_PATH_ID = 16
WEST_STREET_ID = 17
ARMORY_ID = 18
LIBRARY_ID = 19
TEMPLE_ID = 20
EAST_STREET_ID = 21
NORTH_STREET_ID = 22
SOUTH_STREET_ID = 23
ALLEY_ID = 24
BEACH_ENTRANCE_ID = 25
FISH_MARKET_ID = 26
GUARD_BARRACKS_ID = 27
HEALER_HUT_ID = 28
GENERAL_STORE_ID = 29
WEAVERS_SHOP_ID = 30
BAKERY_ID = 31
EMPTY_COTTAGE_ID = 20 # Reusing ID 20, confirm it's not used by Temple? Yes, Temple is 20. Change Cottage ID.
EMPTY_COTTAGE_ID = 32 # Assign new ID for Cottage

BEACH_START_ID = 100
CAVE_ID = 4 # Keep ID 4 for Damp Cave
        # New Beach IDs
CLIFF_CAVE_DEEPER_ID = 110
NORTH_CLIFF_PATH_ID = 111
CLIFF_SUMMIT_ID = 112
SOUTH_DUNES_ID = 113
INLAND_SCRUB_ID = 114

# --- Core Async Database Functions
async def connect_db(db_path: str = DATABASE_PATH) -> aiosqlite.Connection | None:
    """
    Established an asynchronous connection to the SQlite Database
    Creates the databse file and directory if they don't exist.
    Enables WAL mode and foreign key support
    Args:
        db_path: The path to the SQLite database file.
    Returns:
        An aiosqlite.Connection object or None if connection fails.
    """
    try:
        # Ensure the directory exists
        db_dir = os.path.dirname(db_path)
        if db_dir: # check if path includes a directory
            os.makedirs(db_dir, exist_ok=True)
        # connect asynchronously
        conn = await aiosqlite.connect(db_path)
        # use row factory for dictionary-like access
        conn.row_factory = aiosqlite.Row

        # Enable WAL mode for better concurrency
        await conn.execute("PRAGMA journal_mode=WAL;")
        # Enable foreign key support (important!)
        await conn.execute("PRAGMA foreign_keys = ON;")
        await conn.commit() # Commit PRAGMA changes

        log.info("Successfully connected to the database (WAL Mode): %s", db_path)
        return conn
    except aiosqlite.Error as e:  
        log.error("Database connection error to %s: %s", db_path, e, exc_info=True)
        return None

async def init_db(conn: aiosqlite.Connection):
    """
    Initializes the database schema AND populates it with default + test data
    for Alpha testing. Assumes running on an empty DB file.
    """
    log.info("--- Running Database Initialization and Seeding (Alpha v1) ---")
    try:
        await conn.execute("PRAGMA foreign_keys = ON;") # Enforce foreign keys

        # --- Phase 1: Schema Creation ---
        log.info("Step 1: Creating Tables (IF NOT EXISTS)...")
        # Areas
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS areas (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
                description TEXT DEFAULT 'An undescribed area.', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP )
        """)
        # Players
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, hashed_password TEXT NOT NULL,
                email TEXT NOT NULL, is_admin BOOLEAN NOT NULL DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP )
        """)
        # Rooms
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT, area_id INTEGER NOT NULL, name TEXT NOT NULL,
                description TEXT DEFAULT 'You see nothing special.', exits TEXT DEFAULT '{}', flags TEXT DEFAULT '[]',
                spawners TEXT DEFAULT '{}', coinage INTEGER NOT NULL DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE RESTRICT )
        """)
        # Room Items (for persistent ground items)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS room_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT, room_id INTEGER NOT NULL, item_template_id INTEGER NOT NULL,
                dropped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(room_id) REFERENCES rooms(id) ON DELETE CASCADE,
                FOREIGN KEY(item_template_id) REFERENCES item_templates(id) ON DELETE CASCADE )
        """)
        # --- V V V NEW: Create room_objects table V V V ---
        await conn.execute(
        """
        CREATE TABLE IF NOT EXISTS room_objects (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            room_id INTEGER NOT NULL,
            name TEXT NOT NULL, -- Display name (e.g., "a weathered fountain")
            description TEXT DEFAULT 'It looks unremarkable.',
            keywords TEXT NOT NULL DEFAULT '[]', -- JSON list of lowercase keywords for targeting
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY(room_id) REFERENCES rooms(id) ON DELETE CASCADE,
            UNIQUE (room_id, name)
        )
        """)
        log.info("Checked/Created 'room_objects' table.")
        # Races
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS races (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, description TEXT DEFAULT 'An undescribed race.' )
        """)
        # Classes
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, description TEXT DEFAULT 'An undescribed class' )
        """)
        # Item Templates
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS item_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, description TEXT DEFAULT 'An ordinary item.',
                type TEXT NOT NULL, stats TEXT DEFAULT '{}', flags TEXT DEFAULT '[]', damage_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP )
        """)
        # Mob Templates
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mob_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, description TEXT DEFAULT 'A creature.',
                mob_type TEXT DEFAULT NULL, level INTEGER NOT NULL DEFAULT 1, stats TEXT DEFAULT '{}',
                max_hp INTEGER NOT NULL DEFAULT 10, attacks TEXT DEFAULT '[]', loot TEXT DEFAULT '{}',
                flags TEXT DEFAULT '[]', respawn_delay_seconds INTEGER DEFAULT 300, variance TEXT DEFAULT '{}',
                movement_chance REAL NOT NULL DEFAULT 0.0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP )
        """)
        # Characters
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS characters (
                id INTEGER PRIMARY KEY AUTOINCREMENT, player_id INTEGER NOT NULL, first_name TEXT NOT NULL, last_name TEXT NOT NULL,
                sex TEXT NOT NULL, race_id INTEGER, class_id INTEGER, level INTEGER DEFAULT 1, description TEXT DEFAULT '',
                hp REAL DEFAULT 50.0, max_hp REAL DEFAULT 50.0, essence REAL DEFAULT 20.0, max_essence REAL DEFAULT 20.0,
                spiritual_tether INTEGER, xp_pool REAL DEFAULT 0.0, xp_total REAL DEFAULT 0.0,
                status TEXT NOT NULL DEFAULT 'ALIVE', unspent_skill_points INTEGER NOT NULL DEFAULT 0, unspent_attribute_points INTEGER NOT NULL DEFAULT 0,
                stance TEXT NOT NULL DEFAULT 'Standing',
                stats TEXT DEFAULT '{}', skills TEXT DEFAULT '{}', known_spells TEXT NOT NULL DEFAULT '[]', known_abilities TEXT NOT NULL DEFAULT '[]',
                location_id INTEGER DEFAULT 10, -- Start in Tavern now
                inventory TEXT NOT NULL DEFAULT '[]', equipment TEXT NOT NULL DEFAULT '{}', coinage INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_saved TIMESTAMP,
                UNIQUE (player_id, first_name, last_name), FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
                FOREIGN KEY (location_id) REFERENCES rooms(id) ON DELETE SET DEFAULT,
                FOREIGN KEY (race_id) REFERENCES races(id) ON DELETE SET NULL, FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE SET NULL )
        """)
        log.info("Table schema check complete.")

        # --- Phase 2: Populate Base Lookups (Races, Classes) ---
        log.info("Step 2: Populating Races and Classes...")
        default_races = [ # Use 'Chrozalin'
            (1, "Chrozalin", "Versatile humans, common throughout the lands."),
            (2, "Dwarf", "Stout and hardy mountain folk."),
            (3, "Elf", "Graceful, long-lived forest dwellers."),
            (4, "Yan-tar", "Ancient, wise turtle-like people."),
            (5, "Grak", "Grak are towering humanoids known for their formidable strength and hardy builds, often found in harsh climates or working demanding physical labor.")
        ]
        await conn.executemany("INSERT OR IGNORE INTO races(id, name, description) VALUES(?, ?, ?)", default_races)

        default_classes = [
            (1, "Warrior", "Master of weapons and armor."),
            (2, "Mage", "Controller of arcane energies."),
            (3, "Cleric", "Channeler of divine power."),
            (4, "Rogue", "Agent of stealth and skill.")
        ]
        await conn.executemany("INSERT OR IGNORE INTO classes(id, name, description) VALUES(?, ?, ?)", default_classes)
        log.info("Races & Classes populated.")

        # --- Phase 3: Populate Item Templates ---
        log.info("Step 3: Populating Item Templates (~50)...")
        # (IDs 1-20 defined previously - some may be adjusted slightly)
        default_items = [
            # --- Basic Gear & Loot (1-20) ---
            (1, "a rusty dagger", "Simple, pitted.", "WEAPON", json.dumps({"wear_location": "WIELD_MAIN", "damage_base": 2, "damage_rng": 4, "speed": 1.5, "weight": 1, "value": 5}), json.dumps([]), "pierce"),
            (2, "a cloth shirt", "Basic protection.", "ARMOR", json.dumps({"wear_location": "TORSO", "armor": 1, "weight": 1, "value": 10}), json.dumps([]), None),
            (3, "a small pouch", "Holds small items. Requires a belt.", "CONTAINER", json.dumps({"wear_location": "BELT_ITEM", "weight": 0, "value": 2, "capacity": 5}), json.dumps(["CONTAINER"]), None), # Added BELT_ITEM location concept
            (4, "heavy work boots", "Scuffed but sturdy.", "ARMOR", json.dumps({"wear_location": "FEET", "armor": 1, "speed": 0.2, "weight": 3, "value": 20}), json.dumps([]), None),
            (5, "an iron ring", "A plain band.", "ARMOR", json.dumps({"wear_location": ["FINGER_L", "FINGER_R"], "armor": 0, "weight": 0, "value": 10}), json.dumps([]), None),
            (6, "a wooden shield", "Offers basic defense.", "SHIELD", json.dumps({"wear_location": "WIELD_OFF", "armor": 2, "block_chance": 0.1, "speed": 0.5, "weight": 5, "value": 30}), json.dumps([]), None),
            (7, "stale bread", "Looks barely edible.", "FOOD", json.dumps({"weight": 0, "value": 1, "effect": "heal_hp", "amount": 2}), json.dumps([]), None),
            (8, "cloth trousers", "Simple leg coverings.", "ARMOR", json.dumps({"wear_location": "LEGS", "armor": 1, "weight": 1, "value": 10}), json.dumps([]), None),
            (9, "a leather cap", "Minimal head protection.", "ARMOR", json.dumps({"wear_location": "HEAD", "armor": 1, "weight": 1, "value": 15}), json.dumps([]), None),
            (10, "a short sword", "A standard sidearm.", "WEAPON", json.dumps({"wear_location": "WIELD_MAIN", "damage_base": 3, "damage_rng": 6, "speed": 2.0, "weight": 3, "value": 25}), json.dumps([]), "slash"),
            (11, "leather gloves", "Protects the hands.", "ARMOR", json.dumps({"wear_location": "HANDS", "armor": 1, "weight": 0, "value": 12}), json.dumps([]), None),
            (12, "a minor healing potion", "A vial of swirling red liquid.", "CONSUMABLE", json.dumps({"weight": 0, "value": 25, "effect": "heal_hp", "amount": 20}), json.dumps(["POTION"]), None),
            (13, "a silver locket", "Engraved with faded initials.", "ARMOR", json.dumps({"wear_location": "NECK", "armor": 0, "weight": 0, "value": 50}), json.dumps([]), None),
            (14, "a sturdy backpack", "Well-used leather, can hold much.", "CONTAINER", json.dumps({"wear_location": "BACK", "weight": 2, "value": 30, "capacity": 20}), json.dumps(["CONTAINER"]), None),
            (15, "a waterskin", "Holds water, nearly full.", "DRINK", json.dumps({"weight": 1, "value": 5, "effect": "quench_thirst", "charges": 3}), json.dumps([]), None), # Added charges
            (16, "a ruby gemstone", "A glittering red gem.", "TREASURE", json.dumps({"weight": 0, "value": 100}), json.dumps([]), None),
            (17, "a rat tail", "A trophy, or perhaps useful?", "GENERAL", json.dumps({"weight": 0, "value": 1}), json.dumps(["LOOT"]), None),
            (18, "crab chitin", "A sharp piece of crab shell.", "GENERAL", json.dumps({"weight": 0, "value": 3}), json.dumps(["LOOT"]), None),
            (19, "sprite dust", "Fine, shimmering dust.", "GENERAL", json.dumps({"weight": 0, "value": 10}), json.dumps(["LOOT", "MAGICAL"]), None),
            (20, "turtle shell fragment", "A hard piece of shell.", "GENERAL", json.dumps({"weight": 1, "value": 5}), json.dumps(["LOOT"]), None),

            # --- More Variety (21-50) ---
            (21, "a hand axe", "A simple woodcutting axe.", "WEAPON", json.dumps({"wear_location": "WIELD_MAIN", "damage_base": 2, "damage_rng": 6, "speed": 2.2, "weight": 4, "value": 18}), json.dumps([]), "slash"),
            (22, "a wooden club", "A heavy piece of wood.", "WEAPON", json.dumps({"wear_location": "WIELD_MAIN", "damage_base": 3, "damage_rng": 4, "speed": 2.5, "weight": 5, "value": 10}), json.dumps([]), "bludgeon"),
            (23, "leather armor", "Suit of boiled leather.", "ARMOR", json.dumps({"wear_location": "TORSO", "armor": 3, "weight": 10, "value": 50}), json.dumps([]), None),
            (24, "leather leggings", "Matching leather trousers.", "ARMOR", json.dumps({"wear_location": "LEGS", "armor": 2, "weight": 5, "value": 40}), json.dumps([]), None),
            (25, "a bronze key", "A small, tarnished key.", "KEY", json.dumps({"weight": 0, "value": 1, "key_id": "starter_chest"}), json.dumps(["KEY"]), None),
            (26, "a lockpick set", "Tools for bypassing locks.", "TOOL", json.dumps({"weight": 1, "value": 75}), json.dumps([]), None),
            (27, "a cleric symbol", "A holy symbol of carved wood.", "GENERAL", json.dumps({"weight": 0, "value": 5}), json.dumps([]), None),
            (28, "a mage staff", "A simple oak staff, faintly humming.", "WEAPON", json.dumps({"wear_location": "WIELD_MAIN", "damage_base": 1, "damage_rng": 4, "speed": 2.8, "weight": 4, "value": 30, "bonus_apr": 1}), json.dumps(["TWO_HANDED", "MAGICAL"]), "bludgeon"), # Staff gives APR bonus
            (29, "a torch", "Unlit, smells of pitch.", "LIGHT", json.dumps({"weight": 1, "value": 2, "duration": 300}), json.dumps([]), None),
            (30, "chainmail shirt", "Interlinked metal rings.", "ARMOR", json.dumps({"wear_location": "TORSO", "armor": 5, "speed": 0.3, "weight": 20, "value": 150}), json.dumps([]), None),
            (31, "leather helm", "Simple studded leather.", "ARMOR", json.dumps({"wear_location": "HEAD", "armor": 2, "weight": 2, "value": 35}), json.dumps([]), None),
            (32, "leather boots", "Standard adventurer footwear.", "ARMOR", json.dumps({"wear_location": "FEET", "armor": 1, "weight": 2, "value": 30}), json.dumps([]), None),
            (33, "a mace", "A metal head on a wooden shaft.", "WEAPON", json.dumps({"wear_location": "WIELD_MAIN", "damage_base": 3, "damage_rng": 5, "speed": 2.4, "weight": 6, "value": 22}), json.dumps([]), "bludgeon"),
            (34, "chainmail leggings", "Heavy protection for the legs.", "ARMOR", json.dumps({"wear_location": "LEGS", "armor": 4, "speed": 0.2, "weight": 15, "value": 120}), json.dumps([]), None),
            (35, "a shortbow", "Made of yew wood.", "WEAPON", json.dumps({"wear_location": "WIELD_MAIN", "damage_base": 0, "damage_rng": 0, "speed": 3.0, "weight": 3, "value": 40, "requires_ammo": "arrow"}), json.dumps(["RANGED", "TWO_HANDED"]), "pierce"), # Ranged example
            (36, "a bundle of arrows", "Simple arrows with iron heads.", "AMMO", json.dumps({"weight": 1, "value": 10, "ammo_type": "arrow", "quantity": 20}), json.dumps([]), None), # Ammo example
            (37, "a silk cloak", "Dyed a deep blue.", "ARMOR", json.dumps({"wear_location": "CLOAK", "armor": 0, "weight": 1, "value": 60}), json.dumps([]), None),
            (38, "leather bracers", "Protect the forearms.", "ARMOR", json.dumps({"wear_location": "ARMS", "armor": 1, "weight": 1, "value": 25}), json.dumps([]), None),
            (39, "a simple belt", "A sturdy leather belt.", "ARMOR", json.dumps({"wear_location": "WAIST", "armor": 0, "weight": 0, "value": 8}), json.dumps([]), None),
            (40, "a minor essence potion", "A vial of swirling blue liquid.", "CONSUMABLE", json.dumps({"weight": 0, "value": 30, "effect": "heal_essence", "amount": 15}), json.dumps(["POTION"]), None),
            (41, "a steel shield", "Heavy and strong.", "SHIELD", json.dumps({"wear_location": "WIELD_OFF", "armor": 4, "block_chance": 0.15, "speed": 0.8, "weight": 12, "value": 100}), json.dumps([]), None),
            (42, "a long sword", "A well-balanced knightly sword.", "WEAPON", json.dumps({"wear_location": "WIELD_MAIN", "damage_base": 4, "damage_rng": 8, "speed": 2.5, "weight": 5, "value": 75}), json.dumps([]), "slash"),
            (43, "a warhammer", "A heavy, intimidating hammer.", "WEAPON", json.dumps({"wear_location": "WIELD_MAIN", "damage_base": 5, "damage_rng": 6, "speed": 3.0, "weight": 8, "value": 70}), json.dumps(["TWO_HANDED"]), "bludgeon"),
            (44, "a length of rope", "About 50 feet of hemp rope.", "TOOL", json.dumps({"weight": 3, "value": 5}), json.dumps([]), None),
            (45, "emerald dust", "Gritty green powder.", "REAGENT", json.dumps({"weight": 0, "value": 40}), json.dumps(["MAGICAL"]), None), # Example reagent
            (46, "a wolf pelt", "Thick grey fur.", "GENERAL", json.dumps({"weight": 2, "value": 8}), json.dumps(["LOOT"]), None), # Example type loot
            (47, "bone dust", "Coarse powder from crushed bones.", "REAGENT", json.dumps({"weight": 0, "value": 3}), json.dumps(["LOOT"]), None), # Example type loot
            (48, "a gold necklace", "Simple but elegant.", "ARMOR", json.dumps({"wear_location": "NECK", "armor": 0, "weight": 0, "value": 150}), json.dumps([]), None),
            (49, "plate mail", "Gleaming articulated steel plates.", "ARMOR", json.dumps({"wear_location": "TORSO", "armor": 8, "speed": 0.5, "weight": 40, "value": 500}), json.dumps([]), None), # Heavy armor
            (50, "a spyglass", "Used for seeing distant things.", "TOOL", json.dumps({"weight": 1, "value": 120}), json.dumps([]), None),
        ]
        try:
            await conn.executemany(
                """INSERT OR IGNORE INTO item_templates (id, name, description, type, stats, flags, damage_type) VALUES (?, ?, ?, ?, ?, ?, ?)""", default_items
            )
            log.info("Item Templates populated.")
        except aiosqlite.Error as e: log.error("Failed to populate default item templates: %s", e)

        # --- Phase 4: Populate Mob Templates ---
        log.info("Step 4: Populating Mob Templates...")
        default_mobs = [
            (1, "a giant rat", "Larger than common vermin, this grey-furred rat has beady eyes and sharp, yellowed teeth. It twitches nervously.", "Beast", 1,
            json.dumps({"might": 5, "vitality": 5, "agility": 8}), 6, # stats, max_hp
            json.dumps([{"name": "bite", "damage_base": 1, "damage_rng": 3, "speed": 3.0}]), # attacks
            json.dumps({"coinage_max": 3, "items": [{"template_id": 17, "chance": 0.20}]}), # loot (rat tail)
            json.dumps([]), 60, json.dumps({"max_hp_pct": 15, "stats_pct": 10}), 0.03), # flags, respawn, variance, move%
            (2, "a giant crab", "A crustacean about the size of a large plate, its sandy shell blends with the ground. Its claws snap intermittently.", "Beast", 2,
            json.dumps({"might": 8, "vitality": 10, "agility": 6}), 12, # stats, max_hp
            json.dumps([{"name": "pinch", "damage_base": 1, "damage_rng": 4, "speed": 3.5}]), # attacks
            json.dumps({"coinage_max": 5, "items": [{"template_id": 18, "chance": 0.15}]}), # loot (chitin)
            json.dumps(["AGGRESSIVE"]), 90, json.dumps({"max_hp_pct": 15, "stats_pct": 10}), 0.02), # flags, respawn, variance, move%
            (3, "a mischievous sea sprite", "A tiny, humanoid figure wreathed in sea spray and flickering blue light. It darts through the air with playful malice.", "Magical", 3,
            json.dumps({"might": 4, "vitality": 6, "agility": 12, "intellect": 10}), 12, # stats, max_hp
            json.dumps([{"name": "water jet", "damage_base": 1, "damage_rng": 4, "speed": 3.0, "damage_type": "cold"}]), # attacks
            json.dumps({"coinage_max": 8, "items": [{"template_id": 16, "chance": 0.01}, {"template_id": 19, "chance": 0.1}]}), # loot (ruby, dust)
            json.dumps(["AGGRESSIVE"]), 120, json.dumps({"max_hp_pct": 10, "stats_pct": 15}), 0.03), # flags, respawn, variance, move%
            (4, "a giant snapping turtle", "A large turtle with a thick, algae-covered shell and a powerful beak capable of delivering a nasty bite.", "Beast", 4,
            json.dumps({"might": 10, "vitality": 14, "agility": 4}), 25, # stats, max_hp
            json.dumps([{"name": "snap", "damage_base": 3, "damage_rng": 5, "speed": 4.0}]), # attacks
            json.dumps({"coinage_max": 15, "items": [{"template_id": 20, "chance": 0.1}]}), # loot (shell frag)
            json.dumps(["AGGRESSIVE"]), 180, json.dumps({"max_hp_pct": 10, "stats_pct": 5}), 0.0), # flags, respawn, variance, move% (Stationary)
            (5, "a HUGE king snapping turtle", "Truly immense, this ancient turtle seems almost part of the landscape, its shell covered in barnacles and seaweed. Its eyes hold ancient patience... and hunger.", "Beast", 6,
            json.dumps({"might": 15, "vitality": 20, "agility": 3}), 50, # stats, max_hp
            json.dumps([{"name": "CRUSHING bite", "damage_base": 5, "damage_rng": 8, "speed": 5.0}]), # attacks
            json.dumps({"coinage_max": 50, "items": [{"template_id": 6, "chance": 0.05}, {"template_id": 20, "chance": 0.25}]}), # loot (shield, shell frag)
            json.dumps(["AGGRESSIVE"]), 600, json.dumps({"max_hp_pct": 10, "stats_pct": 5}), 0.0), # flags, respawn, variance, move% (Stationary)
            (6, "a Haven town guard", "Clad in simple leather and carrying a sword, the guard looks alert and capable, keeping a watchful eye on the surroundings.", "Humanoid", 5,
            json.dumps({"might": 14, "vitality": 13, "agility": 12, "intellect": 10, "aura": 9, "persona": 10}), 30, # stats, max_hp
            json.dumps([{"name": "sword slash", "damage_base": 4, "damage_rng": 6, "speed": 2.2}]), # attacks
            json.dumps({"coinage_max": 20, "items": [{"template_id": 10, "chance": 0.05}, {"template_id": 2, "chance": 0.02}]}), # loot (short sword, shirt)
            json.dumps(["GUARD"]), 300, json.dumps({"max_hp_pct": 5, "stats_pct": 5}), 0.01), # flags (Removed '?'), respawn, variance, move% (Low chance)
        ]
        try:
            await conn.executemany(
                """INSERT OR IGNORE INTO mob_templates (id, name, description, mob_type, level, stats, max_hp, attacks, loot, flags, respawn_delay_seconds, variance, movement_chance) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", default_mobs
            )
            log.info("Mob Templates populated.")
        except aiosqlite.Error as e: log.error("Failed to populate default mob templates: %s", e)

        # --- Phase 5: Populate World Geometry (Areas, Rooms) ---
        log.info("Step 5: Populating Areas and Rooms...")
        # ... (Define default_areas as before: 1=Genesis, 2=Haven, 3=Beach) ...
        # ... (executemany INSERT OR IGNORE into areas) ...
        default_areas = [
            (1, "The Void", "A swirling nexus outside normal reality."),
            (2, "Seaside Town of Haven", "A bustling port town nestled against the cliffs."),
            (3, "Sandy Beach", "The coastline near Haven, bordering the Azure Sea."),
        ]
        try:
            await conn.executemany("INSERT OR IGNORE INTO areas (id, name, description) VALUES (?, ?, ?)", default_areas)
            await conn.commit() # <<< COMMIT Areas before inserting Rooms
            log.info("Checked/Populated default areas.")
        except aiosqlite.Error as e:
            log.error("Failed to populate default areas: %s", e)
            # If areas fail, rooms will definitely fail, maybe return early?
            raise # Re-raise the exception to stop init_db potentially

        # Define Rooms (ID, AreaID, Name, Desc, Exits JSON, Flags JSON, Spawners JSON, Coinage INT)
        # Expand Haven Town, connect Beach, add spawners sparsely
        default_rooms = [
            # --- Genesis Area (Area 1) ---
            (1, 1, "The Void",
            "A featureless void stretches around you. To the north, the entrance to a noisy tavern shimmers slightly.",
            json.dumps({"north": TAVERN_ID}), json.dumps(["NODE"]), '{}', 0),

            # --- Seaside Town of Haven (Area 2) ---
            (TAVERN_ID, 2, "The Salty Siren Tavern", # ID 10
            "The air smells heavily of stale ale, cheap perfume, sweat, and the nearby sea. A long, sticky bar stretches along the north wall, behind which a burly bartender cleans mugs. Several rough-looking patrons eye you warily. Exits lead south (back to the void) and east (to West Street).",
            json.dumps({"south": 1, "east": WEST_STREET_ID}), json.dumps(["NODE", "INDOORS"]), '{}', 0),
            (MARKET_ID, 2, "Haven Market Square", # ID 11
            "The bustling heart of Haven features a large, weathered fountain depicting leaping dolphins (currently dry). Market stalls, mostly empty now, line the edges. Cobblestone streets lead west (West Street), north (North Street), south (South Street), and east (East Street). A sandy path leads southeast towards the beach.",
            json.dumps({"west": WEST_STREET_ID, "north": NORTH_STREET_ID, "south": SOUTH_STREET_ID, "east": EAST_STREET_ID, "southeast": BEACH_ENTRANCE_ID}), json.dumps(["OUTDOORS"]), json.dumps({"6": {"max_present": 1}}), 0),
            (DOCKS_ID, 2, "Haven Docks", # ID 12
            "The creak of timber and calls of gulls fill the air, mingling with the strong smell of salt and fish. Wooden piers stretch out over the choppy grey water, slick with sea spray. A well-trodden path leads east back towards West Street. A small fish market stall is set up to the north.",
            json.dumps({"east": WEST_STREET_ID, "north": FISH_MARKET_ID}), json.dumps(["OUTDOORS", "WET"]), '{}', 0),
            (TOWNHALL_ID, 2, "Town Hall Steps", # ID 13
            "A sturdy, two-story wooden building stands before you, the seat of Haven's council. Large oak doors mark the entrance (currently closed). Steps lead south back towards North Street.",
            json.dumps({"south": NORTH_STREET_ID}), json.dumps(["OUTDOORS"]), '{}', 0),
            (GATEHOUSE_ID, 2, "South Gatehouse", # ID 14
            "This stone gatehouse guards the southern entrance to Haven. Two guards stand alertly, watching the road south (which is currently blocked by debris). The way back north leads to South Street.",
            json.dumps({"north": SOUTH_STREET_ID}), json.dumps(["OUTDOORS"]), json.dumps({"6": {"max_present": 2}}), 0),
            (GRAVEYARD_ID, 2, "Haven Graveyard", # ID 15
            "An eerie, quiet space filled with weathered headstones leaning at odd angles. Wisps of fog cling to the ground, even on a clear day. A rusty, wrought-iron gate leads east back towards the town path.",
            json.dumps({"east": GRAVEYARD_PATH_ID}), json.dumps(["OUTDOORS", "RESPAWN"]), '{}', 0),
            (GRAVEYARD_PATH_ID, 2, "Graveyard Path", # ID 16
            "A narrow, slightly overgrown path runs between the silent graveyard (west) and the slightly more lively West Street (east). The air here feels cold.",
            json.dumps({"west": GRAVEYARD_ID, "east": WEST_STREET_ID}), json.dumps(["OUTDOORS"]), '{}', 0),
            (WEST_STREET_ID, 2, "West Street", # ID 17
            "A main thoroughfare paved with uneven cobblestones, slick near the docks turnoff. It connects the Docks (west), the Graveyard path (north), the Market Square (east), and the Salty Siren Tavern (south). A small cottage sits to the northwest.",
            json.dumps({"west": DOCKS_ID, "north": GRAVEYARD_PATH_ID, "east": MARKET_ID, "south": TAVERN_ID, "northwest": 20}), json.dumps(["OUTDOORS"]), json.dumps({"6": {"max_present": 1}}), 0), # Added Cottage Exit
            (ARMORY_ID, 2, "Haven Armory", # ID 18
            "The smell of oil and metal polish hangs heavy in the air. Racks of basic weapons and armor stand ready, gleaming dully in the torchlight. The exit leads south onto East Street.",
            json.dumps({"south": EAST_STREET_ID}), json.dumps(["INDOORS"]), '{}', 0), # Connects to East Street now
            (LIBRARY_ID, 2, "Library Entrance", # ID 19
            "Dust motes dance in the dim light filtering through tall, arched windows. Massive bookshelves line the walls, filled with ancient tomes. The entrance lies south on North Street.",
            json.dumps({"south": NORTH_STREET_ID}), json.dumps(["INDOORS", "QUIET"]), '{}', 0),
            (TEMPLE_ID, 2, "Temple of the Sea", # ID 20
            "Cool, salty air fills this large chamber. Intricate carvings of waves and sea creatures adorn the stone walls. A large altar of polished driftwood stands at the far end, dedicated to the ocean deities. The temple entrance is west, onto East Street.",
            json.dumps({"west": EAST_STREET_ID}), json.dumps(["INDOORS", "HOLY"]), '{}', 0),
            (EAST_STREET_ID, 2, "East Street", # ID 21
            "This street runs along the eastern side of the main square. It connects the Market Square (west) to the Temple of the Sea (east). The entrance to the Armory is clearly visible to the north, while a small hut flying a healer's banner sits to the south.",
            json.dumps({"west": MARKET_ID, "east": TEMPLE_ID, "north": ARMORY_ID, "south": HEALER_HUT_ID}), json.dumps(["OUTDOORS"]), '{}', 0),
            (NORTH_STREET_ID, 2, "North Street", # ID 22
            "Heading north from the Market Square, this street leads towards the imposing Town Hall steps further north. The entrance to the Library is on the east side of the street, and a Weaver's Shop is opposite it to the west.",
            json.dumps({"south": MARKET_ID, "north": TOWNHALL_ID, "east": LIBRARY_ID, "west": WEAVERS_SHOP_ID}), json.dumps(["OUTDOORS"]), '{}', 0),
            (SOUTH_STREET_ID, 2, "South Street", # ID 23
            "This street runs south from the Market Square towards the town's South Gatehouse. A dim alleyway branches off to the west, and the smell of fresh bread wafts from a shop to the east. A sturdy building, likely the Guard Barracks, is visible further south before the Gatehouse.",
            json.dumps({"north": MARKET_ID, "south": GUARD_BARRACKS_ID, "west": ALLEY_ID, "east": BAKERY_ID}), json.dumps(["OUTDOORS"]), '{}', 0),
            (ALLEY_ID, 2, "Dim Alley", # ID 24
            "Narrow and shadowed between two tall buildings, this alley smells faintly of refuse and damp stone. It appears to be a dead end further west, with the only way out back east to South Street.",
            json.dumps({"east": SOUTH_STREET_ID}), json.dumps(["OUTDOORS", "DARK"]), '{}', 0), # Dead end for now
            (BEACH_ENTRANCE_ID, 2, "Path to the Beach", # ID 25
            "A well-worn, sandy path winds gently down towards the sound of the surf to the east. Behind you, northwest, lies the bustling Market Square.",
            json.dumps({"northwest": MARKET_ID, "east": BEACH_START_ID}), json.dumps(["OUTDOORS"]), '{}', 0),
            (FISH_MARKET_ID, 2, "Fish Market Stall", # ID 26
            "A simple wooden stall covered by a stained canvas awning. Buckets of fish sit on ice, their briny scent thick in the air. The main docks area is south.",
            json.dumps({"south": DOCKS_ID}), json.dumps(["OUTDOORS", "WET"]), '{}', 0),
            (GUARD_BARRACKS_ID, 2, "Guard Barracks", # ID 27
            "Several bunks line the walls of this functional, slightly spartan room. Off-duty guards might be resting here (no spawns yet). The exit leads north onto South Street.",
            json.dumps({"north": SOUTH_STREET_ID}), json.dumps(["INDOORS"]), '{}', 0),
            (HEALER_HUT_ID, 2, "Healer's Hut", # ID 28
            "The scent of herbs and poultices fills this small hut. Drying plants hang from the rafters. A kindly-looking healer often tends to townsfolk here. The door leads north to East Street.",
            json.dumps({"north": EAST_STREET_ID}), json.dumps(["INDOORS"]), '{}', 0),
            (GENERAL_STORE_ID, 2, "Haven General Store", # ID 29 - Connect to Market?
            "Shelves line the walls, stocked with various basic goods - ropes, torches, tools, and provisions. A counter stands near the back. The entrance opens onto the Market Square.",
            json.dumps({"south": MARKET_ID}), # Assuming north side of market
            json.dumps(["INDOORS"]), '{}', 0),
            (WEAVERS_SHOP_ID, 2, "Weaver's Shop", # ID 30 - Connect to North Street
            "Bolts of simple cloth and finished garments are neatly arranged here. A large loom sits in the corner, currently idle. The door leads east to North Street.",
            json.dumps({"east": NORTH_STREET_ID}),
            json.dumps(["INDOORS"]), '{}', 0),
            (BAKERY_ID, 2, "The Rolling Pin Bakery", # ID 31 - Connect to South Street
            "The warm, inviting smell of baking bread fills the air. Trays of loaves and pastries sit cooling on racks. The entrance is west onto South Street.",
            json.dumps({"west": SOUTH_STREET_ID}),
            json.dumps(["INDOORS"]), '{}', 0),
            (20, 2, "Empty Cottage", # ID 20 from previous plan, now assigned, connected to West St
            "This small cottage seems abandoned. Dust covers the sparse furniture, and cobwebs hang in the corners. The door leads southeast back to West Street.",
            json.dumps({"southeast": WEST_STREET_ID}), json.dumps(["INDOORS", "DARK"]), '{}', 0),


            # --- Beach Area (Area 3) --- IDs 100+ and 4
            (BEACH_START_ID, 3, "Sandy Shore", # ID 100
            "Waves lap gently at the sand under a wide sky...", # Keep desc short
            json.dumps({"northwest": BEACH_ENTRANCE_ID, "north": 101, "south": 102}), json.dumps(["OUTDOORS", "WET"]), json.dumps({"2": {"max_present": 1}}), 0), # Crab
            (101, 3, "North Beach", "The beach curves gently northwards...",
            json.dumps({"north": 103, "south": BEACH_START_ID}), json.dumps(["OUTDOORS", "WET"]), json.dumps({"2": {"max_present": 1}}), 0), # Crab, Sprite
            (102, 3, "South Beach", "Numerous tide pools dot the wet sand...",
            json.dumps({
            "north": BEACH_START_ID, "south": 104,
            "hole": {
            "target": CAVE_ID,
            "skill_check": {"skill": "acrobatics", "dc": 12, "fail_damage": 2, "fail_msg": "You tumble awkwardly into the hole!", "success_msg": "You carefully descend into the hole."}
            } # Correct closing brace for hole dict
            }), # Correct closing brace for main exits dict
            json.dumps(["OUTDOORS", "WET"]), json.dumps({"2": {"max_present": 1}, "4": {"max_present": 1}}), 0),
            (103, 3, "Rocky Outcropping (N)", "Jagged black rocks jut out into the waves...",
            json.dumps({"south": 101, "north": 105}), json.dumps(["OUTDOORS", "ROUGH_TERRAIN", "WET"]), json.dumps({"3": {"max_present": 1}}), 0), # Sprite
            (104, 3, "Turtle Nesting Ground (S)", "Large depressions mark nests...", json.dumps({"north": 102, "south": 108}), json.dumps(["OUTDOORS", "WET"]), json.dumps({"4": {"max_present": 1}, "5": {"max_present": 1}}), 0),
            (CAVE_ID, 3, "A Damp Cave", "Water drips steadily...",
            json.dumps({ # Correct closing brace for climb up dict
                "climb up": {
                    "target": 102,
                    "skill_check": {"skill": "climbing", "dc": 12, "fail_damage": 3, "fail_msg": "You slip while climbing and fall back down!", "success_msg": "You manage to climb up out of the hole."}
                } # Correct closing brace for skill_check dict
            }), # Correct closing brace for main exits dict
            json.dumps(["INDOORS", "DARK", "WET"]), json.dumps({"1": {"max_present": 1}}), 0),
            (105, 3, "Northern Cliffs Base", "Sheer cliffs rise...",
            json.dumps({ # Correct closing brace for climb cliff dict
                "south": 103,
                "climb cliff": {
                    "target": 106,
                    "skill_check": {"skill": "climbing", "dc": 15, "fail_damage": 5, "fail_msg": "The slick rocks offer no purchase and you tumble down!", "success_msg": "You find handholds and scale the lower cliff face."}
                } # Correct closing brace for skill_check dict
            }), # Correct closing brace for main exits dict
            json.dumps(["OUTDOORS", "ROUGH_TERRAIN", "WET"]), json.dumps({"3": {"max_present": 1}}), 0),
            (106, 3, "Northern Cliff Ledge", "You stand on a narrow ledge...",
            json.dumps({ # Correct closing brace for climb down dict
                "in": 107,
                "climb down": {
                    "target": 105,
                    "skill_check": {"skill": "climbing", "dc": 10, "fail_damage": 2, "fail_msg": "You slip near the bottom and land hard!", "success_msg": "You carefully climb back down to the base."} # Note: Changed fail_damage from 5->2 as climb down is easier
                } # Correct closing brace for skill_check dict
            }), # Correct closing brace for main exits dict
            json.dumps(["OUTDOORS", "WINDY", "HEIGHTS"]), '{}', 0),
            (107, 3, "Small Sea Cave", "This cramped, damp cave echoes with the cries of seabirds...",
            json.dumps({"out": 106}), json.dumps(["INDOORS", "DARK", "WET"]), json.dumps({"2": {"max_present": 1}}), 0),
            (108, 3, "Sandy Dunes", "Rolling dunes of fine sand stretch southward...",
            json.dumps({"north": 104, "south": 109}), json.dumps(["OUTDOORS"]), json.dumps({"2": {"max_present": 1}}), 0),
            (109, 3, "Shipwreck Debris", "The shattered timbers... lie half-buried in the sand...",
            json.dumps({"north": 108, "east": INLAND_SCRUB_ID}), json.dumps(["OUTDOORS", "WET"]), json.dumps({"4": {"max_present": 1}}), 0), # Added east exit
            # --- V V V New Beach Rooms V V V ---
            (CLIFF_CAVE_DEEPER_ID, 3, "Cliff Cave - Deeper Section", # ID 110
            "The cave narrows here, the air growing colder. Water pools on the floor, reflecting faint light from unseen phosphorescence. The only way back is out.",
            json.dumps({"out": 107}), json.dumps(["INDOORS", "DARK", "WET"]), json.dumps({"2": {"max_present": 2}}), 0), # More crabs
            (NORTH_CLIFF_PATH_ID, 3, "North Cliff Path", # ID 111
            "The narrow path continues precariously along the cliff face, buffeted by strong winds. The ledge is south, and the path continues north towards the summit.",
            json.dumps({"south": 106, "north": CLIFF_SUMMIT_ID}), json.dumps(["OUTDOORS", "WINDY", "HEIGHTS"]), json.dumps({"3": {"max_present": 1}}), 0), # Sprite
            (CLIFF_SUMMIT_ID, 3, "Cliff Summit", # ID 112
            "You stand atop the sea cliffs, with a commanding view of the Azure Sea stretching to the horizon. The wind whips fiercely here. The only way down is the path south.",
            json.dumps({"south": NORTH_CLIFF_PATH_ID}), json.dumps(["OUTDOORS", "WINDY", "HEIGHTS"]), '{}', 0), # No spawns, scenic spot
            (SOUTH_DUNES_ID, 3, "South Dunes", # ID 113
            "These large sand dunes mark the southern extent of the main beach. Windswept sand shifts constantly. The shipwreck debris is north, and a path seems to lead inland through scrub to the east.",
            json.dumps({"north": 109, "east": INLAND_SCRUB_ID}), json.dumps(["OUTDOORS", "WINDY"]), json.dumps({"2": {"max_present": 1}}), 0), # Crab
            (INLAND_SCRUB_ID, 3, "Inland Scrub", # ID 114
            "Leaving the beach behind, you enter an area of hardy, salt-resistant scrub bushes and rough grasses. The dunes are back to the west.",
            json.dumps({"west": SOUTH_DUNES_ID}), json.dumps(["OUTDOORS"]), json.dumps({"1": {"max_present": 2}}), 0), # Rats inland
            # --- ^ ^ ^ End New Beach Rooms ^ ^ ^ ---
        ]
        try:
            await conn.executemany(
                """INSERT OR IGNORE INTO rooms (id, area_id, name, description, exits, flags, spawners, coinage) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", default_rooms
            )
            log.info("Areas & Rooms populated.")
        except aiosqlite.Error as e: log.error("Failed to populate default rooms: %s", e)

        # Add inside init_db, after populating rooms (Phase 5)
        # --- V V V Populate Room Objects V V V ---
        log.info("Step 5c: Populating Room Objects...") # Example step number
        default_room_objects = [
        # room_id, name, description, keywords_json
        (MARKET_ID, "a weathered fountain", "A large stone fountain depicting leaping dolphins stands in the center of the square. It's currently dry and stained with age and bird droppings.", json.dumps(["fountain", "weathered fountain", "stone fountain"])),
        (TEMPLE_ID, "an altar of driftwood", "Polished smooth by time and sea, this large piece of driftwood serves as the temple's central altar. Offerings of shells and sea glass rest upon it.", json.dumps(["altar", "driftwood", "driftwood altar"])),
        (TAVERN_ID, "a sticky bar", "The long wooden bar is dark with age and stained from countless spills. Several sturdy stools sit before it.", json.dumps(["bar", "sticky bar", "wooden bar"])),
        (LIBRARY_ID, "towering bookshelves", "Floor-to-ceiling bookshelves, crammed with leather-bound volumes, line the library walls.", json.dumps(["bookshelves", "shelves", "bookshelf", "tomes", "books"])),
        (GRAVEYARD_ID, "weathered headstones", "Leaning at odd angles, these stone markers bear faded names and dates, testaments to lives long past.", json.dumps(["headstone", "headstones", "gravestone", "gravestones", "stone", "stones", "marker", "markers"])),
        ]
        try:
            await conn.executemany(
            """INSERT OR IGNORE INTO room_objects (room_id, name, description, keywords)
            VALUES (?, ?, ?, ?)""", default_room_objects
            )
            await conn.commit() # Commit room objects
            log.info("Default room objects populated.")
        except aiosqlite.Error as e:
            log.error("Failed to populate default room objects: %s", e)

        # --- Phase 5b: Populate Armory ---
        log.info("Step 5b: Populating Armory...")
        # IDs: Dagger, Shirt, Boots, W-Shield, Trousers, L-Cap, S-Sword, L-Gloves,
        #      Axe, Club, L-Armor, L-Legs, Chain-Shirt, S-Shield, L-Sword, Warhammer, Plate
        armory_items = [
            (ARMORY_ID, 1), (ARMORY_ID, 2), (ARMORY_ID, 4), (ARMORY_ID, 6), (ARMORY_ID, 8),
            (ARMORY_ID, 9), (ARMORY_ID, 10), (ARMORY_ID, 11), (ARMORY_ID, 21), (ARMORY_ID, 22),
            (ARMORY_ID, 23), (ARMORY_ID, 24), (ARMORY_ID, 30), (ARMORY_ID, 41), (ARMORY_ID, 42),
            (ARMORY_ID, 43), (ARMORY_ID, 49),
        ]
        try:
            await conn.executemany(
            """INSERT INTO room_items (room_id, item_template_id) VALUES (?, ?)""", armory_items
            )
            log.info("Armory populated with test items.")
        except aiosqlite.Error as e:
            log.error("Failed to populate armory: %s", e)

        # --- Phase 6: Create Test Player Accounts ---
        log.info("Step 6: Creating Test Player Accounts...")
        test_players = [
            ("tester", utils.hash_password("password"), "tester@example.com", 0), # Normal user
            ("admin", utils.hash_password("password"), "admin@example.com", 1), # Admin user
        ]
        try: # Add specific try block for integrity errors
            await conn.executemany(
                """INSERT INTO players (username, hashed_password, email, is_admin) VALUES (?, ?, ?, ?)""", test_players
            )
            log.info("Test player accounts seeded.")
        except aiosqlite.IntegrityError:
            log.debug("Test player accounts already exist (UNIQUE constraint ignored).")
        except Exception as e:
            log.error("Unexpected error seeding test players: %s", e, exc_info=True)


        # --- Phase 7: Create Test Characters ---
        log.info("Step 7: Creating Test Characters...")
        player1_id = player2_id = None # Init
        try: # Wrap ID fetching just in case players didn't insert
            async with conn.execute("SELECT id FROM players WHERE username='tester'") as cursor: player1_id = (await cursor.fetchone())[0]
            async with conn.execute("SELECT id FROM players WHERE username='admin'") as cursor: player2_id = (await cursor.fetchone())[0]
        except Exception as e:
            log.error("Could not get test player IDs for character seeding, skipping. Error: %s", e)

        if player1_id and player2_id: # Only proceed if IDs were found
            # Import definitions needed for initialization logic
            from .definitions import skills as skill_defs
            from .definitions import classes as class_defs
            from .definitions import abilities as ability_defs

            # --- Define Character Data ---
            # CHAR 1: Testone Testone (Player 1, Chrozalin Warrior)
            c1_stats = {"might": 18, "vitality": 16, "agility": 14, "intellect": 10, "aura": 8, "persona": 8}
            c1_skills = {sk: 0 for sk in skill_defs.INITIAL_SKILLS}; c1_skills.update(class_defs.get_starting_skill_bonuses("warrior"))
            c1_spells = [k for k,d in ability_defs.ABILITIES_DATA.items() if d["level_req"]==1 and d["type"]=="SPELL" and ("warrior" in d["class_req"] or not d["class_req"])]
            c1_abilities = [k for k,d in ability_defs.ABILITIES_DATA.items() if d["level_req"]==1 and d["type"]=="ABILITY" and ("warrior" in d["class_req"] or not d["class_req"])]
            c1_equip = {"WIELD_MAIN": 10, "TORSO": 2, "LEGS": 8, "FEET": 4} # Sword, Shirt, Trousers, Boots
            c1_inv = [3, 6, 7] # Pouch, W-Shield, Bread
            c1_vit_mod = utils.calculate_modifier(c1_stats['vitality'])
            c1_aur_mod = utils.calculate_modifier(c1_stats['aura'])
            c1_per_mod = utils.calculate_modifier(c1_stats['persona'])
            c1_max_hp = float(max(1, class_defs.CLASS_HP_DIE.get(1, class_defs.DEFAULT_HP_DIE) + c1_vit_mod))
            c1_max_ess = float(max(0, class_defs.CLASS_ESSENCE_DIE.get(1, class_defs.DEFAULT_ESSENCE_DIE) + c1_aur_mod + c1_per_mod))
            c1_tether = max(1, c1_aur_mod)

            # CHAR 2: Elara Quickfoot (Player 1, Elf Rogue)
            c2_stats = {"might": 12, "vitality": 13, "agility": 18, "intellect": 14, "aura": 9, "persona": 14}
            c2_skills = {sk: 0 for sk in skill_defs.INITIAL_SKILLS}; c2_skills.update(class_defs.get_starting_skill_bonuses("rogue"))
            c2_spells = [k for k,d in ability_defs.ABILITIES_DATA.items() if d["level_req"]==1 and d["type"]=="SPELL" and ("rogue" in d["class_req"] or not d["class_req"])]
            c2_abilities = [k for k,d in ability_defs.ABILITIES_DATA.items() if d["level_req"]==1 and d["type"]=="ABILITY" and ("rogue" in d["class_req"] or not d["class_req"])]
            c2_equip = {"WIELD_MAIN": 1, "TORSO": 23, "LEGS": 24, "FEET": 32} # Dagger, L-Armor, L-Legs, L-Boots
            c2_inv = [3, 26, 29] # Pouch, Lockpicks, Torch
            c2_vit_mod = utils.calculate_modifier(c2_stats['vitality'])
            c2_aur_mod = utils.calculate_modifier(c2_stats['aura'])
            c2_per_mod = utils.calculate_modifier(c2_stats['persona'])
            c2_max_hp = float(max(1, class_defs.CLASS_HP_DIE.get(4, class_defs.DEFAULT_HP_DIE) + c2_vit_mod))
            c2_max_ess = float(max(0, class_defs.CLASS_ESSENCE_DIE.get(4, class_defs.DEFAULT_ESSENCE_DIE) + c2_aur_mod + c2_per_mod))
            c2_tether = max(1, c2_aur_mod)

            # CHAR 3: Fimble Bumble (Player 1, Chrozalin Mage)
            c3_stats = {"might": 8, "vitality": 10, "agility": 12, "intellect": 18, "aura": 16, "persona": 15}
            c3_skills = {sk: 0 for sk in skill_defs.INITIAL_SKILLS}; c3_skills.update(class_defs.get_starting_skill_bonuses("mage"))
            c3_spells = [k for k,d in ability_defs.ABILITIES_DATA.items() if d["level_req"]==1 and d["type"]=="SPELL" and ("mage" in d["class_req"] or not d["class_req"])]
            c3_abilities = [k for k,d in ability_defs.ABILITIES_DATA.items() if d["level_req"]==1 and d["type"]=="ABILITY" and ("mage" in d["class_req"] or not d["class_req"])]
            c3_equip = {"WIELD_MAIN": 28, "TORSO": 2, "HEAD": 9} # Staff, Shirt, L-Cap
            c3_inv = [3, 12, 40, 45] # Pouch, Heal Pot, Ess Pot, Emerald Dust
            c3_vit_mod = utils.calculate_modifier(c3_stats['vitality'])
            c3_aur_mod = utils.calculate_modifier(c3_stats['aura'])
            c3_per_mod = utils.calculate_modifier(c3_stats['persona'])
            c3_max_hp = float(max(1, class_defs.CLASS_HP_DIE.get(2, class_defs.DEFAULT_HP_DIE) + c3_vit_mod))
            c3_max_ess = float(max(0, class_defs.CLASS_ESSENCE_DIE.get(2, class_defs.DEFAULT_ESSENCE_DIE) + c3_aur_mod + c3_per_mod))
            c3_tether = max(1, c3_aur_mod)

            # CHAR 4: Borin Stonehand (Player 1, Dwarf Cleric)
            c4_stats = {"might": 14, "vitality": 17, "agility": 9, "intellect": 13, "aura": 15, "persona": 16}
            c4_skills = {sk: 0 for sk in skill_defs.INITIAL_SKILLS}; c4_skills.update(class_defs.get_starting_skill_bonuses("cleric"))
            c4_spells = [k for k,d in ability_defs.ABILITIES_DATA.items() if d["level_req"]==1 and d["type"]=="SPELL" and ("cleric" in d["class_req"] or not d["class_req"])]
            c4_abilities = [k for k,d in ability_defs.ABILITIES_DATA.items() if d["level_req"]==1 and d["type"]=="ABILITY" and ("cleric" in d["class_req"] or not d["class_req"])]
            c4_equip = {"WIELD_MAIN": 33, "WIELD_OFF": 6, "TORSO": 30, "HEAD": 9} # Mace, W-Shield, Chain, L-Cap
            c4_inv = [3, 27, 7] # Pouch, Symbol, Bread
            c4_vit_mod = utils.calculate_modifier(c4_stats['vitality'])
            c4_aur_mod = utils.calculate_modifier(c4_stats['aura'])
            c4_per_mod = utils.calculate_modifier(c4_stats['persona'])
            c4_max_hp = float(max(1, class_defs.CLASS_HP_DIE.get(3, class_defs.DEFAULT_HP_DIE) + c4_vit_mod))
            c4_max_ess = float(max(0, class_defs.CLASS_ESSENCE_DIE.get(3, class_defs.DEFAULT_ESSENCE_DIE) + c4_aur_mod + c4_per_mod))
            c4_tether = max(1, c4_aur_mod)

            # CHAR 5: Admin Adminson (Player 2, Elf Mage)
            c5_stats = {"might": 15, "vitality": 15, "agility": 18, "intellect": 20, "aura": 18, "persona": 18} # Slightly better stats
            c5_skills = {sk: 0 for sk in skill_defs.INITIAL_SKILLS}; c5_skills.update(class_defs.get_starting_skill_bonuses("mage"))
            c5_spells = [k for k,d in ability_defs.ABILITIES_DATA.items() if d["level_req"]==1 and d["type"]=="SPELL" and ("mage" in d["class_req"] or not d["class_req"])]
            c5_abilities = [k for k,d in ability_defs.ABILITIES_DATA.items() if d["level_req"]==1 and d["type"]=="ABILITY" and ("mage" in d["class_req"] or not d["class_req"])]
            c5_equip = {"TORSO": 2, "HEAD": 9, "NECK": 13} # Shirt, L-Cap, Locket
            c5_inv = [3, 12, 40, 16, 5] # Pouch, Heal Pot, Ess Pot, Ruby, Ring
            c5_vit_mod = utils.calculate_modifier(c5_stats['vitality'])
            c5_aur_mod = utils.calculate_modifier(c5_stats['aura'])
            c5_per_mod = utils.calculate_modifier(c5_stats['persona'])
            c5_max_hp = float(max(1, class_defs.CLASS_HP_DIE.get(2, class_defs.DEFAULT_HP_DIE) + c5_vit_mod))
            c5_max_ess = float(max(0, class_defs.CLASS_ESSENCE_DIE.get(2, class_defs.DEFAULT_ESSENCE_DIE) + c5_aur_mod + c5_per_mod))
            c5_tether = max(1, c5_aur_mod)

            # --- Create list of tuples for executemany ---
            test_characters_data = [
            # P_ID, FName, LName, Sex, R_ID, C_ID, StatsJSON, SkillsJSON, Desc, HP, MaxHP, Ess, MaxEss, Tether, InvJSON, EquipJSON, Coin, SpellsJSON, AbilitiesJSON
            (player1_id, "Testone", "Testone", "Male", 1, 1, json.dumps(c1_stats), json.dumps(c1_skills), "A sturdy Chrozalin warrior.", c1_max_hp, c1_max_hp, c1_max_ess, c1_max_ess, c1_tether, json.dumps(c1_inv), json.dumps(c1_equip), 50, json.dumps(c1_spells), json.dumps(c1_abilities)),
            (player1_id, "Elara", "Quickfoot", "Female", 3, 4, json.dumps(c2_stats), json.dumps(c2_skills), "A nimble Elven rogue.", c2_max_hp, c2_max_hp, c2_max_ess, c2_max_ess, c2_tether, json.dumps(c2_inv), json.dumps(c2_equip), 75, json.dumps(c2_spells), json.dumps(c2_abilities)),
            (player1_id, "Fimble", "Bumble", "Male", 1, 2, json.dumps(c3_stats), json.dumps(c3_skills), "A Chrozalin studying the arcane arts.", c3_max_hp, c3_max_hp, c3_max_ess, c3_max_ess, c3_tether, json.dumps(c3_inv), json.dumps(c3_equip), 100, json.dumps(c3_spells), json.dumps(c3_abilities)),
            (player1_id, "Borin", "Stonehand", "Male", 2, 3, json.dumps(c4_stats), json.dumps(c4_skills), "A devout Dwarven cleric.", c4_max_hp, c4_max_hp, c4_max_ess, c4_max_ess, c4_tether, json.dumps(c4_inv), json.dumps(c4_equip), 150, json.dumps(c4_spells), json.dumps(c4_abilities)),
            (player2_id, "Admin", "Adminson", "They/Them", 3, 2, json.dumps(c5_stats), json.dumps(c5_skills), "Looks administratively important.", c5_max_hp, c5_max_hp, c5_max_ess, c5_max_ess, c5_tether, json.dumps(c5_inv), json.dumps(c5_equip), 1000, json.dumps(c5_spells), json.dumps(c5_abilities)),
            ]

            try: # Add specific try block for characters
                # Ensure INSERT statement matches columns AND order in tuple (19 total?)
                await conn.executemany(
                    """INSERT INTO characters (player_id, first_name, last_name, sex, race_id, class_id,
                    stats, skills, description, hp, max_hp, essence, max_essence, spiritual_tether,
                    inventory, equipment, coinage, known_spells, known_abilities, location_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", # 20 placeholders needed
                    # Add TAVERN_ID to each tuple for location_id
                    [(c[0], c[1], c[2], c[3], c[4], c[5], c[6], c[7], c[8], c[9], c[10], c[11], c[12], c[13], c[14], c[15], c[16], c[17], c[18], TAVERN_ID) for c in test_characters_data]
                )
                log.info("Test characters seeded.")
            except aiosqlite.IntegrityError:
                log.debug("Test characters already exist (UNIQUE constraint ignored).")
            except Exception as e:
                log.error("Unexpected error seeding test characters: %s", e, exc_info=True)
        else:
            log.warning("Skipping test character seeding as player IDs were not found.")

        await conn.commit()
        log.info("--- Database Initialization and Seeding Complete ---")

    except aiosqlite.Error as e:
        log.error("Database initialization/seeding error: %s", e, exc_info=True)
        try: await conn.rollback()
        except Exception as rb_e: log.error("Rollback failed: %s", rb_e)


async def execute_query(
    conn: aiosqlite.Connection, query: str, params: tuple = ()
) -> int | None:
    """
    Executes a data-modifying query (INSERT, UPDATE, DELETE) asynchronously.
    Args:
        conn: An active aiosqlite.Connection object.
        query: The SQL query string.
        params: A tuple of parameters to substitute into the query.

    Returns:
        The last inserted row ID for INSERTs, or rows affected for UPDATE/DELETE.
        None if an error occurs. 0 if no rows affected.
    """
    last_id = 0
    row_count = 0
    try:
        # Execute and get cursor within context manager (auto-closes cursor)
        async with conn.execute(query, params) as cursor:
            last_id = cursor.lastrowid
            row_count = cursor.rowcount
        await conn.commit() # Commit the transaction
        return last_id if last_id else row_count
    except aiosqlite.Error as e:
        log.error("Database execute error - Query: %s Params: %s Error: %s", query, params, e, exc_info=True)
        try:
            await conn.rollback()
        except Exception as rb_e:
            log.error("Rollback failed after execute error: %s", rb_e, exc_info=True)
        return None
    # No finally block needed for cursor closing as 'with conn:' context manager handles it if used,
    # but since we pass 'conn' in, we rely on the caller or explicit close. Cursor is method-local.

async def fetch_one(
    conn: aiosqlite.Connection, query: str, params: tuple = ()
) -> aiosqlite.Row | None:
    """
    Executes a SELECT query asynchronously and fetches the first result.

    Args:
        conn: An active aiosqlite.Connection object.
        query: The SQL SELECT query string.
        params: A tuple of parameters to substitute into the query.

    Returns:
        A single aiosqlite.Row object or None if no result or error.
    """
    try:
        async with conn.execute(query, params) as cursor:
            return await cursor.fetchone()
    except aiosqlite.Error as e:
        log.error("Database fetch_one error - Query: %s Params: %s Error: %s", query, params, e, exc_info=True)
        return None

async def fetch_all(
    conn: aiosqlite.Connection, query: str, params: tuple = ()
) -> list[aiosqlite.Row] | None:
    """
    Executes a SELECT query asynchronously and fetches all results.

    Args:
        conn: An active aiosqlite.Connection object.
        query: The SQL SELECT query string.
        params: A tuple of parameters to substitute into the query.

    Returns:
        A list of aiosqlite.Row objects or None if an error occurs. Empty list if no rows found.
    """ 
    try:
        async with conn.execute(query, params) as cursor:
            return await cursor.fetchall()
    except aiosqlite.Error as e:
        log.error("Database fetch_all error - Query: %s Params: %s Error: %s", query, params, e, exc_info=True)
        return None
# --- Hashing Utility (Remains synchronous - CPU bound, okay outside event loop if complex) ---
# Consider running complex hashing in executor if it becomes blocking
def hash_password(password: str) -> str:
    """Basic password hashing using sha256. TODO: Replace with bcrypt later"""
    # For production, use bcrypt and run it in an executor:
    # import bcrypt
    # salt = bcrypt.gensalt()
    # return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def verify_password(stored_hash: str, provided_password: str) -> bool:
    """Verfies a password against a stored sha256 hash. REPLACE later."""
    # For production with bcrypt:
    # import bcrypt
    # return bcrypt.checkpw(provided_password.encode('utf-8'), stored_hash.encode('utf-8'))
    return stored_hash == hashlib.sha256(provided_password.encode('utf-8')).hexdigest()

async def load_all_areas(conn: aiosqlite.Connection) -> list[aiosqlite.Row] | None:
    """Fetches all rows from the areas table."""
    return await fetch_all(conn, "SELECT * FROM areas ORDER BY id")

async def load_all_rooms(conn: aiosqlite.Connection) -> list[aiosqlite.Row] | None:
    """Fetches all rows from the rooms table."""
    # Order by ID for consistency, though not strictly necessary
    return await fetch_all(conn, "SELECT * FROM rooms ORDER BY id")

async def load_player_account(conn: aiosqlite.Connection, username: str) -> aiosqlite.Row | None:
    """Fetches a player account by username (case-insensitive)."""
    # Use lower() for case-insensitive lookup if desired and COLLATE NOCASE isn't used on column
    # Using parameter binding is generally safer than f-string for user input
    return await fetch_one(conn, "SELECT *, is_admin FROM players WHERE lower(username) = lower(?)", (username,))

async def create_player_account(conn: aiosqlite.Connection, username: str, hashed_password: str, email: str) -> int | None:
    """Creates a new player account and returns the new player Id."""
    query = """
        INSERT INTO players (username, hashed_password, email, last_login)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP)
    """
    # execute_query returns lastrowid on successful insert
    return await execute_query(conn, query, (username, hashed_password, email))

async def load_characters_for_account(conn: aiosqlite.Connection, player_id: int) -> list[aiosqlite.Row] | None:
    """Fetches basic info (id, names, level) for all characters belonging to a player account"""
    query = """
    SELECT id, first_name, last_name, level, race_id, class_id
    FROM characters
    WHERE player_id = ?
    ORDER BY last_saved DESC, id ASC
    """
    return await fetch_all(conn, query, (player_id,))

async def load_character_data(conn: aiosqlite.Connection, character_id: int) -> aiosqlite.Row | None:
    """Fetches all data for a specific character by their ID"""
    return await fetch_one(conn, "SELECT * FROM characters WHERE id = ?", (character_id,))

async def save_character_data(conn: aiosqlite.Connection, character_id: int, data: dict) -> int | None:
    """
    Updates specified fields for a character dynamically.

    Args:
        conn: Active aiosqlite connection.
        character_id: The ID of the character to update.
        data: A dictionary where keys are column names and values are the new values.

    Returns:
        Number of rows affected (e.g., 1 on success) or None on error.
    """
    if not data:
        log.warning("save_character_data called with empty data for char %s", character_id)
        return 0 # Nothing to update

    # Build the SET part of the query dynamically
    set_clauses = []
    params = []
    # Define columns allowed for updates via this function
    valid_columns = [
        "location_id", "hp", "essence", "xp_pool", "xp_total", "level",
        "stats", "skills", "description", "sex", "race_id", "class_id",
        "max_hp", "max_essence", "inventory", "equipment", "coinage",
        "unspent_skill_points", "unspent_attribute_points", "known_spells",
        "known_abilities", "status", "stance"
    ]

    for key, value in data.items():
        if key in valid_columns:
            set_clauses.append(f"{key} = ?")
            # Handle JSON data - ensure it's passed as string
            if isinstance(value, (dict, list)):
                params.append(json.dumps(value))
            else:
                params.append(value)
        else:
            log.warning("Attempted to save invalid/protected column '%s' via save_character_data for char %s", key, character_id)

    if not set_clauses:
        log.warning("No valid columns provided to save_character_data for char %s", character_id)
        return 0

    # Always update last_saved timestamp
    set_clauses.append("last_saved = CURRENT_TIMESTAMP")

    query = f"UPDATE characters SET {', '.join(set_clauses)} WHERE id = ?"
    params.append(character_id) # Add the character ID for the WHERE clause
    params_tuple = tuple(params) # Convert list to tuple for execute

    # Keep debug logs to monitor query/params if needed, level DEBUG
    log.debug("Executing Save Character Query: %s", query)
    log.debug("Save Character Params: %s", params_tuple)

    # execute_query returns rowcount for UPDATE or None on error
    result = await execute_query(conn, query, params_tuple)

    log.debug("Save Character execute_query returned: %r", result)

    return result # Return the rowcount (or None)

async def load_all_races(conn: aiosqlite.Connection) -> list[aiosqlite.Row] | None:
    """Fetches all available races."""
    return await fetch_all(conn, "SELECT id, name, description FROM races ORDER BY id")

async def load_all_classes(conn: aiosqlite.Connection) -> list[aiosqlite.Row] | None:
    """Fetches all available classes."""
    return await fetch_all(conn, "SELECT id, name, description FROM classes ORDER BY id")

async def load_all_item_templates(conn: aiosqlite.Connection) -> list[aiosqlite.Row] | None:
    """Fetches all rows from the item_templates table."""
    return await fetch_all(conn, "SELECT * FROM item_templates ORDER BY id")

async def load_item_template(conn: aiosqlite.Connection, template_id: int) -> aiosqlite.Row | None:
    """Fetches a specific item template by its ID."""
    return await fetch_one(conn, "SELECT * FROM item_templates WHERE id = ?", (template_id,))

async def load_items_for_room(conn: aiosqlite.Connection, room_id: int) -> list[int] | None:
    """Loads a list of item template IDs present in a room."""
    query = "SELECT item_template_id FROM room_items WHERE room_id = ?"
    rows = await fetch_all(conn, query, (room_id,))
    if rows is None: # Indicates an error in fetch_all
        return None
    return [row['item_template_id'] for row in rows]

async def load_objects_for_room(conn: aiosqlite.Connection, room_id: int) -> list[aiosqlite.Row] | None:
    """Loads all object rows for a specific room."""
    query = "SELECT id, name, description, keywords FROM room_objects WHERE room_id = ?"
    return await fetch_all(conn, query, (room_id,))

async def load_coinage_for_room(conn: aiosqlite.Connection, room_id: int) -> int | None:
    """Loads the amount of coinage on the ground in a room."""
    query = "SELECT coinage FROM rooms WHERE id = ?"
    row = await fetch_one(conn, query, (room_id,))
    if row:
        return row['coinage']
    else:
        # Room doesn't exist or error fetching
        log.error("load_coinage_for_room: Could not find room or coinage for ID %d", room_id)
        return None # Return None to indicate failure

async def add_item_to_room(conn: aiosqlite.Connection, room_id: int, item_template_id: int) -> int | None:
    """Adds an item instance to the room_items table. Returns new row ID or None."""
    query = "INSERT INTO room_items (room_id, item_template_id) VALUES (?, ?)"
    # Use execute_query which returns lastrowid
    return await execute_query(conn, query, (room_id, item_template_id))

async def remove_item_from_room(conn: aiosqlite.Connection, room_id: int, item_template_id: int) -> int | None:
    """Removes ONE instance of an item template from the room_items table. Returns rowcount or None."""
    # This simple version removes only one matching item. If stacking is added, logic needs change.
    query = "DELETE FROM room_items WHERE id = (SELECT id FROM room_items WHERE room_id = ? AND item_template_id = ? LIMIT 1)"
    # Use execute_query which returns rowcount for DELETE
    return await execute_query(conn, query, (room_id, item_template_id))

async def load_mob_template(conn: aiosqlite.Connection, template_id: int) -> aiosqlite.Row | None:
    """Fetches a specific mob template by its ID."""
    return await fetch_one(conn, "SELECT * FROM mob_templates WHERE id = ?", (template_id,))

async def update_room_coinage(conn: aiosqlite.Connection, room_id: int, amount_change: int) -> int | None:
    """Adds or removes coinage from a room, ensuring it doesn't go below zero."""
    # Check current coinage first to prevent going negative? Or use max(0, ...)
    # Using max(0, ...) is simpler in one query
    query = "UPDATE rooms SET coinage = max(0, coinage + ?) WHERE id = ?"
    # Use execute_query which returns rowcount
    return await execute_query(conn, query, (amount_change, room_id))

async def create_character(
    conn: aiosqlite.Connection, player_id: int, first_name: str, last_name: str, sex: str,
    race_id: int, class_id: int, stats_json: str, skills_json: str, description: str,
    hp: float, max_hp: float, essence: float, max_essence: float,
    known_spells_json: str = '[]', known_abilities_json: str = '[]',
    location_id: int = 10, # Default Tavern
    spiritual_tether: int = 1, # Passed or calculated
    # Add params for inventory, equipment, coinage with defaults
    inventory_json: str = '[]',
    equipment_json: str = '{}',
    coinage: int = 0
) -> int | None:
    """ Creates a new character record, relying less on DB defaults. """

    # --- V V V Update Query (20 columns, 20 placeholders) V V V ---
    query = """
        INSERT INTO characters (
            player_id, first_name, last_name, sex, race_id, class_id,
            stats, skills, description, hp, max_hp, essence, max_essence,
            spiritual_tether, inventory, equipment, coinage,
            known_spells, known_abilities, location_id
            -- Status, Level, XP, Points still use DB defaults
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    # --- ^ ^ ^ ---

    # Recalculate initial tether (use aura from stats_json)
    initial_tether = 1
    try:
        stats_dict = json.loads(stats_json or '{}')
        aura = stats_dict.get("aura", 10)
        aura_mod = utils.calculate_modifier(aura)
        initial_tether = max(1, aura_mod)
    except Exception as e:
        log.error("Error calculating initial tether for new character: %s", e)
        initial_tether = 1

    # --- V V V Update Params Tuple (20 values, matching query order) V V V ---
    params = (
        player_id, first_name, last_name, sex, race_id, class_id,           # 1-6
        stats_json, skills_json, description, hp, max_hp, essence, max_essence, # 7-13
        initial_tether, inventory_json, equipment_json, coinage,             # 14-17
        known_spells_json, known_abilities_json, location_id                 # 18-20
    )
    # --- ^ ^ ^ ---

    try:
        new_char_id = await execute_query(conn, query, params)
        if new_char_id:
            log.info("Successfully created character '%s %s' with ID %s for player %s.",
                    first_name, last_name, new_char_id, player_id)
            return new_char_id
        else:
            log.error("Character creation for player %s failed, execute_query returned %s",
                    player_id, new_char_id)
            return None
    except Exception as e:
        log.exception("Exception during character creation for player %s: %s", player_id, e, exc_info=True)
        return None