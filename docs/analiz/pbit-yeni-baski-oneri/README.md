# 2025 Yeni Baskı Öneri Raporu — .pbit çözümlemesi

Kaynak: `Yandex.Disk/TİMAŞ/2025_Yeni_Baskı Öneri Raporu (5).pbit` (2026-09-22 tarandı).
Biçim: PBIR (yeni Power BI rapor biçimi), tema CY24SU05, sayfalar 1280×720.

Bu klasörde:

- `sql/<Tablo>.sql` — her tablonun kaynağa giden SQL'i, Power Query kaçışları (`#(lf)`, `""`) çözülmüş, çalıştırılabilir halde.
- `m/<Tablo>.pq` — ham Power Query (M) ifadesi; SQL sonrası birleştirme adımları burada.

## 1. Veri kaynakları

| Tablo | Sunucu / DB | Ne döndürür |
|---|---|---|
| `Logo_SatisHizi` | 192.168.0.25 / LOGO_DB | Stok kodu başına dönemsel satış adetleri ve ağırlıklı satış hızı (`V_SatisRaporu_All2`, `Yıl >= 2024`) |
| `Logo_YeniKitapSH` | 192.168.0.25 / LOGO_DB | Son 12 ayda ilk yayını olan kitapların satış hızı + ay pivotu (`V_SatisRaporu_2025_2026` ⨝ linked server `CRMDATABASE.Timas_MSCRM.dbo.new_kitap`) |
| `Logo_FiyatList` | 192.168.0.25 / LOGO_DB | Stok kodu başına son fiyat ve fiyatın başladığı tarih (`PBI_FiyatList`) |
| `Logo_Stok` | 192.168.0.25 / LOGO_DB | Depo stoku (`EOS_DEPO_STOK_KONTROL_211`, `157%` kodlar hariç) |
| `Sorgu3` | 192.168.0.25 / LOGO_DB | Son 12 ay, stok kodu × ay (Ocak…Aralık) satış adedi pivotu |
| `CRM_KitapDetay` | 192.168.0.28 / Timas_MSCRM | `powerbikitap` ⟕ `powerbikitapdetay`, baskı tarihi geçen yılın bu ayından eski olanlar |
| `CRM_YeniKitapDetay` | 192.168.0.28 / Timas_MSCRM | Aynı birleşim, tarih süzgeci yok |
| `Sorgu1` | 192.168.0.28 / Timas_MSCRM | Son 30 günde girilen baskı önerileri (`new_baskioneri` → `new_kitap`) |
| `Sorgu2` | 192.168.0.28 / Timas_MSCRM | Açık sipariş satırları (`new_siparis`/`new_siparissatiri`, B2C ve kapanmış durumlar hariç, 2 cari hariç) |
| `CRM_BekleyenSiparis` | 192.168.0.28 / Timas_MSCRM | Son 2 haftanın bekleyen sipariş adedi (`pbi_bekleyen_sip`) — raporda hiçbir görselde kullanılmıyor |

Not: Logo burada **192.168.0.25 / LOGO_DB** üzerinden okunuyor (bizim bağlantımız .155). `V_SatisRaporu_All2`, `V_SatisRaporu_2025_2026`, `PBI_FiyatList`, `EOS_DEPO_STOK_KONTROL_211` görünümlerinin .155'te karşılığı olup olmadığı ayrıca denetlenmeli.

### Power Query sonrası adımlar

- `Logo_SatisHizi` ⟕ `CRM_KitapDetay` (`Malzeme/Hizmet Kodu = StokKodu`) → `CRM_KitapDetay.StokAdedi` sütunu eklenir; `SatisHizi` → `OrtSatisHizi` olarak yeniden adlandırılır.
- `Logo_YeniKitapSH` ⟕ `CRM_YeniKitapDetay` (`new_stokkodu = StokKodu`) → `CRM_YeniKitapDetay.StokAdedi` eklenir.

## 2. Hesap mantığı

### Dönemler (`Logo_SatisHizi`, hepsi tamamlanmış aylar, bu ay hariç)

| Sütun | Dönem | Dikkat |
|---|---|---|
| `Ilk6Ay` / `Ilk6AyOrt` | Son 6 ay (−6 … −1) | Adı "ilk" ama **en yeni** 6 ay |
| `Son6Ay` / `Son6AyOrt` | Önceki 6 ay (−12 … −7) | Adı "son" ama **eski** 6 ay |
| `Ceyrek1..4` / `…Ort` | 1 = son 3 ay, 4 = 10–12 ay önce | `Ort` = adet / 3 |
| `YillikToplami` / `…Ort` | Son 12 ay | `Ort` = adet / 12 |
| `BuAyinToplami` | 7 ay önceki ay sonu … geçen ayın 1'i | Adı "bu ay" ama aralık bu ayı içermiyor — sorgu hatası olabilir |

