"""M38 Müşteri ilişkileri uçları: /api/v1/musteri/*.

Sayfa kapısı `access.RULES`: özet, cariler, cari ayrıntısı, portföyüm, aksiyonlar `sayfa:musteri-iliskileri`; veri sağlığı
(`/health*`) `sayfa:musteri-veri-sagligi`. Aksiyon yazma `ozellik:musteri.eylem-yaz`, bulgu işaretleme
`ozellik:musteri.bulgu-isaretle`, dışa aktarma `ozellik:veri.disa-aktar` (`FEATURE_RULES`). Açıkça verilenler burada
denetlenir: `ozellik:musteri.herkesinki` (bütün cariler; yoksa yalnız temsilcisi oturumdaki AD hesabı olan cariler),
`ozellik:musteri.guvenlik-bulgulari` (güvenlik bulguları). Zamanlayıcı (`timas-musteri.timer`) yalnız
`POST /api/v1/musteri/run-due?tur=gece|haftalik` çağırır.

CRM'e ve Logo'ya yazılmaz. E-posta yalnız iç alıcılara gider (temsilcinin kurum adresi, müdür ve CRM yöneticisi listesi;
izinli alan adı ayarı doluysa dışına gitmez); müşteriye hiçbir şey otomatik gönderilmez.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import date, timedelta
from typing import Any, Callable, Optional

import sqlalchemy as sa
from fastapi import HTTPException, Request
from fastapi.responses import Response

from semantic_bridge import field_sales as F
from semantic_bridge import field_sales_sources as fs
from semantic_bridge import musteri as M
from semantic_bridge import musteri_sources as src
from semantic_bridge.field_sales_sources import SourceError, day, guid, num, text
from semantic_bridge.musteri import MusteriError

log = logging.getLogger("semantic.musteri.api")
P = "/api/v1/musteri"

#: Ekrandaki «Zeki AI'ya sor» örnekleri (Genel bakış soru kutusuna gider).
ZEKI_QUESTIONS = [
    "Son 12 ayda alımı yüzde 30'dan fazla düşen kitapçılar hangileri?",
    "Kitapyurdu'nun bu yılki net alımı geçen yılın aynı dönemine göre nasıl?",
    "90 gündür sipariş vermeyen ama geçen yıl düzenli alan bayiler kimler?",
    "Ege bölgesinde en çok iade eden 10 cari hangileri?",
    "Dağıtıcı kanalının cirodaki payı son üç yılda nasıl değişti?",
]


class Service:
    """Gece turu (değer, risk, veri sağlığı, aksiyon sonucu), haftalık e-posta, cari ayrıntısının canlı okuması."""

    def __init__(self, source: F.Source, settings: Callable[[], dict[str, Any]], llm: Callable[[Optional[int]], Any],
                 send_mail: Callable[[str, str, list[str]], str], link: Callable[[str], str], batch: int):
        self.source, self.settings, self.llm, self.send_mail, self.link, self.batch = source, settings, llm, send_mail, link, batch
        self._run = threading.Lock()

    def calendar(self, engine: Any, tenant: str) -> dict[str, Any]:
        run = M.meta_get(engine, tenant, "run")
        if not run.get("kesim"):
            raise MusteriError("Müşteri verisi henüz hazırlanmadı: gece turu bir kez koşmalı (Yönetim ya da zamanlayıcı).", 409)
        return run

    # -------------------------------------------------------------- gece turu

    def run_night(self, engine: Any, tenant: str) -> dict[str, Any]:
        if not self._run.acquire(blocking=False):
            return {"skipped": "başka bir müşteri turu sürüyor"}
        try:
            st = self.settings()
            t0 = time.monotonic()
            data = M.read_all(self.source, st)
            rows, info = M.build_accounts(data, st, F.last_visit_days(engine, tenant), M.previous_accounts(engine, tenant))
            M.write_accounts(engine, tenant, rows)
            M.write_segments(engine, tenant, M.segments_of(rows, info["asof"]))
            kesim = date.fromisoformat(info["kesim"])
            info["outcomes"] = M.write_outcomes(engine, M.action_outcomes(
                M.list_actions(engine, tenant), data["logo"]["daily"], kesim))
            info["health"] = self._health(engine, tenant, data, st)
            info["ms"] = int((time.monotonic() - t0) * 1000)
            M.meta_set(engine, tenant, "run", info)
            return {"ok": True, **{k: v for k, v in info.items() if k != "firms"}}
        finally:
            self._run.release()

    def _health(self, engine: Any, tenant: str, data: dict[str, Any], st: dict[str, Any]) -> dict[str, Any]:
        dec = M.decisions(engine, tenant)
        found, ask, info = M.health_findings(data, st, dec, tenant)
        asked = self._ask_pairs(engine, tenant, data, ask, st)
        if asked["decided"]:                       # kararlar bulgu metnine yansısın
            found, ask, info = M.health_findings(data, st, M.decisions(engine, tenant), tenant)
        stats = M.sync_findings(engine, tenant, found, info["tarih"])
        prev = M.save_score(engine, tenant, info)
        new_sec = [f for f in found if f["tur"] == "guvenlik"]
        mail = "yok"
        drop = (prev - info["puan"]) if (prev is not None and info.get("puan") is not None) else 0.0
        if st["crmAdminRecipients"] and drop >= st["scoreDropAlert"]:
            mail = self.send_mail("CRM veri sağlığı puanı düştü",
                                  f"Veri sağlığı puanı {prev} → {info['puan']} (etkin cari {info['etkin_cari']}, bulgulu "
                                  f"{info['bulgulu_cari']}).\n\n" + self.link("/musteri-iliskileri/veri-sagligi"),
                                  st["crmAdminRecipients"])
        new_security = self._new_security(engine, tenant, info["tarih"])
        if st["crmAdminRecipients"] and new_security:
            mail = self.send_mail("Yeni CRM güvenlik bulgusu",
                                  f"Bu gece {new_security} yeni güvenlik bulgusu açıldı (ayrıntı yalnız yetkili ekranda).\n\n"
                                  + self.link("/musteri-iliskileri/veri-sagligi"), st["crmAdminRecipients"])
        M.meta_set(engine, tenant, "health", {**info, "sync": stats, "zeki": asked, "guvenlik": len(new_sec)})
        return {"puan": info["puan"], "onceki": prev, **stats, "zeki": asked, "mail": mail}

    @staticmethod
    def _new_security(engine: Any, tenant: str, on: str) -> int:
        with engine.connect() as c:
            return int(c.execute(sa.select(sa.func.count()).select_from(M.FINDINGS).where(
                M.FINDINGS.c.tenant_id == tenant, M.FINDINGS.c.tur == "guvenlik", M.FINDINGS.c.ilk_goruldu == on)).scalar() or 0)

    def _ask_pairs(self, engine: Any, tenant: str, data: dict[str, Any], ask: list[dict[str, Any]], st: dict[str, Any]) -> dict[str, Any]:
        """Bulanık tekrar adayları için kapalı küme karar (`QueuedLlm.choose`, gece önceliği). Süre bütçesi dolunca kalan
        çiftler sonraki geceye kalır (sıra kalıcı, sessiz tavan yok; bekleyen sayısı ekranda). Eşiğin altındaki cevap
        «belirsiz» kaydedilir ve bulgu olarak kalır; karar CRM yöneticisinindir."""
        if not ask:
            return {"decided": 0, "waiting": 0}
        llm = self.llm(self.batch)
        if llm is None or not callable(getattr(llm, "choose", None)):
            return {"decided": 0, "waiting": len(ask), "note": "Zeki AI bağlı değil"}
        by_id = {guid(a.get("account_id")): a for a in data["crm"].get("health") or []}
        deadline = time.monotonic() + st["llmBudgetSec"]
        done = unsure = 0
        for p in ask:
            if time.monotonic() > deadline:
                break
            try:
                res = llm.choose(M.dup_prompt(by_id[p["a"]], by_id[p["b"]]), list(M.DUP_CHOICES))
            except Exception as e:  # noqa: BLE001
                log.warning("musteri: tekrar kararı alınamadı: %s", e)
                break
            if res.choice is None or not res.confident(st["dupMinProb"], 0.2):
                unsure += 1
                M.save_decision(engine, tenant, p["cift"], "belirsiz", res.probability, "zeki")
                continue
            M.save_decision(engine, tenant, p["cift"], M.DUP_KEYS[res.choice], round(float(res.probability or 0), 4), "zeki")
            done += 1
        return {"decided": done + unsure, "same_or_diff": done, "unsure": unsure, "waiting": len(ask) - done - unsure}

    # -------------------------------------------------------------- haftalık e-posta

    def run_weekly(self, engine: Any, tenant: str) -> dict[str, Any]:
        st = self.settings()
        run = self.calendar(engine, tenant)
        rows = M.account_rows(engine, tenant, None)
        since = (date.fromisoformat(run["asof"]) - timedelta(days=7)).isoformat()
        out: dict[str, Any] = {"ok": True, "temsilci": 0, "mudur": "alıcı yok"}
        if st["repMail"]:
            fresh = [r for r in rows if r.get("risk_duzeyi") in ("yuksek", "kayip") and (r.get("risk_gecis") or "") >= since
                     and r.get("temsilci")]
            mails = self._rep_mails()
            by: dict[str, list[dict[str, Any]]] = {}
            for r in fresh:
                by.setdefault(r["temsilci"], []).append(r)
            for rep, items in by.items():
                to = mails.get(rep)
                if to:
                    items.sort(key=M.SORTS["oncelik"])
                    self.send_mail("Kayıp riski yükselen carileriniz", M.rep_mail_text(items, self.link("/musteri-iliskileri/portfoyum")), [to])
                    out["temsilci"] += 1
        if st["managerRecipients"]:
            out["mudur"] = self.send_mail("Pazartesi kayıp riski özeti", M.manager_mail_text(rows, run["asof"], self.link("/musteri-iliskileri")),
                                          st["managerRecipients"])
        return out

    def _rep_mails(self) -> dict[str, str]:
        from semantic_bridge.people import account

        st = self.settings()
        try:
            rows = self.source.cached("crm-user-mail", False, lambda: self.source.crm(
                lambda run: fs.lower_keys(run(src.crm_user_mail_sql(st["schema"])))))
        except Exception as e:  # noqa: BLE001
            log.warning("musteri: temsilci e-postaları okunamadı: %s", e)
            return {}
        return {account(text(r.get("domain")) or ""): text(r.get("eposta")) for r in rows if text(r.get("eposta"))}

    # -------------------------------------------------------------- cari ayrıntısı (canlı)

    def live(self, engine: Any, tenant: str, row: dict[str, Any], fresh: bool) -> dict[str, Any]:
        """Son faturalar, 12 ay kitap kırılımı (M30 kaynak fonksiyonları), CRM siparişleri; 5 dk bellek."""
        st = self.settings()
        run = self.calendar(engine, tenant)
        f, pf = run["firm"], run.get("prevFirm")
        kesim = date.fromisoformat(run["kesim"])
        code = row["cari_kodu"]
        lo = kesim - timedelta(days=364)

        def logo_part(run_):
            out: dict[str, Any] = {"invoices": fs.read_rows(run_, fs.invoices_for_sql(f, code, 5))}
            if len(out["invoices"]) < 5 and pf:
                out["invoices"] += fs.read_rows(run_, fs.invoices_for_sql(pf, code, 5 - len(out["invoices"])))
            books: dict[str, dict[str, Any]] = {}
            firms = {int(k): v for k, v in (run.get("firms") or {}).items()}
            for ff, a, b in src.firm_windows(firms, lo, kesim):
                for r in fs.read_rows(run_, fs.items_for_sql(ff, code, a, b)):
                    k = text(r.get("stok")) or ""
                    cur = books.setdefault(k, {"stok": k, "ad": text(r.get("ad")), "adet": 0.0, "ciro": 0.0})
                    cur["adet"] += num(r.get("adet"))
                    cur["ciro"] += num(r.get("ciro"))
            out["books"] = sorted(books.values(), key=lambda x: -x["ciro"])
            return out

        logo = self.source.cached(f"musteri-logo:{code}:{kesim}", fresh, lambda: self.source.logo(logo_part))
        crm: dict[str, Any] = {"orders": [], "error": None}
        if row.get("crm_account_id"):
            try:
                crm = self.source.cached(f"musteri-crm:{row['crm_account_id']}", fresh, lambda: self.source.crm(lambda run_: {
                    "orders": fs.lower_keys(run_(fs.crm_orders_for_sql(st["schema"], row["crm_account_id"], 365, M.today()))),
                    "labels": {int(num(r.get("code"))): text(r.get("label")) for r in fs.lower_keys(run_(fs.crm_order_status_sql(st["schema"])))},
                    "error": None}))
            except Exception as e:  # noqa: BLE001
                log.warning("musteri: CRM siparişleri okunamadı: %s", e)
                crm = {"orders": [], "labels": {}, "error": "CRM'e şu an ulaşılamıyor; siparişler gösterilemiyor."}
        return {"logo": logo, "crm": crm}

    def detail(self, engine: Any, tenant: str, user: str, code: str, all_scope: bool, admin: bool, fresh: bool) -> dict[str, Any]:
        row = M.in_scope(engine, tenant, user, code, all_scope)
        warnings: list[str] = []
        live: dict[str, Any] = {}
        try:
            live = self.live(engine, tenant, row, fresh)
        except MusteriError:
            raise
        except Exception as e:  # noqa: BLE001 — Logo düşerse gece turunun rakamlarıyla devam
            log.warning("musteri: cari ayrıntısı canlı okuması başarısız: %s", e)
            warnings.append("Logo'ya şu an ulaşılamıyor; gece turunun rakamları gösteriliyor.")
        logo, crm = live.get("logo") or {}, live.get("crm") or {}
        if crm.get("error"):
            warnings.append(crm["error"])
        field_row = F.one(engine, tenant, code) if self._field_ready(engine) else None
        credit = None
        if field_row:
            credit = {k: field_row.get(k) for k in ("bakiye", "vadesi_gecmis", "k_90p", "risk_doluluk", "siparis_riskte",
                                                     "karsiliksiz_olay_12ay", "protesto_olay_12ay", "son_odeme_tarihi")}
            credit["asof"] = field_row.get("asof")
        return {
            **M.card(row),
            "faturalar": [{"tarih": day(i.get("tarih")), "no": text(i.get("no")), "tutar": num(i.get("tutar"))} for i in logo.get("invoices") or []],
            "kitaplar": [{**b, "adet": round(b["adet"], 2), "ciro": round(b["ciro"], 2)} for b in logo.get("books") or []],
            "siparisler": [{"no": text(o.get("no")), "tarih": day(o.get("tarih")), "tutar": num(o.get("tutar")),
                            "durum": (crm.get("labels") or {}).get(int(num(o.get("durum")))) or str(o.get("durum")),
                            "riskte": int(num(o.get("durum"))) in fs.ORDER_RISK_STATUS} for o in crm.get("orders") or []],
            "ziyaretler": F.list_visits(engine, tenant, user, tur="cari", hedef=code, admin=admin),
            "aksiyonlar": [M._action_out(a) for a in M.list_actions(engine, tenant, code=code)],
            "tahsilat": credit,
            "sahibim": (row.get("temsilci") or "") == user,
            "warnings": warnings,
        }

    @staticmethod
    def _field_ready(engine: Any) -> bool:
        try:
            F.ensure(engine)
            return True
        except Exception:  # noqa: BLE001
            return False

    def monthly(self, engine: Any, tenant: str, row: dict[str, Any], fresh: bool) -> dict[str, Any]:
        run = self.calendar(engine, tenant)
        kesim = date.fromisoformat(run["kesim"])
        firms = {int(k): v for k, v in (run.get("firms") or {}).items()}
        start = date(kesim.year - 2, kesim.month, 1) + timedelta(days=32)
        start = date(start.year, start.month, 1)
        months = self.source.cached(f"musteri-ay:{row['cari_kodu']}:{kesim}", fresh, lambda: self.source.logo(
            lambda run_: src.read_monthly(run_, firms, row["cari_kodu"], start, kesim)))
        return {"code": row["cari_kodu"], "kesim": run["kesim"], "items": M.monthly_series(months, kesim, 24)}

    def summary(self, engine: Any, tenant: str, row: dict[str, Any]) -> dict[str, Any]:
        """Zeki AI neden özeti: olgular → 1–2 cümle; her sayı olgularda geçmeli, geçmezse kural özeti kalır."""
        llm = self.llm(None)
        if llm is None:
            raise MusteriError("Zeki AI bu kurulumda bağlı değil.", 503)
        facts = M.facts_of(row)
        if not facts:
            raise MusteriError("Bu cari için özetlenecek rakam yok.", 409)
        try:
            out = (llm.chat([{"role": "user", "content": M.summary_prompt(row, facts)}], max_tokens=220) or "").strip()
        except Exception as e:  # noqa: BLE001
            raise MusteriError("Zeki AI şu an cevap vermiyor; kural özeti gösteriliyor.", 503) from e
        ok = bool(out) and M.numbers_ok(out, facts)
        final = out if ok else (row.get("neden_ozeti") or M.rule_summary(M._j(row.get("nedenler_json"), [])) or "")
        M.save_summary(engine, tenant, row["cari_kodu"], final, "zeki" if ok else "kural", M.summary_hash(row))
        return {"metin": final, "kaynak": "zeki" if ok else "kural",
                "not": None if ok else "Zeki AI metninde olgularda olmayan bir sayı vardı; kural özeti gösteriliyor."}

    def phone(self, row: dict[str, Any]) -> Optional[str]:
        """Carinin CRM'deki telefonu (tek kayıt, canlı). Yalnız portföy sahibine; uç kontrol eder ve kaydeder."""
        if not row.get("crm_account_id"):
            return None
        st = self.settings()
        p = fs.prefix(st["schema"])
        gid = fs._guid_literal(row["crm_account_id"])
        rows = self.source.crm(lambda run_: fs.lower_keys(run_(
            f"SELECT a.Telephone1 AS tel FROM {p}AccountBase a WHERE a.AccountId = '{gid}'")))
        return text(rows[0].get("tel")) if rows else None


