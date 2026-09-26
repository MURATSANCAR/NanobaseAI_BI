<!-- name: production_character_card version: 1 -->
Bir resimli kitap dizisinin karakter kartını hazırlıyorsun. Kart, karakterin dizinin her kitabında aynı çizilmesi için kullanılacak; editör Türkçe okuyup onaylayacak.
Kitap: {{title}} · Okur yaşı: {{age}}
Karakter: {{name}}
Tür (İngilizce): {{species}}
Görsel modele giden sabit görünüş (İngilizce):
<<<
{{look}}
>>>
Kıyafetleri (İngilizce):
<<<
{{outfits}}
>>>
Kitap metninden görünüş alıntıları:
<<<
{{quotes}}
>>>
Kurallar:
- `look_tr`: sabit görünüşün Türkçesi; anlamı birebir aktar, ekleme yapma, atlama yapma.
- `kind`: karakterin türü listeden (insan çocuksa "çocuk", hayvansa "hayvan"; masal varlığı "fantastik").
- `age`: metinden ya da tariften anlaşılan yaş ("7", "yetişkin", "yavru" gibi kısa); anlaşılmıyorsa boş.
- `outfits`: her kıyafet için verilen `name` aynen, `look_tr` Türkçesi, `color` tarifte kıyafetin ana rengi söyleniyorsa o rengin #RRGGBB karşılığı, söylenmiyorsa boş.
- `colors`: YALNIZ tarifte ya da alıntılarda açıkça söylenen renkler, #RRGGBB olarak: `hair` saç, `fur` tüy/post, `eyes` göz, `skin` ten, `outfit` varsayılan kıyafetin ana rengi, `accent` ayırt edici ayrıntı (fular, gözlük, benek…). Söylenmeyen alanı boş bırak; tahmin etme.
