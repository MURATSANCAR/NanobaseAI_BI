# V16 adayı: kaynak bağlamından sonra iddia çıkarma

## Gerçek hata ve sınırı

V15-r7 nesli `382da5b3-a13a-4986-85ba-1a38fd92ff44` içinde PDF29'un altı kaynak birimi NO_CLAIM olmuş; model balondaki soruyu etkinlik yönergesi saymış ve hiç iddia üretmemiştir. Özgün sayfa render'ı bağımsız incelendi; bu bir balon diyaloğudur. Render SHA256 `27e900ff76c22e9b36a5fcbad3704f10a25df61fd374d66cecf1d4620d063b84`, gerçek evidence kaydıyla aynıdır. Önceki tamamlanmış R5 neslinin aynı sayfa için kaynak bağlamı sınıflandırması NARRATIVE/STORY_WORLD ve desteklidir. Bu eski sonuç yeni neslin anlamsal kabulü değildir.

Genel hata: aday önerici, bütün kaynaklar ve komşu sayfa bağlamıyla yapılan ayrı amaç denetiminden önce sayfayı yeniden sınıflandırıyordu. Yanlış ilk sınıf, diyalog adaylarını sıfırlıyor; sonradan doğru amaç sınıfı üretilse bile kaybolan adayları geri getirmiyordu. Kaynak birimi muhasebesinin tam olması bu anlamsal eksikliği kapatmaz. Sayfa/kitap/karakter istisnası eklenmedi, beklenen kitap cevabı modele verilmedi.

## Genel kod düzeltmesi

- `source_pipeline.py`, `source-spans-v16`: önce sayfaların optik/görsel kaynakları ve doğrulanabilir alt bölgeleri; ardından kaynak bağlamı; sonra iddia adayları. Öncelikli sayfalar işleme sırasını etkiler, bağlam hash sırası `record_key` ile sabit kalır.
- `page_context.py`, `source-page-context-v5`: amaç sınıflandırması artık aday kayıtlarına bağımlı değildir. Her model çağrısından önce/sonra iptal ve lease kontrolü yapılır. Kayıt `BEFORE_CLAIM_PROPOSAL` aşamasını ve adayların girdi olmadığını açıkça taşır.
- `source_unit_claims.py`, `source-unit-claims-v4`: zorunlu, kaynak hash'i doğrulanmış amaç kaydı önericiye verilir. Soru/emir gibi söz edimleri gerçekleşmiş olay veya olumlu cevap yapılmaz. Kimlik belirsizse isim üretilmez. Önericinin farklı amaç sınıfı üretmesi kabul edilmez ve ilgili birimler incelemede kalır.
- Kaynak amacı belirsiz veya öykü dışıysa model çağrılmaz; birimler açık NEEDS_REVIEW olur. Bu durum NO_CLAIM veya tamamlanmış anlam analizi gibi gösterilmez. Ham kaynak ve insan kararları değişmez.
- V16 kaynak önizleme destek listesine eklendi. Tam kaynak denetleyicisi V3 kabulünü koruyup V4 amaç hash'i, çağrılmayan gruplar ve ledger sözleşmesini ayrıca kontrol eder. Gerçek bileşen pilotu API/bağımsız PG eşliğini ve önce/sonra kaynak-inceleme parmak izlerini denetler.

## Gerçek aday kontrolleri

CPU `/data/nanobaseai/editor` üzerinde R5'in değiştirilmemiş gerçek kaynaklarıyla iki bileşen kontrolü geçti: PDF45 bilgilendirici kapsamda 21 birim incelemede; PDF6 anlaşılmış hedef metni olmayan boş katalog. İkisinde de model çağrısı sıfır, API/PG eşliği doğru, kaynak/inceleme kayıtları değişmedi. Kanıtlar:

- `evidence/source-unit-claims-d9ff5c60-dd47-47cb-bf66-70a5cad59cb1-0045-81e67eb13e9d.json`
- `evidence/source-unit-claims-d9ff5c60-dd47-47cb-bf66-70a5cad59cb1-0006-81e67eb13e9d.json`

Bu kontroller V4 önericinin güvenli engelleme yoludur; V5 sınıflandırıcının veya V16 tam akışın kabulü değildir.

Gerçek ilk diyalog pilotu `evidence/source-unit-claims-d9ff5c60-dd47-47cb-bf66-70a5cad59cb1-0029-49eae25011c8.json`: iki aday üretildi, ancak biri çok satırlı sorunun sadece son satırını kaynak seçti; atıf kapısı doğru şekilde engelledi. Genel kök neden balon metninin bölünebilmesiydi.

`source-unit-claims-v4` şimdi tekil geometrik balondaki bütün TEXT_AGREED satırlarını bölünmez ham kaynak birimi yapar. Çakışma, kısmi/okunmayan kutu, kesilme veya kopuk okuma sırası inceleme gerektirir; balonun alt parçalarını prose penceresiyle kaçırmaz. Layout kayıt/hash/bbox ve tüm kaynak kimlikleri taşınır. Gerçek katalog kontrolünde üç satır tek birim oldu; `evidence/atomic-balloon-v16-catalogue-preflight.json`. Gerçek model pilotu `evidence/source-unit-claims-d9ff5c60-dd47-47cb-bf66-70a5cad59cb1-0029-871f780ceb5d.json`: bir aday, bütün üç satır, actor/speaker null. İlk semantik kontrolde anonim kimlik alanı yanlışlıkla bilinmeyen isim kanıtı gibi değerlendirildi.

`source-semantic-review-v6` anonim söz edimi ile kimlik atamasını ayırır; metindeki ad/rol iddiası null alanlarla gizlenemez. Aynı değiştirilmemiş model adayı gerçek sunucuda yeniden değerlendirildi: `evidence/semantic-candidate-7280af899f9e2a9b129a.json`, bir kaynak destekli ifade geçti, kaynak/inceleme yazımı sıfır. Bu figürün karakter kimliğini doğrulamaz.

V6 ayrıca kaynak dışı isim yüzeyi kapısı, belirsizlik derecesini koruyan epistemic_strength ekseni ve sentezde kaynak kapısını içerir. R7'nin 100 gerçek iddiasındaki beş kaynak dışı ad bu kapıda engellendi; küçük harfli konum/sahiplik gibi anlamsal sorunlar bundan ayrı açıktır. [İddia inceleme kaydı](2026-09-18-semantic-source-audit.md).

## Derleme ve açık kabul

Önceki V16-r1/r2 imajları sonraki balon ve anlamsal sözleşme değişikliklerini içermez; yeni yayın için kullanılamaz. Son kaynakla yeni imaj, yeni tam V16 nesli ve aynı sürümde kaynaklı soru/restore/mobil kabulü gerekir. V16 henüz ana yayında değildir. Global karakter kimliği ve bütün kitabın edebî doğruluğu bu düzeltmeyle otomatik tamamlanmaz. Yerel test veya yapay kaynak kullanılmadı.
