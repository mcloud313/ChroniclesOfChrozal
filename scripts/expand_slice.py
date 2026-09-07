"""Add the 100-room QA slice once; never replace existing rooms or reset state."""
import json

REGIONS=[
 ('Reedwater March','coastal',4,'Flooded reed beds hide broken causeways and the remains of old tide shrines.','reed prowler'),
 ('Oldwood Verge','temperate',8,'Ancient trees clasp abandoned boundary stones. Wind carries a distant wooden chime.','briar shade'),
 ('Deep-Vein Foothills','temperate',11,'Ore seams glint in steep slate walls. Abandoned mine tracks lead toward forgotten halls.','slate guardian'),
 ('Ashen Pilgrim Road','arid',14,'Ash settles on carved pilgrim stones beneath an immense open sky.','cinder revenant'),
 ('Celestrian Reach','arctic',17,'Frost traces the names of vanished astronomers across silver-veined ruins.','starbound sentinel')]
LANDMARKS=['Refuge','Trailhead','Watchpost','Hollow','Causeway','Stone Ring','Crossroads','Old Well','Shelter','Boundary','Shrine','Overlook','Ruined Gate','Lower Hall','Echo Chamber','Sanctum','Far Beacon']

async def expand(conn):
    await conn.execute("CREATE TABLE IF NOT EXISTS content_packs(name TEXT PRIMARY KEY,installed_at TIMESTAMPTZ DEFAULT now())")
    await conn.execute('SELECT pg_advisory_xact_lock(819420)')
    if await conn.fetchval("SELECT 1 FROM content_packs WHERE name='qa20-v1'"):return
    plaza=await conn.fetchval("SELECT id FROM rooms WHERE name='Wayfinder''s Plaza'")
    if not plaza:raise ValueError('Install the starter world first; this pack extends Port Valis.')
    await conn.execute('INSERT INTO notice_boards(room_id) VALUES($1) ON CONFLICT DO NOTHING',plaza)
    origin=plaza
    for region,climate,base,flavor,enemy in REGIONS:
        area=await conn.fetchval('INSERT INTO areas(name,description,climate) VALUES($1,$2,$3) RETURNING id',region,flavor,climate)
        room_ids=[]
        for i,landmark in enumerate(LANDMARKS):
            flags=['OUTDOORS'] if i<13 else ['LIT']
            if i in (0,8,16):flags+=['NODE','SAFE_ZONE','LIT']
            if climate=='arctic':flags+=['SNOWY']
            if region=='Reedwater March' and i not in (0,8,16):flags+=['MUD']
            rid=await conn.fetchval('INSERT INTO rooms(area_id,name,description,flags,map_x,map_y) VALUES($1,$2,$3,$4,$5,$6) RETURNING id',area,region+' — '+landmark,flavor+' '+(['A sheltered hearth invites travelers to eat, rest, and share news.' if i in (0,8,16) else f'The {landmark.lower()} offers shelter and sightlines, but tracks warn of danger nearby.'][0]),json.dumps(flags),100+(i%5)*210,70+(i//5)*180)
            room_ids.append(rid)
            if i:
                for src,dst,d in [(room_ids[i-1],rid,'e'),(rid,room_ids[i-1],'w')]:
                    await conn.execute('INSERT INTO exits(source_room_id,destination_room_id,direction) VALUES($1,$2,$3)',src,dst,d)
            if i not in (0,8,16):
                level=min(20,base+i//5)
                template=await conn.fetchval('INSERT INTO mob_templates(name,description,level,max_hp,stats,flags,respawn_delay_seconds,max_coinage) VALUES($1,$2,$3,$4,$5,$6,90,$7) RETURNING id',f'{enemy} {landmark.lower()}',f'A level {level} danger of {region}. It draws back before committing to a heavy strike.',level,24+level*9,json.dumps(dict.fromkeys(['might','vitality','agility','intellect','aura','persona'],10+level)),json.dumps(['TELEGRAPH','INFRAVISION']),level*5)
                await conn.execute('INSERT INTO mob_attacks(mob_template_id,name,damage_base,damage_rng,speed) VALUES($1,$2,$3,3,3)',template,'warning strike',2+level)
                await conn.execute('UPDATE rooms SET spawners=$1 WHERE id=$2',json.dumps({str(template):{'max_present':1}}),rid)
        for src,dst,d in [(origin,room_ids[0],region.lower()),(room_ids[0],origin,'return')]:
            await conn.execute('INSERT INTO exits(source_room_id,destination_room_id,direction) VALUES($1,$2,$3)',src,dst,d)
        await conn.execute('INSERT INTO notice_boards(room_id,name) VALUES($1,$2)',room_ids[0],region+' Notice Board')
        for i in range(10):
            target=1+i
            objectives=[{'kind':'visit','target':room_ids[target],'label':'Survey '+LANDMARKS[target],'count':1},{'kind':'kill','target':f'{enemy} {LANDMARKS[target].lower()}','label':'Clear the nearby danger','count':2}]
            if target==8:objectives=objectives[:1]
            await conn.execute('INSERT INTO quests(name,description,min_level,giver_room_id,objectives,reward_xp,reward_coinage) VALUES($1,$2,$3,$4,$5,$6,$7)',region+': '+LANDMARKS[target],flavor,min(20,base+i//4),room_ids[0],json.dumps(objectives),500+base*120,base*10)
        if region in ('Reedwater March','Deep-Vein Foothills'):
            path='ford rapids' if region=='Reedwater March' else 'climb rockwall'
            check={'skill':'swimming' if region=='Reedwater March' else 'climbing','dc':16,'fail_damage':8,'fail_msg':'You lose your footing and fall.'}
            await conn.execute('INSERT INTO exits(source_room_id,destination_room_id,direction,details) VALUES($1,$2,$3,$4)',room_ids[2],room_ids[6],path,json.dumps({'skill_check':check}))
        origin=room_ids[16]
    # Useful affordable supplies, with one instance per purchased item.
    tavern=await conn.fetchval("SELECT id FROM rooms WHERE name='The Lantern & Tide'")
    await conn.execute("UPDATE rooms SET flags=flags || '[\"SHOP\",\"LIT\"]'::jsonb WHERE id=$1",tavern)
    for name,kind,stats in [('travel ration','FOOD',{'weight':1,'value':2,'effect':'restore_hunger','amount':50}),('spring water','DRINK',{'weight':1,'value':1,'effect':'restore_thirst','amount':50}),('traveler pack','CONTAINER',{'weight':1,'value':10,'capacity':100,'wear_location':'back'}),('coast bow','RANGED_WEAPON',{'weight':2,'value':45,'speed':3,'damage_base':8,'damage_rng':4,'uses_ammo_type':'arrow'}),('coast quiver','QUIVER',{'weight':1,'value':10,'capacity':30,'wear_location':'waist','holds_ammo_type':'arrow'}),('arrow bundle','AMMO',{'weight':1,'value':3,'ammo_type':'arrow','quantity':20})]:
        tid=await conn.fetchval('INSERT INTO item_templates(name,type,stats,description) VALUES($1,$2,$3,$4) RETURNING id',name,kind,json.dumps(stats),'Practical supplies for journeys along the Valian Coast.')
        await conn.execute('INSERT INTO shop_inventories(room_id,item_template_id,stock_quantity,buy_price_modifier) VALUES($1,$2,-1,1)',tavern,tid)
    chest_template=await conn.fetchval("INSERT INTO item_templates(name,type,stats,description) VALUES('weathered lockbox','CONTAINER','{\"capacity\":50,\"weight\":15}','A tarnished lock and a fine wire protect this old box.') RETURNING id")
    await conn.execute('INSERT INTO item_instances(template_id,room_id,instance_stats) VALUES($1,$2,$3)',chest_template,plaza,json.dumps({'is_open':False,'is_locked':True,'lockpick_dc':16,'trap':{'is_active':True,'damage':7,'perception_dc':12,'disarm_dc':14}}))
    for shop_name,keeper_name in [('The Lantern & Tide','Nessa the innkeeper'),('The Tideforge','Orun the smith')]:
        room=await conn.fetchval('SELECT id FROM rooms WHERE name=$1',shop_name)
        keeper=await conn.fetchval("INSERT INTO mob_templates(name,description,level,max_hp,flags) VALUES($1,'An experienced local artisan who keeps regular working hours.',20,300,'[\"CIVILIAN\",\"INFRAVISION\"]') RETURNING id",keeper_name)
        await conn.execute('INSERT INTO npc_schedules(mob_template_id,day_room_id,night_room_id,greeting,lore) VALUES($1,$2,$3,$4,$5)',keeper,room,plaza,'Welcome. Browse my wares while I am at work.','I open at dawn and close at dusk.')
        await conn.execute('INSERT INTO shop_services(room_id,mob_template_id) VALUES($1,$2)',room,keeper)
    await conn.execute("INSERT INTO content_packs(name) VALUES('qa20-v1')")
    print('Added 85 rooms, five areas and five notice boards; existing rooms and characters retained.')
