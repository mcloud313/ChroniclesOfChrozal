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

@pytest.mark.asyncio
async def test_brace_cannot_shorten_attack_recovery():
    from types import SimpleNamespace
    from unittest.mock import AsyncMock
    from game.adventure import cmd_brace
    c=SimpleNamespace(roundtime=3.5,effects={},is_dirty=False,send=AsyncMock())
    await cmd_brace(c,None,'')
    assert c.roundtime==3.5
    assert c.is_dirty


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
