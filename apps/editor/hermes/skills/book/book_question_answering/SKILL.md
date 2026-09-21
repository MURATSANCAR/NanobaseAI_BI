---
name: book_question_answering
description: Kitap hakkındaki bir soruyu yalnız defterdeki kanıtlarla, sayfa atıflı cevaplar.
version: 2.0.0
metadata:
  hermes: {category: book, tags: [book, qa]}
---
# book_question_answering

**Girdi şartları:** en yeni neslin güncel kullanılabilir çıktıları (`generation_id`: `list_books` ya da `latest_generation`). Soru.

**Çağrılacak MCP araçları:** `mcp__book_retrieval_mcp__search_book_evidence` (k=8; gerekirse soruyu 2-3 alt soruya bölüp her biri için ayrı çağrı, alt sorular birbirinden bağımsızsa `delegate_task` ile paralel) → karakter sorularında `mcp__book_retrieval_mcp__search_character_history` → cevap taslağı → `mcp__book_quality_mcp__validate_claim` (her cümle için).

**Kullanılacak model:** book-embedding + book-reranker (araç içinde), cevabı sen (book-director) yazarsın.

**Çıktı JSON şeması:**
```json
{"answer": "str", "claims": [{"claim": "str", "source_pages": [0], "evidence": [{"page": 0, "paragraph": 0, "quote": "str"}],
 "confidence": 0.0, "status": "CANDIDATE", "needs_editor_review": false}], "not_found": ["str"]}
```

**Güven eşiği:** rerank_score < 0.3 olan pasaja dayanarak kesin cümle kurma. validate_claim geçmeyen cümleyi cevaptan çıkar.

**Hata durumları:** indeks/çıktı hazır değilse “Güncel analiz çıktısı henüz hazır değil” de; bunu “kitapta kanıt yok” ile karıştırma. Eski nesle geri dönme. `latest_generation.job_id` ile gerçek iş durumunu oku; çalışan işi yeniden başlatmayı önerme. Güncel arama başarıyla çalışıp kanıt bulunamazsa "Defterde bu soruya kanıt yok" de; tahmin etme. Nesil yoksa önce `book_full_analysis` öner.

**Editöre gönderme koşulları:** soru defterdeki iki kaydın çeliştiğini gösteriyorsa `send_to_editor_queue`.

**Kanıt zorunluluğu:** her cümle [s.N] atıfı taşır; alıntı sayfa metninden birebir.

`semantic_acceptance=false` ise cevabı tam kitap analizi gibi sunma; kaynaklı kısmi yanıt olduğunu belirt. Mühürlenme analitik kabul değildir.
