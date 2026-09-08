"""Allowlisted, authenticated world editor with optimistic concurrency and audit."""
import json
import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from game.database import db_manager
from web.auth import admin_player

EDITABLE = {'lore_articles','shop_services','notice_boards','class_kits','factions','balance_rules','quests','areas','rooms','exits','room_objects','ambient_scripts','item_templates','mob_templates',
            'mob_attacks','mob_loot_table','loot_tables','loot_table_entries','ability_templates',
            'races','classes','damage_types','shop_inventories','resource_nodes','recipes','npc_schedules','relics'}
READONLY = {'board_notices','notice_claims','connection_events','gameplay_metrics','player_homes','market_listings','character_reputation','economy_ledger','game_mail','character_quests','characters','character_stats','character_skills','character_abilities','character_equipment',
            'item_instances','bank_accounts','banked_items','game_economy','room_traps','character_journal'}
router = APIRouter(prefix='/api/admin', dependencies=[Depends(admin_player)])

class Edit(BaseModel):
    values: dict = Field(default_factory=dict)
    original: dict | None = None

async def columns(table):
    if table not in EDITABLE | READONLY:
        raise HTTPException(404, 'Unknown entity')
    return await db_manager.fetch_all_query('''SELECT column_name, data_type, is_nullable, column_default
        FROM information_schema.columns WHERE table_schema='public' AND table_name=$1 ORDER BY ordinal_position''',table)

@router.get('/catalog')
async def catalog():
    result=[]
    for table in sorted(EDITABLE | READONLY):
        result.append({'name':table,'editable':table in EDITABLE,'columns':[dict(c) for c in await columns(table)]})
    return result

@router.get('/status')
async def status(request: Request, offset: int = Query(0,ge=0), limit: int = Query(50,ge=1,le=100)):
    from itertools import islice
    world=request.app.state.world
    online=sorted(world.active_characters.values(),key=lambda c:c.dbid)
    mobs=(m for r in world.rooms.values() for m in r.mobs)
    return {'players':len(online),'connections':len(request.app.state.connections),
        'rooms':len(world.rooms),'npcs':sum(len(r.mobs) for r in world.rooms.values()),
        'online':[{'id':c.dbid,'name':c.name,'room':c.location_id,'hp':c.hp,'level':c.level,'link_lost':getattr(c,'linkdead',False)} for c in online[offset:offset+limit]],
        'mobs':[{'id':str(m.instance_id),'name':m.name,'room':m.location.dbid,'hp':m.hp} for m in islice(mobs,offset,offset+limit)]}

@router.get('/characters/{character_id}')
async def character_detail(character_id: int, request: Request, offset: int = Query(0,ge=0)):
    character=await db_manager.fetch_one_query('SELECT * FROM characters WHERE id=$1',character_id)
    if not character:raise HTTPException(404,'Character not found')
    stats=await db_manager.fetch_one_query('SELECT * FROM character_stats WHERE character_id=$1',character_id)
    equipment=await db_manager.fetch_one_query('SELECT * FROM character_equipment WHERE character_id=$1',character_id)
    items=await db_manager.fetch_all_query('WITH RECURSIVE owned(id) AS (SELECT id FROM item_instances WHERE owner_char_id=$1 UNION SELECT i.id FROM item_instances i JOIN owned o ON i.container_id=o.id) SELECT i.id,t.name,i.container_id,i.instance_stats FROM owned o JOIN item_instances i ON i.id=o.id JOIN item_templates t ON t.id=i.template_id ORDER BY i.id LIMIT 50 OFFSET $2',character_id,offset)
    equipped=[]
    if equipment:
        ids=[value for slot,value in dict(equipment).items() if slot!='character_id' and value]
        names=await db_manager.fetch_all_query('SELECT i.id,t.name FROM item_instances i JOIN item_templates t ON t.id=i.template_id WHERE i.id=ANY($1::uuid[])',ids)
        lookup={r['id']:r['name'] for r in names}
        equipped=[{'slot':slot,'name':lookup.get(value,'Missing instance'),'guid':value} for slot,value in dict(equipment).items() if slot!='character_id' and value]
    live=request.app.state.world.active_characters.get(character_id)
    skills=await db_manager.fetch_all_query('SELECT skill_name,rank FROM character_skills WHERE character_id=$1 ORDER BY skill_name',character_id)
    abilities=await db_manager.fetch_all_query('SELECT ability_internal_name FROM character_abilities WHERE character_id=$1 ORDER BY ability_internal_name LIMIT 100',character_id)
    core=dict(character)
    if isinstance(core.get("runtime_state"),str):core["runtime_state"]=json.loads(core["runtime_state"])
    if live:core.update(hp=live.hp,essence=live.essence,location_id=live.location_id,xp_total=live.xp_total,xp_pool=live.xp_pool,status=live.status,coinage=live.coinage)
    return jsonable_encoder({'character':core,'stats':dict(live.stats) if live else dict(stats) if stats else {},'skills':dict(live.skills) if live else {r['skill_name']:r['rank'] for r in skills},'abilities':[r['ability_internal_name'] for r in abilities],'conditions':live.effects if live else core.get('runtime_state',{}),'equipment':equipped,'inventory':[{**dict(i),'instance_stats':json.loads(i['instance_stats']) if isinstance(i['instance_stats'],str) else i['instance_stats']} for i in items],'inventory_offset':offset,'inventory_more':len(items)==50})

