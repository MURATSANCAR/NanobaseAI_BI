-- Part 3: hasar + prim + teminat + komisyon

-- Hasar talepleri (~700.000) — poliçelerin bir kısmı
INSERT INTO hasar_talepleri (
  hasar_no, "poliçe_id", police_id, musteri_id, acente_id, neden_id,
  durum, talep_tutari, onaylanan_tutar, fraud_skoru,
  ihbar_tarihi, olay_tarihi, kapama_tarihi, created_at
)
SELECT
  'HSR-' || lpad(g::text, 9, '0'),
  p.id,
  p.id,
  p.musteri_id,
  p.acente_id,
  1 + (g % 9),
  (ARRAY['Açık','İncelemede','Onaylandı','Ödendi','Ödendi','Reddedildi','Fraud Şüpheli'])[1 + (g % 7)],
  ROUND((1500 + (g % 180000) + ((g % 40) * 125.5))::numeric, 2),
  CASE WHEN g % 7 IN (2,3,4) THEN ROUND((1000 + (g % 150000))::numeric, 2) ELSE NULL END,
  ROUND((((g * 37) % 1000) / 1000.0)::numeric, 4),
  p.created_at + ((10 + (g % 300)) || ' days')::interval,
  (p.baslangic_tarihi + ((5 + (g % 200))))::date,
  CASE WHEN g % 7 IN (3,4) THEN p.created_at + ((40 + (g % 200)) || ' days')::interval ELSE NULL END,
  p.created_at + ((12 + (g % 300)) || ' days')::interval
FROM (
  SELECT id, musteri_id, acente_id, created_at, baslangic_tarihi,
         row_number() OVER (ORDER BY id) AS rn
  FROM policeler
  WHERE id % 3 = 1
) p
JOIN generate_series(1, 700000) g ON g = p.rn
WHERE p.rn <= 700000;

-- Ekspertiz (~400k)
INSERT INTO ekspertizler (hasar_id, eksper_adi, rapor_no, tespit_tutari, rapor_tarihi, durum)
SELECT
  h.id,
  (ARRAY['Ali Eksper','Can Eksper','Deniz Eksper','Ece Eksper','Murat Eksper'])[1 + (h.id % 5)],
  'EXP-' || lpad(h.id::text, 8, '0'),
  COALESCE(h.onaylanan_tutar, h.talep_tutari * 0.85),
  h.olay_tarihi + ((3 + (h.id % 12))),
  (ARRAY['Tamamlandı','Revize','Bekliyor'])[1 + (h.id % 3)]
FROM hasar_talepleri h
WHERE h.id % 5 <> 0;

-- Hasar belgeleri (~1.4M)
INSERT INTO hasar_belgeleri (hasar_id, belge_tipi, dosya_adi, yukleme_tarihi)
SELECT
  h.id,
  (ARRAY['Fotoğraf','Ekspertiz','Fatura','Tutanak','Kimlik'])[1 + ((h.id + d) % 5)],
  'doc_' || h.id || '_' || d || '.pdf',
  h.ihbar_tarihi + (d || ' hours')::interval
FROM hasar_talepleri h
CROSS JOIN generate_series(1, 2) d;

-- Prim ödemeleri (~4.000.000) — polişe başına 1 veya 2 taksit
INSERT INTO prim_odemeleri (
  "poliçe_id", police_id, taksit_no, planlanan_tutar, planlanan_tarih,
  odeme_tutari, odeme_tarihi, odeme_yontem_id, odeme_yontemi, durum, dekont_referans, aciklama
)
SELECT
  p.id,
  p.id,
  t.taksit_no,
  ROUND(p.prim_tutari / t.taksit_sayisi, 2),
  (p.baslangic_tarihi + ((t.taksit_no - 1) * 30)),
  CASE WHEN (p.id + t.taksit_no) % 10 < 8 THEN ROUND(p.prim_tutari / t.taksit_sayisi, 2) ELSE NULL END,
  CASE WHEN (p.id + t.taksit_no) % 10 < 8 THEN (p.baslangic_tarihi + ((t.taksit_no - 1) * 30) + 3) ELSE NULL END,
  1 + ((p.id + t.taksit_no) % 5),
  (ARRAY['Kredi Kartı','Banka Havalesi/EFT','Otomatik Ödeme','Nakit','Dijital Cüzdan'])[1 + ((p.id + t.taksit_no) % 5)],
  CASE
    WHEN (p.id + t.taksit_no) % 10 < 8 THEN 'Ödendi'
    WHEN (p.id + t.taksit_no) % 10 < 9 THEN 'Bekliyor'
    ELSE 'Gecikmiş'
  END,
  'DKT-' || p.id || '-' || t.taksit_no,
  'Tahsilat kaydı'
