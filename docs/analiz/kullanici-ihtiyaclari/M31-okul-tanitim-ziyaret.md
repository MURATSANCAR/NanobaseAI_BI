# M31 — Okul Tanıtım ve Ziyaret Yönetimi (Bayi Eşleştirme Dahil): kullanıcı ihtiyaç analizi

Durum: kod var (main) — test sunucusunda kabul 5 geçti, 2 doğrulanamadı (2026-09-28 08:00, okul kartı düzeltmesi `0a405e24` sonrası) · Analiz tarihi: 2026-09-28 · Kaynaklar: `specs/M31.txt`, `specs/M59.txt`, `specs/M30.txt`, `veri_haritasi2.txt`,
`configs/semantic/knowledge/crm/OKUNUR-TABLOLAR.md` + `table_descriptions.json` (`new_ziyaretyerleriBase`, `new_etkinlikBase`, `new_siparisBase`,
`LeadBase`, `ContactBase`, `new_kitapBase`, `new_projeBase`), `docs/analiz/meb-uygunluk-olcutleri.md`, `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`,
`configs/semantic/knowledge/logo/knowledge/*`, `apps/editor/src/editor/production/age_report.py`, `backend/semantic_bridge/{author_relations.py, access.py, people.py}`,
kullanıcı belleği (customer-vm-web-watch-off, web-watch-open-sources, no-tech-names-on-screens, no-static-solutions, bi-app-vm-55).

Sunucuya bağlanılmadı; «ölçülecek» işaretli sayılar kodlamadan önce ölçülür.
Otomasyon: **K1** tam otomatik · **K2** Zeki önerir, insan onaylar · **K3** Zeki analiz eder, karar insanın · **K4** yalnız insan (K3/K4 tanımı varsayım).

## 1. Modül ne işe yarar

Okul tanıtım ekibinin hangi okula, ne zaman, hangi kitaplarla gideceğini planlar; okulun profiline (kademe, tür, öğrenci sayısı, bölgenin gelir düzeyi)
uygun katalog seçer; okulun kitabı hangi bayi/kitapçıdan alacağını eşleştirir; ziyaret raporunu ve sonraki adımı kaydeder. Amaç, tanıtımın satışa
(okul satışı, öğretmen/okul örneği sonrası sipariş, bayi üzerinden alım) dönüşmesini ölçülebilir kılmak.
Bugünkü sorun (veri + varsayım): CRM'de 68.713 «ziyaret yeri» (okul, üniversite, MEM, belediye…) ve ziyaret tipli etkinlik kayıtları var, ama hangi
okulun önceliklendirileceği, ziyaretin satışa etkisi ve okul–bayi bağının sonucu izlenmiyor (varsayım).

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Okul tanıtım temsilcisi / eğitim danışmanı (varsayım: ayrı ekip mi BMT mi bilinmiyor) | Satış sahası; CRM etkinlik `new_ziyarettipi` 1 = MEB Okulları, 2 = Özel Okullar, 3 = Üniversiteler | Okul döneminde her gün | **Telefon** |
| BMT (cari ile ortak okul ziyareti) | Satış; etkinlik `new_ziyaretsekli` 1 = «Cari ile Ziyaret» | Haftalık | Telefon |
| Saha yöneticisi (ziyaret planı, katalog ve bayi önerisi onayı) | Satış | Haftalık | Masaüstü |
| Bayi / kitapçı (okula yönlendirilen satıcı) | Dış kullanıcı; CRM etkinlik `new_AracMteriId` «Aracı Müşteri» | Okul başına | **Portal erişimi yok** (ilk sürümde dış kullanıcı yok) |
| Yazar etkinliği koordinatörü (okulda yazar söyleşisi) | Pazarlama / etkinlik (CRM `new_etkinlikBase`, etkinlik tipi 371 çeşit) | Aylık | Masaüstü |
| Pazarlama (sunum seti, okuma kulübü kiti) | Pazarlama | Dönem başı | Masaüstü |

Kişi sayısı: okul ziyareti sahibi kişi sayısı **ölçülecek** (`new_etkinlikBase` tip 1/2/3, son 12 ay, distinct `new_sorumlusu`/`OwnerId`).

