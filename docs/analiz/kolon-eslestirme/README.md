# Logo ve CRM tablo/kolon eşleştirmesi (2026-10-03)

Canlı Logo (.25 `LOGO_DB`) ve canlı CRM (.28 `Timas_MSCRM`) şeması tarandı, elimizdeki sözlükle
karşılaştırıldı; sözlükte olmayanlar için (1) internet, (2) verinin kendisi kullanıldı.

## Dosyalar

| Dosya | İçerik |
|---|---|
| `logo-web-bulgular.json` | Logo için web bulguları: 234 tablo açıklaması (124'ü kaynaklı), 1.084 kolon kaydı (843'ü kaynaklı, 541 ayrı ad), 60 genel kolon, 36 kopya tablo → asıl tablo, 76 bulunamayan, 73 kaynak URL |
| `crm-web-bulgular.json` | CRM için web bulguları: 827 kolon adı (323 adıyla, 504 kalıpla), 179 metadata dışı tablo, 171 Türkçe adsız entity |
| `betikler/` | Envanter (`inv_*`), fark (`gap*`), veri profili (`profile.py`), XML kod çözücü (`probe2.py`), birleştirme (`combine.py`), depo öncesi temizlik (`scrub.py`) |
| Sunucu `/tmp/ltc/out_logo.json`, `/tmp/ltc/out_crm.json` | Tablo/kolon başına birleşik sonuç (durum, açıklama, kaynak, güven, veri sınıfı, kod dağılımı). **Müşteri verisi örnekleri taşıdığı için depoya alınmadı.** |

## Logo — sonuç

Canlı veritabanı (101 firma) 58.706 tablo/view, 1.935.037 kolon. TİMAŞ firmaları
(015,016,105,115,171,181,191,201,211,411) ve firma/dönem numarası atılınca **3.610 şekil**.

| | Sayı |
|---|---|
| Sözlükte (LDDS + DOC + web) olan şekil | 316 (11.922 kolon) |
| Bu tablolarda sözlükte olmayan kolon | 3.000 (209 tablo) |
| Sözlükte hiç olmayan şekil | 2.449 — 182 standart `LG_`, 476 `L_`, 589 özel tablo, 1.202 özel view |
| Bunlardan boş (0 satır) tablo | 584 |

**Sözlükte olmayan kolonlar (dolu tablolarda 1.974):**
- 1.415 **kullanılmıyor**: veride hepsi boş, 0 ya da sabit. Logo'nun yeni sürüm alanları; TİMAŞ doldurmuyor.
- 200 web kaynaklı (ör. `STLINE.VATEXCEPTCODE/REASON`, `GTIPCODE`, `DEDUCTIONPART1/2`, `CLCARD.ISPERSCOMP`, KVKK alanları, e-Arşiv e-posta adresleri).
- 150 yalnız ad benzerliği (düşük güven).
- 209 yalnız veriden sınıflandı (kod / tarih / referans / tutar).

**Sözlükte olmayan tablolar:**
- Standart `LG_`/`L_`: 294 web kaynaklı, 125 ad benzerliği, 31 kopya (ör. `STLINE_yedek1`, `CLFLINE2612017` → asıl tablo).
- Özel tablolar: 50 ad kalıbından (`MS_211_01_STLINE` = 211 STLINE özel kopyası), 11 kolon kümesi Logo tablosunun alt kümesi
  (`AA_CARI_ADRES` ⊂ CLCARD, `A_MS_201_SEVKIYAT_ADRESI` ⊂ SHIPINFO), 187 yalnız veriden, 11 kullanılmıyor.
- 1.202 özel view: tanım okunamadı (aşağıda). 1.153'ü yalnız adı ve kolon adlarıyla duruyor.

