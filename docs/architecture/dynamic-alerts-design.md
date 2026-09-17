# Dinamik uyarılar — tasarım (2026-09-15)

Kural: statik çözüm yok. Hangi prompt yazılırsa yazılsın aynı hattan geçer; örnek başına SQL, kalıp ya da bağ kodu yazılmaz.
Garanti: **yanlış uyarı sessizce çıkmaz** — kural ya doğrulanıp çalışır ya da ekranda nedeniyle reddedilir.

## 1. Canlı ölçüm (prod Logo, köprü :8795, 12 uyarı promptu)

| Sonuç | Adet | Not |
|---|---|---|
| Doğru cevap | 0 | |
| Sessiz yanlış | 1 | "Siparişten 10 gün sonra faturası kesilmemişse uyar" → 48.687 satır = 2026'daki bütün siparişler |
| Açıklama istedi / durdu | 8 | "geçmiş, aşan, düşen, yapmayan, edilmemiş" koşul fiilleri tanınmıyor |
| Eksik cevap | 1 | "geçen yılın aynı ayı" |
| Geçersiz SQL | 1 | "aynı müşteriye aynı gün birden fazla fatura" |

Sessiz yanlışın SQL'inde üç hata: ORFICHE→INVOICE `CLIENTREF` kardeş join'i (sipariş bağı değil), ters tarih mantığı,
**ORFICHE `LG_411` + INVOICE `LG_211` karışık firma** (physicalize hatası). Kapı geçirdi.
Rastgele 5 satırın bağımsız sorguyla kontrolü: 5/5'in faturası 0-2 gün içinde kesilmiş → çürütme adımı yakaladı.

Test kâhini (üründe değil): 10 günden eski, faturası olmayan sipariş = 297 (10,3 Mn ₺), 11'i kısmi faturalı.

## 2. Motor seviyesinde bulunan hatalar (uyarıdan bağımsız, sohbeti de etkiliyor)

1. `physicalize_sql` aynı sorguda iki dönem tablosunu farklı firmaya çözebiliyor (411 + 211).
2. `tools/schema-indexer/scanner/mssql.py` `_LOGO_TABLE_DESC` yanlış: ORFICHE TRCODE 1 aslında **satış** siparişi
   (LDDS: 1=Alınan, 2=Verilen), STATUS 2=Sevkedilemez (öneri değil), INVOICE 3/6 iade türleri ters. Veri doğruluyor:
   TRCODE 1 siparişlerin carileri Kitapyurdu/Amazon, bağlı irsaliyeler 7/8 (satış).
3. Kayıtlı SQL yeniden koşunca dönem birleşimi kaybolur (`run_sql` period almaz).
4. Göreli zaman ("son 60 gün") SQL'e sabit tarih olarak yazılır → dondurulan SQL bayatlar.
5. Uyarı çağrısı `sample_size=5`; tek değer dışı cevap hata.

## 3. Hat

```
prompt ─► A. Anlama ─► B. SQL ─► C. Deterministik kontroller ─► D. Çürütme ─► E. Önizleme+onay ─► kayıt
                                                                                                   │
                         15 dk ◄── H. Yeniden doğrulama ◄── G. Fark (yeni/kapanan) ◄── F. Çalıştırma ◄┘
```

**A. Anlama (LLM, JSON şema).** prompt → `{kayıt birimi, koşullar, zaman çapası (şimdiye göre), tetik: satır_var | yeni_satır | değer_eşik | değişim, belirsizlikler[]}`.
Belirsizlikler ekranda seçenekli soru olur (ör. "sipariş bazında mı satır bazında mı?").

**B. SQL (LLM, katalogdan).** Bağlam: ilgili tabloların LDDS ilişkileri ve resmi değer anlamları (`values_tr`).
Zorunlu biçim: yokluk = ilişki yolu üzerinden `NOT EXISTS`; yaş = `@ASOF`'a göre `DATEADD/DATEDIFF`; tarih sabiti yalnız promptta yazıyorsa.

**C. Deterministik kontroller (her kural için aynı kod).**
- Her join katalogdaki bir ilişkiye denk gelmeli; iki FK'nın aynı ebeveyne eşitlenmesi (kardeş join) reddedilir.
- Dönem tabloları tek firma/dönem kümesine çözülmeli.
- `@ASOF` dışında göreli tarih yok; `GETDATE()` yok.
- Anahtar kolon(lar) tüm sonuçta tekil (fan-out yok).
- Koşul uygulanmış mı: sonuç = aynı penceredeki tüm temel kayıtlar ise red (48.687 vakası).
- Zaman duyarlılığı: `@ASOF` ve `@ASOF-30` sonuçları; göreli zaman varken aynıysa red.
- Mevcut anlam kapısı (`unmet_obligations`).

**D. Çürütme (dinamik).** LLM, SQL'i görmeden, prompttan tek kayıt için "koşul doğru mu?" sorgusu yazar (`@KEY` parametreli).
Sonuçtan 5 rastgele kayıt → hepsi doğru; temel kümeden sonuçta olmayan 5 kayıt → hepsi yanlış olmalı.
Uyuşmazlık → bir onarım turu → sürerse ekranda uyuşmazlık gösterilir, kayıt yok.

**E. Önizleme.** SQL'den (prompttan değil) Türkçe geri çeviri, satır sayısı, ilk satırlar, kontrol listesi (yeşil/kırmızı), belirsizlik seçimleri.

**F. Çalıştırma.** Mantıksal SQL + `@ASOF=şimdi`; dönem `@ASOF`'tan türetilir, birleşim korunur; `run_complete` tüm satırlar.
Tazelik: kuralın tarih kolonunun son değeri → bayat veride durum `veri_bayat`, bildirim yok.

**G. Fark.** `semantic_alert_items (rule_id, key, first_seen, last_seen, closed_at, row_json)`; yeni kayıtlar tek özet e-postada; kapananlar düşer.

**H. Yeniden doğrulama.** Katalog sürümü değişince, yıl devrinde ya da SQL hata verince C+D otomatik koşar; geçmezse durum `doğrulanamadı`, bildirim yok.

## 4. Açık riskler

- Logo'da son kayıt 2026-08-17 (29 gün bayat) — bugün her kural `veri_bayat` görünür.
- Yıl devri: Aralık 2025'in 109 açık siparişi 2026 firmasındaki faturasına ref ile bağlanamıyor; D adımı bunu uyuşmazlık olarak gösterir, çözümü devir kaydının incelenmesi.
- LLM ucu yük altında 529 verebiliyor; kural kurulumu 1-3 dk sürebilir → kurulum arka plan işi + ilerleme göstergesi.
