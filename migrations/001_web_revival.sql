-- Additive migration; never replaces existing characters or world content.
CREATE TABLE IF NOT EXISTS web_sessions (
 token_hash TEXT PRIMARY KEY, player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,
 expires_at TIMESTAMPTZ NOT NULL DEFAULT now() + interval '12 hours'
);
CREATE INDEX IF NOT EXISTS web_sessions_expiry ON web_sessions(expires_at);
CREATE TABLE IF NOT EXISTS builder_audit (
 id BIGSERIAL PRIMARY KEY, player_id INTEGER REFERENCES players(id) ON DELETE SET NULL,
 action TEXT NOT NULL, entity TEXT NOT NULL, entity_id TEXT,
 details JSONB NOT NULL DEFAULT '{}', created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS resource_nodes (
 id SERIAL PRIMARY KEY, room_id INTEGER NOT NULL REFERENCES rooms(id),
 name TEXT NOT NULL UNIQUE, item_template_id INTEGER NOT NULL REFERENCES item_templates(id),
 capacity INTEGER NOT NULL DEFAULT 5 CHECK (capacity > 0),
 remaining INTEGER NOT NULL DEFAULT 5 CHECK (remaining >= 0),
 respawn_seconds INTEGER NOT NULL DEFAULT 300 CHECK (respawn_seconds > 0),
 depleted_at TIMESTAMPTZ
);
CREATE TABLE IF NOT EXISTS recipes (
 id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL, description TEXT NOT NULL DEFAULT '',
 station_room_id INTEGER REFERENCES rooms(id),
 output_template_id INTEGER NOT NULL REFERENCES item_templates(id),
 ingredients JSONB NOT NULL DEFAULT '{}' CHECK (jsonb_typeof(ingredients) = 'object')
);
CREATE TABLE IF NOT EXISTS npc_schedules (
 id SERIAL PRIMARY KEY, mob_template_id INTEGER NOT NULL REFERENCES mob_templates(id),
 day_room_id INTEGER NOT NULL REFERENCES rooms(id), night_room_id INTEGER NOT NULL REFERENCES rooms(id),
 greeting TEXT NOT NULL, lore TEXT NOT NULL DEFAULT '', UNIQUE(mob_template_id)
);
CREATE TABLE IF NOT EXISTS relics (
 id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL, lore TEXT NOT NULL,
 room_id INTEGER NOT NULL REFERENCES rooms(id), template_id INTEGER NOT NULL REFERENCES item_templates(id),
 claimed_by INTEGER REFERENCES characters(id), claimed_at TIMESTAMPTZ,
 instance_id UUID UNIQUE REFERENCES item_instances(id)
);
CREATE TABLE IF NOT EXISTS character_journal (
 id BIGSERIAL PRIMARY KEY, character_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,
 entry TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS journal_character ON character_journal(character_id,id);
CREATE INDEX IF NOT EXISTS instances_owner ON item_instances(owner_char_id);
CREATE INDEX IF NOT EXISTS instances_room ON item_instances(room_id);
CREATE INDEX IF NOT EXISTS instances_container ON item_instances(container_id);
CREATE INDEX IF NOT EXISTS characters_account ON characters(player_id);
