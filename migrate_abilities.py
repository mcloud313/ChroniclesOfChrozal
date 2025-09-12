# migrate_abilities.py
import asyncio
import asyncpg
import json
from game.definitions.abilities import ABILITIES_DATA

# Your database connection details
DB_CONFIG = {
    "user": "chrozal",
    "password": "timcp313",
    "database": "chrozaldb",
    "host": "localhost"
}

async def main():
    conn = await asyncpg.connect(**DB_CONFIG)
    print("Connected to database. Migrating abilities...")
    
    for key, data in ABILITIES_DATA.items():
        print(f"  -> Migrating '{key}'...")
        
        # This query will insert a new ability or update an existing one if the name matches
        query = """
            INSERT INTO ability_templates (
                internal_name, name, ability_type, class_req, level_req, cost, 
                target_type, effect_type, effect_details, cast_time, roundtime, 
                messages, description
            ) VALUES (
                $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11, $12, $13
            )
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
        """
        
        # Handle the inconsistent 'class' vs 'class_req' key
        class_req = data.get("class_req")
        if class_req is None and (cls := data.get("class")):
             class_req = [cls.lower()]
        
        await conn.execute(
            query,
            key,
            data.get("name"),
            data.get("type"),
            json.dumps(class_req or []),
            data.get("level_req"),
            data.get("cost"),
            data.get("target_type"),
            data.get("effect_type"),
            json.dumps(data.get("effect_details", {})),
            data.get("cast_time"),
            data.get("roundtime"),
            json.dumps(data.get("messages", {})),
            data.get("description")
        )
        
    await conn.close()
    print("Migration complete!")

if __name__ == "__main__":
    asyncio.run(main())