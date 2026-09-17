# NanobaseAI BI — Proje Belleği

## 2026-09-17 — Editör kitap kapsamlı yetki sürümü

`book-access-v3-20260917` ana sunucuya yayımlandı. Gerçek kitap/API/PostgreSQL, kaynak kayıtlarının değişmezliği, kapsam dışı erişim, okuyucu yazma yasağı ve anahtar iptali geçti; yönetici/okuyucu ekranları 320/390/768/1440 px doğrulandı. Yeni sürüm için offline/restore kabulü ayrı yürütülüyor. 48 sayfa işlenmiş olsa da 321 kaynak bölgesi ve konuşmacı/anlamsal kabul açık. Ayrıntılar: `docs/editor/2026-09-17-book-access.md`.


Bu dosya canlı özet, tek doğru kaynak. Değişiklik olunca üzerine yazılır (eski bilgi silinir/düzeltilir). Kronolojik geçmiş için [docs/GELISTIRME-GUNLUGU.md](docs/GELISTIRME-GUNLUGU.md)'ye bak.

## Proje ne

Doğal dilde soru → yönetilen SQL → doğru veri. Tek başına kurulan BI ürünü: React arayüz, FastAPI backend, Query Gateway, semantic katman, senaryo motoru ve LLM servisi. İlk/ana müşteri: TİMAŞ Logo (mağaza/satış verisi).

## Editör modülü — bağımsız altyapı (2026-09-17)

Editör aynı depoda `apps/editor/` altında BI'dan bağımsızdır. Sunucu `nanobase-direct`, kök `/data/nanobaseai/editor`; API/web localhost 8810, metrikler 9096. Ayrı PostgreSQL, Qdrant, API/worker, OCR, yerel LLM/embedding/reranker, Prometheus, gateway ve ağsız parser olmak üzere 11 servis. PDF araçları ağsız Docling/Poppler/Tesseract konteynerindedir. BI iç kodu/tablosu kullanılmaz; entegrasyon API üzerinden yapılacaktır.

**Son yayın — otomatik yükleme:** `upload-queue-v2-20260917`. Yeni PDF arayüzden yüklenir, ağsız parser kuyruğunda hazırlanır; 202/job_id, kalıcı durum, iptal, iki iş sınırı ve tekrar kontrolü vardır. Boş ayrı kurulumda özgün kitabın 48 sayfası, gerçek API/PG/Poppler ve dört ekran genişliğiyle doğrulandı. Kuyruk doluluğu, dosya mühürleme, iptal ve servis yeniden başlatmada devam geçti. Ana kurulumda özgün PDF tekrar kuyruğa alındı, mevcut sürüm kullanıldı; analiz kayıtları değişmedi. Bu yayının kendi offline paket/restore, geri yüklenen API/PG/OCR ve mobil kontrolleri 08:15:30 UTC’de geçti. [Kod ve gerçek kabul](docs/editor/2026-09-17-upload-pipeline.md).

**Bağlayıcı kalite kuralı:** Kitap metni, model cevabı, konuşmacı veya kabul kararı Codex tarafından elle düzeltilmez; beklenen cevap prompt/kural/veriye yazılmaz. Genel kod değiştirilir, gerçek kaynak uygulama tarafından yeniden işlenir. Önceki nesiller silinmez. İşlenen sayfa ile doğrulanmış analiz birbirinden ayrıdır.

**Son tekrar koşusu ve yayın:** `source-review-v2-r2-20260917`; nesil `b652f63c-6ec4-4f9a-aff4-00b32d220b1b`, iş `c70995d2-496b-451d-8b34-a84eda4985f9`. 48/48 COMPLETED / NEEDS_REVIEW; 828 anlaşma/321 inceleme. Gerçek API/PG kontrolünde 371 yeniden okuma, 92 çelişki, 48 sayfanın yeniden kullanılan adayları ve yeni kaynak bağlantıları korundu; yeni model çağrısı 0. Üç nesil üzerinden 15 OCR-VL adayının kaynak bağlantısı geçti. Offline paket/import ve ayrı kuruluma restore geçti; geri yüklenen gerçek API/PG, OCR adayları ve dört genişlikte arayüz 07:18:10 UTC itibarıyla doğrulandı. [Ayrıntılı kod ve kanıt kaydı](docs/editor/2026-09-17-source-v3.md).

**OCR CPU ve paket denetimi:** Sorunlu kırpım pilotu v2 artifact alanında tamamlandı: 15 bölge, 14 tamamlanmış/1 kesilmiş, yalnız 1 sözcüklü okuyucu eşleşmesi; toplam 67,11 sn. Ana metne kabul edilmedi. Üretim önbelleği açık, bölge başına 120 sn sınırı var. Eski artifact korunur. Kurulum denetçisi dosya yazan araçların bitmesini bekler ve boş Docker alt ağı seçer; bu sürümün ayrı kurulum/restore kontrolü geçti. Docker IPAM Config=null hatası giderildi; aktif OCR artifact yazıcısı varken yedek başlamaz.

