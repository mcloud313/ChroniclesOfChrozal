-- Additive content; retain builder-written descriptions.
UPDATE classes SET description=CASE name
 WHEN 'Warrior' THEN 'A disciplined fighter who controls the frontline with precise strikes, armor, and defensive stances.'
 WHEN 'Mage' THEN 'A scholar of arcane forces who shapes destructive spells and protective wards through careful preparation.'
 WHEN 'Cleric' THEN 'A keeper of divine covenants who heals companions, rebukes enemies, and repairs soul tethers at personal experience cost.'
 WHEN 'Rogue' THEN 'A patient infiltrator who uses stealth, ambushes, lockpicks, and trapcraft to choose the terms of an encounter.' END
 WHERE name IN ('Warrior','Mage','Cleric','Rogue') AND (description IS NULL OR trim(description) IN ('','...'));
INSERT INTO classes(id,name,description) VALUES(12,'Tempest','A storm caller who channels wind, thunder, and rain to hinder enemies and protect travelers.') ON CONFLICT DO NOTHING;
INSERT INTO races(name,description) VALUES
 ('Kaiteen','Agile feline folk with expressive ears, patterned fur, and a tradition of traveling storytellers.'),
 ('Aelari','Amphibious coastal folk whose fin-fringed ears and silver gills recall their ancestral tide cities.'),
 ('Veskar','Scaled highland folk with swept horns and tapered tails, famed for stonework and long oral histories.') ON CONFLICT DO NOTHING;
SELECT setval(pg_get_serial_sequence('classes','id'),GREATEST((SELECT max(id) FROM classes),1));
SELECT setval(pg_get_serial_sequence('races','id'),GREATEST((SELECT max(id) FROM races),1));
