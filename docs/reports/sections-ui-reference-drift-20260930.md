# Bölüm/CSV kabulünde canlı kaynak değişimi

`sections_ui.py` önceki ve sonraki bağımsız referans farklıysa, yalnız tam cevap
karşılaştırmasının satır/kimlik/sayısal/NULL/değer farklarını `UNVERIFIED` sayar.
Ortak `composable_live.data_dependent_error` sınıflandırıcısı kullanılır; bölüm
önekleri de aynı politikaya tabidir. Referans sabitse herhangi bir fark `FAIL`
olmaya devam eder.

CSV, aynı yürütmenin saklanan tam sonucuyla karşılaştırıldığı için CSV satır,
kolon, sayı ve metin hataları kaynak değişiminden bağımsız olarak `FAIL` kalır.
Yapı, teslim edilen sonuç, tarayıcı kabul işleminin başarısız çıkışı veya yayın
kodu değişimi de veri hareketiyle gizlenmez. Sonraki referans okunamazsa daha önce
bulunmuş yapısal hatalar korunur; yalnız sayısal farklar kesin başarısızlık diye
sunulmaz. Yeterli gerçek satır olmayıp sayfalama sınanamaması `UNVERIFIED` kalır.

Rapor `referenceChanged` ve gerekirse `structuralErrorsDespiteSourceChange`
alanlarıyla kararı açıklar. Bu değişiklik için yerel test, yeni DB/API koşusu veya
dağıtım yapılmadı; devam eden kabul koşusunun kopyası değiştirilmedi.
