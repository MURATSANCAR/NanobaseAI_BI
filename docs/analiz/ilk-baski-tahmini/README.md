# M10 İlk baskı ve satış tahmini — yöntem ve geçmiş sınama (2026-09-28)

Soru: yeni çıkacak bir kitabın ilk 6 ve 12 aylık satışı, çıkıştan önce ne kadar isabetle tahmin edilebilir; ilk baskı
kaç adet olmalı?

## Veri

- **Satış:** Logo yıllık satış görünümleri `V_SatisRaporu_<yıl>` (Baskı Öneri'nin okuduğu satırlar, aynı süzgeç),
  kitap × ay × `KANAL`, net adet (iade düşülmüş), net tutar, liste tutarı; 2015-01 … 2026-07 (Logo .155 kopyası
  17.08.2026'da donmuş, son tam ay Temmuz 2026). 1,43 milyon satır, yıl yıl okunur (yıl başına 15–75 sn).
- **Kitap kartı:** CRM `new_kitap` + Baskı Öneri'nin `powerbikitap` görünümü: yazar, dizi, kitaplık, yayınevi, hedef
  kitle, tür, sayfa, fiyat, ilk yayın tarihi (UTC → İstanbul).
- **Emsal:** CRM `new_new_kitap_new_emsalkitap3Base` — editörün kitap kartına girdiği emsaller (19.417 bağ; geçerli
  lansmanların %89'unda (3.104 / 3.489) en az bir emsal var; 2021 sonrası emsallerin %98'i kitaptan önce çıkmış).
- **Baskı adetleri:** `powerbikitap.[Baskı Sayısı]` + `powerbikitapdetay.Baskı_Adet` (son baskı). CRM `new_UretimBase`
  2023'ten beri adet taşımıyor; ilk baskı adedi yalnız hiç yeniden basılmamış kitapta bilinir.
- **Kapsam:** yalnız `15201` stok kodları (kitap). 15205/15206 set, 15204/15304 dergi, 157xx e-kitap/öğretmen
  kılavuzu/bülten, 15301/15305 ticari ürün dışarıda (CRM `powerbikitap.Tip` ile ölçüldü).

## Lansman tanımı

Kitabın Logo'daki ilk net satış ayı. CRM ilk yayın ayıyla karşılaştırma (2021-01…2026-02, 4.333 kart): fark 0 ay
1.646, +1 202, +2 133, +3 67, −1 71; 6+ ay 243 (başka baskının/kodun devamı); satışı hiç olmayan 1.895 (çoğu 157xx
e-kitap kodu). Karar: fark en çok ±3 ay olan lansman emsal olur; 2015 başına yapışık satış «lansman gözlenmedi» sayılır.
Sonuç: 3.489 geçerli kitap lansmanı (2016–2026).

## Yöntem

1. **Emsal puanı:** CRM emsali (6) + aynı yazar + aynı dizi (2) + kitaplık + yayınevi + tür + fiyat yakınlığı (fiyat
   çıktığı yılın lansman fiyatı ortancasına oranlanır; enflasyondan arınır) + sayfa yakınlığı; lansman yaşı ile
   e^(−yaş/3 yıl). Yalnız kesimde ilk 6 / 12 ayı tamamen gözlenmiş kitaplar aday.
2. **Baz tahmin:** en yüksek puanlı K emsalin (6 ay: 15, 12 ay: 10) ilk 6 / 12 ay satışının puan ağırlıklı ortancası.
3. **Senaryolar ve aralık:** seçim döneminde gerçekleşen / tahmin oranlarının %10/%20/%50/%80/%90 noktaları, güven
   düzeyine göre (yüksek: ≥3 güçlü emsal — CRM emsali, aynı yazar ya da aynı dizi; orta: 1–2; düşük: yok).
4. **İlk baskı:** kurallar ölçüldü (aşağıda); öneri ilk 6 ayın iyimser senaryosu, yayınevinin geçmişte kullandığı
   en yakın üst ilk baskı adedine yuvarlanır (200 … 30.000 basamak, CRM'den). Asgari: 6 aylık baz.
5. **Aşama 2 (ilk satış takibi):** gerçekleşen ilk m ay × emsallerin m. aydan 6. / 12. aya büyümesi.
6. **Kanal ve ciro:** emsallerin ilk 6 ayındaki `KANAL` payları; ciro = adet × kapak fiyatı × emsallerin net / liste
   tutar oranı.

Ayarlar koordinat inişiyle, amaç ortanca |log(gerçekleşen / tahmin)|, **yalnız 2021-07…2023-12 lansmanlarıyla**
seçildi (`betikler/bt.py fit`). Aşağıdaki bütün sınama sayıları 2024-01 sonrası lansmanlardır (seçimde yoktu).
Her kitap çıkıştan **2 ay önceki** veriyle tahmin edildi (baskı kararı anı).

## Sonuç (sınama: 2024-01…2026-02 çıkışlar)

| İlk 6 ay (760 kitap) | ZEKİ AI emsal | Yalnız CRM emsali | Son 12 ayın ortancası |
| --- | --- | --- | --- |
| Tipik sapma (ortanca \|t−g\|/g) | **%45,3** | %60,6 | %71,2 |
| ±%25 içinde | %26,2 | %19,1 | %11,8 |
| ±%50 içinde | %44,3 | %35,0 | %21,6 |
| 2 kat içinde | %63,9 | %52,8 | %37,4 |
| Toplam adette sapma (WAPE) | %66,8 | %119,3 | %83,8 |
| Yön (gerçekleşen / tahmin ortancası) | 1,06 | 0,78 | 1,42 |
| %80 aralığın kapsaması | %74,2 | — | — |

İlk 12 ay (2024-01…2025-08, 580 kitap): tipik sapma **%54,8** (CRM emsali %77,0, ortanca %79,8); 2 kat içinde %55,9;
aralık kapsaması %68,1.

Güven düzeyine göre (6 ay): yüksek 613 kitap %42,4 sapma, aralık %78,3 tuttu; orta 98 kitap %62,0 / %61,2; düşük
49 kitap %68,7 / %49,0. 12 ayda düşük güvende aralık %34 tuttu — düşük güvenli tahmin tek başına kullanılmamalı.

**Kitap çıktıktan sonra** (revize, ilk 6 ay): 1 ay gerçekleşince %26,8, 2 ay %18,2, 3 ay %12,1 tipik sapma.

### İlk baskı adedi kuralları (12 ayı gözlenmiş 580 kitap)

| Kural | Ortanca adet | 6 ayda tükenen | 12 ayda tükenen | 12. ay sonunda elde kalan |
| --- | --- | --- | --- | --- |
| İlk 6 ay, baz | 2.000 | %41,7 | %55,9 | %0 |
| **İlk 6 ay, iyimser (öneri)** | 4.000 | %21,6 | %32,4 | %33,9 |
| İlk 6 ay, aralığın üstü | 5.000 | %14,7 | %24,3 | %49,4 |
| İlk 12 ay, baz | 3.000 | %34,8 | %46,2 | %7,3 |
| İlk 12 ay, iyimser | 4.500 | %17,9 | %25,3 | %49,7 |
| Yayınevinin gerçek ilk baskısı (yalnız tek baskılı 213 kitap) | 3.000 | %2,8 | %4,2 | %51,3 |

Yayınevi satırı seçim yanlılığı taşır: CRM ilk baskı adedini yalnız hiç yeniden basılmamış kitapta verir; tükenip
yeniden basılan kitap o satıra giremez. Adil karşılaştırma için tükenen kitapların ilk baskı adedi gerekir (açık).

**Karar (iş kararı, gerekçeli):** öneri = ilk 6 ayın iyimser senaryosu. Baz (şartnamedeki «asgari: 6 aylık tahmin»)
kitapların %42'sinde 6 ay dolmadan tükeniyor; aralığın üstü ve 12 ay iyimser elde kalanı %50'ye çıkarıyor. Kitap 12.
aydan sonra da sattığı için elde kalan çoğunlukla sonraki ayların stokudur; tükenme ise yeniden baskı süresince
kayıp satıştır. Ekranda bütün kurallar kitap başına tükenme olasılığıyla birlikte seçenek olarak durur.

### Şartname hedefleriyle

- «Tahmin sapması < %20»: çıkıştan önce **tutmuyor** (%45 tipik sapma). Çıkıştan 2 ay sonra revize tahmin %18 ile
  tutuyor. Yeni kitabın satışı özünde belirsiz; ekran tek sayı değil senaryo ve aralık gösterir.
- «Stok tükenmesi < %5»: hiçbir kural tutturmuyor (en düşük %14,7, elde kalan %49). %5 için aralığın çok üstü basmak
  gerekir.

## Tahmin servisi (zaman serisi modeli) denemeleri

1. **Pazar düzeyi düzeltmesi:** emsalin satışı, kendi dönemindeki portföy toplamıyla yeni kitabın dönemindeki portföy
   toplamının oranıyla ölçeklendi (`beta` üssü; yeni kitabın dönemi tahmin servisinin o güne kadarki veriyle yaptığı
   portföy tahmininden). 6 ay pencerede portföy tahmininin kendi hatası ortanca %20,7. Seçim döneminde iki ufukta da
   `beta = 0` seçildi (düzeltmesiz daha iyi) → kullanılmıyor; kod yolu (`market_factor`) duruyor.
2. **Aşama 2'de zaman serisi:** çıkıştan m ay sonra 12 aylık toplam (658 kitap), tipik sapma:

   | m | Emsal büyümesi | Zaman serisi modeli | İkisinin geometrik ortalaması |
   | --- | --- | --- | --- |
   | 2 | **%31,5** | %51,5 | %33,2 |
   | 3 | **%27,5** | %57,7 | %39,0 |
   | 4 | **%22,6** | %79,2 | %43,2 |
   | 6 | **%17,4** | %24,0 | %18,0 |

   Yeni kitabın düşüşünü (ilk ay dağıtım, sonra iniş) birkaç aylık geçmişten öğrenemiyor → kullanılmıyor. Kitap bir
   yılı doldurunca Baskı Öneri'nin tahmin sekmesi (M11, aynı model) devralır.

## Açık noktalar

- Canlı Logo (.25) yok: satış 17.08.2026'da bitiyor; Ağustos–Eylül 2026'da çıkan kitaplar «yayımlanacak» listesinde.
- Tükenen kitapların ilk baskı adedi (adil karşılaştırma) ve birim maliyet (M9) yok; ciro var, katkı yok.
- Pazarlama planı (M15) ve yazar bilinirliği (M7 sosyal medya) şartnamede var, veri kaynağı yok; yazar etkisi yalnız
  «aynı yazar» emsaliyle giriyor.
- CRM emsal bağının girildiği tarih tutulmuyor: sınamada emsal, kitabın bugünkü kartından okunuyor (çıkıştan sonra
  eklenmiş emsal sınamayı iyimser gösterebilir).
- Ayarlar kitap + set karışık havuzda seçildi; kapsam kitaba daraltılınca yeniden seçilmedi (sınama sayıları kitap
  kapsamıyla).

Betikler `betikler/`: `bt.py` (ayar seçimi ve sınama), `bt2.py` (Aşama 2 zaman serisi deneyi). Test sunucusunda koşar.
