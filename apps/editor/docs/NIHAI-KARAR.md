# Editör — Nihai karar (kaynak metin)

> Bu dosya kullanıcının 2026-09-19'da verdiği analizin kelimesi kelimesine kopyasıdır.
> Modülün bütün kararları buna bağlıdır. Buradan sapan bir uygulama kararı
> `docs/UYGULAMA-NOTLARI.md` içinde gerekçesiyle ayrıca yazılır; bu dosya değiştirilmez.

Hermes, kitabı analiz eden model olmayacak. Hermes:

- Kullanıcıyla konuşacak
- Analiz planını oluşturacak
- Doğru modeli seçecek
- MCP araçlarını çağıracak
- Alt analiz görevlerini paralel yürütecek
- Sonuçları birleştirecek
- Kanıt ve güven kontrolü yaptıracak
- Editör kuyruğuna gönderecek

Kitap gerçekleri Hermes'in hafızasında değil, PostgreSQL ve Evidence Ledger'da tutulacak.

Hermes'in özel model endpoint'i, MCP, skill, alt ajan, kalıcı hafıza ve zamanlanmış görev desteği bu role uygun. Hermes Agent · Hermes araçları

## 1. Hermes tarafında kullanılacak ana yapı

Hermes Agent

Hermes üzerinde şu ana persona bulunur:

**Book Director**

> Sen bir kitap analiz yönetmenisin.
> Kitap hakkında kanıtsız iddia üretme.
> Her çıkarımı sayfa, paragraf, görsel bölge veya olay kaydına bağla.
> Belirsiz sonuçları kesin gerçek olarak yazma.
> Çelişkileri editör incelemesine gönder.

Hermes'in kendi hafızası yalnızca şunları tutar:

- Kullanıcı tercihleri
- Yayıncı değerlendirme kuralları
- Yaş grubu rubrikleri
- Analiz profilleri
- Proje ayarları
- Editörün onayladığı çalışma biçimi

Karakter, olay veya duygu bilgileri Hermes hafızasına yazılmaz. Bunlar PostgreSQL'de tutulur.

## 2. Model gateway

Hermes doğrudan model isimlerini görmemeli. Arada yerel bir Model Gateway olmalı:

```
Hermes
   ↓
Local Model Gateway
   ↓
vLLM / SGLang
   ↓
Qwen modelleri
```

Gateway'de model adları şöyle gizlenebilir:

- book-director
- book-vision-fast
- book-vision-deep
- book-embedding
- book-reranker
- book-audio

### Qwen model dağılımı

| Alias | Gerçek model | Kullanım |
|---|---|---|
| book-director | Ana Qwen reasoning modeliniz | Planlama, sentez, özet, karar |
| book-vision-fast | Qwen3-VL-8B-Instruct | Tüm sayfaların hızlı taranması |
| book-vision-deep | Qwen3-VL-32B-Thinking | Zor görsel, karakter ve sahne analizi |
| book-embedding | Qwen3-Embedding-8B | Kitap/karakter/olay semantik araması |
| book-reranker | Qwen3-Reranker-8B | Kanıt ve sayfa sıralaması |
| book-audio | Qwen3-Omni-30B-A3B-Captioner | İleride sesli kitap/ses analizi |

Qwen3-VL-32B-Thinking, 256K bağlam, uzun belge, görsel akış ve genişletilmiş OCR yetenekleri nedeniyle görsel kitap analizinin ana modeli olur. Model kartı

Qwen3-Embedding-8B, 100'den fazla dil, 32K bağlam ve 4096 boyuta kadar embedding destekliyor. Qwen3-Reranker-8B de 100'den fazla dil ve 32K bağlamla kanıt seçimi için kullanılabilir. Embedding · Reranker

## 3. Hermes Skills

Hermes'e serbest biçimde "kitabı analiz et" dedirtmek yerine kontrollü skill'ler tanımlanmalı.

### Temel skill'ler

- book_intake
- book_full_analysis
- book_question_answering
- book_summary
- character_analysis
- event_timeline
- emotion_analysis
- visual_scene_analysis
- visual_character_continuity
- universe_canon_analysis
- age_group_assessment
- publisher_decision_support
- evidence_quality_check
- editor_review_queue
- report_generation

Her skill şu bilgileri içermeli:

- Girdi şartları
- Çağrılacak MCP araçları
- Kullanılacak model
- Çıktı JSON şeması
- Güven eşiği
- Hata durumları
- Editöre gönderme koşulları
- Kanıt zorunluluğu

## 4. Hermes MCP sunucuları

Hermes'e yalnızca kontrollü ve yüksek seviyeli araçlar açılmalı.

**book_document_mcp**
- inspect_book()
- create_page_manifest()
- extract_text_layer()
- render_page()
- run_ocr()
- get_page_bundle()

**book_vision_mcp**
- analyze_page_visual()
- detect_characters()
- detect_objects()
- detect_scene()
- compare_character_appearances()
- check_text_visual_consistency()

**book_knowledge_mcp**
- save_character_candidate()
- resolve_character_identity()
- save_event()
- merge_events()
- save_emotion()
- build_timeline()
- detect_contradictions()

**book_retrieval_mcp**
- embed_passages()
- search_book_evidence()
- rerank_evidence()
- search_character_history()
- search_universe_canon()

