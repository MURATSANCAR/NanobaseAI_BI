# Yetki mekanizması — analiz (2026-09-27)

İstek: (1) AD kullanıcıları ve gruplarına bağlı yetki; hangi sayfa/menüyü kim görür buradan ayarlanır; bir
kullanıcı bir gruba eklenince o grubun gördüğü her şeyi görür. (2) Ekranlardaki özellikler de rol bazlı
açılır/kapanır.

Bu belge yalnız analizdir; kod yazılmadı. Kararlar bölüm 10'da.

---

## 1. Bugün ne var

| Katman | Bugünkü durum | Dosya |
|---|---|---|
| Giriş | AD (NTLM bind), oturum 8 saat, SQLite'ta yalnız `username` + `displayName`. Oturumda grup bilgisi **yok**. | `scripts/server/portal-login/server.py` |
| Kimlik köprüde | Her istekte çerez giriş servisine (`/session`) sorulur → `board.user_of()` | `backend/semantic_bridge/board.py:110` |
| Rol | Yalnız iki rol: **yönetici** (`TIMAS_ADMIN_USERS` listesi + `TIMAS_ADMIN_GROUP` AD grubu, iç içe gruplar dahil) ve **editör** (`TIMAS_EDITOR_GROUP`, yalnız menü sırası, yetki vermez) | `backend/semantic_bridge/admin.py:211-225, 566` |
| AD grup üyeliği | Canlı AD istek yolunda okunmaz. 15 dk'lık `timas-admin-group.timer` grubu okuyup `semantic_admin_group` tablosuna yazar; AD okunamazsa eski görüntü korunur. | `admin.py:468-555` |
| Menü | Tek tanım `NAV`; öğede `adminOnly` ve ortam bayrağı `feature`. `visibleNav(role, flags)` süzer. Ray, telefon menüsü, ⌘K, Kampüs hepsi buradan okur. | `src/canvas/nav/navModel.ts` |
| Rota | Hepsi `RequireTimasSession` altında (oturum şart). Yalnız yönetim ekranları `AdminGuard` ile korunuyor; öteki sayfalar adres elle yazılınca herkese açılır. | `src/App.tsx:70-118`, `src/canvas/AdminGuard.tsx` |
| Ön yüz rol bilgisi | `GET /api/v1/admin/me` → `{user, isAdmin, isEditor}`; `useAdminMe()` | `app.py:4728`, `src/canvas/useAdmin.ts` |
| Arka uç kapısı | nginx `auth_request` yalnız «oturum var mı» der, sonra paylaşılan `X-Semantic-Caller` jetonunu ekler. Köprü uçlarının büyük çoğunluğu yalnız `_require_caller` çağırır = **giriş yapmış herkes her ucu çağırabilir**. Kişiye bakan kontroller yalnız `_admin_gate`, `_require_admin` ve birkaç sahiplik kontrolü (pano, oda iptali, yazar giriş, masa). | `app.py:1794-1840, 2960` |

**Sonuç:** bugün menüden bir öğeyi gizlemek güvenlik sağlamaz; adresi bilen kişi sayfayı açar, API'yi
doğrudan çağırır. Asıl kapı köprüde (arka uçta) olmalı; menü ve ekran yalnız bu kapının yansıması olmalı.

İyi haber: gereken parçaların yarısı zaten var — AD'den iç içe grup okuma, grup görüntüsü tablosu, 15 dk
tazeleme, tek menü tanımı, yönetici kapısı deseni, değişiklik kaydı (`semantic_audit`).

---

## 2. Hedef model

```
AD kullanıcısı ──üyesi──▶ AD grubu ──bağlı──▶ Rol ──içerir──▶ Yetki anahtarları
      │                                        ▲                (sayfa + özellik)
      └────────────── doğrudan bağ ────────────┘
```

- **Yetki anahtarı**: tek bir sayfa, tek bir özellik ya da tek bir veri alanı. Örn.
  `sayfa:finansal-denetim`, `ozellik:kart.sql-goster`, `veri:muhasebe` (Zeki AI'ın hangi tabloları
  okuyabileceği, bölüm 8).
