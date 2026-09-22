<!-- name: attribute_text version: 1 -->
Aşağıda resimli bir çocuk kitabının METNİ var. Her paragraf [sSAYFA pPARAGRAF] ile başlar. Künye, yazar/çizer tanıtımı ve arka kapak yazıları da metnin içinde olabilir; bunlar hikâye değildir.

Kitabın karakterleri (adı ve diğer anılış biçimleri):
{{characters}}

Görevin: metnin bir karakterin GÖRÜNÜŞÜ hakkında AÇIKÇA söylediklerini çıkarmak. Her bilgi için:
- `subject`: bilginin kime ait olduğu, yukarıdaki listedeki adıyla (listede olmayan kişi için yazma);
- `kind`: özellik türü, `value`: o türün kapalı kümesinden değer;
- `page`, `paragraph`, `quote`: bilginin geçtiği paragraf ve METİNDEN KELİMESİ KELİMESİNE alıntı.

Özellik türleri ve izin verilen değerler:
{{vocabulary}}

Kurallar:
- Yalnız metnin söylediğini yaz: "kırmızı tişörtlü Ali", "gözlüğünü taktı", "sarı saçları" gibi. Çizimden, addan ya da genel bilgiden tahmin yapma.
- Rüya, hayal, oyun, kılık değiştirme, başkasının kıyafeti ve varsayım içindeki bilgileri alma.
- Renk tam uymuyorsa en yakın değeri, hiç uymuyorsa DIGER yaz. Metin "yok" diyorsa (şapkasız, gözlüksüz, saçsız) YOK.
- Aynı özellik iki sayfada söyleniyorsa iki ayrı kayıt yaz. Bilgi yoksa boş liste döndür; bulmak zorunda değilsin.
- Alıntı uydurma: `quote` metinde birebir olmalı.

METİN:
{{text}}
