-- ERP (ticari) — yoğun ilişkisel model, Neon 512MB kotasına göre ayarlı
SET statement_timeout = 0;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

DO $$
DECLARE r record;
BEGIN
  FOR r IN (SELECT tablename FROM pg_tables WHERE schemaname='public') LOOP
    EXECUTE format('DROP TABLE IF EXISTS public.%I CASCADE', r.tablename);
  END LOOP;
  FOR r IN (SELECT viewname FROM pg_views WHERE schemaname='public') LOOP
    EXECUTE format('DROP VIEW IF EXISTS public.%I CASCADE', r.viewname);
  END LOOP;
END $$;

-- ===== REFERANS =====
CREATE TABLE ulkeler (id smallint PRIMARY KEY, kod text UNIQUE, ad text);
CREATE TABLE iller (id smallint PRIMARY KEY, ulke_id smallint REFERENCES ulkeler(id), ad text);
CREATE TABLE para_birimleri (id smallint PRIMARY KEY, kod text UNIQUE, ad text);
CREATE TABLE odeme_kosullari (id smallint PRIMARY KEY, kod text UNIQUE, ad text, gun int);
CREATE TABLE birimler (id smallint PRIMARY KEY, kod text UNIQUE, ad text);

CREATE TABLE sirketler (
  id smallserial PRIMARY KEY, kod text UNIQUE, unvan text, vergi_no text, created_at timestamptz DEFAULT now()
);
CREATE TABLE subeler (
  id smallserial PRIMARY KEY, sirket_id smallint REFERENCES sirketler(id),
  kod text, ad text, il_id smallint REFERENCES iller(id)
);
CREATE TABLE depolar (
  id smallserial PRIMARY KEY, sube_id smallint REFERENCES subeler(id),
  kod text, ad text
);
CREATE TABLE departmanlar (
  id smallserial PRIMARY KEY, sirket_id smallint REFERENCES sirketler(id), kod text, ad text
);
CREATE TABLE personeller (
  id serial PRIMARY KEY, sube_id smallint REFERENCES subeler(id), departman_id smallint REFERENCES departmanlar(id),
  sicil_no text UNIQUE, ad text, soyad text, unvan text, ise_giris date, aktif boolean DEFAULT true
);

CREATE TABLE musteri_gruplari (id smallserial PRIMARY KEY, kod text UNIQUE, ad text);
CREATE TABLE musteriler (
  id serial PRIMARY KEY, grup_id smallint REFERENCES musteri_gruplari(id),
  musteri_no text UNIQUE, tip text, unvan text, vergi_no text, il_id smallint REFERENCES iller(id),
  email text, telefon text, risk_limit numeric(14,2), aktif boolean DEFAULT true, created_at timestamptz
);
CREATE TABLE musteri_adresleri (
  id serial PRIMARY KEY, musteri_id int REFERENCES musteriler(id), tip text, adres text, il_id smallint REFERENCES iller(id), birincil boolean DEFAULT false
);

CREATE TABLE tedarikci_gruplari (id smallserial PRIMARY KEY, kod text UNIQUE, ad text);
CREATE TABLE tedarikciler (
  id serial PRIMARY KEY, grup_id smallint REFERENCES tedarikci_gruplari(id),
  tedarikci_no text UNIQUE, unvan text, vergi_no text, il_id smallint REFERENCES iller(id),
  email text, telefon text, aktif boolean DEFAULT true, created_at timestamptz
);

CREATE TABLE urun_kategorileri (
  id smallserial PRIMARY KEY, parent_id smallint, kod text UNIQUE, ad text
);
CREATE TABLE markalar (id smallserial PRIMARY KEY, kod text UNIQUE, ad text);
CREATE TABLE urunler (
  id serial PRIMARY KEY, kategori_id smallint REFERENCES urun_kategorileri(id), marka_id smallint REFERENCES markalar(id),
  stok_kodu text UNIQUE, ad text, birim_id smallint REFERENCES birimler(id),
  alis_fiyat numeric(14,2), satis_fiyat numeric(14,2), kdv_orani numeric(5,2), aktif boolean DEFAULT true, created_at timestamptz
);
CREATE TABLE stok_bakiyeleri (
  id bigserial PRIMARY KEY, depo_id smallint REFERENCES depolar(id), urun_id int REFERENCES urunler(id),
  miktar numeric(14,3), rezervasyon numeric(14,3) DEFAULT 0,
  UNIQUE(depo_id, urun_id)
);

