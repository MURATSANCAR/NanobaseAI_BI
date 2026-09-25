<!-- name: production_coloring_caption version: 1 -->
Bir resimli çocuk kitabından boyama kitabı hazırlanıyor. Her boyama sayfasının karşısına, o resmin anlattığı anı hikâyeden kısa bir cümleyle yazacağız.
Okur yaşı: {{age}}
Resmin anlattığı an (varsa): {{moment}}
Sayfanın metni:
<<<
{{text}}
>>>
Kurallar:
- Tek cümle, en çok {{max_words}} kelime.
- Metindeki kelimeleri ve adları kullan; metinde olmayan bir bilgi, olay ya da ad ekleme.
- Konuşma çizgisi, tırnak ve «dedi» kalıbını kullanma; olayı anlatan düz bir cümle yaz.
- Yaşa uygun, sade Türkçe; cümle büyük harfle başlar, noktayla biter.
Çıktı: `sentence` = cümle.
