# M20 — Basın, Medya ve Halkla İlişkiler: kullanıcı ihtiyaç analizi

Durum: analiz (kod yok) · Tarih: 2026-09-28 · Kaynaklar: `specs/M20.txt` (ZEKİ_Moduller3.html), `ZEKİ_Veri_Haritasi2.html` (PR Girdileri, Medya Takip), `configs/semantic/knowledge/crm/table_descriptions.json` (CRM MetadataSchema 2026-09-09), `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`, `docs/analiz/kitap-yazar-web-taramasi-2026-09-24.md`, `docs/analiz/yetki-mekanizmasi-2026-09-27.md`, `backend/semantic_bridge/web_watch.py`, `author_relations.py`, `editorial_studio_marketing.py`, `alerts.py`, `access.py`, `access_catalog.json`, `src/canvas/nav/navModel.ts`, `docs/LLM-KAPISI.md`, kullanıcı belleği (web-watch-open-sources, customer-vm-web-watch-off, no-tech-names-on-screens, tsoft-no-write, crm-systemuser-directory, logo-155-frozen-copy).

> Kural: sunucuya bağlanılmadı. Sayılar yalnız depodaki ölçümlerden alındı; ölçülmemiş her şey **ölçülecek**, kanıtsız her iddia **varsayım** diye işaretlidir.

## 1. Modül ne işe yarar

Yeni ve önemli kitaplar için basın bülteni, medya kiti ve kişiye özel tanıtım e-postası (pitch) hazırlanır; kitabın konusuna uyan gazeteci, editör, köşe yazarı, podcast ve YouTube kanalı listesi çıkarılır; kime ne gönderildiği, kimin cevap verdiği ve hangi haberin çıktığı takip edilir; haftalık yansıma raporu üretilir (iş tanımı M20: kartlar «Medya Listesi & Hedefleme» K2, «Basın Bülteni & Medya Kiti» K2; eğitim K2 onay, K3 yansıma analizi).

TİMAŞ'ın bugünkü sorunu: CRM'de bir **Haber** modülü var (`new_haberlerBase`, 1.369 kayıt: haber tarihi, başlık, bağlantı, mecra, haberi yapan kişi, basında görüşülen kişi, kitap gönderimi, basın ziyareti, medya planı, hangi Timaş sitesinde yayınlandığı), ama son değişikliği **2025-06**'da; 2026-09-15 ölçümünde «ölü modül» sayıldı (`crm-timas-mscrm-detay-2026-09-15.md`). Yani basın takibi ya CRM dışına (Excel/e-posta, **varsayım**) kaydı ya da hiç tutulmuyor. Bülten metni kitap kartında tek bir serbest alanda (`new_kitapBase.new_BasnBlteni`) duruyor; gönderim, cevap ve yansıma birbirine bağlı değil.

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Basın/PR sorumlusu (halkla ilişkiler uzmanı) | Pazarlama (CRM TeamMembership «Pazarlama» 35 kişi; PR'ın ayrı ekip olup olmadığı **varsayım**, AD'de unvan/bölüm boş — `crm-systemuser-directory`) | Her gün | Masaüstü (bülten, liste); telefon (yansıma kaydı, gazeteciyle görüşme sonrası not) |
| Pazarlama müdürü | Pazarlama | Haftada 1–2 (onay, rapor) | Telefon + masaüstü |
| Yayın yönetmeni / kitabın editörü | Editörya (TeamMembership «Editörya» 54) | Kitap başına birkaç kez (bülten içeriğinin doğruluğu, röportaj soruları) | Masaüstü |
| Genel müdür / üst yönetim | Yönetim | Ayda 1 (yansıma raporu) | Telefon |
| Yazar (dolaylı) | Dışarıda; portala giremez | Röportaj takvimi | — (e-postayla) |

Rol-kişi eşlemesi veride yok: CRM `SystemUser` unvan/birim alanları neredeyse boş, AD'de title/department boş. Kimin PR işini yaptığı **uzmana sorulacak** (bölüm 10).

## 3. Bugün bu iş nasıl yapılıyor

