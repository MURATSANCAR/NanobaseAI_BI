# Görsel bölge kapsamı: genel aday düzeltme ve gerçek ölçüm

## V8 gerçek entegrasyon kabulü — 14:22 UTC

`narrative-coverage-v8-20260917` stage API 18810'da, nesil `7e7db466-3576-4c23-85b2-73483ab4508e` gerçek 2/13/29. sayfaları üzerinden API/PG ve ebeveyn ham kaynak eşliğiyle doğrulandı. Gözlemlenmemiş bölge sayıları 5/1/0; 13. sayfa simgesi artık kapsam eksikliği olarak kaydediliyor. Büyük bölge gözlemleri ve ham okuyucu verileri korundu. `whole_page_visual_coverage` ve `figure_coverage` hâlâ `NOT_VERIFIED`; kimlik kabulü verilmedi. Üç sayfalık entegrasyon kontrolü geçti, genel kitap anlamsal kabulü açık.

Kanıt: `/data/nanobaseai/editor-qualifications/source-boundaries-v4-r2-20260917/99881d8f/installation/evidence/narrative-coverage-integration-20260917T142236Z.json`. Doğrulayıcı kaynak veya karar yazmadı; dağıtımı bu alt görev yapmadı. Aşağıdaki aday geliştirme/dağıtılmamış durumu, V8 öncesi tarihçedir.

## Durum ve sınır

17 Eylül 2026: kod adaydır, çalışan V7 yayınına kurulmadı. Gerçek 48 sayfanın API/PostgreSQL kayıtları üzerinde seçim ve kapsam hesabı doğrulandı; yeni görsel model çağrısı yapılmadı. Görsel kimlik, konuşmacı veya kitap analizi kabulü verilmedi. Kitap metni, figür adı ve inceleme kararları değiştirilmedi.

## Somut hata

`source_pipeline.observe`, yalnız alanı sayfanın %6'sından büyük `PICTURE` bölgelerini listeleyip ilk üçünü işlerken `omitted_regions` değerini de bu daraltılmış liste üzerinden hesaplıyordu. Küçük bölgeler gözlemlenmediği hâlde atlanan bölge sayısı sıfır görünebiliyordu. Docling'in bölgeleri de tam sayfa görsel kapsamının kanıtı değildir.

Gerçek 13. sayfanın özgün render'ı görsel olarak incelendi. Sayfa metin ağırlıklıdır; solda kesilmiş komşu illüstrasyon parçaları vardır. Kayıtlı tek `PICTURE`, alt bölümdeki sayfa numarası simgesidir: `#/pictures/18`, bbox `[0.47633032995043884, 0.871144512899561, 0.03995936950240242, 0.0465255438112745]`. Alan yaklaşık %0,186'dır. Mevcut gözlem boş, `omitted_regions=0` idi. Bu bölgede tam karakter figürü bulunduğu veya metindeki adın bir figüre bağlandığı söylenemez. Simgeyi modele okutmak konuşmacı kimliği çözümü değildir.

## Genel kod değişikliği

- Yeni `apps/editor/backend/editor/visual_coverage.py`: mevcut büyük bölge seçimi, layout sırası ve üç bölgeli inference bütçesi korunur. Küçük bölgelere otomatik model çağrısı eklenmez.
- Bütün ilan edilmiş `PICTURE` bölgeleri kayda girer. Eksikler `BELOW_MINIMUM_AREA`, `INVALID_REGION_GEOMETRY`, `REGION_BUDGET_LIMIT`, `OBSERVATION_MISSING` olarak ayrılır. Eşik/bütçe dışında kalanlar silinmez.
- `whole_page_visual_coverage` ve `figure_coverage` açıkça `NOT_VERIFIED` kalır. İlan edilmiş bölgelerin gözlemlenmesi sayfanın eksiksiz anlaşılması değildir.
- `observe` mevcut ham gözlemleri korur; seçili fakat gözlemi bulunmayan kırpımları yeni nesilde ayrıca işler. Yeni figür çıktılarında dört figür sınırına ulaşılması ve atılan aday sayısı kaydedilir. Önceki model metrikleri yeni model çağrısı gibi gösterilmez.

