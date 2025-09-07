# game/database.py
"""
Handles asynchronous database interactions using aiosqlite
Manages players (accounts), characters, rooms, and areas
"""
import logging
import json
import os
import sys
import hashlib
import asyncio
import aiosqlite
import config
import math
from typing import TYPE_CHECKING, Optional, Dict, Any, List, Set, Union
from . import utils
from .definitions import classes as class_defs
from .definitions import skills as skill_defs
from .definitions import abilities as ability_defs


try:
    import config
except ModuleNotFoundError:
    config = None
    print("Warning: config.py not found on initial import.")

DATABASE_PATH = getattr(config, 'DB_NAME', 'data/default.db')

log = logging.getLogger(__name__)

# --- Core Async Database Functions
async def connect_db(db_path: str = DATABASE_PATH) -> aiosqlite.Connection | None:
    """
    Establishes an asynchronous connection to the SQLite Database.
    Creates the database file and directory if they don't exist.
    Enables WAL mode and foreign key support.
    """
    try:
        db_dir = os.path.dirname(db_path)
        if db_dir:
            os.makedirs(db_dir, exist_ok=True)
        conn = await aiosqlite.connect(db_path)
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA journal_mode=WAL;")
        await conn.execute("PRAGMA foreign_keys = ON;")
        await conn.commit()
        log.info("Successfully connected to the database (WAL Mode): %s", db_path)
        return conn
    except aiosqlite.Error as e:
        log.error("Database connection error to %s: %s", db_path, e, exc_info=True)
        return None

