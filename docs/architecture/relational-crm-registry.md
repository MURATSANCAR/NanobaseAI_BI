# CRM ilişkisel kaynak kayıt defteri

`backend/semantic_bridge/finance_query/relational_contracts.py`, soru metni veya
kabul sorusu kimliği içermeyen kaynak sözlüğüdür. İlk kapsam 15 fiziksel varlık,
108 mantıksal alan ve 19 yönlü ilişkidir. Rapor seçmek yerine sorgu planı bu
varlık, alan ve ilişki kimliklerini kullanır. Bu sözlük tek başına SQL çalıştırmaz.

Kanıt, 30 Eylül 2026 tarihli `crm-coverage/inventory-source.json` fiziksel kolon,
PK, FK ve durum etiketi kayıtları ile mevcut `crm_reports.py` alan anlamlarıdır.
Envanter SHA-256:
`ee26a27cc48bd6fa7d5d631453d4a75025c61517705e2602ea0927e341fe9a8e`.
Kaynak yolu ve kapsam sınırları `SCHEMA_PROVENANCE` içinde korunur. Eski SQL
kataloğu kullanılmadı; yeni DB/API sorgusu yapılmadı. Fiziksel kolon adlarının
büyük/küçük harfi envanterden alınır; eşsiz olmayan ad eşleşmesi kabul edilmez.

Her varlığın tek fiziksel PK'sı, alan türleri, NULL bilgisi ve güvenilir aktiflik
koşulu vardır. Kitap, Contact ve marka için yayımlı aktif durum kodu 1, diğer
durumlu varlıklarda statecode=0 kullanılır. Account genel aktif kurumdur; müşteri
durum koduna göre seçilmiş müşteri kümesi değildir. İş varlığı statecode=0 ile
başlar; açık iş, iptal ve tamamlanma koşulları ayrıca açık filtrelenmelidir.
Ara tabloların durum alanı yoktur; bağlı uçların aktifliği ayrıca uygulanır.

İzinli JOIN yönü çocuk FK → tekil hedef PK'dır (`many_to_one`). Üst sınırı PK
kanıtlar; her aktif hedefin mevcut olduğu veya ilişkinin iş bakımından tam
olduğu sonucu çıkmaz. LEFT JOIN hedef aktifliği ON/alt sorguda uygulanmalı,
WHERE ile kök satırlar sessizce düşürülmemelidir. Ters yönde çoğalma ilk derleyici
kapsamında yasaktır. Kitap–sözleşme ve kitap–proje N:N bağları fiziksel ara kayıt
kimlikleriyle ayrı varlıklardır. Birden fazla lookup yolunu eşdeğer sayıp OR JOIN
üretmek yasaktır.

Hiçbir sayısal alan için toplamsallık kanıtlanmadığından `sum_allowed=False`.
Baskı sayısı, durum kodu ve kimlikleri toplamak anlamlı iş ölçüsü sayılmaz.
Alan türü, tek başına bir hesabın iş tanımını doğrulamaz. CreatedOn/ModifiedOn
değişiklik geçmişi veya aşamaya giriş tarihi değildir. Sözleşme ana kimlik metni,
ülke–bölge yorumları, hukuki öncelik, ad benzerliğinden kimlik ve marka hiyerarşisi
kanıtlanmamış bağlantılar olarak dışarıda tutulur.

Önceki **31 tablo / 161 alan** manifesti `crm_reports.py` raporlarının kapsamıdır;
bu kayıt defterinin 15/108 sayısıyla aynı ölçüm değildir. Ara tablo PK'ları ve
aktiflik kolonları yeni sözlükte açık alan olarak yer alır. Yeni sözlüğün
çalışma anında şema kontrolü ve bağlı gerçek DB/API üzerinden bağımsız kabulü
henüz yapılmadı: **DOĞRULANAMADI**. Metadata varlığı, bütün CRM sorularının
yanıtlandığını veya yeni AST'nin üretime hazır olduğunu göstermez.
