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
from typing import TYPE_CHECKING, Optional, Dict, Any, List, Set, Union
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
    Initializes the database schema and populates essential lookup tables
    and a minimal starting environment. Assumes running on an empty DB file.
    """
    log.info("--- Running Database Initialization (Schema + Base Data Only) ---")
    try:
        await conn.execute("PRAGMA foreign_keys = ON;")

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
        # Room Items
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS room_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT, room_id INTEGER NOT NULL, item_template_id INTEGER NOT NULL,
                dropped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(room_id) REFERENCES rooms(id) ON DELETE CASCADE,
                FOREIGN KEY(item_template_id) REFERENCES item_templates(id) ON DELETE CASCADE )
        """)
        # Room Objects
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS room_objects (
                id INTEGER PRIMARY KEY AUTOINCREMENT, room_id INTEGER NOT NULL, name TEXT NOT NULL,
                description TEXT DEFAULT 'It looks unremarkable.', keywords TEXT NOT NULL DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(room_id) REFERENCES rooms(id) ON DELETE CASCADE,
                UNIQUE (room_id, name) )
        """)
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
                stance TEXT NOT NULL DEFAULT 'Standing', stats TEXT DEFAULT '{}', skills TEXT DEFAULT '{}',
                known_spells TEXT NOT NULL DEFAULT '[]', known_abilities TEXT NOT NULL DEFAULT '[]',
                location_id INTEGER DEFAULT 1, -- <<< Default location now Room 1
                inventory TEXT NOT NULL DEFAULT '[]', equipment TEXT NOT NULL DEFAULT '{}', coinage INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_saved TIMESTAMP,
                UNIQUE (player_id, first_name, last_name), FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
                FOREIGN KEY (location_id) REFERENCES rooms(id) ON DELETE SET DEFAULT,
                FOREIGN KEY (race_id) REFERENCES races(id) ON DELETE SET NULL, FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE SET NULL )
        """)
        await conn.commit() # Commit schema changes
        log.info("Table schema check complete.")

        # --- Phase 2: Populate Base Lookups (Races, Classes) ---
        log.info("Step 2: Populating Races and Classes...")
        default_races = [
            (1, "Chrozalin", "Versatile humans, common throughout the lands."),
            (2, "Dwarf", "Stout and hardy mountain folk, shorter than humans but broader."),
            (3, "Elf", "Graceful, long-lived forest dwellers with keen senses."),
            (4, "Yan-tar", "Ancient, wise turtle-like people known for their patience."),
            (5, "Grak", "Towering humanoids known for formidable strength and hardy builds.")
        ]
        await conn.executemany("INSERT OR IGNORE INTO races(id, name, description) VALUES(?, ?, ?)", default_races)

        default_classes = [
            (1, "Warrior", "Master of weapons and armor."),
            (2, "Mage", "Controller of arcane energies."),
            (3, "Cleric", "Channeler of divine power."),
            (4, "Rogue", "Agent of stealth and skill.")
        ]
        await conn.executemany("INSERT OR IGNORE INTO classes(id, name, description) VALUES(?, ?, ?)", default_classes)
        await conn.commit() # Commit Races/Classes
        log.info("Races & Classes populated.")

        # --- REMOVED Phase 3: Populate Item Templates ---
        # --- REMOVED Phase 4: Populate Mob Templates ---

        # --- Phase 5: Populate Minimal World Geometry ---
        log.info("Step 5: Populating Minimal World (Area 1, Room 1)...")
        default_areas = [
            (1, "The Void", "A swirling nexus outside normal reality. Builders start here.")
        ]
        try:
            await conn.executemany("INSERT OR IGNORE INTO areas (id, name, description) VALUES (?, ?, ?)", default_areas)
            await conn.commit() # Commit Area 1
            log.info("Default area created.")
        except aiosqlite.Error as e:
            log.error("Failed to populate default area: %s", e)
            raise

        default_rooms = [
            # ID, AreaID, Name, Desc, Exits JSON, Flags JSON, Spawners JSON, Coinage INT
            (1, 1, "The Void",
            "An empty, featureless void stretches endlessly around you. There is nowhere to go until you build it.",
            json.dumps({}), json.dumps(["NODE", "RESPAWN"]), '{}', 0), # Room 1 is NODE and RESPAWN point
        ]
        try:
            await conn.executemany(
                """INSERT OR IGNORE INTO rooms (id, area_id, name, description, exits, flags, spawners, coinage) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""", default_rooms
            )
            await conn.commit() # Commit Room 1
            log.info("Default starting room created.")
        except aiosqlite.Error as e:
            log.error("Failed to populate default room: %s", e)
            raise

        # --- REMOVED Phase 5b: Populate Armory ---
        # --- REMOVED Phase 5c: Populate Room Objects ---

        # --- Phase 6: Create Test Player Accounts ---
        log.info("Step 6: Creating Test Player Accounts...")
        test_players = [
            ("tester", utils.hash_password("password"), "tester@example.com", 0),
            ("admin", utils.hash_password("password"), "admin@example.com", 1),
        ]
        try:
            await conn.executemany(
                """INSERT INTO players (username, hashed_password, email, is_admin) VALUES (?, ?, ?, ?)""", test_players
            )
            await conn.commit() # Commit Players
            log.info("Test player accounts seeded.")
        except aiosqlite.IntegrityError:
            log.debug("Test player accounts already exist (UNIQUE constraint ignored).")
            # No need to commit if ignored, but commit ensures consistency if it *did* insert.
            # We can commit outside the try/except too if preferred for players/chars
            await conn.commit()
        except Exception as e:
            log.error("Unexpected error seeding test players: %s", e, exc_info=True)
            raise # Stop init if players fail critically

        # --- REMOVED Phase 7: Create Test Characters ---
        log.info("Step 7: Skipping Test Character seeding (Use creation or builder tools).")

        # Final commit to ensure everything is saved
        await conn.commit()
        log.info("--- Database Initialization and Seeding Complete (Schema + Base Data Only) ---")

    except aiosqlite.Error as e:
        log.error("Database initialization/seeding error: %s", e, exc_info=True)
        try:
            log.warning("Attempting rollback due to error...")
            await conn.rollback()
        except Exception as rb_e:
            log.error("Rollback failed: %s", rb_e)
        raise # Re-raise original error to prevent server starting with bad DB state

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
    
