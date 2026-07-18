-- Neon 512MB kotasına sığan yoğun sigorta modeli
SET statement_timeout = 0;

TRUNCATE
  hasar_belgeleri, ekspertizler, hasar_talepleri,
  prim_odemeleri, police_teminatlari, komisyon_odemeleri, police_notlari,
  acente_hedefleri, musteri_iletisim,
  policeler, araclar, konutlar, musteriler, acenteler
RESTART IDENTITY CASCADE;

-- ~1.200 acente
INSERT INTO acenteler (kod, unvan, bolge, il_id, komp_kodu, komisyon_orani, aktif, created_at)
SELECT
  'ACN-' || lpad(g::text, 5, '0'),
  (ARRAY['Anadolu','Başak','Yıldız','Marmara','Ege','Akdeniz','Kapadokya','Karadeniz','Doğu','Güneş'])[1+(g%10)]
    || ' Sigorta Acenteliği ' || g,
  (ARRAY['Marmara','Ege','Akdeniz','İç Anadolu','Karadeniz','Doğu Anadolu','Güneydoğu'])[1+(g%7)],
  (ARRAY[34,41,16,35,9,7,33,6,42,55,61,25,44,21,27])[1+(g%15)],
  'KMP-' || (100+(g%40)),
  10 + (g%12) + ((g%7)*0.25),
  (g%17)<>0,
  timestamp '2020-01-01' + ((g%1800)||' days')::interval
FROM generate_series(1,1200) g;

-- 80.000 müşteri (daha dar satır)
INSERT INTO musteriler (musteri_no, tip, ad, soyad, tckn_vkn, dogum_tarihi, cinsiyet, email, telefon, il_id, risk_skoru, created_at)
SELECT
  'MST-' || lpad(g::text, 7, '0'),
  CASE WHEN g%9=0 THEN 'Kurumsal' ELSE 'Bireysel' END,
  (ARRAY['Ahmet','Mehmet','Ayşe','Fatma','Ali','Zeynep','Mustafa','Elif','Hüseyin','Emine','Can','Deniz','Burak','Selin','Cem'])[1+(g%15)],
  CASE WHEN g%9=0 THEN NULL ELSE (ARRAY['Yılmaz','Kaya','Demir','Çelik','Şahin','Yıldız','Aydın','Öztürk','Arslan','Doğan','Kılıç','Aslan','Koç','Polat','Kurt'])[1+(g%15)] END,
  lpad(((g::bigint*7919)%100000000000)::text, 11, '0'),
  date '1955-01-01' + ((g*37)%20000),
  CASE WHEN g%2=0 THEN 'E' ELSE 'K' END,
  'u'||g||'@m.com',
  '05'||lpad(((g::bigint*13)%1000000000)::text,9,'0'),
  (ARRAY[34,41,16,35,9,7,33,6,42,55,61,25,44,21,27])[1+(g%15)],
  ROUND((1+(g%900)/100.0)::numeric,2),
  timestamp '2019-01-01' + ((g%2000)||' days')::interval
FROM generate_series(1,80000) g;

INSERT INTO araclar (musteri_id, plaka, marka, model, model_yili, kullanim_tarzi, created_at)
SELECT m.id,
  (ARRAY['34','06','35','16','07'])[1+(m.id%5)]||' ABC '||lpad((m.id%900)::text,3,'0'),
  (ARRAY['Toyota','VW','Renault','Fiat','Ford','Hyundai'])[1+(m.id%6)],
  (ARRAY['Corolla','Golf','Clio','Egea','Focus','i20'])[1+(m.id%6)],
  2010+(m.id%15),
  CASE WHEN m.id%11=0 THEN 'Ticari' ELSE 'Hususi' END,
  m.created_at
FROM musteriler m WHERE m.id <= 55000;

INSERT INTO konutlar (musteri_id, il_id, yapi_tarzi, metrekare, deprem_bolgesi, created_at)
SELECT m.id, m.il_id,
  (ARRAY['Betonarme','Yığma','Çelik'])[1+(m.id%3)],
  70+(m.id%180), 1+(m.id%5), m.created_at
FROM musteriler m WHERE m.id <= 40000;
