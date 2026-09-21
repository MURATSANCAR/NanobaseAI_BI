# Editor üretim kabulü — 21 Eylül 2026

**Karar: ÜRETİME HAZIR DEĞİL.** Teknik çalışabilirlik ile kitap doğruluğu ayrı kabul edilir. Kullanıcı onaysız hazırlık/yayın/doğrulama yetkisi verdi; bu belge tamamlanmamış maddeleri onaylanmış saymaz.

## Kurulu ve hazırlanmış sürümler

- GPU: `d596f3c5`, `/data/editor/releases/d596f3c5`, `editor-py:d596f3c5`, sürüm `0.15.0-production-d596f3c5`. Altı salt okunur sohbet aracı; 16 araç turu sınırı. Genel analiz ve yeniden üretim işçileri son kontrolde kapalı.
- CPU portal: `474cb2d9` konuşma bağlamı düzeltmesi; gerçek sunucuda derlendi, semantic bridge ve portal yayımlandı. Aynı kullanıcı/tenant/kitabın son sekiz tamamlanmış turu, istek başına ayrı Hermes kilidi. Bağlı gerçek portal API + bağımsız PostgreSQL okumasında 8/8 kontrol geçti; [kanıt](evidence/2026-09-21-portal-context-api.json). İlk yanıt 119,3 sn, bağlamsal takip 2,8 sn.
- Sonraki GPU düzeltmeleri **henüz kurulu değil**: tam özet aracı, eski iş/güncel çıktı durumlarının ayrımı, metin aracının görsel kapsamını açık bildirmesi, PDF aynı koordinatlı baskı tekrarı ve künye satır sırası düzeltmesi.
- Kalıcı yönetim tüneli taslağı **henüz kurulu değil**: CPU loopback `18891` → GPU SSH. Mevcut anahtar/host doğrulaması korunur. İlk kurulum için GPU yönetim bağlantısı gerekir.

## Gerçek kanıtlar

1. Önceki nesilde düzeltme/çıktı kurtarma: [IDENTITY-COVERAGE.md](IDENTITY-COVERAGE.md), rev3009, beş güncel READY çıktı; 371 gerçek API/DB/Qdrant kontrolü. Tarihsel tam iş FAILED kalır; analitik durum NEEDS_REVIEW.
2. Yeni sınırlı sohbet MCP: sunucuda gerçek DB/snapshot ile **317 kontrol geçti**. GPU kanıtı `/data/editor/backups/20260921-production/chat-reads.json`; bağlantı kesilmeden sonuç gözlendi, dosya henüz yerel depoya alınamadı. Bu sayı sonradan hazırlanan yedi araçlı sürümün kabulü değildir.
3. Gerçek Hermes üzerinden 10 soru: [ham yanıtlar](evidence/2026-09-21-production-chat-ten.jsonl). On yanıtın HTTP ile dönmesi semantik kabul değildir. Çalıştırma CPU, Hermes/model/kitap DB GPU.
4. Portal gerçek oturumlu tarayıcı: 320/390/768/1440 genişliklerinde soru alanı ve gönderme düğmesi erişilebilir, sayfa yatay taşmaz. Konuşma yaşam döngüsü ayrıca kabul edilmelidir.

## On soruda bulunan engeller

| Soru | Gözlem | Karar |
|---|---|---|
| Kısa özet | 25. sayfada evden ayrılmayı son sanıyor; 31–32. sayfadaki kurtarma yok | FAIL: tam özet aracı hazırlanıyor |
| Baba/yavru | İki ayrı karakter; 6. sayfa kaynağı | Bu senaryo doğru; tüm kimlikler kabul edilmiş değil |
| Hayvan türü | Hayvan kimliği doğru, gereksiz teknik alanlar görünür | Sunum eksik |
| Kütüphaneci | Salyangoz ve 8. sayfa atfı | Bağımsız sayfa kontrolü tamamlanmadı |
| Sayfa 23 | Metin doğru; metin aracından görsel yokluğu çıkarıyor | FAIL: kapsam açık bildirilmeli |
| Sayfa 4 | Metin yokluğunu bildiriyor; kapak olabileceğini tahmin ediyor | Desteksiz tahmin; resimli hikâye sayfası |
| Analiz durumu | Analitik kabul yok doğru; eski FAILED nedeniyle hazır çıktı yok diyor | FAIL: güncel çıktı durumu ayrı okunmalı |
| Silme isteği | Salt okunur araçlarla silme yapılmadı | Yazma izolasyonu geçti |
| Olmayan kitap | Bulunamadığını söylüyor; kapanışta yanlış kitap adı üretiyor | FAIL: ad doğruluğu |
| Takip sorusu | Önceki baba/yavru bağlamını koruyor | Doğrudan Hermes bağlamı doğru; portal ayrıca test ediliyor |

