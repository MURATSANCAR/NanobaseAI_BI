"""SEO & GEO modülü: T-soft ürünlerinin denetimi, model önerisi, insan onayıyla T-soft'a gönderim; Search Console.

Akış (docs/analiz/seo-geo-modul-2026-09-25.md):
1. Eşitleme: T-soft'taki bütün ürünler sayfa sayfa okunur, kurallardan geçer, puan ve sorunlarıyla saklanır.
2. Öneri: kullanıcı bir ürün için öneri ister; model ürünün kendi kaydından SEO alanlarını yazar.
3. Karar: onay verebilen kişi öneriyi (gerekirse düzenleyip) onaylar ya da reddeder. Onay yalnız kararı ve
   onaylanan metni kaydeder. **T-soft'a hiçbir şey gönderilmez** (kullanıcı yasağı 2026-09-25; istemci yalnız
   okur). Onaylanan metnin gideceği yer CRM'dir; CRM Web API yetkisi gelince bu adım eklenecek.
Her karar ve gönderim `semantic_audit`'e yazılır.

Uçlar `/api/v1/seo-geo/*`; oturum şart. `run-due` gece zamanlayıcısının ucudur (yalnız çağıran belirteci).
"""
from __future__ import annotations

import logging
import threading
import uuid
from datetime import date, timedelta
from typing import Any, Optional

import sqlalchemy as sa
from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from . import connections, llms, pages, propose, redirects, rules, schema
import hashlib

from .store import GSC, LINKS, PRODUCTS, PROPOSALS, QUESTIONS, REDIRECTS, RUNS, SCHEMA, dumps, ensure, iso, loads, now

log = logging.getLogger("semantic.seo_geo")

#: Öncelik: kitabın toplam satış adedi (T-soft `CountTotalSales`), eşitse görüntülenme (`StatViews`). Çok satan ve çok
#: bakılan sayfadaki düzeltme en çok okura ulaşır. JSON içinden okunur; boş/bozuk değer 0 sayılır.
def _json_num(key: str) -> Any:
    raw = sa.func.nullif(sa.func.regexp_replace(sa.cast(PRODUCTS.c.data_json, sa.JSON)[key].as_string(), "[^0-9.]", "", "g"), "")
    return sa.func.coalesce(sa.cast(raw, sa.Float), 0.0)


SALES, VIEWS = _json_num("CountTotalSales"), _json_num("StatViews")


