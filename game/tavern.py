"""Virtual-currency house games. Persist wagers and hidden decks before revealing cards."""
import json
import secrets
import logging
log=logging.getLogger(__name__)
from collections import Counter

RNG=secrets.SystemRandom()

def score(cards):
    counts=Counter(c%13+2 for c in cards)
    ranks=sorted(counts,reverse=True)
    flush=len({c//13 for c in cards})==1
    straight=(5 if ranks==[14,5,4,3,2] else max(ranks)) if len(ranks)==5 and (max(ranks)-min(ranks)==4 or ranks==[14,5,4,3,2]) else 0
    groups=sorted(((n,r) for r,n in counts.items()),reverse=True)
    if straight and flush:return (8,straight)
    if groups[0][0]==4:return (7,groups[0][1],groups[1][1])
    if [g[0] for g in groups]==[3,2]:return (6,groups[0][1],groups[1][1])
    if flush:return (5,*ranks)
    if straight:return (4,straight)
    if groups[0][0]==3:return (3,groups[0][1],*sorted((r for r in ranks if counts[r]==1),reverse=True))
    pairs=sorted((r for r in ranks if counts[r]==2),reverse=True)
    if len(pairs)==2:return (2,*pairs,next(r for r in ranks if counts[r]==1))
    if pairs:return (1,*pairs,*sorted((r for r in ranks if counts[r]==1),reverse=True))
    return (0,*ranks)

NAMES=('high card','pair','two pairs','three of a kind','straight','flush','full house','four of a kind','straight flush')
def display(cards):
    return ' '.join(f'{i+1}:{"23456789TJQKA"[c%13]}{"♣♦♥♠"[c//13]}' for i,c in enumerate(cards))

def dealer_draw(hand,deck):
    if score(hand)[0]>=4:return hand
    counts=Counter(c%13 for c in hand)
    keep={i for i,c in enumerate(hand) if counts[c%13]>1}
    if not keep:keep=set(sorted(range(5),key=lambda i:hand[i]%13,reverse=True)[:2])
    return [c if i in keep else deck.pop() for i,c in enumerate(hand)]

async def command(c,w,args,game='cards'):
    if not args:
        if game=='cards':
            row=await w.db_manager.fetch_one_query('SELECT state FROM tavern_hands WHERE character_id=$1 AND NOT settled',c.dbid)
            if row:
                state=json.loads(row['state']) if isinstance(row['state'],str) else row['state']
                await c.send('Your saved hand: '+display(state['player']))
        await c.send('CARDS BET <1-10>: five-card draw versus the house. CARDS DRAW 1,3 exchanges up to three cards and settles; CARDS STAND keeps all five. Standard poker ranks; suits tie. Win returns twice your stake, tie returns stake. DICE <1-10>: roll two dice; 7 or 11 wins triple your stake. Bets require level 10, a tavern, and 30 seconds between games. Talons only; maximum 100 staked per real UTC day.');return True
    if c.level<10 or 'TAVERN' not in c.location.flags or c.is_fighting:
        await c.send('Gambling requires level 10 and a peaceful tavern.');return True
    parts=args.lower().split();bet=None
    if game=='dice' or parts[0]=='bet':
        try:bet=int(parts[0] if game=='dice' else parts[1])
        except (ValueError,IndexError):await c.send('Choose a stake of 1–10 Talons.');return True
        if not 1<=bet<=10 or len(parts)!=(1 if game=='dice' else 2):
            await c.send('Choose a stake of 1–10 Talons.');return True
    elif parts[0] not in ('stand','draw'):
        await c.send('Use CARDS BET, CARDS DRAW, or CARDS STAND.');return True
    # Persist current game earnings before a SQL monetary transaction.
    c.is_dirty=True
    await c.save()
    async with w.db_manager.pool.acquire() as conn:
        async with conn.transaction():
            balance=await conn.fetchval('SELECT coinage FROM characters WHERE id=$1 FOR UPDATE',c.dbid)
            row=await conn.fetchrow('SELECT *, played_at>now()-interval \'30 seconds\' AS recent FROM tavern_hands WHERE character_id=$1 FOR UPDATE',c.dbid)
            if bet is not None:
                if row and (not row['settled'] or row['recent']):
                    await c.send('Finish your saved hand, or wait 30 seconds after starting your last game.');return True
                spent=await conn.fetchval("SELECT coalesce(sum(stake),0) FROM tavern_ledger WHERE character_id=$1 AND created_at>=date_trunc('day',now())",c.dbid)
                if spent+bet>100:
                    await c.send('The tavern limits each adventurer to 100 Talons staked per real UTC day.');return True
                if balance<bet:
                    await c.send('You cannot afford that stake.');return True
                if game=='cards':
                    deck=list(range(52));RNG.shuffle(deck)
                    state={'player':[deck.pop() for _ in range(5)],'dealer':[deck.pop() for _ in range(5)],'deck':deck}
                    payout=0;settled=False;message='Your hand: '+display(state['player'])+'. Draw up to three positions, or stand.'
                else:
                    rolls=[RNG.randint(1,6),RNG.randint(1,6)];payout=bet*3 if sum(rolls) in (7,11) else 0
                    state={};settled=True;message=f'Dice: {rolls[0]} + {rolls[1]} = {sum(rolls)}. Return: {payout} Talons (stake {bet}).'
                await conn.execute('INSERT INTO tavern_hands(character_id,room_id,bet,state,settled) VALUES($1,$2,$3,$4,$5) ON CONFLICT(character_id) DO UPDATE SET room_id=excluded.room_id,bet=excluded.bet,state=excluded.state,settled=excluded.settled,played_at=now()',c.dbid,c.location_id,bet,json.dumps(state),settled)
                balance+=payout-bet
                await conn.execute('INSERT INTO tavern_ledger(character_id,game,stake,payout,details) VALUES($1,$2,$3,$4,$5)',c.dbid,game,bet,payout,'wager' if game=='cards' else message)
            else:
                if not row or row['settled']:
                    await c.send('No unfinished hand. Use CARDS BET <stake>.');return True
                if row['room_id']!=c.location_id:
                    await c.send('Return to the tavern where you placed your stake.');return True
                try:
                    positions=[] if parts==['stand'] else [int(x)-1 for x in ''.join(parts[1:]).split(',')]
                    assert parts[0]=='stand' and len(parts)==1 or parts[0]=='draw' and 1<=len(positions)<=3
                    assert len(set(positions))==len(positions) and all(0<=i<5 for i in positions)
                except (ValueError,AssertionError):
                    await c.send('DRAW 1,3 exchanges unique positions 1–5, up to three. Or STAND.');return True
                state=json.loads(row['state']) if isinstance(row['state'],str) else row['state']
                for i in positions:state['player'][i]=state['deck'].pop()
                state['dealer']=dealer_draw(state['dealer'],state['deck'])
                a,b=score(state['player']),score(state['dealer'])
                payout=row['bet']*(2 if a>b else 1 if a==b else 0)
                balance+=payout
                message=f'You: {display(state["player"])} ({NAMES[a[0]]}). House: {display(state["dealer"])} ({NAMES[b[0]]}). Return: {payout} Talons (stake {row["bet"]}).'
                await conn.execute('UPDATE tavern_hands SET settled=true,state=$1 WHERE character_id=$2',json.dumps(state),c.dbid)
                await conn.execute('INSERT INTO tavern_ledger(character_id,game,stake,payout,details) VALUES($1,\'cards\',0,$2,$3)',c.dbid,payout,message)
            await conn.execute('UPDATE characters SET coinage=$1 WHERE id=$2',balance,c.dbid)
    c.coinage=balance;c.is_dirty=True
    log.info("TAVERN character=%s game=%s balance=%s settled=%s",c.dbid,game,balance,game=="dice" or bet is None)
    await c.send(message)
    if game=='dice' or bet is None:await c.location.broadcast(f'{c.name} finishes a tavern game. {message}',exclude={c})
    return True

async def dice(c,w,args):return await command(c,w,args,'dice')
