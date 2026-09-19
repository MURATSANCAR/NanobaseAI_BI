# CRM'de kullanıcılar hakkında tutulan bilgiler

Tarih: 2026-09-14. Kaynak: `Timas_MSCRM` (192.168.0.155), köprü kataloğu + canlı sayım sorguları.
Veri 2026-09-08 18:08'de donmuş görünüyor (bkz. günlük); sayılar o güne ait.
Kişisel değer (ad, telefon, e-posta, şifre) okunmadı ve bu belgeye yazılmadı; yalnız alan adları ve sayılar var.

## Bağlantı: AD kullanıcısı ↔ CRM kullanıcısı

- CRM kullanıcı tablosu: `SystemUserBase` — **386 kayıt**, 186 etkin, 200 devre dışı.
- AD ile eşleşme anahtarı: `DomainName` (`TIMAS\hesapadı`); ayrıca `ActiveDirectoryGuid` (AD `objectGUID`).
- AD tarafı: 213 etkin kişi. **Eşleşme sayısı henüz çıkarılmadı** — AD listesi ile CRM listesini
  karşılaştıran sorgu izin denetimine takıldı.

## 1. Kullanıcı kaydının kendisi (`SystemUserBase`, 96 kolon)

### Kimlik ve iletişim
| Kolon | Anlamı |
|---|---|
| `FirstName`, `MiddleName`, `LastName`, `FullName`, `NickName`, `Salutation` | Ad, ikinci ad, soyad, tam ad, takma ad, hitap |
| `YomiFirstName`, `YomiMiddleName`, `YomiLastName`, `YomiFullName` | Japonca okunuş (kullanılmıyor olmalı) |
| `Title`, `JobTitle` | Unvan, iş unvanı |
| `InternalEMailAddress` | Birincil (şirket) e-posta |
| `PersonalEMailAddress` | Kişisel e-posta |
| `MobileAlertEMail` | Mobil uyarı e-postası |
| `HomePhone`, `MobilePhone` | Ev ve cep telefonu |
| `PreferredEmailCode`, `PreferredPhoneCode`, `PreferredAddressCode` | Tercih edilen iletişim kanalı |
| `PhotoUrl`, `EntityImageId` | Fotoğraf |
| `EmployeeId` | Çalışan (sicil) numarası |
| `GovernmentId` | Resmi kimlik numarası (**hassas**) |
| `Skills` | Beceriler |

### Hesap, lisans, durum
| Kolon | Anlamı | Dağılım (386 kayıt) |
|---|---|---|
| `DomainName` | AD kullanıcı adı | — |
| `ActiveDirectoryGuid`, `AzureActiveDirectoryObjectId`, `WindowsLiveID` | Dizin kimlikleri | — |
| `IsDisabled`, `DisabledReason` | Etkin mi, neden kapatıldı | etkin 186 · kapalı 200 |
| `AccessMode` | Erişim türü | 0 okuma-yazma 385 · 2 yalnız okuma 1 |
| `CALType`, `UserLicenseType`, `IsLicensed` | Lisans türü | 0 (Professional) 378 · 5 7 · 2 1 |
| `IsIntegrationUser` | Entegrasyon hesabı | hepsi hayır |
| `IsActiveDirectoryUser`, `IsSyncWithDirectory`, `SetupUser` | AD kullanıcısı, dizinle eşitleme, kurulum kullanıcısı | — |
| `InviteStatusCode` | Davet durumu | — |
| `CreatedOn`, `CreatedBy`, `ModifiedOn`, `ModifiedBy`, `CreatedOnBehalfBy`, `ModifiedOnBehalfBy`, `OverriddenCreatedOn` | Kaydı kim ne zaman açtı/değiştirdi | — |

### Organizasyondaki yeri
| Kolon | Anlamı |
|---|---|
| `BusinessUnitId` | Departman (`BusinessUnitBase`, 25 departman) |
| `ParentSystemUserId` | Yöneticisi (başka bir CRM kullanıcısı) |
| `TerritoryId` | Satış bölgesi (`TerritoryBase`, 2 bölge) |
| `PositionId` | Hiyerarşik güvenlik pozisyonu |
| `SiteId` | Konum |
| `OrganizationId` | Kuruluş |
| `QueueId`, `DefaultMailbox`, `CalendarId` | Varsayılan kuyruk, posta kutusu, takvim |
| `TransactionCurrencyId`, `ExchangeRate` | Para birimi |

### E-posta ve entegrasyon ayarları
`IncomingEmailDeliveryMethod`, `OutgoingEmailDeliveryMethod`, `EmailRouterAccessApproval`,
`IsEmailAddressApprovedByO365Admin`, `YammerEmailAddress`, `YammerUserId`, `SharePointEmailAddress`,
`DefaultOdbFolderName`, `MobileOfflineProfileId`, `ApplicationId`, `ApplicationIdUri`,
`DefaultFiltersPopulated`, `DisplayInServiceViews`.

