#game/commands/trade.py
import logging
import json
from typing import TYPE_CHECKING
from .. import utils
from ..item import Item

if TYPE_CHECKING:
    from ..character import Character
    from ..world import World

log = logging.getLogger(__name__)

async def cmd_list(character: 'Character', world: 'World', args_str: str) -> bool:
    """Displays items for sale in the current room if it's a shop."""
    # 1. Check if the current room is a shop
    if "SHOP" not in character.location.flags:
        await character.send("This is not a shop.")
        return True
    
    # 2. Get the shop's inventory from the world cache
    inventory = world.get_shop_inventory(character.location.dbid)
    if not inventory:
        await character.send("This shop has nothing for sale.")
        return True
    
    # 3. Build the formatted output
    output = ["\n\r{c--- Items for Sale ---{x"]
    for shop_item in inventory:
        template = world.get_item_template(shop_item['item_template_id'])
        if not template:
            continue

        stats = template.get('stats', {})
        base_value = stats.get('value', 0)
        
        price = int(base_value * shop_item['buy_price_modifier'])

        #Determine stock display
        stock = shop_item['stock_quantity']
        stock_display = f"(Stock: {stock})" if stock != -1 else "(Stock: Unlimited)"

        # Format the line
        price_str = f"[{utils.format_coinage(price):>10}]"
        output.append(f" {price_str} {template['name']} {stock_display}")

    output.append("{c----------------------{x")
    await character.send("\n\r".join(output))
    return True

async def cmd_buy(character: 'Character', world: 'World', args_str: str) -> bool:
    """Buys an item from a shop."""
    if not args_str:
        await character.send("Buy what?")
        return True
    
    # 1. Check if the room is a shop and has inventory
    if "SHOP" not in character.location.flags:
        await character.send("This is not a shop.")
        return True
    
    shop_inventory = world.get_shop_inventory(character.location.dbid)
    if not shop_inventory:
        await character.send("This shop has nothing for sale.")
        return True
    
    # 2. Find the requested item in the shop's inventory
    item_to_buy = None
    item_template = None
    for stock_item in shop_inventory:
        template = world.get_item_template(stock_item['item_template_id'])
        if template and args_str.lower() in template['name'].lower():
            item_to_buy = stock_item
            item_template = template
            break

    if not item_to_buy or not item_template:
        await character.send("That item is not for sale here.")
        return True
    
    # 3. Check stock
    if item_to_buy['stock_quantity'] == 0:
        await character.send("That item is out of stock.")
        return True
    
    # 4. Calculate price and check if the player can afford it.
    stats = item_template.get('stats', {})
    base_value = stats.get('value', 0)

    price = int(base_value * item_to_buy['buy_price_modifier'])

    # --- NEW: Apply Bartering Skill Discount ---
    bartering_rank = character.get_skill_rank("bartering")
    discount_mod = bartering_rank // 25  # 1% discount per 25 ranks
    if discount_mod > 0:
        price = int(price * (1.0 - (discount_mod / 100.0)))
    # ----------------------------------------

    if character.coinage < price:
        await character.send("You can't afford that.")
        return True
    
    # 5. Check the two hand inventory limit
    if character.hands_are_full():
        await character.send("Your hands are full. You must put something away to buy that.")
        return True

    # 6. Perform the transaction
    character.coinage -= price

    # Create a new unique instance of the item for the player
    new_instance_data = await world.db_manager.create_item_instance(
        template_id=item_template['id'],
        owner_char_id=character.dbid
    )

    # This should always succeed, but it's good practice to check
    if not new_instance_data:
        log.error(f"Failed to create item instance for template {item_template['id']} during purchase.")
        character.coinage += price # Refund player
        await character.send("An error occured with your purchase. You have been refunded.")
        return True
    
    # Add the new item to the character's in memory inventory
    new_item_obj = Item(new_instance_data, item_template)
    character._inventory_items[new_item_obj.id] = new_item_obj
    world._all_item_instances[new_item_obj.id] = new_item_obj

    # 7. Update shop stock if it's not infinite
    if item_to_buy['stock_quantity'] != -1:
        item_to_buy['stock_quantity'] -= 1
        # Here we would also update the stock in the database
        # We'll add this helper function in the next section
        await world.db_manager.update_shop_stock(item_to_buy['id'], -1)
    
    await character.send(f"You buy {item_template['name']} for {utils.format_coinage(price)}.")
    return True

