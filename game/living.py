"""Small, deterministic living-world systems; transactions protect scarce rewards."""
import json
import time
from game.mob import Mob
from game.item import Item

async def refresh_inventory(character, world):
    equipped={slot:item.id for slot,item in character._equipped_items.items()}
    rows=await world.db_manager.get_instances_for_character(character.dbid)
    owned={}
    for row in rows:
        template=world.get_item_template(row["template_id"])
        if template:
            item=Item(dict(row),template)
            owned[item.id]=item
            world._all_item_instances[item.id]=item
    for item in owned.values():
        if item.container_id in owned:
            owned[item.container_id].contents[item.id]=item
    character._equipped_items={slot:owned[id] for slot,id in equipped.items() if id in owned}
    equipped_ids=set(equipped.values())
    character._inventory_items={id:item for id,item in owned.items() if id not in equipped_ids and not item.container_id}
    character.is_dirty=True


class LivingWorld:
    def __init__(self, world):
        self.world=world
        self.schedules=[]
        self.last_tick=0

    async def load(self):
        self.schedules=[dict(r) for r in await self.world.db_manager.fetch_all_query('SELECT * FROM npc_schedules')]
        await self.tick(0)

    async def tick(self, dt):
        if time.monotonic()-self.last_tick < 10:
            return
        self.last_tick=time.monotonic()
        for schedule in self.schedules:
            destination=self.world.get_room(schedule['night_room_id'] if self.world.is_night() else schedule['day_room_id'])
            template=self.world.get_mob_template(schedule['mob_template_id'])
            if not destination or not template:
                continue
            mob=next((m for r in self.world.rooms.values() for m in r.mobs if m.template_id==schedule['mob_template_id']),None)
            if mob is None:
                mob=Mob(template,destination)
                destination.add_mob(mob)
            elif mob.is_alive() and not mob.is_fighting and mob.location != destination:
                old=mob.location
                old.remove_mob(mob)
                await old.broadcast(f'{mob.name} leaves to attend to the day\'s duties.')
                mob.location=destination
                destination.add_mob(mob)
                await destination.broadcast(f'{mob.name} arrives, carrying a weathered journal.')

async def cmd_talk(character, world, args):
    npc=next((m for m in character.location.mobs if args.lower() in m.name.lower() and m.is_alive()),None) if args else None
    schedule=next((s for s in world.living.schedules if npc and s['mob_template_id']==npc.template_id),None)
    if schedule:
        from game.adventure import event
        await event(character,world,'talk',npc.name)
        await character.send(f'{npc.name} says, "{schedule["greeting"]}"\n{schedule["lore"]}')
    else:
        await character.send('Talk to whom? Use talk <name> near a resident.')
    return True

async def cmd_gather(character, world, args):
    db=world.db_manager
    message='There is no matching resource here. Use gather to list resources.'
    if not args:
        rows=await db.fetch_all_query('SELECT name FROM resource_nodes WHERE room_id=$1',character.location_id)
        await character.send('Resources: '+(', '.join(r['name'] for r in rows) or 'none'))
        return True
    if character.hands_are_full():
        await character.send('Your hands are full. Put an item in an open container or sheathe your weapon first.')
        return True
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            node=await conn.fetchrow('SELECT * FROM resource_nodes WHERE room_id=$1 AND lower(name)=lower($2) FOR UPDATE',character.location_id,args)
            if node:
                await conn.execute("UPDATE resource_nodes SET remaining=capacity,depleted_at=NULL WHERE id=$1 AND remaining=0 AND depleted_at+respawn_seconds*interval '1 second' <= now()",node['id'])
                remaining=await conn.fetchval('SELECT remaining FROM resource_nodes WHERE id=$1',node['id'])
                template=world.get_item_template(node['item_template_id'])
                weight=template.get('stats',{}).get('weight',0) if template else 0
                if character.get_current_weight()+weight > character.get_max_weight():
                    message='You cannot carry any more.'
                elif remaining:
                    await conn.execute('INSERT INTO item_instances(template_id,owner_char_id) VALUES($1,$2)',node['item_template_id'],character.dbid)
                    await conn.execute('UPDATE resource_nodes SET remaining=remaining-1,depleted_at=CASE WHEN remaining=1 THEN now() ELSE depleted_at END WHERE id=$1',node['id'])
                    message=f'You gather {template["name"]}.'
                    character.roundtime=3
                else:
                    message='This resource is depleted. It will recover with time.'
    await refresh_inventory(character, world)
    if message.startswith('You gather'):
        from game.adventure import event
        await event(character,world,'gather',args)
        skill='mining' if 'iron' in args else 'herbalism'
        character.skills[skill]=min(100,character.skills.get(skill,0)+1)
    await character.send(message)
    return True

