import json
import secrets
import pytest
from unittest.mock import AsyncMock
from test_integration import client,login


def test_account_reset_is_single_use_and_revokes_sessions(client):
    from web.recovery import issue
    from game.database import db_manager as db
    headers=login(client,True)
    async def fixture():
        pid=await db.create_player_account('reset'+secrets.token_hex(4),'disabled',secrets.token_hex(4)+'@example.test')
        await db.execute_query("INSERT INTO web_sessions(token_hash,player_id) VALUES('fixture-reset-session',$1)",pid)
        return pid,await issue(pid,'reset')
    pid,token=client.portal.call(fixture)
    body={'token':token,'password':'new-secure-test-password'}
    assert client.post('/api/auth/recovery/redeem',headers=headers,json=body).status_code==200
    assert client.post('/api/auth/recovery/redeem',headers=headers,json=body).status_code==400
    async def count():return await db.fetch_one_query('SELECT count(*) n FROM web_sessions WHERE player_id=$1',pid)
    assert client.portal.call(count)['n']==0


def test_slice_boards_movement_food_and_ranged(client):
    from scripts.expand_slice import expand
    from game.database import db_manager as db
    from game.character import Character
    from game.mob import Mob
    from game import notices
    from game.commands.handler import process_command
    from web.builds import hot_publish
    async def scenario():
        w=client.app.state.world
        async with w.mutation_lock:
            before=await db.fetch_one_query('SELECT count(*) n FROM rooms')
            async with db.pool.acquire() as conn:
                async with conn.transaction():await expand(conn)
            after=await db.fetch_one_query('SELECT count(*) n FROM rooms');assert after['n']==before['n']+85
            async with db.pool.acquire() as conn:
                async with conn.transaction():await expand(conn)
            assert (await db.fetch_one_query('SELECT count(*) n FROM rooms'))['n']==after['n']
            await hot_publish(client.app)
            pid=await db.create_player_account('newqa'+secrets.token_hex(4),'disabled',secrets.token_hex(8)+'@example.test')
            cid=await db.create_character(pid,'QA','Ranger','Male',1,5,'Ranger',dict.fromkeys(['might','vitality','agility','intellect','aura','persona'],20),'A traveler.',100,100,50,50,3)
            c=Character(None,dict(await db.load_character_data(cid)),w);c.send=AsyncMock();await c.load_related_data();c.location=w.rooms[1];c.location.add_character(c);w.add_active_character(c)
            try:
                assert c.coinage==125
                for command,destination in [('n',5),('south',1),('go north',5),('s',1)]:
                    c.roundtime=0;await process_command(c,w,command);assert c.location_id==destination,c.send.call_args
                await notices.command(c,w,'')
                board=await db.fetch_one_query('SELECT * FROM notice_boards WHERE room_id=1')
                date=await notices.populate(w,board)
                available=await db.fetch_all_query('SELECT * FROM board_notices WHERE board_id=$1 AND game_date=$2 ORDER BY slot',board['id'],date)
                assert len(available)==10
                q=available[0];await notices.command(c,w,'accept '+str(q['id']))
                await notices.command(c,w,'accept '+str(available[1]['id']))
                assert (await db.fetch_one_query('SELECT count(*) n FROM notice_claims WHERE character_id=$1 AND active',cid))['n']==1
                for obj in json.loads(q['objectives']):
                    for _ in range(obj.get('count',1)):await notices.event(c,w,obj['kind'],obj['target'])
                previous=c.coinage;await notices.command(c,w,'complete');assert c.coinage>previous
                previous=c.coinage;await notices.command(c,w,'complete');assert c.coinage==previous
                await w.update_xp_absorption(60)
                c.roundtime=0;await process_command(c,w,'advance');assert c.level>=2
                w.game_day+=1;newdate=await notices.populate(w,board);assert newdate!=date
                assert (await db.fetch_one_query('SELECT count(*) n FROM board_notices WHERE board_id=$1 AND game_date=$2',board['id'],newdate))['n']==10
                # Real movement to a scheduled shop, then consumed food and node resting.
                c.roundtime=0;await process_command(c,w,'w');assert c.location_id==2
                w.game_hour=10;w.living.last_tick=0;await w.living.tick(0)
                c.hunger=0;c.thirst=0;c.hp=10;c.roundtime=0
                await process_command(c,w,'buy travel ration');await process_command(c,w,'eat travel ration');assert c.hunger==50
                await process_command(c,w,'buy spring water');await process_command(c,w,'drink spring water');assert c.thirst==50
                c.roundtime=0;await process_command(c,w,'rest');c.update_regen(10,True);assert c.hp>10
                c.roundtime=0;await process_command(c,w,'stand')
                # Shop instances go through real wear/put commands.
                c.coinage=125
                for command in ['buy coast quiver','wear coast quiver','open coast quiver','buy arrow bundle','put arrow bundle in coast quiver','buy coast bow','wield coast bow']:
                    c.roundtime=0;await process_command(c,w,command)
                assert c._equipped_items.get('main_hand'),c.send.call_args
                quiver=next(i for i in c._equipped_items.values() if i.item_type=='QUIVER');ammo=next(iter(quiver.contents.values()))
                c.roundtime=0;await process_command(c,w,'e');c.roundtime=0;await process_command(c,w,'s')
                template=next(t for t in w.mob_templates.values() if t['name']=='tide scavenger')
                mob=Mob(template,c.location);c.location.add_mob(mob)
                c.roundtime=0;quiver.instance_stats['is_open']=False
                await process_command(c,w,'shoot tide scavenger');assert ammo.stats['quantity']==20
                assert 'Open your quiver' in c.send.call_args.args[0]
                quiver.instance_stats['is_open']=True
                from unittest.mock import patch
                with patch('game.combat.hit_resolver.random.randint',side_effect=lambda a,b:b):
                    await process_command(c,w,'shoot tide scavenger')
                assert mob.hp<mob.max_hp
                assert ammo.stats['quantity']==19,c.send.call_args
                assert c.roundtime>=3
                c.is_dirty=True;await c.save()
                saved=await db.fetch_one_query('SELECT instance_stats FROM item_instances WHERE id=$1',ammo.id)
                assert json.loads(saved['instance_stats'])['quantity']==19
                c.roundtime=0;await process_command(c,w,'sheathe')
                assert not c._equipped_items.get('main_hand')
                c.location.remove_character(c);c.update_location(w.rooms[2]);c.location.add_character(c)
                await process_command(c,w,'remove coast quiver');await process_command(c,w,'deposit coast quiver');await process_command(c,w,'withdraw coast quiver')
                restored_quiver=next(i for i in c._inventory_items.values() if i.item_type=='QUIVER')
                assert next(iter(restored_quiver.contents.values())).stats['quantity']==19
                await process_command(c,w,'wear coast quiver');await process_command(c,w,'unsheathe coast bow');assert c._equipped_items.get('main_hand')
            finally:
                c.location.remove_character(c);w.remove_active_character(cid)
    client.portal.call(scenario)


