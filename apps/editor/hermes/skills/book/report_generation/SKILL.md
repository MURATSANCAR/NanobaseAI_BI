---
name: report_generation
description: Atıflı analiz raporunu üretir ya da gösterir; eski raporun üzerine yazmaz.
version: 1.0.0
metadata:
  hermes: {category: book, tags: [book, report]}
---
# report_generation

**Girdi şartları:** generation_id; rapor türü: ANALYSIS (varsayılan), EDITOR, AGE_GROUP, PUBLISHER.

**Çağrılacak MCP araçları:** varsa `mcp__book_jobs_mcp__get_report`; yeniden üretmek için `mcp__book_quality_mcp__run_regression_suite` → `mcp__book_quality_mcp__create_analysis_report`. Ek bölümler (EDITOR/AGE_GROUP/PUBLISHER) önce Critic Agent'tan geçer.

**Kullanılacak model:** book-director.

**Çıktı JSON şeması:**
```json
{"report_id": "uuid", "kind": "str", "markdown": "str", "saved_claims": ["uuid"]}
```

**Güven eşiği:** rapor doğrulanmamış cümleleri "(doğrulanmadı)" diye işaretler; çıkarmaz.

**Hata durumları:** regresyon KALDI ise raporun başına bunu yaz ve kullanıcıya söyle.

**Editöre gönderme koşulları:** regresyon kalırsa kalan kontrolleri kuyruğa gönder.

**Kanıt zorunluluğu:** rapordaki her kitap cümlesi [s.N] atıflı; her rapor yeni kayıttır, eskisi değişmez.
