<!-- name: production_profile version: 1 -->
Aşağıda basıma hazırlanacak bir kitabın metni var. Kitabı bir yayınevinin yayın kurulu gibi değerlendir.
Kitap adı: {{title}}
<<<
{{text}}
>>>
Metne bakarak şunları belirle:
- `age_min`, `age_max`: kitabın hitap ettiği okur yaşı (metnin dili, cümle uzunluğu, konu ve duygusal ağırlığa göre).
- `genre`: RESIMLI_OYKU (resimle birlikte okunan kısa çocuk öyküsü), ILK_OKUMA (bölümlü, kısa cümleli ilk okuma kitabı), COCUK_ROMANI, GENCLIK_ROMANI, YETISKIN_ROMANI, OYKU_KITABI, SIIR, KURGU_DISI_COCUK, KURGU_DISI.
- `illustration`: HER_SAYFA (her sayfada resim), BOLUM_BASI (yalnız bölüm başlarında), YOK.
- `tone`: kitabın havasını anlatan en çok 5 kısa sıfat (Türkçe).
- `reasons`: her kararın gerekçesi; her gerekçeye metinden KELİMESİ KELİMESİNE bir `quote` ekle.
Metinde olmayan bir şeyi gerekçe olarak yazma.
