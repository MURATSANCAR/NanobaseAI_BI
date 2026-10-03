-- Merkezi denetim kaydı (portalın Yönetim → Denetim kaydı) — editör tarafı.
-- Kişinin isteğiyle (X-Editor başlıklı yazma isteği) açılan işlemde değişen her satır, önceki/sonraki hâliyle
-- `ed.audit_outbox`'a yazılır; portal köprüsü kart servisi üzerinden çeker (`/v1/audit/outbox`) ve onaylayınca silinir.
-- Bağlam `nanobase.audit` (kişi + istek kimliği) `db.tx()` içinde konur; bağlamsız işlem (işçi, model, yeniden kurma)
-- tetikleyiciyi çalıştırmaz — makinenin işi kendi iş kayıtlarında durur.
SET search_path = ed, public;

CREATE TABLE IF NOT EXISTS ed.audit_outbox (
    seq  bigserial PRIMARY KEY,
    at   timestamptz NOT NULL DEFAULT clock_timestamp(),
    body jsonb NOT NULL
);

CREATE OR REPLACE FUNCTION ed.nb_audit_hidden(v jsonb, how text) RETURNS jsonb LANGUAGE sql IMMUTABLE AS $f$
  SELECT CASE WHEN v IS NULL OR v = 'null'::jsonb THEN v
              WHEN how = 'b' THEN to_jsonb('«ikili veri · ' || greatest((length(v #>> '{}') - 2) / 2, 0)
                                           || ' bayt · ' || left(md5(v #>> '{}'), 8) || '»')
              ELSE to_jsonb('«gizli · ' || left(md5(v #>> '{}'), 8) || '»') END
$f$;

CREATE OR REPLACE FUNCTION ed.nb_audit_row() RETURNS trigger LANGUAGE plpgsql AS $f$
DECLARE
  ctx jsonb;
  o jsonb; n jsonb; ch text[]; k text; parts text[]; pk jsonb := '{}'::jsonb;
  pkcols text[] := string_to_array(NULLIF(TG_ARGV[0], ''), ',');
  masks text[] := string_to_array(NULLIF(TG_ARGV[1], ''), ',');
BEGIN
  ctx := NULLIF(current_setting('nanobase.audit', true), '')::jsonb;
  IF ctx IS NULL THEN RETURN NULL; END IF;
  IF TG_OP <> 'INSERT' THEN o := to_jsonb(OLD); END IF;
  IF TG_OP <> 'DELETE' THEN n := to_jsonb(NEW); END IF;
  IF TG_OP = 'UPDATE' THEN
    SELECT array_agg(e.key ORDER BY e.key) INTO ch FROM jsonb_each(n) e WHERE e.value IS DISTINCT FROM o -> e.key;
    IF ch IS NULL THEN RETURN NULL; END IF;
  END IF;
  IF pkcols IS NOT NULL THEN
    FOREACH k IN ARRAY pkcols LOOP pk := pk || jsonb_build_object(k, coalesce(n, o) -> k); END LOOP;
    IF TG_OP = 'UPDATE' THEN
      o := (SELECT jsonb_object_agg(key, value) FROM jsonb_each(o) WHERE key = ANY(ch));
      n := (SELECT jsonb_object_agg(key, value) FROM jsonb_each(n) WHERE key = ANY(ch));
    END IF;
  END IF;
  IF masks IS NOT NULL THEN
    FOREACH k IN ARRAY masks LOOP
      parts := string_to_array(k, ':');
      IF o ? parts[1] THEN o := jsonb_set(o, ARRAY[parts[1]], ed.nb_audit_hidden(o -> parts[1], parts[2])); END IF;
      IF n ? parts[1] THEN n := jsonb_set(n, ARRAY[parts[1]], ed.nb_audit_hidden(n -> parts[1], parts[2])); END IF;
    END LOOP;
  END IF;
  INSERT INTO ed.audit_outbox(body) VALUES (jsonb_build_object(
    'type', 'row', 'id', 'row:' || txid_current() || ':' || nextval('ed.audit_outbox_seq_seq'),
    'at', clock_timestamp(), 'rid', ctx ->> 'rid', 'actor', ctx ->> 'actor', 'table', TG_TABLE_NAME, 'op', TG_OP,
    'pk', CASE WHEN pk = '{}'::jsonb THEN NULL ELSE pk END, 'changed', to_jsonb(ch), 'old', o, 'new', n));
  RETURN NULL;
END $f$;

-- Tetikleyicisi olmayan ya da kolon yapısı değişen her `ed` tablosuna kurar. `db.migrate()` her göçten sonra çağırır:
-- sonradan açılan tablolar da kapsanır.
CREATE OR REPLACE FUNCTION ed.nb_audit_install() RETURNS integer LANGUAGE plpgsql AS $f$
DECLARE
  r record; want text; n integer := 0;
BEGIN
  FOR r IN
    SELECT c.oid, c.relname,
           coalesce((SELECT string_agg(a.attname, ',' ORDER BY array_position(i.indkey::int2[], a.attnum))
                     FROM pg_index i JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                     WHERE i.indrelid = c.oid AND i.indisprimary), '') AS pk,
           coalesce((SELECT string_agg(a.attname || ':' || CASE WHEN t.typname = 'bytea' THEN 'b' ELSE 's' END, ',' ORDER BY a.attnum)
                     FROM pg_attribute a JOIN pg_type t ON t.oid = a.atttypid
                     WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped
                       AND (t.typname = 'bytea' OR a.attname ~* '(pass(word|wd)?|pwd|parola|sifre|secret|token|api_?key|credential|private_?key|cookie)')), '') AS masks,
           (SELECT encode(tg.tgargs, 'escape') FROM pg_trigger tg WHERE tg.tgrelid = c.oid AND tg.tgname = 'nb_audit_row') AS have
    FROM pg_class c JOIN pg_namespace ns ON ns.oid = c.relnamespace
    WHERE ns.nspname = 'ed' AND c.relkind IN ('r', 'p') AND NOT c.relispartition
      AND c.relname NOT IN ('audit_outbox', 'schema_migration')
  LOOP
    want := r.pk || '\000' || r.masks || '\000';
    CONTINUE WHEN r.have = want;
    EXECUTE format('DROP TRIGGER IF EXISTS nb_audit_row ON ed.%I', r.relname);
    EXECUTE format('CREATE TRIGGER nb_audit_row AFTER INSERT OR UPDATE OR DELETE ON ed.%I FOR EACH ROW '
                   'WHEN (coalesce(current_setting(''nanobase.audit'', true), '''') <> '''') '
                   'EXECUTE FUNCTION ed.nb_audit_row(%L, %L)', r.relname, r.pk, r.masks);
    n := n + 1;
  END LOOP;
  RETURN n;
END $f$;

SELECT ed.nb_audit_install();
