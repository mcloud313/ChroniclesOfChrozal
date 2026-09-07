"""Bounded stream adapter keeps the existing game engine transport independent."""
import asyncio
import re

ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
COLORS = re.compile(r'<(?:b?[kKRGYBMCWrg ybmcwxiu])>|\{[kKRGYBMCWrg ybmcwx]'.replace(' ', ''))
TOKEN = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]|<(?:b?[kKRGYBMCWrg ybmcwxiu])>|\{[kKRGYBMCWrg ybmcwx]'.replace(' ', ''))
PALETTE = {'r':'red','g':'green','y':'gold','b':'blue','m':'magenta','c':'cyan','w':'white','k':'muted'}

def colored_text(text):
    spans=[]; color=''; pos=0
    for match in TOKEN.finditer(text):
        if match.start()>pos: spans.append({'text':text[pos:match.start()], 'color':color})
        code=match.group()
        if code.startswith('\x1b'):
            values=code[2:-1].split(';')
            if '0' in values or code=='\x1b[m': color=''
            for value in values:
                if value.isdigit() and (30<=int(value)<=37 or 90<=int(value)<=97):
                    color=PALETTE['krgybmcw'[int(value)%10]]
        else: color=PALETTE.get(code[1:2].lower(),'')
        pos=match.end()
    if pos<len(text): spans.append({'text':text[pos:], 'color':color})
    return spans


class BrowserWriter:
    def __init__(self, websocket):
        self.websocket = websocket
        self.queue = asyncio.Queue(maxsize=256)
        self.closed = False

    def get_extra_info(self, name, default=None):
        return self.websocket.client.host if name == 'peername' and self.websocket.client else default

    def write(self, data):
        spans=colored_text(data.decode('utf-8', errors='replace'))
        payload=''.join(s['text'] for s in spans)
        self.emit('text', payload)
        if self.queue.qsize():
            self.queue._queue[-1]['spans']=spans


    def emit(self, kind, payload):
        if self.closed:
            return
        try:
            self.queue.put_nowait({'type': kind, 'payload': payload})
        except asyncio.QueueFull:
            self.close()
            raise BrokenPipeError('Slow client output limit reached')

    async def drain(self):
        if self.closed:
            raise BrokenPipeError('Connection closed')

    def close(self):
        self.closed = True

    def is_closing(self):
        return self.closed

    async def wait_closed(self):
        return

    async def pump(self):
        while not self.closed or not self.queue.empty():
            try:
                message = await asyncio.wait_for(self.queue.get(), timeout=1)
            except asyncio.TimeoutError:
                continue
            try:
                await asyncio.wait_for(self.websocket.send_json(message), timeout=5)
            except RuntimeError:
                from starlette.websockets import WebSocketState
                if self.websocket.client_state == WebSocketState.DISCONNECTED or self.websocket.application_state == WebSocketState.DISCONNECTED:
                    return
                raise


def snapshot(character, world):
    if not character or character.dbid not in world.active_characters:
        return None
    from game.definitions import calendar as cal
    room = character.location
    visible = character.can_see()
    return {
        'name': character.name,
        'online': sorted(c.name+(' [link lost]' if getattr(c,'linkdead',False) else '') for c in world.active_characters.values()),
        'xp_total': character.xp_total,
        'playtime': character.total_playtime_seconds + int(__import__('time').monotonic()-character.login_timestamp) if character.login_timestamp else character.total_playtime_seconds,
        'stats': dict(character.stats),
        'class':world.get_class_name(character.class_id),
        'description':character.description,
        'coins':character.coinage,
        'conditions':list(character.effects),
        'xp_next': __import__('game.utils',fromlist=['xp_needed_for_level']).xp_needed_for_level(character.level) if character.level<99 else None,
        'safe': bool(set(room.flags)&{'NODE','SAFE_ZONE','SAFE'}) and not character.is_fighting, 'hp': character.hp, 'max_hp': character.max_hp,
        'essence': character.essence, 'max_essence': character.max_essence,
        'soul_tether':character.spiritual_tether,
        'combat':{'melee':character.mar,'ranged':character.rar,'arcane':character.apr,'divine':character.dpr,'defense':character.dv,'armor':character.total_av},
        'date':f'{cal.DAY_NAMES[((world.game_month-1)*cal.DAYS_PER_MONTH+world.game_day-1)%cal.DAYS_PER_WEEK]}, {world.game_day} {cal.MONTH_NAMES[world.game_month-1]}, {world.game_year} · {cal.get_season(world.game_month)}',
        'level': character.level, 'xp_pool': character.xp_pool, 'roundtime': character.roundtime,
        'stance': character.stance, 'hunger': character.hunger, 'thirst': character.thirst,
        'room': {'id': room.dbid, 'name': room.name if visible else 'Darkness',
                 'exits': [d for d,e in room.exits.items() if not e.get('is_hidden')] if visible else []},
        'time': f'{world.game_hour:02}:{world.game_minute:02}',
        'weather': world.area_weather.get(room.area_id, {}).get('condition', 'CLEAR'),
        'inventory': [f"{i.instance_stats.get('held_hand','held').title()}: {i.name}" for i in character._inventory_items.values()],
    }
