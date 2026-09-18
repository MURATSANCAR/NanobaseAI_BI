# R7 ayrı kurulum ağ çakışması

Gerçek Docker IPAM incelemesi, wrapper'ın zorladığı `10.203.80.0/24` ve `10.203.81.0/24` ağlarının `editor-restore-acl-v4_private` / `editor-restore-acl-v4_ingress` tarafından kullanıldığını gösterdi. `qualify-completed-installation.py` içindeki `available_subnets` bu çakışmayı doğru biçimde reddetmişti. Sorun yedek veya kitap verisi değil, dış wrapper'ın sabit ağ seçimiydi. Mevcut ağlar/container'lar silinmedi.

Yeni genel `scripts/qualification-network-plan.py`, açık IPv4 havuzu/prefix yapılandırmasıyla gerçek Docker IPAM envanterini okuyup çakışmayan iki alt ağ üretir. Çıktı envanter ve SHA içerir; ağ ayırmaz veya silmez. Wrapper tek planın ingress değerini nginx allow, UFW ve qualifier hedef ortamına verir. Qualifier restore öncesinde çakışmayı yeniden denetler; arada başka işlem ağı kullanırsa kapalı biçimde durur.

CPU sunucusunda gerçek salt okunur kontrol `10.203.64.0/18` havuzundan70/71 çiftini seçti. `/data/nanobaseai/editor/evidence/v15-r7-network-plan.json` kanıtıdır. Bu yalnız seçim kontrolüdür; restore kabulü değildir. Resume wrapper `runtime/run-v15-r7-qualification-resume.py` tek kopya proxy lock ile hazırlandı. İlk başarısız log `evidence/v15-r7-qualification-network-failure-preserved.log` olarak ayrıca korundu.

Yeni R7 gerçek soru/indeks kabulü tamamlanana kadar snapshot/restore başlatılmadı. Önceki backup yeni soru kayıtlarını içermez; QA sonrasında eski backup silinmeden arşivlenmeli ve aynı pinned offline paket/restore başlamamış hedef üzerinde yeni backup alınmalıdır. Ana backend/model/kaynaklar değiştirilmedi. Ağ düzeltmesinin tam restore kabulü henüz **DOĞRULANAMADI**.

## Sonraki kabul engeli

R7 gerçek soru arayüzü kanıtı `source-question-ui-ac2208e5-aa2c-44d6-9194-906d06c5abf3` PASS bildirdi; ancak bağımsız100pasaj denetimi `source-preview-20260918T082747212072Z.json` içinde `Passage exposes a partial hyphenated word` hatasıyla FAILED oldu. Arayüz başarısı bu kaynak bütünlüğü hatasını kapatmaz. Backend/verifier teşhisi ve gerçek yeniden kabul tamamlanmadan restore başlatılmayacak, backup değiştirilmeden korunacak. IPAM düzeltmesi bu anlamsal/kaynak bütünlüğü kontrolünün yerine geçmez.

## Aynı pinned R7 koşusuna devam

Bağımsız denetimdeki yanlış pozitif genel verifier düzeltmesiyle giderildi; aynı gerçek R7 API/PG/Qdrant kontrolü `source-preview-20260918T083135488336Z.json` PASS oldu. Ana ürün kodu değişmedi. Yeni QA inputu nesil `382da5b3-a13a-4986-85ba-1a38fd92ff44`, soru işleri `571649c1-c6ac-4983-9030-4e085bcd0c1f` ve `f058d90c-06e2-4a3b-9d85-cf525b773924` ile yenilendi. Eski input `source-preview-qualification-input-r4-preserved.json`; eski backup aynı qualification dizininde `backup-before-r7-source-preview` olarak korunur.

2026-09-18 08:34UTC'de tek resume PID1470576 başladı; log `evidence/v15-r7-qualification-resume.log`. Release bytes PASS, aynı offline bundle REUSED; yeni dolu soru kayıtları/index için yeni backup alınacak. Bu başlatma, tamamlanmış restore kabulü değildir.

