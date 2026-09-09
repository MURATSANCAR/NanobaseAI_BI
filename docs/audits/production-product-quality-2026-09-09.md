# Üretim ürün kalitesi incelemesi — 9 Eylül 2026

Karar: Mevcut kanıtlarla ürünün tamamına üretime hazır onayı verilemez. Satış toplama sorgularındaki ilerleme gerçek; büyük sonuç teslimi, gelişmiş analiz ve doğrulama mekanizmalarında açıklar var. Kullanıcı girişi ve yetkilendirme kapsam dışıdır.

## Kanıt ve sınırlar

- Yerel commit: `50665a6f766c97f0779a8adac325ff7d1cf5b6f9`. İnceleme başlangıcında çalışma ağacı temizdi.
- Canlı semantic bridge aktif; `/health` başarılı. Bridge, compiler ve value_probe dosyalarının SHA256 değerleri yerelle birebir aynı. Sunucu dizini Git checkout değil; sunucu commit'i iddia edilmiyor.
- Üretim API'sine iki yeni soru gönderildi. İlkinde gerçek veritabanı sorgusu yürütüldü; ikinci soru SQL üretilemeden durdu. Ham sonuç satırları kanıt dosyalarına alınmadı.
- Mevcut semantic testleri: **457 geçti, 2 uyarı, 35,73 saniye**. Bu yerel regresyon kontrolüdür; gerçek veri doğruluğu oranı değildir.
- Test komutu: `rtk proxy env PYTHONPATH=backend SEMANTIC_TABLE_SELECTOR=off uv run --python 3.11 --with-requirements backend/requirements-semantic.txt -- python -m pytest backend/semantic_layer/tests -q --disable-warnings --tb=short`.
- Bu turda uygulama kodu/katalog değiştirilmedi, deployment yapılmadı. Ağ kesintisi veya yüksek eşzamanlı yük üretimde zorlanmadı. Arayüz bulguları kaynak ve API sözleşmesinden doğrulandı; tarayıcı testi yapılmadı.

## 1. P1 — Büyük raporun tamamı ürünün dışa aktarım yolunda yok

Canlı soru: “Ocak 2024 için müşteri, ürün, ödeme planı, satış temsilcisi, teslimat şehri ve birim bazında satılan adet göster.”

32,49 saniyede `TEXT_TO_SQL` geldi. `shownRows=50`, `totalRows=500`, `truncated=true`. Aynı `resultId` ile `/api/v1/result/{id}` çağrısı da **500 satır ve truncated=true** döndürdü. Dolayısıyla yalnız ekran sayfalaması söz konusu değil; saklanan yürütme sonucu da kesilmiş.

`backend/semantic_bridge/app.py:728` çalıştırmayı `settings.max_rows` ile sınırlar; `:401` sınırlı kayıtları saklar. Varsayılan sınır `backend/semantic_layer/config.py:38` içinde 500. `backend/semantic_layer/profiler/connectors.py:118` yalnız `limit+1` satır okur.

Etki: Tam rapor talebi ürün içinden tamamlanamıyor. Excel yolu kesik dosyayı işaretliyor; bu doğru bir uyarı fakat eksik sonucu tamamlamıyor. Önceki 100 testteki 7.089–85.703 satırlık kontroller API sonucundan değil, test aracının SQL'i ayrıca 100.000 sınırıyla çalıştırmasından geliyor.

Kapanış: Ekran sınırı ile tam yürütme/saklama sınırını ayırmak; büyük sonuç için disk veya nesne deposunda aynı yürütmeye bağlı dosya üretmek; tablo, grafik ve Excel'i o yürütmeye bağlamak. Sadece `MAX_ROWS` yükseltmek, 64 sonucun bellekte tutulduğu mevcut tasarımda yeterli çözüm değil. Kabul: gerçek DB'de 500'den fazla satır üreten sorgunun indirilen dosyasının referansla satır ve kolon bazında eşleşmesi.

## 2. P1 — Aylık müşteri sıralaması ve önceki aya göre değişim çözülemiyor

Canlı soru: “2026 yılında her ay için müşterileri net satış tutarına göre sırala ve her müşterinin önceki aya göre yüzde değişimini göster.”

**52,62 saniye sonra NON_SQL_QUERY** döndü. `degisimini` kelimesi için `ETK_URUNLER.FIYAT_DEGISIM_TARIHI` önerildi. İzde “önceki ay” her satırın önceki ayı yerine Ağustos 2026 olarak çözülmüş; karşılaştırma Ağustos 2026 ile tüm 2026 arasında kurulmuş. Müşteri kırılımı `groupBy=[]` olarak kalmış.

Bu, veri eksikliği kanıtı değil; soru şeklinin yanlış anlaşılmasıdır. Yanlış sayı döndürülmediği için güvenli durma çalışıyor, fakat istenen ürün yeteneği mevcut soruda çalışmıyor. Sekiz tabloyu JOIN edebilmek, pencere fonksiyonu ve dönemler arası analiz desteğini kanıtlamıyor.

