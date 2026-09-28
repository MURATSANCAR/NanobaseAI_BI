# M28 — Kanaat Önderleri, Kurumsal İlişkiler ve Kamu Projeleri: kullanıcı ihtiyaç analizi

Durum: kod var (main) — test sunucusunda kabul bekliyor (testler koordinatörde) · Analiz tarihi: 2026-09-28 · Kaynaklar: `specs/M28.txt` (ZEKİ_Moduller3.html), `specs/M31.txt`, `specs/M32.txt`, `specs/M33.txt` (örtüşme için), `ZEKİ_Veri_Haritasi2.html` (İlişki & Proje Girdileri, İzleme & Araştırma), `configs/semantic/knowledge/crm/table_descriptions.json` (2026-09-09), `configs/semantic/knowledge/crm/OKUNUR-TABLOLAR.md`, `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md`, `docs/analiz/meb-uygunluk-olcutleri.md`, `docs/analiz/kitap-yazar-web-taramasi-2026-09-24.md`, `backend/semantic_bridge/author_relations.py`, `web_watch.py`, `editorial_studio*.py` (yaş uygunluğu raporu), `access.py`, `access_catalog.json`, `src/canvas/nav/navModel.ts`, `docs/LLM-KAPISI.md`, kullanıcı belleği (customer-vm-web-watch-off, web-watch-open-sources, crm-systemuser-directory, no-tech-names-on-screens, no-silent-limits-rule, no-static-solutions).

> Kural: sunucuya bağlanılmadı. Ölçülmemiş her şey **ölçülecek**, kanıtsız her iddia **varsayım** diye işaretlidir.

## 1. Modül ne işe yarar

Üç iş: (1) **Kanaat önderi ilişkileri** — akademisyen, eğitimci, gazeteci/yazar, STK yöneticisi ve alanında etkili kişilere kitap-kişi eşleştirmesi, kişiselleştirilmiş hediye kitap programı, tanıtım notu ve takip. (2) **Kamu kurumları ve ortak projeler** — MEB, Diyanet, belediyeler, üniversiteler, kütüphanelerle okuma kampanyası, kütüphane bağışı, eğitim materyali gibi projelerin fikir → teklif dosyası → ilerleme takibi. (3) **Etki ve imaj izleme** — kanaat önderlerinin kitap tavsiyeleri, marka bahsi, kriz sinyali, kamu projelerinin erişim ve yansıması (iş tanımı M28: K2 iki kart, K3 etki izleme; hepsi yönetim onayında).

