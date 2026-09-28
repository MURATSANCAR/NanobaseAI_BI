"""M6 Telif ve sözleşme: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`).

Kaynak kimliklerinin öneki `sozlesme.`. Üç tür kaynak var:

- **CRM portföyü** (liste, özet, sözleşme sayfasının CRM hâli, seçiciler): istek anında CRM'den okunur. Liste ve özet
  uçlarında gösterilen metin, uçta çalışan `editorial.*_sql(...)` metninin kendisidir (değerler yerinde); sözleşme
  sayfası ve seçicilerde çalıştırıcının döndürdüğü çalışan metin (`physicalSql`) kaydedilir (`Kayit`).
- **Portal kayıtları** (taslak, zeyilname, ödeme takvimi, hakediş, şablon): elle girilir; gösterilen SQL uçta çalışan
  SQLAlchemy ifadesidir (`contracts.*_stmt`).
- **Hakediş hesabı**: Logo satış görünümlerinden okunur; hesap anında çalışan Logo/CRM metni hesap sonucunun yanında
  saklanır (`calc.sorgular`), kaydedilen hakedişte de aynı metin görünür.

Kişisel veri: SQL metni gösterilir, sonuç satırı kayda girmez (yalnız satır sayısı).
"""
from __future__ import annotations

import time
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge import contracts as C
from semantic_bridge import editorial as E
from semantic_bridge import provenance as P

# ------------------------------------------------------------------ formüller (ekranda okunur metin)

F_OZET = ("Tek CRM sorgusunda etkin (statecode = 0) sözleşmeler sayılır. Yürürlükte = durumu Aktif - Sözleşme, Aktif "
          "(Proje) ya da Aktif - Yenileme; yenilemede = Aktif - Yenileme; «N günde bitiyor» = yürürlükte, süresiz "
          "olmayan ve bitişi bugün ile bugün + N gün arasında olan; ortalama telif = yürürlükteki sözleşmelerde karton "
          "kapak telif oranı (new_Telif) sıfırdan büyük olanların ortalaması, yanındaki sayı bu oranı dolu sözleşme "
          "sayısıdır. N (uyarı günü) Yönetim ayarıdır (EDITORIAL_CONTRACT_WARN_DAYS, varsayılan 60).")
F_SECENEK = "Süzgeç seçeneğindeki sayı = o durumdaki (ya da tipteki) etkin CRM sözleşmesi sayısı."
F_LISTE = ("Liste: süzgece uyan etkin CRM sözleşmeleri, sayfa başına 50 kayıt (toplam ayrı sayım sorgusundan). Kalan gün = "
           "bitiş − bugün (CRM sorgusunda DATEDIFF). Telif oranları sözleşme kartındaki biçim oranlarıdır; avans "
           "sözleşmedeki avans tutarı; taraf payı taraf kaydındaki ödeme payıdır (new_Odeme). Kitaplar ve taraflar "
           "yalnız bu sayfadaki sözleşmeler için okunur.")
F_PORTAL_FARK = ("«Portalda» rozeti: sözleşme portalda düzenlenmişse portal kaydının durumu; «N fark» = portal şartları "
                 "ile kaydın portala alındığı andaki CRM kopyası arasında değişen alan sayısı.")
F_KAYITLAR = ("Portal kayıtları: portalda açılan ya da düzenlenen bütün sözleşmeler (elle girilir). Arama süzgeci satırlar "
              "okunduktan sonra uygulanır. Satırdaki «N ödeme gecikti» = bekleyen (planlandı) ödemelerden vadesi bugünden "
              "önce olanların sayısı; «sıradaki ödeme» = bekleyen ödemelerin en yakın vadesi. Sekme rozeti = listedeki "
              "kayıt sayısı.")
F_SARTLAR = ("Şartlar (oranlar, avans, tek ödeme, stopaj, iskonto, pay, kapak fiyatı, süre, dönem, vade, ilk baskı) portal "
             "kaydında ekrandan girilir; CRM'den alınan kayıtta ilk değerler CRM sözleşmesinden gelir.")