CREATE TABLE siparis_durumlari (id smallint PRIMARY KEY, kod text UNIQUE, ad text);

-- Satış
CREATE TABLE satis_siparisleri (
  id bigserial PRIMARY KEY, siparis_no text UNIQUE, musteri_id int REFERENCES musteriler(id),
  sube_id smallint REFERENCES subeler(id), personel_id int REFERENCES personeller(id),
  durum_id smallint REFERENCES siparis_durumlari(id), para_id smallint REFERENCES para_birimleri(id),
  siparis_tarihi date, teslim_tarihi date, ara_toplam numeric(14,2), kdv_toplam numeric(14,2),
  genel_toplam numeric(14,2), created_at timestamptz
);
CREATE TABLE satis_siparis_kalemleri (
  id bigserial PRIMARY KEY, siparis_id bigint REFERENCES satis_siparisleri(id),
  urun_id int REFERENCES urunler(id), miktar numeric(14,3), birim_fiyat numeric(14,2),
  kdv_orani numeric(5,2), tutar numeric(14,2)
);

CREATE TABLE faturalar (
  id bigserial PRIMARY KEY, fatura_no text UNIQUE, musteri_id int REFERENCES musteriler(id),
  siparis_id bigint REFERENCES satis_siparisleri(id), sube_id smallint REFERENCES subeler(id),
  tip text, durum text, fatura_tarihi date, vade_tarihi date,
  ara_toplam numeric(14,2), kdv_toplam numeric(14,2), genel_toplam numeric(14,2), created_at timestamptz
);
CREATE TABLE fatura_kalemleri (
  id bigserial PRIMARY KEY, fatura_id bigint REFERENCES faturalar(id),
  urun_id int REFERENCES urunler(id), miktar numeric(14,3), birim_fiyat numeric(14,2),
  kdv_orani numeric(5,2), tutar numeric(14,2)
);

CREATE TABLE tahsilatlar (
  id bigserial PRIMARY KEY, tahsilat_no text UNIQUE, musteri_id int REFERENCES musteriler(id),
  fatura_id bigint REFERENCES faturalar(id), tutar numeric(14,2), odeme_tarihi date,
  yontem text, durum text, created_at timestamptz
);

CREATE TABLE sevkiyatlar (
  id bigserial PRIMARY KEY, sevkiyat_no text UNIQUE, siparis_id bigint REFERENCES satis_siparisleri(id),
  depo_id smallint REFERENCES depolar(id), durum text, sevk_tarihi date, created_at timestamptz
);
CREATE TABLE sevkiyat_kalemleri (
  id bigserial PRIMARY KEY, sevkiyat_id bigint REFERENCES sevkiyatlar(id),
  urun_id int REFERENCES urunler(id), miktar numeric(14,3)
);

-- Satınalma
CREATE TABLE satin_alma_siparisleri (
  id bigserial PRIMARY KEY, siparis_no text UNIQUE, tedarikci_id int REFERENCES tedarikciler(id),
  sube_id smallint REFERENCES subeler(id), durum_id smallint REFERENCES siparis_durumlari(id),
  siparis_tarihi date, ara_toplam numeric(14,2), kdv_toplam numeric(14,2), genel_toplam numeric(14,2), created_at timestamptz
);
CREATE TABLE satin_alma_kalemleri (
  id bigserial PRIMARY KEY, siparis_id bigint REFERENCES satin_alma_siparisleri(id),
  urun_id int REFERENCES urunler(id), miktar numeric(14,3), birim_fiyat numeric(14,2), tutar numeric(14,2)
);

