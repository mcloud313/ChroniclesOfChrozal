# game/database.py
"""
Handles database interactions (SQLite initially).
"""
import sqlite3
import logging
import json
import config  # Assuming config.py is in the parent directory or PYTHONPATH is set
import os
import sys
import time # For timestamp updates
import hashlib # For password hashing (example)

DATABASE_PATH = config.DB_NAME

# Configure logging for database operations
log = logging.getLogger(__name__)
# Set default logging level if not configured elsewhere
if not log.handlers:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )


def connect_db(db_path: str = DATABASE_PATH) -> sqlite3.Connection | None:
    """
    Establishes a connection to the SQLite Database
    Args:
        db_path: The path to the SQLite database file.
    Returns:
        A sqlite3.Connection object or None if connection fails.
    """
    try:
        # Ensure the directory exists (optional, connect might handle it)
        # connect() will create the file if it doesn't exist
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(
            db_path, check_same_thread=False
        )  # check_same_thread=False is needed for asynchio potentially accessing from different contexts
        # Use Row factory for dictionary-like access to columns
        conn.row_factory = sqlite3.Row #Dictionary-like row access 
        #Enable foreign key support (important!)
        conn.execute("PRAGMA foreign_keys = ON;")
        log.info(f"Successfully connected to database: {db_path}")
        return conn
    except sqlite3.Error as e:
        log.error(f"Database connection error to {db_path}: {e}", exc_info=True)
        return None