async def init_db(conn: aiosqlite.Connection):
    """
    Initializes the database schema and populates essential lookup tables
    and a minimal starting environment.
    """
    log.info("--- Running Database Initialization (Schema + Base Data) ---")
    try:
        await conn.execute("PRAGMA foreign_keys = ON;")

        # --- Schema Creation ---
        log.info("Step 1: Creating tables (IF NOT EXISTS)...")
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS areas (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL,
                description TEXT DEFAULT 'An undescribed area.', created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS players (
                id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT UNIQUE NOT NULL, hashed_password TEXT NOT NULL,
                email TEXT NOT NULL, is_admin BOOLEAN NOT NULL DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_login TIMESTAMP )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS rooms (
                id INTEGER PRIMARY KEY AUTOINCREMENT, area_id INTEGER NOT NULL, name TEXT NOT NULL,
                description TEXT DEFAULT 'You see nothing special.', exits TEXT DEFAULT '{}', flags TEXT DEFAULT '[]',
                spawners TEXT DEFAULT '{}', coinage INTEGER NOT NULL DEFAULT 0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (area_id) REFERENCES areas(id) ON DELETE RESTRICT )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS room_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT, room_id INTEGER NOT NULL, item_template_id INTEGER NOT NULL,
                dropped_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(room_id) REFERENCES rooms(id) ON DELETE CASCADE,
                FOREIGN KEY(item_template_id) REFERENCES item_templates(id) ON DELETE CASCADE )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS room_objects (
                id INTEGER PRIMARY KEY AUTOINCREMENT, room_id INTEGER NOT NULL, name TEXT NOT NULL,
                description TEXT DEFAULT 'It looks unremarkable.', keywords TEXT NOT NULL DEFAULT '[]',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(room_id) REFERENCES rooms(id) ON DELETE CASCADE,
                UNIQUE (room_id, name) )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS races (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, description TEXT DEFAULT 'An undescribed race.' )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, description TEXT DEFAULT 'An undescribed class' )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS item_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, description TEXT DEFAULT 'An ordinary item.',
                type TEXT NOT NULL, stats TEXT DEFAULT '{}', flags TEXT DEFAULT '[]', damage_type TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS mob_templates (
                id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT UNIQUE NOT NULL, description TEXT DEFAULT 'A creature.',
                mob_type TEXT DEFAULT NULL, level INTEGER NOT NULL DEFAULT 1, stats TEXT DEFAULT '{}',
                max_hp INTEGER NOT NULL DEFAULT 10, attacks TEXT DEFAULT '[]', loot TEXT DEFAULT '{}',
                flags TEXT DEFAULT '[]', respawn_delay_seconds INTEGER DEFAULT 300, variance TEXT DEFAULT '{}',
                movement_chance REAL NOT NULL DEFAULT 0.0, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP )
        """)
        await conn.execute("""
            CREATE TABLE IF NOT EXISTS characters (
                id INTEGER PRIMARY KEY AUTOINCREMENT, player_id INTEGER NOT NULL, first_name TEXT NOT NULL, last_name TEXT NOT NULL,
                sex TEXT NOT NULL, race_id INTEGER, class_id INTEGER, level INTEGER DEFAULT 1, description TEXT DEFAULT '',
                hp REAL DEFAULT 50.0, max_hp REAL DEFAULT 50.0, essence REAL DEFAULT 20.0, max_essence REAL DEFAULT 20.0,
                spiritual_tether INTEGER, xp_pool REAL DEFAULT 0.0, xp_total REAL DEFAULT 0.0,
                status TEXT NOT NULL DEFAULT 'ALIVE', unspent_skill_points INTEGER NOT NULL DEFAULT 0, unspent_attribute_points INTEGER NOT NULL DEFAULT 0,
                stance TEXT NOT NULL DEFAULT 'Standing', stats TEXT DEFAULT '{}', skills TEXT DEFAULT '{}',
                known_spells TEXT NOT NULL DEFAULT '[]', known_abilities TEXT NOT NULL DEFAULT '[]',
                location_id INTEGER DEFAULT 1,
                inventory TEXT NOT NULL DEFAULT '[]', equipment TEXT NOT NULL DEFAULT '{}', coinage INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP, last_saved TIMESTAMP,
                UNIQUE (player_id, first_name, last_name), FOREIGN KEY (player_id) REFERENCES players(id) ON DELETE CASCADE,
                FOREIGN KEY (location_id) REFERENCES rooms(id) ON DELETE SET DEFAULT,
                FOREIGN KEY (race_id) REFERENCES races(id) ON DELETE SET NULL, FOREIGN KEY (class_id) REFERENCES classes(id) ON DELETE SET NULL )
        """)
        await conn.commit()
        log.info("Table schema check complete.")

        # --- Populate Base Lookups (Races, Classes) ---
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
        await conn.commit()
        log.info("Races & Classes populated.")

        # --- Populate Minimal World Geometry ---
        log.info("Step 3: Populating Minimal World (Area 1, Room 1)...")
        await conn.execute("INSERT OR IGNORE INTO areas (id, name, description) VALUES (?, ?, ?)",
                           (1, "The Void", "A swirling nexus outside normal reality. Builders start here."))
        await conn.execute("""
            INSERT OR IGNORE INTO rooms (id, area_id, name, description, exits, flags, spawners, coinage)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (1, 1, "The Void",
             "An empty, featureless void stretches endlessly around you. There is nowhere to go until you build it.",
             json.dumps({}), json.dumps(["NODE", "RESPAWN"]), '{}', 0))
        await conn.commit()
        log.info("Default area and starting room created.")

        # --- Create Test Player Accounts ---
        log.info("Step 4: Creating test player accounts...")
        test_players = [
            ("tester", utils.hash_password("password"), "tester@example.com", 0),
            ("admin", utils.hash_password("password"), "admin@example.com", 1),
        ]
        try:
            await conn.executemany(
                """INSERT INTO players (username, hashed_password, email, is_admin) VALUES (?, ?, ?, ?)""", test_players
            )
            await conn.commit()
            log.info("Test player accounts seeded.")
        except aiosqlite.IntegrityError:
            log.debug("Test player accounts already exist (UNIQUE constraint ignored).")
            await conn.commit()

        # --- Test character seeding is now removed from init_db ---
        log.info("Step 5: Skipping test character seeding. Use in-game creation or builder tools.")

        await conn.commit()
        log.info("--- Database Initialization and Seeding Complete ---")

    except aiosqlite.Error as e:
        log.exception("Database initialization/seeding error: %s", e)
        try:
            await conn.rollback()
        except Exception as rb_e:
            log.error("Rollback failed: %s", rb_e)
        raise

async def execute_query(conn: aiosqlite.Connection, query: str, params: tuple = ()) -> int | None:
    """Executes a data-modifying query (INSERT, UPDATE, DELETE) asynchronously."""
    try:
        async with conn.execute(query, params) as cursor:
            last_id = cursor.lastrowid
            row_count = cursor.rowcount
        await conn.commit()
        result = last_id if last_id else row_count
        log.debug("execute_query successful: Query=[%s], Params=%r, Result=%r", query, params, result)
        return result
    except aiosqlite.Error as e:
        log.error("Database execute error - Query: %s, Params: %s, Error: %s", query, params, e)
        try:
            await conn.rollback()
        except Exception as rb_e:
            log.error("Rollback failed after execute error: %s", rb_e)
        return None

