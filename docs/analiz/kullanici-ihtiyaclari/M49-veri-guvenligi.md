# M49 — Veri Yönetimi ve Güvenlik: kullanıcı ihtiyaç analizi

Durum: ilk sürüm kodlandı (2026-09-28, dalda; sunucuda doğrulanmadı — günlük «M49»). Önceden kodlu: yetki Aşama A/B/C, Yönetim ekranı, değişiklik kaydı, kişisel veri sütunu tespiti — eksikler
bu belgede) · Tarih: 2026-09-28 · Kaynaklar: iş tanımı `specs/M49.txt`, Veri Haritası (`veri_haritasi2.txt`: «Güvenlik
Girdileri», «Risk Girdileri»), `docs/analiz/yetki-mekanizmasi-2026-09-27.md`, `main`'deki `backend/semantic_bridge/access.py`,
`access_catalog.json`, `data_domains.json` (Aşama C), `backend/semantic_bridge/admin.py` (`semantic_audit`,
`semantic_admin_group`), `scripts/server/portal-login/server.py`, `backend/semantic_layer/profiler/sensitivity.py`,
`backend/semantic_layer/store/schema.py` (`sl_query_log`, `sl_schema_profile`), `src/canvas/admin/` (AccessAdmin,
AuditLog, PromptTracker), `docs/analiz/crm-timas-mscrm-detay-2026-09-15.md` (hassas CRM sütunları), `docs/GELISTIRME-GUNLUGU.md`
(2026-09-27/28 yetki ve test verisi girdileri), bellek: `admin-screen`, `no-demo-login`, `crm-systemuser-directory`,
`timas-crm-prod-28`, `deploy-never-deletes-customer-data`, `no-tech-names-on-screens`. Sunucuya bağlanılmadı.

## 1. Modül ne işe yarar

Portalın ve arkasındaki verinin kim tarafından, hangi yetkiyle, ne zaman kullanıldığını izler; kişisel veriyi bulur,
sınıflar, saklama süresini uygular ve KVKK yükümlülüklerinin (aydınlatma, ihlal bildirimi, envanter) belgesini üretir.
İzleme ve süre uygulaması tam otomatiktir (K1); politika, yetki matrisi değişikliği, silme/anonimleştirme planı ve ihlal
bildirimi Zeki AI önerisi + güvenlik/hukuk onayıyla yürür (K2).

TİMAŞ'ın bugünkü durumu: **erişim kapısı kuruldu, izleme ve uyum tarafı yok.** Yetki A/B/C ile sayfa, işlem ve Zeki AI veri
alanı role bağlı (`data_domains.json`, `Runtime._check_data_scope`); ama «Herkes» rolü hâlâ her şeyi taşıyor (karar:
prod öncesi daraltılacak). Portal girişi başarılı/başarısız hiç kayda geçmiyor (`server.py` `log_message` boş, yalnız
dizine ulaşılamazsa stderr); kim hangi ekranı açtı, kim ne indirdi bilinmiyor (değişiklik kaydı yalnız oluştur/güncelle/
sil/çalıştır yazar). Soru kaydı (`sl_query_log`) her sorunun **tam sonucunu** (`result_json`) süresiz saklıyor; depoda bu
tabloyu temizleyen kod bulunamadı. Kişisel veri tespiti TC/e-posta/telefon/IBAN/adres/doğum tarihi/parola kalıplarını
yakalıyor, kişi **adını** kişisel veri saymıyor (`sensitivity.py` `_NAME_PATTERNS`).

## 2. Kim kullanacak (uzman rolleri)

| Rol | TİMAŞ'ta hangi birim | Ne sıklıkla | Masaüstü / telefon |
|---|---|---|---|
| Portal yöneticisi / yetki sorumlusu | BT (bugünkü yöneticiler `TIMAS_ADMIN_USERS` + yönetici AD grubu) | Haftalık; işe giriş-çıkışta | Masaüstü |
| Bilgi güvenliği sorumlusu | BT (**varsayım**: ayrı kişi yok, BT sorumlusu üstlenir) | Günlük uyarı, haftalık inceleme | Masaüstü; uyarı telefonda |
| KVKK irtibat kişisi / hukuk | Hukuk ya da idari işler (**varsayım**; CRM TeamMembership'te hukuk takımı görünmüyor) | Aylık; talep/ihlal anında | Masaüstü |
| Veri sahibi (alan sahibi) | Finans/Mali İşler (muhasebe, banka-kasa, cari), Satış (satış), Editörya (yayın-CRM, telif-sözleşme) — alanlar `data_domains.json`'dan; sahip ataması **varsayım** | Çeyreklik yetki gözden geçirme; rol talebinde | Masaüstü; onay telefonda |
| Üst yönetim | Genel müdürlük (**varsayım**) | Çeyreklik uyum raporu | PDF |

## 3. Bugün bu iş nasıl yapılıyor

- **Portal yöneticisi:** Yönetim → Yetkiler: roller, bağlar (AD grubu / OU / CRM rolü / kişi), «Kişi gözüyle» (hangi
  rolü nereden alıyor), «Veri alanları» (tablo başına alan, «Kurala dön»). Yönetim → Değişiklik kaydı (`semantic_audit`,
  süzgeçli), Soru izleme («Yetki dışı veri» türü dahil). Tıkanma: AD grup yapısı okunmadı (`ad-groups-inventory.py`
  koşulmadı, yetki analizi §11); rol ataması AD'deki mevcut yapıya bağlı bekliyor. Oturum listeleme/kapatma yok (bellek
  `admin-screen`); AD'de kapatılan hesabın açık oturumu 8 saate kadar sürer.