async def cmd_sell(character: 'Character', world: 'World', args_str: str) -> bool:
    """Sells an item from inventory to a shop."""
    # ... (initial checks for args_str and SHOP flag are the same) ...
    
    item_to_sell = character.find_item_in_inventory_by_name(args_str)
    if not item_to_sell:
        await character.send("You aren't carrying that.")
        return True
    
    if item_to_sell.has_flag("NOSELL"):
        await character.send("You cannot sell that.")
        return True
    
    # --- NEW, MORE SPECIFIC LOGIC ---
    room_data = character.location
    buy_filter = room_data.shop_buy_filter
    
    is_interested = False
    if isinstance(buy_filter, dict):
        # Check if the item's type is in the allowed types list
        if item_to_sell.item_type in buy_filter.get("types", []):
            is_interested = True
        # Check if the item's template ID is in the allowed template_ids list
        if item_to_sell.template_id in buy_filter.get("template_ids", []):
            is_interested = True
            
    if not is_interested:
        await character.send("The shopkeeper is not interested in buying that.")
        return True
    # --- END NEW LOGIC ---

    base_value = item_to_sell.value
    if base_value <= 0:
        await character.send("That item is worthless.")
        return True
    
    sell_modifier = room_data.shop_sell_modifier
    price = int(base_value * sell_modifier)

    if price <= 0:
        await character.send("The shopkeeper offers you nothing for that.")
        return True
    
    # Apply Bartering Skill Bonus
    bartering_rank = character.get_skill_rank("bartering")
    profit_mod = bartering_rank // 25 # 1% profit bonus per 25 ranks
    if profit_mod > 0:
        price = int(price * (1.0 + (profit_mod / 100.0)))
    
    # Perform the transaction
    await world.db_manager.delete_item_instance(item_to_sell.id)

    character.coinage += price
    del character._inventory_items[item_to_sell.id]
    if item_to_sell.id in world._all_item_instances:
        del world._all_item_instances[item_to_sell.id]

    await character.send(f"You sell {item_to_sell.name} for {utils.format_coinage(price)}.")
    return True

async def cmd_balance(character: 'Character', world: 'World', args_str: str) -> bool:
    """Displays the character's bank balance"""
    if "BANK" not in character.location.flags:
        await character.send("You must be in a bank to check your balance.")
        return True
    
    balance = await world.db_manager.get_character_balance(character.dbid)
    await character.send(f"Your current bank balance is {utils.format_coinage(balance)}.")
    return True

async def cmd_deposit(character: 'Character', world: 'World', args_str: str) -> bool:
    """Deposits coinage or an item into the bank."""
    if not args_str:
        await character.send("Deposit what? (e.g. deposit 100 or deposit sword)")
        return True
    
    if "BANK" not in character.location.flags:
        await character.send("You must be in a bank to make a deposit.")
        return True
    
    # --- Try to deposit coinage
    try:
        amount = int(args_str)
        if amount <= 0:
            await character.send("You must deposit a positive amount.")
            return True
        if character.coinage < amount:
            await character.send("You don't have that much coinage.")
            return True
        
        # Perform transaction
        character.coinage -= amount
        await world.db_manager.update_character_balance(character.dbid, amount)

        await character.send(f"You deposit {utils.format_coinage(amount)}.")
        return True
    except ValueError:
        pass # IT's not a number so we assume it's an item name

    # Try to store an item
    item_name = args_str
    item_to_deposit = character.find_item_in_inventory_by_name(item_name)
    if not item_to_deposit:
        await character.send("You aren't carrying that.")
        return True
    
    #CAlculate storage fee (10% of value)
    fee = int(item_to_deposit.value * 0.10)
    if character.coinage < fee:
        await character.send(f"You can't afford the {utils.format_coinage(fee)} storage fee for that item.")
        return True
    
    # Perform Transaction
    character.coinage -= fee

    #Move item to the bank in the database
    success = await world.db_manager.bank_item(character.dbid, item_to_deposit.id)
    if not success:
        log.error("Failed to bank item %s for character %s", item_to_deposit.id, character.dbid)
        character.coinage += fee # Refund
        await character.send("There was an error storing your item. You have been refunded.")
        return True
    
    # Remove item from character's in-memory state
    del world._all_item_instances[item_to_deposit.id]
    del character._inventory_items[item_to_deposit.id]

    fee_str = f", paying a fee of {utils.format_coinage(fee)}" if fee > 0 else ""
    await character.send(f"You deposit {item_to_deposit.name}{fee_str}.")
    return True

async def cmd_withdraw(character: 'Character', world: 'World', args_str: str) -> bool:
    """Withdraws coinage or an item from the bank."""
    if not args_str:
        await character.send("Withdraw what? (e.g., withdraw 100, or withdraw sword.)")
        return True
    
    if "BANK" not in character.location.flags:
        await character.send("You must be in a bank to make a withdrawal.")
        return True
    
    # --- Try to withdraw coinage (This part is correct)
    try:
        amount = int(args_str)
        if amount <= 0:
            await character.send("You must withdraw a positive amount.")
            return True
        
        balance = await world.db_manager.get_character_balance(character.dbid)
        if balance < amount:
            await character.send("You don't have that much in your account.")
            return True
        
        character.coinage += amount
        await world.db_manager.update_character_balance(character.dbid, -amount)

        await character.send(f"You withdraw {utils.format_coinage(amount)}.")
        return True
    except ValueError:
        pass # It's not a number so we assume it's an item name.

    # --- Try to withdraw an item
    if len(character._inventory_items) >= 2:
        await character.send("Your hands are full.")
        return True
    
    item_name = args_str

    instance_record = await world.db_manager.find_banked_item_for_character(character.dbid, item_name)
    if not instance_record:
        await character.send("You don't have that item in your bank box.")
        return True
    
    success = await world.db_manager.unbank_item(character.dbid, instance_record['id'])
    if not success:
        log.error("Failed to unbank item %s for character %s", instance_record['id'], character.dbid)
        await character.send("There was an error retrieving your item.")
        return True
    
    template = world.get_item_template(instance_record['template_id'])
    item_obj = Item(dict(instance_record), template)

    # Add the item to the character's in-memory inventory
    character._inventory_items[item_obj.id] = item_obj
    
    # FIX: Register the newly created item with the world's master list
    world._all_item_instances[item_obj.id] = item_obj

    await character.send(f"You withdraw {item_obj.name} from your bank box.")
    return True