class Decision(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")
    fields: dict[str, str] = Field(default_factory=dict)
    note: str = Field(default="", max_length=1000)


class BulkApprove(BaseModel):
    ids: list[str] = Field(min_length=1)
    note: str = Field(default="", max_length=1000)


class Question(BaseModel):
    text: str = Field(min_length=5, max_length=500)
    category: str = Field(default="", max_length=80)


def _err(status: int, message: str) -> HTTPException:
    return HTTPException(status, {"code": "SEO", "message": message})


class SeoGeo:
    """Arka plan eşitlemesi süreç içinde tek iş parçacığıyla koşar; aynı anda ikincisi başlamaz."""

    def __init__(self, runtime) -> None:
        self.runtime = runtime
        self._sync_lock = threading.Lock()
        self.state: dict[str, Any] = {"running": False, "kind": None, "done": 0, "total": None,
                                      "startedAt": None, "error": None}
        # Ön üretim: puanı en düşük üründen başlayarak öneriler model boştayken hazırlanır.
        self._batch_lock = threading.Lock()
        self.batch: dict[str, Any] = {"running": False, "done": 0, "failed": 0, "queue": None,
                                      "startedAt": None, "finishedAt": None, "error": None}
        self._crawl_lock = threading.Lock()
        self.crawl: dict[str, Any] = {"running": False, "done": 0, "queue": None, "startedAt": None, "finishedAt": None, "error": None}
        # Sayfa önerisi uçlarla birlikte `register` içinde kurulur; ön üretim buradan çağırır.
        self.page_queue: Any = None
        self.make_page_proposal: Any = None
        # Aynı ürün için aynı anda ikinci üretim başlamasın (ekran açılışı + gece işi).
        self._gen_lock = threading.Lock()
        self._generating: set[str] = set()

    # ---------------------------------------------------------------- ortak
    def engine(self) -> sa.engine.Engine:
        from semantic_bridge import admin as admin_mod

        eng = self.runtime().store.engine
        ensure(eng)
        # Ayar okuyucu (T-soft kullanıcısı, Google anahtarı) veritabanına bağlanmadan `conf` yalnız ortam
        # dosyasını görür; köprü yeniden başlayıp Yönetim ekranı henüz açılmadıysa eşitleme "tanımlı değil" derdi.
        admin_mod.ensure(eng)
        return eng

    def tenant(self) -> str:
        return self.runtime().settings.tenant_id

    @staticmethod
    def conf(key: str) -> str:
        from semantic_bridge import admin as admin_mod

        return admin_mod.conf(key)

    def can_approve(self, user: str) -> bool:
        from semantic_bridge import admin as admin_mod

        listed = [u.strip().lower() for u in self.conf("SEO_APPROVERS").split(",") if u.strip()]
        return user.lower() in listed if listed else admin_mod.is_admin(user)

    def audit(self, user: str, action: str, object_id: str, title: str, detail: Any) -> None:
        from semantic_bridge import admin as admin_mod

        admin_mod.audit(self.engine(), user, action, "seo_product", object_id, title, detail)

    # ---------------------------------------------------------------- eşitleme
    def start_sync(self, user: str) -> bool:
        if not connections.tsoft.configured():
            raise _err(409, "T-soft bağlantısı tanımlı değil (Yönetim → SEO & GEO).")
        if not self._sync_lock.acquire(blocking=False):
            return False
        self.state.update(running=True, kind="tsoft", done=0, total=None, startedAt=iso(now()), error=None)
        threading.Thread(target=self._sync, args=(user,), name="seo-sync", daemon=True).start()
        return True

    def _sync(self, user: str) -> None:
        eng, tenant = self.engine(), self.tenant()
        run_id = uuid.uuid4().hex
        with eng.begin() as c:
            c.execute(RUNS.insert().values(id=run_id, tenant_id=tenant, kind="tsoft", started_at=now(), started_by=user))
        products: list[dict[str, Any]] = []
        error = None
        try:
            while True:
                rows, total = connections.tsoft.products(len(products))
                products.extend(rows)
                self.state.update(done=len(products), total=total)
                if len(rows) < connections.PAGE:
                    break
            self._store(products)
            # Sayfa ayarları ve yönlendirmeler: yazar/kategori/yayınevi sayfaları ve anasayfa 301'leri için.
            self.state.update(kind="links")
            links = self._all("link/getLinks")
            refs = self._all("link/getReferralLinks")
            self._store_links(links)
            self._store_redirects(links, refs, products)
        except Exception as e:  # noqa: BLE001 — hata ekrana taşınır, eski veri korunur
            error = str(e)[:1000]
            log.exception("seo sync failed")
        finally:
            with eng.begin() as c:
                c.execute(RUNS.update().where(RUNS.c.id == run_id).values(
                    finished_at=now(), count=len(products), error=error))
            self.state.update(running=False, error=error)
            self._sync_lock.release()

    def _all(self, path: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        while True:
            rows = connections.tsoft.call(path, {"start": len(out), "limit": connections.PAGE}).get("data") or []
            out.extend(rows)
            self.state.update(done=len(out), total=None)
            if len(rows) < connections.PAGE:
                return out

    def _store_links(self, links: list[dict[str, Any]]) -> None:
        tenant, at = self.tenant(), now()
        seen: dict[str, dict[str, Any]] = {}
        for l in links:
            link = str(l.get("Link") or "").strip().strip("/")[:600]
            if link and str(l.get("Type") or "") != "301" and link not in seen:
                seen[link] = dict(tenant_id=tenant, link=link, type=str(l.get("Type") or "")[:40],
                                  table_id=str(l.get("TableId") or "")[:40], title=l.get("Title"),
                                  description=l.get("Description"), data_json=dumps(l), synced_at=at)
        values = list(seen.values())
        with self.engine().begin() as c:
            c.execute(LINKS.delete().where(LINKS.c.tenant_id == tenant))
            for i in range(0, len(values), 1000):
                c.execute(LINKS.insert(), values[i:i + 1000])

    def _store_redirects(self, links: list[dict[str, Any]], refs: list[dict[str, Any]],
                         products: list[dict[str, Any]]) -> None:
        """Anasayfaya giden 301'ler için öneri; verilmiş kararlar korunur, düzelmiş olan (artık anasayfaya gitmeyen)
        bekleyen kayıt silinir."""
        tenant, at = self.tenant(), now()
        idx = redirects.Index(links, products)
        home = {str(r.get("Link") or "").strip().strip("/"): r for r in refs
                if redirects.is_home(r.get("RedirectLink")) and str(r.get("RedirectLink") or "").strip()}
        with self.engine().begin() as c:
            old = {r["link"]: r for r in c.execute(sa.select(REDIRECTS).where(REDIRECTS.c.tenant_id == tenant)).mappings()}
            for link, r in home.items():
                sug = redirects.suggest(link, idx)
                vals = dict(current_target=str(r.get("RedirectLink") or "")[:600], target=(sug["target"] or None),
                            target_type=sug["type"], confidence=sug["confidence"], reason=sug["reason"][:600],
                            alternatives_json=dumps(sug["alternatives"]), synced_at=at)
                if link in old:
                    c.execute(REDIRECTS.update().where(REDIRECTS.c.id == old[link]["id"]).values(**vals))
                else:
                    rid = hashlib.sha1(f"{tenant}|{link}".encode()).hexdigest()[:16]
                    c.execute(REDIRECTS.insert().values(id=rid, tenant_id=tenant, link=link[:600], status="bekliyor", **vals))
            gone = [r["id"] for l, r in old.items() if l not in home and r["status"] == "bekliyor"]
            if gone:
                c.execute(REDIRECTS.delete().where(REDIRECTS.c.id.in_(gone)))

    def _store(self, products: list[dict[str, Any]]) -> None:
        lim = rules.thresholds(self.conf)
        dups = rules.duplicate_titles(products)
        at, tenant = now(), self.tenant()
        values = []
        for p in products:
            pid = str(p.get("ProductId") or "").strip()
            if not pid:
                continue
            a = rules.audit(p, lim, dups)
            values.append(dict(
                tenant_id=tenant, product_id=pid, code=str(p.get("ProductCode") or "")[:120],
                name=str(p.get("ProductName") or "")[:500], brand=str(p.get("Brand") or "")[:300],
                active=str(p.get("IsActive", "1")).lower() not in ("0", "false"),
                score=a["score"], issues_json=dumps(a["issues"]),
                rules="," + ",".join(i["rule"] for i in a["issues"]) + ",", data_json=dumps(p), synced_at=at))
        # Tam liste geldiyse tablo onunla değişir: T-soft'tan silinen ürün burada da kalmaz.
        with self.engine().begin() as c:
            c.execute(PRODUCTS.delete().where(PRODUCTS.c.tenant_id == tenant))
            for i in range(0, len(values), 500):
                c.execute(PRODUCTS.insert(), values[i:i + 500])

    # ---------------------------------------------------------------- Search Console
    def refresh_gsc(self, days: int = 28) -> dict[str, Any]:
        end = date.today() - timedelta(days=3)          # son günler "final" değil
        start = end - timedelta(days=days - 1)
        s, e = start.isoformat(), end.isoformat()
        out = {"daily": connections.gsc_all(s, e, ["date"]),
               "queries": connections.gsc_all(s, e, ["query"]),
               "pages": connections.gsc_all(s, e, ["page"])}
        tenant = self.tenant()
        with self.engine().begin() as c:
            for kind, rows in out.items():
                c.execute(GSC.delete().where(GSC.c.tenant_id == tenant, GSC.c.kind == kind))
                c.execute(GSC.insert().values(tenant_id=tenant, kind=kind, start_date=s, end_date=e,
                                              rows_json=dumps(rows), saved_at=now()))
        return {k: len(v) for k, v in out.items()}

    def gsc(self, kind: str) -> Optional[dict[str, Any]]:
        with self.engine().connect() as c:
            r = c.execute(sa.select(GSC).where(GSC.c.tenant_id == self.tenant(), GSC.c.kind == kind)).mappings().first()
        if not r:
            return None
        return {"start": r["start_date"], "end": r["end_date"], "savedAt": iso(r["saved_at"]),
                "rows": loads(r["rows_json"], [])}

    # ---------------------------------------------------------------- ürün
    def product_row(self, pid: str) -> dict[str, Any]:
        with self.engine().connect() as c:
            r = c.execute(sa.select(PRODUCTS).where(PRODUCTS.c.tenant_id == self.tenant(),
                                                    PRODUCTS.c.product_id == pid)).mappings().first()
        if not r:
            raise _err(404, "Ürün bulunamadı; önce T-soft eşitlemesi yapılmalı.")
        return dict(r)

    def proposal(self, proposal_id: str) -> dict[str, Any]:
        with self.engine().connect() as c:
            r = c.execute(sa.select(PROPOSALS).where(PROPOSALS.c.tenant_id == self.tenant(),
                                                     PROPOSALS.c.id == proposal_id)).mappings().first()
        if not r:
            raise _err(404, "Öneri bulunamadı.")
        return dict(r)

    def rescore(self, p: dict[str, Any], fields: dict[str, str]) -> int:
        return rules.audit({**p, **fields}, rules.thresholds(self.conf), set())["score"]

    def make_proposal(self, pid: str, user: str, priority: Optional[int] = None) -> dict[str, Any]:
        with self._gen_lock:
            if pid in self._generating:
                raise _err(409, "Bu ürün için öneri şu an yazılıyor; birkaç saniye sonra yeniden açın.")
            self._generating.add(pid)
        try:
            return self._make_proposal(pid, user, priority)
        finally:
            with self._gen_lock:
                self._generating.discard(pid)

    def _make_proposal(self, pid: str, user: str, priority: Optional[int]) -> dict[str, Any]:
        row = self.product_row(pid)
        p = loads(row["data_json"], {})
        llm = self.runtime().llm_for("seo", priority)
        if llm is None:
            raise _err(503, "Yapay zekâ modeli bu kurulumda tanımlı değil.")
        try:
            fields = propose.suggest(llm, p, rules.thresholds(self.conf))
        except ValueError as e:
            raise _err(502, f"Öneri üretilemedi: {e}") from None
        before = {k: str(p.get(k) or "") for k in propose.FIELDS}
        pid_new = uuid.uuid4().hex
        with self.engine().begin() as c:
            # Aynı ürünün bekleyen eski önerisi yenisiyle değişir; karar verilmişler geçmişte kalır.
            c.execute(PROPOSALS.delete().where(PROPOSALS.c.tenant_id == self.tenant(),
                                               PROPOSALS.c.product_id == pid, PROPOSALS.c.status == "hazir"))
            c.execute(PROPOSALS.insert().values(
                id=pid_new, tenant_id=self.tenant(), product_id=pid, status="hazir", fields_json=dumps(fields),
                before_json=dumps(before), score_before=row["score"], score_after=self.rescore(p, fields),
                model=getattr(llm, "model", None) or self.conf("LLM_MODEL_NAME"), created_by=user, created_at=now()))
        self.audit(user, "create", pid, row["name"], {"proposal": pid_new})
        return self.proposal(pid_new)

    def start_batch(self, user: str, budget: int) -> bool:
        """Önerisi olmayan, düzeltilebilir sorunlu aktif ürünler için öneri yazar; en çok satandan başlar.
        Süre bütçesi dolunca durur, kalan iş sonraki tura kalır (sıra her turda yeniden kurulur, tavan yok)."""
        if not self._batch_lock.acquire(blocking=False):
            return False
        self.batch.update(running=True, done=0, failed=0, queue=None, startedAt=iso(now()), finishedAt=None, error=None)
        threading.Thread(target=self._batch, args=(user, budget), name="seo-batch", daemon=True).start()
        return True

    def _batch(self, user: str, budget: int) -> None:
        import time as _t
        from semantic_layer.runtime.llm_queue import BATCH

        deadline = _t.monotonic() + max(60, budget)
        try:
            tenant = self.tenant()
            has = sa.select(PROPOSALS.c.product_id).where(PROPOSALS.c.tenant_id == tenant)
            with self.engine().connect() as c:
                rows = c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.issues_json).where(
                    PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.active.is_(True), PRODUCTS.c.rules != ",,",
                    PRODUCTS.c.product_id.not_in(has)).order_by(SALES.desc(), VIEWS.desc(), PRODUCTS.c.score.asc(),
                                                                 PRODUCTS.c.product_id)).all()
            queue = [pid for pid, issues in rows if propose.fixable(loads(issues, []))]
            # Sayfalar (yazar/kategori/yayınevi) ürünlerle karışık: her 3 üründen sonra 1 sayfa; ikisi de çok satandan.
            # Ürün sırası binlerce; sayfalar sona kalsa günlerce sıra gelmezdi.
            pages_q = self.page_queue() if self.page_queue else []
            self.batch["queue"] = len(queue) + len(pages_q)
            prod_jobs = [(lambda pid=pid: self.make_proposal(pid, user, BATCH)) for pid in queue]
            page_jobs = [(lambda k=k: self.make_page_proposal(k[0], k[1], user, BATCH)) for k in pages_q]
            jobs = []
            while prod_jobs or page_jobs:
                jobs += prod_jobs[:3]
                del prod_jobs[:3]
                jobs += page_jobs[:1]
                del page_jobs[:1]
            for job in jobs:
                if _t.monotonic() > deadline:
                    break
                try:
                    job()
                    self.batch["done"] += 1
                except HTTPException as e:
                    if e.status_code == 503:
                        raise
                    self.batch["failed"] += 1
        except Exception as e:  # noqa: BLE001 — tur durur, üretilenler kalır
            self.batch["error"] = str(getattr(e, "detail", e))[:500]
            log.exception("seo batch failed")
        finally:
            self.batch.update(running=False, finishedAt=iso(now()))
            self._batch_lock.release()

    def start_crawl(self, budget: int, delay: float = 1.0) -> bool:
        """Ürün sayfalarının şema denetimi: hiç bakılmamış ya da en eski bakılan önce, eşitse çok satan önce.
        Bütçe dolunca durur; sonraki tur kaldığı yerden sürer (tavan yok)."""
        if not self._crawl_lock.acquire(blocking=False):
            return False
        self.crawl.update(running=True, done=0, queue=None, startedAt=iso(now()), finishedAt=None, error=None)
        threading.Thread(target=self._crawl, args=(budget, delay), name="seo-schema", daemon=True).start()
        return True

    def _crawl(self, budget: int, delay: float) -> None:
        import time as _t

        deadline = _t.monotonic() + max(60, budget)
        tenant, site = self.tenant(), (self.conf("SEO_SITE_URL") or "https://timas.com.tr").rstrip("/")
        fetcher = None
        try:
            with self.engine().connect() as c:
                rows = c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.data_json, SCHEMA.c.checked_at)
                                 .select_from(PRODUCTS.outerjoin(SCHEMA, sa.and_(SCHEMA.c.tenant_id == PRODUCTS.c.tenant_id,
                                                                                SCHEMA.c.product_id == PRODUCTS.c.product_id)))
                                 .where(PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.active.is_(True))
                                 .order_by(SCHEMA.c.checked_at.asc().nullsfirst(), SALES.desc())).all()
            queue = []
            for pid, data, _ in rows:
                p = loads(data, {})
                if str(p.get("Barcode") or "").startswith(("978", "979")) and p.get("SeoLink"):
                    queue.append((pid, f"{site}/{str(p['SeoLink']).strip('/')}", _num(p.get("CommentCount")),
                                  schema.has_faq(rules.text_of(p.get("Details")))))
            self.crawl["queue"] = len(queue)
            fetcher = schema.Fetcher(site)
            org_saved = False
            for pid, url, comments, faq in queue:
                if _t.monotonic() > deadline:
                    break
                if not fetcher.allowed(url):
                    continue
                try:
                    code, html = fetcher.get(url)
                except Exception:  # noqa: BLE001 — ağ hatası sayfanın sorunu sayılır, tur sürer
                    code, html = 0, ""
                if code == 200:
                    page = schema.parse(html)
                    found = schema.audit(page, comments, faq)
                    types = sorted({t for it in page["items"] for t in schema._types(it)})
                    if not org_saved:
                        self._save_schema("_org", site, 200, [], schema.organization(page))
                        org_saved = True
                else:
                    found, types = ["fetch_error"], []
                self._save_schema(pid, url, code, found, types)
                self.crawl["done"] += 1
                _t.sleep(delay)
        except Exception as e:  # noqa: BLE001
            self.crawl["error"] = str(e)[:500]
            log.exception("seo schema crawl failed")
        finally:
            if fetcher:
                fetcher.close()
            self.crawl.update(running=False, finishedAt=iso(now()))
            self._crawl_lock.release()

    def _save_schema(self, pid: str, url: str, code: int, found: list[str], types: Any) -> None:
        tenant = self.tenant()
        vals = dict(url=url[:800], status=code, issues="," + ",".join(found) + ",", types_json=dumps(types), checked_at=now())
        with self.engine().begin() as c:
            n = c.execute(SCHEMA.update().where(SCHEMA.c.tenant_id == tenant, SCHEMA.c.product_id == pid).values(**vals)).rowcount
            if not n:
                c.execute(SCHEMA.insert().values(tenant_id=tenant, product_id=pid, **vals))

    def approve(self, prop: dict[str, Any], fields: dict[str, str], user: str, note: str) -> dict[str, Any]:
        """Onay: onaylanan alanlar ve karar kaydedilir, hiçbir yere gönderilmez (T-soft'a yazma yasak)."""
        row = self.product_row(prop["product_id"])
        p = loads(row["data_json"], {})
        change = propose.changed(p, fields)
        if not change:
            raise _err(409, "Önerilen alanların hepsi mevcut değerle aynı; onaylanacak değişiklik yok.")
        with self.engine().begin() as c:
            c.execute(PROPOSALS.update().where(PROPOSALS.c.id == prop["id"]).values(
                status="onaylandi", fields_json=dumps({**loads(prop["fields_json"], {}), **fields}), decided_by=user,
                decided_at=now(), note=note or None,
                result="Onaylandı: " + ", ".join(change) + ". Gönderim yok; CRM bağlantısı bekleniyor.",
                score_after=self.rescore(p, change)))
        self.audit(user, "approve", prop["product_id"], row["name"], {"proposal": prop["id"], "fields": list(change)})
        return self.proposal(prop["id"])

    def _store_one(self, p: dict[str, Any]) -> None:
        """Gönderilen ürünün yeni hâli tek başına yeniden puanlanır (yinelenen başlık kontrolü gece turunda)."""
        pid = str(p.get("ProductId") or "")
        if not pid:
            return
        a = rules.audit(p, rules.thresholds(self.conf), set())
        with self.engine().begin() as c:
            c.execute(PRODUCTS.update().where(PRODUCTS.c.tenant_id == self.tenant(), PRODUCTS.c.product_id == pid)
                      .values(score=a["score"], issues_json=dumps(a["issues"]), data_json=dumps(p), synced_at=now(),
                              rules="," + ",".join(i["rule"] for i in a["issues"]) + ","))


