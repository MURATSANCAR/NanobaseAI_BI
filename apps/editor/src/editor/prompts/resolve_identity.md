<!-- name: resolve_identity version: 1 -->
Bir kitaptaki karakter anmalarını kimliklere birleştir. Aşağıda her anma: id, sayfa, yazıldığı ad, metin mi görsel mi, görünüm, kanıt cümlesi.
<<<
{{mentions}}
>>>
EDİTÖRÜN KİMLİK DÜZELTMELERİ (bağlayıcı):
{{corrections}}

Kurallar:
- Aynı kişiye ait anmaları tek karakterde topla; `mention_ids` listele. Farklı adlar (lakap, unvan: "dedesi", "Profesör Bulut") aynı kişiyse `aliases` içine yaz ve `merge_basis` alanında hangi kanıta dayandığını söyle.
- Adı olmayan görsel figürü bir karaktere ancak açık kanıtla bağla; yoksa `unresolved_mention_ids` içinde bırak.
- `identity_confidence`: 0.85 ve üstü yalnız birden fazla bağımsız kanıt varsa. Tek kanıta dayanan birleştirme en fazla 0.7.
- Tek bir anmanın iki karaktere birden bağlandığı durumları `conflicts` içine yaz.
- Türkçe yaz.
