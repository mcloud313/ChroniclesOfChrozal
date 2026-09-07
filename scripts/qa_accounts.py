"""Explicit local QA provisioning; no default passwords or automatic accounts."""
import getpass
from game.database import db_manager as db
from game import utils
from game.definitions import classes
from game.appearance import describe

async def provision():
    for name in ('chrozal_admin','chrozal_tester'):
        if await db.fetch_one_query('SELECT id FROM players WHERE username=$1',name):
            raise ValueError('QA accounts already exist; existing passwords and characters retained.')
    passwords=[getpass.getpass(f'Choose password for {name} (12+ characters): ') for name in ('chrozal_admin','chrozal_tester')]
    if any(len(p)<12 for p in passwords):raise ValueError('Both passwords must have 12+ characters')
    ids=[]
    for name,password in zip(('chrozal_admin','chrozal_tester'),passwords):
        ids.append(await db.create_player_account(name,utils.hash_password(password),name+'@example.test'))
    await db.execute_query('UPDATE players SET is_admin=true WHERE id=$1',ids[0])
    rows=await db.fetch_all_query('SELECT id,name FROM classes ORDER BY id')
    for row in rows:
        cid=row['id'];name=row['name'];stats=dict.fromkeys(['might','vitality','agility','intellect','aura','persona'],16)
        hp=30+classes.CLASS_HP_DIE.get(cid,8)+utils.calculate_modifier(16)
        essence=15+classes.CLASS_ESSENCE_DIE.get(cid,6)+2*utils.calculate_modifier(16)
        await db.create_character(ids[1],name,'Playtest','They/Them',1,cid,name,stats,
            describe({'first_name':name,'race_name':'Chrozalin','sex':'They/Them'}),hp,hp,essence,essence,3)
    print(f'Created chrozal_admin (administrator) and chrozal_tester ({len(rows)} level-1 class characters). Passwords are the values you entered.')

async def set_character(args):
    import config
    row=await db.fetch_one_query("SELECT c.* FROM characters c JOIN players p ON p.id=c.player_id JOIN classes cl ON cl.id=c.class_id WHERE p.username='chrozal_tester' AND lower(cl.name)=lower($1)",args.class_name)
    if not row:raise ValueError('Run qa-accounts first and choose an existing test class.')
    if await db.fetch_one_query('SELECT 1 FROM web_sessions WHERE player_id=$1 AND expires_at>now()',row['player_id']):
        raise ValueError('Sign out of the testing account before changing its fixtures.')
    level=args.level or row['level']
    if not 1<=level<=config.MAX_LEVEL:raise ValueError('Level must be 1–99')
    tether=args.tether if args.tether is not None else row['spiritual_tether']
    if not 0<=tether<=10:raise ValueError('Tether must be 0–10')
    hp=30+level*(classes.CLASS_HP_DIE.get(row['class_id'],8)//2+2)
    essence=15+level*(classes.CLASS_ESSENCE_DIE.get(row['class_id'],6)//2+2)
    xp=utils.xp_needed_for_level(level-1) if level>1 else 0
    if args.surplus_xp<0 or args.coins<0:raise ValueError('Use nonnegative XP/coins')
    await db.execute_query('UPDATE characters SET level=$1,xp_total=$2,xp_pool=0,spiritual_tether=$3,hp=$4,max_hp=$5,essence=$6,max_essence=$6,coinage=$7,status=$8,location_id=1,runtime_state=\'{}\' WHERE id=$9',level,xp+args.surplus_xp,tether,0 if args.dead else hp,hp,essence,args.coins,'DEAD' if args.dead else 'ALIVE',row['id'])
    print(f'{args.class_name} testing fixture updated. This command only changes chrozal_tester characters.')