async def create_room(conn: aiosqlite.Connection, area_id: int, name: str, description: str = "An undescribed room.") -> Optional[int]:
    """Inserts a new room into the database and returns its ID"""
    log.debug("DB: Creating room '%s' in area %d", name, area_id)
    query = """
        INSERT INTO rooms (area_id, name, description, exits, flags, spawners, coinage)
        VALUES (?, ?, ?, '{}', '[]', '{}', 0)
        """
    # execute_query returns lastrowid on success
    new_id = await execute_query(conn, query, (area_id, name, description))
    if new_id:
        log.info("DB: Created room '%s' with ID %d in area %d", name, new_id, area_id)
    return new_id

async def update_room_basic(conn: aiosqlite.Connection, room_id: int, field: str, value: Any) -> bool:
    """Updates basic fields (name, description, area_id) for a room."""
    if field not in ["name", "description", "area_id"]:
        log.error("DB: Attempted to update invalid room field '%s'", field)
        return False
    log.debug("DB: Updating room %d, setting %s = %r", room_id, field, value)
    query = f"UPDATE rooms SET {field} = ? WHERE id = ?"
    rowcount = await execute_query(conn, query, (value, room_id))
    return rowcount is not None and rowcount > 0

async def update_room_field(conn: aiosqlite.Connection, room_id: int, field: str, value: Any) -> int | None:
    """Updates a specific field for a room. Handles JSON conversion for exits/flags/spawners."""
    # Validate field name
    valid_fields = ["name", "description", "exits", "flags", "spawners", "coinage", "area_id"]
    if field not in valid_fields:
        log.error("Attempted to update invalid room field: %s for room %d", field, room_id)
        return None

    # Prepare value - serialize if it's a dict/list/set meant for a TEXT JSON column
    param_value = value
    if field in ["exits", "flags", "spawners"]:
        try:
            # Ensure flags are saved as a list
            if field == "flags" and isinstance(value, set):
                param_value = json.dumps(sorted(list(value)))
            else: # Assume dict/list for exits/spawners
                param_value = json.dumps(value)
        except (TypeError, OverflowError) as e:
            log.error("Failed to serialize value for room %d field %s: %s", room_id, field, e)
            return None
    elif field in ["coinage", "area_id"]: # Ensure numeric types are correct
        try:
            param_value = int(value)
        except (ValueError, TypeError):
            log.error("Invalid numeric value '%s' for room %d field %s", value, room_id, field)
            return None

    query = f"UPDATE rooms SET {field} = ? WHERE id = ?"
    # execute_query returns rowcount for UPDATE
    return await execute_query(conn, query, (param_value, room_id))

