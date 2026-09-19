<!-- name: resolve_identity version: 2 -->
Bir kitabın METNİNDE geçen karakter anmalarını kimliklere birleştir. Aşağıda her anma: id, sayfa, metinde yazıldığı ad, kanıt cümlesi.
<<<
{{mentions}}
>>>
EDİTÖRÜN KİMLİK DÜZELTMELERİ (bağlayıcı):
{{corrections}}

Kurallar:
- Aynı kişiye ait anmaları tek karakterde topla; `mention_ids` listele. Farklı adlar (lakap, unvan, akrabalık adı: "dedesi", "Profesör Bulut") aynı kişiyse aynı karakterde topla ve `merge_basis` alanında hangi cümleye dayandığını söyle. Kanıtı olmayan birleştirme yapma: iki ad aynı kişi olabilir ama metin söylemiyorsa ayrı bırak.
- `canonical_name`: o karakterin anmalarında GEÇEN adlardan en tam olanı. Listede olmayan bir ad uydurma. `aliases` alanını boş bırak; diğer adları sistem anmalardan kendisi çıkarır.
- `description`: karakterin kim olduğu ve hikâyedeki rolü, YALNIZ metindeki kanıtlara göre. Saç, kıyafet, renk gibi görünüm bilgisi YAZMA; görünüm çizimlerden ayrıca çıkarılır.
- `identity_confidence`: 0.85 ve üstü yalnız birden fazla bağımsız kanıt varsa. Tek kanıta dayanan birleştirme en fazla 0.7.
- Bir anmanın iki karaktere birden uyabildiği durumları `conflicts` içine yaz; tahminle çözme.
- Türkçe yaz.