F_CRM = ("CRM sözleşmesi: başlık (oranlar, avans, tek ödeme, iskonto, süre, haklar), kitaplar (stok kodu, ISBN, kapak "
         "fiyatı new_kdvdahilfiyat; e-kitap stok kodu ayrı satır) ve taraflar (pay new_Odeme) üç sorguda okunur; ana "
         "sözleşme ve bağlı kayıtlar dördüncü sorgudan. Rol, yazar/mütercim/çizer metninden çıkarılır.")
F_FARK = ("CRM ile fark = CRM sözleşmesinin bugünkü şartları ile portal şartları arasında değişen alanlar (her alan "
          "eski → yeni). Portal CRM'e yazmaz; bu değerler CRM'de elle güncellenir.")
F_ODEME = ("Ödeme takvimi elle girilir (avans, tek ödeme, diğer) ya da onaylanan hakedişten gelir. «Vadesi geçti» = "
           "durumu planlandı ve vadesi bugünden önce. «Bekleyen» = planlandı durumundaki ödemelerin tutar toplamı, para "
           "birimine göre ayrı; sekme rozeti bekleyen ödeme sayısıdır.")
F_ZEYIL = "Zeyilname sayısı = sözleşmenin bütün zeyilnameleri (taslak, imzalı, iptal); değişen alanlar eski → yeni."
F_GECMIS = "Geçmiş sayısı = sözleşmenin bütün değişiklik kayıtları (kim, ne zaman, ne değişti)."
F_HAKEDIS_SAYI = "Hakediş sekmesindeki sayı = iptal edilmemiş hakedişler (taslak ve onaylı)."
F_HAKEDIS = ("Hakediş hesabı: satır telifi = matrah × oran. Satıştan ödemede satış Logo satış görünümlerinden (yalnız "
             "faturalı malzeme satırı) kitabın stok koduyla ay ay okunur, iade satırları adetten ve tutardan düşülür. Net "
             "esasta matrah = dönemin net satış tutarı (Σ Net Tutar); brüt esasta matrah = Σ ay (net adet × o ayın kapak "
             "fiyatı), kapak fiyatı = ayın en yüksek satır birim fiyatı; elle girilen kapak fiyatı önce gelir, Logo'da "
             "fiyat yoksa CRM'deki kapak fiyatı. Baskıdan ödemede matrah = elle girilen basılan adet × kapak fiyatı. "
             "Hesaplama iskontosu varsa matrah × (1 − iskonto). Kademeli ödemede oran, sözleşme başından dönem başına "
             "kadar birikmiş adede göre dilim dilim uygulanır. Satır taraflara pay oranında bölünür (pay boş ya da 0 ise "
             "eşit). Brüt telif = Σ satır telifi (TL); sözleşme yabancı paradaysa brüt ÷ dönem sonu kuru (elle girilen "
             "kur ya da TCMB'nin o gün / önceki iş günü döviz alış kuru). Tutar = brüt + önceki dönemden devreden eksi "
             "tutar. Avans mahsubu = en çok (avans − önceki onaylı hakedişlerde düşülen) kadar, tutarı aşmadan; tutar "
             "eksiyse ödeme yok, eksi tutar sonraki döneme devreder. Stopaj = (tutar − mahsup) × stopaj oranı; ödenecek "
             "net = tutar − mahsup − stopaj.")
F_SABLON = ("Şablon alan sayısı = şablon metnindeki {{alan}} yer tutucuları ile yüklenen Word dosyasındakilerin "
            "birleşimi (tekrarsız); tanınmayan alan listede olmayan yer tutucudur.")
F_TAKVIM = ("Ödeme takvimi: bütün portal sözleşmelerinin ödemeleri, vadeye göre. Bekleyen = listede durumu planlandı olan "
            "ödeme sayısı; vadesi geçen = bunlardan vadesi bugünden önce olanlar. Toplam (para birimi) = listedeki "
            "ödemelerin tutar toplamı; «vadesi geçmiş» = vadesi geçenlerin tutar toplamı. Ödenen ödemede gösterilen "
            "tutar ödendi işaretlenirken girilen tutardır.")
F_ARAMA = ("CRM seçicisi: arama metni kitap adında, stok kodunda ya da ISBN'de (kişi/firma seçicisinde adda) aranır; "
           "«N içinden N» = CRM'deki bütün eşleşme (COUNT(*) OVER ()) ve bu sayfayla birlikte gösterilen kayıt sayısı. "
           "Sayfa 20 kayıttır; e-kitap stok kodu olan kitap kartı listede iki satır olur.")

