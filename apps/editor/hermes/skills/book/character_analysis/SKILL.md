---
name: character_analysis
description: Bir karakterin kimliği, diğer adları, görünümü, duyguları ve katıldığı olaylar; kimlik belirsizliğini açıkça söyler.
version: 1.0.0
metadata:
  hermes: {category: book, tags: [book, character]}
---
# character_analysis

**Girdi şartları:** generation_id, karakter adı (ya da "bütün karakterler").

**Çağrılacak MCP araçları:** `mcp__book_retrieval_mcp__search_character_history` → gerekirse `mcp__book_retrieval_mcp__search_book_evidence` → kimlik şüphesi varsa `mcp__book_knowledge_mcp__resolve_character_identity` yalnız çözülmemiş anmalar için. Yeni anma kaydı: `mcp__book_knowledge_mcp__save_character_candidate` (kanıtla).

**Kullanılacak model:** book-director; görünüm sorusunda `visual_character_continuity` skill'ine geç.

**Çıktı JSON şeması:**
```json
{"name": "str", "aliases": ["str"], "identity_status": "CANDIDATE|UNCERTAIN|CONFIRMED", "identity_confidence": 0.0,
 "description": "str", "first_page": 0, "emotions": [{"page": 0, "emotion": "str"}],
 "events": [{"pages": [0, 0], "modality": "str", "summary": "str"}], "claims": [{"claim": "str", "source_pages": [0]}]}
```

**Güven eşiği:** kimlik CONFIRMED değilse ve güven < 0.85 ise "kimlik kesinleşmedi" de.

**Hata durumları:** ad defterde yoksa benzer adları listele; uydurma.

**Editöre gönderme koşulları:** iki farklı karakterin aynı kişi olabileceğine dair kanıt varsa ya da bir anma iki karaktere bağlanıyorsa `send_to_editor_queue` (öncelik 2).

**Kanıt zorunluluğu:** her özellik bir anma ya da olay kaydına atıflı.
