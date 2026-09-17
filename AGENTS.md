# Çalışma kuralları

## Editör çalışma kaydı ve veri bütünlüğü

Kitap metni, model cevabı, konuşmacı ve inceleme kararı elle düzeltilmez; beklenen cevap model girdisine taşınmaz. Genel kod düzeltilir ve gerçek kaynak yeni nesilde yeniden doğrulanır. İşleme tamamlanması anlamsal kabul değildir.

17 Eylül yapılan işler, sürümler ve gerçek kabul sınırları [güncel durum belgesinde](docs/editor/2026-09-17-status-and-handoff.md) tutulur. Editör README, OCR/frontend belgeleri, roadmap, kabul defteri, proje belleği ve günlük ilgili değişikliklerde birlikte güncellenir; geçmiş sonuçlar kendi nesil/tarihleriyle korunur.

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

## Editör modülü: aynı depo, bağımsız uygulama

Kullanıcının 2026-09-16 kararı bağlayıcıdır: Editör modülü bu ana proje deposunda, BI'dan izole bir uygulama olarak geliştirilecek; sonrasında BI ekranlarına tanımlı API sözleşmeleri üzerinden bağlanacaktır.

- Hedef kök `apps/editor/` dizinidir; frontend, backend, Dockerfile, `compose.yaml`, `.env.example` ve README bu modül altında tutulur. Bu bir mimari karardır; uygulamanın henüz oluşturulduğu anlamına gelmez.
- Editör kendi bağımlılıklarına, yapılandırmasına ve Docker servislerine sahip olur; BI çalışmadan da başlatılıp kullanılabilmeli, bağımsız derlenip yayınlanabilmelidir.
- Kalıcı veri gerekiyorsa Editörün kendi veri alanı ve migration'ları olur. BI'ın iç koduna veya veritabanı tablolarına doğrudan bağımlılık kurulmaz; entegrasyon tanımlı API'ler üzerinden yapılır.
- Editörün bütün arayüzleri mobil öncelikli olur; yukarıdaki mobil doğrulama ve ilgili gerçek DB kabul kuralları bu modül için de geçerlidir.
- Kalıcı `editor` dalı veya ikinci trunk açılmaz. Küçük işler `main` üzerinde, kapsamlı işler `main`den açılan kısa ömürlü `codex/editor-...` dallarında yürütülür; tamamlanan iş `main`e alınır ve dal silinir. Bağımsız dağıtım, uzun ömürlü ayrı branch gerektirmez.

## Editör kaynak güvenliği — 2026-09-16

- Kullanıcının açık talebi: kalite hataları genel uygulama kodu/iş akışı üzerinden düzeltilir. Codex kitap metnini, modelin cevabını, kişi/konuşmacı etiketini veya kabul kararını elle düzelterek koşuyu başarılı gösteremez. Beklenen kitap cevapları prompt, özel kural veya veri kaydına yazılmaz. Değişiklik sonrası gerçek kaynak sistem tarafından yeniden işlenir; önceki nesil kanıt olarak korunur.
- Yeni okumalar sayfa sayfa, yeni analiz neslinde ilerler; önceki hatalı koşunun kayıtları silinmez veya yeni koşuya doğrulanmış veri olarak taşınmaz.
- Alıntı metni konumlu `source_spans` üzerinden gelir; ham metin, bbox, okuyucu/model sürümü ve uyuşmazlık durumu korunur. PDF metin katmanı bozuksa tek kaynak veya doğrulayıcı sayılamaz.
- `visual_observations` görsel gözlem adaylarıdır. Doğrulanmamış serbest `visuals.description` sahne/iddia/cevap girdisi olarak kullanılamaz.
- Kaynak sayfasının bulunması anlamsal doğruluk değildir. Alıntı, olumsuzluk, kişi/sayı ve konuşmacı kontrolleri geçmeyen iddia incelemeye ayrılır; ona bağlı kabul/sentez durur, diğer sayfaların kaynak okuması sürebilir.
- Konuşmacı için yeterli kaynak yoksa UNKNOWN kalır. Okunan/kaydedilen sayfa sayısı ile doğrulanmış sayfa/iddia sayısı ayrı gösterilir. Optik anlaşma editör onayı değildir.

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