# ------------------------------------------------------------------ uçlar


def register(app: Any, deps: dict[str, Any]) -> Service:
    """app.py'de bağlanır. `deps`: auth(request) → (engine, tenant, user, display) · require_caller(request) · can(user, key) ·
    is_admin(user) · audit(engine, user, action, kind, id, title, detail) · conf(key, default) · fresh() ·
    crm_connect() / logo_connect() → salt okunur bağlantı · llm(priority) → LLM kapısı istemcisi ya da None · batch (gece
    önceliği) · engine() / tenant() → zamanlayıcı ucunun veritabanı ve kiracısı."""
    from semantic_bridge.budget_api import _send_mail

    auth, require_caller, can, is_admin, audit, conf, fresh = (
        deps[k] for k in ("auth", "require_caller", "can", "is_admin", "audit", "conf", "fresh"))
    settings = lambda: M.settings_from(conf)  # noqa: E731

    def link(path: str) -> str:
        base = (conf("ALERT_LINK") or "").split("/uyarilar")[0]
        return f"{base}{path}" if base else ""

    def internal_mail(subject: str, body: str, to: list[str]) -> str:
        allowed = [d.strip().lower().lstrip("@") for d in (conf("ALERT_RECIPIENT_DOMAINS") or "").split(",") if d.strip()]
        to = [x for x in to if not allowed or x.lower().rsplit("@", 1)[-1] in allowed]
        return _send_mail(subject, body, to) if to else "alıcı yok"

    svc = Service(F.Source(deps["crm_connect"], deps["logo_connect"]), settings, deps["llm"], internal_mail, link,
                  deps.get("batch", 2))

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        engine, tenant, user, display = auth(request)
        M.ensure(engine)
        return engine, tenant, user, display

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except (MusteriError, F.FieldError) as e:
            # 403 ön yüzde «oturum yok» sanılmasın: yetki reddi her zaman FORBIDDEN koduyla döner.
            raise HTTPException(status_code=e.status, detail={"code": "FORBIDDEN" if e.status == 403 else "MUSTERI",
                                                              "message": str(e)}) from e
        except SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "DATA_SOURCE_UNAVAILABLE", "message": str(e)}) from e
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            log.exception("musteri: istek başarısız")
            state = str(getattr(e, "args", [""])[0])
            if state in ("08S01", "08001", "HYT00", "HYT01") or "timeout" in str(e).lower():
                raise HTTPException(status_code=503, detail={"code": "DATA_SOURCE_UNAVAILABLE", "retryable": True,
                                    "message": "CRM ya da Logo şu anda yanıt vermiyor; birazdan tekrar deneyin."}) from e
            raise HTTPException(status_code=502, detail={"code": "MUSTERI", "message": "Müşteri verisi okunamadı."}) from e

    def flag(user: str, key: str) -> bool:
        return is_admin(user) or can(user, key)

    def all_scope(user: str) -> bool:
        return flag(user, "ozellik:musteri.herkesinki")

    def security(user: str) -> bool:
        return flag(user, "ozellik:musteri.guvenlik-bulgulari")

    def owner_of(user: str, temsilci: str) -> Optional[str]:
        """Portföy süzgeci: yetkisiz kişi yalnız kendisi; yetkili boş temsilciyle herkes, doluysa o temsilci."""
        if not all_scope(user):
            return user
        return temsilci.strip().lower() or None

    def page(items: list[Any], p: int, size: int) -> tuple[list[Any], dict[str, int]]:
        size = max(1, min(1000, int(size or 50)))
        p = max(1, int(p or 1))
        return items[(p - 1) * size:p * size], {"page": p, "size": size, "total": len(items),
                                                 "pages": max(1, -(-len(items) // size))}

    # -------------------------------------------------------------- genel

    @app.get(f"{P}/meta")
    def musteri_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        run = M.meta_get(engine, tenant, "run")
        st = settings()
        mine = sa.select(sa.func.count()).select_from(M.ACCOUNTS).where(M.ACCOUNTS.c.tenant_id == tenant, M.ACCOUNTS.c.temsilci == user)
        with engine.connect() as c:
            my = int(c.execute(mine).scalar() or 0)
        kanal = sa.select(M.ACCOUNTS.c.logo_kanal).where(M.ACCOUNTS.c.tenant_id == tenant).distinct()
        bolge = sa.select(M.ACCOUNTS.c.bolge).where(M.ACCOUNTS.c.tenant_id == tenant).distinct()
        with engine.connect() as c:
            kanallar = sorted({r[0] for r in c.execute(kanal) if r[0]})
            bolgeler = sorted({r[0] for r in c.execute(bolge) if r[0]})
        return {
            "me": {"username": user, "display": display, "admin": is_admin(user), "cari": my, "canAll": all_scope(user),
                   "canAction": flag(user, "ozellik:musteri.eylem-yaz"), "canMark": flag(user, "ozellik:musteri.bulgu-isaretle"),
                   "canSecurity": security(user), "canExport": flag(user, "ozellik:veri.disa-aktar"),
                   "canHealth": flag(user, "sayfa:musteri-veri-sagligi")},
            "weights": [{"key": k, "max": w, "label": lab} for k, w, lab in M.WEIGHTS],
            "levels": [{"key": k, "label": v} for k, v in M.LEVELS.items()],
            "actionTypes": [{"key": k, "label": v} for k, v in M.ACTION_TYPES.items()],
            "healthTypes": [{"key": k, "label": v} for k, v in M.HEALTH_TYPES.items() if k != "guvenlik" or security(user)],
            "healthStates": [{"key": k, "label": v} for k, v in M.HEALTH_STATES.items()],
            "run": {k: run.get(k) for k in ("asof", "kesim", "year", "accounts", "assigned", "levels", "warnings", "ms", "_at")},
            "rules": {"riskHigh": st["riskHigh"], "riskMid": st["riskMid"], "lostMinDays": st["lostMinDays"],
                      "lostMultiple": st["lostMultiple"], "minPurchaseDays": st["minPurchaseDays"],
                      "orderFloorDays": st["orderFloorDays"]},
            "reps": M.reps(engine, tenant) if all_scope(user) else [],
            "kanallar": kanallar, "bolgeler": bolgeler, "zekiQuestions": ZEKI_QUESTIONS,
        }

    @app.post(f"{P}/run-due")
    def musteri_run_due(request: Request, tur: str = "gece") -> dict[str, Any]:
        """Zamanlayıcı: gece (değer + risk + veri sağlığı + aksiyon sonucu), haftalik (pazartesi e-postaları)."""
        require_caller(request)
        engine, tenant = deps["engine"](), deps["tenant"]()
        M.ensure(engine)
        if tur == "gece":
            return call(svc.run_night, engine, tenant)
        if tur == "haftalik":
            return call(svc.run_weekly, engine, tenant)
        raise HTTPException(status_code=422, detail={"code": "MUSTERI", "message": "tur gece ya da haftalik olmalı."})

    @app.post(f"{P}/refresh")
    def musteri_refresh(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        if not is_admin(user):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Müşteri verisini yenilemek yönetici işidir."})
        out = call(svc.run_night, engine, tenant)
        audit(engine, user, "run", "musteri_tur", None, "Müşteri verisi yenilendi", {k: out.get(k) for k in ("accounts", "ms")})
        return out

    # -------------------------------------------------------------- özet ve cariler

    @app.get(f"{P}/overview")
    def musteri_overview(request: Request, temsilci: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        owner = owner_of(user, temsilci)
        rows = M.account_rows(engine, tenant, owner)
        codes = None if owner is None else {r["cari_kodu"] for r in rows}
        acts = M.list_actions(engine, tenant, codes=codes, person=user if owner == user else "")
        hist = M.score_history(engine, tenant, 400)
        run = M.meta_get(engine, tenant, "run")
        out = M.overview(rows, acts, hist[-1] if hist else None)
        return {**out, "asof": run.get("asof"), "kesim": run.get("kesim"), "kapsam": "herkes" if owner is None else owner}

    @app.get(f"{P}/accounts")
    def musteri_accounts(request: Request, kanal: str = "", bolge: str = "", temsilci: str = "", risk: str = "",
                         segment: str = "", q: str = "", sort: str = "oncelik", p: int = 1, size: int = 50) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        rows = M.filter_rows(M.account_rows(engine, tenant, owner_of(user, temsilci)), kanal=kanal, bolge=bolge,
                             risk_=risk, q=q, segment=segment)
        rows.sort(key=M.SORTS.get(sort, M.SORTS["oncelik"]))
        items, pg = page([M.card(r) for r in rows], p, size)
        return {"items": items, **pg, "toplam": {"net12": round(sum(num(r.get("net_12ay")) for r in rows), 2),
                                                 "riskli": sum(1 for r in rows if r.get("risk_duzeyi") in ("yuksek", "kayip"))}}

    @app.get(f"{P}/accounts/export.csv")
    def musteri_accounts_csv(request: Request, kanal: str = "", bolge: str = "", temsilci: str = "", risk: str = "",
                             segment: str = "", q: str = "", sort: str = "oncelik") -> Response:
        engine, tenant, user, _ = ctx(request)
        rows = M.filter_rows(M.account_rows(engine, tenant, owner_of(user, temsilci)), kanal=kanal, bolge=bolge,
                             risk_=risk, q=q, segment=segment)
        rows.sort(key=M.SORTS.get(sort, M.SORTS["oncelik"]))
        audit(engine, user, "run", "musteri_disa", None, "Cari listesi dışa aktarıldı",
              {"satir": len(rows), "kanal": kanal, "bolge": bolge, "risk": risk, "temsilci": temsilci})
        return Response(M.accounts_csv(rows), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="cariler.csv"'})

    @app.get(f"{P}/accounts/{{code}}")
    def musteri_account(code: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return call(svc.detail, engine, tenant, user, code, all_scope(user), is_admin(user), fresh())

    @app.get(f"{P}/accounts/{{code}}/monthly")
    def musteri_account_monthly(code: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        row = call(M.in_scope, engine, tenant, user, code, all_scope(user))
        return call(svc.monthly, engine, tenant, row, fresh())

    @app.post(f"{P}/accounts/{{code}}/summary")
    def musteri_account_summary(code: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        row = call(M.in_scope, engine, tenant, user, code, all_scope(user))
        out = call(svc.summary, engine, tenant, row)
        audit(engine, user, "run", "musteri_ozet", code, "Zeki AI risk nedeni özeti", {"kaynak": out["kaynak"]})
        return out

    @app.get(f"{P}/accounts/{{code}}/phone")
    def musteri_account_phone(code: str, request: Request) -> dict[str, Any]:
        """Arama için telefon: yalnız carinin portföy sahibi temsilcisine (KVKK); her okuma değişiklik kaydına düşer."""
        engine, tenant, user, _ = ctx(request)
        row = call(M.in_scope, engine, tenant, user, code, False)
        tel = call(svc.phone, row)
        audit(engine, user, "run", "musteri_telefon", code, "Cari telefonu görüntülendi", None)
        return {"code": code, "telefon": tel}

    @app.post(f"{P}/accounts/{{code}}/actions", status_code=201)
    def musteri_action_add(code: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        row = call(M.in_scope, engine, tenant, user, code, all_scope(user))
        out = call(M.add_action, engine, tenant, user, row, body)
        audit(engine, user, "create", "musteri_aksiyon", out["id"], row.get("ad") or code,
              {"tur": out["tur"], "sahip": out["sahip"], "termin": out["termin"], "risk": out["riskDuzeyi"]})
        return out

    @app.get(f"{P}/actions")
    def musteri_actions(request: Request, durum: str = "", temsilci: str = "", musteri: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        owner = owner_of(user, temsilci)
        codes = None if owner is None else {r["cari_kodu"] for r in M.account_rows(engine, tenant, owner)}
        rows = M.list_actions(engine, tenant, codes=codes, code=musteri, durum=durum, person=user if owner == user else "")
        return {"items": [M._action_out(a) for a in rows], "etki": M.action_effect(rows)}

    @app.patch(f"{P}/actions/{{aid}}")
    def musteri_action_update(aid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out, diff = call(M.update_action, engine, tenant, user, aid, body, all_scope(user))
        if diff:
            audit(engine, user, "update", "musteri_aksiyon", aid, out.get("cariAd") or out["code"], diff)
        return out

    @app.get(f"{P}/my-portfolio")
    def musteri_my_portfolio(request: Request, q: str = "") -> dict[str, Any]:
        """Temsilcinin kendi carileri (telefon): risk × değer sırası; yetkisi olsa da yalnız kendi portföyü."""
        engine, tenant, user, _ = ctx(request)
        rows = M.filter_rows(M.account_rows(engine, tenant, user), q=q)
        rows.sort(key=M.SORTS["oncelik"])
        acts = M.list_actions(engine, tenant, codes={r["cari_kodu"] for r in rows}, durum="acik", person=user)
        run = M.meta_get(engine, tenant, "run")
        week = [r for r in rows if r.get("risk_duzeyi") in ("yuksek", "kayip")]
        return {"asof": run.get("asof"), "kesim": run.get("kesim"), "count": len(rows), "buHafta": len(week),
                "items": [M.card(r) for r in rows], "acikAksiyon": [M._action_out(a) for a in acts]}

    # -------------------------------------------------------------- veri sağlığı

    @app.get(f"{P}/health")
    def musteri_health(request: Request, tur: str = "", durum: str = "acik-hepsi", onem: str = "", q: str = "",
                       p: int = 1, size: int = 50) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        if tur == "guvenlik" and not security(user):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Güvenlik bulgularını görme yetkiniz yok."})
        st = settings()
        rows = M.list_findings(engine, tenant, tur=tur, durum=durum, onem=onem, q=q, security=security(user))
        items, pg = page([M._finding_out(r, st["crmUrl"]) for r in rows], p, size)
        hist = M.score_history(engine, tenant, 400)
        info = M.meta_get(engine, tenant, "health")
        return {"items": items, **pg, "sayilar": M.finding_counts(engine, tenant, security(user)),
                "puan": hist[-1] if hist else None, "onceki": hist[-2] if len(hist) > 1 else None,
                "veriDurumu": info.get("veriDurumu"), "crmKanal": info.get("crmKanal"), "kisi": info.get("kisi"),
                "zeki": info.get("zeki"), "tarih": info.get("tarih"), "warnings": (M.meta_get(engine, tenant, "run").get("warnings") or [])}

    @app.get(f"{P}/health/export.csv")
    def musteri_health_csv(request: Request, tur: str = "", durum: str = "acik-hepsi", onem: str = "", q: str = "") -> Response:
        """«CRM'de düzeltilecek» listesi (CRM'e elle işlenir; portal CRM'e yazmaz)."""
        engine, tenant, user, _ = ctx(request)
        if tur == "guvenlik" and not security(user):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Güvenlik bulgularını görme yetkiniz yok."})
        rows = M.list_findings(engine, tenant, tur=tur, durum=durum, onem=onem, q=q, security=security(user))
        audit(engine, user, "run", "musteri_disa", None, "CRM'de düzeltilecek listesi dışa aktarıldı", {"satir": len(rows), "tur": tur})
        return Response(M.findings_csv(rows), media_type="text/csv; charset=utf-8",
                        headers={"Content-Disposition": 'attachment; filename="crm-duzeltilecek.csv"'})

    @app.post(f"{P}/health/{{fid}}/mark")
    def musteri_health_mark(fid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out, diff = call(M.mark_finding, engine, tenant, user, fid, body, security(user))
        audit(engine, user, "update", "musteri_bulgu", fid, out.get("ad") or out["kayit"], diff)
        return out

    @app.get(f"{P}/health/score-history")
    def musteri_health_history(request: Request, gun: int = 365) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return {"items": M.score_history(engine, tenant, max(1, min(3650, int(gun))))}

    @app.get(f"{P}/segments")
    def musteri_segments(request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return {"items": M.list_segments(engine, tenant), "kural": "Değer dilimi: son 12 ay net alıma göre sıralı carilerin "
                "birikimli payının ilk %80'i A, sonraki %15'i B, kalanı C. Eğilim: önceki 12 aya göre %10'dan çok artış "
                "büyüyen, düşüş düşen; önceki 12 ayda alımı yoksa yeni."}

    return svc
