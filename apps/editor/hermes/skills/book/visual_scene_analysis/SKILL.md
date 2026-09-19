---
name: visual_scene_analysis
description: Bir sayfanın ya da sahnenin görsel analizi; zor sayfalarda derin modeli kullanır.
version: 1.0.0
metadata:
  hermes: {category: book, tags: [book, vision]}
---
# visual_scene_analysis

**Girdi şartları:** generation_id, sayfa numarası.

**Çağrılacak MCP araçları:** önce `mcp__book_document_mcp__get_page_bundle` (tarama zaten var mı). Yoksa `mcp__book_vision_mcp__analyze_page_visual(depth="fast")`. Kimlik belirsiz, metin-görsel çelişkili ya da olay önemliyse `depth="deep"`. Ayrıntı: `detect_scene`, `detect_characters`, `detect_objects`, `check_text_visual_consistency`. Birden çok sayfa bağımsızsa `delegate_task` ile paralel.

**Kullanılacak model:** book-vision-fast; yalnız belirsizlikte book-vision-deep.

**Çıktı JSON şeması:**
```json
{"page": 0, "pass": "FAST|DEEP", "scene": {"setting": "str", "time_of_day": "str", "mood": "str", "description": "str"},
 "characters": [{"name": "str", "identity_uncertain": true, "action": "str"}], "objects": ["str"],
 "text_visual_candidates": [{"text_quote": "str", "visual_observation": "str", "note": "str"}]}
```

**Güven eşiği:** figür güveni < 0.6 ise ad verme.

**Hata durumları:** gpu_busy → kullanıcıya bildir; derin model yoksa hızlı sonucu "doğrulanmadı" diye ver.

**Editöre gönderme koşulları:** metin-görsel aday bulgu güveni ≥ 0.6 ise `send_to_editor_queue` (contradiction_id ile).

**Kanıt zorunluluğu:** görsel iddia görsel bölge kaydına bağlıdır; uyuşmazlık aday bulgudur, hata değil.
