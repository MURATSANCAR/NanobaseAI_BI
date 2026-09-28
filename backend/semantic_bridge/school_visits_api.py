"""M31 Okul tanıtım ve ziyaret: servis ve uçlar (`/api/v1/schools/*`).

Sayfa kapısı `access.RULES` (`sayfa:okul-tanitim`); işlem yetkileri `FEATURE_RULES`'ta (ziyaret raporu yazma
`ozellik:okul.ziyaret`, bağlam yükleme `ozellik:okul.baglam-yukle`, PDF `ozellik:veri.disa-aktar`). Plan onayı
`ozellik:okul.plan`, bayi eşleştirme onayı açıkça verilen `ozellik:okul.bayi-onay`, bütün ekibin kaydını görmek
`ozellik:okul.herkesinki` ucun içinde denetlenir. Zamanlayıcı (`timas-schools.timer`) yalnız `POST /run-due`'yu çağırır.

Kapsam: `okul.herkesinki` yoksa kişi kendi okullarını görür — CRM'de ziyaret yerinin sahibi, ilin müşteri temsilcisi,
okulda CRM ziyareti sorumlusu ya da portalda ziyaret/plan yazmış olduğu okullar (ayar `SCHOOLS_OWNER_RULES`). Okul
adıyla arama (en az 3 harf) bütün listede yapılır ki yeni okul açılabilsin; başkasının portal ziyaret raporu
görünmez (403).

Dış gönderim yok (kullanıcı kararı 2026-09-28): e-posta/SMS atılmaz; hatırlatma ve onay kuyruğu ekranda.
"""
from __future__ import annotations

import json
import logging
import threading
import time
import uuid
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional

# Modül düzeyinde: `from __future__ import annotations` ile fonksiyon içindeki `Request` sorgu parametresi sanılır (422).
from fastapi import HTTPException, Request
from fastapi.responses import Response

from semantic_bridge import provenance as PV
from semantic_bridge import school_visits as SV
from semantic_bridge import school_visits_kaynak as K
from semantic_bridge import school_visits_sources as src
from semantic_bridge.school_visits import SchoolError, fold

log = logging.getLogger("semantic.school_visits.api")
P = "/api/v1/schools"
DAYS_TR = ["Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar"]