async def fetch_one(conn: aiosqlite.Connection, query: str, params: tuple = ()) -> aiosqlite.Row | None:
    """Executes a SELECT query asynchronously and fetches the first result."""
    try:
        async with conn.execute(query, params) as cursor:
            return await cursor.fetchone()
    except aiosqlite.Error as e:
        log.error("Database fetch_one error - Query: %s, Params: %s, Error: %s", query, params, e)
        return None

async def fetch_all(conn: aiosqlite.Connection, query: str, params: tuple = ()) -> list[aiosqlite.Row] | None:
    """Executes a SELECT query asynchronously and fetches all results."""
    try:
        async with conn.execute(query, params) as cursor:
            return await cursor.fetchall()
    except aiosqlite.Error as e:
        log.error("Database fetch_all error - Query: %s, Params: %s, Error: %s", query, params, e)
        return None

# ... (player and character functions remain the same for now) ...
async def load_all_areas(conn: aiosqlite.Connection) -> list[aiosqlite.Row] | None:
    return await fetch_all(conn, "SELECT * FROM areas ORDER BY id")

async def load_all_rooms(conn: aiosqlite.Connection) -> list[aiosqlite.Row] | None:
    return await fetch_all(conn, "SELECT * FROM rooms ORDER BY id")

async def load_player_account(conn: aiosqlite.Connection, username: str) -> aiosqlite.Row | None:
    return await fetch_one(conn, "SELECT *, is_admin FROM players WHERE lower(username) = lower(?)", (username,))

async def create_player_account(conn: aiosqlite.Connection, username: str, hashed_password: str, email: str) -> int | None:
    query = "INSERT INTO players (username, hashed_password, email, last_login) VALUES (?, ?, ?, CURRENT_TIMESTAMP)"
    return await execute_query(conn, query, (username, hashed_password, email))

async def update_player_password(conn: aiosqlite.Connection, player_id: int, new_hashed_password: str) -> int | None:
    query = "UPDATE players SET hashed_password = ? WHERE id = ?"
    return await execute_query(conn, query, (new_hashed_password, player_id))

async def load_characters_for_account(conn: aiosqlite.Connection, player_id: int) -> list[aiosqlite.Row] | None:
    query = "SELECT id, first_name, last_name, level, race_id, class_id FROM characters WHERE player_id = ? ORDER BY last_saved DESC, id ASC"
    return await fetch_all(conn, query, (player_id,))

async def load_character_data(conn: aiosqlite.Connection, character_id: int) -> aiosqlite.Row | None:
    return await fetch_one(conn, "SELECT * FROM characters WHERE id = ?", (character_id,))

async def save_character_data(conn: aiosqlite.Connection, character_id: int, data: dict) -> int | None:
    if not data:
        return 0
    set_clauses = []
    params = []
    valid_columns = [
        "location_id", "hp", "essence", "xp_pool", "xp_total", "level", "stats", "skills",
        "description", "sex", "race_id", "class_id", "max_hp", "max_essence", "inventory",
        "equipment", "coinage", "unspent_skill_points", "unspent_attribute_points",
        "known_spells", "known_abilities", "status", "stance", "spiritual_tether"
    ]
    for key, value in data.items():
        if key in valid_columns:
            set_clauses.append(f"{key} = ?")
            params.append(json.dumps(value) if isinstance(value, (dict, list, set)) else value)
    if not set_clauses:
        return 0
    set_clauses.append("last_saved = CURRENT_TIMESTAMP")
    query = f"UPDATE characters SET {', '.join(set_clauses)} WHERE id = ?"
    params.append(character_id)
    return await execute_query(conn, query, tuple(params))

async def load_all_races(conn: aiosqlite.Connection) -> list[aiosqlite.Row] | None:
    return await fetch_all(conn, "SELECT id, name, description FROM races ORDER BY id")

async def load_all_classes(conn: aiosqlite.Connection) -> list[aiosqlite.Row] | None:
    return await fetch_all(conn, "SELECT id, name, description FROM classes ORDER BY id")

