# Eksiksiz iddia dayanağı — ayrı aday modül

`source_obligations.py`, genel bir iddia metnini deterministik token aralıklarına böler. Aralıklar whitespace dahil özgün metnin tamamını sıralı ve boşluksuz kapsar. Model bu aralıkları değiştiremez, atlayamaz veya çoğaltamaz. Her aralıkta PASS/FAIL/UNKNOWN ve gerekçe; her PASS için gerçek kaynak bölgesine ait literal altmetin/ref/karakter aralığı gerekir. Runtime tam şemayı, sıra/kapsamı ve birebir substring eşitliğini doğrular; kaynak bölgesi ve literal hashlerini saklar. Eksik veya yanlış destek, eksik çıktı ve bütçe aşımı kabul üretmez.

Bu, mevcut kaynak/kimlik/kip/anlamsal eksenlerin yerine geçmez. Tam alıntı bütünlüğü anlam eşdeğerliği kanıtı değildir; model bütün parçaların kaynak tarafından desteklenip desteklenmediğini yine yanlış değerlendirebilir. Sonuç `semantic_acceptance:false` kalır. Modül hiçbir kayıt veya kaynak metnini değiştirmez.

İlk gerçek bileşen probe `probe-source-obligations.py` üzerinden aynı kayıtlı R7 iddiaları ve onların gerçek refs'iyle başlatıldı. API/PG eşitliği, ana iş kuyruğunun boşluğu, kaynak/inceleme önce-sonra hashleri ve aday modül SHA kaydedilir. Beklenen cevap ve kitap özel kuralları modele verilmez. Her on kayıt için ilerleme JSON'u stderr'e yazılır. CPU ham log: `/data/nanobaseai/editor/evidence/source-obligations-probe.log`. Model sonucu ve gerçek başarısız konum/sahiplik örneklerinin durumu görülmeden bu çalışma çözüm veya üretim kabulü sayılmaz.

Yalnız yeni modül ve aday sürücü üzerinde çalışılmıştır; `semantic_acceptance.py` entegrasyonu ve dağıtım bu adımda yapılmamıştır. İlk uzak kopyadan sonra yalnız geçersiz span_id/quote türleri için yerel şema koruması eklenmiştir; final kanıttaki modül SHA koşulan uzak kopyaya aittir.

## İlk gerçek ölçüm ve v2 düzeltmesi

İlk 19 gerçek kayıtta 16 çıktı literal quote/Unicode offset eşleşmesi hatasıyla engellendi. İki çıktı anlamsal olarak reddedildi, yalnız biri geçti. Bu dağılım kalite başarısı veya güvenilir yanlış-ret ölçümü değildir: modelin kaynak metnini ve karakter konumunu yeniden üretmesi baskın biçim hatasıydı. Kanıt CPU `evidence/source-obligations-probe-20260918T085431688866Z.json`; kaynak/inceleme hashleri değişmedi.

`source-obligations-v2` bu genel hatayı modelden metin/offset istemeyi kaldırarak düzeltir. Kaynak tokenları önceden deterministik kimliklere ayrılır; model yalnız mevcut `SOURCE_...` kimliklerini seçer. Runtime bu kimlikten gerçek span, başlangıç/bitiş, literal quote, kaynak ve literal hashlerini aynen üretir. Bilinmeyen veya tekrarlı kimlik, atlanan iddia parçası ve dayanıksız PASS reddedilir. Türkçe kaynak metni modele yeniden yazdırılmaz. İddia token/bütçe sınırı veya model kesilmesi açık `NEEDS_REVIEW` sonucudur; diğer altyapı hataları gizlenmez.

İkinci gerçek 19 kayıt probe için bütün v2 düzeltmeleri tek dondurulmuş modülde birleştirildi: SHA `5b732dc3e7aee05921eab7d8f48c8372619ee9fb818cf1eb7e8c1e6134a0dddb`. Uzak ve yerel aday aynı sürümdür; koşu sırasında modül değiştirilmez. Ham log `evidence/source-obligations-v2-probe.log`. Sonuç görülmeden v2 kabul edilmiş sayılmaz.

