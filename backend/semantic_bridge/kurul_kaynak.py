"""DYK Kurul: ekrandaki her rakamın sorgu bilgisi (ortak sözleşme `provenance.py`, kılavuz `docs/analiz/sorgu-bilgisi-kilavuz.md`).

Kurul rakam üretmez; göstergeler diğer modüllerin onaylı çıktılarıdır (`kurul_sources`). Bu yüzden bir göstergenin «asıl
SQL»i ölçüm anında kaynak modülde çalışan sorgudur:

- **Ölçüm** (`timas-kurul` günlük koşusu, «Şimdi ölç»): her sağlayıcı kendi modülünün hesabını çağırır; aynı anda o modülün
  sorgu bilgisi kurulur (M45 `finance_kaynak.for_summary`, M46 `budget_kaynak.for_tracking` / `for_deviations`, M47
  `risk_kaynak.for_summary`, M59 `dealers_kaynak.for_summary`) ya da modülün kaynak dosyası yoksa ölçüm sırasında
  portal veritabanında ÇALIŞAN ifadeler yakalanır (M50 Zeki AI kalitesi, M48 sistem durumu: `Capture`), CRM okuması
  çalıştırıcı sarmalanarak kaydedilir (M6 sözleşme sayacı: `RunLog`). Göstergenin değerine giden zincir (hesap → sorgu →
  tabloyu dolduran Logo/CRM sorgusu) değer satırıyla birlikte `semantic_kurul_values.ayrinti_json` içinde `_sorgu`
  anahtarıyla saklanır; ekrana giden ayrıntıdan ayrılır (`kurul._value_out`).
- **Panel ve ayrıntı**: gösterilen portal SQL'i uçta çalışan ifadedir (`kurul.values_stmt`, `series_stmt`, ...); ölçümde
  saklanan zincir onun kökenidir (`origin`). Kaydı olmayan (bu sürümden önce ölçülmüş) dönemde açıklama bunu yazar.
- **Paket**: derleme anında çalışan sorgular aynı biçimde içerikte `_kaynaklar` anahtarıyla dondurulur (`for_compile`);
  paket ekranında paket kaydının SQL'i + derleme anının zinciri gösterilir (`for_package`).

Kaynak kimlikleri `kurul.` önekiyle başlar; başka modülden taşınan kayıt `kurul.<sağlayıcı>.<dönem>.<asıl kimlik>` olur.
Kişisel veri: SQL metni gösterilir, sonuç satırı kayda girmez (yalnız satır sayısı).
"""
from __future__ import annotations

import logging
import os
import threading
import time
import weakref
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

from semantic_bridge import kurul as K
from semantic_bridge import provenance as P

log = logging.getLogger("semantic.kurul.kaynak")

#: Rakam olmayan sayılar: sıra, sürüm, gündem sırası, içerik yapı sürümü.
NOT_RAKAM = (
    "bolumler[].gostergeler[].sira", "bolumler[].gostergeler[].surum", "kritik[].sira", "kritik[].surum",
    "gosterge.sira", "gosterge.surum", "items[].sira", "items[].surum", "items[].paketSurum", "siradaki.paketSurum",
    "gundem[].sira", "kararlar[].gundemSira", "paketler[].surum", "surum", "icerik.surumYapisi", "icerik.gundem[].sira",
)


def logo_db() -> Optional[str]:
    """Logo bağlantı dosyasından yalnız veritabanı adı (SSMS'te kopyala-çalıştır için «USE» satırı)."""
    return P.connection_database(os.environ.get("SEMANTIC_CONNECTION_FILE"))


def crm_db() -> Optional[str]:
    return P.connection_database(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE",
                                                "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"))


def crm_db_of(schema: str) -> Optional[str]:
    """CRM şemasının (ör. `Timas_MSCRM.dbo`) veritabanı adı; CRM SQL'i üç parçalı adla yazılıdır."""
    db, _, _ = (schema or "").strip().rstrip(".").rpartition(".")
    return db or None


# ================================================================== ölçüm anı: çalışan sorguların kaydı


class RunLog:
    """CRM/Logo çalıştırıcısı (`run(sql)`) sarmalayıcısı: istenen ve çalışan metin, satır, süre, an. Sonuç aynen geçer."""

    def __init__(self, run: Callable[..., Any]):
        self._run = run
        self.items: list[dict[str, Any]] = []

    def __call__(self, sql: str, *a: Any, **kw: Any) -> Any:
        t0 = time.monotonic()
        out = self._run(sql, *a, **kw)
        item: dict[str, Any] = {"asked": sql, "sql": sql, "rows": None, "dbMs": int((time.monotonic() - t0) * 1000),
                                "at": time.time()}
        if isinstance(out, dict):
            item["sql"] = out.get("physicalSql") or sql
            recs = out.get("records")
            item["rows"] = out.get("totalRows") if out.get("totalRows") is not None else (len(recs) if isinstance(recs, list) else None)
            if out.get("dbMs") is not None:
                item["dbMs"] = out["dbMs"]
            if out.get("computedAt"):
                item["at"] = out["computedAt"]
        self.items.append(item)
        return out

    def find(self, asked: str) -> Optional[dict[str, Any]]:
        return next((it for it in reversed(self.items) if it["asked"] == asked), None)


_SKIP = ("pg_catalog", "information_schema", "sqlite_master", "pg_namespace")


