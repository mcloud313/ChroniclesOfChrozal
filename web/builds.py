"""Named authoring states and in-place world reloads that preserve connected players."""
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from game.database import db_manager
from web.auth import admin_player

router=APIRouter(prefix='/api/admin/builds',dependencies=[Depends(admin_player)])
TABLES=['class_kits','factions','balance_rules','areas','races','classes','damage_types','item_templates','mob_templates','ability_templates','rooms',
        'exits','mob_attacks','mob_loot_table','room_objects','ambient_scripts','loot_tables','loot_table_entries',
        'shop_inventories','resource_nodes','recipes','npc_schedules','relics','quests','notice_boards','shop_services','lore_articles']
RUNTIME={'resource_nodes':{'remaining','depleted_at'},'relics':{'claimed_by','claimed_at','instance_id'},'rooms':{'coinage'}}

class BuildName(BaseModel):
    name:str=Field(min_length=1,max_length=100)

@router.get('')
async def states():
    return [dict(r) for r in await db_manager.fetch_all_query('SELECT id,name,created_at,created_by FROM build_states ORDER BY id DESC LIMIT 100')]

@router.post('')
async def save_state(body:BuildName,request:Request,player=Depends(admin_player)):
    async with request.app.state.world.mutation_lock:
        async with db_manager.pool.acquire() as c:
            async with c.transaction(isolation='repeatable_read'):
                data={}
                for table in TABLES:
                    data[table]=json.loads(await c.fetchval(f"SELECT coalesce(jsonb_agg(to_jsonb(t)),'[]') FROM {table} t"))
                id=await c.fetchval('INSERT INTO build_states(name,payload,created_by) VALUES($1,$2,$3) RETURNING id',body.name,json.dumps(data),player['id'])
                await c.execute("INSERT INTO builder_audit(player_id,action,entity,entity_id) VALUES($1,'snapshot','build_states',$2)",player['id'],str(id))
    return {'id':id,'name':body.name}

@router.post('/{id}/restore')
async def restore(id:int,request:Request,player=Depends(admin_player)):
    world=request.app.state.world
    async with world.mutation_lock:
        saved=await db_manager.fetch_one_query('SELECT payload FROM build_states WHERE id=$1',id)
        if not saved:raise HTTPException(404,'Build state not found')
        data=json.loads(saved['payload'])
        async with db_manager.pool.acquire() as c:
            async with c.transaction():
                for table in TABLES:
                    for row in data.get(table,[]):
                        fields=[k for k in row if k not in {'id','created_at','updated_at'}|RUNTIME.get(table,set())]
                        update=', '.join(f'"{k}"=EXCLUDED."{k}"' for k in fields)
                        await c.execute(f'INSERT INTO {table} SELECT * FROM jsonb_populate_record(NULL::{table},$1::jsonb) ON CONFLICT(id) DO UPDATE SET {update}',json.dumps(row))
                await c.execute("INSERT INTO builder_audit(player_id,action,entity,entity_id) VALUES($1,'restore','build_states',$2)",player['id'],str(id))
        await hot_publish(request.app)
    return {'ok':True,'note':'Saved definitions restored and published; player progress and later-added entities retained.'}

async def hot_publish(app):
    from game.world import World
    from game.living import LivingWorld
    state=app.state;old=state.world
    async with old.mutation_lock:
        await old.save_state()
        replacement=World(db_manager)
        if not await replacement.build():raise HTTPException(422,'Build failed; live world retained')
        if any(c.location_id not in replacement.rooms for c in old.active_characters.values()):
            raise HTTPException(409,'A connected character references a missing room')
        replacement.living=LivingWorld(replacement)
        await replacement.living.load()
        active=old.active_characters
        old_mobs={m.instance_id:m for r in old.rooms.values() for m in r.mobs}
        new_mobs={m.instance_id:m for r in replacement.rooms.values() for m in r.mobs}
        for c in active.values():
            c.location=replacement.rooms[c.location_id]
            c.location.add_character(c)
            if c.target and hasattr(c.target,'instance_id'):
                c.target=new_mobs.get(c.target.instance_id)
                c.is_fighting=c.target is not None
            for item in c.get_all_owned_item_instances():
                template=replacement.get_item_template(item.template_id)
                if template:item._template=template;item._template_stats=template['stats']
                replacement._all_item_instances[item.id]=item
        for id,mob in new_mobs.items():
            if id in old_mobs:
                mob.target=old_mobs[id].target
                mob.is_fighting=old_mobs[id].is_fighting
        preserved={k:getattr(old,k) for k in ['mutation_lock','active_characters','active_groups','pending_invites']}
        old.__dict__.update(replacement.__dict__)
        old.__dict__.update(preserved)
        old.living.world=old
        # Callbacks remain bound to the same World instance; no reset or reconnect.
        await old.save_state()
