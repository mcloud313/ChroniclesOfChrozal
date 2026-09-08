"""Persistent scarce resources; tools, open containers and stations."""
import json
import logging
import random
from game.living import refresh_inventory
log=logging.getLogger(__name__)
ATTRIBUTES=dict(mining='might',herbalism='intellect',skinning='agility',fishing='agility',logging='might',farming='vitality',hunting='agility',smithing='might',alchemy='intellect',cooking='intellect',runecrafting='aura',brewing='intellect')

def held_tool(c,p):
    from game.hands import assign
    assign(c)
    items=list(c._inventory_items.values())+[c._equipped_items[s] for s in ('main_hand','off_hand') if c._equipped_items.get(s)]
    return next((i for i in items if i.condition>0 and p in i.stats.get('tool_for',[])),None)

def check(c,p,difficulty):
    rank=max(c.skills.get(p,0),c.skills.get('blacksmithing',0) if p=='smithing' else 0)
    modifier={'might':'might_mod','vitality':'vit_mod','agility':'agi_mod','intellect':'int_mod','aura':'aura_mod'}[ATTRIBUTES[p]]
    bonus=rank//5+getattr(c,modifier,0)
    roll=random.randint(1,20)
    return roll!=1 and (roll==20 or roll+bonus>=difficulty),f'[d20:{roll} + skill/stat:{bonus} vs difficulty:{difficulty}]'

def accessible(c):
    def visit(i):
        yield i
        if i.instance_stats.get('is_open'):
            for child in i.contents.values():yield from visit(child)
    seen=set()
    for item in list(c._inventory_items.values())+list(c._equipped_items.values()):
        for child in visit(item):
            if child.id not in seen:seen.add(child.id);yield child

async def replenish(w,dt):
    # Tick-rate independent Poisson recovery, mean one hour after cooldown.
    chance=1-2.718281828459045**(-min(max(dt,0),30)/3600)
    if chance:
        await w.db_manager.execute_query("""UPDATE resource_nodes SET remaining=capacity,uses=0,depleted_at=NULL
          WHERE remaining=0 AND depleted_at+respawn_seconds*interval '1 second'<=now() AND random()<$1""",chance)

async def gather(c,w,args,corpse=None):
    if not args:
        rows=await w.db_manager.fetch_all_query('SELECT name,profession,remaining FROM resource_nodes WHERE room_id=$1 ORDER BY name',c.location_id)
        await c.send('Resources:\n'+'\n'.join(f'{r["name"]} ({r["profession"]}) — '+('available' if r['remaining'] else 'depleted') for r in rows if r['profession'].upper()+'_NODE' in c.location.flags));return True
    async with w.db_manager.pool.acquire() as conn:
        async with conn.transaction():
            n=await conn.fetchrow('SELECT * FROM resource_nodes WHERE room_id=$1 AND lower(name)=lower($2) FOR UPDATE',c.location_id,args.strip())
            if not n or n['profession'].upper()+'_NODE' not in c.location.flags:
                await c.send('No matching resource node here. Use GATHER to list nodes.');return True
            p=n['profession']
            if not n['remaining']:
                await c.send('This node is depleted. Explore elsewhere; recovery is rare.');return True
            if not held_tool(c,p):
                await c.send(f'Hold a {p} tool first.');return True
            if c.hands_are_full():
                await c.send('Your hands are full. Hold your tool in one hand and free the other.');return True
            t=w.get_item_template(n['item_template_id'])
            if c.get_current_weight()+t.get('stats',{}).get('weight',0)>c.get_max_weight():
                await c.send('You cannot carry the harvest.');return True
            if corpse is not None:
                claimed=await conn.fetchval('INSERT INTO harvest_claims(token,character_id) VALUES($1,$2) ON CONFLICT DO NOTHING RETURNING token',corpse.harvest_token,c.dbid)
                if not claimed:
                    await c.send('That carcass has already been skinned.');return True
            success,math=check(c,p,n['difficulty']);uses=n['uses']+1
            exhausted=not success or n['remaining']<=1 or random.random()<min(.95,.10+.15*uses)
            await conn.execute('UPDATE resource_nodes SET uses=$1,remaining=$2,depleted_at=CASE WHEN $2=0 THEN now() ELSE NULL END WHERE id=$3',uses,0 if exhausted else n['remaining']-1,n['id'])
            if success:await conn.execute('INSERT INTO item_instances(template_id,owner_char_id) VALUES($1,$2)',n['item_template_id'],c.dbid)
    c.roundtime=5;c.is_dirty=True
    await refresh_inventory(c,w)
    message=(f'You gather {t["name"]}. ' if success else 'Your attempt fails, spoiling the remaining resource. ')+math+(' The node is exhausted.' if exhausted else '')
    if success:
        c.skills[p]=min(100,c.skills.get(p,0)+1)
        from game.adventure import event
        await event(c,w,'gather',args)
    log.info('GATHER character=%s node=%s %s',c.dbid,n['id'],message)
    await c.send(message);return True

