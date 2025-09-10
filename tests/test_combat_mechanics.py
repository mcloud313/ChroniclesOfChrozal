# tests/test_combat_mechanics.py
import unittest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from game import combat
from game.character import Character
from game.world import World

class TestCombatMechanics(unittest.IsolatedAsyncioTestCase):
    """Test suite for core combat functions and calculations."""

    def setUp(self):
        """Set up mock objects for use in various tests."""
        self.mock_world = Mock()
        self.mock_writer = MagicMock(spec=asyncio.StreamWriter)
        self.mock_writer.drain = AsyncMock()
        
        self.mock_world.get_item_template.side_effect = lambda tid: {
            10: {'id': 10, 'name': 'a leather cap', 'type': 'ARMOR', 'stats': '{"armor": 2}'},
            11: {'id': 11, 'name': 'a leather tunic', 'type': 'ARMOR', 'stats': '{"armor": 5}'},
        }.get(tid)

    @patch('random.randint')
    def test_roll_exploding_dice_no_explosion(self, mock_randint):
        mock_randint.return_value = 3
        result = combat.roll_exploding_dice(6)
        self.assertEqual(result, 3)

    @patch('random.randint')
    def test_roll_exploding_dice_single_explosion(self, mock_randint):
        mock_randint.side_effect = [6, 4]
        result = combat.roll_exploding_dice(6)
        self.assertEqual(result, 10)

    @patch('random.randint')
    def test_roll_exploding_dice_multiple_explosions(self, mock_randint):
        mock_randint.side_effect = [10, 10, 5]
        result = combat.roll_exploding_dice(10)
        self.assertEqual(result, 25)

    def test_armor_value_calculation(self):
        """Tests that get_total_av correctly sums armor from equipment."""
        # --- This test now correctly uses the Item Instance system ---
        from game.item import Item

        char_data = {
            "id": 1, "player_id": 1, "first_name": "Armor", "last_name": "Test", "sex": "Male",
            "race_id": 1, "class_id": 1, "level": 1, "hp": 50.0, "max_hp": 50.0,
            "essence": 50.0, "max_essence": 50.0, "xp_pool": 0, "xp_total": 0,
            "unspent_skill_points": 0, "unspent_attribute_points": 0, "spiritual_tether": 1,
            "description": "", "coinage": 0, "location_id": 1, "total_playtime_seconds": 0,
            "status": "ALIVE", "stance": "Standing", "stats": {}, "skills": {},
            "inventory": [], "equipment": {}, "known_spells": [], "known_abilities": []
        }
        character = Character(self.mock_writer, char_data, self.mock_world)

        # Create mock Item instances based on the templates
        cap_template = {'id': 10, 'name': 'a leather cap', 'stats': '{"armor": 2}'}
        tunic_template = {'id': 11, 'name': 'a leather tunic', 'stats': '{"armor": 5}'}
        
        cap_instance = Item({'id': 'cap-uuid-1', 'template_id': 10}, cap_template)
        tunic_instance = Item({'id': 'tunic-uuid-1', 'template_id': 11}, tunic_template)

        # Start with no equipment
        self.assertEqual(character.get_total_av(), 0)

        # Equip the cap
        character._equipped_items['HEAD'] = cap_instance
        self.assertEqual(character.get_total_av(), 2)
        
        # Equip the tunic
        character._equipped_items['TORSO'] = tunic_instance
        self.assertEqual(character.get_total_av(), 7)

    @patch('random.randint')
    async def test_damage_mitigation(self, mock_randint):
        """Tests that PDS and AV correctly reduce incoming physical damage."""
        # --- This test now correctly uses the Item Instance system ---
        from game.item import Item

        mock_attacker = Mock(spec=Character)
        mock_attacker.name = "Attacker"
        mock_attacker.is_alive.return_value = True
        mock_attacker.mar = 20
        mock_attacker.might_mod = 5
        mock_attacker.get_skill_rank.return_value = 0
        
        # side_effect[0] is hit roll, side_effect[1] is damage roll
        mock_randint.side_effect = [15, 10]
        
        char_data = {
            "id": 2, "player_id": 1, "first_name": "Target", "last_name": "Test", "sex": "Male",
            "race_id": 1, "class_id": 1, "level": 1, "hp": 50.0, "max_hp": 50.0,
            "essence": 50.0, "max_essence": 50.0, "xp_pool": 0, "xp_total": 0,
            "unspent_skill_points": 0, "unspent_attribute_points": 0, "spiritual_tether": 1,
            "description": "", "coinage": 0, "location_id": 1, "total_playtime_seconds": 0,
            "status": "ALIVE", "stance": "Standing", "stats": {"vitality": 12}, "skills": {},
            "inventory": [], "equipment": {}, "known_spells": [], "known_abilities": []
        }
        target_character = Character(self.mock_writer, char_data, self.mock_world)
        
        # Create mock armor Item instances and equip them
        cap_template = {'id': 10, 'name': 'a leather cap', 'stats': '{"armor": 2}'}
        tunic_template = {'id': 11, 'name': 'a leather tunic', 'stats': '{"armor": 5}'}
        cap_instance = Item({'id': 'cap-uuid-2', 'template_id': 10}, cap_template)
        tunic_instance = Item({'id': 'tunic-uuid-2', 'template_id': 11}, tunic_template)
        target_character._equipped_items['HEAD'] = cap_instance
        target_character._equipped_items['TORSO'] = tunic_instance

        mock_room = Mock()
        mock_room.broadcast = AsyncMock()
        target_character.location = mock_room
        mock_attacker.location = mock_room
        
        initial_hp = target_character.hp
        
        # pre-mitigation damage is 16. (1 base + 10 roll + 5 mod)
        # mitigation is 4 (PDS) + 7 (AV) = 11.
        # final damage = 16 - 11 = 5.
        expected_damage = 5

        await combat.resolve_physical_attack(mock_attacker, target_character, None, self.mock_world)
        
        damage_taken = initial_hp - target_character.hp
        self.assertEqual(damage_taken, expected_damage)