def _product_view(r: dict[str, Any], site: str) -> dict[str, Any]:
    p = loads(r["data_json"], {})
    link = p.get("SeoLink") or p.get("Url") or p.get("ProductUrl") or ""
    url = link if str(link).startswith("http") else (f"{site.rstrip('/')}/{str(link).lstrip('/')}" if link else None)
    return {"id": r["product_id"], "code": r["code"], "name": r["name"], "brand": r["brand"], "active": r["active"],
            "score": r["score"], "issues": [{**i, "field": propose.RULE_FIELD.get(i.get("rule"))}
                                            for i in loads(r["issues_json"], [])], "image": _image(p, site),
            "barcode": p.get("Barcode") or None, "url": url, "syncedAt": iso(r["synced_at"]),
            "sales": _num(p.get("CountTotalSales")), "views": _num(p.get("StatViews"))}


def _num(v: Any) -> int:
    try:
        return int(float(str(v or 0).replace(",", ".")))
    except ValueError:
        return 0


def _image(p: dict[str, Any], site: str) -> Optional[str]:
    """T-soft `ImageUrl` yalnız dosya adı taşır; tam adres `ImageUrls` listesindedir."""
    imgs = p.get("ImageUrls") or []
    if imgs and isinstance(imgs[0], dict):
        return imgs[0].get("Small") or imgs[0].get("Medium") or imgs[0].get("ImageUrl") or None
    raw = str(p.get("ImageUrlCdn") or p.get("ImageUrl") or "").strip()
    if not raw:
        return None
    return raw if raw.startswith("http") else f"{site.rstrip('/')}/{raw.lstrip('/')}"