async def craft(c,w,args):
    if not args:
        rows=await w.db_manager.fetch_all_query('SELECT name,profession,description FROM recipes ORDER BY name LIMIT 100')
        await c.send('Recipes:\n'+'\n'.join(f'{r["name"]} ({r["profession"]}): {r["description"]}' for r in rows));return True
    async with w.db_manager.pool.acquire() as conn:
        async with conn.transaction():
            r=await conn.fetchrow('SELECT * FROM recipes WHERE lower(name)=lower($1)',args.strip())
            if not r:
                await c.send('Unknown recipe. Use CRAFT to list recipes.');return True
            p=r['profession']
            if p.upper()+'_STATION' not in c.location.flags:
                await c.send(f'Find a {p} station first.');return True
            tool=held_tool(c,p)
            if not tool:
                await c.send(f'Hold a {p} tool first.');return True
            ingredients=json.loads(r['ingredients']) if isinstance(r['ingredients'],str) else r['ingredients']
            if not ingredients:
                await c.send('This recipe has no ingredients; tell a builder.');return True
            selected=[];equipped={i.id for i in c._equipped_items.values()}
            materials=[i for i in accessible(c) if i.id not in equipped and i.id!=tool.id and not i.contents]
            for tid,qty in ingredients.items():
                candidates=[i for i in materials if i.template_id==int(tid)]
                if not isinstance(qty,int) or qty<1 or len(candidates)<qty:
                    await c.send('Required materials must be held or inside open containers.');return True
                selected.extend(candidates[:qty])
            from game.hands import assign
            if len(assign(c))>=2 and not any(i.id in c._inventory_items for i in selected):
                await c.send('Free a hand for the finished item.');return True
            output=w.get_item_template(r['output_template_id'])
            if c.get_current_weight()-sum(i.weight for i in selected)+output.get('stats',{}).get('weight',0)>c.get_max_weight():
                await c.send('You cannot carry the finished item.');return True
            ids=[i.id for i in selected]
            locked=await conn.fetch('SELECT id FROM item_instances WHERE id=ANY($1::uuid[]) FOR UPDATE',ids)
            if len(locked)!=len(ids):
                await c.send('Your materials changed. Try again.');return True
            success,math=check(c,p,r['difficulty'])
            await conn.execute('DELETE FROM item_instances WHERE id=ANY($1::uuid[])',ids)
            if success:await conn.execute('INSERT INTO item_instances(template_id,owner_char_id) VALUES($1,$2)',r['output_template_id'],c.dbid)
    for i in selected:w._all_item_instances.pop(i.id,None)
    await refresh_inventory(c,w);c.roundtime=6;c.is_dirty=True
    message=(f'You craft {output["name"]}. ' if success else 'Your work fails; the ingredients are spoiled. ')+math
    if success:
        c.skills[p]=min(100,c.skills.get(p,0)+1)
        from game.adventure import event
        await event(c,w,'craft',args)
    log.info('CRAFT character=%s recipe=%s %s',c.dbid,r['id'],message)
    await c.send(message);return True
