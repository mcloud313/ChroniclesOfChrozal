CREATE TABLE class_kits(id SERIAL PRIMARY KEY,name TEXT UNIQUE NOT NULL,definition JSONB NOT NULL);
INSERT INTO balance_rules(name,value,description) VALUES
('xp_level_75_total',10800000,'Cumulative XP required for level 75'),
('xp_after_75_growth',1.18,'Per-level XP growth multiplier after 75'),
('xp_absorb_rate',5,'XP absorbed per second at a node'),
('technique_base',4,'Base technique damage before level/stat scaling'),
('technique_per_level',2,'Technique damage per level'),
('technique_signature_cost',4,'Signature essence cost'),
('technique_finale_cost',8,'Finale essence cost'),
('technique_signature_multiplier',1.45,'Signature damage multiplier'),
('technique_finale_multiplier',2,'Finale damage multiplier'),
('mob_xp_base',25,'Kill XP per mob level'),
('mud_roundtime',1.5,'Additional movement recovery in mud'),
('snow_roundtime',1,'Additional movement recovery in snow'),
('tether_xp_per_level',250,'Cleric XP cost per target level'),
('tether_xp_per_missing',1000,'Cleric XP cost per missing tether point')
ON CONFLICT(name) DO NOTHING;
