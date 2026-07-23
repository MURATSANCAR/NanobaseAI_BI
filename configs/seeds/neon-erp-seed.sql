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
 (1,'IT','Bilgi Teknolojileri'),
 (1,'IT-OPEX','BT İşletme Giderleri'),(1,'IT-CAPEX','BT Yatırım Giderleri');

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

-- BT tedarikçileri + gerçek dünya OPEX/CAPEX planı + YTD alış faturaları
-- planlanan_tutar ≈ yıllık brüt (KDV dahil); actuals SUM(alis_faturalari.genel_toplam)
INSERT INTO tedarikciler (grup_id, tedarikci_no, unvan, vergi_no, il_id, email, telefon, aktif, created_at)
VALUES
 (2,'T-AWS','Amazon Web Services EMEA SARL','1111111111',34,'aws-tr@example.com','2125550101',true,now()),
 (2,'T-AZURE','Microsoft Azure / Türkiye','2222222222',34,'azure-tr@example.com','2125550102',true,now()),
 (2,'T-GCP','Google Cloud Türkiye','2222222233',34,'gcp-tr@example.com','2125550103',true,now()),
 (1,'T-MSFT','Microsoft Türkiye (M365/Lisans)','2222222244',34,'msft-tr@example.com','2125550104',true,now()),
 (2,'T-DELL','Dell Technologies Türkiye','3333333333',6,'dell-tr@example.com','3125550201',true,now()),
 (2,'T-CISCO','Cisco Systems Türkiye','3333333344',34,'cisco-tr@example.com','2125550202',true,now()),
 (2,'T-FTNT','Fortinet Türkiye','3333333355',34,'fortinet-tr@example.com','2125550203',true,now()),
 (1,'T-TT','Türk Telekom','4444444444',6,'kurumsal@turktelekom.example','3125550301',true,now()),
 (1,'T-TCELL','Turkcell Superonline','4444444455',34,'kurumsal@turkcell.example','2125550302',true,now()),
 (3,'T-CONS','Nanobase IT Danışmanlık A.Ş.','5555555555',34,'ops@itcons.example','2125550401',true,now()),
 (3,'T-MSSP','CyberShield MSSP A.Ş.','5555555566',34,'soc@cybershield.example','2125550402',true,now()),
 (2,'T-ATLAS','Atlassian Pty Ltd','6666666666',34,'billing@atlassian.example','',true,now()),
 (2,'T-VEEAM','Veeam Software','6666666677',6,'tr@veeam.example','',true,now()),
 (1,'T-DC','Equinix Istanbul Colocation','7777777777',34,'tr@equinix.example','2125550501',true,now());

INSERT INTO butce_planlari (mali_yil, departman_kod, butce_kodu, kalem_adi, tur, planlanan_tutar, para_birimi) VALUES
 -- 2026 OPEX (~9.8M TRY brüt)
 (2026,'IT-OPEX','IT-CLOUD','Bulut altyapı (AWS/Azure/GCP IaaS-PaaS)','OPEX',2880000,'TRY'),
 (2026,'IT-OPEX','IT-SAAS','SaaS abonelikleri (M365, Atlassian, Slack vb.)','OPEX',1152000,'TRY'),
 (2026,'IT-OPEX','IT-LICENSE','Yazılım lisans / yıllık bakım','OPEX',1320000,'TRY'),
 (2026,'IT-OPEX','IT-SEC','Siber güvenlik (EDR, SIEM, SOC, WAF)','OPEX',864000,'TRY'),
 (2026,'IT-OPEX','IT-BACKUP','Yedekleme / felaket kurtarma (DR)','OPEX',432000,'TRY'),
 (2026,'IT-OPEX','IT-SUPPORT','Destek ve managed service','OPEX',648000,'TRY'),
 (2026,'IT-OPEX','IT-TELCO','Telekom / MPLS / internet hatları','OPEX',360000,'TRY'),
 (2026,'IT-OPEX','IT-CONTRACTOR','IT danışman / contractor','OPEX',864000,'TRY'),
 (2026,'IT-OPEX','IT-TRAIN','Eğitim / sertifikasyon','OPEX',216000,'TRY'),
 (2026,'IT-OPEX','IT-DC','Veri merkezi / colocation kira','OPEX',576000,'TRY'),
 -- 2026 CAPEX (~7.9M TRY brüt)
 (2026,'IT-CAPEX','IT-HW','Sunucu / storage / network donanımı','CAPEX',3360000,'TRY'),
 (2026,'IT-CAPEX','IT-ENDPOINT','Uç nokta / notebook yenileme','CAPEX',1440000,'TRY'),
 (2026,'IT-CAPEX','IT-SW-CAP','Büyük yazılım aktivasyonu (ERP/CRM)','CAPEX',2160000,'TRY'),
 (2026,'IT-CAPEX','IT-SEC-HW','Güvenlik cihazları (firewall, NGFW)','CAPEX',1080000,'TRY'),
 (2026,'IT-CAPEX','IT-NET','Ağ modernizasyonu (Wi-Fi / switch)','CAPEX',900000,'TRY'),
 -- 2025 karşılaştırma
 (2025,'IT-OPEX','IT-CLOUD','Bulut altyapı (IaaS/PaaS)','OPEX',2160000,'TRY'),
 (2025,'IT-OPEX','IT-SAAS','SaaS abonelikleri','OPEX',864000,'TRY'),
 (2025,'IT-OPEX','IT-SEC','Siber güvenlik','OPEX',600000,'TRY'),
 (2025,'IT-CAPEX','IT-HW','Sunucu / network donanımı','CAPEX',2400000,'TRY'),
 (2025,'IT-CAPEX','IT-ENDPOINT','Uç nokta yenileme','CAPEX',960000,'TRY');

