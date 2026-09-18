# V14-r5: kesilmiş model yanıtı ve bağımsız bölgesel OCR uzlaşması

18 Eylül 05:28 UTC. R4 teknik kabulden sonra açık işleri bekletmek yerine geliştirmeye devam edildi. Bu belge R5'in tam kitap kabulü değildir.

## Kod değişiklikleri

`analysis.py`: yalnız `finish_reason=length` olan model çağrısı aynı kaynak, istem, model ve seed ile bir kez daha yapılır. Çıktı bütçesi en fazla iki katına çıkar; gerçek tokenizer ile ölçülen bağlam sınırı ve 512 token pay korunur. Kısmi yanıt yeni isteme eklenmez. Tamamlanmış olumsuz/belirsiz karar olumlu sonuç aramak için tekrar edilmez. İlk kesilmiş çıktı, iki isteğin/yanıtın hashleri, değişmeyen mesaj hashleri, token kullanımı ve bitiş nedenleri kanıt olarak saklanır. İkinci deneme de kesilirse kabul verilmez; `semantic_acceptance.py` başarısız deneme izini de korur.

`ocr_vl.py` V2: temiz ve geometrisi bağlı PDF metni, Tesseract'ın iki kırpım okuması ve OCR-VL aynı sözcükleri ve noktalama konumlarını destekliyorsa tek bölgesel Paddle uyuşmazlığı aşılabilir. Apostrof ile çift tırnak birbirine çevrilmez; sözcük sınırları, olumsuzluk ve ham okuyucu metni korunur. Bozuk PDF, kararsız kırpım, noktalama farkı veya bağımsız destek eksikliği bu yeni yolu açmaz. Hangi okuyucunun geçersiz kılındığı kaydedilir. Kitaba/sayfaya/karakter adına özel yanıt yoktur.

Kaynak doğrulayıcı, bu yeni seçim yolundaki dört tam token akışını üretim seçim fonksiyonunu kullanmadan karşılaştırır. Türetilmiş analiz doğrulayıcı aynı girdili en fazla iki model denemesini, bağlam/çıktı sınırını ve yalnız kesilmiş yanıtın yeniden denenmesini denetler.

## Gerçek CPU API / PostgreSQL / GPU bileşen doğrulaması

Kaynak nesil R4 `08ca6877-6e30-4bb3-b1fa-767f048248e4`. Uygulama kayıtları yalnız okundu; kitap veya inceleme kararı yazımı 0. Yerel/sentetik test çalıştırılmadı.

- 10 ve32. sayfalarda gerçek kesilmiş ikinci atıf çağrıları, aynı girdi hashleriyle tekrar üretildi. İkisinde de ilk çağrı yeniden `length` oldu; tek ek deneme tamamlandı ve kaynak denetimi geçti. Kanıtlar CPU `evidence/bounded-model-retry-real-page-0010.json` ve `...0032.json`; log `evidence/bounded-retry-probe.log`. Bu yalnız iki gerçek bileşenin kabulüdür, bütün kitabın değil.
- 1.149 gerçek kaynak bölgesi API/bağımsız PG eşliğiyle incelendi. 210 OCR-VL ölçümü, mevcut13 OCR-VL seçimi korunarak sınandı. Son dosya hashinde9 ek bölge yeni güçlü uzlaşma kuralını karşıladı. Diğer incelemeler açık kaldı. Kanıt `evidence/ocr-native-crop-consensus-v2-final-real-book.json`; son kod SHA256 `0fa06d3baa2a005eb35947dd4aa181b27e9a86b20f1cfc41a90778e5ffbd1c24`. Önceki aday kanıtı ayrı dosyada korunur.

## Hazırlanan imajlar

CPU üzerinde mevcut R4 tabanlarından ağsız derlendi; bu satırların yazıldığı anda henüz canlıya alınmadı:

- API `nanobase-editor:source-analysis-v14-r5-20260918`: `sha256:5f7c9aa044619bc189ec3b016829b91d175d64fe7e7783810cc9bf42b8668d64`
- Document `nanobase-editor-document:source-analysis-v14-r5-20260918`: `sha256:12e6a914c7a2b58ab906fea82438db1390c04eb6db40d183f4c54ea8cf624928`
- `analysis.py`: `ef08da2339dba6f09a07c9a803468ea476d8ad0e4e966831af84e7a0a2cf0191`
- `semantic_acceptance.py`: `1dd31aa2254ae7fde29bb432f7b29ac67fbef48dac6398a6ec80ad6cdc0a36ba`

Build kanıtı `evidence/v14-r5-build-proof.json`. Model tekrar kodu paylaşılan çalışma alanında `d95d1a4` commitine girdi; içerik hashleri yukarıdadır. R5 yeni nesil ve yeni tam API/PG/atıf/paket/restore kabulünden geçmeden R4 başarısı R5'e taşınmaz. Genel figür kimliği, tam anlamsal kapsam ve üretim kabulü açık kalır.