#: Rakam olmayan sayılar: sayfa ve sayfa boyu, kayıt sürümü, zeyilname sıra numarası.
NOT_RAKAM = ("page", "pageSize", "items[].version", "record.version", "version", "addenda[].seq")


# ------------------------------------------------------------------ çalışan sorgu kaydı


def _now() -> float:
    return time.time()


class Kayit:
    """Uçta çalışan Logo/CRM sorgularının kaydı: metin (çalıştırıcının çalıştırdığı hâli), satır sayısı, süre ve an.
    Sonuç satırları KAYDA GİRMEZ. Kayıt JSON'a yazılabilir sözlüklerdir (hesap sonucunun yanında saklanır)."""

    def __init__(self) -> None:
        self.items: list[dict[str, Any]] = []

    def add(self, conn: str, sql: str, *, rows: Optional[int] = None, ms: Optional[int] = None, at: Any = None,
            cached: bool = False, title: Optional[str] = None) -> dict[str, Any]:
        item = {"conn": conn, "title": title or baslik(sql, conn), "sql": sql, "rows": rows, "dbMs": ms,
                "at": at if at is not None else _now(), "cached": bool(cached)}
        self.items.append(item)
        return item

    def res(self, run: Callable[[str], dict[str, Any]], conn: str = "crm") -> Callable[[str], dict[str, Any]]:
        """Köprünün `run_sql` çıktısı (sözlük) döndüren çalıştırıcıyı sarar; çalışan metin `physicalSql`dir."""
        def wrapped(sql: str) -> dict[str, Any]:
            t0 = time.monotonic()
            out = run(sql)
            recs = out.get("records") if isinstance(out, dict) else None
            self.add(conn, (out or {}).get("physicalSql") or sql,
                     rows=out.get("totalRows") if out.get("totalRows") is not None else (len(recs) if isinstance(recs, list) else None),
                     ms=out.get("dbMs") if out.get("dbMs") is not None else int((time.monotonic() - t0) * 1000),
                     at=out.get("computedAt") or _now(), cached=bool(out.get("cached")))
            return out
        return wrapped

    def rows(self, run: Callable[[str], list[dict[str, Any]]], conn: str) -> Callable[[str], list[dict[str, Any]]]:
        """Satır listesi döndüren çalıştırıcıyı (`budget_sources.runner`) sarar."""
        def wrapped(sql: str) -> list[dict[str, Any]]:
            t0 = time.monotonic()
            out = run(sql)
            self.add(conn, sql, rows=len(out), ms=int((time.monotonic() - t0) * 1000))
            return out
        return wrapped


def baslik(sql: str, conn: str = "") -> str:
    """Kayıtlı sorgunun ekrandaki adı (metnin okuduğu tablodan)."""
    s = sql or ""
    rules = (
        ("sys.views", "Logo'daki yıllık satış görünümleri"),
        ("[Fatura Tarihi] DESC", "Logo satış verisinin son günü"),
        ("[Malzeme/Hizmet Kodu]", "Logo satış satırları (stok kodu × ay, satış / iade)"),
        ("StringMapBase", "CRM seçim listesi etiketleri"),
        ("new_KorumaDEser", "CRM kitaba bağlı sözleşmeler (hak bitleri)"),
        ("new_SzlemeYenilenmeSklyl", "CRM yenileme penceresi (bitişi yaklaşan ya da geçmiş sözleşmeler)"),
        ("new_haklaraciklama AS metin", "CRM hak açıklamaları"),
        ("new_SozlemeninSahibi", "CRM sözleşme başlıkları (oran, avans, süre, haklar)"),
        ("new_sozlesmetarafiBase", "CRM sözleşme tarafları"),
        ("new_new_sozlesme_new_kitapBase", "CRM sözleşme kitapları"),
        ("new_anasozlesmeid) =", "CRM ana ve bağlı sözleşmeler"),
        ("new_sozlesmeBase", "CRM sözleşmeleri"),
        ("ContactBase", "CRM kişi ve firma arama"),
        ("new_kitapBase", "CRM kitap kartı"),
    )
    for marker, title in rules:
        if marker in s:
            return title
    return "Logo sorgusu" if conn == "logo" else "CRM sorgusu"


