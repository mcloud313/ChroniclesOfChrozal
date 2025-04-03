# game/database.py
"""
Handles database interactions (SQLite initially).
"""
import sqlite3
import logging
import json
import config  # Assuming config.py is in the parent directory or PYTHONPATH is set

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
        # connect() will create the file if it doesn't exist
        conn = sqlite3.connect(
            db_path, check_same_thread=False
        )  # check_same_thread=False is needed for asynchio potentially accessing from different contexts
        # Use Row factory for dictionary-like access to columns
        conn.row_factory = sqlite3.Row
        log.info(f"Successfully connected to database: {db_path}")
        return conn
    except sqlite3.Error as e:
        log.error(f"Database connection error to {db_path}: {e}", exc_info=True)
        return None


def init_db(conn: sqlite3.Connection):
    """
    Initializes the database schema if tables don't exist.
    Creates players and rooms tables and a default starting room.

    Args:
        conn: An active sqlite3.Connection object.
    """
    try:
        cursor = conn.cursor()

        # Create  players table
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT UNIQUE NOT NULL,
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
                name TEXT NOT NULL,
                description TEXT DEFAULT 'You see nothing special.',
                exits TEXT DEFAULT '{}', -- Storing exits as JSON text
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (area_id) REFERENCES areas(id)
            )
        """
        )
        log.info("Checked/Created 'rooms' table")

        # Check if the default room exists, add it if not
        cursor.execute("SELECT COUNT(*) FROM rooms WHERE id = 1")
        room_exists = cursor.fetchone()[0]

        if not room_exists:
            log.info("Default room #1 not found, creating it.")
            cursor.execute(
                """
                           INSERT INTO rooms (id, name, description, exits)
                           VALUES (?, ?, ?, ?)
            """,
                (
                    1,
                    "The Void",
                    "A featureless void stretches out around you. It feels safe, somehow.",
                    json.dumps({}),
                ),
            )  # No exits initially
            log.info("Default Room #1 created.")

        conn.commit()
        log.info("Database initialization check complete.")

    except sqlite3.Error as e:
        log.error(f"Database initialization error: {e}", exc_info=True)
        conn.rollback()  # Rollback changes if error occurs during init


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
        conn.rollback()
        return None


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


# Example of how to use these functions (for testing purposes)
if __name__ == "__main__":
    log.info("Running database module test...")
    connection = connect_db()

    if connection:
        init_db(connection)

        # --- Example Usage (Comment out or remove after testing) ---
        # Test Insert (will fail if name 'testuser' already exists due to UNIQUE constraint)
        # test_pass = "hashed_password_placeholder"
        # inserted_id = execute_query(connection,
        #                             "INSERT INTO players (name, hashed_password) VALUES (?, ?)",
        #                             ("testuser", test_pass))
        # if inserted_id:
        #     log.info(f"Test user inserted with ID: {inserted_id}")
        # else:
        #     log.warning("Test user insertion failed (might already exist).")

        # Test Fetch One
        log.info("Fetching player with ID 1:")
        player_one = fetch_one(connection, "SELECT * FROM players WHERE id = ?", (1,))
        if player_one:
            log.info(
                f"Found Player 1: Name={player_one['name']}, Location={player_one['location_id']}"
            )
        else:
            log.info("Player 1 not found.")

        # Test Fetch All Rooms
        log.info("Fetching all rooms:")
        all_rooms = fetch_all(connection, "SELECT id, name FROM rooms")
        if all_rooms is not None:
            for room in all_rooms:
                log.info(f"Room ID: {room['id']}, Name: {room['name']}")
        else:
            log.info("Could not fetch rooms.")
        # --- End Example Usage ---

        connection.close()
        log.info("Database connection closed.")
    else:
        log.error("Failed to connect to the database for testing.")
