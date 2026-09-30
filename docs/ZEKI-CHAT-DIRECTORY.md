# ZEKI AI CHAT: AD rehberi ve CRM ekipleri

2026-09-30 kullanıcı talebi: bütün etkin AD hesapları sohbet aramasında görünsün; CRM ekiplerinden varsayılan sohbet grupları oluşsun.

## Çalışan yapı

`deploy/zeki/sync-directory.py` portal sunucusunda çalışır. AD ve CRM yalnız okunur; yazma yalnız `127.0.0.1` üzerindeki sohbet API'sine ve eşitlemenin kendi durum dosyasınadır. Sohbet konteynerinin dış ağ engeli açılmaz. `zeki-directory-sync.timer`, başarılı ilk elle çalıştırma sonrasında açılmıştır; son koşunun bitiminden 15 dakika sonra (en çok 30 sn gecikmeyle) tekrar çalışır.

- Kaynak hesaplar: AD `objectCategory=person`, `objectClass=user`, devre dışı biti kapalı. Kullanıcının tercihi gereği etkin servis hesapları da kapsamda; CRM'de kaydı olmasa da sohbet rehberine alınır.
- Yeni sohbet hesabı sıradan `user` rolündedir. AD/CRM yöneticilik yetkisi aktarılmaz. Karşılama e-postası gönderilmez; rastgele parola kullanıcıya verilmez. Giriş portalın mevcut AD oturumu üzerinden yapılır.
- `administrator` gibi ayrılmış adlar `ad-administrator` biçiminde; Türkçe harf/özel karakter nedeniyle kabul edilmeyen kullanıcı adları sabit bir teknik adla eşlenir. Portal SSO ve aktarım aynı `chat_account_name` işlevini kullanır. Ekranda AD'deki görünen ad kullanılır. Eşleme çakışırsa işlem durur; başka bir hesabın kimliği devralınmaz.
- CRM ekipleri `TeamBase` + `TeamMembership`; iş birimi `BusinessUnitBase.IsDisabled=0`, kullanıcı `SystemUserBase.IsDisabled=0`, `AccessMode IN (0,1)`. Kişi önce `ActiveDirectoryGuid = objectGUID` ile eşleşir; CRM GUID'i boşsa hesap adı kullanılır. Dolu fakat eşleşmeyen GUID, ad benzerliğiyle zorla bağlanmaz.
- Etkin AD üyesi bulunan CRM ekipleri **özel sohbet grubu** olur. Üyelik CRM'den yönetilir; bu yönetilen gruplara elle eklenen fazladan üyeler sonraki eşitlemede çıkarılır. Sohbet servis yöneticisi grubun sahibi olarak kalır. Diğer elle açılmış gruplara dokunulmaz.
- CRM ekip kimliği odadaki `zekiCrmTeamId` alanında saklanır. Ad değişince aynı grup yeniden adlandırılır; yeni grup/mesaj geçmişi oluşturulmaz. Boşalan grup silinmez; geçmişi korunur, eski ekip üyeleri çıkarılır.
- Yalnız bu eşitlemenin oluşturduğu hesaplar AD'den kaldırıldığında/devre dışı olduğunda kapatılır. Önceden var olan yerel hesaplar ve servis yöneticisi kapatılmaz. Bir hesabı yönetici ayrıca kapattıysa eşitleme keyfi olarak açmaz; yalnız kendisinin kapattığını yeniden açar.

## Kurulum ve işletim

Kaynak `main`; çalıştırılabilir kopya `/opt/timas-login/sync-directory.py`, portal `/opt/timas-login/server.py`. Servis/timer kaynakları `deploy/zeki/zeki-directory-sync.{service,timer}`. Python ortamı `/data/nanobaseai/bi/semantic-venv`; `PYTHONPATH=/data/nanobaseai/bi/frontend/backend`. CRM bağlantı dosyası ve AD/sohbet sırları mevcut kurulumdan okunur, Git'e yazılmaz.