## 3. Bugün bu iş nasıl yapılıyor

- **Temsilci — okul listesi:** CRM `new_ziyaretyerleriBase` (68.713): kurum tipi (Okul, Üniversite, Milli Eğitim, Belediye, Kaymakamlık, Valilik, Diğer),
  kurum türü (Devlet/Özel/Vakıf), okul türü (Anadolu Lisesi, İmam Hatip, Temel Eğitim…), kademe (Anaokulu, İlkokul, Ortaokul, Lise, BİLSEM, RAM),
  öğrenci/öğretmen/derslik/kitap sayısı, konferans salonu, il/ilçe. Sayısal alanlar **metin** (nvarchar) → doluluk ve okunabilirlik ölçülecek. Liste büyük
  olasılıkla MEB kurum listesinden içe alınmış (varsayım; kaynak ve tarih sorulacak).
- **Temsilci — ziyaret kaydı:** CRM `new_etkinlikBase`: ziyaret tipi, ziyaret şekli (Cari ile / Doğrudan), ziyaret yeri (`new_ZiyaretYeri`), okul
  (`new_OkulKurum` / metin `new_Okul`), iletişim kurulan kişi, katılımcı sayısı, satılan kitap adedi, dağıtılan kumbara adedi, gerçekleşen ziyaret tarihi,
  aracı müşteri (bayi), il/ilçe, sorumlu; durum Planlandı / Tamamlandı / İptal. «Çoğunluğu satış ziyareti» (crm-timas-mscrm-detay). Okul ziyareti payı
  ve yıllara göre sayısı ölçülecek.
- **Örnek gönderimi ve okul satışı:** CRM sipariş tipleri 10 «Okul Örneği», 11 «Öğretmen Örneği», 13 «Okul Satışı»; pazarlama tanıtım gönderimi 12.
  Hacim ölçülecek.
- **Öğretmen/okul iletişimi:** CRM `LeadBase`/`ContactBase` form tipi 7 «Timaş Okul», kurum tipi Devlet/Özel, alanı (İlkokul…Üniversite), sınıf bitleri
  1–12, okul adı, İYS/KVKK izin alanları. Proje kaydında `new_okulbutcesi` (okul bütçesi) alanı var (doluluk ölçülecek).
- **Tıkanma (varsayım):** okul seçimi deneyimle; hangi okulun hangi bayiden aldığı ziyaret notunda kalıyor; ziyaretin satışa etkisi ölçülmüyor;
  sunum materyali her seferinde elle hazırlanıyor.

## 4. İhtiyaçlar ve acı noktaları

- **Temsilci:** (1) Bölgemdeki okulların öncelik sırası ve gerekçesi (öğrenci sayısı, kademe, son ziyaret, geçmiş alım). (2) Okula gitmeden önce profile
  uygun 10–20 kitaplık katalog (yaş/kademe uygun, stokta, fiyat aralığı uygun). (3) Okulun bağlı bayisi kim, yoksa önerilen bayi. (4) Telefondan 1 dakikada
  ziyaret raporu (görüşülen kişi rolü, ilgi düzeyi, istenen kitaplar, sonraki adım). (5) Sınav haftası/tatil günlerinde plan yapılmaması.
- **Saha yöneticisi:** (1) Dönem ziyaret planı ve gerçekleşmesi. (2) Bayi eşleştirme önerilerini onaylamak. (3) Ziyaret → sipariş dönüşümü (okul/bayi bazında).
- **Bayi:** (dolaylı) kendisine yönlendirilen okulların listesi — ilk sürümde BMT brifingine düşer (M30).
- **Pazarlama:** okul profiline göre sunum seti ve okuma kulübü kiti şablonu.

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- Okul temsilcisi olarak bu haftanın ziyaret listemi öncelik ve gerekçeyle görmek istiyorum, çünkü hangi okula gideceğime zaman kaybetmeden karar vermeliyim.
- Okul temsilcisi olarak okulun kademesine uygun, stokta olan kitap listesini PDF olarak almak istiyorum, çünkü öğretmene bırakacağım.
- Okul temsilcisi olarak okul için önerilen bayiyi ve iletişim yolunu görmek istiyorum, çünkü öğretmeni oraya yönlendireceğim.
- Okul temsilcisi olarak ziyaret sonrası raporu telefondan girmek istiyorum, çünkü akşam masaya oturmuyorum.
- Saha yöneticisi olarak Zeki'nin okul–bayi eşleştirme önerisini onaylamak istiyorum, çünkü bayi ağındaki dengeyi ben biliyorum.
- Saha yöneticisi olarak dönem sonunda ziyaret edilen okulların kaçının bayi üzerinden sipariş verdiğini görmek istiyorum.

