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
    assert client.get('/admin').status_code==403
    assert client.get('/static/admin.html').status_code==403
    assert client.get('/static/admin.js').status_code==403
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
        from unittest.mock import patch
        from game.commands.handler import process_command
        async def give_tool(profession):
            tid=await db.fetch_one_query('SELECT id FROM item_templates WHERE name=$1',profession+' tool')
            await db.execute_query('INSERT INTO item_instances(template_id,owner_char_id) VALUES($1,$2)',tid['id'],c.dbid)
            await living.refresh_inventory(c,world)
        await give_tool('herbalism')
        with patch('game.professions.random.randint',return_value=20),patch('game.professions.random.random',return_value=.99):
            for _ in range(2):
                c.roundtime=0;await living.cmd_gather(c,world,'silverleaf')
                c.roundtime=0;await process_command(c,world,'put silverleaf in traveler backpack')
        c.roundtime=0;await process_command(c,world,'put herbalism tool in traveler backpack')
        await give_tool('alchemy')
        c.update_location(world.get_room(4))
        with patch('game.professions.random.randint',return_value=20):
            await living.cmd_craft(c,world,'coast salve')
        assert any(i.name=='coast salve' for i in c._inventory_items.values())
        c.update_location(world.get_room(6))
        c.level=50
        await living.cmd_attune(c,world,'starmap fragment')
        count=await db.fetch_one_query('SELECT count(*) n FROM item_instances i JOIN relics r ON r.instance_id=i.id')
        assert count['n']==1
        await living.cmd_attune(c,world,'starmap fragment')
        count2=await db.fetch_one_query('SELECT count(*) n FROM item_instances i JOIN relics r ON r.instance_id=i.id')
        assert count2['n']==1
        c.is_dirty=True;await c.save()
        reloaded=Character(None,dict(await db.load_character_data(c.dbid)),world)
        reloaded.send=AsyncMock()
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
            a.level=b.level=10
            await a.save();await b.save()
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
            await community.cmd_mail(b,w,f'send {a.dbid} | A gift | Keep it safe. | test dagger')
            assert any(i.name=='test dagger' for i in b._inventory_items.values())
            assert 'letters only' in b.send.call_args.args[0]
            for c in chars:w.remove_active_character(c.dbid)
    client.portal.call(scenario)


def test_shop_and_housing_roundtrip(client):
    from game.database import db_manager as db
    from game.character import Character
    from game.commands import trade,movement
    from game import horizon
    from unittest.mock import AsyncMock
    async def scenario():
        w=client.app.state.world
        async with w.mutation_lock:
            row=await db.fetch_one_query('SELECT c.* FROM characters c JOIN players p ON p.id=c.player_id WHERE p.username=$1',client.fixture_names[0])
            c=Character(None,dict(row),w);c.send=AsyncMock();await c.load_related_data();c.coinage=10000;c.update_location(w.get_room(4));w.add_active_character(c)
            await trade.cmd_buy(c,w,'wayfarer dagger')
            item=next(i for i in c._inventory_items.values() if i.name=='wayfarer dagger')
            assert item.speed==1.5
            paid=10000-c.coinage;assert paid>0
            await trade.cmd_sell(c,w,'wayfarer dagger')
            assert 10000-paid<c.coinage<10000
            c.update_location(w.get_room(2));c.location.add_character(c)
            await horizon.cmd_home(c,w,'buy')
            home=await db.fetch_one_query('SELECT * FROM player_homes WHERE owner_id=$1',c.dbid)
            assert home['room_id'] in w.rooms
            await horizon.cmd_home(c,w,'describe Books and a sturdy writing desk.')
            await horizon.cmd_home(c,w,'enter')
            assert c.location_id==home['room_id']
            assert 'writing desk' in c.location.description
            c.hunger=99.873;c.thirst=98.432
            await w.save_state()
            saved=await db.load_character_data(c.dbid)
            assert saved['location_id']==home['room_id']
            assert saved['hunger']==pytest.approx(99.873) and saved['thirst']==pytest.approx(98.432)
            c.roundtime=0;await movement.cmd_go(c,w,'out')
            assert c.location_id==2
            c.location.remove_character(c);w.remove_active_character(c.dbid)
    client.portal.call(scenario)
