"""Single-use, expiring reset/verification tokens; no secrets in logs or URLs."""
import asyncio
import os
import secrets
import smtplib
import ssl
from email.message import EmailMessage
from fastapi import APIRouter,Request,HTTPException
from pydantic import BaseModel,Field
from game.database import db_manager as db
from game import utils
from web.auth import origin_check,rate_limit,digest,hash_slots

router=APIRouter(prefix='/api/auth/recovery')
class RecoveryRequest(BaseModel):
    email:str=Field(max_length=254)
    purpose:str='reset'
class Redeem(BaseModel):
    token:str=Field(min_length=20,max_length=128)
    password:str=Field(default='',max_length=128)

def configured():return bool(os.getenv('SMTP_HOST') and os.getenv('MAIL_FROM'))

def send_email(address,purpose,token):
    message=EmailMessage();message['From']=os.environ['MAIL_FROM'];message['To']=address
    message['Subject']='Chrozal '+('password recovery' if purpose=='reset' else 'email verification')
    message.set_content('Enter this single-use code in the Chrozal account recovery panel within 30 minutes:\n\n'+token+'\n\nIf you did not request this, ignore this message.')
    with smtplib.SMTP(os.environ['SMTP_HOST'],int(os.getenv('SMTP_PORT','587')),timeout=10) as smtp:
        smtp.starttls(context=ssl.create_default_context())
        if os.getenv('SMTP_USER'):smtp.login(os.environ['SMTP_USER'],os.environ['SMTP_PASSWORD'])
        smtp.send_message(message)

async def issue(player_id,purpose):
    token=secrets.token_urlsafe(32)
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            await conn.execute('DELETE FROM account_tokens WHERE player_id=$1 AND purpose=$2 OR expires_at<now()',player_id,purpose)
            await conn.execute('INSERT INTO account_tokens(token_hash,player_id,purpose) VALUES($1,$2,$3)',digest(token),player_id,purpose)
    return token

@router.post('/request')
async def request_token(body:RecoveryRequest,request:Request):
    origin_check(request);rate_limit(request)
    if body.purpose not in ('reset','verify'):raise HTTPException(422,'Invalid purpose')
    if not configured():raise HTTPException(503,'Email delivery is not configured. Ask the host for an account recovery code.')
    row=await db.fetch_one_query('SELECT id,email FROM players WHERE lower(email)=lower($1)',body.email.strip())
    if row:
        token=await issue(row['id'],body.purpose)
        try:await asyncio.to_thread(send_email,row['email'],body.purpose,token)
        except Exception:
            __import__('logging').getLogger(__name__).error('Account email delivery failed; check SMTP configuration')
    return {'message':'If the address is registered, a code has been sent.'}

@router.post('/redeem')
async def redeem(body:Redeem,request:Request):
    origin_check(request);rate_limit(request)
    async with hash_slots:
        hashed=await asyncio.to_thread(utils.hash_password,body.password) if len(body.password)>=12 else None
    async with db.pool.acquire() as conn:
        async with conn.transaction():
            token=await conn.fetchrow('SELECT * FROM account_tokens WHERE token_hash=$1 AND expires_at>now() FOR UPDATE',digest(body.token))
            if not token:raise HTTPException(400,'Invalid or expired code')
            if token['purpose']=='reset':
                if not hashed:raise HTTPException(422,'Use a password with at least 12 characters')
                await conn.execute('UPDATE players SET hashed_password=$1 WHERE id=$2',hashed,token['player_id'])
                await conn.execute('DELETE FROM web_sessions WHERE player_id=$1',token['player_id'])
            else:await conn.execute('UPDATE players SET email_verified=true WHERE id=$1',token['player_id'])
            await conn.execute('DELETE FROM account_tokens WHERE player_id=$1 AND purpose=$2',token['player_id'],token['purpose'])
    return {'message':'Account updated. You can sign in.'}