- **PR sorumlusu** (varsayım, CRM izine dayanarak): kitap kartından arka kapak metni (`new_ozet`) ve kısa/uzun tanıtım (`new_kisabilgi`, `new_uzunbilgi`) alınır → Word'de bülten yazılır → kişisel adres defterinden/Excel'den gazetecilere e-posta atılır → kitap gönderimi CRM'de «Pazarlama (Tanıtım Gönderimi)» tipli sipariş olarak açılır (`new_siparisBase.new_siparistipi = 12`; bu tipin hacmi **ölçülecek**) → çıkan haber bir zamanlar CRM Haber kaydına girilirdi (2025-06'dan beri girilmiyor). Tıkandığı yer: gönderim–cevap–yansıma zinciri kopuk; hangi gazeteciye hangi kitap gitti, geri dönüş oldu mu sorusunun tek kaynağı yok.
- **Gazeteci listesi**: CRM `ContactBase`'te «Basın medya Mecrası» (`new_ilgilioldugumecra`) ve iş unvanı alanları var; kaç kişide dolu olduğu **ölçülecek**. İlgi alanı/yazdığı konu alanı yok.
- **Yansıma takibi**: test sunucusunda «Basın ve web» ekranı 55 açık RSS akışında yazar ve kitap adını arıyor (`web_watch.py`, gece 02:30); **müşteri VM'inde kapalı** (`WEB_WATCH_ENABLED=0`, kullanıcı kararı 2026-09-25). Basılı gazete, TV ve radyo yansıması için hiçbir kaynak yok.
- **Pazarlama müdürü**: rapor muhtemelen elle derleniyor (**varsayım**).

## 4. İhtiyaçlar ve acı noktaları

**PR sorumlusu**
1. Kitap başına tek «PR dosyası»: bülten, medya kiti, gönderim listesi, cevaplar, yansımalar aynı yerde.
2. Bülten ve pitch taslağının kitabın kendi bilgisinden (CRM kartı + stüdyo pazarlama kiti) dakikalar içinde gelmesi.
3. «Bu kitabı kime göndereyim?» sorusuna geçmiş haberlerden gerekçeli cevap (bu gazeteci daha önce hangi Timaş kitabını yazdı).
4. Gönderim sonrası hatırlatma: 5 gün cevap yoksa takip.
5. Yansıma kaydını telefondan 30 saniyede girmek (bağlantı yapıştır → kitap/yazar/mecra otomatik dolsun).

**Pazarlama müdürü**
1. Bülten ve listeyi göndermeden önce onaylamak (K2).
2. Haftalık/aylık yansıma sayısı, mecra dağılımı, en çok haber alan kitaplar.
3. PR emeğinin satışa etkisini görmek (haber tarihi etrafında kitabın satışı — Logo).