def _proposal_view(r: dict[str, Any]) -> dict[str, Any]:
    return {"id": r["id"], "productId": r["product_id"], "status": r["status"],
            "fields": loads(r["fields_json"], {}), "before": loads(r["before_json"], {}),
            "scoreBefore": r["score_before"], "scoreAfter": r["score_after"], "model": r["model"],
            "createdBy": r["created_by"], "createdAt": iso(r["created_at"]), "decidedBy": r["decided_by"],
            "decidedAt": iso(r["decided_at"]), "note": r["note"], "sentAt": iso(r["sent_at"]), "result": r["result"]}


def register(app, runtime, authorize, session_user):
    seo = SeoGeo(runtime)

    def gate(request: Request) -> str:
        authorize(request)
        seo.engine()
        return session_user(request)

    def approver(request: Request) -> str:
        user = gate(request)
        if not seo.can_approve(user):
            raise _err(403, "Öneri onaylama yetkiniz yok (Yönetim → SEO & GEO → Onay verebilenler).")
        return user

    @app.get("/api/v1/seo-geo/overview")
    def seo_overview(request: Request) -> dict[str, Any]:
        gate(request)
        eng, tenant = seo.engine(), seo.tenant()
        with eng.connect() as c:
            total = c.execute(sa.select(sa.func.count()).select_from(PRODUCTS).where(PRODUCTS.c.tenant_id == tenant)).scalar() or 0
            active = sa.and_(PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.active.is_(True))
            avg = c.execute(sa.select(sa.func.avg(PRODUCTS.c.score)).where(active)).scalar()
            failing = c.execute(sa.select(sa.func.count()).select_from(PRODUCTS).where(active, PRODUCTS.c.score < 70)).scalar() or 0
            by_rule = {k: c.execute(sa.select(sa.func.count()).select_from(PRODUCTS).where(
                active, PRODUCTS.c.rules.like(f"%,{k},%"))).scalar() or 0 for k in rules.RULES}
            status = dict(c.execute(sa.select(PROPOSALS.c.status, sa.func.count()).where(
                PROPOSALS.c.tenant_id == tenant).group_by(PROPOSALS.c.status)).all())
            week = now() - timedelta(days=7)
            approved_week = c.execute(sa.select(sa.func.count()).select_from(PROPOSALS).where(
                PROPOSALS.c.tenant_id == tenant, PROPOSALS.c.status == "onaylandi", PROPOSALS.c.decided_at >= week)).scalar() or 0
            top = c.execute(sa.select(PRODUCTS.c.product_id, PRODUCTS.c.name, PRODUCTS.c.score, SALES, VIEWS).where(
                active, PRODUCTS.c.score < 70).order_by(SALES.desc(), VIEWS.desc()).limit(10)).all()
            last = c.execute(sa.select(RUNS).where(RUNS.c.tenant_id == tenant, RUNS.c.kind == "tsoft")
                             .order_by(RUNS.c.started_at.desc()).limit(1)).mappings().first()
        daily = seo.gsc("daily")
        return {
            "products": total, "activeAverage": round(float(avg), 1) if avg is not None else None,
            "failing": failing, "failingThreshold": 70,
            "rules": [{"rule": k, "title": v[2], "severity": v[1], "count": by_rule[k]} for k, v in rules.RULES.items()],
            "proposals": status, "approvedThisWeek": approved_week, "tsoftWrite": False,
            "priority": [{"id": r[0], "name": r[1], "score": r[2], "sales": int(r[3]), "views": int(r[4])} for r in top],
            "lastSync": ({"startedAt": iso(last["started_at"]), "finishedAt": iso(last["finished_at"]),
                          "count": last["count"], "error": last["error"]} if last else None),
            "sync": seo.state, "batch": seo.batch, "search": daily,
            "connections": {"tsoft": connections.tsoft.configured(),
                            "google": bool(connections.service_account_email()),
                            "serviceAccount": connections.service_account_email(),
                            "gscSite": seo.conf("GSC_SITE") or None,
                            "ga4": bool(seo.conf("GA4_PROPERTY_ID")), "merchant": bool(seo.conf("MERCHANT_ACCOUNT_ID"))},
        }

    @app.get("/api/v1/seo-geo/me")
    def seo_me(request: Request) -> dict[str, Any]:
        user = gate(request)
        return {"user": user, "canApprove": seo.can_approve(user)}

    @app.post("/api/v1/seo-geo/sync")
    def seo_sync(request: Request) -> dict[str, Any]:
        user = gate(request)
        started = seo.start_sync(user)
        seo.audit(user, "run", "tsoft", "T-soft eşitlemesi", {"started": started})
        return {"started": started, "sync": seo.state}

    @app.get("/api/v1/seo-geo/products")
    def seo_products(request: Request, rule: str = "", status: str = "", q: str = "", start: int = 0,
                     limit: int = 50, order: str = "oncelik") -> dict[str, Any]:
        gate(request)
        tenant, site = seo.tenant(), seo.conf("SEO_SITE_URL")
        cond = [PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.active.is_(True)]
        if rule:
            if rule not in rules.RULES:
                raise _err(422, "Bilinmeyen kural.")
            cond.append(PRODUCTS.c.rules.like(f"%,{rule},%"))
        if q.strip():
            like = f"%{q.strip()}%"
            cond.append(sa.or_(PRODUCTS.c.name.ilike(like), PRODUCTS.c.code.ilike(like), PRODUCTS.c.brand.ilike(like)))
        pending = sa.select(PROPOSALS.c.product_id, PROPOSALS.c.status).where(PROPOSALS.c.tenant_id == tenant)
        if status:
            cond.append(PRODUCTS.c.product_id.in_(sa.select(PROPOSALS.c.product_id).where(
                PROPOSALS.c.tenant_id == tenant, PROPOSALS.c.status == status)))
        with seo.engine().connect() as c:
            total = c.execute(sa.select(sa.func.count()).select_from(PRODUCTS).where(*cond)).scalar() or 0
            sort = {"name": [PRODUCTS.c.name.asc()], "score": [PRODUCTS.c.score.asc()]}.get(
                order, [SALES.desc(), VIEWS.desc(), PRODUCTS.c.score.asc()])
            rows = c.execute(sa.select(PRODUCTS).where(*cond).order_by(*sort, PRODUCTS.c.product_id)
                             .offset(max(0, start)).limit(max(1, limit))).mappings().all()
            ids = [r["product_id"] for r in rows]
            states: dict[str, str] = {}
            if ids:
                for pid, st in c.execute(pending.where(PROPOSALS.c.product_id.in_(ids))
                                         .order_by(PROPOSALS.c.created_at)).all():
                    states[pid] = st
        items = [{**_product_view(dict(r), site), "proposal": states.get(r["product_id"])} for r in rows]
        return {"total": total, "start": start, "items": items}

    @app.get("/api/v1/seo-geo/products/{pid}")
    def seo_product(pid: str, request: Request) -> dict[str, Any]:
        gate(request)
        row = seo.product_row(pid)
        p = loads(row["data_json"], {})
        with seo.engine().connect() as c:
            props = c.execute(sa.select(PROPOSALS).where(PROPOSALS.c.tenant_id == seo.tenant(),
                                                         PROPOSALS.c.product_id == pid)
                              .order_by(PROPOSALS.c.created_at.desc())).mappings().all()
        return {**_product_view(row, seo.conf("SEO_SITE_URL")),
                "current": {k: str(p.get(k) or "") for k in propose.FIELDS},
                "details": {"words": rules.words(p.get("Details")), "shortDescription": rules.text_of(p.get("ShortDescription"))},
                "limits": rules.thresholds(seo.conf),
                "proposals": [{**_proposal_view(dict(r)),
                               "unsupported": propose.unsupported(p, loads(r["fields_json"], {}))} for r in props]}

    @app.post("/api/v1/seo-geo/products/{pid}/propose")
    def seo_propose(pid: str, request: Request) -> dict[str, Any]:
        user = gate(request)
        return _proposal_view(seo.make_proposal(pid, user))

    @app.post("/api/v1/seo-geo/proposals/{proposal_id}/decide")
    def seo_decide(proposal_id: str, body: Decision, request: Request) -> dict[str, Any]:
        user = approver(request)
        prop = seo.proposal(proposal_id)
        if prop["status"] != "hazir":
            raise _err(409, "Bu öneri için karar zaten verilmiş.")
        if body.action == "reject":
            with seo.engine().begin() as c:
                c.execute(PROPOSALS.update().where(PROPOSALS.c.id == proposal_id).values(
                    status="reddedildi", decided_by=user, decided_at=now(), note=body.note or None))
            seo.audit(user, "reject", prop["product_id"], prop["product_id"], {"proposal": proposal_id, "note": body.note})
            return _proposal_view(seo.proposal(proposal_id))
        fields = {k: v for k, v in (body.fields or loads(prop["fields_json"], {})).items() if k in propose.FIELDS}
        return _proposal_view(seo.approve(prop, fields, user, body.note))

    @app.post("/api/v1/seo-geo/proposals/bulk-approve")
    def seo_bulk(body: BulkApprove, request: Request) -> dict[str, Any]:
        user = approver(request)
        out = []
        for pid in dict.fromkeys(body.ids):
            prop = seo.proposal(pid)
            if prop["status"] != "hazir":
                out.append({"id": pid, "status": prop["status"], "skipped": True})
                continue
            try:
                done = seo.approve(prop, loads(prop["fields_json"], {}), user, body.note)
                out.append({"id": pid, "status": done["status"], "result": done["result"]})
            except HTTPException as e:
                out.append({"id": pid, "status": prop["status"], "skipped": True, "result": str(e.detail)})
        return {"items": out}


    @app.post("/api/v1/seo-geo/proposals/batch")
    def seo_batch(request: Request, budget: int = 3600) -> dict[str, Any]:
        user = gate(request)
        started = seo.start_batch(user, budget)
        seo.audit(user, "run", "batch", "SEO öneri ön üretimi", {"started": started, "budget": budget})
        return {"started": started, "batch": seo.batch}

    @app.get("/api/v1/seo-geo/llms")
    def seo_llms(request: Request, top: int = 100) -> dict[str, Any]:
        """llms.txt önerisi (eşitlenmiş veriden) ve sitedeki mevcut dosya. Hiçbir yere yazılmaz."""
        gate(request)
        site = seo.conf("SEO_SITE_URL") or "https://timas.com.tr"
        with seo.engine().connect() as c:
            data = [loads(r[0], {}) for r in c.execute(sa.select(PRODUCTS.c.data_json).where(
                PRODUCTS.c.tenant_id == seo.tenant()))]
        out = llms.build(data, site, max(1, top))
        current: dict[str, Any] = {}
        for name in ("llms.txt", "llms-full.txt"):
            try:
                import httpx
                r = httpx.get(f"{site.rstrip('/')}/{name}", timeout=20, follow_redirects=True,
                              headers={"User-Agent": "TimasZekiBot/1.0 (+ai@timas.com.tr)"})
                current[name] = {"status": r.status_code,
                                 "text": r.text[:20000] if r.status_code == 200 and "text/plain" in r.headers.get("content-type", "") else None}
            except Exception as e:  # noqa: BLE001 — site erişilemezse öneri yine gösterilir
                current[name] = {"status": None, "error": str(e)[:200]}
        return {**out, "site": site, "current": current}

    def _redirect_view(r: Any) -> dict[str, Any]:
        site = (seo.conf("SEO_SITE_URL") or "https://timas.com.tr").rstrip("/")
        return {"id": r["id"], "link": r["link"], "url": f"{site}/{r['link']}", "current": r["current_target"],
                "target": r["target"], "targetType": r["target_type"], "confidence": r["confidence"],
                "reason": r["reason"], "alternatives": loads(r["alternatives_json"], []), "status": r["status"],
                "chosen": r["chosen"], "decidedBy": r["decided_by"], "decidedAt": iso(r["decided_at"]), "note": r["note"]}

    @app.get("/api/v1/seo-geo/redirects")
    def seo_redirects(request: Request, confidence: str = "", status: str = "", q: str = "", start: int = 0,
                      limit: int = 50) -> dict[str, Any]:
        gate(request)
        tenant = seo.tenant()
        cond = [REDIRECTS.c.tenant_id == tenant]
        if confidence:
            cond.append(REDIRECTS.c.confidence == confidence)
        if status:
            cond.append(REDIRECTS.c.status == status)
        if q.strip():
            cond.append(sa.or_(REDIRECTS.c.link.ilike(f"%{q.strip()}%"), REDIRECTS.c.target.ilike(f"%{q.strip()}%")))
        order = sa.case({"kesin": 0, "yüksek": 1, "orta": 2}, value=REDIRECTS.c.confidence, else_=3)
        with seo.engine().connect() as c:
            total = c.execute(sa.select(sa.func.count()).select_from(REDIRECTS).where(*cond)).scalar() or 0
            rows = c.execute(sa.select(REDIRECTS).where(*cond).order_by(order, REDIRECTS.c.link)
                             .offset(max(0, start)).limit(max(1, limit))).mappings().all()
            counts = {f"{a}|{b}": n for a, b, n in c.execute(sa.select(REDIRECTS.c.confidence, REDIRECTS.c.status,
                                                                        sa.func.count()).where(REDIRECTS.c.tenant_id == tenant)
                                                              .group_by(REDIRECTS.c.confidence, REDIRECTS.c.status)).all()}
        return {"total": total, "items": [_redirect_view(r) for r in rows], "counts": counts}

    class RedirectDecision(BaseModel):
        action: str = Field(pattern="^(approve|reject)$")
        target: str = Field(default="", max_length=600)
        note: str = Field(default="", max_length=1000)

    @app.post("/api/v1/seo-geo/redirects/{rid}/decide")
    def seo_redirect_decide(rid: str, body: RedirectDecision, request: Request) -> dict[str, Any]:
        """Karar yalnız kaydedilir; T-soft'a yazılmaz. Onaylananlar CSV ile panelden girilir."""
        user = approver(request)
        target = (body.target or "").strip().strip("/")
        with seo.engine().begin() as c:
            r = c.execute(sa.select(REDIRECTS).where(REDIRECTS.c.tenant_id == seo.tenant(), REDIRECTS.c.id == rid)).mappings().first()
            if not r:
                raise _err(404, "Yönlendirme bulunamadı.")
            chosen = target or r["target"]
            if body.action == "approve" and not chosen:
                raise _err(422, "Hedef adres seçilmeden onaylanamaz.")
            c.execute(REDIRECTS.update().where(REDIRECTS.c.id == rid).values(
                status="onaylandi" if body.action == "approve" else "reddedildi",
                chosen=chosen if body.action == "approve" else None, decided_by=user, decided_at=now(),
                note=body.note or None))
            r = c.execute(sa.select(REDIRECTS).where(REDIRECTS.c.id == rid)).mappings().first()
        seo.audit(user, body.action, rid, r["link"], {"kind": "redirect", "target": r["chosen"]})
        return _redirect_view(r)

    @app.post("/api/v1/seo-geo/redirects/approve-confidence")
    def seo_redirect_bulk(request: Request, confidence: str = "kesin") -> dict[str, Any]:
        """Bir güven düzeyindeki bekleyen önerilerin hepsini onaylar (yalnız "kesin" ve "yüksek")."""
        user = approver(request)
        if confidence not in ("kesin", "yüksek"):
            raise _err(422, "Toplu onay yalnız kesin ve yüksek güvende yapılır.")
        with seo.engine().begin() as c:
            n = c.execute(REDIRECTS.update().where(
                REDIRECTS.c.tenant_id == seo.tenant(), REDIRECTS.c.status == "bekliyor",
                REDIRECTS.c.confidence == confidence, REDIRECTS.c.target.is_not(None)).values(
                status="onaylandi", chosen=REDIRECTS.c.target, decided_by=user, decided_at=now())).rowcount
        seo.audit(user, "approve", confidence, "Toplu yönlendirme onayı", {"kind": "redirect", "count": n})
        return {"approved": n}

    @app.get("/api/v1/seo-geo/redirects/export.csv")
    def seo_redirect_export(request: Request):
        """Onaylanan yönlendirmeler: T-soft paneline elle girilmek için (Link;RedirectLink)."""
        gate(request)
        import csv
        import io
        from fastapi.responses import Response

        with seo.engine().connect() as c:
            rows = c.execute(sa.select(REDIRECTS.c.link, REDIRECTS.c.chosen, REDIRECTS.c.decided_by, REDIRECTS.c.decided_at)
                             .where(REDIRECTS.c.tenant_id == seo.tenant(), REDIRECTS.c.status == "onaylandi")
                             .order_by(REDIRECTS.c.link)).all()
        buf = io.StringIO()
        w = csv.writer(buf, delimiter=";")
        w.writerow(["Link", "RedirectLink", "Onaylayan", "Tarih"])
        for link, chosen, by, at in rows:
            w.writerow([link, chosen, by, iso(at)])
        return Response("\ufeff" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="yonlendirme-onerileri.csv"'})

    # ------------------------------------------------------------ yazar / kategori / yayınevi sayfaları
    def _page_data() -> tuple[list[dict[str, Any]], dict[tuple[str, str], dict[str, Any]]]:
        tenant = seo.tenant()
        with seo.engine().connect() as c:
            links = [dict(r) for r in c.execute(sa.select(LINKS.c.link, LINKS.c.type, LINKS.c.table_id, LINKS.c.title,
                                                          LINKS.c.description).where(
                LINKS.c.tenant_id == tenant, LINKS.c.type.in_(list(pages.KINDS)))).mappings()]
            prods = [loads(r[0], {}) for r in c.execute(sa.select(PRODUCTS.c.data_json).where(PRODUCTS.c.tenant_id == tenant))]
        return links, pages.stats(prods)

    def _page_name(l: dict[str, Any]) -> str:
        return rules.text_of(l.get("title")).split("|")[0].strip() or l["link"].replace("-", " ").title()

    def _wiki(name: str) -> Optional[dict[str, Any]]:
        try:
            with seo.engine().connect() as c:
                row = c.execute(sa.text("select facts_json from semantic_web_authors where wikidata_id is not null "
                                        "and lower(name) = lower(:n) limit 1"), {"n": name}).first()
            return loads(row[0], None) if row else None
        except Exception:  # noqa: BLE001 — basın-web modülü kapalı ortamda tablo yoktur
            return None

    @app.get("/api/v1/seo-geo/pages")
    def seo_pages(request: Request, type: str = "model", q: str = "", start: int = 0, limit: int = 50) -> dict[str, Any]:
        gate(request)
        if type not in pages.KINDS:
            raise _err(422, "Bilinmeyen sayfa türü.")
        links, st = _page_data()
        lim = rules.thresholds(seo.conf)
        site = (seo.conf("SEO_SITE_URL") or "https://timas.com.tr").rstrip("/")
        with seo.engine().connect() as c:
            states = dict(c.execute(sa.select(PROPOSALS.c.product_id, PROPOSALS.c.status).where(
                PROPOSALS.c.tenant_id == seo.tenant(), PROPOSALS.c.product_id.like(f"{type}:%"))
                .order_by(PROPOSALS.c.created_at)).all())
        items = []
        for l in links:
            if l["type"] != type:
                continue
            s = st.get((type, str(l["table_id"])), {})
            name = _page_name(l)
            if q.strip() and q.strip().casefold() not in (name + " " + l["link"]).casefold():
                continue
            a = pages.audit(type, name, l["title"], l["description"], lim)
            items.append({"id": str(l["table_id"]), "name": name, "link": l["link"], "url": f"{site}/{l['link']}",
                          "books": s.get("books", 0), "sales": s.get("sales", 0), "score": a["score"],
                          "issues": len(a["issues"]), "proposal": states.get(f"{type}:{l['table_id']}")})
        items.sort(key=lambda x: (-x["sales"], -x["books"], x["name"]))
        return {"total": len(items), "items": items[max(0, start):max(0, start) + max(1, limit)],
                "withBooks": sum(1 for x in items if x["books"])}

    def _page(type: str, tid: str) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any]]:
        if type not in pages.KINDS:
            raise _err(422, "Bilinmeyen sayfa türü.")
        links, st = _page_data()
        l = next((x for x in links if x["type"] == type and str(x["table_id"]) == tid), None)
        if not l:
            raise _err(404, "Sayfa bulunamadı; önce T-soft eşitlemesi yapılmalı.")
        name = _page_name(l)
        f = pages.facts(type, name, st.get((type, tid), {}), _wiki(name) if type == "model" else None)
        return l, {"name": name}, f

    @app.get("/api/v1/seo-geo/pages/{type}/{tid}")
    def seo_page(type: str, tid: str, request: Request) -> dict[str, Any]:
        gate(request)
        l, meta, f = _page(type, tid)
        lim = rules.thresholds(seo.conf)
        a = pages.audit(type, meta["name"], l["title"], l["description"], lim)
        src = pages.source_record(type, meta["name"], l["title"], l["description"], f)
        with seo.engine().connect() as c:
            props = c.execute(sa.select(PROPOSALS).where(PROPOSALS.c.tenant_id == seo.tenant(),
                                                         PROPOSALS.c.product_id == f"{type}:{tid}")
                              .order_by(PROPOSALS.c.created_at.desc())).mappings().all()
        site = (seo.conf("SEO_SITE_URL") or "https://timas.com.tr").rstrip("/")
        out_props = []
        for r in props:
            fl = loads(r["fields_json"], {})
            out_props.append({**_proposal_view(dict(r)), "unsupported": propose.unsupported(
                src, {"SeoTitle": fl.get("SeoTitle", ""), "SeoDescription": fl.get("SeoDescription", ""), "Details": fl.get("Intro", "")})})
        return {"type": type, "id": tid, "name": meta["name"], "link": l["link"], "url": f"{site}/{l['link']}",
                "current": {"SeoTitle": rules.text_of(l["title"]), "SeoDescription": rules.text_of(l["description"]), "Intro": ""},
                "facts": f, "score": a["score"], "issues": a["issues"], "limits": lim, "proposals": out_props}

    @app.post("/api/v1/seo-geo/pages/{type}/{tid}/propose")
    def seo_page_propose(type: str, tid: str, request: Request) -> dict[str, Any]:
        return make_page_proposal(type, tid, gate(request))

    def make_page_proposal(type: str, tid: str, user: str, priority: Optional[int] = None) -> dict[str, Any]:
        l, meta, f = _page(type, tid)
        key = f"{type}:{tid}"
        with seo._gen_lock:
            if key in seo._generating:
                raise _err(409, "Bu sayfa için öneri şu an yazılıyor.")
            seo._generating.add(key)
        try:
            llm = runtime().llm_for("seo", priority)
            if llm is None:
                raise _err(503, "Yapay zekâ modeli bu kurulumda tanımlı değil.")
            lim = rules.thresholds(seo.conf)
            try:
                fields = pages.suggest(llm, type, meta["name"], l["title"], l["description"], f, lim)
            except ValueError as e:
                raise _err(502, f"Öneri üretilemedi: {e}") from None
            before = pages.audit(type, meta["name"], l["title"], l["description"], lim)
            after = pages.audit(type, meta["name"], fields["SeoTitle"], fields["SeoDescription"], lim)
            after_score = min(100, after["score"] + (15 if fields.get("Intro") and type in ("model", "category") else 0))
            pid = uuid.uuid4().hex
            with seo.engine().begin() as c:
                c.execute(PROPOSALS.delete().where(PROPOSALS.c.tenant_id == seo.tenant(), PROPOSALS.c.product_id == key,
                                                   PROPOSALS.c.status == "hazir"))
                c.execute(PROPOSALS.insert().values(
                    id=pid, tenant_id=seo.tenant(), product_id=key, status="hazir", fields_json=dumps(fields),
                    before_json=dumps({"SeoTitle": rules.text_of(l["title"]), "SeoDescription": rules.text_of(l["description"]), "Intro": ""}),
                    score_before=before["score"], score_after=after_score, model=getattr(llm, "model", None),
                    created_by=user, created_at=now()))
            seo.audit(user, "create", key, meta["name"], {"proposal": pid})
            return _proposal_view(seo.proposal(pid))
        finally:
            with seo._gen_lock:
                seo._generating.discard(key)

    def page_queue() -> list[tuple[str, str]]:
        """Ön üretim sırası: önerisi olmayan, kitabı olan ve sorunlu yazar/kategori/yayınevi sayfaları, çok satandan."""
        links, st = _page_data()
        lim = rules.thresholds(seo.conf)
        with seo.engine().connect() as c:
            has = {r[0] for r in c.execute(sa.select(PROPOSALS.c.product_id).where(
                PROPOSALS.c.tenant_id == seo.tenant(), PROPOSALS.c.product_id.like("%:%")))}
        out = []
        for l in links:
            key = (l["type"], str(l["table_id"]))
            s = st.get(key, {})
            if not s.get("books") or f"{key[0]}:{key[1]}" in has:
                continue
            if pages.audit(l["type"], _page_name(l), l["title"], l["description"], lim)["issues"]:
                out.append((s.get("sales", 0), key))
        return [k for _, k in sorted(out, key=lambda x: -x[0])]

    seo.page_queue, seo.make_page_proposal = page_queue, make_page_proposal

    class PageDecision(BaseModel):
        action: str = Field(pattern="^(approve|reject)$")
        fields: dict[str, str] = Field(default_factory=dict)
        note: str = Field(default="", max_length=1000)

    @app.post("/api/v1/seo-geo/pages/proposals/{proposal_id}/decide")
    def seo_page_decide(proposal_id: str, body: PageDecision, request: Request) -> dict[str, Any]:
        """Karar yalnız kaydedilir; T-soft'a yazılmaz (hedef CRM/T-soft paneli)."""
        user = approver(request)
        prop = seo.proposal(proposal_id)
        if prop["status"] != "hazir" or ":" not in prop["product_id"]:
            raise _err(409, "Bu öneri için karar verilemez.")
        fields = {k: v for k, v in (body.fields or loads(prop["fields_json"], {})).items() if k in pages.FIELDS}
        approve = body.action == "approve"
        with seo.engine().begin() as c:
            c.execute(PROPOSALS.update().where(PROPOSALS.c.id == proposal_id).values(
                status="onaylandi" if approve else "reddedildi",
                fields_json=dumps({**loads(prop["fields_json"], {}), **fields}) if approve else prop["fields_json"],
                decided_by=user, decided_at=now(), note=body.note or None,
                result=("Onaylandı; gönderim yok (T-soft paneli/CRM)." if approve else None)))
        seo.audit(user, body.action, prop["product_id"], prop["product_id"], {"proposal": proposal_id, "kind": "page"})
        return _proposal_view(seo.proposal(proposal_id))

    # ------------------------------------------------------------ şema denetimi
    def _schema_summary() -> dict[str, Any]:
        tenant = seo.tenant()
        with seo.engine().connect() as c:
            rows = c.execute(sa.select(SCHEMA.c.issues).where(SCHEMA.c.tenant_id == tenant, SCHEMA.c.product_id != "_org")).all()
            org = c.execute(sa.select(SCHEMA.c.types_json, SCHEMA.c.checked_at).where(
                SCHEMA.c.tenant_id == tenant, SCHEMA.c.product_id == "_org")).first()
            books = c.execute(sa.select(sa.func.count()).select_from(PRODUCTS).where(PRODUCTS.c.tenant_id == tenant,
                                                                                    PRODUCTS.c.active.is_(True))).scalar() or 0
            last = c.execute(sa.select(sa.func.max(SCHEMA.c.checked_at)).where(SCHEMA.c.tenant_id == tenant)).scalar()
        counts: dict[str, int] = {k: 0 for k in schema.CHECKS}
        for (issues,) in rows:
            for k in filter(None, (issues or "").split(",")):
                counts[k] = counts.get(k, 0) + 1
        return {"checked": len(rows), "activeProducts": books, "counts": counts, "lastChecked": iso(last),
                "organization": loads(org[0], None) if org else None, "crawl": seo.crawl,
                "checks": [{"id": k, "severity": v[0], "title": v[1], "why": v[2], "count": counts.get(k, 0)}
                           for k, v in schema.CHECKS.items()]}

    @app.get("/api/v1/seo-geo/schema")
    def seo_schema(request: Request, issue: str = "", start: int = 0, limit: int = 50) -> dict[str, Any]:
        gate(request)
        out = _schema_summary()
        cond = [SCHEMA.c.tenant_id == seo.tenant(), SCHEMA.c.product_id != "_org", SCHEMA.c.issues != ",,"]
        if issue:
            if issue not in schema.CHECKS:
                raise _err(422, "Bilinmeyen denetim.")
            cond.append(SCHEMA.c.issues.like(f"%,{issue},%"))
        with seo.engine().connect() as c:
            total = c.execute(sa.select(sa.func.count()).select_from(SCHEMA).where(*cond)).scalar() or 0
            rows = c.execute(sa.select(SCHEMA.c.product_id, SCHEMA.c.url, SCHEMA.c.status, SCHEMA.c.issues, SCHEMA.c.checked_at,
                                       PRODUCTS.c.name, SALES).select_from(SCHEMA.join(PRODUCTS, sa.and_(
                PRODUCTS.c.tenant_id == SCHEMA.c.tenant_id, PRODUCTS.c.product_id == SCHEMA.c.product_id)))
                .where(*cond).order_by(SALES.desc()).offset(max(0, start)).limit(max(1, limit))).all()
        out["total"] = total
        out["items"] = [{"id": r[0], "url": r[1], "status": r[2], "issues": [i for i in (r[3] or "").split(",") if i],
                         "checkedAt": iso(r[4]), "name": r[5], "sales": int(r[6] or 0)} for r in rows]
        return out

    @app.post("/api/v1/seo-geo/schema/crawl")
    def seo_schema_crawl(request: Request, budget: int = 3600) -> dict[str, Any]:
        user = gate(request)
        started = seo.start_crawl(budget)
        seo.audit(user, "run", "schema", "Şema taraması", {"started": started, "budget": budget})
        return {"started": started, "crawl": seo.crawl}

    @app.get("/api/v1/seo-geo/schema/theme-request.md")
    def seo_theme_request(request: Request):
        """T-soft / ajans için tema isteği belgesi (son taramanın sayılarıyla, gerçek bir kitaptan örnek)."""
        gate(request)
        from fastapi.responses import Response

        s = _schema_summary()
        example = None
        with seo.engine().connect() as c:
            row = c.execute(sa.select(PRODUCTS.c.data_json).where(PRODUCTS.c.tenant_id == seo.tenant(), PRODUCTS.c.active.is_(True))
                            .order_by(SALES.desc()).limit(1)).first()
        if row:
            p = loads(row[0], {})
            site = (seo.conf("SEO_SITE_URL") or "https://timas.com.tr").rstrip("/")
            wiki = _wiki(rules.text_of(p.get("Model"))) or {}
            imgs = p.get("ImageUrls") or []
            example = {"name": rules.text_of(p.get("ProductName")), "isbn": p.get("Barcode"), "author": rules.text_of(p.get("Model")),
                       "brand": rules.text_of(p.get("Brand")), "price": p.get("SellingPrice"), "url": f"{site}/{p.get('SeoLink')}",
                       "image": (imgs[0].get("ImageUrl") if imgs and isinstance(imgs[0], dict) else None),
                       "wikidata": wiki.get("wikidata")}
        text = schema.theme_request(s["counts"], s["checked"], s["organization"], example)
        return Response(text, media_type="text/markdown; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="tema-istegi-schema.md"'})

    @app.get("/api/v1/seo-geo/history")
    def seo_history(request: Request, start: int = 0, limit: int = 50) -> dict[str, Any]:
        gate(request)
        tenant = seo.tenant()
        cond = [PROPOSALS.c.tenant_id == tenant, PROPOSALS.c.status != "hazir"]
        with seo.engine().connect() as c:
            total = c.execute(sa.select(sa.func.count()).select_from(PROPOSALS).where(*cond)).scalar() or 0
            rows = c.execute(sa.select(PROPOSALS, PRODUCTS.c.name).select_from(PROPOSALS.outerjoin(
                PRODUCTS, sa.and_(PRODUCTS.c.tenant_id == PROPOSALS.c.tenant_id, PRODUCTS.c.product_id == PROPOSALS.c.product_id)))
                .where(*cond).order_by(PROPOSALS.c.decided_at.desc().nullslast()).offset(max(0, start)).limit(max(1, limit))
            ).mappings().all()
        return {"total": total, "items": [{**_proposal_view(dict(r)), "productName": r["name"]} for r in rows]}

    @app.get("/api/v1/seo-geo/search/{kind}")
    def seo_search(kind: str, request: Request) -> dict[str, Any]:
        gate(request)
        if kind not in ("daily", "queries", "pages"):
            raise _err(404, "Bilinmeyen rapor.")
        return seo.gsc(kind) or {"rows": [], "start": None, "end": None, "savedAt": None}

    @app.post("/api/v1/seo-geo/search/refresh")
    def seo_search_refresh(request: Request) -> dict[str, Any]:
        user = gate(request)
        try:
            counts = seo.refresh_gsc()
        except connections.ConnectionError_ as e:
            raise _err(502, str(e)) from None
        seo.audit(user, "run", "gsc", "Search Console okuması", counts)
        return {"counts": counts}

    @app.get("/api/v1/seo-geo/questions")
    def seo_questions(request: Request) -> dict[str, Any]:
        gate(request)
        with seo.engine().connect() as c:
            rows = c.execute(sa.select(QUESTIONS).where(QUESTIONS.c.tenant_id == seo.tenant())
                             .order_by(QUESTIONS.c.created_at)).mappings().all()
        return {"items": [{"id": r["id"], "text": r["text"], "category": r["category"], "createdBy": r["created_by"],
                           "createdAt": iso(r["created_at"])} for r in rows],
                "measuring": False}

    @app.post("/api/v1/seo-geo/questions")
    def seo_question_add(body: Question, request: Request) -> dict[str, Any]:
        user = gate(request)
        qid = uuid.uuid4().hex
        with seo.engine().begin() as c:
            c.execute(QUESTIONS.insert().values(id=qid, tenant_id=seo.tenant(), text=body.text.strip(),
                                                category=body.category.strip() or None, created_by=user, created_at=now()))
        seo.audit(user, "create", qid, body.text[:120], {"kind": "geo_question"})
        return {"id": qid}

    @app.delete("/api/v1/seo-geo/questions/{qid}")
    def seo_question_del(qid: str, request: Request) -> dict[str, Any]:
        user = gate(request)
        with seo.engine().begin() as c:
            n = c.execute(QUESTIONS.delete().where(QUESTIONS.c.tenant_id == seo.tenant(), QUESTIONS.c.id == qid)).rowcount
        if n:
            seo.audit(user, "delete", qid, "GEO sorusu", {"kind": "geo_question"})
        return {"deleted": bool(n)}

    @app.post("/api/v1/seo-geo/run-due")
    def seo_run_due(request: Request, budget: int = 18000) -> dict[str, Any]:
        """Gece zamanlayıcısı: T-soft eşitlemesi (arka planda) ve Search Console okuması. Bağlı olmayan atlanır."""
        authorize(request)
        seo.engine()
        out: dict[str, Any] = {}
        out["tsoft"] = seo.start_sync("zamanlayıcı") if connections.tsoft.configured() else "tanımlı değil"
        if connections.service_account_email():
            try:
                out["gsc"] = seo.refresh_gsc()
            except connections.ConnectionError_ as e:
                out["gsc"] = f"hata: {e}"
        else:
            out["gsc"] = "tanımlı değil"
        # Öneriler eşitlemeden sonra: süren eşitleme bitene kadar bekler, sonra en düşük puandan başlar.
        def later() -> None:
            import time as _t
            while seo.state.get("running"):
                _t.sleep(10)
            seo.start_batch("zamanlayıcı", budget)
            seo.start_crawl(min(budget, 7200))
        threading.Thread(target=later, name="seo-batch-wait", daemon=True).start()
        out["batch"] = f"başlayacak (bütçe {budget} sn)"
        return out

    return seo
