# TimesFM 3.0 × Yeni Baskı Öneri — geriye dönük değerlendirme (2026-09-24)

Soru: Baskı Tekrar havuzunda (5.053 kitap) TimesFM 3.0, Power BI şablonunun ağırlıklı satış hızından
(0,50·son 3 ay + 0,20·10–12 ay önce + …) daha iyi talep ve tükenme kararı veriyor mu?

## Veri ve yöntem

- Satış: Logo yıllık satış görünümleri `V_SatisRaporu_<yıl>` (ALL2 ile aynı satırlar), kitap × ay, 2015-01…2026-07.
  Logo .155 (`AISERVER`) 17.08.2026'da donmuş kopya; son tam ay Temmuz 2026.
- Stok: Logo `LV_<firma>_01_STINVTOT`, kesim gününe kadar `SUM(ONHAND)` (2021–2025 firma 211, 2026 firma 411).
  Doğrulama: 17.08 stoku raporun depo stokuyla 5.053/5.053 birebir.
- Kesimler: 2024-07 (12 ay), 2025-01 (6), 2025-07 (12), 2026-01 (6). Kesimden önce en az 12 ay geçmişi olan kitaplar.
- Yöntemler: Power BI hızı (düz), geçen yılın aynı ayı, TimesFM 3.0 (CPU, 24 iş parçacığı) beş ayarla:
  temel, simetrik ortalama, mevsim ek değişkeni (ay sin/cos + eylül-ekim işareti, geçmiş+gelecek),
  mevsim + portföy büyümesi (bütün kodların log toplam satışı, yalnız geçmiş), log dönüşümü.
- Karar: aynı Logo stoku ile tükenme ayı; gerçek = gerçek aylık satışın stoku aştığı ay.

## Sonuç

| 4 kesim ortalaması | dönem toplamı WAPE | aylık WAPE |
| --- | --- | --- |
| Power BI hızı | %38,8 | %62,4 |
| Geçen yılın aynı ayı | %40,1 | %68,3 |
| TimesFM temel | %35,1 | %55,4 |
| TimesFM mevsim + portföy | **%35,0** | **%55,0** |

- TimesFM dört kesimin dördünde de dönem toplamında Power BI'dan iyi (−1,5 … −6 puan), aylıkta −6 … −10 puan.
- Okul dönemi zirvesi (eylül-ekim) sapması: Power BI −%45/−%49, TimesFM temel −%41/−%51,
  mevsim + portföy ek değişkeni ile −%27/−%33. Zirveyi hâlâ eksik tahmin ediyor; zirve her yıl büyüyor
  (eylül+ekim / diğer aylar: 2022 1,39 → 2025 2,32).
- Simetrik ortalama +0,1 puan, maliyet 2×: gereksiz. Log dönüşümü geri dönüşte taştı: kullanılmaz.
- p10–p90 aralığı gerçeği %88–92 kapsıyor (hedef %80): biraz geniş, temkinli.
- "2,5 ay içinde tükenir" uyarısı: Power BI %44–58 yakalıyor, TimesFM p50 %46–66 (dört kesimde de ≥).
  TimesFM p80 %77–91 yakalıyor ama boşuna uyarı 2–3×.
- "6 ay içinde tükenir": karışık; 2025-07'de TimesFM belirgin iyi (%76 / %66), 2026-01'de Power BI
  yakalamada iyi (%62 / %57) ama TimesFM isabette iyi (%56 / %49). TimesFM p80 %88–95 yakalıyor.
- Tükenme ayı mutlak hatası: TimesFM dört kesimin üçünde düşük (ör. 2025-07: 1,39 / 1,64 ay).
- CRM yayınevi kırılımı (2025-07): TimesFM en büyük 6 yayınevinin hepsinde iyi; en büyük kazanç
  Timaş Yayınları (%53,6 → %43,0) ve Eğlenceli Bilgi (%35,5 → %28,0).
- Süre: 5 bin kitap, temel ayar ~30 sn, ek değişkenli ~150 sn (CPU) — gecelik iş için yeterli.

## Stok maskeleme deneyi (2026-09-24)

Logo `STINVTOT` günlük stoğundan kitap × ay stoksuz gün sayısı çıkarıldı (2021-01…2026-07; en az 7 gün stoksuz = kayıp talep ayı).
Kitap-ayların %18,8'i işaretlendi ama bunların %77'si ilk satıştan önceki aylar (yayın öncesi); yayından sonra oran %5,1
ve bu aylar satışın yalnız %0,9'u. Maske (NaN → motorun doğrusal ara değeri), ek değişken (stoksuz gün oranı) ve ikisi
birlikte denendi: WAPE değişimi ≤0,5 puan, zirve sapması aynı (−%28 / −%33). Sonuç: bu veride kayıp talep küçük;
zirve açığının sebebi her yıl büyüyen ve sivrileşen talep. Üretimde maske yok.

Portföy serisini yalnız havuz kitaplarından kurmak da denendi (2025-07: %32,9 / %33,0; 2026-01: %37,2 / %36,9): fark ≤0,3 puan.
Üretimde geçmiş yıl yıl okunduğu için portföy yine bütün kodlardan kurulur.

## Üretimdeki karşılığı

Baskı Öneri raporunun "ZEKI AI Tahminleme" sekmesi (`semantic_bridge/management/zeki_tahmin.py`): gizli rapor
`baski-oneri-tahmin` günde bir Logo'dan 2015'ten bu yana aylık satışı yıl yıl okur, tahmin servisinin
`POST /forecast/batch` ucuna (TimesFM 3.0, takvim + portföy ek değişkeni) gönderir. Sekme canlı CRM stoku ve bekleyen
siparişle tükenme ayını, baskı ihtiyacını ve ZEKI önerisini Power BI önerisinin yanında gösterir; altında son kullanıcı
açıklaması, bu sınamanın tablosu ve SQL'ler var. Power BI sekmeleri değişmez (test: tahminle ve tahminsiz birebir).

## Açık noktalar

- Zirve açığı (−%27…−%33) sürüyor; sıradaki aday okul dönemi için ayrı büyüme/ölçek düzeltmesi.
- Canlı Logo olmadan tahmin Temmuz 2026'dan başlar; müşteriye gösterilmeden önce canlı kaynak şart.

Betikler `betikler/`: `fc_extract.py` (aylık satış + CRM), `fc_stock.py` (kesim stokları), `fc_exp.py`
(TimesFM ayarları, `timesfm-venv`), `fc_eval.py` (ölçütler). Test sunucusunda `/tmp/fc` altında koşar.
