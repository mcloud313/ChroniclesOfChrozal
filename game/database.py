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
# Set default logging level if not configured elsewhere
if not log.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )

# Define some constants for key room IDs for easier linking
TAVERN_ID = 10
MARKET_ID = 11
DOCKS_ID = 12
TOWNHALL_ID = 13
GATEHOUSE_ID = 14
GRAVEYARD_ID = 15
GRAVEYARD_PATH_ID = 16
WEST_STREET_ID = 17
ARMORY_ID = 18
BEACH_ENTRANCE_ID = 25
BEACH_START_ID = 100

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
    Initializes the database schema AND populates it with default + test data.
    Assumes it's potentially running on an empty DB file.
    Args:
        conn: An active aosqlite.Connection object.
    """
    log.info("--- Running Database Initialization and Seeding ---")
    # --- Phase 1: Schema Creation ---
    try:
        # --- Create areas table ---
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS areas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT DEFAULT 'An undescribed area.',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """
        )
        log.info("Checked/Created 'areas' table.")

        # Create  players (accounts) table
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                hashed_password TEXT NOT NULL,
                email TEXT NOT NULL,
                is_admin BOOLEAN NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP
            )
        """
        )
        log.info("Checked/Created 'players' table.")

        # Create rooms table
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                area_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT 'You see nothing special.',
                exits TEXT DEFAULT '{}', -- Storing exits as JSON text
                flags TEXT DEFAULT '[]', -- JSON text for set of flags
                spawners TEXT DEFAULT '{}', -- JSON like {"1": {"max_present": 3}} MobTemplateID: {details}
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE RESTRICT -- Prevent deleting area if rooms exist
            )
        """
        )
        log.info("Checked/Created 'rooms' table with spawners!")

        # --- Create races table ---
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS races (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT DEFAULT 'An undescribed race.'
            -- TODO: Add base stat modifiers, abilities etc later
            )
            """
        )
        log.info("Checked/Created 'races' table.")

        # --- Create classes table ---
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS classes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT DEFAULT 'An undescribed class'
            -- Add skill bonsuses, abilities etc. later
            )
            """
        )
        log.info("Checked/Created 'classes' table.")

        # --- Create items tamplate
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS item_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL,
            description TEXT DEFAULT 'An ordinary item.',
            type TEXT NOT NULL, -- WEAPON, ARMOR, CONTAINER, CONSUMABLE, GENERAL, TREASURE, KEY, etc.
            stats TEXT DEFAULT '{}', -- JSON: {wear_location: str|list, damage_base: int, damage_rng: int, armor: int, speed: float, weight: int, value: int}
            flags TEXT DEFAULT '[]', -- JSON List: ["MAGICAL", "NODROP", "ROOM-OBJECT"]
            damage_type TEXT, -- slash, pierce, bludgeon, fire, cold, etc. NULLable
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        log.info("Checked/Created items_templates table.")

        # --- Create mob_templates table ---
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS mob_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
                description TEXT DEFAULT 'A creature.',
                level INTEGER NOT NULL DEFAULT 1,
                stats TEXT DEFAULT '{}', -- JSON: {might: 10, vit: 10, agi: 10...}
                max_hp INTEGER NOT NULL DEFAULT 10,
                attacks TEXT DEFAULT '[]', -- JSON: [{"name": "hit", "damage_base": 1, "damage_rng": 1, "speed": 2.0}]
                loot TEXT DEFAULT '{}', -- JSON: {"coinage_max": 5, "items": [{"template_id": 7, "chance": 0.1}]}
                flags TEXT DEFAULT '[]', -- JSON: ["AGGRESSIVE", "STATIONARY"]
                respawn_delay_seconds INTEGER DEFAULT 300, -- Time to respawn after death
                variance TEXT DEFAULT '{}', -- << ADDED JSON: {"max_hp_pct": 10, "stats_pct": 5}
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                -- Add faction, behaviors etc. later
            )
            """
        )
        log.info("Checked/Created 'mob_templates' table.")

        # --- Create characters table ---
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            sex TEXT NOT NULL,
            race_id INTEGER,
            class_id INTEGER,
            level INTEGER DEFAULT 1,
            description TEXT DEFAULT '',
            hp INTEGER DEFAULT 50,
            max_hp INTEGER DEFAULT 50,
            essence INTEGER DEFAULT 20,
            max_essence INTEGER DEFAULT 20,
            spiritual_tether INTEGER,
            xp_pool INTEGER DEFAULT 0, -- Unabsorbed XP
            xp_total INTEGER DEFAULT 0, -- XP accumulated within current level
            unspent_skill_points INTEGER NOT NULL DEFAULT 0,
            unspent_attribute_points INTEGER NOT NULL DEFAULT 0,
            stats TEXT DEFAULT '{}', -- JSON: {"might": 10, "agility": 10, ...}
            skills TEXT DEFAULT '{}', -- JSON: {"climb": 0, "appraise": 0, ...}
            known_spells TEXT NOT NULL DEFAULT '[]',
            known_abilities TEXT NOT NULL DEFAULT '[]',
            location_id INTEGER DEFAULT 1, -- Default starting room ID
            inventory TEXT NOT NULL DEFAULT '[]', -- JSON List of item_template_ids
            equipment TEXT NOT NULL DEFAULT '{}',     -- JSON Dict {slot: item_template_id}
            coinage INTEGER NOT NULL DEFAULT 0,   -- Total lowest denomination (Talons)
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_saved TIMESTAMP,
            UNIQUE (player_id, first_name, last_name), -- Character names unique per player account
            FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE, -- Delete characters if player account is deleted
            FOREIGN KEY (location_id) REFERENCES rooms(id) ON DELETE SET DEFAULT, -- If room deleted, move char to default room 1
            FOREIGN KEY (race_id) REFERENCES races(id) ON DELETE SET NULL, -- If race deleted, set char race to NULL
            FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE SET NULL -- If class deleted, set char class to NULL
            )
            """
        )
        log.info("Checked/Created 'characters' table.")

        # --- Phase 2: Populate Base Lookups (Races, Classes) ---
        log.info("Step 2: Populating Races and Classes...")
        default_races = [ # Use 'Chrozalin' now based on feedback
            (1, "Chrozalin", "Versatile humans, common throughout the lands."),
            (2, "Dwarf", "Stout and hardy mountain folk."),
            (3, "Elf", "Graceful, long-lived forest dwellers."),
            (4, "Yan-tar", "Ancient, wise turtle-like people.")
        ]
        try:
            # Use INSERT OR IGNORE to avoid errors if they already exist
            await conn.executemany("INSERT OR IGNORE INTO races(id, name, description) VALUES(?, ?, ?)", default_races)
            log.info("Checked/Populated default races.")
        except aiosqlite.Error as e:
            log.error("Failed to populate default races: %s", e)

        # --- Populate Default Classes ---
        default_classes = [
            (1, "Warrior", "Master of weapons and armor."),
            (2, "Mage", "Controller of arcane energies."),
            (3, "Cleric", "Channeler of divine power."),
            (4, "Rogue", "Agent of stealth and skill.")
        ]
        try:
            await conn.executemany("INSERT OR IGNORE INTO classes(id, name, description) VALUES(?, ?, ?)", default_classes)
            log.info("Checked/Populated default classes.")
        except aiosqlite.Error as e:
            log.error("Failed to populate default classes: %s", e)

        # --- Phase 3: Populate Item Templates ---
        log.info("Step 3: Populating Item Templates...")
        default_items = [
            (1, "a rusty dagger", "Simple, pitted.", "WEAPON", json.dumps({"wear_location": "WIELD_MAIN", "damage_base": 2, "damage_rng": 4, "speed": 1.5, "weight": 1, "value": 5}), json.dumps([]), "pierce"),
            (2, "a cloth shirt", "Basic protection.", "ARMOR", json.dumps({"wear_location": "TORSO", "armor": 1, "weight": 1, "value": 10}), json.dumps([]), None),
            (3, "a small pouch", "Holds small items.", "GENERAL", json.dumps({"weight": 0, "value": 2}), json.dumps([]), None), # Type GENERAL now
            (4, "heavy work boots", "Scuffed but sturdy.", "ARMOR", json.dumps({"wear_location": "FEET", "armor": 1, "speed": 0.2, "weight": 3, "value": 20}), json.dumps([]), None),
            (5, "an iron ring", "A plain band.", "ARMOR", json.dumps({"wear_location": ["FINGER_L", "FINGER_R"], "armor": 0, "weight": 0, "value": 10}), json.dumps([]), None),
            (6, "a wooden shield", "Offers basic defense.", "SHIELD", json.dumps({"wear_location": "WIELD_OFF", "armor": 2, "block_chance": 0.1, "speed": 0.5, "weight": 5, "value": 30}), json.dumps([]), None), # Added block_chance
            (7, "stale bread", "Looks barely edible.", "FOOD", json.dumps({"weight": 0, "value": 1}), json.dumps([]), None),
            (8, "cloth trousers", "Simple leg coverings.", "ARMOR", json.dumps({"wear_location": "LEGS", "armor": 1, "weight": 1, "value": 10}), json.dumps([]), None),
            (9, "a leather cap", "Minimal head protection.", "ARMOR", json.dumps({"wear_location": "HEAD", "armor": 1, "weight": 1, "value": 15}), json.dumps([]), None),
            (10, "a short sword", "A standard sidearm.", "WEAPON", json.dumps({"wear_location": "WIELD_MAIN", "damage_base": 3, "damage_rng": 6, "speed": 2.0, "weight": 3, "value": 25}), json.dumps([]), "slash"),
            (11, "leather gloves", "Protects the hands.", "ARMOR", json.dumps({"wear_location": "HANDS", "armor": 1, "weight": 0, "value": 12}), json.dumps([]), None),
            (12, "a healing salve", "A soothing, minty balm.", "CONSUMABLE", json.dumps({"weight": 0, "value": 25, "effect": "heal_hp", "amount": 20}), json.dumps([]), None), # Example potion
            (13, "a silver locket", "A simple silver locket.", "ARMOR", json.dumps({"wear_location": "NECK", "armor": 0, "weight": 0, "value": 50}), json.dumps([]), None),
            (14, "a sturdy backpack", "Can hold many things.", "GENERAL", json.dumps({"weight": 2, "value": 30}), json.dumps(["CONTAINER"]), None), # Example container flag
            (15, "a waterskin", "Holds water.", "DRINK", json.dumps({"weight": 1, "value": 5, "effect": "quench_thirst"}), json.dumps([]), None), # Example drink
            (16, "a ruby gemstone", "A glittering red gem.", "TREASURE", json.dumps({"weight": 0, "value": 100}), json.dumps([]), None), # Example treasure
            # Add 10-15 more varied items...
        ]
        try:
            # Use INSERT OR IGNORE to avoid errors if items somehow already exist
            await conn.executemany(
                """INSERT OR IGNORE INTO item_templates
                (id, name, description, type, stats, flags, damage_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                default_items
            )
            log.info("Item Templates populated.")
        except aiosqlite.Error as e:
            log.error("Failed to populate default item templates: %s", e)

        # --- Phase 4: Populate Mob Templates ---
        log.info("Step 4: Populating Mob Templates...")
        # Add templates for Crab, Sprite, Turtle, King Turtle for the beach
        default_mobs = [
            # ID 1: Giant Rat
            (1, "a giant rat", "A rodent of unusual size, its eyes gleam.", 1,
            json.dumps({"might": 5, "vitality": 5, "agility": 8}), 8, # stats, max_hp
            json.dumps([{"name": "bite", "damage_base": 3, "damage_rng": 3, "speed": 2.5}]), # attacks (kept buffed version)
            json.dumps({"coinage_max": 3, "items": [{"template_id": 7, "chance": 0.05}]}), # loot (bread)
            json.dumps([]), 60, # flags, respawn_delay
            json.dumps({"max_hp_pct": 20, "stats_pct": 10})), # <<< Added Variance
            # ID 2: Giant Crab
            (2, "a giant crab", "Its claws click menacingly.", 2,
            json.dumps({"might": 8, "vitality": 10, "agility": 6}), 15, # stats, max_hp
            # --- Reduced Damage ---
            json.dumps([{"name": "pinch", "damage_base": 1, "damage_rng": 4, "speed": 3.0}]), # Changed base 2->1, rng 5->4
            json.dumps({"coinage_max": 5, "items": []}), # loot
            json.dumps(["AGGRESSIVE"]), 90, # flags, respawn_delay
            json.dumps({"max_hp_pct": 15, "stats_pct": 10})), # <<< Added Variance
            # ID 3: Sea Sprite
            (3, "a mischievous sea sprite", "It flits around, trailing seawater.", 3,
            json.dumps({"might": 4, "vitality": 6, "agility": 12, "intellect": 10}), 12, # stats, max_hp
            json.dumps([{"name": "water jet", "damage_base": 1, "damage_rng": 4, "speed": 2.0, "damage_type": "cold"}]), # attacks
            json.dumps({"coinage_max": 8, "items": [{"template_id": 16, "chance": 0.02}]}), # loot (ruby)
            json.dumps(["AGGRESSIVE"]), 120, # flags, respawn_delay
            json.dumps({"max_hp_pct": 10, "stats_pct": 15})), # <<< Added Variance
            # ID 4: Giant Snapping Turtle
            (4, "a giant snapping turtle", "Its beak looks powerful enough to snap bone.", 4,
            json.dumps({"might": 10, "vitality": 14, "agility": 4}), 25, # stats, max_hp
            json.dumps([{"name": "snap", "damage_base": 4, "damage_rng": 6, "speed": 4.0}]), # attacks
            json.dumps({"coinage_max": 15, "items": []}), # loot
            json.dumps(["AGGRESSIVE"]), 180, # flags, respawn_delay
            json.dumps({"max_hp_pct": 10, "stats_pct": 5})), # <<< Added Variance
            # ID 5: King Snapping Turtle
            (5, "a HUGE king snapping turtle", "Ancient and immense, barnacles coat its shell.", 6,
            json.dumps({"might": 15, "vitality": 20, "agility": 3}), 50, # stats, max_hp
            json.dumps([{"name": "CRUSHING bite", "damage_base": 6, "damage_rng": 8, "speed": 5.0}]), # attacks
            json.dumps({"coinage_max": 50, "items": [{"template_id": 6, "chance": 0.1}]}), # loot (shield)
            json.dumps(["AGGRESSIVE"]), 600, # flags, respawn_delay
            json.dumps({"max_hp_pct": 10, "stats_pct": 5})), # <<< Added Variance
        ]
        await conn.executemany(
            """INSERT OR IGNORE INTO mob_templates (id, name, description, level, stats, max_hp, attacks, loot, flags, respawn_delay_seconds, variance) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", default_mobs
        )
        log.info("Mob Templates populated.")

        # --- Phase 5: Populate World Geometry (Areas, Rooms) ---

        # --- Create Default Area and Room if they don't exist ---
        default_areas = [
            (1, "The Genesis Area", "Void and testing grounds."),
            (2, "Seaside Town of Haven", "A bustling port town."),
            (3, "Sandy Beach", "The coastline near Haven.")
        ]
        await conn.executemany("INSERT OR IGNORE INTO areas (id, name, description) VALUES (?, ?, ?)", default_areas)

        # Define Rooms (ID, AreaID, Name, Desc, Exits JSON, Flags JSON, Spawners JSON)
        default_rooms = default_rooms = [
            # --- Genesis Area (Area 1) ---
            (1, 1, "The Void",
            "A featureless void stretches around you. To the north, something shimmers slightly.",
            json.dumps({"north": TAVERN_ID}), # Simple Exit
            json.dumps(["NODE"]),
            '{}'),

            # --- Seaside Town of Haven (Area 2) ---
            (TAVERN_ID, 2, "The Salty Siren Tavern",
            "The air smells of stale ale, sweat, and the sea. A bar stretches along one wall. Exits lead south (to the void) and east (to West Street).",
            json.dumps({"south": 1, "east": WEST_STREET_ID}), # Simple Exits
            json.dumps(["NODE", "INDOORS"]),
            '{}'),
            (MARKET_ID, 2, "Haven Market Square",
            "A bustling square with stalls (inactive). Streets lead west (West Street), north (Town Hall), south (Gatehouse), east (Armory), and southeast (Path to Beach).",
            json.dumps({"west": WEST_STREET_ID, "north": TOWNHALL_ID, "south": GATEHOUSE_ID, "east": ARMORY_ID, "southeast": BEACH_ENTRANCE_ID}), # Simple Exits
            json.dumps(["OUTDOORS"]),
            '{}'),
            (DOCKS_ID, 2, "Haven Docks",
            "The smell of salt and fish is strong here. Piers stretch out over the water. A path leads east.",
            json.dumps({"east": WEST_STREET_ID}), # Simple Exit
            json.dumps(["OUTDOORS", "WET"]),
            '{}'),
            (TOWNHALL_ID, 2, "Town Hall Entrance",
            "A sturdy wooden building. Market Square is south.",
            json.dumps({"south": MARKET_ID}), # Simple Exit
            json.dumps(["OUTDOORS"]),
            '{}'),
            (GATEHOUSE_ID, 2, "South Gatehouse",
            "Guards stand watch. Market Square is north. The South Gate isn't functional yet.",
            json.dumps({"north": MARKET_ID}), # Simple Exit
            json.dumps(["OUTDOORS"]),
            '{}'),
            (GRAVEYARD_ID, 2, "Haven Graveyard",
            "An eerie, quiet space filled with weathered headstones. A rusty gate leads east.",
            json.dumps({"east": GRAVEYARD_PATH_ID}), # Simple Exit
            json.dumps(["OUTDOORS"]), # Respawn point
            '{}'),
            (GRAVEYARD_PATH_ID, 2, "Graveyard Path",
            "A path between the graveyard (west) and West Street (east).",
            json.dumps({"west": GRAVEYARD_ID, "east": WEST_STREET_ID}), # Simple Exits
            json.dumps(["OUTDOORS"]),
            '{}'),
            (WEST_STREET_ID, 2, "West Street",
            "Connects the Docks (west), the Graveyard path (north), the Market Square (east), and the Tavern (south).",
            json.dumps({"west": DOCKS_ID, "north": GRAVEYARD_PATH_ID, "east": MARKET_ID, "south": TAVERN_ID}), # Simple Exits
            json.dumps(["OUTDOORS"]),
            '{}'),
            (ARMORY_ID, 2, "Haven Armory",
            "Racks of basic gear line the walls. Market Square is west.",
            json.dumps({"west": MARKET_ID}), # Simple Exit
            json.dumps(["INDOORS"]),
            '{}'),
            (BEACH_ENTRANCE_ID, 2, "Path to the Beach",
            "A sandy path leads down towards the sounds of the surf to the east. Market square lies northwest.", # Updated description slightly
            json.dumps({"northwest": MARKET_ID, "east": BEACH_START_ID}), # Simple Exits
            json.dumps(["OUTDOORS"]),
            '{}'),

            # --- Beach Area (Area 3) ---
            (BEACH_START_ID, 3, "Sandy Shore",
            "Waves lap gently at the sand. The path back towards town is northwest. The beach stretches north and south.",
            json.dumps({"northwest": BEACH_ENTRANCE_ID, "north": 101, "south": 102}), # Simple Exits
            json.dumps(["OUTDOORS", "WET"]),
            json.dumps({"2": {"max_present": 2}})), # Spawns Crabs (Mob ID 2)
            (101, 3, "North Beach",
            "More sand and dunes. The shore continues north and south.",
            json.dumps({"north": 103, "south": BEACH_START_ID}), # Simple Exits
            json.dumps(["OUTDOORS", "WET"]),
            json.dumps({"2": {"max_present": 1}, "3": {"max_present": 1}})), # Crab, Sprite
            (102, 3, "South Beach",
            "Tide pools dot the sand here. The shore continues north and south. A dark hole gapes in the sand.",
            # Exit 'hole' requires skill check
            json.dumps({
                "north": BEACH_START_ID,
                "south": 104,
                "hole": { # <<< Complex Exit Definition Start
                    "target": 4,
                    "skill_check": {
                        "skill": "acrobatics",
                        "dc": 12,
                        "fail_damage": 2,
                        "fail_msg": "You tumble awkwardly into the hole!",
                        "success_msg": "You carefully descend into the hole."
                    }
                } # <<< Complex Exit Definition End
            }),
            json.dumps(["OUTDOORS", "WET"]),
            json.dumps({"2": {"max_present": 2}, "4": {"max_present": 1}})), # Crabs, Turtle
            (103, 3, "Rocky Outcropping (N)",
            "Sharp rocks jut out into the sea. The beach is south, and climbs further north.",
            json.dumps({"south": 101, "north": 105}), # Simple Exits
            json.dumps(["OUTDOORS", "ROUGH_TERRAIN"]),
            json.dumps({"3": {"max_present": 2}})), # Sprites
            (104, 3, "Turtle Nesting Ground (S)",
            "Depressions in the sand mark turtle nests. The beach is north. Sandy dunes lie south.",
            json.dumps({"north": 102, "south": 108}), # Simple Exits
            json.dumps(["OUTDOORS", "WET"]),
            json.dumps({"4": {"max_present": 2}, "5": {"max_present": 1}})), # Turtles + King Turtle
            (4, 1, "A Damp Cave", # <--- Note: Back in Area 1 (Genesis) for this example room ID
            "Water drips steadily in this small, dark cave. The only way out seems to be climbing up the hole you fell through.",
            # Exit 'climb up' requires skill check
            json.dumps({
                "climb up": { # <<< Complex Exit Definition Start
                    "target": 102, # Target is South Beach
                    "skill_check": {
                        "skill": "climbing",
                        "dc": 12,
                        "fail_damage": 3,
                        "fail_msg": "You slip while climbing and fall back down!",
                        "success_msg": "You manage to climb up out of the hole."
                    }
                } # <<< Complex Exit Definition End
            }),
            json.dumps(["INDOORS", "DARK", "WET"]),
            '{}'), # No spawners here initially
            (105, 3, "Northern Cliffs Base",
            "Steep cliffs rise to the north, slick with spray. The rocky beach continues south.",
            # Exit 'climb cliff' requires skill check
            json.dumps({
                "south": 103,
                "climb cliff": { # <<< Complex Exit Definition Start
                    "target": 106,
                    "skill_check": {
                        "skill": "climbing",
                        "dc": 15, # Harder climb
                        "fail_damage": 5,
                        "fail_msg": "The slick rocks offer no purchase and you tumble down!",
                        "success_msg": "You find handholds and scale the lower cliff face."
                    }
                } # <<< Complex Exit Definition End
            }),
            json.dumps(["OUTDOORS", "ROUGH_TERRAIN", "WET"]),
            json.dumps({"3": {"max_present": 2}})), # Sprites
            (106, 3, "Northern Cliff Ledge",
            "A narrow ledge partway up the cliff face. A small cave mouth leads inward. You can try to climb down.",
            # Exit 'climb down' requires skill check
            json.dumps({
                "in": 107,
                "climb down": { # <<< Complex Exit Definition Start
                    "target": 105,
                    "skill_check": {
                        "skill": "climbing",
                        "dc": 10, # Easier going down
                        "fail_damage": 2,
                        "fail_msg": "You slip near the bottom and land hard!",
                        "success_msg": "You carefully climb back down to the base."
                    }
                } # <<< Complex Exit Definition End
            }),
            json.dumps(["OUTDOORS", "WINDY"]),
            '{}'),
            (107, 3, "Small Sea Cave",
            "A cramped, damp cave smelling of brine and guano. The only exit is out.",
            json.dumps({"out": 106}), # Simple Exit
            json.dumps(["INDOORS", "DARK", "WET"]),
            json.dumps({"2": {"max_present": 1}})), # Crab
            (108, 3, "Sandy Dunes",
            "Rolling dunes block view further south. The nesting ground is north.",
            json.dumps({"north": 104, "south": 109}), # Simple Exits
            json.dumps(["OUTDOORS"]),
            json.dumps({"2": {"max_present": 3}})), # Crabs
            (109, 3, "Shipwreck Debris",
            "The shattered remnants of a small ship lie half-buried in the sand. The dunes are north.",
            json.dumps({"north": 108}), # Simple Exit
            json.dumps(["OUTDOORS", "WET"]),
            json.dumps({"4": {"max_present": 1}})), # Turtle
        ]
        await conn.executemany(
            """INSERT OR IGNORE INTO rooms (id, area_id, name, description, exits, flags, spawners) VALUES (?, ?, ?, ?, ?, ?, ?)""", default_rooms
        )
        log.info("Areas & Rooms populated.")

        # --- Phase 6: Create Test Player Accounts ---
        log.info("Step 6: Creating Test Player Accounts...")
        test_players = [
            ("tester", utils.hash_password("password"), "tester@example.com", 0), # Normal user
            ("admin", utils.hash_password("password"), "admin@example.com", 1), # Admin user
        ]
        # Use direct INSERT assuming clean DB for test accounts
        await conn.executemany(
            """INSERT INTO players (username, hashed_password, email, is_admin) VALUES (?, ?, ?, ?)""", test_players
        )
        log.info("Test player accounts created.")

        # --- Phase 7: Create Test Characters ---
        log.info("Step 7: Creating Test Characters...")
        # Get IDs - assume 1 & 2 if DB was clean
        async with conn.execute("SELECT id FROM players WHERE username='tester'") as cursor:
            player1_id = (await cursor.fetchone())[0]
        async with conn.execute("SELECT id FROM players WHERE username='admin'") as cursor:
            player2_id = (await cursor.fetchone())[0]

        # Character 1: Testone Testone (Chrozalin Warrior)
        char1_stats = {"might": 16, "vitality": 14, "agility": 12, "intellect": 10, "aura": 8, "persona": 8}
        char1_skills = {"bladed weapons": 10, "shield usage": 10, "armor training": 20}
        char1_equip = {"WIELD_MAIN": 1, "TORSO": 2, "FEET": 4} # Dagger, Shirt, Boots
        char1_inv = [3, 7, 16] # Pouch, Bread, Ruby
        char1_aura_mod = utils.calculate_modifier(char1_stats['aura'])
        char1_tether = max(1, char1_aura_mod) # Level 1

        # Character 2: Admin Ad Minson (Elf Mage)
        char2_stats = {"might": 12, "vitality": 14, "agility": 16, "intellect": 18, "aura": 15, "persona": 15}
        char2_skills = {"spellcraft": 5, "magical devices": 3}
        char2_equip = {"HEAD": 9} # Leather Cap
        char2_inv = [12, 5] # Healing Salve, Iron Ring
        char2_aura_mod = utils.calculate_modifier(char2_stats['aura'])
        char2_tether = max(1, char2_aura_mod) # Level 1

        test_characters = [
            (player1_id, "Testone", "Testone", "Male", 1, 1, json.dumps(char1_stats), json.dumps(char1_skills), "A generic Chrozalin.", 18, 18, 5, 5, char1_tether, json.dumps(char1_inv), json.dumps(char1_equip), 50), # P1, F, L, Sex, R_ID, C_ID, Stats, Skills, Desc, HP, MaxHP, Ess, MaxEss, Tether, Inv, Equip, Coinage
            (player2_id, "Admin", "Adminson", "They/Them", 3, 2, json.dumps(char2_stats), json.dumps(char2_skills), "Looks administratively important.", 10, 10, 15, 15, char2_tether, json.dumps(char2_inv), json.dumps(char2_equip), 1000), # P2, F, L, Sex, R_ID, C_ID, Stats, Skills, Desc, HP, MaxHP, Ess, MaxEss, Tether, Inv, Equip, Coinage
        ]
        # Use direct INSERT, assumes clean DB & create_character logic verified elsewhere
        # Need to calculate HP/MaxHP etc based on Character logic before insert? Yes.
        # Let's manually calc for seed:
        # Char1: War(10)+VitMod(3)=13 HP? User has 18/18. Aura(2)+Pers(2)=4 Ess? User has 5/5. Needs recalc based on formula/class base.
        # Char2: Mage(4)+VitMod(2)=6 HP? User has 10/10. Aura(3)+Pers(3)=6 Ess? User has 15/15.
        # Okay, need to calc HP/Ess based on the stats assigned here and class bases.
        # Recalc based on ClassHP + VitMod, ClassEssDieMax + AuraMod + PersMod
        # Char1 (War): HP = 10 + utils.calculate_modifier(16) = 10 + 3 = 13. Ess = 4 + utils.calculate_modifier(10) + utils.calculate_modifier(12) = 4 + 2 + 2 = 8? No, Class Base Essence is 0 for War -> Ess = 0 + 2 + 2 = 4.
        # Char2 (Mage): HP = 4 + utils.calculate_modifier(14) = 4 + 2 = 6. Ess = 10 + utils.calculate_modifier(15) + utils.calculate_modifier(15) = 10 + 3 + 3 = 16.
        # Update test_characters data with these calculated values:
        test_characters = [
            (player1_id, "Testone", "Testone", "Male", 1, 1, json.dumps(char1_stats), json.dumps(char1_skills), "A generic Chrozalin.", 13, 13, 4, 4, char1_tether, json.dumps(char1_inv), json.dumps(char1_equip), 50),
            (player2_id, "Admin", "Adminson", "They/Them", 3, 2, json.dumps(char2_stats), json.dumps(char2_skills), "Looks important.", 6, 6, 16, 16, char2_tether, json.dumps(char2_inv), json.dumps(char2_equip), 1000),
        ]
        await conn.executemany(
            """INSERT INTO characters (player_id, first_name, last_name, sex, race_id, class_id, stats, skills, description, hp, max_hp, essence, max_essence, spiritual_tether, inventory, equipment, coinage, location_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""", # Added location_id default override (Tavern)
            [(c[0], c[1], c[2], c[3], c[4], c[5], c[6], c[7], c[8], c[9], c[10], c[11], c[12], c[13], c[14], c[15], c[16], TAVERN_ID) for c in test_characters] # Start in Tavern
        )
        log.info("Test characters created.")

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
        "known_abilities"
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

