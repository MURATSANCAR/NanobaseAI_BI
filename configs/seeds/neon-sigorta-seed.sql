-- Neon sigorta demo — gerçek dünyaya yakın TR sigorta OLTP
-- Hedef: milyonlarca satır, çok tablolu ilişkisel model

CREATE EXTENSION IF NOT EXISTS pgcrypto;

DROP SCHEMA IF EXISTS employees CASCADE;

DO $$
DECLARE r record;
BEGIN
  FOR r IN (
    SELECT tablename FROM pg_tables WHERE schemaname = 'public'
  ) LOOP
    EXECUTE format('DROP TABLE IF EXISTS public.%I CASCADE', r.tablename);
  END LOOP;
  FOR r IN (
    SELECT viewname FROM pg_views WHERE schemaname = 'public'
  ) LOOP
    EXECUTE format('DROP VIEW IF EXISTS public.%I CASCADE', r.viewname);
  END LOOP;
END $$;

-- ========== BOYUT / REFERANS ==========
CREATE TABLE bolgeler (
  id smallint PRIMARY KEY,
  kod text NOT NULL UNIQUE,
  ad text NOT NULL
);

CREATE TABLE iller (
  id smallint PRIMARY KEY,
  bolge_id smallint NOT NULL REFERENCES bolgeler(id),
  ad text NOT NULL
);

CREATE TABLE urunler (
  id smallint PRIMARY KEY,
  kod text NOT NULL UNIQUE,
  ad text NOT NULL,
  brans text NOT NULL, -- Kasko, Trafik, Konut, Sağlık, Hayat, DASK
  aktif boolean NOT NULL DEFAULT true
);

CREATE TABLE teminatlar (
  id smallint PRIMARY KEY,
  kod text NOT NULL UNIQUE,
  ad text NOT NULL,
  brans text NOT NULL
);

CREATE TABLE hasar_nedenleri (
  id smallint PRIMARY KEY,
  kod text NOT NULL UNIQUE,
  ad text NOT NULL,
  brans text NOT NULL
);

CREATE TABLE odeme_yontemleri (
  id smallint PRIMARY KEY,
  ad text NOT NULL UNIQUE
);

-- ========== ANA VARLIKLAR ==========
CREATE TABLE acenteler (
  id bigserial PRIMARY KEY,
  kod text NOT NULL UNIQUE,
  unvan text NOT NULL,
  bolge text NOT NULL,
  il_id smallint REFERENCES iller(id),
  komp_kodu text,
  komisyon_orani numeric(5,2) NOT NULL DEFAULT 15,
  aktif boolean NOT NULL DEFAULT true,
  created_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz
);

CREATE TABLE musteriler (
  id bigserial PRIMARY KEY,
  musteri_no text NOT NULL UNIQUE,
  tip text NOT NULL CHECK (tip IN ('Bireysel', 'Kurumsal')),
  ad text NOT NULL,
  soyad text,
  tckn_vkn text,
  dogum_tarihi date,
  cinsiyet text,
  email text,
  telefon text,
  il_id smallint REFERENCES iller(id),
  risk_skoru numeric(4,2),
  created_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz
);

