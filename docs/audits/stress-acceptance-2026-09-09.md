# Geniş kabul testi — 9 Eylül 2026

## Kapsam ve yöntem

Test sayıları aynı sorunun tekrarları değildir; ancak bunları bağımsız insan sorusu sayısı gibi yorumlamak da yanlıştır. Kontrollü matris 3 yıl × 12 ay × 5 şehir × 4 kanal × 3 işlem kapsamı × 4 ölçü ifadesi × 3 ifade düzeni = 25.920 benzersiz metindir. Ölçü ifadelerinden ikisi eş anlamlıdır. 7.200 sentetik fatura; iade/satış/iptal, şehir, kanal, ay ve yıl açısından birbirinden ayrılabilen tutarlar içerir. Beklenen sayı, SQL veya çözülmüş plandan okunmaz; bağımsız Python satır filtresiyle hesaplanır. Bu yol LLM kullanmaz.

AST kümesi 8 bozulma sınıfını 1.000 ad/değer varyantında ve 1.000 doğru kontrolle sınar. 9.000 SQL, 9.000 farklı saldırı sınıfı demek değildir. Belirsizlik kümesi 432 metin varyantıdır; gerçek LLM çağrısı içermez.

## Sonuçlar

| Küme | Sayı | Sonuç |
|---|---:|---|
| Sayısal soru matrisi | 25.920 | 25.920 doğru sayı; yanıltıcı ay adı kolonlarıyla da geçti |
| Bozulmuş SQL | 8.000 | Tamamı reddedildi |
| Doğru SQL kontrolleri | 1.000 | Tamamı kabul edildi |
| Belirsiz iş tanımı | 432 | 288 hedefli netleştirme, 144 desteksiz; yürütülebilir SQL yok |
| Semantik birim testleri | 399 | Tamamı geçti |
| Gerçek veri / referans SQL | 4 | Düzeltmeden sonra 4/4 sayısal eşleşme |

## Canlı ölçümün bulduğu gerçek hata

Gerçek katalogda MART ve NISAN adlı kolonlar var. “Mart 2026” ile “Nisan 2026” hem tarih hem de fiziksel kolon=2026 sanılıyor; yanlış ek koşul iki doğru soruyu INCOMPLETE_ANSWER'a düşürüyordu. Küçük sentetik şemada bu kolonlar olmadığı için ilk matris bunu yakalamadı.

Düzeltme: ayrıştırılmış tarih ifadesi, açık = veya : ataması yoksa ikinci kez fiziksel kod sayılmaz. Açık MART=2026 ve TRCODE 8 korunur. 12 ay ve iki açık kolon ataması regresyon testi eklendi. Test matrisine yanıltıcı ay adı kolonları eklenerek kapsam genişletildi. question_facts.py sunucuya alındı; kaynak yedeği /tmp/question_facts-before-acceptance.py.

| Yeni yazılan soru | Önce | Sonra |
|---|---|---|
| Mart 2026 toptan satış tutarı | Gereksiz red | Referansla aynı |
| Mayıs 2026 perakende satış tutarı | Referansla aynı | Referansla aynı |
| Şubat 2026 net ciro | Referansla aynı | Referansla aynı |
| Nisan 2026 kanal bazında net ciro | Gereksiz red | Referansla aynı |

İlk karşılaştırma aracında sözlük satırlarını değerler yerine anahtarlarıyla karşılaştıran hata düzeltildi; iki sayısal fark iddiası ürüne ait değildi. live-before-fix.json içindeki reference_equals_generated alanı düzeltilmiş değerlendirmedir; eski correct alanı hatalı ilk ölçümden kalır ve kullanılmamalıdır.

Bu dört soru bu çalışma için model tarafından yazıldı; saklı gerçek kullanıcı korpusu değildir. Düzeltmede kullanıldıkları için artık regresyon örneğidir. Genel gerçek kullanıcı başarı yüzdesi çıkarılamaz.

## İşletim ve arayüz

- Tam metadata yedeği: /data/nanobaseai/bi/backups/metadata-acceptance-1788906782.dump, 40.356.618 bayt. Arşiv kontrolü başarılı. Ayrı geçici veritabanına restore başarılı, 90 public tablo; geçici veritabanı temizlendi. Üretim verisi restore hedefi yapılmadı.
- Eski gece işi 8 Eylül 02:00–04:00 arasında timeout olmuş. Sonradan fark taraması için override eklenmiş; yeni sürümün başarılı koşu kaydı henüz yok. Sıradaki planlı koşu 9 Eylül 02:00.
- Sunucudaki nightly-semantic.sh statik incelemesinde sertifikalama sonrası kalite hatası yalnız loglanıyor; otomatik rollback yok. İç reload çağrılarında admin başlığı yok ve hatalar yok sayılıyor. Bu yeni işletim riski geniş sorgu matrisinin geçmesiyle kapanmış sayılmaz.
- Tarayıcı Timaş basic-auth sınırına ulaştı. Mevcut kullanıcı girişi sağlanmadığından soru → takip → grafik → Excel zinciri gerçek UI üzerinden tamamlanmadı. Kimlik doğrulama aşılmadı; API testi UI testi diye sunulmadı.
- “Pahalı”, “kazanç”, işlem yönü gibi kavramların iş tanımını test sistemi onaylayamaz. Desteksiz cevaplar başarıya eklenmedi.

## Yeniden çalıştırma / kanıt

Repo kökünde PYTHONPATH=backend ile tests/stress/semantic_matrix.py, obligation_mutations.py ve ambiguous_matrix.py çalışır. live_reference.py sunucunun mevcut SEMANTIC_* ortamını ve salt-okunur kaynak bağlantısını kullanır. İstatistikler artifacts/stress altında; credential içermez. UI girişi ve bağımsız gerçek kullanıcı korpusu tamamlanmadan sınırsız üretim doğruluğu iddia edilmez.
