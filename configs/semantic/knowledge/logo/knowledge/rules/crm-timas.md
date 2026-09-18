# CRM (TIMAS_MSCRM) kuralları

CRM kaynağı Dynamics CRM'dir; tablolar `*Base` ile biter (`NEW_SOZLESMEBASE`, `NEW_SATISHEDEFLERIBASE`). Sütun adları büyük/küçük harf karışıktır; şemadaki yazımıyla kullan.

## Kural C1 — Kayıt durumu

- Her CRM tablosunda `statecode = 0` aktif kayıttır; silinmiş/pasif (`statecode = 1`) kayıtlar sayım ve toplamlara alınmaz. Sorgu bu koşulu her CRM tablosunda yazar.
- Kişi/hesap adı `name`, özel varlıklarda `new_name`.

## Kural C2 — Satış hedefleri (NEW_SATISHEDEFLERIBASE)

- Bir satır = bir ürünün (`new_stokkarti`, kodu `new_StokKodu`, adı `new_itemno`) bir yıl için aylık hedefleri. Aylar **sütundur**: `new_ocak, new_subat, new_Mart, new_Nisan, new_mayis, new_Haziran, new_Temmuz, new_agustos, new_eylul, new_Ekim, new_kasim, new_aralik`; yıllık toplam `new_ToplamHedef`.
- `new_yil` bir seçim listesi kodudur, yıl sayısı değildir: 1 = 2023, 2 = 2024, 3 = 2025, 100000000 = 2026 (kaynak: `StringMap`, `AttributeName = 'new_yil'`). "Bu yılın hedefi" = `new_yil = 100000000`.
- **Aylara dağılımın dengesizliği** = 12 aylık değerin değişim katsayısı (standart sapma / ortalama). Aylar sütun olduğu için önce `CROSS APPLY (VALUES (new_ocak), (new_subat), … (new_aralik)) v(ay)` ile satıra açılır, sonra ürün başına `STDEV(ay) / NULLIF(AVG(ay), 0)` alınır; yıllık toplamı 0 olan ürünler dışlanır. "En dengesiz" = bu oran en yüksek ürün; cevapta oran, yıllık toplam ve ürün kodu/adı yazılır.

## Kural C3 — Satış senaryosu ve baskı maliyeti (NEW_SATISSENARYOSUBASE)

- Bir kitabın baskı maliyet hesabı **satış senaryosu**dur; kitap `new_projeid` (NEW_PROJEBASE) ile bağlanır. **Forma sayısı** `new_Forma`; **toplam baskı maliyeti** `new_ToplamMaliyet`, **birim maliyet** `new_BirimMaliyet`; forma başına maliyet = `new_ToplamMaliyet / NULLIF(new_Forma, 0)`.
- "Forma sayısı N'in üstünde olan kitapların baskı maliyeti" = `new_Forma > N` senaryolarının `new_ToplamMaliyet` ortalaması, kitap sayısı `COUNT(DISTINCT new_projeid)`. Koşula uyan kayıt yoksa sonuç boştur; boş sonuç "bu forma sayısında senaryo yok" demektir.

## Kural C4 — Sözleşme tarafları (NEW_SOZLESMETARAFIBASE)

- Bir sözleşmenin tarafları `new_sozlesmeid` ile NEW_SOZLESMEBASE'e bağlanır; tarafın ödeme yüzdesi `new_Odeme` (0–100). "Birden fazla tarafı olan" = `HAVING COUNT(*) > 1`; "yüzdeler toplamı yüzü aşan" = `HAVING SUM(new_Odeme) > 100`. Cevapta sözleşme adı (`NEW_SOZLESMEBASE.new_name`) ve toplam yüzde yazılır.

## Kural C5 — Sözleşmeler (NEW_SOZLESMEBASE)