### Sistem içi (iş anlamı yok)
`SystemUserId`, `VersionNumber`, `PassportLo`, `PassportHi`, `ImportSequenceNumber`,
`UTCConversionTimeZoneCode`, `TimeZoneRuleVersionNumber`, `ProcessId`, `StageId`, `TraversedPath`,
`obs_managedfromdistributionmanager`.

### TİMAŞ'a özel alanlar
| Kolon | Anlamı | Dağılım |
|---|---|---|
| `new_KullancKoduLogoyaGnderilen` | Logo'ya gönderilen kullanıcı kodu — **Logo ile köprü** | — |
| `new_maxriskyuzdesi` | Onaylayabileceği azami risk (%) | — |
| `new_varsayilanfiyatlistesiid` | Varsayılan fiyat listesi | — |
| `new_varsayilandepoid` | Varsayılan depo | — |
| `new_defaultkoliid` | Varsayılan koli | — |
| `new_barkodyazici`, `new_normalyazici` | Barkod ve normal yazıcı | — |
| `new_toplayici` | Depo toplayıcısı mı | evet 12 · hayır 137 · boş 237 |
| `new_bmt` | BMT | evet 23 · hayır 96 · boş 267 |
| `new_KurumTemsilcisi` | Kurum temsilcisi (seçenek) | 2: 8 · 1: 1 · 3: 1 · boş 376 |
| `new_gorevbirimi` | Görev birimi (seçenek) | 2: 1 · boş 385 |
| `new_KullancTipi` | Kullanıcı tipi | hepsi boş |
| `new_depokullaniciadi` | Depo sistemi kullanıcı adı | — |
| `new_deposifre` | **Depo sistemi şifresi — düz metin kolon** | — |

> **Güvenlik bulgusu:** `new_deposifre` şifreyi CRM veritabanında açık metin olarak tutuyor. Değer
> okunmadı. Bu kolon katalogda hassas olarak işaretlenmeli, sorgulara hiç açılmamalı; TİMAŞ BT'ye bildirilmeli.

## 2. Kullanıcıya bağlı iş kayıtları

Kataloğa göre **538 CRM tablosu** kullanıcıya standart alanlarla bağlanıyor:
`OwnerId` (sahibi), `CreatedBy` (oluşturan), `ModifiedBy` (değiştiren), `CreatedOnBehalfBy`, `ModifiedOnBehalfBy`.
Yani her kullanıcı için "sahip olduğu / açtığı / değiştirdiği kayıtlar" çıkarılabilir. En büyükleri:

| Tablo | Satır | Sahip (`OwnerId`) var mı |
|---|---|---|
| `new_siparissatiriBase` (sipariş satırı) | 9.745.521 | yok, yalnız oluşturan/değiştiren |
| `new_serilothareketsatiriBase` | 9.056.897 | var |
| `new_malzemehareketsatiriBase` | 8.382.298 | var |
| `new_sevkiyatsatiriBase` | 6.451.786 | var |
| `new_bekleyenurunBase` (bekleyen ürün) | 772.616 | var |
| `new_malzemehareketiBase` | 395.052 | var |
| `new_satishedefleriBase` (satış hedefi) | 334.982 | yok |
| `new_siparisBase` (sipariş) | 333.063 | var |
| `new_sevkiyatBase` (sevkiyat) | 286.601 | var |
| `new_ziyaretyerleriBase` (ziyaret yeri) | 68.713 | var |
| `ContactBase` (kişi) | 59.637 | var |
| `new_etkinlikBase` (etkinlik) | 57.013 | var |
| `AccountBase` (firma) | 47.550 | var |
| `new_eserkatilimBase` | 36.330 | var |
| `new_sozlesmeBase` (sözleşme) | 14.766 | var |
| `new_tahsilatBase` (tahsilat) | 14.089 | var |
| `new_kitapBase` (kitap) | 13.598 | var |
| `new_butcekalemiBase` (bütçe kalemi) | 10.042 | var |
| `new_plansorumlulariBase` | 9.766 | var |
| `new_projeBase` (proje) | 6.598 | var |

## 3. Kullanıcıya iş rolüyle bağlanan özel alanlar (15 tablo)

Standart sahip/oluşturan dışında, TİMAŞ'ın eklediği "bu işi kim yaptı / onayladı" alanları:

| Tablo | Alan |
|---|---|
| `new_siparisBase` | Risk limiti onaylayan · Risk limiti reddeden · Siparişi birleştiren |
| `new_tahsilatBase` | Onaylayan · Reddeden |
| `AccountBase` | İzin veren kullanıcı · Vade iskonto onaylayan |
| `ContactBase` | Nüfus cüzdanı sahibi · Muhasebe onayı veren |
| `new_sozlesmeBase` | Sözleşmeyi kilitleyen · Sözleşmeyi açan |
| `new_projeBase` | Yayın kurulu onay yetkilisi · Pazarlama sorumlusu |
| `BusinessUnitBase` | Editoryal direktör · Departman yöneticisi |
| `new_bekleyenurunBase` | İptal eden |
| `new_kitapgecmisiBase` | Değiştiren |
| `new_hediyetalebiBase` | Onay veren · İptal eden |
| `new_stoksayimiBase` | Kullanıcı |
| `new_onlinesiparisBase` | Kullanıcı |
| `new_reklamplaniBase` | Gerçekleşen teslim tarihini giren kullanıcı |
| `new_sablonplansorumlulariBase` | Birincil yetkili |
| `new_demirbaslarBase` | Demirbaş (zimmet) |

