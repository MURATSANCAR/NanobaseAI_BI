# Okul ve MEB uygunluk ölçütleri — kaynaklar ve denetime bağlanışı (2026-09-25)

Kitap Tasarım Stüdyosu'nun **Yaş uygunluğu raporu** (`apps/editor/src/editor/production/age_report.py`) bu belgedeki
maddelere dayanır. Her madde resmî, kamuya açık bir kaynaktan alındı; bağlantısı yanındadır. **Kaynağı bulunamayan
ölçüt yazılmadı.** Metinler kaynağın ifadesine yakın özetlerdir; bağlayıcı olan kaynağın kendisidir.

Rapordaki kısaltmalar (ekranda ve PDF'te bu adlarla görünür):

| Kısa ad | Kaynak | Bağlantı | Okunduğu yol |
|---|---|---|---|
| **OKY** | Millî Eğitim Bakanlığı Okul Kütüphaneleri Yönetmeliği, RG 23.11.2024 / 32731 | [Lexpera tam metin](https://www.lexpera.com.tr/resmi-gazete/metin/milli-egitim-bakanligi-okul-kutuphaneleri-yonetmeligi-32731) · [MEB duyurusu](https://www.meb.gov.tr/milli-egitim-bakanligi-okul-kutuphaneleri-yonetmeligi-resmi-gazetede-yayimlandi/haber/35539/tr) | Lexpera metni (Resmî Gazete sitesi sertifika hatası verdi) |
| **KLV** | Okul Kütüphaneleri Yönetmeliği Uygulama Kılavuzu, MEB, Ankara 2025 | [meb.gov.tr PDF](https://www.meb.gov.tr/meb_iys_dosyalar/2025_10/22121751_Okul_Kutuphaneleri_Yonetmelik_Uygulama_Kilavuzu.pdf) | PDF metni (test sunucusunda `pdftotext`) |
| **DKY** | MEB Ders Kitapları ve Eğitim Araçları Yönetmeliği, RG 14.10.2021 / 31628 | [Resmî Gazete](https://www.resmigazete.gov.tr/eskiler/2021/10/20211014-1.htm) · [özet metin](https://www.alomaliye.com/2021/10/14/milli-egitim-bakanligi-ders-kitaplari-ve-egitim-araclari-yonetmeligi/) | ikincil metin; madde 8/6'nın ifadesi KRT 7.5.4 ile birebir |
| **KRT** | TTKB, «Türkiye Yüzyılı Maarif Modeli … taslak ders kitapları ve eğitim araçları ile bunlara ait elektronik içeriklerin incelenmesinde değerlendirmeye esas olacak kriterler ve açıklamaları» (Kurul mütalaası 15.10.2024, duyuru 17.10.2024) | [PDF](https://ttkb.meb.gov.tr/meb_iys_dosyalar/2024_10/15183917_tymm_kriter_ve_aciklamalari.pdf) · [duyuru](https://ttkb.meb.gov.tr/www/ders-kitaplari-ve-egitim-araclari-ile-bunlara-ait-elektronik-iceriklerin-incelenmesinde-degerlendirmeye-esas-olacak-kriterler-ve-aciklamalari-guncellendi/icerik/657) | PDF metni |
| **TDP** | Türkçe Dersi Öğretim Programı (İlkokul ve Ortaokul 1–8), MEB 2019 — «Ders Kitaplarına Alınacak Metinlerin Nitelikleri» | [mufredat.meb.gov.tr PDF](https://mufredat.meb.gov.tr/Dosyalar/20195716392253-02-T%C3%BCrk%C3%A7e%20%C3%96%C4%9Fretim%20Program%C4%B1%202019.pdf) | PDF metni, s. 18 |
| **TEM** | TEGM duyurusu 19.12.2018: 100 Temel Eser listeleri uygulamadan kaldırıldı (17.12.2018 tarih ve 2018/17 sayılı Genelge) | [tegm.meb.gov.tr](https://tegm.meb.gov.tr/www/ogrencilerimize-okuma-aliskanligi-kazandirmak-amaciyla-ilkogretim-ve-ortaogretim-ogrencileri-icin-tavsiye-niteliginde-belirlenen-100-temel-eser-listeleri-uygulamadan-kaldirilmistir/icerik/557) | sayfa metni |
| **MUZ** | 1117 sayılı Küçükleri Muzır Neşriyattan Koruma Kanunu | [mevzuat.gov.tr PDF](https://www.mevzuat.gov.tr/MevzuatMetin/1.3.1117.pdf) | arama özeti + Lexpera; m.1 |
| **KYT** | MEB Okul Öncesi Eğitim ve İlköğretim Kurumları Yönetmeliği (ilkokula kayıt yaşı) | [mevzuat.gov.tr](https://www.mevzuat.gov.tr/mevzuat?MevzuatNo=19942&MevzuatTur=7&MevzuatTertip=5) · [okul duyurusu 2026–2027](https://cicekhatunanaokulu.meb.k12.tr/icerikler/okulakayitbaslamayasibilgilendirmetablosu20262027yeniogretimyili_16297595.html) | ikincil (okul sitesi); hüküm metni alıntılı |

## 1. Maddeler

### OKY — Okul Kütüphaneleri Yönetmeliği, madde 10 (kaynakların seçimi)
Seçim ve Ayıklama Komisyonunun seçtiği kaynaklar öncelikle (m.10/1):
- **a)** Türk millî eğitiminin genel amaçları ve temel ilkelerine uygun,
- **b)** öğrencilerin yaş ve gelişim düzeylerine uygun,
- **c)** millî, manevi, kültürel, ahlaki ve insani değerlere uygun,
- **ç)** öğrencilerin beden, zihin, ahlak, ruh ve duygu bakımından dengeli ve sağlıklı bir kişiliğe sahip olmalarını destekleyici,
- **d)** Türkçenin doğru ve güzel kullanımını sağlamaya yönelik okuma, dinleme, anlama, konuşma, münazara ve yazma becerilerini destekleyici,
- **e)** eleştirel, analitik, özgün düşünme becerilerini ve akademik başarıyı destekleyici,
- **f)** görsel, dijital, medya okuryazarlığı gibi farklı okuryazarlıkları destekleyici olmalıdır.
- m.10/4: Türk millî eğitiminin genel amaçları ve temel ilkelerine uygun olmayan kitaplar kütüphanelerde bulundurulamaz.

### KLV — Uygulama Kılavuzu (2025)
- **1.4** Seçilecek kitaplar öğrencilerin yaş ve gelişim düzeylerine uygun olmalıdır; seçkide okul türü ve alana göre düzenleme esastır.
- **2.2** «Kazandırılacak kaynaklarda aranan nitelikler»: OKY m.10/1'in a–f bentleriyle aynı liste + özel eğitim ihtiyacı olan öğrencilere uygun kaynakları kapsayıcılık.
- **4.1.1** İlkokul seçkisi örneği: «görselliği güçlü, sade anlatımlı masal, hikâye, çocuk romanları, temel değerler eğitimi içeren kitaplar» (öneri; ölçüt değil, rapora bağlanmadı).

### DKY — Ders Kitapları ve Eğitim Araçları Yönetmeliği, madde 8/6 (punto)
Metin kısımlarında (başlık, resim altı, dipnot hariç) ilkokul 1. sınıf için **20**, 2. sınıf **18**, 3. sınıf **14**,
4. sınıf **12**, ortaokul 5. sınıf **11**, daha üst sınıflar için **10** puntodan küçük harf kullanılmaz.
**Kapsam: ders kitabı ve Bakanlığın eğitim araçları.** Okul kütüphanesine alınan yayınevi kitabı için bağlayıcı
değildir; rapor bilgi olarak verir.

### KRT — TTKB değerlendirme kriterleri (2024) — ders kitabı ve eğitim aracı içindir
Belgenin kapağında «HİZMETE ÖZEL olarak … hazırlanmıştır. Başka bir amaçla kullanılamaz.» notu var; belge TTKB
sitesinde herkese açık yayımlanmış. Rapor maddeleri yalnız **kaynak göstererek, kısa özetle** anar, belgeyi
çoğaltmaz (açık konu: hukuki görüş).
- **1.3.1–1.3.4** Eşitlik ve kapsayıcılık: ayrımcılık yok; kişi ve toplulukları aşağılayıcı, dışlayıcı, etiketleyici ifade yok; kadın-erkek temsilinde kalıp yargı yok, makul denge.
- **1.3.5** Engelli bireyler hakkında genelleme yapan, onları kısıtlamalarla tanımlayan ifade ve görsel yok.
- **1.3.7** Çocuk haklarına (yaşama, gelişim, korunma, katılım) aykırı yazılı ya da görsel unsur yok.
- **1.5.1** Bağımlılık yapıcı, müstehcen, kişilik gelişimini olumsuz etkileyebilecek unsur yok; **korku, şiddet, hakaret, aşağılama, cinsel içerikli öge**; bağımlılığı özendirici mesaj yok; yaşa uygun olmayan rol modeli, ürün, sembol, imge yok.
- **1.5.2** Fiziksel gelişimi ve beden sağlığını olumsuz etkileyecek öge yok.
- **1.6.1** Kimliği belirli/belirlenebilir gerçek kişiyle ilişkilendirilebilecek kişisel veri yok.
- **1.7.1** Lehte/aleyhte reklam, ticari yönlendirme, çağrışım yok.
- **1.8.1** Alıntı ve atıflar telif mevzuatına uygun, kaynak gösterilmiş.
- **1.8.3** Yapay zekâdan hangi aşamada yararlanıldığı belirtilir; üretilen içerik için kaynakçada «Yapay zekâ tarafından üretilmiştir.» ibaresi.
- **1.9.1 / 1.9.3** Çevre bilincine ve hayvan haklarına aykırı unsur yok.
- **6.1.1** Öğrencilerin sınıf seviyelerine uygun ve söz varlıklarını zenginleştiren bir dil; Türkçeye yerleşmemiş yabancı sözcük yerine varsa Türkçe karşılığı.
- **6.3.2** Anlatım akıcılığı bozacak nitelikte **uzun cümlelerden** ve karışık ifadelerden uzak, kolay okunabilir.
- **7.5.4** Punto DKY m.8/6'daki gibi; **vurgulama amaçlı büyük harf kullanılmamalı**; **otomatik tam bloklama (iki yana yaslama) yapılmamalı**.

### TDP — Türkçe Dersi Öğretim Programı (2019), «Ders Kitaplarına Alınacak Metinlerin Nitelikleri», madde 9
Metinlerdeki eğitsel yönden uygun olmayan ifadeler (**argo ve küfür, olumsuz örnek oluşturabilecek davranışlar,
cinsellik, şiddet** vb. içeren unsurlar) metnin bütünlüğünü bozmamak kaydıyla çıkarılmalıdır. (Ders kitabına alınacak
metin içindir.)

### TEM — 100 Temel Eser
«100 Temel Eser» listeleri (2004/60, 2005/70 sayılı genelgeler) **17.12.2018 tarih ve 2018/17 sayılı Genelge ile
kaldırıldı**. Kaldırılma gerekçeleri arasında telif sorunları, çeviri eserlerdeki içerik sorunları ve izinsiz
«MEB Tavsiyeli» logosu kullanımı sayılıyor. Yerine öğretmen rehberliğinde Anayasa'ya, yasalara ve millî eğitimin
temel amaçlarına ters düşmeyen bütün eserlerden yararlanılması uygun görülmüş. **Bugün geçerli bir MEB «temel eser»
listesi kaynağı bulunamadı**; rapor böyle bir listeye uygunluk denetlemez, yalnız metinde/künyede «MEB tavsiyeli» ya da
«100 Temel Eser» ibaresi olup olmadığına bakar.

### MUZ — 1117 sayılı Kanun, madde 1
On sekiz yaşından küçüklerin maneviyatı üzerinde muzır tesir yapacağı anlaşılan basılı eserler kanundaki
sınırlamalara tabidir. Rapor bu yaşı çocuk/genç kitabı sınırı olarak kullanır: bandın en küçük yaşı 18 ve üstüyse
hassas içerik ve okul ölçütleri koşmaz.

### KYT — İlkokula kayıt yaşı
«İlkokulların birinci sınıfına, kayıtların yapıldığı yılın eylül ayı sonu itibarıyla 69 ayını dolduran çocukların
kaydı yapılır.» Rapor, punto bilgisinde bandın en küçük yaşından **en alt sınıfı** bulur: 6 yaş (72–83 ay) → 1. sınıf;
7 yaş → 1. ya da 2. sınıf, küçük sınıf (büyük punto) alınır; 6 yaşından küçük → okul öncesi, yönetmelikte karşılığı yok.

### Kaynağı bulunamayanlar
- **2024 Türkiye Yüzyılı Maarif Modeli İlkokul Türkçe Dersi Öğretim Programı** metin seçim ölçütleri: PDF
  (`tymm.meb.gov.tr/upload/program/2024programtur1234Onayli.pdf`) 25.09.2026'da HTTP 500 verdi; okunamadı. 2019
  programının maddesi kullanıldı; 2024 programında aynı maddenin sürüp sürmediği **doğrulanamadı**.
- **Okul kütüphanesine alınacak kitap için yaşa göre cümle uzunluğu, kelime sayısı ya da okunabilirlik eşiği:**
  hiçbir resmî kaynakta sayı bulunamadı. Rapordaki eşikler yayınevinin kendi kitaplarından ölçülür (aşağıda).
- **Yardımcı ve kaynak eser inceleme ölçütleri:** Talim ve Terbiye Kurulu'nun ayrı bir «yardımcı ve kaynak eser»
  inceleme yönergesi aranıp bulunamadı; DKY kapsamındaki «yardımcı kitap» Bakanlık birimleri ve kamu kurumlarınca
  hazırlanan materyaldir. Eğitim ve Kültür Yayınları Yönetmeliği (2025) Bakanlığın kendi yayınlarını düzenler, rapora bağlanmadı.

## 2. Otomatik denetim (rapor `checks`)

| Rapor maddesi | Kaynak | Nasıl ölçülür | Durum |
|---|---|---|---|
| Yaş ve gelişim düzeyine uygun (okunabilirlik) | OKY m.10/1-b; KLV 1.4, 2.2 | Son okumanın `age_fit.readability`'si: sayfa metni bant kitaplarının sayfalarının %99'undan zor mu (üç ölçünün en az ikisi), kitap geneli bant içinde kaçıncı yüzdelik | zor sayfa ya da kitap %95 dışı → Dikkat |
| Uzun cümle | KRT 6.3.2 | Bant kitaplarındaki cümlelerin %99'undan uzun cümle (6-10: 24 kelime) | varsa Dikkat |
| Söz varlığı seviyeye uygun | KRT 6.1.1; OKY m.10/1-b | Zemberek kökü; kök bant kitaplarının en çok K'sinde geçiyorsa seyrek. K ve %95 sınırı derlemden ölçüldü (aşağıda) | pay %95 üstü → Dikkat, liste varsa Bilgi |
| Korku, şiddet, hakaret, aşağılama, cinsellik, bağımlılık | KRT 1.5.1; TDP m.9; MUZ m.1 | `age_fit.sensitive`: genel sözlük aday seçer, Zeki AI kapalı kümede sınıflar, harfi harfine alıntı ister | yüksek olasılık → Dikkat |
| Punto sınıf düzeyine uygun | DKY m.8/6; KRT 7.5.4; KYT | planın/spec'in en küçük metin puntosu ↔ en alt sınıfın punto sınırı | ders kitabı ölçütü: bilgi amaçlı Dikkat |
| İki yana yaslama yok | KRT 7.5.4 | plan sayfalarında `align: justify`, plan yoksa spec | Dikkat |
| Vurgu için büyük harf yok | KRT 7.5.4 | hikâye metninde tamamı büyük harfli sözcük (başlık ve ses sözcüğü bloğu hariç) | Bilgi (kısaltma olabilir) |
| «MEB tavsiyeli» / «100 Temel Eser» ibaresi yok | TEM | metin ve künye taranır | varsa Dikkat |
| Yapay zekâ beyanı | KRT 1.8.3 | işte Zeki AI ile üretilmiş resim/figür sayısı | ders kitabı ölçütü: Bilgi |

**Hüküm (bant uyumu):** *Uyumsuz* = editörün «sorun değil» demediği yüksek olasılıklı hassas içerik (KRT 1.5.1
«bulunmamalıdır»). *Sınırda* = açık uzun cümle / zor sayfa, kitap geneli bant kitaplarının %95'inden zor, seyrek
kelime payı bant kitaplarının %95'inden yüksek, ya da düşük olasılıklı/korku-yas hassas pasajı. *Uygun* = hiçbiri.
Hedef yaş yoksa «Hedef yaş belirtilmemiş», bant için derlem yoksa «Banda göre değerlendirilemedi», bant 18+ ise
«Çocuk/genç kitabı değil». Ön kontrole bilgi satırı olarak girer (OK/WARN; baskıyı durdurmaz).

## 3. Editör kontrol listesi (otomatik denetlenemeyenler)

OKY m.10/1-a, c, ç, d, e, f (m.10/4 ile); KRT 1.3.1–1.3.4, 1.3.5, 1.3.7, 1.5.1 (rol modeli, sembol, imge — resimler
dahil), 1.5.2, 1.6.1, 1.7.1, 1.8.1, 1.9.1/1.9.3; TDP m.9 (argo, küfür, olumsuz örnek — otomatik tarama yardımcıdır);
MUZ m.1. Her madde «Uygun / Uygun değil» + not; işaretleyen kişi (oturumdaki AD hesabı) ve zaman kaydedilir,
günlük silinmez (`yas-raporu-kararlar.json`), PDF'e yazılır.

## 4. Kelime düzeyinin ölçümü (uydurma liste yok)

`python -m editor.production.age_report vocab /data/organized <çıktı>` (GPU, geçici kap, salt okunur derlem):
- Derlem: yayınevinin PDF'leri (`/data/organized`, `nonbook` hariç 735 PDF); her PDF'in metin katmanı okumadaki
  paragraf kurucuyla (`document.paragraphs_from_layout`) kurulur, bant **kitabın kendi basılı bandı** (`_age_fit_ref` ile
  aynı kural), ≥300 kelime, aynı metin tek sayılır. 6-10 bandı: **286 kitap** (`_age_fit_ref`: 288; fark aynı metinli
  kopyaların tekilleştirilmesi).
- Her kitabın hikâye metni Zemberek köküne indirilir (özel ad, işlev sözcüğü dışarıda); `df` = kökün geçtiği bant kitabı sayısı.
- **K** (seyrek eşiği): bant kitaplarının kendi içerik sözcüklerinin (kitap kendisi hariç, kitap ağırlıklı) en çok
  %1'inin kaldığı en büyük `df`. Ölçülen: F(0)=%0,43, F(1)=%0,83, F(2)=%1,21 → **K = 1** (kök en çok bir bant kitabında).
- Kitabın seyrek payı yüzdelikleri (kitap ağırlıklı): p50 %0,59, p90 %1,46, **p95 %2,07**, p99 %5,56.
- Aynı kitap: iki farklı bant kitabı arasında seyrek kök payının en yükseği **0,6**; bu payı aşan eşleşme «kitap derlemde»
  sayılır ve kendi kökleri sayılmaz.
- Veri `apps/editor/src/editor/production/data/age_vocab.json.gz` (ölçüm tarihi dosyada).
- Karşılık önerisi: her seyrek köke Zeki AI (gateway, `book-director`) biçim biçim, cümlede yerine geçecek en çok 3 sade
  karşılık önerir; öneri metne kendiliğinden girmez, editör onaylar, «Metne uygula» sayfa planına yazar (plan sürümü artar,
  geri alınabilir).

Bilinen sınırlar: cümle başındaki bazı özel adlar (sözlükte cins adı da olan) kök sayılabilir; sözlükte çözümlenemeyen
biçimler listelenir ama kelime düzeyine katılmaz; derlem 6-10 dışında bant vermez (4-5: 5 kitap < 30).