Durum `/var/lib/zeki-directory-sync/state.json`, son sonuç `last-run.json`; dizin 0700, dosyalar 0600. Kilit aynı anda iki eşitlemeyi engeller. AD sayfalaması veya CRM okuması eksik/hatalıysa yazma başlamaz. API hatası koşuyu başarısız bitirir; başarılı işlemler atomik ara kayıtla saklanır, tekrar koşu kaldığı yerden ilerler. İlk aktarım öncesi Mongo yedeği test sunucusunda özel izinle alındı.

Compose, `UI_Allow_room_names_with_special_chars=true` ve `UI_Use_Real_Name=true` değerlerini uygular. Böylece Türkçe ekip adları ve AD görünen adları korunur. Korumalı ayarların REST uçlarında 2FA gereksinimi kaldırılmadı.

Yazmasız önizleme:

```bash
sudo env PYTHONPATH=/data/nanobaseai/bi/frontend/backend \
  /data/nanobaseai/bi/semantic-venv/bin/python /opt/timas-login/sync-directory.py
```

Ürün eşitlemesini çalıştırma ve durum:

```bash
sudo systemctl start zeki-directory-sync.service
systemctl status zeki-directory-sync.service
systemctl list-timers zeki-directory-sync.timer
```

## Gerçek kaynak kabulü

216 etkin AD hesabının tamamı sohbette: 215 hesap oluşturuldu, mevcut AD hesabı korundu. Kurulum yöneticisi ve botla toplam 218 sohbet hesabı vardır. Yeni hesapların tamamı yalnız `user` rolünde.

25 etkin CRM ekibinden 12'sinin etkin AD üyesi vardır. Bir CRM üyeliği etkin AD kimliğiyle eşleşmedi, eklenmedi. 13 boş ekip için grup oluşturulmadı. CRM'deki yazım aynen korunur; `Tüm Kullanılar` ve `Teelif Satış` kaynak adlarıdır.

| Grup | Etkin CRM–AD üyesi |
|---|---:|
| Timaş CRM | 105 |
| Tüm Kullanılar | 18 |
| Satış | 17 |
| Editörya | 13 |
| Mali İşler | 3 |
| Pazarlama | 2 |
| Üretim | 2 |
| Lojistik | 2 |
| İdari İşler | 1 |
| Bilgiişlem | 1 |
| Telif Satış Ekibi | 1 |
| Teelif Satış | 1 |

Her grupta bunlara ek olarak mevcut sohbet servis yöneticisi sahip olarak bulunur. `scripts/acceptance/zeki-directory/verify.py`, bağımsız LDAP etkinlik filtresi + doğrudan CRM JOIN sonucunu gerçek sohbet API'si ve Mongo abonelikleriyle karşılaştırdı; 12/12 eşleşti. İkinci eşitleme: 0 yeni hesap, 0 grup, 0 davet/çıkarma; çoğaltma yok.

Son dağıtımda görünen AD adıyla gerçek kişi araması 320/390/768/1440 px genişliklerinde geçti; taşma, JavaScript hatası ve dış HTTP isteği yok. Üç konteyner/ağ denetimi geçti. Toplam 3 kısa portal oturumu ve 9 sohbet jetonu temizlendi (ilk arama seçicisi denemesi dahil); kalan test jetonu ve geçici sır dosyası yok. Beş kurulum dosyasının SHA-256 değeri main ile eşleşti. Kanıtlar: `apps/zeki-chat/docs/evidence/2026-09-30-directory/`. Yeni kullanıcılar/gruplar test verisi değildir: kullanıcı tarafından istenen gerçek şirket rehberi ve ekipleridir, silinmez. Doğrulama için yalnız mevcut `timasai` hesabının kısa oturumları kullanılır ve temizlenir. Gerçek bir çalışanın parolası kullanılmadı; AD kaynaklarında kullanıcı/üyelik değiştirerek ayrılma veya yeniden katılma senaryosu denenmedi. Yerel test ve müşteri VM kurulumu yapılmadı.