async def load_all_item_templates(conn: aiosqlite.Connection, search_term: Optional[str] = None) -> list[aiosqlite.Row] | None:
    if search_term:
        query = "SELECT id, name, type FROM item_templates WHERE name LIKE ? ORDER BY id"
        params = (f"%{search_term}%",)
    else:
        query = "SELECT * FROM item_templates ORDER BY id"
        params = ()
    return await fetch_all(conn, query, params)

async def load_item_template(conn: aiosqlite.Connection, template_id: int) -> aiosqlite.Row | None:
    return await fetch_one(conn, "SELECT * FROM item_templates WHERE id = ?", (template_id,))

async def load_items_for_room(conn: aiosqlite.Connection, room_id: int) -> list[int] | None:
    query = "SELECT item_template_id FROM room_items WHERE room_id = ?"
    rows = await fetch_all(conn, query, (room_id,))
    return [row['item_template_id'] for row in rows] if rows is not None else None

async def load_objects_for_room(conn: aiosqlite.Connection, room_id: int) -> list[aiosqlite.Row] | None:
    query = "SELECT id, name, description, keywords FROM room_objects WHERE room_id = ?"
    return await fetch_all(conn, query, (room_id,))

async def load_coinage_for_room(conn: aiosqlite.Connection, room_id: int) -> int | None:
    query = "SELECT coinage FROM rooms WHERE id = ?"
    row = await fetch_one(conn, query, (room_id,))
    return row['coinage'] if row else None

async def add_item_to_room(conn: aiosqlite.Connection, room_id: int, item_template_id: int) -> int | None:
    query = "INSERT INTO room_items (room_id, item_template_id) VALUES (?, ?)"
    return await execute_query(conn, query, (room_id, item_template_id))

async def remove_item_from_room(conn: aiosqlite.Connection, room_id: int, item_template_id: int) -> int | None:
    query = "DELETE FROM room_items WHERE id = (SELECT id FROM room_items WHERE room_id = ? AND item_template_id = ? LIMIT 1)"
    return await execute_query(conn, query, (room_id, item_template_id))

async def load_mob_template(conn: aiosqlite.Connection, template_id: int) -> aiosqlite.Row | None:
    return await fetch_one(conn, "SELECT * FROM mob_templates WHERE id = ?", (template_id,))

async def update_room_coinage(conn: aiosqlite.Connection, room_id: int, amount_change: int) -> int | None:
    query = "UPDATE rooms SET coinage = max(0, coinage + ?) WHERE id = ?"
    return await execute_query(conn, query, (amount_change, room_id))

