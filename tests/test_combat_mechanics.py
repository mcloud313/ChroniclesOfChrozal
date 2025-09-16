import unittest
from unittest.mock import Mock, patch, AsyncMock, MagicMock
import sys
import os
import asyncio

# --- Boilerplate to ensure the game package is in the path ---
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

# --- Imports from your game code ---
from game import resolver
from game.character import Character
from game.mob import Mob
from game.item import Item
from game.combat.hit_resolver import HitResult
from game.combat.damage_calculator import DamageInfo

class TestCombatMechanics(unittest.IsolatedAsyncioTestCase):
    """Test suite for core combat functions and calculations."""

    def setUp(self):
        """Set up mock objects for use in various tests."""
        self.mock_world = Mock()
        self.mock_writer = MagicMock(spec=asyncio.StreamWriter)
        self.mock_writer.drain = AsyncMock()

        # Mock the database manager for durability updates
        self.mock_world.db_manager = AsyncMock()
        
        # Mock the item template data that the tests will need
        self.mock_world.get_item_template.side_effect = lambda tid: {
            10: {'id': 10, 'name': 'a leather cap', 'type': 'ARMOR', 'stats': '{"armor": 2}'},
            11: {'id': 11, 'name': 'a leather tunic', 'type': 'ARMOR', 'stats': '{"armor": 5}'},
            100: {'id': 100, 'name': 'a test sword', 'type': 'WEAPON', 'stats': '{"speed": 2.0, "damage_base": 1, "damage_rng": 8}'}
        }.get(tid)

    @patch('game.resolver.random')
    def test_roll_exploding_dice(self, mock_random):
        """Tests the exploding dice mechanic."""
        mock_random.randint.side_effect = [6, 4] # Explodes once, then rolls a 4
        result = resolver.roll_exploding_dice(6)
        self.assertEqual(result, 10)

    def test_armor_value_calculation(self):
        """Tests that total_av correctly sums armor from equipment."""
        char_data = { "id": 1, "player_id": 1, "first_name": "Armor", "last_name": "Test", "sex": "Male", "race_id": 1, "class_id": 1, "level": 1, "hp": 50.0, "max_hp": 50.0, "essence": 50.0, "max_essence": 50.0, "xp_pool": 0, "xp_total": 0, "unspent_skill_points": 0, "unspent_attribute_points": 0, "spiritual_tether": 1, "description": "", "coinage": 0, "location_id": 1, "total_playtime_seconds": 0, "status": "ALIVE", "stance": "Standing", "stats": {}, "skills": {}, "inventory": [], "equipment": {}, "known_spells": [], "known_abilities": [] }
        character = Character(self.mock_writer, char_data, self.mock_world)

        cap_template = self.mock_world.get_item_template(10)
        tunic_template = self.mock_world.get_item_template(11)
        cap_instance = Item({'id': 'cap-uuid-1', 'template_id': 10}, cap_template)
        tunic_instance = Item({'id': 'tunic-uuid-1', 'template_id': 11}, tunic_template)

        self.assertEqual(character.total_av, 0)
        character._equipped_items['HEAD'] = cap_instance
        self.assertEqual(character.total_av, 2)
        character._equipped_items['TORSO'] = tunic_instance
        self.assertEqual(character.total_av, 7)

    @patch('game.combat.damage_calculator.calculate_physical_damage')
    @patch('game.combat.hit_resolver.check_physical_hit')
    async def test_damage_mitigation(self, mock_check_hit, mock_calc_damage):
        """Tests that PDS and AV correctly reduce incoming physical damage."""
        mock_check_hit.return_value = HitResult(is_hit=True, is_crit=False, is_fumble=False, roll=15, attacker_rating=10, target_dv=5)
        mock_calc_damage.return_value = DamageInfo(pre_mitigation_damage=16, damage_type="bludgeon", is_crit=False)

        mock_attacker = MagicMock(spec=Character, name="Attacker")
        mock_attacker.name = "Attacker"
        mock_attacker.is_alive.return_value = True
        mock_attacker.slow_penalty = 0.0
        mock_attacker.total_av = 0 
        
        char_data = { "id": 2, "player_id": 1, "first_name": "Target", "last_name": "Test", "sex": "Male", "race_id": 1, "class_id": 1, "level": 1, "hp": 50.0, "max_hp": 50.0, "essence": 50.0, "max_essence": 50.0, "xp_pool": 0, "xp_total": 0, "unspent_skill_points": 0, "unspent_attribute_points": 0, "spiritual_tether": 1, "description": "", "coinage": 0, "location_id": 1, "total_playtime_seconds": 0, "status": "ALIVE", "stance": "Standing", "stats": {"vitality": 12}, "skills": {}, "inventory": [], "equipment": {}, "known_spells": [], "known_abilities": [] }
        target_character = Character(self.mock_writer, char_data, self.mock_world)
        target_character.stats = char_data["stats"]
        
        cap_instance = Item({'id': 'cap-uuid-2', 'template_id': 10}, self.mock_world.get_item_template(10))
        tunic_instance = Item({'id': 'tunic-uuid-2', 'template_id': 11}, self.mock_world.get_item_template(11))
        target_character._equipped_items['HEAD'] = cap_instance
        target_character._equipped_items['TORSO'] = tunic_instance

        mock_room = Mock(broadcast=AsyncMock())
        target_character.location = mock_room
        mock_attacker.location = mock_room
        
        initial_hp = target_character.hp
        expected_damage = 5 # 16 (pre-mit) - 4 (PDS from 12 vit) - 7 (AV) = 5

        await resolver.resolve_physical_attack(mock_attacker, target_character, None, self.mock_world)
        
        damage_taken = initial_hp - target_character.hp
        self.assertEqual(damage_taken, expected_damage)

    @patch('game.combat.outcome_handler.random')
    @patch('game.combat.hit_resolver.check_physical_hit')
    async def test_weapon_loses_condition_on_hit(self, mock_check_hit, mock_random):
        """Tests that an attacker's weapon loses condition after a successful hit."""
        # 1. Arrange
        mock_check_hit.return_value = HitResult(is_hit=True, is_crit=False, is_fumble=False, roll=15, attacker_rating=10, target_dv=5)
        mock_random.random.return_value = 0.05 # Force durability check to pass

        # FIX: Use a real Character object instead of a complex mock to prevent TypeErrors.
        attacker_data = { "id": 3, "player_id": 1, "first_name": "Durable", "last_name": "Hitter", "name": "Durable Hitter", "sex": "Male", "race_id": 1, "class_id": 1, "level": 1, "hp": 50, "max_hp": 50, "essence": 50, "max_essence": 50, "xp_pool": 0, "xp_total": 0, "unspent_skill_points": 0, "unspent_attribute_points": 0, "spiritual_tether": 1, "description": "", "coinage": 0, "location_id": 1, "total_playtime_seconds": 0, "status": "ALIVE", "stance": "Standing", "stats": {"might": 15}, "skills": {}, "inventory": [], "equipment": {}, "known_spells": [], "known_abilities": [] }
        attacker_char = Character(self.mock_writer, attacker_data, self.mock_world)

        target_mob = MagicMock(spec=Mob, name="Target", hp=50, max_hp=50)
        target_mob.is_alive.return_value = True
        target_mob.resistances = {} # Ensure resistances attribute exists
        target_mob.total_av = 0
        target_mob.dv = 10
        mock_room = Mock(broadcast=AsyncMock())
        attacker_char.location = mock_room
        target_mob.location = mock_room
        target_mob.pds = 0
        target_mob.total_av = 0
        target_mob.barrier_value = 0
        target_mob.name = "target_mob"
        
        weapon_template = self.mock_world.get_item_template(100)
        weapon_instance = Item({'id': 'weapon-uuid-1', 'template_id': 100, 'condition': 100}, weapon_template)
        
        # 2. Act
        await resolver.resolve_physical_attack(attacker_char, target_mob, weapon_instance, self.mock_world)

        # 3. Assert
        self.assertEqual(weapon_instance.condition, 99)
        self.mock_world.db_manager.update_item_condition.assert_called_once_with('weapon-uuid-1', 99)

if __name__ == '__main__':
    unittest.main()