# Portal kitap kartları

2026-09-21: portal cevapları kapak, başlık, yazar, sayfa kaynaklı kısa özet ve kitap seçme düğmesi içerir.
`editor.card_api` salt okunur ayrı servistir (:19141); modelleri/işçileri başlatmaz ve bakım kilidini kaldırmaz. Uçlar: `/v1/books/cards`, `/v1/books/{id}/cover`, `/v1/books/{id}/graph`, `/v1/books/{id}/proofing` (son okuma: son neslin her denetim için en yeni koşusu + bulguları; koşu yoksa boş listeler).
`presentation.cards` kitap ve kapak kaydını okur. Yazar/özet yalnız güncel revizyonun `current_artifact`
katalog çıktısından gelir. Eski `book_card.summary` kullanılmaz; migration henüz yoksa alanlar eksik döner.
PDF sayfası kapak diye sunulmaz. Kaynak dosyası yalnız Editor storage altında okunur.

Test sunucusuna özel loopback tünel: `editor-cards-tunnel.service`, CPU :18889 → GPU :19141.
SSH kullanıcısının izin verilen portlarına yalnız 18889 eklenir. Mevcut model tüneli değiştirilmez.
Bağımsız `EDITOR_CARDS_KEY`, GPU `secrets/cards.env` içinde tutulur. Köprüde `EDITOR_CATALOG_BASE`
ve `EDITOR_CATALOG_KEY` tanımlanır; browser anahtar görmez. İnternete yeni açık port yoktur.
Köprü kullanıcı oturumu altında kart ve görsel sunar. Kaydedilen soru yalnız kitap kimliklerini saklar;
her okuma güncel karta gider, eski içerik kopyası gösterilmez.

Konu önerisi yalnız güncel özetlerden seçilir. Özet yoksa mevcut kitaplar açıkça öneri olmayan katalog
listesi olarak gösterilir. Seçilen kitapta eksik yazar/özet açık yazılır. Böylece bakım sırasında kapak
ve başlık görülebilir, doğrulanmamış eski içerik doğrulanmış gibi sunulmaz.

Kabul: gerçek PostgreSQL, salt okunur kart API, portal API ve 320/390/768/masaüstü tarayıcı kontrolleri.
Güncel özet üretimi ve anlamsal öneri kalitesi ayrı kabul gerektirir; kartın çizilmesi bu kabul değildir.

## Test portalı yayını — 2026-09-21

Kod: `b0a7b36` kart akışı, `13b6dc1` bağımsız Compose overlay, `97e38e6` dar ekran düzeltmesi.
GPU image: `editor-cards:b0a7b36` (`editor-cards:1` etiketi aynı image).
Mevcut Editor kurulumuna `deploy/cards.override.yml` eklenerek yalnız
`docker compose -f deploy/docker-compose.yml -f deploy/cards.override.yml up -d --no-deps cards`
çalıştırılır. Model/işçi yaşam döngüsü bu servisten bağımsızdır.

Frontend uzak derleme dizini: `nanobase-direct:/tmp/book-cards-b0a7b36`.
TypeScript kontrolü ve Vite üretim derlemesi sunucuda geçti; yerel test çalıştırılmadı.
Portal derlemesinde `VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas` zorunludur.
Yanlış varsayılan `/bi/` ile bir ara yayında varlıklar yüklenmedi; eski index geri alınıp
bu iki değişkenle yeniden derlendi. Son HTTPS HTML hash'i:
`981ce3047ad7414ab5685b5622e1e96423841a6325c8f676fdd1d8ce53b433d2`.
Mevcut finansal ekran kaynakları korunarak derlendi; eski varlıklar silinmedi.

Gerçek GPU PostgreSQL bağımsız sorgusu + storage dosyaları ile kart API'si 6/6 başlık/kapak
eşleşti; `evidence/2026-09-21-portal-cards-db.json`. Yetkisiz kart API isteği 401.
Oturumlu portalda isimle soru tek kart getirdi; konu sorusu altı gerçek kartı açıkça
öneri sıralaması olmayan katalog listesi olarak getirdi. Altı kitapta da güncel içerik
çıktısı yok; yazar/özet yer tutucuları bilinçlidir. Konuya göre öneri kalitesi DOĞRULANAMADI.

Son yayın: oturumlu isimle kart sorusu, gerçek kapak yüklenmesi, kitap seçme (tıklama ve
klavye), yenilemede boş sohbet doğrulandı. 320/390/768/1440 genişliklerinde sayfa scrollWidth
viewport genişliğine eşit. 320px başlık artık 161px alanda iki satır; ilk dar kolon hatası
düzeltilip tekrar ölçüldü. `evidence/2026-09-21-portal-cards-browser.json`.
Tarayıcı ekran boyutu kontrol sonunda eski haline getirildi. Tam içerik soru-cevap ve
konu önerisinin anlamsal doğruluğu bu kart sunum kabulünün dışındadır.
