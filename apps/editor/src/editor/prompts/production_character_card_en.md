<!-- name: production_character_card_en version: 1 -->
Bir resimli kitap dizisinin editörü bir karakterin görünüşünü Türkçe yazdı. Görsel model yalnız İngilizceyi güvenilir anlıyor; tarifi İngilizceye çevir.
Karakter (adı olduğu gibi kalır, çevrilmez): {{name}}
Sabit görünüş:
<<<
{{look}}
>>>
Kıyafetler (sırayla):
<<<
{{outfits}}
>>>
Kurallar:
- Anlamı birebir aktar; editörün yazmadığı hiçbir şeyi ekleme, hiçbir şeyi atlama.
- Renk, hayvan, eşya adlarını tam İngilizce karşılığıyla yaz; genel bir kelimeye kaçma.
- Görsel modele verilecek kısa, açık tarif cümleleri olsun (en çok 60 kelime).
Çıktı: `look_en` = sabit görünüşün çevirisi; `outfits` = kıyafet tariflerinin çevirileri, aynı sırayla (kıyafet yoksa boş liste).