### Ağırlıklı satış hızı (SQL `SatisHizi` → `OrtSatisHizi`, aylık adet)

```
0,50 × Çeyrek1Ort + 0,10 × Çeyrek2Ort + 0,05 × Çeyrek3Ort + 0,20 × Çeyrek4Ort
+ 0,05 × Ilk6AyOrt + 0,05 × Son6AyOrt + 0,05 × YillikToplamiOrt      (toplam %100)
```

Çeyrek4'ün (geçen yılın aynı dönemi) %20 alması mevsimselliği yakalamak için.

### DAX

| Ad | Tür | Formül |
|---|---|---|
| `Tükenme Süresi` | ölçü | `SUM(CRM_KitapDetay[StokAdedi]) / SUM(Logo_SatisHizi[OrtSatisHizi])` — stok kaç ay yeter |
| `Marj` | hesaplı sütun | `StokAdedi / OrtSatisHizi − 1` |
| `Öneri` | hesaplı sütun | `Marj ≤ 0` Risk/Acil · `≤ 0,5` Kritik · `≤ 1` Karar Ver · `≤ 1,5` Takip Et · üstü Yeterli Stok |
| `Marj_Y`, `Öneri_Y` | hesaplı sütun | Aynı kural, `Logo_YeniKitapSH`: `StokAdedi / SonBirYilSatisOrtalamasi − 1` |
| `Bu Ay Tahmini` | hesaplı sütun | `BuAyinToplami / DAY(TODAY()) × 30` |
| `Çeyrek1..4`, `BuAY`, `İlk6`, `Son6`, `Tahmini Satış Hızı`, `TahminiSatışHızı`, `Ölçü` | ölçü/sütun | Görsellerde **kullanılmıyor**. Ağırlıkları SQL'dekinden farklı (50/10/5/20/20/5/5 = %115) — eski deneme kalıntısı |

### Yeni kitap hızı (`Logo_YeniKitapSH`, ilk yayını son 12 ayda olanlar)

| Sütun | Anlam |
|---|---|
| `SatisSuresi` | İlk yayından bugüne ay sayısı |
| `SonBirYilSatis` / `SonBirYilSatisOrtalamasi` | Son 12 ay adedi / `SatisSuresi` |
| `DagilimSatıs` | İlk yayın ayındaki satış (ilk dağıtım) |
| `RPTSatis` / `RPTHizi` | İlk yayından 1 ay sonrası satış (tekrar sipariş) / `SatisSuresi` |
| `SatisHiziTahmini` | `0,4 × SonBirYilSatisOrtalamasi + 0,6 × RPTHizi` |
| `BuAyinSatisi` | Bu takvim ayının satışı |
| `1..12`, `ToplamSatis` | `V_SatisRaporu_2025_2026` ay pivotu (yıl ayrımı yok — iki yılın aynı ayı toplanır) |

## 3. İlişkiler

Merkez `CRM_KitapDetay[StokKodu]` ve `Logo_SatisHizi[Malzeme/Hizmet Kodu]`. Çoğu çift yönlü.