CREATE TABLE araclar (
  id bigserial PRIMARY KEY,
  musteri_id bigint NOT NULL REFERENCES musteriler(id),
  plaka text NOT NULL,
  marka text NOT NULL,
  model text NOT NULL,
  model_yili int NOT NULL,
  kullanim_tarzi text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE konutlar (
  id bigserial PRIMARY KEY,
  musteri_id bigint NOT NULL REFERENCES musteriler(id),
  il_id smallint REFERENCES iller(id),
  yapi_tarzi text NOT NULL,
  metrekare int NOT NULL,
  deprem_bolgesi smallint,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE policeler (
  id bigserial PRIMARY KEY,
  police_no text NOT NULL UNIQUE,
  musteri_id bigint NOT NULL REFERENCES musteriler(id),
  acente_id bigint NOT NULL REFERENCES acenteler(id),
  urun_id smallint NOT NULL REFERENCES urunler(id),
  arac_id bigint REFERENCES araclar(id),
  konut_id bigint REFERENCES konutlar(id),
  durum text NOT NULL, -- Aktif, İptal, Süresi Doldu, Askıda
  prim_tutari numeric(14,2) NOT NULL,
  net_prim numeric(14,2) NOT NULL,
  vergi_tutari numeric(14,2) NOT NULL,
  komisyon_tutari numeric(14,2) NOT NULL,
  teminat_bedeli numeric(14,2) NOT NULL,
  baslangic_tarihi date NOT NULL,
  bitis_tarihi date NOT NULL,
  yenileme_no int NOT NULL DEFAULT 0,
  created_at timestamptz NOT NULL,
  deleted_at timestamptz
);

-- BI uyumluluk: bazı sorgular "poliçe_id" bekler
CREATE TABLE hasar_talepleri (
  id bigserial PRIMARY KEY,
  hasar_no text NOT NULL UNIQUE,
  "poliçe_id" bigint NOT NULL REFERENCES policeler(id),
  police_id bigint NOT NULL REFERENCES policeler(id),
  musteri_id bigint NOT NULL REFERENCES musteriler(id),
  acente_id bigint NOT NULL REFERENCES acenteler(id),
  neden_id smallint NOT NULL REFERENCES hasar_nedenleri(id),
  durum text NOT NULL, -- Açık, İncelemede, Onaylandı, Reddedildi, Ödendi, Fraud Şüpheli
  talep_tutari numeric(14,2) NOT NULL,
  onaylanan_tutar numeric(14,2),
  fraud_skoru numeric(5,4),
  ihbar_tarihi timestamptz NOT NULL,
  olay_tarihi date NOT NULL,
  kapama_tarihi timestamptz,
  created_at timestamptz NOT NULL DEFAULT now(),
  deleted_at timestamptz
);

CREATE TABLE hasar_belgeleri (
  id bigserial PRIMARY KEY,
  hasar_id bigint NOT NULL REFERENCES hasar_talepleri(id),
  belge_tipi text NOT NULL,
  dosya_adi text NOT NULL,
  yukleme_tarihi timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ekspertizler (
  id bigserial PRIMARY KEY,
  hasar_id bigint NOT NULL REFERENCES hasar_talepleri(id),
  eksper_adi text NOT NULL,
  rapor_no text NOT NULL,
  tespit_tutari numeric(14,2) NOT NULL,
  rapor_tarihi date NOT NULL,
  durum text NOT NULL
);

CREATE TABLE prim_odemeleri (
  id bigserial PRIMARY KEY,
  "poliçe_id" bigint NOT NULL REFERENCES policeler(id),
  police_id bigint NOT NULL REFERENCES policeler(id),
  taksit_no int NOT NULL,
  planlanan_tutar numeric(14,2) NOT NULL,
  planlanan_tarih date NOT NULL,
  odeme_tutari numeric(14,2),
  odeme_tarihi date,
  odeme_yontem_id smallint REFERENCES odeme_yontemleri(id),
  odeme_yontemi text,
  durum text NOT NULL, -- Ödendi, Bekliyor, Gecikmiş, İptal
  dekont_referans text,
  aciklama text,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE police_teminatlari (
  id bigserial PRIMARY KEY,
  police_id bigint NOT NULL REFERENCES policeler(id),
  teminat_id smallint NOT NULL REFERENCES teminatlar(id),
  limit_tutari numeric(14,2) NOT NULL,
  muafiyet_tutari numeric(14,2) NOT NULL DEFAULT 0,
  UNIQUE (police_id, teminat_id)
);

CREATE TABLE acente_hedefleri (
  id bigserial PRIMARY KEY,
  acente_id bigint NOT NULL REFERENCES acenteler(id),
  donem text NOT NULL,
  hedef_prim numeric(14,2) NOT NULL,
  hedef_police int NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (acente_id, donem)
);

CREATE TABLE komisyon_odemeleri (
  id bigserial PRIMARY KEY,
  acente_id bigint NOT NULL REFERENCES acenteler(id),
  police_id bigint NOT NULL REFERENCES policeler(id),
  donem text NOT NULL,
  tutar numeric(14,2) NOT NULL,
  durum text NOT NULL,
  odeme_tarihi date,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE police_notlari (
  id bigserial PRIMARY KEY,
  police_id bigint NOT NULL REFERENCES policeler(id),
  kullanici text NOT NULL,
  not_metni text NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE ihbar_kanallari (
  id smallint PRIMARY KEY,
  ad text NOT NULL UNIQUE
);

CREATE TABLE musteri_iletisim (
  id bigserial PRIMARY KEY,
  musteri_id bigint NOT NULL REFERENCES musteriler(id),
  kanal text NOT NULL,
  deger text NOT NULL,
  birincil boolean NOT NULL DEFAULT false
);

-- ========== VIEW'LAR (BI) ==========
CREATE OR REPLACE VIEW v_aktif_policeler AS
SELECT * FROM policeler WHERE durum = 'Aktif' AND deleted_at IS NULL;

CREATE OR REPLACE VIEW v_acente_performans_ozeti AS
SELECT
  a.id AS acente_id,
  a.unvan,
  a.bolge,
  a.komisyon_orani,
  a.aktif,
  COUNT(DISTINCT p.id) AS police_sayisi,
  COUNT(DISTINCT CASE WHEN p.durum = 'Aktif' THEN p.id END) AS aktif_police,
  COALESCE(SUM(p.prim_tutari), 0) AS toplam_prim,
  COALESCE(SUM(h.onaylanan_tutar), 0) AS toplam_hasar,
  COUNT(DISTINCT h.id) AS hasar_sayisi,
  COUNT(DISTINCT CASE WHEN h.durum = 'Fraud Şüpheli' THEN h.id END) AS fraud_supheli,
  ROUND(100.0 * COALESCE(SUM(h.onaylanan_tutar), 0) / NULLIF(SUM(p.prim_tutari), 0), 2) AS hasar_prim_orani_pct,
  ROUND(COALESCE(SUM(p.prim_tutari), 0) * a.komisyon_orani / 100.0, 2) AS tahmini_komisyon
FROM acenteler a
LEFT JOIN policeler p ON p.acente_id = a.id AND p.deleted_at IS NULL
LEFT JOIN hasar_talepleri h ON h.police_id = p.id AND h.deleted_at IS NULL
WHERE a.deleted_at IS NULL
GROUP BY a.id, a.unvan, a.bolge, a.komisyon_orani, a.aktif;

CREATE OR REPLACE VIEW v_bolge_yonetim_ozeti AS
SELECT
  a.bolge,
  COUNT(DISTINCT a.id) AS acente_sayisi,
  COUNT(DISTINCT p.id) AS police_sayisi,
  COALESCE(SUM(p.prim_tutari), 0) AS toplam_prim,
  COALESCE(SUM(h.onaylanan_tutar), 0) AS toplam_hasar,
  ROUND(AVG(a.komisyon_orani)::numeric, 2) AS ort_komisyon,
  ROUND(100.0 * COALESCE(SUM(h.onaylanan_tutar), 0) / NULLIF(SUM(p.prim_tutari), 0), 2) AS hasar_prim_orani_pct
FROM acenteler a
LEFT JOIN policeler p ON p.acente_id = a.id AND p.deleted_at IS NULL
LEFT JOIN hasar_talepleri h ON h.police_id = p.id AND h.deleted_at IS NULL
WHERE a.deleted_at IS NULL
GROUP BY a.bolge;

-- ========== SEED REFERANS ==========
INSERT INTO bolgeler (id, kod, ad) VALUES
 (1,'MARM','Marmara'),(2,'EGE','Ege'),(3,'AKDN','Akdeniz'),
 (4,'ICAN','İç Anadolu'),(5,'KSRA','Karadeniz'),(6,'DOGU','Doğu Anadolu'),(7,'GDOG','Güneydoğu');

INSERT INTO iller (id, bolge_id, ad) VALUES
 (34,1,'İstanbul'),(41,1,'Kocaeli'),(16,1,'Bursa'),(35,2,'İzmir'),(9,2,'Aydın'),
 (7,3,'Antalya'),(33,3,'Mersin'),(6,4,'Ankara'),(42,4,'Konya'),(55,5,'Samsun'),
 (61,5,'Trabzon'),(25,6,'Erzurum'),(44,6,'Malatya'),(21,7,'Diyarbakır'),(27,7,'Gaziantep');

INSERT INTO urunler (id, kod, ad, brans) VALUES
 (1,'KSK','Kasko Plus','Kasko'),
 (2,'TRF','Zorunlu Trafik','Trafik'),
 (3,'KNT','Konut Güvence','Konut'),
 (4,'SGL','Sağlık Tamamlayıcı','Sağlık'),
 (5,'HYT','Hayat Birikimli','Hayat'),
 (6,'DSK','DASK','DASK'),
 (7,'IMM','İşyeri Paket','Konut'),
 (8,'YKSK','Yüksek Kasko','Kasko');

INSERT INTO teminatlar (id, kod, ad, brans) VALUES
 (1,'CAM','Cam Kırılması','Kasko'),(2,'CAL','Çalınma','Kasko'),(3,'IMM','İmm','Trafik'),
 (4,'YK','Yangın','Konut'),(5,'SEL','Sel/Su','Konut'),(6,'DEP','Deprem','DASK'),
 (7,'YTR','Yatarak Tedavi','Sağlık'),(8,'ATR','Ayakta Tedavi','Sağlık'),(9,'VFT','Vefat','Hayat');

INSERT INTO hasar_nedenleri (id, kod, ad, brans) VALUES
 (1,'CRD','Çarpışma','Kasko'),(2,'PRK','Park Halinde Hasar','Kasko'),(3,'CAL','Hırsızlık','Kasko'),
 (4,'YNG','Yangın','Konut'),(5,'SU','Su Baskını','Konut'),(6,'DEP','Deprem','DASK'),
 (7,'AMEL','Ameliyat','Sağlık'),(8,'ILC','İlaç/Tedavi','Sağlık'),(9,'TRF','Trafik Kazası','Trafik');

INSERT INTO odeme_yontemleri (id, ad) VALUES
 (1,'Kredi Kartı'),(2,'Banka Havalesi/EFT'),(3,'Otomatik Ödeme'),(4,'Nakit'),(5,'Dijital Cüzdan');

INSERT INTO ihbar_kanallari (id, ad) VALUES
 (1,'Mobil App'),(2,'Çağrı Merkezi'),(3,'Acente'),(4,'Web'),(5,'WhatsApp');

-- Acenteler (~2.500)
INSERT INTO acenteler (kod, unvan, bolge, il_id, komp_kodu, komisyon_orani, aktif, created_at)
SELECT
  'ACN-' || lpad(g::text, 5, '0'),
  (ARRAY['Anadolu','Başak','Yıldız','Marmara','Ege','Akdeniz','Kapadokya','Karadeniz','Doğu','Güneş'])[1 + (g % 10)]
    || ' Sigorta Acenteliği ' || g,
  (ARRAY['Marmara','Ege','Akdeniz','İç Anadolu','Karadeniz','Doğu Anadolu','Güneydoğu'])[1 + (g % 7)],
  (ARRAY[34,41,16,35,9,7,33,6,42,55,61,25,44,21,27])[1 + (g % 15)],
  'KMP-' || (100 + (g % 40)),
  10 + (g % 12) + ((g % 7) * 0.25),
  (g % 17) <> 0,
  timestamp '2020-01-01' + ((g % 1800) || ' days')::interval
FROM generate_series(1, 2500) g;

-- Müşteriler (500.000)
INSERT INTO musteriler (musteri_no, tip, ad, soyad, tckn_vkn, dogum_tarihi, cinsiyet, email, telefon, il_id, risk_skoru, created_at)
SELECT
  'MST-' || lpad(g::text, 8, '0'),
  CASE WHEN g % 9 = 0 THEN 'Kurumsal' ELSE 'Bireysel' END,
  (ARRAY['Ahmet','Mehmet','Ayşe','Fatma','Ali','Zeynep','Mustafa','Elif','Hüseyin','Emine','Can','Deniz','Burak','Selin','Cem'])[1 + (g % 15)],
  CASE WHEN g % 9 = 0 THEN NULL ELSE (ARRAY['Yılmaz','Kaya','Demir','Çelik','Şahin','Yıldız','Aydın','Öztürk','Arslan','Doğan','Kılıç','Aslan','Koç','Polat','Kurt'])[1 + (g % 15)] END,
  lpad(((g::bigint * 7919) % 100000000000)::text, 11, '0'),
  date '1955-01-01' + ((g * 37) % 20000),
  CASE WHEN g % 2 = 0 THEN 'E' ELSE 'K' END,
  'm' || g || '@ornekmail.com',
  '053' || lpad(((g::bigint * 13) % 100000000)::text, 8, '0'),
  (ARRAY[34,41,16,35,9,7,33,6,42,55,61,25,44,21,27])[1 + (g % 15)],
  ROUND((1 + (g % 900) / 100.0)::numeric, 2),
  timestamp '2019-01-01' + ((g % 2200) || ' days')::interval
FROM generate_series(1, 500000) g;