- Sözleşme kaydı `NEW_SOZLESMEBASE` (`new_sozlesmeId`, adı `new_name`, telif tipi `new_TelifTipi`, sözleşmedeki telif yüzdesi `new_Telif`). Tarafları `NEW_SOZLESMETARAFIBASE.new_sozlesmeid` ile bağlanır.
- "Ödeme yüzdeleri toplamı yüzde yüzü tutmayan" = taraf ödeme yüzdeleri toplamı `<> 100` (`HAVING SUM(new_Odeme) <> 100`); sapma = `SUM(new_Odeme) − 100`. Her iki tabloda `statecode = 0`.

## Kural C6 — Telif tanımı ve baskı adedi kademesi (NEW_TELIFTANIMBASE)

- Telif kademeleri `NEW_TELIFTANIMBASE` satırlarıdır: baskı adedi aralığı `new_BalangicAdeti`–`new_BitisAdeti`, o aralıkta geçerli **telif yüzdesi** `new_TelifYuzdesi` (0–100). Sözleşmeye `new_sozlesme` ile bağlanır.
- "Baskı adedi arttıkça telif yüzdesi nasıl değişir" = aralık başlangıcı (`new_BalangicAdeti`) bazında `AVG(new_TelifYuzdesi)`, kademe sayısıyla, başlangıca göre artan sırada; yüzdesi ya da başlangıcı boş kademeler dışlanır. Bu CRM sorusudur; Logo üretim emri (PRODORD) baskı adedi burada kullanılmaz.

## Kural C7 — Önerilen baskı adedi ve gerçekleşen üretim (NEW_BASKIONERIBASE, NEW_URETIMBASE)

- **Önerilen baskı adedi** `NEW_BASKIONERIBASE.new_OnerilenBaskiAdeti`; öneri kitaba `new_BaskionerileriId = NEW_KITAPBASE.new_kitapId` ile bağlıdır.
- **Gerçekleşen üretim adedi** baskı kaydındadır: `NEW_BASKIBASE.new_uretimadedi` (net baskı `new_netbaskiadedi`). Baskı, üretim kaydına `NEW_BASKIBASE.new_uretimid = NEW_URETIMBASE.new_UretimId`, üretim kitaba `NEW_URETIMBASE.new_kitapid` ile bağlanır. `NEW_URETIMBASE.new_UretimAdedi` sütunu bu kurulumda hiç dolu değildir; kullanılmaz.
- "Önerilen ile gerçekleşen fark" = kitap bazında `SUM(önerilen)` ile `SUM(üretim adedi)` ayrı alt sorgularda toplanıp kitap üzerinden birleştirilir; fark = gerçekleşen − önerilen, sapma yüzdesi = fark / NULLIF(önerilen, 0) × 100. Logo STLINE/PRODORD bu soruda kullanılmaz.

## Kural C8 — Rakip kitap eşleşmesi ve liste fiyatı

- Kendi kitabımız `NEW_KITAPBASE` (adı `new_name`, **liste fiyatı** = KDV dahil fiyat `new_kdvdahilfiyat`); rakip kitap `NEW_RAKIPKITAPBASE` (adı `new_name`, yayınevi `new_Yaynevi`, liste fiyatı `new_ListeFiyat`).
- **Eşleşme** N:N tablosudur: `NEW_NEW_KITAP_NEW_RAKIPKITAPBASE (new_kitapid, new_rakipkitapid)`. "Rakiplere göre nerede duruyor" = kitap bazında kendi liste fiyatı, rakip ortalama liste fiyatı (`AVG(new_ListeFiyat)`, 0 ve boş fiyatlar dışlanır), fark ve fark yüzdesi (kendi − rakip) / rakip × 100, rakip sayısı.

## Kural C9 — Sözleşme sahibi (yazar), aracı, yurtiçi/yurtdışı

