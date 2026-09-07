"""Disposable-database, authenticated WebSocket load harness.
Creates only namespaced fixture accounts; deletes only those accounts afterward.
The game must already be running against DATABASE_URL. Never use production.
"""
import argparse
import asyncio
import hashlib
import json
import os
import secrets
import statistics
import sys
import time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
import asyncpg
import websockets

async def main(args, pool=None):
    if not args.confirm_disposable_database:
        raise SystemExit('Requires --confirm-disposable-database; use a test database only.')
    conn=await pool.acquire() if pool else await asyncpg.connect(os.environ['DATABASE_URL'])
    players=[];sessions=[];samples=[];failures=[];maximum=0;active=0
    prefix='load_'+secrets.token_hex(5)
    try:
        for index in range(args.players):
            name=f'{prefix}_{index}'
            pid=await conn.fetchval('INSERT INTO players(username,hashed_password,email) VALUES($1,$2,$3) RETURNING id',name,'disabled-load-fixture',name+'@example.test')
            players.append(pid)
            cid=await conn.fetchval("INSERT INTO characters(player_id,first_name,last_name,sex,hp,max_hp,essence,max_essence,location_id) VALUES($1,$2,'Load','They/Them',100,100,50,50,1) RETURNING id",pid,f'Traveler{index}')
            await conn.execute('INSERT INTO character_stats(character_id) VALUES($1)',cid)
            await conn.execute('INSERT INTO character_equipment(character_id) VALUES($1)',cid)
            token=secrets.token_urlsafe(32)
            await conn.execute('INSERT INTO web_sessions(token_hash,player_id) VALUES($1,$2)',hashlib.sha256(token.encode()).hexdigest(),pid)
            sessions.append(token)
        if pool:await pool.release(conn)
        else:await conn.close()
        conn=None
        ready=asyncio.Event()
        connected=0
        async def player(index,token):
            nonlocal connected,active,maximum
            try:
                async with websockets.connect(args.url,origin=args.origin,additional_headers={'Cookie':'chrozal_session='+token},proxy=None,open_timeout=60,max_size=2**20) as ws:
                    await ws.send(json.dumps({'type':'command','payload':'1'}))
                    async def until(predicate):
                        async with asyncio.timeout(90):
                            while True:
                                m=json.loads(await ws.recv())
                                if predicate(m):return m
                    await until(lambda m:m['type']=='vitals_update')
                    active+=1;maximum=max(maximum,active);connected+=1
                    if connected==args.players:ready.set()
                    await asyncio.wait_for(ready.wait(),120)
                    for round in range(args.rounds):
                        marker=f'loadcheck{index}x{round}'
                        start=time.perf_counter()
                        await ws.send(json.dumps({'type':'command','payload':'say '+marker}))
                        await until(lambda m:m['type']=='text' and marker in m['payload'])
                        samples.append((time.perf_counter()-start)*1000)
                        await asyncio.sleep(1)
                    await ws.send(json.dumps({'type':'command','payload':'quit'}))
                    active-=1
            except Exception as exc:
                failures.append({'player':index,'error':type(exc).__name__+': '+str(exc)})
                ready.set()
        start=time.perf_counter()
        await asyncio.gather(*(player(i,t) for i,t in enumerate(sessions)))
        result={'players_requested':args.players,'peak_simultaneous_in_world':maximum,
                'command_samples':len(samples),'elapsed_seconds':round(time.perf_counter()-start,2),
                'p50_ms':round(statistics.median(samples),2) if samples else None,
                'p95_ms':round(sorted(samples)[max(0,int(len(samples)*.95)-1)],2) if samples else None,
                'max_ms':round(max(samples),2) if samples else None,'failures':failures,
                'scope':'Authenticated session fixtures; same-room speech broadcast and HUD; excludes HTTP login, combat and mixed workloads.'}
        print(json.dumps(result,indent=2))
        if args.output:Path(args.output).write_text(json.dumps(result,indent=2)+'\n')
        return 1 if failures or maximum!=args.players else 0
    finally:
        if conn is not None:
            if pool:await pool.release(conn)
            elif not conn.is_closed():await conn.close()
        # Let WebSocket cleanup persist before removing fixture accounts.
        # Wait for every fixture's logout save instead of deleting records while
        # the server is still draining a mass disconnect.
        deadline=time.monotonic()+120
        while True:
            probe=await pool.acquire() if pool else await asyncpg.connect(os.environ['DATABASE_URL'])
            try:
                pending=await probe.fetchval('SELECT count(*) FROM characters WHERE player_id=ANY($1::int[]) AND total_playtime_seconds=0',players)
            finally:
                if pool:await pool.release(probe)
                else:await probe.close()
            if not pending:break
            if time.monotonic()>deadline:
                raise RuntimeError('Fixture logout saves did not complete; fixture records retained for diagnosis')
            await asyncio.sleep(.2)
        conn=await pool.acquire() if pool else await asyncpg.connect(os.environ['DATABASE_URL'])
        try:
            await conn.execute('DELETE FROM players WHERE id=ANY($1::int[])',players)
        finally:
            if pool:await pool.release(conn)
            else:await conn.close()

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--confirm-disposable-database',action='store_true');p.add_argument('--players',type=int,default=100);p.add_argument('--rounds',type=int,default=5);p.add_argument('--url',default='ws://localhost:8000/ws');p.add_argument('--origin',default='http://localhost:8000');p.add_argument('--output')
    raise SystemExit(asyncio.run(main(p.parse_args())))
