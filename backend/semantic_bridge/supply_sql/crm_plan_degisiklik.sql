-- M52 Baskı planı değişiklikleri (CRM new_uretimplanlamatakvimiBase, yalnız okuma): değişen baskı tarihi ve sebebi.
-- Kartla bağ `new_uretimplanlamatakvimi` arama kolonundan (ölçülecek: profilde karta bağlı görünmedi); bağlanamayan
-- değişiklik ekranda ayrıca sayılır.
SELECT t.new_uretimplanlamatakvimiId AS id, t.new_uretimplanlamatakvimi AS kart_id, t.new_degisenbaskitarihi AS yeni_tarih,
  CAST(t.new_degisikliksebebi AS int) AS sebep, t.CreatedOn AS tarih
FROM {crm}new_uretimplanlamatakvimiBase t
WHERE t.statecode = 0 AND t.CreatedOn >= '{bas}'
