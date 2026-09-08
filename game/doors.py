"""Shared exit state for builders, navigation, searching and lock work."""
import json
from game import utils, resolver
from game.commands.movement import resolve_exit


def details(exit_data):
    value=exit_data.get('details') or {}
    if isinstance(value,str):value=json.loads(value)
    exit_data['details']=value
    return value

async def save(w, room, name, data):
    # Persist both faces of a linked door in one transaction.
    other=w.get_room(data.get('destination_room_id'));changed=[(room,name,data)]
    if other:
        candidates=[(k,e) for k,e in other.exits.items() if e.get('destination_room_id')==room.dbid and details(e).get('is_door')]
        reverse=details(data).get('reverse_exit')
        if reverse:candidates=[(k,e) for k,e in candidates if k==reverse]
        elif len(candidates)!=1:candidates=[]
        for key,back in candidates:
            if back.get('destination_room_id')==room.dbid and details(back).get('is_door'):
                for field in ('is_open','is_locked'):
                    if field in details(data):details(back)[field]=details(data)[field]
                changed.append((other,key,back))
    async with w.db_manager.pool.acquire() as conn:
        async with conn.transaction():
            for r,key,e in changed:
                await conn.execute('UPDATE exits SET details=$1 WHERE source_room_id=$2 AND direction=$3',json.dumps(details(e)),r.dbid,key)

async def trigger(c,w,trap):
    if not trap or not trap.get('is_active'):return False
    trap['is_active']=False
    damage=max(0,int(trap.get('damage',5)))
    from game.combat.outcome_handler import apply_damage
    apply_damage(c,damage)
    c.stance='Lying';c.roundtime=max(c.roundtime,3);c.is_dirty=True
    await c.send(f'<r>A trap strikes you for {damage} damage and knocks you prone!<x>')
    if not c.is_alive():await resolver.handle_defeat(c,c,w)
    return True

async def command(c,w,verb,args):
    target,_,key_name=args.partition(' with ')
    name,data=resolve_exit(c.location,target)
    if not data:return False
    d=details(data)
    if not d.get('is_door') and not d.get('trap'):
        await c.send('That path has no door or mechanism.');return True
    if verb in ('open','close'):
        if verb=='open' and d.get('is_locked'):
            await c.send('The door is locked.');return True
        if verb=='open' and await trigger(c,w,d.get('trap')):
            await save(w,c.location,name,data);return True
        d['is_open']=verb=='open'
    elif verb in ('lock','unlock'):
        key=c.find_item_in_inventory_by_name(key_name)
        if not key or d.get('lock_id') not in key.unlocks:
            await c.send('Hold the matching key: '+verb+' '+name+' with <key>.');return True
        if verb=='lock' and d.get('is_open'):
            await c.send('Close the door first.');return True
        d['is_locked']=verb=='lock'
    elif verb=='lockpick':
        if not d.get('is_locked'):await c.send('Already unlocked.');return True
        if d.get('lockpick_dc') is None:await c.send('This lock cannot be picked.');return True
        result=utils.skill_check(c,'lockpicking',dc=d['lockpick_dc']);c.roundtime=5
        await c.send(f"Lockpicking: {result['total_check']} vs DC {result['dc']}.")
        if result['success']:d['is_locked']=False
        else:await c.send('The lock resists.');return True
    elif verb=='disarm':
        trap=d.get('trap')
        if not trap or not trap.get('is_active') or 'exit_'+name not in c.detected_traps:
            await c.send('Search and locate an active trap first.');return True
        result=utils.skill_check(c,'disable device',dc=trap.get('disarm_dc',20));c.roundtime=4
        if result['success']:trap['is_active']=False
        else:await trigger(c,w,trap)
    else:return False
    await save(w,c.location,name,data)
    await c.send(f'{name.title()}: '+('open' if d.get('is_open') else 'closed')+', '+('locked' if d.get('is_locked') else 'unlocked')+'.')
    return True
