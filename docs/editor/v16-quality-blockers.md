# V16 R5 gerçek kalite engelleri — 18 Eylül 2026

Nesil `116bb4a8-b7b5-45dd-9986-ac80fd706533`, yayın `source-analysis-v16-r5-20260918`. İşleme tamamlandı; kitabın anlamsal kabulü verilmedi. Bu incelemede model/QA çağrısı, uygulama veya kitap kaydı yazımı yapılmadı. CPU gerçek API ve PostgreSQL kullanıldı.

## 774 inceleme biriminin anlamı

Toplam 1489 kaynak birimi: 774 NEEDS_REVIEW, 521 NO_CLAIM, 194 CANDIDATE. Birimler bağımsız hata veya ayrı OCR bölgesi değildir: balon dışı kayan metin pencereleri örtüşebilir. Bu nedenle 774/1489 doğrudan hata oranı sayılamaz.

| İnceleme grubu | Birim | Anlam |
|---|---:|---|
| NON_STORY_WORLD_SOURCE_REQUIRES_SEPARATE_ANALYSIS | 666 | Öykü dışı içerik, ayrı analiz kapsamı gerekiyor |
| PAGE_PURPOSE_REVIEW_REQUIRED | 10 | Sayfa amacı doğrulanmamış |
| INVALID_OR_MISSING_UNIT_REVIEW | 15 | Model kapsam kaydında eksik/geçersiz birim kararı |
| Diğer narrative kaynak/model gerekçeleri | 83 | Eksik cümle, doğrulanmamış bölge, kimlik/bağlam sınırları |

666 birim, incelemenin yaklaşık %86'sıdır. Amaç dağılımı: FRONT_MATTER/INFORMATIONAL 85; ACTIVITY/EXERCISE 540; INFORMATIONAL/MIXED 20; INFORMATIONAL/INFORMATIONAL 21; UNKNOWN 10; NARRATIVE/STORY_WORLD 98. Dolayısıyla yüksek inceleme sayısının büyük bölümü öykü dışı kapsamın açık muhasebesidir; otomatik olarak kalite gerilemesi değildir. Öykü dışı analizin henüz tamamlanmamış olması yine ürün kapsamı eksikliğidir.

Etkinlik birimleri PDF16=107, 24=99, 35=132, 43=145, 46=41, 47=16. Orta kitaptaki 338 birim ayrıca gerçek kaynak üzerinden incelendi: TEXT_AGREED başlık parçaları ve bağımsız PDF metin katmanı bölüm sonu etkinliklerini, okura kutu hazırlama/robot çizme/hazine avı kurma yönergelerini gösteriyor. Bu üç sayfada narrative reddini yanlış sınıflama sayacak bulgu yok. Ham render SHA kaydedildi; bu kontrol ayrıca görsel render incelemesi yaptığını iddia etmez.

PDF6/12/14/37 UNKNOWN amaçlı fakat sıfır katalog birimli; dolayısıyla 774 sayısında görünmezler. Sıfır birim kaynak kapsamının tamamlandığı anlamına gelmez. PDF48 UNKNOWN 10 birimdir. PDF41 narrative incelemelerinin 10'unda konuşmacı kimliği/bağlam gerekçesi vardır: anonim ve kimlik gerektirmeyen söz edimleri ile kimlik gerektiren iddiaları ayırma kapsamı hâlâ incelenmelidir; otomatik kabul önerilmez.

## Figür–karakter kimliği

Dondurulmuş `audit-identity-blockers.py` gerçek API == bağımsız PG karşılaştırması PASS; korunan önce/sonra kaynak ve inceleme hashleri aynı. Önceki R7 (`382da5b3-a13a-4986-85ba-1a38fd92ff44`) ve yeni nesilde aynı 48 sayfa, 2 balon–figür bağlantısı, 0 kaynakla doğrulanmış isim çıpası, 46 bağlantısız sayfa ve 17 rol kapısına takılan sayfa bulunuyor. Bağlantı düzeyindeki ROLE_GATE gerekçesi 2'den 1'e düşmüş; bu, isim/kimlik doğrulamasının gerçekleştiği anlamına gelmiyor. Yeni nesilde NO_EXPLICIT_ATTRIBUTION=2, MULTIPLE_TAIL_OR_FIGURE=1; kayıtlı CHARACTER_IDENTITY_NOT_GROUNDED=1 ve AMBIGUOUS_TAIL_OR_FIGURE=1.

