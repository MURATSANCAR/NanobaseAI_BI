# Kitaptan bağımsız üretim sözleşmesi

Kullanıcının 21 Eylül 2026 talimatı: hedef ürünün üretim hazırlığıdır; herhangi bir kitap için özel kod, prompt istisnası, sayfa listesi veya karakter eşlemesi eklenmez.

## Kabul birimi

Bir kitabın geçmesi ürün kabulü değildir. Gerçek katalogdan farklı uzunluk/görsel yoğunluk/başlık düzenlerine sahip kitaplar aynı kod, model ve prompt sürümüyle işlenir. Kabul referansı uygulama cevabından bağımsız özgün PDF/metin/görsel kaynak incelemesidir. Kitap bazlı beklenen sonuçlar test verisidir, çalışma zamanı kuralı değildir.

## Zorunlu sözleşmeler

- Fiziksel kaynak kapsamı ve anlamsal çıkarım kapsamı ayrı ölçülür; boş sayfa, okunamayan sayfa ve boş model cevabı birbirine çevrilmez.
- Her zorunlu sayfa/parça görevi sonuçlanır. Kısmi fan-out başarısızlığı yeni workflowlarda işin başarıya ilerlemesini engeller; geçmiş Temporal kayıtları patch sınırıyla korunur.
- Critic her verilen iddiaya bir kez cevap verir; bilinmeyen, tekrarlı veya eksik ID listesi geçerli denetim değildir. Sınırlı yeniden denemeler sonunda eksik karar teknik hata olur.
- İlk model güveni değişmez kanıtta saklanır. Tekrar denetim hesaplanmış güveni girdi yapamaz. Eski kayıtta ilk güven bilinmiyorsa mevcut puan ilk model puanı diye geriye doldurulmaz; yeni nesil gerekir.
- Ad eşitliği kimlik kanıtı değildir; görsel etiket, metinde anılan ad ve kişi kimliği ayrılır. Belirsiz kişi zorla bağlanmaz.
- Rapor/özet/indeks aynı doğrulanmış revizyondan üretilir. Revizyon, kod veya policy değişirse eski READY sonucu kabul edilmez.
- Kaynak/kimlik/olay kapsamı, regresyon ve bağımsız semantik kabul olmadan üretim veya tam kitap etiketi verilmez. Teknik tutarlılık sayıları bu kapının yerine geçmez.

## Güncel çalışma

İlk sistemik düzeltmeler: kısmi görev başarısızlığını durdurma, tam Critic ID sözleşmesi ve tekrar doğrulamada güven puanı kaymasını engelleme. Canlı çok kitap kabulü henüz tamamlanmadı. Eski tek kitap kanıtları kendi sürümleriyle sınırlı regresyon verisidir.
