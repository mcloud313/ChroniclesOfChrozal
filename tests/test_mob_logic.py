# tests/test_mob_logic.py
import unittest
from unittest.mock import Mock, patch, AsyncMock
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from game.mob import Mob
from game import combat

# FIX 1: Use a single, async-compatible test class for all tests in this file.
class TestMobLogic(unittest.IsolatedAsyncioTestCase):
    """Test suite for Mob creation, loot, and basic AI."""

    def setUp(self):
        """Set up a mock room and mob template for use in tests."""
        self.mob_template = {
            "id": 1,
            "name": "a giant rat",
            "description": "A large, filthy rat.",
            "level": 1,
            "stats": '{"might": 12, "vitality": 10}',
            "max_hp": 20,
            "variance": '{"max_hp_pct": 10, "stats_pct": 10}',
            "attacks": '[]',
            "loot": '{}',
            "flags": '["AGGRESSIVE"]'
        }

    @patch('random.uniform')
    def test_mob_spawns_with_variance(self, mock_uniform):
        """Tests that a mob's stats are varied upon creation."""
        mock_uniform.return_value = 0.10
        mob = Mob(self.mob_template, Mock())
        self.assertEqual(mob.max_hp, 22)
        self.assertEqual(mob.stats['might'], 13)

    def test_mob_loot_drop(self):
        """Tests that loot drops according to a 100% chance."""
        loot_table = {
            "coinage_max": 50,
            "items": [
                {"template_id": 101, "chance": 1.0},
                {"template_id": 102, "chance": 0.0}
            ]
        }
        dropped_coinage, dropped_items = combat.determine_loot(loot_table)
        self.assertGreaterEqual(dropped_coinage, 0)
        self.assertIn(101, dropped_items)
        self.assertNotIn(102, dropped_items)

    async def test_mob_aggressive_ai_finds_target(self):
        """Tests that an aggressive mob targets a player in the same room."""
        # Setup
        mock_room = Mock()
        # FIX 2: Configure the room's 'broadcast' method to be an async mock
        mock_room.broadcast = AsyncMock()

        mob = Mob(self.mob_template, mock_room)
        mock_character = Mock()
        mock_character.is_alive.return_value = True
        
        # Place the character in the room's character list
        mock_room.characters = {mock_character}
        
        # Run the AI tick
        await mob.simple_ai_tick(dt=1.0, world=Mock())
        
        # Verify
        self.assertTrue(mob.is_fighting)
        self.assertEqual(mob.target, mock_character)