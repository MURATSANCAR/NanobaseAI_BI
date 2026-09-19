# Görev: altın cevap referansları (salt okunur)

Türkçe doğal dil → SQL üreten bir BI köprüsünün 100 soruluk zor test setinde, sana verilen soru numaraları için
**bağımsız referans SQL** yaz, canlı veritabanında koştur, köprünün bugünkü cevabıyla karşılaştır ve altın girişleri
bir JSON dosyasına yaz. Hiçbir kodu, kataloğu, kuralı ya da servisi DEĞİŞTİRME; köprüye soru SORMA (tek işleyicili,
başkası ölçüm yapıyor). Yalnız SELECT çalıştır. Parola/bağlantı dosyası içeriği yazdırma.

## Veriler
- Sorular: `tests/text2sql/set100.jsonl` (satır sırası = soru numarası; alanlar `id, soru, kaynak (logo|crm|ikisi), beklenen`).
- Köprünün bugünkü cevapları (sunucuda): `nanobase-direct:~/testset/run100-0918c.jsonl` — alanlar `id, type, rows, summary,
  explanation, sql`. `sql` yalnız köprünün hangi tabloya baktığına dair İPUCUDUR; referansı ondan kopyalama, tanımı kendin kur.
- İş tanımları: `docs/TIMAS-IS-TANIMLARI.md`, `configs/semantic/knowledge/logo/knowledge/rules/logo-erp.md`,
  `.../rules/crm-timas.md`, `.../metrics/logo-timas.md`, `.../caveats/logo-timas.md`. Dün geceki doğrulama notları:
  `docs/GELISTIRME-GUNLUGU.md` (ara: "Soru 12", "Q28–Q59", "karne").
- Örnek altın girişler ve kontrol türleri: `tests/text2sql/answers-set100.json`, kapı: `tests/text2sql/answer-gate.py`.

## Veritabanı gerçekleri
- Tek şirket; tablo önekleri YIL kopyasıdır: `LG_411_*` = 2026, `LG_211_*` = 2021–2025 (dönemli tablolar `LG_411_01_STLINE`,
  kartlar `LG_411_CLCARD`, `LG_411_ITEMS`). "Bu yıl" = 2026. 211 tabloları çok büyük: tarih filtresi olmadan okuma, zaman aşımına uğrar.
- Logo = SQL Server `LOGO_DB`; CRM = ayrı SQL Server, veritabanı `Timas_MSCRM`, **büyük/küçük harf duyarlı**: fiziksel tablo adını
  katalogdan al (aşağıdaki `phys()`); her CRM tablosunda `statecode = 0` aktif kayıttır.
- İki sunucu tek SQL'de birleşmez. `kaynak: ikisi` sorularında kontrol olarak `lookup` kullan (anahtar başına nokta sorgusu).

## Sorgu koşturma (Mac'te işlem yok; sunucuda koşar)
Betiği scratch'e yaz, ssh ile stdin'den ver:
```bash
ssh -o ConnectTimeout=15 nanobase-direct '/data/nanobaseai/bi/semantic-venv/bin/python -' < /yol/betik.py
```
Betik iskeleti:
```python
import sys, json, os
sys.path.insert(0, "/data/nanobaseai/bi/frontend/backend")
from semantic_layer.profiler.connectors import connector_from_file
logo = connector_from_file("/data/nanobaseai/bi/secrets/logo-mssql-connection.json")
crm  = connector_from_file("/data/nanobaseai/bi/secrets/crm-mssql-connection.json")
rows = logo.execute("SELECT ...", 100000)[1]        # -> list[dict]
```
CRM fiziksel tablo adı (katalogdan; DSN sudo ile okunur):
```bash
ssh nanobase-direct 'DSN=$(sudo grep -E "^SEMANTIC_STORE_DSN=" /etc/nanobase/semantic-bridge.env | cut -d= -f2- | sed "s/+psycopg2//"); psql "$DSN" -Atc "select entity, schema_name, table_name from sl_schema_profile where upper(entity) in ('"'"'NEW_SOZLESMEBASE'"'"')"'
```
Kolon adları için `INFORMATION_SCHEMA.COLUMNS` kullan. Aynı anda başka ajanlar da sorguluyor: ağır sorguyu daralt, 60 sn'yi
aşan sorguyu yeniden tasarla; `08001`/`HYT00` bağlantı hatası alırsan 1 dk bekleyip bir kez daha dene, sürerse raporla.

## Altın giriş biçimi
```json
{"n": 28, "id": "A030", "soru": "...", "kaynak": "logo", "holdout": false,
 "expect": "answer",            // "answer" | "deny" | "clarify" | ["deny","answer"] (birden çok dürüst sonuç)
 "verified": true,              // referans ile köprünün bugünkü cevabı UYUŞUYORSA true; uyuşmuyorsa false + note'ta fark
 "source": "logo",              // referans SQL'in koşacağı yer: "logo" | "crm"
 "reference_sql": "SELECT ...", // bağımsız; göreli dönemleri GETDATE() ile kendisi hesaplasın
 "checks": [ {"kind":"rows","tolerance":0} ],
 "note": "tarih, ölçülen değerler, tanımın dayanağı, köprü cevabıyla fark"}
```
`holdout`: `tests/text2sql/set100-split.json` içindeki listede ise true. Kontrol türleri: `rows` (satır sayısı; referans satır
sayısıyla), `value` (tek değer: `{"kind":"value","answer":["kolon_adayı","*"],"reference":"ref_kolonu","tolerance":0}` — `"*"` =
cevaptaki ilk sayısal kolon), `sum`, `pairs` (anahtar→değer; `answer_key`/`answer_value` aday LİSTESİ olabilir çünkü kolon adı
model koşusuna göre değişir), `lookup` (anahtar başına nokta sorgusu, `{key}` yer tutucusu), `empty` (boş cevap beklenir).
Sayımlarda `tolerance: 0`. Köprünün cevabı dürüst ret ise (veri yok / tanım yok) ve veritabanı bunu doğruluyorsa `expect:"deny"`
ya da `["deny","answer"]` + `empty`, reddin dayandığı veri durumunu gösteren bir referans SQL ile.

## Karar kuralları
- Referansı İŞ TANIMINDAN kur. Köprünün cevabı referansla uyuşmuyorsa referansı köprüye uydurma: `verified:false` yaz ve
  farkın nedenini `note`'a yaz (ör. "model 'tamamen'i 'hiç' okumuş; 6.179 / referans 6.181"). Bu bulgular değerlidir.
- Tanım belirsizse ya da veri yoksa uydurma: girişi `"expect": null, "verified": false` ile yaz, `note`'ta neyin eksik olduğunu söyle.
- Yalnız sana verilen sorular. Çıktı dosyası dışında hiçbir dosyayı değiştirme; git commit yapma.

## Çıktı
`tests/text2sql/gold-parts/part-<ilk>-<son>.json` → `{"cases":[...]}` (n'e göre sıralı, geçerli JSON). Son mesajında kısa özet ver:
kaç soru verified, kaçında köprü cevabı referansla uyuşmadı (hangileri, neden), kaçı belirsiz kaldı.
