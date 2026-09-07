"""Runs against a disposable PostgreSQL database supplied by TEST_DATABASE_URL.
Never point this suite at production: it creates fixture accounts and world data.
"""
import os
import json
import secrets
import pytest
from fastapi.testclient import TestClient

pytestmark=pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'),reason='Set TEST_DATABASE_URL to a disposable PostgreSQL database')

@pytest.fixture(scope='module')
def client():
    import config
    config.DATABASE_URL=os.environ.get('TEST_DATABASE_URL',config.DATABASE_URL)
    from web.app import app
    from game.database import db_manager as db
    from game import utils
    with TestClient(app) as client:
        async def fixtures():
            if await db.fetch_one_query("SELECT 1 FROM rooms WHERE name='The Void'"):
                from scripts.manage import seed
                await seed()
                from game.world import World
                from game.living import LivingWorld
                from game import ticker
                await ticker.stop_ticker();ticker._callbacks.clear()
                world=World(db);assert await world.build()
                world.living=LivingWorld(world);await world.living.load()
                app.state.world=world;world.subscribe_to_ticker();ticker.subscribe(world.living.tick);await ticker.start_ticker()
            password='test-'+secrets.token_urlsafe(20)
            suffix=secrets.token_hex(4)
            for name,admin in [('builder'+suffix,True),('player'+suffix,False)]:
                pid=await db.create_player_account(name,utils.hash_password(password),name+'@example.test')
                await db.execute_query('UPDATE players SET is_admin=$1 WHERE id=$2',admin,pid)
                cid=await db.create_character(pid,'Test','Traveler','Male',1,1,'Warrior',dict.fromkeys(['might','vitality','agility','intellect','aura','persona'],20),'A traveler.',100,100,50,50,3)
                assert cid
            return suffix,password
        suffix,password=client.portal.call(fixtures)
        client.fixture_names=('builder'+suffix,'player'+suffix,password)
        yield client


def login(client,admin=False):
    import config
    builder,player,password=client.fixture_names
    response=client.post('/api/auth/login',headers={'origin':config.PUBLIC_ORIGIN},json={'username':builder if admin else player,'password':password})
    assert response.status_code==200,response.text
    return {'origin':config.PUBLIC_ORIGIN}


def test_auth_and_admin_boundary(client):
    client.cookies.clear()
    assert client.get('/api/admin/catalog').status_code==401
    assert client.post('/api/auth/login',json={'username':'someone','password':'bad'}).status_code==403
    login(client)
    assert client.get('/api/admin/catalog').status_code==403
    headers=login(client,True)
    assert client.get('/api/admin/catalog').status_code==200
    assert client.post('/api/admin/entities/rooms',json={'values':{'name':'blocked'}}).status_code==403
    assert client.post('/api/admin/entities/players',headers=headers,json={'values':{'is_admin':True}}).status_code==403


def test_builder_optimistic_edit_and_audit(client):
    headers=login(client,True)
    row=client.get('/api/admin/entities/rooms').json()[0]
    name=row['name']+'!'
    payload={'values':{'name':name},'original':row}
    assert client.post('/api/admin/entities/rooms',headers=headers,json=payload).status_code==200
    assert client.post('/api/admin/entities/rooms',headers=headers,json=payload).status_code==409
    changed=dict(row,name=name)
    assert client.post('/api/admin/entities/rooms',headers=headers,json={'values':{'name':row['name']},'original':changed}).status_code==200
    assert client.get('/api/admin/logs').json()['audit']


def test_browser_login_command_hud_disconnect(client):
    import config
    login(client)
    with client.websocket_connect('/ws',headers={'origin':config.PUBLIC_ORIGIN}) as ws:
        ws.send_json({'type':'command','payload':'1'})
        seen=''
        for _ in range(40):
            message=ws.receive_json()
            if message['type']=='text':seen+=message['payload']
            if message['type']=='vitals_update':
                assert message['payload']['hp']>0
                assert message['payload']['room']['id']==1
                break
        else:pytest.fail('No HUD received')
        assert 'Welcome back' in seen
        ws.send_json({'type':'command','payload':'emote listens to the sea.'})
        for _ in range(20):
            msg=ws.receive_json()
            if msg['type']=='text' and 'listens to the sea' in msg['payload']:break
        else:pytest.fail('Emote did not arrive')
        ws.send_json({'type':'command','payload':'quit'})


