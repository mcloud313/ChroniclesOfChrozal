ALTER TABLE rooms ADD COLUMN map_x DOUBLE PRECISION;
ALTER TABLE rooms ADD COLUMN map_y DOUBLE PRECISION;
INSERT INTO classes(id,name,description) VALUES(11,'Runewarden','A guardian who etches protective runes and channels the memory of stone.') ON CONFLICT DO NOTHING;
SELECT setval(pg_get_serial_sequence('classes','id'),GREATEST((SELECT max(id) FROM classes),1));
CREATE TABLE harvest_claims(token TEXT PRIMARY KEY,character_id INTEGER REFERENCES characters(id) ON DELETE SET NULL,created_at TIMESTAMPTZ DEFAULT now());
ALTER TABLE player_homes ADD COLUMN room_id INTEGER REFERENCES rooms(id);