**Ana ekranlar ve akış**
- Telefon ilk açılış: «Bu hafta» okul listesi (öncelik, ilçe, kademe, öğrenci sayısı, son ziyaret, bağlı bayi, akademik takvim uyarısı).
- Okul kartı: profil · geçmiş ziyaretler · geçmiş örnek/satış siparişleri · bağlı bayi · önerilen katalog · «Zeki AI ziyaret önerisi» (2–3 cümle).
- Ziyaret raporu (alt sayfa): kişi rolü (müdür/müdür yardımcısı/kütüphane/Türkçe öğretmeni…), ilgi düzeyi (3 düğme), istenen kitaplar (katalogdan seç),
  sonraki adım + tarih, bayi yönlendirildi mi.
- Yönetici (masaüstü): dönem planı (il/ilçe × hafta), onay kuyruğu (bayi eşleştirme, katalog), dönüşüm raporu.
- En sık 3 işlem: okul kartını aç (1 dokunuş), rapor gir (≤ 6 dokunuş + kısa metin), katalog PDF'i paylaş (2 dokunuş).

**Zeki AI'ya soracakları**
- «Üsküdar'da 1.000'den fazla öğrencisi olan ve hiç ziyaret etmediğimiz ortaokullar hangileri?»
- «Geçen yıl okul örneği gönderdiğimiz okullardan kaçı bayi üzerinden sipariş verdi?»
- «4. sınıflar için stokta olan, fiyatı 150 ₺ altındaki kitaplarımız neler?»
- «Bu okulun yakınındaki, çocuk kitabı satan bayilerimiz kimler?»
- «Ekim ayında sınav haftası olan illeri planımdan çıkar.»
- «Yazar söyleşisi yaptığımız okullarda sonraki 3 ayda satış arttı mı?»

**Otomasyon katmanı**
- K2: okul önceliklendirme ve haftalık plan önerisi (temsilci/ yönetici onayı); profil bazlı katalog; bayi eşleştirme önerisi (yönetici onayı).
- K2: sunum notu ve okuma kulübü kiti taslağı (pazarlama şablonundan; temsilci onaylar).
- K1: ziyaret raporu sonrası hatırlatıcı (sonraki adım tarihi), dönem sonu özet.
- K3: okul penetrasyonu ve bölge analizi (ilçe bazında ziyaret edilen / toplam okul, dönüşüm).
- K4: okulla yapılan anlaşma, yazar etkinliği kararı, okul bütçesi kullanımı.

**Bildirim/uyarı**
- Temsilci: pazartesi 08:00 haftalık liste; sonraki adım tarihi gelince (sabah); planlanan ziyaret bir sınav/tatil gününe denk gelirse (plan anında).
- Yönetici: bayi eşleştirme onayı bekliyor (anında); dönem planının %50'si ay ortasında gerçekleşmediyse (haftalık özet).
- BMT (M30 üzerinden): kendi bayisine yeni okul yönlendirildiğinde.