- **Rol**: yetki anahtarlarının adlı kümesi (örn. «Finans okuyucu», «Editör», «Pazarlama»). Portalda,
  Yönetim ekranında tanımlanır.
- **Bağ**: bir AD grubu (ya da tek bir AD kullanıcısı) → bir veya birden çok rol.
- **Kişinin yetkisi** = bağlı olduğu bütün grupların + doğrudan bağlarının rollerindeki anahtarların
  **birleşimi**. «Yasak» kuralı yok: bir yerden izin gelirse izinlidir. Bu, «gruba eklenince o grupta ne
  varsa görür» isteğini birebir karşılar ve kimin neyi neden gördüğünü açıklamayı kolaylaştırır.
- **Yönetici** her şeyi görür. `TIMAS_ADMIN_USERS` listesi kilitlenmeye karşı kalır (AD okunamasa da
  yönetici içeri girer ve yetkileri düzeltir).
- **Ortam bayrağı** (`WEB_WATCH_ENABLED` gibi) yetkiden ayrı kalır: ortamda kapalı özellik yetkisi olan
  kişiye de görünmez.

### Neden AD grubuna doğrudan değil de rol üzerinden

AD grupları BT'nin düzenidir (departman, bina, dağıtım listesi); portalın ekran düzeniyle birebir
örtüşmez. Rol katmanı olunca:
- «Finans okuyucu» bir kez tanımlanır, üç AD grubuna bağlanır; ekran eklenince tek yerde güncellenir.
- AD'de grup açtırmak gerekmez; mevcut gruplar kullanılır.
- Tek kişiye istisna (geçici erişim) grup açmadan verilir.

İstenirse ekranda «her AD grubuna bir rol» diye de kullanılabilir; model bunu da kaldırır.

---

## 3. Yetki anahtarları

### 3.1 Sayfa anahtarları

Menü öğelerinin `id`'sinden türetilir; yeni bir sayfa menüye eklenince anahtarı kendiliğinden olur.
Menüde olmayan detay sayfaları bağlı olduğu öğenin anahtarını kullanır (bugünkü `also` alanı zaten bu
eşleşmeyi tutuyor):

| Alan | Sayfa anahtarları |
|---|---|
| Kampüs | `kampus` (her zaman açık: giriş sonrası boş ekran olmasın) |
| Analiz | `genel-bakis`, `panolar`, `planli-raporlar`, `uyarilar` |
| Finans | `finansal-denetim`, `yonetim-raporlari`, `baski-oneri` |
| Editoryal | `editoryal` (+ `/kitap/:id`), `yazar-giris` (+ `/yazar-giris/:id`), `yayin-kurulu`, `redaksiyon`, `cevirmenler`, `son-okuma`, `kitap-tasarim` (+ `/kitap-tasarim/:iş/*`) |
| Kayıtlar | `kisiler`, `basin-web`, `telif-sozlesme`, `editor-atama` |
| Pazarlama | `seo-geo` ve 9 alt sayfası |
| Yönetim | `veri-sozlugu`, `onaylar`, `es-anlamlilar`, `portal-ayarlari` (varsayılan yalnız yönetici) |
| Menü dışı | `sohbet` (Zeki AI sohbet, `/timas/sohbet/`) |

Grup (alan) yetkisi ayrı anahtar değildir: alanın içinden bir sayfa görünüyorsa alan da görünür, hiçbiri
görünmüyorsa alan raydan kalkar (bugünkü `visibleNav` zaten boş grubu atıyor).

### 3.2 Özellik anahtarları

Özellik = sayfa içindeki bir işlem. Beş tür yeter:

| Tür | Örnek | Anlam |
|---|---|---|
| `gor` | `kart.sql-goster` | Bir paneli/bilgiyi görmek |
| `islem` | `pano.kart-ekle`, `uyari.kural-yaz` | Kayıt oluşturmak/değiştirmek |
| `sil` | `rapor.sil` | Silmek |
| `onay` | `seo.oneri-onayla`, `editor.inceleme-karar` | Başkasının/modelin önerisini kabul etmek |
| `disa-aktar` | `pano.csv`, `rapor.excel` | Veriyi dışarı almak |
| `kapsam` | `yazar-giris.herkesinki` | Yalnız kendi kaydını değil herkesinkini görmek/değiştirmek (bugün `is_admin` ile bağlı) |

