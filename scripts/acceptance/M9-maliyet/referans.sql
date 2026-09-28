-- M9 birim maliyet sağlayıcısı — bağımsız referans sorguları (test sunucusunda). kabul.py bunları kendi parametreleriyle
-- koşturur; burada elle koşturmak için {yer tutucu}lu hâlleri durur. Firma: 411 = 2026, 211 = 2021–2025 (görüntünün
-- `copies` listesi hangi kopyanın okunduğunu söyler).

-- R1. Onaylı analizin dondurulmuş birim maliyeti (portal kaydı, PostgreSQL). Sağlayıcı: kaynak «onayli-analiz».
--     Birden çok satır varsa Aşama «kesin» önce, aynı aşamada son onay imzası en yeni olan.
SELECT a.id, a.stage, (a.result_json::json -> 'summary' ->> 'unitCost')::numeric AS birim_maliyet,
       (SELECT MAX(p."at") FROM semantic_pricing_approvals p
         WHERE p.analysis_id = a.id AND p.version = a.version AND p.decision = 'onay') AS onay_gunu
FROM semantic_pricing_analyses a
WHERE a.tenant_id = '{kiraci}' AND a.status = 'onaylandi' AND a.stock_code = '{stok_kodu}';

-- R2. Logo gerçekleşen birim maliyet: kitabın maliyeti girilmiş satış satırlarının (OUTCOST > 0) en son yılı.
--     Sağlayıcı: kaynak «gerceklesen», yil = {yil}. Tarih aralığı görüntünün o yıl için okuduğu kopyayla sınırlı.
SELECT SUM(S.AMOUNT * S.OUTCOST) / NULLIF(SUM(S.AMOUNT), 0) AS birim_maliyet, COUNT(*) AS satir
FROM LG_411_01_STLINE S JOIN LG_411_ITEMS IT ON IT.LOGICALREF = S.STOCKREF
WHERE IT.CODE = '{stok_kodu}' AND S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (7, 8, 9)
  AND S.OUTCOST > 0 AND S.DATE_ >= '{yil}0101' AND S.DATE_ < '{yil+1}0101';

-- R3. Maliyeti hiç girilmemiş kitap: her kopyada OUTCOST > 0 satış satırı 0 olmalı. Sağlayıcı: kaynak «yok», maliyet NULL.
SELECT COUNT(*) AS maliyetli_satir
FROM LG_411_01_STLINE S JOIN LG_411_ITEMS IT ON IT.LOGICALREF = S.STOCKREF
WHERE IT.CODE = '{stok_kodu}' AND S.CANCELLED = 0 AND S.LINETYPE = 0 AND S.INVOICEREF <> 0 AND S.TRCODE IN (7, 8, 9)
  AND S.OUTCOST > 0;
-- (211 kopyası için aynı sorgu LG_211_* tablolarıyla.)
