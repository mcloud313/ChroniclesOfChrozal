ALTER TABLE resource_nodes DROP CONSTRAINT IF EXISTS resource_nodes_name_key;
CREATE UNIQUE INDEX resource_node_room_name ON resource_nodes(room_id,lower(name));
ALTER TABLE resource_nodes ADD COLUMN profession TEXT NOT NULL DEFAULT 'herbalism' CHECK (profession IN ('mining','herbalism','skinning','fishing','logging','farming','hunting'));
ALTER TABLE resource_nodes ADD COLUMN difficulty INTEGER NOT NULL DEFAULT 8 CHECK(difficulty BETWEEN 2 AND 40);
ALTER TABLE resource_nodes ADD COLUMN uses INTEGER NOT NULL DEFAULT 0 CHECK(uses>=0);
ALTER TABLE recipes ADD COLUMN profession TEXT NOT NULL DEFAULT 'alchemy' CHECK(profession IN ('smithing','alchemy','cooking','runecrafting','brewing'));
ALTER TABLE recipes ADD COLUMN difficulty INTEGER NOT NULL DEFAULT 8 CHECK(difficulty BETWEEN 2 AND 40);
CREATE INDEX resource_depleted ON resource_nodes(depleted_at) WHERE remaining=0;
-- Idempotent starter-content installer, also used after a fresh seed. Custom worlds retained.
CREATE FUNCTION chrozal_professions_setup() RETURNS void LANGUAGE plpgsql AS $$
DECLARE p TEXT; tid INTEGER; rid INTEGER; material TEXT; ingredient TEXT; output TEXT; ids JSONB;
BEGIN
 IF NOT EXISTS(SELECT 1 FROM rooms WHERE id=3 AND name='Saltwind Strand') THEN RETURN; END IF;
 UPDATE resource_nodes SET respawn_seconds=900 WHERE name IN ('silverleaf','iron fragments') AND respawn_seconds=300;
 UPDATE resource_nodes SET profession='mining' WHERE name='iron fragments' AND profession='herbalism';
 UPDATE recipes SET profession='smithing' WHERE name='wayfarer charm' AND profession='alchemy';
 FOR p,material,rid IN SELECT * FROM (VALUES
 ('herbalism','silverleaf',3),('mining','iron fragment',5),('skinning','saltwind hide',7),
 ('fishing','shore trout',3),('logging','driftwood timber',5),('farming','barley grain',7),('hunting','game meat',7)) AS v(a,b,c)
 LOOP
  INSERT INTO item_templates(name,type,description,stats) SELECT material,'OTHER','A gathered coastal resource.', '{"weight":0.5,"value":4}' WHERE NOT EXISTS(SELECT 1 FROM item_templates WHERE name=material);
  SELECT id INTO tid FROM item_templates WHERE name=material ORDER BY id LIMIT 1;
  INSERT INTO resource_nodes(room_id,name,item_template_id,profession,respawn_seconds) SELECT rid,material,tid,p,900 WHERE NOT EXISTS(SELECT 1 FROM resource_nodes WHERE item_template_id=tid AND room_id=rid);
  UPDATE rooms SET flags=flags || jsonb_build_array(upper(p)||'_NODE') WHERE id=rid AND NOT flags ? (upper(p)||'_NODE');
 END LOOP;
 FOR p IN SELECT unnest(ARRAY['mining','herbalism','skinning','fishing','logging','farming','hunting','smithing','alchemy','cooking','runecrafting','brewing']) LOOP
  INSERT INTO item_templates(name,type,description,stats)
    SELECT p||' tool','OTHER','A one-handed apprentice tool. Hold it while working.',jsonb_build_object('weight',1,'value',10,'tool_for',jsonb_build_array(p))
    WHERE NOT EXISTS(SELECT 1 FROM item_templates WHERE name=p||' tool');
  SELECT id INTO tid FROM item_templates WHERE name=p||' tool' ORDER BY id LIMIT 1;
  INSERT INTO shop_inventories(room_id,item_template_id,stock_quantity,buy_price_modifier) SELECT 4,tid,-1,1 WHERE NOT EXISTS(SELECT 1 FROM shop_inventories WHERE room_id=4 AND item_template_id=tid);
 END LOOP;
 FOR p,output,ingredient IN SELECT * FROM (VALUES
 ('cooking','grilled trout','shore trout'),('brewing','barley tea','barley grain'),('runecrafting','coastal rune','iron fragment')) AS v(a,b,c) LOOP
  INSERT INTO item_templates(name,type,description,stats) SELECT output,CASE WHEN p='cooking' THEN 'FOOD' WHEN p='brewing' THEN 'DRINK' ELSE 'OTHER' END,
   'Made at a coastal workshop.',jsonb_build_object('weight',0.3,'value',8,'effect',CASE WHEN p='cooking' THEN 'restore_hunger' ELSE 'restore_thirst' END,'amount',30)
   WHERE NOT EXISTS(SELECT 1 FROM item_templates WHERE name=output);
  SELECT id INTO tid FROM item_templates WHERE name=output ORDER BY id LIMIT 1;
  SELECT jsonb_build_object(id::text,1) INTO ids FROM item_templates WHERE name=ingredient ORDER BY id LIMIT 1;
  INSERT INTO recipes(name,description,station_room_id,output_template_id,ingredients,profession)
   VALUES(output,'Requires 1 '||ingredient||', a held '||p||' tool and a '||p||' station.',4,tid,ids,p) ON CONFLICT(name) DO NOTHING;
 END LOOP;
 FOR p IN SELECT unnest(ARRAY['smithing','alchemy','cooking','runecrafting','brewing']) LOOP
  UPDATE rooms SET flags=flags || jsonb_build_array(upper(p)||'_STATION') WHERE id=4 AND NOT flags ? (upper(p)||'_STATION');
 END LOOP;
 UPDATE rooms SET flags=flags || '["TAVERN"]' WHERE id=2 AND NOT flags ? 'TAVERN';
 UPDATE rooms SET description='Grey-green waves wash the shore. Patches of medicinal growth and quiet fishing pools lie between the stones. Use GATHER to inspect available resources.' WHERE id=3 AND description LIKE '%Try gather silverleaf.%';
 UPDATE mob_templates SET flags=flags || '["AGGRESSIVE"]' WHERE name='tide scavenger' AND NOT flags ? 'AGGRESSIVE';
 UPDATE mob_templates SET description='A lean coastal scavenger prowls for scraps, snapping at anyone who approaches its feeding ground.' WHERE name='tide scavenger' AND description LIKE '%Watch its posture%';
END $$;
SELECT chrozal_professions_setup();
