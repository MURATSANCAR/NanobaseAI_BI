<!-- name: match_figures version: 2 -->
İlk görüntüler REFERANS'tır: her biri kitabın bir karakterinin, kim olduğu metinle kesinleşmiş bir sayfadan kırpılmış çizimidir ({{references}}). SON görüntü, aynı kitabın {{page_no}}. sayfasından kırpılmış bir FİGÜR'dür.

Soru: FİGÜR, referanslardan biriyle AYNI karakter mi?
- Önce türe bak: insan, hayvan, robot/makine, düşsel yaratık. Tür farklıysa aynı karakter OLAMAZ; renk benzerliği (ör. ikisinde de kırmızı bir şey olması) eşleşme değildir.
- Aynı türdeyse ayırt edici özellikleri karşılaştır: saç rengi ve biçimi, aksesuar, yüz, beden yapısı, kıyafet (kıyafet sahneden sahneye değişebilir; saç ve aksesuar daha güvenilirdir).
- `matching_features` ve `conflicting_features` alanlarını doldur. Çelişen ayırt edici bir özellik varsa (farklı saç rengi, farklı tür) `reference` = NONE.
- Emin değilsen NONE de; zorla eşleştirme. `confidence`: 0.9 ve üstü yalnız birden çok ayırt edici özellik açıkça örtüşüyorsa.
Türkçe yaz.
