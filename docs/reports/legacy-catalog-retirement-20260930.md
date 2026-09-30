# Eski semantik katalog kaldırma — 30 Eylül 2026

Kullanıcı talebi: “eski kataloğu sil”. Kapsam eski soru–kolon eşleştirmeleri, kavramlar, formüller, eş anlamlılar, öğrenilmiş adaylar ve katalog sürüm snapshotlarıdır. Logo/CRM kaynak kayıtları, fiziksel tablo profilleri ve denetim/soru geçmişi silinmez.

100 soru başlangıç kanıtı: `/data/nanobaseai/bi/acceptance/complex100-20260930/`. 74 kapsam reddi,1 gerçek netleştirme,22 eski akışta engellenen/geçersiz,1 yanlış boş cevap,2 HTTP503. Tam kabul0/100.

## Değişiklik

- Runtime.ask eski resolver/compiler fallback kodu çıkarıldı. Intro ve bağımsız portal kapalı planları sonrası bütün veri soruları yeni finance_query planına gider; kelime filtresi ve ortam değişkeni eski yolu geri açamaz.
- Eski kural paketi, Q→SQL örnekleri ve dil havuzu yüklenmez.
- `retire-legacy-catalog.py`: önce PostgreSQL consistent snapshot custom dump; tam pg_restore okuması ve SHA256; sonra aynı transactionda katalog kayıtlarını silme ve tekrar yazmaya karşı trigger. Başka tenant/datasource kayıtları silinmez.
- Fiziksel şema profilleri modüllerin doğrudan veri okumaları için korunur; eski kavram eşleştirmesi yerine kullanılmaz.

## Canlı durum

Hazırlık tamamlandı; dağıtım, katalog silme ve gerçek DB/API kabulü henüz yapılmadı. Yeni iş sorularının destek kapsamı bu kaldırmayla genişlemiş sayılmaz.