**Kaynak ekranı:** `source-review-v2-20260917` web imajında bölgeyi özgün sayfada işaretleme, PDF kullanılabilirliği ve yeniden okumalar görülebilir. Gerçek Chrome/API ile 320/390/768/1440 px, kutu eşliği ve sayfa değişimi kontrolleri geçti. OCR-VL CPU pilotu tamamlandı; doğrulanmış metin/analiz kabulü henüz yok.

**Güncel yayın — source-spans-v3:** Ek Unicode özel kullanım karakteri hatası giderildi; 371 yeniden okuma yeni nesilde kullanılıyor. Gerçek API/PG salt okunur tekrarda anlaşan bölge 778 → 828, inceleme 371 → 321; anlamsal kabul yok. Nesil `646f7dbe-fe96-4467-ae1e-351af9073543` 48/48 sayfayla tamamlandı, NEEDS_REVIEW; 828 anlaşma/321 inceleme. İlk 43 sayfanın değişmeyen ham adayları tekrar kapıdan geçirildi, son beş sayfanın çıkarımı yenilendi. OCR-VL pilotu tamamlandı ve adayları inceleme API/ekranına kaynak kimliğiyle bağlandı; ana metne kabul edilmedi. [Kod, sürüm ve kabul sınırları](docs/editor/2026-09-17-source-v3.md).

**Önceki ek yayın — otomatik yeniden okuma:** `region-reread-v1-20260917`; 46 sayfadaki 371 sorunlu bölge ağsız Tesseract PSM 7/13 ile yeniden okundu. 175 kararlı okuma, mevcut okuyucuyla eşleşen 147 aday; bunlar kabul edilmiş metin değildir. Özgün kayıtlar değişmedi. Çıktılar ayrı değişmez artifact alanında ve `region-rereads` API’sinde; `source-review` bunlara bağlanır. 46 sayfa/371 bölgenin gerçek API/artifact/PG ve inceleme bağlantısı kontrolü geçti. Konuşmacı/anlamsal kabul açık, yeni offline restore henüz yok. API imajı `sha256:3ec5c8082a38d568288b13158a1696491740d439852d84f5791b25cc1085e981`, belge imajı `sha256:2d166c713e64d9a967865ddd17c5e5e0bc681ae75017dd023f6ae41e29ed7f23`. [Yöntem, hashler ve gerçek koşu](docs/editor/2026-09-17-region-reread.md).

**Önceki inceleme API yayını:** `source-review-v1-20260917` inceleme API’si ve sayfa koordinatında balon-kuyruk/figür aday bağlantısı eklendi. 27 dosya çalışan imajla eşleşti; 48 sayfanın gerçek API/PG kontrolü geçti, kaynaklar değişmedi. 371 bölge ve karakter kimliği kabulü açık. İmaj `sha256:288d43b350356c736529eed8256dc2be3ddb929cd51d715096c3add507094ac1`; backend hash `97ce923c7592d8494546f3c51da379139a0a53dea8e3a1c887b98b155a65e00d`. Yeni ek API sürümünün offline restore kabulü henüz yok. [Kod ve doğrulama ayrıntıları](docs/editor/2026-09-17-source-review.md).

**Önceki v2 koşusu:** `source-spans-v2`, uygulama imajı `sha256:67226135f7620aa2cdd1639543700ff3dfcc42beab8248d38c490caf514e71b2`, backend ağaç hash `58004e5a5043d27508c12aa370ef81d92d97d08778abf2c7cc1b9b5a934fe2ef`, kod commit `6f14bb9`. Yeni nesil `a9471749-7447-4826-b003-f25e53943763`, iş `0d53b03d-67e5-44c4-b523-bf9a2aa56ac2`. V1 nesli `7a19f9eb-7e3e-40d0-822b-ac5e557960b4` API üzerinden iptal edildi; 18 OCR/görsel ve 17 aday/kontrol sayfası korundu. Yeni sürüm ham ölçümleri kaynak hash/köken denetimiyle yeniden kullanabilir; yeni okuma veya doğrulanmış analiz olarak göstermez. Yeni türetimler ayrı nesle yazılır.

**Düzeltmeler:** Bölgesel Paddle ölçümü artık PDF/Tesseract satırının tamamıyla değil konumca karşılık gelen kelimelerle karşılaştırılır. S.16'da gerçek veri tekrarında anlaşan bölge 1/56 → 46/56; ham metin değişmedi, bu anlamsal doğruluk oranı değildir. Alıntıda kelime sınırı, sıralı/kesintisiz kaynak ve yinelenen referans kontrolü vardır; uyuşmayan bölgeler model bağlamında boşluk olarak korunur. Serbest `visuals.description` iddia girdisi değildir. `source_spans`, `layout_regions`, `visual_observations`, `page_claims`, `page_checks` ayrı tutulur.