- **Bilgi güvenliği sorumlusu:** portal için elinde bir şey yok. Başarısız giriş denemeleri yalnız ters vekilin erişim
  günlüğünde 401 olarak görünür (**varsayım**: kimse okumuyor). Yetkisiz uç çağrısı (403) tabloya yazılmıyor.
- **KVKK irtibat kişisi:** portalın hangi kişisel veriyi nerede kopyaladığını (soru kaydı, rapor dosyaları, kişi
  profilleri, fotoğraflar, yazar/serbest çalışan kayıtları) gösteren envanter yok. TİMAŞ'ın mevcut KVKK envanteri,
  aydınlatma metinleri ve VERBİS kaydı **bilinmiyor** (soru 1).
- **Veri sahibi:** kimin kendi alanına eriştiğini görmüyor; rol ataması BT'nin elinde, onay akışı yok.
- **Kanıt olarak yakın geçmiş:** 2026-09-28'de test sırasında açılmış hesap izleri (`claude`, `qa-*`) Kişiler listesinde
  kalmıştı, betikle temizlendi (günlük 2026-09-28) — «kim bu hesap» sorusunun cevabını veren bir hesap hijyeni raporu yok.

## 4. İhtiyaçlar ve acı noktaları

**Portal yöneticisi**
1. Hesap hijyeni: CRM'de etkin ama AD'de kapalı (bellek `crm-systemuser-directory`: 30 kişi), uzun süredir girmeyen, test/servis hesapları, rolü olmayan kişiler.
2. Oturum listesi ve tek tıkla oturum kapatma (işten ayrılan, çalınan cihaz).
3. «Herkes» daraltma günü için hazırlık: daraltırsam kim neyi kaybeder önizlemesi.
4. Rol değişikliğinde veri sahibinin onayı (bugün yönetici tek başına verir).

**Bilgi güvenliği sorumlusu**
1. Giriş kaydı: başarılı/başarısız, saat, kaynak adres; aynı hesaba art arda hatalı deneme uyarısı.
2. Yetkisiz erişim denemesi (403, `NOT_PERMITTED`) ve anormal örüntü uyarısı: mesai dışı toplu dışa aktarma, bir kişinin kısa sürede çok sayıda farklı kişi kaydı açması, yeni yönetici eklenmesi, «Herkes»e yetki eklenmesi.
3. Dışa aktarma kaydı: kim hangi veriyi Excel/CSV/PDF/Word olarak indirdi.

**KVKK irtibat kişisi**
1. Portal içi kişisel veri envanteri: hangi kaynak tablo, hangi sütun, hangi portal kopyası, ne kadar süre.
2. Saklama süresinin otomatik uygulanması (soru sonuçları, rapor dosyaları, giriş kayıtları) ve kanıtı.
3. İhlal müdahale planı ve 72 saatlik bildirim akışı; aydınlatma metni taslağı.
4. İlgili kişi talebi (kişi «hakkımda ne tutuyorsunuz» dediğinde) cevabı için arama.

**Veri sahibi**
1. Kendi alanına kimin erişebildiği listesi ve çeyreklik «devam / kaldır» onayı.
2. Yeni rol talebine onay.

## 5. Nasıl kullanmak isteyecekler

**Kullanıcı hikâyeleri**
- Yönetici olarak AD'de kapatılmış ama portalda açık oturumu olan hesapları görüp kapatmak istiyorum, çünkü işten ayrılan kişi 8 saat daha veri görebiliyor.
- Yönetici olarak «Herkes» rolünü daraltmadan önce kimin hangi sayfayı kaybedeceğini görmek istiyorum, çünkü prod günü şikâyet yağmasın.
- Güvenlik sorumlusu olarak bir hesaba 10 dakikada 5'ten çok hatalı giriş denenirse haber almak istiyorum, çünkü parola denemesini erken görmeliyim.
- Güvenlik sorumlusu olarak mesai dışında yapılan toplu dışa aktarmaları haftalık listede görmek istiyorum, çünkü veri sızıntısının en olası yolu bu.
- KVKK irtibat kişisi olarak portalın tuttuğu kişisel veri kopyalarını tek listede görmek istiyorum, çünkü envanterimi güncellemem gerekiyor.
- KVKK irtibat kişisi olarak soru sonuçlarının N gün sonra otomatik silindiğini kanıtıyla görmek istiyorum, çünkü denetimde soracaklar.
- KVKK irtibat kişisi olarak bir ihlal şüphesinde 72 saatlik akışı adım adım yürütmek istiyorum, çünkü süre kaçarsa ceza var.
- Veri sahibi (Mali İşler) olarak muhasebe alanını okuyabilenleri çeyrekte bir onaylamak istiyorum, çünkü yetki birikir.

**Ana ekranlar ve akış** (`/timas/veri-guvenligi`)
- İlk açılış «Özet»: açık güvenlik uyarıları (kırmızı), bekleyen onaylar (rol talebi, gözden geçirme, silme planı), uyum
  göstergeleri (saklama süresi uygulanıyor mu, son uygulama tarihi, envanterde atanmamış tablo sayısı, «Herkes» rolünün kapsamı).