def _compile(conn: Any, clause: Any, multiparams: Any, params: Any) -> Optional[str]:
    from sqlalchemy.sql import CompoundSelect, Select
    from sqlalchemy.sql.elements import TextClause

    if not isinstance(clause, (Select, CompoundSelect, TextClause)):
        return None
    p: dict[str, Any] = {}
    for m in (multiparams if isinstance(multiparams, (list, tuple)) else [multiparams]):
        if isinstance(m, dict):
            p.update(m)
    if isinstance(params, dict):
        p.update(params)
    if p:
        clause = clause.bindparams(**p) if isinstance(clause, TextClause) else clause.params(**p)
    text = P.portal_sql(clause, conn)
    if isinstance(clause, TextClause) and not text.lstrip().lower().startswith(("select", "with")):
        return None
    if any(s in text.lower() for s in _SKIP):
        return None
    return text


_local = threading.local()
_hooked: "weakref.WeakSet[Any]" = weakref.WeakSet()
_hook_lock = threading.Lock()


def _active() -> list["Capture"]:
    caps = getattr(_local, "caps", None)
    if caps is None:
        caps = _local.caps = []
    return caps


def _on_before(conn, clause, multiparams, params, execution_options) -> None:  # noqa: ANN001
    for cap in _active():
        if conn.engine is cap.engine:
            cap._before(conn, clause, multiparams, params)


def _on_after(conn, clause, multiparams, params, execution_options, result) -> None:  # noqa: ANN001
    for cap in _active():
        if conn.engine is cap.engine:
            cap._after()


def _hook(engine: Any) -> None:
    """Dinleyici motora bir kez takılır ve kalır: yakalama yalnız bu iş parçacığındaki etkin kayda yazar. Dinleyiciyi her
    ölçümde takıp sökmek başka iş parçacığında süren sorgunun dinleyici listesini değiştirirdi."""
    with _hook_lock:
        if engine in _hooked:
            return
        sa.event.listen(engine, "before_execute", _on_before)
        sa.event.listen(engine, "after_execute", _on_after)
        _hooked.add(engine)


class Capture:
    """Bu iş parçacığında portal veritabanında ÇALIŞAN okuma ifadeleri (değerleri yerinde). Başka modülün okuma işlevini
    değiştirmeden «gösterilen = çalışan» sağlar; kaynak modülün `*_stmt` işlevi olmadığında kullanılır."""

    def __init__(self, engine: Any):
        self.engine = engine
        self.items: list[dict[str, Any]] = []
        self._open: list[Optional[dict[str, Any]]] = []

    def _before(self, conn: Any, clause: Any, multiparams: Any, params: Any) -> None:
        try:
            text = _compile(conn, clause, multiparams, params)
        except Exception:  # noqa: BLE001 — derlenemeyen ifade kayda girmez (uydurulmaz)
            text = None
        item = {"sql": text, "t0": time.monotonic(), "at": time.time(), "dbMs": None} if text else None
        self._open.append(item)
        if item:
            self.items.append(item)

    def _after(self) -> None:
        if not self._open:
            return
        item = self._open.pop()
        if item:
            item["dbMs"] = int((time.monotonic() - item.pop("t0")) * 1000)

    def __enter__(self) -> "Capture":
        _hook(self.engine)
        _active().append(self)
        return self

    def __exit__(self, *exc: Any) -> None:
        caps = _active()
        if self in caps:
            caps.remove(self)
        for it in self.items:
            it.pop("t0", None)

    def sqls(self, contains: Iterable[str] = ()) -> list[dict[str, Any]]:
        want = [c.lower() for c in contains]
        out, seen = [], set()
        for it in self.items:
            low = it["sql"].lower()
            if want and not all(w in low for w in want):
                continue
            if it["sql"] in seen:
                continue
            seen.add(it["sql"])
            out.append(it)
        return out


def capture(engine: Any) -> Capture:
    return Capture(engine)


def closure(kd: dict[str, Any], refs: Iterable[str]) -> dict[str, Any]:
    """Bir kaynak kaydından (`Kaynaklar.to_dict()`) verilen alanların bütün zinciri: hesap → girdiler → sorgular → köken."""
    sources: dict[str, Any] = {}
    formulas: dict[str, Any] = {}

    def visit(r: str) -> None:
        if r.startswith("hesap:"):
            name = r[6:]
            f = (kd.get("formulas") or {}).get(name)
            if f is None or name in formulas:
                return
            formulas[name] = f
            for i in f.get("inputs") or []:
                visit(i)
            return
        s = (kd.get("sources") or {}).get(r)
        if s is None or r in sources:
            return
        sources[r] = s
        for o in s.get("origin") or []:
            visit(o)

    roots = [r for r in refs if r]
    for r in roots:
        visit(r)
    return {"refs": roots, "sources": sources, "formulas": formulas}


def from_kaynak(prov: str, k: Optional[P.Kaynaklar], mapping: dict[str, list[str]]) -> dict[str, dict[str, Any]]:
    """Kaynak modülün sorgu bilgisinden gösterge başına kayıt: {kod: {saglayici, refs, sources, formulas}}."""
    if k is None:
        return {kod: {"saglayici": prov, "hata": "Kaynak modül bu ölçümde sorgu bilgisi vermedi."} for kod in mapping}
    kd = k.to_dict()
    out: dict[str, dict[str, Any]] = {}
    for kod, paths in mapping.items():
        refs = [kd["fields"][p] for p in paths if p in kd["fields"]]
        if not refs:
            out[kod] = {"saglayici": prov, "hata": "Kaynak modülün sorgu bilgisinde bu kalem yok."}
            continue
        out[kod] = {"saglayici": prov, **closure(kd, refs)}
    return out