- Sözleşmenin **yazarı/sahibi** `NEW_SOZLESMEBASE.new_SozlemeninSahibi → ACCOUNTBASE.AccountId` (adı `ACCOUNTBASE.Name`); ContactBase değildir. "Yazarlara göre" = bu hesap bazında kırılım.
- **Aracı firma** taraf kaydındadır: `NEW_SOZLESMETARAFIBASE.new_aracivarmi = 1` (aracı firması `new_aracifirma`, aracı yüzdesi `new_araciyuzdesi`, aracı alacak tutarı `new_aracialacaktutari`). "Aracı üzerinden yürüyen sözleşme" = en az bir tarafında `new_aracivarmi = 1` olan sözleşme; payı = aracılı sözleşme / aktif tüm sözleşme × 100.
- Tarafın **yurtiçi/yurtdışı** kodu `NEW_SOZLESMETARAFIBASE.new_yurticiyurtdisi`: 1 = Yurtiçi Alış, 2 = Yurtdışı Satış, 3 = Yurtdışı Alış. "Yurtdışı hak alınmış sözleşme" = tarafı 3 (yurtdışından hak alınan); "yurtdışına hak satılmış" = 2.
- **Ajans servis ücreti** `NEW_SOZLESMEBASE.new_ajansservisucreti`; sözleşmedeki **telif tutarı** `NEW_SOZLESMEBASE.new_teliftutari`. Boş sütun toplamı NULL döner; cevapta adedi ver, tutarın kayıtlı olmadığını söyle.

## Kural C10 — Etkinlikler ve giderleri (NEW_ETKINLIKBASE)

- **Etkinlik gideri** = `NEW_ETKINLIKBASE.new_ToplamEtkinlikGideri` (dolu olan sütun budur; `new_etkinlikgideri` ve `new_promosyontutari` hiç dolu değil). Yazar etkinlik telifi `new_YazarEtkinlikTelifi`.
- Etkinliğin **yazarı** N:N tablosundadır: `NEW_NEW_ETKINLIK_NEW_YAZARBASE (new_etkinlikid, new_yazarid) → NEW_YAZARBASE.new_name`; `new_lgiliYazar` (Contact) sütunu hiç dolu değil. "Yazar bazında etkinlik gideri" = yazar adı, etkinlik adedi (`COUNT(DISTINCT new_etkinlikId)`), `SUM(new_ToplamEtkinlikGideri)`; "en pahalı N yazar" = gidere göre azalan ilk N.
- Uyarı: yazar eşleşme tablosu (`new_new_etkinlik_new_yazar`) bu kurulumda boştur ve taranmış tablolar arasında değildir; `new_lgiliYazar` da hiç dolu değil. Yazar bazında gider **hesaplanamaz**: bu soruya tek satır — toplam etkinlik gideri ve gideri dolu etkinlik adedi — ver, yorum satırında yazar kırılımının veri yokluğundan yapılamadığını yaz. Taranmamış tabloyu sorguda kullanma.

## Kural C11 — Projeler (NEW_PROJEBASE)

- Proje durumu `statuscode` seçim kodudur: 100000011 Yeni Proje (toplantıya hazırlanıyor), 100000013 Basılmayacak, 100000014 Beklemede, 100000015 Yayın Kuruluna Hazır, 100000017 **Tamamlandı**, 100000019 İş Planı Çalışıyor, 100000020 **Yayın Kurulu Onaylı (basılacak)**, 100000009/100000021 İptal, 100000012 Red, 100000018 İleri Tarihli.
- "Tamamlanmamış proje" = `statuscode NOT IN (100000017, 100000009, 100000012, 100000021)`; **metin teslim tarihi** `new_tahminimetinteslimtarihi`; "teslim tarihi geçtiği hâlde tamamlanmamış" = bu tarih `< GETDATE()` ve tamamlanmamış; gecikme günü `DATEDIFF(day, new_tahminimetinteslimtarihi, GETDATE())`. `new_tamamlanma` sütunu projede boştur.
- "Yayın kurulunda onaylanan proje" = `statuscode = 100000020` (kurul sonucu sütunu `new_YaynKurulSonucu`: 1 Yayınlama, 2 Yeniden Değerlendirme, 100000000 Red — çoğunlukla boş). **Önerilen telif oranı** `new_olasitelif` (yüzde); avans bedeli sütunu projede yok.

