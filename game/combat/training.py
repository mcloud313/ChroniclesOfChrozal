"""One definition of weapon training shared by hit and damage calculations."""
def weapon_rank(c,weapon=None):
    weapon=weapon if weapon is not None else c._equipped_items.get('main_hand')
    if not weapon:return c.get_skill_rank('martial arts')
    if weapon.item_type=='RANGED_WEAPON':return c.get_skill_rank('projectile weapons')
    if weapon.damage_type=='pierce':return max(c.get_skill_rank('piercing weapons'),c.get_skill_rank('bladed weapons'))
    return c.get_skill_rank('bludgeon weapons' if weapon.damage_type=='bludgeon' else 'bladed weapons')
