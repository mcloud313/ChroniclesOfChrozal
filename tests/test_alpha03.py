"""Desktop-reported gameplay regressions, exercised against persistent instances."""
import json
import secrets
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch
import pytest
from test_integration import client,login

def test_named_exits_are_unambiguous():
    from game.commands.movement import resolve_exit
    room=SimpleNamespace(exits={'reedwater march':{'destination_room_id':16},'return':{'destination_room_id':1}})
    assert resolve_exit(room,'march')[0]=='reedwater march'
    assert resolve_exit(room,'reedwater')[0]=='reedwater march'
    assert resolve_exit(room,'return')[1]['destination_room_id']==1
    room.exits['reedwater village']={}
    assert resolve_exit(room,'reedwater')[1] is None

def test_defense_channels_and_percent_resistance():
    from game.combat.damage_calculator import DamageInfo,mitigate_damage,mitigate_magical_damage
    target=SimpleNamespace(pds=2,sds=3,total_av=10,barrier_value=20,resistances={'fire':50,'slash':50})
    assert mitigate_damage(target,DamageInfo(40,'slash',False))==14
    assert mitigate_magical_damage(target,DamageInfo(40,'fire',False))==8
    target.total_av=999
    assert mitigate_magical_damage(target,DamageInfo(40,'fire',False))==8
    target.barrier_value=999;target.total_av=10
    assert mitigate_damage(target,DamageInfo(40,'slash',False))==14

def test_race_options_and_emote_catalog():
    from game.definitions.traits import TRAIT_OPTIONS
    from game.definitions.races import RACIAL_STAT_MODIFIERS
    from game.appearance import describe
    from game.emotes import EMOTES
    assert len(EMOTES)>=200
    for race in RACIAL_STAT_MODIFIERS:
        assert len(TRAIT_OPTIONS[race])>=9
        text=describe({'race_name':race,'description_traits':{k:v[-1] for k,v in TRAIT_OPTIONS[race].items()}})
        assert race in text and len(text)>180

@pytest.mark.asyncio
async def test_creation_handles_every_race_trait():
    from game.handlers.creation import CreationHandler,CreationState
    from game.definitions.traits import TRAIT_OPTIONS
    for race,options in TRAIT_OPTIONS.items():
        c=object.__new__(CreationHandler);c.creation_data={'race_name':race};c._send=AsyncMock();c._prompt=AsyncMock();c._read_line=AsyncMock(return_value='1')
        await c._handle_build_description_start()
        while c.state!=CreationState.FINALIZE:
            assert c.state==CreationState.GET_TRAIT_GENERIC
            await c._handle_get_trait(c._trait_keys[c._current_trait_index])
        assert set(c.creation_data['description_traits'])==set(options)

