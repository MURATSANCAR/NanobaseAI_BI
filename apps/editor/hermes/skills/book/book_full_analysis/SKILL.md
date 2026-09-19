---
name: book_full_analysis
description: "Bu kitabı tam analiz et" isteği. 15 adımlık analizi Temporal iş akışında başlatır, job_id verir, izler; sohbet turunda analiz yapmaz.
version: 1.0.0
metadata:
  hermes: {category: book, tags: [book, analysis, workflow]}
---
# book_full_analysis

**Girdi şartları:** inbox'taki PDF adı ya da deftere alınmış kitap. Aynı içerik sürümünde koşan bir iş varsa yenisi açılmaz.

**Çağrılacak MCP araçları:** `mcp__book_jobs_mcp__start_analysis_job` (job_id döner) → `mcp__book_jobs_mcp__get_job_status` (izleme) → bitince `mcp__book_jobs_mcp__get_report`.

İş akışının adımları (Temporal, kalıcı, yeniden denemeli): 1 sürüm + yeni generation_id · 2 sayfa manifesti · 3 metin katmanı · 4 OCR · 5 hızlı görsel tarama · 6 belirsiz sayfalarda derin inceleme · 7 karakter/olay adayları · 8 kimlik birleştirme (+ görsel süreklilik) · 9 gerçekleşmiş/plan/hayal/şaka ayrımı · 10 duygu ve tema · 11 embedding + reranker indeksi · 12 bölüm ve kitap özetleri · 13 Critic Agent · 14 çelişkiler → NEEDS_REVIEW · 15 regresyon + rapor.

**Kullanılacak model:** iş akışı seçer: OCR ve tarama book-vision-fast; belirsiz sayfa, süreklilik book-vision-deep; çıkarım, özet, Critic book-director; indeks book-embedding + book-reranker. Modeller yalnız o adımda açılır, iş bitince kapanır.

**Çıktı JSON şeması:**
```json
{"job_id": "uuid", "workflow_id": "str", "book_version_id": "uuid", "status": "QUEUED|RUNNING|SUCCEEDED|FAILED",
 "step": "n/15 ad", "generation_id": "uuid", "open_review_items": 0, "report_id": "uuid"}
```

**Güven eşiği:** iş akışının içinde: Critic sonrası güveni 0.55'in altındaki iddia editör kuyruğuna gider.

**Hata durumları:** FAILED → `error` alanını kullanıcıya aynen ilet, işi yeniden başlatmayı öner; `failures` alanındaki tek tek düşen sayfaları raporla. gpu_busy → GPU'yu editör dışı bir iş tutuyor; kullanıcıya söyle, zorlamaya çalışma.

**Editöre gönderme koşulları:** iş akışı otomatik gönderir (adım 14 ve Critic). Bitince açık kalem sayısını kullanıcıya bildir ve `editor_review_queue` skill'ini öner.

**Kanıt zorunluluğu:** raporu özetlerken yalnız rapordaki atıflı cümleleri kullan.
