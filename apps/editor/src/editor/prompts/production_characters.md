<!-- name: production_characters version: 2 -->
Bir resimli kitabın karakter tasarımcısısın. Aşağıdaki kitapta birden fazla sahnede görünen karakterlerin görünüşünü tasarla; her resimde aynı çizilecekler.
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
Görünüşü ikiye ayır:
- SABİT görünüş (`base_look`): hiç değişmeyen beden: tür, boy/oran, tüy/ten ve göz rengi, yüz. Giysi ve takılan eşya BURAYA YAZILMAZ.
- KIYAFETLER (`outfits`): karakterin metin boyunca giydiği/taktığı şeyler. Her kıyafet ayrı kayıttır; metin karakterin bir şeyi giydiğini ya da taktığını söylüyorsa (ör. "önlüğünü giydi, gözlüğünü taktı") o ayrı bir kıyafettir ve `from_text`'e o cümle KELİMESİ KELİMESİNE yazılır. Metinde giysi geçmiyorsa sade, tutarlı bir gündelik kıyafet seç (from_text boş).
Her karakter için:
- `name`: metinde geçtiği adıyla.
- `species`: tür (İngilizce, ör. "baby wombat").
- `base_look`: İngilizce, en çok 40 kelime.
- `outfits`: en az bir kayıt; her kayıtta `name` (kısa Türkçe ad, ör. "gündelik", "deney"), `look` (İngilizce, en çok 30 kelime), `from_text` (alıntılar).
- `default_outfit`: karakterin hikâyenin çoğunda giydiği kıyafetin `name`'i (genellikle gündelik olan).
- `from_text`: `base_look` içindeki, metinden gelen beden ayrıntılarının alıntıları.
- `role`: ANA (neredeyse her sahnede), YAN (birkaç sahnede).
Yalnız metinde gerçekten geçen karakterleri yaz; yazar, çizer gibi kitap dışı kişileri yazma. En çok 8 karakter.