## Kural C12 — İş planları (NEW_ISPLANIBASE)

- İş planı satırı bir projenin (`new_projeid`) planıdır; **sorumlusu** `OwnerId → SYSTEMUSERBASE.SystemUserId` (adı `FullName`); **tamamlanma oranı** `new_tamamlanma` (0–100). Durum `statuscode`: 1 Taslak, 2 Tamamlanmış, 100000000 Aktif, 100000001 Durdurulmuş.
- "Tamamlanma oranı en düşük sorumlular" = sorumlu bazında iş adedi ve `AVG(new_tamamlanma)`, artan sırada; tamamlanması boş satırlar ortalamaya girmez.

## Kural C13 — CRM siparişleri (NEW_SIPARISBASE)

- CRM sipariş satırı `NEW_SIPARISBASE`: sipariş adedi `new_siparisadeti`, **bekleyen adet** `new_bekleyenadet`, **termin** = istenen sevk tarihi `new_istenensevktarihi`, sevk tarihi `new_sevktarihi`.
- Durum `statuscode`: 1 Taslak, 2 Etkin değil, 100000000 Sevk Edildi, 100000001 İptal, 100000002 Sipariş, 100000003 **Birleştirildi** (başka siparişe katıldı, bekleyen sayılmaz), 100000004 Risk Limit Onayı Bekliyor, 100000005 Pazarlama Bütçesi Onayı Bekliyor, 100000011 Depoda Bekliyor, 100000012 Pusula Alındı, 100000013/14 Kutulanıyor/Kutulandı, 100000015 Tamamlandı, 100000016 Risk Bilgisi Bekleniyor.
- "Termini geçtiği hâlde bekleyen sipariş satırı" = `new_bekleyenadet > 0 AND new_istenensevktarihi < GETDATE()` ve durum Tamamlandı/Sevk Edildi/İptal/Birleştirildi/Etkin değil dışı. Durum listesi tek başına "bekleyen" demek değildir; bekleyen adet şarttır. Sonuç 0 olabilir; 0 doğru cevaptır.

## Kural C14 — Sevkiyat satırları ve indirim (NEW_SEVKIYATSATIRIBASE)

- Sevkiyat satırı: liste birim fiyatı `new_listebirimfiyati`, adet `new_adet`, **indirim yüzdesi** `new_indirimyuzdesi` (0–100), birim indirim tutarı `new_indirimtutari` (birim başınadır), indirimli birim fiyat `new_indirimlibirimfiyati`, liste toplamı `new_toplamtutar`, indirimli toplam `new_indirimlitoplamtutar`.
- "Liste fiyatı üzerinden ortalama kaç puan indirim" = **tutarla ağırlıklı** indirim yüzdesi: `SUM(new_indirimtutari × new_adet) / NULLIF(SUM(new_listebirimfiyati × new_adet), 0) × 100` (≈ `SUM(new_toplamtutar − new_indirimlitoplamtutar) / SUM(new_toplamtutar)`); basit `AVG(new_indirimyuzdesi)` yanında verilebilir ama ana cevap ağırlıklı olandır. `new_listebirimfiyati > 0 AND new_adet > 0`.

## Kural C15 — Talep yönetimi / destek talepleri (NEW_TALEPYONETIMIBASE)

- Destek (iç talep) kaydı `NEW_TALEPYONETIMIBASE`; açılış `CreatedOn`, **tamamlanma** `new_tamamlanmatarihi`, planlanan bitiş `new_planlananbitistarihi`. Durum `statuscode`: 1 Yeni Talep, 100000000 Üzerinde Çalışılıyor, 100000001 Ötelendi, 100000002 İptal, 100000003 **Tamamlandı**, 100000004 Sıra Bekliyor, 100000005 Test, 100000006 Analiz, 100000007 Yazılım, 100000008 Bilgi Bekleniyor, 100000009 Bilgi İşleme Aktarıldı.
- **Departman** `new_ilgilidepartman` seçim kodudur (bu varlığa özel): 1 Kültür Editorya, 2 Çocuk Editorya, 3 Muhasebe, 4 Satış, 6 Pazarlama, 7 Depo, 8 Grafik, 9 Kültür & Çocuk Editorya, 10 Üretim. Metin sütunu `new_departman` boştur.
- "Ortalama sonuçlandırma süresi" = yalnız Tamamlandı (100000003) ve tamamlanma tarihi dolu kayıtlarda `AVG(DATEDIFF(day, CreatedOn, new_tamamlanmatarihi))`; açık talepler dışlanır, departman bazında talep adedi ile.