İsmi kaynaksız figüre atayarak sıfırı artırmak çözüm değildir. Gerekli genel çalışma: metinsel atıf kapsamını aynı figür/balon geometrisiyle bağlayan açık kanıt; yoksa UNKNOWN.

## Kritik yanlış PASS: özne–yüklem ilişkisi

Root'un gerçek 91 uygun iddia içerik incelemesinde PDF27 kesin yanlış PASS bulundu. İddia: “Bilge'nin her gün yeni bilgiler yüklediği ve öğrenmeye bayıldığı belirtilmiştir.” Kaynakta “BEN DE ÖĞRENMEYE BAYILIRIM! BİLGE HER GÜN BANA YEPYENİ BİLGİLER YÜKLÜYOR.” bulunuyor. Öğrenmeye bayılan birinci kişi ile bilgi yükleyen adlandırılmış kişi aynı özne olarak kanıtsız birleştirilmiş. Actor/speaker alanlarının null olması metnin içinde yapılan özne atamasını güvenli yapmıyor. Tokenlerin kaynakta bulunması onların doğru özne–yüklem ilişkisini kanıtlamıyor.

Bu kesin hata mevcut semantik kapıların yeterli olmadığını gösterir; işleme/teknik PASS üretim anlamsal kabulüne çevrilemez. PDF34 özne gönderimi ve PDF28 kapsam/liste aktarımı ayrıca risk adayıdır; kesin hata ile aynı statüde sunulmaz.

Önerilen genel düzeltme: kaynak cümleciklerinden SOURCE token kimliklerine bağlı özne–yüklem–nesne ve konuşma kapsamı ilişkileri çıkarmak; iddia ilişkilerini bunlarla ayrıca eşlemek. Zamir/birinci kişi ile yakın özel ad arasında açık eşgönderim kanıtı yoksa ilişki transferi UNKNOWN olmalı. Kaynak tuple ve iddia tuple aynı model tahmininin iki kopyası olarak bağımsız kanıt sayılmamalı. Literal token, tam kapsam, belirsizlik ve mevcut kimlik kapıları korunmalı. Yeni tam koşudan önce gerçek kaydedilmiş başarısız iddia ve olumlu karşı örnekler üzerinde bileşen kabulü gerekir.

## Kanıtlar

CPU kökü `/data/nanobaseai/editor/evidence/`:

- `identity-blocker-audit-c13d03b1-76be-4fb9-8bef-c123d3c62ce0.json`: yeni nesil gerçek API/PG, korunan hashler.
- `identity-blocker-audit-10377d6a-cfdc-4a94-a1a6-2575cc843380.json`: önceki R7 karşılaştırma.
- `v16-r5-source-unit-review-breakdown.json`: bütün sayfalarda gerçek page_claims/page_context kayıt kimlikleri, neden ve amaç dağılımı.
- `v16-r5-activity-source-readonly.json`: PDF16/24/35 gerçek source_spans + evidence, metin/bbox/render hashleri.
- `v16-r5-eligible-claims-readonly.json`: root'un 91 gerçek uygun iddia içerik denetim girdisi.
- `v16-r5-page-ledger-monitor.json`: önceki 48/48 teknik kaynak/amaç sırası API/PG kabulü; anlamsal kabul değildir.

Bu not veri düzeltmesi, backend değişikliği veya yeni ana koşu içermez. Kitap/sayfa/karakter örnekleri yalnız başarısız gerçek regresyon kanıtıdır; üretim kurallarına özel durum olarak taşınamaz.
