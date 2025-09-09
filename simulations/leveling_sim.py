# simulations/leveling_sim.py
"""
A standalone script to simulate a character leveling from 1 to 100
to validate the XP curve and stat progression.
"""
import sys
import os
from unittest.mock import Mock

# Add project root to the path to allow imports
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from game.character import Character
from game import utils
import config

def run_simulation():
    """Creates a mock character and levels them up to MAX_LEVEL."""
    print("--- Running Character Leveling Simulation ---")

    # 1. Create a mock character
    mock_writer = Mock()
    mock_world = Mock()
    char_data = {
        "id": 1, "player_id": 1, "first_name": "Sim", "last_name": "Test",
        "sex": "Male", "race_id": 1, "class_id": 1, "level": 1,
        "hp": 15.0, "max_hp": 15.0, "essence": 12.0, "max_essence": 12.0,
        "stats": {"might": 15, "vitality": 15, "aura": 12, "persona": 12}, "skills": {},
        # Add other required fields...
        "equipment": {}, "status": "ALIVE", "stance": "Standing", "xp_pool": 0, "xp_total": 0,
        "unspent_skill_points": 0, "unspent_attribute_points": 0, "spiritual_tether": 1,
        "description": "", "coinage": 0, "location_id": 1, "total_playtime_seconds": 0,
        "known_spells": [], "known_abilities": [], "inventory": []
    }
    character = Character(mock_writer, char_data, mock_world)

    print(f"Starting as Level {character.level} Warrior with {character.max_hp} HP / {character.max_essence} Essence.")

    # 2. Loop from level 1 to MAX_LEVEL - 1
    for i in range(1, config.MAX_LEVEL):
        # Give character exactly enough XP for the next level
        xp_needed = utils.xp_needed_for_level(character.level)
        character.xp_total = xp_needed
        
        # Simulate the 'advance' command
        character.level += 1
        character.unspent_skill_points += config.SKILL_POINTS_PER_LEVEL
        if character.level % 4 == 0:
            character.unspent_attribute_points += 1
        
        hp_gain, essence_gain = character.apply_level_up_gains()
        
        print(f"LEVEL UP! -> Lvl {character.level}: "
              f"MaxHP={int(character.max_hp)} (+{int(hp_gain)}), "
              f"MaxEss={int(character.max_essence)} (+{int(essence_gain)}), "
              f"XP for next Lvl={utils.xp_needed_for_level(character.level)}")
    
    print("\n--- Simulation Complete ---")

if __name__ == "__main__":
    run_simulation()