# Ana V5 kaynaklarında kalan OCR uyuşmazlıkları — 17 Eylül 2026

## Kapsam ve veri bütünlüğü

**328 inceleme bölgesi salt okunur olarak sınıflandı.** Bu bir düzeltme veya yeni kabul değildir. Kitap metni, karar, konuşmacı ve mevcut kaynak kayıtları değiştirilmedi; model çağrısı veya yeni analiz başlatılmadı. Bütün hesaplar gerçek sunucuda, gerçek ana API ve bağımsız PostgreSQL kayıtlarıyla yapıldı; yerel test kullanılmadı.

- API: `http://127.0.0.1:8810`, sunucu `nanobase-direct`, kök `/data/nanobaseai/editor`.
- Kaynak nesil: `14a79646-79c6-4cdb-8714-00adf5698770`, `source-spans-v5`.
- Ölçüm: **2026-09-17 14:17:08 UTC**.
- Toplam 1.149 `source_spans`: **821 TEXT_AGREED, 328 NEEDS_REVIEW**.
- Sayfalanmış API'nin tam kaynak JSON'u bağımsız PostgreSQL sorgusuyla eşit. Önce/sonra kayıtlar eşit.
- Kaynak kayıtları SHA256: `4bc44462e801866cf54ee6791e6713d8788571fe15738d9e5829f871ec459738`.
- Genel ölçüm betiği: `apps/editor/scripts/audit-ocr-residuals.py`.
- Betik SHA256: `847580c9b2a1d2d92026f8fbf5352b3685a597efe21645c522fbaa57bd08e5ae`.
- Kanıt: `/data/nanobaseai/editor/evidence/ocr-residual-audit-14a79646-79c6-4cdb-8714-00adf5698770.json`.

## Birbirini dışlayan ana sınıflar

| Sınıf | Bölge |
|---|---:|
| Yüksek bölgesel OCR skoru; bağımsız okuyucu vetosu | 157 |
| Bölgesel OCR skoru 0,90 altında | 90 |
| Mevcut sıkı bölgesel seçim şartlarıyla desteklenen aday | 39 |
| Bölgesel okuma boş | 37 |
| Yüksek bölgesel skor, bağımsız destek yok | 3 |
| Yüksek bölgesel skor, bağımsız okuyucu vetosu yok ancak stabil tekrar vetosu var | 2 |
| **Toplam** | **328** |

Sınıflama sırası betikte açıktır; aynı bölge tek ana sınıfa girer. 39 desteklenen aday önceki bölgesel seçim çalışmasıyla tutarlıdır; bu rapor onların ana V5 kaydını değiştirmedi. V5'te 328 inceleme sayısı değişmedi. Bu raporu yeni nesilde gerçekleşmiş 39 kabul olarak sunmayın.

## Birbirleriyle örtüşebilen bulgular

- 208 bölgede bölgesel OCR skoru en az 0,90; 154 bölgede bölgesel okuma tam sayfa okumasıyla kelime düzeyinde eşit.
- 123 bölgede hizalanmış ikinci okuyucu metni yok. 164 bölgede ikinci okuyucu bölgesel okumayla çelişiyor.
- 215 bölgede PDF metni kullanılabilir; 106'sı bölgesel okumayla eşit, 109'u çelişkili.
- 21 bölgede PDF metni dolu fakat Unicode özel kullanım/değiştirme karakterleri nedeniyle bozuk ve kullanılamaz. İncelenen ikinci okuyucu metinlerinde bu Unicode bozukluğu türü bulunmadı; yanlış kelime/harf okumaları ayrı problemdir.
- 321 bölgede PSM 7/13 tekrar ölçümü mevcut: 55'i bölgesel okumayla stabil eşit, 79'u stabil çelişkili, 187'si kararsız. 7 bölgede tekrar yok.
- Tekrar durumları burada **bölgesel okumaya** göre yeniden hesaplandı. Mevcut kayıttaki tam sayfa okumaya göre `REREAD_CONFLICT` sayısı 92'dir; iki farklı karşılaştırmayı karıştırmayın.
- Kalan bölgelerin rolü: 310 `TEXT`, 18 `PAGE_LABEL_CANDIDATE`. Bu otomatik rol etiketleri insan onaylı belge sınıfı değildir.

