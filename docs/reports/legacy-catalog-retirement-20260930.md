# Eski semantik katalog kaldırma — 30 Eylül 2026

Kullanıcı talebi: “eski kataloğu sil”. Kapsam eski soru–kolon eşleştirmeleri, kavramlar, formüller, eş anlamlılar, öğrenilmiş adaylar ve katalog sürüm snapshotlarıdır. Logo/CRM kaynak kayıtları, fiziksel tablo profilleri ve denetim/soru geçmişi silinmez.

100 soru başlangıç kanıtı: `/data/nanobaseai/bi/acceptance/complex100-20260930/`. 74 kapsam reddi,1 gerçek netleştirme,22 eski akışta engellenen/geçersiz,1 yanlış boş cevap,2 HTTP503. Tam kabul0/100.

## Değişiklik

- Runtime.ask eski resolver/compiler fallback kodu çıkarıldı. Intro ve bağımsız portal kapalı planları sonrası bütün veri soruları yeni finance_query planına gider; kelime filtresi ve ortam değişkeni eski yolu geri açamaz.
- Eski kural paketi, Q→SQL örnekleri ve dil havuzu yüklenmez.
- `retire-legacy-catalog.py`: önce PostgreSQL consistent snapshot custom dump; tam pg_restore okuması ve SHA256; sonra aynı transactionda katalog kayıtlarını silme ve tekrar yazmaya karşı trigger. Başka tenant/datasource kayıtları silinmez.
- Fiziksel şema profilleri modüllerin doğrudan veri okumaları için korunur; eski kavram eşleştirmesi yerine kullanılmaz.

## Canlı durum

Test sunucusunda tamamlandı. Tutarlı yedek tam `pg_restore` okumasından geçti; SHA256 `2495799f838b90003012bc12dfe441cb40b045594cc156cb2484eced7f3e8068`.

Yedek: `/data/nanobaseai/bi/backups/retired-legacy-catalog-20260930-zstd/legacy-catalog.dump`; aynı dizinde `backup.json`, `retirement.json`.

| Tablo | Silinen kayıt |
|---|---:|
| sl_mapping | 6624 |
| sl_evidence | 13517 |
| sl_counter_evidence | 436 |
| sl_candidate | 4441 |
| sl_concept | 6624 |
| sl_catalog_version | 70586 |
| sl_vocabulary | 41152 |
| sl_suggestion | 54 |
| **Toplam** | **143434** |

Sekiz tabloda emekliye ayrılan kapsamın kalan kayıt sayısı 0. Fiziksel profiller4259 ve annotation7 korundu. Dört yeniden-yazma engeli etkin; eski semantic-worker/vocabulary zamanlayıcıları kapalı. Bağımsız iş kataloğu zamanlayıcısına dokunulmadı.

Gerçek API/veritabanı duman kabulü20/20: kapsam boşluğu, profiller, trigger, yeniden yazmanın reddi, eski uçların410 cevabı, sağlık ve giriş cevapları. Kanıt `/tmp/codex-retire-catalog-20260930/smoke.json`; geçici timasai oturumu1 silindi. Kaynak Logo/CRM kayıtlarına yazılmadı.

Silme öncesi yeni motorun12 temel gerçek cevap referansı12/12 geçti. Katalog emekliliğinin20 kontrolü yeni kapsamın veya100 karmaşık sorunun doğru cevaplandığını göstermez. Kapsam genişletmesinin kabulü ayrı ve henüz bekliyor.