-- YTD (Oca–Tem 2026) gerçekleşen AP + 2025 kapanış; KDV %20
INSERT INTO alis_faturalari
  (fatura_no, tedarikci_id, sube_id, butce_kodu, departman_kod, durum, fatura_tarihi, vade_tarihi,
   ara_toplam, kdv_toplam, genel_toplam)
SELECT
  v.fatura_no, t.id, 1, v.butce_kodu, v.departman_kod, v.durum, v.fatura_tarihi::date,
  (v.fatura_tarihi::date + 30), v.ara, v.kdv, v.genel
FROM (VALUES
  -- IT-CLOUD aylık (AWS + Azure + GCP)
  ('AF-2026-CL-01','T-AWS','IT-CLOUD','IT-OPEX','odendi','2026-01-28', 145000.00, 29000.00, 174000.00),
  ('AF-2026-CL-02','T-AZURE','IT-CLOUD','IT-OPEX','odendi','2026-01-29', 98000.00, 19600.00, 117600.00),
  ('AF-2026-CL-03','T-AWS','IT-CLOUD','IT-OPEX','odendi','2026-02-28', 152000.00, 30400.00, 182400.00),
  ('AF-2026-CL-04','T-AZURE','IT-CLOUD','IT-OPEX','odendi','2026-02-27', 101000.00, 20200.00, 121200.00),
  ('AF-2026-CL-05','T-GCP','IT-CLOUD','IT-OPEX','odendi','2026-03-15', 42000.00, 8400.00, 50400.00),
  ('AF-2026-CL-06','T-AWS','IT-CLOUD','IT-OPEX','odendi','2026-03-28', 168000.00, 33600.00, 201600.00),
  ('AF-2026-CL-07','T-AZURE','IT-CLOUD','IT-OPEX','odendi','2026-03-29', 110000.00, 22000.00, 132000.00),
  ('AF-2026-CL-08','T-AWS','IT-CLOUD','IT-OPEX','odendi','2026-04-28', 175000.00, 35000.00, 210000.00),
  ('AF-2026-CL-09','T-AZURE','IT-CLOUD','IT-OPEX','odendi','2026-04-27', 108000.00, 21600.00, 129600.00),
  ('AF-2026-CL-10','T-AWS','IT-CLOUD','IT-OPEX','odendi','2026-05-28', 181000.00, 36200.00, 217200.00),
  ('AF-2026-CL-11','T-AZURE','IT-CLOUD','IT-OPEX','odendi','2026-05-29', 115000.00, 23000.00, 138000.00),
  ('AF-2026-CL-12','T-GCP','IT-CLOUD','IT-OPEX','odendi','2026-06-12', 48000.00, 9600.00, 57600.00),
  ('AF-2026-CL-13','T-AWS','IT-CLOUD','IT-OPEX','odendi','2026-06-28', 190000.00, 38000.00, 228000.00),
  ('AF-2026-CL-14','T-AZURE','IT-CLOUD','IT-OPEX','odendi','2026-06-27', 119000.00, 23800.00, 142800.00),
  ('AF-2026-CL-15','T-AWS','IT-CLOUD','IT-OPEX','acik','2026-07-20', 198000.00, 39600.00, 237600.00),
  ('AF-2026-CL-16','T-AZURE','IT-CLOUD','IT-OPEX','acik','2026-07-21', 122000.00, 24400.00, 146400.00),
  -- IT-SAAS
  ('AF-2026-SA-01','T-MSFT','IT-SAAS','IT-OPEX','odendi','2026-01-10', 72000.00, 14400.00, 86400.00),
  ('AF-2026-SA-02','T-ATLAS','IT-SAAS','IT-OPEX','odendi','2026-01-15', 28000.00, 5600.00, 33600.00),
  ('AF-2026-SA-03','T-MSFT','IT-SAAS','IT-OPEX','odendi','2026-04-10', 74000.00, 14800.00, 88800.00),
  ('AF-2026-SA-04','T-ATLAS','IT-SAAS','IT-OPEX','odendi','2026-04-12', 29000.00, 5800.00, 34800.00),
  ('AF-2026-SA-05','T-MSFT','IT-SAAS','IT-OPEX','odendi','2026-07-08', 76000.00, 15200.00, 91200.00),
  ('AF-2026-SA-06','T-ATLAS','IT-SAAS','IT-OPEX','acik','2026-07-10', 30000.00, 6000.00, 36000.00),
  -- IT-LICENSE (yıllık yenileme + ara bakım)
  ('AF-2026-LI-01','T-MSFT','IT-LICENSE','IT-OPEX','odendi','2026-02-01', 420000.00, 84000.00, 504000.00),
  ('AF-2026-LI-02','T-VEEAM','IT-LICENSE','IT-OPEX','odendi','2026-03-15', 95000.00, 19000.00, 114000.00),
  ('AF-2026-LI-03','T-MSFT','IT-LICENSE','IT-OPEX','odendi','2026-06-01', 180000.00, 36000.00, 216000.00),
  -- IT-SEC
  ('AF-2026-SE-01','T-MSSP','IT-SEC','IT-OPEX','odendi','2026-01-20', 48000.00, 9600.00, 57600.00),
  ('AF-2026-SE-02','T-MSSP','IT-SEC','IT-OPEX','odendi','2026-02-20', 48000.00, 9600.00, 57600.00),
  ('AF-2026-SE-03','T-MSSP','IT-SEC','IT-OPEX','odendi','2026-03-20', 48000.00, 9600.00, 57600.00),
  ('AF-2026-SE-04','T-MSSP','IT-SEC','IT-OPEX','odendi','2026-04-20', 52000.00, 10400.00, 62400.00),
  ('AF-2026-SE-05','T-MSSP','IT-SEC','IT-OPEX','odendi','2026-05-20', 52000.00, 10400.00, 62400.00),
  ('AF-2026-SE-06','T-MSSP','IT-SEC','IT-OPEX','odendi','2026-06-20', 52000.00, 10400.00, 62400.00),
  ('AF-2026-SE-07','T-MSSP','IT-SEC','IT-OPEX','acik','2026-07-18', 52000.00, 10400.00, 62400.00),
  ('AF-2026-SE-08','T-FTNT','IT-SEC','IT-OPEX','odendi','2026-03-05', 85000.00, 17000.00, 102000.00),
  -- IT-BACKUP
  ('AF-2026-BK-01','T-VEEAM','IT-BACKUP','IT-OPEX','odendi','2026-02-12', 65000.00, 13000.00, 78000.00),
  ('AF-2026-BK-02','T-AWS','IT-BACKUP','IT-OPEX','odendi','2026-05-18', 72000.00, 14400.00, 86400.00),
  ('AF-2026-BK-03','T-VEEAM','IT-BACKUP','IT-OPEX','acik','2026-07-05', 68000.00, 13600.00, 81600.00),
  -- IT-SUPPORT
  ('AF-2026-SU-01','T-CONS','IT-SUPPORT','IT-OPEX','odendi','2026-01-31', 42000.00, 8400.00, 50400.00),
  ('AF-2026-SU-02','T-CONS','IT-SUPPORT','IT-OPEX','odendi','2026-03-31', 42000.00, 8400.00, 50400.00),
  ('AF-2026-SU-03','T-CONS','IT-SUPPORT','IT-OPEX','odendi','2026-05-31', 45000.00, 9000.00, 54000.00),
  ('AF-2026-SU-04','T-DELL','IT-SUPPORT','IT-OPEX','odendi','2026-06-15', 88000.00, 17600.00, 105600.00),
  ('AF-2026-SU-05','T-CONS','IT-SUPPORT','IT-OPEX','acik','2026-07-22', 45000.00, 9000.00, 54000.00),
  -- IT-TELCO
  ('AF-2026-TE-01','T-TT','IT-TELCO','IT-OPEX','odendi','2026-01-05', 22000.00, 4400.00, 26400.00),
  ('AF-2026-TE-02','T-TCELL','IT-TELCO','IT-OPEX','odendi','2026-01-08', 8500.00, 1700.00, 10200.00),
  ('AF-2026-TE-03','T-TT','IT-TELCO','IT-OPEX','odendi','2026-02-05', 22000.00, 4400.00, 26400.00),
  ('AF-2026-TE-04','T-TCELL','IT-TELCO','IT-OPEX','odendi','2026-02-08', 8500.00, 1700.00, 10200.00),
  ('AF-2026-TE-05','T-TT','IT-TELCO','IT-OPEX','odendi','2026-03-05', 22500.00, 4500.00, 27000.00),
  ('AF-2026-TE-06','T-TCELL','IT-TELCO','IT-OPEX','odendi','2026-03-08', 8500.00, 1700.00, 10200.00),
  ('AF-2026-TE-07','T-TT','IT-TELCO','IT-OPEX','odendi','2026-04-05', 22500.00, 4500.00, 27000.00),
  ('AF-2026-TE-08','T-TCELL','IT-TELCO','IT-OPEX','odendi','2026-04-08', 9000.00, 1800.00, 10800.00),
  ('AF-2026-TE-09','T-TT','IT-TELCO','IT-OPEX','odendi','2026-05-05', 23000.00, 4600.00, 27600.00),
  ('AF-2026-TE-10','T-TCELL','IT-TELCO','IT-OPEX','odendi','2026-05-08', 9000.00, 1800.00, 10800.00),
  ('AF-2026-TE-11','T-TT','IT-TELCO','IT-OPEX','odendi','2026-06-05', 23000.00, 4600.00, 27600.00),
  ('AF-2026-TE-12','T-TCELL','IT-TELCO','IT-OPEX','odendi','2026-06-08', 9000.00, 1800.00, 10800.00),
  ('AF-2026-TE-13','T-TT','IT-TELCO','IT-OPEX','acik','2026-07-05', 23500.00, 4700.00, 28200.00),
  ('AF-2026-TE-14','T-TCELL','IT-TELCO','IT-OPEX','acik','2026-07-08', 9200.00, 1840.00, 11040.00),
  -- IT-CONTRACTOR
  ('AF-2026-CO-01','T-CONS','IT-CONTRACTOR','IT-OPEX','odendi','2026-02-28', 145000.00, 29000.00, 174000.00),
  ('AF-2026-CO-02','T-CONS','IT-CONTRACTOR','IT-OPEX','odendi','2026-04-30', 160000.00, 32000.00, 192000.00),
  ('AF-2026-CO-03','T-CONS','IT-CONTRACTOR','IT-OPEX','odendi','2026-06-30', 175000.00, 35000.00, 210000.00),
  ('AF-2026-CO-04','T-CONS','IT-CONTRACTOR','IT-OPEX','acik','2026-07-15', 90000.00, 18000.00, 108000.00),
  -- IT-TRAIN
  ('AF-2026-TR-01','T-CONS','IT-TRAIN','IT-OPEX','odendi','2026-03-12', 42000.00, 8400.00, 50400.00),
  ('AF-2026-TR-02','T-MSFT','IT-TRAIN','IT-OPEX','odendi','2026-05-20', 38000.00, 7600.00, 45600.00),
  ('AF-2026-TR-03','T-CISCO','IT-TRAIN','IT-OPEX','acik','2026-07-02', 35000.00, 7000.00, 42000.00),
  -- IT-DC
  ('AF-2026-DC-01','T-DC','IT-DC','IT-OPEX','odendi','2026-01-02', 40000.00, 8000.00, 48000.00),
  ('AF-2026-DC-02','T-DC','IT-DC','IT-OPEX','odendi','2026-02-02', 40000.00, 8000.00, 48000.00),
  ('AF-2026-DC-03','T-DC','IT-DC','IT-OPEX','odendi','2026-03-02', 40000.00, 8000.00, 48000.00),
  ('AF-2026-DC-04','T-DC','IT-DC','IT-OPEX','odendi','2026-04-02', 40000.00, 8000.00, 48000.00),
  ('AF-2026-DC-05','T-DC','IT-DC','IT-OPEX','odendi','2026-05-02', 42000.00, 8400.00, 50400.00),
  ('AF-2026-DC-06','T-DC','IT-DC','IT-OPEX','odendi','2026-06-02', 42000.00, 8400.00, 50400.00),
  ('AF-2026-DC-07','T-DC','IT-DC','IT-OPEX','acik','2026-07-02', 42000.00, 8400.00, 50400.00),
  -- CAPEX
  ('AF-2026-HW-01','T-DELL','IT-HW','IT-CAPEX','odendi','2026-02-18', 980000.00, 196000.00, 1176000.00),
  ('AF-2026-HW-02','T-CISCO','IT-HW','IT-CAPEX','odendi','2026-05-10', 620000.00, 124000.00, 744000.00),
  ('AF-2026-HW-03','T-DELL','IT-HW','IT-CAPEX','acik','2026-07-08', 410000.00, 82000.00, 492000.00),
  ('AF-2026-EP-01','T-DELL','IT-ENDPOINT','IT-CAPEX','odendi','2026-03-22', 380000.00, 76000.00, 456000.00),
  ('AF-2026-EP-02','T-DELL','IT-ENDPOINT','IT-CAPEX','odendi','2026-06-14', 420000.00, 84000.00, 504000.00),
  ('AF-2026-SW-01','T-MSFT','IT-SW-CAP','IT-CAPEX','odendi','2026-04-30', 850000.00, 170000.00, 1020000.00),
  ('AF-2026-SW-02','T-MSFT','IT-SW-CAP','IT-CAPEX','acik','2026-07-12', 320000.00, 64000.00, 384000.00),
  ('AF-2026-SH-01','T-FTNT','IT-SEC-HW','IT-CAPEX','odendi','2026-03-08', 520000.00, 104000.00, 624000.00),
  ('AF-2026-SH-02','T-CISCO','IT-SEC-HW','IT-CAPEX','odendi','2026-06-20', 210000.00, 42000.00, 252000.00),
  ('AF-2026-NT-01','T-CISCO','IT-NET','IT-CAPEX','odendi','2026-04-15', 340000.00, 68000.00, 408000.00),
  ('AF-2026-NT-02','T-CISCO','IT-NET','IT-CAPEX','acik','2026-07-01', 180000.00, 36000.00, 216000.00),
  -- 2025 kapanış örnekleri
  ('AF-2025-CL-99','T-AWS','IT-CLOUD','IT-OPEX','odendi','2025-11-10', 180000.00, 36000.00, 216000.00),
  ('AF-2025-CL-98','T-AZURE','IT-CLOUD','IT-OPEX','odendi','2025-12-08', 120000.00, 24000.00, 144000.00),
  ('AF-2025-HW-99','T-DELL','IT-HW','IT-CAPEX','odendi','2025-09-20', 750000.00, 150000.00, 900000.00),
  ('AF-2025-EP-99','T-DELL','IT-ENDPOINT','IT-CAPEX','odendi','2025-10-15', 280000.00, 56000.00, 336000.00)
) AS v(fatura_no, tedarikci_no, butce_kodu, departman_kod, durum, fatura_tarihi, ara, kdv, genel)
JOIN tedarikciler t ON t.tedarikci_no = v.tedarikci_no;

INSERT INTO alis_fatura_kalemleri (alis_fatura_id, aciklama, butce_kodu, miktar, birim_fiyat, kdv_orani, tutar)
SELECT f.id, 'BT harcama — '||f.butce_kodu, f.butce_kodu, 1, f.ara_toplam, 20, f.ara_toplam
FROM alis_faturalari f;