async def cmd_craft(character, world, args):
    db=world.db_manager
    if not args:
        recipes=await db.fetch_all_query('SELECT name,description FROM recipes ORDER BY name')
        await character.send('Recipes:\n'+'\n'.join(f'{r["name"]}: {r["description"]}' for r in recipes))
        return True
    message='Unknown recipe. Use craft to list recipes.'
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            recipe=await conn.fetchrow('SELECT * FROM recipes WHERE lower(name)=lower($1)',args)
            if recipe:
                if recipe['station_room_id'] and recipe['station_room_id']!=character.location_id:
                    message='You need to be at the recipe\'s crafting station.'
                else:
                    ingredients=json.loads(recipe['ingredients'])
                    selected=[]
                    equipped={i.id for i in character._equipped_items.values()}
                    for key, quantity in ingredients.items():
                        items=await conn.fetch('SELECT id FROM item_instances WHERE owner_char_id=$1 AND template_id=$2 AND container_id IS NULL ORDER BY id FOR UPDATE',character.dbid,int(key))
                        # Only loose, unequipped materials; never consume a container with contents.
                        eligible=[r['id'] for r in items if r['id'] not in equipped and r['id'] in character._inventory_items and not character._inventory_items[r['id']].contents]
                        if len(eligible)<quantity:
                            break
                        selected.extend(eligible[:quantity])
                    else:
                        output=world.get_item_template(recipe['output_template_id'])
                        occupied=len(character._inventory_items)-len(selected)+len([slot for slot in ('main_hand','off_hand') if character._equipped_items.get(slot)])
                        if occupied>=2:
                            await character.send('Put away excess items before crafting.');return True
                        consumed=sum(character._inventory_items[i].weight for i in selected)
                        if character.get_current_weight()-consumed+output.get('stats',{}).get('weight',0)>character.get_max_weight():
                            await character.send('You cannot carry the crafted item.')
                            return True
                        if not ingredients:
                            await character.send('This recipe is incomplete; tell a builder.')
                            return True
                        await conn.execute('DELETE FROM item_instances WHERE id=ANY($1::uuid[])',selected)
                        await conn.execute('INSERT INTO item_instances(template_id,owner_char_id) VALUES($1,$2)',recipe['output_template_id'],character.dbid)
                        message=f'You craft {output["name"]}.'
                        character.roundtime=5
                    if message.startswith('Unknown'):
                        message='You do not have the required loose materials.'
    await refresh_inventory(character, world)
    if message.startswith('You craft'):
        from game.adventure import event
        await event(character,world,'craft',args)
        skill='alchemy' if 'salve' in args else 'blacksmithing'
        character.skills[skill]=min(100,character.skills.get(skill,0)+1)
    await character.send(message)
    return True

async def cmd_relics(character, world, args):
    rows=await world.db_manager.fetch_all_query('SELECT name,lore,claimed_at FROM relics ORDER BY id')
    await character.send('Echoes of the old world:\n'+'\n'.join(f'{r["name"]} — {r["lore"]}'+(' [discovered]' if r['claimed_at'] else '') for r in rows))
    return True

async def cmd_attune(character, world, args):
    if character.level<50:
        await character.send('Legendary relics require level 50 or above.');return True
    message='No unclaimed relic answers you here.'
    async with world.db_manager.pool.acquire() as conn:
        async with conn.transaction():
            relic=await conn.fetchrow('SELECT * FROM relics WHERE room_id=$1 AND lower(name)=lower($2) AND claimed_by IS NULL FOR UPDATE',character.location_id,args)
            if relic:
                template=world.get_item_template(relic['template_id'])
                if character.get_current_weight()+template.get('stats',{}).get('weight',0)>character.get_max_weight():
                    await character.send('You cannot carry the relic.')
                    return True
                instance=await conn.fetchval('INSERT INTO item_instances(template_id,owner_char_id) VALUES($1,$2) RETURNING id',relic['template_id'],character.dbid)
                await conn.execute('UPDATE relics SET claimed_by=$1,claimed_at=now(),instance_id=$2 WHERE id=$3',character.dbid,instance,relic['id'])
                message=f'You awaken {relic["name"]}. {relic["lore"]}'
                await conn.execute('INSERT INTO character_journal(character_id,entry) VALUES($1,$2)',character.dbid,message)
                character.roundtime=8
    await refresh_inventory(character, world)
    await character.send(message)
    return True

async def cmd_journal(character, world, args):
    rows=await world.db_manager.fetch_all_query('SELECT entry FROM character_journal WHERE character_id=$1 ORDER BY id DESC LIMIT 30',character.dbid)
    await character.send('Your chronicle:\n'+('\n'.join(r['entry'] for r in rows) or 'Your story is still unwritten.'))
    return True

async def cmd_skin(c,w,args):
    if c.hands_are_full():
        await c.send('Free a hand before skinning.');return True
    mob=next((m for m in c.location.mobs if args.lower() in m.name.lower() and not m.is_alive() and 'SKINNABLE' in m.flags),None)
    if not args or not mob or not mob.harvest_token:
        await c.send('Choose a slain, skinnable beast here.');return True
    async with w.db_manager.pool.acquire() as conn:
        async with conn.transaction():
            template=await conn.fetchval("SELECT id FROM item_templates WHERE name='saltwind hide' LIMIT 1")
            if not template:return True
            item_template=w.get_item_template(template)
            if c.get_current_weight()+item_template.get('stats',{}).get('weight',0)>c.get_max_weight():
                await c.send('You cannot carry a hide.');return True
            claimed=await conn.fetchval('INSERT INTO harvest_claims(token,character_id) VALUES($1,$2) ON CONFLICT DO NOTHING RETURNING token',mob.harvest_token,c.dbid)
            if not claimed:await c.send('That carcass has already been skinned.');return True
            await conn.execute('INSERT INTO item_instances(template_id,owner_char_id) VALUES($1,$2)',template,c.dbid)
    c.skills['skinning']=min(100,c.skills.get('skinning',0)+1);c.roundtime=5
    await refresh_inventory(c,w);await c.send('You recover a usable saltwind hide.');return True