def test_door_and_hazard_state_match_movement(client):
    from game.database import db_manager as db
    from game.character import Character
    from game.commands.handler import process_command
    from game.doors import details
    async def scenario():
        w=client.app.state.world
        async with w.mutation_lock:
            row=await db.fetch_one_query('SELECT c.* FROM characters c JOIN players p ON p.id=c.player_id WHERE p.username=$1',client.fixture_names[0])
            c=Character(None,dict(row),w);c.send=AsyncMock();await c.load_related_data();c.update_location(w.rooms[1]);c.location.add_character(c);w.add_active_character(c);c.hp=100;c.stance='Standing'
            door={'is_door':True,'is_open':False,'is_locked':True,'lockpick_dc':0}
            await db.execute_query("INSERT INTO exits(source_room_id,destination_room_id,direction,details) VALUES(1,5,'test gate',$1)",json.dumps(door))
            c.location.exits['test gate']={'destination_room_id':5,'details':door}
            try:
                await process_command(c,w,'go test gate');assert c.location_id==1
                await process_command(c,w,'lockpick test gate');assert not door['is_locked']
                c.roundtime=0;await process_command(c,w,'open test gate');assert door['is_open']
                saved=await db.fetch_one_query("SELECT details FROM exits WHERE direction='test gate'");assert json.loads(saved['details'])['is_open']
                door['skill_check']={'skill':'climbing','dc':10000,'fail_damage':7}
                c.roundtime=0;await process_command(c,w,'go test gate');assert c.location_id==1 and c.hp==93 and c.stance=='Lying'
                assert 'Failure' in ''.join(call.args[0] for call in c.send.call_args_list)
            finally:
                c.location.exits.pop('test gate',None);await db.execute_query("DELETE FROM exits WHERE direction='test gate'")
                c.location.remove_character(c);w.remove_active_character(c.dbid)
    client.portal.call(scenario)