def test_gather_craft_relic_persistence(client):
    from game.database import db_manager as db
    from game.character import Character
    from game import living
    from unittest.mock import AsyncMock
    async def scenario():
        world=client.app.state.world
        data=await db.fetch_one_query('SELECT c.* FROM characters c JOIN players p ON c.player_id=p.id WHERE p.username=$1',client.fixture_names[1])
        c=Character(None,dict(data),world);c.send=AsyncMock()
        await c.load_related_data()
        c.update_location(world.get_room(3))
        await db.execute_query("UPDATE resource_nodes SET remaining=capacity WHERE name='silverleaf'")
        await living.cmd_gather(c,world,'silverleaf');await living.cmd_gather(c,world,'silverleaf')
        c.update_location(world.get_room(4))
        await living.cmd_craft(c,world,'coast salve')
        assert any(i.name=='coast salve' for i in c._inventory_items.values())
        c.update_location(world.get_room(6))
        await living.cmd_attune(c,world,'starmap fragment')
        count=await db.fetch_one_query('SELECT count(*) n FROM item_instances i JOIN relics r ON r.instance_id=i.id')
        assert count['n']==1
        await living.cmd_attune(c,world,'starmap fragment')
        count2=await db.fetch_one_query('SELECT count(*) n FROM item_instances i JOIN relics r ON r.instance_id=i.id')
        assert count2['n']==1
        c.is_dirty=True;await c.save()
        reloaded=Character(None,dict(await db.load_character_data(c.dbid)),world)
        await reloaded.load_related_data()
        assert any(i.name=='coast salve' for i in reloaded._inventory_items.values())
    client.portal.call(scenario)


def test_duplicate_socket_and_cross_origin_denied(client):
    import config
    from starlette.websockets import WebSocketDisconnect
    login(client)
    with pytest.raises(WebSocketDisconnect):
        with client.websocket_connect('/ws',headers={'origin':'https://evil.example'}):pass
    with client.websocket_connect('/ws',headers={'origin':config.PUBLIC_ORIGIN}) as ws:
        assert ws.receive_json()['type']=='session'
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect('/ws',headers={'origin':config.PUBLIC_ORIGIN}):pass
        ws.send_json({'type':'command','payload':'quit'})


def test_runtime_restart_and_live_publish(client):
    from game.database import db_manager as db
    from game.world import World
    from web.builds import hot_publish
    from game.state import save_runtime
    async def scenario():
        w=client.app.state.world
        async with w.mutation_lock:
            mob=next(m for r in w.rooms.values() for m in r.mobs if 'TELEGRAPH' in m.flags)
            id=mob.instance_id;mob.hp=13
            await w.save_state()
            rebuilt=World(db);assert await rebuilt.build()
            restored=next(m for r in rebuilt.rooms.values() for m in r.mobs if m.instance_id==id)
            assert restored.hp==13
            await hot_publish(client.app)
            assert client.app.state.world is w
            assert next(m for r in w.rooms.values() for m in r.mobs if m.instance_id==id).hp==13
    client.portal.call(scenario)


def test_build_snapshot_restores_definitions(client):
    headers=login(client,True)
    state=client.post('/api/admin/builds',headers=headers,json={'name':'Before description edit'})
    assert state.status_code==200,state.text
    rooms=client.get('/api/admin/entities/rooms').json()
    row=next(r for r in rooms if r['id']==1)
    assert client.post('/api/admin/entities/rooms',headers=headers,json={'values':{'description':'Changed in test'},'original':row}).status_code==200
    restored=client.post(f'/api/admin/builds/{state.json()["id"]}/restore',headers=headers)
    assert restored.status_code==200,restored.text
    assert client.app.state.world.rooms[1].description==row['description']


