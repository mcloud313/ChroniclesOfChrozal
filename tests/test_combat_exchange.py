# tests/test_combat_exchange.py
import unittest
from unittest.mock import Mock, AsyncMock, patch, MagicMock
import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from game.world import World
from game.room import Room
from game.character import Character
from game.mob import Mob
from game.commands import combat as combat_cmds

class TestCombatExchange(unittest.IsolatedAsyncioTestCase):
    """Test suite for a full combat interaction."""

    def setUp(self):
        """Sets up a mini-game world for our test."""
        self.mock_db_manager = AsyncMock()
        self.mock_writer = MagicMock(spec=asyncio.StreamWriter)
        self.mock_writer.drain = AsyncMock()
        self.world = World(self.mock_db_manager)

        self.world.item_templates[1] = {
            'id': 1, 'name': 'a test sword', 'type': 'WEAPON', 'description': 'A test sword.',
            'stats': '{"damage_base": 5, "damage_rng": 3, "speed": 2.0}', 'damage_type': 'slash'
        }
        self.world.mob_templates[1] = {
            'id': 1, 'name': 'a test rat', 'level': 1, 'max_hp': 15, 'description': 'A furry pest.',
            'stats': '{"might": 10, "vitality": 10, "agility": 10}',
            'attacks': '[{"name": "bite", "damage_base": 1, "damage_rng": 2, "speed": 2.0}]',
            'flags': '[]', 'variance': '{}', 'loot': '{}'
        }
        
        room_data = { 'id': 1, 'area_id': 1, 'name': 'Test Arena', 'description': 'A simple test arena.' }
        self.room = Room(room_data)
        self.world.rooms[1] = self.room
        self.room.broadcast = AsyncMock()

        char_data = {
            "id": 1, "player_id": 1, "first_name": "Hero", "last_name": "Test", "sex": "Male",
            "race_id": 1, "class_id": 1, "level": 1, "hp": 50.0, "max_hp": 50.0,
            "essence": 50.0, "max_essence": 50.0, "stats": {"might": 15, "agility": 12, "vitality": 13}, 
            "skills": {}, "equipment": {'WIELD_MAIN': 1}, "status": "ALIVE", "stance": "Standing", 
            # (all other required fields with default values)
            "xp_pool": 0, "xp_total": 0, "unspent_skill_points": 0, "unspent_attribute_points": 0,
            "spiritual_tether": 1, "description": "", "coinage": 0, "location_id": 1,
            "total_playtime_seconds": 0, "known_spells": [], "known_abilities": [], "inventory": []
        }
        self.character = Character(self.mock_writer, char_data, self.world)

        mob_template = self.world.get_mob_template(1)
        self.mob = Mob(mob_template, self.room)

        self.room.add_character(self.character)
        self.character.update_location(self.room)
        self.room.add_mob(self.mob)

    @patch('random.randint')
    async def test_player_attacks_mob_and_hits(self, mock_randint):
        """Tests a single player attack from a command."""
        mock_randint.side_effect = [15, 2] # d20 roll, then d3 damage roll
        initial_mob_hp = self.mob.hp

        await combat_cmds.cmd_attack(self.character, self.world, "rat")

        self.assertLess(self.mob.hp, initial_mob_hp)
        self.assertTrue(self.character.is_fighting)
        self.assertTrue(self.mob.is_fighting)
        self.assertEqual(self.character.target, self.mob)
        self.assertEqual(self.mob.target, self.character)

    @patch('random.randint')
    async def test_full_combat_round(self, mock_randint):
        """
        Tests a full combat round: player attacks, then mob's AI retaliates.
        """
        # --- Arrange ---
        # Dice rolls: Player hit(18), Player dmg(3), Mob hit(16), Mob dmg(1)
        mock_randint.side_effect = [18, 3, 16, 1] 
        initial_char_hp = self.character.hp
        initial_mob_hp = self.mob.hp

        # --- Act ---
        # 1. Player initiates combat
        await combat_cmds.cmd_attack(self.character, self.world, "rat")
        
        # 2. Simulate the game ticker advancing, allowing the mob's AI to act
        #    (since the player has roundtime, but the mob does not)
        await self.mob.simple_ai_tick(dt=1.0, world=self.world)
        
        # --- Assert ---
        # Verify player's attack worked
        self.assertLess(self.mob.hp, initial_mob_hp)
        # Verify mob's attack worked
        self.assertLess(self.character.hp, initial_char_hp)
        
        # Verify both have roundtime and are still fighting
        self.assertGreater(self.character.roundtime, 0)
        self.assertGreater(self.mob.roundtime, 0)
        self.assertTrue(self.character.is_fighting)