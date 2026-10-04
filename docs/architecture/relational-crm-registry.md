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

Katılım kökünden kitap, kişi ve katılım rolüne; kitap üzerinden yayıncı, alt
marka, alternatif alt marka ve kitap projesine ilerleyen yol mevcut kayıtta
tanımlıdır. Yedi ileri FK bağlantısı sekiz SQL tablo takma adı oluşturur;
marka tablosu iki farklı lookup rolüyle kullanıldığı için fiziksel tablo sayısı
yedidir. `book.book_project_id` fiziksel `new_KitapProjesi` alanıdır ve
`new_new_proje_new_kitap_KitapProjesi` FK'sıyla `new_projeBase.new_projeId`
anahtarına gider. Bu yol ters JOIN gerektirmez; sonuç tanesi katılım kaydı
olmaya devam eder. LEFT/INNER tercihi nüfusu belirler; NULL proje veya diğer
aktif hedeflerin bulunmaması, açık seçim olmadan kök kayıtları düşürmemelidir.

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

## CRM süreç kayıtları (2026-10-04)

`relational_process.py` (üretici `scripts/crm-process/build_process_registry.py`, sunucuda CRM .28 okunarak) kayıt
defterine 24 varlık, 211 alan ve 31 ilişki ekler: sipariş (`crm_order`), sipariş satırı (`crm_order_line`), bekleyen ürün
(`pending_item`), satış hedefi (`sales_target`), etkinlik (`crm_activity`), ziyaret yeri (`visit_place`), kitap yaş/sınıf/
kategori/anahtar kelime bağları ve bunların hedef tabloları (il, ilçe, etkinlik tipi, CRM kullanıcısı, ürün…). Alan adları ve
kod etiketleri CRM metadata'sından (Türkçe), ilişkiler fiziksel FK → tekil PK; aktif satırda doluluk ≥ %5 olan alan alınır,
kişisel veri adı taşıyan alan (telefon, adres, e-posta, kimlik) alınmaz. Her PK tekil, her FK hedefte %100 bulundu
(`MEASUREMENTS`). Durum alanı (statecode) modele verilmez: aktif kayıt koşulu otomatik.

Kurallar:
- **Kaynak ayrımı:** CRM süreçtir (sipariş girişi ve durumu, bekleyen ürün, hedef, etkinlik/ziyaret, okul/kurum); tamamlanmış
  finansal olay (fatura, satış tutarı/ciro, iade, tahsilat, muhasebe) Logo'dur. CRM sipariş tutarı ciro değildir. Planlayıcı
  istemindeki «Kaynak ayrımı» cümlesi bunu söyler.
- **Kod listesi:** `values` taşıyan alan `label` işlemiyle CRM etiketiyle gösterilir, süzgeçte sayısal kodla süzülür.
- **Toplam yalnız kökte:** bağlantılar yalnız çocuk → üst olduğu için üst kaydın tutarı her alt satırda tekrarlanır; `sum`
  yalnız kök alanında. `sum_allowed`: tutar ve adet alanları; oran, birim fiyat, stok, limit, risk, kod listesi toplanmaz.
- **Süzgeç değerleri düz metin:** `{type,value}` nesnesi modeli kısıtlı çözümlemede boş satır döngüsüne sokuyordu (vLLM
  0.27.1, 3/3 yeniden üretildi); tür alanın kayıttaki türünden gelir.
- **Bildirilmiş PK:** tek kolonlu PRIMARY KEY varsa tekillik taraması (9,8 Mn sipariş satırı) atlanır.
- **Satış hedefi taneciği:** kitap × yıl × bölge × satış temsilcisi (BMT); 12 ay kolonu her satırda toplam hedefe eşit.
