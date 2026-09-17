# Otomatik bölge OCR: lease sonrası toparlanma

Kod incelemesinde, geçici lease/bağlantı kaybının kuyruğa kalıcı iptal işareti yazdığı ve aynı nesilde yeniden denenen işin aynı istek kimliğine döndüğü bulundu. Consumer başarısız sonucu değişmez kaydettiği için yeni iş denemesi de eski `REREAD_CANCELLED` sonucuna takılıyordu. Bu bir kitap içeriği sorunu değildir.

V10-r2 adayı, üretim optik akışında isteğe işin `fencing_token` değerini `attempt_token` olarak ekler. Yeni lease farklı kuyruk kimliği kullanır; eski iptal ve başarısızlık kanıtları silinmez. Tamamlanan raporlar `page-NNNN-<requestUUID>.json` yolunda saklanır. Eski `page-NNNN.json` raporları ve nesiller arası kaynak kökeni doğrulaması desteklenmeye devam eder. API rapor listesi ve bağımsız artifact denetçisi her iki biçimi okur.

Bir önceki deneme ölçümü tamamladıysa, yeni deneme aynı kaynak/render, bölge sırası ve bbox, dil/model/motor/kod politikasıyla eşleşen tamamlanmış raporu yeniden kullanır. Böylece kısmen kaydedilmiş değişmez kaynak kayıtlarına farklı deneme kökeni eklenmez. Queue volume boşken de artifact raporundan sonuç işaretçisi yeniden kurulabilir. Kuyruk bekleme süresi dolduğunda iptal işareti yazılır; başarısız işin tüketici kuyruğunda çalışmaya devam etmesi engellenir.

Gerçek kabul senaryosu: gerçek kaynaktan aynı bölgelerle ilk denemeyi gönder; bekleme sırasında kontrollü lease hatası oluştur; iptal/başarısız sonuç kanıtını sakla; aynı nesil ve sayfayı yeni attempt ile gönder; yeni istek kimliğiyle tamamlandığını ve bağımsız crop/TSV hashlerini doğrula. Üçüncü attempt aynı tamamlanmış raporu ve artifact hashini kullanmalıdır. Eski nesil kökeni ve boş queue volume sonrası artifact recovery ayrıca doğrulanmalıdır.

Bu not kod düzeltmesini kaydeder. Yerel test veya uzak dağıtım yapılmadı. Önceki consumer bileşen kabulü değişen kod için geçerli değildir; V10-r2 gerçek fault/optik kabulü tamamlanana kadar durum **DOĞRULANAMADI**.
