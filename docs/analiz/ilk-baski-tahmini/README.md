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

## Yazar geçmişi (2026-10-06)

Soru (kullanıcı): emsal puanında «aynı yazar» var ama yazarın satış gücü ayrıca ölçülüyor mu? Ölçülmüyordu: aynı
yazarın kitapları K emsal içinde seyreliyordu. Örnek: Mert Arık «Babası Kılıklı» (Ağustos 2026) — yazarın önceki 11
kitabı ilk 6 ayda 65–148 bin sattı (tipik ~113 bin), emsal tahmini 9.091 (öneri 15.000); yayınevi 100.000 bastı,
ilk 2 ayda 80.586 satıldı.

**Ölçüm (canlı veri kümesi, 2026-09 son tam ay; `betikler/yazar_bt.py`, `tani.py`):** sınama kitaplarının %61'inde
(820'de 501) yazarın ilk 6 ayı dolmuş önceki kitabı var. Yazarı çok satan (≥3 önceki kitap, ortanca ≥20 bin) 21
sınama kitabında emsal tahmini gerçekleşenin ortanca **7,5 kat** altında; yalnız yazar ortancası bu kitaplarda çok daha
isabetli (|log| ortancası 2,03 → 0,49). Sıradan yazarda tersi: emsal tahmini yazar ortancasından iyi (dağınık
geçmişte yazar ortancası 1,15, emsal 0,65). Sonuç: yazarın ağırlığı sabit olamaz, kitap sayısına ve tutarlılığa bağlı.

**Yöntem (`ilk_baski_model.author_effect`, `AUTHOR`):** yazar düzeyi μ = önceki kitapların log ilk 6 ayının yaşla
(e^(−yaş/2 yıl)) ağırlıklı ortalaması; dağınıklık s² önsel s0 = 0,3 ile (ν = 3 kitap) yumuşatılır; ağırlık
a = n / (n + 16 · s²) (n etkin kitap sayısı); çarpan = exp(a · (μ − log baz₆)). Çarpan yalnız ilk 6 aydan hesaplanır
ve 12 aya aynen uygulanır (ayrı ayar seçilince 12 ay tahmini 6 aydan küçük çıkıyordu). Emsal ayarları (`PARAMS`)
değişmedi; yazar ayarları **2019-01…2023-12** lansmanlarıyla seçildi (2021-07 sonrası dönemde çok satan yazar örneği
yalnız 1 idi), sınama 2024+ (seçimde yok). Denenip bırakılanlar: sabit ağırlıklı harman (A), yazarın kendi tahmin
artığı (B) — ikisi de çok satan yazarı düzeltmedi; tutarlılık ağırlıklı artık (CB) 6 ayda CA'ya yakın, Babası
Kılıklı'yı 33 bin veriyor.

**Sonuç (raporun kendi sınaması, kalibrasyon dahil; yazarsız → yazarlı):**

| | 6 ay (820) | 12 ay (630) |
| --- | --- | --- |
| Tipik sapma | %47,2 → **%45,9** | %55,1 → %55,4 |
| Toplam adette sapma (WAPE) | %67,5 → **%60,5** | %73,0 → **%67,9** |
| 2 kat içinde | %63,7 → %64,5 | %54,6 → %54,0 |
| %80 aralığın kapsaması | %74,4 → **%77,8** | %71,7 → %73,5 |
| Önerilen baskıda 6 ayda tükenme | %21,5 → %21,2 | — |

Çok satan yazarlı 21 kitapta (6 ay): tahmin/gerçekleşen yanı 7,5 kat → 2,1 kat; 2 kat içinde %10 → %43.
Babası Kılıklı: baz 8.302 → 61.071, öneri 15.000 → **102.000**, 12 ay baz 14.162 → 105.758.

Sınır: yazar kırılımı (Anıl Basılı «Anne Terliği»: geçmiş ~20 bin, gerçekleşen 132 bin) öngörülmez; yazarın düşüşü
(Talha Uğurluel: geçmiş ~22 bin, yeni kitaplar 3–6 bin) çarpanı yanıltır. Aynı eserin özel baskısı («Bez Ciltli»)
yeni kitap sayılıyor ve yazar geçmişini aşağı çeker — ayrı iş.

## Stok ve yeniden baskı (2026-10-06)

Soru (kullanıcı): «Babası Kılıklı» için firma «stok yetmedi» diyerek 100.000 daha bastı; ekran 12 ay revize tahmini
(194.353) gösteriyordu ama «stok bitecek, şu kadar daha basın» demiyordu. Kitap bir yılı doldurana kadar yeniden baskı
uyarısı yoktu (Baskı Öneri'nin yeni kitap görünümü Power BI formülü: stok ÷ son 1 yıl ortalaması).

**Yöntem (`Engine.reprint`, `calibrate_revise`):** elde kalan = Logo depo stoku (`EOS_DEPO_STOK_KONTROL_211`, Baskı
Öneri ile aynı; 2026 kitapları için güncel — Babası Kılıklı 16.955 ≈ 100.000 − 80.586) − CRM bekleyen sipariş (aynı
kural). 12. aya kadar kalan satış = 12 ay revize − gerçekleşen, emsallerin aylık payıyla aylara bölünür; birikimli
satış elde kalanı geçtiği ay tükenme ayı. Aralık: seçim döneminde (12 ayı gözlenmiş 842 kitap) gerçekleşenin revize
tahmine oranı, gerçekleşen ay sayısına göre (%20 / %50 / %80; m = 2'de 0,68 / 0,96 / 1,46). Ek baskı üste
yuvarlanır (10 bine kadar binlik, 50 bine kadar 5 binlik, üstü 10 binlik; ilk baskı basamakları 30.000'den sonra
100.000'e sıçradığı için kullanılmadı). Durum: stok yok · acil (< 2 ay) · gerekli (12. ay dolmadan biter) · yeterli.

**Sınama (2024+, 630 kitap):** kalan satışın (12 ay − ilk m ay) tipik sapması m = 1…11 için %70–%79 — tek sayı
olarak zayıf; bu yüzden ekran aralığı ve bu sapmayı yanında gösterir. Stokun geçmiş hâli tutulmadığı için tükenme
ayının kendisi geçmişte sınanamaz.

**Bugünkü sonuç (stok 2026-10-06):** takipteki 357 kitaptan 26 acil, 7 stok yok, 58 gerekli, 237 yeterli. Babası
Kılıklı: elde 15.135, Kasım 2026'da tükenir, Temmuz 2027'ye kadar kalan satış 106.670 → ek baskı 91.535 → öneri
**100.000** (aralık 36.128 – 187.352); firma 100.000 bastı. CRM'de ikinci baskı henüz yok (baskı sayısı 1).

## Açık noktalar

- Canlı Logo (.25) yok: satış 17.08.2026'da bitiyor; Ağustos–Eylül 2026'da çıkan kitaplar «yayımlanacak» listesinde.
- Tükenen kitapların ilk baskı adedi (adil karşılaştırma) ve birim maliyet (M9) yok; ciro var, katkı yok.
- Pazarlama planı (M15) ve yazar bilinirliği (M7 sosyal medya) şartnamede var, veri kaynağı yok; yazar etkisi «aynı
  yazar» emsali ve yazar geçmişi çarpanıyla giriyor (yalnız yazarın daha önce bizde çıkmış kitapları).
- CRM emsal bağının girildiği tarih tutulmuyor: sınamada emsal, kitabın bugünkü kartından okunuyor (çıkıştan sonra
  eklenmiş emsal sınamayı iyimser gösterebilir).
- Ayarlar kitap + set karışık havuzda seçildi; kapsam kitaba daraltılınca yeniden seçilmedi (sınama sayıları kitap
  kapsamıyla).

Betikler `betikler/`: `bt.py` (ayar seçimi ve sınama), `bt2.py` (Aşama 2 zaman serisi deneyi), `yazar_bt.py` (yazar
geçmişi yöntemleri ve ayar seçimi), `tani.py` (yazar geçmişi isabeti, kitap sayısı ve dağınıklığa göre). Test sunucusunda koşar.