Kodda kitap adı, sayfa numarası, karakter adı, beklenen cevap veya kaynak hash'iyle çalışan özel koşul yoktur.

## Gerçek salt okunur kabul

Yürütme ortamı: sunucu üzerinde, konteyner dışında aday yardımcı fonksiyon; gerçek stage HTTP API `127.0.0.1:18810` ve ayrı PostgreSQL. Çalışan V7 tamamlanmamış olduğundan tam 48 sayfalık değişmez ebeveyn `8c780a30-fc9b-4ad7-a576-317e6142ad3f` kullanıldı. Yerel test, mock veya sentetik kitap yok.

| Kontrol | Sonuç |
|---|---:|
| Gerçek layout/visual API–PG eşliği | 48/48 |
| Bağımsız seçim ve kapsam hesabı eşliği | 48/48 |
| Korunan eski büyük bölge | 19 |
| Küçük bölge yüzünden dışlanan eski büyük bölge | 0 |
| Son politikada ek inference kırpımı | 0 |
| Mevcut gözlemlerde açıkça raporlanan gözlemlenmemiş bölge | 52 |
| Yeni inference / kaynak veya karar yazımı | 0 / 0 |

13. sayfa aday kapsamı artık `BELOW_MINIMUM_AREA` nedeniyle bir gözlemlenmemiş bölge ve `INCOMPLETE` gösterir. İlk deneyde kaynak/ölçüm kayıtlarının önce/sonra eşliği tekrar denetlendi. Son politikanın gerçek 48 sayfa API/PG eşliği ve bağımsız kapsam hesabı ayrıca geçti.

**Reddedilen alternatif:** büyükleri koruyup boş bütçeyi küçüklerle doldurmak 37 sayfada 50 yeni model kırpımı ekleyecekti. 52 küçük bölgenin alanları %0,0549–%5,6286 arasında; örnek 13. sayfa yalnız numara simgesidir. Bu maliyeti kimlik kanıtıyla gerekçelendiren kabul olmadığı için otomatik küçük-kırpım politikası alınmadı. Eski 19 büyük bölge korunarak 52 küçük bölgenin tamamı açık kapsam eksikliği olarak kaydedilir.

Son aday yardımcı dosya SHA-256: `88d3c2e3102e706f1bf78fbfa1aa353f28844a1d9c5114d5057fc01a97cac6e0`.

Kalıcı sunucu kanıtı:
`/data/nanobaseai/editor-qualifications/source-boundaries-v4-r2-20260917/99881d8f/installation/evidence/visual-coverage-candidate-20260917T141434Z.json`.

Bu ilk kanıt boş slotları dolduran reddedilmiş politikanın ölçümüdür; önceki SHA `6866ad335b1ff20ec7d63c353e2a0b5441b4c2e48a3c7f201276e6fa52330f71` olarak korunur. Son politika kanıtı aynı dizinde `visual-coverage-explicit-exclusions-20260917T141602Z.json` dosyasıdır.

Bu kabul yalnız saf bölge seçimi/kapsam hesabınındır. `observe` entegrasyonunun yeni nesil gerçek model çalışması, çalışma süresi ve üretim kabulü henüz **DOĞRULANAMADI**. Çalışan V7 durdurulmadı veya değiştirilmedi.

## Gerçek arayüz kabulü

V8 web imajı `nanobase-editor-web:visual-coverage-v8-20260917` ayrı gateway'e kuruldu. Gerçek eski V7 kaydında kapsamın ölçülmediği uyarısı ve yeni V8 kaydında API'deki toplam/eksik bölge sayıları 320/390/768/1440 px üzerinde birebir denetlendi; altı sekmede yatay taşma yok. Figür dizisi boşken boş paragraf yerine gözlem kaydedilmediği gösterilir. Kanıtlar `evidence/visual-coverage-web-verification-explicit.log` ve `evidence/narrative-coverage-v8-ui.log`. Backend 39 dosya hash `4560e0701e5027969a087a46b4ca915df047e13a890f80ec599250102521333c`; web kaynak/çıktı hash eşliği `evidence/narrative-coverage-v8-release.log`. Bu ayrı ortam kabulüdür; ana yayın halen V5'tir.
