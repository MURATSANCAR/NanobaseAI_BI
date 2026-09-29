"""M44 Lojistik ve kargo uçları: /api/v1/shipping/*.

Sayfa kapısı `access.RULES`: günlük hat, gönderi arama/kartı ve taslaklar `sayfa:kargo`; firma karnesi ve karar kaydı
`sayfa:kargo-firmalar`; mutabakat `sayfa:kargo-mutabakat`. İşlem yetkileri:

- `ozellik:kargo.maliyet` (açıkça verilir) — tutar, desi, desi/sevk başı maliyet ve mutabakat. Yetkisi olmayana bu alanlar
  sunucuda çıkarılır (ekranda gizlemek yetmez).
- `ozellik:kargo.alici` (açıkça verilir, KVKK) — gönderi kartında alıcı ve teslim alan adı. Liste ve dışa aktarmada hiç yok.
- `ozellik:kargo.karar` (açıkça verilir) — kurye/bölge/sözleşme kararı kaydı ve iş eşikleri (N gün, il hedefleri).
- `ozellik:kargo.taslak` — Zeki AI gecikme/özür/iade mesajı taslağı (`FEATURE_RULES`); gönderimi insan yapar.
- `ozellik:veri.disa-aktar` — Excel (`FEATURE_RULES`).

Zamanlayıcı (`timas-shipping.timer`, 15 dk) yalnız `POST /api/v1/shipping/run-due`'yu çağırır; köprü günde bir (06:45 sonrası)
hata sınıflaması + iç özet e-postası, pazartesi (08:00 sonrası) haftalık firma karnesi, ayın 3'ünde önceki ayın
mutabakat özeti işlerini kendisi zamanlar. Alıcılar yönetim ekranındaki ayardır; boşsa e-posta gitmez. Kargo firmasına,
CRM'e, Logo'ya ya da müşteriye hiçbir şey gönderilmez.

Model çağrıları LLM kapısından: `llm(priority)` → `rt.llm_for("kargo", …)`; `LlmClient` doğrudan kurulmaz.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request
from fastapi.responses import Response

from semantic_bridge import provenance as PV
from semantic_bridge import shipping as S
from semantic_bridge import shipping_kaynak as K
from semantic_bridge import shipping_sources as src

log = logging.getLogger("semantic.shipping.api")
P = "/api/v1/shipping"
F_COST = "ozellik:kargo.maliyet"
F_RECIPIENT = "ozellik:kargo.alici"
F_DECIDE = "ozellik:kargo.karar"
F_DRAFT = "ozellik:kargo.taslak"
F_EXPORT = "ozellik:veri.disa-aktar"
PAGE_HOME, PAGE_CARRIERS, PAGE_RECONCILE = "sayfa:kargo", "sayfa:kargo-firmalar", "sayfa:kargo-mutabakat"
TTL = 5 * 60
LIST_PAGE = 50
XLSX = S.XLSX_MIME


class _Cache:
    """Süreli bellek (5 dk) + ağır okumalarda portal anlık görüntüsü (`S.SNAPSHOTS`). Aynı anahtarı iki iş parçacığı
    birlikte okumaz. Her okumanın çalıştırdığı sorgular değerle birlikte saklanır; önbellekten ya da görüntüden dönen
    değerde de açık sorgu bilgisi toplayıcısına verilir (`src.collect`).

    `persist=True` okumada sıra: bellek → görüntü (`SHIPPING_SNAPSHOT_MAX_MIN` dakikadan tazeyse; zamanlayıcı 15 dakikada
    bir yeniler) → CRM (sonuç görüntüye yazılır). Görüntüden dönen değer okumanın dönüşünün aynısıdır; sorgu bilgisinde
    görüntü okuması (portal) ve kökeni olarak zamanlayıcıda çalışan CRM metni görünür. «Yenile» (`fresh`) her zaman CRM'e
    gider. Görüntü okunamaz ya da yazılamazsa ekran canlı okumayla çalışır (rakam düşmez)."""

    def __init__(self, store: Optional[Callable[[], tuple[Any, str, int]]] = None) -> None:
        self._data: dict[Any, tuple[float, Any]] = {}
        self._runs: dict[Any, list[dict[str, Any]]] = {}
        self._locks: dict[Any, threading.Lock] = {}
        self._derived: dict[str, tuple[Any, Any]] = {}
        self._guard = threading.Lock()
        self._store = store

    def get(self, key: Any, ttl: float, load: Callable[[], Any], fresh: bool = False, persist: bool = False) -> Any:
        with self._guard:
            lock = self._locks.setdefault(key, threading.Lock())
        with lock:
            hit = self._data.get(key)
            if hit and not fresh and time.monotonic() - hit[0] < ttl:
                src.note(self._runs.get(key) or [])
                return hit[1]
            tag = key[0] if isinstance(key, tuple) else key
            if persist and not fresh:
                snap = self._snapshot(key, tag)
                if snap is not None:
                    val, runs = snap
                    self._data[key] = (time.monotonic(), val)
                    self._runs[key] = runs
                    src.note(runs)
                    return val
            t0 = time.monotonic()
            with src.collect() as got:
                val = load()
            for r in got:
                r.setdefault("tag", tag)
            self._data[key] = (time.monotonic(), val)
            self._runs[key] = list(got)
            if persist:
                self._save(key, val, list(got), int((time.monotonic() - t0) * 1000))
            return val

    def _snapshot(self, key: Any, tag: str) -> Optional[tuple[Any, list[dict[str, Any]]]]:
        if self._store is None:
            return None
        try:
            engine, tenant, max_min = self._store()
            t0 = time.monotonic()
            snap = S.snapshot_read(engine, tenant, S.snapshot_key(key), max_min)
            if snap is None:
                return None
            runs = [{**r, "tag": r.get("tag") or tag, "anlik": True} for r in snap["sorgular"]]
            runs.append({"name": "portal_anlik", "conn": "portal", "sql": PV.portal_sql(snap["stmt"], engine), "rows": 1,
                         "ms": int((time.monotonic() - t0) * 1000), "at": time.time(), "tag": tag,
                         "alindi": snap["alindi"].astimezone(S.TZ).strftime("%d.%m.%Y %H:%M")})
            return snap["deger"], runs
        except Exception as e:  # noqa: BLE001 — görüntü yoksa canlı okunur
            log.warning("kargo: anlık görüntü okunamadı (%s): %s", key, e)
            return None

    def _save(self, key: Any, val: Any, runs: list[dict[str, Any]], ms: int) -> None:
        if self._store is None:
            return
        try:
            engine, tenant, max_min = self._store()
            if max_min > 0:
                S.snapshot_write(engine, tenant, S.snapshot_key(key), val, runs, ms)
        except Exception as e:  # noqa: BLE001 — görüntü yazılamazsa ekran canlı okumayla çalışır
            log.warning("kargo: anlık görüntü yazılamadı (%s): %s", key, e)

    def derived(self, name: str, base: Any, build: Callable[[], Any]) -> Any:
        """`base` (bellekteki okuma) değişmedikçe aynı türetilmiş değer (ör. kargo kaydı dizini) yeniden kurulmaz."""
        with self._guard:
            hit = self._derived.get(name)
        if hit is not None and hit[0] is base:
            return hit[1]
        val = build()
        with self._guard:
            self._derived[name] = (base, val)
        return val

    def clear(self) -> None:
        with self._guard:
            self._data.clear()
            self._derived.clear()


def register(app: Any, deps: dict[str, Any]) -> _Cache:
    """app.py'de bağlanır. `deps`: auth(request) → (engine, tenant, user, display) · require_caller(request) · can(user, key) ·
    is_admin(user) · audit(engine, user, action, kind, id, title, detail) · conf(key, default) · engine() · tenant() ·
    logo_file() · crm_file() · llm(priority) → LLM kapısı istemcisi ya da None · send_mail(subject, text, to, attachments)."""
    auth, require_caller, can, is_admin, audit, conf = (deps[k] for k in ("auth", "require_caller", "can", "is_admin", "audit", "conf"))

    def cfg() -> dict[str, Any]:
        return S.settings_from(conf)

    def snapshot_store() -> tuple[Any, str, int]:
        engine = deps["engine"]()
        S.ensure(engine)
        return engine, deps["tenant"](), cfg()["snapshotMaxMin"]

    cache = _Cache(snapshot_store)

    def crm():
        return src.recording(src.runner(deps["crm_file"]()))

    def logo():
        return src.recording(src.runner(deps["logo_file"]()))

    def kdeps() -> dict[str, Any]:
        """Sorgu bilgisi bağlamı: yalnız veritabanı adları (bağlantı bilgisi okunmaz)."""
        return {"logo_db": PV.connection_database(deps["logo_file"]() or None),
                "crm_db": PV.connection_database(deps["crm_file"]() or None)}

    def model(priority: int):
        try:
            return deps["llm"](priority)
        except Exception as e:  # noqa: BLE001 — model tanımlı değil
            log.info("kargo: model yok: %s", e)
            return None

    def chooser(priority: int) -> Optional[Callable[[str, list[str]], Any]]:
        m = model(priority)
        if m is None or not hasattr(m, "choose"):
            return None
        return lambda prompt, choices: m.choose(prompt, choices)

    def chatter(priority: int, max_tokens: int = 500) -> Optional[Callable[[list[dict[str, str]]], str]]:
        m = model(priority)
        if m is None:
            return None
        return lambda messages: m.chat(messages, max_tokens=max_tokens, temperature=0.2)

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        engine, tenant, user, display = auth(request)
        S.ensure(engine)
        return engine, tenant, user, display

    def has(user: str, key: str) -> bool:
        return bool(is_admin(user) or can(user, key))

    def need(user: str, key: str, what: str) -> None:
        if not has(user, key):
            raise HTTPException(403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except S.ShippingError as e:
            raise HTTPException(e.status, detail={"code": "FORBIDDEN" if e.status == 403 else "SHIPPING", "message": str(e)}) from e
        except src.SourceError as e:
            raise HTTPException(503, detail={"code": "SHIPPING_SOURCE", "retryable": True, "message": str(e)}) from e

    # ------------------------------------------------------------------ okuma (5 dk bellek)

    def carriers(fresh: bool = False) -> dict[str, dict[str, Any]]:
        c = cfg()
        return cache.get("carriers", 30 * 60, lambda: src.read_carriers(crm(), c["schema"]), fresh, persist=True)

    def index(fresh: bool = False) -> S.CargoIndex:
        c = cfg()
        raw = cache.get("index", TTL, lambda: src.read_cargo_rows(crm(), c["schema"]), fresh, persist=True)
        return cache.derived("index", raw, lambda: S.CargoIndex(raw, c))

    def since(c: dict[str, Any]) -> date:
        return S.today() - timedelta(days=c["windowDays"])

    def error_rows(c: dict[str, Any], fresh: bool = False) -> list[dict[str, Any]]:
        s = since(c)
        return cache.get(("errors", s), TTL, lambda: src.read_orders(crm(), c["schema"], src.errors_where(s)), fresh,
                         persist=True)

    def untracked_rows(c: dict[str, Any], fresh: bool = False) -> list[dict[str, Any]]:
        s = since(c)
        return cache.get(("untracked", s, c["untrackedStatuses"], c["untrackedExcludeTypes"]), TTL,
                         lambda: src.read_orders(crm(), c["schema"], src.untracked_where(s, c["untrackedStatuses"], c["untrackedExcludeTypes"]),
                                                 sira="ORDER BY s.new_sevktarihi DESC, s.new_name DESC"), fresh, persist=True)

    def boxed_rows(c: dict[str, Any], fresh: bool = False) -> list[dict[str, Any]]:
        return cache.get("boxed", TTL, lambda: src.read_orders(crm(), c["schema"], src.boxed_where(),
                                                                sira="ORDER BY s.new_sipariskutulanditarihi, s.new_name"), fresh,
                         persist=True)

    def shipped(c: dict[str, Any], fresh: bool = False) -> dict[str, int]:
        s, t = since(c), S.today()
        return cache.get(("shipped", s, t, c["shippedStatuses"]), TTL,
                         lambda: src.read_shipped_count(crm(), c["schema"], s, t, c["shippedStatuses"]), fresh, persist=True)

    def logo_firms() -> dict[int, str]:
        return cache.get("firms", 10 * 60, lambda: src.firms_by_year(logo()))

    def errors_view(engine, tenant, c: dict[str, Any], fresh: bool = False) -> list[dict[str, Any]]:
        return S.error_items(error_rows(c, fresh), carriers(), c, S.load_classes(engine, tenant), S.today())

    def ops(engine, tenant, c):
        return S.ops_settings(engine, tenant, c)

    def overview_data(engine, tenant, user: Optional[str], fresh: bool = False) -> dict[str, Any]:
        c = cfg()
        o = ops(engine, tenant, c)
        idx = index(fresh)
        asof = S.today()
        errs = errors_view(engine, tenant, c, fresh)
        unt = S.untracked_items(untracked_rows(c, fresh), carriers(), asof)
        box = S.boxed_items(boxed_rows(c, fresh), carriers(), asof, o["kutuluGun"])
        wait = S.waiting(idx, asof, o["bekleyenGun"], size=0)
        fresh_info = idx.freshness(c, asof)
        end = idx.data_end or asof
        cost_ok = user is None or has(user, F_COST)
        card = S.scorecard(idx, end - timedelta(days=29), end + timedelta(days=1), cost=cost_ok)
        by_class: dict[str, int] = {}
        for e in errs:
            k = e["sinif"] or "Sınıflanmadı"
            by_class[k] = by_class.get(k, 0) + 1
        return {
            "pencereGun": c["windowDays"], "bugun": asof.isoformat(), "sevk": shipped(c, fresh),
            "hata": len(errs), "hataSiniflari": [{"sinif": k, "adet": v} for k, v in sorted(by_class.items(), key=lambda x: -x[1])],
            "takipsiz": len(unt),
            "kutulandi": {k: box[k] for k in ("toplam", "esikUstu", "esikGun", "tarihsiz")},
            "bekleyen": {k: wait[k] for k in ("toplam", "esikUstu", "esikGun", "kovalar")},
            "kargoVeri": fresh_info,
            "son30": {"baslangic": card["baslangic"], "bitis": card["bitis"], "toplam": card["toplam"],
                      "firmalar": [{k: i.get(k) for k in ("firma", "gonderi", "ortancaGun", "iadeOrani", "desiBasi", "tutar")} for i in card["items"]]},
        }

    # ------------------------------------------------------------------ genel

    @app.get(P + "/meta")
    def shipping_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        c = cfg()
        _, matcher_label = src.cargo_matcher()
        return {
            "hataSiniflari": S.ERROR_CLASSES + [S.UNSURE], "taslakTurleri": S.DRAFT_TYPES, "taslakDurumlari": S.DRAFT_STATES,
            "kararTurleri": S.DECISION_TYPES, "kirilimlar": S.GROUPS, "disaAktarma": S.EXPORTS,
            "siparisDurumlari": {str(k): v for k, v in src.ORDER_STATUS.items()},
            "ayarlar": {"pencereGun": c["windowDays"], "sevkDurumlari": list(c["shippedStatuses"]),
                        "takipsizDurumlar": list(c["untrackedStatuses"]), "takipsizHaricTipler": list(c["untrackedExcludeTypes"]),
                        "eskiGun": c["staleDays"], "logoCariEslemesi": {k: v for k, v in c["carrierCodes"].items()},
                        "gunlukSaat": c["dailyAt"], "haftalikSaat": c["weeklyAt"]},
            "is": call(ops, engine, tenant, c), "eslemeYolu": matcher_label, "modelVar": model(1) is not None,
            "me": {"username": user, "display": display, "admin": bool(is_admin(user)),
                   "maliyet": has(user, F_COST), "alici": has(user, F_RECIPIENT), "karar": has(user, F_DECIDE),
                   "taslak": has(user, F_DRAFT), "disaAktar": has(user, F_EXPORT),
                   "firmalar": has(user, PAGE_CARRIERS), "mutabakat": has(user, PAGE_RECONCILE) and has(user, F_COST)},
        }

    @app.get(P + "/overview")
    def shipping_overview(request: Request, yenile: bool = False) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        with src.collect() as runs:
            out = call(overview_data, engine, tenant, user, yenile)
        return PV.bagla(out, lambda: K.for_overview(engine, tenant, out, runs, kdeps()))

    @app.get(P + "/settings")
    def shipping_settings(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(ops, engine, tenant, cfg())

    @app.put(P + "/settings")
    def shipping_settings_save(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_DECIDE, "Kargo eşiklerini değiştirme")
        out, diff = call(S.save_ops_settings, engine, tenant, user, body, cfg())
        if diff:
            audit(engine, user, "update", "shipping_settings", tenant, "Kargo iş eşikleri", diff)
        return out

    # ------------------------------------------------------------------ gönderiler

    @app.get(P + "/shipments")
    def shipping_shipments(request: Request, q: str = "", firma: str = "", durum: str = "hepsi", sayfa: int = 0) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        c = cfg()
        conds = []
        qs = q.strip()
        if qs:
            conds.append(call(src.search_where, qs))
        else:
            conds.append(f"s.new_siparistarihi >= '{since(c).isoformat()}'")
        if firma:
            conds.append(f"s.new_kargofirmasiid = '{call(src.guid, firma)}'")
        if durum == "sevk":
            conds.append(f"CAST(s.statuscode AS int) IN ({src.ints(c['shippedStatuses'])})")
        elif durum in src.STATUS_GROUPS:
            conds.append(f"CAST(s.statuscode AS int) IN ({src.ints(src.STATUS_GROUPS[durum])})")
        elif durum != "hepsi":
            raise HTTPException(400, detail={"code": "SHIPPING", "message": "Durum hepsi, depoda, kutulandi ya da sevk olmalı."})
        page = max(0, int(sayfa))
        with src.collect() as runs:
            rows = call(src.read_orders, crm(), c["schema"], " AND ".join(f"({x})" for x in conds), offset=page * LIST_PAGE, size=LIST_PAGE)
            cars = call(carriers)
        more = len(rows) > LIST_PAGE
        items = [S.order_view(r, cars, S.today()) for r in rows[:LIST_PAGE]]
        res = {"items": items, "sayfa": page, "sayfaBoyu": LIST_PAGE, "devami": more,
                "kapsam": "bütün kayıtlar" if qs else f"son {c['windowDays']} günün siparişleri",
                "firmalar": sorted(({"id": k, "ad": v["ad"]} for k, v in cars.items() if v.get("ad")), key=lambda x: x["ad"])}
        return PV.bagla(res, lambda: K.for_shipments(engine, tenant, res, runs, kdeps()))

    @app.get(P + "/shipments/{sid}")
    def shipping_shipment(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        with src.collect() as runs:
            out = _shipment(engine, tenant, user, sid)
        return PV.bagla(out, lambda: K.for_shipment(engine, tenant, out, runs, kdeps()))

    def _shipment(engine: Any, tenant: str, user: str, sid: str) -> dict[str, Any]:
        c = cfg()
        gid = call(src.guid, sid)
        run = crm()
        rows = call(src.read_orders, run, c["schema"], f"s.new_siparisId = '{gid}'")
        if not rows:
            raise HTTPException(404, detail={"code": "SHIPPING", "message": "Sipariş bulunamadı."})
        asof = S.today()
        order = S.order_view(rows[0], call(carriers), asof)
        tracking = call(src.read_tracking, run, c["schema"], [gid])
        shipments = call(src.read_shipments, run, c["schema"], [gid])
        idx = call(index)
        matcher, matcher_label = src.cargo_matcher()
        matched = matcher(rows[0], tracking, idx)
        cost_ok, rec_ok = has(user, F_COST), has(user, F_RECIPIENT)
        cargo = [S.cargo_public(r, cost_ok) for r in sorted(matched, key=lambda r: r["irs"] or date.min)]
        if rec_ok and cargo:
            personal = call(src.read_cargo_personal, run, c["schema"], [x["id"] for x in cargo])
            for x in cargo:
                x.update(personal.get(x["id"], {}))
        errs = S.integration_failures(rows[0], c["okValues"])
        classes = S.load_classes(engine, tenant)
        for f in errs:
            cls = classes.get(f["mesajHash"])
            f["sinif"] = cls["sinif"] if cls else None
        logo_note, logo_inv = None, {}
        nums = [src.clean(s.get("fatura_no")) for s in shipments if src.clean(s.get("fatura_no"))]
        if nums:
            try:
                firms = logo_firms()
                years = {src.crm_day(s.get("tarih")).year for s in shipments if src.crm_day(s.get("tarih"))} or {asof.year}
                for y in sorted(years):
                    if y in firms:
                        for inv in src.read_logo_invoices_by_no(logo(), firms[y], nums):
                            d = src.logo_day(inv.get("tarih"))
                            logo_inv[src.normal_key(inv.get("no"))] = {"tarih": d.isoformat() if d else None, "tur": int(inv.get("tur") or 0)}
            except src.SourceError as e:
                logo_note = f"Logo okunamadı ({e}); sevkin Logo karşılığı gösterilemiyor."
        ships = [{"id": S._guid_key(s.get("id")), "no": src.clean(s.get("no")), "tarih": src.crm_time(s.get("tarih")),
                  "tur": src.SHIPMENT_KIND.get(int(s.get("tur") or 0)), "faturaNo": src.clean(s.get("fatura_no")),
                  "logoyaAktarildi": bool(s.get("logoda")), "epostaGitti": {1: True, 2: False}.get(int(s.get("eposta") or 0)),
                  "logo": logo_inv.get(src.normal_key(s.get("fatura_no")))} for s in shipments]
        return {"siparis": order, "takip": [{"belgeNo": src.clean(t.get("belge_no")), "takipNo": src.clean(t.get("takip_no")),
                                             "olusturma": src.crm_time(t.get("olusturma"))} for t in tracking],
                "sevkiyatlar": ships, "kargo": cargo, "eslemeYolu": matcher_label, "hatalar": errs,
                "zamanCizelgesi": S.timeline(order, cargo), "taslaklar": S.drafts_for(engine, tenant, gid),
                "kargoVeri": idx.freshness(c, asof), "logoNotu": logo_note,
                "aliciGorunur": rec_ok, "maliyetGorunur": cost_ok}

    # ------------------------------------------------------------------ günlük hat

    @app.get(P + "/errors")
    def shipping_errors(request: Request, entegrasyon: str = "", sinif: str = "", yenile: bool = False) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        c = cfg()
        with src.collect() as runs:
            items = call(errors_view, engine, tenant, c, yenile)
        ent = sorted({f["entegrasyon"] for i in items for f in i["hatalar"]})
        if entegrasyon:
            items = [i for i in items if any(f["entegrasyon"] == entegrasyon for f in i["hatalar"])]
        if sinif:
            items = [i for i in items if (i["sinif"] or "Sınıflanmadı") == sinif]
        out = {"items": items, "toplam": len(items), "pencereGun": c["windowDays"], "entegrasyonlar": ent,
               "not": "Sonuç alanında «başarılı» sayılan değerler yönetim ayarındadır; değer kümesi ölçülecek."}
        return PV.bagla(out, lambda: K.for_errors(engine, tenant, out, runs, kdeps()))

    @app.get(P + "/untracked")
    def shipping_untracked(request: Request, yenile: bool = False) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        c = cfg()
        with src.collect() as runs:
            items = S.untracked_items(call(untracked_rows, c, yenile), call(carriers), S.today())
        out = {"items": items, "toplam": len(items), "pencereGun": c["windowDays"], "durumlar": list(c["untrackedStatuses"]),
               "haricTipler": [src.ORDER_TYPE.get(t, str(t)) for t in c["untrackedExcludeTypes"]]}
        return PV.bagla(out, lambda: K.for_untracked(engine, tenant, out, runs, kdeps()))

    @app.get(P + "/boxed")
    def shipping_boxed(request: Request, gun: Optional[int] = None, yenile: bool = False) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        c = cfg()
        n = gun if gun is not None and gun >= 0 else ops(engine, tenant, c)["kutuluGun"]
        with src.collect() as runs:
            out = S.boxed_items(call(boxed_rows, c, yenile), call(carriers), S.today(), n)
        return PV.bagla(out, lambda: K.for_boxed(engine, tenant, out, runs, kdeps()))

    @app.get(P + "/waiting")
    def shipping_waiting(request: Request, gun: Optional[int] = None, firma: str = "", sehir: str = "", sayfa: int = 0) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        c = cfg()
        n = gun if gun is not None and gun >= 0 else ops(engine, tenant, c)["bekleyenGun"]
        with src.collect() as runs:
            idx = call(index)
        out = S.waiting(idx, S.today(), n, firma=firma, sehir=sehir, cost=has(user, F_COST), page=max(0, sayfa))
        out["kargoVeri"] = idx.freshness(c, S.today())
        out["sehirler"] = sorted({r["sehir"] for r in idx.rows if r["sehir"]})
        out["firmaListesi"] = sorted({r["firma"] for r in idx.rows})
        return PV.bagla(out, lambda: K.for_waiting(engine, tenant, out, runs, kdeps()))

    # ------------------------------------------------------------------ firma karnesi ve karar

    @app.get(P + "/carriers")
    def shipping_carriers(request: Request, baslangic: str = "", bitis: str = "", sehir: str = "", firma: str = "",
                          kirilim: str = "firma") -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        c = cfg()
        with src.collect() as runs:
            idx = call(index)
        start, end = call(S.period, baslangic, bitis, idx.data_end or S.today())
        out = call(S.scorecard, idx, start, end, group=kirilim, sehir=sehir, firma=firma,
                   targets=ops(engine, tenant, c)["bolgeHedef"], cost=has(user, F_COST))
        out["kargoVeri"] = idx.freshness(c, S.today())
        out["maliyetGorunur"] = has(user, F_COST)
        return PV.bagla(out, lambda: K.for_carriers(engine, tenant, out, runs, kdeps()))

    @app.get(P + "/decisions")
    def shipping_decisions(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return {"items": S.list_decisions(engine, tenant), "turler": S.DECISION_TYPES}

    @app.post(P + "/decisions", status_code=201)
    def shipping_decision_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_DECIDE, "Kurye/bölge kararı kaydı")
        out = call(S.create_decision, engine, tenant, user, body)
        audit(engine, user, "create", "shipping_decision", out["id"], f"{out['turAdi']}: {out['karar'][:120]}",
              {"kapsam": out["kapsam"], "gerekce": (out["gerekce"] or "")[:300]})
        return out

    @app.delete(P + "/decisions/{did}")
    def shipping_decision_delete(did: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_DECIDE, "Kurye/bölge kararı kaydı")
        out = call(S.delete_decision, engine, tenant, did)
        audit(engine, user, "delete", "shipping_decision", did, f"{out['turAdi']}: {out['karar'][:120]}")
        return {"ok": True}

    @app.post(P + "/decisions/summary")
    def shipping_decision_summary(body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Seçili kapsamın karnesinden Zeki AI gerekçe özeti (kaydetmez; karar formuna konur)."""
        engine, tenant, user, _ = ctx(request)
        need(user, F_DECIDE, "Kurye/bölge kararı kaydı")
        c = cfg()
        idx = call(index)
        start, end = call(S.period, str(body.get("baslangic") or ""), str(body.get("bitis") or ""), idx.data_end or S.today(), 90)
        card = call(S.scorecard, idx, start, end, group="firma", sehir=str(body.get("sehir") or ""),
                    targets=ops(engine, tenant, c)["bolgeHedef"], cost=has(user, F_COST))
        facts = {"donem": [card["baslangic"], card["bitis"]], "sehir": body.get("sehir") or "hepsi", "firmalar": card["items"]}
        text = S.decision_summary(facts, chatter(0, 400))
        audit(engine, user, "run", "shipping_decision", None, "Zeki AI karar özeti", {"kaynak": "zeki" if text else "yok"})
        return {"metin": text, "kaynak": "zeki" if text else None, "olgular": facts,
                "not": None if text else "Zeki AI özeti şu an alınamadı ya da olgu dışı sayı içerdiği için atıldı; gerekçeyi siz yazın."}

    # ------------------------------------------------------------------ mutabakat

    def reconcile_data(ay: str) -> dict[str, Any]:
        c = cfg()
        start, end = S.month_bounds(ay)
        idx = index()
        notes: list[str] = []
        invoices: list[dict[str, Any]] = []
        logo_ship = crm_ship = None
        try:
            firms = logo_firms()
            f = src.firm_for(firms, start.year)
            codes = [code for cl in c["carrierCodes"].values() for code in cl]
            if codes:
                invoices = src.read_carrier_invoices(logo(), f, codes, start, end)
            else:
                notes.append("Kargo firmalarının Logo carileri eşlenmemiş (yönetim ayarı «Kargo firması → Logo cari kodları»); "
                             "Logo faturası tarafı boş. «Aday cariler» listesinden eşleyin.")
            logo_ship = src.read_logo_shipments(logo(), f, start, end)
            end_logo = src.read_data_end(logo(), firms)
            if end_logo and end_logo < end - timedelta(days=1):
                notes.append(f"Logo verisi {end_logo.strftime('%d.%m.%Y')} tarihinde bitiyor; ayın sonrası Logo'da yok.")
        except src.SourceError as e:
            notes.append(f"Logo okunamadı: {e}")
        try:
            crm_ship = src.read_crm_month_shipments(crm(), c["schema"], start, end)
        except src.SourceError as e:
            notes.append(f"CRM sevkiyatı okunamadı: {e}")
        if idx.data_end and idx.data_end < end - timedelta(days=1):
            notes.append(f"Kargo kayıtları {idx.data_end.strftime('%d.%m.%Y')} tarihinde bitiyor.")
        notes.append("Kargo kaydındaki tutarın KDV dahil mi hariç mi olduğu ölçülecek; Logo iki biçimde verildi.")
        out = S.reconcile(idx, start, end, carrier_codes=c["carrierCodes"], invoices=invoices, logo_shipments=logo_ship,
                          crm_shipments=crm_ship, notes=notes)
        out["kargoVeri"] = idx.freshness(c, S.today())
        return out

    @app.get(P + "/reconcile")
    def shipping_reconcile(request: Request, ay: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_COST, "Kargo maliyeti görme")
        month = ay or (S.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        with src.collect() as runs:
            out = dict(call(lambda: cache.get(("reconcile", month), TTL, lambda: reconcile_data(month))))
        return PV.bagla(out, lambda: K.for_reconcile(engine, tenant, out, runs, kdeps()))

    @app.post(P + "/reconcile/summary")
    def shipping_reconcile_summary(request: Request, ay: str = "") -> dict[str, Any]:
        engine, _, user, _ = ctx(request)
        need(user, F_COST, "Kargo maliyeti görme")
        month = ay or (S.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
        rec = call(lambda: cache.get(("reconcile", month), TTL, lambda: reconcile_data(month)))
        facts = {"ay": rec["ay"], "firmalar": [{k: i[k] for k in ("firma", "gonderi", "crmTutar", "mukerrer", "mukerrerTutar",
                                                                  "tutarOkunamayan", "logoEslendi", "logoKdvHaric", "farkKdvHaric")}
                                              for i in rec["items"]],
                 "sevk": {k: v for k, v in (rec["sevk"] or {}).items() if k != "eslesmeyen"}}
        text = S.decision_summary(facts, chatter(0, 400))
        audit(engine, user, "run", "shipping_reconcile", month, "Zeki AI mutabakat özeti", {"kaynak": "zeki" if text else "yok"})
        return {"metin": text, "not": None if text else "Zeki AI özeti şu an alınamadı ya da olgu dışı sayı içerdiği için atıldı."}

    @app.get(P + "/reconcile/candidates")
    def shipping_reconcile_candidates(request: Request) -> dict[str, Any]:
        """Logo'da kargo firması olabilecek cariler (son 12 ay alınan hizmet faturası; ünvanda ipucu). İnsan onaylar."""
        engine, tenant, user, _ = ctx(request)
        with src.collect() as runs:
            out = _candidates(user)
        return PV.bagla(out, lambda: K.for_candidates(engine, tenant, out, runs, kdeps()))

    def _candidates(user: str) -> dict[str, Any]:
        need(user, F_COST, "Kargo maliyeti görme")
        c = cfg()
        firms = call(logo_firms)
        f = call(src.firm_for, firms, max(firms)) if firms else None
        if not f:
            raise HTTPException(503, detail={"code": "SHIPPING_SOURCE", "message": "Logo dönemleri okunamadı."})
        hints = list(c["carrierHints"]) + [v["ad"] for v in call(carriers).values() if v.get("ad")]
        rows = call(src.read_carrier_candidates, logo(), f, hints, S.today() - timedelta(days=365))
        mapped = {code for cl in c["carrierCodes"].values() for code in cl}
        return {"items": [{"cari": src.clean(r.get("cari")), "unvan": src.clean(r.get("unvan")), "fatura": int(r.get("fatura") or 0),
                           "kdvHaric": S._r(float(r.get("kdv_haric") or 0)), "son": (src.logo_day(r.get("son")) or date.min).isoformat() if src.logo_day(r.get("son")) else None,
                           "eslenmis": src.clean(r.get("cari")) in mapped}
                          for r in sorted(rows, key=lambda r: -float(r.get("kdv_haric") or 0))],
                "ipuclari": sorted(set(hints)), "ayar": "SHIPPING_LOGO_CARRIER_CODES"}

    # ------------------------------------------------------------------ Zeki AI taslak (gönderim insanda)

    @app.post(P + "/drafts", status_code=201)
    def shipping_draft_create(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        tur = str(body.get("tur") or "")
        if tur not in S.DRAFT_TYPES:
            raise HTTPException(400, detail={"code": "SHIPPING", "message": "Taslak türü gecikme, ozur ya da iade olmalı."})
        gid = call(src.guid, body.get("siparisId"))
        c = cfg()
        run = crm()
        rows = call(src.read_orders, run, c["schema"], f"s.new_siparisId = '{gid}'")
        if not rows:
            raise HTTPException(404, detail={"code": "SHIPPING", "message": "Sipariş bulunamadı."})
        order = S.order_view(rows[0], call(carriers), S.today())
        tracking = call(src.read_tracking, run, c["schema"], [gid])
        matcher, _ = src.cargo_matcher()
        cargo = [S.cargo_public(r, False) for r in sorted(matcher(rows[0], tracking, call(index)), key=lambda r: r["irs"] or date.min)]
        text, kaynak = S.draft_text(tur, S.draft_facts(order, cargo), chatter(0, 400))
        out = call(S.create_draft, engine, tenant, user, order, tur, text, kaynak)
        audit(engine, user, "create", "shipping_draft", out["id"], f"{out['turAdi']} — {order['no']}", {"kaynak": kaynak})
        return out

    @app.patch(P + "/drafts/{did}")
    def shipping_draft_update(did: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out, diff = call(S.update_draft, engine, tenant, user, did, body)
        audit(engine, user, "update", "shipping_draft", did, f"{out['turAdi']} — {out['siparisNo']}", diff)
        return out

    @app.delete(P + "/drafts/{did}")
    def shipping_draft_delete(did: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(S.delete_draft, engine, tenant, did)
        audit(engine, user, "delete", "shipping_draft", did, f"{out['turAdi']} — {out['siparisNo']}")
        return {"ok": True}

    # ------------------------------------------------------------------ dışa aktarma

    @app.get(P + "/export/{liste}.xlsx")
    def shipping_export(liste: str, request: Request, gun: Optional[int] = None, firma: str = "", sehir: str = "",
                        baslangic: str = "", bitis: str = "", kirilim: str = "firma", ay: str = "") -> Response:
        engine, tenant, user, _ = ctx(request)
        if liste not in S.EXPORTS:
            raise HTTPException(404, detail={"code": "SHIPPING", "message": "Böyle bir liste yok."})
        c = cfg()
        asof = S.today()
        cost = has(user, F_COST)
        if liste == "hatalar":
            need(user, PAGE_HOME, "Kargo sayfası")
            rows, cols = S.flatten_errors(call(errors_view, engine, tenant, c)), S.ERROR_COLUMNS
            note = f"Son {c['windowDays']} günün siparişleri; takip numarası olmayan ve entegrasyon sonucu başarılı olmayanlar."
        elif liste == "takipsiz":
            need(user, PAGE_HOME, "Kargo sayfası")
            rows, cols = S.untracked_items(call(untracked_rows, c), call(carriers), asof), S.ORDER_COLUMNS
            note = f"Son {c['windowDays']} günde sevk edilmiş ve takip numarası olmayan siparişler."
        elif liste == "kutulandi":
            need(user, PAGE_HOME, "Kargo sayfası")
            n = gun if gun is not None and gun >= 0 else ops(engine, tenant, c)["kutuluGun"]
            rows, cols = S.boxed_items(call(boxed_rows, c), call(carriers), asof, n)["items"], S.ORDER_COLUMNS
            note = f"Kutulanmış, {n}+ gündür sevk edilmemiş siparişler."
        elif liste == "bekleyen":
            need(user, PAGE_HOME, "Kargo sayfası")
            n = gun if gun is not None and gun >= 0 else ops(engine, tenant, c)["bekleyenGun"]
            w = S.waiting(call(index), asof, n, firma=firma, sehir=sehir, cost=cost, size=10 ** 9)
            rows = w["items"]
            cols = S.WAITING_COLUMNS + ([("desi", "Desi"), ("tutar", "Tutar")] if cost else [])
            note = f"Teslim tarihi olmayan, iade olmayan ve {n}+ gündür bekleyen gönderiler."
        elif liste == "firmalar":
            need(user, PAGE_CARRIERS, "Kargo firma karnesi")
            idx = call(index)
            start, end = call(S.period, baslangic, bitis, idx.data_end or asof)
            card = call(S.scorecard, idx, start, end, group=kirilim, sehir=sehir, firma=firma,
                        targets=ops(engine, tenant, c)["bolgeHedef"], cost=cost)
            rows, cols = card["items"], S.scorecard_columns(card["kirilim"], cost)
            note = f"Dönem {card['baslangic']} – {card['bitis']} (kargo irsaliye tarihi); kırılım {card['kirilimAdi']}."
        else:
            need(user, PAGE_RECONCILE, "Kargo mutabakatı")
            need(user, F_COST, "Kargo maliyeti görme")
            month = ay or (asof.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
            rec = call(lambda: cache.get(("reconcile", month), TTL, lambda: reconcile_data(month)))
            rows, cols = rec["items"], S.RECONCILE_COLUMNS
            note = f"Ay {rec['ay']}. " + " ".join(rec["notlar"])
        data = S.xlsx(S.EXPORTS[liste], cols, rows, note)
        audit(engine, user, "run", "shipping_export", liste, S.EXPORTS[liste], {"satir": len(rows)})
        return Response(data, media_type=XLSX, headers={"Content-Disposition": f'attachment; filename="kargo-{liste}-{asof.isoformat()}.xlsx"'})

    # ------------------------------------------------------------------ zamanlayıcı

    @app.post(P + "/run-due")
    def shipping_run_due(request: Request, gorev: str = "") -> dict[str, Any]:
        """15 dakikada bir çağrılır: her çağrıda ağır CRM okumalarının anlık görüntüsünü yeniler; günlük / haftalık / aylık
        işleri zamanı gelince bir kez koşar. `gorev=anlik|gunluk|haftalik|aylik` elle, zamanını beklemeden koşturur."""
        require_caller(request)
        from semantic_layer.runtime.llm_queue import BATCH

        if gorev not in ("", "anlik", "gunluk", "haftalik", "aylik"):
            raise HTTPException(400, detail={"code": "SHIPPING", "message": "Görev anlik, gunluk, haftalik ya da aylik olmalı."})
        engine, tenant, c = deps["engine"](), deps["tenant"](), cfg()
        S.ensure(engine)
        now = datetime.now(S.TZ)
        link = (conf("ALERT_LINK", "") or "").split("/uyarilar")[0]
        out: dict[str, Any] = {}
        # Anlık görüntü (her çağrıda, 15 dk): günlük hat, teslim bekleyen ve karnenin ağır CRM okumaları yeniden okunur ve
        # portal tablosuna yazılır; ekranı ilk açan kişi CRM'i beklemez. SHIPPING_SNAPSHOT_MAX_MIN=0 kapatır.
        refreshed = False
        if gorev in ("", "anlik") and c["snapshotMaxMin"] > 0:
            t0 = time.monotonic()
            try:
                carriers(True)
                overview_data(engine, tenant, None, True)
                refreshed = True
                out["anlik"] = {"ok": True, "ms": int((time.monotonic() - t0) * 1000)}
            except Exception as e:  # noqa: BLE001 — görüntü yenilenemese de günlük/haftalık/aylık işler koşar
                log.warning("kargo: anlık görüntü yenilenemedi: %s", e)
                out["anlik"] = {"hata": str(e)[:300]}
        if gorev in ("gunluk",) or (not gorev and S.due(now, c["dailyAt"], S.meta_get(engine, tenant, "gunluk"))):
            if not refreshed:
                cache.clear()
            try:
                o = overview_data(engine, tenant, None, not refreshed)
                errs = errors_view(engine, tenant, c)
                out["siniflama"] = S.classify_pending(engine, tenant, errs, chooser(BATCH), c)
                mail = "alici_yok"
                if c["dailyTo"]:
                    mail = deps["send_mail"](f"Kargo günlük özeti: {o['hata']} hata, {o['bekleyen']['esikUstu']} bekleyen",
                                             S.daily_text(o, link), c["dailyTo"], None)
                out["gunluk"] = {"hata": o["hata"], "takipsiz": o["takipsiz"], "eposta": mail}
                S.meta_set(engine, tenant, "gunluk", now.date().isoformat())
            except (src.SourceError, S.ShippingError) as e:
                out["gunluk"] = {"hata": str(e)}
        if gorev == "haftalik" or (not gorev and S.due(now, c["weeklyAt"], S.meta_get(engine, tenant, "haftalik"), weekday=0)):
            try:
                idx = index()
                end = idx.data_end or now.date()
                card = S.scorecard(idx, end - timedelta(days=6), end + timedelta(days=1), cost=True,
                                   targets=S.ops_settings(engine, tenant, c)["bolgeHedef"])
                mail = "alici_yok"
                if c["weeklyTo"]:
                    att = [("kargo-firma-karnesi.xlsx", S.xlsx("Kargo firma karnesi", S.scorecard_columns("firma", True), card["items"]), S.XLSX_MIME)]
                    mail = deps["send_mail"]("Haftalık kargo firma karnesi", S.weekly_text(card, idx.freshness(c, now.date()), link), c["weeklyTo"], att)
                out["haftalik"] = {"firma": len(card["items"]), "eposta": mail}
                S.meta_set(engine, tenant, "haftalik", now.date().isoformat())
            except (src.SourceError, S.ShippingError) as e:
                out["haftalik"] = {"hata": str(e)}
        if gorev == "aylik" or (not gorev and S.due(now, c["dailyAt"], S.meta_get(engine, tenant, "aylik"), monthday=3)):
            try:
                month = (now.date().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
                rec = reconcile_data(month)
                mail = "alici_yok"
                if c["monthlyTo"]:
                    att = [(f"kargo-mutabakat-{month}.xlsx", S.xlsx("Kargo mutabakatı", S.RECONCILE_COLUMNS, rec["items"]), S.XLSX_MIME)]
                    mail = deps["send_mail"](f"Kargo mutabakatı {month}", S.monthly_text(rec, link), c["monthlyTo"], att)
                out["aylik"] = {"ay": month, "firma": len(rec["items"]), "eposta": mail}
                S.meta_set(engine, tenant, "aylik", now.date().isoformat())
            except (src.SourceError, S.ShippingError) as e:
                out["aylik"] = {"hata": str(e)}
        return out or {"bekleyen": "zamanı gelen iş yok"}

    return cache
