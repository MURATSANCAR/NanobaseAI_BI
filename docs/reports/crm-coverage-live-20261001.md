# CRM kapsam ve cevap kabulü — 1 Ekim 2026

Ürün kodu: `19e0d723ca860b2d391fba86921602b5569db934`. Test sunucusunda 17 ilgili kaynak dosyası bu commit ile eşleştirildi (`deployment-r20.json`). Müşteri VM’i bu çalışma kapsamında güncellenmedi.

Yürütme: test sunucusu, gerçek `http://127.0.0.1:8795` API ve bağlı `Timas_MSCRM`. Bağımsız referans sorguları aynı gerçek kaynaktan API öncesi/sonrası alınır; API’nin aynı resultId ile sakladığı tam sonucun kolonları, satırları ve değerleri karşılaştırılır. Yerel/mock/sentetik ürün testi yapılmadı.

## Kapsam ve düzeltmeler

- 3.081 nesne / 90.399 kolon metadata envanteri; doğrudan rapor kapsamı 31 tablo / 161 alan. Fiziksel alan eşleşmesi iş hesabı kabulü değildir.
- 400 özel nesne adayı hâlâ UNREVIEWED; öncelik grupları 25 / 213 / 28 / 134. Bunlar incelenmemiş 3.050 nesnenin altkümesidir.
- Çözülemeyen aktif sözleşme tarafı bağlantıları, ilgili çıktı sözleşmelerinde INCOMPLETE_SOURCE_COVERAGE üretir. Pasif kişi/kurum bilgisi kullanılmaz; dönem dışı eksiklikler sonucu etkilemez.
- Kitap/yayıncı/aşama tarihçesi ve sözleşme revizyonu, kaynağın kanıtlamadığı eski-yeni değer veya hukuki öncelik iddiasına dönüşmez.
- Kullanıcının kısmi cevap izni özgün cümle ve gerçek talep kimliğine bağlıdır; nüfus/tarih/kimlik/sıralama/yasak koşullarını kaldırmaz. İzinli eksik hesap zorunlu gap ve PARTIAL_ANSWER üretir.
- Tamamlanamayan model üretimi, semantik yeniden planlamayla tekrar tekrar çoğaltılmaz. Boş gerekçesiz plan, desteklenmeyen yetenek sayılmadan sınırlı onarıma girer.

## Son sürümün sonuçları

FULL_ANSWER_PASS: bağımsız tam cevap eşleşmesi. BOUNDARY_PASS: döndürülen tam veriler eşleşir ve hesaplanamayan kısım doğru açıklanır; bütün talebin sayısal kabulü değildir. FAIL ve UNVERIFIED başarıya eklenmez.

### crm-r12-permission

Durum sayıları: `{"BOUNDARY_PASS": 1}`. Kod sabitliği: `True`; silinen geçici oturum: `1`; kaynak yazma: `0`.

| Kimlik | Soru | Durum | Tam satır |
| --- | --- | --- | ---: |
| CR023 | CRM'de açık kitap işlerinin aynı aşamada üç aydan uzun bekleyip beklemediğini araştır. Aşamaya giriş tarihi kanıtlanmıyorsa son güncellemeyi kullanma; mevcut işleri ve doğrulanamayan kısmı göster. | BOUNDARY_PASS | 1 |

### crm-r12-coverage

Durum sayıları: `{"FULL_ANSWER_PASS": 2, "BOUNDARY_PASS": 6}`. Kod sabitliği: `True`; silinen geçici oturum: `1`; kaynak yazma: `0`.