def from_items(prov: str, sid: str, title: str, conn: str, items: list[dict[str, Any]], description: str,
               database: Optional[str] = None, period: Optional[str] = None) -> dict[str, Any]:
    """Ölçümde yakalanan (çalışan) sorgulardan kayıt."""
    k = P.Kaynaklar()
    ids = []
    for i, it in enumerate(items, start=1):
        ids.append(k.sorgu(f"{sid}.{i}", f"{title} · {i}" if len(items) > 1 else title, conn, it["sql"], database=database,
                           rows=it.get("rows"), ms=it.get("dbMs"), ran_at=it.get("at"), period=period, description=description))
    if not ids:
        return {"saglayici": prov, "hata": "Ölçümde bu kalemin sorgusu yakalanamadı."}
    return {"saglayici": prov, **closure(k.to_dict(), ids)}


def attach(out: dict[str, dict[str, Any]], prov: str, build: Callable[[], dict[str, dict[str, Any]]]) -> None:
    """Sağlayıcı sonucuna ölçüm zincirini ekler (`_sorgu`). Kayıt kurulamazsa rakam düşmez; neden kayda yazılır."""
    if not any(r.get("durum") == "ok" for r in out.values()):
        return
    try:
        recs = build()
    except Exception as e:  # noqa: BLE001 — sorgu bilgisi ölçümü düşürmez
        log.warning("kurul: %s sorgu bilgisi kurulamadı: %s", prov, e)
        recs = {kod: {"saglayici": prov, "hata": f"Sorgu bilgisi kurulamadı: {str(e)[:200]}"} for kod in out}
    for kod, res in out.items():
        if res.get("durum") == "ok" and kod in recs:
            res["_sorgu"] = recs[kod]


# ================================================================== ekran anı: kayıtların yeniden kurulması


def readd(k: P.Kaynaklar, rec: Optional[dict[str, Any]], prefix: str, note: str = "") -> tuple[list[str], list[str]]:
    """Saklanan zinciri `prefix` önekiyle yeniden kaydeder (her SQL yeniden denetlenir). (sorgu kimlikleri, kök kayıtlar)."""
    if not rec or rec.get("hata"):
        return [], []
    srcs, frms = rec.get("sources") or {}, rec.get("formulas") or {}

    def sid(x: str) -> str:
        return prefix + x

    ids: list[str] = []
    for old, s in srcs.items():
        new = sid(old)
        if new not in k.sources:
            st = s.get("stats") or {}
            k.sorgu(new, s.get("title") or old, s["connection"], s["sql"], database=s.get("database"),
                    rows=st.get("rows"), ms=st.get("dbMs"), ran_at=st.get("ranAt"), data_end=s.get("dataEnd"),
                    period=s.get("period"), origin=[sid(o) for o in s.get("origin") or [] if o in srcs],
                    description=((s.get("description") or "") + (" " + note if note else "")).strip())
        ids.append(new)

    def add_formula(name: str, stack: frozenset = frozenset()) -> Optional[str]:
        new = prefix + name
        if new in k.formulas:
            return "hesap:" + new
        f = frms.get(name)
        if f is None or name in stack:
            return None
        ins = []
        for i in f.get("inputs") or []:
            if i.startswith("hesap:"):
                r = add_formula(i[6:], stack | {name})
                if r:
                    ins.append(r)
            elif i in srcs:
                ins.append(sid(i))
        return k.hesap(new, f["text"], ins) if ins else None

    roots = []
    for r in rec.get("refs") or []:
        got = add_formula(r[6:]) if r.startswith("hesap:") else (sid(r) if r in srcs else None)
        if got:
            roots.append(got)
    return ids, roots