**Editör / yayın yönetmeni**
1. Bültende kitap hakkında yanlış bilgi çıkmaması (yayın tarihi, fiyat, yaş grubu CRM'den).
2. Röportaj soru setinin kitabın metnine dayanması.

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- PR sorumlusu olarak yeni çıkan kitabı seçip bülten taslağını tek tıkla almak istiyorum, çünkü her kitap için sıfırdan yazmak yarım günümü alıyor.
- PR sorumlusu olarak kitaba uygun medya kişilerini geçmiş haberlerine göre sıralı görmek istiyorum, çünkü listeyi hafızamdan kuruyorum.
- PR sorumlusu olarak her gazeteciye kendi mecrasına uygun kısa bir pitch taslağı görmek istiyorum, çünkü toplu e-posta cevap almıyor.
- PR sorumlusu olarak gönderim, cevap ve yayın durumunu tek listede izlemek istiyorum, çünkü takip e-posta kutusunda kayboluyor.
- PR sorumlusu olarak çıkan haberin bağlantısını yapıştırıp kaydetmek istiyorum, çünkü yansıma arşivi dağınık.
- Pazarlama müdürü olarak gönderimden önce bülteni ve listeyi onaylamak istiyorum, çünkü kurum adına dışarı giden her metin benim sorumluluğumda.
- Pazarlama müdürü olarak ay sonunda yansıma raporunu PDF almak istiyorum, çünkü yönetime sunuyorum.
- Editör olarak bültendeki kitap bilgisinin CRM ile uyuştuğunu görmek istiyorum, çünkü yanlış yaş grubu/tarih geri dönüşü zor bir hata.

**Ana ekranlar ve akış**
- İlk açılış (`/timas/basin-iliskileri`): «Bu ay çıkan/çıkacak kitaplar» şeridi (CRM ilk baskı tarihi) + her kitapta PR dosyası durumu (yok / taslak / onayda / gönderildi / yansıma var) + «Cevap bekleyen gönderimler» + «Son yansımalar».
- En sık 3 işlem: (1) Kitap → «PR dosyası aç» → bülten taslağı gelir: 2 tık. (2) Gönderim satırında «cevap geldi/haber çıktı» işareti: 1 tık. (3) Yansıma ekle (bağlantı yapıştır): 2 tık + yapıştır.
- Diğer ekranlar: Medya kişileri (liste + kişi kartı: mecra, geçmiş haberleri, gönderimler, son temas), Yansımalar (arşiv, süzgeç: kitap/mecra/tarih), Rapor.

**Zeki AI'a soracakları**
- «Geçen ay hangi kitaplarımız basında çıktı?»
- «Bu yıl en çok haber alan beş yazarımız kim?»
- «[Kitap] için kime bülten gönderdik, kaçı dönüş yaptı?»
- «Çocuk kitabı yazan gazetecilerden son altı ayda bizimle temas etmeyenler kim?»
- «[Yazar] röportajı için kitabın ana temalarından beş soru hazırla.»
- «[Kitap] bülteninin yerel basın için kısa sürümünü yaz.»
- «Haber çıktıktan sonraki iki haftada [kitap] satışı ne oldu?» (rakam Logo'dan; veri 2026-08-17'de kesiliyor — bkz. bölüm 6)

**Otomasyon katmanı**
- K1: yansıma adayı toplama (yalnız test sunucusunda, açık RSS; müşteride kapalı), haftalık rapor derleme, takip hatırlatıcısı.
- K2: bülten/medya kiti/pitch taslağı, medya kişisi sıralaması → PR sorumlusu düzenler, pazarlama müdürü onaylar; e-posta onaydan sonra ve **tek tek** gider.
- K3: yansımanın tonu (olumlu/nötr/olumsuz) ve kitapla ilgisi → Zeki sınıflar, insan düzeltir.
- K4 (yalnız insan): basın ziyareti, röportaj pazarlığı, kriz açıklaması.

**Bildirim/uyarı**
- PR sorumlusuna: onay çıktı / reddedildi (portal içi + e-posta), gönderimden N gün sonra cevap yok (varsayılan 5 gün, ayar), yeni yansıma adayı (test sunucusunda).
- Pazarlama müdürüne: onay bekleyen PR dosyası (portal Uyarılar rozeti), haftalık yansıma özeti (Planlı raporlar yolu, pazartesi 09:00).

**Onay ve yetki**
- `sayfa:basin-iliskileri` — görmek.
- `ozellik:pr.duzenle` — PR dosyası, medya kişisi, yansıma yazmak.
- `ozellik:pr.onay` (açıkça verilir, explicit) — bülten ve gönderim listesini onaylamak.
- `ozellik:pr.gonder` (açıkça verilir) — onaylı pitch'i portal üzerinden e-postayla göndermek.
- Dışa aktarma mevcut `ozellik:veri.disa-aktar`.

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Kitap künyesi, özet, tanıtım, bülten metni, kapak | CRM `new_kitapBase` (`new_name`, `new_ozet` «Arka Kapak Metni», `new_kisabilgi`, `new_uzunbilgi`, `new_BasnBlteni` «Basın Bülteni», `new_sosyalmedyametni`, `new_kitabinonecikanyanlari` «Bu Kitap Neden Önemli?», `new_kitabinenonemlicumlesi` «Kitabın En Önemli Cümlesi», `new_OnemDerecesi`, `new_resimurl`/`new_kapakresmi`, `new_ilkyayintarihi`, `new_hedefkitle`, `new_turlertext`) | 13.598 kitap; bu metin alanlarının kaç kitapta dolu olduğu **ölçülecek**. Kapak alternatifi yolu CRM sunucusunun yerel diski (web'den açılmaz, 2026-09-15); `new_resimurl` erişilebilirliği **ölçülecek** | Kapak görseli için güvenilir adres |
| Yazar biyografisi, fotoğrafı | CRM `ContactBase` + `new_ozgecmisBase` (89) ; Wikidata (yalnız test sunucusunda, web_watch) | Özgeçmiş 89 kayıtla sınırlı | Çoğu yazar için biyografi yok → kullanıcı girer |
| Yayın/lansman tarihi | CRM `new_kitapBase.new_ilkyayintarihi`, üretim kaydı | Var | M15/M16 lansman planı kodlanmadı |
| Medya kişisi (gazeteci, editör, podcast, YouTube) | CRM `ContactBase` (`FullName`, `EMailAddress1`, `JobTitle`, `new_ilgilioldugumecra`, `ParentCustomerId`, `new_KisiRolleri`), `new_haberlerBase.new_HaberinYazari` | Dolu kayıt sayısı **ölçülecek**; `new_kisiroluBase` 38 rol — içinde «gazeteci/basın» rolü var mı **ölçülecek** | Konu/ilgi alanı yok; podcast/YouTube kanalı listesi yok → köprü tablosu |
| Geçmiş haberler (yansıma arşivi) | CRM `new_haberlerBase` (1.369) + `new_new_haberler_new_kitapBase` (1.485) + `new_new_haberler_contactBase` (1.270); mecra `new_habermecrasiBase` (4), `new_mecratipiBase` (48) | Son değişiklik 2025-06 (ölü) | 2025-06 sonrası kayıt yok |
| Kitap gönderimi (basına kitap) | CRM `new_siparisBase` `new_siparistipi = 12` «Pazarlama (Tanıtım Gönderimi)», satırlar `new_siparissatiriBase` | Tip tanımlı; hacim ve alıcının kişi/cari olup olmadığı **ölçülecek** (sipariş alıcısı `new_faturacarisiid` = cari) | Gazeteci kişi bağı olmayabilir |
| Yeni yansıma (web) | Açık RSS (web_watch, 55 akış), Wikidata | Test sunucusunda çalışıyor; **VM'de kapalı** | Basılı/TV/radyo yok; ücretli medya takip ajansı verisi (teslim biçimi doğrulanmadı) |
| Erişim/tiraj | — | Hiçbir kaynakta yok | İş tanımındaki «toplam erişim tahmini» veri olmadan yapılamaz; mecra kartına kullanıcı girer ya da raporda yer almaz |
| Satış etkisi | Logo `V_SatisRaporu_<yıl>` / `LG_411_01_STLINE` | .155 kopyası **2026-08-17'de donmuş** (logo-155-frozen-copy) | Güncel satış için canlı Logo (.25) erişimi TİMAŞ BT kararı |
| E-posta gönderimi | Portal SMTP (`alerts.smtp_settings()`, `ALERT_SMTP_*`) | Serbest çalışan iletileri bu yoldan gidiyor | Toplu gönderim için uygun değil (bölüm 8) |

## 7. Diğer modüllerle bağ

- Girdi: M15 (kitap pazarlama planı: hedef kitle, basın listesi), M16 (lansman tarihi), M19 (onaylı görsel/metin), M7 Yazar ilişkileri (yazarla röportaj randevusu — mevcut `/yazar-iliskileri`), Kitap Tasarım Stüdyosu pazarlama kiti (arka kapak, sosyal görsel).
- Çıktı: M22 (çıkan haber → sosyal paylaşım), M28 (kanaat önderi/kurum listesiyle ortak kişi), M27 (fuar basın bildirisi), M25 (haber bağlantısı = gelen bağlantı, SEO «Gelen bağlantılar»), Genel bakış/Planlı raporlar (yansıma raporu).
- M15/M16/M19 henüz kodlanmadı: ilk sürüm onlara bağlı olmamalı.

## 8. Kısıtlar

- CRM'e yazma yok: PR dosyası, medya kişisi, gönderim ve yansıma köprünün kendi tablolarında (`semantic_pr_*`). CRM haber kayıtları yalnız okunur ve arşiv olarak birleştirilir.
- T-soft'a yazma yasak (bu modül T-soft'a hiç gitmez).
- Müşteri VM'inde web taraması kapalı: yansıma adayı toplama `WEB_WATCH_ENABLED` bayrağına bağlı; kapalıyken ekran yalnız elle girilen yansımayı gösterir, «tarama kapalı» yazar.
- Ekranda teknoloji/model adı yok: «Zeki AI taslağı», «Zeki AI sınıflandırması».
- Demo veri yok; sayı tavanı yok (iş tanımındaki «öncelikli 20» bir tavan değil, sıralı listenin tamamı görünür, üstten okunur).
- Bot korumasını aşan tarama, sosyal medya kazıma yok; yalnız resmî API/açık RSS.
- KVKK: gazetecinin adı, e-postası, telefonu kişisel veridir. Portalda saklamak için işleme amacı (basın ilişkisi) ve aydınlatma gerekir; «haberdar olmak istemiyorum» diyen kişi listeden düşer ve bir daha önerilmez. Basın bülteninin 6563 sayılı Kanun kapsamında «ticari elektronik ileti» sayılıp sayılmadığı ve İYS onayı gerekip gerekmediği **hukuka sorulacak** (CRM'de İYS alanları var: `obs_sendtoemailiys`, `new_iysonayi`). Haber metni kopyalanmaz; yalnız başlık, 400 karakterlik özet ve bağlantı (web_watch kuralı).
- Portal SMTP hesabı tek tek, kişiye özel pitch içindir; yüzlerce alıcıya toplu bülten bu hesaptan gönderilmez (gönderim sınırı ve itibar riski — **varsayım**, sağlayıcı sınırı ölçülmedi).

## 9. Kapsam önerisi

**İlk sürüm**
- Kitap başına PR dosyası: bülten (ulusal/yerel sürüm), medya kiti derlemesi (künye + özet + yazar bilgisi + kapak + stüdyo pazarlama kiti dosyaları), pitch taslağı.
- Medya kişileri: CRM'den okunan (mecrası dolu kişiler + CRM haberlerinde «haberi yapan kişi») + portalda yeni eklenen; konu etiketleri kullanıcıdan.
- Gönderim takibi: kime, ne zaman, hangi kanal (e-posta/kargo/elden), durum (gönderildi → cevap → haber çıktı / olumsuz), takip hatırlatıcısı.
- Yansıma kaydı: bağlantı yapıştır → sayfa başlığı ve tarih okunur (yalnız o tek sayfa, robots.txt'e uyarak; okunamazsa elle), kitap/yazar/mecra eşleşir; CRM Haber arşivi aynı listede.
- Haftalık/aylık rapor (PDF/Excel), onay akışı (K2).

**Sonraki sürüm**
- Kitap × medya kişisi eşleşme puanı (geçmiş haberlerin konusu + kişinin etiketleri + kitabın türü/hedef kitlesi).
- Röportaj soru seti (kitap metninden; stüdyo okuması varsa).
- Haber tarihi etrafında satış değişimi (canlı Logo erişimi gelince).
- Lisanslı medya takip hizmeti bağlanırsa basılı/TV yansıması içe aktarma.

**Mevcut kodda yeniden kullanılacaklar**
- `backend/semantic_bridge/web_watch.py` (RSS okuma, yazar/kitap eşleştirme, model etiketi, `WEB_WATCH_ENABLED`), ekran `src/canvas/editorial/web/`.
- `backend/semantic_bridge/author_relations.py` (kart + temas + ısı puanı deseni; medya kişisi için aynı yapı).
- `backend/semantic_bridge/editorial_studio_marketing.py` (arka kapak, sosyal görsel, ürün sayfası — medya kiti içeriği).
- `backend/semantic_bridge/freelance.py` (`send_mail` geri çağrısı: Reply-To = yazanın rehber e-postası) + `alerts.smtp_settings()`.
- `backend/semantic_bridge/reports.py` (haftalık rapor gönderimi), `admin.audit` (değişiklik kaydı), `access.py` (sayfa/özellik kapısı).

## 10. Uzmanlara sorulacak sorular

1. Basın ilişkilerini kim yürütüyor (kişi/ajans)? Dışarıdan PR ajansı varsa portalı ajans da kullanacak mı?
2. Gazeteci listesi bugün nerede tutuluyor (Excel, e-posta grubu, CRM kişi rolü)? Aktarılacak dosya var mı?
3. CRM Haber modülü 2025-06'da neden bırakıldı? Arşivdeki kayıtlar güvenilir mi?
4. Basına kitap gönderimi «Pazarlama (Tanıtım Gönderimi)» siparişiyle mi açılıyor; alıcı gazeteci olarak kayıtlı mı?
5. Basın bülteni gönderimi için hukuk/KVKK birimi İYS onayı istiyor mu?

## 11. Başarı ölçütü

- Bülten taslağından onaya süre: bugünkü süre (sorulacak) → hedef aynı gün.
- Kitap başına PR dosyası açılma oranı: ay içinde çıkan önemli kitapların (CRM `new_kitapBase.new_OnemDerecesi` 100000001 «Çok Önemli» / 100000002 «Önemli»; dolu oranı **ölçülecek**) tamamı.
- Gönderim–cevap oranı ve cevapsız kalan gönderime hatırlatma yapılma oranı.
- Yansıma kaydı: ayda girilen yansıma sayısı (2025-06'dan beri 0).
- Kullanım: PR sorumlusunun haftalık aktif gün sayısı; pazarlama müdürünün raporu portaldan alması.

## 12. Uzman gözüyle en iyi sistem

*15 yıllık yayınevi basın sorumlusu gözüyle.*

Büyük yayınevlerinde basın işi üç araç üstünde döner: güncel bir medya veritabanı (kim hangi konuyu yazıyor, en son neyi yazdı), kitap başına «publicity plan» (kime, ne zaman, hangi ön okuma nüshası, hangi röportaj teklifi) ve yansıma arşivi. Uluslararası yazılımlar (medya veritabanı + pitch takibi + yansıma raporu tek yerde) değerini veritabanının güncelliğinden alır; asıl emek listenin temiz tutulmasıdır. Türkiye'de kültür-sanat sayfası sayısı az, kişisel ilişki belirleyici; bu yüzden TİMAŞ için mükemmel sistem büyük bir gazeteci veritabanı değil, **TİMAŞ'ın kendi ilişki hafızası**dır: kim hangi Timaş kitabını yazdı, en son ne zaman konuştuk, hangi kitabı istedi, hangi tür onu ilgilendirmez.

**Bir iş günü**
- 09:00 Açılış: «Bugün» kartı — bu hafta çıkan 4 kitap, 2 PR dosyası onayda, 3 gönderim 5 günü geçti cevapsız, dün gece 2 yansıma adayı (test ortamında) ya da «tarama kapalı».
- 09:15 Cevapsız üç gönderime Zeki'nin kısa takip taslağı; ikisini düzeltip gönderir, birini «telefonla ararım» diye işaretler.
- 10:00 Yeni kitap: «PR dosyası aç» → Zeki kitap kartından bülten (ulusal + yerel), üç farklı açılış cümlesi, yazar biyografisi boşsa «biyografi eksik» uyarısı. Editöre «bilgiyi doğrula» görevi düşer.
- 11:30 Medya listesi: kitaba uygun kişiler sıralı; her birinin yanında gerekçe («2024'te iki Timaş tarih kitabını yazdı»). 12 kişiyi seçer; pitch'ler kişiye göre hazırlanır.
- 14:00 Pazarlama müdürü telefondan onaylar.
- 14:10 Pitch'ler gönderilir (tek tek, Reply-To PR sorumlusu); kargo ile kitap gidecekler için «tanıtım gönderimi» listesi Excel.
- 16:00 Bir gazeteci aradı: kişi kartına 20 saniyelik not + «röportaj istiyor» → Yazar ilişkileri ekranında randevu önerisi.
- 17:30 Çıkan haber bağlantısı yapıştırılır; kitap, yazar, mecra kendiliğinden bağlanır; cuma günü haftalık rapor müdüre kendiliğinden gider.

**«Bunu görürsem hemen kullanırım»**
1. Kitap sayfasında tek bakışta PR geçmişi: kime gitti, kim yazdı, bağlantılar.
2. Gazeteci kartında «en son ne yazdı / hangi Timaş kitabını aldı / cevap verdi mi».
3. Bağlantıyı yapıştırınca yansımanın kendiliğinden kitaba bağlanması.

**«Bunu yaparsanız kullanmam»**
1. Onaysız ya da toplu (herkese aynı) e-posta gönderen sistem — gazeteciyle ilişkiyi bitirir.
2. Uydurulmuş «erişim» ya da «PR değeri» rakamı — yönetimde güvenimi kaybettirir.
3. Her kaydı üç form sayfası isteyen giriş — telefondan 30 saniyede giremiyorsam girmem.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo/görünüm/ölçü) | CRM (varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Bu ay çıkan kitaplar | — | `new_kitapBase.new_ilkyayintarihi`, `statuscode`, `new_kitap_yayincilikstatusu` | — | Tarih ve durum SQL'le gelir |
| Bülten / medya kiti taslağı | — | `new_ozet`, `new_kisabilgi`, `new_uzunbilgi`, `new_BasnBlteni`, `new_hedefkitle`, `new_turlertext`, yazar `ContactBase.FullName` | Taslak metin (ulusal/yerel sürüm), 3 açılış cümlesi | Model yalnız CRM metninden yazar; fiyat/tarih gibi rakamlar şablona SQL'den girer, model üretmez |
| Pitch e-postası | — | Kişi `new_ilgilioldugumecra`, geçmiş haber `new_haberlerBase` | Kişiye/mecraya göre kısa pitch taslağı | Kişiselleştirme dil işi |
| Medya kişisi sıralaması | — | `new_new_haberler_new_kitapBase`, `new_new_haberler_contactBase`, `new_haberlerBase.new_mecratipi` | Gerekçe cümlesi (sıralama puanı kuralla: aynı tür/yazar haberi sayısı, son temas tarihi) | Puan açıklanabilir olmalı; model yalnız gerekçeyi yazar |
| Yansıma ilgisi ve tonu | — | Kitap/yazar adları | Kapalı seçim: `olumlu/notr/olumsuz/ilgisiz` — tek token + olasılık (vLLM choice + logprobs deseni) | Sınıflandırma; web_watch'taki aynı kapı |
| Yansıma raporu | — | — | Haftanın 3 cümlelik özeti | Sayılar SQL'den; model yalnız yorumlar |
| Satış etkisi (sonraki sürüm) | `V_SatisRaporu_<yıl>` (`[Malzeme/Hizmet Kodu]`, `[Yıl]`, `[Ay]`, `[Miktar]`, `[Net Tutar]`, `[Satır Türü]=N'Malzeme'`), stok kodu CRM `new_kitapBase.new_StokKodu` | `new_StokKodu` | Yorum cümlesi | Logo kayıt sistemidir; satış = faturalı satır |
| Doğal dil soru | Katalog ölçüleri | CRM haber/kişi tabloları katalogdaysa | Genel bakıştaki soru hattı | Mevcut hat |

Model çağrısı yalnız LLM kapısından: köprü içinde `rt.llm_for("pr")` (ekranda bekleyen iş öncelik 0), gece yansıma sınıflandırması `rt.llm_for("pr", BATCH)`; `LlmClient` doğrudan kurulmaz.

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları**
- `backend/semantic_bridge/pr.py` — tablolar, iş kuralları, puan, rapor derleme (saf işlevler test edilebilir).
- `backend/semantic_bridge/pr_sources.py` — CRM okuma SQL'leri (`Timas_MSCRM.dbo.` önekli; `_conn_for` .28'e yollar), web_watch'tan yansıma adayı okuma.
- `backend/semantic_bridge/pr_api.py` — `register(app, deps)`; `app.py`'de `editorial_studio_marketing.register` deseniyle iki satır.

**Tablolar** (bi_meta, ilk kullanımda `ensure`)
- `semantic_pr_contacts` (id, tenant_id, crm_contact_id NULL, name, outlet, outlet_type [gazete/dergi/tv/radyo/web/podcast/youtube], role, email, phone, topics_json, region [ulusal/yerel], do_not_contact bool, note, created_by, created_at, updated_at)
- `semantic_pr_kits` (id, tenant_id, crm_book_id, status [taslak/onayda/onaylı/reddedildi/kapalı], release_national, release_local, pitch_template, qa_json, assets_json, approved_by, approved_at, created_by, …)
- `semantic_pr_sends` (id, kit_id, contact_id, channel [eposta/kargo/elden/telefon], sent_at, crm_order_no NULL, status [gönderildi/cevap/haber/olumsuz/cevapsız], follow_up_at, note)
- `semantic_pr_coverage` (id, tenant_id, url UNIQUE, title, published_at, outlet, contact_id NULL, crm_book_id NULL, crm_contact_author_id NULL, tone, source [elle/web/crm-arsiv], summary≤400, created_by)
- `semantic_pr_events` (değişiklik geçmişi; ayrıca `admin.audit`)

**Uçlar** (`/api/v1/pr/*`)
- `GET meta`, `GET home` (bu ay kitaplar + bekleyenler), `GET books/{crmBookId}/kit`, `POST kits`, `PATCH kits/{id}`, `POST kits/{id}/draft` (Zeki taslağı; `/api/v1/llm/jobs` ile bırakılan iş, ekran sonucu sorar), `POST kits/{id}/submit`, `POST kits/{id}/approve|reject`
- `GET contacts`, `POST contacts`, `PATCH contacts/{id}`, `GET contacts/{id}` (geçmiş haberler + gönderimler), `GET kits/{id}/suggest-contacts`
- `POST kits/{id}/sends`, `PATCH sends/{id}`, `POST sends/{id}/mail` (SMTP, tek alıcı)
- `GET coverage`, `POST coverage` (bağlantı → başlık okuma), `PATCH coverage/{id}`
- `GET report?from=&to=`, `GET report/export.pdf|xlsx`
- `POST run-due` (SYSTEM: hatırlatma + web adaylarını al)

**Ekranlar** `src/canvas/pr/` — `PrHome.tsx`, `PrKit.tsx`, `PrContacts.tsx`, `PrCoverage.tsx`, `PrReport.tsx`; rota `/timas/basin-iliskileri` (+ `/kitap/:id`, `/kisiler`, `/yansimalar`, `/rapor`). Menü: `navModel.ts` → çalışma alanı `pazarlama`, yeni bölüm `section: 'İletişim'`, öğe `{ id: 'basin-iliskileri', label: 'Basın ilişkileri', icon: Megaphone, hint: 'Bülten, medya kişileri ve yansımalar' }`. Kitap sayfasına (`/kitap/:id`) «Basın» sekmesi. Kampüs: `modules.json` Pazarlama grubunda M20 çalışan olarak işaretlenir. Mobil: yansıma ekleme ve gönderim durumu telefonda tek sütun.

**Yetki** — `access_catalog.json`: sayfa `sayfa:basin-iliskileri` (area `pazarlama`); özellikler `ozellik:pr.duzenle`, `ozellik:pr.onay` (explicit), `ozellik:pr.gonder` (explicit). `access.py` RULES: `("/api/v1/pr/run-due", SYSTEM)`, `("/api/v1/pr/", frozenset({page("basin-iliskileri")}))`; FEATURE_RULES: POST/PATCH `^/api/v1/pr/(kits|contacts|sends|coverage)` → `ozellik:pr.duzenle`; export → `ozellik:veri.disa-aktar`. Onay ve gönderim ucun içinde `_need(user, "ozellik:pr.onay")`.

**Zamanlayıcı** — `scripts/server/timas-pr.timer` her gün 08:30: `POST /api/v1/pr/run-due` → cevapsız gönderim hatırlatması, web_watch'un son 24 saatteki ilgili kayıtlarından yansıma adayı (bayrak kapalıysa atlanır), cuma 16:00 haftalık rapor. Kurulumdan önce elle bir kez koşturulur.

**Kabul testleri** (gerçek veriyle; referans `connector_from_file` ile doğrudan DB)
1. CRM arşiv sayısı: ekrandaki «CRM arşivi» yansıma sayısı = `SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_haberlerBase WHERE statecode = 0`.
2. Kitap başına arşiv: seçilen kitap için ekran = `SELECT COUNT(DISTINCT hk.new_haberlerid) FROM Timas_MSCRM.dbo.new_new_haberler_new_kitapBase hk WHERE hk.new_kitapid = '<guid>'` (ve `new_haberlerBase.new_Kitapid` ile birleşik fark ayrıca sayılır).
3. Medya kişisi havuzu: CRM'den gelen kişi sayısı = `SELECT COUNT(*) FROM Timas_MSCRM.dbo.ContactBase WHERE statecode = 0 AND (NULLIF(LTRIM(new_ilgilioldugumecra),'') IS NOT NULL OR ContactId IN (SELECT new_HaberinYazari FROM Timas_MSCRM.dbo.new_haberlerBase))` — önce `new_HaberinYazari`'nın Contact'a mı SystemUser'a mı baktığı ölçülür.
4. Tanıtım gönderimi: kitabın «basına gönderilen adet»i = `SELECT SUM(ss.new_adet) FROM Timas_MSCRM.dbo.new_siparissatiriBase ss JOIN Timas_MSCRM.dbo.new_siparisBase s ON s.new_siparisId = ss.new_siparisid WHERE s.new_siparistipi = 12 AND ss.new_StokKodu = '<stok kodu>'`.
5. Bu ay çıkan kitaplar: ekran listesi = `SELECT COUNT(*) FROM Timas_MSCRM.dbo.new_kitapBase WHERE statuscode = 1 AND new_ilkyayintarihi >= '<ay başı>' AND new_ilkyayintarihi < '<sonraki ay başı>'`.
6. Portal kayıtları: raporun «gönderim/cevap/haber» sayıları = `semantic_pr_sends` üzerinde doğrudan `COUNT(*) … GROUP BY status` (dönem süzgeciyle).
7. VM davranışı: `WEB_WATCH_ENABLED=0` iken `run-due` web adayı eklemez, ekranda «tarama kapalı» yazar; `src/` ve ekrana giden metinlerde model/teknoloji adı taraması boş döner.

**Bağımlılık** — Kendi başına kodlanabilir (M15/M16/M19'u beklemez). Yetki Aşama B düzeni (sayfa/özellik anahtarı) hazır. M7 ekranıyla paralel yürür; medya kişisi için author_relations deseni kopyalanmaz, ortak yardımcılar (ısı puanı) çıkarılarak paylaşılır.

**Tahmini büyüklük** — L (3+ gün): köprü + 5 ekran + onay/SMTP + zamanlayıcı + kabul.