def kaydet(k: P.Kaynaklar, prefix: str, items: Iterable[dict[str, Any]], dbs: dict[str, Optional[str]],
           description: str = "", period: Optional[str] = None) -> list[str]:
    """Kayıtlı çalışan sorguları kaynak olarak ekler (kimlik `<önek>.<sıra>`). Metni gösterilemeyen sorgu atlanmaz:
    kayıt kurulamazsa hata yükselir, `P.bagla` ekrana yazar."""
    ids = []
    for i, it in enumerate(items or []):
        conn = it.get("conn") if it.get("conn") in ("logo", "crm") else "crm"
        note = " Sonuç bu istekte önbellekten verildi; sorgu gösterilen anda çalıştı." if it.get("cached") else ""
        ids.append(k.sorgu(f"{prefix}.{i + 1}", it.get("title") or baslik(it.get("sql") or "", conn), conn, it["sql"],
                           database=dbs.get(conn), rows=it.get("rows"), ms=it.get("dbMs"), ran_at=it.get("at"),
                           description=(description + note).strip(), period=period))
    return ids


def crm_db(prefix_or_schema: str) -> Optional[str]:
    """CRM şemasının (ör. `Timas_MSCRM.dbo`) veritabanı adı; SQL üç parçalı adla yazılıdır, `USE` satırı buna göre."""
    db, _, _ = (prefix_or_schema or "").strip().rstrip(".").rpartition(".")
    return db or None


def settings_src(k: P.Kaynaklar, engine: Any, sid: str, title: str, keys: Iterable[str], description: str) -> str:
    """Yönetim ekranında girilen ayarların okuması (girilmeyen ayar ortam değerinden ya da varsayılandan gelir)."""
    from semantic_bridge import admin as ADM

    if sid in k.sources:
        return sid
    return k.portal(sid, title, sa.select(ADM.SETTINGS.c.key, ADM.SETTINGS.c.value).where(ADM.SETTINGS.c.key.in_(sorted(keys))),
                    engine, description=description)


def _stats(out: dict[str, Any]) -> dict[str, Any]:
    db = (out or {}).get("db") or {}
    return {"ms": db.get("dbMs"), "ran_at": db.get("computedAt")}


# ------------------------------------------------------------------ CRM portföyü (app.py uçları)


def for_summary(schema: str, out: dict[str, Any], engine: Any = None) -> P.Kaynaklar:
    """`GET /api/v1/editorial/contracts/summary`: yürürlükte, yenilemede, N günde bitiyor, ortalama telif, süzgeç sayıları."""
    k = P.Kaynaklar()
    db = crm_db(E._prefix(schema))
    warn = int(out.get("warnDays") or 60)
    ozet = k.sorgu("sozlesme.crm.ozet", "CRM sözleşme özeti", "crm", E.summary_sql(schema, warn), database=db, rows=1,
                   description=f"Uyarı günü {warn} ile çalıştı; tarih koşulu sorgunun çalıştığı günün tarihidir (GETDATE).",
                   **_stats(out))
    durum = k.sorgu("sozlesme.crm.durumlar", "CRM sözleşme durumları (süzgeç)", "crm", E.facet_sql(schema, "statuscode"),
                    database=db, rows=len(out.get("statuses") or []))
    tip = k.sorgu("sozlesme.crm.tipler", "CRM sözleşme tipleri (süzgeç)", "crm", E.facet_sql(schema, "new_SozlesmeTipi"),
                  database=db, rows=len(out.get("kinds") or []))
    inputs = [ozet]
    if engine is not None:
        inputs.append(settings_src(k, engine, "sozlesme.ayar", "Sözleşme uyarı günü ayarı", ["EDITORIAL_CONTRACT_WARN_DAYS"],
                                   "Yönetim ekranında girilen uyarı günü; girilmediyse ortam değeri ya da 60."))
    f = k.hesap("ozet", F_OZET, inputs)
    k.alanlar({"total": f, "active": f, "renewal": f, "expiring": f, "avgRoyalty": f, "avgRoyaltyOver": f, "warnDays": f,
               "db": ozet, "statuses[]": k.hesap("durumlar", F_SECENEK, [durum]), "kinds[]": k.hesap("tipler", F_SECENEK, [tip])})
    return k


