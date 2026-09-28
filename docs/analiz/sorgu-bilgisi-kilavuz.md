# Sorgu bilgisi — yayılım kılavuzu

Kullanıcı isteği (2026-09-28, birebir): «tüm hesaplama ve rakam verdiğimiz ekranlarda çalıştırdığımız sorguları info
olarak her kalemde ver ve kopyalanabilir olsun ama eksiksiz hepsinde istiyorum».

Tek kalıp vardır; her modül aynısını uygular. Örnek uygulamalar: M46 bütçe (`/butce`), M45 finansal raporlar
(`/finansal-raporlar`), M9 fiyatlama (`/fiyatlama`). Hangi ekranın hangi kalemi kaldı: `sorgu-bilgisi-envanteri.md`.

## Parçalar

| Parça | Dosya | Ne yapar |
|---|---|---|
| Sözleşme ve yardımcılar | `backend/semantic_bridge/provenance.py` | `Kaynaklar` kaydı, SQL'e değer yerleştirme, sır/teknoloji adı süzgeci, portal SQL'i derleme, kapsam denetimi |
| Modül kaynak dosyası | `backend/semantic_bridge/<modül>_kaynak.py` (paket içindeyse `<paket>/kaynak.py`) | Uç başına `for_<uç>()`: hangi rakam hangi sorgu ve hesaptan |
| Ön yüz tipi ve saf mantık | `src/canvas/components/sqlInfo.ts` | `Kaynaklar` tipi, alan çözümü, zincir toplama, kopyalama (http'de de çalışır) |
| Ön yüz bileşeni | `src/canvas/components/SqlInfo.tsx` | «i» düğmesi + pencere (telefonda alttan sayfa); `InfoLabel` başlık kısayolu |
| Kart kutuları | `Kpi` (`editorial/kit.tsx`), `Stat` (`pricing/parts.tsx`) | `info` özelliği: «i» kartın sağ üstünde, kartın düğmesinin dışında |
| Test | `backend/semantic_layer/tests/test_sorgu_bilgisi.py`, `src/canvas/components/sqlInfo.test.ts` | Örnek modüllerin her ucu + yardımcılar |
| Kabul | `scripts/acceptance/sorgu-bilgisi/` | Test sunucusunda her SQL'i gerçekten koşturur, doğrudan SQL referansları |
| Envanter denetimi | `scripts/analiz/sorgu_bilgisi_envanter.py` | Envanter ↔ menü + rota; eksik ekran kalmasın |

## Sözleşme (cevaptaki `kaynaklar`)

```json
"kaynaklar": {
  "sources":  { "<kimlik>": { "id", "connection": "logo|crm|portal", "connectionLabel", "database", "title", "description",
                              "sql": "<TAMAMI, değerler yerinde, kopyala-çalıştır>",
                              "stats": { "rows", "dbMs", "ranAt" } | null, "dataEnd", "period", "origin": ["<kimlik>"] } },
  "formulas": { "<ad>": { "name", "text": "net = Σ LINENET (7,8,9) − Σ LINENET (2,3) …", "inputs": ["<kimlik>|hesap:<ad>"] } },
  "fields":   { "<alan yolu>": "<kimlik>" | "hesap:<ad>" },
  "dataEnd", "asOf"
}
```

- **Alan yolu** cevabın JSON yoludur: `sirket.gercekCiro`, `yayinevleri[].hedefCiro`, `cards[]`. Bir yol altındaki bütün
  rakamları kapsar. Ön yüz bulamazsa yolu yukarı kısaltır (`sirket.gercekCiro` → `sirket`).
- **Satıra özel anahtar**: liste satırları farklı sorgulardan geliyorsa (özet kartları, plan başına toplam, nakit kalemi)
  `"cards[]:net-satis"`; ön yüz `row="net-satis"` verir. Yanına bütün satırları kapsayan genel anahtar da yazılır.
- **`origin`**: portal tablosundan (semantic_*) okunan rakamda gösterilen SQL uçta çalışan ifadedir; tabloyu dolduran asıl
  Logo/CRM sorgusu `origin`'dir (hangi yıl kopyası, kaç satır, ne zaman okundu). Önbellekten gelen rakamın «asıl SQL»i budur.
- **Hesap** (`formulas`): Python'da yapılan her işlem okunur bir formülle yazılır; girdileri sorgu ya da başka hesaptır.
- `connection` yalnız `logo | crm | portal`. Dış API ya da yüklenen dosyadan gelen rakamda SQL yoktur: onu besleyen portal
  tablosunun SQL'i + «hesap» metninde kaynağın adı («Search Console dışa aktarımı, gece eşitlemesi») yazılır.

## Arka uç: 3 adım

1. **Okuma ifadesini ayır.** Portal tablosunu okuyan `sa.select(...)` fonksiyonun içinden çıkar, `<ad>_stmt(...)` olarak
   yaz ve hem okumada hem kaynak kaydında onu kullan (gösterilen = çalışan). Örnek: `budget.sales_stmt`,
   `finance.account_totals_stmt`, `pricing.store.analyses_stmt`. Logo/CRM SQL'i zaten `*_sql(firma, yıl)` fonksiyonuysa
   aynen kullanılır; yenileme işi hangi firma kopyasını okuduysa meta kaydına `firm` yazılır (`budget` gider meta'sına eklendi).
2. **`<modül>_kaynak.py` yaz.** Uç başına:
   ```python
   def for_tracking(engine, tenant, out, logo_db) -> P.Kaynaklar:
       k = P.Kaynaklar(data_end=B.data_end(engine))
       logo = k.sorgu(f"logo.satis.{y}", "Logo satış satırları · 2026", "logo", src.sales_sql(firm, y),
                      database=logo_db, rows=m["rows"], ms=m["dbMs"], ran_at=m["_at"], period=f"{y} · Logo firma {firm}")
       act = k.portal("portal.satis", "Gerçekleşen satış", B.sales_stmt(y, y), engine, origin=[logo])
       k.alanlar({"sirket": k.hesap("sirket", F_SIRKET, [act, ...]), "aylar[]": ...})
       return k
   ```
   Parametreli SQL'de `k.sorgu(..., sql, params=[...] | {...})` — `?` ve `:ad` değerle değiştirilir (tarih SQL Server'da
   `'YYYYMMDD'`, metin `N'…'`). `{f}` gibi şablon metni asla verilmez; çalışmış metin yoksa kayıt açılmaz.
3. **Uca bağla** (tek satır): `return P.bagla(out, lambda: K.for_tracking(engine, tenant, out, logo_db()))`.
   `logo_db()` = `P.connection_database(bağlantı dosyası)` — dosyadan **yalnız** veritabanı adı okunur; Logo/CRM SQL'inin
   başına `USE [VT];` yazılır (SSMS'te kopyala-çalıştır). Kayıt kurulamazsa rakamlar yine döner, pencere nedeni yazar.

## Ön yüz: 2 adım

1. Cevap tipine `kaynaklar?: Kaynaklar` ekle (`import type { Kaynaklar } from '../components/sqlInfo'`).
2. Her rakamın yanına «i»:
   - Kart: `<Kpi … info={<SqlInfo k={d.kaynaklar} alan="sirket" label="Şirket satışı" />} />` (fiyatlamada `Stat`).
   - Tablo başlığı: `<th className={th}><InfoLabel k={d.kaynaklar} alan="items[].ciro">Hedef ciro</InfoLabel></th>`.
   - Liste satırı kendi sorgusundan: `<SqlInfo k={…} alan="cards[]" row={c.id} label={c.label} />`.
   - Grafik: panel başlığına `alan="aylar[]"`; cümle içindeki rakamda `className="ml-0.5"` ile satır içi.
   - Tıklanan kartın/satırın **içine** koyma (iç içe düğme olur): kartı `relative` bir kutuya al, «i»'yi sağ üste
     mutlak yerleştir (`Kpi`/`SummaryTab.Card`/`ScenariosTab` örnekleri).

Pencerede: başlık, veri sonu, hesap (formül), her sorgu için bağlantı · veritabanı, dönem, satır, süre, çalıştığı an, SQL'in
tamamı ve «Kopyala» (birden çok sorguda «Hepsini kopyala»). SQL metni yalnız «SQL'i göster ve kopyala» yetkisinde
(`ozellik:kart.sql-goster`) görünür; yetkisi olmayan formülü ve kaynağın adını görür, SQL yerine yetki notu çıkar.

## Test

- pytest: modülün her rakam ucu için
  ```python
  out = P.ekle(B.tracking(...), K.for_tracking(...))
  assert P.uncovered_numbers(out, K.NOT_RAKAM) == []   # kaynaksız rakam yok
  assert P.problems(out) == []                         # SQL dolu, yer tutucu yok, köken kayıtlı, sır izi yok
  ```
  `NOT_RAKAM`: rakam olmayan sayılar (yıl, ay numarası, sürüm, sayfa). Yeni bir rakam alanı eklenip kaynağı yazılmazsa
  test düşer — «eksiksiz» şartının bekçisi budur.
- vitest: yalnız yeni bir yardımcı yazıldıysa; bileşenin mantığı `sqlInfo.test.ts`'te sınanıyor.
- Kabul (sunucuda): `scripts/acceptance/sorgu-bilgisi/kabul.py` her kaynağın SQL'ini gerçekten koşturur (K3) ve en az bir
  doğrudan SQL referansı ekler (Logo sorgusunun toplamı = portal tablosunun toplamı gibi). Yeni modül için aynı dosyaya
  bir blok eklenir.

## Kurallar

- Gösterilen SQL çalışan SQL'dir; elle yeniden yazılmış «benzer» sorgu yok. Portal okuması `P.portal(stmt, engine)` ile
  çalışan ifadeden derlenir.
- SQL açıklama satırında model/araç/teknoloji adı olmaz; geçerse o satır atılır (`clean_sql`). Formül metninde geçerse kayıt
  reddedilir.
- Parola, anahtar, bağlantı dizesi hiçbir koşulda: `clean_sql` sır izi (`PWD=`, `Driver={…}`) ya da parola/anahtar kolonu
  okuyan SQL görürse kaydı reddeder (CRM kargo firmasının parola/anahtar kolonları buna dahildir).
- Kişisel veri: SQL metni gösterilir, sonuç satırı asla kayda girmez (yalnız satır sayısı).
- Rakam modelden gelmez; model metni olan ekranda «i» yalnız metnin dayandığı olguların sorgusunu gösterir.
- Sessiz tavan yok: sorgu bilgisi satır kesmez; listede görünen sayfa ile sorgunun tamamı farklıysa açıklamada yazılır.

## Sık hatalar

| Hata | Doğrusu |
|---|---|
| Şablon SQL göstermek (`LG_{f}_01_STLINE`, `?`) | Çalışmış metin (`snap["sql"]`, `*_sql(firma, yıl)`) ya da `params=` ile değer yerleştirme; `placeholders_left` boş olmalı |
| Portal okumasını elle yazılmış SQL metniyle göstermek | Okumayı `<ad>_stmt()`'e ayır, aynı ifadeyi `k.portal(...)`'a ver |
| Önbellekten gelen rakamda yalnız portal SQL'i | `origin=[Logo/CRM kaydı]` — asıl SQL tabloyu dolduran sorgudur |
| Firma kopyasını bilmeden Logo SQL'i kurmak | Yenileme işi meta kaydına `firm` yazsın; yoksa kayıt açılmaz (yanlış yıl kopyası göstermek yanlıştır) |
| «i»'yi tıklanan kartın içine koymak | Kart `relative` kutuda, «i» mutlak sağ üstte |
| Liste satırlarının hepsine aynı genel kaydı göstermek | Satır kendi sorgusundan geliyorsa `alan:row` anahtarı + `row` özelliği |
| Uç kimliği ile kaynak kimliğinin çakışması (iki modül aynı `logo.satis.2026`) | Modül öneki: bütçe `logo.satis.*`, finans `logo.fin.*`, fiyatlama `fiyatlama.*` |
| `USE [..]` satırını kaynağa elle yazmak | `database=` ver; satırı `sorgu()` ekler |
| Rakam olmayan sayıyı (yıl, sürüm) kaynaksız bırakıp testi geçirmek için alan uydurmak | `NOT_RAKAM`'a yaz |
| Kaynak kurulamayınca sessiz geçmek | `P.bagla` hata metnini `kaynaklar.error`'a yazar; pencere gösterir |
