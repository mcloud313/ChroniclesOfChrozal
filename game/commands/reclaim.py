"""Explicit instance destruction and emergency healing; never infer a deletion."""
import logging
import time
log=logging.getLogger(__name__)

async def destroy(c,w,args):
    if args.strip().lower()=='confirm':
        pending=getattr(c,'pending_destroy',None)
        c.pending_destroy=None
        if not pending or pending[1]<time.monotonic():
            await c.send('No current destruction request. Use destroy <held item or GUID>.');return True
        item=c._inventory_items.get(pending[0])
    else:
        matches=[i for i in c._inventory_items.values() if str(i.id)==args.strip() or i.name.lower()==args.strip().lower()]
        item=matches[0] if len(matches)==1 else None
        if not item:
            await c.send('Select exactly one held item. For duplicates use destroy <GUID>; inventory lists GUIDs.');return True
    if not item:
        await c.send('That instance is no longer held.');return True
    relic=await w.db_manager.fetch_one_query('SELECT id FROM relics WHERE template_id=$1',item.template_id)
    if relic or 'RELIC' in item.flags or item.contents:
        await c.send('Relics and containers with contents cannot be destroyed.');return True
    if args.strip().lower()!='confirm':
        c.pending_destroy=(item.id,time.monotonic()+30)
        await c.send(f'Destroy {item.name} [{item.id}] permanently? Type DESTROY CONFIRM within 30 seconds.');return True
    await w.db_manager.delete_item_instance(item.id)
    c._inventory_items.pop(item.id,None);w._all_item_instances.pop(item.id,None);c.is_dirty=True
    log.info('Destroyed instance=%s template=%s character=%s',item.id,item.template_id,c.dbid)
    await c.send(f'You destroy {item.name}.');return True

async def administer(c,w,args):
    potion_name,sep,target_name=args.partition(' to ')
    target=c.location.get_character_by_name(target_name) if sep else None
    potion=c.find_item_in_inventory_by_name(potion_name)
    if not target or target.status!='DYING' or not potion or potion.item_type!='POTION' or potion.stats.get('effect')!='heal_hp' or potion.stats.get('amount',0)<=0:
        await c.send('administer <held healing potion> to <dying character>');return True
    await w.db_manager.delete_item_instance(potion.id)
    c._inventory_items.pop(potion.id,None);w._all_item_instances.pop(potion.id,None)
    target.hp=1;target.status='ALIVE';target.death_timer_ends_at=None;target.is_dirty=True;c.is_dirty=True;c.roundtime=2
    await c.location.broadcast(f'<g>{c.name} administers {potion.name} to {target.name}, bringing them back from the brink at 1 HP.<x>')
    return True
