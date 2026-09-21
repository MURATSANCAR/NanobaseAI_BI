<!-- name: cluster_name version: 2 -->
Aşağıdaki görüntüler aynı kitabın farklı sayfalarından kırpıldı (sayfalar: {{pages}}). Bir benzerlik ölçüsü bunların aynı karakteri gösterdiğini söylüyor; bunu önce sen doğrulayacaksın.

Sırayla karar ver:
1. `is_character`: bu kırpımlar çizilmiş bir KARAKTERİ (insan, hayvan, robot, düşsel yaratık) gösteriyor mu? Nesne, manzara, desen, yazı, sayfa süsü, boş alan ya da tanınmayacak bir parça ise false.
2. `same_character`: kırpımların hepsi AYNI karakteri mi gösteriyor? Biri bile başka biriyse false.
3. `name`: (yalnız ikisi de true ise) bu karakter, kitabın metninden çıkarılmış şu kişilerden hangisi:
<<<
{{candidates}}
>>>
Bu kırpımların alındığı sayfaların metni:
<<<
{{pages_text}}
>>>
İsim seçerken:
- Yalnız çizimde GÖRÜNENE ve sayfa metninin söylediğine dayan. Adayların açıklaması (yaş, cinsiyet, tür, akrabalık) ile çizim uyuşmalıdır.
- Seçtiğin ad kırpımların hepsine birden uymalıdır.
- Hiçbiri uymuyorsa ya da hangisi olduğunu ayırt edemiyorsan `name` alanına NONE yaz. Tahmin etme.
- `reason`: hangi görünür özelliğin ve hangi cümlenin bu kararı verdirdiği, tek cümle.
Türkçe yaz.
