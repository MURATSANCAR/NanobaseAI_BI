---
name: character_analysis
description: Bir karakterin kimliği, diğer adları, görünümü, duyguları, katıldığı olaylar ve başka karakterlerle ilişkisi (kimlerle birlikte, kim kime ne yaptı); kimlik belirsizliğini açıkça söyler.
version: 1.0.0
metadata:
  hermes: {category: book, tags: [book, character]}
---
# character_analysis

**Girdi şartları:** generation_id, karakter adı (ya da "bütün karakterler").

**Çağrılacak MCP araçları:** `mcp__book_retrieval_mcp__search_character_history` → gerekirse `mcp__book_retrieval_mcp__search_book_evidence` → kimlik şüphesi varsa `mcp__book_knowledge_mcp__resolve_character_identity` yalnız çözülmemiş anmalar için. Yeni anma kaydı: `mcp__book_knowledge_mcp__save_character_candidate` (kanıtla).

**İlişki soruları** ("X kimlerle birlikte", "X ile Y'nin ilişkisi", "kim kime ne yaptı", "X'e en yakın kim"):
`mcp__book_graph_mcp__character_synergies` (aynı olayda geçen bütün karakterler ve ortak olaylar),
`mcp__book_graph_mcp__recommend_related` (en ilişkili k karakter, gerekçesiyle),
`mcp__book_graph_mcp__event_triples` (yapan → olay → nesne kenarları, sayfa+alıntı kanıtıyla).
Bu araçlar yalnız kabul edilmiş iddia ve doğrulanmış alıntı üstünden çalışır; varsayılan olarak
gerçekleşmiş olaylar (plan/hayal/şaka sayılmaz). Cevapta ilişkiyi ortak olayın sayfasıyla ver.
Boş sonuç yokluk kanıtı değildir: "kayıtlarda ortak olay yok" de, "ilişkileri yok" deme.

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
