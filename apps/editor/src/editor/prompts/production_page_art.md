<!-- name: production_page_art version: 1 -->
Bir resimli kitabın sayfa resmini tarif ediyorsun. Resim sayfanın {{placement}} yer alacak; yazı resmin içine girmeyecek.
Kitap: {{title}} · Okur yaşı: {{age}}
Karakterler (adı: görünüşü):
<<<
{{characters}}
>>>
Önceki sayfanın metni:
<<<
{{before}}
>>>
BU SAYFANIN METNİ (resim bunu anlatacak):
<<<
{{page_text}}
>>>
Sonraki sayfanın metni:
<<<
{{after}}
>>>
Çıktı:
- `moment`: bu sayfada resmedilecek tek an, Türkçe, tek cümle; bu sayfanın metninde geçmeli.
- `quote`: bu anı anlatan cümle, bu sayfanın metninden KELİMESİ KELİMESİNE.
- `characters`: resimde görünen karakterlerin adları (yalnız yukarıdaki listeden).
- `scene`: görsel model için sahne tarifi, İngilizce, en çok 70 kelime: kim, ne yapıyor, nerede, ifadeler, ışık, kompozisyon. Karakterlerin görünüşünü tekrar yazma, adlarını kullan. Metinde olmayan olay ekleme.
- `setting`: mekân, İngilizce, kısa.