## Kural C16 — Fiziki arşiv ve emanet (NEW_FIZIKIARSIVBASE)

- Arşiv kaydı `NEW_FIZIKIARSIVBASE`; ürün `new_arsivurun → NEW_KITAPBASE.new_kitapId` (adı `new_name`); **emanet alan kişi** `new_emanetalankisi → SYSTEMUSERBASE.SystemUserId` (`FullName`); emanet başlangıcı `new_baslangictarihi`, bitişi `new_bitistarihi`, açıklaması `new_emanetaciklamasi`.
- **Arşiv durumu** `new_arsivdurumu`: 1 Arşivde, 2 **Emanette**. "Emanete verilmiş ve geri dönmemiş" = `new_arsivdurumu = 2`; bekleme süresi `DATEDIFF(day, new_baslangictarihi, GETDATE())`.

## Kural C17 — Baskı işlemleri (NEW_BASKIISLEMBASE)

- Baskı işlemi satırı: işlem tipi `new_islemtipiid → NEW_ISLEMTIPIBASE.new_name`, birim fiyat `new_birimfiyat`, toplam tutar `new_toplamtutar`, forma sayısı `new_formasayisi`, baskıya `new_baskiid → NEW_BASKIBASE`. Bu kurulumda yalnız 2015–2017 kayıtları var (23 satır; birim fiyatı dolu 1 satır). "Birim fiyatı en çok artan işlem tipi" = işlem tipi × yıl ortalama birim fiyat, ardışık yıl farkı; iki yılı olan tip yoksa sonuç boştur ve bu söylenir.
- "Kitap başına ortalama baskı maliyeti" = baskı işlem toplam tutarı / baskı adedi (`NEW_BASKIBASE.new_netbaskiadedi`) baskı bazında; son bir yılda kayıt yoksa sonuç boştur (veri 2015–2018 ile sınırlı).

## Kural C18 — Telif hakedişleri ve ödeme dönemi

- Hakediş `NEW_ODEMEHAKEDISBASE` (telif tutarı `new_TelifTutari`, ödenen `new_odenenTutar`, dönem `new_Donem → NEW_ODEMEDONEMIBASE`, sözleşme `new_SzlemeId`); ödeme dönemi `NEW_ODEMEDONEMIBASE` (`new_DonemBaslangicTarihi`, `new_DonemBitisTarihi`, `new_sozlesme`). "Ödeme dönemi kapandığı hâlde ödenmemiş hakediş" = dönem bitişi `< GETDATE()` ve `new_odenenTutar` boş/0 (ya da `< new_TelifTutari`). Hakediş tablosu bu kurulumda boştur (0 kayıt), 7 ödeme dönemi kaydı var; sonuç boş = veri yok.

## Kural C19 — Kargo bilgileri (NEW_KARGOBILGISIBASE)

- Kargo kaydı `NEW_KARGOBILGISIBASE` (13.242 kayıt); **çıkış şubesi** `new_sevkiyatcikissubesi`, varış şubesi `new_sevkiyatvarissubesi`, kargo firması `new_kargofirmasi`, **sevk adedi** `new_sevkadeti`, **tutar (kargo maliyeti)** `new_Tutar`, desi `new_desi`, ağırlık `new_agirlik` — bunların hepsi **metin** sütunudur, ondalık ayracı virgüldür: `TRY_CAST(REPLACE(new_Tutar, ',', '.') AS FLOAT)` ile okunur.
- "Sevk adedi başına maliyet çıkış şubelerine göre" = şube bazında `SUM(tutar) / NULLIF(SUM(sevk adedi), 0)`, kargo adedi ve toplamlarla; şubesi boş kayıtlar ayrı satırda "Belirtilmemiş" olarak kalır.

