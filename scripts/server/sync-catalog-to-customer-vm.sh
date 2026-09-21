#!/usr/bin/env bash
# Test sunucusunun anlam katalogunu (tablo profili + kavram + eşleme + kanıt) müşteri VM'ine taşır.
#
# Neden: iki tarafın tablo profilleri zaten aynı (4.874), ama sertifikalı kavram sayısı
# test sunucusunda ~4.980, VM'de 110. Kod ne kadar doğru olursa olsun, sözlük olmadan
# sorular "katalogda tanımlı değil" diye reddedilir. Taşınan yalnız "bu kelime şu
# tabloyu/kolonu anlatır" bilgisidir; müşteri verisine dokunulmaz.
#
# Nerede koşar: bizim test sunucusunda (nanobase-direct), VPN (tun0) açıkken.
#   Kuru koşu:  bash ~/catalog-sync.sh
#   Uygula:     bash ~/catalog-sync.sh --apply
#
# Idempotent: aynı id varsa güncellenir, VM'e özel kayıtlar silinmez.
set -euo pipefail
APPLY="${1:-}"
DSN=$(sudo grep -E '^SEMANTIC_STORE_DSN=' /etc/nanobase/semantic-bridge.env | cut -d= -f2- | sed 's/+psycopg2//')
VMC='cd /home/ai/bi-docker/infra/docker/bi && docker compose exec -T db psql -U bi_meta -d bi_meta'
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT

echo "== kaynak (test sunucusu)"
for t in sl_schema_profile sl_concept sl_mapping sl_evidence; do
  psql "$DSN" -tA -c "COPY (SELECT row_to_json(t) FROM $t t) TO STDOUT" > "$W/$t.json"
  echo "  $t: $(wc -l < "$W/$t.json") satır"
done

echo "== hedef (VM) bugün"
ssh -o BatchMode=yes timas-vm "$VMC -F, -tA -c \"select status, count(*) from sl_concept group by status order by 2 desc\"" || true

echo "== geçici tablolara aktarılıyor"
for t in sl_schema_profile sl_concept sl_mapping sl_evidence; do
  gzip -c "$W/$t.json" | ssh -o BatchMode=yes timas-vm "cat > /tmp/$t.json.gz"
done
ssh -o BatchMode=yes timas-vm "cd /home/ai/bi-docker/infra/docker/bi && for t in sl_schema_profile sl_concept sl_mapping sl_evidence; do
  docker compose exec -T db psql -U bi_meta -d bi_meta -q -c \"drop table if exists stage_\$t; create table stage_\$t (d jsonb);\"
  gunzip -c /tmp/\$t.json.gz | docker compose exec -T db psql -U bi_meta -d bi_meta -q -c \"COPY stage_\$t (d) FROM STDIN\"
done"

echo "== fark"
ssh -o BatchMode=yes timas-vm "$VMC -F'|' -tA -c \"
  select 'yeni kavram='||count(*) from stage_sl_concept s where not exists (select 1 from sl_concept c where c.id = s.d->>'id')
  union all select 'guncellenen='||count(*) from stage_sl_concept s join sl_concept c on c.id = s.d->>'id'
  union all select 'VMe ozel (dokunulmaz)='||count(*) from sl_concept c where not exists (select 1 from stage_sl_concept s where s.d->>'id' = c.id)
  union all select 'kaynak kavram toplam='||count(*) from stage_sl_concept
  union all select 'profil: yeni='||count(*) from stage_sl_schema_profile s where not exists (select 1 from sl_schema_profile p where p.id = s.d->>'id')
  union all select 'profil: guncellenen='||count(*) from stage_sl_schema_profile s join sl_schema_profile p on p.id = s.d->>'id'
  union all select 'profil: VMe ozel='||count(*) from sl_schema_profile p where not exists (select 1 from stage_sl_schema_profile s where s.d->>'id' = p.id)\""

