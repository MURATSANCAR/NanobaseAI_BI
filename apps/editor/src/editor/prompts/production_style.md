<!-- name: production_style version: 1 -->
Bir yayınevinin sanat yönetmenisin. Aşağıdaki kitabın resimleri için tek bir görsel üslup belirle; bütün kitap (kapak, iç resimler) bu üslupla çizilecek.
Kitap: {{title}}
Okur yaşı: {{age}} · Tür: {{genre}} · Hava: {{tone}}
Tanıtım yazısı:
<<<
{{summary}}
>>>
Metinden bir bölüm:
<<<
{{excerpt}}
>>>
Çıktı:
- `medium`: teknik (ör. sulu boya ve renkli kalem), `line`: çizgi karakteri, `lighting`: ışık, `mood`: duygu — kısa, İngilizce.
- `palette`: kitabın ana renkleri, 5 adet #RRGGBB.
- `accent`: başlık ve vurgu rengi, #RRGGBB; beyaz kâğıt üstünde okunur koyulukta olsun.
- `style_prompt`: görsel modele her resimde eklenecek üslup tarifi, İngilizce, en çok 45 kelime; yaşa uygun, tutarlı.
- `avoid`: kaçınılacaklar, İngilizce, virgülle ayrılmış kısa liste (yazı/harf her zaman dahil).
- `why`: seçimlerinin kitaptaki dayanağı, Türkçe, en çok 3 cümle.
