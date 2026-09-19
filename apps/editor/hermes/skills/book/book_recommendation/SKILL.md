---
name: book_recommendation
description: Okuyucunun isteğine (konu, tema, yaş, karakter, durum) uyan kitapları katalogdan, doğrulanmış tema ve olaylara dayanarak sayfa atıflı önerir.
version: 1.0.0
metadata:
  hermes: {category: book, tags: [book, catalog, recommendation]}
---
# book_recommendation

**Girdi şartları:** serbest metin istek ("çocukların tabletle ilişkisi hakkında kitap öner"); isteğe bağlı yaş. Katalogda en az bir kitap kartı olmalı (kart, tamamlanan her analizin sonunda kendiliğinden kurulur).

**Çağrılacak MCP araçları:** `mcp__book_retrieval_mcp__search_books(query, k, age)` → ayrıntı gerekiyorsa `mcp__book_retrieval_mcp__get_book_card(book_id)` → bir kitabın içinden örnek pasaj istenirse `mcp__book_retrieval_mcp__search_book_evidence` (kartın `generation_id`'si ile). İstek birden çok ayrı konu içeriyorsa her konu için ayrı `search_books` çağrısı yap (bağımsızsa `delegate_task` ile paralel).

**Kullanılacak model:** book-embedding + book-reranker (araç içinde); öneri metnini sen (book-director) yazarsın.

**Çıktı JSON şeması:**
```json
{"request": "str", "recommendations": [{"book_id": "uuid", "title": "str", "authors": ["str"], "age_range": ["str"],
  "cover": {"url": "str", "source": "UPLOADED|PDF_PAGE"}, "match_score": 0.0,
  "reasons": [{"text": "str", "source_pages": [0]}]}], "not_found": "str"}
```

**Güven eşiği:** `match_score` < 0.3 olan kitabı önerme; hepsi altındaysa "katalogda bu isteğe uyan kitap bulunamadı" de ve en yakın olanı "uzak eşleşme" diye ayrı belirt.

**Hata durumları:** katalog boş → söyle, önce kitap analizi öner. Yaş filtresi sonuç bırakmıyorsa filtresiz sonucu yaş uyarısıyla ver.

**Editöre gönderme koşulları:** yok (kart yalnız Critic'in doğruladığı ya da editörün onayladığı iddialardan kurulur).

**Kanıt zorunluluğu:** her öneri gerekçesi aracın döndürdüğü `why` kayıtlarından gelir ve [s.N] atıfı taşır. Kitap hakkında kartta ve defterde olmayan bir şey söyleme; kendi genel bilginle kitap önerme. Kapak görselini cevaba `cover.url` ile ekle.
