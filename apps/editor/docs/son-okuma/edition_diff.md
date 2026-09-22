# Baskılar arası fark (`edition_diff`)

## 1. Analiz

### Editör son okumada ne bakar

Yeni baskı (tıpkı basım, düzeltilmiş baskı, yeni sürüm) geldiğinde editörün sorusu:
"Önceki onaylı baskıya göre **ne değişti** ve değişen her şey **bilerek mi** değişti?"
Matbaa öncesi sürüm karşılaştırması (PDF "compare") yayınevlerinde standart bir adımdır;
diff-pdf (GPL-2.0, github.com/vslavik/diff-pdf), DiffPDF, diff-pdf-visually gibi açık
araçlar sayfayı piksel ya da metin olarak karşılaştırır. Hepsinin ortak zayıflığı:
**sayfalar kayınca** (bir sayfa eklenince) sonraki her sayfa "değişmiş" görünür. Bizim
kontrolümüz sayfaları önce **içerikle hizalar**, sonra karşılaştırır.

Değişiklik türleri ve beklenen önem derecesi:

| Tür | Örnek | Önem |
|---|---|---|
| Künye | "6. Baskı → 7. Baskı", baskı tarihi, matbaa, baskı adedi, ISBN | INFO (baskıda beklenir) |
| Hikâye metni | bir kelime düzeltilmiş, bir cümle eklenmiş/çıkarılmış | WARN |
| Sayfa ekleme/çıkarma | reklam sayfası eklendi, bir hikâye sayfası düştü | WARN (künye/metinsiz sayfada INFO) |
| Resim | bir resim değiştirilmiş, bir figür rötuşlanmış | WARN |
| Yalnız dizgi | satır sonu heceleme, tırnak biçimi, boşluk | bulgu değil (normalizasyonla elenir) |

ISBN'in değişmesi (aynı kitap kaydında) yasal olarak yeni bir basım/sürüm demektir; brief
gereği INFO, ama mesaj bunu açıkça söyler.

### Veride ne var

- `ed.book_version`: her farklı dosya içeriği (sha256) bir satır, `UNIQUE(book_id, sha256)`.
  Aynı kitaba yeni PDF gelirse aynı `book` altına yeni satır açılır (`document.inspect_book`).
- 2026-09-22 itibarıyla altı kitabın **her birinin tek sürümü var** (6 book, 6
  book_version). Bir kitabın birden çok **generation**'ı olabilir (Ekrana… 7 generation)
  ama hepsi aynı dosya. **İki sürümlü gerçek bir çift yok.**
- Metin: `source.read(gid)` (PDF metin katmanı; yoksa OCR), sayfa görüntüsü:
  `document._open_version` ile PyMuPDF; metin satırlarının kutuları PDF katmanından.
- Künye: `METADATA` iddiaları (ISBN, EDITION) — ama her generation'da yok; bu yüzden
  künye alanları metinden deterministik düzenli ifadeyle de okunur.

### Açık araçlar ve lisans

- `imagehash` (BSD-2, JohannesBuchner/imagehash): aHash/pHash/dHash/wHash. İmajda
  Pillow ve scipy **yok**; dHash ve piksel farkı numpy + PyMuPDF ile 20 satırda yazılabilir,
  yeni bağımlılık gerekmiyor.
- diff-pdf (GPL-2.0): masaüstü/CLI; sayfa hizalaması yok, bağımlılık olarak alınmadı.
- Metin farkı: Python `difflib` (standart kütüphane).

### Yanlış alarm riskleri

1. Sayfa kayması → hizalama içerikle yapılır (dinamik programlama, sıralı).
2. Dizgi farkı (satır sonu tireleri, tırnak biçimi, boşluk) → `source.key` normalizasyonu.
3. Metin katmanı ile OCR karışımı: bir sürümde katman, diğerinde OCR okunursa OCR hataları
   "değişiklik" gibi görünür → metin kaynağı sayfa başına aynı türden seçilir; farklıysa
   bulgu bunu söyler.
4. Yeniden dışa aktarma gürültüsü (farklı JPEG sıkıştırma, renk profili) → piksel eşiği
   yeniden sıkıştırma gürültüsüyle ölçülerek seçilir.
5. Metin değişikliği pikselleri de değiştirir → resim karşılaştırmasında metin satırı
   kutuları maskelenir.

### Nasıl ölçülür

- Gerçek iki sürümlü çift yok: kesinlik/duyarlılık **ölçülemedi** (açıkça yazılır).
- Akıl sağlığı (ölçüm değil): her PDF kendisiyle karşılaştırılır → sıfır bulgu beklenir.
- Mekanizma testi (ölçüm değil): altı PDF'in sunucuda geçici kopyasına bilinen
  değişiklikler enjekte edilir (sayfa sil, sayfa ekle, kelime değiştir, resme şekil çiz,
  baskı numarasını değiştir) ve her birinin bulunup bulunmadığına, fazladan bulgu çıkıp
  çıkmadığına bakılır. Bu, gerçek bir baskı farkının dağılımını temsil etmez.
- Eşik ölçümü: sayfa hizalama eşiği aynı kitabın **farklı** sayfaları arasındaki
  benzerlik dağılımından; piksel eşiği aynı sayfanın farklı çözünürlük/JPEG kalitesiyle
  yeniden üretilmiş hâlinden.