#: Kurul değerinin kaynak modülün rakamından nasıl alındığı (gösterge koduna göre).
DERIVE: dict[str, str] = {
    "net_satis": "Değer = finansal raporların «Net satış» kartı (yıl başından); önceki = kartın geçen yılın aynı dönemi.",
    "brut_kar_marji": "Değer = «Brüt kâr» kartının oranı × 100 (maliyeti işlenmiş satış).",
    "faaliyet_gideri": "Değer = «Faaliyet giderleri» kartı (yıl başından); önceki = kartın karşılaştırması.",
    "kasa_banka": "Değer = «Kasa ve banka» kartı (veri son günü bakiyesi).",
    "vadesi_gecmis_alacak": "Değer = «Vadesi geçmiş alacak» kartı (13 haftalık nakit tablosunun vade dağılımı).",
    "butce_satis": ("Değer = bütçe izlemesinde şirket satışı gerçekleşen ÷ bugüne beklenen × 100; hedef %100; renk bütçe "
                    "modülünün eşiği (iyi → yeşil, izle → sarı, sapma → kırmızı)."),
    "butce_gider": ("Değer = departman gider bütçesi kullanımı × 100 (gerçekleşen ÷ döneme düşen bütçe); hedef %100; renk: "
                    "aşan kalem varsa kırmızı, yaklaşan varsa sarı, yoksa yeşil."),
    "butce_sapma": "Değer = bütçe modülünün açık sapma uyarısı sayısı (satış ve gider).",
    "bayi_vadesi_gecmis": ("Değer = günlük bayi turunun vadesi geçmiş bakiye toplamı; önceki = ~30 gün önceki günün "
                           "satırlarıyla aynı toplam."),
    "bayi_yogunlasma": "Değer = pozitif bakiyede en büyük 10 carinin payı × 100; önceki = ~30 gün önceki gün.",
    "bayi_d_segment": ("Değer = D segmentindeki etkin cari sayısı (bütün kanallar toplamı); önceki = 30 gün önceki girdiler "
                       "bugünkü kuralla puanlanarak."),
    "sozlesme_bitecek": "Değer = CRM'de yürürlükteki ve uyarı günü içinde biten sözleşme sayısı (sorgunun «yaklasan» kolonu).",
    "risk_kritik": "Değer = risk kaydında canlı ve seviyesi kritik olan risk sayısı.",
    "risk_kirmizi_gosterge": "Değer = son ölçümü kırmızı olan risk göstergesi sayısı.",
    "risk_geciken_aksiyon": "Değer = termini geçmiş açık risk aksiyonu sayısı.",
    "zeki_cevaplama": ("Değer = pencere içinde sorulan sorulardan veriyle cevaplananların payı × 100 (Zeki AI kalitesi "
                       "karnesi; pencere günü ayar)."),
    "zeki_saglam": "Değer = son bitmiş kalite koşusunda referansla doğrulanmış soruların sağlam kalan payı × 100.",
    "sistem_acik_olay": "Değer = kapanmamış sistem olayı (kopma, veri eskiliği) sayısı; renk sistem durumunun kendi tonu.",
    "logo_veri_gecikmesi": "Değer = ölçüm günü − Logo halkasının veri son günü (gün).",
}
F_OLCUM = ("Ölçüm günde bir (06:30) ve «Şimdi ölç» ile yapılır; değer kurul değer tablosuna dönem satırı olarak yazılır, "
           "ekran o satırı okur. Kaynak önceki değeri vermezse önceki = bir önceki dönemin ölçümü. Renk: göstergenin kendi "
           "eşiği varsa yöne göre (sarı / kırmızı), yoksa kaynak modülün rengi, o da yoksa «eşik yok». Eğilim = (değer − "
           "önceki) ÷ |önceki|.")
F_GRI = "Kaynağı yok ya da henüz ölçülmedi: sayı ve renk yazılmaz."
F_KATALOG = "Eşikler, yön, sahip ve sıra gösterge kataloğunda elle girilir; rakam kaynağı (sağlayıcı) kodla bağlıdır."
F_KALAN = "Kalan gün = termin − bugün (İstanbul); eksi ise geçti. Açık aksiyonun kalan günü eksiyse «Gecikti»."


def _plain(text: str) -> str:
    """Katalogda elle yazılan ad formül metnine girer: teknoloji adı geçerse kayıt reddedilmesin diye çıkarılır."""
    return P._TECH.sub("…", str(text))


def _name(g: dict[str, Any]) -> str:
    return _plain(g.get("ad") or g.get("kod") or "")


class _Ctx:
    def __init__(self, engine: Any, tenant: str, data_end: Any = None):
        self.engine, self.tenant = engine, tenant
        self.k = P.Kaynaklar(data_end=data_end)

    def portal(self, sid: str, title: str, stmt: Any, desc: str, origin: Iterable[str] = ()) -> str:
        if sid in self.k.sources:
            return sid
        return self.k.portal(sid, title, stmt, self.engine, description=desc, origin=origin)

    def catalog(self) -> str:
        return self.portal("kurul.katalog", "Gösterge kataloğu", K.indicators_stmt(self.tenant),
                           "Tanım, bölüm, birim, yön, sarı ve kırmızı eşik, sahip, sıra, sürüm (semantic_kurul_indicators); "
                           "eşik ve sahip elle girilir.")

    def comments(self, donem: str) -> str:
        return self.portal("kurul.yorumlar", f"Gösterge yorumları · {donem}", K.comments_stmt(self.tenant, donem=donem),
                           "Bölüm yöneticisinin yorumları ve durumu (onaylı / taslak); elle ya da Zeki AI taslağıyla yazılır.")

    def values(self, donem: str) -> str:
        return self.portal("kurul.degerler", f"Gösterge değerleri · {K.donem_label(donem)}", K.values_stmt(self.tenant, donem),
                           "Dönemin ölçüm satırları: değer, hedef, önceki, renk, veri son günü, kaynak (semantic_kurul_values).")

    def indicator(self, g: dict[str, Any], donem: str, rec: Optional[dict[str, Any]], stmt: Any, sid: str,
                  title_tail: str, extra_desc: str = "") -> str:
        """Tek göstergenin değer hesabı: değer satırı (köken: ölçüm zinciri) + katalog + kaynak modülün hesabı."""
        kod = g["kod"]
        prov = (rec or {}).get("saglayici") or g.get("saglayici") or "kurul"
        ids, roots = readd(self.k, rec, f"kurul.{prov}.{donem}.", note=f"Kurul ölçümünde ({K.donem_label(donem)}) okundu.")
        if g.get("durum") == "ok" or (rec and not rec.get("hata")):
            miss = ""
            if not rec:
                miss = " Bu dönem sorgu kaydı tutulmadan önce ölçüldü; ölçüm zinciri bir sonraki ölçümden sonra görünür."
            elif rec.get("hata"):
                miss = " " + rec["hata"]
            desc = (f"Satır: kod = '{kod}', dönem {donem}. Değer ölçümde kaynak modülden okunup yazıldı; köken: ölçümde "
                    f"çalışan sorgular.{miss}{extra_desc}")
            val = self.portal(sid, f"{g.get('ad') or kod} · {title_tail}", stmt, desc, origin=ids)
            text = " ".join(x for x in (f"{_name(g)}: {DERIVE.get(kod, 'Değer kaynak modülün kaydından okunur.')}",
                                        f"Kaynak: {_plain(g.get('kaynak') or '—')}.", F_OLCUM) if x)
            return self.k.hesap(f"kurul.gosterge.{kod}.{donem}", text, [val, self.catalog()] + roots)
        return self.k.hesap(f"kurul.gosterge.{kod}.{donem}", f"{_name(g)}: {F_GRI} {F_KATALOG}",
                            [self.portal(sid, f"{g.get('ad') or kod} · {title_tail}", stmt,
                                         f"Satır: kod = '{kod}', dönem {donem}.{extra_desc}"), self.catalog()])


