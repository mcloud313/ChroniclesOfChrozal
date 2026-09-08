"""Opaque, expiring, server-side sessions; exact-origin mutation protection."""
import asyncio
import hashlib
import secrets
import time
from collections import OrderedDict
from fastapi import APIRouter, HTTPException, Request, Response, Depends
from pydantic import BaseModel, Field
import config
from game.database import db_manager
from game.player import Player
from game import utils

router = APIRouter(prefix='/api/auth')
# Bounded buckets and hashing concurrency protect the single simulation process.
buckets = OrderedDict()
hash_slots = asyncio.Semaphore(2)

class Credentials(BaseModel):
    username: str = Field(min_length=3, max_length=32, pattern=r'^[A-Za-z0-9_]+$')
    password: str = Field(min_length=1, max_length=128)
    email: str = Field(default='', max_length=254)


def origin_check(request):
    if request.headers.get('origin') != config.PUBLIC_ORIGIN:
        raise HTTPException(403, 'Origin not allowed')


def rate_limit(request):
    key = request.client.host if request.client else 'unknown'
    now = time.monotonic()
    times = [t for t in buckets.pop(key, []) if now-t < 60]
    if len(buckets) >= 4096:
        buckets.popitem(last=False)
    buckets[key] = times
    if len(times) >= 10:
        raise HTTPException(429, 'Please wait a minute before trying again')
    times.append(now)


def digest(token):
    return hashlib.sha256(token.encode()).hexdigest()


async def session_player(token):
    if not token or len(token) > 128:
        return None
    return await db_manager.fetch_one_query('''SELECT p.* FROM players p JOIN web_sessions s ON p.id=s.player_id
        WHERE s.token_hash=$1 AND s.expires_at > now()''', digest(token))


async def current_player(request: Request):
    player = await session_player(request.cookies.get('chrozal_session'))
    if not player:
        raise HTTPException(401, 'Sign in to continue')
    return player


async def admin_player(request: Request, player=Depends(current_player)):
    if player['must_change_password']:
        raise HTTPException(403,'Change the initial password before using administration')
    if not player['is_admin']:
        raise HTTPException(403, 'Builder access required')
    if request.method not in {'GET', 'HEAD'}:
        origin_check(request)
    return player


@router.get('/me')
async def me(player=Depends(current_player)):
    return {'username': player['username'], 'is_admin': player['is_admin'], 'must_change_password':player['must_change_password']}


class PasswordChange(BaseModel):
    password: str = Field(min_length=12,max_length=128)

@router.post('/change-password')
async def change_password(body: PasswordChange, request: Request, response: Response, player=Depends(current_player)):
    origin_check(request)
    rate_limit(request)
    async with hash_slots:
        account=Player(**dict(player))
        same,_=await asyncio.to_thread(account.check_password,body.password)
        if same:raise HTTPException(422,'Choose a different password')
        hashed=await asyncio.to_thread(utils.hash_password,body.password)
    async with db_manager.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('UPDATE players SET hashed_password=$1,must_change_password=false WHERE id=$2',hashed,player['id'])
            await conn.execute('DELETE FROM web_sessions WHERE player_id=$1',player['id'])
    response.delete_cookie('chrozal_session')
    return {'message':'Password changed. Sign in again.'}

@router.post('/{action}')
async def authenticate(action: str, body: Credentials, request: Request, response: Response):
    origin_check(request)
    rate_limit(request)
    if action not in {'login', 'register'}:
        raise HTTPException(404)
    async with hash_slots:
        if action == 'register':
            if not config.ALLOW_REGISTRATION:
                raise HTTPException(403, 'Registration is currently invite-only; ask the host for an account')
            if len(body.password) < 12 or '@' not in body.email or '.' not in body.email.split('@')[-1]:
                raise HTTPException(422, 'Use a 12-character password and valid email')
            from web.recovery import configured
            if not configured():raise HTTPException(503,'Public registration requires configured verification email delivery')
            hashed = await asyncio.to_thread(utils.hash_password, body.password)
            result = await db_manager.create_player_account(body.username, hashed, body.email, email_verified=False)
            if not result:
                raise HTTPException(409, 'Account could not be created')
            return {'verification_required':True}
        player = await db_manager.load_player_account(body.username)
        if not player:
            # Equalize expensive work for unknown usernames.
            await asyncio.to_thread(utils.hash_password, body.password)
            raise HTTPException(401, 'Invalid credentials')
        account = Player(**dict(player))
        valid, rehash = await asyncio.to_thread(account.check_password, body.password)
        if not valid:
            raise HTTPException(401, 'Invalid credentials')
        if not player['email_verified']:
            raise HTTPException(403,'Verify your email through Account recovery before signing in')
        if rehash:
            hashed = await asyncio.to_thread(utils.hash_password, body.password)
            await db_manager.execute_query('UPDATE players SET hashed_password=$1 WHERE id=$2', hashed, player['id'])
    token = secrets.token_urlsafe(32)
    async with db_manager.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('DELETE FROM web_sessions WHERE expires_at < now() OR player_id=$1', player['id'])
            await conn.execute('INSERT INTO web_sessions(token_hash,player_id) VALUES($1,$2)', digest(token),player['id'])
    response.set_cookie('chrozal_session', token, httponly=True, secure=config.COOKIE_SECURE,
                        samesite='strict', max_age=43200)
    return {'username': player['username'], 'is_admin': player['is_admin'], 'must_change_password':player['must_change_password']}


@router.delete('/session')
async def logout(request: Request, response: Response):
    origin_check(request)
    await db_manager.execute_query('DELETE FROM web_sessions WHERE token_hash=$1', digest(request.cookies.get('chrozal_session','')))
    response.delete_cookie('chrozal_session')
    return {'ok': True}