**book_quality_mcp**
- validate_claim()
- calculate_confidence()
- send_to_editor_queue()
- run_regression_suite()
- create_analysis_report()

Hermes'e doğrudan şu yetkiler verilmemeli:

- Serbest SQL
- Sınırsız dosya sistemi
- Root terminal
- Ham model değiştirme
- Kanıt olmadan kayıt güncelleme
- Editör onayı olmadan kanonu değiştirme

## 5. Analiz iş akışı

Kullanıcı:

> "Bu kitabı tam analiz et."

Hermes şu sırayla çalışır:

1. Kitap ve içerik sürümünü oluşturur.
2. Sayfa manifestini çıkarır.
3. PDF metin katmanını kontrol eder.
4. Gerekli sayfalarda OCR çalıştırır.
5. Sayfaları görsel olarak Qwen3-VL-8B-Instruct ile tarar.
6. Belirsiz sayfaları Qwen3-VL-32B-Thinking modeline gönderir.
7. Karakter ve olay adaylarını çıkarır.
8. Karakter kimliklerini birleştirir.
9. Gerçekleşmiş olay, plan, hayal ve şaka ayrımını yapar.
10. Duygu ve tema analizini gerçekleştirir.
11. Embedding ve reranker indeksini oluşturur.
12. Ana Qwen modeliyle bölüm ve kitap özetlerini üretir.
13. Critic Agent kanıtları kontrol eder.
14. Çelişkileri NEEDS_REVIEW olarak editör kuyruğuna gönderir.
15. Rapor ve atıflı soru-cevap ekranını hazırlar.

Uzun süren bu işlem Hermes'in tek sohbet turunda tutulmamalı. Hermes job_id oluşturmalı; kalıcı iş akışı ve retry sistemi ayrı workflow servisinde çalışmalıdır.

En kaliteli yapı:

```
Hermes → MCP → Temporal Workflow
                 ↓
       Python analiz işçileri
                 ↓
       PostgreSQL / Qdrant / Filesystem
```

Mevcut Python + LangGraph planı analiz grafiğinde kullanılabilir; Temporal ise uzun işlerin checkpoint, retry ve devam ettirme katmanı olur.

## 6. İki H100 için yerleşim

H100 NVL 94 GB varsayımıyla:

**GPU 0**
- Ana Qwen reasoning modeli
- Qwen3-Embedding-8B
- Qwen3-Reranker-8B

Ana model çok büyükse embedding ve reranker batch modunda geçici olarak GPU'ya alınır.

**GPU 1**
- Qwen3-VL-32B-Thinking
- Qwen3-VL-8B-Instruct

8B modeli bütün kitabı hızlı tarar. 32B Thinking modeli yalnızca:

- Karakter kimliği belirsiz sayfalarda
- Görsel-metinsel çelişkilerde
- Önemli olaylarda
- Karakter sürekliliği kontrolünde
- Editör raporu hazırlanırken

kullanılır.

Qwen3-VL-235B-A22B modelini bu sunucuda ana görsel model olarak seçmem. 236B toplam parametre nedeniyle BF16 olarak iki H100'e sığmaz; 4-bit çalıştırılsa bile ana model ve KV cache için çok az alan bırakır. Model kartı

## 7. Kalite kuralları

Her çıkarım şu alanları taşımak zorunda:

```json
{
  "claim": "Mert karanlıktan korkuyor",
  "source_pages": [8, 9],
  "evidence": "Mert karanlıkta geri dönmek istedi",
  "confidence": 0.91,
  "status": "CANDIDATE",
  "needs_editor_review": false
}
```

Zorunlu kurallar:

- Kaynaksız iddia üretilemez.
- Belirsiz karakter kesin kimlik olarak kaydedilemez.
- Plan, hayal veya şaka gerçekleşmiş olay sayılmaz.
- Görsel-metinsel uyuşmazlık doğrudan hata değil, aday bulgu olur.
- Eski analiz raporu üzerine yazılmaz; yeni generation_id oluşturulur.
- Editör düzeltmesi sonraki analizlere aktarılır.
- Model, prompt, sürüm ve kullanılan kaynaklar kaydedilir.
- Her analiz sonunda regression test çalışır.

## Nihai Hermes mimarisi

```
Hermes Book Director
 ├── Book Skills
 ├── Critic Agent
 ├── Editor Review Agent
 ├── Local Model Gateway
 ├── Book Analysis MCP
 ├── Temporal/LangGraph Workflow
 ├── PostgreSQL Evidence Store
 ├── Qdrant Retrieval
 └── Local PDF/Image Storage
```

Bu tasarımda Hermes yalnızca sohbet eden bir agent olmaz. Kitap alma, görsel analiz, karakter sürekliliği, evren takibi, yaş grubu değerlendirmesi ve yayıncı karar desteğini yöneten kanıta bağlı bir kitap istihbarat yöneticisi olur.

## Çalışma kuralı (aynı mesajdan)

- Editör BI'dan ayrı bir modüldür; BI tarafından hiçbir şey kullanmaz. Kod bu depoda durur, geri kalan her şey (veritabanı, vektör deposu, model kopyaları, konteynerler, ağ) kendine aittir.
- Kullanılan her şey Docker içinde çalışır. Modeller yalnız ihtiyaç anında ayağa kalkar, iş bitince durur; boşta GPU ve RAM tutmaz.
- Kurulan her şeyin en güncel sürümü kullanılır.