- Sekmeler: Uyarılar · Giriş ve oturumlar · Erişim kaydı (403, dışa aktarma, hassas okuma) · Hesap hijyeni · Kişisel veri
  envanteri · Saklama süreleri · Yetki gözden geçirme · Belgeler (aydınlatma, ihlal planı, olay kayıtları).
- Mevcut Yönetim → Yetkiler ve Değişiklik kaydı yerinde kalır; bu ekran onlara bağlantı verir, kopyalamaz.
- En sık 3 işlem: uyarıyı incele ve kapat (2 tık), oturum kapat (2 tık: kişi → «Oturumlarını kapat»), gözden geçirmede «devam/kaldır» (1 tık/satır, toplu seçim).

**Zeki AI'ya soracakları örnek sorular** (cevap bu modülün tablolarından; sohbetin finans kapsamının dışında ayrı yol)
- «Son 7 günde kimler mesai dışında dışa aktarma yaptı?»
- «Muhasebe verisini okuyabilen kaç kişi var, hangi rollerden?»
- «Dün başarısız girişlerin en çok olduğu hesap hangisi?»
- «Portalda TC kimlik numarası tutan bir tablo ya da dosya var mı?»
- «Ayşe Y. hakkında portalda hangi kayıtlar var?» (ilgili kişi talebi)
- «Herkes rolünü yalnız Kampüs'e daraltırsak kaç kişi hangi sayfayı kaybeder?»
- «Bu çeyrekte kaç rol değişikliği onaysız yapıldı?»

**Otomasyon katmanı**
- K1: giriş/erişim/dışa aktarma kaydı; kural tabanlı anormallik uyarısı; saklama süresi uygulaması (gece); hesap hijyeni
  taraması (gece); envanter yenileme (katalog taramasından sonra).
- K2: veri sınıflandırma önerisi (sütun/tablo için gizlilik derecesi, gerekçesiyle) → alan sahibi onaylar; yetki matrisi
  değişikliği (rol talebi) → veri sahibi onaylar; silme/anonimleştirme planı → KVKK irtibat kişisi onaylar; ihlal bildirimi
  taslağı → hukuk onaylar.
- K3: politika belgelerinin yıllık gözden geçirmesi (Zeki AI farkları çıkarır, karar hukukta).
- K4: yok.

**Bildirim/uyarı**
- Kritik (anında, e-posta): yeni yönetici eklendi; «Herkes» rolüne yetki eklendi; bir hesaba art arda hatalı giriş eşiği;
  mesai dışı toplu dışa aktarma; saklama işi 2 gece üst üste çalışmadı. Alıcı: güvenlik sorumlusu + yönetici.
- Günlük özet: 403 ve `NOT_PERMITTED` sayısı kişi bazında. Alıcı: güvenlik sorumlusu.
- Çeyreklik: yetki gözden geçirme görevi. Alıcı: her veri sahibi.
- İhlal akışında: 24/48/72. saat hatırlatması. Alıcı: KVKK irtibat kişisi + hukuk.

**Onay ve yetki**
- `sayfa:veri-guvenligi` — güvenlik sorumlusu, KVKK irtibat kişisi, yönetici.
- `ozellik:guvenlik.oturum-kapat` (açıkça verilir).
- `ozellik:guvenlik.uyari-kapat` — uyarı inceleme/kapama.
- `ozellik:guvenlik.saklama` (açıkça verilir) — saklama süresi politikasını değiştirmek; silme planını onaylamak.
- `ozellik:guvenlik.ihlal` (açıkça verilir) — ihlal kaydı açmak, bildirim taslağını onaylamak.
- `ozellik:guvenlik.gozden-gecir` — veri sahibinin kendi alanı için «devam/kaldır» kararı (satır erişimi: yalnız sahibi olduğu alanlar).
- Rol/bağ değişikliğinin kendisi bugünkü gibi Yönetim → Yetkiler'de (yönetici); yeni: bir alanın `veri:<alan>` anahtarını
  ekleyen değişiklik, alan sahibi tanımlıysa «onay bekliyor» durumuna düşer (K2).

## 6. Veri