-- Alış faturaları (AP) — OPEX/CAPEX gerçekleşen harcama kaynağı
CREATE TABLE alis_faturalari (
  id bigserial PRIMARY KEY,
  fatura_no text UNIQUE,
  tedarikci_id int REFERENCES tedarikciler(id),
  siparis_id bigint REFERENCES satin_alma_siparisleri(id),
  sube_id smallint REFERENCES subeler(id),
  butce_kodu text,
  departman_kod text,
  durum text DEFAULT 'acik',
  fatura_tarihi date,
  vade_tarihi date,
  ara_toplam numeric(14,2),
  kdv_toplam numeric(14,2),
  genel_toplam numeric(14,2),
  created_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_alis_faturalari_butce ON alis_faturalari (butce_kodu);
CREATE INDEX IF NOT EXISTS ix_alis_faturalari_tarih ON alis_faturalari (fatura_tarihi);

CREATE TABLE alis_fatura_kalemleri (
  id bigserial PRIMARY KEY,
  alis_fatura_id bigint REFERENCES alis_faturalari(id),
  aciklama text,
  butce_kodu text,
  miktar numeric(14,3),
  birim_fiyat numeric(14,2),
  kdv_orani numeric(5,2),
  tutar numeric(14,2)
);

-- Bütçe plan kalemleri (OPEX / CAPEX)
CREATE TABLE butce_planlari (
  id bigserial PRIMARY KEY,
  mali_yil integer NOT NULL,
  departman_kod text NOT NULL,
  butce_kodu text NOT NULL,
  kalem_adi text NOT NULL,
  tur text NOT NULL DEFAULT 'OPEX',
  planlanan_tutar numeric(18,2) NOT NULL,
  para_birimi text NOT NULL DEFAULT 'TRY',
  created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_butce_planlari_yil ON butce_planlari (mali_yil);
CREATE INDEX IF NOT EXISTS ix_butce_planlari_kod ON butce_planlari (butce_kodu);

CREATE TABLE stok_hareketleri (
  id bigserial PRIMARY KEY, depo_id smallint REFERENCES depolar(id), urun_id int REFERENCES urunler(id),
  hareket_tipi text, miktar numeric(14,3), referans_no text, hareket_tarihi date, created_at timestamptz
);

-- Muhasebe hafif
CREATE TABLE hesap_planlari (
  id serial PRIMARY KEY, kod text UNIQUE, ad text, tip text, aktif boolean DEFAULT true
);
CREATE TABLE yevmiye_fisleri (
  id bigserial PRIMARY KEY, fis_no text UNIQUE, fis_tarihi date, aciklama text, created_at timestamptz
);
CREATE TABLE yevmiye_kalemleri (
  id bigserial PRIMARY KEY, fis_id bigint REFERENCES yevmiye_fisleri(id),
  hesap_id int REFERENCES hesap_planlari(id), borc numeric(14,2) DEFAULT 0, alacak numeric(14,2) DEFAULT 0
);

CREATE TABLE fiyat_listeleri (
  id serial PRIMARY KEY, kod text UNIQUE, ad text, para_id smallint REFERENCES para_birimleri(id), aktif boolean DEFAULT true
);
CREATE TABLE fiyat_listesi_kalemleri (
  id bigserial PRIMARY KEY, liste_id int REFERENCES fiyat_listeleri(id), urun_id int REFERENCES urunler(id),
  fiyat numeric(14,2), UNIQUE(liste_id, urun_id)
);

-- ===== SEED REFERANS =====
INSERT INTO ulkeler VALUES (1,'TR','Türkiye');
INSERT INTO iller VALUES
 (34,1,'İstanbul'),(6,1,'Ankara'),(35,1,'İzmir'),(16,1,'Bursa'),(7,1,'Antalya'),
 (41,1,'Kocaeli'),(33,1,'Mersin'),(42,1,'Konya'),(55,1,'Samsun'),(27,1,'Gaziantep');
INSERT INTO para_birimleri VALUES (1,'TRY','Türk Lirası'),(2,'USD','Amerikan Doları'),(3,'EUR','Euro');
INSERT INTO odeme_kosullari VALUES (1,'PESIN','Peşin',0),(2,'30G','30 Gün',30),(3,'60G','60 Gün',60),(4,'90G','90 Gün',90);
INSERT INTO birimler VALUES (1,'AD','Adet'),(2,'KG','Kilogram'),(3,'KT','Kutu'),(4,'LT','Litre'),(5,'MT','Metre');
INSERT INTO siparis_durumlari VALUES (1,'DRAFT','Taslak'),(2,'ONAY','Onaylandı'),(3,'SEVK','Sevkedildi'),(4,'FAT','Faturalandı'),(5,'IPTAL','İptal'),(6,'KAPALI','Kapalı');

INSERT INTO sirketler (kod, unvan, vergi_no) VALUES ('NB','Nanobase Ticaret A.Ş.','1234567890');
INSERT INTO subeler (sirket_id, kod, ad, il_id)
SELECT 1, 'SB'||g, 'Şube '||g, (ARRAY[34,6,35,16,7,41,33,42,55,27])[1+(g%10)]
FROM generate_series(1,12) g;
INSERT INTO depolar (sube_id, kod, ad)
SELECT s.id, 'DP'||s.id||'-'||d, 'Depo '||d
FROM subeler s CROSS JOIN generate_series(1,3) d;
INSERT INTO departmanlar (sirket_id, kod, ad) VALUES
 (1,'SAT','Satış'),(1,'SIN','Satınalma'),(1,'STK','Stok'),(1,'MUH','Muhasebe'),(1,'IK','İK'),(1,'LOJ','Lojistik'),
 (1,'IT','Bilgi Teknolojileri');

INSERT INTO personeller (sube_id, departman_id, sicil_no, ad, soyad, unvan, ise_giris, aktif)
SELECT 1+((g-1)%12), 1+((g-1)%6), 'P'||lpad(g::text,5,'0'),
  (ARRAY['Ahmet','Ayşe','Mehmet','Fatma','Can','Elif','Burak','Zeynep'])[1+(g%8)],
  (ARRAY['Yılmaz','Kaya','Demir','Çelik','Şahin','Aydın'])[1+(g%6)],
  (ARRAY['Uzman','Yetkili','Müdür','Temsilci'])[1+(g%4)],
  date '2018-01-01' + ((g%2000)), true
FROM generate_series(1,400) g;

INSERT INTO musteri_gruplari (kod, ad) VALUES ('A','Premium'),('B','Standart'),('C','Ekonomik'),('K','Kurumsal');
INSERT INTO tedarikci_gruplari (kod, ad) VALUES ('YER','Yerli'),('ITH','İthal'),('KR','Kritik');
INSERT INTO markalar (kod, ad)
SELECT 'M'||g, 'Marka '||g FROM generate_series(1,40) g;
INSERT INTO urun_kategorileri (id, parent_id, kod, ad) VALUES
 (1,NULL,'ELK','Elektronik'),(2,NULL,'GDA','Gıda'),(3,NULL,'TX','Tekstil'),(4,NULL,'OTM','Otomotiv'),
 (5,1,'ELK-PC','Bilgisayar'),(6,1,'ELK-TV','TV/AV'),(7,2,'GDA-SC','Su/içecek'),(8,3,'TX-GIY','Giyim');

-- IT tedarikçileri + OPEX/CAPEX plan + gelen alış faturaları (match demosu)
INSERT INTO tedarikciler (grup_id, tedarikci_no, unvan, vergi_no, il_id, email, telefon, aktif, created_at)
VALUES
 (1,'T-AWS','AWS Cloud Türkiye','1111111111',34,'aws@example.com','',true,now()),
 (1,'T-MSFT','Microsoft Türkiye','2222222222',34,'ms@example.com','',true,now()),
 (2,'T-DELL','Dell Technologies','3333333333',6,'dell@example.com','',true,now()),
 (1,'T-TT','Türk Telekom','4444444444',6,'tt@example.com','',true,now()),
 (3,'T-CONS','IT Danışmanlık A.Ş.','5555555555',34,'cons@example.com','',true,now());

INSERT INTO butce_planlari (mali_yil, departman_kod, butce_kodu, kalem_adi, tur, planlanan_tutar) VALUES
 (2026,'IT-OPEX','IT-CLOUD','Bulut altyapı (IaaS/PaaS)','OPEX',1800000),
 (2026,'IT-OPEX','IT-SAAS','SaaS abonelikleri','OPEX',720000),
 (2026,'IT-OPEX','IT-LICENSE','Yazılım lisans / bakım','OPEX',950000),
 (2026,'IT-OPEX','IT-SUPPORT','Destek ve managed service','OPEX',480000),
 (2026,'IT-OPEX','IT-TELCO','Telekom / hat','OPEX',240000),
 (2026,'IT-OPEX','IT-CONTRACTOR','IT danışman / contractor','OPEX',600000),
 (2026,'IT-CAPEX','IT-HW','Sunucu / network donanımı','CAPEX',2500000),
 (2026,'IT-CAPEX','IT-ENDPOINT','Uç nokta / notebook yenileme','CAPEX',900000),
 (2026,'IT-CAPEX','IT-SW-CAP','Büyük yazılım aktivasyonu','CAPEX',1500000),
 (2025,'IT-OPEX','IT-CLOUD','Bulut altyapı (IaaS/PaaS)','OPEX',1500000),
 (2025,'IT-CAPEX','IT-HW','Sunucu / network donanımı','CAPEX',2000000);

INSERT INTO alis_faturalari
  (fatura_no, tedarikci_id, sube_id, butce_kodu, departman_kod, durum, fatura_tarihi, vade_tarihi,
   ara_toplam, kdv_toplam, genel_toplam)
SELECT
  v.fatura_no, t.id, 1, v.butce_kodu, v.departman_kod, 'odendi', v.fatura_tarihi::date,
  (v.fatura_tarihi::date + 30), v.ara, v.kdv, v.genel
FROM (VALUES
  ('AF-2026-0001','T-AWS','IT-CLOUD','IT-OPEX','2026-02-15', 420000.00, 75600.00, 495600.00),
  ('AF-2026-0002','T-AWS','IT-CLOUD','IT-OPEX','2026-05-12', 380000.00, 68400.00, 448400.00),
  ('AF-2026-0003','T-MSFT','IT-SAAS','IT-OPEX','2026-01-20', 180000.00, 32400.00, 212400.00),
  ('AF-2026-0004','T-MSFT','IT-LICENSE','IT-OPEX','2026-03-01', 310000.00, 55800.00, 365800.00),
  ('AF-2026-0005','T-TT','IT-TELCO','IT-OPEX','2026-04-05', 45000.00, 8100.00, 53100.00),
  ('AF-2026-0006','T-CONS','IT-CONTRACTOR','IT-OPEX','2026-06-10', 220000.00, 39600.00, 259600.00),
  ('AF-2026-0007','T-CONS','IT-SUPPORT','IT-OPEX','2026-02-28', 95000.00, 17100.00, 112100.00),
  ('AF-2026-0008','T-DELL','IT-HW','IT-CAPEX','2026-03-18', 980000.00, 176400.00, 1156400.00),
  ('AF-2026-0009','T-DELL','IT-ENDPOINT','IT-CAPEX','2026-05-22', 320000.00, 57600.00, 377600.00),
  ('AF-2026-0010','T-MSFT','IT-SW-CAP','IT-CAPEX','2026-04-30', 650000.00, 117000.00, 767000.00),
  ('AF-2025-0099','T-AWS','IT-CLOUD','IT-OPEX','2025-11-10', 200000.00, 36000.00, 236000.00)
) AS v(fatura_no, tedarikci_no, butce_kodu, departman_kod, fatura_tarihi, ara, kdv, genel)
JOIN tedarikciler t ON t.tedarikci_no = v.tedarikci_no;

INSERT INTO alis_fatura_kalemleri (alis_fatura_id, aciklama, butce_kodu, miktar, birim_fiyat, kdv_orani, tutar)
SELECT f.id, 'Kalem — '||f.butce_kodu, f.butce_kodu, 1, f.ara_toplam, 18, f.ara_toplam
FROM alis_faturalari f;
