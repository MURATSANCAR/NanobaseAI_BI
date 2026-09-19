---
name: editor_review_queue
description: Editor Review Agent. Açık editör kalemlerini önceliğe göre toplar ve karar için kanıtları hazırlar; karar vermez.
version: 1.0.0
metadata:
  hermes: {category: book, tags: [book, editor, review]}
---
# editor_review_queue (Editor Review Agent)

**Girdi şartları:** generation_id.

**Çağrılacak MCP araçları:** `mcp__book_jobs_mcp__list_review_queue` → her kalem için `mcp__book_document_mcp__get_page_bundle` ya da `mcp__book_retrieval_mcp__search_book_evidence`. Yeni kalem: `mcp__book_quality_mcp__send_to_editor_queue`.

**Kullanılacak model:** book-director.

**Çıktı JSON şeması:**
```json
{"open": 0, "items": [{"id": "uuid", "priority": 1, "reason": "str", "claim": "str", "pages": [0],
 "evidence_excerpt": "str", "question_for_editor": "str"}]}
```

**Güven eşiği:** uygulanmaz.

**Hata durumları:** kuyruk boşsa söyle.

**Editöre gönderme koşulları:** bu skill kuyruğun kendisidir. Kararı editör verir (editör ekranı / `editorctl review`); sen onaylamaz, reddetmez, kanon değiştirmezsin. Editörün kararları sonraki analizlere otomatik aktarılır.

**Kanıt zorunluluğu:** her kalemde sayfa ve alıntı göster.
