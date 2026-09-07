"""Finite public contracts, claimed by one character or a co-located party."""
import json


def decode(value):
    return json.loads(value) if isinstance(value,str) else value

async def populate(w, board):
    date=f'{w.game_year}-{w.game_month}-{w.game_day}'
    async with w.db_manager.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('SELECT pg_advisory_xact_lock($1)',int(board['id']))
            if await conn.fetchval('SELECT 1 FROM board_notices WHERE board_id=$1 AND game_date=$2',board['id'],date):return date
            templates=await conn.fetch('SELECT * FROM quests WHERE giver_room_id=$1 ORDER BY min_level,id',board['room_id'])
            if not templates:return date
            for slot in range(board['daily_limit']):
                q=templates[slot%len(templates)];party=2+(slot%2) if slot>=8 else 1
                objectives=[o for o in decode(q['objectives']) if o['kind']!='talk']
                if not objectives:continue
                await conn.execute('''INSERT INTO board_notices(board_id,game_date,slot,name,description,min_level,group_size,objectives,reward_xp,reward_coinage,faction_id,required_standing,reputation_reward)
                  VALUES($1,$2,$3,$4,$5,$6,$7,$8,$9,$10,$11,$12,$13)''',board['id'],date,slot,q['name'], 'The board requests: '+ '; '.join(o['label'] for o in objectives)+'. Return here to report completion.',q['min_level'],party,json.dumps(objectives),q['reward_xp'],q['reward_coinage'],q['faction_id'],q['required_standing'],q['reputation_reward'])
    return date

async def event(c,w,kind,target):
    row=await w.db_manager.fetch_one_query('SELECT nc.*,n.objectives,n.group_size FROM notice_claims nc JOIN board_notices n ON n.id=nc.notice_id WHERE character_id=$1 AND active',c.dbid)
    if not row:return
    if row['group_size']>1:
        ids=await w.db_manager.fetch_all_query('SELECT character_id FROM notice_claims WHERE notice_id=$1 AND active',row['notice_id'])
        present=[w.active_characters.get(r['character_id']) for r in ids]
        if any(not p or p.location!=c.location or not p.is_alive() or not c.group or p not in c.group.members for p in present):return
    progress=decode(row['progress']);objectives=decode(row['objectives'])
    for i,o in enumerate(objectives):
        if o['kind']==kind and str(o['target']).lower()==str(target).lower():progress[str(i)]=min(o.get('count',1),progress.get(str(i),0)+1)
    await w.db_manager.execute_query('UPDATE notice_claims SET progress=$1 WHERE notice_id=$2 AND character_id=$3',json.dumps(progress),row['notice_id'],c.dbid)

