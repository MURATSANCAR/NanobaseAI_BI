# M19 — Pazarlama Görsel Üretim ve Yaratıcı İçerik: kullanıcı ihtiyaç analizi

Durum: kod var (main) — test sunucusunda kabul bekliyor (testler koordinatörde) · Analiz tarihi: 2026-09-28 · Kaynaklar: `specs/M19.txt`, `specs/M21.txt` ve `specs/M22.txt` (M19 çıktısını okuyanlar), `ZEKİ_Veri_Haritasi2.html` (Görsel Girdileri, İçerik Girdileri), `docs/analiz/studyo-sayfa-plani-sozlesme.md` («J: Pazarlama kiti», kolaj kapak, seri karakter kartı), `apps/editor/src/editor/production/marketing.py` + `api_marketing.py` (şablonlar, görsel kaynakları, efektler, onay kaydı), `backend/semantic_bridge/editorial_studio_marketing.py`, `backend/semantic_bridge/access.py` (`ozellik:tasarim.uret` kuralı), `docs/analiz/yetki-mekanizmasi-2026-09-27.md` (`tasarim.pazarlama`), `PROJECT-MEMORY.md` (Kitap Tasarım Stüdyosu), `configs/semantic/knowledge/crm/table_descriptions.json` (döküm 2026-09-09), `docs/analiz/crm-eticaret-entegrasyon-2026-09-27.md`, `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`, `docs/analiz/seo-geo-modul-2026-09-25.md`, `docs/analiz/kullanici-ihtiyaclari/M15-yeni-kitap-pazarlama.md` (materyal brief'leri), kullanıcı belleği (editor-book-visuals-qwen-image, no-tech-names-on-screens, tsoft-no-write, seo-geo-module, editor-no-book-specific-development, llm-gate).

> Kural: sunucuya bağlanılmadı. Ölçülmemiş her şey **ölçülecek**, kanıtsız her iddia **varsayım**.

## 1. Modül ne işe yarar

Pazarlama planlarının (M15–M18) istediği görsel ve metin içeriğini üretir, onaylatır ve arşivler: sosyal medya görseli ve story, reklam banner'ları (farklı boyutlar), e-bülten başlık görseli, web kampanya banner'ı; reklam başlığı ve metni, sosyal medya açıklaması ve hashtag, 30–60 saniyelik video senaryosu, influencer brief'i. Her iş en az iki varyantla (A/B) gelir; tasarım ekibi görsel kaliteyi, pazarlama mesajı onaylar; onaylı varlıklar kitap ve kampanyaya bağlı, sürümlü bir arşivde durur (iş tanımı: K2 «ZEKİ üretir / tasarım onaylar», K2 «ZEKİ yazar / ekip onaylar»).

**Mevcut kodla örtüşme — yeniden yazılmayacak:** Kitap Tasarım Stüdyosu'nun «Pazarlama kiti» (studio J) bugün stüdyoda işi olan kitap için arka kapak yazısı, e-ticaret ürün sayfası (SEO'ya öneri), sosyal medya görselleri (kare 1080×1080, dikey 1080×1920, yatay 1200×628; kaynak kapak / iç sayfa resmi / alıntı; efekt düz/gölge/kontur/patlama/gökkuşağı; paletten renk; modelsiz dizim) ve öğretmen okuma kılavuzu üretiyor; her çıktı editör onayı istiyor, onaysız indirilemiyor, model üretimi görsel kullanan görsel «taslak — ticari kullanım izni bekleniyor» etiketli ve dosya adı `TASLAK-` ile başlıyor. M19 bu motoru **genişletir**: stüdyo işi olmayan kitaplar, reklam/banner boyutları, metin varyantları, iki aşamalı onay, kitaplar arası arşiv.

