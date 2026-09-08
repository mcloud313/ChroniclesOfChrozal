import os,json,secrets,time
import pytest
from unittest.mock import AsyncMock,patch
from tests.test_integration import client,login
pytestmark=pytest.mark.skipif(not os.getenv('TEST_DATABASE_URL'),reason='Use a disposable database')

def test_builder_pagination_lookup_exit_delete(client):
    headers=login(client,True)
    data=client.get('/api/admin/entity-page/quests?limit=1').json()
    assert len(data['rows'])==1 and data['total']>1
    look=client.get('/api/admin/lookup/mob_templates?q=tide').json()
    assert any('tide' in r['label'].lower() for r in look)
    response=client.post('/api/admin/entities/exits',headers=headers,json={'values':{'source_room_id':1,'destination_room_id':3,'direction':'qa ledge','details':{'is_complex':True,'skill_check':{'skill':'acrobatics','dc':12,'fail_damage':3,'fail_prone':True}}}})
    assert response.status_code==200,response.text
    row=response.json()
    assert client.post(f'/api/admin/exits/{row["id"]}/delete',headers=headers,json={'original':{**row,'direction':'wrong'}}).status_code==409
    assert client.post(f'/api/admin/exits/{row["id"]}/delete',headers=headers,json={'original':row}).status_code==200
    login(client,False)
    assert client.get('/api/admin/lookup/mob_templates').status_code==403
    assert client.post(f'/api/admin/exits/{row["id"]}/delete',headers=headers,json={'original':row}).status_code==403


