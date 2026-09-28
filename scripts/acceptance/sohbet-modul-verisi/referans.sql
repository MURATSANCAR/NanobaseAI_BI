-- Zeki AI sohbetine modül verisi — doğrudan-SQL referansları (PostgreSQL, portal veritabanı, salt okunur).
-- Köprü kodu kullanılmadan elle yazıldı; kabul.py her referansı aynı anda chat_portal'ın derlediği planla karşılaştırır.
-- :tenant köprünün kiracısıdır (SEMANTIC_TENANT_ID). Her blok «-- @Rn» ile başlar; ilk kolon anahtar, ikinci değer
-- (anahtarsız tek değerde ilk kolon değer). Tablo boşsa ya da bu sunucuda yoksa sonuç «VERİ YOK» sayılır, başarısız değil.

-- @R1 risk kaydı: durumu açık olanların sayısı
SELECT count(*) FROM semantic_risk_register WHERE tenant_id = :tenant AND durum = 'acik';

-- @R2 risk kaydı: kategoriye göre sayı
SELECT kategori, count(*) FROM semantic_risk_register WHERE tenant_id = :tenant GROUP BY kategori;

-- @R3 risk aksiyonu: bağlı risk kaydının kategorisine göre sayı (aksiyon tablosunda kiracı yok; kiracı risk kaydından)
SELECT r.kategori, count(*)
  FROM semantic_risk_actions a JOIN semantic_risk_register r ON r.id = a.risk_id AND r.tenant_id = :tenant
 GROUP BY r.kategori;

-- @R4 kurumsal gelen kutusu: İK iletisi hariç, duruma göre ileti sayısı
SELECT status, count(*) FROM semantic_mail_messages
 WHERE tenant_id = :tenant AND (is_hr IS NULL OR is_hr = false) GROUP BY status;

-- @R5 reklam: geçen ay platform bazında harcama (günlük → kampanya → hesap)
SELECT ac.platform, sum(d.spend)
  FROM semantic_ads_daily d
  JOIN semantic_ads_campaigns c ON c.id = d.campaign_id AND c.tenant_id = :tenant
  LEFT JOIN semantic_ads_accounts ac ON ac.id = c.account_id AND ac.tenant_id = :tenant
 WHERE d.day >= to_char(date_trunc('month', now() AT TIME ZONE 'Europe/Istanbul') - interval '1 month', 'YYYY-MM-DD')
   AND d.day <  to_char(date_trunc('month', now() AT TIME ZONE 'Europe/Istanbul'), 'YYYY-MM-DD')
 GROUP BY ac.platform;

-- @R6 okur envanteri: en son sayım günündeki e-posta izinli okur toplamı (günler toplanmaz)
SELECT sum(eposta_izinli) FROM semantic_okur_inventory
 WHERE tenant_id = :tenant AND tarih = (SELECT max(tarih) FROM semantic_okur_inventory WHERE tenant_id = :tenant);

-- @R7 kurul aksiyonu: duruma göre sayı
SELECT durum, count(*) FROM semantic_kurul_actions WHERE tenant_id = :tenant GROUP BY durum;

-- @R8 Zeki AI iş kuyruğu: modüle göre ortalama bekleme (ms)
SELECT module, avg(queue_wait_ms) FROM sl_llm_job WHERE tenant_id = :tenant GROUP BY module;

-- @R9 yazar başvurusu: duruma göre sayı
SELECT status, count(*) FROM semantic_editorial_applications WHERE tenant_id = :tenant GROUP BY status;

-- @R10 çeviri işi: taslak durumuna göre sayı
SELECT draft_state, count(*) FROM semantic_translation_jobs WHERE tenant_id = :tenant GROUP BY draft_state;
