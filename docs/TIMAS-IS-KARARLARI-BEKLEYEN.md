# TİMAŞ — iş tarafından bekleyen kararlar (2026-09-18)

Altın cevap dosyası yazılırken (`tests/text2sql/answers-set100.json`) bağımsız referanslar canlı Logo/CRM'de koşturuldu.
Aşağıdaki sorularda **doğru cevap bir iş tanımına bağlı**; veri iki okumayı da destekliyor ve hangisinin geçerli olduğunu
ancak işi bilen biri söyleyebilir. Karar verilene kadar ilgili altın giriş notunda iki okuma da yazılıdır. Kararlar
soru bazında değil **konu** bazındadır: bir karar, aynı konudaki bütün soruları bağlar.

| # | Konu | Karar | Okuma A | Okuma B | Etkilenen |
|---|---|---|---|---|---|
| 1 | Termin tarihi kimin | Sipariş termini hangi sistemden okunur? | CRM: bekleyen 4.043 sipariş başlığı ve 19.759 satırın hiçbirinde termin dolu değil → 0 satır | Logo `ORFLINE.DUEDATE` → 1.061 satır (2026) | Q37, Q42, Q57, Q73 |
| 2 | "Sepet" | Ortalama sepet tutarı sipariş mi, fatura mı? | Logo satış faturası ortalaması (katalogdaki tanım) | CRM sipariş başlığı → ilk on firma tamamen farklı | Q43 |
| 3 | Karşılıksız çek | "Bu yıl karşılıksız çıkan" olay mı, güncel durum mu? | Olay (`CSTRANS`): 6 çek, 6.326.658 ₺ — hepsi sonradan iade edilmiş | Güncel durum (`CURRSTAT`): kayıt yok (bugünkü kural) | Q23 |
| 4 | "Kitap" | Hangi malzeme kartları kitaptır? | Bugün: bütün malzeme kartları (ayraç, kahve çekirdeği, bandrol dahil) | Kart tipine/özel koda göre yalnız kitaplar — tanımı iş verir | "kitap" geçen bütün sorular (Q25 ilk 20'nin 5'i kitap değil) |
| 5 | Etkinlik–yazar bağı | `new_new_etkinlik_contactBase` "etkinliğe katılan yazar" mıdır? | Evet: 9.012 bağ, kişilerin ~%97'si yazar işaretli → yazar bazında gider hesaplanır (toplam 9.275 ₺) | Hayır: Kural C10'daki "hesaplanamaz" kalır | Q49, Q77 |
| 6 | Yıl kopyaları | "Son üç baskı", "hiç sipariş vermemiş" gibi dönemsiz sorular kaç yıl okur? | Yalnız güncel kopya (2026): Q13 94 kitap, Q17 4 cari | Bütün kopyalar (2021–2026): Q13 1.705 kitap, Q17 1.826 cari | Q13, Q16, Q17 |
| 7 | Bedelsiz satırlar | "Maliyetin altında satış"ta bedelsiz (0 ₺) satırlar sayılır mı? | Sayılır: 745 müşteri, 42.956 satır | Sayılmaz: 253 müşteri | Q6 |
| 8 | Fiyat listesi | "Liste fiyatının altında" hangi listeye göre? (aynı kitap için aynı anda birçok kanal listesi geçerli, faturayı listeye bağlayan alan yok) | En düşük geçerli liste: 39.711 fatura · en yüksek öncelikli: 40.361 · en yeni: 40.355 | Herhangi bir geçerli liste: 62.507 (dün "doğru" sayılan, aşırı kapsayıcı) | Q7, Q80 |
| 9 | Yurtdışı hak | Oran hangi yıla ve hangi taraf tipine göre? | Sözleşme kayıt yılı + "Yurtdışı Alış": %19,80 → %9,04 | Satış+alış: %40,5 → %23,1 · başlangıç tarihi: %12,8 → %12,5 (düşüş kaybolur) | Q59 |
| 10 | "Bu ara" | Dönem söylemeyen "bu ara" nasıl okunur? | Netleştirme sorulur (bugünkü davranış, altında beklenti bu) | "Bu yıl" varsayılır (922.418.666,06 ₺) | Q19 |
| 11 | Bekleyen sipariş tutarı | Brüt mü, iskonto sonrası mı? | Liste fiyatıyla brüt: 18,06 Mn ₺ (bugünkü cevap, brüt olduğu söylenmiyor) | İskonto sonrası: 10,05 Mn ₺ | Q29, Q58 |

## Veriyle çürüyen kurallar (iş kararı değil, düzeltme; kapıdan geçirilerek yapılacak)

Bu kurallar 17–18 Eylül gecesi model yardımıyla yazılıp iş teyidi beklenmeden isteme girmişti; bağımsız ölçüm çürüttü:

- **Kural C10** (etkinlik yazarı "hesaplanamaz"): bağ ayrı tabloda var (bkz. karar 5).
- **Kural C11** (önerilen telif oranı): yanlış alanı gösteriyor (`new_olasitelif` = "Olası Telif Oranı"); adı birebir "Önerilen Telif Oranı" olan alan `new_yayinkurulutoplantilariBase`'te. Köprü %5,96, referans %5,64.
- **Kural C13** ("sipariş satırı"): başlık tablosunu anlatıyor; gerçek satır tablosu `new_siparissatiriBase`.
- **Kural C14** (indirim eşitliği): "≈ (toplam − indirimli toplam) / toplam" tutmuyor (%46,16; doğru %43,95; fark 156,2 Mn ₺ özel indirim).
- **Caveat** (asgari stok, "seviye kontrolü açık 125.682 satır"): bugün 0.
- **Kural 12** (karşılıksız çek, güncel durum okuması): bkz. karar 3.
