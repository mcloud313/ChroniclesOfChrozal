"""Small-community housing, player stalls, enchanting and a social tavern game."""
import json
from game.community import rule

async def cmd_home(c,w,args):
    row=await w.db_manager.fetch_one_query('SELECT * FROM player_homes WHERE owner_id=$1',c.dbid)
    if not args:
        await c.send(f"{row['name']}\n{row['description']}\nUse home enter from the tavern, or out to leave." if row else 'At the tavern, home buy purchases a room charter. home describe <text> decorates it.');return True
    if 'BANK' not in c.location.flags:
        await c.send('Visit the Lantern & Tide to manage your room.');return True
    if args=='buy':
        price=await rule(w,'housing_price',2500)
        if row or c.coinage<price:await c.send(f'A room charter costs {price} coins; one per character.');return True
        async with w.db_manager.pool.acquire() as conn:
            async with conn.transaction():
                room=await conn.fetchrow("INSERT INTO rooms(area_id,name,description,flags) VALUES($1,$2,'A quiet room above the Lantern & Tide.','[\"NODE\",\"SAFE_ZONE\",\"HOME\",\"LIT\"]') RETURNING *",c.location.area_id,c.name+'’s room')
                await conn.execute("INSERT INTO exits(source_room_id,destination_room_id,direction) VALUES($1,2,'out')",room['id'])
                await conn.execute('INSERT INTO player_homes(owner_id,room_id) VALUES($1,$2)',c.dbid,room['id'])
                await conn.execute('UPDATE characters SET coinage=$1 WHERE id=$2',c.coinage-price,c.dbid)
                await conn.execute("INSERT INTO economy_ledger(character_id,reason,coin_delta) VALUES($1,'housing',$2)",c.dbid,-price)
        from game.room import Room
        live=Room(dict(room));live.exits['out']={'destination_room_id':2};w.rooms[live.dbid]=live
        c.coinage-=price;c.is_dirty=True;await c.send('Your room charter is recorded. Use home enter.');return True
    if row and args.startswith('describe ') and len(args)<=2010:
        async with w.db_manager.pool.acquire() as conn:
            async with conn.transaction():
                await conn.execute('UPDATE player_homes SET description=$1 WHERE owner_id=$2',args[9:],c.dbid)
                await conn.execute('UPDATE rooms SET description=$1 WHERE id=$2',args[9:],row['room_id'])
        if row['room_id'] in w.rooms:w.rooms[row['room_id']].description=args[9:]
        await c.send('Your room description is saved.');return True
    if args=='enter' and row and row['room_id'] in w.rooms:
        c.location.remove_character(c);c.update_location(w.rooms[row['room_id']]);c.location.add_character(c);c.roundtime=1;c.is_dirty=True
        await c.send(c.location.get_look_string(c,w));return True
    if args.startswith('visit ') and args[6:].isdigit():
        other=await w.db_manager.fetch_one_query('SELECT * FROM player_homes WHERE owner_id=$1',int(args[6:]))
        await c.send(f"{other['name']}\n{other['description']}" if other else 'No room is registered.');return True
    await c.send('Use home, home buy, home describe <text>, or home visit <character id>.');return True

async def cmd_enchant(c,w,args):
    item=c.find_item_in_inventory_by_name(args)
    if c.location_id!=4 or not item or item.item_type not in ('WEAPON','TWO_HANDED_WEAPON','RANGED_WEAPON','ARMOR'):
        await c.send('Bring a loose weapon or armor to the Tideforge: enchant <item>.');return True
    rank=item.instance_stats.get('enchantment_rank',0)+1;cost=await rule(w,'enchant_price',500)*rank*rank
    if rank>3 or c.coinage<cost:await c.send(f'Enchantment costs {cost} coins and is capped at rank 3.');return True
    stats={**item.instance_stats,'enchantment_rank':rank}
    async with w.db_manager.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('UPDATE item_instances SET instance_stats=$1 WHERE id=$2',json.dumps(stats),item.id)
            await conn.execute('UPDATE characters SET coinage=$1 WHERE id=$2',c.coinage-cost,c.dbid)
            await conn.execute("INSERT INTO economy_ledger(character_id,reason,coin_delta) VALUES($1,'enchantment',$2)",c.dbid,-cost)
    c.coinage-=cost;c.is_dirty=True;c.roundtime=10;item.instance_stats=stats
    await c.send(f'{item.name} gains permanent enchantment rank {rank}.');return True