FROM policeler p
JOIN (
  SELECT 1 AS taksit_no, 1 AS taksit_sayisi
  UNION ALL SELECT 1, 2
  UNION ALL SELECT 2, 2
) t ON (p.id % 2 = 0 AND t.taksit_sayisi = 2) OR (p.id % 2 = 1 AND t.taksit_sayisi = 1);

-- Poliçe teminatları (~5M) — her poliçeye 2-3 teminat
INSERT INTO police_teminatlari (police_id, teminat_id, limit_tutari, muafiyet_tutari)
SELECT
  p.id,
  1 + ((p.id + t) % 9),
  ROUND((20000 + ((p.id * t) % 900000))::numeric, 2),
  ROUND(((p.id % 20) * 250)::numeric, 2)
FROM policeler p
CROSS JOIN generate_series(0, 2) t
ON CONFLICT DO NOTHING;

-- Komisyon ödemeleri (~1M aktif/ödendi poliçe üzerinden)
INSERT INTO komisyon_odemeleri (acente_id, police_id, donem, tutar, durum, odeme_tarihi, created_at)
SELECT
  p.acente_id,
  p.id,
  to_char(p.baslangic_tarihi, 'YYYY-MM'),
  p.komisyon_tutari,
  CASE WHEN p.id % 10 < 8 THEN 'Ödendi' ELSE 'Bekliyor' END,
  CASE WHEN p.id % 10 < 8 THEN p.baslangic_tarihi + 20 ELSE NULL END,
  p.created_at + interval '15 days'
FROM policeler p
WHERE p.id % 2 = 0;

-- Acente hedefleri (aylık)
INSERT INTO acente_hedefleri (acente_id, donem, hedef_prim, hedef_police)
SELECT
  sub.acente_id,
  sub.donem,
  ROUND(GREATEST(sub.prim * 1.15, 25000), 2),
  GREATEST(CEIL(sub.police * 1.12)::int, 3)
FROM (
  SELECT
    acente_id,
    to_char(date_trunc('month', created_at), 'YYYY-MM') AS donem,
    SUM(prim_tutari) AS prim,
    COUNT(*) AS police
  FROM policeler
  WHERE deleted_at IS NULL
  GROUP BY 1, 2
) sub
ON CONFLICT (acente_id, donem) DO UPDATE
SET hedef_prim = EXCLUDED.hedef_prim,
    hedef_police = EXCLUDED.hedef_police;

-- İletişim (~500k)
INSERT INTO musteri_iletisim (musteri_id, kanal, deger, birincil)
SELECT id, 'Telefon', telefon, true FROM musteriler
UNION ALL
SELECT id, 'E-posta', email, false FROM musteriler WHERE id % 2 = 0;

-- Index'ler (sorgu performansı)
CREATE INDEX IF NOT EXISTS ix_police_acente ON policeler(acente_id);
CREATE INDEX IF NOT EXISTS ix_police_musteri ON policeler(musteri_id);
CREATE INDEX IF NOT EXISTS ix_police_durum ON policeler(durum);
CREATE INDEX IF NOT EXISTS ix_police_baslangic ON policeler(baslangic_tarihi);
CREATE INDEX IF NOT EXISTS ix_hasar_police ON hasar_talepleri(police_id);
CREATE INDEX IF NOT EXISTS ix_hasar_durum ON hasar_talepleri(durum);
CREATE INDEX IF NOT EXISTS ix_hasar_fraud ON hasar_talepleri(fraud_skoru);
CREATE INDEX IF NOT EXISTS ix_prim_police ON prim_odemeleri(police_id);
CREATE INDEX IF NOT EXISTS ix_prim_durum ON prim_odemeleri(durum);
CREATE INDEX IF NOT EXISTS ix_musteri_il ON musteriler(il_id);
CREATE INDEX IF NOT EXISTS ix_acente_bolge ON acenteler(bolge);

ANALYZE;
