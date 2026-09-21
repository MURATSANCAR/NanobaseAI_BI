# Portal kitap kartları

2026-09-21: portal cevapları kapak, başlık, yazar, sayfa kaynaklı kısa özet ve kitap seçme düğmesi içerir.
`editor.card_api` salt okunur ayrı servistir (:19141); modelleri/işçileri başlatmaz ve bakım kilidini kaldırmaz.
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