TİMAŞ'ın bugünkü sorunu: her kampanya görseli grafik ekibince tek tek hazırlanıyor (varsayım: masaüstü tasarım programlarıyla), boyut çoğaltma (aynı görselin 6–10 formatı) zaman alıyor, metinler dağınık (CRM kitap kartında sosyal medya metni ve hashtag alanı var), onaylı son sürümün nerede olduğu belirsiz.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Grafik tasarımcı (görsel onaycı ve düzeltici) | Grafik (CRM ekip 13 kişi; üretim kartında `new_sorumlugrafiker`; CRM `new_gorevbirimi` 1 = Grafik) | Her gün | Masaüstü |
| Sosyal medya / dijital pazarlama uzmanı (talep eden, kullanan) | Pazarlama (varsayım) | Her gün | Masaüstü + telefon (yayın) |
| Metin yazarı / kitap pazarlama sorumlusu | Pazarlama (varsayım: ayrı metin yazarı olup olmadığı bilinmiyor) | Kampanya başına | Masaüstü |
| Pazarlama müdürü (mesaj onaycısı) | Pazarlama | Haftada birkaç kez | Masaüstü; onay telefonda |
| Editör (alıntı ve içerik doğruluğu) | Editörya | Kitap başına | Masaüstü |
| E-ticaret sorumlusu (site banner'ı, ürün sayfası) | Varsayım | Kampanya başına | Masaüstü |

## 3. Bugün bu iş nasıl yapılıyor

- **Grafik** (varsayım): brief e-postayla/yüz yüze gelir; kapak dosyası grafik arşivinden (CRM üretim kartında «Baskı PDF», «Diğer kitap materyalleri» alanları; kapak alternatifleri ve oylaması CRM'de — `kapakalternatifi` 13.338, `kapaksecimi` 2.878); görsel masaüstü programda hazırlanır, her boyut elle çoğaltılır, e-postayla onaya gider. Tıkanma: boyut çoğaltma, sürüm karmaşası, onay e-postada.
- **Sosyal medya uzmanı**: metin CRM kitap kartındaki `new_sosyalmedyametni` ve `new_hastag` (3.587 kitapta dolu) alanlarından ya da sıfırdan; doluluk (sosyal medya metni) **ölçülecek**.
- **Stüdyo kullanıcısı (editör)**: stüdyoda işi olan kitaplar için pazarlama kitinden sosyal görsel ve arka kapak üretebiliyor (test sunucusunda; müşteri VM'inde stüdyo açık, pazarlama kitinin VM'deki durumu **ölçülecek**). Stüdyo işi yalnız okunmuş kitap ya da Word'den açılıyor; kataloğun geri kalanı için kit kullanılamıyor.
- **Marka kılavuzu**: depoda yok; varsa grafik ekibinde (varsayım).

## 4. İhtiyaçlar ve acı noktaları

**Grafik tasarımcı**
1. Tek ana tasarımdan bütün platform boyutlarının kendiliğinden çıkması (kapak kırpma ve yazı yerleşimi bozulmadan).
2. Marka kılavuzuna (renk, yazı tipi, logo yeri) uyan şablonlar; kurumun yazı tipleri.
3. Zeki AI'ın ürettiği görselin düzenlenebilir olması (başlık, renk, kaynak görsel değiştirme) — yeniden üretmeden.
4. Onayın kaydı ve sürüm geçmişi.

**Sosyal medya / dijital uzmanı**
1. Stüdyo işi olmayan kitap için de (yalnız kapak ve CRM metinleriyle) görsel ve metin.
2. Platforma göre karakter sınırına uyan başlık/açıklama varyantları ve hashtag önerisi.
3. A/B için en az iki varyant; hangi varyantın kullanıldığının kaydı.
4. Onaylı paketin tek zip'te, düzenli dosya adlarıyla indirilmesi.

**Pazarlama müdürü**
1. Mesaj onayı ile tasarım onayını ayrı görmek; kanıtsız iddia içeren metni yakalamak.

**Editör**
1. Kitaptan alıntıların birebir doğru olması.

## 5. Nasıl kullanmak isteyecekler

### Kullanıcı hikâyeleri
- Sosyal medya uzmanı olarak **plandaki bir materyal satırından tek tıkla içerik talebi** açmak istiyorum, çünkü brief'i yeniden yazmak istemiyorum.
- Sosyal medya uzmanı olarak **stüdyo işi olmayan bir backlist kitabı için kapaktan kare, dikey ve yatay görsel** üretmek istiyorum.
- Grafik tasarımcı olarak **ana görseli düzeltince bütün boyutların güncellenmesini** istiyorum.
- Dijital uzman olarak **5–10 reklam başlığı varyantını karakter sınırıyla** almak ve ikisini A/B için seçmek istiyorum.
- Pazarlama müdürü olarak **onay kuyruğumda yalnız mesajı** (metin) onaylamak istiyorum; tasarım onayı grafikte.
- Editör olarak **alıntı içeren varlıkta alıntının kitaptaki yerini** görmek istiyorum.
- E-ticaret sorumlusu olarak **site banner'ını doğru ölçüde** ve onaylı indirmek istiyorum.

### Ana ekranlar ve akış
- **İlk açılış (`/pazarlama/icerik`)**: iki sekme — **Talepler** (pano: Talep → Üretimde → Tasarım onayı → Mesaj onayı → Onaylı; kart: kitap kapağı, kanal, formatlar, termin, isteyen) ve **Arşiv** (onaylı varlıklar; kitap, kampanya, kanal, format, tarih süzgeci; sürümler).
- **Talep ekranı (`/pazarlama/icerik/:id`)**: solda brief (plandan gelir; hedef kitle, ton, mesaj hiyerarşisi), ortada varyant ızgarası (görsel × format), sağda metin varyantları (platforma göre sayaçlı), altta onay ve geçmiş.
- En sık üç işlem: (1) talep aç (plandan 1 tık, elle 3 alan); (2) «Üret» → varyantlar gelir, beğenileni seç — 2 tık; (3) onay — 1 tık + (retde) not.

### Zeki AI'ya soracakları
1. «Bu kitap için Instagram'a üç açıklama yaz, kitaptan birebir bir alıntı kullan, 5 hashtag öner.»
2. «Google reklamı için 30 karakteri geçmeyen 10 başlık yaz.»
3. «Bu kampanyanın 45 saniyelik video senaryosunu sahne sahne yaz.»
4. «Öğretmenler günü için bu beş kitabı anlatan influencer brief'i hazırla.»
5. «Geçen ay onaylanan görsellerden hangileri bu kitaba ait?»
6. «Bu metinde kanıtsız bir iddia var mı?»

### Otomasyon katmanı
| Adım | Katman | Not |
|---|---|---|
| Plandan talep açılması (M15 materyal satırı `tur` görsel/metin) | K1 | Plan onaylanınca talep kendiliğinden «Talep»e düşer |
| Boyut çoğaltma (ana tasarım → formatlar) | K1 | Modelsiz dizim |
| Görsel varyant üretimi | K2 | Kapak/iç sayfa/alıntı + şablon; model görseli yalnız istenirse ve «taslak» etiketli |
| Metin varyantları, hashtag, video senaryosu, influencer brief | K2 | Zeki AI taslak; sayaç ve yasaklı kalıp denetimi kodda |
| Tasarım onayı | K2 | Grafik |
| Mesaj onayı | K2 | Pazarlama müdürü (ya da yetkili) |
| Arşive yazma, sürüm, kitap/kampanya bağı | K1 | Onayla birlikte |
| Eğitim verisi (onaylı görsel–metin çiftleri) | K1 kayıt | Yalnız dışa aktarım (M50); model eğitimi bu modülde yok |

### Bildirim / uyarı
- Yeni talep → Grafik ekibi (talep kuyruğu rozeti; günlük özet e-posta).
- Tasarım onayı verildi → mesaj onaycısına.
- Onaylandı / reddedildi → talep edene.
- Termine 2 gün kalan ve onaylı olmayan talep → talep eden ve grafik sorumlusu.
- Kanal: Uyarılar rozeti + günlük özet e-posta (tek tek değil).

### Onay ve yetki
- Görür: `sayfa:pazarlama-icerik`.
- Talep açar: `ozellik:icerik.talep`. Üretir/düzenler: `ozellik:icerik.uret`; model ile görsel üretimi ayrıca mevcut `ozellik:tasarim.uret` ister (GPU harcar).
- Tasarım onayı: `ozellik:icerik.tasarim-onay` (explicit). Mesaj onayı: `ozellik:icerik.mesaj-onay` (explicit). Aynı kişi iki onayı birden veremez.
- Arşivden indirme: `ozellik:veri.disa-aktar` gerektirmez (asıl iş), `sayfa:pazarlama-icerik` yeter; taslak (lisans bekleyen) varlık `TASLAK-` adıyla iner.

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Onaylı kapak (yüksek çözünürlük) | Stüdyo kapak açılımı (işi varsa; `_cover_front`); CRM `new_resimurl` (göreli yol, 7.886 kitap); T-soft ürün görseli (SEO modülü okuyor); grafik arşivi (M14) | Stüdyo kapağı var | Stüdyo dışı kitapta yüksek çözünürlüklü kapak kaynağı **uzmana sorulacak** (CRM/T-soft görselleri web boyutunda olabilir — **ölçülecek**) |
| Marka paleti, tipografi, logo | Kullanıcı yükler (marka kiti) | **Yok** | Grafik ekibinden alınacak |
| Kurum yazı tipleri ve lisansları | Kullanıcı | **Yok**; stüdyoda açık lisanslı yazı tipleri var (Special Elite Apache 2.0, Courier Prime, Poppins OFL) | Kurum yazı tipinin sunucuda kullanım lisansı **uzmana sorulacak** |
| Platform boyutları | Sabit tablo (kodda) | Stüdyoda 3 şablon | Banner boyutları eklenmeli (aşağıda) |
| Brief, hedef kitle, ton, mesaj hiyerarşisi | M15 planı (`semantic_mkt_materials`, plan satırları, karne) | M15 henüz yok | Yoksa talep formunda elle |
| Kitap metinleri (alıntı, özet) | Stüdyo el yazması (işi varsa, yalnız stüdyo servisi görür); CRM `new_ozet`, `new_kitapspotu`, `new_kitabinenonemlicumlesi` (5.459), `new_alintlar` (1.622), `new_sosyalmedyametni`, `new_hastag` (3.587) | Kısmen ölçülü | — |
| Kitap iç resimleri | Stüdyo (resimli kitaplarda) | Var | Stüdyo dışı yok |
| Varlık arşivi | Köprü dosya alanı (yeni) + stüdyo iş klasörü `pazarlama/` | Stüdyo içinde iş başına | Kitaplar arası arşiv yok (yeni) |
| Görsel modelin ticari izni | — | **İzin yok** (bellek): model görseli taslak | İzin gelene kadar yalnız modelsiz görseller «onaylı» olabilir |

## 7. Diğer modüllerle bağ

- **Girdi**: M15 (materyal brief'leri, hedef kitle, ton) · M16 (lansman günü içerik ihtiyacı) · M17 (yeniden keşfet içerikleri) · M18 (aylık içerik takvimi, föy görselleri) · M53 (set/hediye tanıtım görseli) · M13/M14 ve stüdyo (kapak, iç resim, palet, karakter kartı).
- **Çıktı**: M21 (reklam materyalleri — «Onaylı görsel ve metin materyalleri (M19)») · M22 (sosyal medya içerikleri) · M23 (influencer brief) · M24 (e-bülten başlığı) · M25/SEO (ürün sayfası metni → `external_proposal`) · M50 (onaylı görsel–metin çiftleri, eğitim verisi olarak dışa aktarım).

## 8. Kısıtlar

- **Görsel modelin lisansı ticari kullanıma izin vermiyor** (bellek): model üretimi görsel kullanan her varlık «taslak — ticari kullanım izni bekleniyor» etiketli, dosya adı `TASLAK-`; mesaj ve tasarım onayı alsa bile «yayına hazır» sayılmaz. Modelsiz dizim (kapak + şablon + yazı) bu kısıta takılmaz.
- **Ekranda teknoloji adı yok**: «Zeki AI görsel üretimi».
- **Dış kanala yayın yok**: M19 üretir ve arşivler; yayın M21/M22'de ve insan eliyle.
- **CRM'e yazma yok**: iş tanımındaki «Dynamics CRM kampanyasına bağlantılı» arşiv bağı köprünün kendi tablosunda; CRM kitap kartına işlenecek sosyal medya metni «CRM'e işlenecek» listesinde.
- **T-soft'a yazma yasak**: ürün sayfası metni yalnız SEO önerisi.
- **Kitaba özel çözüm yok** (editör kuralı): şablonlar ve kurallar kitaptan bağımsız.
- **Hukuki**: influencer işbirliği içeriklerinde reklam olduğunun belirtilmesi (Reklam Kurulu'nun sosyal medya etkileyicileri kılavuzu — **varsayım**, hukuk birimi doğrulamalı); kanıtsız üstünlük iddiası yasak kalıp listesinde; yazar fotoğrafı ve alıntı kullanım hakkı sözleşmeye bağlı (M6); kurum yazı tiplerinin sunucuda kullanım lisansı.
- **KVKK**: influencer adı/hesabı brief'te kişisel veri; M23'ten okunur, dışa aktarım yetkiyle.

## 9. Kapsam önerisi

**İlk sürüm**
- Talep kuyruğu (plandan ve elle), iki aşamalı onay, arşiv (kitap/kampanya/kanal/format, sürüm).
- Üretim yolu A — **stüdyo işi olan kitap**: mevcut pazarlama kiti uçları (sosyal görsel, arka kapak, ürün sayfası) köprüden çağrılır; çıktı arşive bağlanır.
- Üretim yolu B — **stüdyo işi olmayan kitap**: stüdyoda yeni «pazarlama işi» türü (`kind: marketing`, `studio.new_job(extra=)` kancası; boyama kitabı türetmesiyle aynı yol): kapak görseli + CRM metinleri + palet (kapaktan çıkarılır) → aynı `render_social` dizimi. Kitap metni yoksa alıntı yalnız CRM alanlarından.
- Yeni formatlar: reklam/banner boyutları (ör. 1080×1350 dikey gönderi, 1200×1200, 300×250, 728×90, 160×600, 320×50, 1920×600 site bandı, 600×200 e-bülten başlığı — kesin liste grafik ekibiyle belirlenir).
- Metin: reklam başlığı/metin varyantları (platform sayaçlı), açıklama + hashtag (CRM hashtag'i önce), video senaryosu, influencer brief; yasaklı kalıp denetimi; alıntı doğrulama.
- Marka kiti yükleme (palet, logo, yazı tipi dosyası + lisans notu).

**Sonraki sürüm**
- Ana tasarımda düzenleme (başlık konumu, kaynak görsel kırpma) ve bütün boyutlara yayma — kullanıcıya düzenleme paneli.
- Varyant performansı (M21/M22 bağlanınca hangi varyant daha iyi).
- Model görsel üretimi ticari izin gelince «onaylı» olabilir.

**Mevcut kodda yeniden kullanılacaklar**
- `apps/editor/src/editor/production/marketing.py`: `render_social`, `social_sources`, `source_image`, `palette_colors`, `_draw_headline`, `_fit`, `add_social`, `approve_social`, `social_zip`, `product_*`, `gen_back`, `digest`, `in_book`/`clean_quote` (alıntı doğrulama), `log_event` (onay kaydı).
- `apps/editor/src/editor/production/api_marketing.py` ve köprü `backend/semantic_bridge/editorial_studio_marketing.py` (vekil uçlar, `studio_*` denetim kaydı).
- `studio.new_job(..., extra=)` (türetilmiş iş kancası), `cover_text` yazı tipleri, `palette.py`.
- `seo_geo/__init__.py` `external_proposal`.
- `backend/semantic_bridge/freelance.py`: dosya alanı düzeni (`FREELANCE_DIR` gibi `MARKETING_ASSETS_DIR`), nginx yükleme boyutu betiği kalıbı (`deploy/nanobase-direct/add-freelance-routes.py`).

## 10. Uzmanlara sorulacak sorular

1. Marka kılavuzu (renk, yazı tipi, logo kullanımı) var mı; kurum yazı tiplerinin sunucuda kullanım lisansı var mı?
2. Hangi platformlar ve hangi boyutlar standart (sosyal, reklam, site, e-bülten)? Yayınevi markalarına (alt markalar) göre ayrı şablon gerekiyor mu?
3. Yüksek çözünürlüklü kapak dosyaları nerede duruyor (grafik arşivi, üretim kartı)? Portal okuyabilir mi?
4. Görsel onayını kim, mesaj onayını kim veriyor; tek kişi yeter mi?
5. Metin yazarı ayrı bir rol mü, kitap pazarlama sorumlusu mu yazıyor?

## 11. Başarı ölçütü

- Talep → onaylı varlık süresi (ortanca), ilk ay taban alınır.
- Grafik ekibinin boyut çoğaltmaya harcadığı iş (talep başına elle düzeltilen format sayısı) — azalma.
- Zeki AI metin varyantlarından düzeltmesiz onaylananların oranı; yasaklı kalıp yakalanma sayısı.
- Onaylı varlıkların %100'ünün bir kitaba ve (varsa) plana bağlı olması; arşivden yeniden kullanım sayısı.
- Teknoloji adı taraması 0; lisans bekleyen varlığın «onaylı/yayına hazır» görünme sayısı 0.

## 12. Uzman gözüyle en iyi sistem

**Kim konuşuyor:** 15 yıllık yaratıcı ekip lideri (grafik + sosyal medya).

**Sektörde iyi örnekler** (genel sektör uygulaması; TİMAŞ'ta doğrulanmadı): ekipler marka şablonlu tasarım araçlarında «bir kez tasarla, her boyuta uyarla» çalışır; dijital varlık yönetimi (DAM) her varlığı ürün/kampanya/kanal etiketiyle, sürüm ve kullanım hakkıyla tutar; reklamlarda aynı mesajın birkaç başlık/görsel varyantı dönüşümle sınanır; onay akışı yaratıcı ve marka onayını ayırır.

**TİMAŞ için mükemmel sistem:** planda «Instagram gönderisi, 3 adet» yazıyorsa talep kendiliğinden açılmış; kapaktan ve kitaptan birebir alıntıyla varyantlar hazır; grafik yalnız ince ayar yapıyor; onaylı paket tek tıkla doğru adlarla iniyor; altı ay sonra «bu kitabın bütün görselleri» tek aramada.

**Bir iş günü:**
- 09:00 — Grafik lideri talep panosunu açar: 9 yeni talep (6'sı dünkü onaylı M15 planlarından kendiliğinden). Termine göre sıralar, ikisini ekibe atar.
- 09:30 — Bir backlist kitabı (stüdyo işi yok): «Üret» → kapaktan kare/dikey/yatay/banner varyantları + CRM'deki en önemli cümleyle alıntı görseli. Renk kapaktan çıkmış; birinde başlık kapağın yazısını örtüyor, kaynağı iç sayfa yerine kapak kırpması yapar.
- 11:00 — Sosyal medya uzmanı metin sekmesinde 8 açıklama varyantından ikisini seçer; biri «Türkiye'nin en çok okunan…» dediği için yasaklı kalıp uyarısı almış, düzeltir.
- 13:30 — Grafik onayı → pazarlama müdürü telefonda mesaj onayını verir.
- 15:00 — E-ticaret sorumlusu site bandını arşivden indirir; dosya adı `kitap-adi_site-bandi_1920x600_v2.png`.
- 17:00 — Arşivde «Öğretmenler Günü 2026» etiketiyle 40 varlık; gelecek yıl aynı etiketle bulunacak.

**«Bunu görürsem hemen kullanırım» (3):**
1. Tek tasarımdan bütün boyutlar, marka şablonuyla, bozulmadan.
2. Planın materyal satırından kendiliğinden açılan talep ve iki aşamalı onay.
3. Kitaba ve kampanyaya bağlı, sürümlü, aranabilir arşiv.

**«Bunu yaparsanız kullanmam» (3):**
1. Düzenlenemeyen, «al ya da yeniden üret» görsel.
2. Lisansı belirsiz model görselini «onaylı» gösterip yayına sokmak.
3. Kurum yazı tipi ve renkleri yerine genel şablon; ya da her varyant için ayrı ayrı onay e-postası.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (hangi tablo/görünüm/ölçü) | CRM (hangi varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Talep açma | — | — (plan köprüde) | — | Deterministik |
| Kitap bilgisi | `LG_{firma}_ITEMS` (stok kodu doğrulama) | `new_kitapBase` (`new_name`, `new_yazartext`, `new_resimurl`, `new_ozet`, `new_kitapspotu`, `new_kitabinenonemlicumlesi`, `new_alintlar`, `new_hastag`, `new_sosyalmedyametni`, `new_hedefkitle`) | — | Kaynak metin |
| Görsel dizimi (şablon, boyut, renk) | — | — | — (modelsiz; Pillow dizimi) | Deterministik, lisans sorunu yok |
| Model ile görsel (istenirse) | — | — | Stüdyonun görsel modeli (GPU, sırayla; ana model devri kuralı) — çıktı «taslak» | Yalnız istenince |
| Görsel başlığı (görsel üstü yazı) | — | Kitap metin alanları | 3–5 kısa başlık önerisi | Metin üretimi |
| Metin varyantları (reklam, açıklama, video senaryosu, influencer brief) | — | Kitap metin alanları; M15 brief'i | Varyantlar; kod platform sayacı ve yasaklı kalıp denetimi yapar | Asıl model değeri |
| Hashtag | — | `new_hastag` (önce CRM), `new_AnahtarKelimeler`, anahtar kelime N:N | CRM'de yoksa öneri | Öneri |
| Alıntı doğrulama | — | CRM metin alanı ya da stüdyo el yazması | — (kod: normalleştirilmiş birebir arama `in_book`) | Deterministik |
| Kanıtsız iddia denetimi | Gerekirse satış sırası (Logo) kanıt olarak | — | İddia cümlesi sınıflandırma: «üstünlük iddiası mı?» evet/hayır (tek token + olasılık); yasaklı kalıp listesi kodda | Yargı + kural |
| Arşiv arama | — | — | — | Deterministik |

Model çağrıları: metin işleri köprüde LLM kapısından `rt.llm_for("marketing", NORMAL)` (ekranda bekleniyor), toplu varyant `BATCH`. Kitap metnine dayanan işler (stüdyo işi olan kitap) stüdyo servisinde, stüdyonun kendi kapısı (`book-director` takma adı, gateway) üzerinden — kitap metni köprüye taşınmaz. `LlmClient` doğrudan kurulmaz.

## 14. Kodlama planı (kodlayıcıya devir)

**İki parça**: (A) köprüde talep/onay/arşiv ve metin; (B) stüdyoda (GPU editör servisi) kitapsız pazarlama işi ve yeni formatlar.

**(A) Köprü — `backend/semantic_bridge/marketing/creative.py` + `creative_api.py`** (pazarlama paketi varsa içine; yoksa `backend/semantic_bridge/marketing_creative.py` olarak bağımsız — M15'i beklemez)

Tablolar:
- `semantic_mkt_creative_requests`: `id` (`MC-<yıl>-<sıra>`), `tenant_id`, `plan_id` (ops.), `materyal_id` (ops.), `stok_kodu`, `studio_job` (ops.), `kanal` (`instagram|facebook|x|linkedin|tiktok|youtube|google-ads|meta-ads|site|e-bulten|diger`), `formatlar` (json), `metin_turleri` (json: `baslik|aciklama|reklam-metni|video-senaryosu|influencer-brief|hashtag`), `brief`, `termin`, `durum` (`talep|uretimde|tasarim-onayi|mesaj-onayi|onayli|reddedildi|arsiv`), `isteyen`, `atanan`, `olusturma`.
- `semantic_mkt_assets`: `id`, `request_id`, `stok_kodu`, `tur` (`gorsel|metin`), `format` (`kare-1080|dikey-1080x1920|yatay-1200x628|banner-300x250|…`), `varyant` (A/B/C…), `dosya_yolu` (`MARKETING_ASSETS_DIR/<id>.png`) ya da `studio_ref` (`<iş>/<sid>`), `metin`, `kaynak` (`studio-kit|studio-marketing-job|zeki|yukleme`), `taslak_lisans` (bool — model görseli), `dogrulama_json` (alıntı, sayaç, yasaklı kalıp), `surum`, `onceki_id`, `tasarim_onaylayan`, `tasarim_onay`, `mesaj_onaylayan`, `mesaj_onay`, `etiketler` (json: kampanya, sezon), `kullanildi_json` (M21/M22 bildirirse).
- `semantic_mkt_brand`: `surum`, `palet_json`, `logo_dosyalari`, `yazi_tipleri_json` (dosya + lisans notu), `kurallar_metni`, `yukleyen`, `zaman`.
- `semantic_mkt_banned_phrases`: `kalip`, `aciklama`, `ekleyen` (yasaklı kalıp listesi; ekrandan yönetilir).

Uçlar (`/api/v1/marketing/creative/…`):
- `GET requests?durum=&kanal=&stok=&atanan=`, `POST requests`, `GET|PATCH requests/{id}`.
- `POST requests/{id}/produce` (görseller: stüdyo işi varsa `…/studio/jobs/{iş}/marketing/social`; yoksa (B)'deki pazarlama işi; iş kuyruğu, durum `GET requests/{id}/jobs`).
- `POST requests/{id}/copy` (`{turler, platform, adet}` → Zeki AI varyantları + denetim).
- `PUT assets/{aid}` (metin düzelt / yeni sürüm), `POST assets/{aid}/approve` (`{seviye: tasarim|mesaj}`; aynı kişi iki seviye → 409), `POST assets/{aid}/reject`.
- `GET assets?stok=&etiket=&kanal=&format=&durum=onayli` (arşiv, tavansız sayfalı), `GET assets/{aid}/file`, `GET requests/{id}/zip`.
- `GET|PUT brand`, `GET|PUT banned-phrases`.
- `GET contract/assets?stok=&kanal=&durum=onayli` (M21/M22/M24 okur).

Dosyalar: `MARKETING_ASSETS_DIR` (öntanım `/data/nanobaseai/bi/var/marketing-assets`, köprü kullanıcısının); nginx yükleme sınırı (marka kiti, yazı tipi) `deploy/nanobase-direct/` altında freelance betiği kalıbıyla; VM `web.default.conf.template`.

**(B) Stüdyo — `apps/editor/src/editor/production/marketing_job.py`** (+ `api_marketing.py`'ye uçlar)
- `POST /v1/studio/marketing-jobs` `{stok_kodu, baslik, yazar, kapak_url|kapak_dosyasi, metinler:{ozet, spot, alinti[], hashtag}}` → `studio.new_job(..., extra={"kind": "marketing"})`; el yazması yok, kapak görselinden palet (`palette.py`).
- `marketing.TEMPLATES`'e yeni boyutlar (liste uzmanla kesinleşir); `render_social` kitapsız işte `VISUALS = cover|quote` ile çalışır (iç sayfa yok).
- Köprü vekili `editorial_studio_marketing.py`'ye `marketing-jobs` yolu; GPU giriş kapısı betiğine yeni blok (`deploy/tt-gpu/editor-ingress/`, `EDITOR-STUDYO-PAZARLAMA-IS`); VM kart beyaz listesine yol (bellek: yeni kart ucu = yeni location).
- Görsel model çağrısı yalnız kullanıcı isterse ve `ozellik:tasarim.uret` ile; gateway devri kuralı aynı.

**Ekranlar**: `src/canvas/marketing/creative/` — `CreativeHome.tsx` (sekmeler `RequestsBoard.tsx` pano, `AssetLibrary.tsx` arşiv ızgarası), `RequestScreen.tsx` (brief, varyant ızgarası, metin sayaçları, onay), `BrandKit.tsx` (Yönetim → Pazarlama altında ya da sekme). Mevcut stüdyo bileşenleri `src/canvas/editorial/studio/marketing/SocialTab.tsx` ve `parts.tsx` yeniden kullanılır. Rotalar `/pazarlama/icerik`, `/pazarlama/icerik/:id`. Menü (alan `pazarlama`, yeni bölüm **«Üretim»**): `{ id: 'pazarlama-icerik', label: 'Görsel ve metin', to: '/pazarlama/icerik', section: 'Üretim', keywords: ['görsel', 'banner', 'sosyal medya', 'reklam metni', 'hashtag'] }`. Kampüs `LIVE.M19 = '/pazarlama/icerik'`.

**Yetki**: `sayfa:pazarlama-icerik`; `ozellik:icerik.talep`, `ozellik:icerik.uret`, `ozellik:icerik.tasarim-onay` (explicit), `ozellik:icerik.mesaj-onay` (explicit); model görseli ayrıca `ozellik:tasarim.uret`; marka kiti düzenleme `ozellik:icerik.marka` (explicit). `access.RULES`: `/api/v1/marketing/creative` → `page("pazarlama-icerik")`; `FEATURE_RULES`: `POST ^/api/v1/marketing/creative/requests$` → `icerik.talep`; `POST ^/api/v1/marketing/creative/requests/[^/]+/(produce|copy)$` → `icerik.uret`; onaylar ucun içinde.

**Zamanlayıcı**: gerekmez (üretim isteğe bağlı). Günlük özet e-postası pazarlama zamanlayıcısına (`timas-marketing.timer`, M15) eklenir; yoksa `POST /api/v1/marketing/creative/run-due` için ayrı günlük tetik.

**Kabul testleri** (test sunucusu + GPU stüdyosu; gerçek CRM .28)
1. **Kitap bilgisi**: `SELECT new_name, new_yazartext, new_hastag, new_kitabinenonemlicumlesi FROM Timas_MSCRM.dbo.new_kitapBase WHERE new_StokKodu = '<kod>'` = kitapsız pazarlama işine giden `metinler` (karakter karakter); önerilen hashtag listesi CRM hashtag'ini içerir.
2. **Boyut**: her format dosyası tam piksel ölçüsünde (ör. 1080×1080, 1080×1920, 1200×628, 300×250, 728×90) — PIL ile okunur.
3. **Kapak**: stüdyo işi olan kitapta üretilen görseldeki kapak kaynağı stüdyonun ön kapak kırpmasıyla aynı (`_cover_front` çıktısının özeti); stüdyo işi olmayanda `kapak_url`'den indirilen dosyanın özeti iş klasöründe kayıtlı.
4. **Alıntı**: alıntı içeren her varlıkta alıntı kaynağında (`in_book` normalleştirmesiyle) bulunur; bulunmayan varyant üretilmez ve sayısı yazılır.
5. **Sayaç ve yasaklı kalıp**: platform sınırını aşan metin varyantı 0; yasaklı kalıp listesindeki bir ifadeyi içeren varyant «uyarı» durumunda.
6. **Onay**: aynı kişi tasarım ve mesaj onayını birlikte veremez (409); `icerik.tasarim-onay` olmayan 403; her onay `semantic_audit`'te; model görseli onaylı olsa da indirilen adı `TASLAK-` ile başlar.
7. **Arşiv**: `SELECT COUNT(*) FROM semantic_mkt_assets WHERE stok_kodu = '<kod>' AND mesaj_onay IS NOT NULL` = arşiv ekranında o kitabın onaylı varlık sayısı; zip'teki dosya sayısı aynı.
8. **Teknoloji adı**: ekran ve iner dosya adlarında model/ürün adı taraması 0.
9. **Kitapsız iş**: stüdyo işi olmayan bir backlist kitabında kare/dikey/yatay üretimi GPU görsel modeli açılmadan tamamlanır (gateway kaydında görsel model devri yok).

**Bağımlılık**: Stüdyo pazarlama kiti (var). M15 bağımsız: talepler elle de açılır; M15 gelince plan bağlantısı çalışır. (B) stüdyo değişikliği GPU'ya kurulum gerektirir (dağıtım sırası: main → test sunucusu + GPU → VM). M21/M22 sonra bağlanır.

**Tahmini büyüklük**: L (köprü M + stüdyo kitapsız iş ve formatlar M; toplam 3 gün).