**Açık kapsam:** Konuşmacı kimliği ve anlamsal kabul henüz tamamlanmadı; bütün sayfaların işlenmesi nesli `NEEDS_REVIEW` yapar. Kitap sentezi, indeks, soru-cevap, kullanıcı/kitap rolleri, editör düzeltme bağımlılıkları tam müşteri ortam çeşitliliği kabulü tamamlanmış sayılmaz. `pilot_ready=false`. Diğer iki gerçek kitap, ikinci baskı ve insan editör süresi yoktur. Bu eksikler tahmin veya sentetik veriyle kapatılmaz.

**Takip:** `evidence/source-spans-run.json` canlı kimlik, `source-pages-v2-follow.log` ilerleme, `source-pages-status.md` tarihli görünüm. Her 10 sayfada ve terminal durumda `verify-source-pipeline.py` gerçek API/PG eşliğini denetler. Kod/model değişikliğinden sonra eski kabul aktarılmaz. LLM Qwen3.8-27B Q4_K_M, 48 CPU/thread, tek slot, 8192 bağlam, 1024 görsel token; embedding/reranker dörder CPU. PaddleOCR ana Compose servisidir; PP-OCRv5 Latin ağırlıkları imaj içinde, çalışma ağı kapalıdır.

**Kanıt/belgeler:** [Sistem düzeltmeleri ve açık işler](docs/editor/2026-09-16-system-quality-followup.md), [v1 kaynak akışının tarihçesi](docs/editor/2026-09-16-source-spans.md), [22 bölümlük kapsam](docs/editor/roadmap-live-status.md), [kurulum/restore](apps/editor/README.md). İlk OCR pilotu, eski caption yanlışları, iptal edilen koşular ve önceki mobil/altyapı kabulleri geliştirme günlüğünde ve bağlantılı raporlarda korunur; güncel sürüm kabulü olarak sunulmaz.


**Önceki v2 sonucu:** 48/48 sayfa işlendi; 1.149 kaynak bölgesinin 778’inde okuyucular anlaştı, 371 bölge incelemede. İş `COMPLETED`, nesil `NEEDS_REVIEW`; anlamsal kabul verilmedi. Gerçek API/PG eşliği, offline paket, ayrı kuruluma yedekten dönüş ve restore sonrası dört genişlikte mobil kontrol geçti. Manuel review ve kaynak düzeltmesi 0.

**Kurulum denetimi:** 17 Eylül 01:56:09 UTC itibarıyla v2 offline paket (8 imaj, 94 dosya, dört GGUF ve OCR), gerçek yedek/restore, hedef API/PG ve mobil kontrol geçti. Denetim `/data/nanobaseai/editor-qualifications/a9471749`; hedef servisler kontrol sonrası durduruldu, veriler korundu. Aynı hostta ayrı kurulum doğrulaması bütün müşteri ortamlarının kabulü değildir.

**Ayrıntılı devir:** [Yapılan işler ve son durum](docs/editor/2026-09-17-status-and-handoff.md).

## Mimari (üstten alta)


```
React (src/, Vite)  →  nanobase_api (FastAPI, :8790)  →  semantic_layer (Katalog + Evidence Engine + Resolver/Compiler)
                                                        →  semantic_bridge (:8795, Timaş'a özel köprü)
                                                        →  query_gateway (:8792, salt-okunur/izin listeli tek SQL çalışma noktası)
                        nanobase_awel  →  LLM operatörleri (planlama/onarım/açıklama iş akışları)
```

- **semantic_layer**: NL→SQL çekirdeği. Katalog + kanıt motoru esas doğru kaynak (WrenAI kaldırıldı, bkz. proje belleği `wren-teardown-done`). Detay: `docs/architecture/semantic-layer-v1.md`.
- **semantic_bridge (:8795)**: Timaş kokpitine özel köprü — `/api/v1/ask`, `/run_sql`, `/api/v1/semantic/*`, `/api/v1/schema/*`.
- **query_gateway (:8792)**: Müşteri SQL'inin tek çalışma noktası, salt okunur, izin listeli.
- **nanobase_api (:8790)**: API, chat gateway, semantic katalog, senaryo motoru.

## Stack

- Frontend: React + Vite + TypeScript (`src/`), Tailwind.
- Backend: Python/FastAPI (`backend/nanobase_api`, `backend/nanobase_awel`, `backend/query_gateway`, `backend/semantic_layer`, `backend/semantic_bridge`).
- Şema tarama/gömme: `tools/schema-indexer`.
- Kurulum: Docker Compose (`deploy/compose`, müşteri paketi), `deploy/llm-server` (GPU sunucusu LLM tanımı).
- Meta DB: Postgres (:5434).

## Sunucu / port yapısı