def for_page(engine: Any, tenant: str, schema: str, out: dict[str, Any], page: int, *, order: str = "bitis", q: str = "",
             status: Optional[int] = None, kind: Optional[int] = None, expiring_days: Optional[int] = None) -> P.Kaynaklar:
    """`GET /api/v1/editorial/contracts`: CRM sözleşme listesinin sayfası (oranlar, avans, pay, kalan gün) ve portal rozeti."""
    k = P.Kaynaklar()
    db = crm_db(E._prefix(schema))
    flt = {"q": q, "status": status, "kind": kind, "expiring_days": expiring_days}
    items = out.get("items") or []
    cnt = k.sorgu("sozlesme.crm.sayim", "CRM sözleşme sayısı (süzgece uyan)", "crm", E.count_sql(schema, **flt), database=db,
                  rows=1)
    lst = k.sorgu("sozlesme.crm.liste", "CRM sözleşme listesi (bu sayfa)", "crm", E.list_sql(schema, page, order=order, **flt),
                  database=db, rows=len(items), description="Sayfa başına 50 sözleşme; OFFSET sayfa numarasından.",
                  **_stats(out))
    inputs = [cnt, lst]
    ids = [c["id"] for c in items if c.get("id")]
    if ids:
        inputs.append(k.sorgu("sozlesme.crm.kitaplar", "CRM sözleşme kitapları (bu sayfa)", "crm", E.books_sql(schema, ids),
                              database=db))
        inputs.append(k.sorgu("sozlesme.crm.taraflar", "CRM sözleşme tarafları (bu sayfa)", "crm", E.parties_sql(schema, ids),
                              database=db))
    liste = k.hesap("liste", F_LISTE, inputs)
    fields = {"total": k.hesap("toplam", "Toplam = süzgece uyan etkin CRM sözleşmesi sayısı (sayım sorgusu).", [cnt]),
              "items[]": liste, "db": lst}
    if ids:
        st = k.portal("sozlesme.portalDurum", "Portalda düzenlenen sözleşmeler (bu sayfa)", C.crm_state_stmt(tenant, ids),
                      engine, description="Portal kaydı olan CRM sözleşmeleri: durum ve CRM kopyası (crm_terms).")
        fields["items[].portal"] = k.hesap("portalFark", F_PORTAL_FARK, [st])
    k.alanlar(fields)
    return k


# ------------------------------------------------------------------ portal kayıtları


def for_records(engine: Any, tenant: str, out: dict[str, Any], *, status: str = "", source: str = "") -> P.Kaynaklar:
    k = P.Kaynaklar()
    rec = k.portal("sozlesme.kayitlar", "Portal sözleşme kayıtları", C.records_stmt(tenant, status, source), engine,
                   description="Portalda açılan ya da düzenlenen sözleşmeler (elle girilir).")
    pay = k.portal("sozlesme.bekleyenOdemeler", "Kayıtların bekleyen ödemeleri", C.records_payments_stmt(tenant, status, source),
                   engine, description="Durumu planlandı olan ödemeler: sayı, vadesi geçen, sıradaki vade.")
    f = k.hesap("kayitlar", F_KAYITLAR + " " + F_SARTLAR, [rec, pay])
    k.alanlar({"items[]": f, "sayac.kayit": f})
    return k


