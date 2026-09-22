# Dizi tutarlılığı (`series_canon`)

## 1. Analiz

### Editör son okumada ne bakar

Bir dizinin (aynı kahramanın ya da aynı evrenin birden çok kitabı) yeni kitabı son
okumaya geldiğinde editör, yayınevinin **dizi kutsal kitabını** ("series bible") açar ve
yeni kitabı onunla karşılaştırır. Yayıncılık pratiğinde bu belge her kitaptan sonra
güncellenen tek başvuru kaynağıdır: karakterin adının yazımı, türü (insan / hayvan /
robot), cinsiyeti, yaşı, akrabalıkları, kişilik özellikleri, **görünüşü** (saç, göz,
kıyafet, ayırt edici işaret — çoğu zaman önceki kitaptan kesilmiş resimlerle), yer adları
ve dünyanın kuralları. Kaynaklar: Nathan Bransford, *The Series Bible*
(nathanbransford.com/blog/2010/05/series-bible); K.M. Allan, *Series Bible: What To
Include*; Atmosphere Press, *Creating a Story Bible*. Hepsinin ortak listesi: görünüş
(önceki kitaptan birebir), kardeş/ebeveyn sayısı ve adları, yaş, kişilik, özel adların
yazımı; ve "yeni kitap basılmadan önce ona göre güncellenir".

Çocuk kitabında tipik dizi hataları:

| Tür | Örnek (uydurma, türü göstermek için) | Kesin mi? |
|---|---|---|
| Ad yazımı | 1. kitapta "Kâmil", 3. kitapta "Kamil"; "Süheyla"/"Süheyle" | Birebir karşılaştırma kesin; hangisinin doğru olduğu editörün kararı |
| Tür | 1. kitapta köpek olan "Bitirim" 2. kitapta kedi olarak çizilmiş/anılmış | Ledger'daki `kind` karşılaştırması kesin; `kind`'ın kendisi modelin okuması |
| Cinsiyet / yaş bandı | kız kardeş sonraki kitapta "kardeşim o" ile erkek | `traits` karşılaştırması kesin; yaş bandı hikâye içinde büyüme ile açıklanabilir |
| Akrabalık | 1. kitapta "Mert, Levent'in kardeşi", 2. kitapta "kuzeni" | Açıklamalar modelin cümlesi; akrabalık kelimesi kapalı bir sınıftır |
| Çizim | saç rengi, gözlük, ten rengi kitaptan kitaba değişmiş | Karar gerektirir; CCIP benzerliği ölçülebilir, eşik bu külliyatta ölçüldü |

"Hikâye açıklıyorsa" istisnası (karakter büyüdü, saçını kestirdi) deterministik olarak
bilinemez; bu yüzden bulgu bir **aday**dır ve mesaj "hikâye açıklamıyorsa" der.

### Dizi üyeliği nereden bilinir (veride ne var)

Altı kitabın verisine bakıldı (2026-09-22, salt okunur):

- `ed.book.universe` — altı kitabın hepsinde **boş**. `ed.canon_entry` — **0 satır**
  (tablo ve `cli canon add` var ama hiç kullanılmamış).
- `METADATA / SERIES` iddiaları (künye sayfasından model okuması, alıntı birebir doğrulanmış):
  - Dedem Tekrar Çocuk Oldu: "Geyikli Kitaplar"
  - Anne Terliği: "TİMAŞ ÇOCUK" (yanlış alan — bu yayınevinin çocuk markası; aynı
    iddia kümesi TITLE için "Geyikli Kitaplar" demiş)
  - Ekrana Sığmayan Macera: "TİMAŞ ÇOCUK Psikoloji Kitaplığı"
  - Dünyanın En Korkak Hayvanı: "Düşler Kitaplığı"
  - Kahramanını Yutan Kitap, Levent: SERIES iddiası yok.
  Ayrıca iddialar kitabın **en son** generation'ında değil, eski generation'larda duruyor
  (ör. Dünyanın… için 3c63c8ea…, son analiz 4d1ebf3b…): kitap düzeyinde aranmalı.
- Künye sayfasının kendisi (ISBN geçen sayfa) dizi adını ve **dizideki sırasını**
  yazıyor: "Geyikli Kitaplar|1" (Anne Terliği), "Geyikli Kitaplar | 6" (Dedem…),
  "Düşler Kitaplığı / 4", "Psikoloji Kitaplığı | 18", "Umutlu Kitaplar / 73". Levent
  kitabının künyesinde dizi adı yok; dizisi yalnız arka kapak reklamlarında
  ("LEVENT İz Peşinde 6", "Levent Türkiye'yi Geziyorum 7") görünüyor.
