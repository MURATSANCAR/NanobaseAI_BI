# Logo rapor kaynak kapsamı — 30 Eylül 2026

Bu belge fiziksel şema keşfi ve uygulama bağlarını kaydeder. Yeni raporların gerçek API kabulü bu çalışma sırasında **koşulmadı**; şema bulunması iş doğruluğu veya üretim kabulü değildir.

## Fiziksel envanter

Tek kalıcı SSH bağlantısı üzerinden, Logo'ya yalnız SELECT gönderilerek elde edildi. İlk bellekte biriktiren metadata süreci yalnız kendi PID'si doğrulanarak durduruldu; sonuç yerine gösterilmedi. Son koşu 500 satırlık parçalarla, yaklaşık 20 saniyede tamamlandı; işletme tablolarının tüm veri satırları taranmadı.

| Kapsam | Sayı |
|---|---:|
| Veritabanında görünür tablo/görünüm adı | 58.703 |
| Seçili 211/411 kaynaklarının bütün fiziksel dönemleri ve `L_` ortak tablolarının kolonları | 43.488 |
| Aynı kapsamda indeks kolonları | 9.441 |
| Veritabanında bildirilen fiziksel FK | 0 |
| Doğrulanan şirket dönemi kaynağı | 2 |

Diğer teknik yedeklerin nesne adları envanterdedir; kolon/indeksleri seçili şirket kapsamına dahilmiş gibi genişletilmedi. `211`: 2021-01-01–2025-12-31; `411`: 2026-01-01–2026-12-31. Bunlar ayrı şirket değildir. İki kaynakta da `PERLOCALCTYPE=160`, `PERREPCURR=1`; üretici döviz listesinde 160=TL, 1=USD, 20=EUR bulundu.

- Ham metadata SHA256: `fbeed86d53446e644af0624508fa11aecee1eb6b773141e23dc03af5eb8506db`
- Gzip dosya SHA256: `5bd2893f5536dc6571fa2e1c73a6b78ef8bc738aca372ba021bb82ad71023053`
- Kanıt kökü: `/Users/msancar/.codex/visualizations/2026/09/30/01a0f2ac-0c9e-7a23-8f10-1e43ca564e51/`
- Ham akış: `logo-physical-inventory-stream-20260930.jsonl.gz`
- Şablon/sayı özeti: `logo-physical-inventory-summary-20260930.json`
- Mod ve ilişki kapsamı: `logo-report-source-coverage-20260930.json`
- İlk dar şema, ilişki ve örnek keşifleri: `logo-report-schema-20260930.json`, `logo-report-relations-20260930.json`, `logo-report-source-status-20260930.json`.

## Bağlar ve sınırlar

| Rapor | Kullanılan aile/alanlar | Koruma / açık kalan |
|---|---|---|
| Stok ve stok geçmişi | `LV_*_STINVTOT.STOCKREF/INVENNO/DATE_/ONHAND`; `STLINE.STOCKREF/SOURCEINDEX/IOCODE/AMOUNT/UINFO1/UINFO2`; `ITEMS` | Günlük görünüm ile bağımsız yönlü hareket her anahtarda uzlaşmadan miktar sunulmaz. Farklı/bilinmeyen birim dönüşümü ve uyuşmazlıkta NULL + açık eksik. Fiziksel sayım doğrulaması değildir. |
| Açık sipariş | `ORFLINE.ORDFICHEREF → ORFICHE.LOGICALREF`, `STOCKREF → ITEMS`, `CLIENTREF → CLCARD`; `AMOUNT/SHIPPEDAMOUNT/CLOSED/CANCELLED/DUEDATE` | Satır birimi korunur. Oransal kalan net tutar yeni fatura değildir. Aynı stok siparişlere tekrar tahsis edilmez. Güncel kapalı/sevk alanından geçmiş tarihli açık durum üretilmez. |
| Müşteri bakiyesi | `CLFLINE.CLIENTREF → CLCARD.LOGICALREF`; `SIGN/AMOUNT/DATE_/CANCELLED` | Tek kaynak döneminde açılış + borç − alacak. Bilinmeyen SIGN sessizce atlanmaz. Bakiye açık fatura veya yaşlandırma değildir. Yıllık devirler toplanmaz. |
| Ödeme hareket türü | `CLFLINE` + `CLCARD`; mevcut açık collections sözleşmesindeki 1/20/61/62/70 | Çek/senet teslimi banka nakdi sayılmaz. Gerçekleşme ve fatura kapama kanıtı değildir. |
| İşlem para birimi | `INVOICE.TRCURR/TRNET/NETTOTAL`; `L_CURRENCYLIST` | Yerel ve işlem tutarı ayrı; dövizler birleştirilmez. Kimliği bulunamayan veya tutarı eksik işlem dövizinde sayısal özgün tutar tahmini yapılmaz. |
| Alış fiyatı | `STLINE` faturalı malzeme alışları + `ITEMS/CLCARD`; `UOMREF/UINFO1/UINFO2/TRCURR` | Birim, kaynak ve işlem para birimi ayrı gruplardır. Gerçek alış fiyatı satılan mal maliyeti değildir; kur etkisi otomatik ayrıştırılmaz. |
| Kesin yaşlandırma | `PAYTRANS.TOTAL/PAID/CROSSREF/FICHEREF/FICHELINEREF/MODULENR/DATE_/PROCDATE/MATCHDATE` fiziksel olarak var | Gerçek kapama kapsamı/ilişkisi kanıtlanmadı. Bounded CROSSREF>0 sorgusunun boş dönmesi bütün kapama yöntemlerinin bulunmadığı anlamına gelmez. TOTAL−PAID/FIFO ile kesin alacak üretilmez. |
| Kâr | `STLINE.OUTCOST/RETCOST/STDUNITCOST` fiziksel olarak var | Örneklerde OUTCOST=0; değerleme yöntemi ve tam kapsam doğrulanmadı. Son alış veya satış fiyatından kâr uydurulmaz. |

