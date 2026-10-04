# CRM uçtan uca tarama — 2026-10-04

Kapsam: test sunucusu (nanobase-direct) canlı günlükleri ve zamanlayıcıları, müşteri VM'i (.55) konteyner
günlükleri, CRM'i okuyan/yazan kod (köprü, süzgeç, SEO yazımı, editör bağlayıcısı, gece işleri). Kod
değiştirilmedi, CRM'e yazılmadı. Canlı CRM'e tek okuma sorgusu atıldı (new_kitapBase günlük değişiklik sayısı).

## A. Bugün canlıda olan

| # | Bulgu | Kanıt | Etki |
|---|---|---|---|
| A1 | CRM'e test sunucusundan **~8 saat erişilemedi** (04.10 ~02:00 → 10:05). Neden: TİMAŞ VPN'i (`timas-vpn-mfa`, MFA'lı) düştü, ancak 10:05'te yeniden bağlandı. Son 2 günde 4 kesinti: 02.10 21:23–21:56 (AUTH_FAILED), 03.10 ~06:00–09:19, 03.10 17:xx–18:26, 04.10 02:xx–10:05; aynı gün bir kez daha 19:46–22:30 (5. kesinti, 3 gün içinde). | köprü günlüğü: 7 günde ~17.000 «Unable to connect: Adaptive Server…»; VPN günlüğü | Gece CRM işlerinin hepsi kesintiye denk geldi |
| A2 | **5 gece işi düştü**, ertesi geceye kadar yeniden koşmayacak: `timas-schools`, `timas-musteri@gece`, `timas-field@gece`, `timas-crm-unassigned` (07:00 e-postası gitmedi), `timas-book-similar` | `systemctl --failed`; 503 ile 900 sn bekleyip vazgeçti | Okul, müşteri, saha ekranları dünkü veriyle |
| A3 | **6 gece işi CRM'e ulaşamadığı halde «başarılı» bitti**: `timas-channels`, `timas-readers`, `timas-dijital`, `timas-stock`, `timas-catalog`, `timas-corporate` — çıktıda `"Veritabanına şu an ulaşılamıyor"`, systemd'de `success` | işlerin günlük çıktısı | Hata hiçbir izlemeye düşmüyor, yeniden denenmiyor |
| A4 | `timas-book-similar` DB'ye ulaşamayınca **500** döndü (503 değil) → hiç yeniden denenmedi | köprü 03:40:09 | Diğer işler 15 dk denedi, bu 0 kez |
| A5 | VM'de BT izleme «CRM verisi 3 Ekim'den beri güncellenmiyor» uyarısı üretti — **yanlış alarm**: Pazar günü kitap kartı değişmiyor (27.09 Pazar da 0). Eşik sabit 24 saat, hafta sonunu bilmiyor. Uyarı zaten `no_recipient` — VM'de BT alıcısı tanımlı değil | VM `bi-jobs-1` günlüğü; CRM sorgusu: 03.10'da 6, 02.10'da 22 değişiklik | Pazartesi BT'ye boş alarm gider (alıcı tanımlanınca) |
| A6 | Uyarı e-postalarının alıcısı yok: `timas-readers` (`alici_yok`), `timas-dijital` telif uyarısı (`alici_yok`), VM BT günlük özeti (`no_recipient`) | iş çıktıları | Hatalar kimseye ulaşmıyor |
| A7 | Editör bağlayıcısı bugün 10:10'da koştu (VPN dönünce); 4 kitap `FETCH_FAILED` aldı — bu kitaplar **bir daha denenmeyecek** (bkz. B5) | `editor-crm-connector` günlüğü | 4 kitabın kapağı/kaydı eksik kalır |

## B. Koddaki kesin hatalar (kodda doğrulandı)

**Önce düzeltilmeli — CRM yazım güvenliği (SEO alanları)**

1. **Öneriyi isteyen kendi önerisini onaylayabiliyor** — `backend/semantic_bridge/seo_geo/__init__.py:976` `seo_decide`'da `created_by == user` denetimi yok (toplu onayda da). Kural: «öneriyi yazan onaylayamaz». Düzeltme: 403.
2. **İnsan onayı olmadan CRM'e yazım yolu var** — `seo_geo/crm_write.py:188-199`: `--onayla` bekleyen bütün önerileri «ZEKİ AI» adına onaylıyor; ardından `--yaz` + `acik` kip ile CRM'e gider. Kural: yalnız ekranda insan onayı, otomatik yazma yok. Düzeltme: `--yaz` yalnız `decided_by != ZEKİ AI` olanları yazsın.
3. **CRM'e yazıp kaydı kaybetme** — `crm_write.py:255-272`: önce CRM'e commit, sonra eski değer portal DB'sine. Arada portal DB hatası → CRM değişmiş, eski değer ve «geri al» yok. Düzeltme: önce `yaziliyor` satırı, commit sonrası `yazildi`.
4. **Geri al sonradan yapılan elle düzeltmeyi eziyor** — `crm_write.py:365-389`: CRM'deki güncel değer bizim yazdığımızla aynı mı bakılmıyor; eski yazımı geri almak yeni yazımı da siliyor; `rowcount` denetlenmiyor (kart pasife alınmışsa «geri alındı» der ama hiçbir şey değişmez). Düzeltme: oku-karşılaştır, değiştiyse 409; yalnız en son yazım; `rowcount != 1` → hata.
5. Onayda yarış: `status='hazir'` önce okunuyor, UPDATE koşulsuz → iki eşzamanlı onay iki yazım (`__init__.py:976` / `:663`).

**Okuma doğruluğu**

6. **CRM sorgularında süre ayarı etkisiz** — `backend/semantic_layer/runtime/crm_active.py:224`: `ActiveOnly` sarmalında `__setattr__` yok; `conn.query_timeout = 1800` sarmala yazılıyor, asıl bağlantı 120 sn ile kalıyor. Bütçe (1800), başvurular (900), BT denetimi uzun CRM sorgularında 120 sn'de düşer. Düzeltme: ayarı içe ileten `__setattr__` + test.
7. **Pasif süzgeci görünümlerde çalışmıyor** — süzgeç yalnız `*Base` tablolarına uygulanıyor: `contracts_compare.py:279` (`new_kitap`), `marketing/launch_sources.py:135` (`new_etkinlik`), `budget_sources.py:192` ve `corporate_sales_sources.py:323` (`powerbikitap`). `sets_sources.py:240`, `corporate_sales_sources.py:317`, `budget_sources.py:198` `statecode=0` var ama «Pasif» durum nedeni süzülmüyor. Kural: «pasif hiçbir yerde gelmeyecek».
8. **Süzgeç kurulamazsa 5 dk süzgeçsiz okur** — `crm_active.py:249-264`. Bugünkü kesintide tam bu oldu («tablo listesi okunamadı» uyarısı). Bağlantı geri geldiği ilk 5 dk pasif kayıt ekrana gelebilir. Tablo listesi süreç yeniden başlayana kadar da tazelenmiyor.

**Gece işleri ve izleme**

9. **Saha gece turu her zaman «başarılı» görünüyor** — `backend/semantic_bridge/it_ops_sources.py:389`: izlenen ad `timas-field-gece.timer` → `timas-field-gece.service` aranıyor; gerçek birim `timas-field@gece.service`, olmayan birim systemd'de `success` döner. `timas-musteri`, `timas-book-similar`, `timas-readers`, `timas-channels`, `zeki-directory-sync` izleme listesinde hiç yok. Hiçbir birimde `OnFailure=` yok.
10. **E-posta gitmese de iş başarılı** — `crm_unassigned.py:174`: SMTP yok/gönderim düştü → HTTP 200 + `ok:false`, birim `success`. A3'teki 6 iş de aynı desen: hata gövdede, durum kodu 200.
11. **Editör bağlayıcısı FETCH_FAILED'i bir daha denemiyor** — `apps/editor/connectors/crm_covers.py:431`: değişmedi denetimi yalnız `NO_MATCH`/`AMBIGUOUS`'a bakıyor. Düzeltme: `if last["outcome"] == "FETCH_FAILED": return False`.
12. **Sohbet rehberi eşitlemesi kalıcı kilitlenebilir** — `deploy/zeki/sync-directory.py:258`: eşitlemenin açtığı bir sohbet hesabı elle silinmişse her 15 dk aynı yerde `SyncError` ile düşer, bütün ekip eşitlemesi durur. (Bugün çalışıyor.)

## C. Risk / eksik (acil değil)

- `crm_covers.py:422`: koşu sırasında değişen CRM kaydı kalıcı kaçabilir (karşılaştırma okuma zamanıyla değil yazma zamanıyla); kitap başına `try` yok, tek sorgu hatası bütün işi bitirir.
- `book_similarity.py`: CRM boş liste dönerse bütün etkin kayıtlar pasife çekilir; tema okuması düşerse bütün dizin iki kez baştan gömülür.
- `musteri_api.py:122`: aynı gün ikinci koşu güvenlik bulgusu e-postasını yineler.
- `editorial.py:349,369,378`: CRM tarihleri UTC; `YEAR()`/`CAST(... AS date)` +3 saat düzeltmesiz → gece yarısı kayıtları önceki güne/yıla düşer.
- `crm_write.py:148`: yazma bağlantı dizesinde şifre kaçışsız (`;` / `}` bozar). `crm_write.py:335`: gece denetimi pasife alınmış kartı «CRM'de değişmiş» sayar.
- `timas-channels`: ilk adım düşerse Trendyol/Amazon adımları hiç koşmuyor. `timas-crm-unassigned.timer`'da `Persistent=` yok.
- VM: `bi-bridge-1` 03:35'te yeniden başlamış (2 yeniden başlatma, OOM değil); 00:30'da bir CRM sorgusu FreeTDS «Unknown error (0)» ile düştü (baskı öneri kitap kartı). RAM 7,7 GB'ın 6 GB'ı dolu.

## D. Temiz çıkanlar

- CRM'e yazan tek kod `seo_geo/crm_write.py`; kolon listesi iki yerde denetleniyor, değerler parametreli. Fiilen yazılan: `new_seobaslik`, `new_seoaciklama`, `new_kapakalt`, `new_seodurum`, `new_seoguncelleme` (izin listesinden dar — güvenli taraf).
- Kip varsayılanı `kapali`; test sunucusu `SEO_CRM_WRITE=deneme`, VM'de tanım yok (= kapalı).
- Logo ile CRM'i tek SQL'de birleştiren sorgu yok. Arama metni giren CRM sorgularında enjeksiyon bulunmadı.
- Koddaki CRM tablo/kolon adlarının hepsi CRM sözlüğünde var.
- CRM verisi canlı: kitap kartında 03.10'da 6, 02.10'da 22, 01.10'da 25 değişiklik.

**Güncelleme 04.10 22:50:** düşen 5 iş elle yeniden koşturuldu, hepsi başarılı. 4'ü VPN dönene kadar bekleyip
(22:30) bitti; `crm-unassigned` 106 kişilik listeyi Bilgiislem@timas.com.tr'ye gönderdi. `book-similar` ilk denemede
yine 500 ile düştü (A4), VPN dönünce ikinci denemede bitti (4 kitap gömüldü).

## Önerilen sıra

1. **Bugün (elle, ~5 dk):** düşen 5 işi şimdi koştur — `sudo systemctl start timas-schools timas-musteri@gece timas-field@gece timas-crm-unassigned timas-book-similar`; «başarılı» görünen 6 işi de (`timas-channels timas-readers timas-dijital timas-stock timas-catalog timas-corporate`).
2. **SEO yazım güvenliği (B1–B5)** — CRM'e yazma `acik` kipe geçmeden önce şart. ~2-3 saat + test.
3. **Hata görünürlüğü (B9, B10, A3, A4, A6)** — işler hata gövdesinde 5xx dönsün, izleme listesi düzelsin, alıcılar tanımlansın. ~3 saat.
4. **VPN kesintisi (A1)** — kalıcı çözüm TİMAŞ BT'de (MFA'sız servis hesabı ya da site-to-site). Bizim tarafta: VPN geri gelince düşen gece işlerini otomatik yeniden koştur.
5. **Okuma doğruluğu (B6–B8, B11)** — ~2 saat.
