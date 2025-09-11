# tests/test_item_interaction.py
import unittest
from unittest.mock import MagicMock, AsyncMock
import sys
import os
import asyncio

# Add the project root to the Python path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from game.world import World
from game.room import Room
from game.character import Character
from game.item import Item
from game.commands import item as item_cmds

class TestItemInteraction(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        """Set up a mock world, character, and items for testing."""
        # Mock the database manager and its methods
        self.mock_db_manager = AsyncMock()
        self.mock_db_manager.update_item_location = AsyncMock()
        self.mock_db_manager.delete_item_instance = AsyncMock()

        # Mock the network writer
        mock_writer = MagicMock(spec=asyncio.StreamWriter)
        mock_writer.drain = AsyncMock()
        
        # Initialize the world
        self.world = World(self.mock_db_manager)
        
        # Populate the world with all necessary templates
        self.world.item_templates[1] = {'id': 1, 'name': 'a simple sword', 'type': 'WEAPON', 'stats': '{}'}
        self.world.item_templates[2] = {'id': 2, 'name': 'a leather cap', 'type': 'ARMOR', 'stats': '{"wear_location": "HEAD"}'}
        self.world.item_templates[3] = {'id': 3, 'name': 'a small pouch', 'type': 'CONTAINER', 'stats': '{"capacity": 100}'}
        self.world.item_templates[4] = {'id': 4, 'name': 'a green gem', 'type': 'TREASURE', 'stats': '{"weight": 1}'}

        # Create instance data and objects for ALL items
        self.sword_instance_data = {'id': 'sword-uuid-123', 'template_id': 1, 'room_id': 1}
        self.cap_instance_data = {'id': 'cap-uuid-456', 'template_id': 2, 'owner_char_id': 1}
        self.pouch_instance_data = {'id': 'pouch-uuid-789', 'template_id': 3, 'owner_char_id': 1}
        self.gem_instance_data = {'id': 'gem-uuid-101', 'template_id': 4, 'owner_char_id': 1}
        
        sword_obj = Item(self.sword_instance_data, self.world.item_templates[1])
        self.cap_obj = Item(self.cap_instance_data, self.world.item_templates[2])
        self.pouch_obj = Item(self.pouch_instance_data, self.world.item_templates[3])
        self.gem_obj = Item(self.gem_instance_data, self.world.item_templates[4])

        # Place all instances into the world's master cache
        self.world._all_item_instances = {
            'sword-uuid-123': sword_obj,
            'cap-uuid-456': self.cap_obj,
            'pouch-uuid-789': self.pouch_obj,
            'gem-uuid-101': self.gem_obj
        }

        # Set up the room and place the sword in it
        self.room = Room({'id': 1, 'area_id': 1, 'name': 'Test Room', 'description': 'A room for testing.'})
        self.room.item_instance_ids.append(self.sword_instance_data['id'])
        self.world.rooms[1] = self.room

        # Set up the character
        # The character starts with the cap, pouch, and gem IN THEIR HANDS. This violates the 2-hand
        # limit but is necessary to set up the various tests correctly.
        char_data = {"id": 1, "player_id": 1, "first_name": "Hero", "last_name": "Test", "sex": "Male", "race_id": 1, "class_id": 1, "level": 1, "hp": 50.0, "max_hp": 50.0, "essence": 50.0, "max_essence": 50.0, "stats": {}, "skills": {}, "equipment": {}, "inventory": [], "status": "ALIVE", "stance": "Standing", "xp_pool": 0, "xp_total": 0, "unspent_skill_points": 0, "unspent_attribute_points": 0, "spiritual_tether": 1, "description": "", "coinage": 0, "location_id": 1, "total_playtime_seconds": 0, "known_spells": [], "known_abilities": []}
        self.character = Character(mock_writer, char_data, self.world)
        
        # Manually set up the in-memory state for the tests
        self.character._inventory_items = {
            self.cap_obj.id: self.cap_obj,
            self.pouch_obj.id: self.pouch_obj,
            self.gem_obj.id: self.gem_obj
        }
        
        # Place the character in the room
        self.character.update_location(self.room)
        self.room.add_character(self.character)

    async def test_get_item_from_room(self):
        """Verify that a character can get an item from the room."""
        # Pre-condition: Sword is in the room
        self.assertIn(self.sword_instance_data['id'], self.room.item_instance_ids)

        # FIX: Character starts with 3 items, so their hands are full.
        # Drop two items to make space before trying to get the sword.
        await item_cmds.cmd_drop(self.character, self.world, "gem")
        await item_cmds.cmd_drop(self.character, self.world, "pouch")
        self.assertEqual(len(self.character._inventory_items), 1) # Hands now have space

        # Action: Run the 'get' command
        await item_cmds.cmd_get(self.character, self.world, "sword")

        # Post-condition: Sword is no longer in the room and is now in inventory
        self.assertNotIn(self.sword_instance_data['id'], self.room.item_instance_ids)
        self.assertIn(self.sword_instance_data['id'], self.character._inventory_items)

    async def test_drop_item_from_inventory(self):
        """Verify that a character can drop an item into the room."""
        # Pre-condition: Cap is in inventory
        self.assertIn(self.cap_instance_data['id'], self.character._inventory_items)

        # Action: Run the 'drop' command
        await item_cmds.cmd_drop(self.character, self.world, "cap")

        # Post-condition: Cap is no longer in inventory and is now in the room
        self.assertNotIn(self.cap_instance_data['id'], self.character._inventory_items)
        self.assertIn(self.cap_instance_data['id'], self.room.item_instance_ids)

    async def test_wear_item_from_inventory(self):
        """Verify that a character can wear an item from their inventory."""
        # Pre-condition: Cap is in inventory
        self.assertIn(self.cap_instance_data['id'], self.character._inventory_items)

        # Action: Run the 'wear' command
        await item_cmds.cmd_wear(self.character, self.world, "cap")

        # Post-condition: Cap is no longer in inventory and is now equipped
        self.assertNotIn(self.cap_instance_data['id'], self.character._inventory_items)
        self.assertIn('HEAD', self.character._equipped_items)
        self.assertEqual(self.character._equipped_items['HEAD'].id, self.cap_instance_data['id'])

    async def test_put_and_get_from_container(self):
        """Verify that a character can put an item in a container and get it back."""
        pouch_id = self.pouch_obj.id
        gem_id = self.gem_obj.id

        # The character starts with 3 items, so they can't get another item yet.
        # First, we need to make space by putting the gem in the pouch.
        self.assertEqual(len(self.character._inventory_items), 3)

        # --- Act (Put) ---
        await item_cmds.cmd_put(self.character, self.world, "gem in pouch")

        # --- Assert (Put) ---
        self.assertEqual(len(self.character._inventory_items), 2) # Hands now have space
        self.assertNotIn(gem_id, self.character._inventory_items)
        self.assertIn(gem_id, self.pouch_obj.contents)

        # --- Act (Get) ---
        # Now that hands are not full, this should fail because the two-hand limit is met.
        # Let's drop the cap to make space.
        await item_cmds.cmd_drop(self.character, self.world, "cap")
        self.assertEqual(len(self.character._inventory_items), 1)

        # Now, get the gem from the pouch
        await item_cmds.cmd_get(self.character, self.world, "gem from pouch")

        # --- Assert (Get) ---
        self.assertEqual(len(self.character._inventory_items), 2)
        self.assertIn(gem_id, self.character._inventory_items)
        self.assertNotIn(gem_id, self.pouch_obj.contents)