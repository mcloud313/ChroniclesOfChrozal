-- Legacy essential rows used explicit IDs. Advance sequences without moving them backwards.
DO $$
DECLARE t text; seq text; highest bigint; current_value bigint;
BEGIN
  FOREACH t IN ARRAY ARRAY['areas','rooms','races','classes'] LOOP
    seq := pg_get_serial_sequence(t,'id');
    EXECUTE format('SELECT COALESCE(max(id),1) FROM %I',t) INTO highest;
    EXECUTE format('SELECT last_value FROM %s',seq) INTO current_value;
    PERFORM setval(seq, GREATEST(highest,current_value));
  END LOOP;
END $$;
