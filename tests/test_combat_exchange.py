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
from game.item import Item
from game.commands import combat as combat_cmds
from game.combat.hit_resolver import HitResult

class TestCombatExchange(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_db_manager = AsyncMock()
        self.mock_writer = MagicMock(spec=asyncio.StreamWriter)
        self.mock_writer.drain = AsyncMock()
        self.world = World(self.mock_db_manager)
        
        self.world.item_templates[1] = {'id': 1, 'name': 'a test sword', 'type': 'WEAPON', 'stats': '{"damage_base": 5, "damage_rng": 3, "speed": 2.0}'}
        self.world.mob_templates[1] = {
            'id': 1, 'name': 'a test rat', 'level': 1, 'max_hp': 15, 
            'description': 'A gnarly rat.', 'stats': '{"vitality": 10}', 
            'attacks': '[{"name": "bite"}]', 'loot_table': [], 'flags': [],
            'variance': '{}', 'loot': '{}', 'resistances': {},
            'respawn_delay_seconds': 300, 'movement_chance': 0.0
        }
        
        room_data = {'id': 1, 'area_id': 1, 'name': 'Test Arena', 'description': 'A simple test arena.'}
        self.room = Room(room_data)
        self.world.rooms[1] = self.room
        self.room.broadcast = AsyncMock()

        # FIX: This dictionary must contain ALL keys that Character.__init__ expects
        char_data = {
            "id": 1, "player_id": 1, "first_name": "Hero", "last_name": "Test", "sex": "Male",
            "race_id": 1, "class_id": 1, "level": 1, "description": "A mighty hero.",
            "hp": 50.0, "max_hp": 50.0, "essence": 50.0, "max_essence": 50.0,
            "xp_pool": 0, "xp_total": 0, "unspent_skill_points": 0, "unspent_attribute_points": 0,
            "spiritual_tether": 1, "coinage": 0, "location_id": 1, "total_playtime_seconds": 0,
            "status": "ALIVE", "stance": "Standing",
            "stats": {"might": 15, "agility": 12, "vitality": 13}
        }
        self.character = Character(self.mock_writer, char_data, self.world)
        self.character.stats = char_data["stats"]
        
        sword_instance = Item({'id': 'sword-uuid-123', 'template_id': 1}, self.world.item_templates[1])
        self.character._equipped_items['main_hand'] = sword_instance

        mob_template = self.world.get_mob_template(1)
        self.mob = Mob(mob_template, self.room)
        self.mob.stats = {"might": 12, "agility": 12, "vitality": 10}
        

        self.room.add_character(self.character)
        self.character.update_location(self.room)
        self.room.add_mob(self.mob)

    @patch('game.combat.damage_calculator.random')
    @patch('game.combat.hit_resolver.random')
    async def test_player_attacks_mob_and_hits(self, mock_hit_random, mock_dmg_random):
        mock_hit_random.randint.return_value = 15
        mock_dmg_random.randint.return_value = 2
        await combat_cmds.cmd_attack(self.character, self.world, "rat")
        self.assertTrue(self.character.is_fighting)

    @patch('game.resolver.random')
    @patch('game.combat.damage_calculator.random')
    @patch('game.combat.hit_resolver.random')
    async def test_full_combat_round(self, mock_hit_random, mock_dmg_random, mock_resolver_random):
        initial_char_hp = self.character.hp
        initial_mob_hp = self.mob.hp

        # Player's turn
        mock_hit_random.randint.return_value = 18
        mock_dmg_random.randint.return_value = 3
        await combat_cmds.cmd_attack(self.character, self.world, "rat")
        
        # Mob's turn
        mock_hit_random.randint.return_value = 16
        mock_resolver_random.randint.return_value = 1
        await self.mob.simple_ai_tick(dt=1.0, world=self.world)
        
        self.assertLess(self.mob.hp, initial_mob_hp)
        self.assertLess(self.character.hp, initial_char_hp)

    @patch('game.resolver.random')
    @patch('game.combat.outcome_handler.random')
    @patch('game.combat.damage_calculator.random')
    @patch('game.combat.hit_resolver.check_physical_hit')
    async def test_mob_defeat_and_loot_drop(self, mock_check_hit, mock_dmg_random, mock_outcome_random, mock_resolver_random):
        mock_check_hit.return_value = HitResult(is_hit=True, is_crit=True, is_fumble=False, roll=20, attacker_rating=20, target_dv=5)
        mock_dmg_random.randint.return_value = 3
        mock_resolver_random.randint.return_value = 3
        mock_outcome_random.random.return_value = 0.01
        mock_outcome_random.randint.return_value = 5

        self.world.mob_templates[1]['loot_table'] = [{'item_template_id': 1, 'drop_chance': 1.0}]
        self.mock_db_manager.create_item_instance.return_value = {'id': 'looted-sword-uuid', 'template_id': 1, 'room_id': self.room.dbid}
        
        self.mob.hp = 1
        
        await combat_cmds.cmd_attack(self.character, self.world, "rat")

        self.assertFalse(self.mob.is_alive())
        self.mock_db_manager.create_item_instance.assert_called_with(1, room_id=self.room.dbid)