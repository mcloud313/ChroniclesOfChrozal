"""Offline maintenance commands. Run from the repository root."""
import argparse
import asyncio
import getpass
import json
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from game.database import db_manager
from game import utils

async def main(args):
    await db_manager.connect()
    try:
        await db_manager.init_db()
        from web.app import migrate
        await migrate()
        if args.command=='init':
            result=await db_manager.bootstrap_admin()
            if result:print('Initial administrator username: admin\nInitial password: '+result+'\nChange required before playing or administration. Store this password securely; it is printed only once.')
        if args.command=='account':
            password=getpass.getpass('Password (12+ characters): ')
            if len(password)<12:
                raise ValueError('Password must be at least 12 characters')
            account=await db_manager.create_player_account(args.username,utils.hash_password(password),args.email)
            if not account:
                raise ValueError('Username or email already exists')
            if args.admin:
                await db_manager.execute_query('UPDATE players SET is_admin=true WHERE id=$1',account)
            print('Account created.')
        elif args.command=='recovery-code':
            from web.recovery import issue
            player=await db_manager.load_player_account(args.username)
            if not player:raise ValueError('Unknown account')
            print('Single-use recovery code (30 minutes): '+await issue(player['id'],'reset'))
        elif args.command=='qa-set':
            from scripts.qa_accounts import set_character
            await set_character(args)
        elif args.command=='qa-add-missing':
            from scripts.qa_accounts import add_missing
            await add_missing()
        elif args.command=='qa-accounts':
            from scripts.qa_accounts import provision
            await provision()
        elif args.command=='expand-slice':
            from scripts.expand_slice import expand
            async with db_manager.pool.acquire() as conn:
                async with conn.transaction():await expand(conn)
        elif args.command=='seed':
            await seed()
        elif args.command=='disable-legacy-accounts':
            # Explicit operator action; do not silently alter an existing host's accounts.
            await db_manager.execute_query("DELETE FROM web_sessions WHERE player_id IN (SELECT id FROM players WHERE username IN ('admin','tester'))")
            for name in ('admin','tester'):
                import secrets
                await db_manager.execute_query('UPDATE players SET hashed_password=$1,is_admin=false WHERE username=$2',utils.hash_password(secrets.token_urlsafe(48)),name)
            print('Legacy admin/tester passwords randomized and administrator flags removed.')
    finally:
        await db_manager.close()