Tam liste envanterden çıkar (bölüm 7). Kural: **her özellik bir sayfaya bağlıdır**; sayfası kapalı
kişiye özelliği açık olsa da görünmez.

### 3.3 Tek kaynak

Anahtar listesi **tek bir JSON dosyasında** (`shared/access-catalog.json`): anahtar, Türkçe ad, ait olduğu
sayfa, tür, açıklama. Köprü bunu okur (doğrulama + yönetim ekranına katalog), ön yüz derlemede içe
aktarır (TypeScript tipi buradan: yanlış yazılmış anahtar derlemede hata verir). İki tarafın ayrı liste
tutması bir gün mutlaka ayrışır.

---

## 4. Nerede zorlanır — dört katman

| # | Katman | Ne yapar | Zorunlu mu |
|---|---|---|---|
| 1 | **Köprü (arka uç)** | Her uç bir yetki anahtarı taşır; yoksa 403 `FORBIDDEN`. | **Evet — tek gerçek kapı** |
| 2 | Rota | `<RequirePerm perm="…">` (bugünkü `AdminGuard`'ın genellemesi); yetkisiz kişi «Yetkiniz yok» kartı görür, iç bileşen hiç yüklenmez. | Evet |
| 3 | Menü | `visibleNav` `adminOnly` yerine anahtara bakar. Ray, telefon, ⌘K, Kampüs, Son açılanlar aynı listeden. | Evet |
| 4 | Ekran içi | `<Can perm="…">` / `useCan("…")`: düğme, sekme, panel. | Özellik aşamasında |

### 4.1 Köprüde uygulama

- `require(request, "sayfa:finansal-denetim")` — FastAPI bağımlılığı. İçeride: `_require_caller`
  (bugünkü jeton) + çerezden kişi + kişinin yetki kümesi.
- **Uç → anahtar eşlemesi** yönlendirici (router) düzeyinde: `/api/v1/financial-audit/*` →
  `sayfa:finansal-denetim`, `/api/v1/seo-geo/*` → `sayfa:seo-geo` … Özellik isteyen uçlar (sil, onayla,
  dışa aktar) ek olarak kendi anahtarını ister.
- **Kapsam testi**: köprüdeki bütün yolları listeleyen bir test; anahtarı olmayan (ve «herkese açık» ya
  da «sistem işi» diye işaretlenmemiş) her uç testi düşürür. Böylece yarın eklenen bir uç yetkisiz
  kalamaz.
- **Sistem işleri** (timer'lar: `run-due`, `alerts/check`, `admin/group/refresh`) çerezsiz, yalnız
  jetonla gelir. Bunlar «sistem» olarak işaretlenir; çerezli kişi bu uçlara giremez.
- **Birden çok sayfanın ortak kullandığı uçlar** (kişi rehberi, kitap arama, profil, tercih): «oturum
  yeter» diye işaretlenir; sayfa yetkisi istemez.

### 4.2 Köprü dışındaki kapılar

| Yüzey | Bugün | Yapılacak |
|---|---|---|
| Zeki AI sohbet (`/timas/sohbet/`) | nginx yalnız oturuma bakıyor | Giriş servisine `/check?perm=sohbet`; `/chat-sso` da yetkiye bakar |
| Metrikler (`/timas/metrics/`) | oturum | aynı, `perm=portal-ayarlari` |
| GPU editör servisleri | köprü üzerinden, `X-Editor` başlığı köprü koyar | köprüdeki uç yetkisi yeter (doğrudan yol yok) |
| Zamanlı işler | jeton | değişmez |

Giriş servisi (`server.py`) yetkiyi kendisi hesaplamaz; köprünün `/api/v1/access/check` ucuna sorar ya da
aynı Postgres tablolarını okur. Öneri: köprüye sormak (tek hesaplama yeri), kısa bellek önbelleğiyle.

---

## 5. Veri modeli

Meta DB (Postgres), `semantic_` önekiyle, köprünün `ensure()` desenine uygun:

```
semantic_access_roles       (id, tenant_id, name, description, is_system, created_by, created_at, updated_at)
semantic_access_role_perms  (role_id, perm_key)                         -- PK (role_id, perm_key)
semantic_access_bindings    (id, tenant_id, role_id, subject_type,      -- 'group' | 'user'
                             subject, created_by, created_at)          -- subject: grup adı/DN ya da sAMAccountName
semantic_admin_group        (mevcut tablo; group_name → üye listesi)    -- bağlı her grup için satır
```

- `semantic_admin_group` tablosu zaten «grup adı → üyeler» tutuyor; yalnız yönetici/editör grubu için değil,
  **bağı olan her AD grubu** için doldurulur. Tabloya dokunmadan kullanılabilir.
- Sistem rolleri (`is_system`): **Yönetici** (hepsi, silinemez), **Herkes** (bkz. 6.2).
- Her değişiklik `semantic_audit`'e `kind='access'` ile yazılır (kim, hangi role hangi anahtarı ekledi/çıkardı,
  hangi grubu bağladı).

### Etkin yetki hesaplama

```
gruplar(kişi)  = { g | g bağlı bir grup ve kişi ∈ semantic_admin_group[g].members }
roller(kişi)   = bağlar(gruplar(kişi)) ∪ bağlar(kişi) ∪ {Herkes}
yetki(kişi)    = ∪ rol.perms   (yönetici ise hepsi)
```

- Bellekte 30 sn önbellek (bugünkü `_grp_mem` deseni). Canlı AD istek yolunda okunmaz.
- `GET /api/v1/access/me` → `{user, displayName, roles[], perms[], isAdmin, workspace}`. Bugünkü
  `/api/v1/admin/me` bunun üstüne ince bir sarmal olarak kalır (geri uyumluluk).
- `isEditor` (menü sırası) rolün bir özelliği olur: rolde «çalışma alanı: Editoryal» seçilir; ayrı AD
  grubu ayarı gerekmez.

### AD değişikliği ne zaman yansır

| Olay | Yansıma |
|---|---|
| Kullanıcı AD'de gruba eklendi/çıkarıldı | En geç 15 dk (timer). Yönetim ekranında «Şimdi tazele» düğmesi anında. Kişinin çıkış-giriş yapması gerekmez: yetki her istekte hesaplanır. |
| Rol/yetki portalda değişti | 30 sn içinde (önbellek). Açık sekme menüyü bir sonraki sorguda (en geç 60 sn) yeniler. |
| AD'ye ulaşılamıyor | Son görüntü geçerli kalır; yönetim ekranında hata ve son tazeleme zamanı görünür. |
| AD'de hesap kapatıldı | Yeni giriş zaten reddedilir; açık oturum 8 saat içinde düşer. İstenirse tazelemede grup üyesi olmayan açık oturumlar silinir. |

---

## 6. Yönetim ekranı

`/yonetim` → yeni sekme **«Yetkiler»**. Üç bölüm:

1. **Roller** — liste + düzenleyici. Düzenleyici menüyle aynı ağaç: alan → sayfa (onay kutusu) → sayfanın
   altında özellikleri (onay kutusu). Sayfa kapatılınca özellikleri soluklaşır. «Bu rolle menü şöyle
   görünür» önizlemesi yanında.
2. **Bağlar** — «AD grubu ya da kişi → roller». AD grubu seçici dizinde arar (yeni uç:
   `GET /api/v1/access/ad-groups?q=`, servis hesabıyla). Kişi seçici mevcut kişi rehberinden. Grup
   bağlanınca üyeleri hemen okunur ve sayısı gösterilir.
3. **Kişi gözüyle** — bir kişi seçilir: hangi AD gruplarında, hangi rolleri hangi gruptan alıyor, hangi
   sayfa ve özellikleri görüyor ve **neden** (her satırın yanında kaynağı: «Finans-Muhasebe grubundan →
   Finans okuyucu rolü»). Yanlış yetki şikâyetinde ilk bakılacak yer.


### 6.1 Yetkisiz özellik: gizlenir (karar)

Yetkisi olmayan kişi düğmeyi, sekmeyi, paneli **hiç görmez**; soluk/pasif düğme yok. Arka uç yine 403
verir (gizlemek kapı değildir).

### 6.2 Geçiş (karar): prod öncesine kadar herkes her şeyi görür

- Kurulumda sistem rolü **«Herkes»** oluşturulur, bütün sayfa + özellik + veri alanı anahtarlarını içerir
  (yönetim sayfaları hariç — onlar bugün de yalnız yöneticide). Kurulum anında davranış birebir aynıdır.
- Roller ve AD grup bağları **prod öncesi** tanımlanır; o gün «Herkes» yalnız Kampüs'e (+ istenirse Sohbet)
  daraltılır. Bu, tek onay kutusu işidir; kod değişikliği gerekmez.
- Mekanizma ve kapılar (köprü 403, rota, menü, veri kapsamı) kurulumla birlikte devrededir; yalnız «Herkes»
  geniş olduğu için kimse fark etmez. Böylece prod'a geçerken ayrıca kod kurulmaz.

---

## 7. Ekran özellikleri envanteri

Kaynak kod taraması (2026-09-27). Köprüde **333 uç** var:

| Bugünkü kapı | Uç sayısı | Anlamı |
|---|---|---|
| Hiç kontrol yok | 16 | `generate_summary` (gövdeden SQL çalıştırır), `feedback`, `semantic/resolve`, `explain`, `schema/inventory`… |
| Yalnız jeton (`_require_caller`) | 25 | `run_sql`, `ask`, `ask/stream`, timer uçları, **Finansal denetimin 12 ucunun hepsi** |
| Oturum (kişi okunur, rol yok) | ~244 | Kitap tasarım (90), editoryal, pano, rapor, uyarı, oda, kişi, SEO (23), yönetim raporları |
| Rol/sahip kontrolü | 48 | 32 hep yönetici, 11 yönetici-jetonlu (`SEMANTIC_ADMIN_TOKEN` boşsa açık), 5 SEO onaycısı |

Yani uçların ~%87'si giriş yapmış herkese açık. Aşağıda **önerilen özellik anahtarları** var — her biri
envanterdeki bir ya da birkaç düğmeyi ve arkasındaki ucu kapsar. Sayfa anahtarı (bölüm 3.1) sayfayı ve
okuma uçlarını açar; bu tablolar sayfanın **içindeki** işlemlerdir.

### 7.1 Ortak (birçok ekranda)

| Anahtar | Ekrandaki karşılığı | Uç |
|---|---|---|
| `zeki.soru` | Zeki AI'a sor (Kampüs, Genel bakış, Pano «kart ekle», Uyarı «şu anki değeri ölç») | `/ask`, `/ask/stream` |
| `kart.sql-goster` | «SQL'i göster / Kopyala» (`CardSql.tsx`, pano SQL paneli, rapor «son SQL», denetim `SqlEvidence`, Baskı öneri «Kaynaklar») | yanıtın içinde → yanıttan `sql` alanı sunucuda çıkarılır |
| `veri.disa-aktar` | Excel / CSV / PDF (pano, Baskı öneri CSV, rehber CSV, SEO CSV) | `board/export.xlsx` + istemci tarafı |

### 7.2 Analiz

| Anahtar | Ekrandaki karşılığı |
|---|---|
| `pano.duzenle` | Panoya ekle, kart ekle/çıkar/boyut/grafik, otomatik tazeleme saati |
| `rapor.planla` | Taslak oluştur, plan kaydet/düzenle, duraklat/sürdür, sil |
| `rapor.eposta` | Alıcı ekleme, «Şimdi çalıştır» (e-posta gider) |
| `uyari.kural` | Kural kaydet, duraklat, sil, «şimdi kontrol et» |

### 7.3 Finans

| Anahtar | Ekrandaki karşılığı |
|---|---|
| `denetim.detay` | Logo hareket detayı, e-defter belgeleri, istisnalar |
| `denetim.inceleme` | İncelemeyi kaydet (not + kanıt) — bugün kimin yazdığı kaydedilmiyor, düzeltilir |
| `denetim.yenile` | Verileri yenile |
| `yonetim-raporu.yenile` | Baskı öneri «Verileri yenile» |

### 7.4 Editoryal

| Anahtar | Ekrandaki karşılığı |
|---|---|
| `kitap.ticari` | Kitap 360'ta fiyat, telif, editör görüşleri |
| `kitap.inceleme-karar` | İnceleme kuyruğu kararı (tekil/toplu/düzelt) — bugün sahip/rol kontrolü yok |
| `yazar-giris.herkesinki` | Yazar giriş listesinde herkesin projesi (bugün `is_admin`) |
| `yayin-kurulu.gorusler` | Üye görüşleri adıyla (bugün `is_admin`) |
| `redaksiyon.calis` | Yeni eser, metin yükle, ZEKİ incelemesi, öneri kabul/red, bölüm onayı |
| `son-okuma.calis` | Prova yükle, ISBN, kontrol geçti/kaldı, bulgu kararı, Word indir |
| `son-okuma.imzaci` | İmzacı ekle/çıkar |
| `masa.herkesinki` | Masam'da herkesin işi (bugün `is_admin`) |
| `tasarim.uret` | Üretim başlat (kitaptan/Word), yeniden başlat/sürdür — **GPU harcar** |
| `tasarim.gorsel` | Görsel yeniden üret, figür üret, dekupe, büyüt, boyama, kolaj — **GPU harcar** |
| `tasarim.duzenle` | Sayfa planı, künye, resim modu, varyant seç/onayla, sürüme dön, fotoğraf yükle |
| `tasarim.seslendirme` | Seslendirme (tümü/sayfa) — **GPU harcar** |
| `tasarim.pazarlama` | Arka kapak, ürün sayfası → SEO'ya öneri, sosyal görsel |
| `tasarim.baski` | İç/kapak/baskı PDF'i, EPUB |
| `tasarim.herkesinki` | Başkasının tasarım işini açmak/değiştirmek — bugün hiçbir sahip kontrolü yok |

### 7.5 Kayıtlar

| Anahtar | Ekrandaki karşılığı |
|---|---|
| `sozlesme.tutar` | Avans tutarı, telif oranları, ortalama telif (Sözleşmeler, Kişiler) |

### 7.6 Pazarlama (SEO & GEO)

| Anahtar | Ekrandaki karşılığı |
|---|---|
| `seo.oneri-uret` | Öneri üret (ürün, sayfa), önceden toplu üret — **model harcar** |
| `seo.onay` | Onayla / Reddet / toplu onay (ürün, sayfa, yönlendirme) — bugün `SEO_APPROVERS` listesi; role taşınır |
| `seo.esitle` | T-soft eşitle, şema taraması, arama verisini yenile |
| `seo.gorunurluk` | Yapay zekâ görünürlüğü: soru ekle/sil/ölç |

### 7.7 Kampüs ve Yönetim

| Anahtar | Ekrandaki karşılığı |
|---|---|
| `oda.yonet` | Oda ekle/kaldır, başkasının rezervasyonunu iptal (bugün `is_admin`) |
| `yonetim.*` | Yönetim sayfaları bugünkü gibi yalnız Yönetici rolünde; ayrıca bölünmez |

Sahip kontrolleri (kendi panosu, kendi raporu, kendi rezervasyonu, kendi profili) olduğu gibi kalır;
yalnız «herkesinki» kapsamı `is_admin` yerine bir yetki anahtarına bağlanır.

### 7.8 Önce kapatılacak açıklar (yetki modelinden bağımsız)

Bunlar kapanmadan rol tanımlamak anlamsız; Aşama A'nın ilk işi:

1. `/api/v1/generate_summary` hiçbir kontrol yapmadan gövdedeki SQL'i çalıştırıyor (`app.py:2110`).
2. `/api/v1/run_sql` yalnız jetonla; ön yüz Genel bakış göstergelerini ham SQL göndererek alıyor
   (`cfo.ts:222`). Veri kapsamı (bölüm 8) bu ucu da kişiye göre süzecek; ayrıca SQL'in kendisi değil,
   gösterge kimliği gönderilmeli.
3. Finansal denetimin 12 ucu kişiyi hiç okumuyor; inceleme notu kimin yazdığı olmadan kaydediliyor.
4. `_require_admin` uçları `SEMANTIC_ADMIN_TOKEN` boşsa herkese açık (`app.py:1802`); tarayıcıdan gelen
   istekte oturum + yönetici şartı jetondan bağımsız olmalı.
5. Kitap tasarımında işin sahibi kontrol edilmiyor; herkes herkesin işini yeniden başlatabilir/silebilir.
6. Rotalar menüden gizlense de adresle açılıyor (yalnız 4 ekran kendini koruyor).

---

## 8. Zeki AI veri kapsamı (karar: bu işe dahil)

Sayfa yetkisi veriyi korumaz: Finansal denetim sayfası kapalı biri Genel bakıştaki soru kutusuna «cari
bakiyeler» yazarsa cevap alır. Bu yüzden rolün üçüncü boyutu **veri alanı**dır.

### 8.1 Veri alanı nedir

Kataloğun her varlığı (tablo/görünüm) bir veri alanına bağlıdır. Rol, sayfa ve özelliklerin yanında
hangi veri alanlarını okuyabileceğini de taşır: `veri:satis`, `veri:muhasebe` …

Önerilen ilk alanlar (Logo tablo ailesinden ve CRM şemasından kural ile atanır, tablo tablo elle değil):

| Veri alanı | Kapsadığı (örnek) |
|---|---|
| `satis` | Fatura, fatura satırı, sevkiyat, sipariş, satış kanalları |
| `stok` | Malzeme kartı, stok hareketleri, depo |
| `cari` | Cari kart, cari hareket, ödeme/tahsilat, vade/yaşlandırma |
| `muhasebe` | Genel muhasebe fişi/satırı, hesap planı, bakiyeler |
| `banka-kasa` | Banka ve kasa hareketleri, çek/senet |
| `yayin-crm` | CRM kitap/proje kartları, yazar giriş, editör atama |
| `telif-sozlesme` | CRM sözleşme, telif oranı, avans, serbest çalışan ödemeleri |

Kural: tablo ailesi → alan eşlemesi tek dosyada (`shared/data-domains.json`); ailesi bulunamayan
varlık `atanmamis` alanına düşer ve Yönetim → Yetkiler'de «atanmamış varlıklar» listesinde görünür (gece
taraması yeni tablo getirirse sessizce kimseye açılmaz ya da herkese açılmaz — yönetici görür). Kesin
eşleme listesi, test sunucusunda kataloğun sertifikalı varlıkları sayılarak çıkarılır.

