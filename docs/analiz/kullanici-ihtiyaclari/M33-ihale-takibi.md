# M33 — Okul, Kütüphane ve Kamu İhale Takibi: kullanıcı ihtiyaç analizi

Durum: analiz (kod yok) · Tarih: 2026-09-28 · Kaynaklar: `specs/M33.txt`, `specs/M28.txt` (veri: «Kamu ihale ve proje portalleri»), `specs/M31.txt`, `specs/M32.txt`,
`veri_haritasi2.txt`, `docs/analiz/meb-uygunluk-olcutleri.md` (OKY m.10: Seçim ve Ayıklama Komisyonu), `configs/semantic/knowledge/crm/OKUNUR-TABLOLAR.md`
+ `table_descriptions.json` (`AccountBase.new_KurumRolu`, `new_ziyaretyerleriBase.new_KurumTipi`, `OpportunityBase`), `configs/semantic/knowledge/logo/knowledge/*`
(Kural 3, 8, stok bakiyesi), `backend/semantic_bridge/{web_watch.py, access.py, contracts_docs.py}`, `apps/editor/src/editor/production/age_report.py`,
kullanıcı belleği (customer-vm-web-watch-off, web-watch-open-sources, no-tech-names-on-screens, no-silent-limits-rule).
Depoda ihale/EKAP ile ilgili hiçbir tablo, kod ya da belge **yok** (dosya araması, 2026-09-28).

Sunucuya bağlanılmadı; «ölçülecek» işaretli sayılar kodlamadan önce ölçülür. Dış kaynak (EKAP vb.) bu çalışmada açılmadı; hakkındaki ifadeler genel bilgi
ya da varsayımdır ve kodlamadan önce resmî kaynaktan doğrulanmalıdır.
Otomasyon: **K1** tam otomatik · **K2** Zeki önerir, insan onaylar · **K3** Zeki analiz eder, karar insanın · **K4** yalnız insan (K3/K4 tanımı varsayım).

## 1. Modül ne işe yarar

Okul, kütüphane ve kamu kurumlarının kitap alımlarını (ihale, doğrudan temin, yayın alım başvurusu) takip eder: uygun ilanı bulur ve bildirir, teknik şartnameyi
TİMAŞ kataloğuyla eşleştirir (uygun kitaplar, stok, fiyat), teklif fiyat tablosunu ve belge kontrol listesini hazırlar, başvuru kararını ve sonucunu kaydeder,
geçmişten kazanma analizi çıkarır.
Bugünkü durum: portal ve depoda ihale takibine dair hiçbir kayıt yok; CRM'de kamu kurumu işaretleri (`AccountBase.new_KurumRolu` 2 = Devlet Kurumu, 3 = Resmi)
ve ziyaret yerlerinde kamu kurum tipleri (Milli Eğitim, Belediye, Kaymakamlık, Valilik) var. TİMAŞ'ın ihaleye doğrudan mı, bayi üzerinden mi girdiği bilinmiyor
(sorulacak). Sorun (varsayım): ilanlar kişisel takiple yakalanıyor, kaçırılıyor; şartname–katalog eşleştirmesi elle ve uzun sürüyor.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Kamu satış / ihale sorumlusu (ilan takibi, şartname analizi, dosya) | Satış (varsayım: kurum temsilcisi — CRM `new_KullancTipi` 2 — ya da ayrı kişi) | Günlük tarama, ihale dönemlerinde yoğun | **Masaüstü**; bildirim telefona |
| Satış müdürü / genel müdür (başvuru kararı, teklif fiyatı onayı) | Yönetim | İhale başına | Masaüstü + telefon (onay) |
| Muhasebe / finans (teminat, vergi-SGK belgeleri, fatura) | Mali işler | İhale başına | Masaüstü |
| Hukuk (şartname ve sözleşme incelemesi) | Hukuk/danışman (varsayım) | İhale başına | Masaüstü |
| Depo / lojistik (teslim kapasitesi, süre) | Depo | Kazanılan ihalede | Masaüstü |
| Okul tanıtım ekibi (M31; okul/kütüphane alım dönemi bilgisi) | Satış sahası | Dönemsel | Telefon |

## 3. Bugün bu iş nasıl yapılıyor

