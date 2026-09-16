# NanobaseAI BI — Proje Belleği

Bu dosya canlı özet, tek doğru kaynak. Değişiklik olunca üzerine yazılır (eski bilgi silinir/düzeltilir). Kronolojik geçmiş için [docs/GELISTIRME-GUNLUGU.md](docs/GELISTIRME-GUNLUGU.md)'ye bak.

## Proje ne

Doğal dilde soru → yönetilen SQL → doğru veri. Tek başına kurulan BI ürünü: React arayüz, FastAPI backend, Query Gateway, semantic katman, senaryo motoru ve LLM servisi. İlk/ana müşteri: TİMAŞ Logo (mağaza/satış verisi).

## Editör modülü — bağımsız altyapı (2026-09-16)

**Sistem düzeltmesi:** Kullanıcı kitap verilerinin/cevapların elle düzeltilmesini açıkça yasakladı; yalnız genel kod ve sistemin gerçek kaynak üzerinden yeniden işlemesi kullanılacak. Kelime/satır konum eşleştirmesi, kesintisiz alıntı kontrolü ve denetimli takip için `source-spans-v2` hazırlanıyor. İlk 18 sayfanın gerçek verisiyle salt okunur karşılaştırma yapıldı; s.16 okuyucu anlaşması 1/56 → 46/56, semantik kabul değil. [Denetim, kod düzeltmeleri ve açık işler](docs/editor/2026-09-16-system-quality-followup.md). Aşağıdaki v1 durumları bu yeni sürümün canlı kabulü sayılmaz.

Güncel ana akış `source-spans-v1`: eski koşu ve ilk canary iptal edilip korundu; yeni nesil `7a19f9eb-7e3e-40d0-822b-ac5e557960b4`, iş `1b2335a4-5dfa-4fce-89df-71259c8aa1cd` sayfa bazında sürüyor. PaddleOCR artık ana Compose servisidir. Yerel PDF kelime kutuları + bölgesel Paddle/Tesseract okumaları `source_spans`, yerleşim/balon adayları `layout_regions`, kırpılmış resim adayları `visual_observations` olarak ayrı tutulur. Serbest görsel açıklama iddia girdisi değildir. Uyuşmazlık incelemeye ayrılır; kaynak eşleşmesi semantik kabul sayılmaz. Konuşmacı kimliği ve anlamsal doğrulama henüz tamamlanmadığından adaylar sentez/indeks/soru aşamasına otomatik geçmez; biten nesil NEEDS_REVIEW olur. Son UI'da gerçek 320/390/768/1440 px kontrolü geçti. [Yeni akış, canlı kimlikler ve kabul sınırları](docs/editor/2026-09-16-source-spans.md). Aşağıdaki paragraflar eski koşuların tarihsel durumudur.

İsteğe bağlı PaddleOCR ikinci okuyucusu `compose.ocr.yaml` ile özel ağda çalışır (4 CPU/4 GiB); sabit revision ağırlıklar imaj içindedir, dış TCP engellidir. Gerçek PDF 38, API/bağımsız PostgreSQL ve kaynak hashleriyle doğrulanarak 1600/2400 px işlendi: 30,353/31,610 s, kritik olumsuzluk korundu, eski görsel alıntı uyuşmazlığı kapıda bloke edildi. Dört bölgede okuma uyuşmazlığı sürüyor; tam doğruluk iddiası yok. Sağlık yanıtı OCR'dan ayrıldı; yük altında 15/15 yanıt. Servis ve alıntı kapısı tek sayfa kalibrasyonudur, mevcut analiz nesline otomatik yazmaz. [Pilot kanıtı ve sınırlar](docs/editor/2026-09-16-ocr-page-pilot.md). Offline paket `--with-ocr` seçeneği eklendi; yeni tam paket restore kabulü bekliyor.