- CRM: editör veritabanında CRM'den yalnız `cover_lookup.crm_book_id / crm_title`
  saklanıyor; dizi/seri alanı gelmiyor. CRM'den dizi bilgisi bugün **yok**.
- `book_card.metadata.SERIES` — yukarıdaki iddiaların kopyası.

Sonuç: altı kitaptan yalnız **Anne Terliği (Geyikli Kitaplar 1)** ve **Dedem Tekrar Çocuk
Oldu (Geyikli Kitaplar 6)** aynı diziye ait. Ancak bu bir yayınevi **kitaplığı**
(koleksiyon): yazarları farklı (Anıl Basılı / Salih Uyan), ortak karakterleri yok.
Karakter evreni paylaşan (aynı kahramanlı) **gerçek bir çift yok**. Levent kitabı bir
karakter dizisinin 1 kitabı; dizinin diğer kitapları analiz edilmemiş.

Bu ayrım kontrolün tasarımını belirliyor: "aynı dizi" iki anlama geliyor — (a) yayınevi
kitaplığı (farklı yazarlar, bağımsız hikâyeler), (b) karakter evreni. (a)'da aynı ad
tesadüftür: altı kitapta "Can" iki kitapta geçiyor (birinde haber spikeri yetişkin,
diğerinde yeni taşınmış çocuk). Aynı kitaplıkta olsalardı ad eşleşmesi yanlış alarm
üretirdi.

### Açık araçlar

- Görünüş benzerliği: CCIP ("bu iki çizim aynı karakter mi?" için eğitilmiş gömme;
  projede `editor-embed` servisinde zaten çalışıyor, `figure_identity.py`). Bu külliyatta
  ölçülmüş eşik `EDITOR_CCIP_SAME_MAX=0.15` (üç kitap, 194 adlı figür: aynı karakter
  ~0.11, farklı ~0.23). Yeni bağımlılık gerekmiyor.
- Türkçe büyük/küçük harf ve özel ad: Zemberek (Apache-2.0) özel ad sözlüğü içerir ama
  "Masal", "Bilge", "Defne", "Can" gibi hem cins hem özel ad olan kelimelerde sözlük
  karar veremez; kitabın kendi metnindeki yazım (cümle ortasında büyük harf) daha güvenli
  ve bağımlılıksız.
- Dizi kutsal kitabı için hazır açık veri seti yok; `ed.canon_entry` projenin kendi
  tablosu ve editör onaylı girişleri taşımak için tasarlanmış.

### Yanlış alarm riskleri

1. Kitaplık ≠ evren: farklı yazarların aynı adlı karakterleri.
2. Cins isimle anılan karakterler: "Anne", "Babam", "Dede", "Öğretmen", "Fil" — her
   kitapta var, hiçbiri dizinin tekrar eden karakteri değildir.
3. Künyedeki kişiler: ledger bazı kitaplarda yayın yönetmeni/editör/yazarı "karakter"
   olarak kaydetmiş (Dünyanın… kitabında 7 kişi). Aynı yayınevinin her kitabında aynı
   yayın yönetmeni geçer → sahte tekrar eden karakter.
4. Modelin `kind/traits` okuması yanlış olabilir → bulgu her iki kitabın kanıt sayfasını
   gösterir; editör sayfaya bakarak karar verir.
5. Kıyafet dizi içinde değişebilir; CCIP tüm figürü karşılaştırır → yalnız eşik üstü ve
   medyan üzerinden karar.

### Nasıl ölçülür

- Gerçek bir karakter-evreni çifti yok: **recall ölçülemez** (açıkça yazılır).
- Gerçek bir aynı-kitaplık çifti var (Anne Terliği ↔ Dedem…): burada doğru sonuç **sıfır
  WARN**; bu bir kesinlik (yanlış alarm) ölçümüdür.
- Stres testi: dizi kapısı kapatılıp altı kitabın 15 çiftinin hepsi "aynı diziymiş gibi"
  karşılaştırılır; çıkan her eşleşme elle incelenir (hiçbiri gerçek tekrar eden karakter
  değildir, yani her ad eşleşmesi süzgeçlerin kaçırdığı bir yanlış alarmdır).
- Görünüş alt-kuralı: kitap içi vekil ölçüm — her onaylı karakterin çizimleri sayfa
  sırasına göre ikiye bölünür, iki yarı "iki kitap" gibi karşılaştırılır (aynı karakter
  → uyarı çıkmamalı); farklı karakterlerin figür kümeleri karşılaştırılır (uyarı
  çıkmalı).
