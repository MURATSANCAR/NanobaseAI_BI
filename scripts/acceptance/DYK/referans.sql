-- DYK Kurul — bağımsız referans sorguları (köprü kodu kullanılmadan; test sunucusunda, salt okunur).
-- Firma numarası yıla göre L_CAPIPERIOD'dan okunur (411 = 2026, 211 = 2021–2025); aşağıda 411/211 örnektir, kabul.py
-- güncel firmayı ve veri son gününü (M45'in «veriSonu», panelde net satışın veri son günü) koyar.
-- CRM (.28) ve Logo ayrı sunuculardır; tek sorguda birleşmez.

-- R1 · Net satış (yıl başından veri son gününe): M45 tanımı — faturalı satış satırı, iade eksi, LINENET.
--      Panel «Net satış (yıl başından)» = bu toplam (0,01 ₺ tolerans).
SELECT SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN 1 ELSE -1 END * S.LINENET) AS net
FROM dbo.LG_411_01_STLINE AS S
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND S.DATE_ >= '2026-01-01' AND S.DATE_ < DATEADD(day, 1, '2026-08-17');
-- Bilgi (karşılaştırma değil): fatura başlığı seviyesinde net ciro (analiz §14 kabul 1: 848.110.178,82 ₺). Satır seviyesi
-- ile farkı rapora yazılır; panel M45'in satır tanımını gösterir (yeniden hesap yok).
SELECT SUM(CASE WHEN TRCODE IN (7,8,9) THEN NETTOTAL ELSE -NETTOTAL END) AS net_fatura
FROM dbo.LG_411_01_INVOICE WHERE CANCELLED = 0 AND TRCODE IN (2,3,7,8,9) AND DATE_ >= '2026-01-01' AND DATE_ < '2027-01-01';

-- R2 · Geçen yılın aynı dönemi (panelde net satışın «önceki» değeri): 1 Ocak – geçen yılın aynı günü (dahil).
SELECT SUM(CASE WHEN S.TRCODE IN (7,8,9) THEN 1 ELSE -1 END * S.LINENET) AS net_onceki
FROM dbo.LG_211_01_STLINE AS S
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND S.DATE_ >= '2025-01-01' AND S.DATE_ < DATEADD(day, 1, '2025-08-17');

-- R3 · Brüt kâr marjı (maliyeti işlenmiş satış): (Σ maliyetli net − Σ adet × OUTCOST) ÷ Σ maliyetli net × 100.
SELECT SUM(CASE WHEN S.OUTCOST <> 0 THEN CASE WHEN S.TRCODE IN (7,8,9) THEN 1 ELSE -1 END * S.LINENET ELSE 0 END) AS maliyetli_net,
       SUM(CASE WHEN S.OUTCOST <> 0 THEN CASE WHEN S.TRCODE IN (7,8,9) THEN 1 ELSE -1 END * S.AMOUNT * S.OUTCOST ELSE 0 END) AS maliyet
FROM dbo.LG_411_01_STLINE AS S
WHERE S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (2,3,7,8,9)
  AND S.DATE_ >= '2026-01-01' AND S.DATE_ < DATEADD(day, 1, '2026-08-17');

-- R4 · Kasa ve banka: 100 + 102 hesap bakiyesi (borç − alacak), yılın açılış fişi dahil, veri son gününe kadar.
SELECT SUM(L.DEBIT - L.CREDIT) AS kasa_banka
FROM dbo.LG_411_01_EMFLINE AS L
JOIN dbo.LG_411_01_EMFICHE AS F ON F.LOGICALREF = L.ACCFICHEREF
JOIN dbo.LG_411_EMUHACC AS A ON A.LOGICALREF = L.ACCOUNTREF
WHERE L.CANCELLED = 0 AND F.CANCELLED = 0 AND A.CODE LIKE '10[02]%'
  AND L.DATE_ >= '2026-01-01' AND L.DATE_ < DATEADD(day, 1, '2026-08-17');

-- R5 · 60 günde biten sözleşme (CRM; EDITORIAL_CONTRACT_WARN_DAYS = 60): panel «Süresi yaklaşan sözleşme».
SELECT COUNT(*) AS n FROM Timas_MSCRM.dbo.new_sozlesmeBase s
WHERE s.statecode = 0 AND s.statuscode IN (100000000, 100000006, 100000007)
  AND ISNULL(s.new_suresizsozlesme, 0) = 0 AND s.new_SozlesmeBitisTarihi >= CAST(GETDATE() AS date)
  AND s.new_SozlesmeBitisTarihi < DATEADD(day, 61, CAST(GETDATE() AS date));

-- R6 · Logo verisinin yaşı: gösterge = bugün − bu gün (beklenen 2026-08-17, donmuş .155 kopyası).
SELECT MAX(DATE_) AS son FROM dbo.LG_411_01_INVOICE WHERE CANCELLED = 0;

-- Uç ↔ uç karşılaştırmaları (analizin kabul 3 ve kaynak modül sözleşmeleri; doğrudan SQL değil, aynı veri tabanında):
--   bütçe oranı = GET /api/v1/budget/tracking?year=Y → sirket.oran × 100; plan yoksa panelde «kaynak yok» (değer boş)
--   bayi vadesi geçmiş = GET /api/v1/dealers/summary → vadesiGecmis (yönetici: bütün bayiler)
--   kritik risk = GET /api/v1/risk/summary → sayilar.kritik; Zeki AI cevaplama = GET /api/v1/model-quality/scorecard
