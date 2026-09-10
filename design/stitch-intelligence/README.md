# NanobaseAI · Intelligence Portal

Stitch tasarım projesi: https://stitch.withgoogle.com/projects/9228120035083968175

## Tasarım yönü

Doğal dille veri analizi yapan portal için koyu grafit zemin, nane yeşili vurgu,
Manrope tipografi ve belirgin bilgi hiyerarşisi. Ana odak, kullanıcının iş sorusunu
yazacağı alan ve cevabı anlamlandırmasını sağlayan grafiklerdir.

- Ana mesaj: **Büyük resmi görün.**
- Ana eylem: **Verine Sor**.
- Navigasyon: genel bakış, panolar, bütçe, sorgular, rapor takvimi ve uyarılar.
- Ana içerik: dört özet gösterge, satış karşılaştırma grafiği, içgörüler ve panolar.
- Renkler: zemin `#090D12`, yüzey `#111820`, vurgu `#63E6CE`.
- İkincil açıklamalar okunabilir olmalı; dikkat gerektiren durumlar amber kullanır.

## Kapsam

Bu çıktı görsel tasarım önizlemesidir. Gösterilen sayılar örnektir; gerçek API/DB
sonuçları değildir. Üretim arayüzüne veya sunucuya uygulanmamıştır.
API anahtarı bu dosyalarda saklanmaz.

## Uygulama eşlemesi

- Uygulama kabuğu: `src/components/Layout.tsx`, `src/components/Sidebar.tsx`.
- Ana pano: `src/pages/BiSupersetPage.tsx`.
- Doğal dil analizi: `src/pages/BiChatPage.tsx` ve mevcut sohbet bileşenleri.
- Menü: `src/lib/navGroups.ts`.
- Tasarım değişkenleri: `src/index.css`.

Üretime uygulamada mevcut kimlik doğrulama, izinler, API çağrıları ve sorgu akışları
korunmalı; örnek göstergeler gerçek veri yerine kullanılmamalıdır. Boş, yükleniyor,
hata ve belirsiz soru durumları ayrıca tasarlanmalıdır.
