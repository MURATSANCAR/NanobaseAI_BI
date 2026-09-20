# Editör: uygulama notları

Kaynak karar metni: [NIHAI-KARAR.md](NIHAI-KARAR.md). Bu dosya, o metnin açık bıraktığı ya da sunucunun
fiziksel sınırları yüzünden yorumlanması gereken noktaları ve gerekçelerini yazar. Kararın kendisi değişmedi.

## Ana kurallar (kullanıcı, 2026-09-19)

1. **Kitaba özel geliştirme yok.** Bir kusur tek bir kitapta görülmüş olabilir; çözümü her kitapta aynı çalışan genel bir mekanizmadır. Kitap adı, sayfa numarası, karakter adı, kelime listesi ya da tek kitabın verisine oturtulmuş eşik koda ve prompt'lara girmez. Eşik gerekiyorsa fiziksel anlamı olur, ayardan okunur ve ikinci bir kitapta doğrulanana kadar "tek kitapta ölçüldü" diye not edilir.
2. **Veriye elle müdahale yok.** Hatayı uygulama kendisi tespit eder ve kendisi düzeltir: kayıt yazılmadan önce kanıt/piksel/tutarlılık denetimi, geçmeyeni reddetme ya da daha güçlü modele/editör kuyruğuna gönderme, her koşunun sonunda regresyon değişmezleri. Geliştirici (ve Claude) defteri yalnız teşhis için okur; düzeltme kaydı, kanon ve altın dosya yazmak editörün işidir. Bir düzeltmenin işe yaradığı, kitabın yeni nesil olarak yeniden koşturulmasıyla kanıtlanır.

## Bileşenler ve sürümler (2026-09-19, hepsi en güncel sürüm)

| Parça | Sürüm | Nerede |
|---|---|---|
| Hermes Agent | `nousresearch/hermes-agent:v2026.9.14` | `editor-hermes`, API 127.0.0.1:19110 |
| Model sunucusu | `vllm/vllm-openai:v0.29.0` | model başına bir konteyner, `editor-model-*` |
| Model Gateway | kendi kodumuz (`src/editor/gateway.py`) | `editor-gateway`, 127.0.0.1:19100 |
| MCP sunucuları | `mcp` 2.2.0 (MCPServer, Streamable HTTP) | `editor-mcp`, yalnız iç ağ |
| İş akışı | Temporal server 1.32.0, UI 2.54.1, Python SDK 1.33.0 | `editor-temporal`, UI 127.0.0.1:19120 |
| Analiz grafiği | LangGraph 1.2.11 | `editor-worker` içinde |
| Kanıt defteri | PostgreSQL 18.6 | `editor-postgres`, 127.0.0.1:19130 |
| Vektör deposu | Qdrant 1.19.1 | `editor-qdrant`, yalnız iç ağ |
| Python | 3.14 (slim) | `editor-py` imajı |

Hepsi `/data/editor` altında (tt-gpu). BI'ın konteynerleri, ağı, veritabanı, Qdrant'ı ve model dosyaları kullanılmaz.

## Karar metninin yorumlandığı yerler