## Düşük güvenli Tesseract vetosu neden tek başına kök çözüm değil?

Yüksek bölgesel OCR skoru ile Tesseract vetosu birlikte **138** bölgede var. Tesseract kelime güvenlerinin bölge ortalaması:

| Ortalama güven | Bölge |
|---|---:|
| 80 ve üzeri | 113 |
| 50–79 | 9 |
| 25–49 | 11 |
| 25 altında | 5 |

Yalnız **16** bölgede ortalama 50 altındadır. En az bir kelimenin güveni 50 altındaysa sayı **22** olur. Bu 22'nin 20'sinde kullanılabilir PDF bölgesel okumayı destekler; ancak **13'ü sayfa etiketi**, yalnız **7'si TEXT** rolündedir. Bu 20'nin yalnız 6'sında PSM 7/13 tekrarları bölgesel okumayla stabil eşittir.

Bu nedenle düşük güvenli Tesseract'ı otomatik yok saymak hem bağımsız veto kuralını zayıflatır hem de kitap anlamasında büyük bir kazanımı kanıtlamaz. Skorlar okuyucular arası kalibre edilmiş doğruluk olasılıkları değildir. Buradaki 50/80 eşikleri yalnız tanısal histogram içindir; kabul eşiği değildir.

## Yüksek skorla çelişen 138 bölgenin metin farkı

| Tanısal fark türü | Bölge |
|---|---:|
| Türkçe diakritikler kaldırıldığında aynı harf dizisi | 63 |
| Aynı kelime sayısı, diğer harf farkları | 37 |
| Bölgesel okuma sayısal, ikinci okuma farklı | 17 |
| İkinci okuyucuda daha az kelime | 9 |
| İkinci okuyucuda daha çok kelime | 6 |
| Harf dizisi aynı, kelime sınırları farklı | 6 |

Diakritik sınıfı `ç/ğ/ı/ö/ş/ü` farkını tanısal olarak sayar; bu dönüştürme **hiçbir kabul kapısına uygulanmadı**. Özellikle ı/i ve kelime sınırları anlamı değiştirebilir. 63 diakritik uyuşmazlığının yalnız 16'sında PDF bölgesel okumayı destekler; 32'sinde stabil tekrar bölgesel okumayla çelişir, 26'sında tekrar kararsızdır, 5'inde eşittir. Dolayısıyla bölgesel okumanın her durumda doğru olduğu da gösterilmemiştir.

Kanıt JSON'u her bölgenin kimliğini, bbox'ını, ham/bölgesel/ikinci/PDF metnini, kelime güvenlerini ve orijinal tekrar ölçümlerini içerir. Kitaba ait değerler üretim kuralı veya beklenen cevap yapılmadı.

## Kanıta dayanan sonraki genel kod iyileştirmesi

**Öncelikli aday: dile göre yapılandırılmış, hedefli bağımsız kırpım okuması.** Mevcut `source_regions.py` ve `region_reread.py` Tesseract'ı `tur+eng` ile çalıştırıyor. Kalan uyuşmazlıklarda Türkçe harf farkları belirgin olduğundan, aynı gerçek bölgelerde `tur` dil profili ve mevcut `tur+eng` profilini karşılaştıran sınırlı bir ölçüm makuldür. Bu bir başarı iddiası değildir; yeni model veya ağır tam kitap koşusu gerektirmeyen deney önerisidir.

