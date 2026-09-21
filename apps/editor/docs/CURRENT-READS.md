# Güncel ve kullanılabilir bilgi okuma sözleşmesi

2026-09-21 — sunucuda gerçek DB/API ve MCP okuma kabulü geçti.

`read_model.py`, kullanıcı okumalarını `current_artifact` ve onun değişmez bilgi sürümüne bağlar. Rapor, timeline, aktör, karakter geçmişi, olay/duygu/iddia listeleri ve kitap kartı bu sözleşmeyi kullanır. Güncel çıktı yoksa tarihsel `report`, `book_card` veya ham olay tablosuna geri dönüş yoktur. Hazır olmayan listeler gerçek boş sonuç gibi gösterilmez: HTTP 409 veya `available=false`, `total=null`.

En yeni nesil seçilir; eski mühürlü nesil yeni neslin önüne geçmez. Karakter adı yalnız kimlik adaylarını seçer; anılışlar, duygular ve olaylar karakter kimliği üzerinden bağlanır. Belirsiz kimlikler aday olarak kalır; doğrulanmış geçmişe katılmaz. Metin anılışında güncel kaynak hash/aralık eşleşmesi gerekir. Analitik kabul daima ayrıca belirtilir.

Üreticilerin doğrulama öncesi aday timeline okuması `candidate_timeline` olarak ayrıdır. Editör inceleme kuyruğu ve kaynak sayfaları denetim verisidir; kabul edilmiş sonuç değildir. Genel analiz açılmaz.

Kitap araması güncel kartları reranker ile sıralar; tarihsel katalog Qdrant metinlerini kullanmaz. Modelden sonra nesil/build anahtarı tekrar kontrol edilir. Yaş filtresinde bilinmeyen yaş uygun kabul edilmez. Kitap içi aramada boş sonuç yolu da sorgu sonrasında güncellik kontrolünden geçer.

Bu değişiklik model doğruluğu, tam kitap analitik kabulü, Hermes sohbeti veya mobil ekran kabulü iddiası değildir. Kapsam ve kanıtlar aşağıdadır.

## Son yayın ve gerçek kabul

- Runtime `0.13.0-reads-7eda4ec1`; `/data/editor/app` → `/data/editor/releases/7eda4ec1`.
- Image `sha256:b6fd3ab548932465818f07b69832e40b7b129e32cbd1e4b1898e718ab8736037`. Yeni migration yok. Kontrol/kart servisleri bu image ile çalışıyor; MCP/gateway bu sürümle sınandı, sonra durduruldu. Worker/rebuild konteynerleri yeni image ile oluşturuldu, **başlatılmadı**.
- Gerçek Vombat nesli `3a987c80-95ba-48ce-a08e-820425cf438d`, revizyon **2874**. Çıktılar yeniden üretilmedi; önceki doğrulanmış immutable çıktılar yeni okuyucuyla kullanıldı.
- **120/120** kontrol API–bağımsız temel DB karşılaştırması: tam kayıtlar/sayfalama, rapor, timeline, aktörler, yedi karakterin kimlik/anılış/duygu/olay geçmişi, literal joker karakter, kart kimlik/açıklamaları ve eski nesil engelleri. Kaynak hash/alinti referansı kontrol edildi.
- **22/22** gerçek Streamable HTTP MCP: beş aracın tam HTTP cevabıyla eşliği, tarihsel veri engelleri; gerçek reranker ile katalog sorgusu ve embedding+reranker ile kitap içi sorgu. Düzeltilmiş anne olayı (`edbb7da8-9435-467a-bf78-88a189936ddb`) tam güncel metniyle döndü. MCP UTC `Z`, FastAPI `+00:00` farkı aynı zaman anına normalize edildi; diğer alanlar değiştirilmeden karşılaştırıldı.
- **7/7** kart API/kapak: altı kitabın tam kart cevabı bağımsız DB referansıyla aynı, altı gerçek kapak erişilebilir.
- **522/522** mevcut çıktı içerik/referans/sürüm regresyonu; Qdrant 160/160 tam payload aynı. Bu sayılar soru veya semantik doğruluk sayısı değildir.
- **16 tablonun** önce/sonra tam içerik hashleri aynı. Kaynak, iddia, olay, duygu, kimlik, kanıt, inceleme, rapor/kart ve immutable sürüm kayıtlarına yazılmadı. Model çağrı denetimleri ve bakım kilidi zaman damgası teknik kayıtlardır.
- Bakım tekrar **true**, aktif Temporal işi ve bekleyen rebuild yok. MCP/gateway/Editor modelleri durduruldu, GPU 1 **0 MiB**, BI GPU 0'da çalışıyor. Kontrollü iki arama için bakım geçici kaldırıldı; tarama işçisi çalışmadı.

Kanıt: [özet JSON](evidence/2026-09-21-current-reads.json); tam özel cevaplar `/data/editor/backups/20260921-current-reads/{api-final,cards-final,mcp-final,outputs-final,before,after,runtime}.json`. Tekrarlanabilir sunucu koşucuları `deploy/verify_current_reads.py`, `deploy/verify_current_reads_mcp.py`; yerel test çalıştırılmadı. Eski `verify_foundation.py` 0.10 dönemi ham legacy önizleme sözleşmesini sınar; yeni kullanıcı okuma sözleşmesinin kabul koşucusu değildir.

## Açık kalan sınırlar

- Bu koşuda yeni bir düzeltme yazılmadı veya eşzamanlı düzeltme yarışı üretilmedi. Önceki döngü kabulü korunuyor; bu koşu gerçek mevcut reddedilmiş/tarihsel kayıtların kullanıcı okumalarından dışlandığını doğrular.
- Hermes'in MCP araçları sınandı; doğal dil sohbet zinciri ve mobil tarayıcı akışı bu kabulün dışında. Kart API biçimi korundu.
- Analitik kabul hâlâ BLOCKED: kaynak/sayfa türü, karakter kimliği kapsamı ve açık incelemeler ayrı iş. Son kodla sıfırdan tam kitap ve çeşitli gerçek kitaplarda analitik regresyon yapılmadı.
- Güncel katalog bütün hazır kartları reranker ile sıralar; bu altı kitaplı kurulumda gerçek sorgu geçti. Büyük katalog yükü/ölçek kabulü yok; eski Qdrant katalog noktaları silinmedi ve okunmaz.
- GitHub HTTPS kimliği yok; `git push origin main` başarısız. Kod yerel main ve sunucuda; kimlik sağlanınca kalan komut `git push origin main`.
