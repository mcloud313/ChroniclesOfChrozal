"""Level 1–10 class kits, authored quest objectives, and tactical combat choices."""
import json
import config
import random
from game import utils
from game.mob import Mob

# All classes have a resource-free basic action, a level-3 signature, and a level-7 finisher.
KITS={
 'warrior':('slash','might','sunder',1.0,'A measured cut; sunder exposes armor.'),
 'mage':('spark','intellect','surge',1.15,'Arcane damage; surge trades essence for burst.'),
 'cleric':('smite','aura','rebuke',.95,'Divine damage; rebuke also restores health.'),
 'rogue':('jab','agility','ambush',1.05,'Precise damage; ambush is stronger against wounded foes.'),
 'ranger':('loose','agility','volley',1.05,'A conjured arrow; volley strikes a concentrated burst.'),
 'barbarian':('hew','might','fury',1.2,'Heavy damage; fury risks your own health.'),
 'druid':('thorn','aura','bloom',.95,'Living thorns; bloom restores health.'),
 'bard':('discord','persona','crescendo',1.0,'Sonic damage; crescendo restores a little essence.'),
 'paladin':('judgment','aura','oath',1.0,'Radiant damage; oath reduces the next incoming blow.'),
 'monk':('palm','agility','flurry',1.05,'Unarmed control; flurry delays the next enemy action.'),
 'runewarden':('etch','intellect','aegis',1.0,'Stone runes; aegis wards the next incoming blow.'),
}

async def event(character,world,kind,target):
    rows=await world.db_manager.fetch_all_query("SELECT cq.quest_id,cq.progress,q.objectives FROM character_quests cq JOIN quests q ON q.id=cq.quest_id WHERE character_id=$1 AND status='active'",character.dbid)
    for row in rows:
        progress=json.loads(row['progress']);objectives=json.loads(row['objectives']);changed=False
        for i,obj in enumerate(objectives):
            if obj['kind']==kind and str(obj['target']).lower()==str(target).lower():
                key=str(i);progress[key]=min(obj.get('count',1),progress.get(key,0)+1);changed=True
        if changed:
            await world.db_manager.execute_query('UPDATE character_quests SET progress=$1 WHERE character_id=$2 AND quest_id=$3',json.dumps(progress),character.dbid,row['quest_id'])
            if all(progress.get(str(i),0)>=o.get('count',1) for i,o in enumerate(objectives)):
                await character.send('A chapter is ready to turn in. Return to its giver and use quest complete.')