def test_all_classes_have_working_level_twenty_combat(client):
    from game.database import db_manager as db
    from game.character import Character
    from game.mob import Mob
    from game import adventure,utils
    from game.commands.handler import process_command
    import random
    async def scenario():
        w=client.app.state.world
        async with w.mutation_lock:
            templates=await db.fetch_all_query('SELECT * FROM classes ORDER BY id')
            results=[]
            for definition in templates:
                pid=await db.create_player_account('kit'+secrets.token_hex(5),'disabled',secrets.token_hex(8)+'@example.test')
                cid=await db.create_character(pid,'Kit','Tester','Male',1,definition['id'],definition['name'],dict.fromkeys(['might','vitality','agility','intellect','aura','persona'],16),'A traveler.',100,100,50,50,3)
                c=Character(None,dict(await db.load_character_data(cid)),w);c.send=AsyncMock();await c.load_related_data();w.add_active_character(c);c.update_location(w.rooms[7]);c.location.add_character(c)
                for level in (1,5,10,15,20):
                    random.seed(90210+level)
                    c.level=level;c.recalculate_max_vitals();c.hp=c.max_hp;c.essence=c.max_essence;c.stance='Standing';c.status='ALIVE';c.effects={}
                    template={'id':999999,'name':'sparring shade','description':'A test opponent.','level':level,'max_hp':24+level*7,'stats':dict.fromkeys(['might','vitality','agility','intellect','aura','persona'],10+level),'flags':['TELEGRAPH','INFRAVISION'],'attacks':[]}
                    mob=Mob(template,c.location);c.location.add_mob(mob)
                    basic,_,signature,_,_=adventure.KITS[definition['name'].lower()]
                    for turn in range(80):
                        c.roundtime=0
                        move=signature if level>=3 and c.essence>=4 else basic
                        await process_command(c,w,'technique '+move+' sparring shade')
                        if not mob.is_alive():break
                        mob.roundtime=0;await mob.simple_ai_tick(3,w)
                        assert c.is_alive(),(definition['name'],level,turn)
                    else:pytest.fail(str((definition['name'],level,'fight never resolved',c.send.call_args)))
                    c.location.remove_mob(mob);results.append((definition['name'],level,turn+1))
                c.location.remove_character(c);w.remove_active_character(cid)
            assert len(results)==60
            print('CLASS COMBAT SAMPLE',results,flush=True)
    client.portal.call(scenario)


def test_party_notice_tracks_followers_and_completes_once(client):
    from game.database import db_manager as db
    from game.character import Character
    from game.group import Group
    from game import notices
    from game.commands.handler import process_command
    async def scenario():
        w=client.app.state.world
        async with w.mutation_lock:
            chars=[]
            for name in client.fixture_names[:2]:
                row=await db.fetch_one_query('SELECT c.* FROM characters c JOIN players p ON p.id=c.player_id WHERE p.username=$1',name)
                c=Character(None,dict(row),w);c.send=AsyncMock();await c.load_related_data();c.level=20;c.status='ALIVE';c.hp=100;c.stance='Standing';c.roundtime=0;c.update_location(w.rooms[1]);c.location.add_character(c);w.add_active_character(c);chars.append(c)
            a,b=chars;group=Group(a);group.add_member(b)
            try:
                board=await db.fetch_one_query('SELECT * FROM notice_boards WHERE room_id=1');date=await notices.populate(w,board)
                q=await db.fetch_one_query('SELECT * FROM board_notices WHERE board_id=$1 AND game_date=$2 AND group_size=2 AND NOT claimed',board['id'],date)
                assert q
                await db.execute_query('UPDATE board_notices SET objectives=$1,required_standing=0 WHERE id=$2',json.dumps([{'kind':'visit','target':5,'label':'Survey the road','count':1}]),q['id'])
                await notices.command(a,w,'accept '+str(q['id']))
                await process_command(a,w,'n');assert a.location_id==b.location_id==5
                claims=await db.fetch_all_query('SELECT progress FROM notice_claims WHERE notice_id=$1',q['id'])
                assert len(claims)==2 and all(json.loads(r['progress']).get('0')==1 for r in claims)
                a.roundtime=b.roundtime=0;await process_command(a,w,'s');a.roundtime=b.roundtime=0
                before=[c.coinage for c in chars];await notices.command(a,w,'complete')
                assert all(c.coinage>old for c,old in zip(chars,before))
                before=[c.coinage for c in chars];await notices.command(b,w,'complete');assert [c.coinage for c in chars]==before
            finally:
                for c in chars:c.location.remove_character(c);w.remove_active_character(c.dbid);c.group=None
    client.portal.call(scenario)
