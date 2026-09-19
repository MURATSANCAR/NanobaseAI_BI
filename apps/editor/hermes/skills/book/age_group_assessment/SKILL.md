---
name: age_group_assessment
description: Kitabın hedef yaş grubuna uygunluğunu yayıncı rubriğine göre, kanıtla değerlendirir.
version: 1.0.0
metadata:
  hermes: {category: book, tags: [book, age, publisher]}
---
# age_group_assessment

**Girdi şartları:** generation_id; hedef yaş grubu; yaş grubu rubriği (hafızandaki onaylı rubrik; yoksa kullanıcıdan iste ve onaylanınca hafızaya yaz).

**Çağrılacak MCP araçları:** rubriğin her ölçütü için `mcp__book_retrieval_mcp__search_book_evidence` (ölçütler bağımsızsa `delegate_task` ile paralel) + `search_character_history` (duygu yoğunluğu) → bölümleri Critic Agent'a denetlet → `mcp__book_quality_mcp__create_analysis_report(kind="AGE_GROUP", sections=[...])`.

**Kullanılacak model:** book-director.

**Çıktı JSON şeması:**
```json
{"target_age": "str", "verdict": "UYGUN|KOŞULLU|UYGUN_DEĞİL|BELİRSİZ",
 "criteria": [{"criterion": "str", "finding": "str", "claims": [{"claim": "str", "evidence": [{"page": 0, "paragraph": 0, "quote": "str"}], "confidence": 0.0, "needs_editor_review": false}]}],
 "report_id": "uuid"}
```

**Güven eşiği:** bir ölçütün bulgusu güven < 0.6 ise verdict BELİRSİZ ya da KOŞULLU.

**Hata durumları:** kanıtı doğrulanamayan iddia create_analysis_report'ta reddedilir; o iddiayı çıkar, uydurma.

**Editöre gönderme koşulları:** verdict UYGUN_DEĞİL ya da BELİRSİZ ise; hassas içerik (şiddet, korku yoğunluğu ≥ 0.8) her zaman.

**Kanıt zorunluluğu:** her bulgu sayfa alıntısıyla.
