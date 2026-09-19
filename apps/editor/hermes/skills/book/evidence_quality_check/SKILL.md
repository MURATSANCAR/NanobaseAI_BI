---
name: evidence_quality_check
description: Critic Agent. Bir iddia ya da cevap taslağının her cümlesini kanıtına göre denetler.
version: 1.0.0
metadata:
  hermes: {category: book, tags: [book, quality, critic]}
---
# evidence_quality_check (Critic Agent)

Bu skill'i `delegate_task` ile bir alt ajana ver; alt ajan başka bir şey yapmaz.

**Girdi şartları:** generation_id; iddia listesi (§7 biçimi) ya da claim_id'ler.

**Çağrılacak MCP araçları:** her iddia için `mcp__book_quality_mcp__validate_claim` → kayıtlı iddiada `mcp__book_quality_mcp__calculate_confidence` → gerekirse `mcp__book_document_mcp__get_page_bundle` ile sayfa metnini oku.

**Kullanılacak model:** book-director (alt ajan).

**Çıktı JSON şeması:**
```json
{"results": [{"claim": "str", "valid": true, "problems": ["str"], "confidence": 0.0, "needs_editor_review": false}],
 "passed": 0, "failed": 0}
```
Her iddianın biçimi:
```json
{"claim": "Mert karanlıktan korkuyor", "source_pages": [8, 9], "evidence": "Mert karanlıkta geri dönmek istedi",
 "confidence": 0.91, "status": "CANDIDATE", "needs_editor_review": false}
```

**Güven eşiği:** 0.55 altı → needs_editor_review=true.

**Hata durumları:** alıntı sayfada yoksa iddia geçersizdir; düzeltmeye çalışma, raporla.

**Editöre gönderme koşulları:** kip ihlali (plan/hayal/şaka gerçekleşmiş gibi), kesinleşmemiş kimlik kesin gibi, güven < 0.55.

**Kanıt zorunluluğu:** kaynaksız iddia geçemez.