async def cmd_quest(c,w,args):
    args=args.strip()
    if not args:
        rows=await w.db_manager.fetch_all_query('''SELECT q.*,cq.status,cq.progress FROM quests q LEFT JOIN character_quests cq ON cq.quest_id=q.id AND cq.character_id=$1 ORDER BY q.min_level''',c.dbid)
        lines=['Your chapters (quest accept <number>, quest complete):']
        for r in rows:
            state=r['status'] or ('available' if c.level>=r['min_level'] else 'locked')
            lines.append(f'{r["id"]}. {r["name"]} — level {r["min_level"]} [{state}]\n{r["description"]}')
            progress=json.loads(r['progress'] or '{}')
            for i,o in enumerate(json.loads(r['objectives'])):
                lines.append(f'  {o["label"]}: {progress.get(str(i),0)}/{o.get("count",1)}')
        await c.send('\n'.join(lines));return True
    if args.startswith('accept '):
        try:qid=int(args.split()[-1])
        except ValueError:await c.send('Use quest accept <number>.');return True
        q=await w.db_manager.fetch_one_query('SELECT * FROM quests WHERE id=$1',qid)
        from game.community import has_standing
        if q and not await has_standing(c,w,q):
            await c.send('Your faction standing is too low for this chapter.');return True
        if not q or c.level<q['min_level'] or c.location_id!=q['giver_room_id']:
            await c.send('Meet the required level and visit the quest giver.');return True
        await w.db_manager.execute_query("INSERT INTO character_quests(character_id,quest_id) VALUES($1,$2) ON CONFLICT DO NOTHING",c.dbid,qid)
        await c.send(q['description']);return True
    if args=='complete':
        awarded=False
        reward_xp=0;reward_coins=0
        async with w.db_manager.pool.acquire() as conn:
            async with conn.transaction():
                rows=await conn.fetch("SELECT cq.*,q.objectives,q.reward_xp,q.reward_coinage,q.name,q.faction_id,q.reputation_reward FROM character_quests cq JOIN quests q ON q.id=cq.quest_id WHERE character_id=$1 AND status='active' AND q.giver_room_id=$2 FOR UPDATE OF cq",c.dbid,c.location_id)
                for r in rows:
                    progress=json.loads(r['progress']);objectives=json.loads(r['objectives'])
                    if all(progress.get(str(i),0)>=o.get('count',1) for i,o in enumerate(objectives)):
                        # Reward and completion commit together; repeat submissions cannot duplicate them.
                        await conn.execute("UPDATE character_quests SET status='complete' WHERE character_id=$1 AND quest_id=$2",c.dbid,r['quest_id'])
                        await conn.execute('UPDATE characters SET xp_pool=$1,coinage=$2 WHERE id=$3',c.xp_pool+reward_xp+r['reward_xp'],c.coinage+reward_coins+r['reward_coinage'],c.dbid)
                        await conn.execute('INSERT INTO character_journal(character_id,entry) VALUES($1,$2)',c.dbid,'Completed '+r['name'])
                        if r['faction_id']:
                            await conn.execute('INSERT INTO character_reputation(character_id,faction_id,standing) VALUES($1,$2,$3) ON CONFLICT(character_id,faction_id) DO UPDATE SET standing=character_reputation.standing+EXCLUDED.standing',c.dbid,r['faction_id'],r['reputation_reward'])
                        reward_xp+=r['reward_xp'];reward_coins+=r['reward_coinage'];awarded=True
        c.xp_pool+=reward_xp;c.coinage+=reward_coins
        c.is_dirty=True
        await c.send('Chapter completed. Meditate at a node, then advance when ready.' if awarded else 'No completed chapter can be turned in here.')
        return True
    await c.send('Use quest, quest accept <number>, or quest complete.');return True

