-- Non-destructive BT (IT) bütçe zenginleştirme — mevcut ERP verisini silmez.
-- Hedef: butce_planlari + alis_faturalari üzerinden /bi/budget Sync from source.
-- Uygulama:
--   psql "$BI_ERP_DATABASE_URL" -f configs/seeds/neon-erp-bt-budget-patch.sql
SET statement_timeout = 0;

-- Maliyet merkezleri (departmanlar)
INSERT INTO departmanlar (sirket_id, kod, ad)
SELECT 1, v.kod, v.ad
FROM (VALUES
  ('IT','Bilgi Teknolojileri'),
  ('IT-OPEX','BT İşletme Giderleri'),
  ('IT-CAPEX','BT Yatırım Giderleri')
) AS v(kod, ad)
WHERE NOT EXISTS (
  SELECT 1 FROM departmanlar d WHERE d.kod = v.kod
);

-- BT tedarikçileri (upsert by tedarikci_no)
INSERT INTO tedarikciler (grup_id, tedarikci_no, unvan, vergi_no, il_id, email, telefon, aktif, created_at)
SELECT g.id, v.tedarikci_no, v.unvan, v.vergi_no, v.il_id, v.email, v.telefon, true, now()
FROM (VALUES
  ('ITH','T-AWS','Amazon Web Services EMEA SARL','1111111111',34,'aws-tr@example.com','2125550101'),
  ('ITH','T-AZURE','Microsoft Azure / Türkiye','2222222222',34,'azure-tr@example.com','2125550102'),
  ('ITH','T-GCP','Google Cloud Türkiye','2222222233',34,'gcp-tr@example.com','2125550103'),
  ('YER','T-MSFT','Microsoft Türkiye (M365/Lisans)','2222222244',34,'msft-tr@example.com','2125550104'),
  ('ITH','T-DELL','Dell Technologies Türkiye','3333333333',6,'dell-tr@example.com','3125550201'),
  ('ITH','T-CISCO','Cisco Systems Türkiye','3333333344',34,'cisco-tr@example.com','2125550202'),
  ('ITH','T-FTNT','Fortinet Türkiye','3333333355',34,'fortinet-tr@example.com','2125550203'),
  ('YER','T-TT','Türk Telekom','4444444444',6,'kurumsal@turktelekom.example','3125550301'),
  ('YER','T-TCELL','Turkcell Superonline','4444444455',34,'kurumsal@turkcell.example','2125550302'),
  ('KR','T-CONS','Nanobase IT Danışmanlık A.Ş.','5555555555',34,'ops@itcons.example','2125550401'),
  ('KR','T-MSSP','CyberShield MSSP A.Ş.','5555555566',34,'soc@cybershield.example','2125550402'),
  ('ITH','T-ATLAS','Atlassian Pty Ltd','6666666666',34,'billing@atlassian.example',''),
  ('ITH','T-VEEAM','Veeam Software','6666666677',6,'tr@veeam.example',''),
  ('YER','T-DC','Equinix Istanbul Colocation','7777777777',34,'tr@equinix.example','2125550501')
) AS v(grup_kod, tedarikci_no, unvan, vergi_no, il_id, email, telefon)
JOIN tedarikci_gruplari g ON g.kod = v.grup_kod
WHERE NOT EXISTS (
  SELECT 1 FROM tedarikciler t WHERE t.tedarikci_no = v.tedarikci_no
);

UPDATE tedarikciler t SET
  unvan = v.unvan,
  email = v.email,
  telefon = v.telefon,
  aktif = true