def _statement_sources(k: P.Kaynaklar, s: dict[str, Any], dbs: dict[str, Optional[str]], inputs: list[str],
                       engine: Any = None, tenant: str = "") -> str:
    """Kaydedilmiş bir hakedişin hesabı: hesap anında çalışan Logo/CRM metni (hakedişin yanında saklanır). Telif dönemi
    koşusundan gelen hakedişte asıl sorgu koşunun hesabında çalışan metindir (koşunun kaydından)."""
    calc = s.get("calc") or {}
    logged = calc.get("sorgular") or []
    kosu = calc.get("kosu") or {}
    sid8 = str(s.get("id") or "")[:8]
    period = f"{calc.get('periodStart') or s.get('periodStart')} – {calc.get('periodEnd') or s.get('periodEnd')}"
    if not logged and kosu.get("id") and engine is not None:
        from semantic_bridge import royalty as RY

        ids = kaydet(k, f"sozlesme.kosu.{str(kosu['id'])[:8]}", RY.run_queries(engine, tenant, kosu["id"]), dbs,
                     description=f"{kosu.get('no') or 'Telif dönemi'} koşusu hesaplanırken çalıştı (bütün kapsam için tek "
                                 "okuma); bu hakediş o koşunun satırından oluştu.")
        logged = ids and [True]
    else:
        ids = kaydet(k, f"sozlesme.hakedis.{sid8}", logged, dbs,
                     description=f"{period} hakedişi hesaplanırken çalıştı; sonuç hakediş kaydına yazıldı.")
    text = F_HAKEDIS
    if not logged:
        text += (" Bu hakediş, çalışan sorgunun hakedişle birlikte saklanmasından önce hesaplandı; o anın Logo metni "
                 "kayıtlı değil (yeniden hesaplanan hakedişte görünür). Rakamlar kayıttaki hesap sonucudur.")
    if calc.get("fx"):
        fx = calc["fx"]
        text += f" Kur: {fx.get('rate')} ({fx.get('on')}, {fx.get('source') or 'kaynak yazılmamış'})."
    return k.hesap(f"hakedis:{s.get('id')}", text, inputs + ids)


def for_detail(engine: Any, tenant: str, out: dict[str, Any], crm_log: Optional[Kayit], prefix: str,
               logo_db: Optional[str] = None) -> P.Kaynaklar:
    """`GET /api/v1/editorial/contracts/item/{key}`: şartlar, CRM farkı, zeyilname, ödeme takvimi, hakedişler, geçmiş."""
    k = P.Kaynaklar()
    dbs = {"crm": crm_db(prefix), "logo": logo_db}
    crm_ids = kaydet(k, "sozlesme.crm.sozlesme", crm_log.items if crm_log else [], dbs,
                     description="Sözleşme sayfası açılırken CRM'den okundu.")
    rec = out.get("record")
    fields: dict[str, str] = {}
    if crm_ids:
        crm = k.hesap("crm", F_CRM, crm_ids)
        fields["crm"] = crm
    if rec:
        rid = rec["id"]
        r = k.portal("sozlesme.kayit", "Portal sözleşme kaydı", C.record_stmt(tenant, rid), engine,
                     description="Şartlar ekrandan girilir; CRM'den alınan kayıtta ilk değerler CRM'den gelir.",
                     origin=crm_ids)
        add = k.portal("sozlesme.zeyilnameler", "Zeyilnameler", C.addenda_stmt(tenant, rid), engine, description=F_ZEYIL)
        pay = k.portal("sozlesme.odemeler", "Ödeme takvimi", C.payments_stmt(tenant, rid), engine,
                       description="Elle girilen ödemeler ve onaylanan hakedişlerin ödeme satırları.")
        st = k.portal("sozlesme.hakedisler", "Hakedişler", C.statements_stmt(tenant, rid), engine,
                      description="Kaydedilen hakedişler: hesap sonucu (calc), durum, onay.")
        ev = k.portal("sozlesme.gecmis", "Sözleşme geçmişi", C.events_stmt(tenant, rid), engine, description=F_GECMIS)
        sartlar = k.hesap("sartlar", F_SARTLAR, [r])
        odeme = k.hesap("odeme", F_ODEME, [pay])
        fields.update({"record": r, "terms": sartlar, "addenda[]": add, "payments[]": odeme, "events[]": ev,
                       "statements[]": k.hesap("hakedisler", F_HAKEDIS, [st, r]),
                       "sayac.zeyilname": k.hesap("zeyilSayisi", F_ZEYIL, [add]), "sayac.odeme": odeme,
                       "sayac.bekleyen": odeme, "sayac.hakedis": k.hesap("hakedisSayisi", F_HAKEDIS_SAYI, [st]),
                       "sayac.gecmis": k.hesap("gecmisSayisi", F_GECMIS, [ev])})
        if crm_ids:
            fields["diff"] = k.hesap("fark", F_FARK, [r] + crm_ids)
        for s in out.get("statements") or []:
            fields[f"statements[]:{s['id']}"] = _statement_sources(k, s, dbs, [st, r], engine, tenant)
    elif crm_ids:
        fields["terms"] = fields["crm"]
    k.alanlar(fields)
    return k