Kaynak inceleme ekranında sahne içindeki kişi/olay adayları ve sayfa bağlantıları canlı API ile dört genişlikte doğrulandı. Soru cevabının durumu ve sınırlamaları görünür; dolu cevap kabulü bekleniyor. Yeni koşuda 13 yeniden kullanılan görselin önceki kaynak hatalarını aynen taşıdığı açıklama/render eşliğiyle doğrulandı; yeni PDF 6 hatasıyla en az 14 sayfada bilinen yanlış var, genel doğruluk oranı değildir. Takip betikleri gateway bağlantı resetini sınırlı retry ile ele alır; analiz işçisi kesilmedi. Yedekler artık 8 kitap tablosunun ve bütün artifact dosyalarının hashlerini içerir, restore yazıcıları başlatmadan karşılaştırır. Gerçek kaynaktan 340 dosya/207.058.811 bayt için referans üretildi; tam restore/arama kabulü henüz yok.

Gerçek koşuda üç sahne çağrısının 1800 token çıktıda kesilmesi üzerine sahne bütçesi 3600 yapıldı; toplam 8192 bağlam denetimi ve otomatik alt gruba bölme korundu. Kitap içeriği/istem değiştirilmedi. `max_output_tokens` çağrı izine eklendi. Tamamlanan 48 kaynak/48 görsel/ilk sahne korunarak aynı iş ikinci denemede sürüyor; yeni teknik sürümün tam anlamsal kabulü henüz yok.

Salt okunur inceleme ekranı `/editor/` altında canlıdır: bağımsız React/TypeScript, gerçek operatör API’si, kitap/sürüm seçimi, özgün sayfa ve OCR/PDF/model adayları, mevcut sahne/varlık/olay/yorum/soru sekmeleri. Sunucu Chrome ile 320/390/768/1440 px, altı sekme, kaynak sayfası ve oturum çıkışı doğrulandı; taşma yok. Kitap/analiz listesi API çıktısı bağımsız PostgreSQL ile eşleşti. Ekran kabul kararlarını yazmaz; kullanıcı/kitap/rol, yükleme ve düzeltme arayüzleri ile PDF.js/bbox tamamlanmadı. Yeni gateway web imajı nedeniyle eski offline paketin kabulü bu sürüme taşınmaz. Embedding/reranker sınırları ayrı ayarlanabilir, bu koşuda dörder CPU/thread.

Güncel kabul yöntemi (kullanıcının düzeltmesi): kitabın içeriği Codex tarafından tamamlanmaz; yalnız mevcut sunucu altyapısının çıktıları değerlendirilir. Önceki `18c22ea1-35e8-4e49-b762-82b3320ed49c` neslinin 48 görseli tamamlandı fakat bu nesilde Codex'in kaydettiği ret kararları sahne girdisini filtrelediğinden müdahalesiz kabul sayılamaz. İçerik düzeltmesi kaydı oluşturulmadı. Eski nesil iptal edilip korunarak `6fffd7ed-f0c6-4de5-af1b-1ebea8898c8b` / iş `99b42a5b-7eaf-40b2-b2e3-980046965b0f` başlatıldı; yalnız özgün model görselleri yeniden kullanılır, review kararları taşınmaz. Takip: `evidence/reference-follow-unassisted.log`. Kapasite 48 CPU/48 thread, dört slot oldu. API/DB kontrolü sıfır kaynak düzeltmesi ve sıfır inceleme kararı ile model girdisinin kökenini de denetler. [22 bölümlük kapsam ve kalite durumu](docs/editor/roadmap-live-status.md) açık işleri gösterir. Önceki paragraflardaki generation/CPU değerleri tarihsel koşulardır; yeni koşu tamamlanmış veya kabul edilmiş değildir.