# ------------------------------------------------------------------ uçlar


def for_panel(engine: Any, tenant: str, out: dict[str, Any]) -> P.Kaynaklar:
    """`GET /kurul/panel`: gösterge kutuları, dikkat isteyenler, sayaçlar, son ölçüm."""
    x = _Ctx(engine, tenant, out.get("enEskiVeri"))
    k = x.k
    donem = out["donem"]
    recs = K.measured_queries(engine, tenant, donem)
    vals, cat, com = x.values(donem), x.catalog(), x.comments(donem)
    fields: dict[str, str] = {}
    flat = [g for b in out.get("bolumler") or [] for g in b.get("gostergeler") or []]
    for g in flat:
        ref = x.indicator(g, donem, recs.get(g["kod"]), K.values_stmt(tenant, donem), f"kurul.deger.{g['kod']}",
                          f"değer kaydı {K.donem_label(donem)}")
        fields[f"bolumler[].gostergeler[]:{g['kod']}"] = ref
        fields[f"kritik[]:{g['kod']}"] = ref
    genel = k.hesap("kurul.gostergeler", "Her kutu kendi göstergesinin ölçüm satırıdır (kutunun «i» düğmesi). " + F_OLCUM,
                    [vals, cat])
    fields.update({
        "bolumler[].gostergeler[]": genel,
        "bolumler[].gostergeler[].esikSari": cat, "bolumler[].gostergeler[].esikKirmizi": cat,
        "kritik[]": k.hesap("kurul.kritik", "Dikkat isteyenler = bu dönemde rengi kırmızı olan göstergeler (katalog sırası). "
                                            + F_OLCUM, [vals, cat, com]),
        "sayilar": k.hesap("kurul.sayac", "Toplam = panelde gösterilen (etkin) gösterge; hazır = kaynağı okunan; kaynak yok = "
                                          "sağlayıcısı olmayan ya da henüz ölçülmeyen; okunamadı = kaynak hata verdi; kırmızı "
                                          "/ sarı = o renkteki; yorumsuz renkli = kırmızı ya da sarı olup bu dönem onaylı "
                                          "yorumu olmayan gösterge sayısı.", [vals, cat, com]),
    })
    if out.get("olcum"):
        fields["olcum"] = x.portal("kurul.olcum", "Son ölçüm kaydı", K.meta_stmt(tenant, "olcum"),
                                   "Son ölçümün anı, dönemi, ölçülen, kaynaksız (gri) ve okunamayan gösterge sayısı.")
    k.alanlar(fields)
    return k


def for_indicator(engine: Any, tenant: str, kod: str, out: dict[str, Any]) -> P.Kaynaklar:
    """`GET /kurul/indicators/{kod}`: seçili dönemin değeri, son dönemler serisi (her dönem kendi ölçüm zinciriyle)."""
    g = out["gosterge"]
    x = _Ctx(engine, tenant, g.get("veriSonGunu"))
    k = x.k
    months = K.settings()["historyMonths"]
    stmt = K.series_stmt(tenant, kod, months)
    with engine.connect() as c:
        rows = {r.donem: K._value_out(r) for r in c.execute(stmt)}
    desc = f" Seri son {months} dönemi okur (ayar: geçmiş ay sayısı)."
    fields: dict[str, str] = {}
    cur = x.indicator(g, out["donem"], (rows.get(out["donem"]) or {}).get("_sorgu"), stmt, f"kurul.seri.{out['donem']}",
                      f"dönem {K.donem_label(out['donem'])}", desc)
    fields["gosterge"] = cur
    fields["gosterge.esikSari"] = fields["gosterge.esikKirmizi"] = x.catalog()
    every = []
    for s in out.get("seri") or []:
        d = s["donem"]
        v = rows.get(d) or {}
        ref = cur if d == out["donem"] else x.indicator({**g, "durum": v.get("durum") or s.get("durum")}, d, v.get("_sorgu"),
                                                         stmt, f"kurul.seri.{d}", f"dönem {K.donem_label(d)}", desc)
        fields[f"seri[]:{d}"] = ref
        every.append(ref)
    fields["seri"] = k.hesap("kurul.seri", f"Son dönemler: her dönemin son ölçümü (dönem başına bir satır, en çok {months} "
                                           "dönem; ölçülemeyen dönem boş). Sayı = serideki dönem sayısı.",
                             [x.portal(f"kurul.seri.{out['donem']}", f"{g.get('ad') or kod} · seri", stmt, desc.strip())] + every)
    k.alanlar(fields)
    return k