class Service:
    """Okuma (CRM + Logo) + portal kayıtları + hesaplar. Model ve puanlar bellekte; yazma olunca puanlar yeniden."""

    def __init__(self, source: src.Source, settings: Callable[[], dict[str, Any]], llm: Callable[[int], Any]):
        self.source = source
        self.settings = settings
        self.llm = llm
        self._lock = threading.Lock()
        self._model: Optional[tuple[tuple, SV.Model]] = None
        self._scored: Optional[tuple[tuple, dict[str, Any]]] = None

    # -------------------------------------------------------------- model ve puan
    def model(self, engine: Any, tenant: str, fresh: bool = False) -> SV.Model:
        """Okumanın dizini; okuma yenilenince ya da yeni ad eşleşmesi kaydedilince yeniden kurulur."""
        snap = self.source.snapshot(fresh)
        key = (snap["at"], self._matches)
        with self._lock:
            if self._model and self._model[0] == key:
                return self._model[1]
            m = SV.Model(snap, self.settings(), SV.load_matches(engine, tenant))
            self._model = (key, m)
            return m

    _matches = 0

    def invalidate_matches(self) -> None:
        self._matches += 1

    def current(self) -> Optional[SV.Model]:
        return self._model[1] if self._model else None

    def scored(self, engine: Any, tenant: str, fresh: bool = False) -> dict[str, Any]:
        m = self.model(engine, tenant, fresh)
        key = (id(m), SV.VERSION[0])
        with self._lock:
            if self._scored and self._scored[0] == key:
                return self._scored[1]
        ctx = SV.load_context(engine, tenant)
        portal_last = SV.last_visits(engine, tenant)
        portal_owner = SV.portal_owners(engine, tenant)
        links = SV.approved_links(engine, tenant)
        st = m.settings
        refs = SV._ref_students(m)
        now = SV.today()
        fit_memo: dict[frozenset, int] = {}
        out: dict[str, dict[str, Any]] = {}
        owners: dict[str, set[str]] = {}
        rules = set(st["owners"])
        for sid, sc in m.schools.items():
            crm = m.crm_visits(sid)
            crm_last = max((v["day"] for v in crm if v["done"] and v["day"]), default=None)
            last = max((x for x in (crm_last, portal_last.get(sid)) if x), default=None)
            if sc["grades"] not in fit_memo:
                fit_memo[sc["grades"]] = len(m.fitting_books(sc["grades"]))
            endeks = (ctx["ilce_endeks"].get(f"{fold(sc['il'])}|{fold(sc['ilce'])}") or {}).get("endeks")
            s = SV.score_school(sc, weights=st["weights"], ref_students=refs.get(sc["kurumTipiKod"], 0.0), last_visit=last,
                                orders=m.orders_by_school.get(sid, []), fitting=fit_memo[sc["grades"]], endeks=endeks,
                                endeks_range=ctx["endeksRange"], has_dealer=bool(links.get(sid)), now=now)
            s["lastVisit"] = last
            s["dealers"] = [{"code": x["cari_kodu"], "name": x["bayi_adi"]} for x in links.get(sid, [])]
            out[sid] = s
            who: set[str] = set(portal_owner.get(sid, set()))
            if "sahip" in rules and sc["owner"]:
                who.add(sc["owner"])
            if "il" in rules and sc["ilOwner"]:
                who.add(sc["ilOwner"])
            if "ziyaret" in rules:
                who.update(v["owner"] for v in crm if v["owner"])
            owners[sid] = who
        res = {"model": m, "ctx": ctx, "scores": out, "owners": owners, "links": links, "at": time.time()}
        with self._lock:
            self._scored = (key, res)
        return res

    # -------------------------------------------------------------- yardımcılar
    @staticmethod
    def mine(res: dict[str, Any], user: str) -> set[str]:
        return {sid for sid, who in res["owners"].items() if user in who}

    def _row(self, res: dict[str, Any], sid: str, week_conf: dict[str, list]) -> dict[str, Any]:
        sc = res["model"].schools[sid]
        s = res["scores"][sid]
        return {"id": sid, "name": sc["name"], "il": sc["il"], "ilce": sc["ilce"], "kademe": sc["kademe"] or sc["gradesText"],
                "kurumTuru": sc["kurumTuru"], "okulTuru": sc["okulTuru"], "students": sc["students"], "score": s["score"],
                "reason": s["reason"], "lastVisit": s["lastVisit"], "dealers": s["dealers"],
                "calendar": week_conf.get(fold(sc["il"]), [])}

    # -------------------------------------------------------------- liste
    def list(self, engine: Any, tenant: str, user: str, can_all: bool, *, il: str = "", ilce: str = "", kademe: str = "",
             tur: str = "", min_score: Optional[float] = None, q: str = "", kapsam: str = "", sort: str = "puan",
             page: int = 0, fresh: bool = False) -> dict[str, Any]:
        res = self.scored(engine, tenant, fresh)
        m = res["model"]
        qf = fold(q)
        search_all = len(qf) >= 3 and kapsam != "benim"
        if kapsam == "hepsi" and not can_all and not search_all:
            raise SchoolError("Bütün okulları görmek yetkinizde yok; okul adıyla arayın (en az 3 harf).", 403)
        if can_all:
            scope = self.mine(res, user) if kapsam == "benim" else None
        else:
            scope = None if search_all else self.mine(res, user)
        items = []
        for sid, sc in m.schools.items():
            if scope is not None and sid not in scope:
                continue
            if il and fold(sc["il"]) != fold(il):
                continue
            if ilce and fold(sc["ilce"]) != fold(ilce):
                continue
            if kademe and str(sc["kademeKod"] or "") != kademe and fold(sc["kademe"]) != fold(kademe):
                continue
            if tur and str(sc["kurumTuruKod"] or "") != tur:
                continue
            if min_score is not None and res["scores"][sid]["score"] < min_score:
                continue
            if qf and qf not in fold(sc["name"]) and qf not in fold(sc["code"]):
                continue
            items.append(sid)
        sc_ = res["scores"]
        key = {
            "ad": lambda x: (fold(m.schools[x]["name"]),),
            "ogrenci": lambda x: (-(m.schools[x]["students"] or -1), fold(m.schools[x]["name"])),
            "son": lambda x: (sc_[x]["lastVisit"] or "0000", fold(m.schools[x]["name"])),
        }.get(sort, lambda x: (-sc_[x]["score"], fold(m.schools[x]["name"])))
        items.sort(key=key)
        page = max(0, page)
        wk = SV.monday(SV.today())
        week_conf = self._week_conflicts(res["ctx"], wk)
        rows = [self._row(res, sid, week_conf) for sid in items[page * SV.PAGE_SIZE:(page + 1) * SV.PAGE_SIZE]]
        return {"items": rows, "total": len(items), "page": page, "pageSize": SV.PAGE_SIZE,
                "scope": "hepsi" if scope is None else "benim", "mineCount": len(self.mine(res, user)),
                "asOf": m.as_of, "listChanged": m.list_changed, "warnings": m.warnings}

    @staticmethod
    def _week_conflicts(ctx: dict[str, Any], wk: date) -> dict[str, list]:
        out: dict[str, list] = {}
        for e in ctx.get("takvim") or []:
            if e["bitis"] < wk.isoformat() or e["baslangic"] > (wk + timedelta(days=6)).isoformat():
                continue
            key = fold(e.get("il")) if e.get("il") else "*"
            out.setdefault(key, []).append({"from": e["baslangic"], "to": e["bitis"], "kind": e["tur"], "name": e.get("ad")})
        if "*" in out:
            common = out.pop("*")
            return _AllIl(common, out)
        return out

    # -------------------------------------------------------------- okul kartı
    def card(self, engine: Any, tenant: str, user: str, can_all: bool, sid: str, fresh: bool = False) -> dict[str, Any]:
        sid = SV.school_id(sid)
        res = self.scored(engine, tenant, fresh)
        m = res["model"]
        sc = m.schools.get(sid)
        if not sc:
            raise SchoolError("Okul bulunamadı (CRM'de etkin ziyaret yeri değil).", 404)
        s = res["scores"][sid]
        crm = sorted(m.crm_visits(sid), key=lambda v: v["day"] or "", reverse=True)
        portal = [SV.visit_view(r, viewer=user, can_all=can_all) for r in SV.load_visits(engine, tenant, school=sid)]
        hidden_others = 0
        if not can_all:
            hidden_others = sum(1 for v in portal if not v["mine"])
            portal = [v for v in portal if v["mine"]]
        links = [SV.link_view(r, m) for r in SV.load_links(engine, tenant, school=sid)]
        plans = [SV.plan_view(r, None, []) for r in SV.load_plans(engine, tenant) if r["ziyaret_yeri_id"] == sid
                 and (can_all or r["sahip"] == user)]
        now = SV.today()
        conf = SV.conflicts(res["ctx"], now, now + timedelta(days=21), sc["il"])
        cats = []
        with engine.connect() as c:
            for r in c.execute(SV.catalogs_stmt(tenant, sid)).mappings():
                cats.append({"id": r["id"], "by": r["olusturan"], "at": SV._iso(r["olusturma"]),
                             "count": len(json.loads(r["kitaplar_json"] or "[]")), "total": r["uygun_toplam"]})
        orders = sorted(m.orders_by_school.get(sid, []), key=lambda o: o["day"] or "", reverse=True)
        done_linked = sum(1 for v in m.visits.get(sid, []) if v["done"])
        return {
            "school": {k: v for k, v in sc.items() if k != "grades"} | {"grades": sorted(sc["grades"])},
            "score": s["score"], "parts": s["parts"], "reason": s["reason"], "lastVisit": s["lastVisit"],
            "inScope": user in res["owners"].get(sid, set()),
            "crmVisits": crm, "crmDoneLinked": done_linked,
            "crmDoneByName": sum(1 for v in m.visits_by_name.get(sid, []) if v["done"]),
            "portalVisits": portal, "hiddenOthers": hidden_others,
            "orders": orders, "ordersNote": "CRM siparişinde okul alanı yok: firma adı okul adıyla (aynı ilde) eşleşen siparişler.",
            "links": links, "plans": plans, "calendar": conf, "catalogs": cats,
            "fittingBooks": len(m.fitting_books(sc["grades"])), "logoOk": m.logo_ok,
            "source": {"asOf": m.as_of, "changed": sc["changed"], "listChanged": m.list_changed,
                       "label": "CRM ziyaret yerleri listesi"},
            "warnings": m.warnings,
        }

    def advice(self, engine: Any, tenant: str, user: str, can_all: bool, sid: str) -> dict[str, Any]:
        card = self.card(engine, tenant, user, can_all, sid)
        sc = card["school"]
        m = self.model(engine, tenant)
        books = SV.select_catalog(m, m.schools[sc["id"]], {"adet": 5})["items"] if sc["grades"] else []
        facts = {"okul": sc["name"], "ilce": sc["ilce"], "kademe": sc["kademe"] or sc["gradesText"], "ogrenci": sc["students"],
                 "kurum_turu": sc["kurumTuru"], "son_ziyaret": card["lastVisit"],
                 "son_ziyaret_notlari": [v.get("note") for v in card["portalVisits"][:3] if v.get("note")],
                 "siparisler": [{"tur": o["typeLabel"], "gun": o["day"]} for o in card["orders"][:5]],
                 "bagli_bayi": [x["name"] for x in card["links"] if x["state"] == "onayli"],
                 "onerilecek_kitaplar": [b["title"] for b in books],
                 "takvim": [f"{x['name']} {x['from']}–{x['to']}" for x in card["calendar"]]}
        text = SV.ai_advice(self.llm(0), facts)
        if not text:
            first = books[0]["title"] if books else None
            text = (f"{card['reason']}. " + (f"Kademeye uygun ve stokta kitaplardan «{first}» ile başlayabilirsiniz. " if first else "")
                    + ("Bağlı bayi: " + ", ".join(facts["bagli_bayi"]) + "." if facts["bagli_bayi"] else
                       "Bağlı bayi yok; bayi önerilerine bakın."))
            return {"text": text, "ai": False}
        return {"text": text, "ai": True}

    # -------------------------------------------------------------- plan
    def plan(self, engine: Any, tenant: str, user: str, can_all: bool, week: date, owner: Optional[str], everyone: bool,
             fresh: bool = False) -> dict[str, Any]:
        res = self.scored(engine, tenant, fresh)
        m = res["model"]
        who = None if (everyone and can_all) else (owner if (owner and can_all) else user)
        rows = SV.load_plans(engine, tenant, week=week, owner=who)
        visits = SV.load_visits(engine, tenant, owner=who, since=datetime(week.year, week.month, week.day, tzinfo=SV.TZ))
        items = []
        for r in rows:
            sc = m.schools.get(r["ziyaret_yeri_id"]) or {}
            day = r.get("gun")
            conf = SV.conflicts(res["ctx"], day or week, day or (week + timedelta(days=4)), sc.get("il")) if r["durum"] != "iptal" else []
            v = self._realized(r, visits, m)
            pv = SV.plan_view(r, v, conf)
            pv.update({"il": sc.get("il"), "ilce": sc.get("ilce"), "kademe": sc.get("kademe") or sc.get("gradesText"),
                       "students": sc.get("students"), "lastVisit": (res["scores"].get(r["ziyaret_yeri_id"]) or {}).get("lastVisit"),
                       "dealers": (res["scores"].get(r["ziyaret_yeri_id"]) or {}).get("dealers", [])})
            items.append(pv)
        nexts = []
        for r in SV.load_visits(engine, tenant, owner=who):
            if r.get("sonraki_tarih") and r.get("hatirlatildi") is None and r["sonraki_tarih"] <= week + timedelta(days=6):
                sc = m.schools.get(r["hedef_kimlik"]) or {}
                nexts.append({"visitId": r["id"], "school": r["hedef_kimlik"], "schoolName": sc.get("name"), "step": r.get("sonraki_adim"),
                              "day": SV._dstr(r["sonraki_tarih"]), "late": r["sonraki_tarih"] < SV.today(), "owner": r["sahip"]})
        nexts.sort(key=lambda x: x["day"] or "")
        cal = [e for e in res["ctx"].get("takvim") or [] if not (e["bitis"] < week.isoformat() or e["baslangic"] > (week + timedelta(days=6)).isoformat())]
        return {"week": week.isoformat(), "weekEnd": (week + timedelta(days=6)).isoformat(), "term": SV.term_of(week),
                "owner": who, "items": items, "nextSteps": nexts, "calendar": cal,
                "done": sum(1 for x in items if x["realized"]), "planned": sum(1 for x in items if x["state"] != "iptal"),
                "days": [{"day": (week + timedelta(days=i)).isoformat(), "label": DAYS_TR[i]} for i in range(5)]}

    @staticmethod
    def _realized(plan: dict[str, Any], visits: list[dict[str, Any]], m: SV.Model) -> Optional[dict[str, Any]]:
        wk = plan["hafta"] if isinstance(plan["hafta"], date) else date.fromisoformat(str(plan["hafta"])[:10])
        lo, hi = wk.isoformat(), (wk + timedelta(days=6)).isoformat()
        for v in visits:
            if v["hedef_kimlik"] != plan["ziyaret_yeri_id"] or v["sahip"] != plan["sahip"] or v["durum"] != "yapildi":
                continue
            day = SV.local_day(v.get("gerceklesen"))
            if day and lo <= day <= hi:
                return {"source": "portal", "day": day, "visitId": v["id"]}
        for v in m.crm_visits(plan["ziyaret_yeri_id"]):
            if v["done"] and v["owner"] == plan["sahip"] and v["day"] and lo <= v["day"] <= hi:
                return {"source": "crm", "day": v["day"], "visitId": v["id"]}
        return None

    def generate(self, engine: Any, tenant: str, user: str, display: str, can_all: bool, body: dict[str, Any],
                 *, system: bool = False) -> dict[str, Any]:
        """Haftalık ziyaret planı önerisi (K2): kapsamdaki okullar puan sırasıyla; yakında ziyaret edilen, aynı hafta
        zaten planda olan ve rehberlik merkezi (katalog yok) dışarıda; aynı ilçeler aynı güne; tatil/sınav gününe düşen
        okul o haftanın boş gününe kayar, boş gün yoksa çakışma işaretiyle kalır."""
        res = self.scored(engine, tenant)
        m = res["model"]
        st = m.settings
        week = SV.monday(SV.parse_day(body.get("hafta"), "Hafta") or SV.today())
        owner = str(body.get("sahip") or "").strip().lower() or user
        if owner != user and not (can_all or system):
            raise SchoolError("Başkası adına plan kurmak yetkinizde yok.", 403)
        n = src.ival(body.get("adet")) or st["planSize"]
        if n <= 0:
            raise SchoolError("Plandaki okul sayısı en az 1 olmalı.")
        scope = self.mine(res, owner)
        if not scope:
            raise SchoolError("Size bağlı okul bulunamadı: CRM'de ziyaret yeri sahibi, ilin müşteri temsilcisi ya da okulda "
                              "ziyaret sorumlusu olarak görünmüyorsunuz. Okul adıyla arayıp karttan ziyaret ya da plan ekleyin.", 409)
        existing = {r["ziyaret_yeri_id"] for r in SV.load_plans(engine, tenant, week=week, owner=owner) if r["durum"] != "iptal"}
        cut = (SV.today() - timedelta(days=st["revisitDays"])).isoformat()
        il, ilce, kademe = fold(body.get("il")), fold(body.get("ilce")), str(body.get("kademe") or "")
        cands = []
        for sid in scope:
            sc = m.schools.get(sid)
            s = res["scores"].get(sid)
            if not sc or not s or sid in existing or not sc["grades"]:
                continue
            if s["lastVisit"] and s["lastVisit"] >= cut:
                continue
            if il and fold(sc["il"]) != il:
                continue
            if ilce and fold(sc["ilce"]) != ilce:
                continue
            if kademe and str(sc["kademeKod"] or "") != kademe:
                continue
            cands.append(sid)
        cands.sort(key=lambda x: (-res["scores"][x]["score"], fold(m.schools[x]["name"])))
        chosen = cands[:n]
        # aynı ilçe aynı güne: ilçe sırası ilk okulun puanına göre
        order: dict[str, int] = {}
        for sid in chosen:
            order.setdefault(fold(m.schools[sid]["ilce"]), len(order))
        chosen.sort(key=lambda x: (order[fold(m.schools[x]["ilce"])], -res["scores"][x]["score"]))
        per_day = max(1, -(-len(chosen) // 5))
        days = [week + timedelta(days=i) for i in range(5)]
        load = {d: 0 for d in days}
        rows = []
        at = SV.now_utc()
        term = SV.term_of(week)
        i = 0
        for sid in chosen:
            sc = m.schools[sid]
            base = days[min(4, i // per_day)]
            i += 1
            pick = None
            for d in [base] + [x for x in days if x != base]:
                if load[d] < per_day + 1 and not SV.conflicts(res["ctx"], d, d, sc["il"]):
                    pick = d
                    break
            pick = pick or base
            load[pick] += 1
            s = res["scores"][sid]
            rows.append({"id": uuid.uuid4().hex, "tenant_id": tenant, "sahip": owner,
                         "sahip_ad": display if owner == user else (m.users.get(owner) or {}).get("name"),
                         "donem": term, "hafta": week, "gun": pick, "ziyaret_yeri_id": sid, "okul_adi": sc["name"][:300],
                         "puan": s["score"], "gerekce": s["reason"], "model_gerekce": None, "durum": "oneri", "not": None,
                         "onaylayan": None, "onay_zamani": None, "olusturan": "sistem" if system else user, "olusturma": at,
                         "guncelleyen": None, "guncelleme": None})
        SV.insert_plans(engine, rows)
        return {"created": len(rows), "candidates": len(cands), "week": week.isoformat(), "owner": owner,
                "skippedRecent": st["revisitDays"]}

    def patch_plan(self, engine: Any, tenant: str, user: str, can_all: bool, pid: str, body: dict[str, Any]) -> dict[str, Any]:
        pid = SV.rid(pid, "Plan")
        rows = SV.load_plans(engine, tenant, pid=pid)
        if not rows:
            raise SchoolError("Plan bulunamadı.", 404)
        r = rows[0]
        if r["sahip"] != user and not can_all:
            raise SchoolError("Başkasının planını değiştiremezsiniz.", 403)
        vals: dict[str, Any] = {"guncelleyen": user, "guncelleme": SV.now_utc()}
        if "gun" in body:
            d = SV.parse_day(body.get("gun"), "Gün")
            wk = r["hafta"] if isinstance(r["hafta"], date) else date.fromisoformat(str(r["hafta"])[:10])
            if d and not (wk <= d <= wk + timedelta(days=6)):
                raise SchoolError("Gün planın haftası içinde olmalı.")
            vals["gun"] = d
        if "durum" in body:
            st = str(body.get("durum") or "")
            if st not in ("oneri", "iptal"):
                raise SchoolError("Plan yalnız iptal edilir ya da öneriye döner; onay kendi düğmesinden.")
            vals["durum"] = st
            if st == "oneri":
                vals.update(onaylayan=None, onay_zamani=None)
        if "not" in body:
            vals["not"] = SV._text(body.get("not"), 1000, "Not")
        out = SV.update_plan(engine, tenant, pid, vals)
        return SV.plan_view(out, None, [])

    def add_plan(self, engine: Any, tenant: str, user: str, display: str, sid: str, body: dict[str, Any]) -> dict[str, Any]:
        """Karttan tek okulu plana ekleme (öneri olarak)."""
        sid = SV.school_id(sid)
        res = self.scored(engine, tenant)
        sc = res["model"].schools.get(sid)
        if not sc:
            raise SchoolError("Okul bulunamadı.", 404)
        day = SV.parse_day(body.get("gun"), "Gün", required=True)
        week = SV.monday(day)
        if any(r["ziyaret_yeri_id"] == sid and r["durum"] != "iptal" for r in SV.load_plans(engine, tenant, week=week, owner=user)):
            raise SchoolError("Bu okul o hafta zaten planınızda.", 409)
        s = res["scores"][sid]
        row = {"id": uuid.uuid4().hex, "tenant_id": tenant, "sahip": user, "sahip_ad": display, "donem": SV.term_of(week),
               "hafta": week, "gun": day, "ziyaret_yeri_id": sid, "okul_adi": sc["name"][:300], "puan": s["score"],
               "gerekce": s["reason"], "model_gerekce": None, "durum": "oneri", "not": SV._text(body.get("not"), 1000, "Not"),
               "onaylayan": None, "onay_zamani": None, "olusturan": user, "olusturma": SV.now_utc(), "guncelleyen": None,
               "guncelleme": None}
        SV.insert_plans(engine, [row])
        return SV.plan_view(row, None, SV.conflicts(res["ctx"], day, day, sc["il"]))

    def approve_plan(self, engine: Any, tenant: str, user: str, pid: str) -> dict[str, Any]:
        pid = SV.rid(pid, "Plan")
        rows = SV.load_plans(engine, tenant, pid=pid)
        if not rows:
            raise SchoolError("Plan bulunamadı.", 404)
        if rows[0]["durum"] == "iptal":
            raise SchoolError("İptal edilmiş plan onaylanamaz.", 409)
        out = SV.update_plan(engine, tenant, pid, {"durum": "onayli", "onaylayan": user, "onay_zamani": SV.now_utc()})
        return SV.plan_view(out, None, [])

    # -------------------------------------------------------------- bayi
    def dealers(self, engine: Any, tenant: str, sid: str) -> dict[str, Any]:
        sid = SV.school_id(sid)
        res = self.scored(engine, tenant)
        m = res["model"]
        sc = m.schools.get(sid)
        if not sc:
            raise SchoolError("Okul bulunamadı.", 404)
        links = [SV.link_view(r, m) for r in SV.load_links(engine, tenant, school=sid)]
        counts: dict[str, int] = {}
        for rs in res["links"].values():
            for r in rs:
                if r.get("cari_kodu"):
                    counts[r["cari_kodu"].upper()] = counts.get(r["cari_kodu"].upper(), 0) + 1
        cands = SV.dealer_candidates(m, sc, linked_counts=counts, risk=SV.read_risk(engine))
        taken = {(x["code"] or "").upper() for x in links if x["state"] in ("oneri", "onayli")}
        for c in cands:
            c["linked"] = c["code"].upper() in taken
        return {"links": links, "candidates": cands, "logoOk": m.logo_ok, "months": m.settings["dealerMonths"],
                "rule": "Aday: okulun ilindeki bayi ve kitapçılar. Puan: aynı ilçe 40 · bu kademeye uygun kitap satışı 40 "
                        "(adaylar arasında en çok satana göre) · bu okulda (10) ya da ilçede (5) geçmiş ortak ziyaret · "
                        "ağ dengesi 10 (bağlı okul sayısı arttıkça azalır)."}

    def add_dealer(self, engine: Any, tenant: str, user: str, sid: str, code: str, can_approve: bool,
                   kaynak: str = "elle", note: Optional[str] = None) -> dict[str, Any]:
        sid = SV.school_id(sid)
        m = self.model(engine, tenant)
        if sid not in m.schools:
            raise SchoolError("Okul bulunamadı.", 404)
        d = m.dealers.get((code or "").strip().upper())
        if not d:
            raise SchoolError("Bayi bulunamadı (CRM'de etkin bayi ya da kitapçı değil).", 404)
        durum = "onayli" if can_approve else "oneri"
        row = SV.add_link(engine, tenant, user, sid, d, kaynak=kaynak, durum=durum, puan=None,
                          gerekce=note or ("Yönetici elle ekledi." if can_approve else "Temsilci önerdi; yönetici onayı bekliyor."),
                          approver=user if can_approve else None)
        return SV.link_view(row, m)

    def decide(self, engine: Any, tenant: str, user: str, sid: str, link: str, approve: bool, note: Optional[str]) -> dict[str, Any]:
        sid = SV.school_id(sid)
        m = self.model(engine, tenant)
        if link.startswith("c-"):
            # Kaydedilmemiş aday: onayla = öneri olarak açılıp aynı anda onaylanır; ret de kayda geçer.
            d = m.dealers.get(link[2:].upper())
            if not d or sid not in m.schools:
                raise SchoolError("Aday bayi bulunamadı.", 404)
            cands = {c["code"].upper(): c for c in SV.dealer_candidates(m, m.schools[sid], linked_counts={}, risk={})}
            c = cands.get(link[2:].upper())
            row = SV.add_link(engine, tenant, user, sid, d, kaynak="oneri", durum="oneri", puan=(c or {}).get("score"),
                              gerekce="; ".join((c or {}).get("why") or []) or None)
            link = row["id"]
        lid = SV.rid(link, "Eşleşme")
        rows = SV.load_links(engine, tenant, lid=lid)
        if not rows or rows[0]["ziyaret_yeri_id"] != sid:
            raise SchoolError("Eşleşme bulunamadı.", 404)
        return SV.link_view(SV.decide_link(engine, tenant, lid, user, approve, SV._text(note, 500, "Not")), m)

    def queue(self, engine: Any, tenant: str) -> dict[str, Any]:
        m = self.model(engine, tenant)
        items = []
        for r in SV.load_links(engine, tenant, state="oneri"):
            v = SV.link_view(r, m)
            sc = m.schools.get(r["ziyaret_yeri_id"]) or {}
            v.update({"schoolName": sc.get("name"), "schoolIl": sc.get("il"), "schoolIlce": sc.get("ilce"),
                      "kademe": sc.get("kademe") or sc.get("gradesText")})
            items.append(v)
        return {"items": items, "total": len(items)}

    # -------------------------------------------------------------- katalog
    def catalog(self, engine: Any, tenant: str, user: str, sid: str, body: dict[str, Any]) -> dict[str, Any]:
        sid = SV.school_id(sid)
        m = self.model(engine, tenant)
        sc = m.schools.get(sid)
        if not sc:
            raise SchoolError("Okul bulunamadı.", 404)
        sel = SV.select_catalog(m, sc, body)
        if not m.stock:
            sel["warning"] = "Logo stoku okunamadı: stok süzgeci uygulanmadı."
        if body.get("onizleme"):
            return {"id": None, **sel}
        dealer = None
        code = str(body.get("bayi") or "").strip().upper()
        approved = [r for r in SV.load_links(engine, tenant, school=sid, state="onayli")]
        pick = next((r for r in approved if (r.get("cari_kodu") or "").upper() == code), None) if code else (approved[0] if approved else None)
        if pick:
            d = m.dealers.get((pick.get("cari_kodu") or "").upper()) or {}
            dealer = {"name": pick.get("bayi_adi") or d.get("name"), "il": d.get("il"), "ilce": d.get("ilce"), "phone": d.get("phone")}
        row = SV.save_catalog(engine, tenant, user, sc, sel, dealer)
        return {"id": row["id"], **sel, "dealer": dealer}

    def catalog_pdf(self, engine: Any, tenant: str, cid: str, display: str) -> tuple[bytes, str]:
        cat = SV.load_catalog(engine, tenant, SV.rid(cid, "Katalog"))
        m = self.current()
        sc = m.schools.get(cat["ziyaret_yeri_id"]) if m else None
        data = SV.catalog_pdf(cat, sc, display)
        name = "kitap-onerileri-" + (fold(cat.get("okul_adi")).replace(" ", "-")[:60] or "okul") + ".pdf"
        return data, name

    # -------------------------------------------------------------- ziyaret
    def add_visit(self, engine: Any, tenant: str, user: str, display: str, sid: str, body: dict[str, Any],
                  can_approve: bool) -> dict[str, Any]:
        sid = SV.school_id(sid)
        m = self.model(engine, tenant)
        if sid not in m.schools:
            raise SchoolError("Okul bulunamadı.", 404)
        vals = SV.visit_values(body, m, SV.today())
        details = vals["_details"]
        if details.get("plan_id"):
            rows = SV.load_plans(engine, tenant, pid=SV.rid(details["plan_id"], "Plan"))
            if not rows or rows[0]["ziyaret_yeri_id"] != sid:
                raise SchoolError("Plan bu okula ait değil.")
        vid = SV.add_visit(engine, tenant, user, display, sid, vals)
        link = None
        if details.get("bayi_yonlendirildi") and details.get("yonlendirilen_bayi"):
            try:
                link = self.add_dealer(engine, tenant, user, sid, details["yonlendirilen_bayi"], can_approve,
                                       note=f"Ziyaret raporunda bayiye yönlendirildi ({display}).")
            except SchoolError as e:
                log.info("school_visits: yönlendirilen bayi bağlanamadı: %s", e)
        out = SV.visit_view(SV.load_visits(engine, tenant, vid=vid)[0], viewer=user, can_all=True)
        out["link"] = link
        return out

    def visits(self, engine: Any, tenant: str, user: str, can_all: bool, sid: str) -> dict[str, Any]:
        sid = SV.school_id(sid)
        rows = [SV.visit_view(r, viewer=user, can_all=can_all) for r in SV.load_visits(engine, tenant, school=sid)]
        if not can_all:
            rows = [v for v in rows if v["mine"]]
        m = self.model(engine, tenant)
        return {"portal": rows, "crm": sorted(m.crm_visits(sid), key=lambda v: v["day"] or "", reverse=True)}

    def visit(self, engine: Any, tenant: str, user: str, can_all: bool, vid: str) -> dict[str, Any]:
        rows = SV.load_visits(engine, tenant, vid=SV.rid(vid, "Ziyaret"))
        if not rows:
            raise SchoolError("Ziyaret bulunamadı.", 404)
        if rows[0]["sahip"] != user and not can_all:
            raise SchoolError("Başka bir temsilcinin ziyaret raporunu göremezsiniz.", 403)
        return SV.visit_view(rows[0], viewer=user, can_all=can_all)

    def next_done(self, engine: Any, tenant: str, user: str, vid: str) -> dict[str, Any]:
        rows = SV.load_visits(engine, tenant, vid=SV.rid(vid, "Ziyaret"))
        if not rows:
            raise SchoolError("Ziyaret bulunamadı.", 404)
        if rows[0]["sahip"] != user:
            raise SchoolError("Yalnız ziyareti yazan kişi sıradaki adımı kapatabilir.", 403)
        SV.mark_reminded(engine, [rows[0]["id"]])
        SV.bump()
        return {"ok": True}

    def suggest_fields(self, engine: Any, tenant: str, sid: str, note: str) -> dict[str, Any]:
        sid = SV.school_id(sid)
        m = self.model(engine, tenant)
        sc = m.schools.get(sid)
        if not sc:
            raise SchoolError("Okul bulunamadı.", 404)
        text = SV._text(note, 2000, "Not")
        if not text:
            raise SchoolError("Önce notu yazın.")
        books = m.fitting_books(sc["grades"], min_stock=0) or m.books
        st = m.settings
        out = SV.ai_note_fields(self.llm(0), text, books, st["suggestMinP"], st["suggestMinMargin"])
        if out is None:
            return {"fields": {}, "ai": False, "message": "Zeki AI şu an cevap vermiyor; alanları elle doldurun."}
        return {"fields": out, "ai": True}

    # -------------------------------------------------------------- bağlam
    def upload(self, engine: Any, tenant: str, user: str, body: dict[str, Any]) -> dict[str, Any]:
        tur = str(body.get("tur") or "")
        if tur not in SV.CONTEXT_KINDS:
            raise SchoolError("Yükleme türü «ilce_endeks» ya da «takvim» olmalı.")
        source = SV._text(body.get("kaynak"), 300, "Kaynak")
        if not source:
            raise SchoolError("Verinin kaynağını yazın (ör. «Sanayi ve Teknoloji Bakanlığı SEGE 2022»).")
        day = SV.parse_day(body.get("kaynakTarihi"), "Kaynak tarihi")
        rows = SV.read_table(body)
        m = self.model(engine, tenant)
        parsed = SV.parse_context(tur, rows, m.districts)
        if not parsed["items"]:
            raise SchoolError("Dosyada okunabilir satır yok. Beklenen başlıklar: "
                              + ("il; ilce; endeks" if tur == "ilce_endeks" else "baslangic; bitis; tur; ad; il"))
        up = SV.save_context(engine, tenant, user, tur, parsed["items"], source, day)
        return {"upload": up, "kind": tur, "read": len(rows), "saved": len(parsed["items"]), "problems": parsed["bad"]}

    # -------------------------------------------------------------- dönem raporu
    def term_report(self, engine: Any, tenant: str, user: str, can_all: bool, term: str, il: str = "",
                    owner: str = "") -> dict[str, Any]:
        term = term or SV.term_of(SV.today())
        a, b = SV.term_range(term)
        res = self.scored(engine, tenant)
        m = res["model"]
        who = (owner.strip().lower() or None) if can_all else user
        fil = fold(il)

        def in_il(sid: str) -> bool:
            return not fil or fold((m.schools.get(sid) or {}).get("il")) == fil

        plans = [r for r in SV.load_plans(engine, tenant, since=a, until=b, owner=who) if r["durum"] != "iptal" and in_il(r["ziyaret_yeri_id"])]
        pvis = [r for r in SV.load_visits(engine, tenant, owner=who) if r["durum"] == "yapildi" and in_il(r["hedef_kimlik"])]
        pvis_in = []
        for r in pvis:
            ld = SV.local_day(r.get("gerceklesen"))
            d = date.fromisoformat(ld) if ld else None
            if d and a <= d <= b:
                pvis_in.append((r, d))
        crm_in = []
        for sid, vs in list(m.visits.items()) + list(m.visits_by_name.items()):
            if not in_il(sid):
                continue
            for v in vs:
                if v["done"] and v["day"] and a.isoformat() <= v["day"] <= b.isoformat() and (who is None or v["owner"] == who):
                    crm_in.append((sid, v))
        realized = sum(1 for r in plans if self._realized(r, [x for x, _ in pvis_in], m))
        visited: dict[str, str] = {}
        for r, d in pvis_in:
            visited[r["hedef_kimlik"]] = min(visited.get(r["hedef_kimlik"], "9999"), d.isoformat())
        for sid, v in crm_in:
            visited[sid] = min(visited.get(sid, "9999"), v["day"])
        # siparişler: dönemde açılan (CreatedOn), tip başına — okul/temsilci ayrımı CRM'de yok, bütün okul siparişleri
        orders = [o for o in m.orders if o["created"] and a.isoformat() <= o["created"] <= b.isoformat()
                  and (not fil or not o["ilId"] or fold(self._il_name(m, o["ilId"])) == fil)]
        by_type = {t: {"type": t, "label": lbl, "count": 0, "amount": 0.0} for t, lbl in src.ORDER_TYPES.items()}
        for o in orders:
            if o["type"] in by_type:
                by_type[o["type"]]["count"] += 1
                by_type[o["type"]]["amount"] += o["amount"] or 0.0
        sample_to_sale = 0
        sampled = 0
        for sid, os_ in m.orders_by_school.items():
            if not in_il(sid):
                continue
            inr = [o for o in os_ if o["created"] and a.isoformat() <= o["created"] <= b.isoformat()]
            first_sample = min((o["created"] for o in inr if o["type"] in (10, 11)), default=None)
            if first_sample:
                sampled += 1
                if any(o["type"] == 13 and o["created"] >= first_sample for o in inr):
                    sample_to_sale += 1
        # bayi dönüşümü: ziyaret edilen okulların onaylı bayisi; ziyaret ayından sonraki k ay vs önceki k ay
        k = m.settings["conversionMonths"]
        conv = {"dealers": 0, "up": 0, "down": 0, "flat": 0, "before": 0.0, "after": 0.0, "months": k, "pending": 0}
        seen: set[str] = set()
        cur_ym = SV.today().year * 100 + SV.today().month
        for sid, first in visited.items():
            for r in res["links"].get(sid, []):
                code = (r.get("cari_kodu") or "").upper()
                if not code or code in seen:
                    continue
                seen.add(code)
                d0 = date.fromisoformat(first)
                after_m = [_ym_add(d0, i) for i in range(1, k + 1)]
                before_m = [_ym_add(d0, -i) for i in range(1, k + 1)]
                if after_m[-1] >= cur_ym:
                    conv["pending"] += 1
                    continue
                months = m.dealer_months.get(code) or {}
                bq = sum((months.get(x) or {}).get("qty", 0.0) for x in before_m)
                aq = sum((months.get(x) or {}).get("qty", 0.0) for x in after_m)
                conv["dealers"] += 1
                conv["before"] += bq
                conv["after"] += aq
                conv["up" if aq > bq else ("down" if aq < bq else "flat")] += 1
        # il bazında penetrasyon
        by_il: dict[str, dict[str, Any]] = {}
        for sid, sc in m.schools.items():
            if not in_il(sid):
                continue
            key = sc["il"] or "İli boş"
            row = by_il.setdefault(key, {"il": key, "schools": 0, "visited": 0})
            row["schools"] += 1
            if sid in visited:
                row["visited"] += 1
        il_rows = sorted(by_il.values(), key=lambda x: (-x["visited"], -x["schools"], fold(x["il"])))
        for r in il_rows:
            r["rate"] = round(r["visited"] / r["schools"], 4) if r["schools"] else None
        by_owner: dict[str, dict[str, Any]] = {}
        for r in plans:
            o = by_owner.setdefault(r["sahip"], {"owner": r["sahip"], "name": r.get("sahip_ad") or r["sahip"], "planned": 0,
                                                 "realized": 0, "visits": 0})
            o["planned"] += 1
            if self._realized(r, [x for x, _ in pvis_in], m):
                o["realized"] += 1
        for r, _ in pvis_in:
            o = by_owner.setdefault(r["sahip"], {"owner": r["sahip"], "name": r.get("sahip_ad") or r["sahip"], "planned": 0,
                                                 "realized": 0, "visits": 0})
            o["visits"] += 1
        return {"term": term, "from": a.isoformat(), "to": b.isoformat(), "owner": who, "il": il or None,
                "plans": {"planned": len(plans), "approved": sum(1 for r in plans if r["durum"] == "onayli"),
                          "realized": realized, "rate": round(realized / len(plans), 4) if plans else None},
                "visits": {"portal": len(pvis_in), "crm": len(crm_in), "schools": len(visited)},
                "orders": {"items": list(by_type.values()), "total": len(orders),
                           "note": "CRM'de dönemde açılan okul örneği / öğretmen örneği / okul satışı siparişleri (bütün okullar; "
                                   "siparişte temsilci ve okul alanı yok)."},
                "samples": {"schools": sampled, "converted": sample_to_sale,
                            "note": "Firma adı okul adıyla eşleşen siparişlerde: dönemde örnek giden okulların kaçına sonra okul satışı açıldı."},
                "conversion": conv | {"note": f"Ziyaret edilen okulların onaylı bayileri: ilk ziyaret ayından önceki {k} ay ile sonraki {k} ayın "
                                               "faturalı net satış adedi (bütün kitaplar). Süresi dolmayan ziyaretler «bekliyor»."},
                "byIl": il_rows, "byOwner": sorted(by_owner.values(), key=lambda x: -x["planned"]),
                "asOf": m.as_of, "warnings": m.warnings}

    @staticmethod
    def _il_name(m: SV.Model, il_id: Optional[str]) -> Optional[str]:
        for sid in m.by_il.get(il_id or "", [])[:1]:
            return m.schools[sid]["il"]
        return None

    # -------------------------------------------------------------- zamanlayıcı
    def run_due(self, engine: Any, tenant: str, kind: str = "nightly", budget: Optional[int] = None) -> dict[str, Any]:
        t0 = time.monotonic()
        out: dict[str, Any] = {"kind": kind}
        if kind == "weekly":
            res = self.scored(engine, tenant, fresh=True)
            week = SV.monday(SV.today())
            since = SV.now_utc() - timedelta(days=180)
            active = {r["sahip"] for r in SV.load_visits(engine, tenant, since=since)}
            active |= {r["sahip"] for r in SV.load_plans(engine, tenant, since=SV.today() - timedelta(days=56))}
            made, skipped = 0, []
            for who in sorted(active):
                if SV.load_plans(engine, tenant, week=week, owner=who):
                    continue
                try:
                    r = self.generate(engine, tenant, who, (res["model"].users.get(who) or {}).get("name") or who, True,
                                      {"hafta": week.isoformat(), "sahip": who}, system=True)
                    made += r["created"]
                except SchoolError as e:
                    skipped.append({"owner": who, "reason": str(e)})
            out.update(week=week.isoformat(), owners=len(active), created=made, skipped=skipped)
            out["ms"] = int((time.monotonic() - t0) * 1000)
            return out
        m = self.model(engine, tenant, fresh=True)
        out["schools"] = len(m.schools)
        out["history"] = SV.sync_history_links(engine, tenant, m)
        out["profiles"] = SV.write_profiles(engine, tenant, m)
        # Belirsiz ad eşleşmesi: CRM etkinliğindeki serbest okul metni, aynı ildeki aday okullar + «Hiçbiri» arasından
        # kapalı küme seçimle (QueuedLlm.choose) eşlenir; otomatik kabul eşiği (p, marj) ayarda. Karar kalıcıdır
        # (evet / hayır / belirsiz; yeniden sorulmaz). Bütçe gece başına; kalan sonraki geceye (sonuçta sayısı yazılır).
        llm = self.llm(2)
        st = m.settings
        left = st["matchBudget"] if budget is None else budget
        asked = matched = unsure = 0
        pending = 0
        for key, u in m.unmatched_names.items():
            cands = m.candidates_for(u["ilId"], u["text"])
            if not cands:
                continue
            if left <= 0:
                pending += 1
                continue
            r = SV.ai_pick_school(llm, u["text"], [m.schools[sid] for sid, _ in cands], st["autoMinP"], st["autoMinMargin"])
            if not r["available"]:
                pending += 1
                continue
            left -= 1
            asked += 1
            if r["school"] is None:
                SV.save_match(engine, tenant, key, None, "model", "belirsiz", r.get("probability"))
                unsure += 1
            else:
                SV.save_match(engine, tenant, key, r["school"] or None, "model", None, r.get("probability"))
                matched += int(bool(r["school"]))
        if asked:
            self.invalidate_matches()
        out["names"] = {"unmatched": len(m.unmatched_names), "asked": asked, "matched": matched, "unsure": unsure,
                        "pending": pending}
        res = self.scored(engine, tenant, fresh=False)
        term = SV.term_of(SV.today())
        out["priority"] = SV.write_priority(engine, tenant, term, res["scores"], res["owners"])
        # Plandaki (bu ve gelecek hafta) bağlı bayisi olmayan okullar için en iyi aday öneri olarak kuyruğa.
        week = SV.monday(SV.today())
        plans = [r for w in (week, week + timedelta(days=7)) for r in SV.load_plans(engine, tenant, week=w) if r["durum"] != "iptal"]
        pending_links = {r["ziyaret_yeri_id"] for r in SV.load_links(engine, tenant, state="oneri")}
        counts: dict[str, int] = {}
        for rs in res["links"].values():
            for r in rs:
                if r.get("cari_kodu"):
                    counts[r["cari_kodu"].upper()] = counts.get(r["cari_kodu"].upper(), 0) + 1
        risk = SV.read_risk(engine)
        proposed = 0
        for sid in {r["ziyaret_yeri_id"] for r in plans}:
            if res["links"].get(sid) or sid in pending_links or sid not in res["model"].schools:
                continue
            cands = SV.dealer_candidates(res["model"], res["model"].schools[sid], linked_counts=counts, risk=risk)
            if not cands:
                continue
            # Kuralın ilk beş adayı arasından Zeki AI seçer (onaya gider); emin değilse kuralın birincisi önerilir.
            c = cands[0]
            note = "Kuralın birinci adayı."
            if len(cands) > 1 and left > 0:
                pick = SV.ai_pick_dealer(llm, res["model"].schools[sid], cands[:5], st["suggestMinP"], st["suggestMinMargin"])
                if pick["available"]:
                    left -= 1
                if pick.get("code"):
                    c = next(x for x in cands if x["code"] == pick["code"])
                    note = f"Zeki AI seçimi (olasılık %{round((pick.get('probability') or 0) * 100)})."
            d = res["model"].dealers[c["code"].upper()]
            why = note + " " + "; ".join(c["why"]) + (f" Uyarı: {c['warning']}" if c["warning"] else "")
            SV.add_link(engine, tenant, "sistem", sid, d, kaynak="oneri", durum="oneri", puan=c["score"], gerekce=why)
            proposed += 1
        out["dealerSuggestions"] = proposed
        # Plan satırlarına Zeki AI gerekçe cümlesi (yalnız eksik olanlara; bütçe aynı).
        wrote = 0
        for r in plans:
            if r.get("model_gerekce") or left <= 0 or llm is None:
                continue
            sc = res["model"].schools.get(r["ziyaret_yeri_id"])
            s = res["scores"].get(r["ziyaret_yeri_id"])
            if not sc or not s:
                continue
            left -= 1
            text = SV.ai_reason(llm, sc, s)
            if text:
                SV.update_plan(engine, tenant, r["id"], {"model_gerekce": text})
                wrote += 1
        out["aiReasons"] = wrote
        out["warnings"] = m.warnings
        out["ms"] = int((time.monotonic() - t0) * 1000)
        return out


class _AllIl(dict):
    """Bütün illere uyan takvim satırları + il'e özel olanlar: `get(il)` ikisini birleştirir."""

    def __init__(self, common: list, by: dict[str, list]):
        super().__init__(by)
        self.common = common

    def get(self, key, default=None):  # noqa: D401
        return self.common + (super().get(key) or [])


def _ym_add(d: date, months: int) -> int:
    y, mth = d.year, d.month + months
    while mth > 12:
        y, mth = y + 1, mth - 12
    while mth < 1:
        y, mth = y - 1, mth + 12
    return y * 100 + mth


# ------------------------------------------------------------------------------------------ uçlar


def register(app: Any, deps: dict[str, Any]) -> Service:
    """app.py'de bağlanır. `deps`:
    auth(request) → (engine, tenant, user, display) · can(user, key) → bool · is_admin(user) → bool ·
    audit(engine, user, action, kind, id, title, detail) · conf(key, default) → str · fresh() → bool ·
    crm_connect() / logo_connect() → salt okunur bağlantı · llm(priority) → LLM kapısı istemcisi ya da None ·
    system() → (engine, tenant) · require_caller(request) (zamanlayıcı jetonu)."""
    auth, can, is_admin, audit, conf, fresh = (deps[k] for k in ("auth", "can", "is_admin", "audit", "conf", "fresh"))
    settings = lambda: SV.settings_from(conf)  # noqa: E731
    source = src.Source(deps["crm_connect"], deps["logo_connect"], lambda: conf("CRM_SCHEMA"), settings)
    svc = Service(source, settings, deps.get("llm") or (lambda _p: None))

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        engine, tenant, user, display = auth(request)
        SV.ensure(engine)
        return engine, tenant, user, display

    def allowed(user: str, key: str) -> bool:
        return bool(is_admin(user) or can(user, key))

    def need(user: str, key: str, what: str) -> None:
        if not allowed(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except SchoolError as e:
            code = "FORBIDDEN" if e.status == 403 else "SCHOOLS"
            raise HTTPException(status_code=e.status, detail={"code": code, "message": str(e)}) from e
        except src.SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "DATA_SOURCE_UNAVAILABLE", "message": str(e)}) from e
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001 — kaynak düştüyse kişiye düz cümle, ayrıntı günlükte
            log.exception("school_visits: istek başarısız")
            state = str(getattr(e, "args", [""])[0])
            if state in ("08S01", "08001", "HYT00", "HYT01") or "timeout" in str(e).lower():
                raise HTTPException(status_code=503, detail={"code": "DATA_SOURCE_UNAVAILABLE", "retryable": True,
                                    "message": "CRM ya da Logo şu anda yanıt vermiyor; birazdan tekrar deneyin."}) from e
            raise HTTPException(status_code=502, detail={"code": "SCHOOLS", "message": "Okul kayıtları okunamadı."}) from e

    def can_all(user: str) -> bool:
        return allowed(user, "ozellik:okul.herkesinki")

    # ---- sabit yollar önce (/{okul} ile karışmasın)

    @app.get(f"{P}/meta")
    def schools_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        st = settings()
        ils: list[str] = []
        status: dict[str, Any] = {}
        try:
            model = svc.model(engine, tenant)
            if model is not None:
                ils = sorted({sc["il"] for sc in model.schools.values() if sc["il"]}, key=fold)
                status = {"asOf": model.as_of, "listChanged": model.list_changed, "logoOk": model.logo_ok,
                          "warnings": model.warnings, "schools": len(model.schools)}
        except Exception as e:  # noqa: BLE001
            log.info("schools meta: il listesi okunamadı: %s", e)
        uploads = SV.load_context(engine, tenant)["uploads"]
        out = {"weights": [{"key": k, "label": SV.WEIGHT_LABELS[k], "max": v} for k, v in st["weights"].items()],
                "roles": [{"key": k, "label": v} for k, v in SV.ROLES.items()],
                "interest": [{"key": k, "label": v} for k, v in SV.INTEREST.items()],
                "kademeler": [{"key": str(k), "label": v} for k, v in src.KADEME.items()],
                "kurumTurleri": [{"key": str(k), "label": v} for k, v in src.KURUM_TURU.items()],
                "contextKinds": [{"key": k, "label": v} for k, v in SV.CONTEXT_KINDS.items()],
                "ils": ils, "status": status, "uploads": list(uploads.values()),
                "settings": {k: st[k] for k in ("planSize", "catalogSize", "revisitDays", "dealerMonths", "conversionMonths",
                                                "historyFrom")},
                "term": SV.term_of(SV.today()), "today": SV.today().isoformat(),
                "me": {"username": user, "display": display, "admin": bool(is_admin(user)), "all": can_all(user),
                       "canVisit": allowed(user, "ozellik:okul.ziyaret"), "canPlan": allowed(user, "ozellik:okul.plan"),
                       "canDealer": allowed(user, "ozellik:okul.bayi-onay"),
                       "canUpload": allowed(user, "ozellik:okul.baglam-yukle"),
                       "canExport": allowed(user, "ozellik:veri.disa-aktar")}}
        return PV.bagla(out, lambda: K.for_meta(engine, tenant, svc.current(), out))

    @app.get(f"{P}/plan")
    def schools_plan(request: Request, hafta: str = "", sahip: str = "", hepsi: int = 0) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        week = SV.monday(call(SV.parse_day, hafta, "Hafta") or SV.today())
        out = call(svc.plan, engine, tenant, user, can_all(user), week, sahip.strip().lower() or None, bool(hepsi), fresh())
        return PV.bagla(out, lambda: K.for_plan(engine, tenant, svc.current(), week, out["owner"], out))

    @app.post(f"{P}/plan/generate", status_code=201)
    def schools_plan_generate(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        out = call(svc.generate, engine, tenant, user, display, can_all(user), body)
        audit(engine, user, "create", "school_plan", None, f"Haftalık plan önerisi ({out['week']})",
              {"owner": out["owner"], "created": out["created"]})
        return out

    @app.patch(f"{P}/plan/{{pid}}")
    def schools_plan_patch(pid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(svc.patch_plan, engine, tenant, user, can_all(user), pid, body)
        audit(engine, user, "update", "school_plan", out["id"], out["schoolName"], {k: body.get(k) for k in ("gun", "durum", "not") if k in body})
        return out

    @app.post(f"{P}/plan/{{pid}}/approve")
    def schools_plan_approve(pid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, "ozellik:okul.plan", "Plan onayı")
        out = call(svc.approve_plan, engine, tenant, user, pid)
        audit(engine, user, "approve", "school_plan", out["id"], out["schoolName"], {"week": out["week"], "owner": out["owner"]})
        return out

    @app.get(f"{P}/dealer-queue")
    def schools_dealer_queue(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        out = call(svc.queue, engine, tenant)
        return PV.bagla(out, lambda: K.for_queue(engine, tenant, svc.current(), out))

    @app.get(f"{P}/catalogs/{{cid}}.pdf")
    def schools_catalog_pdf(cid: str, request: Request) -> Response:
        engine, tenant, user, display = ctx(request)
        data, name = call(svc.catalog_pdf, engine, tenant, cid, display)
        audit(engine, user, "run", "school_catalog", cid, "Katalog PDF", None)
        return Response(content=data, media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @app.post(f"{P}/context/upload", status_code=201)
    def schools_context_upload(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(svc.upload, engine, tenant, user, body)
        audit(engine, user, "create", "school_context", out["upload"], SV.CONTEXT_KINDS[out["kind"]],
              {"read": out["read"], "saved": out["saved"], "problems": len(out["problems"]), "source": body.get("kaynak")})
        return out

    @app.get(f"{P}/context")
    def schools_context(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        c = SV.load_context(engine, tenant)
        out = {"uploads": list(c["uploads"].values()), "calendar": c["takvim"],
               "districts": sorted(c["ilce_endeks"].values(), key=lambda x: (fold(x.get("il")), fold(x.get("ilce")))),
               "range": c["endeksRange"]}
        return PV.bagla(out, lambda: K.for_context(engine, tenant, svc.current(), out))

    @app.get(f"{P}/report/term")
    def schools_term(request: Request, donem: str = "", il: str = "", sahip: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(svc.term_report, engine, tenant, user, can_all(user), donem, il, sahip)
        a, b = SV.term_range(out["term"])
        return PV.bagla(out, lambda: K.for_term(engine, tenant, svc.current(), out, a, b, out["owner"]))

    @app.post(f"{P}/run-due")
    def schools_run_due(request: Request, kind: str = "nightly", budget: Optional[int] = None) -> dict[str, Any]:
        """Zamanlayıcı: gece 03:30 (`nightly`) ve pazartesi 07:30 (`weekly`)."""
        deps["require_caller"](request)
        engine, tenant = deps["system"]()
        SV.ensure(engine)
        if kind not in ("nightly", "weekly"):
            raise HTTPException(status_code=400, detail={"code": "SCHOOLS", "message": "kind nightly ya da weekly olmalı."})
        out = call(svc.run_due, engine, tenant, kind, budget)
        audit(engine, "sistem", "run", "school_run_due", None, f"Okul tanıtım zamanlı iş ({kind})",
              {k: v for k, v in out.items() if k != "warnings"})
        return out

    @app.get(f"{P}/visits/{{vid}}")
    def schools_visit(vid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(svc.visit, engine, tenant, user, can_all(user), vid)
        return PV.bagla(out, lambda: K.for_visit(engine, tenant, out["id"], out))

    @app.post(f"{P}/visits/{{vid}}/next-done")
    def schools_visit_next_done(vid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(svc.next_done, engine, tenant, user, vid)
        audit(engine, user, "update", "saha_ziyaret", vid, "Sıradaki adım tamam", None)
        return out

    # ---- liste ve okul

    @app.get(P)
    def schools_list(request: Request, il: str = "", ilce: str = "", kademe: str = "", tur: str = "", oncelik: str = "",
                     q: str = "", kapsam: str = "", sirala: str = "puan", page: int = 0) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        ms = src.num(oncelik) if oncelik else None
        out = call(svc.list, engine, tenant, user, can_all(user), il=il, ilce=ilce, kademe=kademe, tur=tur, min_score=ms,
                   q=q, kapsam=kapsam, sort=sirala, page=page, fresh=fresh())
        return PV.bagla(out, lambda: K.for_list(engine, tenant, svc.current(), out))

    @app.get(f"{P}/{{sid}}")
    def schools_card(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(svc.card, engine, tenant, user, can_all(user), sid, fresh())
        return PV.bagla(out, lambda: K.for_card(engine, tenant, svc.current(), out["school"]["id"], out))

    @app.post(f"{P}/{{sid}}/advice")
    def schools_advice(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return call(svc.advice, engine, tenant, user, can_all(user), sid)

    @app.post(f"{P}/{{sid}}/plan", status_code=201)
    def schools_add_plan(sid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        out = call(svc.add_plan, engine, tenant, user, display, sid, body)
        audit(engine, user, "create", "school_plan", out["id"], out["schoolName"], {"day": out["day"]})
        return out

    @app.post(f"{P}/{{sid}}/catalog", status_code=201)
    def schools_catalog(sid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(svc.catalog, engine, tenant, user, sid, body)
        if out.get("id"):
            audit(engine, user, "create", "school_catalog", out["id"], f"Katalog ({len(out['items'])} kitap)",
                  {"school": sid, "grades": out["grades"], "priceCap": out["priceCap"], "total": out["total"]})
        return PV.bagla(out, lambda: K.for_catalog(engine, tenant, svc.current(), out))

    @app.get(f"{P}/{{sid}}/dealers")
    def schools_dealers(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        out = call(svc.dealers, engine, tenant, sid)
        return PV.bagla(out, lambda: K.for_dealers(engine, tenant, svc.current(), SV.school_id(sid), out))

    @app.post(f"{P}/{{sid}}/dealers", status_code=201)
    def schools_dealer_add(sid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(svc.add_dealer, engine, tenant, user, sid, str(body.get("code") or ""),
                   allowed(user, "ozellik:okul.bayi-onay"), "elle", SV._text(body.get("not"), 500, "Not"))
        audit(engine, user, "create", "school_dealer_link", out["id"], out["name"], {"school": sid, "state": out["state"]})
        return out

    @app.post(f"{P}/{{sid}}/dealers/{{link}}/approve")
    def schools_dealer_approve(sid: str, link: str, request: Request, body: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, "ozellik:okul.bayi-onay", "Bayi eşleştirme onayı")
        out = call(svc.decide, engine, tenant, user, sid, link, True, (body or {}).get("not"))
        audit(engine, user, "approve", "school_dealer_link", out["id"], out["name"], {"school": sid})
        return out

    @app.post(f"{P}/{{sid}}/dealers/{{link}}/reject")
    def schools_dealer_reject(sid: str, link: str, request: Request, body: Optional[dict[str, Any]] = None) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, "ozellik:okul.bayi-onay", "Bayi eşleştirme kararı")
        out = call(svc.decide, engine, tenant, user, sid, link, False, (body or {}).get("not"))
        audit(engine, user, "reject", "school_dealer_link", out["id"], out["name"], {"school": sid})
        return out

    @app.get(f"{P}/{{sid}}/visits")
    def schools_visits(sid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(svc.visits, engine, tenant, user, can_all(user), sid)
        return PV.bagla(out, lambda: K.for_visits(engine, tenant, svc.current(), SV.school_id(sid), out))

    @app.post(f"{P}/{{sid}}/visits", status_code=201)
    def schools_visit_add(sid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        out = call(svc.add_visit, engine, tenant, user, display, sid, body, allowed(user, "ozellik:okul.bayi-onay"))
        audit(engine, user, "create", "saha_ziyaret", out["id"], "Okul ziyareti",
              {"school": sid, "state": out["state"], "interest": out["interest"], "routed": out["routed"]})
        return out

    @app.post(f"{P}/{{sid}}/visits/suggest")
    def schools_visit_suggest(sid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return call(svc.suggest_fields, engine, tenant, sid, str(body.get("not") or ""))

    return svc