async def cmd_give(character: 'Character', world: 'World', args_str: str) -> bool:
    """Initiates giving an item or coinage to another character."""
    if " to " not in args_str:
        await character.send("Who do you want to give what to? (e.g., give sword to aragorn)")
        return True
    
    item_or_amount, target_name = [s.strip() for s in args_str.split(" to ", 1)]

    target_char = character.location.get_character_by_name(target_name)
    if not target_char:
        await character.send("You don't see them here.")
        return True
    if target_char == character:
        await character.send("You can't give things to yourself.")
        return True
    if target_char.pending_give_offer:
        await character.send(f"{target_char.name} is busy considering another offer.")
        return True
    
    # -- Try to give coinage ---
    try:
        amount = int(item_or_amount)
        if amount <= 0:
            await character.send("You must give a positive amount.")
            return True
        if character.coinage < amount:
            await character.send("You don't have that much coinage.")
            return True
        
        # Set the pending offer on the target
        target_char.pending_give_offer = {
            "from_char": character,
            "coinage": amount,
            "item": None
        }
        await target_char.send(f"{{y{character.name} offers you {utils.format_coinage(amount)}. Type 'accept' or 'decline'.{{x")
        await character.send(f"You offer {utils.format_coinage(amount)} to {target_char.name}.")
        return True
    except ValueError:
        pass # not a number so it's an item

    # --- Try to give an item
    item_to_give = character.find_item_in_inventory_by_name(item_or_amount)
    if not item_to_give:
        await character.send("You aren't carrying that.")
        return True
    if len(target_char._inventory_items) >= 2:
        await character.send(f"{target_char.name}'s hands are full.")
        return True
    
    # Set the pending offer on the target
    target_char.pending_give_offer = {
        "from_char": character,
        "coinage": 0,
        "item": item_to_give
    }
    await target_char.send(f"{{y{character.name} offers you {item_to_give.name}. Type 'accept' or 'decline'.{{x")
    await character.send(f"You offer {item_to_give.name} to {target_char.name}.")
    return True

async def cmd_accept(character: 'Character', world: 'World', args_str: str) -> bool:
    """Accepts a pending item or coinage offer."""
    offer = character.pending_give_offer
    if not offer:
        await character.send("You have not been offered anything.")
        return True
    
    giver = offer["from_char"]
    item_to_receive = offer["item"]
    coinage_to_receive = offer["coinage"]

    # Clear the offer immediately to prevent race conditions
    character.pending_give_offer = None

    #Re-validate conditions
    if not giver or giver.location != character.location:
        await character.send(f"{giver.name} is no longer here.")
        return True
    
    if item_to_receive:
        if len(character._inventory_items) >= 2:
            await character.send("Your hands are now full. You cannot accept the item.")
            await giver.send(f"{character.name}'s hands are now full; they could not accept your {item_to_receive.name}.")
            return True
        if item_to_receive.id not in giver._inventory_items:
            await character.send("The item is no longer available.")
            return True
        
        # Perform item transfer
        del giver._inventory_items[item_to_receive.id]
        character._inventory_items[item_to_receive.id] = item_to_receive
        await world.db_manager.update_item_location(item_to_receive.id, owner_char_id=character.dbid)

        await character.send(f"You accept the {item_to_receive.name} from {giver.name}.")
        await giver.send(f"{character.name} accepts your {item_to_receive.name}.")

    elif coinage_to_receive > 0:
        if giver.coinage < coinage_to_receive:
            await character.send("The coinage is no longer available.")
            return True
        
        # Perform coin transfer
        giver.coinage -= coinage_to_receive
        character.coinage += coinage_to_receive
        
        await character.send(f"You accept {utils.format_coinage(coinage_to_receive)} from {giver.name}.")
        await giver.send(f"{character.name} accepts your {utils.format_coinage(coinage_to_receive)}.")

    return True

async def cmd_decline(character: 'Character', world: 'World', args_str: str) -> bool:
    """Declines a pending item or coinage offer."""
    offer = character.pending_give_offer
    if not offer:
        await character.send("You have not been offered anything.")
        return True

    giver = offer["from_char"]
    character.pending_give_offer = None # Clear the offer

    await character.send("You decline the offer.")
    if giver and giver.location == character.location:
        await giver.send(f"{character.name} has declined your offer.")
    return True