@router.get('/analytics')
async def analytics():
    connections=await db_manager.fetch_all_query("SELECT date_trunc('day',created_at) AS day,event,count(*) AS events,count(DISTINCT player_id) AS accounts FROM connection_events GROUP BY day,event ORDER BY day DESC LIMIT 100")
    economy=await db_manager.fetch_all_query('SELECT reason,sum(coin_delta) AS coins,sum(xp_delta) AS xp,count(*) AS events FROM economy_ledger GROUP BY reason ORDER BY reason')
    gameplay=await db_manager.fetch_all_query('SELECT metric,sum(total) AS total FROM gameplay_metrics GROUP BY metric')
    return {'connections':[dict(r) for r in connections],'economy':[dict(r) for r in economy],'gameplay':[dict(r) for r in gameplay]}

@router.get('/logs')
async def logs(request: Request, q: str = '', level: str = '', offset: int = Query(0,ge=0), limit: int = Query(50,ge=1,le=100)):
    entries=[e for e in reversed(request.app.state.logs.entries) if q[:100].lower() in e['message'].lower() and (not level or e['level']==level)]
    audit=await db_manager.fetch_all_query('SELECT * FROM builder_audit ORDER BY id DESC LIMIT 100')
    return {'runtime':entries[offset:offset+limit],'has_more':len(entries)>offset+limit,'audit':[dict(a) for a in audit]}

@router.get('/entities/{table}')
async def entities(table: str, q: str = '', offset: int = Query(0,ge=0), limit: int = Query(50,ge=1,le=100), area_id: int | None = None):
    cols=await columns(table)
    order='id' if any(c['column_name']=='id' for c in cols) else 'character_id' if any(c['column_name']=='character_id' for c in cols) else cols[0]['column_name']
    # Identifiers only come from the server allowlist. Values remain parameterized.
    area_filter=f' AND t.area_id={int(area_id)}' if table=='rooms' and area_id is not None else f' AND t.source_room_id IN (SELECT id FROM rooms WHERE area_id={int(area_id)})' if table=='exits' and area_id is not None else ''
    rows=await db_manager.fetch_all_query(f'''SELECT to_jsonb(t) AS data FROM "{table}" t
        WHERE to_jsonb(t)::text ILIKE $1 {area_filter} ORDER BY t."{order}" LIMIT $2 OFFSET $3''', '%'+q[:100]+'%',limit,offset)
    return [json.loads(r['data']) for r in rows]

@router.post('/entities/{table}')
async def edit(table: str, body: Edit, request: Request, player=Depends(admin_player)):
    async with request.app.state.world.mutation_lock:
        return await _edit(table,body,request,player)

