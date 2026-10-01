"""M7 Yazar ilişkileri: ağır kaynak okumaları önceden hazırlanır, ekran hazır veriden anında hesaplanır.

Kullanıcı kararı (2026-09-28): benzer veri çeken ekranlar açılışta kaynağı beklemez; veri arka planda 5 dakikada
bir (ve «Yenile» ile hemen) tazelenir. Mekanizma `EditorialHomeSnapshots` (diskte atomik parça, tek yazıcı kilidi,
hata olursa son başarılı kayıt korunur, kod değişince eski kayıt okunmaz).

Parçalar:
- **crm**: yürürlükte sözleşmesi olan yazarlar, son 12 ayın CRM olayları, bütün yazarların sadakat izi, yazar
  rolüyle bütün kitaplar (stok kodu, barkod) ve aday havuzu (olası yazar projeleri). Kaynak önbelleği atlanır.
- **sales**: Logo yıllık satış görünümleri, stok kodu × ay × satış/iade (M6 hakediş ve Baskı önerisiyle aynı kural:
  faturalı malzeme satırı, 157 kodları ve bedelsiz satır dışarıda). İçinde bulunulan yıl her turda, geçmiş yıllar
  günde bir yeniden okunur (geçmiş yıl görünümü değişmez; her 5 dakikada 6 yılı taramak Logo'yu boşuna yorar).

Kişiye özel ve portal kayıtları (kart, görüşme, hakediş, yorum özeti) hazırlanmaz: her istekte canlı okunur, ucuzdur.

Hız (2026-09-29): parçalar diskte onlarca MB JSON'dur (bütün yazarlar, bütün kitaplar, altı yılın satışı) ve her turda
(5 dk) yeniden yazılır. Eskiden tur bitince ilk gelen istek (ısı haritası `status()`/`queries()` ile satış parçasını da)
dosyayı istek içinde baştan ayrıştırıyordu; ekranı açan kişi bunu bekliyordu, aynı anda gelen kart/ajanda istekleri de
aynı süreçte işlemci sırası bekliyordu. Şimdi: yeni dosya arkada ayrıştırılır (izleyici iş parçası tur yazar yazmaz
yükler), ayrıştırma sürerken istek bir önceki hazırlığı alır (hazır veri zaten ≤ 5 dk eskidir; rakam hesabı aynı).
Yalnız süreç açılışındaki ilk okuma beklenir (tek okuma, aynı anda gelenler onu bekler). Isı haritasının sadakat
sözlüğü hazırlık ve gün başına bir kez kurulur; hazırlık yokken canlı CRM okuması 5 dk süreç içi bellekte tutulur.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from semantic_bridge import author_growth as G
from semantic_bridge import author_relations as R
from semantic_bridge.editorial_home import EditorialHomeSnapshots, INTERVAL
from semantic_bridge.hizli_bellek import Bellek

log = logging.getLogger("semantic.author_snapshots")

#: Geçmiş yılların satışı bu kadar süre taze sayılır.
PAST_YEAR_SECONDS = 24 * 3600
SALES_YEARS = 6
#: İzleyicinin yeni tur dosyasına bakma aralığı (saniye).
WATCH_SECONDS = 5.0
PARTS = ("crm", "sales")

#: Hazırlık yokken (ilk kurulum, kod değişince yeni klasör) ısı haritasının canlı CRM okuması: aynı metin, tur
#: aralığı kadar süreç içinde tutulur (bayat sunulmaz). Anahtar = kiracı + SQL metni.
CANLI = Bellek("yazar.canli", taze=INTERVAL)


def all_books_sql(schema: str) -> str:
    p = G._prefix(schema)
    return (
        "SELECT e.new_Katilimsaglayan AS kisi, b.new_kitapId, b.new_name, b.new_StokKodu, b.new_EKitapStokKodu, b.new_ean13,"
        " b.new_ilkyayintarihi, MIN(e.CreatedOn) AS CreatedOn"
        f" FROM {p}new_eserkatilimBase e JOIN {p}new_katilimcitipiBase t ON t.new_katilimcitipiId = e.new_katilimciTipi"
        f" JOIN {p}new_kitapBase b ON b.new_kitapId = e.new_Kitap"
        " WHERE e.statecode = 0 AND b.statecode = 0 AND t.new_name = N'Yazar' AND e.new_Katilimsaglayan IS NOT NULL"
        " GROUP BY e.new_Katilimsaglayan, b.new_kitapId, b.new_name, b.new_StokKodu, b.new_EKitapStokKodu, b.new_ean13,"
        " b.new_ilkyayintarihi"
    )


def pool_all_sql(schema: str, since: str) -> str:
    """Olası yazarın bütün projeleri (reddedilen/iptal dahil; süzgeç ekranda)."""
    p = R._prefix(schema)
    return (
        "SELECT k.ContactId, k.FullName, j.new_projeId, j.new_name, j.statuscode, j.CreatedOn, u.FullName AS editor,"
        f" CASE WHEN j.statuscode IN ({', '.join(map(str, R.PROJECT_CLOSED))}) THEN 1 ELSE 0 END AS kapali"
        f" FROM {p}new_projeBase j JOIN {p}ContactBase k ON k.ContactId = j.new_OlasYazarYazar"
        f" LEFT JOIN {p}SystemUserBase u ON u.SystemUserId = j.new_editoru"
        f" WHERE j.statecode = 0 AND k.statecode = 0 AND j.CreatedOn >= '{R._since(since)}'"
        f" AND NOT {R._is_author(p, 'j.new_OlasYazarYazar')}"
    )


def year_sales_sql(year: int) -> str:
    from semantic_bridge.contracts_royalty import SALES_FILTER
    from semantic_bridge.management import SALES_VIEW_FILTER
    return (
        "SELECT s.[Malzeme/Hizmet Kodu] AS kod, s.[Ay] AS ay, s.[Satis_Iade] AS tur, SUM(s.[Miktar]) AS miktar,"
        f" SUM(s.[Net Tutar]) AS net FROM dbo.V_SatisRaporu_{int(year)} AS s"
        f" WHERE {SALES_VIEW_FILTER} AND {SALES_FILTER}"
        " GROUP BY s.[Malzeme/Hizmet Kodu], s.[Ay], s.[Satis_Iade]"
    )


def _compact(rows: list[dict[str, Any]]) -> dict[str, list[list[Any]]]:
    out: dict[str, list[list[Any]]] = {}
    for r in rows:
        code = str(r.get("kod") or "").strip()
        if not code:
            continue
        ret = 1 if str(r.get("tur") or "").strip().replace("İ", "i").lower().startswith("iade") else 0
        out.setdefault(code, []).append([int(G._f(r.get("ay"))), ret, G._f(r.get("miktar")), G._f(r.get("net"))])
    return out


class AuthorSnapshots:
    def __init__(self, scope: Callable[[], list[Any]], schema: Callable[[], str], pool_since: Callable[[], str],
                 fetch_all: Callable[[str], list[dict[str, Any]]],
                 logo: Callable[[], Any]):
        """`fetch_all(sql)` CRM'den tam sonuç (önbelleksiz); `logo()` → (views: set[int], run(sql) -> satırlar,
        data_end(yıl) -> date, close())."""
        self._schema, self._pool_since, self._fetch_all, self._logo = schema, pool_since, fetch_all, logo
        # ad → (dosyanın mtime'ı, değer ya da None, dosya yolu). Yol da anahtardır: kapsam (şema, kiracı) değişince
        # başka klasörün verisi sunulmaz.
        self._memo: dict[str, tuple[float, Optional[dict[str, Any]], Path]] = {}
        self._memo_lock = threading.Lock()
        self._load_locks: dict[str, threading.Lock] = {name: threading.Lock() for name in PARTS}
        self._loading: set[str] = set()
        self._loyalty: Optional[tuple[Any, date, dict[str, dict[str, Any]]]] = None
        self._bg: Optional[threading.Thread] = None
        self._watch: Optional[threading.Thread] = None
        self.snap = EditorialHomeSnapshots(
            lambda: ["author-snapshots", *scope()], self._builders,
            sources=("author_snapshots.py", "author_growth.py", "author_relations.py"), name="author-snapshots")

    # ---- parçalar
    def _builders(self) -> dict[str, Callable[[], Any]]:
        return {"crm": self._build_crm, "sales": self._build_sales}

    def _build_crm(self) -> dict[str, Any]:
        schema = self._schema()
        keys = R.month_keys()
        started = time.time()
        # Sorgu bilgisi: hazırlıkta çalışan CRM metni, satır, süre ve an (sonuç satırı ayrıca saklanmaz).
        queries: list[dict[str, Any]] = []

        def fetch(tag: str, sql: str) -> list[dict[str, Any]]:
            t0 = time.time()
            rows = self._fetch_all(sql)
            queries.append({"tag": tag, "conn": "crm", "sql": sql, "rows": len(rows),
                            "dbMs": int((time.time() - t0) * 1000), "at": time.time()})
            return rows

        out = {
            "authors": fetch("sozlesmeliYazarlar", R.contracted_authors_sql(schema)),
            "events": fetch("olaylar", R.crm_events_sql(schema, keys[0] + "-01")),
            "loyalty": fetch("sadakat", G.loyalty_sql(schema)),
            "books": fetch("kitaplar", all_books_sql(schema)),
            "pool": fetch("havuz", pool_all_sql(schema, self._pool_since())),
            "poolSince": self._pool_since(),
            "months": keys,
            "queries": queries,
        }
        out["seconds"] = round(time.time() - started, 1)
        return out

    def _build_sales(self) -> dict[str, Any]:
        # Önceki tur bellekteyse dosya ikinci kez ayrıştırılmaz (aynı dosya: mtime ve yol tutuyor).
        previous = (self._previous("sales") or {}).get("data") or {}
        years_prev = previous.get("years") or {}
        views, run, data_end, close = self._logo()
        try:
            return self._read_years(previous, years_prev, views, run, data_end)
        finally:
            close()

    def _read_years(self, previous, years_prev, views, run, data_end) -> dict[str, Any]:
        today = date.today()
        wanted = [y for y in range(today.year - SALES_YEARS + 1, today.year + 1) if y in views]
        years: dict[str, Any] = {}
        started = time.time()
        for y in wanted:
            old = years_prev.get(str(y))
            if y < today.year and old and time.time() - old.get("at", 0) < PAST_YEAR_SECONDS:
                years[str(y)] = old
                continue
            t0 = time.time()
            sql = year_sales_sql(y)
            rows = run(sql)
            # Sorgu bilgisi: o yılın okumasında çalışan Logo metni (yıllık görünüm), satır, süre, an.
            years[str(y)] = {"at": time.time(), "rows": _compact(rows),
                             "query": {"sql": sql, "rows": len(rows), "dbMs": int((time.time() - t0) * 1000), "at": time.time()}}
        end = data_end(max(wanted)) if wanted else None
        from semantic_bridge.contracts_royalty import data_end_sql
        return {"years": years, "dataEnd": end.isoformat() if end else None,
                "dataEndQuery": ({"sql": data_end_sql(max(wanted)), "at": time.time()} if wanted else None),
                "missing": [y for y in range(today.year - SALES_YEARS + 1, today.year + 1) if y not in views],
                "seconds": round(time.time() - started, 1)}

    # ---- okuma (dosya değişmedikçe bellekten; yeni dosya arkada ayrıştırılır)
    def part(self, name: str) -> Optional[dict[str, Any]]:
        path: Path = self.snap.directory() / f"{name}.json"
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return None
        with self._memo_lock:
            hit = self._memo.get(name)
        if hit and hit[2] == path:
            if hit[0] == mtime:
                return hit[1]
            # Tur yeni dosya yazdı: ayrıştırma arkada, bu istek bir önceki hazırlığı alır (beklemez).
            self._load_later(name, path)
            return hit[1]
        return self._load(name, path)

    def _load(self, name: str, path: Path) -> Optional[dict[str, Any]]:
        """Dosyayı ayrıştırıp belleğe koyar; aynı parçayı aynı anda isteyenler tek ayrıştırmayı bekler."""
        with self._load_locks.setdefault(name, threading.Lock()):
            try:
                mtime = path.stat().st_mtime
            except OSError:
                return None
            with self._memo_lock:
                hit = self._memo.get(name)
            if hit and hit[0] == mtime and hit[2] == path:
                return hit[1]
            value = EditorialHomeSnapshots.load(path)
            value = value if value.get("data") else None
            with self._memo_lock:
                self._memo[name] = (mtime, value, path)
            return value

    def _load_later(self, name: str, path: Path) -> None:
        with self._memo_lock:
            if name in self._loading:
                return
            self._loading.add(name)

        def run() -> None:
            try:
                self._load(name, path)
            except Exception:  # noqa: BLE001 — önceki hazırlık sunulmaya devam eder
                log.exception("author snapshots: %s parçası ayrıştırılamadı", name)
            finally:
                with self._memo_lock:
                    self._loading.discard(name)

        threading.Thread(target=run, daemon=True, name=f"author-snapshots-load-{name}").start()

    def _previous(self, name: str) -> Optional[dict[str, Any]]:
        """Turun okuduğu önceki kayıt: bellekteki aynı dosyaysa o, değilse diskten (hatalı kayıt da döner)."""
        path: Path = self.snap.directory() / f"{name}.json"
        try:
            mtime = path.stat().st_mtime
        except OSError:
            return None
        with self._memo_lock:
            hit = self._memo.get(name)
        if hit and hit[0] == mtime and hit[2] == path and hit[1] is not None:
            return hit[1]
        return EditorialHomeSnapshots.load(path)

    def warm(self) -> None:
        """Diskteki parçaları belleğe alır (izleyici ve açılış); değişmemiş dosya yeniden ayrıştırılmaz."""
        for name in PARTS:
            if self.snap.stopping.is_set():
                return
            try:
                self._load(name, self.snap.directory() / f"{name}.json")
            except Exception:  # noqa: BLE001
                log.exception("author snapshots: %s parçası belleğe alınamadı", name)

    def status(self) -> dict[str, Any]:
        out: dict[str, Any] = {"intervalSeconds": INTERVAL, "refreshing": bool(self._bg and self._bg.is_alive())}
        for name in ("crm", "sales"):
            p = self.part(name)
            out[name] = None if p is None else {
                "updatedAt": datetime.fromtimestamp(p.get("updatedAt", 0), timezone.utc).isoformat(),
                "error": p.get("error"), "seconds": (p.get("data") or {}).get("seconds")}
        return out

    def refresh_now(self) -> dict[str, Any]:
        """«Yenile»: arka planda hemen bir tur (sürüyorsa yenisi açılmaz); ekran hazır veriyi göstermeye devam eder."""
        if not (self._bg and self._bg.is_alive()):
            def run():
                try:
                    self.snap.refresh(force=True)
                except Exception:  # noqa: BLE001
                    log.exception("author snapshots: zorla yenileme başarısız")
            self._bg = threading.Thread(target=run, daemon=True, name="author-snapshots-now")
            self._bg.start()
        return self.status()

    def start(self) -> None:
        self.snap.start()

        def watch() -> None:
            # Tur dosyayı yazar yazmaz ayrıştırılır; ekranı açan kişi ayrıştırmayı beklemez.
            while True:
                self.warm()
                if self.snap.stopping.wait(WATCH_SECONDS):
                    return

        self._watch = threading.Thread(target=watch, daemon=True, name="author-snapshots-watch")
        self._watch.start()

    def stop(self) -> None:
        self.snap.stop()

    # ---- hazır veriden hesap
    def queries(self) -> dict[str, Any]:
        """Hazır parçaları dolduran okumalarda çalışan CRM/Logo sorguları (sorgu bilgisi kökeni). Kayıt tutmayan önceki
        sürümün parçasında boş döner."""
        crm, sales = self.part("crm"), self.part("sales")
        out: dict[str, Any] = {"crm": [], "sales": [], "dataEnd": None}
        if crm is not None:
            out["crm"] = list((crm.get("data") or {}).get("queries") or [])
        if sales is not None:
            data = sales.get("data") or {}
            out["sales"] = [dict(y["query"], year=int(k)) for k, y in sorted((data.get("years") or {}).items())
                            if isinstance(y, dict) and y.get("query")]
            out["dataEnd"] = data.get("dataEndQuery")
        return out

    def crm_for_heatmap(self) -> Optional[dict[str, Any]]:
        p = self.part("crm")
        return None if p is None else p["data"]

    def loyalty_map(self, crm: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Hazır CRM parçasının bütün yazarlarının sadakati (`G.loyalty_map`, bugünün tarihiyle). Parça ve gün başına
        bir kez kurulur; sonuç paylaşılır, çağıran değiştirmez (ısı haritası yalnız okur)."""
        today = G._now().date()
        with self._memo_lock:
            hit = self._loyalty
        if hit is not None and hit[0] is crm and hit[1] == today:
            return hit[2]
        out = G.loyalty_map(crm["loyalty"], today)
        with self._memo_lock:
            self._loyalty = (crm, today, out)
        return out

    @staticmethod
    def live_reader(fetch_all: Callable[[str], list[dict[str, Any]]], tenant: str,
                    fresh: bool = False) -> Callable[[str], list[dict[str, Any]]]:
        """Hazırlık yokken ısı haritasının canlı CRM okuyucusu: aynı metin `CANLI` bellekte (tur aralığı kadar);
        `fresh` («Verileri yenile») kaynağı bekler. Dönen liste paylaşılır; çağıran değiştirmez."""
        return lambda sql: CANLI.al((tenant, sql), lambda: fetch_all(sql), zorla=fresh)

    def books_of(self, contact_id: str) -> Optional[list[dict[str, Any]]]:
        """Yazarın yazar rolüyle hazır kitap satırları (stok kodu, barkod); CRM parçası hazır değilse None."""
        crm = self.part("crm")
        if crm is None:
            return None
        cid = G._guid(contact_id)
        return [b for b in crm["data"]["books"] if str(b.get("kisi") or "").strip("{}").lower() == cid]

    def growth_inputs(self, contact_id: str) -> Optional[dict[str, Any]]:
        """Bir yazarın hazır kitap satırları, sadakat izi ve satış okuyucusu; parçalar hazır değilse None."""
        crm, sales = self.part("crm"), self.part("sales")
        if crm is None or sales is None:
            return None
        cid = G._guid(contact_id)
        books = [b for b in crm["data"]["books"] if str(b.get("kisi") or "").strip("{}").lower() == cid]
        loy = next((r for r in crm["data"]["loyalty"] if str(r.get("kisi") or "").strip("{}").lower() == cid), None)
        years = sales["data"].get("years") or {}

        def logo(codes: list[str], start: date, end: date):
            want = set(codes)
            rows = []
            for y, part in years.items():
                yi = int(y)
                if yi < start.year or yi > end.year:
                    continue
                for code, items in (part.get("rows") or {}).items():
                    if code not in want:
                        continue
                    for ay, ret, qty, net in items:
                        rows.append({"kod": code, "yil": yi, "ay": ay, "tur": "İade" if ret else "Satış", "miktar": qty, "net": net})
            end_day = G._day(sales["data"].get("dataEnd"))
            return rows, end_day, [y for y in sales["data"].get("missing") or [] if start.year <= y <= end.year]

        return {"books": books, "loyalty": loy, "logo": logo,
                "updatedAt": min(crm.get("updatedAt", 0), sales.get("updatedAt", 0))}

    def pool_page(self, engine: Any, tenant: str, page_no: int, *, q: str = "", closed: bool = False) -> Optional[dict[str, Any]]:
        p = self.part("crm")
        if p is None:
            return None
        people: dict[str, dict[str, Any]] = {}
        for r in p["data"]["pool"]:
            is_closed = int(G._f(r.get("kapali"))) == 1
            if is_closed and not closed:
                continue
            cid = str(r.get("ContactId") or "").strip("{}").lower()
            if not cid:
                continue
            item = people.setdefault(cid, {"crmContactId": cid, "name": R._s(r.get("FullName")), "projects": 0, "last": None,
                                           "latest": None, "cardId": None, "cardStage": None})
            item["projects"] += 1
            on = str(r.get("CreatedOn") or "")
            if item["last"] is None or on > item["last"]:
                item["last"] = on
                item["latest"] = {"id": str(r.get("new_projeId") or "").lower(), "name": R._s(r.get("new_name")),
                                  "status": R._s(r.get("statuscode")), "on": on, "editor": R._s(r.get("editor"))}
        nq = R._norm(q)
        items = [i for i in people.values() if not nq or nq in R._norm(i["name"] or "")]
        items.sort(key=lambda i: (i["last"] or ""), reverse=True)
        total = len(items)
        page_no = max(0, int(page_no))
        chunk = items[page_no * R.PAGE_SIZE:(page_no + 1) * R.PAGE_SIZE]
        ids = [i["crmContactId"] for i in chunk]
        if ids:
            import sqlalchemy as sa
            with engine.connect() as c:
                for row in c.execute(sa.select(R.CARDS.c.id, R.CARDS.c.stage, R.CARDS.c.crm_contact_id).where(
                        R.CARDS.c.tenant_id == tenant, R.CARDS.c.crm_contact_id.in_(ids))).fetchall():
                    for i in chunk:
                        if i["crmContactId"] == row.crm_contact_id:
                            i["cardId"], i["cardStage"] = row.id, row.stage
        return {"items": chunk, "total": total, "page": page_no, "pageSize": R.PAGE_SIZE, "since": p["data"].get("poolSince"),
                "db": None, "snapshotAt": datetime.fromtimestamp(p.get("updatedAt", 0), timezone.utc).isoformat()}
