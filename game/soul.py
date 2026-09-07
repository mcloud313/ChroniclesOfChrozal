"""Clerical soul rites with transactional XP payment and irreversible death guards."""
import config

async def cmd_tether(c,w,args):
    if not args:
        await c.send(f'Soul tether: {c.spiritual_tether}/10. Releasing at zero permanently ends this character. Clerics can use tether <character> at a node to restore one point.');return True
    if w.get_class_name(c.class_id).lower()!='cleric' or 'NODE' not in c.location.flags or c.is_fighting:
        await c.send('Only a cleric at a peaceful node can mend a soul tether.');return True
    target_name=args.removesuffix(' confirm')
    target=c if target_name.lower() in ('self',c.name.lower()) else c.location.get_character_by_name(target_name)
    if not target or target.status!='ALIVE' or not 0<target.spiritual_tether<10:
        await c.send('Choose a living soul here with fewer than ten tether points.');return True
    cost=250*target.level+1000*(10-target.spiritual_tether)
    if c.xp_total<cost:
        await c.send(f'This rite costs the cleric {cost:,} absorbed XP. You have {int(c.xp_total):,}.');return True
    if not args.endswith(' confirm'):
        await c.send(f'The rite costs YOU {cost:,} absorbed XP. Use tether {target.name} confirm to perform it.');return True
    return await perform_rite(c,target,w,cost)

async def perform_rite(c,target,w,cost):
    async with w.db_manager.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('UPDATE characters SET xp_total=$1 WHERE id=$2',c.xp_total-cost,c.dbid)
            await conn.execute('UPDATE characters SET spiritual_tether=$1 WHERE id=$2',target.spiritual_tether+1,target.dbid)
            await conn.execute('INSERT INTO character_journal(character_id,entry) VALUES($1,$2)',target.dbid,f'{c.name} restored a soul tether at a cost of {cost} XP.')
    c.xp_total-=cost;target.spiritual_tether+=1;c.roundtime=15;c.is_dirty=True;target.is_dirty=True
    await c.send(f'You sacrifice {cost:,} XP. {target.name} now has {target.spiritual_tether}/10 tether.');return True
