"""Stable right/left labels for held instances; equipment also consumes hands."""
def occupied(c):
    slots=set()
    if c._equipped_items.get('main_hand'):slots.add('right')
    if c._equipped_items.get('off_hand'):slots.add('left')
    if c.is_wielding_two_handed:slots.update(('right','left'))
    for item in c._inventory_items.values():
        hand=item.instance_stats.get('held_hand')
        if hand=='both':slots.update(('right','left'))
        elif hand in ('right','left'):slots.add(hand)
    return slots


def assign(c):
    used=set()
    if c._equipped_items.get('main_hand'):used.add('right')
    if c._equipped_items.get('off_hand'):used.add('left')
    if c.is_wielding_two_handed:used.update(('right','left'))
    for item in c._inventory_items.values():
        hand=item.instance_stats.get('held_hand')
        if hand=='both' and not used:used.update(('right','left'));continue
        if hand not in ('right','left') or hand in used:hand=next((h for h in ('right','left') if h not in used),None)
        if hand:used.add(hand);item.instance_stats['held_hand']=hand
    return used

async def command(c,w,args):
    if ' in ' not in args:
        assign(c)
        await c.send('\n'.join(f"{i.instance_stats.get('held_hand','unplaced').title()} hand: {i.name}" for i in c._inventory_items.values()) or 'Your hands hold no loose items.')
        return True
    name,hand=args.rsplit(' in ',1);hand=hand.replace(' hands','').replace(' hand','').strip().lower()
    item=c.find_item_in_inventory_by_name(name)
    if not item or hand not in ('right','left','both'):
        await c.send('hold <held item> in left / right / both');return True
    others=[i for i in c._inventory_items.values() if i!=item]
    blocked=set()
    if c._equipped_items.get('main_hand'):blocked.add('right')
    if c._equipped_items.get('off_hand'):blocked.add('left')
    if c.is_wielding_two_handed:blocked.update(('left','right'))
    for i in others:blocked.update(('left','right') if i.instance_stats.get('held_hand')=='both' else [i.instance_stats.get('held_hand')])
    if hand in blocked or hand=='both' and blocked:
        await c.send('That hand is occupied. Put the other item away first.');return True
    item.instance_stats['held_hand']=hand;c.is_dirty=True
    await w.db_manager.update_item_instance_stats(item.id,item.instance_stats)
    await c.send(f'You hold {item.name} in your {hand} hand(s).');return True