async def cmd_technique(c,w,args):
    name=w.get_class_name(c.class_id).lower();kit=getattr(w,"class_kits",KITS).get(name)
    if not kit:await c.send('Choose a class before using techniques.');return True
    basic,stat,signature,multiplier,description=kit
    if not args:
        await c.send(f'{name.title()}: {description}\ntechnique {basic} <enemy> (level 1, no cost)\ntechnique {signature} <enemy> (level 3, 4 essence)\ntechnique finale <enemy> (level 7, 8 essence)\nbrace reduces the next blow; recover at a safe node.');return True
    move,_,target_name=args.partition(' ')
    if move not in (basic,signature,'finale') or (move==signature and c.level<3) or (move=='finale' and c.level<7):
        await c.send('That technique is not available. Type technique for your kit.');return True
    target=c.location.get_mob_by_name(target_name) if target_name else None
    if not target or 'CIVILIAN' in target.flags or not target.is_alive():
        await c.send('Choose a living hostile creature in this room.');return True
    cost=0 if move==basic else config.TECHNIQUE_SIGNATURE_COST if move==signature else config.TECHNIQUE_FINALE_COST
    if c.essence<cost:await c.send('You lack essence. Use your basic technique or retreat and recover.');return True
    if not c.can_see():await c.send('You cannot make out a target in the dark.');return True
    c.essence-=cost
    from game.combat import hit_resolver, damage_calculator
    physical=name in ('warrior','rogue','ranger','barbarian','monk')
    weapon=c._equipped_items.get('main_hand')
    speed=weapon.speed if weapon and physical else 2.5
    c.roundtime=max(1,speed)+(1 if move==signature else 2 if move=='finale' else 0)+c.slow_penalty+c.total_av*.05
    c.is_dirty=True;c.is_fighting=True;c.target=target;target.is_fighting=True;target.target=c
    hit=hit_resolver.check_physical_hit(c,target,use_rar=name=='ranger') if physical else hit_resolver.check_magical_hit(c,target,'Arcane' if name in ('mage','bard','runewarden') else 'Divine')
    roll_text=f'[d20 {hit.roll} + attack {hit.attacker_rating} vs defense {hit.target_dv}; recovery {c.roundtime:.1f}s]'
    if not hit.is_hit:
        await c.send(f'Your {move} misses {target.name}. {roll_text}');return True
    base=config.TECHNIQUE_BASE+c.level*config.TECHNIQUE_PER_LEVEL+utils.calculate_modifier(c.stats.get(stat,10))
    damage=max(1,round(base*multiplier*random.uniform(.85,1.15)))
    if move==signature:
        damage=round(damage*config.TECHNIQUE_SIGNATURE_MULTIPLIER)
        if name=='warrior':target.effects['exposed']={'amount':2,'ends_at':__import__('time').monotonic()+10}
        if name in ('cleric','druid'):c.hp=min(c.max_hp,c.hp+base//2)
        if name=='rogue' and target.hp<target.max_hp/2:damage+=base//2
        if name=='barbarian':c.hp=max(1,c.hp-base//4);damage+=base//3
        if name=='bard':c.essence=min(c.max_essence,c.essence+2)
        if name in ('paladin','runewarden'):c.effects['braced']={'amount':.5,'ends_at':__import__('time').monotonic()+10}
        if name=='monk':target.roundtime=max(target.roundtime,3)
    if move=='finale':damage*=config.TECHNIQUE_FINALE_MULTIPLIER
    if 'exposed' in target.effects:damage+=2
    c.is_dirty=True;c.is_fighting=True;c.target=target
    target.is_fighting=True;target.target=c
    if hit.is_crit:damage=round(damage*1.5)
    info=damage_calculator.DamageInfo(pre_mitigation_damage=damage,damage_type='slash' if physical else 'arcane',is_crit=hit.is_crit)
    damage=damage_calculator.mitigate_damage(target,info) if physical else damage_calculator.mitigate_magical_damage(target,info)
    target.hp=max(0,target.hp-damage)
    await c.send(f'Your {move} hits {target.name} for {damage}. [{round(target.hp)}/{target.max_hp} HP] {roll_text}')
    if target.hp<=0:
        from game.combat.outcome_handler import handle_defeat
        await handle_defeat(c,target,w)
        c.is_fighting=False;c.target=None
    return True

async def cmd_brace(c,w,args):
    import time
    c.effects['braced']={'amount':.5,'ends_at':time.monotonic()+8};c.roundtime=max(c.roundtime,1);c.is_dirty=True
    await c.send('You brace for the next blow.');return True

async def cmd_recover(c,w,args):
    if 'NODE' not in c.location.flags or c.is_fighting:
        await c.send('Recover at a peaceful node, away from combat.');return True
    c.hp=c.max_hp;c.essence=c.max_essence;c.hunger=100;c.thirst=100;c.is_dirty=True;c.roundtime=5
    await c.send('You take a meal and tend your wounds. You feel restored.');return True


async def cmd_treat(c,w,args):
    salve=next((i for i in c._inventory_items.values() if i.name=='coast salve'),None)
    if not salve:
        await c.send('You need a crafted coast salve in your inventory.');return True
    if c.hp>=c.max_hp:
        await c.send('You do not need a salve right now.');return True
    async with w.db_manager.pool.acquire() as conn:
        async with conn.transaction():
            deleted=await conn.fetchval('DELETE FROM item_instances WHERE id=$1 AND owner_char_id=$2 RETURNING id',salve.id,c.dbid)
            if not deleted:return True
            healed=min(c.max_hp,c.hp+30)
            await conn.execute('UPDATE characters SET hp=$1 WHERE id=$2',healed,c.dbid)
    c.hp=healed;c.is_dirty=True;c.roundtime=2
    c._inventory_items.pop(salve.id,None);w._all_item_instances.pop(salve.id,None)
    await c.send('You apply the coast salve, restoring up to 30 hit points.');return True
