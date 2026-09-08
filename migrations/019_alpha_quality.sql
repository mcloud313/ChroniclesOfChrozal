ALTER TABLE players ADD COLUMN IF NOT EXISTS must_change_password BOOLEAN NOT NULL DEFAULT false;
CREATE TABLE IF NOT EXISTS lore_articles (
 id SERIAL PRIMARY KEY, topic TEXT NOT NULL UNIQUE, category TEXT NOT NULL DEFAULT 'world',
 title TEXT NOT NULL, body TEXT NOT NULL, published BOOLEAN NOT NULL DEFAULT true,
 updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO lore_articles(topic,category,title,body)
 SELECT lower(name),'races',name,description FROM races ON CONFLICT(topic) DO NOTHING;
INSERT INTO lore_articles(topic,category,title,body)
 SELECT lower(name),'classes',name,description FROM classes ON CONFLICT(topic) DO NOTHING;
INSERT INTO item_templates(name,type,description,stats) VALUES
 ('traveler backpack','CONTAINER','A sturdy canvas backpack with leather straps.', '{"weight":1,"capacity":30,"wear_location":["back"],"value":0}'),
 ('traveler shirt','ARMOR','A simple linen shirt fit for the road.', '{"weight":0.3,"wear_location":["torso"],"value":0}'),
 ('traveler trousers','ARMOR','Hard-wearing wool trousers.', '{"weight":0.4,"wear_location":["legs"],"value":0}'),
 ('traveler boots','ARMOR','Comfortable leather walking boots.', '{"weight":0.5,"wear_location":["feet"],"value":0}')
 ON CONFLICT(name) DO NOTHING;
CREATE INDEX IF NOT EXISTS characters_player_page ON characters(player_id,id);
CREATE INDEX IF NOT EXISTS instances_owner_page ON item_instances(owner_char_id,id);
CREATE INDEX IF NOT EXISTS exits_source_page ON exits(source_room_id,id);
-- Once-only outfitting for existing characters, preserving every occupied slot.
DO $$
DECLARE outfit RECORD; recipient RECORD; instance UUID;
BEGIN
 FOR outfit IN SELECT name,slot FROM (VALUES ('traveler backpack','back'),('traveler shirt','torso'),('traveler trousers','legs'),('traveler boots','feet')) AS outfits(name,slot)
 LOOP
  FOR recipient IN EXECUTE format('SELECT character_id FROM character_equipment WHERE %I IS NULL',outfit.slot)
  LOOP
   INSERT INTO item_instances(template_id,owner_char_id,instance_stats)
    SELECT id,recipient.character_id,'{"is_open":true}'::jsonb FROM item_templates WHERE name=outfit.name RETURNING id INTO instance;
   EXECUTE format('UPDATE character_equipment SET %I=$1 WHERE character_id=$2',outfit.slot) USING instance,recipient.character_id;
  END LOOP;
 END LOOP;
END $$;