def for_indicators(engine: Any, tenant: str, out: dict[str, Any]) -> P.Kaynaklar:
    """`GET /kurul/indicators`: katalog (eşikler elle)."""
    x = _Ctx(engine, tenant)
    x.k.alanlar({"items[]": x.k.hesap("kurul.katalog", F_KATALOG, [x.catalog()])})
    return x.k


def for_meetings(engine: Any, tenant: str, out: dict[str, Any]) -> P.Kaynaklar:
    """`GET /kurul/meetings`: kalan gün, karar sayısı, son paket sürümü."""
    x = _Ctx(engine, tenant)
    k = x.k
    m = x.portal("kurul.toplantilar", "Kurul toplantıları", K.meetings_stmt(tenant), "Tür, başlık, tarih, saat, yer, durum.")
    d = x.portal("kurul.kararSayisi", "Toplantı başına karar sayısı", K.decision_counts_stmt(tenant), "Karar kayıtlarının sayımı.")
    v = x.portal("kurul.paketSurum", "Toplantı başına son paket sürümü", K.package_versions_stmt(tenant), "Paket sürümleri.")
    f = x.portal("kurul.paketDondu", "Dondurulmuş paketi olan toplantılar", K.frozen_packages_stmt(tenant),
                 "Durumu donduruldu ya da dağıtıldı olan paketler.")
    kalan = "Kalan gün = toplantı tarihi − bugün (İstanbul); eksi ise geçti."
    items = k.hesap("kurul.toplanti", kalan + " Karar sayısı = toplantının karar kayıtları; paket = son sürüm ve dondurulup "
                                              "dondurulmadığı.", [m, d, v, f])
    k.alanlar({"items[]": items, "items[].kalanGun": k.hesap("kurul.kalanGun", kalan, [m]), "items[].kararSayisi": d,
               "siradaki": k.hesap("kurul.siradaki", "Sıradaki = tarihi bugün ya da sonra olan, durumu planlandı olan en yakın "
                                                    "toplantı. " + kalan, [m, d, v, f])})
    return k


def for_meeting(engine: Any, tenant: str, mid: str, out: dict[str, Any]) -> P.Kaynaklar:
    """`GET /kurul/meetings/{id}`: gündem (süre elle), kararlar, aksiyonların kalan günü, paketler."""
    x = _Ctx(engine, tenant)
    k = x.k
    m = x.portal("kurul.toplanti", "Toplantı", K.meeting_stmt(tenant, mid), "Toplantının kaydı.")
    ag = x.portal("kurul.gundem", "Gündem maddeleri", K.agenda_stmt(mid), "Başlık, tür, sunan ve süre (dakika) elle girilir.")
    dec = x.portal("kurul.kararlar", "Kararlar", K.decisions_stmt(tenant, [mid]), "Karar metni, gündem sırası, oy özeti (elle).")
    act = x.portal("kurul.kararAksiyon", "Kararların aksiyonları", K.decision_actions_stmt(tenant, [mid]),
                   "Eylem, sahip, termin, durum.")
    pk = x.portal("kurul.toplantiPaket", "Toplantının paketleri", K.meeting_packages_stmt(mid), "Sürüm, durum, derleme ve dondurma.")
    k.alanlar({"gundem[]": k.hesap("kurul.gundem", "Gündem sekreterce elle girilir; süre dakikadır.", [ag]),
               "kararlar[]": dec, "kararlar[].aksiyonlar[]": k.hesap("kurul.aksiyonKalan", F_KALAN, [act, dec]),
               "paketler[]": pk, "katilimcilar": m})
    return k


def for_agenda_suggest(engine: Any, tenant: str, mid: str, out: dict[str, Any]) -> P.Kaynaklar:
    """`GET /kurul/meetings/{id}/agenda/suggest`: öneri başlığındaki sayı (geciken aksiyon) ve gösterge değeri."""
    panel = K.panel(engine, tenant)
    x = _Ctx(engine, tenant)
    k = x.k
    late = x.portal("kurul.aksiyonAcik", "Açık kurul aksiyonları", K.actions_stmt(tenant, "geciken"),
                    "Durumu açık aksiyonlar; geciken = termini bugünden önce olanlar (hesap).")
    donem = panel["donem"]
    recs = K.measured_queries(engine, tenant, donem)
    fields = {"items[]:aksiyon": k.hesap("kurul.oneriAksiyon", "Başlıktaki sayı = termini geçmiş açık kurul aksiyonu sayısı. "
                                                               + F_KALAN, [late])}
    for g in panel["kritik"]:
        fields[f"items[]:{g['kod']}"] = x.indicator(g, donem, recs.get(g["kod"]), K.values_stmt(tenant, donem),
                                                    f"kurul.deger.{g['kod']}", f"değer kaydı {K.donem_label(donem)}")
    fields["items[]"] = k.hesap("kurul.oneri", "Öneri kuralı (model yok): geciken kurul aksiyonları bir bilgi maddesi, her "
                                               "kırmızı gösterge bir karar maddesi olur.", [late, x.values(donem), x.catalog()])
    k.alanlar(fields)
    return k