if [ "$APPLY" != "--apply" ]; then echo "== KURU KOŞU — hiçbir şey yazılmadı. Uygulamak için: bash ~/catalog-sync.sh --apply"; exit 0; fi

echo "== yazılıyor"
ssh -o BatchMode=yes timas-vm "$VMC -v ON_ERROR_STOP=1 -q -c \"
BEGIN;
-- Profiller önce: ilişkiler (relationships_json), kolon etiketleri ve açıklamalar burada durur;
-- kavram eşlemeleri bunlara dayanır. VM'de 5.085 ilişki vardı, kaynakta 6.388.
INSERT INTO sl_schema_profile
SELECT (jsonb_populate_record(null::sl_schema_profile, d)).* FROM stage_sl_schema_profile
ON CONFLICT (id) DO UPDATE SET table_pattern=EXCLUDED.table_pattern, entity=EXCLUDED.entity,
  columns_json=EXCLUDED.columns_json, primary_key_json=EXCLUDED.primary_key_json,
  relationships_json=EXCLUDED.relationships_json, context_json=EXCLUDED.context_json,
  row_count=EXCLUDED.row_count, description=EXCLUDED.description, scanned_at=EXCLUDED.scanned_at,
  time_window_json=EXCLUDED.time_window_json, derived_json=EXCLUDED.derived_json;

INSERT INTO sl_concept
SELECT (jsonb_populate_record(null::sl_concept, d)).* FROM stage_sl_concept
ON CONFLICT (id) DO UPDATE SET term=EXCLUDED.term, normalized_term=EXCLUDED.normalized_term,
  semantic_type=EXCLUDED.semantic_type, domain=EXCLUDED.domain, sense_id=EXCLUDED.sense_id,
  status=EXCLUDED.status, confidence=EXCLUDED.confidence, version=EXCLUDED.version,
  synonyms_json=EXCLUDED.synonyms_json, explain_json=EXCLUDED.explain_json, updated_at=EXCLUDED.updated_at;

DELETE FROM sl_mapping m WHERE EXISTS (SELECT 1 FROM stage_sl_mapping s WHERE s.d->>'concept_id' = m.concept_id);
INSERT INTO sl_mapping
SELECT (jsonb_populate_record(null::sl_mapping, d)).* FROM stage_sl_mapping
ON CONFLICT (id) DO NOTHING;

DELETE FROM sl_evidence e WHERE EXISTS (SELECT 1 FROM stage_sl_evidence s WHERE s.d->>'concept_id' = e.concept_id);
INSERT INTO sl_evidence SELECT * FROM jsonb_populate_recordset(null::sl_evidence, (SELECT jsonb_agg(d) FROM stage_sl_evidence))
ON CONFLICT DO NOTHING;

INSERT INTO sl_catalog_version (id, tenant_id, datasource_id, version, certified_count, snapshot_json, note, created_at)
VALUES ('cv_'||substr(md5(random()::text||clock_timestamp()::text),1,12), 'default', 'logo',
        (SELECT coalesce(max(version),0)+1 FROM sl_catalog_version),
        (SELECT count(*) FROM sl_concept WHERE status='CERTIFIED'),
        '{}'::jsonb, 'test sunucusundan sözlük aktarımı', now());
DROP TABLE stage_sl_schema_profile; DROP TABLE stage_sl_concept; DROP TABLE stage_sl_mapping; DROP TABLE stage_sl_evidence;
COMMIT;\""

echo "== VM köprüsü yenileniyor (katalog yeniden okunsun)"
ssh -o BatchMode=yes timas-vm "cd /home/ai/bi-docker/infra/docker/bi && docker compose restart bridge && sleep 25 && docker compose ps --format '{{.Service}} {{.State}}'"

echo "== sonuç (VM)"
ssh -o BatchMode=yes timas-vm "$VMC -F, -tA -c \"select status, count(*) from sl_concept group by status order by 2 desc\""