| Gereken veri | Kaynak (Logo / CRM / T-soft / kullanıcı girer / dış) | Depoda bilinen durumu | Boşluk |
|---|---|---|---|
| Rol, bağ, üyelik, sayfa/işlem/veri alanı yetkisi | Köprü: `semantic_access_roles|role_perms|bindings|members`, `semantic_access_entity_domains` | Var (Aşama A/B/C, `main`) | Veri sahibi alanı ve onay durumu yok |
| AD grup/OU üyeliği | AD (15 dk'lık tazeleme) | `semantic_access_members` | AD grup envanteri okunmadı (yetki analizi §11) |
| CRM güvenlik rolleri | CRM `SystemUserRoles`, `RoleBase` (2.857), `SystemUserBase` (386) | `access.Directory.crm_role_members` okuyor | — |
| Başarılı/başarısız giriş | Giriş servisi (`server.py`) | **Yazılmıyor** | Yeni olay tablosu |
| Açık oturumlar | Giriş servisi SQLite `sessions` (token özeti, kullanıcı, bitiş, ad) | Var, listelenmiyor | Açılış zamanı, adres yok; kapatma ucu yok |
| Yetkisiz erişim (403) | Köprü `page_gate`, `FEATURE_RULES` | Tabloya yazılmıyor | Yeni kayıt |
| Yetki dışı soru | `sl_query_log.answer_type = 'NOT_PERMITTED'` | Var (Aşama C) | — |
| Dışa aktarma | Köprü uçları (pano Excel, rapor dosyası, denetim dışa aktarma, sözleşme Word, çeviri DOCX…) + istemci tarafı CSV | `semantic_audit`'te yalnız birkaçı (ör. `export studio_pdf`) | İstemci tarafı CSV'ler hiç kaydedilmiyor; birleşik kayıt yok |
| Değişiklik kaydı | `semantic_audit` | Var | Saklama süresi yok |
| Soru + SQL + tam sonuç | `sl_query_log` (`question`, `sql_text`, `result_json`, `username`) | Var, süresiz | Saklama/anonimleştirme yok; kişi adları sonuçta kalabilir |
| Kişisel veri sütunları | Katalog `sl_schema_profile.columns_json[].sensitive` + `sensitivity_reason` | Var (otomatik kalıp) | Ad-soyad kalıbı yok; sınıflandırma derecesi yok; toplam sayı **ölçülecek** |
| Bilinen hassas CRM sütunları | CRM: `SystemUser.new_deposifre`, web kullanıcısı şifre/token, `Contact` TC/nüfus, tahsilat vergi no | `crm-timas-mscrm-detay` §121 | Katalogda `sensitive` işaretli olup olmadıkları **ölçülecek** |
| Portal içi kişisel veri kopyaları | `semantic_people_profiles` (dahili, cep, fotoğraf), `semantic_greetings`, yazar kartları/görüşmeler, serbest çalışan kayıtları, sözleşme tarafları, rapor dosyaları (`var/reports`), soru kaydı | Dağınık | Envanter yok |
| CRM denetim kaydı | CRM `AuditBase` (55.021.691 satır) | Katalogda değil (PROJECT-MEMORY «Yazar giriş süreci») | Okunacaksa kapsam kararı |
| Logo kullanıcı/yetki tabloları | Logo sistem tabloları (`data_domains.json` «sistem» alanı: `^L_`, SYSLOG, CHANGELOG…) | Alan kuralı var | Hangi tabloların katalogda olduğu **ölçülecek** |
| KVKK belgeleri (envanter, aydınlatma, VERBİS, ihlal planı) | TİMAŞ hukuk | **Bilinmiyor** | Soru 1 |
| Tehdit istihbaratı, sızma testi sonuçları | Dış / TİMAŞ BT | Yok; müşteride web taraması kapalı | İlk sürüm dışı |

## 7. Diğer modüllerle bağ

- **M48 IT altyapı:** olay tablosu ortak görünüm; yedek doğrulaması M48'de; güvenlik uyarıları M48 olay listesinde de görünür.
- **M47 Risk ve uyum:** KVKK uyum skoru ve açık bulgular M47'nin risk matrisine girdi.
- **M50 Model geliştirme:** modele giden bağlamda kişisel veri olmadığının kanıtı (sensitive sütunlar istemden çıkar) M50 raporunda.
- **M51 Destek:** müşteri talepleri kişisel veri taşır (ad, e-posta, sipariş); saklama süresi ve ilgili kişi talebi araması M51 kayıtlarını da kapsar.
- **Bütün modüller:** her yeni tablo/dosya yazan modül envantere kaydını ekler (kod kuralı, §14).

## 8. Kısıtlar

- CRM'e yazma yok, T-soft'a yazma yok; AD'ye yazma yok (hesap kapatma AD'de BT'nin işi; portal yalnız kendi oturumunu kapatır).
- Demo veri yok; giriş yalnız AD (bellek `no-demo-login`) — güvenlik ekranı da test hesabı açmaz; testte yalnız `timasai` kısa oturumu, iş sonunda silinir (AGENTS.md, 2026-09-28 kuralı).
- Ekranda teknoloji adı yok.
- Sayı tavanı yok: kayıt listeleri sayfalı, tavansız; saklama süresi bir «tavan» değil, kullanıcının verdiği politikadır.
- Kurulum veri silmez; saklama işi yalnız politika onaylıysa ve kanıt yazarak siler (satır sayısı, tablo, tarih aralığı).
- Müşteride web taraması kapalı → dış tehdit istihbaratı çekilmez.
- **KVKK:** portal veri işleyen konumundadır, TİMAŞ veri sorumlusudur (**varsayım**, hukukla teyit). Giriş/erişim kayıtları
  çalışanın kişisel verisidir; çalışanlara aydınlatma gerekir. Kayıt sürelerini hukuk belirler (soru 2); aşırı kayıt da
  risktir (ölçülülük) — bu yüzden her istek değil, yalnız 403, dışa aktarma ve hassas kayıt okuması yazılır.
- Kişi adının kişisel veri kalıbına eklenmesi soru hattını etkileyebilir (maskelenen sütun istemden düşer;
  `sensitivity.py` başındaki açıklama: yanlış pozitif sorguyu bozar). Bu yüzden ad-soyad **maskelenmez**, yalnız envanterde «kişisel
  veri (ad)» diye sınıflanır; soru hattına dokunan her değişiklikten sonra tam set regresyonu (bellek `full-set-regression-after-every-change`).

## 9. Kapsam önerisi

**İlk sürüm**
- Giriş olay kaydı (başarılı/başarısız) + açık oturum listesi + oturum kapatma.
- Erişim kaydı: 403, `NOT_PERMITTED`, sunucu tarafı dışa aktarmalar; istemci tarafı CSV'ler için tek «dışa aktarma bildirimi» ucu.
- Kural tabanlı uyarılar (5 kural, §5) + e-posta.
- Hesap hijyeni raporu (AD kapalı / CRM etkin, uzun süre girmeyen, rolsüz, test adı kalıplı hesaplar).
- «Herkes» daraltma önizlemesi (kimin neyi kaybedeceği).
- Saklama politikası tablosu + gece uygulaması: `sl_query_log.result_json` N gün sonra boşaltılır (soru ve SQL kalır), giriş/erişim kaydı M ay; kanıt satırı.
- Kişisel veri envanteri (katalogdaki `sensitive` sütunlar + portal içi kopyalar listesi, elle bakımlı kayıt defteriyle).

**Sonraki sürüm**
- Veri sahibi ataması ve çeyreklik yetki gözden geçirme kampanyası; rol değişikliğinde sahip onayı.
- Zeki AI sınıflandırma önerisi (gizlilik derecesi) ve belge taslakları (aydınlatma, ihlal planı).
- İhlal kaydı ve 72 saat akışı.
- İlgili kişi talebi araması (ad/e-posta ile portal tablolarında arama; sonuç yalnız KVKK irtibat kişisine).
- CRM denetim kaydından (AuditBase) seçili olay okuması (kapsam kararıyla).

**Mevcut kodda yeniden kullanılacaklar**
- `backend/semantic_bridge/access.py` (`effective`, `explain`, `data_domains`, `domain_listing`, `allowed_domains`, `Directory.list_people`, `crm_role_members`), `access_catalog.json`, `data_domains.json`.
- `backend/semantic_bridge/admin.py` (`audit`, `audit_list`, `users`, `conf`, SMTP gönderimi).
- `scripts/server/portal-login/server.py` (oturum tablosu, AD doğrulama) — olay yazımı buraya eklenir.
- `backend/semantic_layer/profiler/sensitivity.py` (kalıplar, `holds_codes_not_personal_data`).
- `src/canvas/admin/AccessAdmin.tsx`, `AuditLog.tsx`, `PromptTracker.tsx`, `People.tsx`, `ui.tsx`.
- `backend/semantic_bridge/people.py` (CRM ∩ AD ∩ son giriş kuralı — hesap hijyeni aynı kaynaktan).
- `backend/semantic_bridge/alerts.py` bildirim deseni.

## 10. Uzmanlara sorulacak sorular

1. TİMAŞ'ın KVKK envanteri, VERBİS kaydı ve çalışan/müşteri aydınlatma metinleri kimde; portal bunlara nasıl eklenmeli (yeni işleme amacı: «yapay zekâ ile iş analizi»)?
2. Saklama süreleri: soru sonuçları, giriş ve erişim kayıtları, rapor dosyaları kaç gün/ay tutulsun? Hukukun belirlediği bir süre var mı?
3. AD'de departman güvenlik grupları güncel tutuluyor mu; veri alanlarının sahibi kim olmalı (ör. muhasebe = Mali İşler müdürü)?
4. Hesap kilitleme politikası AD'de nasıl (kaç hatalı deneme)? Portalın ayrıca kilitlemesi istenir mi, yoksa yalnız uyarı mı?
5. Sızma testi ya da dış denetim yapıldı mı; sonuç ve düzeltici eylem listesi portala alınsın mı?

## 11. Başarı ölçütü

- Giriş ve erişim kaydı eksiksiz: denetim günü rastgele 20 olayın 20'si kayıtta.
- AD'de kapatılan hesabın portal oturumunun kapanma süresi: bugün ≤ 8 saat → hedef ≤ 15 dk (üyelik tazelemesi) ya da anında (elle).
- Saklama işi: süresi dolmuş `result_json` satırı 0; son 30 gecenin ≥ 29'unda iş başarılı.
- Hesap hijyeni: prod öncesi raporda «açıklanamayan hesap» 0.
- «Herkes» rolü prod günü daraltıldı ve ilk hafta yetki şikâyeti (M51'e düşen «göremiyorum» talebi) sayısı ölçülür.
- Uyarı kalitesi: kapatılan uyarıların «gerçek değil» oranı < %20; kritik uyarının incelenme süresi ≤ 1 iş günü.
- Çeyreklik gözden geçirmeyi tamamlayan veri sahibi oranı ≥ %90.

## 12. Uzman gözüyle en iyi sistem

**Kimin yerine geçiyorum:** 15 yıllık bilgi güvenliği ve KVKK uyum uzmanı; orta ölçekli, çok birimli bir şirkette tek
başına ya da hukukla birlikte çalışıyor. ISO 27001 denetimi ve KVKK Kurulu şikâyeti görmüş.

**Sektörde en iyiler nasıl yapıyor:** (1) kimlik merkezî (AD/SSO), yetki rol tabanlı ve **veri sahibi onaylı**; yetkiler
çeyrekte bir gözden geçirilir (access review), gözden geçirilmeyen yetki otomatik düşer. (2) Denetim izi «kim, ne zaman,
neyi gördü/değiştirdi/indirdi» sorusuna cevap verir, değiştirilemez biçimde saklanır, süresi bellidir. (3) Kişisel veri
envanteri canlıdır: yeni tablo/dosya eklendiğinde envantere kendiliğinden düşer. (4) Uyarılar az ama anlamlıdır (UEBA
yaklaşımı: kişinin kendi normaline göre sapma). (5) İhlal akışı tatbikatı yapılmış bir runbook'tur, 72 saat sayacıyla.
Yayıncılıkta ek hassasiyet: yazar sözleşmeleri, telif tutarları, okur/müşteri verisi, çocuk okur verisi.

**TİMAŞ için mükemmel sistem:** portal kendi güvenlik kanıtını üretir: bir denetçi geldiğinde tek tıkla «yetki matrisi +
son gözden geçirme + erişim kaydı + saklama kanıtı + kişisel veri envanteri» paketi çıkar. Veri sahibi kendi alanının
bekçisidir; BT yalnız mekanizmayı işletir.

**Bir iş günü:**
- 09:00 — Özet: 1 kritik uyarı («Dün 23:40 muhasebe raporu 3 kez Excel'e aktarıldı, mesai dışı»). Kişiye ve rapora tıklar,
  planlı raporun gece otomatik gönderimi olduğunu görür → «gerçek değil: zamanlanmış iş» diye kapatır; kural, zamanlanmış
  gönderimleri ayrı saymayı öğrenir (kural ayarı, model değil).
- 10:30 — İK'dan işten ayrılış e-postası: Hesap hijyeni → kişi → «Oturumlarını kapat»; AD kapatması BT'de.
- 13:00 — Hukuk bir okurun ilgili kişi başvurusunu iletir: ada göre arama → portal kopyalarında 0 kayıt, CRM'de kayıt var
  (kaynak sistem TİMAŞ'ın) → cevap taslağı.
- 15:00 — Çeyrek sonu: gözden geçirme kampanyasını başlatır; veri sahiplerine görev e-postası gider.
- 17:00 — Haftalık uyum göstergesi: saklama işi 7/7, atanmamış tablo 0, «Herkes» hâlâ geniş (kırmızı, prod öncesi iş).

**«Bunu görürsem hemen kullanırım» — 3 özellik**
1. Denetçi paketi: tek tıkla yetki matrisi + gözden geçirme + erişim kaydı + saklama kanıtı.
2. «Bu değişiklikle kim neyi kaybeder/kazanır» önizlemesi.
3. Kişi gözüyle tam iz: bu kişi hangi rolle, neyi gördü, neyi indirdi.

**«Bunu yaparsanız kullanmam» — 3 tuzak**
1. Her isteği kaydetmek: milyonlarca satır, hiçbir şey bulunamaz; ayrıca çalışanın gereksiz izlenmesi (KVKK ölçülülük).
2. Silme işini kanıtsız yapmak ya da geri dönülmez silmeyi onaysız başlatmak.
3. Uyarıyı model «hissiyle» üretmek: gerekçesi olmayan, tekrarlanamayan alarm.

## 13. Zeki AI (yerel model), Logo ve CRM nerede kullanılır

| Adım | Logo (hangi tablo/görünüm/ölçü) | CRM (hangi varlık/alan) | Yerel model (Zeki AI) ne yapar | Neden |
|---|---|---|---|---|
| Hesap hijyeni | — | `SystemUserBase` (`IsDisabled`, `DomainName`, `ActiveDirectoryGuid`) | Hiçbir şey | CRM ∩ AD ∩ son giriş kesişimi deterministik (`people.py` kuralı) |
| CRM rol üyeliği | — | `SystemUserRoles`, `RoleBase` | Hiçbir şey | Bağ türü «CRM rolü» zaten okunuyor |
| Veri alanı ataması | Logo tablo aileleri (`data_domains.json` kuralları) | CRM varlık adları (aynı dosya) | Atanmamış tabloya alan **önerisi**: tablo açıklaması + sütun adlarından kapalı küme seçimi (tek token + olasılık, 10 alan); marj düşükse öneri yok | Kural düşmeyen az sayıda tablo kalıyor; yönetici tek tık onaylar |
| Kişisel veri sınıflandırma | Logo sütun profilleri (`sl_schema_profile`) | CRM sütun profilleri (örn. `Contact` TC/nüfus, web kullanıcısı şifre/token) | Kalıbın yakalamadığı sütunlar için «kişisel veri mi, hangi tür» önerisi (kapalı küme) | Kalıp ad-soyad, serbest metin not gibi alanları kaçırır; karar alan sahibinde |
| Anormallik tespiti | — | — | **Yok** (kurallar + kişinin 30 günlük kendi ortalaması, kodla) | Uyarı tekrarlanabilir ve açıklanabilir olmalı |
| Uyarı açıklaması | — | — | Uyarının olay satırlarından 1–2 cümle açıklama | Okunabilirlik; rakamlar kayıttan |
| Saklama uygulaması | — | — | Hiçbir şey | Silme deterministik ve kanıtlı |
| Belge taslakları (K2) | — | — | Aydınlatma metni, ihlal bildirimi, politika taslağı — envanter ve olay kaydından | Metin üretimi modelin işi; hukuk onaylar |
| İlgili kişi araması | Logo cari kartı (`LG_…_CLCARD` adı/unvanı, yalnız varlık sayısı) | `Contact`/`Account` adı (yalnız eşleşme sayısı, değer göstermeden) | Hiçbir şey | Kaynak sistemdeki kaydı göstermek portalın işi değil; yalnız «nerede var» der |
| Soru kutusu | — | — | Soruyu modülün sabit sorgularından birine eşler (kapalı küme) | Güvenlik verisi üzerinde serbest SQL yok |

Model çağrıları `rt.llm_for("guvenlik", priority=BATCH)` ile LLM kapısından; `LlmClient` doğrudan kurulmaz. Modele
kişisel veri **değeri** gönderilmez: yalnız tablo/sütun adı, açıklama, veri tipi; hassas sütun örneği zaten hiç
okunmuyor (`sensitivity.py`).

## 14. Kodlama planı (kodlayıcıya devir)

**Mevcut sayılanlar (dokunulmaz, üstüne kurulur):** yetki Aşama A (sayfa), B (20+ işlem anahtarı, `FEATURE_RULES`, `_can`),
C (veri alanları `data_domains.json` + `semantic_access_entity_domains`, `veri:<alan>` anahtarları, `Runtime._check_data_scope`,
`DATA_ALLOWED`, `access.acting_as`, `NOT_PERMITTED`); Yönetim → Yetkiler (roller, bağlar, Kişi gözüyle, Veri alanları),
Değişiklik kaydı, Soru izleme; `sensitivity.py`.

**Köprü dosyaları**
- `backend/semantic_bridge/data_security.py` — tablolar, `ensure`, olay yazıcıları (`record_access(user, kind, path, detail)`),
  kural motoru (anormallik), saklama uygulayıcı, hijyen taraması, envanter derleyici.
- `backend/semantic_bridge/data_security_api.py` — `register(app, *, rt, can, audit, conf, directory)`.
- `backend/semantic_bridge/data_security_inventory.json` — portal içi kişisel veri kopyaları defteri (tablo/dosya → tür →
  amaç → saklama anahtarı). Yeni modül yeni kişisel veri yazıyorsa buraya satır ekler; test, `semantic_` tablolarından
  kişisel veri alanı taşıyanların (ad listesiyle) defterde olduğunu denetler.
- `scripts/server/portal-login/server.py` — değişiklik: `login_events` tablosu (SQLite, aynı dosya: `id`, `at`, `username`,
  `ok`, `reason` `bad_password|unknown_domain|directory_down|ok`, `addr` (X-Forwarded-For), `ua_hash`); `sessions`'a
  `created` ve `addr` kolonları; yalnız loopback'ten ve `LOGIN_ADMIN_TOKEN` başlığıyla çalışan `GET /events?after=<id>`,
  `GET /sessions`, `POST /sessions/revoke` (kullanıcı adı ya da token özeti). Parola ve token hiçbir yerde yazılmaz.
- `app.py` `page_gate`: 403 kararında `data_security.record_access(user, "forbidden", path, key)`; dışa aktarma uçlarında
  (`FEATURE_RULES`'ta `ozellik:veri.disa-aktar` eşleşen istekler) `record_access(..., "export", ...)`.

**Tablolar (meta DB)**
- `semantic_security_logins` (id, at, username, ok, reason, addr, ua_hash, src_event_id) — giriş servisinden çekilir.
- `semantic_security_access` (id, at, username, kind `forbidden|not_permitted|export|sensitive_read`, path, perm_key, detail_json).
- `semantic_security_alerts` (id, at, rule, username, severity, summary, evidence_json, state `open|closed`, closed_by, closed_at, verdict `gercek|gercek-degil`, note).
- `semantic_security_retention` (object `query_result|login|access|audit|report_file`, days, approved_by, approved_at) + `semantic_security_retention_runs` (id, at, object, rows_affected, range_from, range_to, ok, error).
- `semantic_security_domain_owners` (tenant_id, domain, owner_subject_type, owner_subject, set_by, set_at).
- `semantic_security_reviews` (id, campaign, domain, subject_type, subject, role_id, owner, decision `devam|kaldir|bekliyor`, decided_at, applied_at).
- `semantic_security_docs` (id, kind `aydinlatma|ihlal-plani|politika|ihlal-kaydi`, version, status `taslak|onayli`, body, drafted_by, approved_by, approved_at).

**Uçlar (`/api/v1/data-security/*`)**
- `GET summary` · `GET alerts` · `PATCH alerts/{id}` (`ozellik:guvenlik.uyari-kapat`)
- `GET logins?user=&ok=&since=` · `GET sessions` · `POST sessions/revoke` (`ozellik:guvenlik.oturum-kapat`)
- `GET access?kind=&user=&since=` · `POST export-notice` (istemci tarafı CSV/PDF bildirimi; OPEN — her oturumlu kişi kendi aktarımını bildirir)
- `GET hygiene` · `GET preview-everyone?perms=` («Herkes» daraltma önizlemesi; yönetici)
- `GET inventory` · `GET retention` · `PUT retention` (`ozellik:guvenlik.saklama`) · `GET retention/runs`
- `GET owners` · `PUT owners/{domain}` (yönetici) · `POST reviews/campaign` (yönetici) · `GET reviews?mine=1` · `PATCH reviews/{id}` (`ozellik:guvenlik.gozden-gecir`, yalnız sahibi olduğu alan)
- `GET docs` · `POST docs/draft` · `PATCH docs/{id}` (`ozellik:guvenlik.ihlal` ya da `.saklama` türüne göre)
- `POST run-due` (SYSTEM: giriş olaylarını çek, kuralları koş, hijyen, saklama)
- `access.py` `RULES`: `("/api/v1/data-security/run-due", SYSTEM)`, `("/api/v1/data-security/export-notice", OPEN)`,
  `("/api/v1/data-security/", frozenset({page("veri-guvenligi")}))`; `FEATURE_RULES` yukarıdaki işlem anahtarları.

**Ekranlar**
- `src/canvas/data-security/DataSecurityScreen.tsx` (sekmeler §5), `AlertsTab.tsx`, `LoginsTab.tsx`, `HygieneTab.tsx`,
  `InventoryTab.tsx`, `RetentionTab.tsx`, `ReviewsTab.tsx`, `DocsTab.tsx`. Rota `/timas/veri-guvenligi`.
- Menü: M48 ile açılan `altyapi` çalışma alanında `{ id: 'veri-guvenligi', label: 'Veri güvenliği' }`.
- Yönetim → Yetkiler «Kişi gözüyle» paneline «Girişleri ve erişim kaydı» bağlantısı; rol düzenleyicide «Herkes»
  değişikliğinde önizleme penceresi.
- İstemci tarafı dışa aktaran bileşenler (Baskı öneri CSV, rehber CSV, SEO CSV, pano PDF) aktarımdan önce `export-notice` çağırır (hata aktarımı durdurmaz).
- Kampüs: `ModulesMenu.LIVE.M49 = '/veri-guvenligi'`.
- `access_catalog.json`: `sayfa:veri-guvenligi`; `ozellik:guvenlik.uyari-kapat`; açıkça verilen: `ozellik:guvenlik.oturum-kapat`, `ozellik:guvenlik.saklama`, `ozellik:guvenlik.ihlal`; `ozellik:guvenlik.gozden-gecir` (açıkça verilir, satır erişimi sahipliğe bağlı).

**Zamanlayıcı:** `timas-security.timer` her 5 dk `run-due` (giriş olayı çekme + kurallar); saklama ve hijyen aynı işin
içinde günde bir (03:40; gece taraması ve CRM bağlayıcısından sonra). VM'de `jobs.py` `JOBS`'a eklenir. İlk koşu elle.

**Kabul testleri**
1. Giriş kaydı: `timasai` ile bir yanlış parola + bir doğru giriş (kısa oturum, sonra silinir) → `semantic_security_logins`'te iki satır, `ok` false/true; giriş servisinin SQLite'ında `SELECT count(*) FROM login_events WHERE username='timasai' AND at > <test başı>` = 2.
2. 403 kaydı: yetkisi olmayan deneme oturumuyla `GET /api/v1/financial-audit/overview` → 403 ve `semantic_security_access`'te `kind='forbidden'`, `perm_key='sayfa:finansal-denetim'` satırı.
3. Envanter: meta DB `SELECT count(*) FROM sl_schema_profile p, jsonb_array_elements(p.columns_json::jsonb) c WHERE (c->>'sensitive')::boolean` = Envanter sekmesindeki «kaynakta kişisel veri sütunu» sayısı; CRM `Contact` TC sütunu listede ve `sensitive=true` (değilse bulgu olarak raporlanır, düzeltme `SEMANTIC_PII_PATTERNS` ile).
4. Hijyen: CRM (.28, doğrudan) `SELECT count(*) FROM Timas_MSCRM.dbo.SystemUserBase WHERE IsDisabled = 0 AND DomainName LIKE 'timas\%'` ile AD etkin kişi listesinin farkı = Hesap hijyeni «CRM'de etkin, AD'de kapalı» sayısı.
5. Saklama: politika `query_result=N` onaylıyken gece işinden sonra `SELECT count(*) FROM sl_query_log WHERE created_at < now() - interval 'N days' AND result_json IS NOT NULL` = 0 ve `semantic_security_retention_runs` son satırında `rows_affected` = işten önce aynı sorgunun verdiği sayı (`created_at` kolonu ve `ix_sl_query_log_recent` dizini şemada var).
6. «Herkes» önizlemesi: «Herkes»ten `sayfa:finansal-denetim` çıkarılırsa önizlemedeki «kaybeden kişi» sayısı = yalnız «Herkes»ten bu sayfayı alan etkin kişi sayısı (`access.explain` ile kişi kişi hesap, birim testi + gerçek AD görüntüsü).
7. Soru hattı etkilenmedi: değişiklik sonrası `tests/text2sql/resolver-gate.py` ve tam set regresyonu (`scripts/testset_regress.py`) bozulan 0.
8. Ekran metni taraması: teknoloji adı yok; hiçbir uç parola/token/TC değeri döndürmüyor (yanıt gövdelerinde 11 haneli sayı ve `@` içeren alan taraması).

**Bağımlılık:** Aşama A/B/C (var). M48'in bildirim/olay deseniyle aynı tarz; paralel kodlanabilir. Giriş servisi
değişikliği sunucuda sudo ister (kurulumu kullanıcı çalıştırır, bellek `zeki-chat-sso-paused` deseni).

**Tahmini büyüklük:** İlk sürüm **L** (3 gün: giriş servisi + köprü kayıt + kurallar + hijyen + saklama + envanter + ekran).
Gözden geçirme kampanyası ve belge taslakları **M**.
