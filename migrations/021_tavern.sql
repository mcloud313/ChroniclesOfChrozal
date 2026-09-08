CREATE TABLE tavern_hands (
 character_id INTEGER PRIMARY KEY REFERENCES characters(id) ON DELETE CASCADE,
 room_id INTEGER NOT NULL REFERENCES rooms(id), bet INTEGER NOT NULL CHECK(bet BETWEEN 1 AND 10),
 state JSONB NOT NULL, settled BOOLEAN NOT NULL DEFAULT false,
 played_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE tavern_ledger (
 id BIGSERIAL PRIMARY KEY, character_id INTEGER REFERENCES characters(id) ON DELETE SET NULL,
 game TEXT NOT NULL, stake INTEGER NOT NULL, payout INTEGER NOT NULL,
 details TEXT NOT NULL, created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX tavern_ledger_character_time ON tavern_ledger(character_id,created_at);
