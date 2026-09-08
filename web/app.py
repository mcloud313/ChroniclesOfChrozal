"""One authoritative world, shared by authenticated browser clients and builders."""
import asyncio
import anyio
import contextlib
import json
import logging
import time
from collections import deque
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Depends, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
import config
from game.database import db_manager
from game.world import World
from game.player import Player
from game.handlers.connection import ConnectionHandler, ConnectionState
from game import ticker
from web import auth
from web.transport import BrowserWriter, snapshot

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger(__name__)

class RecentLogs(logging.Handler):
    def __init__(self):
        super().__init__(logging.INFO)
        self.entries = deque(maxlen=300)
    def emit(self, record):
        self.entries.append({'time': record.created, 'level': record.levelname,
                             'logger': record.name, 'message': record.getMessage()[:2000]})

async def migrate():
    async with db_manager.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('SELECT pg_advisory_xact_lock(730031)')
            await conn.execute('CREATE TABLE IF NOT EXISTS schema_migrations(name TEXT PRIMARY KEY, applied_at TIMESTAMPTZ DEFAULT now())')
            for path in sorted((ROOT/'migrations').glob('*.sql')):
                if not await conn.fetchval('SELECT 1 FROM schema_migrations WHERE name=$1',path.name):
                    await conn.execute(path.read_text())
                    await conn.execute('INSERT INTO schema_migrations(name) VALUES($1)',path.name)

async def autosave(app):
    while True:
        await asyncio.sleep(config.AUTOSAVE_INTERVAL_SECONDS)
        try:
            await app.state.world.save_state()
        except Exception:
            log.exception('Autosave failed')

@asynccontextmanager
async def lifespan(app):
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(name)s %(message)s')
    from game.logging_config import configure
    file_handlers=configure()
    recent = RecentLogs()
    logging.getLogger().addHandler(recent)
    app.state.logs = recent
    app.state.connections = {}
    app.state.detached = {}
    app.state.join_lock = asyncio.Lock()
    app.state.started = time.monotonic()
    app.state.ready = False
    tasks = []
    try:
        await db_manager.connect()
        await db_manager.init_db()
        await migrate()
        world = World(db_manager)
        if not await world.build():
            raise RuntimeError('World could not be loaded')
        from game.living import LivingWorld
        world.living = LivingWorld(world)
        await world.living.load()
        app.state.world = world
        world.subscribe_to_ticker()
        async def living_tick(dt):
            async with app.state.world.mutation_lock:
                await app.state.world.living.tick(dt)
        ticker.subscribe(living_tick)
        await ticker.start_ticker(config.TICKER_INTERVAL_SECONDS)
        if config.AUTOSAVE_INTERVAL_SECONDS > 0:
            tasks.append(asyncio.create_task(autosave(app)))
        app.state.ready = True
        yield
    finally:
        app.state.ready = False
        for detached in list(app.state.detached.values()):
            detached['expiry'].cancel()
            detached['reader'].feed_eof()
            await detached['task']
        app.state.detached.clear()
        await ticker.stop_ticker()
        ticker._callbacks.clear()
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        try:
            if hasattr(app.state, 'world'):
                await app.state.world.save_state()
        finally:
            await db_manager.close()
            logging.getLogger().removeHandler(recent)
        for logger,handler in file_handlers:
            logger.removeHandler(handler);handler.close()

app = FastAPI(title='Chronicles of Chrozal', lifespan=lifespan, docs_url=None, redoc_url=None)
app.include_router(auth.router)
from web.recovery import router as recovery_router
app.include_router(recovery_router)

@app.middleware('http')
async def headers(request, call_next):
    if int(request.headers.get('content-length','0') or 0) > 65536:
        from fastapi.responses import JSONResponse
        return JSONResponse({'detail':'Request too large'}, status_code=413)
    if __import__('posixpath').normpath(request.scope['path']) in {'/static/admin.html','/static/admin.js','/static/map.js'}:
        try:
            player=await auth.current_player(request)
            await auth.admin_player(request, player)
        except __import__('fastapi').HTTPException as exc:
            from fastapi.responses import JSONResponse
            return JSONResponse({'detail':exc.detail},status_code=exc.status_code)
    response = await call_next(request)
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'same-origin'
    response.headers['Content-Security-Policy'] = "default-src 'self'; connect-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    if request.url.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store'
    return response

