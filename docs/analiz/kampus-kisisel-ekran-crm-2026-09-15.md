# Kampüs (giriş sonrası) ekranı: kart → kaynak eşlemesi (2026-09-15)

Kaynaklar: `src/canvas/kampus/KampusPage.tsx` (14 blok), `/opt/timas-login/server.py` (AD: yalnız
`sAMAccountName` + `displayName`), semantic katalog `/api/v1/schema/inventory` (Timas_MSCRM.dbo: 753 tablo),
`backend/semantic_bridge/prefs.py` (`semantic_user_prefs`, `/api/v1/me/prefs/{key}`).

## Köprü: AD hesabı → CRM kullanıcısı
`SystemUserBase.DomainName` = `timas\<hesap>` → `SystemUserId`. Bu satırdan: FullName, Title, JobTitle,
InternalEMailAddress, MobilePhone, HomePhone, PhotoUrl, BusinessUnitId, ParentSystemUserId (yönetici),
TerritoryId (bölge), IsDisabled, CalendarId, EmployeeId. 386 satır (aktif+pasif).
Kişiye ait kayıtlar: `OwnerId` / `CreatedBy` / `new_Editoru` / `new_yayinyonetmeni` / `systemuserid` = SystemUserId.

## Katalogda OLMAYAN CRM tabloları (taramaya eklenmeli)
BusinessUnitBase (departman adı), TeamBase/TeamMembership, ActivityPointer/Appointment/Task/PhoneCall/Email,
AnnotationBase (ek dosyalar; kapak görseli), QueueItem, CalendarBase.

## Kart → kaynak
| # | Kart (bugün) | Kaynak | Ne gelir |
|---|---|---|---|
| 1 | Üst şerit kişi (ad, "Kat 4 • Edebiyat Dizisi", foto) | AD + SystemUserBase | displayName (var). Title/JobTitle + BusinessUnit → alt satır. PhotoUrl → avatar |
| 2 | Bildirim zili | köprü alerts/reports | tetikte uyarı + başarısız rapor sayısı (motor verisi, CRM değil) |
| 3 | Sesli Bülten #42 | yok | kaldır |
| 4 | Şirket Nabzı: "180 Aktif", mod, günün sözü | SystemUserBase (IsDisabled=0, DomainName timas\) + prefs `kampus:mood` | aktif kullanıcı sayısı; mod kişisel tercih; %89 = tüm kullanıcıların modlarının oranı; söz kaldır |
| 5 | Hızlı Operasyon & Destek (BT, kurye, telif) | new_talepyonetimiBase (CreatedBy=ben: talep türü, destek tipi, öncelik, planlanan bitiş), new_sozlesmeBase (OwnerId=ben: bitiş tarihi yaklaşan) | "açık taleplerim", ortalama yanıt = tamamlanma-oluşturma; kurye satırı için CRM'de kişiye bağlı kaynak yok → kaldır |
| 6 | Kampüs Odaları & Stüdyo | yok | kaldır ya da prefs ile basit rezervasyon (paylaşımlı olduğu için yeni tablo gerekir) |
| 7 | Kahve & Çekiliş | yok | kaldır |
| 8 | ZEKİ sahnesi (Selam {ad}, öneri çipleri) | AD + SystemUser.Title | ad var; çipler unvana göre (editör: "kitaplarım", satış: "hedefim", üretim: "bu ay baskılar") |
| 9 | Modüller | modules.json | zaten gerçek |
| 10 | Rehber (6 kişi, kat süzgeci, dahili) | SystemUserBase (386) | FullName, JobTitle, InternalEMailAddress, MobilePhone, PhotoUrl, yönetici; süzgeç kat→departman (BusinessUnit). Dahili/masa CRM'de yok → prefs `kampus:masa` (kişi kendi girer) veya AD physicalDeliveryOfficeName |
| 11 | Alkış duvarı | yeni tablo `semantic_kampus_posts` | prefs kişiye özel; alkış paylaşımlı. Yıl dönümü için CRM'de işe giriş tarihi yok (SystemUser.CreatedOn zayıf vekil) |
| 12 | Podcast | yok | kaldır |
| 13 | Ajanda (22 Nisan, TÜYAP 18 gün) | new_yayinkurulutoplantilariBase (toplantı tarihi, new_Editoru=ben), new_etkinlikBase (BaşlangıçTarihi, OwnerId=ben; fuar tipi → geri sayım), new_isplaniBase (tahmini bitiş; plansorumlulari OwnerId=ben), new_sozlesme bitiş | kişinin önümüzdeki 30 günü |
| 14 | Bugün Doğanlar | yok (SystemUser'da doğum günü yok; ContactBase.BirthDate dış kişiler) | kaldır ya da prefs `kampus:dogumgunu` (kişi kendi girer) |
| 15 | Matbaadan Yeni Çıkanlar ("6 yeni baskı") | new_UretimBase (UretimTarihi son 30 gün, UretimAdedi, UretimTipi) + new_kitapBase | son üretimler; "benim kitaplarım" = new_yayinyonetmeni=ben; kapak görseli için AnnotationBase gerekli (katalogda yok) |
| 16 | Yemekhane | yok | kaldır |

## Kişiye özel yeni kartlar (CRM'den doğrudan)
- İş planlarım: new_plansorumlulariBase (OwnerId=ben) → toplam/tamamlanan iş adedi, saat; new_isplaniBase gecikme günü, tamamlanma %.
- Projelerim: new_projeBase (OwnerId=ben) → durum, tamamlanma %, metin teslim tarihi.
- Kitaplarım: new_kitapBase (new_yayinyonetmeni=ben) → yayıncılık statüsü.
- Kapak oylamalarım: new_new_kapakalternatifi_systemuserBase (35 bin) + new_kapaksecimiBase (oy, yorum).
- Kampanyalarım / depo yetkim: new_new_kampanya_systemuserBase, new_systemuser_new_depoBase.
- Satış hedefim: new_satishedefleriBase bölge ↔ SystemUser.TerritoryId (eşleme doğrulanmalı).

## Saklama (mevcut yapı)
`semantic_user_prefs` (tenant, datasource, username, key, JSON). Önerilen anahtarlar:
`kampus:profil` (CRM özeti önbelleği, refreshedAt), `kampus:mood`, `kampus:masa`, `kampus:dogumgunu`, `kampus:duzen`.
Paylaşımlı içerik (alkış, oda) prefs'e sığmaz → yeni küçük tablo.

## Doğrulanmadı
CRM'e doğrudan sorgu bu oturumda çalıştırılamadı; tablo/sütun bilgisi katalogdan (değerler değil, şekil).
AD'den ek öznitelik (mail, title, department, thumbnailPhoto, manager) çekilebilir mi denenmedi; server.py'de attributes listesi genişletilmeli.