def for_actions(engine: Any, tenant: str, out: dict[str, Any], durum: str, sahip: Optional[str]) -> P.Kaynaklar:
    """`GET /kurul/actions`: kalan gün, liste sayısı, geciken sayısı."""
    x = _Ctx(engine, tenant)
    k = x.k
    a = x.portal("kurul.aksiyonlar", "Kurul aksiyonları", K.actions_stmt(tenant, durum, sahip),
                 f"Süzgeç: {durum}{' · yalnız bana atananlar' if sahip else ''}; kararı ve toplantısıyla.")
    kalan = k.hesap("kurul.aksiyonKalan", F_KALAN, [a])
    say = k.hesap("kurul.aksiyonSay", "Liste = süzgeçten geçen aksiyon sayısı («geciken» süzgecinde yalnız termini geçmiş "
                                      "açıklar); geciken = listede termini geçmiş açık aksiyon sayısı. " + F_KALAN, [a])
    k.alanlar({"items[]": kalan, "total": say, "geciken": say})
    return k


def for_packages(engine: Any, tenant: str, out: dict[str, Any]) -> P.Kaynaklar:
    x = _Ctx(engine, tenant)
    x.k.alanlar({"items[]": x.portal("kurul.paketler", "Kurul paketleri", K.packages_stmt(tenant),
                                     "Toplantı, sürüm, durum, derleme ve dondurma anı; taslaklar yalnız hazırlayana görünür.")})
    return x.k


def for_job(engine: Any, tenant: str, jid: str, out: dict[str, Any]) -> P.Kaynaklar:
    """`GET /kurul/jobs/{id}`: tutanak önerisinde atılan öneri sayısı (ön yüzde sayılır)."""
    x = _Ctx(engine, tenant)
    j = x.portal("kurul.is", "Arka plan işi", K.job_stmt(tenant, jid), "İşin türü, durumu ve sonucu (öneriler, atılanlar).")
    x.k.alanlar({"sonuc": x.k.hesap("kurul.isSonuc", "Atılan öneri = Zeki AI önerisinden notlarda ve gündemde geçmeyen sayı, "
                                                     "tarih ya da kişi içerdiği için süzülen madde sayısı; öneriler "
                                                     "kaydedilmez, forma alınır.", [j]), "sonuc.dusenler": "hesap:kurul.isSonuc"})
    return x.k


# ------------------------------------------------------------------ paket: derleme anı ve okuma


