"""Published lore is edited through the administrator's lore articles panel."""
async def command(c,w,args):
    from game.definitions.races import format_racial_modifiers
    query=args.strip().lower()
    rows=await w.db_manager.fetch_all_query('SELECT topic,title,body,category FROM lore_articles WHERE published AND (lower(topic)=$1 OR lower(category)=$1 OR $1=\'\') ORDER BY category,topic LIMIT 100',query)
    if len(rows)==1 and rows[0]['topic']==query:
        row=rows[0];message=f"{row['title']}\n{row['body']}"
        if row['category']=='races':message+='\n'+format_racial_modifiers(query)
    else:message='Lore topics (lore <topic>):\n'+'\n'.join(f"{r['topic']} — {r['title']}" for r in rows)
    await c.send(message if rows else 'No published topic matches. Try lore, lore races, or lore classes.')
    return True
