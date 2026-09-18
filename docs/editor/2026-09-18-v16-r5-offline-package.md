# V16-r5 çevrimdışı kurulum paketi

Canlı dağıtımın `deployment-result.json` PASS sonucu ve gerçek `/v1/system` yanıtındaki `source-analysis-v16-r5-20260918` sürümü doğrulandı. Temiz main `1200bdd859bd9b704e62f3af754cea81f27a20f0` manifestindeki 234 uygulama dosyasının CPU üzerindeki hashleri birebir eşleşti. Kaynak kod donduruldu; aktif yeni kitap nesli paketleme girdisi değildir.

Paket hedefi `/data/nanobaseai/editor-qualifications/v16-r5-20260918/release/offline`. `bundle.py --external-models`, uygulama kaynaklarını, yerel embedding/reranker dosyalarını ve sekiz Docker imajını paketler. Harici Qwen/OCR GPU ağırlıkları pakette yoktur; müşteri ortamında uç nokta ve erişim kabulü gerekir. Kitap, gerçek .env, secrets, runtime ve evidence kopyalanmaz. `.env.example` yalnız yayın/çevrimdışı compose/harici model kimliği için dönüşür; uç noktalar boş kalır.

Paketleme başlamadan gerçek web imajının 11 kaynak hash kümesi ve bütün build çıktı hashleri dahil edilen frontend ile eşleşti. Backend API/document imajları R5 build proof ile sabittir; web imajı P5 aday kabulündeki imajdır. Sonraki import her paket dosyasının hashini ve yüklenen bütün imaj kimliklerini yeniden denetler. Import uygulama veya model başlatmaz.

İlk hedef olan `/data/nanobaseai/editor-releases` üst dizini yetkili kullanıcıya yazılabilir değildi. `evidence/v16-r5-offline-bundle.log` başarısızlığı korunur; izin değiştirmek yerine mevcut yetkili qualifications dizini kullanıldı. Asıl paketleme logu `evidence/v16-r5-offline-bundle-retry1.log`.

Paketleme ve gerçek CPU offline import 09:30:26 UTC tarihinde **PASS**: `evidence/v16-r5-offline-import-proof.json`. Paket manifesti SHA256 `0c835451a89f00a8b0e0f8a6ed81454d2ee12215981df08c01ebbbd35fb0c647`; 238 paket dosyası ve sekiz imaj kimliği doğrulandı. Paketlenen 233 değişmeyen uygulama dosyası temiz main hashleriyle birebir; tek belgeli kaynak dönüşümü `.env.example`. Paket yaklaşık 3,6 GB. Model çağrısı, kitap verisi yazımı, uygulama restartı ve restore başlatılması sıfır. Bu kabul paket bütünlüğüne aittir; yeni müşteri kurulumunun veya kitabın anlamsal kabulü değildir.

Yeni R5 nesli ve iki gerçek soru kabulü tamamlanmadan restore qualification başlatılmayacak; önceki R7/R4 soru kimlikleri R5 kabulüne taşınmayacak. Yeni hedef ağları gerektiğinde `qualification-network-plan.py` ile güncel Docker IPAM üzerinden seçilir; önceki ağları silmek veya sabit subnet yeniden kullanmak yoktur. GPU yönetim VPN erişimi halen ayrı engeldir; coldboot kabulü yapılmadı.
