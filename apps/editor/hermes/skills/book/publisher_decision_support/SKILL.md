---
name: publisher_decision_support
description: Yayıncı değerlendirme kurallarına göre kanıtlı karar desteği raporu; kararı vermez, gerekçelendirir.
version: 1.0.0
metadata:
  hermes: {category: book, tags: [book, publisher]}
---
# publisher_decision_support

**Girdi şartları:** generation_id; yayıncı değerlendirme kuralları (hafızandaki onaylı kurallar).

**Çağrılacak MCP araçları:** `mcp__book_jobs_mcp__get_report` (özet, temalar, karakterler, açık kalemler) → kural başına `mcp__book_retrieval_mcp__search_book_evidence` → gerekirse `age_group_assessment` ve `universe_canon_analysis` skill'lerinin sonuçları → Critic Agent → `mcp__book_quality_mcp__create_analysis_report(kind="PUBLISHER", sections=[...])`.

**Kullanılacak model:** book-director.

**Çıktı JSON şeması:**
```json
{"recommendation": "YAYINLA|DÜZELTMEYLE_YAYINLA|YAYINLAMA|EDİTÖR_KARARI", "strengths": [{"claim": "str", "source_pages": [0]}],
 "risks": [{"claim": "str", "source_pages": [0], "severity": "düşük|orta|yüksek"}], "open_review_items": 0, "report_id": "uuid"}
```

**Güven eşiği:** açık P1 editör kalemi varsa öneri en fazla EDİTÖR_KARARI.

**Hata durumları:** kural seti yoksa kullanıcıdan iste.

**Editöre gönderme koşulları:** öneri YAYINLAMA ya da EDİTÖR_KARARI.

**Kanıt zorunluluğu:** her güçlü yön ve risk sayfa atıflı; karar editörün ve yayıncının.
