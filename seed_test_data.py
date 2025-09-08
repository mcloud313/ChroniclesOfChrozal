# seed_test_data.py
"""
A standalone script to populate the PostgreSQL database with test data.
Run this *after* running server.py once to initialize the schema.
"""
import asyncio
from game.database import db_manager

async def main():
    """Connects to the DB and runs all seeding functions."""
    await db_manager.connect()
    
    try:
        print("--- Seeding test data ---")
        
        # Seed Items
        print("Seeding items...")
        sword_id = await db_manager.create_item_template(
            name="a rusty shortsword", item_type="WEAPON", description="A simple, weathered shortsword.",
            stats={"damage_base": 3, "damage_rng": 4, "speed": 2.5, "weight": 3},
            flags=["WIELDABLE"], damage_type="slash"
        )
        shield_id = await db_manager.create_item_template(
            name="a rickety wooden shield", item_type="SHIELD", description="A simple shield made of splintered wood.",
            stats={"armor": 2, "block_chance": 0.15, "weight": 5},
            flags=["WEARABLE"], damage_type=None
        )
        print(f"-> Created sword (ID: {sword_id}), shield (ID: {shield_id})")

        # Seed Mobs
        print("Seeding mobs...")
        rat_id = await db_manager.create_mob_template(
            name="a giant rat", level=1, description="A large, filthy rat with sharp teeth.",
            stats={"might": 12, "vitality": 12, "agility": 14},
            attacks=[{"name": "bite", "damage_base": 1, "damage_rng": 3, "speed": 2.0, "damage_type": "pierce"}],
            loot={"coinage_max": 10, "items": [{"template_id": sword_id, "chance": 0.05}]},
            flags=["AGGRESSIVE"]
        )
        print(f"-> Created giant rat (ID: {rat_id})")
        
        print("--- Seeding complete ---")

    except Exception as e:
        print(f"An error occurred during seeding: {e}")
    finally:
        await db_manager.close()

if __name__ == "__main__":
    asyncio.run(main())