FROM (VALUES
  ('T-AWS','Amazon Web Services EMEA SARL','aws-tr@example.com','2125550101'),
  ('T-AZURE','Microsoft Azure / Türkiye','azure-tr@example.com','2125550102'),
  ('T-GCP','Google Cloud Türkiye','gcp-tr@example.com','2125550103'),
  ('T-MSFT','Microsoft Türkiye (M365/Lisans)','msft-tr@example.com','2125550104'),
  ('T-DELL','Dell Technologies Türkiye','dell-tr@example.com','3125550201'),
  ('T-CISCO','Cisco Systems Türkiye','cisco-tr@example.com','2125550202'),
  ('T-FTNT','Fortinet Türkiye','fortinet-tr@example.com','2125550203'),
  ('T-TT','Türk Telekom','kurumsal@turktelekom.example','3125550301'),
  ('T-TCELL','Turkcell Superonline','kurumsal@turkcell.example','2125550302'),
  ('T-CONS','Nanobase IT Danışmanlık A.Ş.','ops@itcons.example','2125550401'),
  ('T-MSSP','CyberShield MSSP A.Ş.','soc@cybershield.example','2125550402'),
  ('T-ATLAS','Atlassian Pty Ltd','billing@atlassian.example',''),
  ('T-VEEAM','Veeam Software','tr@veeam.example',''),
  ('T-DC','Equinix Istanbul Colocation','tr@equinix.example','2125550501')
) AS v(tedarikci_no, unvan, email, telefon)
WHERE t.tedarikci_no = v.tedarikci_no;

-- Eski BT plan satırlarını kaldır (yalnız IT-* kodları)
DELETE FROM butce_planlari
WHERE butce_kodu LIKE 'IT-%'
   OR departman_kod IN ('IT-OPEX','IT-CAPEX','IT');

INSERT INTO butce_planlari (mali_yil, departman_kod, butce_kodu, kalem_adi, tur, planlanan_tutar, para_birimi) VALUES
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
 (2026,'IT-CAPEX','IT-HW','Sunucu / storage / network donanımı','CAPEX',3360000,'TRY'),
 (2026,'IT-CAPEX','IT-ENDPOINT','Uç nokta / notebook yenileme','CAPEX',1440000,'TRY'),
 (2026,'IT-CAPEX','IT-SW-CAP','Büyük yazılım aktivasyonu (ERP/CRM)','CAPEX',2160000,'TRY'),
 (2026,'IT-CAPEX','IT-SEC-HW','Güvenlik cihazları (firewall, NGFW)','CAPEX',1080000,'TRY'),
 (2026,'IT-CAPEX','IT-NET','Ağ modernizasyonu (Wi-Fi / switch)','CAPEX',900000,'TRY'),
 (2025,'IT-OPEX','IT-CLOUD','Bulut altyapı (IaaS/PaaS)','OPEX',2160000,'TRY'),
 (2025,'IT-OPEX','IT-SAAS','SaaS abonelikleri','OPEX',864000,'TRY'),
 (2025,'IT-OPEX','IT-SEC','Siber güvenlik','OPEX',600000,'TRY'),
 (2025,'IT-CAPEX','IT-HW','Sunucu / network donanımı','CAPEX',2400000,'TRY'),
 (2025,'IT-CAPEX','IT-ENDPOINT','Uç nokta yenileme','CAPEX',960000,'TRY');

-- Eski BT seed faturalarını kaldır (AF-2026-* / AF-2025-* BT + AF-SEED eski kalıplar)
DELETE FROM alis_fatura_kalemleri
WHERE alis_fatura_id IN (
  SELECT id FROM alis_faturalari
  WHERE butce_kodu LIKE 'IT-%'
    OR fatura_no ~ '^(AF-2026-|AF-2025-)'
);

DELETE FROM alis_faturalari
WHERE butce_kodu LIKE 'IT-%'
   OR fatura_no ~ '^(AF-2026-|AF-2025-)';

INSERT INTO alis_faturalari
  (fatura_no, tedarikci_id, sube_id, butce_kodu, departman_kod, durum, fatura_tarihi, vade_tarihi,
   ara_toplam, kdv_toplam, genel_toplam)
SELECT
  v.fatura_no, t.id, 1, v.butce_kodu, v.departman_kod, v.durum, v.fatura_tarihi::date,
  (v.fatura_tarihi::date + 30), v.ara, v.kdv, v.genel
