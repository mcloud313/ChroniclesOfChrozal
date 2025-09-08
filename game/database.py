# game/database.py
"""
Handles asynchronous database interactions using asyncpg for PostgreSQL.
Encapsulates all database logic within the DatabaseManager class.
"""
import logging
import json
import asyncio
import asyncpg
import config
from typing import Optional, Dict, Any, List

from . import utils

log = logging.getLogger(__name__)

DB_CONFIG = {
    "user": "chrozal",
    "password": "timcp313", # IMPORTANT: Use the password from your docker-compose.yml
    "database": "chrozaldb",
    "host": "localhost"
}

class DatabaseManager:
    """A class to manage the application's PostgreSQL connection pool and queries."""

    def __init__(self):
        self.pool: Optional[asyncpg.Pool] = None

    async def connect(self):
        """Creates the connection pool."""
        try:
            self.pool = await asyncpg.create_pool(**DB_CONFIG)
            log.info("Successfully connected to PostgreSQL and created connection pool.")
        except Exception:
            log.exception("!!! Failed to connect to PostgreSQL database. Server cannot start.")
            raise
    
    async def close(self):
        """Closes the connection pool."""
        if self.pool:
            await self.pool.close()
            log.info("PostgreSQL connection pool closed.")

    async def execute_query(self, query: str, *params) -> str:
        """Executes a data-modifying query. Returns the status string."""
        if not self.pool: raise ConnectionError("Database pool not initialized.")
        async with self.pool.acquire() as conn:
            return await conn.execute(query, *params)
    
    async def fetch_one(self, query: str, *params) -> Optional[asyncpg.Record]:
        """Executes a SELECT query and fetches the first result."""
        if not self.pool: raise ConnectionError("Database pool not initialized.")
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *params)
    
    async def fetch_all(self, query: str, *params) -> List[asyncpg.Record]:
        """Executes a SELECT query and fetches all results."""
        if not self.pool: raise ConnectionError("Database pool not initialized.")
        async with self.pool.acquire() as conn:
            return await conn.fetch(query, *params)
            
    async def init_db(self):
        """Initializes the database schema for PostgreSQL."""
        log.info("--- Initializing PostgreSQL database schema ---")
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # --- Core Tables ---
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS areas (
                        id SERIAL PRIMARY KEY,
                        name TEXT UNIQUE NOT NULL,
                        description TEXT DEFAULT 'An undescribed area.',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS players (
                        id SERIAL PRIMARY KEY,
                        username TEXT UNIQUE NOT NULL,
                        hashed_password TEXT NOT NULL,
                        email TEXT UNIQUE NOT NULL,
                        is_admin BOOLEAN NOT NULL DEFAULT FALSE,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        last_login TIMESTAMPTZ
                    )
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS rooms (
                        id SERIAL PRIMARY KEY,
                        area_id INTEGER NOT NULL REFERENCES areas(id) ON DELETE RESTRICT,
                        name TEXT NOT NULL,
                        description TEXT DEFAULT 'You see nothing special.',
                        exits JSONB DEFAULT '{}'::jsonb,
                        flags JSONB DEFAULT '[]'::jsonb,
                        spawners JSONB DEFAULT '{}'::jsonb,
                        coinage INTEGER NOT NULL DEFAULT 0,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                
                # --- Template Tables ---
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS item_templates (
                        id SERIAL PRIMARY KEY,
                        name TEXT UNIQUE NOT NULL,
                        description TEXT DEFAULT 'An ordinary item.',
                        type TEXT NOT NULL,
                        stats JSONB DEFAULT '{}'::jsonb,
                        flags JSONB DEFAULT '[]'::jsonb,
                        damage_type TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS mob_templates (
                        id SERIAL PRIMARY KEY,
                        name TEXT UNIQUE NOT NULL,
                        description TEXT DEFAULT 'A creature.',
                        mob_type TEXT,
                        level INTEGER NOT NULL DEFAULT 1,
                        stats JSONB DEFAULT '{}'::jsonb,
                        max_hp INTEGER NOT NULL DEFAULT 10,
                        attacks JSONB DEFAULT '[]'::jsonb,
                        loot JSONB DEFAULT '{}'::jsonb,
                        flags JSONB DEFAULT '[]'::jsonb,
                        respawn_delay_seconds INTEGER DEFAULT 300,
                        variance JSONB DEFAULT '{}'::jsonb,
                        movement_chance REAL NOT NULL DEFAULT 0.0,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)

                # --- Lookup & Entity Tables ---
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS races (
                        id SERIAL PRIMARY KEY,
                        name TEXT UNIQUE NOT NULL,
                        description TEXT
                    )
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS classes (
                        id SERIAL PRIMARY KEY,
                        name TEXT UNIQUE NOT NULL,
                        description TEXT
                    )
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS characters (
                        id SERIAL PRIMARY KEY,
                        player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
                        first_name TEXT NOT NULL,
                        last_name TEXT NOT NULL,
                        sex TEXT NOT NULL,
                        race_id INTEGER REFERENCES races(id) ON DELETE SET NULL,
                        class_id INTEGER REFERENCES classes(id) ON DELETE SET NULL,
                        level INTEGER DEFAULT 1,
                        description TEXT DEFAULT '',
                        hp REAL DEFAULT 50.0,
                        max_hp REAL DEFAULT 50.0,
                        essence REAL DEFAULT 20.0,
                        max_essence REAL DEFAULT 20.0,
                        spiritual_tether INTEGER,
                        xp_pool REAL DEFAULT 0.0,
                        xp_total REAL DEFAULT 0.0,
                        status TEXT NOT NULL DEFAULT 'ALIVE',
                        stance TEXT NOT NULL DEFAULT 'Standing',
                        unspent_skill_points INTEGER NOT NULL DEFAULT 0,
                        unspent_attribute_points INTEGER NOT NULL DEFAULT 0,
                        stats JSONB DEFAULT '{}'::jsonb,
                        skills JSONB DEFAULT '{}'::jsonb,
                        known_spells JSONB DEFAULT '[]'::jsonb,
                        known_abilities JSONB DEFAULT '[]'::jsonb,
                        location_id INTEGER DEFAULT 1,
                        inventory JSONB DEFAULT '[]'::jsonb,
                        equipment JSONB DEFAULT '{}'::jsonb,
                        coinage INTEGER NOT NULL DEFAULT 0,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        last_saved TIMESTAMPTZ,
                        total_playtime_seconds INTEGER NOT NULL DEFAULT 0,
                        UNIQUE (player_id, first_name, last_name)
                    )
                """)

                # --- Junction/Instance Tables ---
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS room_items (
                        id SERIAL PRIMARY KEY,
                        room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
                        item_template_id INTEGER NOT NULL REFERENCES item_templates(id) ON DELETE CASCADE,
                        dropped_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS room_objects (
                        id SERIAL PRIMARY KEY,
                        room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        description TEXT DEFAULT 'It looks unremarkable.',
                        keywords JSONB DEFAULT '[]'::jsonb,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        UNIQUE (room_id, name)
                    )
                """)

        # --- Seed Essential Data ---
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Races
                await conn.executemany("INSERT INTO races (id, name, description) VALUES ($1, $2, $3) ON CONFLICT (id) DO NOTHING", 
                                     [(1, "Chrozalin", "Versatile humans..."), (2, "Dwarf", "Stout mountain folk..."), (3, "Elf", "Graceful forest dwellers..."), (4, "Yan-tar", "Ancient turtle-like people..."), (5, "Grak", "Towering humanoids...")])
                # Classes
                await conn.executemany("INSERT INTO classes (id, name, description) VALUES ($1, $2, $3) ON CONFLICT (id) DO NOTHING",
                                     [(1, "Warrior", "..."), (2, "Mage", "..."), (3, "Cleric", "..."), (4, "Rogue", "...")])
                # Areas & Rooms
                await conn.execute("INSERT INTO areas (id, name, description) VALUES ($1, $2, $3) ON CONFLICT (id) DO NOTHING", 1, "The Void", "...")
                await conn.execute("INSERT INTO rooms (id, area_id, name, description, flags) VALUES ($1, $2, $3, $4, $5) ON CONFLICT (id) DO NOTHING", 1, 1, "The Void", "...", json.dumps(["NODE", "RESPAWN"]))
                # Test Players
                await conn.execute("INSERT INTO players (username, hashed_password, email, is_admin) VALUES ($1, $2, $3, $4) ON CONFLICT (username) DO NOTHING", "tester", utils.hash_password("password"), "tester@example.com", False)
                await conn.execute("INSERT INTO players (username, hashed_password, email, is_admin) VALUES ($1, $2, $3, $4) ON CONFLICT (username) DO NOTHING", "admin", utils.hash_password("password"), "admin@example.com", True)
                
        log.info("--- PostgreSQL schema check complete ---")

    # --- Creator Functions (for seeding and building) ---
    async def create_item_template(self, name: str, item_type: str, description: str, stats: dict, flags: list, damage_type: Optional[str]) -> Optional[int]:
        query = "INSERT INTO item_templates (name, type, description, stats, flags, damage_type) VALUES ($1, $2, $3, $4, $5, $6) RETURNING id"
        record = await self.fetch_one(query, name, item_type, description, json.dumps(stats), json.dumps(flags), damage_type)
        return record['id'] if record else None

    async def create_mob_template(self, name: str, level: int, description: str, stats: dict, attacks: list, loot: dict, flags: list) -> Optional[int]:
        query = "INSERT INTO mob_templates (name, level, description, stats, attacks, loot, flags) VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id"
        record = await self.fetch_one(query, name, level, description, json.dumps(stats), json.dumps(attacks), json.dumps(loot), json.dumps(flags))
        return record['id'] if record else None

    async def update_room_exits(self, room_id: int, exits: dict) -> str:
        query = "UPDATE rooms SET exits = $1 WHERE id = $2"
        return await self.execute_query(query, json.dumps(exits), room_id)

    # --- Player Functions ---
    async def load_player_account(self, username: str) -> Optional[asyncpg.Record]:
        query = "SELECT * FROM players WHERE lower(username) = lower($1)"
        return await self.fetch_one(query, username)
    
    async def create_player_account(self, username: str, hashed_password: str, email: str) -> Optional[int]:
        query = "INSERT INTO players (username, hashed_password, email, last_login) VALUES ($1, $2, $3, NOW()) RETURNING id"
        record = await self.fetch_one(query, username, hashed_password, email)
        return record['id'] if record else None

    # --- Character Functions ---
    async def load_characters_for_account(self, player_id: int) -> List[asyncpg.Record]:
        query = "SELECT id, first_name, last_name, level, race_id, class_id FROM characters WHERE player_id = $1 ORDER BY last_saved DESC NULLS LAST, id ASC"
        return await self.fetch_all(query, player_id)
    
    async def load_character_data(self, character_id: int) -> Optional[asyncpg.Record]:
        query = "SELECT * FROM characters WHERE id = $1"
        return await self.fetch_one(query, character_id)
    
    async def save_character_data(self, character_id: int, data: dict) -> str:
        """Dynamically updates character data."""
        if not data: return "UPDATE 0"
        set_clauses = [f"{key} = ${i+1}" for i, key in enumerate(data.keys())]
        params = [json.dumps(v) if isinstance(v, (dict, list)) else v for v in data.values()]
        
        params.append(character_id)
        query = f"UPDATE characters SET {', '.join(set_clauses)}, last_saved = NOW() WHERE id = ${len(params)}"
        return await self.execute_query(query, *params)
    
    async def update_character_playtime(self, character_id: int, session_seconds: int) -> str:
        """Adds the session duration to the character's total playtime."""
        query = "UPDATE characters SET total_playtime_seconds = total_playtime_seconds + $1 WHERE id = $2"
        return await self.execute_query(query, session_seconds, character_id)
    
db_manager = DatabaseManager()