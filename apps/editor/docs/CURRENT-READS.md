# Güncel ve kullanılabilir bilgi okuma sözleşmesi

2026-09-21 — uygulama hazır; sunucuda gerçek DB/API kabulü sürüyor.

`read_model.py`, kullanıcı okumalarını `current_artifact` ve onun değişmez bilgi sürümüne bağlar. Rapor, timeline, aktör, karakter geçmişi, olay/duygu/iddia listeleri ve kitap kartı bu sözleşmeyi kullanır. Güncel çıktı yoksa tarihsel `report`, `book_card` veya ham olay tablosuna geri dönüş yoktur. Hazır olmayan listeler gerçek boş sonuç gibi gösterilmez: HTTP 409 veya `available=false`, `total=null`.

En yeni nesil seçilir; eski mühürlü nesil yeni neslin önüne geçmez. Karakter adı yalnız kimlik adaylarını seçer; anılışlar, duygular ve olaylar karakter kimliği üzerinden bağlanır. Belirsiz kimlikler aday olarak kalır; doğrulanmış geçmişe katılmaz. Metin anılışında güncel kaynak hash/aralık eşleşmesi gerekir. Analitik kabul daima ayrıca belirtilir.

Üreticilerin doğrulama öncesi aday timeline okuması `candidate_timeline` olarak ayrıdır. Editör inceleme kuyruğu ve kaynak sayfaları denetim verisidir; kabul edilmiş sonuç değildir. Genel analiz açılmaz.

Kitap araması güncel kartları reranker ile sıralar; tarihsel katalog Qdrant metinlerini kullanmaz. Modelden sonra nesil/build anahtarı tekrar kontrol edilir. Yaş filtresinde bilinmeyen yaş uygun kabul edilmez. Kitap içi aramada boş sonuç yolu da sorgu sonrasında güncellik kontrolünden geçer.

Bu değişiklik model doğruluğu, tam kitap analitik kabulü, Hermes sohbeti veya mobil ekran kabulü iddiası değildir. Gerçek kabul kanıtı tamamlanınca aşağıya eklenir.