Editör aynı depoda `apps/editor/` altında BI'dan bağımsızdır. Test sunucusunda `/data/nanobaseai/editor` altında ayrı PostgreSQL/Alembic, LangGraph PostgreSQL checkpointer, FastAPI operatör API, kalıcı analiz/soru işçisi, Qdrant, Prometheus ve nginx geçidi çalışır. Host erişimi yalnız `127.0.0.1:8810` ve metrikler `127.0.0.1:9096`; BI iç koduna/tablosuna/ağına bağımlılık yok. Belge aracı Docling + Poppler + Tesseract `tur/eng`, ağsız konteynerde çalışır. CPU model profili Qwen3.8-27B Q4_K_M + Q8 görsel projektör ve mevcut BGE embedding/reranker ağırlıklarını ayrı servislerde kullanır; anlamsal uygunluk henüz kabul edilmiş değildir.

Gerçek referans kitap (SHA-256 `94747e819a760fef5e3cef39bb3284c543e217923e2560a3e5719e1060774e50`) 48/48 sayfa OCR/render olarak işlendi; ilk teknik ayrıştırma 378,22 sn sürdü. Ön yüz yerine gerçek yükleme API'sinden aynı 19.806.912 bayt dosya geçirildi; 48 kaynak kaydının tam API çıktısı bağımsız PostgreSQL sorgusuyla eşleşti. Önceki analiz nesli `18c22ea1-35e8-4e49-b762-82b3320ed49c`, iş `81509659-5c37-4764-8e21-fa2c9687d382`: bütün sayfalarda görsel okuma ve sonraki analiz/arama/soru aşamaları uzun CPU koşusunda; tamamlandığı varsayılmaz. İki eski deneme kaynak düzeltmeleri için iptal edildi ve kayıtları korundu. Sayfa taşan Docling paragrafları ve TSV tırnak ayrıştırması düzeltildi; `ocr-regions-v2` 2400px, sayfa içi kelime/bbox kayıtlarını tutar. OCR'nin kaçırdığı renkli etkinliklerde PDF metin katmanı da korunur. Canlı ilerleme API ve `evidence/reference-follow-v3-resumed.log`, sonuçlar `runtime/book-analysis/<generation_id>/`. İlk görsel sayfa 4 CPU ile 311,825 sn; boş CPU gözleminden sonra yalnız Editör 8 CPU/8 thread olarak sınırlandı. İşçi/model yeniden başlamasında tamamlanan kayıtlar korundu, aynı iş yeniden denendi. Tek operatör erişimi vardır; kullanıcı-kitap rolleri, düzeltme bağımlılıkları, editör karar/düzeltme ekranları ve anlamsal/editör kabulü tamamlanmadı. `pilot_ready=false`. Önceki offline paket/restore doğrulaması altyapı sürümüne aittir; yeni analiz kodunu içermez. BI entegrasyonu tanımlı API'lerle yapılacak.

Son koşu ayrıntısı: `evidence/reference-follow-final.log` güncel takip günlüğüdür. İşçi güncellemeleriyle dolan lease denemeleri sessizce sıfırlanmaz; gerekçeli operatör retry ek deneme açar ve geçmişi korur. İlk 10 görselden 6. sayfadaki göz rengi ve 10. sayfadaki hediye iddiası kaynakla uyuşmadığı için API üzerinden REJECT kaydedildi; sahne çıkarımı bu betimlemeleri kullanmaz. Kaynak karşılaştırması insan editör onayı değildir. Olay modu/fail/konuşmacı, sınırdaki görsel-metin olay birleştirmesi, ayrı destek kontrolü ve sınırlı edebî sentez uygulanır; bunların gerçek koşu kabulü ayrıca beklenir.

