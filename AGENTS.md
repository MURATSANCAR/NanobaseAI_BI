# Çalışma kuralları

@/Users/msancar/.codex/RTK.md

## Ürün tasarımının ana kuralı: mobil uyumluluk

Kullanıcının açık talebi: bu projede yaptığımız bütün tasarımlar mobil öncelikli ve mobil uyumlu olmalı. Bu, yalnız kokpit için değil giriş, modüller, GIF/görseller, menüler, tablolar, grafikler ve tüm yeni arayüzler için geçerlidir.

320px, 390px, 768px ve masaüstü genişliklerinde ilgili akışları tarayıcıda kontrol edin. Sayfa yatay taşmamalı; geniş tablo/kod yalnız kendi kapsayıcısında kaymalıdır. Mobil kontroller dokunulabilir, metinler okunabilir olmalı; temel özellikler mobilde erişilebilir kalmalıdır. Taşmayı sayfa düzeyinde overflow:hidden ile gizlemeyin.

## Zorunlu ürün doğrulama kuralı: bağlı gerçek DB ile test

Kullanıcının kalıcı talebi: ürünün veri alma, SQL üretme, hesaplama, raporlama veya sonuç sunma davranışını etkileyen her değişiklik, bağlı gerçek veritabanı ve gerçek uygulama/API akışı üzerinden doğrulanmadan tamamlanmış veya üretime hazır sayılmaz.

- Kullanıcının açık yasağı: testleri yerel çalışma ortamında çalıştırmayın. Kullanıcı ayrıca açıkça istemedikçe yerel birim testleri, mock, fixture, SQLite veya kontrollü/sentetik veriyle test koşusu başlatmayın. Önceki yerel regresyon izni bu kuralla kaldırılmıştır.
- Ürün testlerini bağlı gerçek DB'yi kullanan gerçek uygulama/API ortamında yürütün. Bağımsız referans hesapları da aynı bağlı gerçek DB üzerinde yapılmalıdır. Yerelden bir uzak koşuyu yönetmek, testin yerel veya yapay veriyle çalıştırılması anlamına gelmez; raporda yürütme ortamını, API'yi ve gerçek veri kaynağını açıkça belirtin.
- Gerçek DB kabulü yerine yerel test sayısı sunmayın. Kullanıcının ayrıca istediği bir yerel test varsa sonucunu gerçek DB kabulünden ayrı gösterin; hiçbir şekilde üretim doğruluğu kanıtı saymayın.
- Etkilenen akışları basitten karmaşığa doğru sınayın. SQL/semantik katman ve katalog değişikliklerinde çok tablolu sorguları; ilgiliyse 7–8 tablolu JOIN, dönem karşılaştırması, NULL/sıfır değerler ve büyük sonuçları kapsayın. Mevcut 100 karmaşık soru setini ilgili geniş regresyonlarda kullanın; yeni doğrulanmış hata senaryolarını sete ekleyerek kapsamı geliştirin.
- Başarıyı yalnız SQL'in çalışmasına göre vermeyin. Gerçek API'nin kullanıcıya sunduğu aynı yürütmenin tam sonucunu, bağımsız referans sorgu/hesapla karşılaştırın. Kolon kimliklerini, satır sayısını, sayısal değerleri ve kesilme bilgisini kontrol edin. Uygulamanın ürettiği SQL'i yeniden çalıştırmak, uygulamanın verdiği cevabı doğrulamak yerine geçmez.
- Tablo, grafik veya dışa aktarım değiştiyse ilgili gerçek kullanıcı akışını da doğrulayın. Önizleme sınırını tam sonuç sınırıyla karıştırmayın.
- Düzeltme sonrası başarısız senaryoyu yeniden çalıştırın. Test edilen kod/katalog sürümünü veya içerik hashlerini, soru kimliğini, sonucu ve kanıt dosyalarını kaydedin. Sonradan değişen kodu önceki testlerle doğrulanmış saymayın.
- Uzun soru koşularında her 10 tamamlanan soruda başarı, başarısızlık ve doğrulanamayan sayısını paylaşın. Sonda soru listesi, statüler, uygulanan çözümler ve açık kalanları verin.
- Gerçek DB/API erişimi yoksa veya bağımsız referans bulunamıyorsa durumu açıkça **DOĞRULANAMADI** olarak raporlayın; başarı veya tamamlanma iddiasında bulunmayın. Tahmini iş tanımlarıyla eksikleri kapatmayın.
- Gerçek veri testlerini salt okunur ve kontrollü yükle yürütün; aynı ağır koşunun birden fazla kopyasını başlatmayın. Canlı kabul sonucu, doğrulanan yayın sürümüne ait olmalıdır.