async def update_room_json_field(conn: aiosqlite.Connection, room_id: int, field: str, json_data: str) -> bool:
    """Updates JSON fields (exits, flags, spawners) for a room."""
    if field not in ["exits", "flags", "spawners"]:
        log.error("DB: Attempted to update invalid room JSON field '%s'", field)
        return False
    log.debug("DB: Updating room %d, setting %s = %s", room_id, field, json_data)
    query = f"UPDATE rooms SET {field} = ? WHERE id = ?"
    rowcount = await execute_query(conn, query, (json_data, room_id))
    return rowcount is not None and rowcount > 0

async def delete_room(conn: aiosqlite.Connection, room_id: int) -> int | None:
    """Deletes a room record by its ID."""
    # Assumes safety checks (no players, mobs, items, objects, incoming exits)
    # are done *before* calling this function.
    # Foreign keys (room_items, room_objects) should CASCADE DELETE.
    # Character location_id should SET DEFAULT (to 1).
    query = "DELETE FROM rooms WHERE id = ?"
    return await execute_query(conn, query, (room_id,))

async def get_room_data(conn: aiosqlite.Connection, room_id: int) -> Optional[aiosqlite.Row]:
    """Fetches all data for a single room."""
    return await fetch_one(conn, "SELECT * FROM rooms WHERE id = ?", (room_id,))

async def get_rooms_in_area(conn: aiosqlite.Connection, area_id: int) -> Optional[List[aiosqlite.Row]]:
    """Fetches basic info (id, name) for rooms in a specific area."""
    query = "SELECT id, name FROM rooms WHERE area_id = ? ORDER BY id"
    return await fetch_all(conn, query, (area_id,))

async def get_all_rooms_basic(conn: aiosqlite.Connection) -> Optional[List[aiosqlite.Row]]:
    """Fetches basic info (id, name, area_id) for ALL rooms."""
    # Join with areas to get area name easily later? Or do lookup in command.
    query = "SELECT r.id, r.name, r.area_id, a.name as area_name FROM rooms r JOIN areas a ON r.area_id = a.id ORDER BY r.area_id, r.id"
    return await fetch_all(conn, query)

async def create_area(conn: aiosqlite.Connection, name: str, description: str = "An undescribed area.") -> int | None:
    """Creates a new area and returns its ID."""
    query = "INSERT INTO areas (name, description) VALUES (?, ?)"
    # execute_query returns lastrowid for INSERT
    new_id = await execute_query(conn, query, (name, description))
    log.info("Created Area ID %s with name '%s'", new_id, name)
    return new_id

async def update_area_field(conn: aiosqlite.Connection, area_id: int, field: str, value: str) -> int | None:
    """Updates a specific field (name or description) for an area."""
    # Validate field name to prevent SQL injection on column names
    valid_fields = ["name", "description"]
    if field not in valid_fields:
        log.error("Attempted to update invalid area field: %s", field)
        return None
    query = f"UPDATE areas SET {field} = ? WHERE id = ?"
    # execute_query returns rowcount for UPDATE
    return await execute_query(conn, query, (value, area_id))

async def get_room_count_for_area(conn: aiosqlite.Connection, area_id: int) -> int:
    """Counts how many rooms belong to a specific area."""
    query = "SELECT COUNT(*) as count FROM rooms WHERE area_id = ?"
    row = await fetch_one(conn, query, (area_id,))
    return row['count'] if row else 0

async def delete_area(conn: aiosqlite.Connection, area_id: int) -> int | None:
    """Deletes an area ONLY if it contains no rooms."""
    room_count = await get_room_count_for_area(conn, area_id)
    if room_count > 0:
        log.warning("Attempted to delete Area ID %d which contains %d rooms.", area_id, room_count)
        return -1 # Indicate error: cannot delete non-empty area

    # If room_count is 0, proceed with deletion
    query = "DELETE FROM areas WHERE id = ?"
    # execute_query returns rowcount
    return await execute_query(conn, query, (area_id,))