Kapanış: Satırın önceki dönemini takvimdeki “geçen ay”dan ayıran analiz planı; müşteri/ay kırılımı; sıralama ve LAG gereksinimlerinin açık doğrulanması; sıfır/eksik önceki ay için belirli davranış. Kabul: gerçek veride bağımsız aylık müşteri referansıyla tam karşılaştırma. Kelimeyi fiyat tarihi kolonuna bağlayan yeni sözlük kaydı eklemek doğru çözüm değil.

## 3. P1 — Mevcut başarı ölçümü yanlış eşleşmeyi kabul edebiliyor

`tests/stress/enduser_live_10000.py:16` içindeki `norm`, her satırdaki değerleri ayrıca sıralıyor. Böylece kolon kimliği kayboluyor. Gerçek fonksiyon ayrı olarak çalıştırıldı: `['İstanbul','Ankara',12]` ile `['Ankara','İstanbul',12]` **eşit kabul edildi**. Bu, karşılaştırıcının testi; gerçek DB'de bu yanlış cevabın üretildiği iddiası değildir.

Ayrıca `:91` API'nin `physicalSql`/saklanan sonucu yerine `r._physical(a['sql'])` ile yeniden yürütme yapıyor. Test doğrulama anı, dönem bağlamı ve ürünün sunduğu sonuç ayrılaşabiliyor.

Kapanış: Beklenen boyutlara açık kolon eşlemesi; satır sırasını önemsizleştirirken kolon rollerini koruma; NULL, boş metin ve sayısal toleransın ayrı tanımlanması; API yürütmesi ile referansın aynı kapsamda karşılaştırılması. Önceki 100/100, bu boşluklar kapandıktan sonra yeniden doğrulanmalı; ürün geneli doğruluk sertifikası değildir.

## 4. P1 — Yayın kalite kontrolü ölçülmemiş oranlarla tam geçiş veriyor

`tools/release-gate/run_quality_benchmark.py:99` içinde sonuç eşdeğerliği 0,95, iş cevabı doğruluğu 0,96 ve bazı diğer başarılar sabit atanıyor. `:140` tam geçişi korpus sayısı ve bu değerlere göre hesaplıyor.

Bu turda `run_offline_eval('audit-readonly')` çalıştırıldı: **mode=offline_inventory, fullPass=true, failures=[]**. Gerçek LLM veya müşteri SQL'i çalıştırılmadı. `.github/workflows/release-gate.yml` bu programı `--require-full` ile kullanıyor. Normal uygulama CI'si artık mevcut; sorun CI yokluğu değil, bu özel kalite kapısının kanıt niteliği.

Kapanış: Ölçülmeyen metrik UNKNOWN olmalı ve tam kalite geçişini engellemeli. Ölçümün veri kaynağı, kod/katalog sürümü, soru kimliği, API yanıtı ve referans karşılaştırması kanıtlanmalı. Korpus envanteri ayrı, canlı doğruluk ayrı raporlanmalı.

## 5. P2 — Sonucun açıklaması ve grafiği çok boyutlu cevabı doğru temsil etmiyor

İlk canlı sorunun özeti “500 satır döndü” diyor; kesilme bilgisini taşımıyor. İlk üç satır özeti ilk dört kolonu seçtiği için altı boyuttan sonra gelen `satilan_adet` metriğini hiç göstermiyor; `None` metinleri görülebiliyor.

Kaynak: `backend/semantic_layer/runtime/compiler.py:1671` ve `backend/semantic_bridge/app.py:538`. Widget `x_key=bir`, `y_key=satilan_adet` seçiyor. Oysa her satır birimin yanında müşteri, ürün, temsilci, şehir ve ödeme planıyla tanımlanıyor. `apps/cockpit/src/components/ResultChart.tsx:178` diğer boyutları taşımadan noktalar üretir. Aynı “adet” etiketi altında farklı kesitler gösterilebilir; bu birim toplamı değildir.

`apps/cockpit/src/components/CopilotPanel.tsx:47` önbellek yaşını alıyor fakat cevap kartında göstermiyor; kesilme bilgisi de ana cevap metninde kullanılmıyor.

Kapanış: “En az 500 satır; sonuç sınırda kesildi” gibi doğru kapsam; özetin ölçü kolonlarını seçmesi; çok boyutlu sonuçta tabloyu tercih etmek veya boyutları açık seçerek yeniden toplamak; önbellek zamanı ve veri kapsamını cevapta görünür kılmak.

## 6. P2 — Büyük sorgular arka planda tekrar çalışıp önbelleğe girmiyor

Kaynak: `backend/semantic_bridge/app.py:448`, `:468`, `:508`, `:511`, `:531`.

200'den fazla satır içeren sonuç `_remember` içinde hemen geri döner. Ancak sorgu sıcak listeye önceden alınmıştır. Süresi başlangıçta 0 kalır; önbellekte kayıt olmadığından `cached_at=0` olur. Tazeleyici bu sorguyu tekrar seçer; sonuç yine saklanmaz. Kullanıcıya önbellek yararı sağlamayan tekrarlar tek DB yürütme kilidini işgal edebilir. Canlıda tazeleyici açık, aralık 15 saniye; ilk incelenen sorgunun SQL yürütmesi 31,3 saniye sürdü.