async def _edit(table,body,request,player):
    if table not in EDITABLE:
        raise HTTPException(403, 'This entity is read-only')
    cols={c['column_name']:dict(c) for c in await columns(table)}
    values=dict(body.values)
    if not values or len(json.dumps(values)) > 50000 or any(k not in cols for k in values):
        raise HTTPException(422, 'Invalid fields')
    for protected in ('id','created_at','updated_at','claimed_by','claimed_at','instance_id','remaining','depleted_at'):
        if protected in values:
            raise HTTPException(422, f'{protected} is managed by the server')
    if table == 'balance_rules' and 'value' in values:
        from game.balance import RULES
        name=values.get('name') or (body.original or {}).get('name')
        if name in RULES and not RULES[name][1]<=float(values['value'])<=RULES[name][2]:
            raise HTTPException(422,'Balance value is outside its supported range')
    if table == 'class_kits' and 'definition' in values:
        definition=values['definition']
        if not isinstance(definition,list) or len(definition)!=5 or not isinstance(definition[3],(float,int)) or not .1<=definition[3]<=5:
            raise HTTPException(422,'Class kit requires [basic,attribute,signature,multiplier,description]')
    if table == 'quests' and 'objectives' in values:
        objectives=values['objectives']
        if not isinstance(objectives,list) or not objectives or any(not isinstance(o,dict) or o.get('kind') not in {'visit','talk','gather','craft','kill'} or 'target' not in o or not isinstance(o.get('label'),str) or type(o.get('count',1)) is not int or not 1<=o.get('count',1)<=100 for o in objectives):
            raise HTTPException(422,'Provide objectives with kind, target, label, and positive count (1–100)')
    if table == 'rooms' and 'coinage' in values:
        raise HTTPException(422,'Room coinage is live state and cannot be edited here')
    if table == 'recipes':
        ingredients=values.get('ingredients')
        if ingredients is not None and (not isinstance(ingredients,dict) or not ingredients or any(not str(k).isdigit() or type(v)!=int or v<1 or v>100 for k,v in ingredients.items())):
            raise HTTPException(422,'Ingredients must map template IDs to positive quantities (1-100)')
    if table == 'exits' and 'direction' in values:
        from game.utils import get_canonical_direction
        direction=get_canonical_direction(values['direction'])
        if not direction:
            direction=values['direction'].strip().lower()
            if not direction or len(direction)>50 or not all(c.isalnum() or c in ' -' for c in direction):
                raise HTTPException(422,'Use a compass direction or a short named path')
        values['direction']=direction
    params=[json.dumps(v) if cols[k]['data_type'] in ('json','jsonb') else v for k,v in values.items()]
    try:
        async with db_manager.pool.acquire() as conn:
            async with conn.transaction():
                original=body.original
                if original is not None:
                    if type(original.get('id')) is not int:
                        raise HTTPException(422,'An integer entity ID is required')
                    current=await conn.fetchval(f'SELECT to_jsonb(t) FROM "{table}" t WHERE id=$1 FOR UPDATE',original['id'])
                    if not current:
                        raise HTTPException(404,'Entity no longer exists')
                    if json.loads(current)!=original:
                        raise HTTPException(409,'Someone changed this entity. Reload before saving.')
                    sets=', '.join(f'"{k}"=${i+1}' for i,k in enumerate(values))
                    row=await conn.fetchrow(f'UPDATE "{table}" SET {sets} WHERE id=${len(params)+1} RETURNING *',*params,original['id'])
                    action='update'
                else:
                    names=', '.join(f'"{k}"' for k in values)
                    slots=', '.join(f'${i+1}' for i in range(len(values)))
                    row=await conn.fetchrow(f'INSERT INTO "{table}" ({names}) VALUES ({slots}) RETURNING *',*params)
                    action='create'
                await conn.execute('INSERT INTO builder_audit(player_id,action,entity,entity_id,details) VALUES($1,$2,$3,$4,$5)',
                    player['id'],action,table,str(row['id']),json.dumps({'before':original,'changes':body.values}))
    except (asyncpg.PostgresError, TypeError, ValueError):
        raise HTTPException(422,'Invalid value, duplicate name, or missing referenced entity')
    return jsonable_encoder(dict(row))

@router.post('/publish')
async def publish(request: Request, player=Depends(admin_player)):
    from web.builds import hot_publish
    await hot_publish(request.app)
    await db_manager.execute_query('INSERT INTO builder_audit(player_id,action,entity) VALUES($1,$2,$3)',player['id'],'publish','world')
    return {'ok':True,'rooms':len(request.app.state.world.rooms)}

@router.get('/map')
async def world_map(area_id: int | None = None):
    if area_id is None:
        row=await db_manager.fetch_one_query('SELECT min(id) AS id FROM areas')
        area_id=row['id']
    rooms=await db_manager.fetch_all_query('SELECT * FROM rooms WHERE area_id=$1 ORDER BY id LIMIT 2000',area_id)
    exits=await db_manager.fetch_all_query('SELECT e.* FROM exits e JOIN rooms r ON r.id=e.source_room_id WHERE r.area_id=$1 ORDER BY e.id LIMIT 10000',area_id)
    return {'rooms':[jsonable_encoder(dict(r)) for r in rooms],'exits':[jsonable_encoder(dict(r)) for r in exits]}

@router.get('/warnings-file')
async def warnings_file():
    import os
    from pathlib import Path
    from fastapi.responses import FileResponse
    path=Path(os.getenv('LOG_DIR','logs'))/'warnings-errors.log'
    if not path.exists():raise HTTPException(404,'No warning archive exists yet')
    return FileResponse(path,filename='chrozal-warnings-errors.log',media_type='text/plain')