**Onay ve yetki**
- `sayfa:okul-tanitim`; temsilci kendi okullarını/ziyaretlerini görür, `ozellik:okul.herkesinki` bütün ekip.
- `ozellik:okul.ziyaret` (rapor yazma), `ozellik:okul.plan` (plan onayı), `ozellik:okul.bayi-onay` (explicit), `ozellik:okul.katalog-sablon` (pazarlama).

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Okul listesi ve profili | CRM `new_ziyaretyerleriBase` (68.713) | kolonlar belli | Sayısal alanlar metin; doluluk ve güncellik (son `ModifiedOn`) **ölçülecek**; MEB'in güncel listesiyle kıyas yıllık elle içe aktarım (dış kaynak taraması müşteride kapalı) |
| İl/ilçe sözlüğü | CRM `new_illerBase` (143), `new_ilceBase` (1.253) | var | 143 il kaydı (81 il + yurtdışı/tekrar?) → temizlik ölçülecek |
| Sosyoekonomik profil | Dış: ilçe gelişmişlik endeksi (resmî kaynak; varsayım: Sanayi ve Teknoloji Bakanlığı SEGE ilçe çalışması), TÜİK il/ilçe göstergeleri | yok | Yılda bir kullanıcı yükler (CSV); otomatik web taraması yok. Okul düzeyinde gelir verisi yok — özel/devlet ve ilçe endeksi vekil |
| Akademik takvim | Dış: MEB çalışma takvimi (resmî) | yok | Kullanıcı yılda bir girer (tarih aralıkları); il bazlı ara tatil farkları elle |
| Geçmiş okul ziyaretleri | CRM `new_etkinlikBase` (tip 1/2/3, şekil, tarih, okul, aracı müşteri, katılımcı, satılan adet) | var | Okul ↔ ziyaret yeri bağının doluluğu ölçülecek (`new_ZiyaretYeri` vs metin `new_Okul`) |
| Okul örneği / okul satışı | CRM `new_siparisBase` tip 10/11/13 + satırları; Logo faturası (sevkiyattan) | var | Siparişin okula bağı (hangi alan) ölçülecek |
| Bayi/kitapçı konumu ve kapsaması | CRM `AccountBase` (`new_FirmaKanal` Bayi/Kitapçı, `new_cariyeaitil`, adres `new_adresBase.new_bolgeid`); Logo `CLCARD.CITY`, TOWN | var | İlçe/konum doluluğu ölçülecek; bayinin kategori uzmanlığı yok (satış karmasından türetilir) |
| Okul–bayi eşleşmesi | CRM etkinlik `new_AracMteriId` + «Cari ile Ziyaret» | kısmi | Kalıcı eşleşme tablosu yok → köprü tablosu |
| Katalog uygunluğu | CRM `new_kitapBase` (hedef yaş, sınıf, okul öncesi, tip, fiyat); Logo stok bakiyesi; MEB uygunluk raporu (`age_report.py`, yalnız stüdyoda işlenen kitaplar) | kısmi | Yaş/sınıf alanlarının doluluğu ölçülecek; uygunluk raporu yalnız stüdyo işleri için var |
| Bölge satışı | Logo faturalı satış × CLCARD CITY/SPECODE2 | tanımlı | Okula doğrudan fatura az (okul çoğunlukla bayiden alır — varsayım) → dönüşüm bayi satışından dolaylı ölçülür |
| Öğretmen/müdür iletişim | CRM `ContactBase`, `LeadBase` (form «Timaş Okul», İYS alanları) | var | KVKK/İYS izni olmadan iletişim listesi üretilmez |

## 7. Diğer modüllerle bağ

- Girdi: **M59** (bayi risk ve kapsama; M59 yoksa M30 sinyalleri — riskli bayiye okul yönlendirilmez uyarısı), **M30** (bayi portföyü, BMT), **M18** (föy,
  kampanya), **M27 Fuar/Etkinlik** (yazar etkinliği), **Kitap Tasarım Stüdyosu yaş uygunluğu raporu** (MEB ölçütleri), **Kategori Ağacı** (gelince).
- Çıktı: **M30** (bayinin brifingine yönlendirilen okullar; ortak ziyaret tablosu `semantic_saha_ziyaret`), **M59** (okul-bayi eşleştirme talepleri),
  **M33** (okul/kütüphane alım dönemi ve karar vericisi bilgisi), **M46** (okul kanalı gerçekleşmesi — ikinci sürüm).

## 8. Kısıtlar

- **CRM'e yazma yok:** iş tanımındaki «okul-bayi eşleştirmesi CRM'e kaydedilir» ve «ziyaret raporu → CRM güncelleme» ilk sürümde köprü tablolarında
  kalır; CRM'e aktarım müşteri Web API yetkisiyle sonraki sürüm.