@app.get('/healthz')
async def health():
    from fastapi.responses import JSONResponse
    try:
        await db_manager.fetch_one_query('SELECT 1')
        ready = app.state.ready
    except Exception:
        ready = False
    return JSONResponse({'ready':ready}, status_code=200 if ready else 503)

@app.get('/')
async def index():
    return FileResponse(ROOT/'web/static/index.html')

@app.get('/admin')
async def admin_page(player=Depends(auth.admin_player)):
    return FileResponse(ROOT/'web/static/admin.html')

app.mount('/static', StaticFiles(directory=ROOT/'web/static'), name='static')

@app.websocket('/ws')
async def websocket(ws: WebSocket):
    if ws.headers.get('origin') != config.PUBLIC_ORIGIN or not app.state.ready:
        await ws.close(code=1008)
        return
    token = ws.cookies.get('chrozal_session')
    player = await auth.session_player(token)
    if not player or player['must_change_password'] or not app.state.ready:
        await ws.close(code=1008)
        return
    player_id = player['id']
    # Reserve before the first await: one active connection per account.
    if player_id in app.state.connections or (player_id not in app.state.detached and len(app.state.connections)+len(app.state.detached) >= config.MAX_PLAYERS):
        await ws.close(code=1013)
        return
    app.state.connections[player_id] = ws
    resumed=app.state.detached.pop(player_id,None)
    if resumed:
        resumed['expiry'].cancel()
        reader,writer,handler=resumed['reader'],resumed['writer'],resumed['handler']
        writer.websocket=ws;writer.closed=False
        while not writer.queue.empty():writer.queue.get_nowait()
        handler.player_account=Player(**dict(player))
        if handler.active_character:handler.active_character.linkdead=False
    else:
        reader = asyncio.StreamReader(limit=config.MAX_INPUT_LENGTH+1)
        writer = BrowserWriter(ws)
        handler = ConnectionHandler(reader, writer, app.state.world, db_manager)
        handler.player_account = Player(**dict(player))
        handler.state = ConnectionState.SELECTING_CHARACTER
    authenticated=True
    last_heartbeat=time.monotonic()
    warned=False
    tasks = []
    try:
        await ws.accept()
        writer.emit('session', {'username':player['username']})
        await db_manager.execute_query("INSERT INTO connection_events(player_id,event) VALUES($1,$2)",player_id,'reconnected' if resumed else 'connected')
        if resumed:writer.emit('text','Connection restored. Your character remained in the world.\n')
        async def receive():
            nonlocal last_heartbeat,warned
            tokens, previous = 10.0, time.monotonic()
            while True:
                raw = await asyncio.wait_for(ws.receive_text(), timeout=1800)
                now = time.monotonic()
                tokens = min(10, tokens+(now-previous)*4)
                previous = now
                if tokens < 1:
                    raise ValueError('Command rate exceeded')
                tokens -= 1
                if len(raw.encode()) > 4096:
                    raise ValueError('Frame too large')
                message = json.loads(raw)
                if isinstance(message,dict) and message.get('type')=='heartbeat':
                    last_heartbeat=now;warned=False
                    continue
                if not isinstance(message, dict) or message.get('type') != 'command':
                    raise ValueError('Invalid protocol')
                last_heartbeat=now;warned=False
                payload = message.get('payload')
                if not isinstance(payload, str) or len(payload.encode()) > config.MAX_INPUT_LENGTH or any(ord(c)<32 for c in payload):
                    raise ValueError('Invalid command')
                # No command buffering while the engine is blocked on another action.
                if len(reader._buffer) > 4096:
                    raise ValueError('Input buffer full')
                # Do not queue future gameplay while an action is recovering.
                c=handler.active_character
                verb=payload.split(' ',1)[0].lower()
                social={'say','whisper','emote','/me','pose','look','l','score','stats','who','help','quest','quit','brace'}
                if c and c.roundtime>0 and verb not in social:
                    writer.emit('text',f'You are recovering for {c.roundtime:.1f}s. Commands are not queued.\n')
                    continue
                if reader._buffer:
                    writer.emit('text','Wait for your previous input to be processed.\n')
                    continue
                reader.feed_data((payload+'\n').encode())
        async def updates():
            nonlocal authenticated,warned
            last_check = 0
            while True:
                await asyncio.sleep(1)
                quiet=time.monotonic()-last_heartbeat
                if quiet>240 and not warned:
                    writer.emit('text','No client heartbeat. Connection expires in one minute; your character may be exposed outside a safe node.\n');warned=True
                if quiet>300:return
                if time.monotonic()-last_check > 15:
                    account = await auth.session_player(token)
                    if not account:
                        authenticated=False
                        return
                    handler.player_account.is_admin = account['is_admin']
                    if handler.active_character:
                        handler.active_character.is_admin = account['is_admin']
                    last_check = time.monotonic()
                state = snapshot(handler.active_character, app.state.world)
                if state:
                    writer.emit('vitals_update', state)
        # Builder publication holds this lock; login cannot enter during replacement.
        async def run_handler():
            async with app.state.join_lock:
                handler.world = app.state.world
            await handler.handle()
        tasks = [asyncio.create_task(c()) for c in (receive, updates, writer.pump)]
        tasks.append(resumed['task'] if resumed else asyncio.create_task(run_handler()))
        await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
    except (WebSocketDisconnect, ConnectionError):
        pass
    finally:
        with anyio.CancelScope(shield=True):
            # Abrupt disconnects retain the authoritative character for five minutes.
            # No invulnerability or command automation is granted while detached.
            if time.monotonic()-last_heartbeat<300 and app.state.ready and handler.active_character and handler.state != ConnectionState.DISCONNECTED and len(tasks)==4 and not tasks[3].done():
                for task in tasks[:3]:task.cancel()
                await asyncio.gather(*tasks[:3],return_exceptions=True)
                writer.closed=True
                handler.active_character.linkdead=True
                async def expire():
                    try:
                        await asyncio.sleep(300)
                        app.state.detached.pop(player_id,None)
                        reader.feed_eof()
                        await tasks[3]
                        await db_manager.execute_query("INSERT INTO connection_events(player_id,event) VALUES($1,'grace_expired')",player_id)
                    except asyncio.CancelledError:pass
                app.state.detached[player_id]={'handler':handler,'reader':reader,'writer':writer,'task':tasks[3],'expiry':asyncio.create_task(expire())}
                app.state.connections.pop(player_id,None)
                await db_manager.execute_query("INSERT INTO connection_events(player_id,event) VALUES($1,'link_lost')",player_id)
                with contextlib.suppress(Exception):await ws.close()
                return
            reader.feed_eof()
            handler.state = ConnectionState.DISCONNECTED
            # Let the handler complete its save/cleanup; do not cancel an in-flight save.
            for task in tasks[:3]:
                if not task.done():
                    task.cancel()
            if len(tasks) == 4:
                try:
                    await asyncio.wait_for(asyncio.shield(tasks[3]), timeout=90)
                except (asyncio.TimeoutError, asyncio.CancelledError):
                    tasks[3].cancel()
            results = await asyncio.gather(*tasks, return_exceptions=True)
            for result in results:
                if isinstance(result, Exception) and not isinstance(result,(WebSocketDisconnect,ValueError,ConnectionError)):
                    log.error('Web connection failed: %s',type(result).__name__, exc_info=(type(result),result,result.__traceback__))
            writer.close()
            app.state.connections.pop(player_id, None)
            with contextlib.suppress(Exception):
                await ws.close()

from web.admin import router as admin_router
app.include_router(admin_router)

from web.builds import router as builds_router
app.include_router(builds_router)