def test_hands_destroy_recovery_and_persistence(client):
    from game.database import db_manager as db
    from game.character import Character
    from game.commands.handler import process_command
    from game.living import refresh_inventory
    from game.hands import repair_overflow
    async def scenario():
        w=client.app.state.world
        async with w.mutation_lock:
            pid=await db.create_player_account('hands'+secrets.token_hex(4),'disabled',secrets.token_hex(8)+'@example.test')
            cid=await db.create_character(pid,'Hand','Tester','Male',1,1,'Warrior',dict.fromkeys(['might','vitality','agility','intellect','aura','persona'],16),'A traveler.',100,100,50,50,3)
            c=Character(None,dict(await db.load_character_data(cid)),w);c.send=AsyncMock();await c.load_related_data();c.update_location(w.rooms[3]);c.location.add_character(c);w.add_active_character(c)
            async def command(text):
                c.roundtime=0;await process_command(c,w,text)
                assert not any('Ope!' in call.args[0] for call in c.send.call_args_list),c.send.call_args_list
            try:
                assert set(c._equipped_items)=={'back','torso','legs','feet'}
                assert not c._inventory_items
                dagger=next(t for t in w.item_templates.values() if t['name']=='wayfarer dagger')
                await db.execute_query('INSERT INTO item_instances(template_id,owner_char_id) VALUES($1,$2)',dagger['id'],cid);await refresh_inventory(c,w)
                await command('wield wayfarer dagger');await command('gather silverleaf')
                assert len(c._inventory_items)==1 and c.hands_are_full()
                leaf=next(iter(c._inventory_items.values()))
                await command('gather silverleaf');assert len(c._inventory_items)==1
                await command('put silverleaf in traveler backpack');assert not c.hands_are_full()
                await command('close traveler backpack');await command('get silverleaf from traveler backpack');assert not c._inventory_items
                await command('open traveler backpack');await command('get silverleaf from traveler backpack');assert leaf.id in c._inventory_items
                relic=await db.fetch_one_query("INSERT INTO relics(name,lore,room_id,template_id) VALUES($1,'A test relic.',1,$2) RETURNING id",'protected '+secrets.token_hex(4),leaf.template_id)
                await command('destroy '+str(leaf.id));assert 'Relics' in c.send.call_args.args[0]
                assert await db.fetch_one_query('SELECT id FROM item_instances WHERE id=$1',leaf.id)
                await db.execute_query('DELETE FROM relics WHERE id=$1',relic['id'])
                await command('destroy '+str(leaf.id));assert await db.fetch_one_query('SELECT id FROM item_instances WHERE id=$1',leaf.id)
                c.pending_destroy=(leaf.id,time.monotonic()-1);await command('destroy confirm')
                assert await db.fetch_one_query('SELECT id FROM item_instances WHERE id=$1',leaf.id)
                await command('destroy '+str(leaf.id))
                await command('destroy confirm');assert not await db.fetch_one_query('SELECT id FROM item_instances WHERE id=$1',leaf.id)
                await command('sheathe');assert not c._equipped_items.get('main_hand')
                await command('unsheathe wayfarer dagger');assert c._equipped_items['main_hand'].name=='wayfarer dagger'
                await command('sheathe');await command('gather silverleaf');await command('drop silverleaf');assert len(c._inventory_items)==1
                c.level=10;await command('drop silverleaf');assert not c._inventory_items
                await command('get silverleaf');assert len(c._inventory_items)==1
                # Simulate the old exploit and ensure recovery retains every GUID.
                template=next(t for t in w.item_templates.values() if t['name']=='silverleaf')
                for _ in range(4):await db.execute_query('INSERT INTO item_instances(template_id,owner_char_id) VALUES($1,$2)',template['id'],cid)
                await refresh_inventory(c,w);before={i.id for i in c.get_all_owned_item_instances()}
                await repair_overflow(c,w);assert len(c._inventory_items)==2
                assert before=={i.id for i in c.get_all_owned_item_instances()}
                c.is_dirty=True;await c.save()
                reloaded=Character(None,dict(await db.load_character_data(cid)),w);reloaded.send=AsyncMock();await reloaded.load_related_data()
                assert before=={i.id for i in reloaded.get_all_owned_item_instances()}
                assert len(reloaded._inventory_items)==2
            finally:c.location.remove_character(c);w.remove_active_character(cid)
    client.portal.call(scenario)