async def seed():
    """Seed only a fresh Void world. Never overwrite an existing authored world."""
    async with db_manager.pool.acquire() as c:
        async with c.transaction():
            count=await c.fetchval('SELECT count(*) FROM rooms')
            name=await c.fetchval('SELECT name FROM rooms WHERE id=1')
            if count!=1 or name!='The Void':
                raise ValueError('Starter seed requires a fresh Void-only database; existing world retained')
            await c.execute("UPDATE areas SET name='The Valian Coast',description='Port Valis and the shores beyond.' WHERE id=1")
            rooms=[(1,"Wayfinder's Plaza","A worn shrine to Orian stands beneath salt-stained banners. Travelers share a fire at the fountain. This is a node: meditate here to absorb experience.",['NODE','RESPAWN','OUTDOORS']),
                (2,'The Lantern & Tide','A warm tavern smells of bread and cedar smoke. An empty chair waits beside every story.', ['NODE','BANK']),
                (3,'Saltwind Strand','Grey-green waves wash the shore. Silverleaf grows between stones. Try gather silverleaf.', ['OUTDOORS']),
                (4,'The Tideforge','A communal workbench stands beside a dwarven forge. Craft coast salve here with two silverleaf, or a wayfarer charm with two iron fragments.', []),
                (5,'Serpent Road','An old road climbs toward the Serpent\'s Tooth Mountains. Iron fragments lie among the scree. Try gather iron fragments.', ['OUTDOORS']),
                (6,'The Broken Observatory','Broken star-rings encircle an altar of Celestria. A quiet Echo answers the patient. The dormant star-rings hint at mysteries reserved for much more experienced adventurers.', [])]
            for rid,name,desc,flags in rooms:
                await c.execute('INSERT INTO rooms(id,area_id,name,description,flags) VALUES($1,1,$2,$3,$4) ON CONFLICT(id) DO UPDATE SET name=EXCLUDED.name,description=EXCLUDED.description,flags=EXCLUDED.flags',rid,name,desc,json.dumps(flags))
            for src,dst,d,back in [(1,2,'w','e'),(1,3,'s','n'),(1,4,'e','w'),(1,5,'n','s'),(5,6,'n','s')]:
                for a,b,direction in [(src,dst,d),(dst,src,back)]:
                    await c.execute('INSERT INTO exits(source_room_id,destination_room_id,direction) VALUES($1,$2,$3)',a,b,direction)
            items={}
            for name,kind,stats,description in [('silverleaf','misc',{'weight':0.1},'A fragrant medicinal leaf.'),('iron fragment','misc',{'weight':0.5},'Weathered iron from an old road.'),('coast salve','misc',{'weight':0.2},'A locally crafted salve. Use treat to restore up to 30 HP.'),('wayfarer charm','misc',{'weight':0.2},'An iron keepsake bearing Orian\'s mark.'),('starmap fragment','misc',{'weight':0.1},'A single fragment of Celestria\'s ancient Starmaps; its power is dormant.')]:
                items[name]=await c.fetchval('INSERT INTO item_templates(name,type,stats,description) VALUES($1,$2,$3,$4) RETURNING id',name,kind,json.dumps(stats),description)
            for room,name,template in [(3,'silverleaf','silverleaf'),(5,'iron fragments','iron fragment')]:
                await c.execute('INSERT INTO resource_nodes(room_id,name,item_template_id) VALUES($1,$2,$3)',room,name,items[template])
            for name,ingredient in [('coast salve','silverleaf'),('wayfarer charm','iron fragment')]:
                await c.execute('INSERT INTO recipes(name,description,station_room_id,output_template_id,ingredients) VALUES($1,$2,4,$3,$4)',name,f'Requires 2 {ingredient}; station: The Tideforge.',items[name],json.dumps({str(items[ingredient]):2}))
            npc=await c.fetchval("INSERT INTO mob_templates(name,description,level,max_hp,flags) VALUES('Mira the Wayfinder','A cartographer with ink-stained hands and a weathered journal.',5,100,$1) RETURNING id",json.dumps(['PACIFIST']))
            await c.execute('INSERT INTO npc_schedules(mob_template_id,day_room_id,night_room_id,greeting,lore) VALUES($1,1,2,$2,$3)',npc,'The coast has room for another story. What will yours be?','Gather silverleaf to the south and craft at the Tideforge. North, beyond Serpent Road, a lost starmap waits in the observatory. I rest in the tavern after dusk.')
            await c.execute('INSERT INTO relics(name,lore,room_id,template_id) VALUES($1,$2,6,$3)','starmap fragment','A surviving piece of the Starmaps of Celestria. Its discovery is unique to this world; the rest of the map remains lost.',items['starmap fragment'])
            await c.execute("INSERT INTO ambient_scripts(area_id,script_text) VALUES(1,'A distant harbor bell carries across the Valian Coast.')")
            # Explicit-ID legacy seeds must not leave SERIAL sequences behind.
            for table in ('areas','rooms','races','classes'):
                await c.execute(f"SELECT setval(pg_get_serial_sequence('{table}','id'),GREATEST((SELECT max(id) FROM {table}),1))")
            from scripts.seed_arc import seed_arc
            await seed_arc(c)
            await c.execute("INSERT INTO item_templates(name,type,stats,description) VALUES('saltwind hide','OTHER','{\"value\":12,\"weight\":1}','A cured strip of coastal hide.')")
            await c.execute("UPDATE mob_templates SET flags=flags || '[\"SKINNABLE\"]'::jsonb WHERE name IN ('tide scavenger','marsh stalker')")
            await c.execute("UPDATE rooms SET flags=flags || '[\"SHOP\"]'::jsonb,shop_buy_filter='{\"types\":[\"WEAPON\",\"ARMOR\",\"OTHER\"]}',shop_sell_modifier=.4 WHERE id=4")
            for name,kind,stats in [('wayfarer dagger','WEAPON',{'speed':1.5,'damage_base':5,'damage_rng':3,'damage_type':'pierce','value':50,'weight':1}),('coast greatsword','TWO_HANDED_WEAPON',{'speed':4.5,'damage_base':13,'damage_rng':5,'damage_type':'slash','value':150,'weight':5})]:
                template=await c.fetchval('INSERT INTO item_templates(name,type,stats,description) VALUES($1,$2,$3,$4) RETURNING id',name,kind,json.dumps(stats),'A practical weapon forged for coastal travel.')
                await c.execute('UPDATE item_templates SET damage_type=$1 WHERE id=$2',stats['damage_type'],template)
                await c.execute('INSERT INTO shop_inventories(room_id,item_template_id,stock_quantity,buy_price_modifier) VALUES(4,$1,20,1.2)',template)
            faction=await c.fetchval("INSERT INTO factions(name,description) VALUES('Valian Wayfinders','The coast’s guides, rescuers and keepers of shared roads.') RETURNING id")
            await c.execute('UPDATE quests SET faction_id=$1,reputation_reward=10',faction)
            await c.execute('UPDATE quests SET required_standing=10 WHERE min_level>1')
            await c.execute('SELECT chrozal_professions_setup()')
            await c.execute('INSERT INTO notice_boards(room_id) VALUES(1) ON CONFLICT DO NOTHING')
            print('Seeded Port Valis: 15 rooms and opening notice-board templates. Use expand-slice for the 100-room world.')

if __name__=='__main__':
    parser=argparse.ArgumentParser();sub=parser.add_subparsers(dest='command',required=True)
    account=sub.add_parser('account');account.add_argument('username');account.add_argument('email');account.add_argument('--admin',action='store_true')
    recovery=sub.add_parser('recovery-code');recovery.add_argument('username')
    qa=sub.add_parser('qa-set');qa.add_argument('class_name');qa.add_argument('--level',type=int);qa.add_argument('--tether',type=int);qa.add_argument('--coins',type=int,default=10000);qa.add_argument('--surplus-xp',type=int,default=0);qa.add_argument('--dead',action='store_true')
    sub.add_parser('qa-add-missing');sub.add_parser('expand-slice');sub.add_parser('qa-accounts');sub.add_parser('seed');sub.add_parser('init');sub.add_parser('disable-legacy-accounts')
    asyncio.run(main(parser.parse_args()))
