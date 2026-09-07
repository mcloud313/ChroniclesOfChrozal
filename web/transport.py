"""Bounded stream adapter keeps the existing game engine transport independent."""
import asyncio
import re

ANSI = re.compile(r'\x1b\[[0-?]*[ -/]*[@-~]')
COLORS = re.compile(r'<[a-zA-Z]>')

class BrowserWriter:
    def __init__(self, websocket):
        self.websocket = websocket
        self.queue = asyncio.Queue(maxsize=256)
        self.closed = False

    def get_extra_info(self, name, default=None):
        return self.websocket.client.host if name == 'peername' and self.websocket.client else default

    def write(self, data):
        self.emit('text', ANSI.sub('', COLORS.sub('', data.decode('utf-8', errors='replace'))))

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
        'name': character.name, 'hp': character.hp, 'max_hp': character.max_hp,
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
        'inventory': [i.name for i in character._inventory_items.values()],
    }
