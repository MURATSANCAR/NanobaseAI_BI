"""M27 Fuar, etkinlik ve ödül: uçlar (`/api/v1/events/*`).

Sayfa kapısı `access.RULES` (`sayfa:etkinlikler`); kart, kitap listesi, görev ekleme/silme, gider, yazar programı ve
tip eşlemesi `ozellik:etkinlik.duzenle`, ödül defteri `ozellik:odul.duzenle`, PDF `ozellik:veri.disa-aktar`
(`FEATURE_RULES`). Katılım kararı / bütçe onayı açıkça verilen `ozellik:etkinlik.onay` ile ucun içinde denetlenir
(kartı açan onaylayamaz). Görevi «yapıldı» işaretlemek görevin sahibine de açıktır (telefonda tek dokunuş).
Kampüs ajandası (`/me/agenda`) oturum yeter: yalnız kişinin kendi kayıtları döner. Zamanlayıcı
(`timas-events.timer`) yalnız `POST /run-due`'yu çağırır.

Dış gönderim yok (kullanıcı kararı 2026-09-28): e-posta/SMS atılmaz; hatırlatmalar ekranda ve Kampüs ajandasında.
CRM'e ve Logo'ya yazılmaz.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from datetime import date, timedelta
from typing import Any, Callable, Optional

# Modül düzeyinde: `from __future__ import annotations` ile fonksiyon içindeki `Request` sorgu parametresi sanılır (422).
from fastapi import HTTPException, Request
from fastapi.responses import Response

from semantic_bridge import events as E
from semantic_bridge import events_kaynak as K
from semantic_bridge import events_sources as src
from semantic_bridge import provenance as PV
from semantic_bridge.events import EventsError

log = logging.getLogger("semantic.events.api")
P = "/api/v1/events"
PAGE = 50


class Service:
    """Kaynak okuması + hesaplar. Tip sınıflaması arka planda tek iş (aynı anda bir tane)."""

    def __init__(self, source: src.Source, llm: Callable[[Optional[int]], Any]):
        self.source = source
        self.llm = llm
        self._job_lock = threading.Lock()
        self.job: dict[str, Any] = {"state": "bos"}
        self._cancel = threading.Event()

    # -------------------------------------------------------------- takvim
    def calendar(self, engine, tenant: str, year: int, classes: list[str], unmapped: bool, fresh: bool) -> dict[str, Any]:
        fairs = E.list_fairs(engine, tenant, year)
        warnings: list[str] = []
        t0 = time.monotonic()
        try:
            events = self.source.events(date(year, 1, 1), date(year + 1, 1, 1), fresh)
        except Exception as e:  # noqa: BLE001 — CRM düşerse portal kartları yine görünür
            log.warning("events: CRM etkinlikleri okunamadı: %s", e)
            events = []
            warnings.append("CRM'e şu an ulaşılamıyor; yalnız portaldaki kartlar gösteriliyor.")
        ms = int((time.monotonic() - t0) * 1000)
        tmap = E.type_map(engine, tenant)
        ev = E.classify_events(events, tmap)
        cal = E.calendar(fairs, ev, year, classes, unmapped)
        cal["unmappedTypes"] = len({e["tipId"] for e in ev if e.get("tipId") and not e.get("sinif")})
        cal["warnings"] = warnings
        cal["crmMs"] = ms
        return cal

    def crm_events(self, engine, tenant: str, frm: date, to: date, cls: str, q: str, page: int, fresh: bool) -> dict[str, Any]:
        if to <= frm:
            raise EventsError("Bitiş başlangıçtan sonra olmalı.", 422)
        ev = E.classify_events(self.source.events(frm, to, fresh), E.type_map(engine, tenant))
        wanted = {c for c in cls.split(",") if c and c != "hepsi"} if cls else set()   # boş ya da «hepsi» = süzgeç yok
        qf = E.fold(q)
        items = [e for e in ev if (not wanted or (e.get("sinif") or "yok") in wanted)
                 and (not qf or qf in E.fold(" ".join(str(e.get(k) or "") for k in ("ad", "tip", "yer", "il", "sorumluAd"))))]
        items.sort(key=lambda e: (e.get("baslangic") or "", e.get("ad") or ""))
        page = max(0, page)
        return {"items": items[page * PAGE:(page + 1) * PAGE], "total": len(items), "page": page, "pageSize": PAGE,
                "from": frm.isoformat(), "to": (to - timedelta(days=1)).isoformat()}

    # -------------------------------------------------------------- öneri ve sonuç
    def _prev(self, engine, tenant: str, fair: dict[str, Any]) -> Optional[dict[str, Any]]:
        if not fair.get("prev_fair_id"):
            return None
        try:
            return E.fair_row(engine, tenant, fair["prev_fair_id"])
        except EventsError:
            return None

    def suggest(self, engine, tenant: str, user: str, fair_id: str, fresh: bool) -> dict[str, Any]:
        st = E.settings()
        fair = E.fair_row(engine, tenant, fair_id)
        if fair["status"] == "iptal":
            raise EventsError("İptal edilmiş karta öneri yapılmaz.", 409)
        basis = E.basis_window(fair, self._prev(engine, tenant, fair))
        sales = self.source.fair_sales(date.fromisoformat(basis["from"]), date.fromisoformat(basis["to"]) + timedelta(days=1),
                                       st["channel"], basis["codes"], fresh)
        warnings = list(sales["warnings"])
        try:
            stock: Optional[dict[str, float]] = self.source.stock(fresh)
        except Exception as e:  # noqa: BLE001
            log.warning("events: stok okunamadı: %s", e)
            stock = None
            warnings.append("Stok okunamadı; stok karşılaştırması yapılmadı, yeni çıkanlar stok şartı aranmadan eklendi.")
        books = self.source.books(fresh)
        items = E.suggest_books(sales["rows"], stock, books, st, fair["starts_on"], basis["label"])
        counts = E.save_suggestions(engine, tenant, user, fair["id"], items)
        if not sales["rows"]:
            warnings.append(f"Temel dönemde ({basis['label']}, {E._tr_day(basis['from'])}–{E._tr_day(basis['to'])}) fuar kanalında "
                            "satış yok; kitapları elle ekleyin ya da önceki fuar kartını bağlayın.")
        return {"counts": counts, "basis": basis, "warnings": warnings, "sql": sales["sql"],
                "detail": E.fair_detail(engine, tenant, fair["id"])}

    def result(self, engine, tenant: str, fair_id: str, fresh: bool, save: bool = True) -> dict[str, Any]:
        st = E.settings()
        fair = E.fair_row(engine, tenant, fair_id)
        prev = self._prev(engine, tenant, fair)
        basis = E.basis_window(fair, prev)
        a, b = E.result_window(fair, st["resultTailDays"])
        codes = E._json_list(fair["logo_client_codes_json"])
        logo_err = crm_err = None
        sales: dict[str, Any] = {"rows": [], "warnings": [], "sql": []}
        prev_sales: Optional[dict[str, Any]] = None
        data_end = None
        try:
            sales = dict(self.source.fair_sales(a, b, st["channel"], codes, fresh))
            prev_sales = self.source.fair_sales(date.fromisoformat(basis["from"]), date.fromisoformat(basis["to"]) + timedelta(days=1),
                                                st["channel"], basis["codes"], fresh)
            data_end = self.source.data_end(fresh)
        except Exception as e:  # noqa: BLE001
            log.warning("events: Logo okunamadı: %s", e)
            logo_err = str(e) if isinstance(e, src.SourceError) else "Logo'ya şu an ulaşılamıyor."
        sales["channel"] = st["channel"]
        orders: list[dict[str, Any]] = []
        crm_events: list[dict[str, Any]] = []
        try:
            orders = self.source.orders(a, b, st["orderTypes"], st["orderExcluded"], fresh)
            ids = E._json_list(fair["crm_event_ids_json"])
            crm_events = self.source.events_by_id(ids) if ids else []
        except Exception as e:  # noqa: BLE001
            log.warning("events: CRM okunamadı: %s", e)
            crm_err = str(e) if isinstance(e, src.SourceError) else "CRM'e şu an ulaşılamıyor."
        r = E.compute_result(fair, sales=sales, prev_sales=prev_sales, basis=basis, orders=orders, crm_events=crm_events,
                             costs=E.fair_costs(engine, fair["id"]), planned=E.planned_books(engine, fair["id"]),
                             data_end=data_end, tail_days=st["resultTailDays"], logo_error=logo_err, crm_error=crm_err)
        r["complete"] = not logo_err and not crm_err
        r["sqlOnceki"] = (prev_sales or {}).get("sql") or []
        if save and r["complete"]:
            E.save_result(engine, tenant, fair["id"], r)
        return r

    # -------------------------------------------------------------- tip sınıflaması (arka plan)
    def start_classify(self, engine, tenant: str, user: str, only_missing: bool) -> dict[str, Any]:
        llm = self.llm(None)
        if llm is None or not hasattr(llm, "choose"):
            raise EventsError("Zeki AI bu kurulumda bağlı değil; eşlemeyi elle yapın.", 503)
        with self._job_lock:
            if self.job.get("state") == "calisiyor":
                raise EventsError("Sınıflama zaten sürüyor.", 409)
            self.job = {"state": "calisiyor", "by": user, "done": 0, "total": None, "startedAt": time.time()}
            self._cancel.clear()
        types = self.source.types()
        t = E.today()
        try:
            recent = self.source.events(t - timedelta(days=365), t + timedelta(days=1))
        except Exception:  # noqa: BLE001 — örnek adlar olmadan da sorulur
            recent = []
        samples: dict[str, list[str]] = {}
        for e in recent:
            if e.get("tipId") and e.get("ad"):
                lst = samples.setdefault(e["tipId"], [])
                if e["ad"] not in lst and len(lst) < 5:
                    lst.append(e["ad"])
        batch = self.llm(1)

        def progress(i: int, n: int) -> None:
            self.job.update(done=i, total=n)

        def run() -> None:
            try:
                out = E.classify_types(engine, tenant, types, lambda p, ch: batch.choose(p, ch, user_id=user), samples,
                                       only_missing=only_missing, cancel=self._cancel, progress=progress)
                self.job.update(state="bitti", result=out, endedAt=time.time())
            except Exception as e:  # noqa: BLE001
                log.warning("events: tip sınıflaması yarıda kaldı: %s", e)
                self.job.update(state="hata", error="Zeki AI cevap vermedi; kalan tipler sonra yeniden sorulabilir.", endedAt=time.time())

        threading.Thread(target=run, name="events-classify", daemon=True).start()
        return dict(self.job)


def register(app: Any, deps: dict[str, Any]) -> Service:
    """app.py'de bağlanır. `deps`:
    auth(request) → (engine, tenant, user, display) · can(user, key) · is_admin(user) ·
    audit(engine, user, action, kind, id, title, detail) · conf(key, default) · fresh() → bool ·
    crm_connect() / logo_connect() → salt okunur bağlantı · llm(priority) → LLM kapısı istemcisi ya da None ·
    system() → (engine, tenant) · require_caller(request) (zamanlayıcı jetonu)."""
    auth, can, is_admin, audit, conf, fresh = (deps[k] for k in ("auth", "can", "is_admin", "audit", "conf", "fresh"))
    source = src.Source(deps["crm_connect"], deps["logo_connect"], lambda: conf("CRM_SCHEMA") or "Timas_MSCRM.dbo")
    svc = Service(source, deps.get("llm") or (lambda _p: None))

    def fair_out(engine, tenant: str, fid: str) -> dict[str, Any]:
        d = fair_out(engine, tenant, fid)
        return PV.bagla(d, lambda: K.for_fair(engine, tenant, d["id"]))

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        engine, tenant, user, display = auth(request)
        E.ensure(engine)
        return engine, tenant, (user or "").lower(), display

    def allowed(user: str, key: str) -> bool:
        return bool(is_admin(user) or can(user, key))

    def need(user: str, key: str, what: str) -> None:
        if not allowed(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except EventsError as e:
            code = "FORBIDDEN" if e.status == 403 else "EVENTS"
            raise HTTPException(status_code=e.status, detail={"code": code, "message": str(e)}) from e
        except src.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "DATA_SOURCE_UNAVAILABLE", "message": str(e)}) from e
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001 — kaynak düştüyse kişiye düz cümle, ayrıntı günlükte
            log.exception("events: istek başarısız")
            state = str(getattr(e, "args", [""])[0])
            if state in ("08S01", "08001", "HYT00", "HYT01") or "timeout" in str(e).lower():
                raise HTTPException(status_code=503, detail={"code": "DATA_SOURCE_UNAVAILABLE", "retryable": True,
                                    "message": "CRM ya da Logo şu anda yanıt vermiyor; birazdan tekrar deneyin."}) from e
            raise HTTPException(status_code=502, detail={"code": "EVENTS", "message": "Etkinlik kayıtları okunamadı."}) from e

    def fair_audit(engine, user, action, fid, title, detail=None) -> None:
        audit(engine, user, action, "events_fair", fid, title, detail)

    def year_of(v: Optional[int]) -> int:
        y = int(v or E.today().year)
        if y < 2000 or y > 2100:
            raise HTTPException(status_code=422, detail={"code": "EVENTS", "message": "Yıl geçersiz."})
        return y

    # ---- genel

    @app.get(f"{P}/meta")
    def events_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        st = E.settings()
        return {"classes": E.CLASSES, "kinds": E.FAIR_KINDS, "statuses": E.FAIR_STATUSES, "phases": E.PHASES,
                "costKinds": E.COST_KINDS, "entryStatuses": E.ENTRY_STATUSES, "orderTypes": src.ORDER_TYPES,
                "settings": {k: st[k] for k in ("channel", "orderTypes", "remindDays", "awardRemindDays", "agendaDays",
                                                "newBookMonths", "newBookFactor", "suggestFactor", "resultTailDays",
                                                "defaultClasses", "receiptMaxMb")},
                "today": E.today().isoformat(), "job": dict(svc.job),
                "me": {"username": user, "display": display, "admin": bool(is_admin(user)),
                       "canEdit": allowed(user, "ozellik:etkinlik.duzenle"), "canApprove": allowed(user, "ozellik:etkinlik.onay"),
                       "canAwards": allowed(user, "ozellik:odul.duzenle"), "canExport": allowed(user, "ozellik:veri.disa-aktar")}}

    @app.get(f"{P}/calendar")
    def events_calendar(request: Request, year: Optional[int] = None, classes: str = "", unmapped: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        cls = [c for c in classes.split(",") if c in E.CLASSES] if classes else E.settings()["defaultClasses"]
        y = year_of(year)
        return PV.bagla(call(svc.calendar, engine, tenant, y, cls, bool(unmapped), fresh()), lambda: K.for_calendar(engine, tenant, y))

    @app.get(f"{P}/upcoming")
    def events_upcoming(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return PV.bagla(call(E.upcoming, engine, tenant), lambda: K.for_upcoming(engine, tenant))

    @app.get(f"{P}/crm-events")
    def events_crm(request: Request, frm: str = "", to: str = "", cls: str = "", q: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        t = E.today()
        a = call(E.parse_day, frm, "Başlangıç") or date(t.year, 1, 1)
        b = call(E.parse_day, to, "Bitiş") or date(t.year, 12, 31)
        out = call(svc.crm_events, engine, tenant, a, b + timedelta(days=1), cls, q, page, fresh())
        return PV.bagla(out, lambda: K.for_crm_events(engine, tenant, a, b + timedelta(days=1)))

    @app.get(f"{P}/me/agenda")
    def events_agenda(request: Request) -> dict[str, Any]:
        """Kampüs «Önemli günler ve ajanda»: yalnız kişinin kendi kayıtları (sayfa yetkisi gerekmez)."""
        engine, tenant, user, _ = ctx(request)
        days = E.settings()["agendaDays"]
        t = E.today()
        warnings = []
        try:
            crm = source.events(t, t + timedelta(days=days + 1), fresh())
        except Exception as e:  # noqa: BLE001
            log.info("events agenda: CRM okunamadı: %s", e)
            crm = []
            warnings.append("CRM'e şu an ulaşılamıyor; yalnız portal kayıtları gösteriliyor.")
        from semantic_bridge import kampus_kaynak as KK
        from semantic_bridge import provenance as PV
        from semantic_bridge import soru_kaynak as SK
        from semantic_bridge import sorgu_izi as IZ

        with IZ.izle(engine) as ran:
            out = call(E.agenda, engine, tenant, user, crm, t, days)
        out["warnings"] = warnings
        out["canOpen"] = allowed(user, "sayfa:etkinlikler")

        def extra(k: PV.Kaynaklar) -> list[str]:
            try:
                return KK.agenda_sources(k, source._schema(), t, t + timedelta(days=days + 1), SK.databases()[1])
            except Exception:  # noqa: BLE001 — CRM şeması tanımlı değilse yalnız portal kayıtları
                return []
        return PV.bagla(out, lambda: IZ.kaynak(engine, ran, out, prefix="portal.kampus.ajanda", title="Ajanda",
                                               text=KK.F_AJANDA, extra=extra, skip=("days",)))

    @app.post(f"{P}/run-due")
    def events_run_due(request: Request) -> dict[str, Any]:
        """Zamanlayıcı (her gün 07:45): hatırlatmalar; biten fuarların sonucunu ön hesaplar, veri sonu fuarın bitişinden
        önceyse sonraki günlerde yeniden hesaplar."""
        deps["require_caller"](request)
        engine, tenant = deps["system"]()
        E.ensure(engine)
        t0 = time.monotonic()
        made = E.run_reminders(engine, tenant)
        results: list[dict[str, Any]] = []
        todo = set(E.fairs_needing_result(engine, tenant))
        for f in E.list_fairs(engine, tenant, active_only=True):
            if f["endsOn"] < E.today().isoformat() and f["endsOn"] >= (E.today() - timedelta(days=60)).isoformat():
                row = E.fair_row(engine, tenant, f["id"])
                if row["result_json"]:
                    old = json.loads(row["result_json"])
                    if (old.get("dataEnd") or "") < (old.get("window") or {}).get("to", ""):
                        todo.add(f["id"])
        for fid in sorted(todo):
            try:
                r = svc.result(engine, tenant, fid, fresh=True)
                if r.get("complete"):
                    E.note_result(engine, tenant, fid)
                results.append({"id": fid, "complete": r.get("complete"), "netCiro": r.get("netCiro")})
            except Exception as e:  # noqa: BLE001
                results.append({"id": fid, "error": str(e)[:200]})
        out = {"reminders": made, "results": results, "ms": int((time.monotonic() - t0) * 1000)}
        audit(engine, "sistem", "run", "events_run_due", None, "Fuar ve etkinlik zamanlı iş", out)
        return out

    # ---- CRM tip eşlemesi

    @app.get(f"{P}/type-map")
    def events_type_map(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        types = call(source.types, fresh())
        rows = E.type_rows(types, E.type_map(engine, tenant))
        out = {"items": rows, "classes": E.CLASSES, "job": dict(svc.job),
               "counts": {"total": len(rows), "decided": sum(1 for r in rows if r["class"]),
                          "suggested": sum(1 for r in rows if not r["class"] and r["suggested"])}}
        return PV.bagla(out, lambda: K.for_type_map(engine, tenant))

    @app.put(f"{P}/type-map")
    def events_type_map_put(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        names = {t["id"]: t["ad"] for t in call(source.types)}
        diff = call(E.set_types, engine, tenant, user, body.get("items"), names)
        if diff:
            audit(engine, user, "update", "events_type_map", None, f"Etkinlik tipi eşlemesi ({len(diff)} tip)", diff)
        return {"changed": len(diff)}

    @app.post(f"{P}/type-map/suggest")
    def events_type_map_suggest(request: Request, hepsi: int = 0) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(svc.start_classify, engine, tenant, user, not bool(hepsi))
        audit(engine, user, "run", "events_type_map", None, "Zeki AI etkinlik tipi önerisi başlatıldı", {"hepsi": bool(hepsi)})
        return out

    # ---- kartlar

    @app.get(f"{P}/fairs")
    def events_fairs(request: Request, year: Optional[int] = None) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        y = year_of(year) if year else None
        return PV.bagla({"items": call(E.list_fairs, engine, tenant, y)}, lambda: K.for_fairs(engine, tenant, y))

    @app.post(f"{P}/fairs", status_code=201)
    def events_fair_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        fid = call(E.create_fair, engine, tenant, user, body)
        d = fair_out(engine, tenant, fid)
        fair_audit(engine, user, "create", fid, d["name"], {"tarih": [d["startsOn"], d["endsOn"]], "tur": d["kind"],
                                                            "butce": d["budgetPlanned"], "gorev": d["tasksTotal"]})
        return d

    @app.get(f"{P}/fairs/{{fid}}")
    def events_fair(fid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        call(E.fair_row, engine, tenant, fid)
        return fair_out(engine, tenant, fid)

    @app.patch(f"{P}/fairs/{{fid}}")
    def events_fair_patch(fid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(E.update_fair, engine, tenant, user, fid, body)
        d = fair_out(engine, tenant, fid)
        if out["diff"]:
            fair_audit(engine, user, "update", fid, d["name"], {**out["diff"], **({"not": "tarih/bütçe değişti, karar yeniden gerekli"}
                                                                                   if out["reopened"] else {})})
        d["reopened"] = out["reopened"]
        return d

    @app.delete(f"{P}/fairs/{{fid}}")
    def events_fair_delete(fid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        cur = call(E.delete_fair, engine, tenant, fid)
        fair_audit(engine, user, "delete", fid, cur["name"], None)
        return {"ok": True}

    @app.post(f"{P}/fairs/{{fid}}/approve")
    def events_fair_approve(fid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, "ozellik:etkinlik.onay", "Katılım kararı ve bütçe onayı")
        out = call(E.approve_fair, engine, tenant, user, fid, body.get("note"))
        fair_audit(engine, user, "approve", fid, out["name"], {"butce": out["budget"], "not": body.get("note")})
        return fair_out(engine, tenant, fid)

    @app.post(f"{P}/fairs/{{fid}}/suggest-books")
    def events_fair_suggest(fid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(svc.suggest, engine, tenant, user, fid, fresh())
        fair_audit(engine, user, "run", fid, out["detail"]["name"], {"oneri": out["counts"], "temel": out["basis"]["label"]})
        return PV.bagla(out, lambda: K.for_suggest(engine, tenant, fid, source, out.get("sql") or []))

    @app.put(f"{P}/fairs/{{fid}}/books")
    def events_fair_books(fid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        items = body.get("items")
        new_codes = isinstance(items, list) and any(isinstance(i, dict) and i.get("new") for i in items)
        books = call(source.books) if new_codes else None
        out = call(E.put_books, engine, tenant, user, fid, items, books)
        if out["diff"]:
            audit(engine, user, "update", "events_books", fid, out["fair"], out["diff"])
        return fair_out(engine, tenant, fid)

    @app.post(f"{P}/fairs/{{fid}}/tasks", status_code=201)
    def events_task_add(fid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(E.add_task, engine, tenant, user, fid, body)
        audit(engine, user, "create", "events_task", out["id"], f"{out['fair']} · {out['title']}", None)
        return fair_out(engine, tenant, fid)

    @app.patch(f"{P}/fairs/{{fid}}/tasks/{{tid}}")
    def events_task_patch(fid: str, tid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(E.patch_task, engine, tenant, user, fid, tid, body, allowed(user, "ozellik:etkinlik.duzenle"))
        if out["diff"]:
            audit(engine, user, "update", "events_task", tid, f"{out['fair']} · {out['title']}", out["diff"])
        return fair_out(engine, tenant, fid)

    @app.delete(f"{P}/fairs/{{fid}}/tasks/{{tid}}")
    def events_task_delete(fid: str, tid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(E.delete_task, engine, tenant, fid, tid)
        audit(engine, user, "delete", "events_task", tid, f"{out['fair']} · {out['title']}", None)
        return fair_out(engine, tenant, fid)

    @app.post(f"{P}/fairs/{{fid}}/costs", status_code=201)
    def events_cost_add(fid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(E.add_cost, engine, tenant, user, fid, body, E.settings()["receiptMaxMb"])
        audit(engine, user, "create", "events_cost", out["id"], out["fair"],
              {"tur": out["kind"], "tutar": out["amount"], "fis": out["receipt"]})
        return fair_out(engine, tenant, fid)

    @app.delete(f"{P}/fairs/{{fid}}/costs/{{cid}}")
    def events_cost_delete(fid: str, cid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(E.delete_cost, engine, tenant, fid, cid)
        audit(engine, user, "delete", "events_cost", cid, out["fair"], {"tur": out["kind"], "tutar": out["amount"]})
        return fair_out(engine, tenant, fid)

    @app.get(f"{P}/fairs/{{fid}}/costs/{{cid}}/receipt")
    def events_cost_receipt(fid: str, cid: str, request: Request) -> Response:
        engine, tenant, _, _ = ctx(request)
        data, ctype, name = call(E.receipt, engine, tenant, fid, cid)
        return Response(content=data, media_type=ctype, headers={"Content-Disposition": f'inline; filename="{name}"',
                                                                 "Cache-Control": "private, max-age=300"})

    @app.post(f"{P}/fairs/{{fid}}/authors", status_code=201)
    def events_author_add(fid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(E.add_author, engine, tenant, user, fid, body)
        audit(engine, user, "create", "events_author", out["id"], f"{out['fair']} · {out['name']}",
              {"cakisma": len(out["conflicts"])})
        d = fair_out(engine, tenant, fid)
        d["newConflicts"] = out["conflicts"]
        return d

    @app.delete(f"{P}/fairs/{{fid}}/authors/{{aid}}")
    def events_author_delete(fid: str, aid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(E.delete_author, engine, tenant, fid, aid)
        audit(engine, user, "delete", "events_author", aid, f"{out['fair']} · {out['name']}", None)
        return fair_out(engine, tenant, fid)

    @app.get(f"{P}/fairs/{{fid}}/result")
    def events_result(fid: str, request: Request, yenile: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        row = call(E.fair_row, engine, tenant, fid)
        if row["result_json"] and not yenile and not fresh():
            r = json.loads(row["result_json"])
            r["complete"] = True
            r["cached"] = True
        else:
            r = call(svc.result, engine, tenant, fid, True)
        out = {"fair": E.fair_detail(engine, tenant, fid), "result": r}
        return PV.bagla(out, lambda: K.for_result(engine, tenant, fid, source, r, row))

    @app.get(f"{P}/fairs/{{fid}}/result/export.pdf")
    def events_result_pdf(fid: str, request: Request) -> Response:
        engine, tenant, user, display = ctx(request)
        row = call(E.fair_row, engine, tenant, fid)
        r = json.loads(row["result_json"]) if row["result_json"] else call(svc.result, engine, tenant, fid, False)
        data = call(E.result_pdf, row, r, display or user)
        audit(engine, user, "run", "events_result_pdf", fid, f"{row['name']} · sonuç PDF", None)
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="fuar-sonucu-{fid[:8]}.pdf"'})

    # ---- aramalar (kitap, yazar, fuar carisi) ve yazar etkinlikleri

    def _search(items: list[dict[str, Any]], q: str, keys: tuple[str, ...]) -> dict[str, Any]:
        qf = E.fold(q)
        if len(qf) < 2:
            return {"items": [], "total": 0, "shown": 0}
        hits = [x for x in items if all(w in E.fold(" ".join(str(x.get(k) or "") for k in keys)) for w in qf.split())]
        hits.sort(key=lambda x: (not E.fold(x.get(keys[0])).startswith(qf), E.fold(x.get(keys[0]))))
        return {"items": hits[:PAGE], "total": len(hits), "shown": min(len(hits), PAGE)}

    @app.get(f"{P}/lookup/books")
    def events_lookup_books(request: Request, q: str = "") -> dict[str, Any]:
        ctx(request)
        return PV.bagla(_search(list(call(source.books).values()), q, ("ad", "stokKodu", "yazar")), K.for_lookup_books)

    @app.get(f"{P}/lookup/authors")
    def events_lookup_authors(request: Request, q: str = "") -> dict[str, Any]:
        ctx(request)
        return PV.bagla(_search(call(source.authors), q, ("ad",)), K.for_lookup_authors)

    @app.get(f"{P}/lookup/clients")
    def events_lookup_clients(request: Request) -> dict[str, Any]:
        ctx(request)
        ch = E.settings()["channel"]
        items = call(source.channel_clients, ch, fresh())
        return PV.bagla({"items": sorted(items, key=lambda x: (x["pasif"], x["kod"] or "")), "channel": ch},
                        lambda: K.for_clients(source, ch))

    @app.get(f"{P}/authors/{{cid}}/events")
    def events_author_events(cid: str, request: Request, year: Optional[int] = None) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        y = year_of(year)
        items = E.classify_events(call(source.author_events, cid, date(y, 1, 1), date(y + 1, 1, 1)), E.type_map(engine, tenant))
        items.sort(key=lambda e: e.get("baslangic") or "")
        return PV.bagla({"year": y, "items": items, "total": len({e["id"] for e in items})},
                        lambda: K.for_author_events(engine, tenant, cid, y))

    # ---- ödül defteri

    @app.get(f"{P}/awards")
    def events_awards(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return PV.bagla(E.list_awards(engine, tenant), lambda: K.for_awards(engine, tenant))

    @app.post(f"{P}/awards", status_code=201)
    def events_award_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(E.create_award, engine, tenant, user, body)
        audit(engine, user, "create", "award", out["id"], out["name"], {k: body.get(k) for k in ("deadline", "category")})
        return E.list_awards(engine, tenant)

    @app.patch(f"{P}/awards/{{aid}}")
    def events_award_patch(aid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(E.update_award, engine, tenant, user, aid, body)
        if out["diff"]:
            audit(engine, user, "update", "award", aid, out["name"], {k: v for k, v in out["diff"].items() if k != "conditions"})
        return E.list_awards(engine, tenant)

    @app.delete(f"{P}/awards/{{aid}}")
    def events_award_delete(aid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(E.delete_award, engine, tenant, aid)
        audit(engine, user, "delete", "award", aid, out["name"], {"basvuru": out["entries"]})
        return E.list_awards(engine, tenant)

    @app.post(f"{P}/awards/{{aid}}/entries", status_code=201)
    def events_entry_add(aid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        books = call(source.books) if body.get("stokKodu") else None
        out = call(E.add_entry, engine, tenant, user, aid, body, books)
        audit(engine, user, "create", "award_entry", out["id"], f"{out['award']} · {out['book']}", None)
        return E.list_awards(engine, tenant)

    @app.patch(f"{P}/award-entries/{{eid}}")
    def events_entry_patch(eid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(E.patch_entry, engine, tenant, user, eid, body)
        if out["diff"] or "text" in body:
            audit(engine, user, "update", "award_entry", eid, f"{out['award']} · {out['book']}",
                  {**out["diff"], **({"metin": "güncellendi"} if "text" in body else {})})
        return E.list_awards(engine, tenant)

    @app.delete(f"{P}/award-entries/{{eid}}")
    def events_entry_delete(eid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(E.delete_entry, engine, tenant, eid)
        audit(engine, user, "delete", "award_entry", eid, f"{out['award']} · {out['book']}", None)
        return E.list_awards(engine, tenant)

    return svc
