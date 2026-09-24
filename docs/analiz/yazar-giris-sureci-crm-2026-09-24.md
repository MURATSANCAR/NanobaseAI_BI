# Yazarın Yayınevine Giriş Süreci → CRM eşlemesi

Tarih: 2026-09-24. Kaynak: müşterinin gönderdiği `Yazar Giriş Süreci.pdf` (3 evre, 9 adım). Karar: süreç ekranı verisini **CRM'den dinleyerek** alır, elle giriş yok.
Ölçüm: canlı CRM (.28, `Timas_MSCRM`), test sunucusundan doğrudan bağlantıyla, salt okuma. Sayılar 2026-09-24 sabahı.

## 1. Adım → CRM alanı

| # | Evre | PDF adımı | CRM'deki karşılığı | Veri durumu |
|---|---|---|---|---|
| 1 | Değerlendirme | Başvuru gelir | `new_projeBase` kaydı açılır; `new_olusturmakanali` (Web Başvurusu, Referans, Yurtdışı, Mevcut Yazar, Fuar, Dosya Başvurusu…), `CreatedOn` | Canlı: 2025'ten beri 2.115 yeni proje, son 90 günde 192. Kanal %47 dolu. `new_dosyabasvuruBase` (19 satır, son 2024-05) ve `new_yeniprojeveyazarBase` (son 2017) ölü — kullanılmaz. |
| 2 | Değerlendirme | İnceleme ve editör ataması | `new_projeBase.new_editoru` → SystemUser | %67 dolu (1.414/2.115). `new_sorumlueditr` hiç dolu değil. |
| 3 | Değerlendirme | Editör raporu | `new_icrapor` (Yok/İstendi/Tamamlandı), `new_disrapor`, `new_okumanotlari`; proje ekleri `AnnotationBase` (ObjectTypeCode 10000) | **Zayıf.** İç rapor "Tamamlandı" yalnız 5 projede, okuma notu 0. Rapor dosyası olarak 2025'ten beri 131 proje eki var (ör. `kendine bakma sanatı.pdf`). Rapor CRM'de tutulmuyor gibi. |
| 4 | Yayın Kurulu | Proje kartı ve ön sunum | `statuscode` = 100000011 «(Yeni Proje) Proje Toplantısına Hazırlanıyor» → 100000014 «Yayın Kuruluna Hazırlanıyor» → 100000015 «Yayın Kuruluna Hazır» | Canlı. Proje kartı zaten 1. adımda açılıyor; PDF'teki sıra ile CRM'deki sıra farklı (bkz. §3). |
| 5 | Yayın Kurulu | Kurul değerlendirmesi | `new_yayinkurulutoplantilariBase` (`new_toplantitarihi`, `new_toplantikararnotu`, fiyat/baskı adedi/telif/avans önerisi; projeye `new_YaynKuruluToplantlarId`), üye görüşleri `new_projegrBase`; karar `statuscode` 100000020 «(Basılacak) Yayın Kurulu Onaylı» / 100000012 «Red Edildi» | Canlı: 514 kurul kaydı, son 90 günde 38. Projedeki `new_yayinkurulutarihi`, `new_yaynkurulsonucu`, `new_yayinkuruluonaytarihi` **hiç dolu değil**; karar yalnız statuscode + kurul tablosunda. Görüş son 90 günde 8. |
| 6 | Giriş | Yazara bilgi verilir | Karşılığı yok | CRM'de alan/aktivite yok. Ya CRM'e alan açılır ya da adım "kurul onayından sonra X gün" diye çıkarımla gösterilir. |
| 7 | Giriş | Cari form ve kişi kartı | Yazar kişi kartı `ContactBase`, projede `new_olasyazaryazar` → Contact | Kişi bağı %62 (1.315/2.115). Cari (`AccountBase`) ekleri bayi evrakı (vergi levhası, imza sirküleri) — yazar cari formu değil. Yazar cari formu CRM'de görünmüyor. |
| 8 | Giriş | Eser katılımcı formu, tarih, sözleşme | `new_eserkatilimBase` (kişi + rol), `new_sozlesmeBase` (+ `new_sozlesmetarafiBase`); tarih `new_hedeflenenbaskitarihi` / `new_nerilenyayntarihi` / `new_yayintarihi` | Katılım ve sözleşme canlı (son 90 günde 221 / 429). Tarih alanları yalnız %9 dolu (200/2.115). |
| 9 | Giriş | Üretim ve stok kartı | `new_projeBase.new_stakkarti` → `new_kitapBase` (Stok Kartı), `new_UretimBase.new_kitapid`; statuscode 100000019 «İş Planı Çalışıyor» | Canlı: stok kartı bağı %73 (1.551/2.115); 972 proje "İş Planı Çalışıyor". Üretimde proje bağı yok, kitap üzerinden gidilir. |

`new_projeasamasi` (Proje Aşamaları tablosu, 80 aşama adı) 2025'ten beri **hiçbir projede dolu değil** — adım göstergesi için kullanılamaz.

## 2. "Dinleme" nasıl yapılır

- **Güncel durum:** `ModifiedOn` üzerinden birkaç dakikada bir çekme (poll). CRM'de olay kuyruğu/webhook yok (on-prem Dynamics, SQL'e salt okuma erişimimiz var).
- **Geçmiş ve adım zamanları:** CRM denetim kaydı (`AuditBase`) Proje, Stok Kartı, Üretim, Sözleşme, Eser Katılımı, Kişi ve Cari için **açık**; Proje için 2013'ten beri 67.588 kayıt, son 60 günde 767. Hangi alanın ne zaman kim tarafından değiştiği (`AttributeMask`, `UserId`) buradan çıkar → her adımın başlangıç tarihi ve süresi geriye dönük hesaplanabilir. Eski değer `ChangeData`'da.
- **Denetim kapalı olanlar:** Yayın Kurulu Toplantıları ve Proje Görüşü. Bunlarda yalnız `CreatedOn` / `ModifiedOn` var.

## 3. PDF ile CRM'in uyuşmadığı yerler

1. PDF'te proje kartı 4. adımda açılıyor; CRM'de başvuru zaten proje kartı olarak giriyor (1. adım). Ekranda 1–3 arası adımlar da proje kartı üzerinden izlenir.
2. Editör raporu (3) ve yazara bilgi (6) CRM'de izlenmiyor. İki seçenek: CRM'e alan açılması (müşterinin CRM ekibi) ya da raporu bizim editör modülümüzde (M1/M2 masası) yazdırıp kaydetmek.
3. Kurul sonucu projede üç ayrı alanda tanımlı ama hiçbiri kullanılmıyor; tek güvenilir kaynak `statuscode` + kurul tablosu.
4. Yazar cari formu CRM'de yok (Logo carisi olabilir — Logo'da ayrıca bakılmalı).

## 4. Müşteriye sorulacaklar

1. Editör raporu nerede duruyor (e-posta, dosya, CRM eki)? CRM'e "Tamamlandı" işaretlenmesi beklenebilir mi?
2. Yazara bilgi verildiği ve cari formun alındığı nereye kaydediliyor?
3. Kurulun 1–2 aylık takvimi CRM'de bir yerde var mı, yoksa toplantı tarihi yalnız kurul kaydından mı okunmalı?
