ALTER TABLE areas ADD COLUMN climate TEXT NOT NULL DEFAULT 'temperate' CHECK(climate IN ('temperate','coastal','arid','arctic','tropical'));