- **İhale sorumlusu:** Araç bilinmiyor (varsayım: EKAP'ta elle arama, e-posta ile ilan bildirimi, kişisel Excel). Portalda ve CRM'de ihale kaydı yok;
  CRM fırsat tablosu 12 kayıt (telif fırsatları) — ihale için kullanılmıyor.
- **Kamu kurumlarına satış:** Logo'da KURUM kanalı (`CLCARD.SPECODE2`) ve CRM kurum rolü ile ölçülebilir; tutarı ve kurum sayısı **ölçülecek**.
- **Okul kütüphaneleri:** Okul kütüphanesine kitap seçimi okuldaki Seçim ve Ayıklama Komisyonunun işidir (OKY m.10, `meb-uygunluk-olcutleri.md`);
  alım çoğunlukla küçük tutarlı ve doğrudan temin/bağış yoluyla olabilir (varsayım — 4734 sayılı Kanun m.22 doğrudan temin; ilan zorunluluğu tutara ve
  usule göre değişir, hukuk teyidi).
- **Halk kütüphaneleri:** Kültür ve Turizm Bakanlığı'nın halk kütüphaneleri için yayın alımı yaptığı bilinir; usul (yayınevi başvurusu/komisyon) varsayım,
  doğrulanacak.
- Tıkanma (varsayım): ilanın geç görülmesi, şartnamedeki kitap listesinin katalogla elle karşılaştırılması, belge eksikliği.

## 4. İhtiyaçlar ve acı noktaları

- **İhale sorumlusu:** (1) Uygun ilanı kaçırmamak (kitap/yayın/kütüphane/okul kitaplığı anahtar kelimeleri, il süzgeci), son teklif tarihiyle. (2) Şartnamedeki
  kitap listesi/özelliklerinin kataloğa eşlenmesi: hangileri bizde var, stok, fiyat, eksikler. (3) Belge kontrol listesi ve son tarih takvimi. (4) Geçmiş
  ihalelerin sonucu ve kazanan fiyatlar.
- **Müdür:** (1) Karar için tek sayfa: tutar, uygunluk oranı, stok yeterliliği, tahmini marj, rakip geçmişi, risk. (2) Teklif fiyatının onayı.
- **Finans:** teminat mektubu tutarı/süresi, belge geçerlilik tarihleri (vergi, SGK, imza sirküleri) hatırlatması.
- **Depo:** kazanılan ihalede teslim takvimi ve adet.

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- İhale sorumlusu olarak sabah yeni çıkan kitap/kütüphane ilanlarını uygunluk puanıyla görmek istiyorum, çünkü son teklif tarihlerini kaçırıyoruz.
- İhale sorumlusu olarak şartnamedeki kitap listesini yapıştırıp kataloğumuzla eşleşmesini görmek istiyorum, çünkü bunu elle yapmak bir gün sürüyor.
- İhale sorumlusu olarak belge kontrol listesinin eksik kalemlerini görmek istiyorum, çünkü belge eksikliğinden elenmek istemiyoruz.
- Müdür olarak başvuru kararını tek sayfalık özetle vermek istiyorum, çünkü birden çok ihaleyi aynı hafta değerlendiriyorum.
- Müdür olarak teklif fiyatını marj ve geçmiş kazanan fiyatlarla birlikte onaylamak istiyorum.
- Finans olarak teminatı ve belge geçerlilik tarihlerini ihale takvimiyle birlikte görmek istiyorum.

**Ana ekranlar ve akış**
- İlk açılış (masaüstü): «Açık ilanlar» — kurum, il, konu, yaklaşık tutar (varsa), son teklif tarihi (kalan gün), uygunluk puanı, durum
  (yeni / inceleniyor / başvurulacak / başvurulmayacak / teklif verildi / sonuçlandı).
- İlan ayrıntısı: şartname özeti (Zeki AI), kitap listesi eşleştirmesi (eşleşti / kısmen / yok, stok, fiyat), belge kontrol listesi, karar paneli.
- Teklif fiyat tablosu: kalem, adet, liste fiyatı, önerilen fiyat, marj, KDV; dışa aktarım (Excel).
- Sonuçlar: kazanılan/kaybedilen, kazanan firma ve fiyat (ilan sonucu açıksa), kayıp nedeni.
- En sık 3 işlem: ilanı süz/değerlendir (1–2 tık), şartname listesini eşleştir (yapıştır + 1 tık), karar/onay (1 tık).

**Zeki AI'ya soracakları**
- «Bu hafta son teklif tarihi dolan kütüphane kitabı ilanları hangileri?»
- «Bu şartnamedeki 240 kitabın kaçı bizde var, stokta kaç tanesi yetersiz?»
- «Geçen yıl kaç ihaleye girdik, kaçını kazandık?»
- «Belediyelere son 2 yılda ne kadar satış yaptık?»
- «Bu ihalede teminat ne kadar, hangi belgeler eksik?»
- «Çocuk kitabı ihalelerinde kazanan fiyatlar liste fiyatının yüzde kaçıydı?»

**Otomasyon katmanı**
- K1 (ancak bölüm 8'deki izinle): ilan içe alma ve anahtar kelime süzgeci, son tarih hatırlatması. İzin yoksa ilan **elle/dosyayla** girilir (K4 giriş, K1 hatırlatma).
- K2: uygunluk puanı ve başvuru tavsiyesi; şartname–katalog eşleştirmesi; teklif fiyat önerisi; şartname yanıt metni taslağı; belge kontrol listesi.
- K3: kazanma olasılığı ve geçmiş analiz (veri biriktikçe).
- K4: başvuru kararı, teklif fiyatı, e-imza ile teklif verme (portal teklif vermez).

**Bildirim/uyarı**
- İhale sorumlusu: yeni uygun ilan (sabah 08:00 özet + yüksek puanlıda anında portal içi); son teklif tarihine 7 ve 2 gün kala.
- Müdür: karar/onay bekleyen ihale (anında); haftalık ihale özeti.
- Finans: belge geçerlilik tarihi 30 gün içinde dolacak; teminat iade tarihi.
- Depo: kazanılan ihalenin teslim takvimi (sonuç kaydında).

**Onay ve yetki**
- `sayfa:ihale`; `ozellik:ihale.duzenle` (ilan girişi, eşleştirme, belge listesi), `ozellik:ihale.karar` (explicit; başvuru kararı ve teklif fiyatı onayı),
  `ozellik:ihale.kaynak-yonet` (ilan kaynağı ayarları; yönetici), dışa aktarım `ozellik:veri.disa-aktar`.

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| İhale ilanları (kurum, konu, tarih, şartname) | Dış, resmî: EKAP / Kamu İhale Bülteni (Kamu İhale Kurumu). Otomatik okuma için resmî veri servisi/izin gerekir (varsayım: herkese açık resmî bir API'nin varlığı doğrulanmadı) | yok | **Kritik boşluk.** Müşteride dış kaynak taraması kapalı; captcha/bot engeli aşılmaz. İlk sürüm: elle giriş + şartname dosyası yükleme; EKAP'ın kurumsal bildirim/abonelik e-postası varsa onun içe alınması (sorulacak) |
| İhale sonuçları, kazanan fiyatlar | Dış, resmî: ihale sonuç ilanları (varsa) | yok | Elle girilir; kamuya açık olup olmadığı ilan türüne göre değişir (varsayım) |
| Halk/okul kütüphanesi alım dönemleri | Dış: Bakanlık duyuruları; M31 okul ziyaretleri | yok | Elle takvim |
| Katalog | Logo `ITEMS` (CODE, NAME, SPECODE yayınevi, ACTIVE 0); CRM `new_kitapBase` (ISBN/barkod, yazar, hedef yaş, sınıf, sayfa, ebat) | var | Şartnamedeki ISBN/ad ile eşleşme anahtarı: barkod/ISBN doluluğu ölçülecek |
| Stok | Logo stok bakiyesi (tarih filtresiz) | tanımlı | donmuş kopya (17.08.2026) |
| Fiyat | Logo `PRCLIST` (Kural 8); CRM `new_kitapBase.new_kdvdahilfiyat` (liste fiyatı) | var | Kamu teklifinde esas fiyat politikası sorulacak |
| Maliyet / marj | Logo `OUTCOST` (maliyetli satırlar) | tanımlı | Yeni kitapta maliyet yok |
| MEB/okul uygunluğu | Stüdyo yaş uygunluğu raporu (`age_report.py`) ve ölçütler (OKY, KLV) | kısmi (yalnız stüdyoda işlenen kitaplar) | Katalog genelinde rapor yok |
| Kamu kurumlarına geçmiş satış | Logo faturalı satış × CRM `new_KurumRolu` (2, 3) / Logo `SPECODE2 = 'KURUM'` | tanımlı parçalar | Kurum eşleşmesi ölçülecek |
| Rakip kazanımları | Dış (sonuç ilanları) | yok | Elle |
| Belgeler (vergi, SGK, imza sirküleri, teminat) | Kullanıcı yükler | yok | Köprü dosya deposu (`result_files.py` deseni) |

## 7. Diğer modüllerle bağ

- Girdi: **M31** (okul/kütüphane karar vericileri, alım dönemi), **M28** Kurumsal ilişkiler (kamu ve proje portalleri — iş tanımında aynı veri geçiyor; kapsam
  M33'te toplanmalı), **M32** (kamu kurumuna ihalesiz doğrudan satış M32'de), **M46** (kitap hedefi — ihale katkısı), **Kitap Tasarım Stüdyosu** (MEB uygunluk).
- Çıktı: **M29** (kazanılan ihalenin sevk planı, stok rezervi), **M12** (ihale adedi için baskı tekrarı ihtiyacı → M11/M12), **M46** (kamu kanalı gerçekleşmesi),
  **M30** (bayi üzerinden girilen ihalelerde bayinin brifingi — varsayım).

## 8. Kısıtlar

- **Dış kaynak:** müşteride web taraması kapalı (bellek: customer-vm-web-watch-off); ilan kaynağının otomatik okunması kullanıcının açık kararı ve kaynağın
  izin verdiği resmî yol (API/abonelik/açık veri) ile olur. Bot korumasını aşan araç, captcha çözme, oturum taklidi **yok** (bellek: web-watch-open-sources).
  Açılırsa ortam bayrağı (`TENDER_WATCH_ENABLED`, varsayılan 0) ve ayrı menü görünürlüğü (`feature`) gerekir.
- **Teklif verme yok:** portal EKAP'a ya da herhangi bir kuruma teklif göndermez, e-imza kullanmaz; yalnız hazırlık ve kayıt.
- **CRM'e yazma yok:** «ihale sonuç kaydı → Dynamics CRM» ilk sürümde köprü tablosunda kalır.
- **Hukuki:** 4734 sayılı Kamu İhale Kanunu ve ikincil mevzuat (teminat, yasak fiiller, belge koşulları) — Zeki'nin şartname yanıt metni ve belge listesi
  «taslak»tır, hukuk/ihale sorumlusu onaylamadan kullanılmaz; yanlış beyan riski ekranda yazılır. MEB/kütüphane ölçütlerine uygunluk iddiası yalnız kaynaklı
  ölçütlerle (`meb-uygunluk-olcutleri.md`); «MEB tavsiyeli» ibaresi kullanılmaz.
- Ekranda teknoloji adı yok; demo ilan yok; sayı tavanı yok (ilan ve şartname kalemleri kesilmez).
- KVKK: ilandaki kurum yetkilisi kişisel bilgisi yalnız ilan kaydında, pazarlama listesine taşınmaz.

## 9. Kapsam önerisi

- **İlk sürüm:** ihale kaydı (elle + şartname PDF/Excel yükleme); şartname kitap listesinin katalogla eşleştirilmesi (ISBN/barkod → ad benzerliği → Zeki
  eşleştirme, insan onayı); stok/fiyat/marj ile teklif fiyat tablosu (Excel); belge kontrol listesi ve belge geçerlilik takvimi; karar/onay akışı; sonuç ve kayıp
  nedeni kaydı; kamu kurumlarına geçmiş satış özeti (Logo).
- **Sonraki sürüm:** kullanıcı onayıyla resmî kaynaktan ilan içe alma (izinli yol) ve günlük tarama; kazanma olasılığı; rakip fiyat analizi; M29'a sevk planı
  aktarımı; şartname yanıt metni üretimi.
- **Yeniden kullanılacaklar:** `web_watch.py` (açık kaynak okuma, ortam bayrağı, gece zamanlayıcı deseni — yalnız izinli kaynakta), `result_files.py` (dosya saklama),
  `contracts_docs.py` (belge üretimi), `board_excel.py`, `budget.py` (onay/iki göz), `access.py`, `age_report.py` (uygunluk hükmü).

## 10. Uzmanlara sorulacak sorular

1. TİMAŞ bugün kamu ihalelerine giriyor mu (doğrudan mı, bayi/dağıtıcı üzerinden mi); yılda kaç ihale, kim takip ediyor?
2. Okul ve halk kütüphanesi alımlarının çoğu ihale mi, doğrudan temin mi, bakanlık yayın alımı mı?
3. EKAP'ta kurumsal kaydınız ve ilan takip/bildirim aboneliğiniz var mı; bildirimler hangi e-postaya geliyor?
4. Teminat mektubu, vergi/SGK belgesi, imza sirküleri gibi belgelerin arşivi ve güncel tutulması kimde?
5. Kamu teklifinde fiyat politikası nedir (liste fiyatı üzerinden sabit iskonto mu, ihale bazında mı)?

## 11. Başarı ölçütü

- Kaçırılan uygun ilan sayısı (sonradan fark edilen) — sıfıra yakın.
- İlan kaydından karar verilmesine geçen gün; şartname eşleştirme süresi (önce 1 gün → hedef 1 saat).
- Belge eksikliği nedeniyle elenme sayısı.
- Başvuru/kazanma oranı ve kamu kanalı net ciro (Logo).
- Eşleştirmede insan düzeltmesi oranı (model kalitesi).

## 12. Uzman gözüyle en iyi sistem

**Uzman:** 15 yıllık kamu satış ve ihale uzmanı. Sektör uygulaması (genel bilgi, doğrulanmadı): kamuya satış yapan firmalar ihale ilanlarını anahtar kelime ve
bölge süzgeçli bildirim servisleriyle izler; her ilan için «git/gitme» kararını uygunluk, rekabet ve kapasiteye göre hızlı verir; şartname kalemlerini ürün
kataloğuyla eşleyen bir tablo, belge kontrol listesi ve teminat takvimi tutar; kaybedilen ihalelerin kazanan fiyatlarını biriktirip fiyat stratejisine çevirir.

**TİMAŞ için mükemmel sistem:** sabah ilan listesi puanlı; şartname yüklenince 15 dakikada kalem–katalog eşleşmesi (eşleşmeyenler işaretli), stok yeterliliği
ve baskı tekrarı ihtiyacı; tek sayfa karar özeti; onaylı teklif tablosu Excel; belge klasörü güncel ve süresi dolacaklar önceden uyarılı; sonuçlar birikip
«hangi ihale türünde, hangi fiyat bandında kazanıyoruz» görülür.

**Bir iş günü:** 08:00 yeni 4 ilan: ikisi belediye kütüphanesi, biri il MEM okul kitaplığı, biri ilgisiz (kırtasiye). MEM ilanının şartnamesini yükler;
312 kalemin 188'i eşleşir, 21'inde stok yetersiz. Karar özeti müdüre gider; 14:00 onay gelir; teklif tablosunu hazırlar, finans teminatı kontrol eder.
16:00 geçen ay kaybedilen ihalenin sonucunu girer (kazanan fiyat liste fiyatının %58'i). 17:00 iki belgenin 20 gün içinde süresinin dolacağı uyarısı.

**«Bunu görürsem hemen kullanırım»:** (1) Şartname kalemlerinin katalog ve stokla otomatik eşleşmesi. (2) Son teklif tarihine göre sıralı ilan ve belge takvimi.
(3) Tek sayfa karar özeti (tutar, uygunluk, stok, marj, geçmiş).

**«Bunu yaparsanız kullanmam»:** (1) Eksik ilan listesi ama «hepsi burada» izlenimi (kaynak ve kapsam yazılmalı). (2) Hukuki sorumluluğu belirsiz, otomatik
yazılmış şartname yanıtı. (3) Kamu teklifini sistemin kendi başına fiyatlaması.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo/ölçü) | CRM (varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| İlan uygunluk ön süzgeci | — | — | İlan başlık/konu metnini «kitap/yayın alımı mı» kapalı küme sınıflaması (evet/hayır/belirsiz, tek token + olasılık) | Serbest metin sınıflama |
| Şartname özeti | — | — | Yüklenen şartnameden özet: konu, teslim süresi, teminat, belge listesi, kritik koşullar — kaynak cümle alıntısıyla | Uzun metin özeti |
| Kalem–katalog eşleştirme | `ITEMS` (CODE, NAME, ACTIVE 0), stok bakiyesi | `new_kitapBase` (barkod/ISBN, ad, yazar, yayınevi) | Önce kural: ISBN/barkod birebir; sonra ad normalizasyonu; kalan kalemlerde aday kitaplar arasında «aynı eser mi» kapalı seçim + olasılık; eşik altı «eşleşmedi» | Eşleştirme |
| Stok/fiyat/marj | stok bakiyesi, `PRCLIST` satış fiyatı, son `OUTCOST` | `new_kdvdahilfiyat` | — | Rakam SQL |
| Uygunluk (okul) | — | `new_kitapBase` hedef yaş/sınıf | Stüdyo raporu hükmü okunur; model yeni hüküm üretmez | Kaynaklı ölçüt |
| Kamu geçmiş satışı | faturalı satış × `CLCARD.SPECODE2`, `CITY` | `AccountBase.new_KurumRolu` 2/3, `new_logicalref` | — | Kayıt sistemi Logo |
| Karar özeti | yukarıdaki rakamlar | — | 5 cümle özet; rakamları verilen JSON'dan aynen kullanır | Okunabilirlik |
| Şartname yanıt taslağı (ikinci sürüm) | — | — | Taslak metin, «taslak — hukuk onayı gerekir» etiketiyle | Taslak |

Model çağrısı `rt.llm_for("ihale")`; şartname özeti ve toplu eşleştirme `/api/v1/llm/jobs` (uzun iş); `LlmClient` doğrudan kurulmaz.

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları** — `backend/semantic_bridge/tenders.py` (tablolar, eşleştirme, karar akışı, takvim), `tenders_sources.py` (Logo/CRM SQL; ilan kaynağı
bağdaştırıcısı ikinci sürümde, bayrakla), `tenders_api.py` (`register(...)`).

**Tablolar**
- `semantic_tenders` (id, kaynak `elle|dosya|resmi`, kaynak_no (ihale kayıt no), kurum, kurum_turu, il, konu, yaklasik_tutar, ilan_tarihi, son_teklif_tarihi,
  usul, durum `yeni|inceleniyor|basvurulacak|basvurulmayacak|teklif_verildi|kazanildi|kaybedildi|iptal`, sorumlu, uygunluk_puani, olusturma/guncelleme)
- `semantic_tender_files` (tender_id, tur `sartname|ek|belge`, dosya_yolu, yukleyen, zaman)
- `semantic_tender_items` (tender_id, sira, sartname_metni, adet, isbn, eslesen_stok_kodu, eslesme_yontemi `isbn|ad|zeki|elle`, olasilik, stok, liste_fiyati,
  onerilen_fiyat, tahmini_maliyet, onaylayan)
- `semantic_tender_checklist` (tender_id, kalem, zorunlu, durum `var|eksik|gecersiz`, belge_id, gecerlilik_tarihi)
- `semantic_tender_documents` (id, ad, tur, gecerlilik_tarihi, dosya_yolu) — şirket belge arşivi
- `semantic_tender_decisions` (tender_id, karar `basvur|basvurma`, teklif_toplami, gerekce, oneren, onaylayan, zaman)
- `semantic_tender_results` (tender_id, sonuc, kazanan, kazanan_fiyat, bizim_fiyat, neden, kaynak)
- Yazmalar `semantic_audit`'e (`tender`, `tender_item`, `tender_decision`, `tender_document`).

**Uçlar** (`/api/v1/tenders/*`)
- `GET /` (süzgeç: durum, il, son tarih) · `POST /` · `GET /{id}` · `PATCH /{id}`
- `POST /{id}/files` · `POST /{id}/summarize` (iş) · `POST /{id}/items/import` (Excel/CSV/yapıştır) · `POST /{id}/items/match` (iş) · `PATCH /{id}/items/{sira}`
- `GET /{id}/pricing.xlsx` · `GET/PATCH /{id}/checklist` · `GET/POST /documents` · `GET /calendar`
- `POST /{id}/decision/submit|approve|reject` · `POST /{id}/result`
- `GET /public-sales?yil=` (kamu kurumlarına geçmiş satış) · `POST /run-due` (SYSTEM)

**Ekranlar** — `src/canvas/tenders/` (`TenderList.tsx`, `TenderDetail.tsx` (sekmeler: Özet · Kalemler · Belgeler · Karar · Sonuç), `DocumentsVault.tsx`,
`api.ts`). Rota `/timas/ihale` (+ `/ihale/:id`). Menü: `satis` alanı, `{ id: 'ihale', label: 'İhale takibi', section: 'Kurumsal' }`. Kampüs:
`ModulesMenu.tsx` → `M33: '/ihale'`. Telefonda liste, karar/onay ve bildirim; kalem eşleştirme masaüstü.

**Yetki** — `sayfa:ihale`; `ozellik:ihale.duzenle`, `ozellik:ihale.karar` (**explicit**; öneren onaylayamaz), `ozellik:ihale.belge` (şirket belge arşivi — finans),
`ozellik:ihale.kaynak-yonet` (yönetici; ikinci sürüm), Excel `ozellik:veri.disa-aktar`. `access.py` `RULES`: `("/api/v1/tenders/run-due", SYSTEM)`,
`("/api/v1/tenders/", frozenset({page("ihale")}))`; `FEATURE_RULES`: `pricing.xlsx` → `ozellik:veri.disa-aktar`, `decision/(approve|reject)` uç içinde
`ozellik:ihale.karar`.

**Zamanlayıcı** — `scripts/server/timas-tenders.{service,timer}`: her gün 07:30 `run-due` (son tarih ve belge geçerlilik hatırlatmaları, kamu satış özeti tazeleme).
İlan içe alma yalnız `TENDER_WATCH_ENABLED=1` ve kullanıcı kararıyla (ikinci sürüm); müşteri VM'inde varsayılan kapalı. İlk kez elle koşturulur.

**Kabul testleri**
1. Kamu kurumlarına satış (yıl) = `SELECT SUM(CASE WHEN L.TRCODE IN (7,8,9) THEN L.LINENET ELSE -L.LINENET END) FROM LG_411_01_STLINE L
   WHERE L.CLIENTREF IN (@kamu_clientref listesi: CRM AccountBase new_KurumRolu IN (2,3), StateCode 0 → new_logicalref) AND L.LINETYPE = 0 AND L.CANCELLED = 0
   AND L.INVOICEREF <> 0 AND L.TRCODE IN (2,3,7,8,9)` (CRM ve Logo iki ayrı sorgu, anahtar listesiyle birleştirme — iki kaynak tek sorguda olmaz).
2. ISBN eşleşmesi: yüklenen örnek şartnamede ISBN'i olan her kalem = `SELECT new_name FROM Timas_MSCRM.dbo.new_kitapBase WHERE <barkod/ISBN alanı> = @isbn AND statecode = 0`
   ile birebir; ISBN'siz kalemler «ad/Zeki» yöntemiyle ve olasılığıyla işaretli.
3. Stok: eşleşen her kitabın stok değeri = Logo stok bakiyesi (IOCODE 1,2 − 3,4; LINETYPE 0; CANCELLED 0; tarih filtresiz, güncel firma).
4. Fiyat: liste fiyatı = geçerli `PRCLIST` satış fiyatı (Kural 8; seçilen liste yazılı) ya da politika gereği CRM `new_kdvdahilfiyat` — hangisi olduğu ekranda.
5. Toplam: teklif tablosu toplamı = Σ(adet × önerilen fiyat) (kuruş; KDV ayrı satır).
6. Kamu kurum sayısı: `SELECT new_KurumRolu, COUNT(*) FROM Timas_MSCRM.dbo.AccountBase WHERE StateCode = 0 AND new_KurumRolu IN (2,3,4) GROUP BY new_KurumRolu` = ekrandaki süzgeç sayıları.
7. Yetki: `ozellik:ihale.karar` olmadan karar onayı 403; öneren onaylayamaz 409; `TENDER_WATCH_ENABLED=0` iken ilan içe alma uçları «bu ortamda kapalı» döner.

**Bağımlılık** — bağımsız başlanabilir (elle giriş + eşleştirme). Resmî ilan kaynağı izni ve müşteri kararı yalnız ikinci sürümü bekletir. M31/M32 ile paralel.

**Büyüklük** — M (1–2 gün) ilk sürüm; şartname özeti ve eşleştirme işi kuyruğuyla L'ye yaklaşabilir.