1. **vLLM / SGLang** — metin ikisini de sayar; tek sunucu olarak vLLM seçildi (Qwen3-VL, Qwen3-Embedding, Qwen3-Reranker ve Qwen3-Omni için resmî destek).
2. **book-director = "Ana Qwen reasoning modeliniz"** — bu, BI'ın da kullandığı `Qwen/Qwen3.8-27B-FP8` (revizyon `017b9c7af6`). Ortak kullanım olmasın diye editörün kendi kopyası var (`/data/editor/models/Qwen3.8-27B-FP8`), kendi konteynerinde koşar.
3. **book-audio** yerleşimi metinde yok ("ileride"); editörün kartında (GPU 1), yalnız istendiğinde açılır.
4. **GPU yerleşimi (2026-09-19, kullanıcı kararı):** metin §6 editöre iki kart ayırıyordu; BI'ın modeli aynı sunucuda koştuğu için kullanıcı kararıyla BI (`qwen38-27b`) yalnız GPU 0'da, editörün bütün modelleri GPU 1'de. §6'daki "GPU 0: ana model + embedding + reranker" ve "GPU 1: 32B + 8B" grupları tek kartta ardışık açılır: ana model (%48) + embedding (%21) + reranker (%23) birlikte sığar (soru-cevapta üçü aynı anda gerekir; embedding ve reranker 8K bağlamla çalışır, pasajlar paragraf boyunda — 32K'de %20 payla KV önbelleği yetmiyordu); 8B tarama (%40) ana modelle birlikte sığar; 32B Thinking (%90) ve ses modeli (%80) kartta yalnız çalışır, gateway boştaki editör modellerini kapatıp yer açar. İş akışının adımları zaten ardışık (tarama → derin inceleme → çıkarım → indeks) olduğu için bu takas adım sınırlarında olur.
4a. **Karar metninden ölçüme dayalı sapma (kullanıcı kararı, 2026-09-19): resimli sayfalar doğrudan derin modele.** Metin "8B bütün kitabı hızlı tarar, 32B yalnız belirsiz sayfalarda" diyor. İlk gerçek koşuda: (a) resimsiz sayfaları ayırma işini artık mürekkep ölçümü yapıyor (model yok, hata yok); (b) resimli 26 sayfanın 26'sı zaten derin modele gitti; (c) hızlı model resimli sayfaların %23'ünde figürü yanlış adlandırdı, bir kısmında işaret koymadan ve yüksek güvenle (tek kitapta ölçüldü). Varsayılan `EDITOR_VISION_SCREEN=deep`: resimli her sayfayı 32B ilk elden okur; 8B yalnız OCR'da kalır. `fast` değeri metindeki iki aşamalı akışı geri getirir; o modda derin modele gidecek sayfayı modelin beyanı değil kanıt belirler (kutusunda mürekkep ölçülen figür → kimlik; metin-görsel çelişkisi; anlaşılmayan sahne). "Önemli olay" kararı her iki modda da tek sayfaya bakan modelden alınmaz: ana model birleştirilmiş zaman çizelgesinde her olaya anlatı rolü verir (giriş, tetikleyici, dönüm noktası, doruk, çözüm, sıradan); kilit olayların derin taranmamış resimli sayfaları o zaman derin modele gider.
5. **Altıncı MCP sunucusu `book_jobs_mcp`.** "Hermes job_id oluşturmalı" ve "Hermes → MCP → Temporal" için gerekli: `start_analysis_job`, `get_job_status`, `cancel_job` ve salt okunur görünümler (`list_books`, `latest_generation`, `list_review_queue`, `get_report`). `book_document_mcp`'ye ayrıca `list_inbox` eklendi. Metindeki araçların hepsi adıyla var.
6. **OCR** ayrı bir motorla değil, book-vision-fast (Qwen3-VL OCR yeteneği) ile yapılır; metinde başka model yok.
7. **Görsel kanıt**: sayfa + görsel bölge kaydına bağlıdır. Metin alıntısı sayfa metninde birebir aranır (`quote_verified`); görsel kanıt modelin kayıtlı gözlemidir.
8. **Güven formülü** (`quality.confidence_from`): `model × (0,5 + 0,5 × doğrulanan alıntı oranı) × Critic katsayısı (DESTEKLİ 1, KISMİ 0,6, DESTEKSİZ 0,1) + min(0,10; 0,03 × (sayfa−1)) + 0,05 (metin+görsel birlikte)`. 0,55 altı editöre gider. Kesin kimlik için ≥0,85 ve en az iki sayfa kanıt.
9. **Editör kararı ve kanon yazımı Hermes aracı değildir.** `editorctl cli review decide …` ve `editorctl cli canon add …` ile yapılır. Düzeltmeler `editor_correction`'a yazılır ve aynı kitabın sonraki her analizine prompt'larla aktarılır.
10. **Hermes hafıza politikası** SOUL.md ile uygulanır (Hermes'te hafızayı konu bazında süzen bir ayar yok). Kitap gerçekleri için Hermes'in yazma yolu yalnız kanıt isteyen MCP araçlarıdır.
11. **Hermes'in yetkileri**: `terminal`, `file`, `code_execution`, `web`, `browser`, `vision` vb. araç setleri kapalı; yalnız MCP + memory + skills + delegation + cronjob + todo/clarify. Serbest SQL yok; dosya okuma yalnız inbox'tan.
12. **Adım 15 "atıflı soru-cevap ekranı"**: soru-cevap Hermes'in OpenAI uyumlu API'si (19110) ve `book_question_answering` skill'i ile hazır; ayrı bir ekran (arayüz) henüz yok.

## Veritabanının zorladığı kurallar

- Kanıtsız iddia: `claim_requires_evidence` tetikleyicisi commit anında reddeder.
- İddia içeriği değişmez; kanıt ve rapor tabloları yalnız eklemeli (`forbid_change`). Yeni analiz = yeni `generation`.
- `CONFIRMED` kimlik ≥ 0,85; `RESOLVED` anma ≥ 0,75.
- Zaman çizelgesi (`timeline` görünümü) yalnız `REALIZED` ve `MEMORY` olayları; `story_order` başka kipe verilemez.
- Çelişkiler `CANDIDATE` doğar; "hata" durumu yok.
- Kanon kaydı `approved_by` olmadan yazılamaz.

## İhtiyaç anında model

Model konteynerleri gateway tarafından `models.yaml`'dan oluşturulur ve durdurulmuş bekler. İlk istekte açılır (`/health` gelene kadar bekler), `idle_stop_sec` (600 sn) boyunca istek gelmezse durur. İş akışı bittiğinde `release_models` bütün editör modellerini kapatır. Kartta yer yoksa gateway yalnız boştaki **editör** modellerini kapatır; editöre ait olmayan bir konteynere dokunmaz, `503 gpu_busy` ile kartı kimin tuttuğunu döner.

## BI ile GPU paylaşımı

2026-09-19 21:10'da kullanıcı kararıyla BI'ın `qwen38-27b` konteyneri tek karta (GPU 0, TP1) alındı (`deploy/tt-gpu/compose.qwen27b.yaml`); öncesinde iki kartın ~78 GB'ını tutuyordu ve editörün büyük modelleri açılamıyordu. GPU 1 tamamen editörün. Gateway yine de editöre ait olmayan hiçbir konteynere dokunmaz.

## İndirme

Sunucunun internet çıkışında bağlantı başına ~0,2 MB/s sınır var; toplamda ~12 MB/s. Modeller `aria2c` ile dosya başına 16 bağlantıyla, `resolve/<revizyon>` adresinden indirildi; revizyonlar `/data/editor/models/MANIFEST.json`'da.

## Tek görsel okuma gerçek değildir (ölçüm, 2026-09-20)

Aynı model aynı sayfayı iki kez okuyunca figür adları 26 sayfanın 18'inde aynı çıkıyor; metin–görsel çelişki adayı bir koşuda 5, sonrakinde 0. Bu yüzden: figür adı taramadan değil kırpım eşleştirmesinden gelir; metin–görsel bulgu ancak 3 bağımsız oyun çoğunluğuyla deftere girer (`text_visual_check` oyları saklar); model değişikliği (`compare_models`) iki BF16 koşusu arasındaki farkla kıyaslanır, tek koşuyla değil. FP8 derin model bu ölçüyle BF16'dan ayırt edilemedi, bu ayarda daha yavaş; varsayılan BF16.