Kişisel veri: `ColumnProfile.sensitive` zaten var (modele gönderilmez, gösterilmez); bu değişmez, veri
alanına ek bir katman.

### 8.2 Nerede zorlanır

Tek geçit zaten var: bütün SQL `Runtime.run_sql` → `allowed_tables(sql, profiles, …)` üstünden geçer
(`app.py:454-462`). Kişinin kapsamı bu çağrıya verilir:

1. **SQL kapısı (asıl kapı):** `allowed_tables` kişinin veri alanlarına düşen varlıklarla çağrılır;
   kapsam dışı tablo içeren SQL çalışmaz. Bu `ask`, `run_sql`, pano kartı, planlı rapor, uyarı, Baskı
   öneri, iki kaynaklı (Logo+CRM) soru — hepsini birden kapsar.
2. **Model bağlamı:** soru hattı modele yalnız kişinin görebileceği varlıkları verir (`tables_for_question`
   öncesi süzme). Böylece model kapsam dışı tabloyu hiç önermez; cevap «bu veriye yetkiniz yok» diye
   açık döner, bozuk SQL denemesiyle değil.
3. **Önbellek:** cevap/sonuç önbelleğinin anahtarına kapsam girer (aynı soru farklı kapsamda farklı cevap).
4. **Zamanlı işler:** pano tazeleme, planlı rapor ve uyarı gece çerezsiz koşar; **sahibinin kapsamıyla**
   koşmalı. Kişinin yetkisi daraltılırsa raporu da ona göre daralır; kapsam dışına düşen rapor hata
   verir ve sahibine yazılır — sessizce eski veriyi göndermez.