| Kimden | Kime | Etkin |
|---|---|---|
| `CRM_KitapDetay.StokKodu` | `Logo_SatisHizi.Malzeme/Hizmet Kodu` | ✓ |
| `Logo_FiyatList.StokKodu` | `CRM_KitapDetay.StokKodu` | ✓ |
| `Logo_Stok.STOK KODU` | `CRM_KitapDetay.StokKodu` | ✓ |
| `Sorgu1.new_StokKodu` | `CRM_KitapDetay.StokKodu` | ✓ |
| `Sorgu2.StokKodu` | `Logo_SatisHizi.Malzeme/Hizmet Kodu` | ✓ (CRM_KitapDetay'a olan pasif) |
| `Sorgu3.Malzeme/Hizmet Kodu` | `Logo_SatisHizi.Malzeme/Hizmet Kodu` | ✓ (CRM_KitapDetay'a olan pasif) |
| `CRM_BekleyenSiparis.STOK_KODU` | `Logo_SatisHizi.Malzeme/Hizmet Kodu` | ✓ (CRM_KitapDetay'a olan pasif) |
| `CRM_YeniKitapDetay.StokKodu` | `Logo_YeniKitapSH.Malzeme/Hizmet Kodu` | ✓ |

## 4. Rapor ekranı

Her sayfa aynı iskelet: üstte 79 px yüksekliğinde dilimleyici şeridi, altında tam genişlik tek tablo (1280×~620).

### Sayfa 1 — Baskı Tekrar (açılış sayfası)

- **Dilimleyiciler** (soldan sağa): Öneri · Baskı Durumu · Yayınevi · Yazar · Statü · Ürün Adı
- **Sayfa süzgeçleri**: `Statü`, `BaskıTarihi` (değer seçili değil)
- **Görsel süzgeci**: Yayınevi *hariç* — Bi Kutu Oyun, Dikkat ve Zeka Akademisi, Sincap Kids, Sincap Kitap, Uçan Kitap, Bir Ocak Eğitim Yayıncılığı A. Ş., Ticari Ürünler
- **Tablo** — `Tükenme Süresi` artan sıralı (en önce bitecek kitap üstte). Sütunlar:
  1. Kimlik: StokKodu, Ürün Adı, Statü, Yazar, Yayınevi, Kitaplık, Dizi_Tür, SayfaSayısı, Üzeri_Fiyat
  2. Baskı: Baskı_Durum, SonBaskıTarihi, Son Fiyat Değişiklik (`Logo_FiyatList.MinDateField`), Baskı_Adet
  3. Stok/talep: StokAdedi (CRM), Stok (Logo depo), Bekleyen Sipariş (`Sorgu2.Sip_Adet`), Öneri Adet (`Sorgu1`, son 30 gün)
  4. Hız: YillikToplami, OrtSatisHizi, YillikToplamiOrt, **Tükenme Süresi**, Marj, **Öneri**, Ilk6AyOrt, Son6AyOrt, Ceyrek1Ort…Ceyrek4Ort
  5. Son 12 ay: Ocak … Aralık (`Sorgu3`)

### Sayfa 2 — Yeni Kitap

- **Dilimleyiciler**: Yayınevi · Baskı Durumu · Yazar · Öneri_Y · Ürün Adı
- **Sayfa süzgeci**: `CRM_KitapDetay.Statü ∈ {YS04 Aktif, YS10A Ürün Fazlası - Stok Eritilecek Ürün (Yeniden Basılabilir)}`
- **Görsel süzgeci**: Yayınevi *hariç* — boş, Bi Kutu Oyun, Bir Ocak Eğitim Yayıncılığı A. Ş., Gülce Kids, Gülce Kinder, Karizma, L&M, Lacivert, Mavi Kirpi Kitap, Sincap Kids, Sincap Kitap, Uçan Kitap
- **Tablo** — `SonBirYilSatis` azalan. Sütunlar: Malzeme/Hizmet Kodu, Ürün Adı, Yazar, Yayınevi, Kitaplık, Dizi_Tür, SayfaSayısı, Üzeri_Fiyat, IlkYayinTarihi, SonBaskıTarihi, Baskı_Durum, Baskı_Adet, StokAdedi, SatisSuresi, SonBirYilSatis, SatisHiziTahmini, SonBirYilSatisOrt, RPTSatis, RPTHizi, Marj_Y, **Öneri_Y**, BuAyinSatisi, DagilimSatıs, Ocak … Aralık

Not: Sayfa süzgeci `CRM_KitapDetay` üstünde ama tablo `CRM_YeniKitapDetay` ile kurulu; ikisi arasında ilişki yok, bu süzgeç tabloyu etkilemiyor olabilir.

### Sayfa 3 — Set Kitaplar (gizli, `HiddenInViewMode`) — **kırık**

- Dilimleyiciler: Öneri · Baskı Durumu · Yayınevi · SetTip
- Tablo `Logo_Setler` tablosuna bağlı; **bu tablo modelde yok** (silinmiş). Sayfa bu haliyle veri göstermez. Sütun listesi `Baskı Tekrar` ile aynı mantık (YillikToplami, Ceyrek1..4Ort, SatisHizi, TükenmeSüresi, Marj_, Öneri_), `YillikToplami` azalan.

## 5. Kullanılmayan / kalıntı

- `CRM_BekleyenSiparis` tablosu — görselde yok (bekleyen sipariş `Sorgu2`'den geliyor).
- `Logo_SatisHizi` ölçüleri `Çeyrek1..4`, `BuAY`, `İlk6`, `Son6`, `Ölçü`, `TahminiSatışHızı` ve hesaplı `Tahmini Satış Hızı`.
- Görsel süzgeçlerinin çoğu (Ceyrek, Marj, Ocak…) değer içermiyor; PBI'ın alan ekleyince kendiliğinden açtığı boş süzgeçler.