Bu bir çalışma/kabul kuralıdır; zamanlanmış otomasyon talebi değildir. Yalnız dokümantasyon gibi ürün davranışını etkilemeyen değişikliklerde gerçek DB sorgusu çalıştırmak gerekmez.

## Bu kurulumun veri anlamı: tek şirket, yıllara ait yedekler

Kullanıcının 2026-09-09 düzeltmesi bağlayıcıdır: tek şirket vardır; farklı veritabanları şirketin yıllar içinde alınan yedekleridir. `411`, `211` gibi teknik kodlardan ayrı firma/şirket üretmeyin, kullanıcıya bu kodlarla şirket seçtirmeyin. Fiziksel nesne adları korunabilir; teknik kaynak kimliğini iş anlamındaki şirket kimliğiyle karıştırmayın.

Veritabanı–yedek tarihi–işlem dönemi eşlemesi ve örtüşen kayıtlarda esas alınacak kaynak doğrulanmadan yedekleri bağımsız şirketler gibi toplamayın. Sırf SQL sonuçları aynı çıktı diye yanlış kaynak varsayımına dayanan bir referansı iş doğruluğu kanıtı saymayın. Önceki ayrı-firma varsayımı ve bu varsayıma dayanan kabul yorumları geçersizdir.

## Tek branch kuralı: yalnız main

Kullanıcının 2026-09-13 kararı bağlayıcıdır: bu depoda tek trunk `main`'dir. Diğer bütün dallar (`perf/full-overhaul-2026-08` dahil) `main`'e merge edilip silindi. Bundan sonra:

- Yeni iş doğrudan `main` üzerinde yapılır veya `main`den açılan kısa ömürlü bir dal `main`e merge edilir edilmez silinir. Kalıcı ikinci bir uzun ömürlü dal (ör. `perf/*`, `dev`) açılmaz.
- Kalıcı bir dalda "birikmiş iş" bırakılmaz: bir dalda duran commit, `main`de olmadığı sürece kimse tarafından kurulmaz, denenmez ve bir sonraki iş onun üstüne gelmez.

### Her geliştirme bitiminde: main'e taşıma (zorunlu adım)

İş bittiğinde — commit atıldıktan ve [CLAUDE.md](CLAUDE.md)'deki belge güncellemesi yapıldıktan sonra — kullanıcı istemese de şu tur koşulur. Uygulama bir `claude/*` dalı ya da worktree açtıysa bile iş orada bırakılmaz.

```bash
# 1. main'i tazele, üstüne otur (çakışma varsa çözülür; günlük dosyasında iki giriş de korunur)
git fetch origin && git rebase main

# 2. main'e ileri sarma ile taşı — ana depo başka bir dizinde olduğu için -C ile
git -C <ana-depo-yolu> merge --ff-only <dal-adı>

# 3. yayınla ve dalı iki yerden birden sil
git -C <ana-depo-yolu> push origin main
git push origin --delete <dal-adı>
git branch -d <dal-adı>
```

- **Taşınmamış iş var mı**, her turun sonunda buradan bakılır; sayı 0 değilse o dal da aynı turdan geçirilir:

  ```bash
  for b in $(git for-each-ref --format='%(refname:short)' refs/heads/ refs/remotes/origin/); do
    echo "$(git rev-list --count main..$b)  $b"
  done
  ```

- Push kimliği bulunmayan bir oturumda (`could not read Username for 'https://github.com'`) merge yerelde tamamlanır, kalan iki komut kullanıcıya **açıkça** bırakılır; "merge edildi" denip origin'de bırakmak olmaz.
- Merge, dağıtımın yerine geçmez: sunucuya kurulan sürüm neyse `main` de o olmalıdır. Sunucuya yama atılıp `main`e girmemiş kod bırakılmaz.
- Bu kural bir talimattır, hook değil — CI/branch-protection ile zorlanmıyor; oturumdaki Claude'un ve kullanıcının uygulamasına bağlıdır.

