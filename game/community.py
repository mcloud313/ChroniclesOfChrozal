"""Persistent offline correspondence, reputation gates and endgame infusion."""
import json
import config

async def rule(w,name,default):
    row=await w.db_manager.fetch_one_query('SELECT value FROM balance_rules WHERE name=$1',name)
    return int(row['value']) if row else default

async def has_standing(c,w,row):
    faction=row.get('faction_id')
    if not faction:return True
    rep=await w.db_manager.fetch_one_query('SELECT standing FROM character_reputation WHERE character_id=$1 AND faction_id=$2',c.dbid,faction)
    return (rep['standing'] if rep else 0)>=row.get('required_standing',0)

async def cmd_reputation(c,w,args):
    rows=await w.db_manager.fetch_all_query('SELECT f.name,f.description,COALESCE(r.standing,0) standing FROM factions f LEFT JOIN character_reputation r ON r.faction_id=f.id AND r.character_id=$1 ORDER BY f.id',c.dbid)
    await c.send('\n'.join(f"{r['name']}: {r['standing']} — {r['description']}" for r in rows) or 'You have not encountered any factions.');return True

async def cmd_mail(c,w,args):
    if not args or args=='inbox':
        rows=await w.db_manager.fetch_all_query('SELECT id,subject,read_at FROM game_mail WHERE recipient_id=$1 ORDER BY id DESC LIMIT 50',c.dbid)
        await c.send('Mail: mail read <id>; mail send <character id> | subject | message\n'+ '\n'.join(f"{r['id']}. {r['subject']}"+(' [new]' if not r['read_at'] else '') for r in rows));return True
    if args.startswith('read '):
        try:id=int(args[5:])
        except ValueError:return True
        row=await w.db_manager.fetch_one_query('UPDATE game_mail SET read_at=now() WHERE id=$1 AND recipient_id=$2 RETURNING subject,body',id,c.dbid)
        await c.send(f"{row['subject']}\n{row['body']}" if row else 'Letter not found.');return True
    if args.startswith('send '):
        parts=[p.strip() for p in args[5:].split('|')]
        if len(parts) not in (3,4) or not parts[0].isdigit() or not 1<=len(parts[1])<=100 or not 1<=len(parts[2])<=3000:
            await c.send('mail send <character id> | subject | message [| loose item UUID]');return True
        recipient=int(parts[0]);fee=await rule(w,'mail_fee',2)
        if c.coinage<fee:await c.send(f'Postage costs {fee} coins.');return True
        item=c._inventory_items.get(parts[3]) if len(parts)==4 else None
        if len(parts)==4 and (not item or item.contents):await c.send('Attach an empty, loose item from your inventory by UUID.');return True
        async with w.db_manager.pool.acquire() as conn:
            async with conn.transaction():
                if not await conn.fetchval("SELECT id FROM characters WHERE id=$1 AND status<>'PERMADEAD'",recipient):
                    await c.send('No living character has that id.');return True
                if item:
                    updated=await conn.fetchval('UPDATE item_instances SET owner_char_id=$1 WHERE id=$2 AND owner_char_id=$3 RETURNING id',recipient,item.id,c.dbid)
                    if not updated:return True
                await conn.execute('INSERT INTO game_mail(sender_id,recipient_id,subject,body) VALUES($1,$2,$3,$4)',c.dbid,recipient,parts[1],parts[2]+(f'\nEnclosed: {item.name} (delivered to inventory).' if item else ''))
                await conn.execute('UPDATE characters SET coinage=$1 WHERE id=$2',c.coinage-fee,c.dbid)
                await conn.execute("INSERT INTO economy_ledger(character_id,reason,coin_delta) VALUES($1,'postage',$2)",c.dbid,-fee)
        c.coinage-=fee;c.is_dirty=True
        if item:
            c._inventory_items.pop(item.id,None)
            receiver=w.active_characters.get(recipient)
            if receiver:receiver._inventory_items[item.id]=item
            else:w._all_item_instances.pop(item.id,None)
        await c.send('Letter delivered.');return True
    await c.send('Use mail inbox, mail read <id>, or mail send.');return True

async def cmd_infuse(c,w,args):
    if c.level<config.MAX_LEVEL or 'NODE' not in c.location.flags or c.is_fighting:
        await c.send('Item infusion requires level 99 and a peaceful node.');return True
    item=c.find_item_in_inventory_by_name(args)
    if not item or item.item_type not in ('WEAPON','TWO_HANDED_WEAPON','RANGED_WEAPON','ARMOR'):
        await c.send('Choose a loose weapon or armor item to infuse.');return True
    rank=int(item.instance_stats.get('infusion_rank',0))+1
    cost=await rule(w,'infusion_base_xp',100000)*rank*rank
    if rank>await rule(w,'infusion_max_rank',10) or c.xp_total-cost<__import__('game.utils',fromlist=['xp_needed_for_level']).xp_needed_for_level(98):
        await c.send(f'Infusion requires {cost:,} surplus XP above the level-99 threshold and an unfinished item.');return True
    stats={**item.instance_stats,'infusion_rank':rank}
    async with w.db_manager.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('UPDATE characters SET xp_total=$1 WHERE id=$2',c.xp_total-cost,c.dbid)
            await conn.execute('UPDATE item_instances SET instance_stats=$1 WHERE id=$2 AND owner_char_id=$3',json.dumps(stats),item.id,c.dbid)
            await conn.execute("INSERT INTO economy_ledger(character_id,reason,xp_delta) VALUES($1,'infusion',$2)",c.dbid,-cost)
    c.xp_total-=cost;c.is_dirty=True;item.instance_stats=stats;c.roundtime=10
    await c.send(f'{item.name} reaches infusion rank {rank}; {cost:,} XP spent.');return True