5. **Hazır ekran uçları** (Finansal denetim, Yönetim raporları, sözleşmeler, kitap 360 ticari alanlar):
   sayfa/özellik anahtarıyla korunur; veri alanı SQL kapısından geçenler içindir.
6. **Zeki AI sohbet** (`/timas/sohbet/`, ayrı `zeki-chat` deposu): sohbet BI'a soru soruyorsa kişi
   kimliğini köprüye taşımalı; paylaşılan servis hesabıyla sorulan soru bütün veriyi görür. Açık nokta:
   `zeki-chat` deposunun köprüyü nasıl çağırdığına bakılacak.

### 8.3 Risk

Soru hattına dokunduğu için her değişiklikten sonra tam set regresyonu (`testset_regress.py`) koşar;
«Herkes» rolü bütün alanları taşıdığı sürece sonuçlar birebir aynı çıkmalı (kapı açık = davranış aynı).
Kapsamlı bir test hesabıyla ayrıca: kapsam içi soru cevap verir, kapsam dışı soru net ret verir.

---

## 9. Aşamalar ve süre

| Aşama | İçerik | Süre (tahmini) |
|---|---|---|
| **A — açıklar + sayfa/menü** | 7.8'deki 6 açık; katalog JSON, 3 tablo, etkin yetki hesaplama, `/access/me`, köprüde router→sayfa eşlemesi + kapsam testi, `RequirePerm`, `visibleNav`/Kampüs/⌘K, nginx sohbet/metrik kapısı, «Herkes» rolü, Yönetim → Yetkiler (roller, bağlar, kişi gözüyle), AD grup arama ucu | 3 gün |
| **B — ekran özellikleri** | bölüm 7 anahtarları, `<Can>`/`useCan`, uçlarda işlem yetkisi, `is_admin`'e bağlı «herkesinki» kontrollerinin ve `SEO_APPROVERS`'ın role taşınması, tasarım işlerine sahip | 2 gün |
| **C — veri kapsamı** | veri alanı eşlemesi + atanmamış varlık listesi, SQL kapısında kapsam, model bağlamı süzme, önbellek anahtarı, zamanlı işlerin sahip kapsamıyla koşması, sohbetin kimlik taşıması, tam set regresyonu | 3–4 gün |