- **Müşteride web taraması kapalı:** MEB okul listesi, akademik takvim, sosyoekonomik veri otomatik çekilmez; kullanıcı dosya yükler (kaynak ve tarih
  kaydıyla). Test sunucusunda da bot korumasını aşan araç kullanılmaz.
- **Sahadan erişim:** portal müşteri ağında; telefonla okul önünden erişim BT kararı (M30 §8).
- **KVKK / İYS:** öğretmen ve müdür kişisel verisi yalnız iş amacıyla, CRM'deki izinlere göre; öğrenci verisi **hiç** tutulmaz; ziyaret raporunda kişi
  rolü yazılır, ad-soyad yalnız CRM kişisine bağlanarak. Toplu e-posta/SMS önerisi İYS onayı olmayan kişiye üretilmez.
- **MEB ve okul idaresi kuralları (varsayım — hukuk teyidi):** okullarda ticari faaliyet/reklam ve öğrenciye kitap aldırma konusunda MEB düzenlemeleri
  vardır; katalog ve sunum metinleri «satış» değil «tanıtım/okuma kültürü» dilinde üretilmeli; «MEB tavsiyeli» ibaresi kullanılmaz (TEM, `meb-uygunluk-olcutleri.md`).
  Okul kütüphanesine kitap seçimi okuldaki Seçim ve Ayıklama Komisyonunun işidir (OKY m.10).
- Ekranda teknoloji adı yok; demo veri yok; sayı tavanı yok (okul listesi kesilmez, sayfalanır).

## 9. Kapsam önerisi

- **İlk sürüm:** okul listesi + profil (CRM ziyaret yerleri, metin sayıların temizlenmesi); öncelik puanı (kural: öğrenci sayısı, kademe, son ziyaret,
  geçmiş örnek/satış, ilçe endeksi yüklenmişse) + gerekçe; haftalık plan; akademik takvim (elle); profil bazlı katalog (yaş/sınıf/stok/fiyat) + PDF;
  bayi eşleştirme önerisi (il/ilçe + bayi satış karması + geçmiş «cari ile ziyaret») ve onay; telefon ziyaret raporu (ortak ziyaret tablosu); dönem özeti.
- **Sonraki sürüm:** sunum seti ve okuma kulübü kiti üretimi; ziyaret → bayi satışı dönüşüm modeli; yazar etkinliği planlama; CRM'e aktarım; bayinin
  kendi görünümü (dış kullanıcı); harita.
- **Yeniden kullanılacaklar:** `author_relations.py` (görüşme notu, ton, sonraki adım), `people.py`, `access.py`, `board_excel.py`, `editorial_studio_age.py`
  + `age_report.py` (MEB uygunluk özetini katalogda rozet olarak göstermek), M30'un `semantic_saha_ziyaret` tablosu, `rooms.py`'deki çakışma denetimi deseni
  (plan–takvim çakışması için).

## 10. Uzmanlara sorulacak sorular