def test_all_classes_can_complete_level_one_to_ten(client):
    from game.database import db_manager as db
    from game.character import Character
    from game.mob import Mob
    from game import adventure,living,utils
    from game.commands import general
    from game.definitions import classes
    from unittest.mock import AsyncMock
    import random
    async def scenario():
        w=client.app.state.world
        async with w.mutation_lock:
            quests=await db.fetch_all_query('SELECT * FROM quests ORDER BY min_level')
            assert len(quests)==9
            for class_id,class_name in enumerate(adventure.KITS,1):
                random.seed(20260908+class_id)
                print("CLASS",class_name,flush=True)
                # Real creation DB path; intentionally conservative stats, no legendary gear.
                pid=await db.create_player_account('arc'+class_name+secrets.token_hex(3),'disabled-fixture',secrets.token_hex(8)+'@example.test')
                hp=30+classes.CLASS_HP_DIE[class_id]+utils.calculate_modifier(10)
                essence=15+classes.CLASS_ESSENCE_DIE[class_id]+2*utils.calculate_modifier(10)
                cid=await db.create_character(pid,'Arc','Traveler','Male',1,class_id,class_name,dict.fromkeys(['might','vitality','agility','intellect','aura','persona'],10),'A traveler.',hp,hp,essence,essence,3)
                c=Character(None,dict(await db.load_character_data(cid)),w);c.send=AsyncMock();await c.load_related_data()
                w.add_active_character(c)
                def move(room):
                    if c.location:c.location.remove_character(c)
                    c.update_location(w.get_room(room));c.location.add_character(c);c.roundtime=0
                for q in quests:
                    print("CHAPTER",class_name,q["min_level"],flush=True)
                    assert c.level>=q['min_level']
                    move(q['giver_room_id']);await adventure.cmd_recover(c,w,'');c.roundtime=0
                    await adventure.cmd_quest(c,w,f'accept {q["id"]}')
                    for obj in json.loads(q['objectives']):
                        if obj['kind']=='visit':
                            move(int(obj['target']));await adventure.event(c,w,'visit',c.location_id)
                        elif obj['kind']=='talk':
                            npc=next(m for r in w.rooms.values() for m in r.mobs if m.name==obj['target'])
                            move(npc.location.dbid);await living.cmd_talk(c,w,'Mira')
                        elif obj['kind']=='gather':
                            node=await db.fetch_one_query('SELECT * FROM resource_nodes WHERE name=$1',obj['target'])
                            await db.execute_query('UPDATE resource_nodes SET remaining=capacity WHERE id=$1',node['id'])
                            move(node['room_id'])
                            for _ in range(obj['count']):await living.cmd_gather(c,w,obj['target'])
                        elif obj['kind']=='craft':
                            recipe=await db.fetch_one_query('SELECT * FROM recipes WHERE name=$1',obj['target'])
                            for template,quantity in json.loads(recipe['ingredients']).items():
                                node=await db.fetch_one_query('SELECT * FROM resource_nodes WHERE item_template_id=$1',int(template))
                                await db.execute_query('UPDATE resource_nodes SET remaining=capacity WHERE id=$1',node['id'])
                                move(node['room_id'])
                                for _ in range(quantity):await living.cmd_gather(c,w,node['name'])
                            move(recipe['station_room_id']);await living.cmd_craft(c,w,obj['target'])
                        elif obj['kind']=='kill':
                            original=next(m for r in w.rooms.values() for m in r.mobs if m.name==obj['target'])
                            for _ in range(obj.get('count',1)):
                                move(1);await adventure.cmd_recover(c,w,'')
                                move(original.location.dbid)
                                # Fresh encounter, no respawn delay in this deterministic test.
                                mob=Mob(w.get_mob_template(original.template_id),c.location)
                                prior=c.location.mobs;c.location.mobs={mob}
                                try:
                                    for turn in range(40):
                                        c.roundtime=0
                                        basic,_,signature,_,_=adventure.KITS[class_name]
                                        move_name=signature if c.level>=3 and c.essence>=4 else basic
                                        await adventure.cmd_technique(c,w,move_name+' '+mob.name)
                                        if not mob.is_alive():break
                                        mob.roundtime=0
                                        await mob.simple_ai_tick(3,w)
                                        assert c.hp>0,(class_name,c.level,mob.name)
                                    else:assert False,('Encounter did not finish',class_name)
                                finally:c.location.mobs=prior
                    move(q['giver_room_id'])
                    before=c.xp_pool
                    await adventure.cmd_quest(c,w,'complete')
                    assert c.xp_pool>before,(class_name,q['name'])
                    duplicate=c.xp_pool;await adventure.cmd_quest(c,w,'complete');assert c.xp_pool==duplicate
                    # Accelerated node time; exercise real absorption and advancement code.
                    await w.update_xp_absorption(1000)
                    while c.level<10 and c.xp_total>=utils.xp_needed_for_level(c.level):
                        await general.cmd_advance(c,w,'')
                assert c.level==10,class_name
                c.is_dirty=True;await c.save()
                saved=await db.load_character_data(cid);assert saved['level']==10
                c.location.remove_character(c);w.remove_active_character(cid)
    client.portal.call(scenario)


def test_banking_and_salve_are_durable(client):
    from game.database import db_manager as db
    from game.character import Character
    from game.adventure import cmd_treat
    from unittest.mock import AsyncMock
    async def scenario():
        w=client.app.state.world
        async with w.mutation_lock:
            row=await db.fetch_one_query('SELECT c.* FROM characters c JOIN players p ON c.player_id=p.id WHERE p.username=$1',client.fixture_names[1])
            c=Character(None,dict(row),w);c.send=AsyncMock();await c.load_related_data()
            salve=next(i for i in c._inventory_items.values() if i.name=='coast salve')
            assert await db.bank_item(c.dbid,salve.id)
            await c.load_related_data()
            assert salve.id not in c._inventory_items
            assert await db.unbank_item(c.dbid,salve.id)
            await c.load_related_data();assert salve.id in c._inventory_items
            c.hp=10
            await cmd_treat(c,w,'')
            assert c.hp==40
            assert not await db.fetch_one_query('SELECT id FROM item_instances WHERE id=$1',salve.id)
            assert (await db.load_character_data(c.dbid))['hp']==40
            assert await db.transfer_bank_coins(c.dbid,100,60)
            assert (await db.load_character_data(c.dbid))['coinage']==40
            assert await db.transfer_bank_coins(c.dbid,40,-20)
            assert (await db.load_character_data(c.dbid))['coinage']==60
            assert not await db.transfer_bank_coins(c.dbid,60,-1000)
            assert (await db.load_character_data(c.dbid))['coinage']==60
    client.portal.call(scenario)