def for_compile(engine: Any, tenant: str, content: dict[str, Any], *, risk_log: Optional[Capture] = None,
                market_log: Optional[Capture] = None, risk_ctx: Any = None) -> dict[str, Any]:
    """Paket derlenirken çalışan sorguların kaydı (içerik yollarına göre). Paketle birlikte dondurulur."""
    kap = content.get("kapak") or {}
    donem = kap.get("donem") or K.current_donem()
    top = kap.get("toplanti") or {}
    x = _Ctx(engine, tenant, kap.get("enEskiVeri"))
    k = x.k
    note = f"Paket derlenirken ({kap.get('derleme') or '—'}) çalıştı."
    vals = x.portal("kurul.derleme.degerler", f"Gösterge değerleri · {K.donem_label(donem)}", K.values_stmt(tenant, donem),
                    "Derleme anında okunan dönem satırları (son ölçüm; derlemede yeniden hesap yok). " + note)
    cat, com = x.catalog(), x.comments(donem)
    recs = K.measured_queries(engine, tenant, donem)
    fields: dict[str, str] = {}
    for b in content.get("gostergeler") or []:
        for g in b.get("gostergeler") or []:
            full = {**g, "saglayici": (recs.get(g["kod"]) or {}).get("saglayici")}
            fields[f"gostergeler[].gostergeler[]:{g['kod']}"] = x.indicator(
                full, donem, recs.get(g["kod"]), K.values_stmt(tenant, donem), f"kurul.derleme.deger.{g['kod']}",
                f"değer kaydı {K.donem_label(donem)}", " " + note)
    fields["gostergeler[].gostergeler[]"] = k.hesap("kurul.derleme.gostergeler", F_OLCUM, [vals, cat])
    fields["sayilar"] = k.hesap("kurul.derleme.sayac", "Toplam, hazır, kaynak yok, okunamadı, kırmızı, sarı ve yorumsuz renkli "
                                                        "gösterge sayısı derleme anındaki paneldendir.", [vals, cat, com])
    fields["kritik[]"] = k.hesap("kurul.derleme.kritik", "Kırmızı göstergeler ve onaylı yorumları.", [vals, cat, com])
    fields["eksikYorum"] = k.hesap("kurul.derleme.eksikYorum", "Yorumu olmayan renkli gösterge = rengi kırmızı ya da sarı "
                                                                "olup derleme anında bu dönem onaylı yorumu olmayanlar; "
                                                                "sayı listedeki gösterge sayısıdır.", [vals, cat, com])
    acts = x.portal("kurul.derleme.aksiyonlar", "Açık kurul aksiyonları", K.actions_stmt(tenant, "acik"), note)
    fields["aksiyonOzeti"] = k.hesap("kurul.derleme.aksiyonOzeti", "Açık = durumu açık kurul aksiyonu sayısı; geciken = "
                                                                    "bunlardan termini derleme gününden önce olan. ", [acts])
    if top.get("id"):
        fields["gundem"] = k.hesap("kurul.derleme.gundem", "Gündem sekreterce elle girilir; süre dakikadır.",
                                   [x.portal("kurul.derleme.gundem", "Gündem maddeleri", K.agenda_stmt(top["id"]), note)])
    if top.get("tarih"):
        prev = x.portal("kurul.derleme.oncekiToplanti", "Önceki toplantılar", K.previous_meetings_stmt(tenant, top["tarih"]), note)
        fields["oncekiKararlar"] = k.hesap("kurul.derleme.oncekiKararlar", "Önceki toplantıların kararları: aksiyonu açık olanlar "
                                                                           "ve son toplantıdan beri kapananlar.", [prev])
    risk = content.get("risk") or {}
    if risk.get("sayilar") is not None and risk_ctx is not None:
        memo = getattr(risk_ctx, "memo", {}).get("m47")
        if memo:
            from semantic_bridge import risk_kaynak as RK

            sm, ind = memo
            rec = from_kaynak("m47", RK.for_summary(engine, tenant, sm, logo_db(), crm_db(), ind), {"s": ["sayilar"]})["s"]
            _ids, roots = readd(k, rec, "kurul.derleme.m47.", note)
            if roots:
                fields["risk.sayilar"] = k.hesap("kurul.derleme.riskSayilar", "Risk kaydının sayıları (canlı, kritik, gösterge, "
                                                                              "kırmızı…) derleme anında risk modülünden okundu.",
                                                 roots)
    for key, cap, title, text in (("risk.brifing", risk_log, "Risk brifingi", "Risk modülünün en son onaylı çeyreklik brifingi; "
                                   "metni Zeki AI yazar, her sayısı brifingin olgularında olmak zorundadır."),
                                  ("pazar", market_log, "Pazar özeti", "Pazar araştırmasının son onaylı aylık özeti; kaynak "
                                   "sayısı özetin dayandığı kaynak listesinin uzunluğudur.")):
        val = risk.get("brifing") if key == "risk.brifing" else content.get("pazar")
        if not val or cap is None:
            continue
        ids = [k.sorgu(f"kurul.derleme.{key.split('.')[-1]}.{i}", f"{title} · okuma {i}", "portal", it["sql"], ms=it.get("dbMs"),
                       ran_at=it.get("at"), description=note)
               for i, it in enumerate(cap.sqls(), start=1)]
        if ids:
            fields[key] = k.hesap(f"kurul.derleme.{key}", text, ids)
    k.alanlar(fields)
    return k.to_dict()


def for_package(engine: Any, tenant: str, pid: str, out: dict[str, Any]) -> P.Kaynaklar:
    """`GET /kurul/packages/{id}`: paket kaydı (dondurulan içerik) + derleme anında saklanan zincir."""
    x = _Ctx(engine, tenant)
    k = x.k
    pk = x.portal("kurul.paket", "Kurul paketi kaydı", K.package_stmt(tenant, pid),
                  "Derleme anında dondurulan içerik (icerik_json); ekrandaki değerler bu kayıttan okunur, kaynak rakam "
                  "sonradan değişse de bu sürüm aynı kalır.")
    rec = K.package_queries(engine, tenant, pid)
    fields: dict[str, str] = {}
    if rec and rec.get("fields"):
        saved = {"refs": list(dict.fromkeys(rec["fields"].values())), "sources": rec.get("sources") or {},
                 "formulas": rec.get("formulas") or {}}
        _ids, _roots = readd(k, saved, "")
        for path, ref in rec["fields"].items():
            if not (ref.startswith("hesap:") and ref[6:] in k.formulas) and ref not in k.sources:
                continue
            name = f"kurul.paket.alan.{path}"
            fields["icerik." + path] = k.hesap(name, "Paket derlendiği anda dondurulmuş değer; bugün paket kaydından okunur. "
                                                     "Derleme anının hesabı ve sorguları aşağıda.", [pk, ref])
        fields["icerik"] = k.hesap("kurul.paket.icerik", "Paket içeriği derleme anında dondurulur.", [pk])
    elif rec and rec.get("hata"):
        fields["icerik"] = k.hesap("kurul.paket.icerik", "Değerler paket kaydından okunur; derleme anında sorgu bilgisi "
                                                         f"kurulamamıştı ({_plain(rec['hata'])}).", [pk])
    else:
        fields["icerik"] = k.hesap("kurul.paket.icerik", "Bu sürüm sorgu kaydı tutulmadan önce derlendi: değerler paket "
                                                         "kaydından okunur; ölçüm sorguları yeniden derlenen sürümde görünür.",
                                   [pk])
    fields["ozetMetin"] = k.hesap("kurul.paket.ozet", "Yönetici özetini Zeki AI yazar ya da genel müdür düzeltir; metindeki her "
                                                      "sayı paketin olgularında (gösterge değerleri, aksiyon ve risk sayıları) "
                                                      "olmalıdır, olmayan sayı uyarı olarak gösterilir.", [pk])
    fields["olguDisiSayilar"] = "hesap:kurul.paket.ozet"
    k.alanlar(fields)
    return k
