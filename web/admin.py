"""Allowlisted, authenticated world editor with optimistic concurrency and audit."""
import json
import asyncpg
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, Field
from game.database import db_manager
from web.auth import admin_player

EDITABLE = {'class_kits','factions','balance_rules','quests','areas','rooms','exits','room_objects','ambient_scripts','item_templates','mob_templates',
            'mob_attacks','mob_loot_table','loot_tables','loot_table_entries','ability_templates',
            'races','classes','damage_types','shop_inventories','resource_nodes','recipes','npc_schedules','relics'}
READONLY = {'player_homes','market_listings','character_reputation','economy_ledger','game_mail','character_quests','characters','character_stats','character_skills','character_abilities','character_equipment',
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
async def status(request: Request):
    world=request.app.state.world
    return {'players':len(world.active_characters),'connections':len(request.app.state.connections),
        'rooms':len(world.rooms),'npcs':sum(len(r.mobs) for r in world.rooms.values()),
        'online':[{'id':c.dbid,'name':c.name,'room':c.location_id,'hp':c.hp} for c in world.active_characters.values()],
        'mobs':[{'id':m.instance_id,'name':m.name,'room':r.dbid,'hp':m.hp} for r in world.rooms.values() for m in r.mobs]}

@router.get('/logs')
async def logs(request: Request):
    audit=await db_manager.fetch_all_query('SELECT * FROM builder_audit ORDER BY id DESC LIMIT 100')
    return {'runtime':list(request.app.state.logs.entries),'audit':[dict(a) for a in audit]}

@router.get('/entities/{table}')
async def entities(table: str, q: str = '', offset: int = Query(0,ge=0), limit: int = Query(50,ge=1,le=100)):
    await columns(table)
    # Identifiers only come from the server allowlist. Values remain parameterized.
    rows=await db_manager.fetch_all_query(f'''SELECT to_jsonb(t) AS data FROM "{table}" t
        WHERE to_jsonb(t)::text ILIKE $1 ORDER BY to_jsonb(t)::text LIMIT $2 OFFSET $3''', '%'+q[:100]+'%',limit,offset)
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
            raise HTTPException(422,'Choose a compass direction')
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
async def world_map():
    rooms=await db_manager.fetch_all_query('SELECT * FROM rooms ORDER BY id LIMIT 2000')
    exits=await db_manager.fetch_all_query('SELECT * FROM exits ORDER BY id LIMIT 10000')
    return {'rooms':[jsonable_encoder(dict(r)) for r in rooms],'exits':[jsonable_encoder(dict(r)) for r in exits]}
