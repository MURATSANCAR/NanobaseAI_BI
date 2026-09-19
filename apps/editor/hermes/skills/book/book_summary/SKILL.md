---
name: book_summary
description: Kitabın ya da bir bölümün özetini defterdeki doğrulanmış SUMMARY iddialarından verir.
version: 1.0.0
metadata:
  hermes: {category: book, tags: [book, summary]}
---
# book_summary

**Girdi şartları:** mühürlenmiş nesil (iş akışı adım 12'de özetleri üretmiştir).

**Çağrılacak MCP araçları:** `mcp__book_jobs_mcp__get_report` (Kitap özeti ve Bölümler kısmı). Bölüme özel ek soru için `mcp__book_retrieval_mcp__search_book_evidence`.

**Kullanılacak model:** book-director (iş akışında üretildi); burada yeniden üretim yok.

**Çıktı JSON şeması:**
```json
{"level": "book|chapter", "title": "str", "sentences": [{"text": "str", "source_pages": [0], "status": "VERIFIED|CANDIDATE"}]}
```

**Güven eşiği:** VERIFIED olmayan cümleleri "doğrulanmadı" etiketiyle ver ya da çıkar.

**Hata durumları:** özet yoksa (nesil yarım) iş durumunu `get_job_status` ile göster.

**Editöre gönderme koşulları:** yok (özetler Critic'ten geçmiştir).

**Kanıt zorunluluğu:** özetteki her cümle kendi sayfa atıfını korur.
