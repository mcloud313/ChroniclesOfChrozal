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
    Initializes the database schema asynchronously if tables don't exist.
    Creates areas, players, rooms, characters tables and default entries.
    Args:
        conn: An active aosqlite.Connection object.
    """
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
            xp_pool INTEGER DEFAULT 0, -- Unabsorbed XP
            xp_total INTEGER DEFAULT 0, -- XP accumulated within current level
            stats TEXT DEFAULT '{}', -- JSON: {"might": 10, "agility": 10, ...}
            skills TEXT DEFAULT '{}', -- JSON: {"climb": 0, "appraise": 0, ...}
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

        # --- Populate Default Races ---
        default_races = [
            (1, "Chrozalin", "Versatile and adaptable."),
            (2, "Dwarf", "Sturdy and resilient."),
            (3, "Elf", "Graceful and long-lived."),
            (4, "Yan-ter", "Wise and patient turtlefolk.")
        ]
        try:
            # Use INSERT OR IGNORE to avoid errors if they already exist
            await conn.executemany("INSERT OR IGNORE INTO races(id, name, description) VALUES(?, ?, ?)", default_races)
            log.info("Checked/Populated default races.")
        except aiosqlite.Error as e:
            log.error("Failed to populate default races: %s", e)

        # --- Populate Default Classes ---
        default_classes = [
            (1, "Warrior", "Master of martial combat."),
            (2, "Mage", "Wielder of arcane energies."),
            (3, "Cleric", "Agent of divine power."),
            (4, "Rogue", "Master of stealth and skill.")
        ]
        try:
            await conn.executemany("INSERT OR IGNORE INTO classes(id, name, description) VALUES(?, ?, ?)", default_classes)
            log.info("Checked/Populated default classes.")
        except aiosqlite.Error as e:
            log.error("Failed to populate default classes: %s", e)

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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                -- Add faction, behaviors etc. later
            )
            """
        )
        log.info("Checked/Created 'mob_templates' table.")
        # --- ^ ^ ^ ---

        # --- V V V Populate Default Item Templates V V V ---
        default_items = [
            (1, "a rusty dagger", "A simple dagger, pitted with rust.", "WEAPON",
            json.dumps({"wear_location": "WIELD_MAIN", "damage_base": 2, "damage_rng": 4, "speed": 1.5, "weight": 1, "value": 5}),
            json.dumps([]), "pierce"),
            (2, "a cloth shirt", "A basic shirt made of rough cloth.", "ARMOR",
            json.dumps({"wear_location": "TORSO", "armor": 1, "weight": 1, "value": 10}),
            json.dumps([]), None),
            (3, "a small pouch", "A simple leather pouch. Doesn't hold much.", "GENERAL", # Changed type from CONTAINER for V1
            json.dumps({"weight": 0, "value": 2}),
            json.dumps([]), None),
            (4, "heavy work boots", "Sturdy boots, scuffed from use.", "ARMOR",
            json.dumps({"wear_location": "FEET", "armor": 1, "speed": 0.2, "weight": 3, "value": 20}),
            json.dumps([]), None),
            (5, "an iron ring", "A plain band of iron.", "ARMOR",
            json.dumps({"wear_location": ["FINGER_L", "FINGER_R"], "armor": 0, "weight": 0, "value": 10}),
            json.dumps([]), None),
            (6, "a wooden shield", "A simple round shield made of wood.", "SHIELD", # Changed type
            json.dumps({"wear_location": "WIELD_OFF", "armor": 2, "speed": 0.5, "weight": 5, "value": 30}),
            json.dumps([]), None),
            (7, "stale bread", "Looks barely edible.", "FOOD", # Changed type from CONSUMABLE
            json.dumps({"weight": 0, "value": 1}), # Add consume effect later {effect: 'heal_hp', amount: 2} ?
            json.dumps([]), None),
        ]
        try:
            # Use INSERT OR IGNORE to avoid errors if items somehow already exist
            await conn.executemany(
                """INSERT OR IGNORE INTO item_templates
                (id, name, description, type, stats, flags, damage_type)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                default_items
            )
            log.info("Checked/Populated default item templates.")
        except aiosqlite.Error as e:
            log.error("Failed to populate default item templates: %s", e)
        # --- ^ ^ ^ End Populate Items ^ ^ ^ ---

        # --- Create Default Area and Room if they don't exist ---
        # Check for default area
        async with conn.execute("SELECT COUNT(*) FROM areas WHERE id = 1") as cursor:
            area_exists = (await cursor.fetchone())[0]
        if not area_exists:
            log.info("Default Area #1 not found, creating it.")
            await conn.execute(
                "INSERT INTO areas (id, name, description) VALUES (?, ?, ?)",
                (1, "The Genesis Area", "A placeholder area for lonely rooms.")
            )
            log.info("Default area #1 created.")

        # Check for default room
        async with conn.execute("SELECT COUNT(*) FROM rooms WHERE id = 1") as cursor:
            room_exists = (await cursor.fetchone())[0]
        if not room_exists:
            log.info("Default room #1 not found, creating it.")
            exits_room1 = json.dumps({"north": 2, "northwest": 3})
            flags_room1 = json.dumps(["NODE"]) # Mark as a node
            await conn.execute(
                """INSERT INTO rooms (id, area_id, name, description, exits, flags)
                VALUES (?, ?, ?, ?, ?, ?)""",
                (1, 1, "The Void", "A featureless void stretches around you. Something shimmers to the north. A faint path leads northwest.", exits_room1, json.dumps([]))
            )
            log.info("Default Room #1 created.")

        # *** NEW: Room 2 ("A Dusty Trail") ***
        async with conn.execute("SELECT COUNT(*) FROM rooms WHERE id = 2") as cursor:
            room2_exists = (await cursor.fetchone())[0]
        if not room2_exists:
            log.info("Default Room #2 not found, creating it.")
            exits_room2 = json.dumps({"south": 1, "hole": 4})
            # Add a spawner for mob template #1 (e.g., a rat), max 1 present
            spawners_room2 = json.dumps({ "1": {"max_present": 1} }) # Spawn Mob Template 1
            await conn.execute(
                """INSERT INTO rooms (id, area_id, name, description, exits, flags, spawners)
                VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (2, 1, "A Dusty Trail", "A dusty trail stretches before you. The void lies south. There is a dark hole in the ground here.", exits_room2, json.dumps(["outdoors"]), spawners_room2) 
            )
            log.info("Default Room #2 created with exit south.")

        # *** NEW: Room 3 ("A Windy Ridge") *** - Exits: Southeast (to R1)
        async with conn.execute("SELECT COUNT(*) FROM rooms WHERE id = 3") as cursor:
            room3_exists = (await cursor.fetchone())[0]
        if not room3_exists:
            log.info("Default Room #3 not found, creating it.")
            exits_room3 = json.dumps({"southeast": 1})
            await conn.execute(
                """INSERT INTO rooms (id, area_id, name, description, exits, flags)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                (3, 1, "A Windy Ridge", "A blustery wind whips around you on this rocky ridge. A path leads back southeast.", exits_room3, json.dumps(["outdoors", "windy"]))
            )
            log.info("Default Room #3 created.")

        # *** NEW: Room 4 ("A Damp Cave") *** - Exits: Climb Up (to R2)
        async with conn.execute("SELECT COUNT(*) FROM rooms WHERE id = 4") as cursor:
            room4_exists = (await cursor.fetchone())[0]
        if not room4_exists:
            log.info("Default Room #4 not found, creating it.")
            # --- V V V SPECIAL EXIT NAME V V V ---
            exits_room4 = json.dumps({"climb up": 2})
            await conn.execute(
                """INSERT INTO rooms (id, area_id, name, description, exits, flags)
                    VALUES (?, ?, ?, ?, ?, ?)""",
                (4, 1, "A Damp Cave", "Water drips steadily in this small, dark cave. The only way out seems to be climbing up the hole you fell through.", exits_room4, json.dumps(["indoors", "dark", "wet"]))
            )
            log.info("Default Room #4 created.")

        default_mobs = [
            (1, "a giant rat", "A rodent of unusual size, its eyes gleam.", 1,
            json.dumps({"might": 5, "vitality": 5, "agility": 8}), 8, # stats, max_hp
            json.dumps([{"name": "bite", "damage_base": 2, "damage_rng": 3, "speed": 2.5}]), # attacks
            json.dumps({"coinage_max": 3, "items": [{"template_id": 7, "chance": 0.05}]}), # loot (bread)
            json.dumps([]), 60), # flags (empty), respawn_delay
            # Add more mobs: Goblin, Wolf etc.
        ]
        try:
            await conn.executemany(
                """INSERT OR IGNORE INTO mob_templates
                (id, name, description, level, stats, max_hp, attacks, loot, flags, respawn_delay_seconds)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                default_mobs
            )
            log.info("Checked/Populated default mob templates.")
        except aiosqlite.Error as e:
            log.error("Failed to populate default mob templates: %s", e)

        await conn.commit()
        log.info("Database initialization check complete.")

    except aiosqlite.Error as e:
        log.error("Database initialization error: %s", e, exc_info=True)
        try:
            await conn.rollback()  # Rollback changes if error occurs during init
        except aiosqlite.Error as rb_e:
            log.error("Rollback failed: %s", rb_e, exc_info=True)

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
        "max_hp", "max_essence", "inventory", "equipment", "coinage"
        # Add others as needed, remove ones that shouldn't be updated here
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
    conn: aiosqlite.Connection,
    player_id: int,
    first_name: str,
    last_name: str,
    sex: str,
    race_id: int, 
    class_id: int,
    stats_json: str, 
    skills_json: str,
    description: str,
    hp: int, 
    max_hp: int,
    essence: int,
    max_essence: int,
    location_id: int = 1 # Default location
) -> int | None:
    """
    Creates a new character record in the database.

    Args:
        conn: Active aiosqlite connection.
        player_id: ID of the owning player account.
        first_name: Character's first name.
        last_name: Character's last name.
        sex: Character's chosen sex ('Male', 'Female', 'They/Them', etc.)
        race_id: ID of the character's race.
        class_id: ID of the character's class.
        stats_json: JSON string representing base stats.
        skills_json: JSON string representing initial skills.
        description: Generated character description string.
        hp: Initial HP value.
        max_hp: Initial Max HP value.
        essence: Initial Essence value.
        max_essence: Initial Max Essence value.
        location_id: Starting location ID (defaults to 1).

    Returns:
        The dbid of the newly created character, or None on error.
    """
    query = """
        INSERT INTO characters (
        player_id, first_name, last_name, sex, race_id, class_id,
        stats, skills, description, hp, max_hp, essence, max_essence,
        location_id
        -- level, xp_pool, xp_total use DB defaults
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        player_id, first_name, last_name, sex, race_id, class_id,
        stats_json, skills_json, description, hp, max_hp, essence, max_essence,
        location_id
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
