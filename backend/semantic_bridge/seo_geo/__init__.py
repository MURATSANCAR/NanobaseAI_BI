"""SEO & GEO modülü: T-soft ürünlerinin denetimi, model önerisi, insan onayıyla T-soft'a gönderim; Search Console.

Akış (docs/analiz/seo-geo-modul-2026-09-25.md):
1. Eşitleme: T-soft'taki bütün ürünler sayfa sayfa okunur, kurallardan geçer, puan ve sorunlarıyla saklanır.
2. Öneri: kullanıcı bir ürün için öneri ister; model ürünün kendi kaydından SEO alanlarını yazar.
3. Karar: onay verebilen kişi öneriyi (gerekirse düzenleyip) onaylar ya da reddeder. Onay T-soft'a yalnız
   değişen alanları gönderir, sonra ürünü yeniden okuyup yazıldığını doğrular. Onaysız hiçbir şey gitmez.
4. Geri alma: gönderimden önceki değerler saklıdır; aynı yoldan geri yazılır.
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

from . import connections, propose, rules
from .store import GSC, PRODUCTS, PROPOSALS, QUESTIONS, RUNS, dumps, ensure, iso, loads, now

log = logging.getLogger("semantic.seo_geo")


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
        except Exception as e:  # noqa: BLE001 — hata ekrana taşınır, eski veri korunur
            error = str(e)[:1000]
            log.exception("seo sync failed")
        finally:
            with eng.begin() as c:
                c.execute(RUNS.update().where(RUNS.c.id == run_id).values(
                    finished_at=now(), count=len(products), error=error))
            self.state.update(running=False, error=error)
            self._sync_lock.release()

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
        """Önerisi olmayan, düzeltilebilir sorunlu aktif ürünler için öneri yazar; en düşük puandan başlar.
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
                    PRODUCTS.c.product_id.not_in(has)).order_by(PRODUCTS.c.score.asc(), PRODUCTS.c.product_id)).all()
            queue = [pid for pid, issues in rows if propose.fixable(loads(issues, []))]
            self.batch["queue"] = len(queue)
            for pid in queue:
                if _t.monotonic() > deadline:
                    break
                try:
                    self.make_proposal(pid, user, BATCH)
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

    def send(self, prop: dict[str, Any], fields: dict[str, str], user: str, note: str) -> dict[str, Any]:
        """Onaylanan alanları T-soft'a yazar ve ürünü yeniden okuyarak doğrular."""
        row = self.product_row(prop["product_id"])
        p = loads(row["data_json"], {})
        change = propose.changed(p, fields)
        status, result = "gonderildi", ""
        if not change:
            status, result = "reddedildi", "Önerilen alanların hepsi T-soft'taki değerle aynı; gönderilecek değişiklik yok."
        else:
            try:
                connections.tsoft.update_product(prop["product_id"], change)
                connections.tsoft.clear_product_cache()
                fresh = connections.tsoft.product(prop["product_id"]) or {}
                missed = [k for k, v in change.items() if str(fresh.get(k) or "").strip() != v.strip()]
                if missed:
                    status, result = "hata", "T-soft kabul etti ama yeniden okunduğunda şu alanlar farklı: " + ", ".join(missed)
                else:
                    result = "Yazıldı ve yeniden okunarak doğrulandı: " + ", ".join(change)
                    self._store_one(fresh or {**p, **change})
            except connections.ConnectionError_ as e:
                status, result = "hata", str(e)[:1000]
        with self.engine().begin() as c:
            c.execute(PROPOSALS.update().where(PROPOSALS.c.id == prop["id"]).values(
                status=status, fields_json=dumps({**loads(prop["fields_json"], {}), **fields}), decided_by=user,
                decided_at=now(), note=note or None, sent_at=now() if status == "gonderildi" else None, result=result))
        self.audit(user, "approve" if status == "gonderildi" else "send_fail", prop["product_id"], row["name"],
                   {"proposal": prop["id"], "fields": list(change), "status": status, "result": result})
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
            "barcode": p.get("Barcode") or None, "url": url, "syncedAt": iso(r["synced_at"])}


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
            raise _err(403, "T-soft'a gönderimi onaylama yetkiniz yok (Yönetim → SEO & GEO → Onay verebilenler).")
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
            sent_week = c.execute(sa.select(sa.func.count()).select_from(PROPOSALS).where(
                PROPOSALS.c.tenant_id == tenant, PROPOSALS.c.status == "gonderildi", PROPOSALS.c.sent_at >= week)).scalar() or 0
            last = c.execute(sa.select(RUNS).where(RUNS.c.tenant_id == tenant, RUNS.c.kind == "tsoft")
                             .order_by(RUNS.c.started_at.desc()).limit(1)).mappings().first()
        daily = seo.gsc("daily")
        return {
            "products": total, "activeAverage": round(float(avg), 1) if avg is not None else None,
            "failing": failing, "failingThreshold": 70,
            "rules": [{"rule": k, "title": v[2], "severity": v[1], "count": by_rule[k]} for k, v in rules.RULES.items()],
            "proposals": status, "sentThisWeek": sent_week,
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
                     limit: int = 50, order: str = "score") -> dict[str, Any]:
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
            sort = PRODUCTS.c.name.asc() if order == "name" else PRODUCTS.c.score.asc()
            rows = c.execute(sa.select(PRODUCTS).where(*cond).order_by(sort, PRODUCTS.c.product_id)
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
        return _proposal_view(seo.send(prop, fields, user, body.note))

    @app.post("/api/v1/seo-geo/proposals/bulk-approve")
    def seo_bulk(body: BulkApprove, request: Request) -> dict[str, Any]:
        user = approver(request)
        out = []
        for pid in dict.fromkeys(body.ids):
            prop = seo.proposal(pid)
            if prop["status"] != "hazir":
                out.append({"id": pid, "status": prop["status"], "skipped": True})
                continue
            done = seo.send(prop, loads(prop["fields_json"], {}), user, body.note)
            out.append({"id": pid, "status": done["status"], "result": done["result"]})
        return {"items": out}

    @app.post("/api/v1/seo-geo/proposals/{proposal_id}/revert")
    def seo_revert(proposal_id: str, request: Request) -> dict[str, Any]:
        user = approver(request)
        prop = seo.proposal(proposal_id)
        if prop["status"] != "gonderildi":
            raise _err(409, "Yalnız gönderilmiş öneri geri alınır.")
        before = loads(prop["before_json"], {})
        fields = {k: before.get(k, "") for k in loads(prop["fields_json"], {}) if k in propose.FIELDS}
        # Boş gönderilen alan T-soft'ta boşalır; önceki değer boşsa geri alma onu da boşaltır.
        try:
            connections.tsoft.update_product(prop["product_id"], fields)
            connections.tsoft.clear_product_cache()
            fresh = connections.tsoft.product(prop["product_id"])
            if fresh:
                seo._store_one(fresh)
        except connections.ConnectionError_ as e:
            raise _err(502, str(e)) from None
        with seo.engine().begin() as c:
            c.execute(PROPOSALS.update().where(PROPOSALS.c.id == proposal_id).values(
                status="geri_alindi", result=f"Geri alındı ({user}): " + ", ".join(fields)))
        seo.audit(user, "revert", prop["product_id"], prop["product_id"], {"proposal": proposal_id, "fields": list(fields)})
        return _proposal_view(seo.proposal(proposal_id))

    @app.post("/api/v1/seo-geo/proposals/batch")
    def seo_batch(request: Request, budget: int = 3600) -> dict[str, Any]:
        user = gate(request)
        started = seo.start_batch(user, budget)
        seo.audit(user, "run", "batch", "SEO öneri ön üretimi", {"started": started, "budget": budget})
        return {"started": started, "batch": seo.batch}

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
        threading.Thread(target=later, name="seo-batch-wait", daemon=True).start()
        out["batch"] = f"başlayacak (bütçe {budget} sn)"
        return out

    return seo
