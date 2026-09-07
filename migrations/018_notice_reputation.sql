ALTER TABLE board_notices ADD COLUMN faction_id INTEGER REFERENCES factions(id);
ALTER TABLE board_notices ADD COLUMN required_standing INTEGER NOT NULL DEFAULT 0;
ALTER TABLE board_notices ADD COLUMN reputation_reward INTEGER NOT NULL DEFAULT 0;
