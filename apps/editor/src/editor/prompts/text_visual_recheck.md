<!-- name: text_visual_recheck version: 1 -->
Görüntü bir kitabın {{page_no}}. sayfası. Tek işin: sayfadaki çizimin, sayfanın metniyle ÇELİŞEN bir şey gösterip göstermediğine bakmak.
Sayfanın metni (paragraf numaralarıyla):
<<<
{{page_text}}
>>>
- Metnin, çizimde denetlenebilecek her somut ifadesini (renk, sayı, nesne, eylem, kişi, yer, nesnenin durumu) tek tek ele al ve çizimle karşılaştır.
- `relation`: CONTRADICTS yalnız çizim metinle ÇELİŞEN bir şeyi AÇIKÇA GÖSTERİYORSA. Metnin söylediği şeyin çizimde hiç görünmemesi çelişki değildir (çizim her şeyi göstermez): ABSENT_IN_IMAGE. Uyumluysa CONSISTENT.
- Çizim üslubu, perspektif, sahnenin bir an öncesini/sonrasını göstermesi çelişki değildir.
- `text_quote` metinden birebir alıntıdır; `visual_observation` yalnız gördüğündür.
- Sayfada çizim yoksa boş liste ver. Türkçe yaz.
