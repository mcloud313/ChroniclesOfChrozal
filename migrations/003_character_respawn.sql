-- Character.save has always included this field; fresh schema omitted it.
ALTER TABLE characters ADD COLUMN IF NOT EXISTS respawn_room_id INTEGER NOT NULL DEFAULT 1;