| Servis | Port |
|---|---|
| Web (Vite dev) | 5174 |
| API (`nanobase_api`) | 8790 |
| Query Gateway | 8792 |
| Semantic Bridge (Timaş) | 8795 |
| LLM (OpenAI uyumlu) | NVIDIA hosted `integrate.api.nvidia.com/v1`, `deepseek-ai/deepseek-v4-flash-0731`, düşünme kapalı (köprü drop-in `semantic-bridge-nvidia.env`, `LLM_EXTRA_BODY_JSON`); eski GPU sunucusu yok. 2026-09-16/17: sağlayıcıda aralıklı 504 ve ~25 dk 404 kesintisi görüldü; yedek model kararı açık (`z-ai/glm-5.3` tek yanıt veren, yavaş) |
| Gömme servisi | 8083 (embedder, CPU) |
| Meta DB (Postgres) | 5434 |
| Zeki AI sohbet | 127.0.0.1:4000 (ayrı Docker, `~/zeki-chat` deposu); portalda `/timas/sohbet/` altında AD oturumu arkasında sunulur |
| Portal giriş servisi | 8796 (`timas-login`, AD + oturum çerezi + `/chat-sso`) |
| BI uygulama VM (müşteri) | http://192.168.0.55/timas/ |

Ayrıntı proje belleklerinde: `semantic-production-deployment`, `bi-app-vm-55`, `llm-nvidia-hosted`, `timas-logo-network-access`.

**Çalışma yeri kuralı (2026-09-14):** Mac'te hiçbir işlem, sorgu ya da çalıştırma yapılmaz. Tüm iş bizim test sunucusu (`nanobase-direct`) ile müşteri sunucusu arasında yürür: sunucu → VPN `tun0` → TİMAŞ ağı (Logo SQL 192.168.0.155: `LOGO_DB`, socat `:14330`, `logo-mssql-connection.json`; CRM prod SQL 192.168.0.28 `CRMDATBASE`: `Timas_MSCRM`, `crm-mssql-connection.json`; BI VM 192.168.0.55). Mac yalnız sunucuya komut ileten uç ve dosya/git yeridir; müşteriye Mac'ten erişim yoktur.

**CRM ve Logo artık iki ayrı SQL sunucusu (2026-09-16):** Logo `.155` (socat `:14330`), CRM `.28` (`connector_from_file` → `secrets/crm-mssql-connection.json`, `zekiai`). Köprü `Runtime._conn_for(sql)` ile yönlendirir: SQL'de `timas_mscrm` varsa → .28, değilse → .155; tek SQL'de ikisi de = kasıtlı hata. Ayrıntı: yerel bellek `timas-crm-prod-28`.

**İki sunuculu (birleşik) sorular — plan (2026-09-16):** `semantic_layer/runtime/federated.py`. Soru iki kaynağa işaret ediyorsa (derleyici `_question_sources`, şemanın veritabanı öneki; `q.sources`) ve `SEMANTIC_FEDERATED=1` ise model tek SQL yerine JSON plan yazar: kaynak başına parça SQL'leri + `links` + bellekte (SQLite) çalışan `final`. `check_plan`: her parça yalnız kendi kaynağının katalog tablolarını okur, `final` yalnız parçaları okur, her bağ `final`'de eşitlik olarak geçer ve katalogda ölçülmüş `cross_source` ilişkisidir. Kapı yükümlülükleri parçalar üzerinde (herhangi biri karşılarsa tamam). Köprü `_answer_plan`: parça kendi bağlantısında tamamen okunur, `execute` birleştirir, cevap normal biçimde + `federated: true`. Bağlar `profiler/cross_source_links.py` + `scripts/discover_cross_links.py` (iki bağlantı) ile ölçülür, `scripts/apply_cross_links.py` ile kataloğa yazılır; gece taraması `cross_source` bağları silmez.

**Soru hattı kararları (2026-09-16):** Katalogun açıklamadığı niteleyici (ör. "tahsil edilmemiş") geri sorulmaz: `model_qualifiers` olarak modele verilir, model `-- yorum: '<kelime>' → <koşul>` satırı yazar (cevabın üstünde görünür), kapı yorum satırını ve ek bir kısıtı arar, cevap sertifikasızdır. Kaynağın kolon açıklamasında anlattığı durum `qualifier_columns` (kapı o kolonun kısıtlanmasını ister); kod etiketi olan durum doğrudan filtre. İstem tabloları sorunun kaynağından seçilir. Liste/ana veri sorularına varsayılan yıl eklenmez. Test: 500 soruluk set (`nanobase-direct:~/testset/all500.jsonl`, en zor 100: `set100.jsonl`), koşturucu `run_testset.py` (`timas-testset` systemd birimi), sonuç ekranı artifact `JMmco7kazxBbYLwaHvnxAV`.