def for_due(engine: Any, tenant: str, out: dict[str, Any], *, status: str = "planlandi", within: Optional[int] = None,
            kind: str = "") -> P.Kaynaklar:
    """`GET /api/v1/editorial/contracts/payments`: ödeme takvimi, bekleyen / vadesi geçen sayısı, para birimi toplamları."""
    k = P.Kaynaklar()
    d = k.portal("sozlesme.takvim", "Ödeme takvimi (bütün sözleşmeler)", C.due_stmt(tenant, status=status, within=within, kind=kind),
                 engine, description="Süzgeç değerleri yerinde: durum, tür ve vade sınırı (bugün + seçilen gün; vadesiz de gelir).")
    f = k.hesap("takvim", F_TAKVIM, [d])
    k.alanlar({"items[]": f, "totals": f, "sayac.bekleyen": f, "sayac.vadesiGecen": f})
    return k


def for_templates(engine: Any, tenant: str, out: dict[str, Any], *, target: str = "", archived: bool = False) -> P.Kaynaklar:
    k = P.Kaynaklar()
    t = k.portal("sozlesme.sablonlar", "Şablon kütüphanesi", C.templates_stmt(tenant, target=target, include_archived=archived),
                 engine, description="Sözleşme, zeyilname ve hakediş bildirimi şablonları (elle girilir; sürüm her kayıtta artar).")
    k.alanlar({"items[]": k.hesap("sablon", F_SABLON, [t])})
    return k


def for_lookup(log: Kayit, prefix: str, out: dict[str, Any]) -> P.Kaynaklar:
    """CRM seçicileri (kitap, kişi/firma): sayfanın kayıtları, CRM'deki bütün eşleşme sayısı."""
    k = P.Kaynaklar()
    ids = kaydet(k, "sozlesme.crm.secici", log.items, {"crm": crm_db(prefix)}, description="Seçicide yazılan metinle çalıştı.")
    f = k.hesap("secici", F_ARAMA, ids)
    k.alanlar({"items[]": f, "total": f, "shown": f})
    return k


def for_calc(engine: Any, tenant: str, out: dict[str, Any], key: str, dbs: dict[str, Optional[str]]) -> P.Kaynaklar:
    """`POST .../statements/preview`: hakediş önizlemesi. Hesap anında çalışan Logo/CRM metni `sorgular`dadır."""
    k = P.Kaynaklar(data_end=out.get("dataEnd"))
    ids = kaydet(k, "sozlesme.onizleme", out.get("sorgular") or [], dbs,
                 description="Hakediş hesaplanırken çalıştı.", period=f"{out.get('periodStart')} – {out.get('periodEnd')}")
    inputs = list(ids)
    if C._PID.match(key or "") or C.is_crm_id(key or ""):
        rec = C.find(engine, tenant, key)
        if rec:
            inputs.append(k.portal("sozlesme.kayit", "Portal sözleşme kaydı (şartlar)", C.record_stmt(tenant, rec["id"]), engine,
                                   description="Hesabın şartları (oran, avans, pay, stopaj) bu kayıttandır."))
            inputs.append(k.portal("sozlesme.oncekiHakedisler", "Önceki onaylı hakedişler",
                                   C.statement_context_stmt(tenant, rec["id"], out.get("periodStart") or ""), engine,
                                   description="Avanstan önceden düşülen toplam ve devreden tutar bunlardan."))
    text = F_HAKEDIS
    if out.get("fx"):
        fx = out["fx"]
        text += f" Kur: {fx.get('rate')} ({fx.get('on')}, {fx.get('source') or 'kaynak yazılmamış'})."
    if not inputs:
        raise P.ProvenanceError("Hakedişin kaynağı kayıtlı değil.")
    f = k.hesap("hakedis", text, inputs)
    k.alanlar({name: f for name, v in out.items() if name != "kaynaklar" and P.numeric_paths(v)})
    return k
