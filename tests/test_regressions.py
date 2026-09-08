import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
import pytest
from game.commands.social import cmd_accept
from game.commands.handler import process_command
from web.transport import BrowserWriter
from web.auth import origin_check
from fastapi import HTTPException

@pytest.mark.asyncio
async def test_group_accept_resolves_invitation():
    room=object()
    leader=SimpleNamespace(dbid=1,name='Leader',group=None,is_alive=lambda:True,location=room,send=AsyncMock())
    # Group members must be hashable.
    class Member:
        def __init__(self,id,name):
            self.dbid=id;self.name=name;self.group=None;self.location=room;self.send=AsyncMock()
        def is_alive(self):return True
    leader=Member(1,'Leader');guest=Member(2,'Guest')
    world=SimpleNamespace(pending_invites={2:1},get_active_character=lambda id:leader,add_active_group=lambda g:None)
    assert await cmd_accept(guest,world,'group')
    assert not world.pending_invites
    assert guest.group is leader.group

@pytest.mark.asyncio
async def test_roleplay_allowed_during_roundtime():
    room=SimpleNamespace(broadcast=AsyncMock())
    c=SimpleNamespace(status='ALIVE',roundtime=8,location=room,name='Traveler',dbid=1,send=AsyncMock())
    assert await process_command(c,None,'emote smiles at the fire.')
    room.broadcast.assert_awaited_once()
    assert await process_command(c,None,'attack rat')
    assert 'recovering' in c.send.call_args.args[0]

def test_slow_consumer_bounded_and_text_safe():
    w=BrowserWriter(SimpleNamespace(client=None))
    w.write(b'\x1b[31mhello<Y>\n')
    assert w.queue.get_nowait()['payload']=='hello\n'
    for _ in range(256):w.emit('text','x')
    with pytest.raises(BrokenPipeError):w.emit('text','overflow')
    assert w.closed

def test_cross_origin_denied():
    with pytest.raises(HTTPException):origin_check(SimpleNamespace(headers={'origin':'https://evil.example'}))

@pytest.mark.asyncio
async def test_failed_save_keeps_character_dirty():
    from game.character import Character
    c=object.__new__(Character)
    c.is_dirty=True;c.dbid=10;c.stats={};c.skills={};c.known_abilities=set()
    c.get_core_data_for_saving=lambda:{};c.get_equipment_for_saving=lambda:{}
    c.get_all_owned_item_instances=lambda:[]
    c.world=SimpleNamespace(db_manager=SimpleNamespace(save_character_full=AsyncMock(side_effect=RuntimeError('database unavailable'))))
    with pytest.raises(RuntimeError):await c.save()
    assert c.is_dirty

def test_brace_removed():
    from game.commands.handler import COMMAND_MAP
    assert 'brace' not in COMMAND_MAP


def test_long_progression_and_cap():
    import config
    from game.utils import xp_needed_for_level as xp
    assert config.MAX_LEVEL==99
    thresholds=[xp(i) for i in range(1,99)]
    assert all(b>a for a,b in zip(thresholds,thresholds[1:]))
    assert xp(74)/config.XP_ABSORB_RATE_PER_SEC/3600==600
    steps=[xp(i)-xp(i-1) for i in range(75,99)]
    assert all(1.17<b/a<1.19 for a,b in zip(steps,steps[1:]))
    assert xp(99)==float('inf')


def test_race_descriptions_cover_traits_without_none_beards():
    from game.appearance import describe
    from game.definitions.traits import TRAIT_OPTIONS
    for race in TRAIT_OPTIONS:
        text=describe({'race_name':race,'first_name':'Traveler','sex':'They/Them'})
        assert race in text
        assert 'none beard' not in text.lower()
        assert 'they has' not in text.lower()


def test_calendar_weather_seasons_match():
    from game.definitions.calendar import get_season
    from game.definitions.weather import WEATHER_TABLES
    assert all(get_season(month) in WEATHER_TABLES for month in range(1,13))


def test_natural_attack_rolls_survive_modifiers(monkeypatch):
    from game.combat.hit_resolver import check_physical_hit
    attacker=SimpleNamespace(mar=0)
    target=SimpleNamespace(dv=1000)
    monkeypatch.setattr('game.combat.hit_resolver.random.randint',lambda a,b:20)
    assert check_physical_hit(attacker,target,hit_modifier=-50).is_crit
    monkeypatch.setattr('game.combat.hit_resolver.random.randint',lambda a,b:1)
    assert not check_physical_hit(attacker,target,hit_modifier=10000).is_hit


def test_weather_changes_spell_damage_and_nodes_protect_pvp():
    from game.resolver import _get_weather_damage_modifier,protected_pvp
    from game.character import Character
    room=SimpleNamespace(flags={'WET','NODE'})
    assert _get_weather_damage_modifier(room,'fire')==.75
    assert _get_weather_damage_modifier(room,'lightning')==1.25
    a=object.__new__(Character);b=object.__new__(Character);a.location=room;b.location=room
    assert protected_pvp(a,b)

@pytest.mark.asyncio
@pytest.mark.parametrize('command', ['n','north','go n','go north'])
@pytest.mark.parametrize('stored', ['n','north'])
async def test_real_movement_dispatch_and_locked_door(command, stored, monkeypatch):
    from game.commands import movement
    source=SimpleNamespace(dbid=1,exits={stored:{'destination_room_id':2,'details':{'is_door':True,'is_open':True,'is_locked':True}}})
    destination=object()
    c=SimpleNamespace(status='ALIVE',stance='Standing',roundtime=0,location=source,location_id=1,
                      name='Traveler',dbid=1,send=AsyncMock(),can_see=lambda:True)
    w=SimpleNamespace(get_room=lambda id:destination,mutation_lock=asyncio.Lock())
    move=AsyncMock();monkeypatch.setattr(movement,'_perform_move',move)
    await process_command(c,w,command)
    move.assert_not_awaited()
    assert 'locked' in c.send.call_args.args[0]
    source.exits[stored]['details']['is_locked']=False
    await process_command(c,w,command)
    move.assert_awaited_once_with(c,w,destination,stored)


def test_browser_colors_preserve_plain_text_without_html_execution():
    from web.transport import colored_text
    spans=colored_text('{rDamage<x> <script>alert(1)</script>\x1b[32m healed\x1b[0m')
    assert ''.join(x['text'] for x in spans)=='Damage <script>alert(1)</script> healed'
    assert spans[0]['color']=='red'
    assert spans[-1]['color']=='green'
