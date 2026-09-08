# Üretim kontrolü — 9 Eylül 2026

Karar: genel kullanıma açık üretim için henüz uygun değil.

## Doğrulanan dağıtım

Sunucu kritik audit/resolver/equivalences dosyalarının SHA256 değerleri yerel sürümle aynı. Servis aktif, sağlık kontrolünde LLM ve veritabanı hazır; 4121 profil, 88 sertifikalı kavram.

## Engeller

1. Dışarıdan oturumsuz `/timas/api/v1/run_sql` isteği SQL denetimine ulaşıyor. Veri okumayan `SELECT 1` isteği 401/403 yerine 400 SQL rejected döndü. Nginx Timaş basic-auth satırları yorumda; SEMANTIC_CALLER_TOKEN ve SEMANTIC_ADMIN_TOKEN yapılandırılmamış. Giriş yönteminin kullanıcı seçimi bekleniyor; bu ayarlar değiştirilmedi.
2. Ana API env dosyasında AUTH_MODE=dev, ENVIRONMENT/APP_ENV yok. Çalışan ana API'nin etkin ayarı ayrıca doğrulanmadan üretim auth kontrolü geçmiş sayılamaz.
3. Yapılandırılmış konuşma planı yok. Canlı zincirde “Peki geçen yıl?” NON_SQL_QUERY: “peki” tanımsız. “Sadece Ankara” ise önceki 2026 kanal cirosunu doğru şehir koşuluyla daralttı. Tutarlı takip desteği kanıtlanmadı.
4. Yokluk soruları güvenli biçimde engelleniyor; “hiç satmayan ürünler” INCOMPLETE_ANSWER. Bu işlev tamamlanmış değil.

## Düzeltilen üretim hatası

İki uvicorn worker, süreç belleğindeki sonuç deposunu paylaşmıyor. Canlıda kanal ve Ankara sonuçları hemen GET edildiğinde 410 döndü. Deploy betiğinde varsayılan 1 yapıldı; farklı değer reddediliyor. Sunucuda zz-single-worker.conf systemd drop-in ile workers=1 uygulandı, servis yeniden başlatıldı ve health başarılı. Yeniden başlatma önceki geçici sonuçları/konuşmaları temizler.

## Canlı davranış

Kitap 10, kanal 16, iade 50, 2026 kanal ciro 17 satır. Pahalı ve iskonto yönü CLARIFICATION; yüklenmemiş aylık karşılaştırma DATA_UNAVAILABLE. Ayrıntılar artifacts/prod-readiness-20260909.json içinde. Bu veri seti bağımsız sayısal doğruluk ölçümü değildir.

## Testler

371 semantik test, 24 frontend test geçti. Deploy betiği bash -n başarılı. Tek worker sonrası aynı sonuca 12 ardışık GET: 12/12 HTTP 200, 17 satır ve aynı önizleme. Kanıt: artifacts/prod-single-worker-20260909.json.