def test_ranged_retaliation_training_magic_and_rogue(client):
    from game.database import db_manager as db
    from game.character import Character
    from game.mob import Mob
    from game.item import Item
    from game import resolver
    from game.commands.combat import cmd_shoot,cmd_ammo
    from game.combat import damage_calculator,hit_resolver
    from game.definitions.abilities import ABILITIES_DATA
    from game.commands.rogue import cmd_pickpocket
    async def scenario():
        w=client.app.state.world
        async with w.mutation_lock:
            people=[]
            for first in ('Archer','Target'):
                pid=await db.create_player_account(first+secrets.token_hex(4),'disabled',secrets.token_hex(8)+'@example.test')
                cid=await db.create_character(pid,first,'Audit','Male',1,2,'Mage',dict.fromkeys(['might','vitality','agility','intellect','aura','persona'],16),'A traveler.',5000,5000,5000,5000,3)
                c=Character(None,dict(await db.load_character_data(cid)),w);c.send=AsyncMock();await c.load_related_data();c.update_location(w.rooms[7]);c.location.add_character(c);w.add_active_character(c);c.level=30;people.append(c)
            c,other=people
            for name,kind,stats in [('audit bow','RANGED_WEAPON',{'speed':3,'damage_base':8,'damage_rng':4,'damage_type':'pierce','uses_ammo_type':'arrow'}),('audit quiver','QUIVER',{'capacity':30,'holds_ammo_type':'arrow','wear_location':['waist']}),('audit arrow bundle','AMMO',{'quantity':20,'ammo_type':'arrow'})]:
                row=await db.fetch_one_query('INSERT INTO item_templates(name,type,stats,damage_type) VALUES($1,$2,$3,$4) RETURNING *',name,kind,json.dumps(stats),'pierce')
                t=dict(row);t['stats']=stats;w.item_templates[t['id']]=t
            template=next(t for t in w.mob_templates.values() if t['name']=='tide scavenger')
            mob=Mob({**template,'max_hp':5000},c.location);mob.name='audit beast';c.location.add_mob(mob)
            try:
                def item(name):
                    t=next(t for t in w.item_templates.values() if t['name']==name)
                    return Item({'id':secrets.token_hex(16),'instance_stats':{}},t)
                bow=item('audit bow');quiver=item('audit quiver');ammo=item('audit arrow bundle')
                # Persist ammunition because SHOOT decrements its instance.
                row=await db.fetch_one_query('INSERT INTO item_instances(template_id,owner_char_id) VALUES($1,$2) RETURNING *',ammo.template_id,c.dbid)
                ammo=Item(dict(row),ammo._template);quiver.contents[ammo.id]=ammo;quiver.instance_stats['is_open']=True
                c._equipped_items['main_hand']=bow;c._equipped_items['waist']=quiver
                c.send.reset_mock()
                with patch('game.combat.hit_resolver.random.randint',return_value=1):await cmd_shoot(c,w,'audit beast')
                assert mob.target is c and mob.is_fighting and ammo.stats['quantity']==19
                c.roundtime=0
                with patch('game.combat.hit_resolver.random.randint',side_effect=lambda a,b:b):await cmd_shoot(c,w,'audit beast')
                assert any('arrow critically hits audit beast' in x.args[0] for x in c.send.call_args_list)
                assert not any('arrow bundle' in x.args[0] for x in c.send.call_args_list)
                await cmd_ammo(c,w,'');assert '18 arrow' in c.send.call_args.args[0]
                c.skills['projectile weapons']=0
                with patch('game.combat.damage_calculator.random.randint',return_value=1):low=damage_calculator.calculate_physical_damage(c,bow,False).pre_mitigation_damage
                rating=c.rar;c.skills['projectile weapons']=100
                assert c.rar==rating+4
                with patch('game.combat.damage_calculator.random.randint',return_value=1):assert damage_calculator.calculate_physical_damage(c,bow,False).pre_mitigation_damage==low+5
                c.effects={'ward':{'stat_affected':'barrier_value','amount':10,'ends_at':time.monotonic()+60}};c.skills['warding']=100
                assert c.barrier_value==15
                c.effects.clear();assert c.barrier_value==0
                c._equipped_items.pop('main_hand');c._equipped_items.pop('waist')
                for key,ability in ABILITIES_DATA.items():
                    if ability.get('level_req',1)>30 or ability.get('effect_type') not in ('DAMAGE','BUFF','DEBUFF','HEAL','CONTESTED_DEBUFF'):continue
                    mob.hp=5000;other.hp=5000;c.hp=5000;c.is_hidden=True
                    target_type=ability.get('target_type')
                    ref,kind=(c.dbid,'SELF') if target_type=='SELF' or ability.get('effect_type') in ('HEAL','BUFF') else (mob.instance_id,'MOB')
                    try:
                        with patch('game.combat.hit_resolver.random.randint',return_value=20):await resolver.resolve_ability_effect(c,ref,kind,{**ability,'internal_name':key},w)
                    except Exception as e:raise AssertionError(f'{key}: {e}') from e
                from game.adventure import ADVANCED,cmd_technique
                for class_id,definition in w.classes.items():
                    c.class_id=class_id;c.level=30;c.essence=5000;c.hp=5000
                    moves=ADVANCED.get(definition['name'].lower(),('focus','cascade','disrupt','ascendance'))
                    for move in moves:
                        mob.hp=5000;c.roundtime=0
                        with patch('game.combat.hit_resolver.random.randint',return_value=20):await cmd_technique(c,w,move+' audit beast')
                        assert mob.hp<5000,(definition['name'],move)
                from game.commands.magic import cmd_cast
                from game.commands.abilities import cmd_use
                c.effects.clear();c.roundtime=0;c.essence=5000
                c.known_abilities.update({'mage armor','forked_lightning','backstab','garrote'})
                await cmd_cast(c,w,'mage armor');assert c.casting_info
                await w.update_roundtimes(30);assert c.barrier_value>=15
                c.roundtime=0;mob.hp=5000
                await cmd_cast(c,w,'forked lightning');assert c.casting_info
                with patch('game.combat.hit_resolver.random.randint',return_value=20):await w.update_roundtimes(30)
                assert mob.hp<5000
                c.roundtime=0;c.is_hidden=True;mob.hp=5000;mob.is_fighting=False;mob.target=None
                with patch('game.combat.hit_resolver.random.randint',return_value=20):await cmd_use(c,w,'backstab audit beast')
                assert mob.hp<5000 and not c.is_hidden
                c.roundtime=0;c.is_hidden=True;mob.hp=5000
                with patch('game.combat.hit_resolver.random.randint',return_value=20):await cmd_use(c,w,'garrote audit beast')
                assert 'GarroteBleed' in mob.effects and 'GarroteSilence' in mob.effects
                before=mob.hp;await w.update_effects(3);assert mob.hp<before
                # Real magic resolver in both player directions; sanctuary rejects it.
                spell={'name':'audit flame','effect_details':{'school':'Arcane','damage_type':'fire','damage_base':30,'damage_rng':0}}
                c.effects.clear();other.effects.clear();other.hp=5000
                with patch('game.combat.hit_resolver.random.randint',return_value=10):await resolver.resolve_magical_attack(c,other,spell,w)
                assert other.hp<5000 and other.target is c
                other.update_location(w.rooms[1]);c.update_location(w.rooms[1]);hp=other.hp
                await resolver.resolve_magical_attack(c,other,spell,w);assert other.hp==hp
                c.update_location(w.rooms[7]);other.update_location(w.rooms[7]);other.hp=0;other.status='DYING'
                heal=next(a for a in ABILITIES_DATA.values() if a.get('effect_type')=='HEAL')
                await resolver.resolve_ability_effect(c,other.dbid,'CHAR',{**heal,'target_type':'CHAR'},w)
                assert other.hp==1 and other.status=='ALIVE'
                c.is_fighting=False;mob.coinage=20
                with patch('game.commands.rogue.utils.skill_check',return_value={'success':True,'total_check':10}),patch('game.commands.rogue.random.randint',return_value=5):await cmd_pickpocket(c,w,'audit beast')
                assert mob.coinage==15
            finally:
                c.location.remove_mob(mob)
                for p in people:w.rooms[7].remove_character(p);w.remove_active_character(p.dbid)
    client.portal.call(scenario)
