"""Serialized world mutations and durable runtime checkpoints."""
import asyncio
import json
import time
from game.mob import Mob

class ReentrantLock:
    def __init__(self):
        self.lock=asyncio.Lock();self.owner=None;self.depth=0
    async def __aenter__(self):
        task=asyncio.current_task()
        if self.owner is not task:
            await self.lock.acquire();self.owner=task
        self.depth+=1
        return self
    async def __aexit__(self,*exc):
        self.depth-=1
        if not self.depth:self.owner=None;self.lock.release()


def serialize_effects(effects):
    now=time.monotonic()
    return {key:{**effect,'ends_at':time.time()+max(0,effect.get('ends_at',now)-now)} for key,effect in effects.items()}


def restore_effects(effects):
    return {key:{**effect,'ends_at':time.monotonic()+effect['ends_at']-time.time()} for key,effect in effects.items() if effect.get('ends_at',0)>time.time()}

async def save_runtime(world):
    mobs=[]
    for room in world.rooms.values():
        for m in room.mobs:
            mobs.append({'id':m.instance_id,'template_id':m.template_id,'harvest_token':getattr(m,'harvest_token',None),'room_id':room.dbid,
                         'hp':m.hp,'max_hp':m.max_hp,'stats':m.stats,'roundtime':m.roundtime,
                         'effects':serialize_effects(m.effects),
                         'death_at':time.time()-(time.monotonic()-m.time_of_death) if m.time_of_death else None})
    payload={'mobs':mobs,'weather':world.area_weather,'saved_at':time.time()}
    await world.db_manager.execute_query("INSERT INTO runtime_checkpoints(key,payload) VALUES('world',$1) ON CONFLICT(key) DO UPDATE SET payload=EXCLUDED.payload,updated_at=now()",json.dumps(payload))

async def restore_runtime(world):
    row=await world.db_manager.fetch_one_query("SELECT payload FROM runtime_checkpoints WHERE key='world'")
    if not row:return
    data=json.loads(row['payload'])
    # Replace initial spawns for known persisted templates; preserve newly authored spawns.
    restored_templates={m['template_id'] for m in data['mobs']}
    for room in world.rooms.values():
        room.mobs={m for m in room.mobs if m.template_id not in restored_templates}
    for saved in data['mobs']:
        room=world.get_room(saved['room_id']);template=world.get_mob_template(saved['template_id'])
        if not room or not template:continue
        mob=Mob(template,room);mob.instance_id=saved['id']
        Mob.next_instance_id=max(Mob.next_instance_id,mob.instance_id+1)
        mob.hp=min(saved['hp'],mob.max_hp);mob.stats=saved['stats']
        mob.roundtime=max(0,saved.get('roundtime',0)-(time.time()-data['saved_at']))
        mob.harvest_token=saved.get('harvest_token')
        mob.effects=restore_effects(saved.get('effects',{}))
        if saved['death_at']:
            mob.time_of_death=time.monotonic()-(time.time()-saved['death_at'])
        room.add_mob(mob)
    world.area_weather={int(k):v for k,v in data.get('weather',{}).items() if int(k) in world.areas}
    for area_id,weather in world.area_weather.items():
        if weather.get('condition')=='BLAZING' and world.areas[area_id].get('climate')!='arid' and world.game_month!=7:
            weather['condition']='CLEAR'
            for room in world.rooms.values():
                if room.area_id==area_id:room.flags.discard('BLAZING')

async def checkpoint(world):
    """One atomic, set-based checkpoint avoids one transaction per player."""
    characters=world.get_active_characters_list()
    core=[];stats=[];skills=[];equipment=[];abilities=[];items=[]
    for c in characters:
        row=c.get_core_data_for_saving();row['runtime_state']=json.loads(row['runtime_state'])
        core.append({'id':c.dbid,**row})
        stats.append({'character_id':c.dbid,**c.stats})
        equipment.append({'character_id':c.dbid,**c.get_equipment_for_saving()})
        skills.extend({'character_id':c.dbid,'skill_name':name,'rank':rank} for name,rank in c.skills.items())
        abilities.extend({'character_id':c.dbid,'ability_internal_name':name} for name in c.known_abilities)
        items.extend({'id':str(i.id),'owner_char_id':c.dbid if i.container_id is None else None,'container_id':str(i.container_id) if i.container_id else None} for i in c.get_all_owned_item_instances())
    mobs=[]
    for room in world.rooms.values():
        for m in room.mobs:
            mobs.append({'id':m.instance_id,'template_id':m.template_id,'harvest_token':getattr(m,'harvest_token',None),'room_id':room.dbid,'hp':m.hp,'max_hp':m.max_hp,'stats':m.stats,'roundtime':m.roundtime,'effects':serialize_effects(m.effects),'death_at':time.time()-(time.monotonic()-m.time_of_death) if m.time_of_death else None})
    payload={'mobs':mobs,'weather':world.area_weather,'saved_at':time.time()}
    encode=lambda value:json.dumps(value,default=str)
    async with world.db_manager.pool.acquire() as conn:
        async with conn.transaction():
            if core:
                assignments=','.join(f'"{k}"=s."{k}"' for k in core[0] if k!='id')
                await conn.execute(f'UPDATE characters c SET {assignments},last_saved=now() FROM jsonb_populate_recordset(NULL::characters,$1) s WHERE c.id=s.id',encode(core))
                for table,rows in [('character_stats',stats),('character_equipment',equipment)]:
                    fields=list(rows[0]);updates=','.join(f'"{k}"=EXCLUDED."{k}"' for k in fields if k!='character_id')
                    names=','.join(f'"{k}"' for k in fields)
                    await conn.execute(f'INSERT INTO {table}({names}) SELECT {names} FROM jsonb_populate_recordset(NULL::{table},$1) ON CONFLICT(character_id) DO UPDATE SET {updates}',encode(rows))
                ids=[c.dbid for c in characters]
                for table,rows in [('character_skills',skills),('character_abilities',abilities)]:
                    await conn.execute(f'DELETE FROM {table} WHERE character_id=ANY($1::int[])',ids)
                    if rows:
                        names=','.join(rows[0])
                        await conn.execute(f'INSERT INTO {table}({names}) SELECT {names} FROM jsonb_populate_recordset(NULL::{table},$1)',encode(rows))
                if items:await conn.execute('UPDATE item_instances i SET owner_char_id=s.owner_char_id,container_id=s.container_id,room_id=NULL,bank_char_id=NULL FROM jsonb_populate_recordset(NULL::item_instances,$1) s WHERE i.id=s.id',encode(items))
            await conn.execute('UPDATE rooms r SET coinage=s.coinage FROM jsonb_populate_recordset(NULL::rooms,$1) s WHERE r.id=s.id',encode([{'id':r.dbid,'coinage':r.coinage} for r in world.rooms.values()]))
            await conn.execute("UPDATE game_economy SET game_year=$1,game_month=$2,game_day=$3,game_hour=$4,game_minute=$5 WHERE key='time'",world.game_year,world.game_month,world.game_day,world.game_hour,world.game_minute)
            await conn.execute("INSERT INTO runtime_checkpoints(key,payload) VALUES('world',$1) ON CONFLICT(key) DO UPDATE SET payload=EXCLUDED.payload,updated_at=now()",encode(payload))
    for c in characters:c.is_dirty=False
    world.dirty_rooms.clear()
