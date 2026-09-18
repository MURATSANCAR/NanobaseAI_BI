# Semantic v6 gerçek kayıt probe sonucu

Yeni `scripts/probe-cited-semantics.py` genel uzak bileşen sürücüsüdür: generation ve sayfaları açık regresyon girdisi olarak alır; API'deki gerçek kaynak pasajlarını ve OCR bölgelerini bağımsız PostgreSQL kayıtlarıyla karşılaştırır. Kayıtlı iddia ve onun kaynak refs'i aynen `review_cited_support` girdisi olur. Beklenen yanıt, kitap özel kuralı veya elle değiştirilmiş metin yoktur. Kaynak/inceleme tablolarının önce-sonra hashleri, aday modül SHA ve çalışma sürümü kaydedilir. Sonraki uzun koşular her 10 tamamlanan kayıtta stderr'e JSON ilerleme kaydı yazar.

18 Eylül CPU koşusu: R7 nesli `382da5b3-a13a-4986-85ba-1a38fd92ff44`, regresyon sayfaları 15/19/22/33/41, 19 kayıt. Teknik bütünlük geçti: API/PG eşit, kaynak/inceleme hashleri aynı, uygulama yazımı sıfır. Aday semantic modül SHA `0e7696b9b0821ea718c4c861717437b540586f541dbc861613169fdb5f02ebb1`. Model 17 kaydı geçirdi; 2 kayıt engellendi. **Bu dağılım kalite başarısı değildir.**

- Sayfa 41'de belirsizliğin kesinliğe dönüşmesi `epistemic_strength=FAIL` ile yakalandı.
- Sayfa 15'te aynı tür belirsizlik kaybı geçti; model konuşma/yardım isteme eyleminin gerçekleşmesini belirsiz önermenin kesinleşmesiyle karıştırdı.
- Sayfa 19'da kaynakta bulunmayan konumun iddiaya eklenmesi geçti. Model gerekçesi konumun kaynakta bulunmadığını açıkça kabul ederken çekirdek eylemin uyuşmasını yeterli saydı.
- Sayfa 22'de kaynakta doğrulanmamış sahiplik eklemesi geçti.
- Sayfa 33'te ilerleyen eylemin dolaylı aktarımı geçti; Türkçede bu biçimin tek başına tamamlanmışlık kanıtı olmadığı ayrıca değerlendirilmelidir. Model geçişi bağımsız dilsel kabul değildir.

Sonuç: yeni epistemik eksen ve sınırlı yüzey adı kapısı bütün önerme kapsamı/atıf hatalarını güvenilir biçimde kapatmamaktadır. **Anlamsal kabul başarısız; canlı yayına hazır sayılmaz.** Mevcut R7 kayıtları değiştirilmedi, V16 dağıtımı veya yeni ana koşu başlatılmadı. Sonraki düzeltme genel doğrulama sözleşmesinde yapılmalı; başarı için bu gerçek başarısız örnekler yeniden denetlenmelidir.

CPU kanıtı: `/data/nanobaseai/editor/evidence/cited-semantics-probe-20260918T084907076324Z.json`; ham log: `/data/nanobaseai/editor/evidence/semantic-v6-saved-claims-probe.log`. Eski kanıtlar korunmuştur.
