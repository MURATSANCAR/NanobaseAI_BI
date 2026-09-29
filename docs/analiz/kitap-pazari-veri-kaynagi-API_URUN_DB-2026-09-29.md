# Kitap pazarı veri kaynağı — `API_URUN_DB` (Logo prod .25)

Ölçüm tarihi: 2026-09-29. Kaynak: canlı Logo sunucusu `192.168.0.25` (`LOGODATABASEN`), aynı SQL Server'da ayrı veritabanı.
Bütün rakamlar test sunucusundan `zekiai` hesabıyla doğrudan sorgulandı (`connector_from_file`, köprü env'i).

## Erişim

- `zekiai` önce `API_URUN_DB`'de yanlışlıkla **`db_datawriter`** rolündeydi (okuma yok, yazma var → her `SELECT` hata 229).
  TİMAŞ BT 2026-09-29'da düzeltti: şimdi yalnız **`db_datareader`**. Bu veritabanına hiçbir koşulda yazılmaz.
- `.25`'teki diğer veritabanlarına (`LOGO_DBN`, `LogoHizliSatisDB`, `LogoRobotPosDb`, `YEDEKTBLDB`, `PRODEYS`, `BORDRO_DB`,
  `SmIntegrationDb*`, `SYNC_LOGOTIGER*`) `zekiai`'nin erişimi yok.
- Görünüm tanımları (`sys.sql_modules.definition`) `VIEW DEFINITION` izni olmadığı için okunamıyor.

## Tablolar

| Tablo | Satır | Ne | Zaman |
|---|---:|---|---|
| `urun_list_BACKUP` | 7.525.932 | **Başarı Dağıtım** kataloğunun tarihli anlık görüntüleri (tek tedarikçi: Başarı Dağıtım) | 35 görüntü, 2024-03-21 → 2026-01-01; 2025-02'den beri ayın 1'i ve 15'i, öncesi aylık |
| `basari_list` | 234.705 | Başarı Dağıtım kataloğu, güncel tek görüntü (aynı kolonlar) | 2026-09-25 11:04 |
| `prefix_list` | 386.124 | **D&R** B2B kataloğu (`dr_price`, `list_price`, ISBN, `bread_crumb` kategori yolu, `available_stock`, `b2bstock`, satış durumu) | 2026-09-25 10:47 |
| `LOGO_TARCIN_ITEM_LIST` | 7.064 | Logo'dan «TARÇIN» özel kodlu ürünler (kod, ad, fiyat, barkod) | 2024-12-31 |
| `urun_raf` | 29 | Raf adları (Dünya Edebiyatı, Timaş Çocuk, Yuzu, Kutu Oyunları…) | 2026-01-21 |
| Görünümler | — | `urun_list`, `URUN_LIST_TO_LOGO`, `LOGO_TO_BASARI` (Logo ↔ Başarı barkod/fiyat eşleme) | — |

Başarı kolonları: barkod, ürün adı, yazar, çevirmen, marka (yayınevi), kategori (`Üst>Alt`), liste fiyatı, iskonto %,
iskontolu fiyat, baskı sayısı, basım yılı, sayfa, kâğıt, kapak, ebat, desi, `stok_durum`, `depo_stok`, görsel URL, tanıtım metni (HTML).

## Ne işe yarar

1. **Satış hızı vekili (sell-in):** aynı barkodun iki görüntüsü arasındaki `depo_stok` düşüşü = Başarı deposundan
   perakendeye çıkış (yeniden stoklama düşüşü gizleyebilir, alt sınırdır). 2025-12-01 → 2026-01-01: 221.964 ortak barkod,
   41.680'inde stok değişti, toplam düşüş 229.073 adet, 7.260 üründe fiyat değişti. En çok düşenler: Kızıl Kaftan (Ötüken)
   1.308→146, Ona Kadar Say 2 (Sia) 1.227→198, Katabasis (İthaki) 1.668→655; TİMAŞ'tan İyilik Timi (İlk Genç Timaş) 914→408.
2. **Pazar yapısı:** yayınevi başına başlık sayısı, kategori dağılımı, fiyat/iskonto seviyesi, baskı sayısı (kaçıncı baskı →
   çok satan işareti), baskısı biten başlıklar (`stok_durum`: Satışta 147.830, Baskısı Yok 52.594, Temin Edilemiyor 33.863).
3. **Rakip fiyatlaması:** Başarı liste/iskonto fiyatı ↔ D&R `dr_price`/`list_price`; zaman içindeki fiyat artışları.
4. **TİMAŞ'ın rafta görünürlüğü:** Başarı güncel — Timaş Çocuk 1.541 başlık (25.205 adet stok), Timaş Yayınları 1.289,
   Timaş Tarih 472, Genç Timaş 336, İlk Genç Timaş 251, Gülce Çocuk 188, Timaş Publishing 92, Timaş Akademi 66, Yuzu 37,
   Timaş İnanç 29, Uçan Kitap 25. D&R — Timaş Çocuk 1.385, Timaş Yayınları 1.346, Genç Timaş 419, Timaş İlk Genç 110,
   Timaş Akademi 49.

## Dikkat

- **Arşiv 2026-01-01'de duruyor.** `basari_list` ve `prefix_list` tek görüntü ve üzerine yazılıyor (tablo `modify_date`
  2026-05-15, veri 2026-09-25). Ocak–Eylül 2026 arası geçmiş yok. İleriye dönük hız ölçmek için görüntüleri bizim
  saklamamız gerekir (gece `basari_list`/`prefix_list` → `semantic_*` tablosu; kaynağa yazılmaz).
- 2024-08 (01 ve 07) ile 2025-02'den sonraki aylarda iki görüntü var; aylık toplamda çift sayma olmaması için görüntü
  tarihiyle çalışılmalı.
- Marka adları kaynaklar arasında farklı yazılıyor («Timaş İlk Genç» ↔ «İlk Genç Timaş», «Doğan Egmont» ↔ «Doğan ve Egmont
  Yayıncılık»); eşleme barkod/ISBN ile yapılmalı.
- D&R `deleted` alanı 382.203 satırda `1` (yalnız 3.920 satır `0`) ama bunların bir kısmında stok var; anlamı doğrulanmadan
  «aktif ürün» süzgeci olarak kullanılmamalı.
- `depo_stok` Başarı'daki stoktur, tüketiciye satış değildir. Stok artışı (yayınevinden giriş) aynı dönemdeki satışı gizler.