## Dağıtım sırası: main → test sunucusu → müşteri VM'i (zorunlu)

Kullanıcının 2026-09-23 kararı bağlayıcıdır. Bir değişiklik müşteri ortamına ancak şu üç adım bu sırayla
tamamlandıktan sonra gider; adım atlanmaz, sıra değişmez:

1. **main'e merge.** `main` dışındaki bir dalda ya da worktree'de duran kod kurulmaz — ne test sunucusuna
   ne müşteri VM'ine. Önce «Her geliştirme bitiminde: main'e taşıma» turu koşulur. Sunucuya atılıp `main`e
   girmemiş yama bırakılmaz; bir sonraki `git archive main` dağıtımı onu sessizce ezer ve hata geri gelir
   (2026-09-22'de üç OCR düzeltmesi tam olarak böyle kaybolmuştu).
2. **Test sunucusunda eksiksiz kurulum ve doğrulama.** Yapının tamamı (arka uç, köprü, arayüz derlemesi,
   varsa göç ve ters vekil yolları) test sunucusuna kurulur ve gerçek veriyle, gerçek oturumla denenir.
   Yarım kurulum — «arka ucu koydum, arayüzü sonra» — doğrulama sayılmaz.
3. **Sonra müşteri VM'i.** Yalnız test sunucusunda çalıştığı görüldükten sonra, kaynak olarak `git archive
   main` kullanılarak kurulur (VM'in canlı ağacında git dışı env/sır dosyaları vardır, o ağaç kaynak olamaz).

Bir şey test sunucusunda doğrulanamıyorsa (ağ kapalı, VPN düşük, servis erişilemez) müşteri VM'ine
kurulmaz; doğrulanamadığı günlüğe yazılır ve iş bekler. «Test sunucusunda deneyemedim ama VM'de çalışır»
gerekçesiyle kurulum yapılmaz.

### Kurulumda dosya taşıma: Mac artığı ve yanlış imaj (zorunlu)

Kullanıcının 2026-09-23 talimatı. İki hata sessizce yanlış şeyi sunucuya koydu; ikisi de kurulum
bitmeden yakalanmalı:

1. **Mac artığı (`._ad`) sunucuya gitmez.** macOS'un `tar`'ı her dosyanın yanına `._dosya` adlı bir meta
   verisi (AppleDouble, imza `00 05 16 07`) koyar. Editörün `db.migrate()`'i `._022_….sql`'i SQL sanıp
   çöktü (2026-09-22); test sunucusunun canlı kaynak ağacında 42 tane birikmişti.
   - Kaynak `git archive main`dir (git bu dosyaları taşımaz). Tek dosya için `scp`. Mac'te `tar` şartsa
     yalnız `COPYFILE_DISABLE=1 tar …`.
   - Kurulumdan sonra hedefte sayı **0** olmalı: `find <kök> -name '._*' -type f -not -path '*/node_modules/*' | wc -l`.
     Değilse her dosyanın imzası (`head -c4 | od -tx1` → `00051607`) doğrulanıp silinir; imzası tutmayana dokunulmaz.
   - Mekanik korumalar: `.gitignore` ve iki `.dockerignore`'da `._*`; `deploy-customer-vm.sh` rsync'leri
     `--exclude "._*"`; `db.migrate()` `._` ile başlayanı atlar. Bunlar kuralın yerine geçmez, ikinci hattır.
2. **Konteyner doğru imajla kalkmalı.** Editör compose dosyasında her servisin kendi imaj değişkeni var:
   `cards` → `EDITOR_CARDS_IMAGE`, diğer Python servisleri → `EDITOR_PY_IMAGE`. Değişkeni verilmeyen servis
   dosyadaki eski varsayılana düşer (2026-09-23: `cards` `0.15.3-condense`'e indi, inceleme ve Son Okuma
   ekranları bozuldu). Konteyner kalkınca imaj ve kod sürümü okunur, dosyalar `main` ile md5 karşılaştırılır:
   `docker inspect <ad> --format '{{.Config.Image}}'` ve `docker exec <ad> printenv EDITOR_CODE_VERSION`.
   Konteynere `docker cp` kurulum değildir — konteyner yeniden oluşunca silinir.

## Editor: kitaptan bağımsız üretim kabulü

Kullanıcının 2026-09-21 talimatı: üretim düzeltmeleri hiçbir kitap adına, PDF hashine, sayfa numarasına veya karakter adına özel uygulama istisnası içeremez. Gerçek kitaplar bağımsız kaynaklı kabul verisidir; bir kitapta geçen kontrol tüm ürünün kabulü değildir. Aynı genel kod/prompt/model sözleşmesi farklı uzunluk ve görsel/metin yapısındaki gerçek kitaplarda doğrulanır. Kaynağa özel beklenen sonuçlar yalnız kabul kanıtında açıkça etiketlenir, üretim karar kurallarına taşınmaz. Teknik çıktı tutarlılığı, kaynak/kimlik/olay kapsamı ve üretim kabulü ayrı raporlanır. Eksik model yanıtları veya başarısız parçalar başarı sayılmaz; bilinmeyen kimlikler zorla bağlanmaz.

## Basın ve web taraması (kullanıcı kararı 2026-09-24)

- **Ne:** CRM'de yazar olarak eser kaydı olan kişiler ve kitapları, açık kaynaklarda aranır: Türk haber sitelerinin
  kendi RSS akışları (29 akış), yazar adıyla başlık açılan sözlükler (Uludağ Sözlük; yazar başına en yeni girdiler,
  14 günde bir) ve Wikidata'nın resmi API'si. Kanallar tek listede (`FEEDS`, `ULUDAG`, `CLOSED`); denenip
  kullanılamayan kanal `CLOSED`'a nedeniyle yazılır, ekrandaki kanal haritasında görünür.
- **Kaynak her zaman belli:** her kaydın yanında kanal adı ve orijinal sayfaya bağlantı ("Habere git" / "Girdiye git")
  vardır; sözlük girdisi girdinin kendi kalıcı adresine gider. Kod `backend/semantic_bridge/web_watch.py`,
  uç `/api/v1/editorial/web*`, tablolar `semantic_web_*`.
- **Ne zaman:** her gece 02:30 (`scripts/server/timas-web-watch.timer` → `timas-web-watch.service` →
  `POST /api/v1/editorial/web/run-due?budget=16200`). Bitmeyen iş (Wikidata sırası, model etiketi) sonraki geceye
  kalır; sıra kalıcıdır, sessiz tavan yoktur. Yeni zamanlı iş ilk kez elle koşturulur, sonra zamanlayıcıya bırakılır.
- **Ekrana yalnız doğru eşleşme çıkar:** her eşleşme yerel modele sorulur (olumlu / olumsuz / notr / ilgisiz);
  "ilgisiz" ve henüz etiketlenmemiş kayıt hiçbir ekranda gösterilmez. Wikidata bilgisi yalnız tek ve kesin eşleşmede
  (insan + yazıyla ilgili meslek, birden çok aday varsa CRM'deki bir kitap "bilinen eseri" olmalı) gösterilir.
- **Nasıl taranır:** açık kimlikle (`TimasZekiBot/1.0`, iletişim adresiyle), hesapla giriş yapmadan, robots.txt'e
  uyarak. Bot korumasını aşan araç (gizlenen tarayıcı, parmak izi taklidi, dönen IP/proxy, CAPTCHA çözme) kullanılmaz;
  engelleyen site (1000Kitap, Kitapyurdu, D&R, Hepsiburada, Ekşi, Kızlar Soruyor — 2026-09-24'te 403) ve
  robots.txt / Content-Signal (`ai-input=no`) ile kapatan site taranmaz. O kaynaklar için yol
  izinli kanaldır: satıcı API'si, veri anlaşması, lisanslı sosyal dinleme hizmeti.
- **Kişisel veri tutulmaz:** muhabir ve okur adı alınmaz; haber metni kopyalanmaz (başlık, en çok 400 karakter özet,
  bağlantı). Model dış buluta gitmez; LLM kapısından `rt.llm_for("web", BATCH)` ile gider.
