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
from game.item import Item
from game.commands import combat as combat_cmds

class TestCombatExchange(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_db_manager = AsyncMock()
        self.mock_writer = MagicMock(spec=asyncio.StreamWriter)
        self.mock_writer.drain = AsyncMock()
        self.world = World(self.mock_db_manager)
        
        self.world.item_templates[1] = {'id': 1, 'name': 'a test sword', 'type': 'WEAPON', 'description': 'A test sword.','stats': '{"damage_base": 5, "damage_rng": 3, "speed": 2.0}', 'damage_type': 'slash', 'flags': '[]'}
        self.world.mob_templates[1] = {'id': 1, 'name': 'a test rat', 'level': 1, 'max_hp': 15, 'description': 'A furry pest.','stats': '{"might": 10, "vitality": 10, "agility": 10}', 'attacks': '[{"name": "bite", "damage_base": 1, "damage_rng": 2, "speed": 2.0}]','flags': '[]', 'variance': '{}', 'loot': '{}'}
        
        room_data = {'id': 1, 'area_id': 1, 'name': 'Test Arena', 'description': 'A simple test arena.'}
        self.room = Room(room_data)
        self.world.rooms[1] = self.room
        self.room.broadcast = AsyncMock()

        char_data = { "id": 1, "player_id": 1, "first_name": "Hero", "last_name": "Test", "sex": "Male","race_id": 1, "class_id": 1, "level": 1, "hp": 50.0, "max_hp": 50.0,"essence": 50.0, "max_essence": 50.0, "stats": {"might": 15, "agility": 12, "vitality": 13},"skills": {}, "equipment": {'WIELD_MAIN': 'sword-uuid-123'}, "status": "ALIVE", "stance": "Standing", "xp_pool": 0, "xp_total": 0, "unspent_skill_points": 0, "unspent_attribute_points": 0,"spiritual_tether": 1, "description": "", "coinage": 0, "location_id": 1,"total_playtime_seconds": 0, "known_spells": [], "known_abilities": [], "inventory": []}
        self.character = Character(self.mock_writer, char_data, self.world)
        
        # FIX: Manually create and cache the Item instance for the equipped sword
        sword_instance_data = {'id': 'sword-uuid-123', 'template_id': 1}
        sword_template_data = self.world.get_item_template(1)
        self.character._equipped_items['WIELD_MAIN'] = Item(sword_instance_data, sword_template_data)

        mob_template = self.world.get_mob_template(1)
        self.mob = Mob(mob_template, self.room)
        self.mob.stats = {"might": 12, "agility": 12, "vitality": 10, "intellect": 10, "aura": 10, "persona": 10}

        self.room.add_character(self.character)
        self.character.update_location(self.room)
        self.room.add_mob(self.mob)

    @patch('random.randint')
    async def test_player_attacks_mob_and_hits(self, mock_randint):
        mock_randint.side_effect = [15, 2]
        await combat_cmds.cmd_attack(self.character, self.world, "rat")
        self.assertTrue(self.character.is_fighting)

    @patch('random.randint')
    async def test_full_combat_round(self, mock_randint):
        mock_randint.side_effect = [18, 3, 16, 1]
        initial_char_hp = self.character.hp
        initial_mob_hp = self.mob.hp
        await combat_cmds.cmd_attack(self.character, self.world, "rat")
        await self.mob.simple_ai_tick(dt=1.0, world=self.world)
        self.assertLess(self.mob.hp, initial_mob_hp)
        self.assertLess(self.character.hp, initial_char_hp)