async def command(c,w,args):
    board=await w.db_manager.fetch_one_query('SELECT * FROM notice_boards WHERE room_id=$1',c.location_id)
    active=await w.db_manager.fetch_one_query('SELECT nc.*,n.* FROM notice_claims nc JOIN board_notices n ON n.id=nc.notice_id WHERE character_id=$1 AND active',c.dbid)
    if args.startswith('abandon') and active:
        if args!='abandon confirm':
            await c.send('Abandoning ends this contract for every participant, without rewards. Use quest abandon confirm.');return True
        await w.db_manager.execute_query('UPDATE notice_claims SET active=false WHERE notice_id=$1',active['notice_id'])
        await c.send('The contract is abandoned. Its notice remains unavailable for the day.');return True
    if not board:
        await c.send('Visit a notice board to accept or complete a contract.'+(f" Active: {active['name']}; progress {active['progress']}" if active else ''));return True
    date=await populate(w,board)
    if not args:
        rows=await w.db_manager.fetch_all_query('SELECT * FROM board_notices WHERE board_id=$1 AND game_date=$2 AND NOT claimed AND NOT completed ORDER BY slot',board['id'],date)
        lines=[f"{board['name']} — {len(rows)} unclaimed today. quest accept <id>; quest complete. One active contract per character."]
        if active:lines.append(f"Active: {active['name']} — {active['progress']}")
        lines += [f"{r['id']}. {r['name']} — level {r['min_level']}+, {r['group_size']} adventurer(s)\n{r['description']}" for r in rows]
        await c.send('\n'.join(lines));return True
    if args.startswith('accept ') and args[7:].isdigit():
        async with w.db_manager.pool.acquire() as conn:
            async with conn.transaction():
                q=await conn.fetchrow('SELECT * FROM board_notices WHERE id=$1 AND board_id=$2 AND game_date=$3 AND NOT claimed FOR UPDATE',int(args[7:]),board['id'],date)
                if not q:await c.send('That notice is no longer available.');return True
                members=[c] if q['group_size']==1 else list(c.group.members) if c.group and c.group.leader==c else []
                if len(members)!=q['group_size'] or any(m.location!=c.location or not m.is_alive() or m.level<q['min_level'] for m in members):
                    await c.send(f"Requires exactly {q['group_size']} present adventurer(s), level {q['min_level']}+. The group leader accepts.");return True
                for m in members:
                    standing=await conn.fetchval('SELECT standing FROM character_reputation WHERE character_id=$1 AND faction_id=$2',m.dbid,q['faction_id']) if q['faction_id'] else 0
                    if q['faction_id'] and (standing or 0)<q['required_standing']:
                        await c.send('An adventurer lacks the required faction standing.');return True
                ids=[m.dbid for m in members]
                if await conn.fetchval('SELECT 1 FROM notice_claims WHERE character_id=ANY($1::int[]) AND active',ids):
                    await c.send('Each adventurer may hold only one active contract.');return True
                await conn.execute('UPDATE board_notices SET claimed=true WHERE id=$1',q['id'])
                for m in members:await conn.execute('INSERT INTO notice_claims(notice_id,character_id) VALUES($1,$2)',q['id'],m.dbid)
        for m in members:await m.send('Contract accepted: '+q['description'])
        return True
    if args=='complete' and active and active['board_id']==board['id']:
        async with w.db_manager.pool.acquire() as conn:
            async with conn.transaction():
                claims=await conn.fetch('SELECT * FROM notice_claims WHERE notice_id=$1 AND active FOR UPDATE',active['notice_id'])
                objectives=decode(active['objectives']);members=[]
                for claim in claims:
                    m=w.active_characters.get(claim['character_id']);progress=decode(claim['progress'])
                    if not m or m.location!=c.location or not m.is_alive() or any(progress.get(str(i),0)<o.get('count',1) for i,o in enumerate(objectives)):
                        await c.send('All contracted adventurers must finish their objectives and return here together.');return True
                    members.append(m)
                if not members:return True
                for m in members:
                    await conn.execute('UPDATE characters SET xp_pool=$1,coinage=$2 WHERE id=$3',m.xp_pool+active['reward_xp'],m.coinage+active['reward_coinage'],m.dbid)
                    if active['faction_id']:
                        await conn.execute('INSERT INTO character_reputation(character_id,faction_id,standing) VALUES($1,$2,$3) ON CONFLICT(character_id,faction_id) DO UPDATE SET standing=character_reputation.standing+EXCLUDED.standing',m.dbid,active['faction_id'],active['reputation_reward'])
                    await conn.execute("INSERT INTO economy_ledger(character_id,reason,coin_delta,xp_delta) VALUES($1,'notice reward',$2,$3)",m.dbid,active['reward_coinage'],active['reward_xp'])
                await conn.execute('UPDATE notice_claims SET active=false WHERE notice_id=$1',active['notice_id'])
                await conn.execute('UPDATE board_notices SET completed=true WHERE id=$1',active['notice_id'])
        for m in members:
            m.xp_pool+=active['reward_xp'];m.coinage+=active['reward_coinage'];m.is_dirty=True
            await m.send('Contract completed and removed from the board. Your reward is ready to soak at a node.')
        return True
    await c.send('Use quest, quest accept <id>, or quest complete.');return True
