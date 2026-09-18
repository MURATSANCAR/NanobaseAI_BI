# Diakritik çelişkilerinde sözlük tanığı — ölçüm, üretime bağlı değil (18 Eylül 2026)

## Genel soru

Okuyucuların yalnız Türkçe diakritikte ayrıştığı bölgelerde (ı/i, ş/s, ğ/g, ö/o, ü/u, ç/c) iki ucuz, model çağırmayan tanık işe yarar mı: (1) Unicode eşdeğerliği (NFC), (2) okuyucuların **zaten ürettiği** iki sözcükten yalnız birinin geçerli Türkçe sözcük biçimi olması. Tanık metin üretmez ve hiçbir okumayı değiştirmez.

## Gerçek ölçüm

Ortam `nanobase-direct:/data/nanobaseai/editor/runtime/morph-probe`, çözümleyici `zeyrek 0.1.3`. Sürücü `apps/editor/scripts/probe-diacritic-witness.py`. Girdi: gerçek API/PG eşliği kayıtlı `ocr-residual-audit-14a79646-….json` (328 inceleme bölgesi; PP-OCRv5 bölgesel, Tesseract tam sayfa, PSM 7/13 yeniden okuma, kullanılabilir PDF metni). Model çağrısı 0, yazım 0, metin düzeltmesi 0. Kanıt: `evidence/diacritic-witness-probe-20260918T115650823394Z.json`.

| Bulgu | Sonuç |
|---|---|
| NFC öncesi farklı, NFC sonrası eşit okuma çifti | **0** — OCRTurk'te raporlanan "harf + birleşen işaret" bölünmesi bu veride yok; varsayım reddedildi |
| Paddle ↔ Tesseract yalnız diakritik farkı olan bölge | 74 |
| Bütün farklı sözcüklerinde tam olarak bir aday geçerli olan bölge | 52 (%70); 22 bölge kararsız |
| Sözcük düzeyi: yalnız Tesseract geçerli / yalnız Paddle geçerli / ikisi de / hiçbiri | 39 / 19 / 19 / 5 |
| Tanığın seçtiği sözcük, hizalı temiz PDF sözcüğüyle aynı mı | 56 karşılaştırmada **55 aynı, 1 farklı** |
| Aynı ölçüm, en az 3 harfli sözcüklerde | 53 / 53 aynı |
| Türkçe alfabesinde olmayan harf üreten Paddle bölgesi | 9: `ș` U+0219 (5), `ï` (2), `í` (1), Yunanca `ς` (1) |

Tek fark iki harfli bir satır sonu parçasıdır (`ki` / `kı`): parça tek başına sözcük olmadığından sözlük tanığı güvenilmez. Hata iki okuyucuya da dağılıyor: Paddle çoğunlukla `ğ`/`ı` düşürüyor (`serinligi`, `işık`), Tesseract bazı satırlarda bütün diakritikleri düşürüyor (`cikaracaktim`, `calistiktan`). Bu yüzden "hep X okuyucusuna güven" kuralı yanlış olur.

`ș` (Romence virgüllü s) ile `ş` (Türkçe çengelli s) ayrı kod noktalarıdır ve NFC ile eşitlenmez; çok dilli Latin tanıyıcının bilinen karışıklığıdır.

## Çıkarım ve önerilen genel kural (uygulanmadı)

Mevcut kapıda tek bağımsız okuyucunun itirazı bölgeyi incelemede tutuyor. Ölçüm şu dar kuralın güvenli olabileceğini gösteriyor: itiraz eden okuma destekli okumadan **yalnız diakritikte** ayrışıyorsa, destekli sözcük geçerli ve itiraz eden sözcük geçersiz bir Türkçe biçimse, sözcük en az 3 harfliyse ve satır sonu tire parçası değilse, itiraz ayrı ve denetlenebilir bir gerekçeyle (`DIACRITIC_VETO_NOT_A_WORD`) geçersiz sayılabilir. İki aday da geçerliyse (`sırada/sirada`, `işte/ıste`) ya da hiçbiri değilse bölge incelemede kalır. Seçilen dizgi her zaman bir okuyucunun ham çıktısıdır.

## Açık kapsam

- Doğruluk yalnız PDF metni temiz olan bölgelerde ölçülebildi. Kuralın asıl gerekeceği, PDF katmanı bozuk sayfalarda bağımsız referans yok: **DOĞRULANAMADI**.
- Tek kitap, eski V5 nesli. Başka kitap ve güncel nesil ölçümü yok.
- `zeyrek` sözlüğü gevşek: `vardi`, `sirada`, `gun`, `ıstanbul` geçerli sayıldı. Bu, kararsız sayısını artırır (güvenli yön) ama gerçek Zemberek belirsizlik gidericisiyle yeniden ölçülmeli.
- Özel adlar, uydurma adlar ve yansımalar sözlükte yok; kural bunlarda karar vermez.
- Kural ve `ș→ş` dil profili eşlemesi kodlanmadı, kapıya bağlanmadı; `semantic_acceptance=false`.