async def load_mob_template(conn: aiosqlite.Connection, template_id: int) -> aiosqlite.Row | None:
    """Fetches a specific mob template by its ID."""
    return await fetch_one(conn, "SELECT * FROM mob_templates WHERE id = ?", (template_id,))

async def create_character(
    conn: aiosqlite.Connection, player_id: int, first_name: str, last_name: str, sex: str,
    race_id: int, class_id: int, stats_json: str, skills_json: str, description: str,
    hp: int, max_hp: int, essence: int, max_essence: int, known_spells_json: str = '[]',
    known_abilities_json: str = '[]', location_id: int = 1, spiritual_tether: int = 1
) -> int | None:
    """ Creates a new character record, calculating initial spiritual tether. """
    query = """
        INSERT INTO characters (
            player_id, first_name, last_name, sex, race_id, class_id,
            stats, skills, description, hp, max_hp, essence, max_essence,
            known_spells, known_abilities, location_id, spiritual_tether,
            -- level, xp_pool, xp_total use DB defaults (1, 0, 0)
            -- points use DB defaults (0, 0) - awarded after creation by handler
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    # --- Calculate initial tether ---
    initial_tether = 1 # Default minimum
    try:
        stats_dict = json.loads(stats_json or '{}')
        aura = stats_dict.get("aura", 10)
        aura_mod = utils.calculate_modifier(aura)
        # Level is 1 initially, floor(1/4) = 0
        initial_tether = max(1, aura_mod + math.floor(1 / 4))
        initial_tether = max(1, aura_mod) 
    except Exception as e:
        log.error("Error calculating initial tether for new character: %s", e)
        initial_tether = 1 # Fallback to minimum

    params = (
        player_id, first_name, last_name, sex, race_id, class_id,
        stats_json, skills_json, description, hp, max_hp, essence, max_essence,
        location_id, spiritual_tether, known_spells_json, known_abilities_json
    )

    try:
        # Use execute_query which returns lastrowid on success
        new_char_id = await execute_query(conn, query, params)
        if new_char_id:
            log.info("Successfully created character '%s %s' with ID %s for player %s.",
            first_name, last_name, new_char_id, player_id)
            return new_char_id
        else:
            # This might happen if execute_query returns 0 or None unexpectedly
            log.error("Character creation for player %s failed, execute_query returned %s",
            player_id, new_char_id)
            return None
        
    except Exception as e:
        # Catch potential errors during creation (like UNIQUE constraint violation maybe?)
        log.exception("Exception during character creation for player %s: %s", player_id, e, exc_info=True)
        return None
