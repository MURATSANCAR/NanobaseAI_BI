---
name: visual_character_continuity
description: Bir karakterin çizimlerinin sayfalar arasında tutarlı olup olmadığını derin modelle karşılaştırır.
version: 1.0.0
metadata:
  hermes: {category: book, tags: [book, vision, continuity]}
---
# visual_character_continuity

**Girdi şartları:** generation_id, karakter adı; karakterin görsel anma sayfaları (`search_character_history` → mentions, via VISUAL/BOTH).

**Çağrılacak MCP araçları:** `mcp__book_retrieval_mcp__search_character_history` → en fazla 6 sayfa seç (başı, ortası, sonu, kıyafet değişimi olan sayfalar) → `mcp__book_vision_mcp__compare_character_appearances`. Çok karakter için `delegate_task` ile paralel.

**Kullanılacak model:** book-vision-deep.

**Çıktı JSON şeması:**
```json
{"character": "str", "pages": [0], "same_character_everywhere": true,
 "differences": [{"attribute": "str", "pages": [0], "description": "str", "explained_by_story": false, "continuity_candidate": true, "confidence": 0.0}]}
```

**Güven eşiği:** confidence < 0.5 farkları "zayıf aday" diye ayrı listele.

**Hata durumları:** 3'ten az görsel sayfa → karşılaştırma yapılmaz, söyle.

**Editöre gönderme koşulları:** `continuity_candidate=true` ve `explained_by_story=false` olan her fark (araç kaydı açar; kuyruk için `send_to_editor_queue`).

**Kanıt zorunluluğu:** her fark sayfa numaralarıyla; farklar hata değil ADAY bulgudur.