async def create_character(
    conn: aiosqlite.Connection, player_id: int, first_name: str, last_name: str, sex: str,
    race_id: int, class_id: int, stats_json: str, skills_json: str, description: str,
    hp: float, max_hp: float, essence: float, max_essence: float,
    known_spells_json: str = '[]', known_abilities_json: str = '[]',
    location_id: int = 1, # FIX: Default to 1 for consistency
    spiritual_tether: int = 1,
    inventory_json: str = '[]',
    equipment_json: str = '{}',
    coinage: int = 0
) -> int | None:
    """Creates a new character record."""
    query = """
        INSERT INTO characters (
            player_id, first_name, last_name, sex, race_id, class_id, stats, skills,
            description, hp, max_hp, essence, max_essence, spiritual_tether, inventory,
            equipment, coinage, known_spells, known_abilities, location_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        player_id, first_name, last_name, sex, race_id, class_id, stats_json, skills_json,
        description, hp, max_hp, essence, max_essence, spiritual_tether, inventory_json,
        equipment_json, coinage, known_spells_json, known_abilities_json, location_id
    )
    return await execute_query(conn, query, params)

async def create_room(conn: aiosqlite.Connection, area_id: int, name: str, description: str = "An undescribed room.") -> Optional[int]:
    query = "INSERT INTO rooms (area_id, name, description) VALUES (?, ?, ?)"
    return await execute_query(conn, query, (area_id, name, description))

async def update_room_basic(conn: aiosqlite.Connection, room_id: int, field: str, value: Any) -> bool:
    if field not in ["name", "description", "area_id"]:
        return False
    query = f"UPDATE rooms SET {field} = ? WHERE id = ?"
    rowcount = await execute_query(conn, query, (value, room_id))
    return rowcount is not None and rowcount > 0

async def update_room_field(conn: aiosqlite.Connection, room_id: int, field: str, value: Any) -> int | None:
    valid_fields = ["name", "description", "exits", "flags", "spawners", "coinage", "area_id"]
    if field not in valid_fields:
        return None
    param_value = value
    if field in ["exits", "flags", "spawners"]:
        param_value = json.dumps(sorted(list(value)) if isinstance(value, set) else value)
    elif field in ["coinage", "area_id"]:
        param_value = int(value)
    query = f"UPDATE rooms SET {field} = ? WHERE id = ?"
    return await execute_query(conn, query, (param_value, room_id))

async def delete_room(conn: aiosqlite.Connection, room_id: int) -> int | None:
    query = "DELETE FROM rooms WHERE id = ?"
    return await execute_query(conn, query, (room_id,))

async def get_room_data(conn: aiosqlite.Connection, room_id: int) -> Optional[aiosqlite.Row]:
    return await fetch_one(conn, "SELECT * FROM rooms WHERE id = ?", (room_id,))

async def get_rooms_in_area(conn: aiosqlite.Connection, area_id: int) -> Optional[List[aiosqlite.Row]]:
    query = "SELECT id, name FROM rooms WHERE area_id = ? ORDER BY id"
    return await fetch_all(conn, query, (area_id,))

async def get_all_rooms_basic(conn: aiosqlite.Connection) -> Optional[List[aiosqlite.Row]]:
    query = "SELECT r.id, r.name, r.area_id, a.name as area_name FROM rooms r JOIN areas a ON r.area_id = a.id ORDER BY r.area_id, r.id"
    return await fetch_all(conn, query)

async def create_area(conn: aiosqlite.Connection, name: str, description: str = "An undescribed area.") -> Optional[aiosqlite.Row]:
    query = "INSERT INTO areas (name, description) VALUES (?, ?)"
    new_id = await execute_query(conn, query, (name, description))
    return await load_area_data(conn, new_id) if new_id else None

async def update_area_field(conn: aiosqlite.Connection, area_id: int, field: str, value: str) -> int | None:
    if field not in ["name", "description"]:
        return None
    query = f"UPDATE areas SET {field} = ? WHERE id = ?"
    return await execute_query(conn, query, (value, area_id))

async def get_room_count_for_area(conn: aiosqlite.Connection, area_id: int) -> int:
    query = "SELECT COUNT(*) as count FROM rooms WHERE area_id = ?"
    row = await fetch_one(conn, query, (area_id,))
    return row['count'] if row else 0

async def delete_area(conn: aiosqlite.Connection, area_id: int) -> int | None:
    room_count = await get_room_count_for_area(conn, area_id)
    if room_count > 0:
        return -1
    query = "DELETE FROM areas WHERE id = ?"
    return await execute_query(conn, query, (area_id,))

async def load_area_data(conn: aiosqlite.Connection, area_id: int) -> aiosqlite.Row | None:
    return await fetch_one(conn, "SELECT * FROM areas WHERE id = ?", (area_id,))

async def create_item_template(conn: aiosqlite.Connection, name: str, item_type: str, description: str = "An ordinary item.", stats_json: str = '{}', flags_json: str = '[]', damage_type: Optional[str] = None) -> Optional[aiosqlite.Row]:
    query = "INSERT INTO item_templates (name, type, description, stats, flags, damage_type) VALUES (?, ?, ?, ?, ?, ?)"
    params = (name, item_type.upper(), description, stats_json, flags_json, damage_type)
    new_id = await execute_query(conn, query, params)
    return await load_item_template(conn, new_id) if new_id else None

async def update_item_template_field(conn: aiosqlite.Connection, template_id: int, field: str, value: Any) -> Optional[aiosqlite.Row]:
    valid_fields = ["name", "description", "type", "stats", "flags", "damage_type"]
    if field not in valid_fields:
        return None
    param_value = str(value).upper() if field == "type" else value
    query = f"UPDATE item_templates SET {field} = ? WHERE id = ?"
    rowcount = await execute_query(conn, query, (param_value, template_id))
    return await load_item_template(conn, template_id) if rowcount else None

async def copy_item_template(conn: aiosqlite.Connection, source_id: int, new_name: str) -> Optional[aiosqlite.Row]:
    source_data = await load_item_template(conn, source_id)
    if not source_data:
        return None
    # BUG FIX: Arguments were in the wrong order. Corrected to match create_item_template signature.
    return await create_item_template(
        conn,
        new_name,
        source_data['type'],
        source_data['description'],
        source_data['stats'],
        source_data['flags'],
        source_data['damage_type']
    )

async def delete_item_template(conn: aiosqlite.Connection, template_id: int) -> int | None:
    query = "DELETE FROM item_templates WHERE id = ?"
    return await execute_query(conn, query, (template_id,))

async def create_mob_template(conn: aiosqlite.Connection, name: str, level: int = 1, description: str = "A creature.") -> Optional[aiosqlite.Row]:
    query = "INSERT INTO mob_templates (name, description, level) VALUES (?, ?, ?)"
    new_id = await execute_query(conn, query, (name, description, level))
    return await load_mob_template(conn, new_id) if new_id else None

async def get_mob_templates(conn: aiosqlite.Connection, search_term: Optional[str] = None) -> list[aiosqlite.Row] | None:
    if search_term:
        # BUG FIX: Removed extra comma before FROM
        query = "SELECT id, name, level FROM mob_templates WHERE name LIKE ? ORDER BY id"
        params = (f"%{search_term}%",)
    else:
        query = "SELECT id, name, level FROM mob_templates ORDER BY id"
        params = ()
    return await fetch_all(conn, query, params)

async def update_mob_template_field(conn: aiosqlite.Connection, template_id: int, field: str, value: Any) -> Optional[aiosqlite.Row]:
    valid_fields = ["name", "description", "mob_type", "level", "stats", "max_hp", "attacks", "loot", "flags", "respawn_delay_seconds", "variance", "movement_chance"]
    if field not in valid_fields:
        return None
    param_value = value
    if field in ["stats", "attacks", "loot", "flags", "variance"]:
        try:
            json.loads(value)
        except (json.JSONDecodeError, TypeError):
            return None
    # ... (add more type validation as before)
    query = f"UPDATE mob_templates SET {field} = ? WHERE id = ?"
    rowcount = await execute_query(conn, query, (param_value, template_id))
    return await load_mob_template(conn, template_id) if rowcount else None

async def copy_mob_template(conn: aiosqlite.Connection, source_id: int, new_name: str) -> Optional[aiosqlite.Row]:
    source_data = await load_mob_template(conn, source_id)
    if not source_data:
        return None
    query = """
        INSERT INTO mob_templates (name, description, mob_type, level, stats, max_hp, attacks, loot, flags, respawn_delay_seconds, variance, movement_chance)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """
    params = (
        new_name, source_data['description'], source_data['mob_type'], source_data['level'],
        source_data['stats'], source_data['max_hp'], source_data['attacks'], source_data['loot'],
        source_data['flags'], source_data['respawn_delay_seconds'], source_data['variance'],
        source_data['movement_chance']
    )
    new_id = await execute_query(conn, query, params)
    return await load_mob_template(conn, new_id) if new_id else None

async def delete_mob_template(conn: aiosqlite.Connection, template_id: int) -> int | None:
    query = "DELETE FROM mob_templates WHERE id = ?"
    return await execute_query(conn, query, (template_id,))

async def create_room_object(conn: aiosqlite.Connection, room_id: int, name: str, keywords_json: str, description: str = "It looks unremarkable.") -> Optional[aiosqlite.Row]:
    query = "INSERT INTO room_objects (room_id, name, keywords, description) VALUES (?, ?, ?, ?)"
    params = (room_id, name, keywords_json, description)
    new_id = await execute_query(conn, query, params)
    return await get_room_object_by_id(conn, new_id) if new_id else None

async def get_room_object_by_id(conn: aiosqlite.Connection, object_id: int) -> Optional[aiosqlite.Row]:
    return await fetch_one(conn, "SELECT * FROM room_objects WHERE id = ?", (object_id,))

async def update_room_object_field(conn: aiosqlite.Connection, object_id: int, field: str, value: str) -> Optional[aiosqlite.Row]:
    valid_fields = ["name", "description", "keywords"]
    if field not in valid_fields:
        return None
    query = f"UPDATE room_objects SET {field} = ? WHERE id = ?"
    rowcount = await execute_query(conn, query, (value, object_id))
    return await get_room_object_by_id(conn, object_id) if rowcount else None

async def delete_room_object(conn: aiosqlite.Connection, object_id: int) -> int | None:
    query = "DELETE FROM room_objects WHERE id = ?"
    return await execute_query(conn, query, (object_id,))