Donmuş paketteki eski bağımsız verifier korunmuştur. Yalnız restore hedefindeki kabul aracı `installation/scripts/verify-source-preview.py` SHA `7ecb96a50f454da52fc1e5702759f7cf22ff083846f15fc301c16663877e8055` yerine gerçek yeniden kabulde kullanılan `e3e5b70bde812e49bdf30fd041aab2f4ac7ed0360d093a0aedc0b02f00e16660` ile değiştirildi. Önceki hedef betiği ayrıca saklanır. Kaynak/hedef yolları ve hashler `evidence/v15-r7-resume-verifier-override.json` içinde açıkça kayıtlıdır; ürün backend/paket hashleri değiştirilmedi. Teknik aktarım kabulü adlandırılmış varlıkların anlamsal doğruluğunu onaylamaz.

## Tekrar koşulabilir kabul kanıtı düzeltmesi

İlk resume, kaynak ve türetilmiş API/PG kontrollerini geçtikten sonra `verify-semantic-provenance.py` sabit nesil+hash dosya adına exclusive yazdığı için önceki PASS kanıtında `FileExistsError` verdi. Aynı kusur sonraki `verify-publication-gates.py` betiğinde de statik incelemeyle bulundu. İki araç artık bağımsız koşu UUID'siyle yeni kanıt dosyası açar; önceki kanıt silinmez, bütün gerçek veri/kabul kontrolleri aynıdır.

Araç hashleri: semantic provenance `5feacf7e36be267e98945386e8799e10ac88b4db97edda66b711154150d9c9fc`; publication gates `1856ab94463ddc7870b7deaab532965a5365618742b4518d1e486b401e3fc1b0`. Root ve restore hedefindeki kabul aracı override'ları `v15-r7-provenance-verifier-override.json` ve `v15-r7-publication-verifier-override.json` ile kaydedildi. Donmuş paket/ürün backend değişmedi. Önceki adım logları `resume-attempt1-logs` içinde ayrıca korunur. Tek resume2 PID1493605; log `evidence/v15-r7-qualification-resume2.log`. Tamamlanma henüz doğrulanmadı.

## Sonuç: gerçek ayrı kurulum teknik kabulü PASS

2026-09-18 08:43:33UTC'de resume2 tamamlandı. `/data/nanobaseai/editor-qualifications/v15-r7-20260918/382da5b3/qualification.json` nihai qualification PASS ve hedef servisler STOPPED kaydını içerir. Tam log `/data/nanobaseai/editor/evidence/v15-r7-qualification-resume2.log`. Dinamik IPAM70/71 ağıyla çakışma giderildi; önceki ağların hiçbiri silinmedi. Geçici nginx proxy ve iki UFW kuralı kaldırıldı, cleanup_errors boş. Hedef veriler/kanıtlar tutuldu.

Yeni QA kayıtlarını içeren backup ve gerçek restore PASS. R7 neslin100pasajı ve vektörü depodan yeniden kuruldu (`embedding_calls=0`); ayrı API/PG/Qdrant kontrolü `installation/evidence/source-preview-20260918T084121516423Z.json` PASS. Kaynak/türetilmiş kayıt eşliği, sentez dayanak bağlantıları ve yayın kapıları PASS. Gerçek tarayıcı320/390/768/1440px ve6sekme kontrolünde yatay taşma yok; `restored_mobile_ui.log` ayrıntıyı kaydeder.

Bu teknik taşınabilirlik/kanıt bütünlüğü kabulüdür. `semantic_acceptance=false` korunur; adlandırılmış gönderge veya kitabın bütün anlamsal kalitesi bu sonuçla onaylanmaz. Eski başarısız loglar, eski backup, eski araçlar ve frozen offline paket korunur. Kaynak kitap, model cevabı, konuşmacı ya da editör kararı elle değiştirilmedi.
