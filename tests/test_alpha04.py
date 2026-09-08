import json
import os
import pytest
import secrets
from unittest.mock import AsyncMock,patch
from tests.test_integration import client
pytestmark=pytest.mark.skipif(not os.getenv("TEST_DATABASE_URL"),reason="Use a disposable TEST_DATABASE_URL")

def test_profession_loops(client):
    from game.database import db_manager as db
    from game.character import Character
    from game import professions as p
    from game.living import refresh_inventory
    from game.commands.handler import process_command
    async def scenario():
        w=client.app.state.world
        async with w.mutation_lock:
            pid=await db.create_player_account('work'+secrets.token_hex(4),'disabled',secrets.token_hex(8)+'@example.test')
            cid=await db.create_character(pid,'Work','Tester','Male',1,1,'Warrior',dict.fromkeys(['might','vitality','agility','intellect','aura','persona'],16),'A traveler.',100,100,50,50,3)
            c=Character(None,dict(await db.load_character_data(cid)),w);c.send=AsyncMock();await c.load_related_data()
            async def give(tid):
                await db.execute_query('INSERT INTO item_instances(template_id,owner_char_id) VALUES($1,$2)',tid,cid);await refresh_inventory(c,w)
            async def stow():
                for i in list(c._inventory_items.values()):
                    c.roundtime=0;await process_command(c,w,'put '+i.name+' in traveler backpack')
            rows=await db.fetch_all_query('SELECT * FROM resource_nodes ORDER BY id')
            assert {r['profession'] for r in rows}==set(list(p.ATTRIBUTES)[:7])
            for n in rows:
                c.update_location(w.rooms[n['room_id']]);await stow()
                await db.execute_query('UPDATE resource_nodes SET remaining=capacity,uses=0,depleted_at=NULL WHERE id=$1',n['id'])
                before=len(c.get_all_owned_item_instances())
                await p.gather(c,w,n['name']);assert 'tool' in c.send.call_args.args[0]
                t=next(t for t in w.item_templates.values() if t['name']==n['profession']+' tool');await give(t['id'])
                flag=n['profession'].upper()+'_NODE';c.location.flags.discard(flag)
                await p.gather(c,w,n['name']);assert 'No matching' in c.send.call_args.args[0];c.location.flags.add(flag)
                with patch('game.professions.random.randint',return_value=20),patch('game.professions.random.random',return_value=.99):
                    await p.gather(c,w,n['name'])
                assert len(c._inventory_items)==2 and c.hands_are_full()
                await p.gather(c,w,n['name']);assert 'hands are full' in c.send.call_args.args[0]
                item=next(i for i in c._inventory_items.values() if i.template_id==n['item_template_id'])
                c.roundtime=0;await process_command(c,w,'put '+item.name+' in traveler backpack')
                with patch('game.professions.random.randint',return_value=1):await p.gather(c,w,n['name'])
                row=await db.fetch_one_query('SELECT remaining,depleted_at,uses FROM resource_nodes WHERE id=$1',n['id'])
                assert row['remaining']==0 and row['depleted_at'] and row['uses']==2
                await p.replenish(w,30)
                assert (await db.fetch_one_query('SELECT remaining FROM resource_nodes WHERE id=$1',n['id']))['remaining']==0
                await p.gather(c,w,n['name']);assert 'depleted' in c.send.call_args.args[0]
            await db.execute_query('SELECT chrozal_professions_setup()')
            preserved=await db.fetch_one_query('SELECT remaining,uses FROM resource_nodes WHERE id=$1',rows[-1]['id'])
            assert preserved['remaining']==0 and preserved['uses']==2
            await stow();c.update_location(w.rooms[4])
            recipes=await db.fetch_all_query('SELECT * FROM recipes ORDER BY id')
            assert {r['profession'] for r in recipes}=={'smithing','alchemy','cooking','runecrafting','brewing'}
            for r in recipes:
                await stow()
                tool=next(t for t in w.item_templates.values() if t['name']==r['profession']+' tool');await give(tool['id'])
                ingredients=json.loads(r['ingredients'])
                bag=c._equipped_items['back']
                for tid,qty in ingredients.items():
                    for _ in range(qty):await db.execute_query('INSERT INTO item_instances(template_id,container_id) VALUES($1,$2)',int(tid),bag.id)
                await refresh_inventory(c,w)
                bag=c._equipped_items['back'];bag.instance_stats['is_open']=False
                await p.craft(c,w,r['name']);assert 'open containers' in c.send.call_args.args[0]
                bag.instance_stats['is_open']=True
                with patch('game.professions.random.randint',return_value=20):await p.craft(c,w,r['name'])
                assert any(i.template_id==r['output_template_id'] for i in c._inventory_items.values())
            await stow()
            tool=next(t for t in w.item_templates.values() if t['name']=='cooking tool')
            # Retrieve the existing tool from the bag instead of creating duplicate tools.
            c.roundtime=0;await process_command(c,w,'get cooking tool from traveler backpack')
            recipe=next(r for r in recipes if r['profession']=='cooking')
            tid=int(next(iter(json.loads(recipe['ingredients']))))
            await db.execute_query('INSERT INTO item_instances(template_id,container_id) VALUES($1,$2)',tid,c._equipped_items['back'].id)
            await refresh_inventory(c,w)
            before=len(c.get_all_owned_item_instances())
            with patch('game.professions.random.randint',return_value=1):await p.craft(c,w,recipe['name'])
            assert 'ingredients are spoiled' in c.send.call_args.args[0]
            assert len(c.get_all_owned_item_instances())==before-1
            c.is_dirty=True;await c.save()
            loaded=Character(None,dict(await db.load_character_data(cid)),w);loaded.send=AsyncMock();await loaded.load_related_data()
            assert set(c.skills)<=set(loaded.skills)
    client.portal.call(scenario)

