"""Class kits, notice objectives, and tactical combat choices."""
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
 'tempest':('gust','aura','thunderhead',1.05,'A storm caller; thunderhead slows an enemy with thunder.'),
}

async def event(character,world,kind,target):
    from game.notices import event as notice_event
    await notice_event(character,world,kind,target)

async def cmd_technique(c,w,args):
    name=w.get_class_name(c.class_id).lower();kit=getattr(w,"class_kits",KITS).get(name)
    if not kit:await c.send('Choose a class before using techniques.');return True
    basic,stat,signature,multiplier,description=kit
    if not args:
        await c.send(f'{name.title()}: {description}\ntechnique {basic} <enemy> (level 1, no cost)\ntechnique {signature} <enemy> (level 3, 4 essence)\ntechnique finale <enemy> (level 7, 8 essence)\nEat, drink, and rest at a safe node.');return True
    move,_,target_name=args.partition(' ')
    if move not in (basic,signature,'finale') or (move==signature and c.level<3) or (move=='finale' and c.level<7):
        await c.send('That technique is not available. Type technique for your kit.');return True
    target=c.location.get_mob_by_name(target_name) if target_name else None
    if not target or 'CIVILIAN' in target.flags or not target.is_alive():
        await c.send('Choose a living hostile creature in this room.');return True
    cost=0 if move==basic else config.TECHNIQUE_SIGNATURE_COST if move==signature else config.TECHNIQUE_FINALE_COST
    if c.essence<cost:await c.send('You lack essence. Use your basic technique or retreat and recover.');return True
    if not c.can_see():await c.send('You cannot make out a target in the dark.');return True
    ambushing=c.is_hidden and name=='rogue' and move==signature
    if c.is_hidden:
        c.is_hidden=False
        await c.send('You leave concealment to strike.')
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
        await c.location.broadcast(f'<r>{c.name} misses {target.name} with {move}. {roll_text}')
        __import__('logging').getLogger(__name__).info('COMBAT technique miss character=%s target=%s %s',c.dbid,target.name,roll_text)
        return True
    base=config.TECHNIQUE_BASE+c.level*config.TECHNIQUE_PER_LEVEL+utils.calculate_modifier(c.stats.get(stat,10))
    damage=max(1,round(base*multiplier*random.uniform(.85,1.15)))
    if ambushing:damage=round(damage*1.5)
    if move==signature:
        damage=round(damage*config.TECHNIQUE_SIGNATURE_MULTIPLIER)
        if name=='warrior':target.effects['exposed']={'amount':2,'ends_at':__import__('time').monotonic()+10}
        if name in ('cleric','druid'):c.hp=min(c.max_hp,c.hp+base//2)
        if name=='rogue' and target.hp<target.max_hp/2:damage+=base//2
        if name=='barbarian':c.hp=max(1,c.hp-base//4);damage+=base//3
        if name=='bard':c.essence=min(c.max_essence,c.essence+2)
        if name in ('paladin','runewarden'):c.effects['signature_ward']={'stat_affected':'barrier_value','amount':5+c.level//4,'ends_at':__import__('time').monotonic()+20}
        if name in ('monk','tempest'):target.roundtime=max(target.roundtime,3)
    if move=='finale':damage*=config.TECHNIQUE_FINALE_MULTIPLIER
    if 'exposed' in target.effects:damage+=2
    c.is_dirty=True;c.is_fighting=True;c.target=target
    target.is_fighting=True;target.target=c
    if hit.is_crit:damage=round(damage*1.5)
    info=damage_calculator.DamageInfo(pre_mitigation_damage=damage,damage_type='slash' if physical else 'arcane',is_crit=hit.is_crit)
    damage=damage_calculator.mitigate_damage(target,info) if physical else damage_calculator.mitigate_magical_damage(target,info)
    target.hp=max(0,target.hp-damage)
    from game.combat import outcome_handler
    info.attack_name=move
    if physical:await outcome_handler.send_attack_messages(c,target,hit,info,damage)
    else:await outcome_handler.send_magical_attack_messages(c,target,hit,info,damage)
    if target.hp<=0:
        from game.combat.outcome_handler import handle_defeat
        await handle_defeat(c,target,w)
        c.is_fighting=False;c.target=None
    return True

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
