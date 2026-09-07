async def available(c,w):
    service=await w.db_manager.fetch_one_query('SELECT * FROM shop_services WHERE room_id=$1',c.location_id)
    if not service:return True
    start,end=service['open_hour'],service['close_hour'];hour=w.game_hour
    opened=start<=hour<end if start<end else hour>=start or hour<end
    keeper=next((m for m in c.location.mobs if m.template_id==service['mob_template_id'] and m.is_alive() and not m.is_fighting),None)
    if not opened or not keeper:
        await c.send(f"The shop is closed or its keeper is unavailable. Hours: {start:02}:00–{end:02}:00.");return False
    return True
