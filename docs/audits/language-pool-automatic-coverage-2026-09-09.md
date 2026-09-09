# Tüm katalog için otomatik ifade bakımı — 2026-09-09

## Kapsam

Bağlı kaynakların katalog metaverisinden, yapılandırılmış `nanobaseai-bi-llm`
modeliyle ifade üretimi ve ayrı eleştirel inceleme yapılıyor. Kullanıcı kayıtları
ve örnek değerler LLM girdisine eklenmiyor. İfadeler aramayı güçlendiren adaylardır;
SQL, ölçü veya iş kuralı sertifikasyonu yapılmıyor.

- 4.874 fiziksel profil; 150.052 fiziksel kolon kaydı.
- 2.281 mantıksal tablo; 59.393 hassas olmayan mantıksal kolon.
- Açıklaması bulunan mantıksal kolon: 17.619.
- Hassas olduğu için hariç tutulan fiziksel kolon kaydı: 3.252.
- Tüm hedefler için 8.440 üretim grubu. Bütün matematiksel kombinasyonlar üretilmez.

Gerçek SQL Server üzerinde `LOGO_DB` ve katalogdaki üç parçalı kaynak adlarıyla
`Timas_MSCRM` metaverisi okundu. 150.052 katalog kolonunun tamamı gerçek kaynakta
bulundu; sorgu kesilmedi. İlk karşılaştırma yalnız varsayılan DB'yi taradığı için
CRM kolonlarını eksik göstermişti; tam kaynak adlarıyla tekrar kontrol edildi.
Bu işlem tablo verisi sayısal kabulü değil, gerçek kaynak/şema eşleşmesidir.

## Uygulama

- Her kolon `PENDING`, `GENERATED`, `NEEDS_DEFINITION`, `RETRY_EXHAUSTED`
  durumlarından biriyle izlenir. Hassas kolonlar ayrı listelenir.
- Her grupta hedeflerin tamamı takip edilir. Birkaç aday çıkması grubun tamamını
  otomatik olarak başarılı yapmaz.
- Metadata, açıklama, ilişki, üretici/inceleyici talimatı ve model kimliği iş
  anahtarına dahildir. Değişen kaynak yeniden planlanır.
- Aynı çıktı/checkpoint dosyası kilitlenir. Yarım kalan işler devam eder.
- Üretim sonrasında LLM inceleyicisi bağlamdan kopuk veya desteklenmeyen birleşimleri
  reddeder; yalnız kabul edilenler şema doğrulamasından geçerek havuza yazılır.
- Havuz atomik yayımlanır; tur sırasında katalog değişmişse yayın engellenir.
- Kapasite sınırı 200.000 aday/256 MiB. Sınır veya hata, kapsam tamamlandı sayılmaz.
- Kullanıcı soruları mevcut LLM kuyruğunda bakımın önüne geçer; arka plan bekleme
  sınırı dolunca kuyruğu aşarak LLM çağırmaz.

## Gerçek deneme ve düzeltme

İlk gerçek üretim 4 grupta 48 aday çıkardı. İncelemede bağlamsız kısa ifadeler ve
ilgisiz kolon birleşimleri görüldü. Bu pilot aktif API havuzuna bağlanmadı;
kanıtları arşivlendi ve eklenen adaylar aday dosyasından çıkarıldı.

İkinci LLM incelemesi eklendikten sonra yeniden gerçek modelle çalışıldı:
2 grup, 24 adaydan 22 kabul ve 2 ret. 16 hedef kolon kapsandı. Önceki 55 aday
korunarak aktif havuz 77 oldu. Gerçek dağıtım runtime'ı 77 adayı yükledi;
22 yeni ifadenin tamamı aramada kendi kaydını geri getirdi, geçersiz/eski aday yoktu.

İlk yayın havuz hashi:
`d02b343615116845496bf85f5eb8eb4d0812e740f8fd983adf3ac0f19a94e60b`.
Bu kontrol arama kanıtıdır; iş sonucu doğruluğu değildir.

## Yayın ve işletim

