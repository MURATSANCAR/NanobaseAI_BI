---
name: emotion_analysis
description: Karakterlerin duygu akışı ve tetikleyicileri, sayfa sayfa.
version: 1.0.0
metadata:
  hermes: {category: book, tags: [book, emotion]}
---
# emotion_analysis

**Girdi şartları:** generation_id; isteğe bağlı karakter.

**Çağrılacak MCP araçları:** `mcp__book_retrieval_mcp__search_character_history` (emotions) → örnek cümle için `mcp__book_retrieval_mcp__search_book_evidence`. Eksik duygu kaydı: `mcp__book_knowledge_mcp__save_emotion` (kanıtla).

**Kullanılacak model:** book-director.

**Çıktı JSON şeması:**
```json
{"character": "str", "arc": [{"page": 0, "emotion": "str", "intensity": 0.0, "trigger": "str", "quote": "str"}],
 "dominant": ["str"], "shifts": [{"from": "str", "to": "str", "pages": [0, 0], "cause": "str"}]}
```

**Güven eşiği:** güveni 0.5 altındaki duyguyu akışa koyma, ayrıca listele.

**Hata durumları:** duygu kaydı yoksa adım 10 bitmemiştir.

**Editöre gönderme koşulları:** yaş grubu için yoğun korku/üzüntü (intensity ≥ 0.8) sayfaları `age_group_assessment` için işaretle; ayrıca kuyruğa gerek yok.

**Kanıt zorunluluğu:** her duygu bir sayfa alıntısına bağlı.