Önceki kapasite adımı: kullanıcının daha fazla CPU izni ve canlı boş kapasite ölçümüyle 32 CPU/32 thread, 4 model slotu, toplam 32768 bağlam (slot başına 8192); bağımsız kaynak grupları en fazla dört paralel çağrı. PID 128 sınırındaki gerçek libgomp başlatma hatası yalnız LLM için 512 sınırıyla giderildi. Ortak sağlık uçları 200; tam SLO kabulü değildir. İlk 13 görselin 9'unda yanlış metin/ayrıntı gözlendi ve REJECT kaydedildi; kaynakları korundu. Bu model kalite bulgusu gizlenmez. Katkıcılar ve yer/nesne adayları, karakter sentezinden ayrı kanonik varlık olarak korunur. [B01–B18/V01–V08 takip tablosu](docs/editor/reference-book-acceptance.md) test başarısı iddiası içermez.

Kalıcı `editor` branch'i açılmaz; tek trunk `main`. Kurulum, ağ çakışması ön kontrolü, offline imaj/model paketi ve yedek/restore adımları: [apps/editor/README.md](apps/editor/README.md). Kanıt ve sınırlar: [altyapı raporu](docs/editor/2026-09-16-infrastructure.md). Bağlayıcı kurallar: [AGENTS.md](AGENTS.md#editör-modülü-aynı-depo-bağımsız-uygulama).

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
| LLM (OpenAI uyumlu) | NVIDIA hosted `integrate.api.nvidia.com/v1`, `deepseek-ai/deepseek-v4-flash-0731`, düşünme kapalı (köprü drop-in `semantic-bridge-nvidia.env`); eski GPU sunucusu yok |
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
| `src/canvas/stitch/Shell.tsx` | Ortak kabuk (üst şerit, ray, modül menüsü). Sağ üstteki yakınlaştırma (%50–%200, adım 10) kabuğun kendi durumudur: ekranlar içeriklerini `ZoomStage` ile sarar (CSS `zoom`, `main` sabit kalır, yazdırmada 1); Genel bakış kanvası `onZoom` ile kendi ölçeğini verir (sığdırma × zoom). Pano sürüklemesi ölçeğe bölünür. 2026-09-16'ya kadar kanvas dışındaki 8 ekranda düğme sabit %100 gösteriyordu |
| `src/canvas/board/` | Panolar: kişiye özel kart panosu (sürükle/boyutlandır, SQL paneli, son sorgu saati, başlık/not, CSV/PDF, KPI karşılaştırma, ECharts-GL 3B); düzen + son sonuç sunucuda `semantic_board_cards` (`backend/semantic_bridge/board.py`, `/api/v1/board`), tarayıcı yalnız önbellek; zamanlayıcı `timas-board.timer` |
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
| `src/canvas/kampus` | Girişten sonraki ilk ekran (`/`): Kampüs intraneti + ZEKİ + modüllere geçiş; BI genel bakış `/genel-bakis`. Rehber ve sağ üstteki profil penceresi (`ProfileDialog.tsx`) gerçek veriden; kutlama/alkış/bülten kartları hâlâ tasarım metni |
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

- **Kokpit yayını:** kaynak sunucuda derlenir. `rsync -a --delete src/ nanobase-direct:/data/nanobaseai/bi/frontend/src/`, sunucuda `VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas npm run build`, sonra `sudo rsync -a --delete --no-o --no-g dist/ /data/nanobaseai/bi/cockpit/dist/`. Commit etmek yayınlamak değildir; canlıdaki `index.html` tarihine bak.

- Bu proje için ayrıca kalıcı bellek kayıtları `~/.claude/projects/.../memory/MEMORY.md` altında tutulur (semantic layer kararları, sertifikalama, kalite kapısı, vb.) — kod tabanından türetilemeyen proje bağlamı orada.
- Bu dosya + `docs/GELISTIRME-GUNLUGU.md` çifti bir **talimat**tır, hook değildir: oturumdaki Claude'un CLAUDE.md'yi okuyup uygulamasına bağlıdır, zorlayıcı değildir. Gerçek zorlama istenirse `.claude/settings.json`'a bir hook eklenebilir (örn. commit sonrası günlük güncellendi mi kontrolü) — bu ayrı bir iş, henüz yapılmadı.
