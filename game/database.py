# game/database.py
"""
Handles asynchronous database interactions using asyncpg for PostgreSQL.
Encapsulates all database logic within the DatabaseManager class.
"""
import uuid
import logging
import json
import asyncio
import asyncpg
import config
from typing import Optional, Dict, Any, List, Set

from . import utils
from .definitions import skills as skill_defs
from .definitions import abilities as ability_defs
from .definitions import classes as class_defs

log = logging.getLogger(__name__)

DB_CONFIG = {
    "user": "chrozal",
    "password": "timcp313", 
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
    
    async def fetch_one_query(self, query: str, *params) -> Optional[asyncpg.Record]:
        """Executes a query that is expected to return at most one row."""
        async with self.pool.acquire() as conn:
            return await conn.fetchrow(query, *params)
    
    async def fetch_all_query(self, query: str, *params) -> List[asyncpg.Record]:
        """Executes a query that returns multiple rows."""
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
                    -- spawners and flags are still JSONB for now, can be normalized later
                    spawners JSONB DEFAULT '{}'::jsonb,
                    flags JSONB DEFAULT '[]'::jsonb,
                    coinage INTEGER NOT NULL DEFAULT 0,
                    shop_buy_filter JSONB DEFAULT '[]'::jsonb,
                    shop_sell_modifier REAL NOT NULL DEFAULT 0.5,
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
                    resistances JSONB DEFAULT '{}'::jsonb,
                    max_hp INTEGER NOT NULL DEFAULT 10,
                    max_coinage INTEGER NOT NULL DEFAULT 0, -- Replaces coinage in loot
                    flags JSONB DEFAULT '[]'::jsonb,
                    respawn_delay_seconds INTEGER DEFAULT 300,
                    variance JSONB DEFAULT '{}'::jsonb,
                    movement_chance REAL NOT NULL DEFAULT 0.0,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS mob_attacks (
                        id SERIAL PRIMARY KEY,
                        mob_template_id INTEGER NOT NULL REFERENCES mob_templates(id) ON DELETE CASCADE,
                        name TEXT NOT NULL,
                        damage_base INTEGER DEFAULT 1,
                        damage_rng INTEGER DEFAULT 0,
                        speed REAL DEFAULT 2.0,
                        attack_type TEXT DEFAULT 'physical'
                    )
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS ability_templates (
                        id SERIAL PRIMARY KEY,
                        internal_name TEXT UNIQUE NOT NULL,
                        name TEXT NOT NULL,
                        ability_type TEXT NOT NULL,
                        class_req JSONB DEFAULT '[]'::jsonb,
                        level_req INTEGER DEFAULT 1,
                        cost INTEGER DEFAULT 0,
                        target_type TEXT,
                        effect_type TEXT,
                        effect_details JSONB DEFAULT '{}'::jsonb,
                        cast_time REAL DEFAULT 0.0,
                        roundtime REAL DEFAULT 1.0,
                        messages JSONB DEFAULT '{}'::jsonb,
                        description TEXT
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
                    CREATE TABLE IF NOT EXISTS damage_types (
                                   id SERIAL PRIMARY KEY,
                                   name TEXT UNIQUE NOT NULL,
                                   is_magical BOOLEAN NOT NULL DEFAULT FALSE
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
                        spiritual_tether INTEGER NOT NULL DEFAULT 3,
                        xp_pool REAL DEFAULT 0.0,
                        xp_total REAL DEFAULT 0.0,
                        status TEXT NOT NULL DEFAULT 'ALIVE',
                        stance TEXT NOT NULL DEFAULT 'Standing',
                        unspent_skill_points INTEGER NOT NULL DEFAULT 0,
                        unspent_attribute_points INTEGER NOT NULL DEFAULT 0,
                        location_id INTEGER DEFAULT 1,
                        coinage INTEGER NOT NULL DEFAULT 0,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        last_saved TIMESTAMPTZ,
                        total_playtime_seconds INTEGER NOT NULL DEFAULT 0,
                        UNIQUE (player_id, first_name, last_name)
                    )
                """)
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS character_stats (
                    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
                    might INTEGER NOT NULL DEFAULT 10,
                    vitality INTEGER NOT NULL DEFAULT 10,
                    agility INTEGER NOT NULL DEFAULT 10,
                    intellect INTEGER NOT NULL DEFAULT 10,
                    aura INTEGER NOT NULL DEFAULT 10,
                    persona INTEGER NOT NULL DEFAULT 10,
                    PRIMARY KEY (character_id)
                )
                """)
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS character_skills (
                    id SERIAL PRIMARY KEY,
                    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
                    skill_name TEXT NOT NULL, -- e.g., 'bladed weapons'
                    rank INTEGER NOT NULL DEFAULT 0,
                    UNIQUE (character_id, skill_name)
                )
                """)
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS character_abilities (
                    id SERIAL PRIMARY KEY,
                    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
                    ability_internal_name TEXT NOT NULL REFERENCES ability_templates(internal_name) ON DELETE CASCADE,
                    UNIQUE (character_id, ability_internal_name)
                )
                """)
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS exits (
                    id SERIAL PRIMARY KEY,
                    source_room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
                    direction TEXT NOT NULL, -- e.g., 'north', 'south'
                    destination_room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
                    details JSONB DEFAULT '{}'::jsonb, -- For locks, skill checks etc.
                    is_hidden BOOLEAN NOT NULL DEFAULT FALSE,
                    UNIQUE (source_room_id, direction)
                )
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS item_instances (
                        id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                        template_id INTEGER NOT NULL REFERENCES item_templates(id) ON DELETE CASCADE,
                        owner_char_id INTEGER REFERENCES characters(id) ON DELETE SET NULL,
                        room_id INTEGER REFERENCES rooms(id) ON DELETE SET NULL,
                        container_id UUID REFERENCES item_instances(id) ON DELETE SET NULL,
                        condition INTEGER NOT NULL DEFAULT 100,
                        instance_stats JSONB DEFAULT '{}'::jsonb,
                        last_moved_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        
                        CONSTRAINT single_location_check CHECK (
                             (owner_char_id IS NOT NULL AND room_id IS NULL AND container_id IS NULL) OR -- In top-level inventory/equipped
                             (owner_char_id IS NULL AND room_id IS NOT NULL AND container_id IS NULL) OR -- On the ground
                             (owner_char_id IS NULL AND room_id IS NULL AND container_id IS NOT NULL)    -- Inside another container
                        )
                    )
                """)
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS mob_loot_table (
                    id SERIAL PRIMARY KEY,
                    mob_template_id INTEGER NOT NULL REFERENCES mob_templates(id) ON DELETE CASCADE,
                    item_template_id INTEGER NOT NULL REFERENCES item_templates(id) ON DELETE CASCADE,
                    drop_chance REAL NOT NULL DEFAULT 1.0, -- e.g., 0.1 for 10%
                    min_quantity INTEGER NOT NULL DEFAULT 1,
                    max_quantity INTEGER NOT NULL DEFAULT 1
                )
                """)
                await conn.execute("""
                CREATE TABLE IF NOT EXISTS character_equipment (
                    character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE PRIMARY KEY,
                    head UUID REFERENCES item_instances(id) ON DELETE SET NULL,
                    torso UUID REFERENCES item_instances(id) ON DELETE SET NULL,
                    legs UUID REFERENCES item_instances(id) ON DELETE SET NULL,
                    feet UUID REFERENCES item_instances(id) ON DELETE SET NULL,
                    hands UUID REFERENCES item_instances(id) ON DELETE SET NULL,
                    main_hand UUID REFERENCES item_instances(id) ON DELETE SET NULL,
                    off_hand UUID REFERENCES item_instances(id) ON DELETE SET NULL
                    -- Add other slots as needed
                )
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS bank_accounts (
                        character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
                        balance BIGINT NOT NULL DEFAULT 0,
                        PRIMARY KEY (character_id)
                    )
                """)

                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS banked_items (
                        id SERIAL PRIMARY KEY,
                        character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
                        item_instance_id UUID NOT NULL UNIQUE REFERENCES item_instances(id) ON DELETE CASCADE,
                        stored_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    )
                """)

                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS game_economy (
                        key TEXT PRIMARY KEY,
                        value BIGINT NOT NULL DEFAULT 0
                    )
                """)
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS shop_inventories (
                        id SERIAL PRIMARY KEY,
                        room_id INTEGER NOT NULL REFERENCES rooms(id) ON DELETE CASCADE,
                        item_template_id INTEGER NOT NULL REFERENCES item_templates(id) ON DELETE CASCADE,
                        stock_quantity INTEGER NOT NULL DEFAULT -1, -- -1 for infinite stock
                        buy_price_modifier REAL NOT NULL DEFAULT 1.25, -- Default 25% markup
                        sell_price_modifier REAL NOT NULL DEFAULT 0.75, -- Default 25% markdown
                        
                        UNIQUE (room_id, item_template_id)
                    )
                """)
                # --- Junction/Instance Tables ---
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
                await conn.execute("""
                    CREATE TABLE IF NOT EXISTS loot_tables (
                                   id SERIAL PRIMARY KEY,
                                   name TEXT UNIQUE NOT NULL,
                                   description TEXT
                                   )
                """)
                await conn.execute("""
                                    CREATE TABLE IF NOT EXISTS loot_table_entries (
                                    id SERIAL PRIMARY KEY,
                                    loot_table_id INTEGER NOT NULL REFERENCES loot_tables(id) ON DELETE CASCADE,
                                    item_template_id INTEGER REFERENCES item_templates(id) ON DELETE SET NULL,
                                    min_coinage INTEGER DEFAULT 0,
                                    max_coinage INTEGER DEFAULT 0,
                                    drop_chance REAL NOT NULL DEFAULT 1.0,
                                    min_quantity INTEGER NOT NULL DEFAULT 1,
                                    max_quantity INTEGER NOT NULL DEFAULT 1
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
                                     [(1, "Warrior", "..."), (2, "Mage", "..."), (3, "Cleric", "..."), (4, "Rogue", "..."),
                                      (5, "Ranger", "A master of ranged combat and survival."),
                                      (6, "Barbarian", "A ferocious warrior who channels primal fury.")])
                # Areas & Rooms
                await conn.execute("INSERT INTO areas (id, name, description) VALUES ($1, $2, $3) ON CONFLICT (id) DO NOTHING", 1, "The Void", "...")
                await conn.execute("INSERT INTO rooms (id, area_id, name, description, flags) VALUES ($1, $2, $3, $4, $5) ON CONFLICT (id) DO NOTHING", 1, 1, "The Void", "...", json.dumps(["NODE", "RESPAWN"]))
                # Test Players
                await conn.execute("INSERT INTO players (username, hashed_password, email, is_admin) VALUES ($1, $2, $3, $4) ON CONFLICT (username) DO NOTHING", "tester", utils.hash_password("password"), "tester@example.com", False)
                await conn.execute("INSERT INTO players (username, hashed_password, email, is_admin) VALUES ($1, $2, $3, $4) ON CONFLICT (username) DO NOTHING", "admin", utils.hash_password("password"), "admin@example.com", True)
                # Seed Damage Types
                damage_types_to_seed = [
                    ('slash', False), ('pierce', False), ('bludgeon', False),
                    ('fire', True), ('cold', True), ('lightning', True),
                    ('earth', True), ('arcane', True), ('divine', True),
                    ('poison', True), ('sonic', True)
                ]
                await conn.executemany(
                    "INSERT INTO damage_types (name, is_magical) VALUES ($1, $2) ON CONFLICT (name) DO NOTHING",
                    damage_types_to_seed
                )
                #--- Seed Ability Templates ---
                log.info("Seeding ability templates...")
                log.info("Seeding ability templates...")
                ability_records = []
                for key, data in ability_defs.ABILITIES_DATA.items():
                    ability_records.append((
                        key, data.get('name'), data.get('type'),
                        # --- FIX: All JSONB fields must be manually converted to strings for executemany ---
                        json.dumps(data.get('class_req', [])), 
                        data.get('level_req', 1),
                        data.get('cost', 0), data.get('target_type'), data.get('effect_type'),
                        json.dumps(data.get('effect_details', {})), 
                        data.get('cast_time', 0.0),
                        data.get('roundtime', 1.0), 
                        json.dumps(data.get('messages', {})),
                        data.get('description')
                    ))
                await conn.executemany("""
                    INSERT INTO ability_templates (
                        internal_name, name, ability_type, class_req, level_req, cost,
                        target_type, effect_type, effect_details, cast_time, roundtime,
                        messages, description
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                    ON CONFLICT (internal_name) DO UPDATE SET
                        name = EXCLUDED.name,
                        ability_type = EXCLUDED.ability_type,
                        class_req = EXCLUDED.class_req,
                        level_req = EXCLUDED.level_req,
                        cost = EXCLUDED.cost,
                        target_type = EXCLUDED.target_type,
                        effect_type = EXCLUDED.effect_type,
                        effect_details = EXCLUDED.effect_details,
                        cast_time = EXCLUDED.cast_time,
                        roundtime = EXCLUDED.roundtime,
                        messages = EXCLUDED.messages,
                        description = EXCLUDED.description;
                """, ability_records)
                
        log.info("--- PostgreSQL schema check complete ---")

    # --- Item Instance Management Functions ---
    async def create_item_instance(self, template_id: int, room_id: Optional[int] = None, owner_char_id: Optional[int] = None, container_id: Optional[str] = None, instance_stats: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        """
        Creates a new, unique instance of an item in the database.
        Returns the new instance's data as a dictionary.
        """
        new_id = str(uuid.uuid4())
        stats_json = json.dumps(instance_stats) if instance_stats else None

        query = """
            INSERT INTO item_instances (id, template_id, owner_char_id, room_id, container_id, instance_stats)
            VALUES ($1, $2, $3, $4, $5, $6)
            RETURNING *;
        """
        try:
            # This call will now work because fetch_one_query is defined above.
            record = await self.fetch_one_query(query, new_id, template_id, owner_char_id, room_id, container_id, stats_json)
            return dict(record) if record else None
        except Exception:
            log.exception("Database error while creating item instance for template %d", template_id)
            return None
        
    async def fetch_loot_table_entries(self, loot_table_id: int) -> List[Dict[str, Any]]:
        """
        Fetches all loot table entries associated with a given ID.
        """
        query = "SELECT * FROM mob_loot_table WHERE mob_template_id = $1"
        records = await self.fetch_all_query(query, loot_table_id)
        return [dict(record) for record in records]
    
    async def get_item_instance(self, instance_id: str) -> Optional[asyncpg.Record]:
        """Retrives a single item instance by its UUID."""
        query = "SELECT * FROM item_instances WHERE id = $1"
        return await self.fetch_one_query(query, instance_id)
    
    async def get_instances_in_room(self, room_id: int) -> List[asyncpg.Record]:
        """Fetches all item instances on the ground in a room."""
        query ="SELECT * FROM item_instances WHERE room_id = $1"
        return await self.fetch_all_query(query, room_id)
    
    async def get_instances_for_character(self, character_id: int) -> List[asyncpg.Record]:
        """Fetches all item instances owned by a character (inventory/equipment)."""
        query = "SELECT * FROM item_instances WHERE owner_char_id = $1"
        return await self.fetch_all_query(query, character_id)
    
    async def update_item_location(self, instance_id: str, room_id: Optional[int] = None,
                               owner_char_id: Optional[int] = None, container_id: Optional[str] = None) -> str:
        """Moves an item by changing its owner, room, or container location."""
        # --- UPDATE THIS FUNCTION ---
        # When an item is dropped (room_id is set), update its timestamp.
        if room_id is not None:
            query = "UPDATE item_instances SET room_id = $1, owner_char_id = $2, container_id = $3, last_moved_at = NOW() WHERE id = $4"
        else:
            query = "UPDATE item_instances SET room_id = $1, owner_char_id = $2, container_id = $3 WHERE id = $4"
        return await self.execute_query(query, room_id, owner_char_id, container_id, instance_id)
    
    async def delete_item_instance(self, instance_id: str) -> str:
        """Permanently deletes an item instance from the world."""
        query = "DELETE FROM item_instances WHERE id = $1"
        return await self.execute_query(query, instance_id)

    # --- Creator Functions (for seeding and building) ---
    async def create_item_template(self, name: str, item_type: str, description: str, stats: dict, flags: list, damage_type: Optional[str]) -> Optional[int]:
        query = "INSERT INTO item_templates (name, type, description, stats, flags, damage_type) VALUES ($1, $2, $3, $4, $5, $6) RETURNING id"
        record = await self.fetch_one_query(query, name, item_type, description, json.dumps(stats), json.dumps(flags), damage_type)
        return record['id'] if record else None

    async def create_mob_template(self, name: str, level: int, description: str, stats: dict, attacks: list, loot: dict, flags: list) -> Optional[int]:
        query = "INSERT INTO mob_templates (name, level, description, stats, attacks, loot, flags) VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id"
        record = await self.fetch_one_query(query, name, level, description, json.dumps(stats), json.dumps(attacks), json.dumps(loot), json.dumps(flags))
        return record['id'] if record else None

    async def update_room_exits(self, room_id: int, exits: dict) -> str:
        query = "UPDATE rooms SET exits = $1 WHERE id = $2"
        return await self.execute_query(query, json.dumps(exits), room_id)

    # --- Player Functions ---
    async def load_player_account(self, username: str) -> Optional[asyncpg.Record]:
        query = "SELECT * FROM players WHERE lower(username) = lower($1)"
        return await self.fetch_one_query(query, username)
    
    async def create_player_account(self, username: str, hashed_password: str, email: str) -> Optional[int]:
        query = "INSERT INTO players (username, hashed_password, email, last_login) VALUES ($1, $2, $3, NOW()) RETURNING id"
        record = await self.fetch_one_query(query, username, hashed_password, email)
        return record['id'] if record else None

    # --- Character Functions ---
    async def load_characters_for_account(self, player_id: int) -> List[asyncpg.Record]:
        query = "SELECT id, first_name, last_name, level, race_id, class_id FROM characters WHERE player_id = $1 ORDER BY last_saved DESC NULLS LAST, id ASC"
        return await self.fetch_all_query(query, player_id)
    
    async def load_character_data(self, character_id: int) -> Optional[asyncpg.Record]:
        query = "SELECT * FROM characters WHERE id = $1"
        return await self.fetch_one_query(query, character_id)
    
    async def create_character(self, player_id: int, first_name: str, last_name: str, sex: str,
                           race_id: int, class_id: int, class_name: str, stats: dict,
                           description: str, hp: float, max_hp: float, essence: float,
                           max_essence: float, spiritual_tether: int) -> Optional[int]:
        """Creates a new character and all associated relational data in a single transaction."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Step 1: Insert into the main characters table
                char_query = """
                INSERT INTO characters (
                    player_id, first_name, last_name, sex, race_id, class_id, description,
                    hp, max_hp, essence, max_essence, spiritual_tether, coinage
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13)
                RETURNING id
                """
                # --- FIX: Added 'spiritual_tether' to the end of this tuple ---
                char_params = (player_id, first_name, last_name, sex, race_id, class_id,
                            description, hp, max_hp, essence, max_essence, spiritual_tether, config.STARTING_COINAGE)
                
                record = await conn.fetchrow(char_query, *char_params)
                if not record:
                    return None
                new_char_id = record['id']

                # Step 2: Insert the initial stats record
                stats_query = """
                    INSERT INTO character_stats (character_id, might, vitality, agility, intellect, aura, persona)
                    VALUES ($1, $2, $3, $4, $5, $6, $7)
                """
                await conn.execute(stats_query, new_char_id, stats.get('might', 10),
                                stats.get('vitality', 10), stats.get('agility', 10),
                                stats.get('intellect', 10), stats.get('aura', 10),
                                stats.get('persona', 10))

                # Step 3: Insert a blank equipment record
                await conn.execute("INSERT INTO character_equipment (character_id) VALUES ($1)", new_char_id)

                # --- CLEANUP: Removed the duplicated, incorrect skill insertion logic ---

                # Step 4: Insert initial skills WITH class bonuses
                bonuses = class_defs.get_starting_skill_bonuses(class_name)
                initial_skill_data = [
                    (new_char_id, skill_name, bonuses.get(skill_name, 0))
                    for skill_name in skill_defs.INITIAL_SKILLS
                ]
                
                if initial_skill_data:
                    await conn.copy_records_to_table(
                    'character_skills',
                    columns=['character_id', 'skill_name', 'rank'],
                    records=initial_skill_data
                )
                
                return new_char_id
    
    async def save_character_core(self, character_id: int, data: dict) -> str:
        """Saves the core character data from the main 'characters' table."""
        if not data: return "UPDATE 0"
        set_clauses = [f"{key} = ${i+1}" for i, key in enumerate(data.keys())]
        params = list(data.values())
        params.append(character_id)
        query = f"UPDATE characters SET {', '.join(set_clauses)}, last_saved = NOW() WHERE id = ${len(params)}"
        return await self.execute_query(query, *params)

    async def save_character_stats(self, character_id: int, stats: dict) -> str:
        """Saves character stats using an INSERT ... ON CONFLICT (upsert) command."""
        query = """
            INSERT INTO character_stats (character_id, might, vitality, agility, intellect, aura, persona)
            VALUES ($1, $2, $3, $4, $5, $6, $7)
            ON CONFLICT (character_id) DO UPDATE SET
                might = EXCLUDED.might,
                vitality = EXCLUDED.vitality,
                agility = EXCLUDED.agility,
                intellect = EXCLUDED.intellect,
                aura = EXCLUDED.aura,
                persona = EXCLUDED.persona;
        """
        params = (
            character_id, stats.get('might', 10), stats.get('vitality', 10),
            stats.get('agility', 10), stats.get('intellect', 10),
            stats.get('aura', 10), stats.get('persona', 10)
        )
        return await self.execute_query(query, *params)
    
    async def save_character_skills(self, character_id: int, skills: dict) -> str:
        """Saves character skills by deleting old ones and inserting the new set."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM character_skills WHERE character_id = $1", character_id)
                if not skills:
                    return "DELETE" # No new skills to add
                
                skill_records = [(character_id, name, rank) for name, rank in skills.items()]
                await conn.copy_records_to_table(
                    'character_skills',
                    columns=['character_id', 'skill_name', 'rank'],
                    records=skill_records
                )
        return "COPY"

    async def save_character_equipment(self, character_id: int, equipment: dict) -> str:
        """Saves character equipment using an upsert."""
        query = """
            INSERT INTO character_equipment (character_id, head, torso, legs, feet, hands, main_hand, off_hand)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
            ON CONFLICT (character_id) DO UPDATE SET
                head = EXCLUDED.head,
                torso = EXCLUDED.torso,
                legs = EXCLUDED.legs,
                feet = EXCLUDED.feet,
                hands = EXCLUDED.hands,
                main_hand = EXCLUDED.main_hand,
                off_hand = EXCLUDED.off_hand;
        """
        params = (
            character_id, equipment.get('head'), equipment.get('torso'), equipment.get('legs'),
            equipment.get('feet'), equipment.get('hands'), equipment.get('main_hand'),
            equipment.get('off_hand')
        )
        return await self.execute_query(query, *params)

    async def save_character_full(self, char_id: int, core_data: dict, stats: dict, skills: dict, equipment: dict, abilities: Set[str]) -> bool:
        """
        Saves all components of a character's state in a single, atomic transaction.
        Returns True on success, False on failure.
        """
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                try:
                    # 1. Save Core Data
                    if core_data:
                        set_clauses = [f"{key} = ${i+1}" for i, key in enumerate(core_data.keys())]
                        params = list(core_data.values())
                        params.append(char_id)
                        query = f"UPDATE characters SET {', '.join(set_clauses)}, last_saved = NOW() WHERE id = ${len(params)}"
                        await conn.execute(query, *params)

                    # 2. Save Stats (Upsert)
                    if stats:
                        stats_query = """
                            INSERT INTO character_stats (character_id, might, vitality, agility, intellect, aura, persona)
                            VALUES ($1, $2, $3, $4, $5, $6, $7)
                            ON CONFLICT (character_id) DO UPDATE SET
                                might = EXCLUDED.might, vitality = EXCLUDED.vitality, agility = EXCLUDED.agility,
                                intellect = EXCLUDED.intellect, aura = EXCLUDED.aura, persona = EXCLUDED.persona;
                        """
                        await conn.execute(stats_query, char_id, stats.get('might', 10), stats.get('vitality', 10),
                                           stats.get('agility', 10), stats.get('intellect', 10), stats.get('aura', 10),
                                           stats.get('persona', 10))

                    # 3. Save Skills (Delete-then-Insert)
                    if skills is not None: # Allow saving an empty skill set
                        await conn.execute("DELETE FROM character_skills WHERE character_id = $1", char_id)
                        if skills:
                            skill_records = [(char_id, name, rank) for name, rank in skills.items()]
                            await conn.copy_records_to_table('character_skills',
                                                             columns=['character_id', 'skill_name', 'rank'],
                                                             records=skill_records)

                    # 4. Save Equipment (Upsert)
                    if equipment:
                        equip_query = """
                            INSERT INTO character_equipment (character_id, head, torso, legs, feet, hands, main_hand, off_hand)
                            VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                            ON CONFLICT (character_id) DO UPDATE SET
                                head = EXCLUDED.head, torso = EXCLUDED.torso, legs = EXCLUDED.legs, feet = EXCLUDED.feet,
                                hands = EXCLUDED.hands, main_hand = EXCLUDED.main_hand, off_hand = EXCLUDED.off_hand;
                        """
                        await conn.execute(equip_query, char_id, equipment.get('head'), equipment.get('torso'),
                                           equipment.get('legs'), equipment.get('feet'), equipment.get('hands'),
                                           equipment.get('main_hand'), equipment.get('off_hand'))
                    
                    # 5. Save Abilities (Delete-then-Insert)
                    if abilities is not None:
                        await conn.execute("DELETE FROM character_abilities WHERE character_id = $1", char_id)
                        if abilities:
                            ability_records = [(char_id, name) for name in abilities]
                            await conn.copy_records_to_table('character_abilities',
                                                             columns=['character_id', 'ability_internal_name'],
                                                             records=ability_records)
                    return True
                except Exception:
                    log.exception(f"Transaction failed for saving character {char_id}. Rolling back.")
                    # The transaction will automatically roll back on exception
                    return False
    
    async def get_character_stats(self, character_id: int) -> Optional[asyncpg.Record]:
        """Fetches the core stats for a character."""
        query = "SELECT * FROM character_stats WHERE character_id = $1"
        return await self.fetch_one_query(query, character_id)

    async def get_character_skills(self, character_id: int) -> List[asyncpg.Record]:
        """Fetches all skills for a character."""
        query = "SELECT skill_name, rank FROM character_skills WHERE character_id = $1"
        return await self.fetch_all_query(query, character_id)

    async def get_character_equipment(self, character_id: int) -> Optional[asyncpg.Record]:
        """Fetches the equipment for a character."""
        query = "SELECT * FROM character_equipment WHERE character_id = $1"
        return await self.fetch_one_query(query, character_id)
    
    async def get_character_abilities(self, character_id: int) -> Set[str]:
        """
        Fetches all known abilities for a character and returns them as a set of strings.
        """
        query = "SELECT ability_internal_name FROM character_abilities WHERE character_id = $1"
        
        # First, fetch the raw database records
        ability_records = await self.fetch_all_query(query, character_id)
        
        # ✅ FIX: Process the records into a set of strings before returning.
        # This ensures the function returns the data type the game expects,
        # restoring the original behavior.
        if not ability_records:
            return set()
            
        return {record['ability_internal_name'] for record in ability_records}
    
    async def save_character_abilities(self, character_id: int, abilities: Set[str]) -> str:
        """Saves character abilities by deleting old ones and inserting the new set."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute("DELETE FROM character_abilities WHERE character_id = $1", character_id)
                if not abilities:
                    return "DELETE"
                
                ability_records = [(character_id, name) for name in abilities]
                await conn.copy_records_to_table(
                    'character_abilities',
                    columns=['character_id', 'ability_internal_name'],
                    records=ability_records
                )

    async def update_character_playtime(self, character_id: int, session_seconds: int) -> str:
        """Adds the session duration to the character's total playtime."""
        query = "UPDATE characters SET total_playtime_seconds = total_playtime_seconds + $1 WHERE id = $2"
        return await self.execute_query(query, session_seconds, character_id)
    
    # --- Item Functions and Economy
    async def update_shop_stock(self, shop_inventory_id: int, quantity_change: int):
        """Updates the stock for an item in a shop's inventory"""
        query = """
            UPDATE shop_inventories
            SET stock_quantity = stock_quantity + $1
            WHERE id = $2 AND stock_quantity != -1
            """
        return await self.execute_query(query, quantity_change, shop_inventory_id)
    
    async def get_character_balance(self, character_id: int) -> int:
        """Fetches the coin balance for a character's bank account."""
        query = "SELECT balance FROM bank_accounts WHERE character_id = $1"
        record = await self.fetch_one_query(query, character_id)
        return record['balance'] if record else 0
    
    async def update_character_balance(self, character_id: int, amount_change: int) -> str:
        """Updates a character's bank balance, creating an account if needed."""
        query = """
            INSERT INTO bank_accounts (character_id, balance)
            VALUES ($1, $2)
            ON CONFLICT (character_id)
            DO UPDATE SET balance = bank_accounts.balance + $2;
        """
        return await self.execute_query(query, character_id, amount_change)
    
    async def bank_item(self, character_id: int, item_instance_id: str) -> bool:
        """Moves an item from a character's inventory into their bank box."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # Remove the item from any in-world location
                status = await conn.execute(
                    "UPDATE item_instances SET owner_char_id = NULL WHERE id = $1",
                    item_instance_id
                )
                if "UPDATE 1" not in status:
                    # Rollback the transaction
                    return False
                
                # Add the item to the bank
                await conn.execute(
                    "INSERT INTO banked_items (character_id, item_instance_id) VALUES ($1, $2)",
                    character_id, item_instance_id
                )
        return True
    
    async def find_banked_item_for_character(self, character_id: int, item_name: str) -> Optional[dict]:
        """Finds a banked item for a character by its name via a JOIN."""
        query = """
            SELECT inst.*
            FROM banked_items AS bank
            JOIN item_instances AS inst ON bank.item_instance_id = inst.id
            JOIN item_templates AS tmpl ON inst.template_id = tmpl.id
            WHERE bank.character_id = $1 AND lower(tmpl.name) LIKE lower($2)
            LIMIT 1;
            """
        # Add wildcards for partial name matching
        search_pattern = f"%{item_name}"
        record = await self.fetch_one_query(query, character_id, search_pattern)
        return dict(record) if record else None

    async def unbank_item(self, character_id: int, item_instance_id: str) -> bool:
        """Moves an item from a character's bank box to their inventory."""
        async with self.pool.acquire() as conn:
            async with conn.transaction():
                # remove the item from the bank
                status = await conn.execute(
                    "DELETE FROM banked_items WHERE character_id = $1 AND item_instance_id = $2",
                    character_id, item_instance_id)
                if "DELETE 1" not in status:
                    return False
                
                # Assign the item to the character
                await conn.execute(
                    "UPDATE item_instances SET owner_char_id = $1 WHERE id = $2",
                    character_id, item_instance_id
                )
                return True
            
    async def update_item_condition(self, instance_id: str, new_condition: int) -> str:
        """Updates the condition of a single item instance."""
        query = "UPDATE item_instances SET condition = $1 WHERE id = $2"
        return await self.execute_query(query, new_condition, instance_id)
    
    async def update_item_instance_stats(self, instance_id: str, new_stats: dict) -> str:
        """Updates the instance_stats JSONB field for a specific item instance."""
        query = "UPDATE item_instances SET instance_stats = $1 WHERE id = $2"
        return await self.execute_query(query, json.dumps(new_stats), instance_id)
    
db_manager = DatabaseManager()