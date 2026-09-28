"""M59 Kitapçı/bayi risk ve performans uçları: /api/v1/dealers/*.

Sayfa kapısı `access.RULES` (`sayfa:bayi-risk`); ziyaret notu `ozellik:bayi.not`, aksiyon `ozellik:bayi.aksiyon`, kural
taslağı `ozellik:bayi.kural`, dışa aktarma `ozellik:veri.disa-aktar` (`FEATURE_RULES`). Açıkça verilen ve burada
denetlenenler: bütün bayileri görme `ozellik:bayi.herkesinki` (yoksa yalnız CRM'de kişiye atanmış cariler — M30'un
atamasıyla aynı: cari sahibi / BMT il temsilcisi, AD hesabı), limit önerisi kararı `ozellik:bayi.limit-onay`, kural onayı
`ozellik:bayi.kural-onay` (hazırlayan/gönderen onaylayamaz). Zamanlayıcı (`timas-dealers@.timer`) yalnız
`POST /api/v1/dealers/run-due?tur=gunluk|sabah` çağırır.

CRM'e ve Logo'ya yazılmaz; e-posta yalnız iç alıcılara (sabah özeti, ayar doluysa). Müşteriye giden hiçbir metinde skor yazmaz.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, timedelta
from typing import Any, Callable, Optional

from fastapi import HTTPException, Request
from fastapi.responses import Response

from semantic_bridge import dealers as D
from semantic_bridge import dealers_sources as dsrc
from semantic_bridge import field_sales as F
from semantic_bridge.dealers import DealerError
from semantic_bridge.field_sales_sources import SourceError, guid, num, text

log = logging.getLogger("semantic.dealers.api")
P = "/api/v1/dealers"

#: Ekrandaki «Zeki AI'ya sor» örnekleri (Genel bakış soru kutusuna gider).
ZEKI_QUESTIONS = [
    "Ege bölgesinde vadesi 60 günü geçen alacağı olan kitapçılar kimler?",
    "Son 3 ayda iade oranı %20'yi geçen bayiler hangileri?",
    "Geçen yıl alıp bu yıl hiç almayan kitapçılar ve geçen yılki cirosu?",
    "Ortalama tahsilat süresi en çok uzayan 10 cari hangileri?",
    "Bu yıl karşılıksız çıkan çeki olan müşteriler kimler?",
    "Kitapyurdu'nun alacağı toplam alacağımızın yüzde kaçı?",
]


class Service:
    """Günlük tur, sabah e-postası, brif ve CRM canlı okumaları. Kaynak okuması `F.Source` (M30 ile aynı sınıf)."""

    def __init__(self, source: F.Source, settings: Callable[[], dict[str, Any]], llm: Callable[[bool], Any],
                 send_mail: Callable[[str, str, list[str]], str], link: Callable[[], str]):
        self.source, self.settings, self.llm, self.send_mail, self.link = source, settings, llm, send_mail, link
        self._run = threading.Lock()

    def run_day(self, engine: Any, tenant: str) -> dict[str, Any]:
        if not self._run.acquire(blocking=False):
            return {"skipped": "başka bir bayi riski turu sürüyor"}
        try:
            t0 = time.monotonic()
            st = self.settings()
            rule = D.rule_body(D.active_rule(engine, tenant, st))
            data = D.read_all(self.source, st)
            raws, info = D.build(data, st, rule)
            now = D.today()
            gun = now.isoformat()
            _, prev = D.previous_raw(engine, tenant, gun)
            g30, past30 = D.previous_raw(engine, tenant, (now - timedelta(days=30)).isoformat(), on_or_before=True)
            rows = D.score_rows(raws, rule, gun, prev, past30, info["dataEnd"], info["agingAsof"])
            D.write_day(engine, tenant, gun, rows, raws)
            props = D.sync_proposals(engine, tenant, rows, rule, gun)
            info.update({"gun": gun, "kural": rule["surum"], "karsilastirma30": g30, "ms": int((time.monotonic() - t0) * 1000),
                         "oneriYeni": len(props["new"]), "oneriDusen": props["dropped"]})
            info["bildirim"] = self._segment_events(engine, tenant, rows, gun)
            info["gerekce"] = self._proposal_texts(engine, props["new"])
            D.meta_set(engine, tenant, "run", info)
            return {"ok": True, **info}
        finally:
            self._run.release()

    @staticmethod
    def _segment_events(engine: Any, tenant: str, rows: list[dict[str, Any]], gun: str) -> int:
        """Segmenti önceki tura göre düşen cari: temsilcisine portal bildirimi (M30 bildirim tablosu, gün başına bir kez)."""
        n = 0
        for r in rows:
            if r.get("bmt") and D.worse(r.get("segment"), r.get("onceki_segment")):
                n += F.add_event(engine, tenant, r["bmt"], "bayi-segment", f"{gun}:{r['logo_code']}",
                                 f"{r.get('unvan') or r['logo_code']}: risk segmenti {r['onceki_segment']} → {r['segment']}",
                                 "Bayi riski kartında bileşenleri görün.", r["logo_code"])
        return n

    def _proposal_texts(self, engine: Any, ids: list[str]) -> dict[str, Any]:
        """Yeni limit önerilerine Zeki AI gerekçe cümlesi (toplu öncelik). Cümledeki her sayı kural gerekçesinde geçmezse
        yazılmaz; ekranda kural gerekçesi kalır."""
        if not ids:
            return {"yazildi": 0}
        llm = self.llm(True)
        if llm is None:
            return {"yazildi": 0, "not": "Zeki AI bağlı değil"}
        ok = bad = 0
        for pid in ids:
            p = D.proposal_by_id(engine, pid)
            if p is None:
                continue
            try:
                out = (llm.chat([{"role": "user", "content": D.proposal_prompt(p)}], max_tokens=160) or "").strip()
            except Exception as e:  # noqa: BLE001
                log.warning("dealers: limit gerekçesi yazılamadı: %s", e)
                break
            if out and D.numbers_ok(out, [p["gerekce_kural"]]):
                D.set_proposal_text(engine, pid, out)
                ok += 1
            else:
                bad += 1
        return {"yazildi": ok, "denetimdenKalan": bad}

    def run_morning(self, engine: Any, tenant: str) -> dict[str, Any]:
        st = self.settings()
        if not st["morningRecipients"]:
            return {"ok": True, "mail": "alıcı yok"}
        gun = D.latest_day(engine, tenant)
        if not gun:
            return {"ok": True, "mail": "veri yok"}
        rule = D.rule_body(D.active_rule(engine, tenant, st))
        s = D.summary(D.day_rows(engine, tenant, gun, None), [], rule)
        pending = len(D.list_proposals(engine, tenant, durum="oneri"))
        run = D.meta_get(engine, tenant, "run")
        body = D.morning_text(s, pending, gun, run.get("dataEnd"), self.link())
        return {"ok": True, "mail": self.send_mail("Bayi riski — sabah özeti", body, st["morningRecipients"]),
                "kotulesen": len(s["kotulesenler"])}

    def crm_history(self, row: dict[str, Any], fresh: bool) -> dict[str, Any]:
        """Tek carinin CRM risk onay geçmişi (son 365 gün, 5 dk bellek). CRM düşerse boş + uyarı."""
        if not row.get("crm_account_id"):
            return {"items": [], "error": None}
        st = self.settings()
        try:
            users = {guid(u.get("id")): text(u.get("ad")) for u in self.source.users(st, fresh)}
            rows = self.source.cached(f"dealer-risk:{row['crm_account_id']}", fresh, lambda: self.source.crm(
                lambda run: run(dsrc.crm_risk_history_sql(st["schema"], row["crm_account_id"], D.today() - timedelta(days=365)))))
            return {"items": dsrc.history_rows(rows, users), "error": None}
        except Exception as e:  # noqa: BLE001
            log.warning("dealers: CRM risk onay geçmişi okunamadı: %s", e)
            return {"items": [], "error": "CRM'e şu an ulaşılamıyor; risk onay geçmişi gösterilemiyor."}

    def brief(self, engine: Any, tenant: str, user: str, row: dict[str, Any], visits: list[dict[str, Any]], force: bool) -> dict[str, Any]:
        """Risk brifi: olgular → Zeki AI özet + 3 madde; her sayı olgularda geçmeli, geçmezse kural brifi. Önbellek girdi
        özetine bağlı (girdi değişmedikçe model yeniden çağrılmaz)."""
        facts = D.facts_of(row, visits)
        h = D.input_hash(facts)
        hit = D.cached_brief(engine, tenant, row["logo_code"])
        if hit and hit["girdi_hash"] == h and not force:
            return {"metin": hit["metin"], "maddeler": D._j(hit["maddeler_json"], []), "kaynak": hit["kaynak"],
                    "zaman": D._iso(hit["olusturma"]), "onbellek": True, "olgular": facts, "not": None}
        metin, items = D.rule_brief(row, visits)
        kaynak, model, note = "kural", "kural", None
        llm = self.llm(False)
        if llm is None:
            note = "Zeki AI bu kurulumda bağlı değil; kural brifi gösteriliyor."
        else:
            try:
                out = (llm.chat([{"role": "user", "content": D.brief_prompt(facts)}], max_tokens=500) or "").strip()
                m, its = D.parse_brief(out)
                if m and its and D.numbers_ok(m + " " + " ".join(its), facts):
                    metin, items, kaynak, model = m, its, "zeki", (getattr(llm, "model", "") or "zeki")
                else:
                    note = "Zeki AI metninde olgularda olmayan bir sayı vardı ya da biçim tutmadı; kural brifi gösteriliyor."
            except Exception as e:  # noqa: BLE001
                log.warning("dealers: brif üretilemedi: %s", e)
                note = "Zeki AI şu an cevap vermiyor; kural brifi gösteriliyor."
        D.save_brief(engine, tenant, row["logo_code"], row.get("gun") or "", h, metin, items, kaynak, model, user)
        return {"metin": metin, "maddeler": items, "kaynak": kaynak, "zaman": None, "onbellek": False, "olgular": facts, "not": note}


# ------------------------------------------------------------------ uçlar


def register(app: Any, deps: dict[str, Any]) -> Service:
    """app.py'de bağlanır. `deps`: auth(request) → (engine, tenant, user, display) · require_caller(request) · can(user, key) ·
    is_admin(user) · audit(engine, user, action, kind, id, title, detail) · conf(key, default) · fresh() ·
    crm_connect() / logo_connect() → salt okunur bağlantı · llm(batch: bool) → LLM kapısı istemcisi ya da None ·
    engine() / tenant() → zamanlayıcı ucunun (oturumsuz) veritabanı ve kiracısı."""
    from semantic_bridge.budget_api import _send_mail

    auth, require_caller, can, is_admin, audit, conf, fresh = (
        deps[k] for k in ("auth", "require_caller", "can", "is_admin", "audit", "conf", "fresh"))
    settings = lambda: D.settings_from(conf)  # noqa: E731

    def link() -> str:
        base = (conf("ALERT_LINK") or "").split("/uyarilar")[0]
        return f"{base}/bayi-risk" if base else ""

    def internal_mail(subject: str, body: str, to: list[str]) -> str:
        """Yalnız iç alıcılar: izinli alan adı ayarı doluysa dışındaki adrese gitmez."""
        allowed = [d.strip().lower().lstrip("@") for d in (conf("ALERT_RECIPIENT_DOMAINS") or "").split(",") if d.strip()]
        to = [x for x in to if not allowed or x.lower().rsplit("@", 1)[-1] in allowed]
        return _send_mail(subject, body, to) if to else "alıcı yok"

    svc = Service(F.Source(deps["crm_connect"], deps["logo_connect"]), settings, deps["llm"], internal_mail, link)

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        engine, tenant, user, display = auth(request)
        D.ensure(engine)
        return engine, tenant, user, display

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except DealerError as e:
            raise HTTPException(status_code=e.status, detail={"code": "DEALERS", "message": str(e)}) from e
        except F.FieldError as e:
            raise HTTPException(status_code=e.status, detail={"code": "DEALERS", "message": str(e)}) from e
        except SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "DATA_SOURCE_UNAVAILABLE", "message": str(e)}) from e
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001 — kaynak düştüyse kişiye düz cümle, ayrıntı günlükte
            log.exception("dealers: istek başarısız")
            state = str(getattr(e, "args", [""])[0])
            if state in ("08S01", "08001", "HYT00", "HYT01") or "timeout" in str(e).lower():
                raise HTTPException(status_code=503, detail={"code": "DATA_SOURCE_UNAVAILABLE", "retryable": True,
                                    "message": "CRM ya da Logo şu anda yanıt vermiyor; birazdan tekrar deneyin."}) from e
            raise HTTPException(status_code=502, detail={"code": "DEALERS", "message": "Bayi riski verisi okunamadı."}) from e

    def flag(user: str, key: str) -> bool:
        return is_admin(user) or can(user, key)

    def need(user: str, key: str, what: str) -> None:
        if not flag(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def all_scope(user: str) -> bool:
        return flag(user, "ozellik:bayi.herkesinki")

    def owner_of(user: str) -> Optional[str]:
        return None if all_scope(user) else user

    def scope_codes(engine, tenant, user) -> Optional[set[str]]:
        if all_scope(user):
            return None
        return {r["logo_code"] for r in D.day_rows(engine, tenant, D.latest_day(engine, tenant), user)}

    def rule_now(engine, tenant) -> dict[str, Any]:
        return D.rule_body(D.active_rule(engine, tenant, settings()))

    # -------------------------------------------------------------- genel

    @app.get(f"{P}/meta")
    def dealers_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        gun = D.latest_day(engine, tenant)
        mine = len(D.day_rows(engine, tenant, gun, user)) if gun else 0
        run = D.meta_get(engine, tenant, "run")
        rule = D.active_rule(engine, tenant, settings())
        rows = D.day_rows(engine, tenant, gun, None) if (gun and all_scope(user)) else []
        return {
            "me": {"username": user, "display": display, "admin": is_admin(user), "cari": mine, "canAll": all_scope(user),
                   "canNote": flag(user, "ozellik:bayi.not"), "canAction": flag(user, "ozellik:bayi.aksiyon"),
                   "canLimit": flag(user, "ozellik:bayi.limit-onay"), "canRule": flag(user, "ozellik:bayi.kural"),
                   "canRuleApprove": flag(user, "ozellik:bayi.kural-onay"), "canExport": flag(user, "ozellik:veri.disa-aktar")},
            "components": [{"key": k, "label": lab, "help": h} for k, lab, h in D.COMPONENTS],
            "segments": [{"key": k, "label": D.SEGMENT_LABEL[k]} for k in D.SEGMENTS],
            "buckets": [{"key": k, "label": lab} for k, lab in F.BUCKETS],
            "actionKinds": [{"key": k, "label": v} for k, v in D.ACTION_KINDS.items()],
            "rule": rule,
            "run": {k: run.get(k) for k in ("gun", "dataEnd", "agingAsof", "scope", "clients", "assigned", "idle", "kural",
                                             "karsilastirma30", "kanallar", "_at")},
            "bmts": D.bmts(rows),
            "kanallar": sorted({r.get("kanal") for r in rows if r.get("kanal")}),
            "iller": sorted({r.get("il") for r in rows if r.get("il")}, key=D.fold),
            "zekiQuestions": ZEKI_QUESTIONS,
        }

    @app.post(f"{P}/run-due")
    def dealers_run_due(request: Request, tur: str = "gunluk") -> dict[str, Any]:
        """Zamanlayıcı: gunluk (06:00 skor + eğilim + öneri + bildirim), sabah (08:00 iç e-posta özeti)."""
        require_caller(request)
        engine, tenant = deps["engine"](), deps["tenant"]()
        D.ensure(engine)
        if tur == "gunluk":
            return call(svc.run_day, engine, tenant)
        if tur == "sabah":
            return call(svc.run_morning, engine, tenant)
        raise HTTPException(status_code=422, detail={"code": "DEALERS", "message": "tur gunluk ya da sabah olmalı."})

    @app.post(f"{P}/refresh")
    def dealers_refresh(request: Request) -> dict[str, Any]:
        """Günlük turu elle koşturur (yönetici): ilk kurulumda zamanlayıcıdan önce bir kez."""
        engine, tenant, user, _ = ctx(request)
        if not is_admin(user):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Bayi riski verisini yenilemek yönetici işidir."})
        out = call(svc.run_day, engine, tenant)
        audit(engine, user, "run", "bayi_tur", None, "Bayi riski yenilendi", {k: out.get(k) for k in ("scope", "kural", "ms")})
        return out

    @app.get(f"{P}/status")
    def dealers_status(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        run = D.meta_get(engine, tenant, "run")
        return {"run": run, "gun": D.latest_day(engine, tenant)}

    # -------------------------------------------------------------- pano ve liste

    @app.get(f"{P}/summary")
    def dealers_summary(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        gun = D.latest_day(engine, tenant)
        owner = owner_of(user)
        rows = D.day_rows(engine, tenant, gun, owner)
        rule = rule_now(engine, tenant)
        g30, _raw = D.previous_raw(engine, tenant, (date.fromisoformat(gun) - timedelta(days=30)).isoformat(), on_or_before=True) if gun else (None, {})
        month_ago = D.day_rows(engine, tenant, g30, owner) if g30 else []
        s = D.summary(rows, month_ago, rule)
        codes = {r["logo_code"] for r in rows}
        pending = [p for p in D.list_proposals(engine, tenant, durum="oneri") if owner is None or p["code"] in codes]
        run = D.meta_get(engine, tenant, "run")
        return {"gun": gun, "gun30": g30, "dataEnd": run.get("dataEnd"), "agingAsof": run.get("agingAsof"),
                "kural": rule["surum"], **s, "limitBekleyen": pending}

    def _list_rows(engine, tenant, user, segment, kanal, il, bmt, q, grup, egilim, durum, order):
        rows = D.day_rows(engine, tenant, D.latest_day(engine, tenant), owner_of(user))
        idle = {"aktif": False, "hareketsiz": True}.get(durum)
        rows = D.filter_rows(rows, segment=segment, kanal=kanal, il=il, bmt=bmt if all_scope(user) else "", q=q,
                             grup=grup, egilim=egilim, hareketsiz=idle)
        rows.sort(key=D.ORDERS.get(order, D.ORDERS["skor"]))
        return rows

    @app.get(f"{P}/list")
    def dealers_list(request: Request, segment: str = "", kanal: str = "", il: str = "", bmt: str = "", q: str = "",
                     grup: str = "", egilim: str = "", durum: str = "", order: str = "skor", page: int = 1, size: int = 50) -> dict[str, Any]:
        """Sayfalı liste: toplam sayı her zaman döner (sessiz kesme yok); `size` 0 ise hepsi."""
        engine, tenant, user, _ = ctx(request)
        rows = _list_rows(engine, tenant, user, segment, kanal, il, bmt, q, grup, egilim, durum, order)
        total = len(rows)
        page = max(1, int(page))
        part = rows if size <= 0 else rows[(page - 1) * size: page * size]
        return {"items": [D.dealer_row(r) for r in part], "count": total, "page": page, "size": size,
                "vadesiGecmis": round(sum(num(r.get("vadesi_gecmis")) for r in rows), 2)}

    @app.get(f"{P}/list/export.csv")
    def dealers_export(request: Request, segment: str = "", kanal: str = "", il: str = "", bmt: str = "", q: str = "",
                       grup: str = "", egilim: str = "", durum: str = "", order: str = "skor") -> Response:
        engine, tenant, user, _ = ctx(request)
        need(user, "ozellik:veri.disa-aktar", "Dışa aktarma")
        rows = _list_rows(engine, tenant, user, segment, kanal, il, bmt, q, grup, egilim, durum, order)
        audit(engine, user, "run", "bayi_disa", None, "Bayi riski listesi dışa aktarıldı", {"satir": len(rows)})
        return Response(content=D.csv_text(rows).encode("utf-8"), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="bayi-riski.csv"'})

    # -------------------------------------------------------------- limit önerileri

    @app.get(f"{P}/limits")
    def dealers_limits(request: Request, durum: str = "oneri", code: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        items = D.list_proposals(engine, tenant, durum=durum, code=code)
        codes = scope_codes(engine, tenant, user)
        if codes is not None and not flag(user, "ozellik:bayi.limit-onay"):
            items = [p for p in items if p["code"] in codes]
        return {"items": items, "count": len(items), "states": [{"key": k, "label": v} for k, v in D.PROPOSAL_STATES.items()]}

    @app.post(f"{P}/limits/{{pid}}/approve")
    def dealers_limit_approve(pid: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, "ozellik:bayi.limit-onay", "Limit önerisi onayı")
        out = call(D.decide_proposal, engine, tenant, user, pid, True, text(body.get("note")))
        audit(engine, user, "approve", "bayi_limit", pid, out.get("unvan") or out["code"],
              {"degisim": out["degisim"], "onerilen": out["onerilen"], "not": body.get("note")})
        return out

    @app.post(f"{P}/limits/{{pid}}/reject")
    def dealers_limit_reject(pid: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, "ozellik:bayi.limit-onay", "Limit önerisi kararı")
        out = call(D.decide_proposal, engine, tenant, user, pid, False, text(body.get("note")))
        audit(engine, user, "reject", "bayi_limit", pid, out.get("unvan") or out["code"], {"not": body.get("note")})
        return out

    @app.post(f"{P}/limits/{{pid}}/crm-done")
    def dealers_limit_crm_done(pid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        if not (flag(user, "ozellik:bayi.limit-onay") or all_scope(user)):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "«CRM'e işlendi» işareti rolünüzde yok."})
        out = call(D.crm_done, engine, tenant, user, pid)
        audit(engine, user, "update", "bayi_limit", pid, out.get("unvan") or out["code"], {"durum": "crm_islendi"})
        return out

    # -------------------------------------------------------------- kurallar

    @app.get(f"{P}/rules")
    def dealers_rules(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        D.active_rule(engine, tenant, settings())
        return {"items": D.list_rules(engine, tenant), "components": [{"key": k, "label": lab, "help": h} for k, lab, h in D.COMPONENTS]}

    @app.post(f"{P}/rules", status_code=201)
    def dealers_rule_create(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        base = rule_now(engine, tenant)
        out = call(D.create_rule, engine, tenant, user, body, base)
        audit(engine, user, "create", "bayi_kural", out["id"], f"Bayi risk kuralı sürüm {out['surum']}", {"gerekce": out.get("gerekce")})
        return out

    @app.patch(f"{P}/rules/{{rid}}")
    def dealers_rule_edit(rid: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(D.edit_rule, engine, tenant, user, rid, body)
        audit(engine, user, "update", "bayi_kural", rid, f"Bayi risk kuralı sürüm {out['surum']}",
              {"agirliklar": out["agirliklar"], "esikler": out["esikler"], "kapsam": out["kapsam"], "limit": out["limit"]})
        return out

    @app.post(f"{P}/rules/{{rid}}/preview")
    def dealers_rule_preview(rid: str, request: Request) -> dict[str, Any]:
        """Taslak kuralla segment dağılımı: bugünkü satırların ham girdileri yeniden puanlanır (Logo'ya gidilmez). Kapsama
        yeni eklenen kanalın carileri bugünkü listede olmadığı için önizlemede görünmez (ekranda yazılır)."""
        engine, tenant, user, _ = ctx(request)
        draft = D.rule_body(call(D.get_rule, engine, tenant, rid))
        rows = D.day_rows(engine, tenant, D.latest_day(engine, tenant), owner_of(user))
        cur_dist = {g: {s: 0 for s in D.SEGMENTS} for g in ("standart", "anahtar")}
        new_dist = {g: {s: 0 for s in D.SEGMENTS} for g in ("standart", "anahtar")}
        changed, out_of_scope = [], 0
        for r in rows:
            if r.get("hareketsiz"):
                continue
            if r.get("segment"):
                cur_dist.setdefault(r.get("grup") or "standart", {s: 0 for s in D.SEGMENTS})[r["segment"]] += 1
            if not D.in_scope(r.get("kanal"), draft):
                out_of_scope += 1
                continue
            ev = D.evaluate(D._raw_from_row(r), draft)
            new_dist[ev["grup"]][ev["segment"]] += 1
            if ev["segment"] != r.get("segment"):
                changed.append({"code": r["logo_code"], "unvan": r.get("unvan"), "eski": r.get("segment"), "yeni": ev["segment"],
                                "eskiSkor": r.get("skor"), "yeniSkor": ev["skor"]})
        changed.sort(key=lambda x: (D.SEGMENTS.index(x["yeni"]) - D.SEGMENTS.index(x["eski"] or "A")), reverse=True)
        return {"mevcut": cur_dist, "taslak": new_dist, "degisen": changed, "kapsamDisi": out_of_scope,
                "not": "Kapsama yeni eklenen kanalın carileri bugünkü listede olmadığından önizlemeye girmez; yürürlüğe girince ilk turda puanlanır."}

    @app.post(f"{P}/rules/{{rid}}/submit")
    def dealers_rule_submit(rid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(D.submit_rule, engine, tenant, user, rid)
        audit(engine, user, "update", "bayi_kural", rid, f"Bayi risk kuralı sürüm {out['surum']}", {"durum": "onayda"})
        return out

    @app.post(f"{P}/rules/{{rid}}/approve")
    def dealers_rule_approve(rid: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, "ozellik:bayi.kural-onay", "Bayi risk kuralı onayı")
        out = call(D.decide_rule, engine, tenant, user, rid, True, text(body.get("note")))
        audit(engine, user, "approve", "bayi_kural", rid, f"Bayi risk kuralı sürüm {out['surum']}", {"not": body.get("note")})
        return out

    @app.post(f"{P}/rules/{{rid}}/reject")
    def dealers_rule_reject(rid: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, "ozellik:bayi.kural-onay", "Bayi risk kuralı kararı")
        out = call(D.decide_rule, engine, tenant, user, rid, False, text(body.get("note")))
        audit(engine, user, "reject", "bayi_kural", rid, f"Bayi risk kuralı sürüm {out['surum']}", {"not": body.get("note")})
        return out

    # -------------------------------------------------------------- aksiyonlar

    @app.get(f"{P}/actions")
    def dealers_actions(request: Request, code: str = "", durum: str = "", sahip: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        items = D.list_actions(engine, tenant, codes=scope_codes(engine, tenant, user), viewer=user, code=code, durum=durum, sahip=sahip)
        return {"items": items, "count": len(items)}

    @app.post(f"{P}/actions", status_code=201)
    def dealers_action_add(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        row = call(D.scoped, engine, tenant, user, str(body.get("code") or ""), all_scope(user))
        out = call(D.add_action, engine, tenant, user, row, body, all_scope(user))
        audit(engine, user, "create", "bayi_aksiyon", out["id"], out.get("unvan") or out["code"], {"tur": out["tur"], "sahip": out["sahip"]})
        return out

    @app.patch(f"{P}/actions/{{aid}}")
    def dealers_action_edit(aid: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out, diff = call(D.update_action, engine, tenant, user, aid, body, all_scope(user))
        if diff:
            audit(engine, user, "update", "bayi_aksiyon", aid, out.get("unvan") or out["code"], diff)
        return out

    # -------------------------------------------------------------- bayi kartı (sabit yollardan sonra)

    def _visits(engine, tenant, user, code) -> list[dict[str, Any]]:
        return F.list_visits(engine, tenant, user, hedef=code, tur="cari", admin=is_admin(user))

    @app.get(f"{P}/{{code}}")
    def dealers_card(code: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        row = call(D.scoped, engine, tenant, user, code, all_scope(user))
        visits = _visits(engine, tenant, user, code)
        run = D.meta_get(engine, tenant, "run")
        hit = D.cached_brief(engine, tenant, code)
        fresh_hash = D.input_hash(D.facts_of(row, visits))
        return {
            **D.dealer_row(row), "gun": row["gun"], "dataEnd": row.get("veri_son_gunu"), "agingAsof": row.get("yaslandirma_gunu"),
            "kuralSurum": row["kural_surum"], "fingerprint": row["fingerprint"],
            "bilesenler": D._j(row.get("bilesen_json"), []),
            "kovalar": {k: row.get(k) for k, _ in F.BUCKETS}, "gelmemis": row.get("gelmemis"), "plansiz": row.get("plansiz"),
            "satis12": row.get("satis_12ay"), "iade12": row.get("iade_12ay"), "buyume6": row.get("buyume_6ay"), "dso": row.get("dso"),
            "duzensizlik": row.get("duzensizlik"), "aktifAy": row.get("aktif_ay"), "odeme12": row.get("odeme_12ay"),
            "karsiliksiz": row.get("karsiliksiz"), "protesto": row.get("protesto"), "cekTutar": row.get("cek_tutar"),
            "limit": D._j(row.get("limit_json"), {}), "crmEsi": bool(row.get("crm_account_id")),
            "siparisRisktetutar": row.get("siparis_riskte_tutar"), "pay": row.get("pay"),
            "seri": D.series(engine, tenant, code),
            "oneriler": D.list_proposals(engine, tenant, code=code),
            "aksiyonlar": D.list_actions(engine, tenant, codes=None, viewer=user, code=code),
            "ziyaretler": visits[:20], "ziyaretSayisi": len(visits),
            "brif": ({"metin": hit["metin"], "maddeler": D._j(hit["maddeler_json"], []), "kaynak": hit["kaynak"],
                      "zaman": D._iso(hit["olusturma"]), "guncel": hit["girdi_hash"] == fresh_hash} if hit else None),
            "calendar": {"year": run.get("year"), "firm": run.get("firm")},
        }

    @app.get(f"{P}/{{code}}/aging")
    def dealers_aging(code: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        row = call(D.scoped, engine, tenant, user, code, all_scope(user))
        return {"code": code, "asof": row.get("yaslandirma_gunu"), "bakiye": row.get("bakiye"), "gelmemis": row.get("gelmemis"),
                "plansiz": row.get("plansiz"), "vadesiGecmis": row.get("vadesi_gecmis"),
                "kovalar": [{"key": k, "label": lab, "tutar": row.get(k)} for k, lab in F.BUCKETS],
                "not": "Yaklaşık: Logo'da ödeme kapama kullanılmıyor; bakiye en yeni vadelerden geriye dağıtıldı (FIFO). "
                       "Vade planına dağıtılamayan bakiye «plansız» olarak ayrı yazılır."}

    @app.get(f"{P}/{{code}}/history")
    def dealers_history(code: str, request: Request, gun: int = 365) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        row = call(D.scoped, engine, tenant, user, code, all_scope(user))
        since = (D.today() - timedelta(days=max(1, int(gun)))).isoformat()
        return {"skor": D.score_history(engine, tenant, code, since), "seri": D.series(engine, tenant, code),
                "crmRisk": svc.crm_history(row, fresh())}

    @app.post(f"{P}/{{code}}/brief")
    def dealers_brief(code: str, request: Request, yenile: bool = False) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        row = call(D.scoped, engine, tenant, user, code, all_scope(user))
        out = call(svc.brief, engine, tenant, user, row, _visits(engine, tenant, user, code), yenile)
        if not out.get("onbellek"):
            audit(engine, user, "run", "bayi_brif", code, "Bayi risk brifi", {"kaynak": out["kaynak"]})
        return out

    @app.get(f"{P}/{{code}}/notes")
    def dealers_notes(code: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        call(D.scoped, engine, tenant, user, code, all_scope(user))
        items = _visits(engine, tenant, user, code)
        return {"items": items, "count": len(items)}

    @app.post(f"{P}/{{code}}/notes", status_code=201)
    def dealers_note_add(code: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """Ziyaret/görüşme notu M30/M31 ortak tablosuna (`tur='cari'`, hedef = cari kodu) yazılır."""
        engine, tenant, user, _ = ctx(request)
        row = call(D.scoped, engine, tenant, user, code, all_scope(user))
        if not (text(body.get("notu"))):
            raise HTTPException(status_code=422, detail={"code": "DEALERS", "message": "Not boş olamaz."})
        payload = {k: body.get(k) for k in ("notu", "ton", "sonrakiAdim", "sonrakiTarih", "sozOdemeTarihi", "sozOdemeTutari",
                                            "gizli", "gerceklesen") if k in body}
        out = call(F.add_visit, engine, tenant, user, {**payload, "tur": "cari", "hedef": code, "durum": "yapildi"}, row.get("unvan"))
        audit(engine, user, "create", "saha_ziyaret", out["id"], row.get("unvan") or code, {"kaynak": "bayi-risk"})
        return out

    return svc