# Need get_area_details (similar to load_character_data)
async def load_area_data(conn: aiosqlite.Connection, area_id: int) -> aiosqlite.Row | None:
    """Fetches all data for a specific area by its ID."""
    return await fetch_one(conn, "SELECT * FROM areas WHERE id = ?", (area_id,))

async def create_item_template(conn: aiosqlite.Connection, name: str, type: str, description: str = "An ordinary item.", stats_json: str = '{}', flags_json: str = '[]', damage_type: Optional[str] = None) -> Optional[aiosqlite.Row]:
    """Creates a new item template and returns the full row data of the new item."""
    query = """
        INSERT INTO item_templates (name, description, type, stats, flags, damage_type)
        VALUES (?, ?, ?, ?, ?, ?)
    """
    params = (name, description, type.upper(), stats_json, flags_json, damage_type)
    new_id = await execute_query(conn, query, params)
    if new_id:
        log.info("Created Item Template ID %s with name '%s'", new_id, name)
        # Fetch the newly created row to return it
        return await load_item_template(conn, new_id)
    else:
        log.error("Failed to create item template with name '%s'", name)
        return None
    
async def update_item_template_field(conn: aiosqlite.Connection, template_id: int, field: str, value: Any) -> Optional[aiosqlite.Row]:
    """Updates a specific field for an item template. Handles JSON conversion. Returns updated row data."""
    valid_fields = ["name", "description", "type", "stats", "flags", "damage_type"]
    if field not in valid_fields:
        log.error("Attempted to update invalid item template field: %s for template %d", field, template_id)
        return None

    param_value = value
    if field in ["stats", "flags"]: # Fields stored as JSON TEXT
        # Ensure the provided value is a valid JSON string (basic check)
        try:
            json.loads(value) # Try parsing to validate
            param_value = value # Use the string directly
        except (json.JSONDecodeError, TypeError):
            log.error("Invalid JSON provided for item template %d field %s: %r", template_id, field, value)
            return None # Indicate failure due to bad JSON value
    elif field == "type":
        param_value = str(value).upper() # Ensure type is uppercase string

    query = f"UPDATE item_templates SET {field} = ? WHERE id = ?"
    rowcount = await execute_query(conn, query, (param_value, template_id))
    if rowcount == 1:
        log.info("Updated item template %d field '%s'", template_id, field)
        return await load_item_template(conn, template_id) # Return updated data
    else:
        log.error("Failed to update item template %d field '%s' (rowcount: %s)", template_id, field, rowcount)
        return None
    
async def copy_item_template(conn: aiosqlite.Connection, source_id: int, new_name: str) -> Optional[aiosqlite.Row]:
    """Copies an existing item template to a new one with a new name."""
    source_data = await load_item_template(conn, source_id)
    if not source_data:
        log.error("Cannot copy item template: Source ID %d not found.", source_id)
        return None

    # Create new template using data from source, but with new name
    return await create_item_template(
        conn, new_name, source_data['description'], source_data['type'],
        source_data['stats'], source_data['flags'], source_data['damage_type']
    )

async def delete_item_template(conn: aiosqlite.Connection, template_id: int) -> int | None:
    """Deletes an item template by ID. WARNING: Does not check usage!"""
    # TODO: Add checks later to see if item is in room_items, character inv/equip, loot tables
    # For now, allow deletion but log a warning.
    log.warning("ADMIN ACTION: Attempting to delete Item Template ID %d. Usage checks not implemented.", template_id)
    query = "DELETE FROM item_templates WHERE id = ?"
    return await execute_query(conn, query, (template_id,))

# Modify load_all_item_templates to allow searching
async def load_all_item_templates(conn: aiosqlite.Connection, search_term: Optional[str] = None) -> list[aiosqlite.Row] | None:
    """Fetches item templates, optionally filtering by name."""
    if search_term:
        query = "SELECT id, name, type FROM item_templates WHERE name LIKE ? ORDER BY id"
        params = (f"%{search_term}%",)
    else:
        query = "SELECT id, name, type FROM item_templates ORDER BY id"
        params = ()
    return await fetch_all(conn, query, params)