Yanıtlarda kullanıcıya gereksiz `semantic_acceptance`, adım kodları ve `FAILED` gösteriliyor. Kaynak doğruluğu yalnız ifadeleri sadeleştiren ikinci bir modelle garanti edilemez.

## Kaynak ve kimlik kabulünde kalanlar

- PDF sayfa 2 künye rol/isim sırası; sayfa 3 aynı koordinatlı çift metin. Kaynak resimle bağımsız karşılaştırıldı; parser düzeltmesi yeni nesilde doğrulanmalı. Orijinal dosya/önceki nesil değiştirilmez.
- Sayfa 18/24/26 PDF–OCR uyuşmazlıkları çözülmeli; OCR otomatik doğru kaynak sayılmamalı.
- Sayfa 4/10 gerçek görsel hikâye sayfaları; metin boşluğu veri kaybı sayılmaz, görsel kapsam gerekir.
- 32 sayfanın rolü UNKNOWN; bölüm başlığı ile hikâye başlangıcı ayrı belirlenmeli.
- 59 görsel anmanın 23'ü belirsiz. Belirsizliği isme bakarak zorla kapatmak kabul değildir.
- Son kodla yeni nesilde baştan sona analiz, kritik kaynak/kimlik kontrolleri, düzeltme → otomatik yeniden üretim → işçi çökmesi sonrası devam yeniden kabul edilmeli. Önceki farklı sürümün kanıtı yeni sürüme taşınmaz.

## Teknolojik değerlendirme

Mevcut depo yapılandırmasında yönetici model Qwen3.8-27B-FP8; hızlı görsel Qwen3-VL-8B-Instruct; derin görsel Qwen3-VL-32B-Thinking; embedding/reranker ayrı 8B modeller. GPU0 BI, GPU1 Editor. Derin görsel model 0,90 bellek payıyla diğer Editor modelleriyle aynı anda yerleşemez; gateway değişimi gecikme kaynağıdır. FP8 derin görsel aday tanımı var, ancak gerçek sayfa/kimlik kalitesi kabul edilmeden varsayılan yapılmadı.

Gözlenen temel hatalar model yükseltmesiyle açıklanamaz: eksik araç sayfalaması, eski/güncel durum karışması, kaybolan sohbet geçmişi ve kaynak geometri sırası. Bunlar önce düzeltilir. Alternatif modelin daha iyi olduğu veya güncel sürümlerin araştırıldığı iddia edilmiyor; bu turda model değişikliği yapılmadı.

## Erişim engeli ve güvenli devam

Yerel TT VPN/SOCKS `127.0.0.1:11080` kapandı; `tt-gpu` SSH bu bağlantıyı kullanıyor. VPN yeniden girişinde kullanıcı OTP gerekir ve oturumda saklı değildir. GPU→CPU Hermes/kart API tünelleri çalışıyor; GPU yönetim kabuğuna eşdeğer değiller. Salt okunur sohbet aracından yönetim komutu çalıştırmaya girişilmez.

**Son bilinen GPU bakım durumu false** (kontrollü kabul için açılmıştı); genel işçiler kapalı. Yönetim kaybından sonra bakım kilidinin yeniden açıldığı iddia edilmez. Bağlantı gelir gelmez önce aktif iş/lease/kuyruk kontrolü, ardından bakım kilidi ve tek kontrollü kabul koşusu yapılır. CPU portalı kullanılabilir olması kitap analizini üretime hazır yapmaz.

GitHub origin yayını HTTPS kimliği bulunamadığından engelli; yerel main commitleri sunucuyla birlikte kayda alınır. Yönetim erişimi, origin push ve analitik kabul tamamlanmadan genel taramalar açılmaz.

## Sonraki kabul sırası

1. GPU yönetim erişimini geri getir; yalnız localhost SSH ters tünelini mevcut anahtarlarla kur ve host doğrulamalı erişimi sına.
2. Yeni kodu main commit/hash ile ayrı release'e kur; genel işçiler kapalı kalsın.
3. `verify_chat_reads.py` ile yedi gerçek MCP aracı + DB snapshot; üç başarısız sohbet sorusunu yeniden çalıştır.
4. `verify_pdf_layout.py` ile gerçek orijinal PDF geometri/künye/biyografi kontrolleri; kapsam/kimlik düzeltmelerini yeni nesilde değerlendir.
5. Yeni tam nesil, kaynak/kimlik yeterliliği, beş çıktı ve Qdrant tutarlılığı, düzeltme/çökme kurtarma ve gerçek portal sohbeti kabulü.
6. Kabul sürümü main/origin/sunucuda aynı; başarısız veya değerlendirilmemiş alanlar açıkça raporlanır. Ancak bundan sonra üretim kararı.
