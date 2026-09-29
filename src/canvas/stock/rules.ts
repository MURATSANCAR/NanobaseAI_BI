/** «Nasıl hesaplandı» panelinin kuralları (köprüdeki `stock.py` belgesiyle aynı; ekranda teknoloji adı yok). */
export const RULES: Array<[string, string]> = [
  ['Logo stok', 'Güncel yılın Logo kopyasında giriş − çıkış (tarih süzgeci yok), ambar kırılımıyla. Planlanan (ileri tarihli) üretim girişi sayılmaz.'],
  ['Aylık satış hızı', 'Mevcut baskı öneri raporuyla aynı hesap: son çeyreklerin ağırlıklı ortalaması (faturalı satış).'],
  ['Kaç gün yeter', 'Logo stok ÷ (aylık satış hızı ÷ 30). Satışı olmayan kitapta hesaplanmaz; stok yoksa 0.'],
  ['Tahmini tükenme', 'Logo verisinin son günü + kaç gün yeter. «Bugün» değil, verinin bittiği gün esas alınır.'],
  ['Bitecek', 'Kaç gün yeter ≤ seçilen gün ya da ≤ baskı süresi + güvenlik günü. Baskı süresi üretim kartlarında ölçülen süredir.'],
  ['Hareketsiz', 'Pencerede (varsayılan 365 gün) hiç stok hareketi yok; yılbaşı devri hareket sayılmaz.'],
  ['Fazla stok', 'Stoğu varsayılan 730 günden uzun yeten kitap. Zeki AI eritme yönü önerir (kampanya, set, bekle); karar sizindir.'],
  ['Logo–CRM farkı', 'CRM raf kalanı − Logo stok. Logo’ya aktarılmamış hareket farkı açıklıyorsa kök neden odur; açıklanamayan fark sayım adayıdır.'],
  ['Stok devir hızı', 'Katalogdaki onaylı ölçü: yıl satış adedi ÷ ((yılbaşı devri + güncel stok) ÷ 2).'],
  ['Dağıtımcıda', 'Barkodu Logo’daki kitapla eşleşen Başarı Dağıtım ve D&R başlığı (her gün okunan son görüntü). Bizde stok varken Başarı «Baskısı Yok / Temin Edilemiyor» diyorsa «baskısı yok görünüyor», «Satışta» ama deposu boşsa «tükenmiş». Başarı çıkışı = görüntüler arası depo düşüşlerinin toplamı; kitapçılara çıkıştır, okura satış değil.'],
  ['Güvenlik stoku', 'Yeniden sipariş noktası = günlük satış × (baskı süresi + güvenlik günü). Onay portalda durur; Logo’ya yazılmaz.'],
];