Kanıt türü: Canlı ayar ve sorgu süresi + doğrulanmış kaynak kontrol akışı. Ayrı yük testi yapılmadı; eşzamanlı kullanıcı gecikmesinin sayısal büyüklüğü ölçülmedi.

Kapanış: Saklanmayacak sonucu otomatik yenileme listesinden çıkarmak veya uygun depolama kullanmak; süre/başarısızlık bilgisini saklama kararından bağımsız güncellemek; aynı sorguyu tek uçuşta çalıştırmak. Kabul: gerçek DB'de aynı büyük raporun birden çok kullanıcısı için kontrollü eşzamanlılık ve p95 ölçümü.

## 7. P2 — Değer araması ortak DB bağlantısının kilidini ve kısa bütçesini korumuyor

Bridge `:249` ValueProbe'a aynı connector'ı veriyor. Normal yürütme `:371` ve dry-run `:325` kilitli. `backend/semantic_layer/runtime/value_probe.py:152` ise doğrudan `search_values` çağırıyor; connector içinde bu yol da aynı `_conn` üzerinden ilerliyor.

Probe'un altı saniyelik varsayılan bütçesi sorguya girmeden önce kontrol ediliyor (`:116`); devam eden DB sorgusunu kesmiyor. Connector sorgu zaman aşımı varsayılan 120 saniye. Dolayısıyla “altı saniyelik arama” tek başına altı saniyede bitme garantisi değil.

Kapanış: Ayrı salt-okunur probe bağlantısı/havuzu ya da tüm erişimlere ortak kilit; kalan bütçeyi DB sorgu süresine uygulamak. Üretimde bağlantı yarışını zorlayıp hata üretmedim; bu bulgu kaynak düzeyinde eşzamanlılık ve süre sınırı açığıdır.

## 8. P2 — Canlı iş anlamı kapsamı hâlâ eksik

Bu turdaki `/api/v1/schema/inventory?columns=false` ölçümü:

| Ölçüm | Değer |
|---|---:|
| Fiziksel tablo | 4.121 |
| Kolon | 129.574 |
| UNDEFINED kolon | 87.721 |
| Açıklaması ve tablo portal notu olmayan tablo | 3.060 |
| CERTIFIED kavram | 104 |
| CANDIDATE kavram | 556 |

UNDEFINED, endpoint'in açıklama/portal notu/sertifikalı kavram ölçütüdür; indeks dışında olma anlamına gelmez. Tüm teknik kolonların iş sözlüğüne girmesi zorunlu değil; bu toplamlar tek başına hata oranı değildir. Ancak “tüm kolonlar indekslendi” ile “iş anlamları tamamlandı” aynı iddia değildir.

Kapanış: Kullanılacak iş akışları için kritik tablo/kolon, metrik bazı, tarih, para birimi, birim dönüşümü ve ilişki tanımlarını önceliklendirmek; her tanımı gerçek veri sorusuyla doğrulamak. Açıklaması olmayan alanlara tahmini anlam yazmak kalite çözümü sayılmaz.

## 9. P2 — Katalog sürüm kimliği canlı içerikle birebir örtüşmüyor

Canlı envanterde CERTIFIED=104; son katalog snapshot'ı sürüm 12 ve certified_count=88. Yeni sorular da catalogVersion=12 bildiriyor. Parmak iziyle yeniden yükleme var; bu nedenle eski katalog servis ediliyor sonucu çıkarılmamalı. Sorun, tek sürüm numarasının sonradan değişen içerikleri ayırt edememesi.

`backend/scripts/register_enduser_dimensions.py:75` ve `register_enduser_net_sales.py:27` kavramları değiştiriyor; sorgu logu bridge `:750` içinde katalog sürümünü yazıyor. Kavram sürümü ile katalog snapshot sürümü farklı şeylerdir.

Kapanış: Tanım güncellemesini yeni değişmez katalog snapshot'ıyla atomik yayınlamak; sorguya snapshot/content hash eklemek. Böylece yanlış cevap ve regresyon aynı içerikle yeniden üretilebilir.

## Kapanmış olanlar ve önerilen sıra

Önceki rapordaki benzer sorunun SQL'ini doğrudan çalıştırma sorunu `chat_gateway.py:767` kontrolüyle engellenmiş. Kokpit `/ask` yanıtını kullanıyor; reddedilen SQL'i otomatik yeniden çalıştırmıyor. Normal uygulama CI'si var. Bunlar bu raporda yeniden açık sayılmadı.

Öncelik: (1) doğrulama karşılaştırıcısı ve gerçek kanıt isteyen kalite kapısı, (2) tam sonuç teslimi ve doğru sunum, (3) gelişmiş analiz planları, (4) yenileme/bağlantı bütçeleri, (5) kritik iş kapsamı ve sürümlü katalog. Yayın kararı bu kapanışların gerçek DB kanıtına dayanmalı.

Kanıt dosyaları: `outputs/production-quality-audit-20260909/live-evidence.jsonl`, `complex-analytic-evidence.jsonl`, `live_probe.py`. Önceki 100 soru: `outputs/enduser-complex-100-20260909/final-list.json`.
