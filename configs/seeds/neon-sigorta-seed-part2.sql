-- Part 2: araç/konut + poliçe + hasar + tahsilat (milyonlarca satır)

-- Araçlar (~350k bireysel müşteri alt kümesi)
INSERT INTO araclar (musteri_id, plaka, marka, model, model_yili, kullanim_tarzi, created_at)
SELECT
  m.id,
  (ARRAY['34','06','35','16','07','41','33','42'])[1 + (m.id % 8)]
    || ' ' || (ARRAY['ABC','DEF','GHJ','KLM','NPR','STV','YZX'])[1 + (m.id % 7)]
    || ' ' || lpad(((m.id * 17) % 1000)::text, 3, '0'),
  (ARRAY['Toyota','Volkswagen','Renault','Fiat','Ford','Hyundai','Mercedes','BMW','Tofaş','Peugeot'])[1 + (m.id % 10)],
  (ARRAY['Corolla','Golf','Clio','Egea','Focus','i20','C-Class','3 Serisi','Şahin','208'])[1 + (m.id % 10)],
  2008 + (m.id % 17),
  CASE WHEN m.id % 11 = 0 THEN 'Ticari' ELSE 'Hususi' END,
  m.created_at + interval '10 days'
FROM musteriler m
WHERE m.tip = 'Bireysel' AND m.id % 1 = 0 AND m.id <= 350000;

-- Konutlar (~200k)
INSERT INTO konutlar (musteri_id, il_id, yapi_tarzi, metrekare, deprem_bolgesi, created_at)
SELECT
  m.id,
  m.il_id,
  (ARRAY['Betonarme','Yığma','Çelik','Ahşap'])[1 + (m.id % 4)],
  60 + (m.id % 220),
  1 + (m.id % 5),
  m.created_at + interval '5 days'
FROM musteriler m
WHERE m.id <= 200000;

-- Poliçeler (2.000.000) — ana üretim tablosu
INSERT INTO policeler (
  police_no, musteri_id, acente_id, urun_id, arac_id, konut_id,
  durum, prim_tutari, net_prim, vergi_tutari, komisyon_tutari, teminat_bedeli,
  baslangic_tarihi, bitis_tarihi, yenileme_no, created_at
)
SELECT
  'PLC' || to_char(date '2021-01-01' + ((g % 1700)), 'YYMM') || lpad(g::text, 8, '0'),
  1 + ((g::bigint * 7919) % 500000),
  1 + ((g::bigint * 104729) % 2500),
  1 + (g % 8),
  CASE WHEN (1 + (g % 8)) IN (1,2,8) THEN 1 + ((g::bigint * 13) % 350000) ELSE NULL END,
  CASE WHEN (1 + (g % 8)) IN (3,6,7) THEN 1 + ((g::bigint * 17) % 200000) ELSE NULL END,
  (ARRAY['Aktif','Aktif','Aktif','Aktif','Süresi Doldu','İptal','Askıda'])[1 + (g % 7)],
  ROUND((800 + (g % 42000) + ((g % 50) * 37.5))::numeric, 2),
  ROUND((700 + (g % 38000))::numeric, 2),
  ROUND((80 + (g % 3500))::numeric, 2),
  ROUND((120 + (g % 5000))::numeric, 2),
  ROUND((50000 + (g % 2500000))::numeric, 2),
  (date '2021-01-01' + ((g % 1700)))::date,
  (date '2021-01-01' + ((g % 1700)) + 365)::date,
  g % 4,
  (timestamp '2021-01-01' + ((g % 1700) || ' days')::interval + ((g % 20) || ' hours')::interval)
FROM generate_series(1, 2000000) g;