**TİMAŞ erişimi:** Logo SQL (192.168.0.155) yalnız nanobase sunucusundaki WatchGuard OpenVPN tüneli (`tun0`) + socat `:14330` ile erişilir; Windows tarafına RDP (`timas\muratsancar`) de açık. VPN kullanıcısı `muratsancar` MFA (push/OTP) istiyor. Kullanıcı adı/şifreler repo'da **tutulmaz** — yerel proje belleğinde: `timas-access-credentials`.

**VPN nasıl açılır (2026-09-14'ten beri):** `timas` servis hesabı `AUTH_FAILED` veriyor; tünel `muratsancar` hesabıyla telefon onayıyla açılır. Sunucu `CRV1` meydan okumasını alır, `CRV1::<state>::p` ile bağlanır, kullanıcı WatchGuard bildirimini onaylar. Birim: `timas-vpn-mfa` (`systemd-run`). Şifreleme şartı: `--data-ciphers AES-256-GCM:AES-128-GCM:CHACHA20-POLY1305:AES-256-CBC --data-ciphers-fallback AES-256-CBC`. Oturum kalıcı değil: kopma veya yeniden başlatmada push adımı tekrarlanır. Kopukken belirti: portal açılır, veri gelmez (köprü logunda FreeTDS `08001`). Kontrol: `ip -br addr show tun0`, `systemctl is-active timas-vpn-mfa`. Adım adım tarif: yerel bellek `timas-logo-network-access`.

**VPN hesabı kısıtı (2026-09-14 13:30'dan beri):** Tünel açılıyor ama WatchGuard bu hesaba yalnız `192.168.0.55:3389` (RDP) izni veriyor. Test sunucusundan `192.168.0.155:1433` (SQL: `LOGO_DB` + `Timas_MSCRM`), `.155:3389` ve `.55:22` kapalı. Aynı gün 10:44'te `.155:1433` açıktı; kural sonradan değişti. Sonuç: test sunucusundan Logo/CRM sorgusu ve `ssh timas-vm` çalışmaz. Gereken: TİMAŞ BT'den VPN hesabına `192.168.0.155 TCP 1433` ve `192.168.0.55 TCP 22` izni.

## Dizin haritası

| Dizin | İçerik |
|---|---|
| `src/` | React + Vite arayüz (tek frontend, kanvas: `src/canvas`) |
| `src/canvas/stitch/Shell.tsx` | Ortak kabuk (üst şerit, ray, modül menüsü). Kırıntıdaki kiracı adı ana sayfaya bağlantıdır; sağ üstteki pil oturumdaki kişinin baş harflerini gösterir (sahte EB/EA/SK yok). Sağ üstteki yakınlaştırma (%50–%200, adım 10) kabuğun kendi durumudur: ekranlar içeriklerini `ZoomStage` ile sarar (CSS `zoom`, `main` sabit kalır, yazdırmada 1); Genel bakış kanvası `onZoom` ile kendi ölçeğini verir (sığdırma × zoom). Pano sürüklemesi ölçeğe bölünür. `/uyarilar` ekranı `AlertsPanel inline` ile kural listesi/yeni kural gövdesidir (`?panel=yeni`); `screens.ts` yalnız `railFor`, `alertsData`, `cfoData` üretir |
| `src/canvas/board/` | Panolar: kişiye özel kart panosu (sürükle/boyutlandır, SQL paneli, son sorgu saati, başlık/not, CSV/PDF, KPI karşılaştırma, ECharts-GL 3B); düzen + son sonuç sunucuda `semantic_board_cards` (`backend/semantic_bridge/board.py`, `/api/v1/board`), tarayıcı yalnız önbellek; zamanlayıcı `timas-board.timer` |
| `backend/semantic_layer/rule_miner/` + `scripts/mine_rules.py`, `scripts/rule_probe.py` | İş kuralı madencisi (2026-09-16): Logo danışman görünümleri (`sys.sql_modules`, 211/411 okuyan 240 görünüm) ve CRM kayıtlı görünümleri (`SavedQueryBase`/`UserQueryBase` FetchXML) → etiket haritası / kolon adı / ölçü / adlandırılmış durum adayları; canlıda çürütme; politika: kaynağın kendi kuralı + çürütmeden geçti + çakışma/çok anlam/genel kelime/tek kelime(<3 kaynak)/tablo-adı değil → `rule-miner` sertifikası, aksi onay ekranı. Canlı: Logo 335 + CRM ~870 sertifika, ~600 onayda. `rule_probe` çözücü seviyesinde ölçer (kolon %90, durum %80, ölçü %73). CRM kolon adları harf duyarlı: profildeki yazım kullanılır |
| `backend/semantic_layer/vocabulary.py` | Eş anlamlı üretim hattı: alan açıklaması → aday → çürütme → insan onayı → kavram `synonyms`; `sl_vocabulary`; ezmeme kuralı (`human`/karar verilmiş satıra üretim dokunmaz); ekran `/es-anlamlilar` |
| `backend/semantic_bridge/reports.py` | Planlı raporlar: cümleden plan (`parse_prompt`), `semantic_reports` tablosu, Excel/CSV üretimi (`/data/nanobaseai/bi/var/reports`), SMTP (ALERT_SMTP_*) yoksa dosya indirilir; `/api/v1/reports*`, zamanlayıcı `timas-reports.timer` (5 dk); ekran `src/canvas/reports/ReportsScreen.tsx` (`/planli-raporlar`) |
| `backend/semantic_bridge/prefs.py` | Kişi tercihleri `semantic_user_prefs` (AD hesabı + anahtar → JSON), `/api/v1/me/prefs/{key}`; Genel bakış kanvas düzeni `layout:<ekran>` burada. Kişiye özel alanların hepsi sunucuda: planlı raporlar (`username`), pano (`username`), uyarılar (`created_by`), kanvas düzeni (prefs); tarayıcı yalnız önbellek |
| `sl_query_log` (+ `src/canvas/admin/PromptTracker.tsx`) | **Promt izleyici**: sorulan her soru + üretilen SQL + tam sonuç (`result_json`) + kim sordu (`username`) + cevap tipi/özet + kapı kararı (`gate_json`) + inceleme işareti/notu. Yazan: `Runtime.ask` içindeki `_log` (16 dal). İnceleme yalnız yöneticiye: Yönetim → "Promt izleme" sekmesi, uçlar `GET/PATCH /api/v1/admin/prompts*` + `export.csv`. Amaç: alıp inceleyip nereyi düzelteceğimizi görmek. Migration `catalog_store._add_missing_columns` (var olan tabloya kolon ekler, restart'ta çalışır) |
| `backend/semantic_bridge/admin.py` + `src/canvas/admin/` | Yönetim (`/yonetim`, yalnız yöneticiler — `is_admin`: `TIMAS_ADMIN_USERS` listesi (vars. `zekiai,timasai,muratsancar`) **ya da** yönetici AD grubu `TIMAS_ADMIN_GROUP` (vars. `Administrators`, iç içe üyelik/`IN_CHAIN`). Grup üyeliği istek yolunda canlı okunmaz: `semantic_admin_group` tablosundaki anlık görüntüden okunur, `timas-admin-group.timer` 15 dk'da bir `POST /api/v1/admin/group/refresh` ile tazeler; tazeleme başarısızsa eski görüntü kalır, görüntü yoksa listeye düşer. `GET /api/v1/admin/group` üyeleri ve son tazelemeyi gösterir). **Veri Sözlüğü (`/veri-sozlugu`) ve Onaylar (`/onaylar`) da yönetici-özel:** menüler yetkisizde hiç çıkmaz (`useIsAdmin` → ray/Kampüs/ModulesMenu), ekranlar `AdminGuard` ile korunur (ortak tema uyumlu `NoAccess` kartı), uçlar `_admin_gate` (concepts/schema.gaps/review/decide 403). Yönetim: ayarlar tablosu `semantic_settings` (ekran > `/etc/nanobase/semantic-bridge.env` > varsayılan; SMTP, alıcı alan adları, e-posta bağlantısı, hatırlatma, rapor dosya sayısı, oda saatleri, CRM şeması, LLM adresi/modeli/anahtarı/zaman aşımı, yöneticiler — `admin.conf()` ile okunur). Dosyada tutulan ayarlar: Active Directory → `/etc/nanobase/timas-ad.json`, Logo veritabanı (sunucu/port/veritabanı/kullanıcı/parola/sürücü/TDS) → `SEMANTIC_CONNECTION_FILE`; ikisi de ekrandan güncellenir. LLM ve veritabanı ayarı kaydedilince çalışan köprüde yeniden kurulur (restart yok); yeni bağlantı kurulamazsa takas edilmez, eski bağlantı sürer ve hata ekranda döner. Bağlantı denemeleri `/api/v1/admin/tests[/{id}]` (database · crm · llm · directory · email · store) gerçek bağlantıyı kurar ve kayda yazılır; salt okunur sistem tanımları `/api/v1/admin/system`. Değişiklik kaydı `semantic_audit` (rapor/uyarı/pano kartı/ayar/sözlük kararı/kolon açıklaması: oluşturma, güncelleme önce→sonra, silme, çalıştırma, deneme), herkesin raporları/uyarıları/kartları, kişiler ve yönetici atama, servis ve zamanlayıcı durumu; uçlar `/api/v1/admin/*` |
| `scripts/server/portal-login/` | Giriş: `timas-login` (:8796) Timaş Active Directory ile doğrular (ldap3 + NTLM MD4; import `Crypto` ya da `Cryptodome` ad alanını kabul eder), oturum çerezi + nginx `auth_request`; AD ayarı sunucuda `/etc/nanobase/timas-ad.json`. Demo/davet/Basic hesap yok (2026-09-14'te kaldırıldı). **Zeki AI sohbet SSO:** `/chat-sso` ucu portal oturumunu doğrular, sohbette (`127.0.0.1:4000`) aynı AD hesabıyla kullanıcıyı bulur/oluşturur (şifre rastgele, kimse bilmez) ve `sso_secret` ile bir giriş jetonu döndürür — şifre sohbete hiç gitmez; sohbet bağlantısı `/etc/nanobase/zeki-chat.json` (`root:www-data 0640`) |
| `deploy/zeki/portal-sso-setup.sh` | Zeki sohbet ↔ portal SSO kurulumu (nanobase-direct'te kullanıcı koşar, sudo; idempotent 3 adım): nginx bloğu (`# ZEKI-CHAT-BASLA/BITTI`; `/timas/sohbet/` auth_request + WebSocket + `proxy_buffering off` → :4000, ayrıca `/timas/sohbet/api/` öneksiz `→ :4000/api/` çünkü Meteor önekli POST'lara 405 verir) → giriş servisini güncelle/yeniden başlat → `zeki-chat.json` yaz. Sohbet kaynağı ayrı depoda (`~/Documents/GitHub/zeki-chat`, dal `zeki/8.5.3`, Rocket.Chat 8.5.3 fork); sunucuda `~/zeki-chat`, derleme `deploy/zeki/build.sh` (paketler → Meteor → Docker `zeki-chat:8.5.3` → compose `-p zeki`), `.env` yalnız sunucuda. **Durum 2026-09-16:** sohbet açılıyor ama otomatik SSO girişi tamamlanmıyor (ddpOverREST 401 → kimlik silme döngüsü); ayrıntı günlükte |
| `backend/nanobase_api` | API, chat gateway, semantic katalog, senaryo motoru |
| `backend/nanobase_awel` | LLM operatörleri, planlama/onarım/açıklama iş akışları |
| `backend/query_gateway` | Müşteri SQL'inin tek çalışma noktası |
| `backend/semantic_layer` | Semantic Catalog + Evidence Engine + History Miner + Profiler + Resolver/Compiler |
| `src/canvas/kampus` | Girişten sonraki ilk ekran (`/`): Kampüs intraneti + ZEKİ + modüllere geçiş; BI genel bakış `/genel-bakis`. Gerçek veriyle çalışan parçalar: rehber ve profil penceresi (`ProfileDialog.tsx`), toplantı odaları, zil (bana gelen kutlamalar) ve alkış duvarı (`semantic_greetings`: `GET /api/v1/greetings` → `sent/inbox/received/wall`, rehberden kişi seçilerek `POST`), günün modu (`prefs kampus:mood`), Dahili Rehber CSV indirme. ZEKİ örnek soruları motorun kapsamındaki finans sorularıdır. 2026-09-17 denetiminde kaynağı olmayan tasarım kartları (sesli bülten, çekiliş, doğum günü, ajanda, yeni kitap, yemekhane, hızlı operasyon, sahte alt bilgi bağlantıları) kaldırıldı; **çalışmayan düğme bırakılmaz** kuralı geçerli |
| `backend/semantic_bridge/people.py` | Kişi rehberi + profil. Liste prod CRM `SystemUserBase` (etkin, AccessMode 0/1) ∩ AD (etkin kişi, `ActiveDirectoryGuid`=`objectGUID`, yoksa hesap adı) ∩ son `PEOPLE_MAX_IDLE_DAYS` (365, Yönetim → Kişi rehberi) gün içinde giriş; birim boşsa AD OU'su. Alan önceliği CRM > AD > kişinin yazdığı. Kişinin dahili/kat/masa/cep/hakkımda + fotoğrafı `semantic_people_profiles` (AD hesabı). Uçlar `/api/v1/people`, `/api/v1/people/{hesap}/photo`, `/api/v1/me/profile[/photo]`. AD ayarı `/etc/nanobase/timas-ad.json` köprüye ACL ile okunur (`u:administrator:r`); okunamazsa liste yalnız CRM'den gelir (`adChecked:false`) |
| `backend/semantic_bridge` | Timaş kokpiti köprüsü (:8795) |
| `tools/schema-indexer` | Şema tarama ve gömme |
| `deploy/compose` | Müşteri kurulum paketi (Docker) |
| `deploy/llm-server` | GPU sunucusu için LLM servis tanımı |
| `docs/architecture` | Kilitli mimari, tasarım ve plan belgeleri |
| `docs/audits` | Denetim/inceleme kayıtları |
| `docs/product` | Ürün belgeleri |
| `configs/` | Operatör yapılandırmaları (bağlantı profilleri, şema katalogları, semantic bağlamalar) |

## Kritik kurallar (AGENTS.md'den, kısa özet)

- **Mobil öncelik**: Her arayüz değişikliği 320/390/768/masaüstü genişliklerde tarayıcıda kontrol edilir; yatay taşma yok. Detay: `apps/cockpit/AGENTS.md`.
- **Gerçek DB ile doğrulama zorunlu**: Veri alma/SQL/hesaplama/raporlama etkileyen her değişiklik bağlı gerçek veritabanı + gerçek API akışıyla doğrulanmadan tamamlanmış sayılmaz. Yerel mock/fixture/SQLite ile test **yasak** (kullanıcı ayrıca istemedikçe). Doğrulanamıyorsa **DOĞRULANAMADI** diye raporla, başarı iddia etme.
- **Tek şirket, çok yıllık yedek**: TİMAŞ'ta tek şirket var; `211`/`411` gibi kodlar farklı şirket değil, yıl yedekleridir (bkz. proje belleği `logo-period-prefixes-are-years`, `timas-logo-database-shape`).
- Tam kural metni: [AGENTS.md](AGENTS.md).

## Notlar

- Çalışma zamanı davranışları (2026-09-17): sorunun veri tabanı (Logo/CRM) ölçünün kaynağından, ölçü yoksa soru kelimelerinin eşleştiği **tablo adlarından** okunur (`SemanticQuery.source_hint` → derleyici tablo kapsamı); yıl kopyaları ortak kolon adlarıyla birleştirilir, tek yönlü tarih sınırı açık uçlu dönemdir, 1899/1900 sentinel tarih dönem değildir; eleştirmen çapraz birleştirmeyi ve farklı hedefli anahtar eşitliklerini bloke eder; kapı `LEFT JOIN … ON` filtresini kabul eder ve `-- yorum`da adı geçen tablonun okunmasını ister; sonuç deposu sınırda hata değil kısmi sonuç + `truncated` döner. Tek tek karne: https://claude.ai/artifact/V99abTkwYZakQNLbA1qTpg
- Çalışma zamanı davranışları (2026-09-17, soru 12–17): kapıda durum ölçüsünün bakiye okuması ve ölçünün dışladığı satırları okuyan alt sorgu dönem kuralından muaf; varlık adı karşılaştırması `LG_` önekine duyarsız; sorunun kelimesi sütun değeri yazılamaz; yokluk sorusu ("hiç X almamış") dışlama yapısı (NOT EXISTS / NOT IN / LEFT JOIN … IS NULL) ister. Çözücü: zaman kelimeleri yeniden aranmaz; adlandırılmış kümeden sonraki sayım sözcüğü o kümenin COUNT'u (`count_key` ile fiş sayımı); "X, Y'nin ne kadarı" oran (`SemanticQuery.ratio`); kolon + "tanımlı/dolu" = dolu koşulu; ölçünün yanındaki kolonlar kırılım; "son N ay" = cari ayla biten N ay. Planlayıcı: aynı hedef tabloya bağlanan eşlemeler referans kuralı taşıyanın yolunu paylaşır; kolon-kolon koşul (`AMOUNT > SHIPPEDAMOUNT`) yazılır; oran sütunu eklenir; kolon başlıkları kavramın kendi adından. Hatırlanan örnek SQL'ler mantıksal adla gösterilir. `LlmClient` süreyi bütün uygular. Env (`semantic-bridge.env`): `LLM_CTX=32768`, `SEMANTIC_PROMPT_RULES_CHARS=40000`, `LLM_TIMEOUT_SEC=900`, `SEMANTIC_SELECTOR_TIMEOUT_SEC=60` (NVIDIA kuyruğu 4+ dk). İş tanımları kararları: [docs/TIMAS-IS-TANIMLARI.md](docs/TIMAS-IS-TANIMLARI.md) (katalogda operatör sertifikası, iş teyidi bekliyor).

- **Kokpit yayını:** kaynak sunucuda derlenir. `rsync -a --delete src/ nanobase-direct:/data/nanobaseai/bi/frontend/src/`, sunucuda `VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas npm run build`, sonra `sudo rsync -a --delete --no-o --no-g dist/ /data/nanobaseai/bi/cockpit/dist/`. Commit etmek yayınlamak değildir; canlıdaki `index.html` tarihine bak.

- Bu proje için ayrıca kalıcı bellek kayıtları `~/.claude/projects/.../memory/MEMORY.md` altında tutulur (semantic layer kararları, sertifikalama, kalite kapısı, vb.) — kod tabanından türetilemeyen proje bağlamı orada.
- Bu dosya + `docs/GELISTIRME-GUNLUGU.md` çifti bir **talimat**tır, hook değildir: oturumdaki Claude'un CLAUDE.md'yi okuyup uygulamasına bağlıdır, zorlayıcı değildir. Gerçek zorlama istenirse `.claude/settings.json`'a bir hook eklenebilir (örn. commit sonrası günlük güncellendi mi kontrolü) — bu ayrı bir iş, henüz yapılmadı.