def test_dying_potion_healing_drag_and_enemy_rolls(client):
    from game.database import db_manager as db
    from game.character import Character
    from game.mob import Mob
    from game import resolver
    from game.commands.handler import process_command
    from game.living import refresh_inventory
    async def scenario():
        w=client.app.state.world
        async with w.mutation_lock:
            chars=[]
            for first in ('Healer','Fallen','Watcher'):
                pid=await db.create_player_account(first+secrets.token_hex(4),'disabled',secrets.token_hex(8)+'@example.test')
                cid=await db.create_character(pid,first,'Tester','Male',1,3,'Cleric',dict.fromkeys(['might','vitality','agility','intellect','aura','persona'],16),'A traveler.',100,100,50,50,3)
                c=Character(None,dict(await db.load_character_data(cid)),w);c.send=AsyncMock();await c.load_related_data();c.update_location(w.rooms[1]);c.location.add_character(c);w.add_active_character(c);chars.append(c)
            healer,fallen,watcher=chars
            try:
                fallen.hp=0;fallen.status='DYING';fallen.death_timer_ends_at=time.monotonic()+10
                await resolver.apply_heal(healer,fallen,{'heal_base':20},w)
                assert fallen.hp==1 and fallen.status=='ALIVE' and fallen.death_timer_ends_at is None
                potion=await db.fetch_one_query("INSERT INTO item_templates(name,type,stats) VALUES($1,'POTION','{\"effect\":\"heal_hp\",\"amount\":20}'::jsonb) RETURNING *",'rescue potion '+secrets.token_hex(3))
                data=dict(potion);data['stats']=json.loads(data['stats']);w.item_templates[data['id']]=data
                await db.execute_query('INSERT INTO item_instances(template_id,owner_char_id) VALUES($1,$2)',data['id'],healer.dbid);await refresh_inventory(healer,w)
                fallen.hp=0;fallen.status='DYING';fallen.death_timer_ends_at=time.monotonic()+10
                await process_command(healer,w,'administer '+data['name']+' to Fallen')
                assert fallen.hp==1 and fallen.status=='ALIVE' and not healer._inventory_items
                fallen.hp=0;fallen.status='DYING';healer.roundtime=0
                await process_command(healer,w,'drag Fallen north')
                assert healer.location_id==fallen.location_id==5
                fallen.hp=100;fallen.status='ALIVE'
                watcher.location.remove_character(watcher);watcher.update_location(w.rooms[5]);watcher.location.add_character(watcher)
                mob=Mob(next(t for t in w.mob_templates.values() if t['name']=='tide scavenger'),healer.location);healer.location.add_mob(mob);mob.target=healer;mob.is_fighting=True
                for c in chars:c.send.reset_mock()
                with patch('game.combat.hit_resolver.random.randint',return_value=20):await mob.simple_ai_tick(1,w)
                assert any('CRITICAL HIT' in call.args[0] and 'Roll:' in call.args[0] for call in healer.send.call_args_list)
                assert any('CRITICAL HIT' in call.args[0] for call in watcher.send.call_args_list)
                assert not any('Brace' in call.args[0] for call in healer.send.call_args_list)
                mob.attacks=[{'name':'dragon breath','attack_type':'fire','damage_base':30,'damage_rng':0,'speed':5,'effect_details':'{"school":"Arcane","damage_type":"fire"}'}]
                healer.hp=100;mob.roundtime=0
                with patch('game.combat.hit_resolver.random.randint',return_value=10):await mob.simple_ai_tick(1,w)
                assert healer.hp<100 and mob.roundtime>=5
                assert any('dragon breath' in call.args[0] and 'Roll:' in call.args[0] for call in healer.send.call_args_list)
                mob.attacks=[{'name':'claw','attack_type':'physical','damage_base':5,'damage_rng':0,'speed':2}]

                healer.hp=100;mob.roundtime=0
                with patch('game.combat.hit_resolver.random.randint',return_value=1):await mob.simple_ai_tick(1,w)
                assert any('misses you' in call.args[0] and 'Roll:' in call.args[0] for call in healer.send.call_args_list)
            finally:
                for c in chars:c.location.remove_character(c);w.remove_active_character(c.dbid)
    client.portal.call(scenario)


def test_admin_character_details_and_password_gate(client):
    from game.database import db_manager as db
    from game import utils
    headers=login(client,True)
    rows=client.get('/api/admin/entities/characters?limit=1').json();cid=rows[0]['id']
    detail=client.get(f'/api/admin/characters/{cid}').json()
    assert detail['equipment'] and all(e['name'] and e['guid'] for e in detail['equipment'])
    assert len(client.get('/api/admin/entities/characters?limit=1').json())==1
    assert client.get('/api/admin/entities/characters?limit=1000').status_code==422
    assert client.get('/api/admin/logs?q=unlikely-no-match').json()['runtime']==[]
    login(client,False)
    assert client.get(f'/api/admin/characters/{cid}').status_code==403
    async def fixture():
        username='forced'+secrets.token_hex(4)
        pid=await db.create_player_account(username,utils.hash_password('initial-test-password'),username+'@example.test')
        await db.execute_query('UPDATE players SET is_admin=true,must_change_password=true WHERE id=$1',pid)
        return username
    username=client.portal.call(fixture)
    response=client.post('/api/auth/login',headers=headers,json={'username':username,'password':'initial-test-password'})
    assert response.json()['must_change_password']
    assert client.get('/api/admin/catalog').status_code==403
    assert client.post('/api/auth/change-password',headers=headers,json={'password':'changed-test-password'}).status_code==200
    assert client.get('/api/auth/me').status_code==401
    assert client.post('/api/auth/login',headers=headers,json={'username':username,'password':'changed-test-password'}).status_code==200
    assert client.get('/api/admin/catalog').status_code==200