| Kimlik | Soru | Durum | Tam satır |
| --- | --- | --- | ---: |
| CR007 | CRM'de aktif kişi yazar bağlantılarının adları kitap yazar künyesiyle uyuşmayan kayıtları bul; yazım farkı adaylarını belirt, kişileri birleştirme. | FULL_ANSWER_PASS | 135 |
| CR013 | 1 Eylül 2026 dahil 1 Ekim 2026 hariç dönemde güncellenen CRM kitaplarında değişiklik geçmişini göster. Baskı/fiyat tarihçesini genel eski-yeni alan değişikliği gibi sunma; doğrulayamadığını belirt. | BOUNDARY_PASS | 368 |
| CR022 | 30 Eylül 2026 dahil 30 Ekim 2026 hariç aralıkta tahmini bitişi olan açık CRM kitap iş planlarını ve geçmiş terminli açık işleri göster; sorumlu ve aşama eksiklerini belirt. | FULL_ANSWER_PASS | 1 |
| CR024 | 30 Eylül 2026 dahil 30 Mart 2027 hariç aralıkta kayıtlı bitiş adayı olan aktif CRM kitap sözleşmelerini kitap, taraf, hak, dil ve bölgeyle göster. Boş bitişleri ayrıca göster; revize/yenileme önceliğini veya satış yasağını varsayma. | BOUNDARY_PASS | 999 |
| CR026 | CRM'de aktif kitap sözleşmelerinin kişi ve firma taraflarını kitapla bağlı kişi yazarlardan ayrı göster; taraf rolünü ve hak kapsamını da ver, yazarın hak sahibi olduğunu varsayma. | BOUNDARY_PASS | 10564 |
| CR030 | CRM aktif kitaplarının bugünkü ve önceki yayın evi alanlarını göster. Geçmiş yayın evi ilişkisinin tarih aralığı yoksa geçmiş sınıflandırmayı doğrulanmış sayma. | BOUNDARY_PASS | 9380 |
| CR031 | CRM'de aktif kitaplara bağlı aktif sözleşmelerin Ana Sözleşme Id metnini göster: kendi kimliğine, başka aktif sözleşmeye ve aktif karşılığı bulunamayan kimliğe gidenleri ayır. Başlangıç, bitiş, revize, yenileme, fesih ve ek protokol tarihlerini ve ek protokol bayraklarını ayrı göster. Hukuki öncelik varsayma, PDF logunu değişiklik geçmişi sayma. | BOUNDARY_PASS | 10564 |
| CR033 | CRM'de kitap yazar Contact kimlikleriyle sözleşmenin Contact taraf kimlikleri farklı olan kitap-sözleşmeleri listele. Kurum tarafları veya eksik kişi bağları karşılaştırılamıyorsa ayrı belirt; isimden eşleştirme yapma ve yazarı hak sahibi varsayma. | BOUNDARY_PASS | 9712 |

## Önceki sürümler ayrı tutulur

- `crm-r9-coverage`: `{"BOUNDARY_PASS": 4, "FAIL": 3}`. Son sürümün kabul toplamına eklenmez.
- `crm-r10-coverage`: `{"BOUNDARY_PASS": 6, "FAIL": 1}`. Son sürümün kabul toplamına eklenmez.
- `crm-r11-permission`: `{"FAIL": 1}`. Son sürümün kabul toplamına eklenmez.

## Açık sınırlar

- Son sürümün bütün 100 karmaşık soru için bağımsız tam cevap kabulü tamamlanmadı; bu hedefli kontroller genel üretim kabulü değildir.
- Gerçek eski-yeni audit çözümü, aşamaya giriş tarihçesi ve sözleşme yürürlük önceliği hâlâ kanıtlanmış değil.
- Kâr/maliyet ve ödeme kapama/yaşlandırma kaynak sınırları ayrı finans raporunda; tahmini iş tanımıyla kapatılmadı.
- Background refresh yolu finansın sınırlı1205 retry’sini kullanmıyor; kilitleyen işlem için DBA deadlock grafiği gerekir.
- Ölçülen yanıt süreleri kanıt JSON’unda; geçiş sayısı yanıt süresi kabulü değildir.

Kanıt özeti: `/Users/msancar/.codex/visualizations/2026/09/30/01a0f2ac-0c9e-7a23-8f10-1e43ca564e51/crm-coverage-live-summary.json`. Uzak tekil kanıtlar `/data/nanobaseai/bi/acceptance/finance-expanded-20260930/` altında, her sorunun resultId, kod hash’i ve referanslarıyla saklanır.
