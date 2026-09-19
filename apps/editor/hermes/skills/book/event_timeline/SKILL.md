---
name: event_timeline
description: Gerçekleşmiş olayların hikâye sırası; plan, hayal, rüya ve şakayı ayrı listeler.
version: 1.0.0
metadata:
  hermes: {category: book, tags: [book, events, timeline]}
---
# event_timeline

**Girdi şartları:** generation_id.

**Çağrılacak MCP araçları:** `mcp__book_knowledge_mcp__build_timeline`; birleştirme gerekirse `mcp__book_knowledge_mcp__merge_events`; kullanıcı yeni bir olay gösterirse `mcp__book_knowledge_mcp__save_event` (kip zorunlu, kanıtla).

**Kullanılacak model:** book-director.

**Çıktı JSON şeması:**
```json
{"timeline": [{"order": 0, "summary": "str", "pages": [0, 0], "participants": ["str"], "confidence": 0.0}],
 "not_realized": [{"modality": "PLAN|DREAM|IMAGINATION|JOKE|LIE|HYPOTHETICAL|UNCERTAIN", "summary": "str", "pages": [0, 0]}]}
```

**Güven eşiği:** güveni 0.5 altındaki olayı sırada "belirsiz" diye işaretle.

**Hata durumları:** zaman çizelgesi boşsa iş adım 9'u geçmemiştir; durumu göster.

**Editöre gönderme koşulları:** kipi UNCERTAIN olan önemli olaylar, sırası çelişen olaylar.

**Kanıt zorunluluğu:** plan, hayal ya da şaka REALIZED sayılmaz; her olay atıflı.
