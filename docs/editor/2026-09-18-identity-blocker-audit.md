# R7 sıfır adlandırılmış görsel dayanak: gerçek kaynak tanısı

Yeni genel `audit-identity-blockers.py`, verilen gerçek neslin figure_identity, character_evidence, layout_regions ve source_spans kayıtlarını API'den okur ve bağımsız PG ile exact karşılaştırır. Model çağırmaz; ad, kimlik veya kaynak kararı üretmez/değiştirmez. Kitap kimliği yalnız ayrı doğrulama girdisidir.

R7 gerçek48sayfa nesli `382da5b3-a13a-4986-85ba-1a38fd92ff44`:48identitykaydı,2balonbağlantısı,0adlandırılmış dayanak.46sayfada balonbağlantısı yok.9sayfada11açık metinsel konuşmacı atfı bulunuyor; bu sayfalar iki balon adayının sayfalarıyla örtüşmüyor.17sayfanın page-purpose kapısı kapalı. İki balon adayının ikisinde açık atıf0; birinde kuyruk/figür çoğulluğu var. Kaynak atfı bulunmayan bu iki adayda quote–balon uyuşmazlığı ayrı baskın neden olarak sayılmadı. Kategoriler birbirini dışlamaz.

Somut ayrışma: regresyon sayfa29kaydı `3fb0f4e6-1814-5781-b90d-c5d67f016f89`, layout `7e747415-31c9-509f-bbd1-627d0e70f35d`, character_evidence `7fc05fdb-b479-5aed-b7cb-e226a4edf26d`. Bir kuyruk tek figüre bağlanmış; `page_purpose_gate.passed=true`, fakat character_evidence.page_role=ACTIVITY ve attributionlistesi boş. Genel akışta metinsel atıf çıkarımı aday sayfa rolünü kullanıyor; sonraki bağımsız sayfa amacı kapısı bu erken boş sonucu yeniden üretmiyor. Bu iki rol kaynağının ayrışması kök neden adayıdır; çözüm isim vermek veya sayfaya özel istisna değildir. Yeni V16 rol/atıf akışında gerçek kaynakla yeniden denetlenmesi gerekir.

Regresyon sayfa37kaydı `6af98076-5bd1-588c-8a5a-e6696e9aa54f`:9kuyruk–figür hit'i, localfigure adayı yok; page-purpose false, attributionpage_roleUNKNOWN. Burada hem çoklu kuyruk/figür hem kaynak rolü/atıf eksikliği var. Bu bulgu sonraki karakter adını çıkarmaya yetmez.

Kanıtlar CPU `/data/nanobaseai/editor/evidence/identity-blocker-audit-10377d6a-cfdc-4a94-a1a6-2575cc843380.json` ve rol alanlarını ayrıştıran `identity-blocker-audit-075e68f7-be7e-4781-b25b-4a71d5cfaf9c.json`. Önce/sonra records MD5 `ff40c81843b8b66f36a63d22bd404b7d`, reviews null; API/PG eşliği, model_calls0/application_writes0. Kimlik üretim kodu değiştirilmedi. Anlamsal veya görsel kimlik kabulü değildir.

## V16 rol sıralaması ve kimlik sınırı

R7'deki29sayfa rol ayrışması V16'nın genel sıralama değişikliğiyle hedefleniyor: kaynak sayfa amacı önce belirlenir; proposal sonunda passedpage_purpose.page_role esas alınır; interpret içindeki character_evidence.extract bundan sonra bu rolü kullanır. Yeni tam V16 neslinin gerçek kaynak kanıtı olmadan ayrışma giderildi denmez. Açık ad/atıf kaynağı yoksa bu düzeltmeden sonra bile adlandırılmış görsel dayanak0kalabilir. Kitaptan isim sağlanmaz; yeni identitykoduna bu adımda dokunulmadı.
