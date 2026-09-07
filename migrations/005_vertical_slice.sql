CREATE TABLE IF NOT EXISTS quests (
 id SERIAL PRIMARY KEY, name TEXT UNIQUE NOT NULL, description TEXT NOT NULL,
 min_level INTEGER NOT NULL CHECK(min_level BETWEEN 1 AND 100),
 giver_room_id INTEGER NOT NULL REFERENCES rooms(id),
 objectives JSONB NOT NULL CHECK(jsonb_typeof(objectives)='array'),
 reward_xp INTEGER NOT NULL CHECK(reward_xp>=0), reward_coinage INTEGER NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS character_quests (
 character_id INTEGER REFERENCES characters(id) ON DELETE CASCADE,
 quest_id INTEGER REFERENCES quests(id), progress JSONB NOT NULL DEFAULT '{}',
 status TEXT NOT NULL DEFAULT 'active' CHECK(status IN ('active','complete')),
 PRIMARY KEY(character_id,quest_id)
);