def init_db(conn: sqlite3.Connection):
    """
    Initializes the database schema if tables don't exist.
    Creates areas, players, rooms, characters tables and default entries.
    Args:
        conn: An active sqlite3.Connection object.
    """
    try:
        cursor = conn.cursor()

        # --- Create areas table ---
        cursor.execute(
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

        # Create  players table
        cursor.execute(
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
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                area_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                description TEXT DEFAULT 'You see nothing special.',
                exits TEXT DEFAULT '{}', -- Storing exits as JSON text
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE RESTRICT -- Prevent deleting area if rooms exist
            )
        """
        )
        log.info("Checked/Created 'rooms' table")

        # --- Create characters table ---
        cursor.execute(
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
        cursor.execute("SELECT COUNT(*) FROM areas WHERE id = 1")
        area_exists = cursor.fetchone()[0]
        if not area_exists:
            log.info("Default Area #1 not found, creating it.")
            cursor.execute(
                "INSERT INTO areas (id, name, description) VALUES (?, ?, ?)",
                (1, "The Genesis Area", "A placeholder area for lonely rooms.")
            )
            log.info("Default area #1 created.")

        # Check for default room
        cursor.execute("SELECT COUNT(*) FROM rooms WHERE id = 1")
        room_exists = cursor.fetchone()[0]

        if not room_exists:
            log.info("Default room #1 not found, creating it.")
            cursor.execute(
                """
                INSERT INTO rooms (id, area_id, name, description, exits)
                VALUES (?, ?, ?, ?, ?)
            """,
                (
                    1,
                    1,
                    "The Void",
                    "A featureless void stretches out around you. It feels safe, somehow.",
                    json.dumps({}), # No exits initially
                ),
            )  
            log.info("Default Room #1 created.")

        conn.commit()
        log.info("Database initialization check complete.")

    except sqlite3.Error as e:
        log.error(f"Database initialization error: {e}", exc_info=True)
        try:
            conn.rollback()  # Rollback changes if error occurs during init
        except sqlite3.Error as rb_e:
            log.error(f"Rollback failed: {rb_e}", exec_info=True)


def execute_query(
    conn: sqlite3.Connection, query: str, params: tuple = ()
) -> int | None:
    """
    Executes a data-modifying query (INSERT, UPDATE, DELETE).

    Args:
        conn: An active sqlite3.Connection object.
        query: The SQL query string.
        params: A tuple of parameters to substitute into the query.

    Returns:
        The last inserted row ID for INSERT queries, or the number of rows affected
        for UPDATE/DELETE, or None if an error occurs. Returns 0 if no rows affected.
    """
    cursor = None # Initialize cursor to None
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        conn.commit()
        # For INSERT, lastrowid is useful. For UPDATE/DELETE, rowcount is useful.
        # Return lastrowid if available (non-zero), else rowcount.
        return cursor.lastrowid if cursor.lastrowid else cursor.rowcount
    except sqlite3.Error as e:
        log.error(
            f"Database execute error - Query: {query} Params: {params} Error: {e}",
            exc_info=True,
        )
        try:
            conn.rollback()
        except Exception as rb_e:
            log.error(f"Rollback failed after execute error: {rb_e}", exc_info=True)
        return None
    # No finally block needed for cursor closing as 'with conn:' context manager handles it if used,
    # but since we pass 'conn' in, we rely on the caller or explicit close. Cursor is method-local.

def fetch_one(
    conn: sqlite3.Connection, query: str, params: tuple = ()
) -> sqlite3.Row | None:
    """
    Executes a SELECT query and fetches the first result.

    Args:
        conn: An active sqlite3.Connection object.
        query: The SQL SELECT query string.
        params: A tuple of parameters to substitute into the query.

    Returns:
        A single sqlite3.Row object (acts like a dictionary) or None if no result or error.
    """
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchone()
    except sqlite3.Error as e:
        log.error(
            f"Database fetch_one error - Query: {query} Params: {params} Error: {e}",
            exc_info=True,
        )
        return None


def fetch_all(
    conn: sqlite3.Connection, query: str, params: tuple = ()
) -> list[sqlite3.Row] | None:
    """
    Executes a SELECT query and fetches all results.

    Args:
        conn: An active sqlite3.Connection object.
        query: The SQL SELECT query string.
        params: A tuple of parameters to substitute into the query.

    Returns:
        A list of sqlite3.Row objects (each acts like a dictionary) or None if an error occurs.
        Returns an empty list if query runs successfully but finds no matching rows.
    """
    cursor = None 
    try:
        cursor = conn.cursor()
        cursor.execute(query, params)
        return cursor.fetchall()
    except sqlite3.Error as e:
        log.error(
            f"Database fetch_all error - Query: {query} Params: {params} Error: {e}",
            exc_info=True,
        )
        return None
    
# --- Hashing Utility (Example - Replace with a robust library like bcrypt later) ---
def hash_password(password: str) -> str:
    """Basic password hashing using sha256. TODO: Replace with bcrypt later"""
    return hashlib.sha256(password.encode('utf-8')).hexdigest()

def verify_password(stored_hash: str, provided_password: str) -> bool:
    """Verfies a password against a stored sha256 hash. REPLACE later."""
    return stored_hash == hashlib.sha256(provided_password.encode('utf-8')).hexdigest()

# ================================================================
# Example of how to use these functions (for testing purposes)
# ================================================================
if __name__ == "__main__":
    # --- IMPORTANT: Fix for running script directly ---
    # Add parent directory to sys.path to find 'config.py'
    current_dir = os.path.dirname(os.path.abspath(__file__)) # game directory
    parent_dir = os.path.dirname(current_dir) # Project root directory
    if parent_dir not in sys.path:
        sys.path.insert(0, parent_dir)
    # Now 'import config' should work
    import config #Re-import if failed initially


    log.info("Running database module test...")
    # use absolute path for DB based on config relative to parent dir
    db_full_path = os.path.join(parent_dir, config.DB_NAME)
    log.info(f"Database path for test: {db_full_path}")
    connection = connect_db(db_full_path) # use the calculated full path

    if connection:
        log.info("-" * 20 + " Initializing DB " + "-" * 20)
        init_db(connection)
        log.info("-" * 20 + " Initialization Complete " + "-" * 20)

    # --- Example Usage ---
    log.info("Attempting to create test player 'testacc'...")
    test_pass = "password123"
    hashed_pass = hash_password(test_pass) # Use the basic hash for testing
    player_id = execute_query(
        connection,
            "INSERT INTO players (username, hashed_password, email) VALUES (?, ?, ?)",
            ("testacc", hashed_pass, "test@example.com")
        )
    
    if player_id:
        log.info(f"Test player 'testacc' created with ID: {player_id}")

        log.info(f"Attempting to create character 'Tester' for player ID {player_id}...")
        initial_stats = json.dumps({"might": 12, "agility": 11, "vitality": 13, "intellect": 9, "aura": 8, "persona": 10})
        initial_skills = json.dumps({"climb": 1, "swim": 1})
        char_id = execute_query(
            connection,
            """INSERT INTO characters (player_id, first_name, last_name, race, class, stats, skills, location_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (player_id, "Tester", "Testee", "Human", "Warrior", initial_stats, initial_skills, 1) # Start in room 1
            )
        if char_id:
            log.info(f"Test character 'Tester' created with ID: {char_id}")
        else:
            log.error("Failed to create test character 'Tester'.")
    
    else:
            log.warning("Test player insertion failed (maybe 'testacc' or test@example.com already exists).")
            # Try to fetch the existing player ID if creation failed
            existing_player = fetch_one(connection, "SELECT id FROM players WHERE username = ?", ("testacc",))
            if existing_player:
                player_id = existing_player['id']
                log.info(f"Found existing player 'testacc' with ID: {player_id}")
            else:
                player_id = None # Ensure player_id is None if not found


            log.info("Fetching character 'Tester'...")
        # Need player_id from above insert/fetch to query character uniquely if needed,
        # but let's fetch by name for this example assuming it might be unique globally for testing
        # A better query would use player_id if available: WHERE player_id = ? AND name = ?
            character_data = fetch_one(connection, "SELECT * FROM characters WHERE first_name = ?", ("Tester",))

            if character_data:
                log.info(f"Found character: ID={character_data['id']}, Name={character_data['first_name']} {character_data['last_name']}, Race={character_data['race']}, Class={character_data['class']}, Level={character_data['level']}")
            # Safely parse JSON data
            try:
                stats = json.loads(character_data['stats'])
                log.info(f"  Stats: {stats}")
            except (json.JSONDecodeError, TypeError):
                log.warning(f"  Could not decode stats JSON: {character_data['stats']}")
            try:
                skills = json.loads(character_data['skills'])
                log.info(f"  Skills: {skills}")
            except (json.JSONDecodeError, TypeError):
                log.warning(f"  Could not decode skills JSON: {character_data['skills']}")
            else:
                log.info("Character 'Tester' not found.")


        # Test Fetch All Rooms in Area 1
            log.info("Fetching all rooms in Area 1:")
            area1_rooms = fetch_all(connection, "SELECT id, name FROM rooms WHERE area_id = ?", (1,))
            if area1_rooms is not None:
                if area1_rooms:
                    for room in area1_rooms:
                        log.info(f" Room ID: {room['id']}, Name: {room['name']}")
                else:
                    log.info(" No rooms found in Area 1.")
            else:
                log.info(" Could not fetch rooms.")
        # --- End Example Usage ---

            log.info("Closing database connection.")
            connection.close()
            log.info("Database connection closed.")
else:
        log.error("Failed to connect to the database for testing.")