1. Dil profili kitap/kurulum sözleşmesinden açıkça gelmeli; başlık, karakter adı veya beklenen metinden çıkarılmamalı. Türkçe dışı kitaplar için aynı genel yapı farklı dil profillerini desteklemeli.
2. Aynı bbox ve değişmez kırpım SHA256 üzerinde yeni ham TSV, okuyucu sürümü, dil profili, PSM ve kelime güvenleri kaydedilmeli. Eski ölçümler silinmemeli veya üzerine yazılmamalı.
3. İlk ölçüm kümesi genel özelliklerle seçilmeli: yüksek bölgesel OCR + ikinci okuyucu çelişkisi; tanısal diakritik, düşük güven, kelime sınırı ve sayısal alt sınıflar ayrı raporlanmalı. Bütün mevcut anlaşma bölgelerinde gerileme de ölçülmeli.
4. Yeni dil profiliyle iki okumanın eşitliği aynı Tesseract ailesinin iki bağımsız modeli sayılmamalı. PDF ve diğer bağımsız okuyucu kanıtı ayrıca korunmalı; stabil çelişki otomatik atlanmamalı.
5. Mevcut kabul kapısı değiştirilmeden aday ölçülmeli. Kelime sınırları, Türkçe harfler ve olumsuzluk normalizasyonla birleştirilmemeli. Kaynakla çelişen sonuç incelemede kalmalı.

İkinci aday, boş/düşük skorlu **127 bölgenin** geometrik kırpım kalitesini ayrı incelemektir. Bu rapor hangi kırpım dönüşümünün daha iyi olduğunu ölçmedi; yeniden ölçekleme/padding/deskew için başarı iddiası yoktur. Büyük yeni genel VLM eklemeden önce mevcut okuyucuların dil ve geometri kaynaklı hataları ölçülmelidir.

## Açık sınır

Ölçüm tek gerçek kitabın V5 neslidir. Diğer iki kitabın kaynak hazırlamasının başarılı olması bu OCR sınıflamasının veya önerilen dil profilinin o kitaplarda doğrulandığı anlamına gelmez. Görsel kimlik, konuşmacı ve anlamsal kitap analizi bu raporda doğrulanmadı.

## Yetkili dil profili pilotunun gerçek sonucu

Yukarıdaki öneri sonrasında **aynı sunucuda gerçek kaynak üzerinde ölçüldü**. Sonuç, `tur` profilini varsayılan yapmak için olumlu kanıt vermedi; **mevcut profil değiştirilmedi**.

- Genel deney betiği: `apps/editor/scripts/probe-ocr-language-profile.py`.
- Betik SHA256: `741d04bc76b5312850f47a3d3e9e90b3bbf78af4bfe54b93cb24145c425170a2`.
- Kanıt kökü: `/data/nanobaseai/editor/evidence/ocr-language-profile-20260917T141938Z/`.
- `report.json`: bütün sonuçlar, orijinal okuyucular, API/PG eşitliği ve değişmezlik kanıtı.
- Her kaynak kayıt anahtarı altındaki `crop.png` ve dört `tur+eng-psm7.tsv`, `tur+eng-psm13.tsv`, `tur-psm7.tsv`, `tur-psm13.tsv`: değişmemiş kırpım ve ham çıktılar. SHA256 değerleri raporda.
- Seçim: kullanıcının sorunlu regresyon sayfası 29'daki bütün **14** bölge; 13 ve 38'de kayıt sırasına göre ilk üçer review ve üçer agreed kontrol. Toplam **26 bölge: 18 NEEDS_REVIEW, 8 TEXT_AGREED**. Sabit sayfalar yalnız deney argümanıdır; üretim kuralı değildir.
- Her bölge aynı orijinal OCR renderı/bbox'ından, mevcut reread ile aynı ölçekleme ve 16px beyaz kenarla üretildi. Dil dışında PSM/ön işleme iki profil için aynıdır.
- 104 Tesseract çağrısı **25,267 saniye** sürdü. `OMP_THREAD_LIMIT=1`; çağrı başına 20 saniye, toplam 600 saniye sınırı vardı. Ağır model çağrısı yok.
- Motor `tesseract 5.3.0`; Türkçe traineddata SHA256 `7393381111e1152420fc4092cb44eef4237580d21b92bf30d7d221aad192c6b7`, İngilizce `7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2`.

| Ölçüm | tur+eng | tur |
|---|---:|---:|
| PSM 7/13 stabil aynı okuma | 15 | 14 |
| Stabil okuma bölgesel OCR ile aynı | 11 | 10 |
| Stabil okuma kullanılabilir PDF ile aynı | 9 | 9 |
| Stabil okuma tam sayfa ham metinle aynı | 8 | 8 |
| 8 mevcut agreed kontrolünde kaynakla eşleşme | 8 | 8 |

