CREATE TABLE player_homes(id SERIAL PRIMARY KEY,owner_id INTEGER UNIQUE NOT NULL REFERENCES characters(id) ON DELETE CASCADE,name TEXT NOT NULL DEFAULT 'A rented room',description TEXT NOT NULL DEFAULT 'A quiet room above the Lantern & Tide.',created_at TIMESTAMPTZ DEFAULT now());
CREATE TABLE market_listings(id SERIAL PRIMARY KEY,seller_id INTEGER NOT NULL REFERENCES characters(id) ON DELETE CASCADE,item_id UUID NOT NULL UNIQUE REFERENCES item_instances(id) ON DELETE CASCADE,price INTEGER NOT NULL CHECK(price>0),created_at TIMESTAMPTZ DEFAULT now());
ALTER TABLE item_instances ADD COLUMN market_id INTEGER REFERENCES market_listings(id) DEFERRABLE INITIALLY DEFERRED;
ALTER TABLE item_instances DROP CONSTRAINT single_location_check;
ALTER TABLE item_instances ADD CONSTRAINT single_location_check CHECK(num_nonnulls(owner_char_id,room_id,container_id,bank_char_id,market_id)=1);
INSERT INTO balance_rules(name,value,description) VALUES('housing_price',2500,'Permanent room charter coin sink'),('market_tax_percent',5,'Seller proceeds tax'),('enchant_price',500,'Cost per enchantment rank squared');
