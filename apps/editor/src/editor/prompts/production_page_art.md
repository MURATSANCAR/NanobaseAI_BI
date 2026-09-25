<!-- name: production_page_art version: 3 -->
Bir resimli kitabın sayfa resmini tarif ediyorsun. Resim sayfanın {{placement}} yer alacak; yazı resmin içine girmeyecek.
Kitap: {{title}} · Okur yaşı: {{age}}
Bu sayfanın resmine girebilecek karakterler (adı: sabit görünüşü; kıyafetleri). Listede olmayan hiçbir karakteri resme koyma:
<<<
{{characters}}
>>>
Önceki sayfanın metni:
<<<
{{before}}
>>>
Önceki sayfanın resmi: mekân = {{prev_setting}}; kıyafetler = {{prev_outfits}}
BU SAYFANIN METNİ (resim bunu anlatacak):
<<<
{{page_text}}
>>>
Sonraki sayfanın metni:
<<<
{{after}}
>>>
Kurallar:
- MEKÂN SÜREKLİLİĞİ: Metin mekânın değiştiğini açıkça söylemedikçe (bir yere gitti, dışarı çıktı, eve vardı…) mekân önceki sayfanınkiyle aynıdır.
- KIYAFET SÜREKLİLİĞİ: Bir karakter metinde bir kıyafeti giydiğinde o kıyafetle devam eder; metin çıkardığını söyleyene ya da yeni bir güne geçilene kadar değişmez. Yeni bir günde (ertesi sabah, günler sonra…) önceki günün kıyafeti sürmez: bu sayfanın metni bir kıyafet söylemiyorsa varsayılan kıyafettir. Metin henüz giydirmediyse varsayılan kıyafettir.
Çıktı:
- `moment`: bu sayfada resmedilecek tek an, Türkçe, tek cümle; bu sayfanın metninde geçmeli.
- `quote`: bu anı anlatan cümle, bu sayfanın metninden KELİMESİ KELİMESİNE.
- `characters`: resimde görünen karakterlerin adları (yalnız yukarıdaki listeden; metnin bu anında orada olmayanı koyma).
- `outfits`: resimdeki her karakter için `character` ve giydiği kıyafetin `outfit` adı (yalnız o karakterin kıyafet listesinden).
- `new_day`: bu sayfanın metni önceki sayfaya göre yeni bir güne geçiyorsa (ertesi sabah, o gece değil ertesi gün, günler sonra…) true, yoksa false.
- `time_quote`: `new_day` true ise bunu söyleyen cümle, bu sayfanın metninden KELİMESİ KELİMESİNE; false ise boş.
- `setting`: mekân, İngilizce, kısa; kurallara göre.
- `setting_reason`: mekânın neden bu olduğu, Türkçe, tek cümle (önceki sayfadan sürüyor / metin şurada değiştirdi).
- `scene`: görsel model için sahne tarifi, İngilizce, en çok 70 kelime: kim, ne yapıyor, ifadeler, ışık, kompozisyon. Karakterlerin görünüşünü ve kıyafetini tekrar yazma, adlarını kullan. Metinde olmayan olay ve listede olmayan karakter ekleme.
