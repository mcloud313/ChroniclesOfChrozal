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
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE RESTRICT -- Prevent deleting area if rooms exist
            )
        """
        )
        log.info("Checked/Created 'rooms' table")

        # --- Create characters table ---
        await conn.execute(
            """
            CREATE TABLE IF NOT EXISTS characters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            player_id INTEGER NOT NULL,
            first_name TEXT NOT NULL,
            last_name TEXT NOT NULL,
            race TEXT,
            class TEXT,
            level INTEGER DEFAULT 1,
            hp INTEGER DEFAULT 50,
            max_hp INTEGER DEFAULT 50,
            essence INTEGER DEFAULT 20,
            max_essence INTEGER DEFAULT 20,
            xp_pool INTEGER DEFAULT 0,
            stats TEXT DEFAULT '{}', -- JSON: {"might": 10, "agility": 10, ...}
            skills TEXT DEFAULT '{}', -- JSON: {"climb": 0, "appraise": 0, ...}
            location_id INTEGER DEFAULT 1, -- Default starting room ID
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            last_saved TIMESTAMP,
            UNIQUE (player_id, first_name, last_name), -- Character names unique per player account
            FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE, -- Delete characters if player account is deleted
            FOREIGN KEY (location_id) REFERENCES rooms(id) ON DELETE SET DEFAULT -- If room deleted, move char to default room 1
            )
            """
        )
        log.info("Checked/Created 'characters' table.")

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
            await conn.execute(
                """
                INSERT INTO rooms (id, area_id, name, description, exits, flags)
                VALUES (?, ?, ?, ?, ?, ?)
            """,
                (
                    1, 1, "The Void",
                    "A featureless void stretches out around you. It feels safe, somehow.",
                    json.dumps({}), # No exits initially
                    json.dumps([]) # flags (empty list/set as JSON)
                ),
            )  
            log.info("Default Room #1 created.")

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

# ================================================================
# Async Test Runner
# ================================================================
async def main_test():
    """Asynchronous main function to run database tests."""
    # Use lazy formatting for log messages
    log.info("Running ASYNC database module test...")

    # --- Path calculation ---
    # Determine DB path relative to project root using the potentially
    # updated global DATABASE_PATH variable.
    current_script_path = os.path.abspath(__file__)
    game_dir = os.path.dirname(current_script_path)
    parent_dir = os.path.dirname(game_dir) # Project root directory
    db_full_path = os.path.join(parent_dir, DATABASE_PATH)
    # ------------------------

    log.info("Database path for test: %s", db_full_path)

    # Must await connection
    connection = await connect_db(db_full_path)

    if connection:
        try: # use try...finally to ensure connection closure
            log.info("%s %s %s", "-" * 20, "Initializing DB (Async)", "-" * 20)
            # Must await initialization
            await init_db(connection)
            log.info("%s %s %s", "-" * 20, "Initialization Complete", "-" * 20)

            # --- Example Usage (Now using await and lazy logging) ---
            log.info("Attempting to create test player 'testacc'...")
            test_pass = "password123"
            hashed_pass = utils.hash_password(test_pass) # Hashing is sync
            player_id = await execute_query( # Must await
                connection,
                "INSERT INTO players (username, hashed_password, email) VALUES (?, ?, ?)",
                ("testacc", hashed_pass, "test@example.com")
            )

            if player_id:
                log.info("Test player 'testacc' created with ID: %s", player_id)

                log.info("Attempting to create character 'Tester' for player ID %s...", player_id)
                initial_stats = json.dumps({"might": 12, "agility": 11, "vitality": 13, "intellect": 9, "aura": 8, "persona": 10})
                initial_skills = json.dumps({"climb": 1, "swim": 1})
                char_id = await execute_query( # Must await
                    connection,
                    """INSERT INTO characters (player_id, first_name, last_name, race, class, stats, skills, location_id)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (player_id, "Tester", "Testee", "Human", "Warrior", initial_stats, initial_skills, 1)
                )
                if char_id:
                    log.info("Test character 'Tester' created with ID: %s", char_id)
                else:
                    log.error("Failed to create test character 'Tester'.") # No variable args here

            else:
                log.warning("Test player insertion failed (maybe 'testacc' or test@example.com already exists).")
                existing_player = await fetch_one(connection, "SELECT id FROM players WHERE username = ?", ("testacc",)) # Must await
                if existing_player:
                    player_id = existing_player['id']
                    log.info("Found existing player 'testacc' with ID: %s", player_id)
                else:
                    player_id = None # Ensure player_id is None if not found and not created


            log.info("Fetching character 'Tester'...")
            character_data = await fetch_one(connection, "SELECT * FROM characters WHERE first_name = ?", ("Tester",)) # Must await

            if character_data:
                # Safely format using fetched data
                log.info(
                    "Found character: ID=%s, Name=%s %s, Race=%s, Class=%s, Level=%s",
                    character_data['id'],
                    character_data['first_name'],
                    character_data['last_name'],
                    character_data['race'],
                    character_data['class'],
                    character_data['level']
                )
                # Safely parse JSON data
                try:
                    stats = json.loads(character_data['stats'])
                    # Use %s for potentially complex objects if not just simple dict __str__
                    log.info("  Stats: %s", stats)
                except (json.JSONDecodeError, TypeError):
                    log.warning("  Could not decode stats JSON: %s", character_data['stats'])
                try:
                    skills = json.loads(character_data['skills'])
                    log.info("  Skills: %s", skills)
                except (json.JSONDecodeError, TypeError):
                    log.warning("  Could not decode skills JSON: %s", character_data['skills'])
            else:
                # Only run this if character_data is None or empty after fetch attempt
                log.info("Character 'Tester' not found.")


            log.info("Fetching all rooms in Area 1:")
            area1_rooms = await fetch_all(connection, "SELECT id, name FROM rooms WHERE area_id = ?", (1,)) # Must await
            if area1_rooms is not None:
                if area1_rooms:
                    for room in area1_rooms:
                        log.info(" Room ID: %s, Name: %s", room['id'], room['name'])
                else:
                    log.info(" No rooms found in Area 1.")
            else:
                log.info(" Could not fetch rooms.")
            # --- End Example Usage ---

        finally:
            log.info("Closing database connection.")
            await connection.close() # Must await close
            log.info("Database connection closed.")
    else:
        log.error("Failed to connect to the database for testing.")

if __name__ == "__main__":
    # Fix path for direct execution IF config wasn't loaded initially
    if not config:
        current_dir = os.path.dirname(os.path.abspath(__file__))
        parent_dir = os.path.dirname(current_dir)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        try:
            import config # Try importing again now path is set
            DATABASE_PATH = config.DB_NAME # Update global if needed
        except ModuleNotFoundError:
            log.error("config.py not found even after path adjustment.")
            # Exit or use fallback path set earlier

    # Run the async test function
    asyncio.run(main_test())