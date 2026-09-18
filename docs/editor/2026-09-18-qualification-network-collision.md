# R7 ayrı kurulum ağ çakışması

Gerçek Docker IPAM incelemesi, wrapper'ın zorladığı `10.203.80.0/24` ve `10.203.81.0/24` ağlarının `editor-restore-acl-v4_private` / `editor-restore-acl-v4_ingress` tarafından kullanıldığını gösterdi. `qualify-completed-installation.py` içindeki `available_subnets` bu çakışmayı doğru biçimde reddetmişti. Sorun yedek veya kitap verisi değil, dış wrapper'ın sabit ağ seçimiydi. Mevcut ağlar/container'lar silinmedi.

Yeni genel `scripts/qualification-network-plan.py`, açık IPv4 havuzu/prefix yapılandırmasıyla gerçek Docker IPAM envanterini okuyup çakışmayan iki alt ağ üretir. Çıktı envanter ve SHA içerir; ağ ayırmaz veya silmez. Wrapper tek planın ingress değerini nginx allow, UFW ve qualifier hedef ortamına verir. Qualifier restore öncesinde çakışmayı yeniden denetler; arada başka işlem ağı kullanırsa kapalı biçimde durur.

CPU sunucusunda gerçek salt okunur kontrol `10.203.64.0/18` havuzundan70/71 çiftini seçti. `/data/nanobaseai/editor/evidence/v15-r7-network-plan.json` kanıtıdır. Bu yalnız seçim kontrolüdür; restore kabulü değildir. Resume wrapper `runtime/run-v15-r7-qualification-resume.py` tek kopya proxy lock ile hazırlandı. İlk başarısız log `evidence/v15-r7-qualification-network-failure-preserved.log` olarak ayrıca korundu.

Yeni R7 gerçek soru/indeks kabulü tamamlanana kadar snapshot/restore başlatılmadı. Önceki backup yeni soru kayıtlarını içermez; QA sonrasında eski backup silinmeden arşivlenmeli ve aynı pinned offline paket/restore başlamamış hedef üzerinde yeni backup alınmalıdır. Ana backend/model/kaynaklar değiştirilmedi. Ağ düzeltmesinin tam restore kabulü henüz **DOĞRULANAMADI**.

## Sonraki kabul engeli

R7 gerçek soru arayüzü kanıtı `source-question-ui-ac2208e5-aa2c-44d6-9194-906d06c5abf3` PASS bildirdi; ancak bağımsız100pasaj denetimi `source-preview-20260918T082747212072Z.json` içinde `Passage exposes a partial hyphenated word` hatasıyla FAILED oldu. Arayüz başarısı bu kaynak bütünlüğü hatasını kapatmaz. Backend/verifier teşhisi ve gerçek yeniden kabul tamamlanmadan restore başlatılmayacak, backup değiştirilmeden korunacak. IPAM düzeltmesi bu anlamsal/kaynak bütünlüğü kontrolünün yerine geçmez.