FROM (VALUES
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
  ('AF-2026-SA-01','T-MSFT','IT-SAAS','IT-OPEX','odendi','2026-01-10', 72000.00, 14400.00, 86400.00),
  ('AF-2026-SA-02','T-ATLAS','IT-SAAS','IT-OPEX','odendi','2026-01-15', 28000.00, 5600.00, 33600.00),
  ('AF-2026-SA-03','T-MSFT','IT-SAAS','IT-OPEX','odendi','2026-04-10', 74000.00, 14800.00, 88800.00),
  ('AF-2026-SA-04','T-ATLAS','IT-SAAS','IT-OPEX','odendi','2026-04-12', 29000.00, 5800.00, 34800.00),
  ('AF-2026-SA-05','T-MSFT','IT-SAAS','IT-OPEX','odendi','2026-07-08', 76000.00, 15200.00, 91200.00),
  ('AF-2026-SA-06','T-ATLAS','IT-SAAS','IT-OPEX','acik','2026-07-10', 30000.00, 6000.00, 36000.00),
  ('AF-2026-LI-01','T-MSFT','IT-LICENSE','IT-OPEX','odendi','2026-02-01', 420000.00, 84000.00, 504000.00),
  ('AF-2026-LI-02','T-VEEAM','IT-LICENSE','IT-OPEX','odendi','2026-03-15', 95000.00, 19000.00, 114000.00),
  ('AF-2026-LI-03','T-MSFT','IT-LICENSE','IT-OPEX','odendi','2026-06-01', 180000.00, 36000.00, 216000.00),
  ('AF-2026-SE-01','T-MSSP','IT-SEC','IT-OPEX','odendi','2026-01-20', 48000.00, 9600.00, 57600.00),
  ('AF-2026-SE-02','T-MSSP','IT-SEC','IT-OPEX','odendi','2026-02-20', 48000.00, 9600.00, 57600.00),
  ('AF-2026-SE-03','T-MSSP','IT-SEC','IT-OPEX','odendi','2026-03-20', 48000.00, 9600.00, 57600.00),
  ('AF-2026-SE-04','T-MSSP','IT-SEC','IT-OPEX','odendi','2026-04-20', 52000.00, 10400.00, 62400.00),
  ('AF-2026-SE-05','T-MSSP','IT-SEC','IT-OPEX','odendi','2026-05-20', 52000.00, 10400.00, 62400.00),
  ('AF-2026-SE-06','T-MSSP','IT-SEC','IT-OPEX','odendi','2026-06-20', 52000.00, 10400.00, 62400.00),
  ('AF-2026-SE-07','T-MSSP','IT-SEC','IT-OPEX','acik','2026-07-18', 52000.00, 10400.00, 62400.00),
  ('AF-2026-SE-08','T-FTNT','IT-SEC','IT-OPEX','odendi','2026-03-05', 85000.00, 17000.00, 102000.00),
  ('AF-2026-BK-01','T-VEEAM','IT-BACKUP','IT-OPEX','odendi','2026-02-12', 65000.00, 13000.00, 78000.00),
  ('AF-2026-BK-02','T-AWS','IT-BACKUP','IT-OPEX','odendi','2026-05-18', 72000.00, 14400.00, 86400.00),
  ('AF-2026-BK-03','T-VEEAM','IT-BACKUP','IT-OPEX','acik','2026-07-05', 68000.00, 13600.00, 81600.00),
  ('AF-2026-SU-01','T-CONS','IT-SUPPORT','IT-OPEX','odendi','2026-01-31', 42000.00, 8400.00, 50400.00),
  ('AF-2026-SU-02','T-CONS','IT-SUPPORT','IT-OPEX','odendi','2026-03-31', 42000.00, 8400.00, 50400.00),
  ('AF-2026-SU-03','T-CONS','IT-SUPPORT','IT-OPEX','odendi','2026-05-31', 45000.00, 9000.00, 54000.00),
  ('AF-2026-SU-04','T-DELL','IT-SUPPORT','IT-OPEX','odendi','2026-06-15', 88000.00, 17600.00, 105600.00),
  ('AF-2026-SU-05','T-CONS','IT-SUPPORT','IT-OPEX','acik','2026-07-22', 45000.00, 9000.00, 54000.00),
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
  ('AF-2026-CO-01','T-CONS','IT-CONTRACTOR','IT-OPEX','odendi','2026-02-28', 145000.00, 29000.00, 174000.00),
  ('AF-2026-CO-02','T-CONS','IT-CONTRACTOR','IT-OPEX','odendi','2026-04-30', 160000.00, 32000.00, 192000.00),
  ('AF-2026-CO-03','T-CONS','IT-CONTRACTOR','IT-OPEX','odendi','2026-06-30', 175000.00, 35000.00, 210000.00),
  ('AF-2026-CO-04','T-CONS','IT-CONTRACTOR','IT-OPEX','acik','2026-07-15', 90000.00, 18000.00, 108000.00),
  ('AF-2026-TR-01','T-CONS','IT-TRAIN','IT-OPEX','odendi','2026-03-12', 42000.00, 8400.00, 50400.00),
  ('AF-2026-TR-02','T-MSFT','IT-TRAIN','IT-OPEX','odendi','2026-05-20', 38000.00, 7600.00, 45600.00),
  ('AF-2026-TR-03','T-CISCO','IT-TRAIN','IT-OPEX','acik','2026-07-02', 35000.00, 7000.00, 42000.00),
  ('AF-2026-DC-01','T-DC','IT-DC','IT-OPEX','odendi','2026-01-02', 40000.00, 8000.00, 48000.00),
  ('AF-2026-DC-02','T-DC','IT-DC','IT-OPEX','odendi','2026-02-02', 40000.00, 8000.00, 48000.00),
  ('AF-2026-DC-03','T-DC','IT-DC','IT-OPEX','odendi','2026-03-02', 40000.00, 8000.00, 48000.00),
  ('AF-2026-DC-04','T-DC','IT-DC','IT-OPEX','odendi','2026-04-02', 40000.00, 8000.00, 48000.00),
  ('AF-2026-DC-05','T-DC','IT-DC','IT-OPEX','odendi','2026-05-02', 42000.00, 8400.00, 50400.00),
  ('AF-2026-DC-06','T-DC','IT-DC','IT-OPEX','odendi','2026-06-02', 42000.00, 8400.00, 50400.00),
  ('AF-2026-DC-07','T-DC','IT-DC','IT-OPEX','acik','2026-07-02', 42000.00, 8400.00, 50400.00),
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
  ('AF-2025-CL-99','T-AWS','IT-CLOUD','IT-OPEX','odendi','2025-11-10', 180000.00, 36000.00, 216000.00),
  ('AF-2025-CL-98','T-AZURE','IT-CLOUD','IT-OPEX','odendi','2025-12-08', 120000.00, 24000.00, 144000.00),
  ('AF-2025-HW-99','T-DELL','IT-HW','IT-CAPEX','odendi','2025-09-20', 750000.00, 150000.00, 900000.00),
  ('AF-2025-EP-99','T-DELL','IT-ENDPOINT','IT-CAPEX','odendi','2025-10-15', 280000.00, 56000.00, 336000.00)
) AS v(fatura_no, tedarikci_no, butce_kodu, departman_kod, durum, fatura_tarihi, ara, kdv, genel)
JOIN tedarikciler t ON t.tedarikci_no = v.tedarikci_no
ON CONFLICT (fatura_no) DO UPDATE SET
  tedarikci_id = EXCLUDED.tedarikci_id,
  butce_kodu = EXCLUDED.butce_kodu,
  departman_kod = EXCLUDED.departman_kod,
  durum = EXCLUDED.durum,
  fatura_tarihi = EXCLUDED.fatura_tarihi,
  vade_tarihi = EXCLUDED.vade_tarihi,
  ara_toplam = EXCLUDED.ara_toplam,
  kdv_toplam = EXCLUDED.kdv_toplam,
  genel_toplam = EXCLUDED.genel_toplam;

INSERT INTO alis_fatura_kalemleri (alis_fatura_id, aciklama, butce_kodu, miktar, birim_fiyat, kdv_orani, tutar)
SELECT f.id, 'BT harcama — '||f.butce_kodu, f.butce_kodu, 1, f.ara_toplam, 20, f.ara_toplam
FROM alis_faturalari f
WHERE f.butce_kodu LIKE 'IT-%'
  AND NOT EXISTS (
    SELECT 1 FROM alis_fatura_kalemleri k WHERE k.alis_fatura_id = f.id
  );