def test_soul_rite_and_zero_tether_permadeath(client):
    from game.database import db_manager as db
    from game.character import Character
    from game.soul import cmd_tether
    from game.commands.general import cmd_release
    from unittest.mock import AsyncMock
    async def scenario():
        w=client.app.state.world
        async with w.mutation_lock:
            pid=await db.create_player_account('soul'+secrets.token_hex(4),'disabled-test',secrets.token_hex(8)+'@example.test')
            cid=await db.create_character(pid,'Soul','Traveler','They/Them',1,3,'Cleric',dict.fromkeys(['might','vitality','agility','intellect','aura','persona'],16),'A cleric.',60,60,60,60,3)
            c=Character(None,dict(await db.load_character_data(cid)),w);c.send=AsyncMock();await c.load_related_data();c.update_location(w.get_room(1))
            c.xp_total=10000
            await cmd_tether(c,w,'self confirm')
            assert c.spiritual_tether==4 and c.xp_total==2750
            saved=await db.load_character_data(cid);assert saved['spiritual_tether']==4 and saved['xp_total']==2750
            c.status='DEAD';c.hp=0;c.spiritual_tether=1;c.roundtime=0
            await cmd_release(c,w,'')
            assert c.status=='PERMADEAD' and c.spiritual_tether==0
            assert (await db.load_character_data(cid))['status']=='PERMADEAD'
            assert not await db.load_characters_for_account(pid)
    client.portal.call(scenario)


def test_mail_stalls_enchant_and_infusion_persist(client):
    from game.database import db_manager as db
    from game.character import Character
    from game import community,horizon,utils,living
    from unittest.mock import AsyncMock
    async def scenario():
        w=client.app.state.world
        async with w.mutation_lock:
            chars=[]
            for _ in range(2):
                pid=await db.create_player_account('community'+secrets.token_hex(4),'disabled-test',secrets.token_hex(8)+'@example.test')
                cid=await db.create_character(pid,'Community','Traveler','They/Them',1,1,'Warrior',dict.fromkeys(['might','vitality','agility','intellect','aura','persona'],16),'A traveler.',60,60,40,40,3)
                c=Character(None,dict(await db.load_character_data(cid)),w);c.send=AsyncMock();await c.load_related_data();c.update_location(w.get_room(2));c.coinage=10000
                w.add_active_character(c);chars.append(c)
            a,b=chars
            await community.cmd_mail(a,w,f'send {b.dbid} | A meeting | Meet by the fountain.')
            await community.cmd_mail(b,w,'inbox')
            row=await db.fetch_one_query('SELECT * FROM game_mail WHERE recipient_id=$1',b.dbid)
            assert row['body']=='Meet by the fountain.'
            await community.cmd_mail(a,w,f'read {row["id"]}')
            assert a.send.call_args.args[0]=='Letter not found.'
            template=await db.fetch_one_query("INSERT INTO item_templates(name,type,stats,description) VALUES('test dagger','WEAPON','{\"damage_base\":4,\"speed\":1.5,\"value\":100}','A test weapon.') RETURNING *")
            data=dict(template);data['stats']=json.loads(data['stats']);w.item_templates[template['id']]=data
            await db.create_item_instance(template['id'],owner_char_id=a.dbid);await living.refresh_inventory(a,w)
            await horizon.cmd_market(a,w,'sell 100 test dagger')
            listing=await db.fetch_one_query('SELECT * FROM market_listings WHERE seller_id=$1',a.dbid)
            assert listing and not a._inventory_items
            await horizon.cmd_market(b,w,f'buy {listing["id"]}')
            assert b.coinage==9900 and a.coinage==10093
            assert not await db.fetch_one_query('SELECT * FROM market_listings WHERE id=$1',listing['id'])
            item=next(iter(b._inventory_items.values()))
            b.update_location(w.get_room(4));await horizon.cmd_enchant(b,w,'test dagger');assert item.damage_base==5
            b.update_location(w.get_room(1));b.level=99;b.xp_total=utils.xp_needed_for_level(98)+100000
            await community.cmd_infuse(b,w,'test dagger');assert item.damage_base==6
            await w.save_state()
            restored=Character(None,dict(await db.load_character_data(b.dbid)),w);restored.send=AsyncMock();await restored.load_related_data()
            assert next(iter(restored._inventory_items.values())).damage_base==6
            for c in chars:w.remove_active_character(c.dbid)
    client.portal.call(scenario)
