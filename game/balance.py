"""Validated database tuning, loaded on startup and builder publication."""
import json
import config

RULES={
 'xp_level_75_total':('XP_LEVEL_75_TOTAL',100000,100000000),
 'xp_after_75_growth':('XP_AFTER_75_GROWTH',1.01,1.3),
 'xp_absorb_rate':('XP_ABSORB_RATE_PER_SEC',.01,100),
 'technique_base':('TECHNIQUE_BASE',1,100),
 'technique_per_level':('TECHNIQUE_PER_LEVEL',.1,20),
 'technique_signature_cost':('TECHNIQUE_SIGNATURE_COST',1,100),
 'technique_finale_cost':('TECHNIQUE_FINALE_COST',1,100),
 'technique_signature_multiplier':('TECHNIQUE_SIGNATURE_MULTIPLIER',1,5),
 'technique_finale_multiplier':('TECHNIQUE_FINALE_MULTIPLIER',1,10),
 'mob_xp_base':('MOB_XP_BASE',1,10000),
 'mud_roundtime':('MUD_ROUNDTIME',0,30),
 'snow_roundtime':('SNOW_ROUNDTIME',0,30),
 'tether_xp_per_level':('TETHER_XP_PER_LEVEL',1,1000000),
 'tether_xp_per_missing':('TETHER_XP_PER_MISSING',1,1000000),
}

async def load(world):
    rows=await world.db_manager.fetch_all_query('SELECT name,value FROM balance_rules')
    changes={}
    for row in rows:
        if row['name'] in RULES:
            key,low,high=RULES[row['name']];value=float(row['value'])
            if not low<=value<=high:raise ValueError(f'Balance rule {row["name"]} must be between {low} and {high}')
            changes[key]=value
    for key,value in changes.items():setattr(config,key,value)
    from game.adventure import KITS
    for name,definition in KITS.items():
        await world.db_manager.execute_query('INSERT INTO class_kits(name,definition) VALUES($1,$2) ON CONFLICT(name) DO NOTHING',name,json.dumps(definition))
    world.class_kits={r['name']:json.loads(r['definition']) for r in await world.db_manager.fetch_all_query('SELECT name,definition FROM class_kits')}
