"""Authored level 1–10 content pack. Called inside the fresh starter seed transaction."""
import json

async def seed_arc(c):
    plaza=await c.fetchval("SELECT id FROM rooms WHERE name=$1","Wayfinder's Plaza")
    road=await c.fetchval("SELECT id FROM rooms WHERE name='Serpent Road'")
    region=await c.fetchval('SELECT area_id FROM rooms WHERE id=$1',plaza)
    rooms=[]
    names=['Lantern Fields','Reedwater Crossing','The Whispering Copse','Iron Claw Outpost','Pilgrim\'s Ascent','Deep-Vein Gate','Hall of Broken Oaths','The Sunken Nave','Celestria\'s Starwell']
    descriptions=[
      'Lanterns guide coastal travelers past wind-bent barley. Scavengers nose through abandoned packs.',
      'Reeds conceal a shallow crossing. Watch a foe\'s wind-up and brace before its heavy strike.',
      'Old trees whisper fragments of the Song of Shaping. Pale wisps gather where the path bends.',
      'The Iron Claw has left scouts near an abandoned signal tower. Grishnak\'s banner snaps in the wind.',
      'Stone pilgrims line the ascent toward the Serpent\'s Tooth. Their guardians still remember their duty.',
      'Cold mine rails disappear beneath the mountain. The miners speak of Ignisyl stirring far below.',
      'A broken oath is carved into every pillar. Echoes of those who served Malakor stalk this hall.',
      'Saltwater pools beneath a celestial mural. Vex Miramar\'s shadow has touched this place.',
      'A shaft of starlight pierces the ruin. The surviving star-ring remembers Celestria. Your first great journey ends here.'
    ]
    previous=road
    for name,desc in zip(names,descriptions):
        rid=await c.fetchval('INSERT INTO rooms(area_id,name,description,flags) VALUES($1,$2,$3,$4) RETURNING id',region,name,desc,json.dumps(['LIT']))
        rooms.append(rid)
        for src,dst,direction in [(previous,rid,'e'),(rid,previous,'w')]:
            await c.execute('INSERT INTO exits(source_room_id,destination_room_id,direction) VALUES($1,$2,$3)',src,dst,direction)
        previous=rid
    enemies=['tide scavenger','marsh stalker','echo wisp','ironclaw scout','stone sentinel','mine shade','oathbreaker echo','starwarden']
    for index,name in enumerate(enemies):
        level=index+2
        template=await c.fetchval('''INSERT INTO mob_templates(name,description,level,max_hp,stats,flags,respawn_delay_seconds,max_coinage)
            VALUES($1,$2,$3,$4,$5,$6,45,$7) RETURNING id''',name,'A guardian of the Valian Coast. Watch its posture before committing to a heavy technique.',level,24+level*9,json.dumps(dict.fromkeys(['might','vitality','agility','intellect','aura','persona'],10+level)),json.dumps(['TELEGRAPH','INFRAVISION']),level*4)
        await c.execute('INSERT INTO mob_attacks(mob_template_id,name,damage_base,damage_rng,speed) VALUES($1,$2,$3,2,3)',template,'measured blow',2+level)
        await c.execute('UPDATE rooms SET spawners=$1 WHERE id=$2',json.dumps({str(template):{'max_present':2 if index<7 else 1}}),rooms[index])
    def objective(kind,target,label,count=1):return {'kind':kind,'target':target,'label':label,'count':count}
    plots=[
      ('A Place at the Fire','Mira welcomes new travelers. Speak with her, gather two silverleaf south of the plaza, and visit Lantern Fields east of Serpent Road.',[objective('talk','Mira the Wayfinder','Speak with Mira'),objective('gather','silverleaf','Gather silverleaf',2),objective('visit',rooms[0],'Visit Lantern Fields')]),
      ('The First Remedy','Craft coast salve at the Tideforge and drive two tide scavengers from Lantern Fields.',[objective('craft','coast salve','Craft coast salve'),objective('kill',enemies[0],'Defeat tide scavengers',2)]),
      ('A Crossing Remembered','Defeat two marsh stalkers at Reedwater Crossing and scout the Whispering Copse beyond.',[objective('kill',enemies[1],'Defeat marsh stalkers',2),objective('visit',rooms[2],'Visit the Whispering Copse')]),
      ('Songs in the Leaves','Defeat two echo wisps in the copse. Craft a wayfarer charm from two iron fragments at the Tideforge.',[objective('kill',enemies[2],'Defeat echo wisps',2),objective('craft','wayfarer charm','Craft wayfarer charm')]),
      ('The Iron Claw Signal','Defeat two ironclaw scouts at the outpost and explore Pilgrim\'s Ascent.',[objective('kill',enemies[3],'Defeat ironclaw scouts',2),objective('visit',rooms[4],'Explore Pilgrim\'s Ascent')]),
      ('The Mountain Listens','Defeat two stone sentinels on the ascent. Bring news of the mountain to Mira.',[objective('kill',enemies[4],'Defeat stone sentinels',2),objective('talk','Mira the Wayfinder','Report to Mira')]),
      ('Beneath the Deep-Vein','Defeat two mine shades at Deep-Vein Gate and enter the Hall of Broken Oaths.',[objective('kill',enemies[5],'Defeat mine shades',2),objective('visit',rooms[6],'Explore the Hall of Broken Oaths')]),
      ('An Oath Reforged','Defeat two oathbreaker echoes and survey the Sunken Nave.',[objective('kill',enemies[6],'Defeat oathbreaker echoes',2),objective('visit',rooms[7],'Survey the Sunken Nave')]),
      ('The Starwell Answers','Defeat the starwarden in the Sunken Nave, reach Celestria\'s Starwell, and return to Mira. A larger threat remains beyond the coast.',[objective('kill',enemies[7],'Defeat the starwarden'),objective('visit',rooms[8],'Reach Celestria\'s Starwell'),objective('talk','Mira the Wayfinder','Share your discovery with Mira')])
    ]
    thresholds=[0,150,400,800,1400,2200,3300,4700,6500,9000]
    for i,(name,description,objectives) in enumerate(plots):
        reward=thresholds[i+1]-thresholds[i]+100
        await c.execute('INSERT INTO quests(name,description,min_level,giver_room_id,objectives,reward_xp,reward_coinage) VALUES($1,$2,$3,$4,$5,$6,$7)',name,description,i+1,plaza,json.dumps(objectives),reward,25*(i+1))
    # Light the entry route so all races/classes can play at any hour.
    await c.execute("UPDATE rooms SET flags=(flags || '[\"LIT\",\"SAFE_ZONE\"]'::jsonb) WHERE id=ANY($1::int[])",[plaza,road])
    await c.execute("UPDATE mob_templates SET flags='[\"CIVILIAN\",\"INFRAVISION\"]' WHERE name='Mira the Wayfinder'")