## 4. Katalogda olmayan ama CRM'de bulunan kullanıcı tabloları

Bunlar köprünün güvenlik kuralı yüzünden şu an sorgulanamıyor (katalogda değil):
`BusinessUnitBase` (25 departman, sözlükte var), `TeamBase` (takımlar), `RoleBase` (2.857 güvenlik rolü kaydı),
`SystemUserRolesBase` (kullanıcı ↔ rol), `TeamMembershipBase` (kullanıcı ↔ takım), `RolePrivilegesBase`,
`PrivilegeBase`, `PositionBase`, `UserSettingsBase`, `PrincipalObjectAccess` (paylaşımlar).
Kullanıcının **departmanı adıyla, rolleri ve takımları** için bu tabloların kataloğa alınması gerekir.

## 5. AD ↔ CRM karşılaştırması (canlı, yalnız sayılar)

| | Sayı |
|---|---|
| AD kişi / etkin | 320 / 213 |
| CRM kullanıcı / etkin | 386 / 186 (`DomainName` dolu 373) |
| **AD etkin ve CRM etkin — panelde CRM bilgisi gösterilebilir** | **148** |
| AD etkin, CRM kaydı hiç yok | 58 |
| AD etkin, CRM kaydı kapalı | 7 |
| CRM etkin, AD hesabı kapalı | 33 (CRM'de kapatılmamış ayrılanlar) |
| CRM etkin, AD'de hiç yok | 4 |

AD'de etkin kişilerde gerçekten dolu: ad soyad 212, soyad 184, e-posta 144, son oturum 191, grup üyeliği 192.
**Boş:** departman, unvan, şirket, yönetici, telefon, ofis, sicil, fotoğraf (hepsi 0).

## 6. Gerçekten dolu CRM alanları (186 etkin kullanıcı)

| Alan | Etkinlerde dolu |
|---|---|
| Ad, soyad, tam ad, AD kullanıcı adı, departman (`BusinessUnitId`), posta kutusu, para birimi | 186 (%100) |
| Şirket e-postası | 169 (%91) |
| Toplayıcı mı (`new_toplayici`) | 129 (%69) |
| BMT (`new_bmt`) | 112 (%60) |
| Varsayılan depo · varsayılan fiyat listesi | 39 (%21) — yalnız 2 farklı değer |
| Logo'ya gönderilen kullanıcı kodu | 21 (%11) |
| Kurum temsilcisi | 10 |
| Konum 5 · fotoğraf 4 · yazıcılar 4 · max risk % 3 · cep telefonu 2 · unvan 1 · yönetici 1 | ≈ boş |
| İş unvanı, ev telefonu, kişisel e-posta, sicil no, beceriler, bölge, pozisyon | 0 |

Departman: etkinler 10 farklı departmana dağılıyor (adları `BusinessUnitBase`'te, katalogda yok).

## 7. Etkin kullanıcıların iş kayıtlarıyla bağı

| Kayıt | Kayıtlı kullanıcı (tüm zaman) | Kayıt | 2026'da kullanıcı | 2026 kayıt |
|---|---|---|---|---|
| Sipariş sahibi | 37 | 236.444 | 23 | 23.000 |
| Tahsilat sahibi | 23 | 9.470 | 9 | 898 |
| Tahsilat onaylayan | 3 | 3.730 | 1 | 586 |
| Firma sahibi | 64 | 44.249 | 27 | 1.526 |
| Kişi sahibi | 45 | 55.222 | 13 | 390 |
| Etkinlik sahibi | 28 | 46.814 | 20 | 7.045 |
| Sözleşme sahibi | 38 | 10.531 | 32 | 1.506 |
| Proje sahibi | 60 | 5.677 | 42 | 513 |
| Bekleyen ürün sahibi | 29 | 402.694 | 18 | 23.627 |
| Sevkiyat sahibi | 3 | 286.601 | 1 | 27.724 (tek toplu hesap) |
| Ziyaret yeri sahibi | 1 | 68.713 | 0 | 0 (tek toplu hesap) |
| Bütçe kalemi sahibi | 0 | 0 | 0 | 0 |

## Açık kalanlar

1. Departman, güvenlik rolü ve takım adları — `BusinessUnitBase`, `SystemUserRolesBase`, `RoleBase`,
   `TeamMembershipBase` kataloğa alınmalı.