def test_poker_ranking():
    from game.tavern import score,dealer_draw
    assert score([12,0,1,2,3])==(8,5) # wheel straight flush
    assert score([8,9,10,11,12])==(8,14)
    assert score([0,13,26,39,12])[0]==7
    assert score([0,13,26,1,14])[0]==6
    assert score([0,13,1,14,12])[0]==2
    deck=list(range(20,40));hand=[0,13,2,5,8]
    drawn=dealer_draw(hand,deck)
    assert drawn[:2]==hand[:2] and len(deck)==17

def test_tavern_persistence(client):
    from game.tavern import command,dice
    from game.database import db_manager as db
    from game.character import Character
    async def scenario():
        w=client.app.state.world
        async with w.mutation_lock:
            row=await db.fetch_one_query('SELECT * FROM characters WHERE player_id=(SELECT id FROM players WHERE username=$1)',client.fixture_names[1])
            c=Character(None,dict(row),w);c.send=AsyncMock();await c.load_related_data();c.update_location(w.rooms[2]);c.level=10;c.coinage=100
            await command(c,w,'bet 5');assert c.coinage==95
            await command(c,w,'bet 5');assert c.coinage==95
            await command(c,w,'draw 1,1');assert c.coinage==95
            saved=Character(None,dict(await db.load_character_data(c.dbid)),w);saved.send=AsyncMock();await saved.load_related_data();saved.update_location(w.rooms[2])
            await command(saved,w,'');assert 'Your saved hand' in saved.send.call_args_list[-2].args[0]
            await command(saved,w,'stand');balance=saved.coinage;assert balance in (95,100,105)
            await command(saved,w,'stand');assert saved.coinage==balance
            await db.execute_query("UPDATE tavern_hands SET played_at=now()-interval '31 seconds' WHERE character_id=$1",c.dbid)
            with patch('game.tavern.RNG.randint',side_effect=[3,4]):await dice(saved,w,'5')
            assert saved.coinage==balance+10
            ledger=await db.fetch_one_query('SELECT sum(payout-stake) AS net FROM tavern_ledger WHERE character_id=$1',c.dbid)
            assert saved.coinage==100+ledger['net']
    client.portal.call(scenario)

def test_narration_and_hostility():
    import asyncio
    from types import SimpleNamespace
    from game.mob import Mob
    from game.combat.damage_calculator import DamageInfo
    from game.combat.outcome_handler import impact
    assert impact(DamageInfo(10,'slash',False,roll_fraction=.9),10)=='cleaves'
    assert impact(DamageInfo(10,'pierce',False,roll_fraction=.2),10)=='grazes'
    assert impact(DamageInfo(10,'fire',False,roll_fraction=.9),10)=='engulfs'
    assert impact(DamageInfo(10,'fire',False),0)=='glances harmlessly off'
    async def scenario():
        class Target:
            pass
        victim=Target();victim.is_alive=lambda:True;victim.is_hidden=True;victim.name='Scout'
        room=SimpleNamespace(flags=set(),characters=[victim],broadcast=AsyncMock())
        m=Mob({'id':999,'name':'test hunter','description':'A prowler.','level':1,'hp':100,'stats':{},'flags':['AGGRESSIVE'],'attacks':[]},room)
        m.movement_chance=0
        await m.simple_ai_tick(1,None);assert not m.is_fighting
        victim.is_hidden=False
        await m.simple_ai_tick(1,None);assert m.target is victim and m.is_fighting
        room.flags.add('SAFE_ZONE');await m.simple_ai_tick(1,None);assert not m.is_fighting
        room.flags.clear();m.is_hidden=True;victim.is_hidden=True
        await m.simple_ai_tick(1,None);assert not m.is_fighting
        victim.is_hidden=False
        m.attacks=[{'name':'ambush','attack_type':'physical'}]
        victim.send=AsyncMock()
        with patch('game.resolver.resolve_physical_attack',new_callable=AsyncMock) as hit:
            await m.simple_ai_tick(1,None);assert hit.await_count==1
    asyncio.run(scenario())