`STFICHE`, `BNFICHE`, `BNFLINE`, `BANKACC`, `KSLINES`, `KSCARD`, `CSCARD`, `CSROLL`, `CSTRANS`, `CSPAYMENT` aileleri envanterde bulunmaktadır. Kullanılmamaları atlandıkları anlamına gelmez: banka/kasa gerçekleşmesi, çek/senet yaşam döngüsü ve çapraz modül kapama ilişkisi henüz iş anlamı bakımından kanıtlanmadığından bu sonuçlar iddia edilmez. `STLINE.ORDTRANSREF`, `ORDFICHEREF`, `STFICHEREF` ve `CLFLINE.SOURCEFREF` fiziksel olarak incelendi; FK bulunmaması ilişkiyi otomatik doğrulamaz.

`ITEMS`, `CLCARD`, `ORFICHE`, `PAYTRANS` için LOGICALREF'e ait benzersiz anahtar indeksleri dar keşifte görüldü. Stok kodu/kişi adı gibi iş anahtarlarının tekilliği bununla aynı şey değildir.

## Stok alanı anlamının sınırlı bağımsız kanıtı

`logo-stock-meaning-20260930.json`: aynı gerçek stok kaydı ve depoda iki tarih için görünümün ONHAND toplamı bağımsız STLINE yönlü toplamıyla eşleşti:

- 16 Ocak sonu: `1050 = 1108 − 3 − 55`.
- 30 Eylül sonu: `659 = 1131 + 4 − 27 − 449`.

Bu tek kayda özel üretim kuralı değildir. Ürün kodu bütün istenen anahtarlarda aynı genel uzlaşma kontrolünü yapar. Bu bulgu günlük ONHAND hareketi yorumunu destekler; tüm stok raporlarının bağımsız gerçek API kabulünün yerine geçmez. `GNTOTST` dar örneğinin boş dönmesi sıfır stok diye yorumlanmadı. Görünüm tanımı mevcut hesapla NULL döndü; üretici SQL sözlüğü resmî web kaynaklarında bulunamadı ve üçüncü taraf blog bilgisi kesin alan anlamı sayılmadı.

## Kabul hazırlığı

`scripts/acceptance/finance_contracts/logo_reports_live.py` uzak sunucu için bağımsız gerçek kaynak satırlarından referans üretir; ürün SQL'ini veya derleyicisini import etmez. Aynı resultId'nin tam sonucu, kolonlar, kimlikler, sayısallar, NULL ve önizleme karşılaştırılır. Para biriminde/stockta doğrulanmış kısmın eşleşmesi `PARTIAL_REFERENCE_MATCH`; yaşlandırma/kâr sınırı `BOUNDARY_PASS` olarak ayrıca sayılır. Bunlar tam sayısal iş kabulü değildir. Tek ortak flock ve mevcut timasai hesabının 15 dakikalık temizlenen oturumu kullanılır. Bu koşucu bu çalışma sırasında çalıştırılmadı.

Kalıcı test sunucusu kanıt kopyası: `/data/nanobaseai/bi/acceptance/finance-expanded-20260930/schema/`.