async def cmd_market(c,w,args):
    if 'BANK' not in c.location.flags:
        await c.send('Visit the tavern’s player stalls.');return True
    if not args:
        rows=await w.db_manager.fetch_all_query('SELECT l.id,l.price,t.name FROM market_listings l JOIN item_instances i ON i.id=l.item_id JOIN item_templates t ON t.id=i.template_id ORDER BY l.id LIMIT 100')
        await c.send('market sell <price> <item>; market buy <listing>; market cancel <listing>\n'+'\n'.join(f"{r['id']}. {r['name']}: {r['price']} coins" for r in rows));return True
    parts=args.split(' ',2)
    if len(parts)<2 or not parts[1].isdigit():return True
    amount=int(parts[1])
    if parts[0]=='sell' and len(parts)==3:
        item=c.find_item_in_inventory_by_name(parts[2])
        if not item or item.contents or item.has_flag('NOSELL') or not 1<=amount<=100000000:
            await c.send('List an empty, tradeable loose item at a positive price.');return True
        async with w.db_manager.pool.acquire() as conn:
            async with conn.transaction():
                id=await conn.fetchval('INSERT INTO market_listings(seller_id,item_id,price) VALUES($1,$2,$3) RETURNING id',c.dbid,item.id,amount)
                await conn.execute('UPDATE item_instances SET owner_char_id=NULL,market_id=$1 WHERE id=$2',id,item.id)
        c._inventory_items.pop(item.id,None);w._all_item_instances.pop(item.id,None)
        await c.send(f'Listing {id} opened.');return True
    if parts[0] not in ('buy','cancel'):return True
    tax=await rule(w,'market_tax_percent',5)
    seller=None;proceeds=0
    async with w.db_manager.pool.acquire() as conn:
        async with conn.transaction():
            row=await conn.fetchrow('SELECT * FROM market_listings WHERE id=$1 FOR UPDATE',amount)
            if not row:await c.send('Listing not found.');return True
            buying=parts[0]=='buy'
            if (not buying and row['seller_id']!=c.dbid) or (buying and (row['seller_id']==c.dbid or c.coinage<row['price'])):
                await c.send('You cannot complete this transaction.');return True
            if buying:
                seller=w.active_characters.get(row['seller_id']);proceeds=row['price']*(100-min(100,tax))//100
                if seller:await conn.execute('UPDATE characters SET coinage=$1 WHERE id=$2',seller.coinage+proceeds,seller.dbid)
                else:await conn.execute('UPDATE characters SET coinage=coinage+$1 WHERE id=$2',proceeds,row['seller_id'])
                await conn.execute('UPDATE characters SET coinage=$1 WHERE id=$2',c.coinage-row['price'],c.dbid)
                await conn.execute("INSERT INTO economy_ledger(character_id,reason,coin_delta) VALUES($1,'market buy',$2),($3,'market sale',$4)",c.dbid,-row['price'],row['seller_id'],proceeds)
            await conn.execute('UPDATE item_instances SET owner_char_id=$1,market_id=NULL WHERE id=$2',c.dbid,row['item_id'])
            await conn.execute('DELETE FROM market_listings WHERE id=$1',amount)
    if buying:
        c.coinage-=row['price'];c.is_dirty=True
        if seller:seller.coinage+=proceeds;seller.is_dirty=True
    from game.living import refresh_inventory
    await refresh_inventory(c,w)
    await c.send('The stall transaction is complete.');return True

async def cmd_tales(c,w,args):
    if 'NODE' not in c.location.flags:
        await c.send('Gather at a node to play Shared Tales.');return True
    if not args:
        await c.send('Shared Tales: each person adds one sentence to a story. tales <sentence>. Take turns; no XP or coin reward is attached.');return True
    state=getattr(w,'tavern_turns',{})
    if state.get(c.location_id)==c.dbid:
        await c.send('Let another traveler add the next sentence.');return True
    state[c.location_id]=c.dbid;w.tavern_turns=state
    await c.location.broadcast(f'Shared Tales — {c.name}: {args[:400]}');return True
