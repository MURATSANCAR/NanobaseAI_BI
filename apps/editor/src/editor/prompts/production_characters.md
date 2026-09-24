<!-- name: production_characters version: 1 -->
Bir resimli kitabın karakter tasarımcısısın. Aşağıdaki kitapta birden fazla sahnede görünen karakterlerin sabit görünüşünü tasarla; her resimde aynı çizilecekler.
Kitap: {{title}} · Okur yaşı: {{age}}
Üslup: {{style}}
Kitabın analizinde bulunan karakterler:
<<<
{{characters}}
>>>
Kitap metni:
<<<
{{text}}
>>>
Her karakter için:
- `name`: metinde geçtiği adıyla.
- `species`: tür (İngilizce, ör. "baby wombat", "lion cub").
- `look`: görsel modele verilecek sabit görünüş tarifi, İngilizce, en çok 50 kelime: boy/oran, renkler, giysi ve eşyalar. Metinde yazan her görünüş ayrıntısı (giysi, eşya, beden) mutlaka yer alsın; metinde yazmayan ayrıntıyı sade ve tutarlı seç, metinle çelişme.
- `from_text`: `look` içinde metinden gelen ayrıntıların kitaptaki KELİMESİ KELİMESİNE alıntıları (Türkçe). Metinde hiç görünüş ayrıntısı yoksa boş liste.
- `role`: ANA (neredeyse her sahnede), YAN (birkaç sahnede).
Yalnız metinde gerçekten geçen karakterleri yaz. Yazar, çizer gibi kitap dışı kişileri yazma. En çok 8 karakter.
