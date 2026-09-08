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
        from game.professions import replenish
        await replenish(self.world, dt)
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

async def cmd_gather(c,w,args):
    from game.professions import gather
    return await gather(c,w,args)

async def cmd_craft(c,w,args):
    from game.professions import craft
    return await craft(c,w,args)

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
    from game.professions import gather
    mob=next((m for m in c.location.mobs if args.lower() in m.name.lower() and not m.is_alive() and 'SKINNABLE' in m.flags),None) if args else None
    if not mob or not mob.harvest_token:
        await c.send('Choose a slain, skinnable beast here.');return True
    node=await w.db_manager.fetch_one_query("SELECT name FROM resource_nodes WHERE room_id=$1 AND profession='skinning' ORDER BY id LIMIT 1",c.location_id)
    if not node:
        await c.send('There is no skinning resource node in this room.');return True
    return await gather(c,w,node['name'],corpse=mob)
