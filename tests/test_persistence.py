# tests/test_persistence.py
import unittest
from unittest.mock import Mock, AsyncMock, MagicMock
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from game.world import World
from game.character import Character
from game.item import Item

class TestPersistence(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_db_manager = AsyncMock()
        mock_writer = MagicMock()
        mock_writer.drain = AsyncMock()
        self.mock_world = World(self.mock_db_manager)
        
        
        # Create a character with some data
        char_data = {
        "id": 1, "player_id": 1, "first_name": "Saver", "last_name": "Test", 
        "sex": "Male", "race_id": 1, "class_id": 1, "level": 5, 
        "description": "", "hp": 50, "max_hp": 50, "essence": 20, "max_essence": 20,
        "xp_pool": 0, "xp_total": 0, "unspent_skill_points": 0, "unspent_attribute_points": 0,
        "spiritual_tether": 1, "coinage": 100, "location_id": 1, "total_playtime_seconds": 0,
        "status": "ALIVE", "stance": "Standing"
    }
        self.character = Character(mock_writer, char_data, self.mock_world)

        self.character.stats = {"might": 15, "vitality": 12}
        self.character.skills = {"bladed weapons": 25}

       

    async def test_character_save_calls_correct_db_methods(self):
        """Verify that character.save() calls the new, granular database functions."""
        # Action: Call the save method
        await self.character.save()

        # Assert: Check that our new database helpers were called
        self.mock_db_manager.save_character_core.assert_called_once()
        self.mock_db_manager.save_character_stats.assert_called_once()
        self.mock_db_manager.save_character_skills.assert_called_once()
        self.mock_db_manager.save_character_equipment.assert_called_once()

        # You can get more specific and check the data that was passed
        stats_call_args = self.mock_db_manager.save_character_stats.call_args[0]
        self.assertEqual(stats_call_args[0], 1) # character_id
        self.assertEqual(stats_call_args[1]['might'], 15) # stats dictionary

    async def test_character_load_populates_data_correctly(self):
        """Verify that character.load_related_data() correctly populates the character."""
        # Arrange: Configure the mock DB to return data for our new tables
        self.mock_db_manager.get_character_stats.return_value = {"character_id": 1, "might": 18, "vitality": 14}
        self.mock_db_manager.get_character_skills.return_value = [
            {"skill_name": "bladed weapons", "rank": 50},
            {"skill_name": "dodge", "rank": 25}
        ]
        # For this test, we don't need equipment or items, so we can return empty values
        self.mock_db_manager.get_character_equipment.return_value = None
        self.mock_db_manager.get_instances_for_character.return_value = []

        # Action: Call the loading method
        await self.character.load_related_data()

        # Assert: Check that the character object was populated correctly
        self.assertEqual(self.character.stats['might'], 18)
        self.assertEqual(self.character.skills['bladed weapons'], 50)
        self.assertEqual(self.character.skills['dodge'], 25)