**Veriden çözülen kodlar** (web'de seçenek adı vardı, sayı karşılığı yoktu). `FICHEOBJECT.LDATA` faturanın zip'li
UBL XML'ini tutuyor; kod başına örnek faturalar açılıp XML'deki değerle eşleştirildi (LG_411):

| Kolon | Kod → anlam |
|---|---|
| `EINVOICEDET.PROFILEID` | 1 Temel fatura, 2 Ticari fatura, 0 İhracat (2 örnek) |
| `EINVOICEDET.EINVOICETYP` | 0 Satış (iade faturasında IADE), 2 İstisna, 4 Tevkifat |
| `EARCHIVEDET.SENDMOD` | 1 Kağıt, 2 Elektronik, 0 belirtilmemiş |
| `EBOOKDETAILDOC.DOCUMENTTYPE` | 2 Fatura, 6 Diğer (açıklama dolu: Kredi Kartı Fişi, Dekont…), 99 belgesiz, 0 seçilmemiş (cari/banka/kasa kaynaklı mahsup) |

Web'den kaynaklı gelen e-belge durum kodları: `INVOICE.ESTATUS` 0–23, `EARCHIVEDET.EARCHIVESTATUS` 0–6,
`STFICHE.EDESPSTATUS` 0–25 (logoyazilimdestek.com).

**Veriden çıkan dikkat çekici bulgu:** `T_USATIS_2006…2014` özel tablolarında kitap başına
`YAYINEVİ, KİTAPLIK, TÜR, YAZAR, YAYIN YÖNETMENİ, YETİŞKİN-ÇOCUK` kolonları var. Yani 2006–2014 satışlarında
yazar Logo tarafında da tutulmuş (bugün yazar yalnız CRM'de). `T_SATIS_HEDEFI_KITAP_16/17` kitap başına aylık satış hedefi,
`T_UYUM_BILANCO / MIZAN*` 2006–2012 bilanço/mizan dökümü, `Ahmet_Yıllara_Göre_Satis` cari×stok×yıl×ay satış/iade özeti (6,9 Mn satır).

## CRM — sonuç

1.011 tablo, 838 entity, 18.535 öznitelik.

| | Sayı | Sonuç |
|---|---|---|
| Türkçe etiketsiz kolon | 2.076 | 1.980 Microsoft kaynaklı, 5 ad benzerliği, 91 bilinmiyor. Hepsi sistem kolonu (`VersionNumber`, `OwnerIdType`, `*IdName`, N:N ara tablo kimlikleri); yalnız 6'sı özel alan |
| Metadata dışı tablo | 179 | 97 CRM iç tablosu (`MatchCode*`, `BulkDeleteIndependent_*`, `*Ids`), 82 müşteri tablosu (`b2b_211_*` Logo 211 kampanya/fiyat kopyası, `tbl_devir*` raf sayımı, `tbl_LogoFirmaNo` yıl→Logo firma no). 124'ü dolu, 101'i veriyle profillendi |
| Türkçe adı olmayan entity | 171 | hepsi açıklandı: 137 özel N:N ara tablo, 34 sistem |

Okunmayan: `tblPaymentLog` (sanal POS yetki/kart verisi, bilerek atlandı). Gizli bilgi taşıyanlar
(`UserSettings.EmailPassword`, `License.LicenseKey`, `TBL_B2CTokens`) hiçbir ekrana çıkmamalı.

## Yöntem ve sınırlar

- Envanter: `sys.objects/sys.columns/sys.partitions`. Firma süzgeci `firm_scope.foreign_tables`.
- Veri profili: 200.000 satıra kadar tablonun tamamı, üstünde en yeni 50.000 satır (`LOGICALREF DESC`).
  Sınıflar: boş, hep-sıfır, sabit, bayrak, kod (≤30 değer), tarih, tarih-sayı, referans, tutar/miktar, metin, metin-kod, guid.
- Web kaynakları: ugurozpinar.github.io/Logo (Yeni + eski "Tablo Açıklamaları"), logoyazilimdestek.com, Logo e-Defter ve
  e-Fatura/e-Arşiv kılavuz PDF'leri, docs.logo.com.tr (DNS'ten erişilemedi, yalnız arama özetleri → en fazla "medium"),
  Microsoft Learn Dataverse entity referansı, CData Dynamics CRM tablo sayfaları.
- Başka tablodaki aynı adlı kolondan aktarılan web açıklamaları (~430) **low**'a indirildi. Örneğin `CLCARD.NAME` için
  `LG_LOCATION`'dan "Stok Yeri Açıklaması" gelmişti, bu yanlış.
- **Logo view tanımları okunamadı:** `zekiai` hesabında `VIEW DEFINITION` yetkisi yok, 10.168 modülün tanımı NULL.
  Yetki verilirse 1.202 özel view'ın hangi tabloyu nasıl okuduğu çıkar (kural madencisi de aynı yetkiye bağlı).

## Açık işler

1. BT'den `zekiai` için `VIEW DEFINITION` (yalnız okuma) → view'lar tanımından açıklanır.
2. `logo-ldds.json`'a aktarım: yalnız high/medium + veride dolu kolonlar (`import_logo_web.py` kalıbında, denetim kaydıyla).
3. Web'de sayısal karşılığı bulunmayan kalan kodlar (`HISTORY.TABLEID/STATUS`, `CHANGELOG.OPERATION`, `L_CAPIRIGHT.TYP`)
   aynı yöntemle veriden çözülebilir.