1. Okul tanıtımını kim yapıyor (ayrı eğitim danışmanları mı, BMT'ler mi), kaç kişi, bölgeler nasıl paylaşılıyor?
2. «Ziyaret Yerleri» listesi nereden geldi (MEB listesi mi), en son ne zaman güncellendi, öğrenci sayıları hangi yıla ait?
3. Okul → bayi yönlendirmesinde kural ne (en yakın bayi, okulun tercihi, BMT'nin carisi, bayinin sözleşmesi)?
4. Okul/öğretmen örneği gönderiminin bütçesi ve onayı kimde; örnek → satış dönüşümü bugün izleniyor mu?
5. Okul ziyaretlerinde uyulan MEB/okul idaresi kuralları için hukuk görüşü var mı; öğretmenlerle iletişimde hangi izinler alınıyor?

## 11. Başarı ölçütü

- Planlanan/gerçekleşen ziyaret oranı (dönem) ve ziyaret başına hazırlık süresi.
- Ziyaret edilen okulların 90 gün içinde (okul satışı siparişi ya da eşleştirilen bayide okul kademesine uygun kitap satış artışı) dönüşüm oranı —
  ziyaret edilmeyen benzer okullarla kıyas.
- Bayi eşleştirme önerilerinin onay oranı ve eşleşen bayinin sonraki dönem satışı.
- Örnek gönderilen okullardan satışa dönen pay (sipariş tipi 10/11 → 13).
- Kullanım: raporu telefondan girilen ziyaret payı.

## 12. Uzman gözüyle en iyi sistem

**Uzman:** 15 yıllık eğitim yayınları bölge sorumlusu. Sektör uygulaması (genel bilgi, doğrulanmadı): eğitim yayıncıları okul segmentasyonunu kademe ×
öğrenci sayısı × okul türü × bölgenin sosyoekonomik düzeyiyle yapar; akademik yılın başında (Eylül–Ekim) ve dönem arasında (Ocak–Şubat) yoğun ziyaret
dalgası planlar; ziyaretin ardından öğretmene örnek bırakır, alım okulun anlaştığı kitapçı üzerinden olur; en iyiler «ziyaret → örnek → sipariş» hunisini
okul bazında izler ve kitapçıya «şu okullar sizden alacak» listesini önceden verir.

**TİMAŞ için mükemmel sistem:** dönem başında ilçe ilçe okul haritası ve öncelik; her okul için kademeye uygun, stokta olan katalog PDF'i ve 3 cümlelik
konuşma notu; ziyaret raporu 1 dakikada; bayi yönlendirmesi aynı anda BMT'nin ve bayinin listesinde; 90 gün sonra hangi ziyaretin satışa döndüğü görünür.

**Bir iş günü:** 08:00 telefonda «Bu hafta»: Kadıköy'de 4 ortaokul, 1 lise. İlk okulun kartı: 1.240 öğrenci, son ziyaret 14 ay önce, geçen yıl öğretmen
örneği gitmiş, bağlı bayi Moda'daki kitapçı. Katalog PDF'ini hazırlar (5–8. sınıf, stokta, 18 kitap). Müdür yardımcısı ve Türkçe öğretmeniyle görüşür,
raporu girer: ilgi yüksek, 3 kitap için sınıf seti isteniyor, bayi yönlendirildi, sonraki adım 2 hafta sonra. Öğleden sonra 2 okul daha; biri
ziyareti ertelemiş, sistem sınav haftasını göstermiş. Akşam 18:00 yönetici bayi eşleştirme önerisini onaylar.

**«Bunu görürsem hemen kullanırım»:** (1) Kademeye uygun ve stokta olan katalogun tek dokunuşla PDF'i. (2) Okulun bağlı bayisi ve bayinin o kademede
geçmiş satışı. (3) Sınav/tatil haftasını plan yaparken kendiliğinden gösteren takvim.

**«Bunu yaparsanız kullanmam»:** (1) Uzun form (15 alanlı ziyaret raporu). (2) Güncel olmayan okul listesi (kapanmış okul, yanlış öğrenci sayısı) —
listenin tarihi ve kaynağı görünmeli. (3) Öğretmenlere toplu mesaj atan, okulda satış yapıyormuş gibi görünen metinler.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo/ölçü) | CRM (varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Okul profili | — | `new_ziyaretyerleriBase` (tür, kademe, sayılar, il/ilçe), `new_illerBase`, `new_ilceBase` | Metin sayıların temizliği **kural** ile (TRY_CAST); model kullanılmaz | Deterministik |
| Okul adı eşleştirme (etkinlikteki serbest `new_Okul` metni ↔ ziyaret yeri) | — | `new_etkinlikBase.new_Okul`, `new_ZiyaretYeri` | Aday ziyaret yerleri arasından «aynı okul mu» kapalı seçim (evet/hayır, tek token + olasılık); eşik altı eşleşmez | Serbest metin eşleştirme |
| Öncelik | okulun bölgesinde bayi satışı (faturalı satış × CITY/TOWN) | geçmiş ziyaret, örnek/satış siparişi (tip 10/11/13) | Puan kural ile; model 1 cümle gerekçe | Denetlenebilir |
| Katalog | stok bakiyesi (tarih filtresiz), `PRCLIST` satış fiyatı (PTYPE 2, ACTIVE 0, geçerlilik) | `new_kitapBase` hedef yaş, sınıf, okul öncesi, özet | Kademe/tema uygunluğu sınıflaması (kapalı küme) ve 1 satırlık öğretmen notu taslağı | Sınıflama + taslak |
| MEB uygunluk rozeti | — | — | — (stüdyo raporunun hükmü okunur: Uygun / Sınırda / Uyumsuz) | Rapor zaten var |
| Bayi eşleştirme | bayi il/ilçe, kademeye uygun kitap satışı (24 ay) | `AccountBase.new_FirmaKanal`, `new_cariyeaitil`, geçmiş `new_AracMteriId` | Aday bayiler kural ile süzülür; model yalnız gerekçe cümlesi | Rakamlar SQL |
| Ziyaret raporu | — | (köprü tablosu) | Kısa sesli/serbest nottan alan önerisi (ilgi düzeyi, istenen kitaplar) — temsilci onaylar | Telefonda hızlı giriş |
| Sunum notu / kulüp kiti | — | — | Taslak metin (şablondan, okul profiline göre) | Taslak |
| Dönüşüm | eşleşen bayinin sonraki 90 gün satışı | sipariş tip 13 | — | Rakam SQL |

Model çağrısı `rt.llm_for("okul")`; toplu eşleştirme `/api/v1/llm/jobs`; `LlmClient` doğrudan kurulmaz.

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları** — `backend/semantic_bridge/school_visits.py`, `school_visits_sources.py`, `school_visits_api.py` (`register(...)`).

**Tablolar**
- `semantic_school_profiles` (ziyaret_yeri_id (CRM GUID), ad, kurum_tipi, kurum_turu, okul_turu, kademe, ogrenci, ogretmen, derslik, kitap_sayisi,
  il, ilce, kaynak `crm|yukleme`, kaynak_tarihi, asof) — CRM'den gece kopya, metin sayılar temizlenmiş.
- `semantic_school_context` (tur `ilce_endeks|takvim`, anahtar (ilçe kodu / tarih aralığı), deger_json, kaynak, yukleyen, yukleme_zamani)
- `semantic_school_priority` (ziyaret_yeri_id, donem, puan, bilesenler_json, gerekce, sahip)
- `semantic_school_plans` (id, sahip, donem, hafta, ziyaret_yeri_id, durum `oneri|onayli|iptal`, onaylayan)
- `semantic_school_dealer_links` (ziyaret_yeri_id, logo_clientref, crm_account_id, kaynak `gecmis|oneri|elle`, durum `oneri|onayli|reddedildi`, gerekce, onaylayan, zaman)
- `semantic_school_catalogs` (id, ziyaret_yeri_id, kitaplar_json (stok kodu, uygunluk, fiyat), pdf_yolu, olusturan)
- Ziyaret raporu: **`semantic_saha_ziyaret`** (M30 ile ortak; `tur='okul'`, `hedef_kimlik = ziyaret_yeri_id`, `eslik_eden_bayi`) + `semantic_school_visit_details`
  (ziyaret_id, kisi_rolu, ilgi `yuksek|orta|dusuk`, istenen_kitaplar_json, bayi_yonlendirildi).
- Yazmalar `semantic_audit`'e.

**Uçlar** (`/api/v1/schools/*`)
- `GET /` (liste, süzgeç: il, ilçe, kademe, tür, öncelik; sayfalı) · `GET /{id}` (kart)
- `GET /plan?hafta=` · `POST /plan/generate` · `PATCH /plan/{id}` · `POST /plan/{id}/approve`
- `POST /{id}/catalog` · `GET /catalogs/{id}.pdf`
- `GET /{id}/dealers` (öneri) · `POST /{id}/dealers/{link}/approve|reject`
- `POST /{id}/visits` (ortak tablo) · `GET /{id}/visits`
- `POST /context/upload` (ilçe endeksi CSV, takvim) · `GET /context`
- `GET /report/term?donem=` · `POST /run-due` (SYSTEM)

**Ekranlar** — `src/canvas/schools/` (`SchoolsWeek.tsx` telefon öncelikli, `SchoolCard.tsx`, `VisitReportSheet.tsx`, `DealerQueue.tsx`, `TermReport.tsx`,
`ContextUpload.tsx`, `api.ts`). Rota `/timas/okul-tanitim` (+ `/okul-tanitim/:id`). Menü: `satis` alanı, `{ id: 'okul-tanitim', label: 'Okul tanıtım',
section: 'Saha' }`. Kampüs: `ModulesMenu.tsx` → `M31: '/okul-tanitim'`.

**Yetki** — `sayfa:okul-tanitim`; `ozellik:okul.herkesinki` (kapsam), `ozellik:okul.ziyaret`, `ozellik:okul.plan`, `ozellik:okul.bayi-onay` (**explicit**),
`ozellik:okul.baglam-yukle` (ilçe endeksi/takvim yükleme), PDF/CSV `ozellik:veri.disa-aktar`. `access.py` `RULES`: `("/api/v1/schools/run-due", SYSTEM)`,
`("/api/v1/schools/", frozenset({page("okul-tanitim")}))`; ortak ziyaret uçları M30'da `page("okul-tanitim")` ile açık.

**Zamanlayıcı** — `scripts/server/timas-schools.{service,timer}`: gece 03:30 `run-due` (CRM ziyaret yerleri ve etkinlik kopyası, öncelik puanı, eşleştirme
aday işi kuyruğa); pazartesi 07:30 haftalık liste. CRM gece bağlayıcısı (03:10) ile çakışmaması için 03:30. İlk kez elle koşturulur.

**Kabul testleri**
1. Okul sayısı: ekrandaki il × kademe dağılımı = `SELECT i.new_name, z.new_okulkademesi, COUNT(*) FROM Timas_MSCRM.dbo.new_ziyaretyerleriBase z
   LEFT JOIN Timas_MSCRM.dbo.new_illerBase i ON i.new_illerId = z.new_ili WHERE z.statecode = 0 AND z.new_KurumTipi = 1 GROUP BY i.new_name, z.new_okulkademesi`.
2. Öğrenci sayısı temizliği: `SELECT COUNT(*) FROM … WHERE statecode = 0 AND TRY_CAST(new_renciSays AS int) IS NOT NULL` = ekranda sayısı dolu okul sayısı;
   dolmayanlar «bilinmiyor» (0 değil).
3. Geçmiş ziyaret: okul kartındaki ziyaret sayısı = `SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_etkinlikBase WHERE statecode = 0 AND new_ZiyaretYeri = @id
   AND new_ziyarettipi IN (1,2,3) AND statuscode = 100000002`.
4. Örnek/satış: `SELECT new_siparistipi, COUNT(*) FROM Timas_MSCRM.dbo.new_siparisBase WHERE statecode = 0 AND new_siparistipi IN (10,11,13) AND CreatedOn >= @donem
   GROUP BY new_siparistipi` = dönem raporu.
5. Katalog: PDF'teki her kitap için stok bakiyesi > 0 (Logo stok bakiyesi ölçüsü, tarih filtresiz) ve fiyat = geçerli `PRCLIST` satış fiyatı (Kural 8).
6. Geçmiş bayi eşleşmesi: `SELECT DISTINCT new_ZiyaretYeri, new_AracMteriId FROM Timas_MSCRM.dbo.new_etkinlikBase WHERE statecode = 0 AND new_ziyaretsekli = 1
   AND new_AracMteriId IS NOT NULL` = `semantic_school_dealer_links` `kaynak='gecmis'` satırları.
7. Kapsam: temsilci başka temsilcinin okul ziyaret raporunu göremez (403), `ozellik:okul.herkesinki` ile görür.

**M59 ile çakışma (kodlamadan önce karar):** M59 analizi okul için bayi önerisi ve bağ uçları öneriyor (`GET /api/v1/dealers/schools/{okul}/suggest`,
`POST /schools/{okul}/link`). Öneri: **eşleşme kaydı ve onayı M31'in** (`semantic_school_dealer_links`, tek tablo); M59 varsa aday bayi listesini onun
`suggest` ucundan alır (bayi riski ve kapsama bilgisi onda), yoksa M31 kendi kuralıyla (il/ilçe + kademeye uygun satış) önerir. M59'un `link` ucu açılırsa
aynı tabloya yazar.

**Bağımlılık** — bağımsız başlanabilir. M30 ile ortak ziyaret tablosu (hangisi önce kodlanırsa açar). M59 beklenmez. Stüdyo yaş raporu var (okunur).

**Büyüklük** — L (3+ gün).
