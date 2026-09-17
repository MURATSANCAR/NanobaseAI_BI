# Editör inceleme ekranı

> 17 Eylül v3 güncellemesi: Yeni kaynak nesli çalışıyor; salt okunur gerçek veri tekrarında 828 anlaşma/321 inceleme. 45 sayfanın inceleme API/PG kontrolü geçti; tam yeni nesil henüz tamamlanmadı. Kaynakta kutu işaretleme ve yeniden okuma karşılaştırması yeni web imajıyla yayımlandı; gerçek Chrome/API üzerinde 320/390/768/1440 kontrolü geçti. OCR-VL sınırlı pilotu sürüyor. Aşağıdaki tamamlanmış 48 sayfa ve restore sonuçları önceki v2 sürümüne aittir. [Yeni kod ve kanıtlar](../../../docs/editor/2026-09-17-source-v3.md).

## 17 Eylül doğrulanmış durum

Restore ortamındaki gerçek Chrome kontrolü 17 Eylül 01:56:09 UTC’de geçti: 320/390/768/1440 px, altı sekme ve gerçek kaynak kaydı. Ekran salt okunur kalır; işin bitişi ile inceleme durumu ayrı gösterilir. Bu sonuç editör karar/yükleme/rol veya anlamsal kabul yerine geçmez.

48/48 sayfa işlendi; 1.149 kaynak bölgesinin 778’inde okuyucular anlaştı, 371 bölge incelemede. İş `COMPLETED`, nesil `NEEDS_REVIEW`; anlamsal kabul verilmedi. Gerçek API/PG eşliği, offline paket, ayrı kuruluma yedekten dönüş ve restore sonrası dört genişlikte mobil kontrol geçti.

[Ayrıntılı çalışma kaydı](../../../docs/editor/2026-09-17-status-and-handoff.md).

Bağımsız React/TypeScript uygulaması `/editor/` altında gerçek operatör API'sini
kullanır. Kitap ve analiz sürümü seçimi, üç ayrı durum (işleme/kaynak kapsamı/editör
incelemesi), özgün sayfa, OCR/PDF metin adayları, ham görsel model çıktıları,
sahne/varlık/olay/edebî yorum ve mevcut soru-cevap kayıtlarını gösterir.

Bu sürüm salt okunurdur. Kabul koşusuna düzeltme veya editör kararı yazmaz.
Operatör anahtarı yalnız React oturum belleğindedir; tarayıcı depolamasına,
adres çubuğuna veya derlenen dosyalara yazılmaz. Çok kullanıcılı kitap/rol
yetkisi, dosya yükleme ekranı, editör karar/düzeltme akışı ve PDF.js/bbox
incelemesi henüz tamamlanmış değildir.

Derleme **sunucuda** yapılır:

```sh
cd /data/nanobaseai/editor/frontend
npm ci --ignore-scripts
npm run build
cd ..
docker compose build gateway
docker compose up -d --no-deps gateway
```

Çevrimdışı müşteri paketinde derlenmiş web imajı bulunur; müşteride npm veya
internetten paket indirme gerekmez. `deploy/nginx.conf` dosyası atomik kopyalama
ile değiştiyse dosya bind mount'unu yenilemek için gateway `--force-recreate`
ile yeniden açılır; yalnız nginx reload eski dosya inode'unu okuyabilir.

16 Eylül gerçek sunucu kontrolü: Chrome ile 320, 390, 768, 1440 px; altı sekme,
gerçek kitap seçimi, PDF 6 kaynak görüntüsü, sayfa taşması ve çıkışta anahtarın
temizlenmesi doğrulandı. Kanıt `evidence/review-ui/verification.json` ve PNG'lerdir.
Boş durumdaki sekmelerin kontrolü henüz üretilmemiş analizin doğru gösterildiği
anlamına gelmez; kayıtlar oluştukça dolu akışlar ayrıca kontrol edilir.

Sunucu betiği `scripts/verify-review-ui.cjs`, sunucudaki Chrome ve
`runtime/browser-check/node_modules/playwright` ile çalışır. Yerel mock test
yerine gerçek API/DB kullanılır. Kitap görüntüleri ve ekran kanıtları Git'e eklenmez.
