ALTER TABLE players ADD COLUMN email_verified BOOLEAN NOT NULL DEFAULT true;
CREATE TABLE account_tokens(token_hash TEXT PRIMARY KEY,player_id INTEGER NOT NULL REFERENCES players(id) ON DELETE CASCADE,purpose TEXT NOT NULL CHECK(purpose IN ('reset','verify')),expires_at TIMESTAMPTZ NOT NULL DEFAULT now()+interval '30 minutes');