## V2 gerçek sonuç

CPU kanıtı `evidence/source-obligations-probe-20260918T085718631141Z.json`: 19 kaydın tamamında yapısal kapsam ve kaynak-ID bütünlüğü geçti; literal/offset biçim hatası sıfır. Kaynak ve inceleme hashleri aynı; API/PG eşit. Model 14 iddiayı geçirdi, beşini incelemeye ayırdı.

Önceden kaçan kaynaksız konum ve robot sahipliği artık ilgili `Bahçede` / `Robotun` tokenlarında UNKNOWN olarak yakalandı. Kaynakta olmayan özel isim ve belirsiz nesne ataması için de ret üretildi. Bununla birlikte kaynakta virgülle bağlanan ifadeyi iddiada `ve` ile birleştiren bir iddia gereksiz biçimde reddedildi. Belirsizlik belirtecinin kesinleştirilmesi örnekleri bu modülden geçti; ayrı epistemik/qualifier kapısıyla AND zorunludur. Bu nedenle 14 model PASS, 14 bağımsız doğruluk kabulü olarak sunulamaz.

Sonuç: kaynak literalini modele yazdırma hatası bu gerçek kümede giderildi; istenen konum/sahiplik sızıntıları kaynak kapsamı sözleşmesiyle yakalandı. Genel anlamsal doğruluk, gereksiz retlerin tamamen kalkması veya başka kitap başarısı iddia edilmez. V2 modülü aynı SHA ile donduruldu; birleşik v7 entegrasyon/kabulü ayrı çalışmadır.

## V3 işlevsel eşdeğerlik sözleşmesi

V2'deki gereksiz bağlaç reddi üzerine genel denetim talimatı netleştirildi: literal dayanak gerçek kaynaktan aynen alınır, fakat iddia kelimesinin kaynakta aynı yazımla bulunması zorunlu değildir. Noktalama/koordinasyonla açıkça desteklenen bağlaç ve çekim ilişkileri anlam korunuyorsa geçebilir; her iki kaynak unsurunun dayanağı ve korunmuş ilişkinin gerekçesi istenir. Yeni konum, sahiplik, fail, zaman, kesinlik veya nedensellik eklemek bu eşdeğerlik kapsamında değildir. FAIL/UNKNOWN kararına kodla override eklenmedi.

`source-obligations-v3` şema, kaynak-ID seçimi ve literal bütünlük kapılarını v2 ile aynı tutar. Dondurulmuş SHA `3380d08ba25ea504ed17201b5f550353c99434277ae09193a965b65f4a6849fc`. Aynı 19 gerçek kayıtla yeni koşunun logu CPU `evidence/source-obligations-v3-probe.log`; önceki v1/v2 kanıtları korunur. Bilinen konum/sahiplik retleri korunmadan ve önceki gereksiz ret yeniden incelenmeden bu değişiklik tamamlanmış sayılmaz.

V3 gerçek sonuç: `evidence/source-obligations-probe-20260918T090037859420Z.json`. 19/19 kapsam/şema doğrulandı, biçim hatası sıfır; 14 model PASS, beş ret. Kaynaksız konum ve sahiplik UNKNOWN kararları korundu. `ve` bağlacı için önceki gereksiz ret kalktı; ancak aynı cümle `düşüyor → düşüyordu` zaman yorumu nedeniyle incelemede kaldı. Türkçe birleşik anlatıda ortak geçmiş eki yorumu mümkün olduğundan bu kalan ret ayrıca dilsel değerlendirme gerektirir; bütün örnek çözülmüş sayılmaz. Kaynak ve inceleme hashleri değişmedi. Dondurulmuş modül SHA aynı; birleşik v7 koşusuna geçilmesi bu belirsizliği kabul edilmiş veri haline getirmez.