def test_lighting_weather_progression_and_lore(client):
    from game.database import db_manager as db
    from game.character import Character
    from game.commands.handler import process_command
    from game import utils,resolver
    from game.combat.outcome_handler import handle_defeat
    from game.item import Item
    async def scenario():
        w=client.app.state.world
        async with w.mutation_lock:
            pid=await db.create_player_account('storm'+secrets.token_hex(4),'disabled',secrets.token_hex(8)+'@example.test')
            cid=await db.create_character(pid,'Storm','Tester','Male',1,12,'Tempest',dict.fromkeys(['might','vitality','agility','intellect','aura','persona'],16),'A traveler.',100,100,50,50,3)
            c=Character(None,dict(await db.load_character_data(cid)),w);c.send=AsyncMock();await c.load_related_data();c.update_location(w.rooms[1]);c.location.add_character(c);w.add_active_character(c)
            original_flags=set(c.location.flags)
            try:
                assert 'wind_lash' in c.known_abilities
                hp,ess=c.max_hp,c.max_essence
                for level in range(2,21):
                    c.xp_total=utils.xp_needed_for_level(c.level);c.roundtime=0
                    await process_command(c,w,'advance');assert c.level==level
                assert c.max_hp>hp and c.max_essence>ess and c.unspent_attribute_points==5
                assert {'storm_mantle','forked_lightning','thunder_lance','eye_of_the_tempest'}<=c.known_abilities
                c.location.flags={'DARK'}
                assert not c.can_see()
                light=Item({'id':__import__('uuid').uuid4(),'instance_stats':{'is_lit':True}},{'name':'torch','type':'LIGHT_SOURCE','stats':{}})
                c._inventory_items[light.id]=light;assert c.can_see()
                c._inventory_items.pop(light.id);assert not c.can_see()
                c.location.flags={'OUTDOORS','NODE','LIT'};assert c.can_see()
                w.area_weather[c.location.area_id]={'condition':'THUNDERSTORM'}
                c.send.reset_mock()
                with patch('game.world.random.random',return_value=0),patch('game.world.random.choice',side_effect=lambda seq:seq[-1]):await w.update_ambient_scripts(1)
                assert any('raindrop' in call.args[0] for call in c.send.call_args_list)
                await process_command(c,w,'lore races');assert 'veskar' in c.send.call_args.args[0]
                c.hp=0;c.coinage=100;c.level=10
                await handle_defeat(None,c,w)
                assert c.coinage==90 and c.status=='DYING'
            finally:c.location.flags=original_flags;c.location.remove_character(c);w.remove_active_character(cid)
    client.portal.call(scenario)


def test_registration_requires_verification(client):
    import config
    headers={'origin':config.PUBLIC_ORIGIN}
    username='signup'+secrets.token_hex(4)
    with patch.object(config,'ALLOW_REGISTRATION',True),patch('web.recovery.configured',return_value=True):
        r=client.post('/api/auth/register',headers=headers,json={'username':username,'password':'registration-test-password','email':username+'@example.test'})
        assert r.status_code==200 and r.json()['verification_required']
        assert client.post('/api/auth/login',headers=headers,json={'username':username,'password':'registration-test-password'}).status_code==403
    from game.database import db_manager as db
    from web.recovery import issue
    async def verify():
        p=await db.load_player_account(username);return await issue(p['id'],'verify')
    token=client.portal.call(verify)
    assert client.post('/api/auth/recovery/redeem',headers=headers,json={'token':token,'password':''}).status_code==200
    assert client.post('/api/auth/login',headers=headers,json={'username':username,'password':'registration-test-password'}).status_code==200


def test_admin_bootstrap_never_resets_existing_admin(client):
    from game.database import db_manager as db
    from game import utils
    async def scenario():
        # Disposable test database only; restore fixture privileges afterward.
        admins=await db.fetch_all_query('SELECT id FROM players WHERE is_admin')
        assert await db.bootstrap_admin() is None
        try:
            await db.execute_query('UPDATE players SET is_admin=false WHERE is_admin')
            initial=await db.bootstrap_admin()
            assert initial and len(initial)>=24
            account=await db.load_player_account('admin')
            assert account['must_change_password'] and account['is_admin']
            from game.player import Player
            assert Player(**dict(account)).check_password(initial)[0]
            assert await db.bootstrap_admin() is None
            unchanged=await db.load_player_account('admin')
            assert unchanged['hashed_password']==account['hashed_password']
        finally:
            await db.execute_query('UPDATE players SET is_admin=true WHERE id=ANY($1::int[])',[r['id'] for r in admins])
    client.portal.call(scenario)