Toplam ~8–9 iş günü. Her aşama ayrı kurulur: main → test sunucusu (gerçek AD grubu, iki hesap: biri
grupta biri değil; menü, adrese elle gitme, API'yi doğrudan çağırma → 403, kapsam dışı soru → ret) →
müşteri VM'i.

---

## 10. Kararlar (2026-09-27, kullanıcı)

| Soru | Karar |
|---|---|
| Rol katmanı mı, AD grubuna doğrudan yetki mi | **Rol katmanı** (AD grubu/kişi → rol → yetki) |
| Yetkisiz özellik | **Gizlenir** |
| Zeki AI veri kapsamı | **Bu işe dahil** (bölüm 8, Aşama C) |
| Varsayılan | **Şimdilik herkes her şeyi görür**; roller prod öncesi atanır |
| AD grup adları | **AD'deki mevcut yapıya bakılacak** — bkz. bölüm 11 |

## 11. AD'deki gruplar — açık

2026-09-27'de test sunucusuna SSH zaman aşımına düştü (port 22), AD okunamadı. Döküm betiği hazır:

```bash
sudo /opt/timas-login/venv/bin/python scripts/server/ad-groups-inventory.py
```

Çıktı: OU başına grup sayısı, her grubun türü (güvenlik/dağıtım), kapsamı, üye sayısı, açıklaması ve etkin
kullanıcıların OU dağılımı (kişi adı yazmaz). Buna bakılarak karar verilecek:

- Departman güvenlik grupları varsa ve güncel tutuluyorsa roller doğrudan onlara bağlanır.
- Gruplar dağıtım listesi ağırlıklıysa ya da eksikse: BT'den `Portal-*` güvenlik grupları istenir (ya da
  geçici olarak rol kişiye doğrudan bağlanır).
- OU yapısı departmanı yansıtıyorsa üçüncü seçenek: rolü OU'ya bağlamak (modelde `subject_type='ou'`).
