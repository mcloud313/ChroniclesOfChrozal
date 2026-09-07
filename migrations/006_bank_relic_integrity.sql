ALTER TABLE item_instances ADD COLUMN IF NOT EXISTS bank_char_id INTEGER REFERENCES characters(id);
ALTER TABLE item_instances DROP CONSTRAINT IF EXISTS single_location_check;
UPDATE item_instances i SET bank_char_id=b.character_id,owner_char_id=NULL,room_id=NULL,container_id=NULL FROM banked_items b WHERE b.item_instance_id=i.id;
ALTER TABLE item_instances ADD CONSTRAINT single_location_check CHECK (num_nonnulls(owner_char_id,room_id,container_id,bank_char_id)=1);
-- The same uniqueness rule applies to crafting, loot, admin-created instances and attunement.
CREATE OR REPLACE FUNCTION guard_unique_relic() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
 IF EXISTS(SELECT 1 FROM relics WHERE template_id=NEW.template_id) THEN
   PERFORM pg_advisory_xact_lock(72701,NEW.template_id);
   IF EXISTS(SELECT 1 FROM item_instances WHERE template_id=NEW.template_id AND id<>NEW.id) THEN
      RAISE EXCEPTION 'This relic already exists in the world';
   END IF;
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER relic_instance_guard BEFORE INSERT OR UPDATE OF template_id ON item_instances FOR EACH ROW EXECUTE FUNCTION guard_unique_relic();
