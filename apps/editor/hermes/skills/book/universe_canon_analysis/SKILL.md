---
name: universe_canon_analysis
description: Kitabı serinin/evrenin editör onaylı kanonuyla karşılaştırır; kanonu değiştirmez.
version: 1.0.0
metadata:
  hermes: {category: book, tags: [book, canon, universe]}
---
# universe_canon_analysis

**Girdi şartları:** generation_id ve evren anahtarı (kitap alınırken verilen `universe`).

**Çağrılacak MCP araçları:** `mcp__book_retrieval_mcp__search_universe_canon` (karakter, mekân, kural için ayrı sorgular) → `mcp__book_retrieval_mcp__search_character_history` / `search_book_evidence` → uyuşmazlık için `mcp__book_quality_mcp__send_to_editor_queue`.

**Kullanılacak model:** book-director; arama book-embedding + book-reranker.

**Çıktı JSON şeması:**
```json
{"universe": "str", "consistent": [{"canon_key": "str", "book_claim": "str", "source_pages": [0]}],
 "conflicts": [{"canon_key": "str", "canon_value": "str", "book_claim": "str", "source_pages": [0], "confidence": 0.0}],
 "new_facts_for_editor": [{"kind": "str", "key": "str", "value": "str", "source_pages": [0]}]}
```

**Güven eşiği:** çatışma güveni ≥ 0.5 ise kuyruğa.

**Hata durumları:** evrende kanon kaydı yoksa söyle; kitabın bulgularını "kanona önerilecek" diye listele.

**Editöre gönderme koşulları:** her çatışma ve her yeni kanon önerisi. Kanon yalnız editör kararıyla değişir; senin kanon yazma aracın yoktur.

**Kanıt zorunluluğu:** kitap tarafındaki her iddia sayfa atıflı.
