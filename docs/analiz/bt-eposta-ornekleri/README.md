# Bilgi İşlem e-posta örnekleri

Bu klasörü `scripts/acceptance/bt-eposta/ornekleri_uret.py` doldurur (örnek satırlardan, gerçek veri değil; veritabanına
ve posta sunucusuna gitmez). Mac'te koşturulmadı (yerelde yalnız derleme denetimi); sunucuda bir kez:

    cd <kaynak>/backend && python3 ../scripts/acceptance/bt-eposta/ornekleri_uret.py

Betik her bildirim için `.html` (e-posta istemcisindeki görünüm) ve `.txt` (düz metin karşılığı) yazar ve bu dosyayı
konu satırları tablosuyla yeniden üretir. Beklenen dosyalar:

| Dosya | Alıcı ayarı | Konu satırı |
| --- | --- | --- |
| `1a-kesinti-logo.html` | `ITOPS_RECIPIENTS` | [Kesinti] Logo bağlantısı 09:42'den beri yanıt vermiyor |
| `1b-duzeldi-logo.html` | `ITOPS_RECIPIENTS` | [Düzeldi] Logo bağlantısı 10:27'de geri geldi · 45 dk sürdü |
| `1c-uyari-logo-verisi-eski.html` | `ITOPS_RECIPIENTS` | [Uyarı] Logo verisi 17 Ağustos'tan beri güncellenmiyor |
| `2-haftalik-sistem-sagligi.html` | `ITOPS_WEEKLY_TO` | [Haftalık] Sistem sağlığı · 22–28 Eylül |
| `3a-guvenlik-uyarisi.html` | `SECURITY_ALERT_RECIPIENTS` | [Güvenlik] Art arda hatalı giriş · «ahmet.yilmaz» hesabı · 29 Eylül 09:40 |
| `3b-guvenlik-gunluk-ozet.html` | `SECURITY_ALERT_RECIPIENTS` | [Günlük] Portal erişim özeti · 3 kişi · 29 Eylül |
| `4a-kesinti-eposta-kutusu.html` | `MAIL_CONNECTION_ALERT_TO` | [Kesinti] Kurumsal e-posta kutusu 09:12'den beri okunamıyor |
| `4b-duzeldi-eposta-kutusu.html` | `MAIL_CONNECTION_ALERT_TO` | [Düzeldi] Kurumsal e-posta kutusu 11:17'de yeniden okundu · 2 sa 5 dk sürdü |
| `5-crm-departmansiz-kullanicilar.html` | `CRM_UNASSIGNED_TO` | [Bilgi] CRM'de departmanı olmayan 4 kullanıcı · 29 Eylül 07:00 (Excel ekli) |

Canlı verili kopyalar: `kabul.py --html-dir <klasör>`.