`tur` profili bu üç kaynak karşılaştırmasının hiçbirinde yeni eşleşme kazanmadı. Bölgesel OCR ile bir eşleşme kaybetti. Kayıt `0029-0013` üzerinde `tur+eng` PSM 7/13 aynı kelime sınırlarını okurken, `tur` PSM 13 son kelimede ek harf üretti ve tekrar kararsızlaştı. Bu metin üretim koduna veya beklenen cevap olarak modele verilmedi; yalnız gerçek motor çıktısı gözlemlendi. Diğer iki stabilite farkı kaynak destekli yeni bir kazanım sağlamadı.

**Karar:** bu pilot sonucuyla dil profili değiştirilmez ve eski okuyucu çelişkisi yok sayılmaz. Deney çözüm değildir. Kalan 328 V5 inceleme kaydı aynı kalmıştır. Bu küçük pilot tüm Türkçe kitapları temsil etmez; profil değişikliği ancak başka gerçek kitaplarda ve daha geniş kontrollerde fayda/gerileme ölçülerek değerlendirilebilir.

## PDF satır bozukluğu bayrağının kelimelere yayılması: gerçek etki sıfır

Ek salt okunur denetim **14:22:10 UTC** tarihinde aynı ana V5 neslinde yapıldı. `pdf_text_regions.py`, `corrupt_private_unicode` satır bayrağını satır metnindeki **en az bir bozuk Unicode karakteri** ile hesaplıyor. Bu ifade bütün satırın çözülemez olduğunu kodlamıyor. `source_alignment.aligned_words`, seçtiği her kelimeye satır bayrağını OR ile taşıdığı için, başka yerdeki bozuk kelimenin temiz seçili kelimeyi etkileyebilmesi yapısal bir adaydır.

Ancak **bu gerçek kitapta bu etki gözlenmedi**:

- 48 PDF bölge artefaktı, **757 satır** ve **1.149 kaynak bölgesi** okundu.
- Gerçek artefaktlarda satır düzeyi `true` bayrak sayısı **0**.
- Satır bayrağı ile bütün Unicode özel kullanım düzlemlerini kapsayan canlı kontrol **685 satırda eşit**, **72 satırda farklı**. Bu tarihsel artefakt bayraklarının tek başına güvenilir olmadığını gösterir; seçili kelimenin karakterleri zaten ayrıca yeniden kontrol ediliyor.
- Gerçek API/PG'de kullanılabilir PDF metni **976** bölgedir. Yalnız seçili kelimenin Unicode durumunu ölçen aday kontrolde sayı yine **976**.
- Satır bayrağı yüzünden yanlış kullanılamaz olan temiz seçili bölge: **0**.
- Seçili kelimelerinde gerçekten bozuk Unicode bulunan bölge: **71**. Bunlar toplam kaynak kümesidir; yalnız 328 review alt kümesi değildir.
- Bütün seçili kelimeler, geometrik koşullar artefaktlardan bağımsız uygulanarak mevcut `pdf_word_regions`, `pdf_text`, `pdf_usable` ile karşılaştırıldı; hepsi eşit. Her artefakt SHA256 değeri kayıtlı kaynak hashine eşit.

Genel betik: `apps/editor/scripts/audit-pdf-corruption-scope.py`; SHA256 `9fd86ed4be6f45c5e5a509b61c6ab29f49eb0c284a04898031e1395132232e60`. Kanıt: `/data/nanobaseai/editor/evidence/pdf-corruption-scope-14a79646-79c6-4cdb-8714-00adf5698770.json`.

**Karar:** satır bayrağı yayılımı bu kitabın kalan OCR sorununu açıklamaz. Gerçek tetikleyici bulunmadan üretim davranışı değiştirilmedi; güven kapısı veya Unicode kapsamı gevşetilmedi. Başka bir gerçek belgede satır içinde bozuk ve temiz kelimelerin birlikte bulunduğu doğrulanırsa kelime düzeyi provenance tasarımı ayrıca değerlendirilebilir. Kaynak/review yazımı ve model çağrısı yine **0**.
