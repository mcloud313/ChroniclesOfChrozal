# tests/test_item_interaction.py
import unittest
from unittest.mock import Mock, AsyncMock, MagicMock
import sys
import os
import asyncio

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from game.world import World
from game.room import Room
from game.character import Character
from game.item import Item
from game.commands import item as item_cmds

class TestItemInteraction(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.mock_db_manager = AsyncMock()
        mock_writer = MagicMock(spec=asyncio.StreamWriter)
        mock_writer.drain = AsyncMock()
        self.world = World(self.mock_db_manager)
        
        self.world.item_templates[1] = {'id': 1, 'name': 'a simple sword', 'type': 'WEAPON', 'description': 'A test sword.', 'stats': '{}', 'flags': '[]'}
        self.world.item_templates[2] = {'id': 2, 'name': 'a leather cap', 'type': 'ARMOR', 'description': 'A test cap.', 'stats': '{"wear_location": "HEAD"}', 'flags': '[]'}

        self.sword_instance_data = {'id': 'sword-uuid-123', 'template_id': 1, 'room_id': 1}
        self.cap_instance_data = {'id': 'cap-uuid-456', 'template_id': 2, 'owner_char_id': 1}
        
        self.room = Room({'id': 1, 'area_id': 1, 'name': 'Test Room', 'description': 'A room for testing.'})
        sword_obj = Item(self.sword_instance_data, self.world.item_templates[1])
        self.world._all_item_instances = {self.sword_instance_data['id']: sword_obj}
        self.room.item_instance_ids.append(self.sword_instance_data['id'])
        self.world.rooms[1] = self.room

        char_data = {"id": 1, "player_id": 1, "first_name": "Hero", "last_name": "Test", "sex": "Male", "race_id": 1, "class_id": 1, "level": 1, "hp": 50.0, "max_hp": 50.0, "essence": 50.0, "max_essence": 50.0, "stats": {}, "skills": {}, "equipment": {}, "inventory": [self.cap_instance_data['id']], "status": "ALIVE", "stance": "Standing", "xp_pool": 0, "xp_total": 0, "unspent_skill_points": 0, "unspent_attribute_points": 0, "spiritual_tether": 1, "description": "", "coinage": 0, "location_id": 1, "total_playtime_seconds": 0, "known_spells": [], "known_abilities": []}
        self.character = Character(mock_writer, char_data, self.world)
        cap_obj = Item(self.cap_instance_data, self.world.item_templates[2])
        self.character._inventory_items[self.cap_instance_data['id']] = cap_obj
        
        self.character.update_location(self.room)
        self.room.add_character(self.character)

    async def test_get_item_from_room(self):
        self.assertIn(self.sword_instance_data['id'], self.room.item_instance_ids)
        await item_cmds.cmd_get(self.character, self.world, "sword")
        self.assertNotIn(self.sword_instance_data['id'], self.room.item_instance_ids)
        self.assertIn(self.sword_instance_data['id'], self.character._inventory_items)

    async def test_drop_item_from_inventory(self):
        self.assertIn(self.cap_instance_data['id'], self.character._inventory_items)
        await item_cmds.cmd_drop(self.character, self.world, "cap")
        self.assertNotIn(self.cap_instance_data['id'], self.character._inventory_items)
        self.assertIn(self.cap_instance_data['id'], self.room.item_instance_ids)

    async def test_wear_item_from_inventory(self):
        self.assertIn(self.cap_instance_data['id'], self.character._inventory_items)
        await item_cmds.cmd_wear(self.character, self.world, "cap")
        self.assertNotIn(self.cap_instance_data['id'], self.character._inventory_items)
        self.assertIn('HEAD', self.character._equipped_items)