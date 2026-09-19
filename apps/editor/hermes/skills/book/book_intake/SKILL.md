---
name: book_intake
description: Yeni bir kitap PDF'ini deftere alır; içerik sürümünü (sha256) oluşturur, sayfa manifestini çıkarır.
version: 1.0.0
metadata:
  hermes: {category: book, tags: [book, intake]}
---
# book_intake

**Girdi şartları:** inbox'ta bir PDF adı (`mcp__book_document_mcp__list_inbox` ile görülür). İsteğe bağlı: başlık, evren (seri), hedef yaş grubu.

**Çağrılacak MCP araçları:** `mcp__book_document_mcp__list_inbox` → `mcp__book_document_mcp__inspect_book` → `mcp__book_document_mcp__create_page_manifest`.

**Kullanılacak model:** yok (deterministik PDF işleme).

**Çıktı JSON şeması:**
```json
{"book_id": "uuid", "book_version_id": "uuid", "title": "str", "sha256": "str",
 "page_count": 0, "new_version": true, "needs_ocr": [0], "no_text_layer": [0]}
```

**Güven eşiği:** uygulanmaz.

**Hata durumları:** dosya inbox'ta değil ya da PDF değil → kullanıcıya dosya adlarını listele; aynı sha256 zaten varsa `new_version=false` döner, yeni sürüm açılmaz.

**Editöre gönderme koşulları:** yok.

**Kanıt zorunluluğu:** bu skill iddia üretmez; yalnız sürüm ve sayfa kaydı açar.