TİMAŞ'ın bugünkü sorunu: kurum verisi CRM'de **çok geniş** — «Ziyaret Yerleri» (`new_ziyaretyerleriBase`) 68.713 kurum (okul, üniversite, Milli Eğitim, belediye, kaymakamlık, valilik; öğrenci/öğretmen/kitap sayısı, il/ilçe), carilerde kurum rolü (`AccountBase.new_KurumRolu`: Müşteri/Devlet Kurumu/Resmi/Özel STK), kişilerde «Karar Veren/Çalışan/Etkileyen» rolü (`ContactBase.AccountRoleCode`), akademik unvan, meslek, uzmanlık alanı (133). Hediye programının izi de var (`new_hediyetalebiBase` «Hediye Talepleri ve Gönderimi», 11 kayıt; tanıtım gönderimi, deprem bağışı, okul/öğretmen örneği sipariş tipleri). Ama ilişki (kime ne zaman hangi kitap gitti, ne döndü), proje ilerlemesi ve etki ölçümü hiçbir yerde tutulmuyor; hediye talebi modülü 11 kayıtla fiilen kullanılmıyor (**varsayım**: iş e-posta/Excel'de).

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Kurumsal ilişkiler müdürü / sorumlusu | Yönetime bağlı ya da Pazarlama (**varsayım**; ayrı birim olup olmadığı sorulacak) | Her gün | Telefon (görüşme notu) + masaüstü (teklif dosyası) |
| Genel müdür / genel yayın yönetmeni | Yönetim | Haftada 1 (onay, kritik ilişkiler) | Telefon |
| Kurumsal satış (B2B, M32) ve okul tanıtım ekibi (M31) | Satış | Proje ve kurum temaslarında | Telefon |
| Editör / yayın yönetmeni | Editörya | Hediye kitap seçimi, proje içeriği (okuma listesi, eğitim materyali) | Masaüstü |
| Basın sorumlusu (M20) | Pazarlama | Ortak kişi (gazeteci kanaat önderi) | Masaüstü |
| Hukuk / KVKK | **varsayım** | Kişi verisi kuralı | — |

## 3. Bugün bu iş nasıl yapılıyor

- **Kurumsal ilişkiler** (varsayım): kişi listesi yöneticilerin telefon rehberinde ve kişisel ilişkide; hediye kitap gönderimi «Pazarlama (Tanıtım Gönderimi)» tipli CRM siparişiyle (`new_siparistipi = 12`; hacim **ölçülecek**) ya da elden; proje teklifi Word'de; kurum yazışması e-postada. Tıkanma: kişiye en son ne gönderildiği ve ne döndüğü hatırlanmıyor; kurum temsilcisi değişince ilişki kayboluyor.
- **Okul/kurum ziyaretleri** CRM etkinlik kaydında (`new_etkinlikBase.new_ziyarettipi`: MEB Okulları/Özel Okullar/Üniversiteler/Cari Ziyareti) — bu kayıtlar M31'in de girdisi.
- **Etki izleme**: yok; test sunucusundaki «Basın ve web» yazar/kitap haberlerini izliyor, müşteri VM'inde kapalı.

## 4. İhtiyaçlar ve acı noktaları

**Kurumsal ilişkiler sorumlusu**
1. Kişi ve kurum kartı: kim, hangi kurum, hangi alan, kimin tanıdığı, son temas, gönderilen kitaplar, dönüş.
2. Kişiye uygun kitap önerisi (ilgi/uzmanlık alanı × kitabın konusu/hedef kitlesi) ve kişisel not taslağı.
3. Hediye programının planı ve takibi (liste, onay, gönderim, teşekkür/geri dönüş).
4. Kamu projesi hattı: fikir → görüşme → teklif → onay → uygulama → rapor; her aşamada sorumlu ve tarih.
5. Teklif dosyası taslağının kurumun diline ve mevzuata uygun gelmesi (MEB kütüphane yönetmeliği vb.).

**Yönetim**
1. Kritik ilişkilerin ve açık projelerin tek sayfalık görünümü.
2. Hediye bütçesi ve proje taahhütlerinin onayı.
3. Marka ve kriz sinyali.

**Editör**
1. Hediye/proje kitap listesinin içerik uygunluğu (yaş, MEB ölçütleri).

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- Kurumsal ilişkiler sorumlusu olarak bir kişinin kartında ona gönderdiğimiz bütün kitapları ve son görüşmeyi görmek istiyorum, çünkü aynı kitabı iki kez göndermek ya da uzun süre aramamak ilişkiye zarar veriyor.
- Kurumsal ilişkiler sorumlusu olarak yeni çıkan kitaplar için «bu kitabı kime göndermeliyiz» listesini gerekçesiyle görmek istiyorum, çünkü hediye programını her ay elle kuruyorum.
- Kurumsal ilişkiler sorumlusu olarak kişiye özel kısa bir not taslağı almak istiyorum, çünkü not kişisel olmazsa kitap okunmuyor.
- Kurumsal ilişkiler sorumlusu olarak bir belediyeyle yürüyen okuma kampanyasının hangi aşamada olduğunu ve sıradaki adımı görmek istiyorum, çünkü projeler aylarca sürüyor.
- Kurumsal ilişkiler sorumlusu olarak MEB kütüphane yönetmeliğine uygun bir bağış teklif dosyası taslağı almak istiyorum, çünkü her kurumun beklediği biçim farklı.
- Genel müdür olarak aylık hediye listesini ve bütçesini telefondan onaylamak istiyorum.
- Genel müdür olarak kamu projelerinin erişimini (okul, öğrenci, kitap adedi) ve basın yansımasını görmek istiyorum, çünkü kurul ve kamuya bunu raporluyoruz.

**Ana ekranlar ve akış**
- İlk açılış (`/timas/kurumsal-iliskiler`): üç şerit — «Temas zamanı gelen kişiler» (son temastan N gün, ayarlı), «Açık projeler» (aşama çubuğu), «Bu ayın hediye programı» (onay durumu).
- En sık 3 işlem: (1) Kişi kartına görüşme notu: 2 tık (telefon). (2) Kitap → «kime gönderelim» → seç → hediye listesine ekle: 3 tık. (3) Proje aşamasını ilerlet + not: 2 tık.
- Diğer ekranlar: Kişiler ve kurumlar (süzgeç: alan, il, kurum tipi, ısı), Projeler (pano), Hediye programı (liste + onay + gönderim durumu), Etki raporu.

**Zeki AI'a soracakları**
- «Son 6 ayda hiç temas etmediğimiz Karar Veren rolündeki kurum temsilcileri kimler?»
- «[Kitap] için hangi akademisyen ve eğitimcilere hediye önerirsin?»
- «Bu yıl hediye kitap programında kaç kişiye kaç kitap gönderdik?»
- «İstanbul'daki Anadolu liselerinin sayısı ve toplam öğrenci sayısı ne?» (CRM ziyaret yerleri)
- «[Belediye] ile okuma kampanyası için teklif dosyası taslağı hazırla.»
- «Açık kamu projelerinden bu ay adım atılmayanlar hangileri?»
- «Deprem bağışı ve okul örneği olarak geçen yıl kaç kitap gönderdik?»

**Otomasyon katmanı**
- K1: temas zamanı hatırlatıcısı, hediye gönderim durumunun CRM siparişinden izlenmesi, proje tarih uyarısı, kurum istatistikleri.
- K2: kişi-kitap eşleştirmesi, hediye listesi, kişisel not, proje fikri ve teklif dosyası → yönetim onayı.
- K3: etki raporu, proje değerlendirmesi, kriz sinyali → üst yönetim kararı.
- K4: kişisel görüşme ve kurum müzakeresi (yalnız insan).

**Bildirim/uyarı**
- Sorumluya: temas zamanı gelen kişiler (haftalık özet), proje adımı gecikti, hediye onaylandı/sevk edildi.
- Yönetime: onay bekleyen hediye listesi/teklif (Uyarılar rozeti), aylık etki özeti.

**Onay ve yetki**
- `sayfa:kurumsal-iliskiler` — dar tutulur (kişi kartları hassas).
- `ozellik:kurumsal.duzenle` (kişi/kurum kartı, not, proje) ; `ozellik:kurumsal.onay` (explicit; hediye listesi, teklif, bütçe); `ozellik:kurumsal.hassas` (explicit; özel notlar ve «yalnız ben» notlarını görme — M7'deki «Yalnız ben ve katılımcılar» deseni).

## 6. Veri

| Gereken veri | Kaynak | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Kurumlar (okul, üniversite, MEB, belediye, kaymakamlık, valilik) | CRM `new_ziyaretyerleriBase` (68.713; `new_KurumTipi`, `new_kurumturu`, `new_okulturu`, `new_okulkademesi`, `new_kurumadi`/`new_okuladi`, `new_renciSays`, `new_ogretmensayisi`, `new_kitapsayisi`, `new_toplamogrencisayisi`, `new_ili`, `new_ilcesi`) | Sayı/metin alanları `nvarchar` (sayıya çevirme gerekir); güncelliği **ölçülecek** | Diyanet, kütüphane, STK ayrı tipte yok → «Diğer» ya da cari |
| Kurum carileri | CRM `AccountBase` (`new_KurumRolu`, `new_KurumunTemsilcisi`, `PrimaryContactId`), Logo `CLCARD.SPECODE2 = 'KURUM'` | Var | — |
| Kişiler ve rolleri | CRM `ContactBase` (`FullName`, `JobTitle`, `new_unvan`, `new_AkademikTitrid`, `new_Meslekid`, `AccountRoleCode` 1 Karar Veren / 2 Çalışan / 3 Etkileyen, `ParentCustomerId`, `new_kurumtipi`, sosyal kullanıcı adları), `new_contact_new_uzmanlikalaniBase` (99) → `new_uzmanlikalaniBase` (133), `new_contact_new_kisiroluBase` (3.305) → `new_kisiroluBase` (38) | Dolu oranları **ölçülecek**; kanaat önderi diye bir rol var mı **ölçülecek** | «Etki alanı» ve «kimin tanıdığı» yok → köprü |
| Hediye/tanıtım gönderimleri | CRM `new_siparisBase.new_siparistipi` 12 (Tanıtım Gönderimi), 15 (Deprem Bağış), 10/11 (Okul/Öğretmen Örneği), 13 (Okul Satışı); `new_hediyetalebiBase` (11), `new_hediyeurunlerBase` (5) | Hacimler **ölçülecek**; alıcı kişi mi cari mi **ölçülecek** | Gönderim ↔ kişi bağı |
| Kurum ziyaretleri | CRM `new_etkinlikBase` (`new_ziyarettipi`, `new_ZiyaretYeri`, `new_OkulKurum`, `new_DzenlenenKurumdaletiimKurulanKii`) | Canlı | — |
| Kitap önerisi girdisi | CRM `new_kitapBase` (`new_ozet`, `new_turlertext`, `new_hedefkitle`, yaş, `new_hedefkitlesinifid`, `new_OnemDerecesi`), M18 föy (kodlanmadı) | Var | Föy yok → CRM metinleri |
| Mevzuat ve uygunluk | `docs/analiz/meb-uygunluk-olcutleri.md` (OKY 2024, Uygulama Kılavuzu 2025, DKY 2021, TTKB kriterleri, TDP) + stüdyo yaş uygunluğu raporu | Var (resmî kaynaklı) | Diyanet/belediye proje koşulları yok → kullanıcı girer |
| Kamu ihale/proje fırsatları | EKAP ve kurum duyuruları | **M33'ün işi**; bu modül tüketir | — |
| Etki izleme | M20 yansımaları, web_watch (test), M22 kendi hesap içgörüleri, resmî API'ler | web_watch **VM'de kapalı** | Kanaat önderinin paylaşımını otomatik izleme yalnız resmî API ile ve sınırlı |
| Proje erişimi (okul, öğrenci, kitap adedi) | CRM sipariş/sevkiyat (dağıtılan adet), ziyaret yerleri öğrenci sayısı, kullanıcı girişi | Kısmen | Etkinliğe katılan kişi sayısı elle |

## 7. Diğer modüllerle bağ

- Girdi: M18 FÖY paketi (kodlanınca), M20 (gazeteci-kanaat önderi ortak kişiler, yansıma), M22 (marka bahsi), M31 (okul ziyaretleri), M32 (kurumsal satış), M33 (ihale/proje fırsatı), M46 (hediye/proje bütçesi), M53 (hediye/set ürünleri), M7 (yazar-kanaat önderi ilişkisi), stüdyo yaş uygunluğu raporu.
- Çıktı: M32/M33 (kurum projesinden satış/ihale), M20 (proje basın bildirisi), M27 (kurumla ortak etkinlik), yönetim raporu (DYK).

## 8. Kısıtlar

- CRM'e yazma yok: kişi ilişki kartı, not, hediye programı, proje `semantic_rel_*`; CRM kişi/kurum yalnız okunur ve kimlikle bağlanır.
- **KVKK — özel nitelikli veri.** İş tanımındaki «din adamları» ve kanaat önderi sınıflaması kişinin din/mezhep inancı ya da siyasi görüşü hakkında çıkarım üretmeye çok yakındır (KVKK md. 6, özel nitelikli kişisel veri; açık rıza ya da kanuni istisna gerekir). Kural: portalda **inanç, mezhep, cemaat, siyasi görüş, parti** alanı ya da etiketi tutulmaz; Zeki bu yönde sınıflama yapmaz. Kişi «alan» ile tanımlanır (akademi, eğitim, medya, STK, kamu yönetimi, din hizmetleri **kurumu** gibi kurum bağı — kurum bağının kendisi de hukuka sorulacak). Kişi kartı verisinin işleme amacı ve aydınlatma metni hukuka sorulacak; «yalnız ben» notları sahibinin ve `ozellik:kurumsal.hassas` sahiplerinin görebildiği alan.
- Kamu görevlisine hediye: kamu görevlilerinin hediye alma yasağı ve sınırları (Kamu Görevlileri Etik Davranış İlkeleri) vardır; hediye programında «kamu görevlisi» işaretli kişi için uyarı ve hukuk onayı adımı olmalı. Tanıtım/bağış ile kişisel hediye ayrımı kurum politikasıdır (**sorulacak**).
- Etki izleme için kazıma yok; müşteri VM'inde web taraması kapalı. Kişi paylaşımları yalnız resmî API ve kullanıcının girdiği bağlantıyla.
- Kamu ihale taraması bu modülde değil, M33'te.
- Ekranda teknoloji adı yok; demo veri yok; sayı tavanı yok; örnek başına elle kalıp yok (eşleştirme her kitap/kişi için aynı dinamik hattan).

## 9. Kapsam önerisi

**İlk sürüm**
- Kişi ve kurum ilişki kartı (CRM kişisine/kurumuna bağlanır ya da portalda yeni): alan etiketleri (kurum politikasıyla onaylı sabit liste), ilişki sahibi, son temas, not (görünürlük seçimi), ısı puanı.
- Hediye programı: aylık liste (kitap × kişi, gerekçe), yönetim onayı, CRM tanıtım siparişinden gönderim durumu, geri dönüş kaydı; «kamu görevlisi» uyarısı.
- Proje hattı: aşamalar (fikir → ön görüşme → teklif → kurum onayı → uygulama → rapor → kapandı), sorumlu, tarih, belgeler; teklif dosyası taslağı (Zeki; MEB ölçütleri belgesi ve kitap listesi girdisiyle).
- Proje erişim raporu: dağıtılan kitap (CRM sipariş/sevkiyat), ulaşılan okul/öğrenci (ziyaret yerleri), elle girilen katılım; basın yansıması (M20 kaydı varsa).

**Sonraki sürüm**
- Kişi-kitap eşleştirme puanı (uzmanlık alanı × tür/hedef kitle × geçmiş gönderim) ve toplu öneri.
- Etki izleme: M20/M22 verisi + resmî API ile kanaat önderinin herkese açık paylaşımında kitap/yayınevi bahsi (yalnız izinli kaynak).
- Kriz sinyali (M22 ile ortak).
- Kurum takvimi (okul dönemleri, bütçe dönemleri) ile proje zamanlaması.

**Mevcut kodda yeniden kullanılacaklar**
- `backend/semantic_bridge/author_relations.py` — kart + randevu/görüşme notu + ısı puanı + «yalnız ben ve katılımcılar» gizliliği + toplantı odası bağı: kanaat önderi kartının neredeyse birebir karşılığı; ortak çekirdek çıkarılıp iki modül paylaşmalı.
- `docs/analiz/meb-uygunluk-olcutleri.md` + stüdyo yaş uygunluğu raporu (`apps/editor/src/editor/production/age_report.py`) — proje kitap listesinin uygunluk kanıtı.
- `backend/semantic_bridge/web_watch.py` (bayrakla etki izleme), `people.py` (ilişki sahibi = rehberdeki çalışan), `rooms.py`.

## 10. Uzmanlara sorulacak sorular

1. Kanaat önderi ve kurum ilişkilerini kim yürütüyor; kişi listesi nerede tutuluyor?
2. Hediye kitap gönderimi hangi yolla yapılıyor (tanıtım siparişi, elden, kargo) ve kim onaylıyor? Kamu görevlisine hediye için kurum politikası nedir?
3. Kişileri hangi alanlarla gruplamak istiyorsunuz? (KVKK sınırı içinde sabit liste onayı)
4. Bugün yürüyen kamu projeleri hangileri (MEB, Diyanet, belediye, üniversite)? Hangi belgelerle ilerliyor?
5. Proje başarısını nasıl raporluyorsunuz (kitap adedi, okul, öğrenci, basın)?

## 11. Başarı ölçütü

- Kritik kişilerin (yönetimin işaretlediği) son temas süresi hedefin altında (ör. 90 gün).
- Hediye programında aynı kişiye aynı kitabın tekrar gönderimi: 0.
- Açık projelerin her ay en az bir adım kaydı; teklif dosyası hazırlık süresi.
- Proje erişim raporunun kurul toplantısından önce portaldan alınması.
- KVKK: hassas etiket taraması 0 (inanç/siyaset alanı yok).

## 12. Uzman gözüyle en iyi sistem

*Yayıncılıkta 15 yıl kurumsal ilişkiler ve kamu işleri yürütmüş bir müdür gözüyle.*

Kurumsal ilişkilerin en değerli varlığı **kurumsal hafızadır**: kiminle ne konuşuldu, kime hangi kitap gitti, hangi projede hangi söz verildi. Bu hafıza kişilerin telefonunda kalırsa kişi ayrılınca kaybolur. Sektörde bu iş için kullanılan paydaş yönetimi yazılımlarının güçlü yanı etkileşim geçmişi, ilişki sahibi, hatırlatıcı ve proje hattıdır; zayıf yanı kişileri «etki puanı» gibi opak ölçülerle sıralamaya çalışmalarıdır. Yayınevlerinde iyi işleyen model: her ay yeni çıkan kitaplardan küçük, kişisel, notlu bir hediye programı; okul ve kütüphane projelerinde yönetmeliğe uygun, ölçülebilir (kaç okul, kaç öğrenci, kaç kitap) teklifler; etkinin sayısı değil **kalitesi** (bir akademisyenin ders listesine kitabı alması) üzerine not. TİMAŞ için mükemmel sistem: CRM'deki 68 bin kurumu ve kişi rollerini temel alan, hediye gönderimini CRM siparişinden izleyen, KVKK sınırını tasarımla koruyan, proje dosyasını MEB ölçütleriyle hazırlayan bir **ilişki ve proje defteri**.

**Bir iş günü**
- 09:00 «Temas zamanı gelen» 7 kişi; ikisi için telefonla arama planı, biri için kısa e-posta taslağı.
- 10:00 Aylık hediye programı: bu ay çıkan 5 kitap için Zeki'nin eşleştirdiği 40 kişi (gerekçeli: «tarih bölümü öğretim üyesi, 2025'te iki tarih kitabımızı almış, teşekkür etmiş»). 25'i seçilir; kişisel not taslakları; bir kişi «kamu görevlisi» uyarısıyla hukuka.
- 12:00 Genel müdür listeyi telefondan onaylar; tanıtım siparişi satış operasyonuna.
- 14:00 İl Milli Eğitim ile okuma kampanyası: teklif dosyası taslağı (hedef okul sayısı ve öğrenci sayısı CRM ziyaret yerlerinden, kitap listesi yaş uygunluk raporuyla); aşama «teklif».
- 16:30 Belediye kütüphane bağışı projesi: sevkiyat tamamlandı (CRM), aşama «rapor»; erişim raporu taslağı.
- Ay sonu: yönetime tek sayfa — temas, hediye, projeler, yansıma.

**«Bunu görürsem hemen kullanırım»**
1. Kişi kartında bütün gönderim ve görüşme geçmişi, ilişki sahibi.
2. Kitaba göre gerekçeli «kime gönderelim» listesi ve kişisel not taslağı.
3. Proje aşama panosu ve MEB ölçütlerine dayanan teklif taslağı.

**«Bunu yaparsanız kullanmam»**
1. Kişileri inanç/siyaset gibi hassas özelliklerle etiketleyen ya da puanlayan sistem — hukuki risk ve itibar riski.
2. Özel notlarımın herkesçe okunabilmesi.
3. Kişiye otomatik e-posta/mesaj gönderen otomasyon.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (tablo/görünüm/ölçü) | CRM (varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Kişi/kurum kartı | — | `ContactBase` (`FullName`, `JobTitle`, `new_unvan`, `new_AkademikTitrid`, `new_Meslekid`, `AccountRoleCode`, `ParentCustomerId`), `AccountBase.new_KurumRolu`, `new_ziyaretyerleriBase` | — | SQL; kişi verisi modele toplu gönderilmez |
| Alan etiketi önerisi | — | Unvan, meslek, uzmanlık alanı metinleri | Kapalı seçim: onaylı sabit alan listesinden biri (akademi/eğitim/medya/STK/kamu yönetimi/kültür-sanat/diğer) — tek token + olasılık; **inanç/siyaset sınıfı listede yok** | Sınıflandırma, KVKK sınırı listeyle korunur |
| Kitap-kişi eşleştirmesi | — | `new_kitapBase` (`new_turlertext`, `new_hedefkitle`, `new_ozet`), kişinin alanı ve geçmiş gönderimleri (köprü) | Puan kuralla; model gerekçe cümlesi | Açıklanabilir |
| Kişisel not | — | Kitap metni + ilişki geçmişi (yalnız o kişinin kartı) | Kısa not taslağı | Metin işi |
| Hediye gönderim durumu | — | `new_siparisBase` (`new_siparistipi` 12/15/10/11, `statuscode`, `new_sevktarihi`) | — | SQL |
| Teklif dosyası | — | Kurum (`new_ziyaretyerleriBase` öğrenci/okul sayısı), kitap listesi | Taslak (amaç, kapsam, fayda, takvim); MEB ölçüt maddeleri belgeden aynen alıntılanır, model uydurmaz | Metin + kaynaklı madde |
| Proje erişimi | (varsa) Logo `KURUM` kanalı satış/sevkiyat (`SPECODE2='KURUM'`) | Sipariş/sevkiyat adedi, ziyaret yerleri | Rapor yorumu | Rakam SQL'den |
| Etki izleme (sonraki) | — | — | Yansıma/paylaşım metninde kitap/TİMAŞ bahsi ve tonu (kapalı seçim) | Sınıflandırma |

Model yalnız LLM kapısından: `rt.llm_for("kurumsal")`; toplu etiket önerisi `BATCH`.

## 14. Kodlama planı (kodlayıcıya devir)

**Köprü dosyaları** — `backend/semantic_bridge/public_affairs.py` (kart, not, ısı, hediye, proje), `public_affairs_sources.py` (CRM SQL), `public_affairs_api.py` (`register`). Ön adım: `author_relations.py`'deki kart/not/ısı çekirdeği `relations_core.py`'ye çıkarılır (M7 davranışı değişmeden; M7 kabul testleri yeniden koşulur).

**Tablolar**
- `semantic_rel_people` (id, tenant_id, crm_contact_id NULL, crm_account_id NULL, name, org_name, title, field_key [sabit liste], is_public_official bool, owner_user, priority [kritik/normal], contact_json, created_by, updated_at)
- `semantic_rel_orgs` (id, tenant_id, crm_visit_place_id NULL, crm_account_id NULL, name, kind [MEB/okul/üniversite/belediye/kaymakamlık/valilik/Diyanet/kütüphane/STK/diğer], city, owner_user)
- `semantic_rel_notes` (id, person_id NULL, org_id NULL, at, channel, tone, text, visibility [herkes/ben-ve-katılımcılar], next_step, next_on, created_by)
- `semantic_rel_gifts` (id, tenant_id, month, person_id, crm_book_id, reason, note_text, status [öneri/onaylı/sevk/teslim/dönüş/iptal], crm_order_no NULL, approved_by, feedback)
- `semantic_rel_projects` (id, tenant_id, org_id, title, kind [okuma kampanyası/kütüphane bağışı/eğitim materyali/etkinlik/diğer], stage, owner_user, budget, books_json, reach_schools, reach_students, reach_books, created_by, updated_at)
- `semantic_rel_project_events` (project_id, at, user, stage_from, stage_to, note, doc_ref)
- `semantic_rel_fields` (key, label, active) — yönetimce onaylanan alan listesi; hassas kategori eklenemez (kodda yasak listesi).

**Uçlar** (`/api/v1/public-affairs/*`): `GET meta`, `GET home`, `GET people`, `POST people`, `GET/PATCH people/{id}`, `POST people/{id}/notes`, `GET orgs`, `POST orgs`, `GET orgs/{id}` (CRM ziyaret yeri istatistiği), `GET gifts?month=`, `POST gifts/suggest` (kitap listesi → kişi önerisi), `PATCH gifts/{id}`, `POST gifts/approve`, `GET projects`, `POST projects`, `PATCH projects/{id}`, `POST projects/{id}/draft-proposal` (LLM iş), `GET projects/{id}/report`, `GET report/export.pdf`, `POST run-due` (SYSTEM).

**Ekranlar** — `src/canvas/public-affairs/` (`PaHome.tsx`, `PaPeople.tsx`, `PaPersonCard.tsx`, `PaOrgs.tsx`, `PaGifts.tsx`, `PaProjects.tsx`, `PaReport.tsx`); rota `/timas/kurumsal-iliskiler` (+ `/kisi/:id`, `/kurumlar`, `/hediye`, `/projeler`, `/rapor`). Menü: `pazarlama` alanı, bölüm `section: 'İlişkiler'`, öğe `{ id: 'kurumsal-iliskiler', label: 'Kurumsal ilişkiler', icon: Landmark, hint: 'Kanaat önderleri, kurumlar ve kamu projeleri' }` — yöneticilerin isteğine göre `kayitlar` alanına da taşınabilir (tek tanım, tek yer). Kampüs: M28 çalışan. Telefon: görüşme notu ve onay kartları.

**Yetki** — `sayfa:kurumsal-iliskiler`; `ozellik:kurumsal.duzenle`; `ozellik:kurumsal.onay` (explicit); `ozellik:kurumsal.hassas` (explicit). `access.py`: `("/api/v1/public-affairs/run-due", SYSTEM)`, `("/api/v1/public-affairs/", frozenset({page("kurumsal-iliskiler")}))`; FEATURE_RULES yazma uçları → `ozellik:kurumsal.duzenle`; `gifts/approve` ve proje bütçesi ucun içinde `ozellik:kurumsal.onay`; «ben ve katılımcılar» notları yanıtta yetkiye göre boşaltılır; export → `ozellik:veri.disa-aktar`.

**Zamanlayıcı** — `scripts/server/timas-public-affairs.timer` pazartesi 08:00: temas zamanı gelen kişiler, geciken proje adımları; her gün 07:50: hediye satırlarının CRM sipariş durumu.

**Kabul testleri**
1. Kurum istatistiği: seçilen il için okul sayısı ve öğrenci toplamı = `SELECT COUNT(*), SUM(TRY_CONVERT(int, NULLIF(new_renciSays,''))) FROM Timas_MSCRM.dbo.new_ziyaretyerleriBase WHERE new_KurumTipi = 1 AND new_ili = '<il guid>'` (sayıya çevrilemeyen satır sayısı ayrıca gösterilir).
2. Tanıtım gönderimi (yıl): «hediye/tanıtım olarak kaç kitap» = `SELECT SUM(ss.new_adet) FROM Timas_MSCRM.dbo.new_siparissatiriBase ss JOIN Timas_MSCRM.dbo.new_siparisBase s ON s.new_siparisId = ss.new_siparisid WHERE s.new_siparistipi = 12 AND s.new_siparistarihi >= '2026-01-01' AND s.statuscode <> <iptal kodu>` (iptal kodu StringMap'ten okunur).
3. Deprem bağışı ve okul/öğretmen örneği adetleri aynı sorguyla `new_siparistipi IN (15)` ve `IN (10,11)`.
4. Karar verici kişiler: «Karar Veren» rolündeki kurum kişileri = `SELECT COUNT(*) FROM Timas_MSCRM.dbo.ContactBase WHERE statecode = 0 AND AccountRoleCode = 1`.
5. Hediye tekrar kuralı: `SELECT person_id, crm_book_id, COUNT(*) FROM semantic_rel_gifts WHERE status NOT IN ('iptal') GROUP BY person_id, crm_book_id HAVING COUNT(*) > 1` boş.
6. KVKK: `semantic_rel_fields` ve kişi kartı yanıtlarında yasak liste (inanç, mezhep, cemaat, siyasi, parti) taraması 0; alan ekleme ucu yasak kelimeyi reddeder (test).
7. Gizlilik: «ben ve katılımcılar» notu başka kullanıcının yanıtında metinsiz döner (M7 kabul testiyle aynı desen).

**Bağımlılık** — `relations_core.py` ayrıştırması önce (M7 regresyonu). M31/M32/M33 ile kurum tablosu ortak kaynaktan (CRM ziyaret yerleri) okunur; M33 ihale fırsatı gelince proje «fikir» aşamasına bağlanır — beklenmez. KVKK alan listesi (soru 3) ilk kodlamadan önce yönetim/hukuk onayı ister; onay gelene kadar alan listesi yalnız kurum türüyle (akademi/eğitim/medya/STK/kamu yönetimi/diğer) başlar.

**Tahmini büyüklük** — L (3+ gün): çekirdek ayrıştırma S, kart/not/hediye M, proje + teklif taslağı M, rapor S.
