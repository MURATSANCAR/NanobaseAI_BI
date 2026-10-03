# Bilinmesi gereken Logo kolonlarının doğrulaması (2026-10-03)

Yöntem: canlı Logo (.25) üzerinde LG_411 (2026) ve LG_211 (2021–2025) birlikte, doğrudan sorgu
(`betikler/verify.py`, kod çözümü `betikler/probe2.py`). Yalnız toplu sayımlar okundu.
Sonuç üç sınıf: **kesin** (sisteme yazıldı), **anlamı kesin, sorulmaz** (yazılmadı), **belirsiz** (yazılmadı).

## Kesin — soru motoruna yazıldı (`finance_query/logo_codes.py`)

| Kırılım | Kolon | Kodlar | Kanıt |
|---|---|---|---|
| Belge türü (`e_document`) | INVOICE.EINVOICE | 0 Kağıt, 1 e-Fatura, 2/3 e-Arşiv | 1 ⇔ EINVOICEDET var (35.683/35.683, 2026); 2 ⇔ EARCHIVEDET var; 3 yalnız 2021–25, 40/40 XML'i EARSIVFATURA |
| e-Fatura senaryosu (`einvoice_scenario`) | INVOICE.PROFILEID | 1 Temel, 2 Ticari, 0 seçilmemiş | UBL XML ProfileID: 1 → TEMELFATURA 15/15, 2 → TICARIFATURA 15/15; 0 karışık (ihracat, e-Arşiv, boş) → «seçilmemiş» |
| e-Belge durumu (`einvoice_status`) | INVOICE.ESTATUS | 0–23 Logo statü listesi | logoyazilimdestek.com statü tablosu; e-Arşiv faturada 2 (61.104 ≈ e-Arşiv 61.107). İade (14) ve harici iptal (23) süzgeç kelimesi değil |
| KDV istisnası (`vat_exemption`) | STLINE / INVOICE.VATEXCEPTCODE | 335 basılı kitap, 301 mal ihracatı, 302 hizmet ihracatı, 350 diğer, 351 istisna olmayan diğer | GİB istisna kod listesi; 335 satırların KDV oranı 0 (1,04 Mn satır) |
| Cari e-Fatura mükellefi (`customer_einvoice_user`) | CLCARD.ACCEPTEINV | 1 mükellef, 0 değil | 2026'da e-Fatura kesilen 2.412 carinin 2.353'ü işaretli |
| Şahıs / şirket (`customer_legal_form`) | CLCARD.ISPERSCOMP | 1 şahıs, 0 şirket | 1 → TC kimlik no dolu 242.820/242.956; 0 → vergi no dolu |

İptal kuralı: ölçüler iptal edilmemiş faturayı sayar. Kodlu süzgeçte aynı koşulla iptal edilmiş fatura varsa cevap
bunu not olarak söyler (2026'da reddedilen 2 e-faturanın ikisi de iptal edilmiş).

## Anlamı kesin, soru motoruna gerek yok

- `INVOICE.CANCELDATE` iptal tarihi, `CANCELEXP` iptal açıklaması (CANCELLED=1'de %99 dolu). 2021–25 iptallerinin %55'i
  faturadan sonraki ay yapılmış: geçmiş ayın satışı iptal gelince geriye doğru değişir.
- `INVOICE.DOCDATE` belge tarihi: satışta her zaman `DATE_` ile aynı; alış (1) ve alınan hizmette (4) farklı ay (11.215 fatura, 2021–25).
- `INVOICE.TOTALSERVICES` = hizmet satırları (LINETYPE 4) toplamı (74.755/74.755 birebir).
- `STLINE.DEDUCTIONPART1/2` tevkifat oranı pay/payda (2/3, 9/10, 5/10…).
- `PAYTRANS.MATCHDATE` kapanma tarihi: 2021–25'te ödenen = toplam olan her satırda dolu, açıkta boş; 2026'da kapama koşulmamış (8 satır).
- `STFICHE.CANCELLEDINVREF1` irsaliyenin bağlı olduğu iptal edilmiş fatura (2021–25: 62/62 iptal).
- `CLFLINE.NETAMOUNT/BRUTAMOUNT` kullanılmıyor (≈ hep 0); tutar `AMOUNT`.

## Belirsiz — yazılmadı

- `PAYTRANS.DEVIR`: 2026'da 14 satır 0/1; 2021–25'te 32–222 arası değerler, bayrak değil. Çift sayım riski 2026'da 14 satır / 330 bin ₺.
- `ORFLINE.ORGPRICE`, `RESERVEAMOUNT`, `STFICHE.DISPSTATUS`, `FROMTRANSFER`, `EMFLINE.LINETYPE` 1–3, `EINVOICETYP` 7, KDV istisna kodu 227/250/331…
- `CLCARD.ISFOREIGN`: anlamı yurt dışı cari, ama satış kanalı YURTDIŞI ile örtüşmüyor (720 YURTDIŞI kanallı carinin 540'ı işaretli);
  «yurtdışı satış» bugün kanalla cevaplandığı için ikinci bir yol açılmadı.

## Canlı deneme (yan köprü, 2026-10-03)

| Soru | Motor | Doğrudan sorgu |
|---|---|---|
| Eylül 2026 e-arşiv faturalarımızın satış tutarı | 11.251.116,12 | 11.251.116,12 |
| 2026 belge türüne göre fatura sayısı | e-Arşiv 61.519 · e-Fatura 27.886 · Kağıt 1.013 | aynı |
| 2026 KDV istisnasına göre satış | 335: 1.235.009.663,97 · yok: 28.210.806,20 · 301: 1.891.373,01 | aynı |
| 2026 ticari senaryo fatura sayısı | 13.648 | 13.648 |
| Bu yıl e-fatura mükellefi müşterilere net satış | 1.101.661.266,34 | 1.101.661.266,34 |
| 2026 şahıs / şirket tahsilatı | 238.076.569,28 / 848.941.096,07 | aynı |
| Eylül 2026 e-fatura ile kesilen fatura sayısı | 5.420 | 5.420 |
| Bu yıl kaç e-fatura reddedildi | 0 + not «2 fatura iptal edilmiş» | 0 iptalsiz, 2 iptalli |
| 2026 e-fatura mükellefi olmayan müşterilere net satış | 79.352.565,98 | 79.352.565,98 |

A/B (aynı anda `main` ve dal yan köprüsü, set100'den 15 + 8 genel satış/fatura/tahsilat sorusu): cevap veren 13 soru iki tarafta aynı;
farklar yalnız iki tarafta da cevapsız kalan sorularda (modelin ret gerekçesi koşudan koşuya değişiyor). Hiçbir plan yeni kodlu kırılımı seçmedi.