## Kural C20 — Reklam planları (NEW_REKLAMPLANIBASE)

- Reklam planı: tutar `new_Tutar`, birim fiyat `new_BirimFiyat`, **onay tarihi** `new_OnayTarihi` (onay veren `new_OnayVeren`; ayrıca `new_editortalonay`, `new_pazarlamayoneticisionayi`, `new_genelmuduronayi` bitleri), **teslim edildi** `new_reklamteslimedildimi` (bit), planlanan teslim `new_PlanlananReklamTeslimTarihi`, gerçekleşen teslim `new_gerceklesenteslimtarihi`; mecra `new_reklammecrasi…`, tip `new_reklamtipi…`.
- "Onaylanmış ama teslim edilmemiş" = `new_OnayTarihi IS NOT NULL AND ISNULL(new_reklamteslimedildimi, 0) = 0`; tutar toplamı `SUM(new_Tutar)`. Bu kurulumda 68 planın hiçbirinde onay tarihi/onay biti dolu değil → sonuç 0/boş; bu veri yokluğudur.

## Kural C21 — Bütçe kayıtları

- Etkinliklere bağlı bir bütçe tablosu yoktur: `NEW_ETKINLIKBASE`'te bütçe sütunu yok; `NEW_BUTCEKALEMIBASE` (iş planı/iş emri bütçe kalemleri, 2013–2014) ve `NEW_PROMOSYONBUTCESIBASE` (promosyon bütçesi: `new_butce`, `new_kullanilanbutce`, `new_kalanbutce`; 2 kayıt, 2017/2020) etkinlikle ilişkili değildir. "Etkinlik giderleri bütçenin neresinde" sorusuna toplam etkinlik gideri verilir ve karşılaştırılacak bir etkinlik bütçesinin tanımlı olmadığı söylenir; promosyon bütçesi etkinlik bütçesi yerine kullanılmaz.

## Kural C22 — Telif ödemesi / tahakkuk (NEW_ODEMEBASE)

- Telif tahakkuk kaydı `NEW_ODEMEBASE`: tahakkuk tutarı `new_TahakkukTutari`, ödeme tarihi `new_odemetarihi`, onay tarihi `new_onaytarihi`, sözleşme `new_sozlesmeid → NEW_SOZLESMEBASE` (yazar = sözleşme sahibi, Kural C9). "Bu yıl hangi yazara ne kadar telif tahakkuk etti" = yıl içindeki tahakkuklar yazar bazında `SUM(new_TahakkukTutari)`. Bu kurulumda kayıtlar yalnız 2014'te (48 kayıt, 274.021 ₺); 2026 için sonuç boştur — veri yok. Satış adedi × fiyat × telif yüzdesi ile tahakkuk **hesaplanmaz** (satış verisi Logo'da, sözleşme yüzdesi CRM'de; çapraz hesap iş teyidi ister).

## Kural C23 — Kampanyalar (NEW_KAMPANYABASE)

- Kampanya `NEW_KAMPANYABASE`: adı `new_name`, tarih aralığı `new_baslangictarihi`–`new_bitistarihi`, **planlanan ciro** `new_planlananciro`, **gerçekleşen ciro** `new_gerceklesenciro`, ek iskonto `new_ekiskonto`. "Planlanan ile gerçekleşen ciro" = kampanya bazında bu iki sütun ve fark; her ikisi de bu kurulumda boş (4 kampanya, 2025–2026) — sonuç "veri girilmemiş" olur. Logo faturalarıyla kampanya eşlemesi (tarih aralığına düşen ciro) yalnız kullanıcı isterse ve kampanya tarihine göre yapılır; bu cevapta iş teyidi gerekir.