Aktif dosya: `/data/nanobaseai/bi/var/language-pool/active.json`.
Checkpoint: aynı dizinde `active.maintenance.json`.
Tam kolon raporu: `active.coverage.json`.
Bakım servisi: `nanobase-language-pool.service`; zamanlayıcı: aynı adlı `.timer`.
Kurulum betiği: `scripts/server/deploy-language-pool-worker.sh`.
Ana semantic bridge kurulumuna da çağrısı eklendi.

Gerçek üretim API'sinde 10 soru çalıştırıldı: **3 başarılı, 2 başarısız,
5 DOĞRULANAMADI**. Koşu boyunca aktif havuz dosyası değişmedi. İki başarılı veri
sorusunun API tam sonucu bağımsız `LG_SLSMAN` referanslarıyla kolon kimlikleri,
satır sayıları ve değerler bakımından eşleşti. Üçüncü başarı, `test` mesajının SQL
üretmeden `MODULE_INTRO` dönmesidir.

İki yeni ifade aramada bulundu, fakat resolver `oluşturan` ve `zaman` sözcükleri
hakkında anlamsız netleştirme istedi. Bu iki soru **başarısızdır**; ifade araması
başarısını uçtan uca ürün başarısı olarak göstermiyoruz. Bu resolver sorunları
bu bakım değişikliğiyle düzeltilmedi.

Dört çok tablolu sorgu ve bir dönem karşılaştırması gerçek DB'de yürüdü. Ancak
yedek seçimi için geçerli bağımsız iş referansı olmadığından sayısal doğrulukları
**DOĞRULANAMADI**. API'nin aynı yürütmelerine ait tam sonuçlar okundu. Tüm veri
sorularında toplam 217,344 sonuç satırı, 155,247 NULL hücre görüldü; tam sonuçlar
kesilmedi. Bu koşuda sıfır sayısal hücreye rastlanmadı; sıfır değer davranışı için
yeni kapsam kanıtı sayılmıyor.

[Sorular, statüler ve üretilen SQL](../../outputs/language-pool-auto-20260909/api-prompts-status-sql.md).
Sonuç kayıtlarını içermeyen kanıt JSON'u ve hashler aynı dizinde tutuluyor.

Zamanlayıcı üretimde etkinleştirildi. Bakım servisi aynı checkpoint üzerinden
çalışmayı sürdürüyor; yeni turların ürettiği havuzları bu ilk 77 adaylık API koşusuyla
sayısal olarak doğrulanmış saymayın.

## Açık sınırlar

Tüm hedefler henüz üretilmedi. İlk incelemeli tur sonunda 59.377 hedef bekliyordu.
Mevcut açıklamalarla anlamı belirlenemeyen kolonlar için model anlam uydurmaz;
inceleme gerektiren durum rapora yazılır. Modelin değerlendirmesi hatasızlık garantisi değildir.

Tek şirketin yedeklerini hangi dönemlerde kullanacağımız ve örtüşen kayıtları
hangi kaynaktan alacağımız, ifade üretiminden çıkarılmaz. Önceki ayrı-firma
varsayımını kullanan 100 soruluk referans tekrar kabul kanıtı olarak kullanılmadı.

Yerel birim testi, mock, fixture veya sentetik DB çalıştırılmadı. Gerçek kaynak
kontrolleri ve API kabulü sunucuda yürütülür. Kanıt dizini:
`outputs/language-pool-auto-20260909/`; sunucu arşivi:
`/data/nanobaseai/bi/backups/language-pool-auto-20260909/`.


## İşletim doğrulaması

Zamanlayıcı `enabled/active`. Servis tamamlanan `NEW_URETIMBASE` ve
`NEW_KITAPBASE` gruplarını atlayarak `CONTACTBASE` ile devam etti; sonraki grupta
8 hedef kolon için 12 yeni aday checkpoint'e yazıldı. Bunlar ilk 77 adaylık
kabul havuzunun dışında, sonraki yayını bekleyen adaylardır. Eşzamanlı `--plan-only`
isteği LLM çağrısı başlamadan kilit nedeniyle reddedildi. Kabul sonrasında izlenen
kod dosyalarında değişiklik bulunmadı.

Operasyon kanıtı: `maintenance-operation.json`. İlk yayın kapsam raporu:
`coverage-first-publication.json`. Bu rapor anlık tüm-katalog tamamlanma iddiası
olarak okunmamalıdır; güncel durum sunucudaki checkpoint/kapsam dosyalarındadır.
