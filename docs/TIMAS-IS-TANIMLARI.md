# TİMAŞ İş Tanımları — kararlar ve uygulama durumu

Güncelleme: 2026-09-17. Bu belge, soru-cevap motorunun uyguladığı iş tanımlarını ve her biri için verilen kararı tutar.
Kararlar operatör (Claude) tarafından canlı veri ölçümüne dayanarak verildi ve **kataloğa sertifikalı** ya da
**bilgi paketine kural** olarak işlendi; iş tarafı farklı bir tanım isterse aynı yerden değiştirilir
(`human_certify`, `configs/semantic/knowledge/logo/knowledge/`). Yayın: https://claude.ai/artifact/9yFqvrMRn9i4bAqWHnctwP

| # | Kavram | Karar (uygulanan tanım) | Nerede |
|---|---|---|---|
| 01 | Net ciro | Satış satırları (TRCODE 7,8,9) `LINENET` − iade satırları (2,3) `LINENET`; iptal ve hizmet dışı satır hariç. Satır düzeyi esas; başlık (`NETTOTAL`) ile ~%0,1 fark yuvarlama/hizmet satırı. | katalog `net ciro` (STLINE, 09-17: TRCODE 9 eklendi) |
| 02 | Maliyet | Satış satırlarında `AMOUNT × OUTCOST`; `OUTCOST = 0` satırlar dahil edilir, sayısı cevapta yazılır. | katalog `maliyeti` (09-17: kapsam 7,8,9 + iptal hariç) |
| 03 | Kâr | Satır `LINENET − AMOUNT × OUTCOST`; satış artı, iade eksi. CRM satış senaryosu kârı ayrı kavram: "senaryo kârı". | katalog `kâr` (yeni), `senaryo karı` genel eş anlamlıları kaldırıldı |
| 04 | Toptan / perakende / diğer | TRCODE 8 / 7 / 9 (fatura ve satır). İskonto oranı **satır düzeyinde**: iskonto satırı (LINETYPE 2) TOTAL / malzeme satırı (LINETYPE 0) TOTAL. | katalog `toptan`, `perakende`, `diğer satış`, `iskonto oranı`; APPROVAL okumaları reddedildi |
| 05 | Müşteri grubu (kanal) | `CLCARD.SPECODE2`; boş kod "Grup kodu boş" olarak raporlanır. | katalog `kanal` (+ müşteri grubu, cari grubu, grup kodu) |
| 06 | Planlanan tahsilat vadesi | Ödeme planı satırları (PAYTRANS MODULENR 4), vade günü = plan tarihi − fatura tarihi, **kalem başına ortalama** (tutar ağırlıklı istenirse ayrı ölçü). | bilgi paketi `caveats/logo-timas.md` |
| 07 | Gerçekleşen tahsilat süresi | Kapatan ödeme (CROSSREF) tarihi − fatura tarihi; 2026'da kapama kaydı yok → "hesaplanamaz" dürüst cevap. | bilgi paketi caveat |
| 08 | Açık alacak / yaşlandırma | Cari net bakiye (CLFLINE); yaşlandırma kapatılmamış plan satırlarının vadesine göre; 2026'da hesaplanamaz. | bilgi paketi caveat |
| 09 | Stok bakiyesi | Giriş (IOCODE 1,2) − çıkış (3,4), tarihsiz, **yalnız cari kopya** (açılış devri zaten içinde; eski yılla birleşim çift sayar). | katalog `stok bakiyesi` (durum ölçüsü) |
| 10 | Bekleyen sipariş | Satış sipariş satırı (TRCODE 1) `CLOSED = 0` **ve** `AMOUNT > SHIPPEDAMOUNT`, iptal hariç; adet = fiş sayısı (`ORDFICHEREF`). CRM "bekleyen ürün talebi" ayrı kavram. | katalog `bekleyen sipariş`, `bekleyen sipariş miktarı`; CRM `backorder` eş anlamlısı kaldırıldı |
| 11 | Stok devir hızı | Dönem satış adedi / ((açılış devri + güncel stok) / 2). | bilgi paketi `metrics/logo-timas.md` |
| 12 | Baskı | Üretim emri (`PRODORD`); "son üç baskı" = **tamamlanmış** (STATUS 3) en yeni üç emir. | katalog `baskı`, bilgi paketi Kural 9 |
| 13 | Çekilen malzeme | Sarf fişi satırları STLINE TRCODE 12, IOCODE 4, `PRODORDERREF` ile emre bağlı; reçete/karma koli planlanan bileşendir. | katalog `çekilen malzeme`, Kural 9 |
| 14 | Üretilen adet | Üretimden giriş STLINE TRCODE 13, IOCODE 1. | katalog `üretilen adet`, Kural 9 |
| 15 | Sipariş | Satış sipariş fişi `LG_ORFICHE` TRCODE 1, iptal hariç; adet = fiş sayısı. Alış siparişleri dahil değil. | katalog `sipariş` |
| 16 | Sevkiyat | STLINE TRCODE 7,8, IOCODE 4 (malzeme çıkışı); "hiç sevkiyat almamış müşteri" müşteri düzeyinde yokluk (NOT EXISTS). | katalog `sevkiyat`, Kural 10 |

İş tarafından hâlâ istenen teyitler: 01 iade düşümü, 02 maliyet alanı (OUTCOST), 04 iskonto tabanı (satır/başlık),
06 ağırlıklı ortalama, 07–08 borç kapamanın 2026'da çalıştırılması, 12 devam eden baskıların sayımı.
