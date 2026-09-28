"""M51 Müşteri hizmetleri uçları: /api/v1/support/*.

Portal ekranı `/timas/musteri-destek` (sayfa `sayfa:musteri-destek`, `access.RULES`). İşlem yetkileri:

- `ozellik:destek.baglam` (**açıkça verilir**, kişisel veri + sipariş): müşteri bağlamı ve bayi görünümü. Ayrıca kişinin
  veri alanı: kimlik eşleşmesi `cari`, sipariş/sevkiyat/kargo/fatura `satis` (Yetki Aşama C) — uç içinde denetlenir.
- `ozellik:destek.oneri` (`FEATURE_RULES`): Zeki AI sınıflama, cevap taslağı, sınıf düzeltme, taslak sonucu (model harcar).
- `ozellik:destek.sss` (açıkça): SSS maddesini düzeltme/onaylama. `ozellik:destek.herkesinki` (açıkça): bütün kuyruk ve
  temsilci kırılımı. `ozellik:destek.ayar` (açıkça): sınıf listesi ve SLA/yükseltme kuralları.

**Destek masası paneli** (`/api/v1/support/panel/*`): NanobaseAI Destek'in temsilci ekranı bağlamı sunucudan sunucuya
ister (çerezsiz). nginx `…/destek-baglam/v1/` konumu Bearer anahtarını denetler ve köprünün çağıran jetonunu ekler; uç
ayrıca `X-Destek-Agent` başlığındaki temsilcinin (AD hesap adı) portal yetkisini ve veri alanlarını uygular — panel,
temsilcinin portalda göremeyeceği hiçbir şeyi göremez. Ayrıntı ve örnek: `docs/analiz/M51-destek-paneli-baglam-ucu.md`.

Zamanlayıcı `timas-support.timer` 5 dk'da bir `POST /api/v1/support/classify/run-due`, gece `POST /api/v1/support/run-due`.
Masaya, CRM'e, Logo'ya ve T-soft'a yazılmaz; müşteriye hiçbir şey gönderilmez (taslağı temsilci kendisi gönderir).
"""
from __future__ import annotations

import logging
import os
import re
import threading
import time
from datetime import date, datetime, timedelta
from typing import Any, Callable, Optional

import sqlalchemy as sa
from fastapi import HTTPException, Query, Request

from semantic_bridge import support as S
from semantic_bridge import support_sources as src
from semantic_bridge.field_sales_sources import SourceError, text

log = logging.getLogger("semantic.support.api")
P = "/api/v1/support"

#: Ekrandaki «Zeki AI'ya sor» örnekleri (Zeki AI sohbeti bütün modüllerin sorularını kapsar; 2026-09-28 kararı).
ZEKI_QUESTIONS = [
    "SLA'sı bugün dolacak kaç talep var, kimde?",
    "Bu hafta en çok hangi konuda şikâyet geldi?",
    "Geçen aya göre ilk yanıt süremiz nasıl?",
    "Hasarlı ürün şikâyetleri hangi kargo firmasında yoğunlaşıyor?",
    "Bu bayinin risk limiti onayı bekleyen kaç siparişi var?",
    "Hangi SSS maddesini yazarsak en çok talep azalır?",
]

F_BAGLAM, F_ONERI, F_SSS, F_ALL, F_AYAR = ("ozellik:destek.baglam", "ozellik:destek.oneri", "ozellik:destek.sss",
                                           "ozellik:destek.herkesinki", "ozellik:destek.ayar")


def _embedder() -> Optional[Callable[[list[str]], list[list[float]]]]:
    url = os.environ.get("BI_EMBED_URL", "").strip()
    if not url:
        return None
    from semantic_layer.runtime.table_router import embed_request

    key = os.environ.get("BI_EMBED_API_KEY") or os.environ.get("CONTRACT_API_KEY", "")
    timeout = float(os.environ.get("SUPPORT_EMBED_TIMEOUT_SEC", "20") or 20)
    return lambda texts: embed_request(url, texts, key, timeout)


class Service:
    """Sınıflama turu, SSS dizini, gece özeti. Kaynak okuması `S.Source`."""

    def __init__(self, source: S.Source, settings: Callable[[], dict[str, Any]], llm: Callable[[Optional[int]], Any]):
        self.source, self.settings, self.llm = source, settings, llm
        self.faq = S.FaqIndex(_embedder())
        self._run = threading.Lock()
        self._agents: tuple[float, dict[str, str]] = (0.0, {})

    def destek(self) -> src.DestekClient:
        return self.source.destek(self.settings())

    # -------------------------------------------------------------- SSS dizini

    def load_faq(self, engine: Any, tenant: str, force: bool = False) -> dict[str, Any]:
        st = self.settings()
        warn = []
        arts, crm = [], []
        client = self.destek()
        if client.configured:
            try:
                arts = client.articles()
            except src.DestekError as e:
                warn.append(f"Destek masası makaleleri okunamadı: {e}")
        try:
            crm = self.source.crm(lambda run: run(src.crm_knowledge_sql(st["schema"])))
        except Exception as e:  # noqa: BLE001
            warn.append("CRM bilgi bankası okunamadı.")
            log.info("support: CRM bilgi bankası okunamadı: %s", e)
        self.faq.load(S.faq_items(arts, crm, S.approved_faq(engine, tenant), st["destekLink"]), force=force)
        return {"items": self.faq.size, "warnings": warn}

    def match_faq(self, engine: Any, tenant: str, query: str) -> dict[str, Any]:
        if not self.faq.size:
            self.load_faq(engine, tenant)
        return self.faq.match(query, self.settings())

    # -------------------------------------------------------------- sınıflama

    def classify_ticket(self, engine: Any, tenant: str, ticket: dict[str, Any], priority: Optional[int]) -> dict[str, Any]:
        st = self.settings()
        classes = S.list_classes(engine, tenant, active_only=True)
        body = ticket.get("description") or ""
        res = S.classify(self.llm(priority), text(ticket.get("subject")) or "", body, classes, st)
        faq = self.match_faq(engine, tenant, f"{ticket.get('subject') or ''}\n{src.clean_html(body)}")
        S.upsert_insight(engine, tenant, str(ticket["name"]), **S.classification_values(res, faq, ticket))
        return {**res, "faq": faq}

    def run_due(self, engine: Any, tenant: str) -> dict[str, Any]:
        """Masada yeni/güncellenen talepleri sırayla (değişme zamanına göre) okur, sınıflanmamışları arka plan
        önceliğiyle sınıflar. Süre `SUPPORT_BATCH_SECONDS`; biten iş sonraki tura kalır, imleç yalnız işlenen talebe ilerler."""
        if not self._run.acquire(blocking=False):
            return {"skipped": "başka bir sınıflama turu sürüyor"}
        try:
            st = self.settings()
            client = self.destek()
            if not client.configured:
                return {"skipped": "destek masası bağlantısı ayarlanmamış"}
            from semantic_layer.runtime.llm_queue import BATCH

            if self.llm(BATCH) is None:
                return {"skipped": "Zeki AI bağlı değil"}
            cur = S.meta_get(engine, tenant, "cursor")
            since = cur.get("modified") or (datetime.now() - timedelta(days=st["gapDays"])).strftime("%Y-%m-%d %H:%M:%S")
            tickets = client.tickets(modified_since=since, with_description=True)
            have = S.insights_for(engine, tenant, [t.get("name") for t in tickets])
            t0 = time.monotonic()
            done = unsure = skipped = 0
            last = since
            stop = None
            self.load_faq(engine, tenant)
            for t in tickets:
                if time.monotonic() - t0 > st["batchSeconds"]:
                    stop = "süre doldu"
                    break
                ref = str(t.get("name"))
                if ref in have and have[ref].get("klassMethod"):
                    skipped += 1
                    last = str(t.get("modified") or last)
                    continue
                try:
                    res = self.classify_ticket(engine, tenant, t, BATCH)
                except S.SupportError as e:
                    stop = str(e)
                    break
                except Exception as e:  # noqa: BLE001 — model yanıt vermedi: imleç ilerlemez, sonra denenir
                    log.warning("support: %s sınıflanamadı: %s", ref, e)
                    stop = "Zeki AI yanıt vermedi"
                    break
                done += 1
                unsure += 0 if res["klass"] else 1
                last = str(t.get("modified") or last)
            S.meta_set(engine, tenant, "cursor", {"modified": last})
            info = {"read": len(tickets), "classified": done, "unsure": unsure, "alreadyDone": skipped,
                    "remaining": len(tickets) - done - skipped, "stop": stop, "ms": int((time.monotonic() - t0) * 1000)}
            S.meta_set(engine, tenant, "classify", info)
            return info
        finally:
            self._run.release()

    def run_night(self, engine: Any, tenant: str) -> dict[str, Any]:
        """Gece: SSS dizinini tazeler, SSS açığı listesini yeniden sayar."""
        st = self.settings()
        faq = self.load_faq(engine, tenant, force=True)
        since = S.today() - timedelta(days=st["gapDays"])
        with engine.connect() as c:
            rows = [S.insight_row(r) for r in c.execute(sa.select(S.INSIGHTS).where(
                S.INSIGHTS.c.tenant_id == tenant, S.INSIGHTS.c.opened_on >= since))]
        gaps = S.refresh_gaps(engine, tenant, rows, S.list_classes(engine, tenant), st, since)
        info = {"faq": faq, "gaps": gaps, "insights": len(rows)}
        S.meta_set(engine, tenant, "night", info)
        return info

    # -------------------------------------------------------------- temsilci eşlemesi (masa kullanıcısı ↔ AD hesabı)

    def agent_emails(self, user: str) -> set[str]:
        """Portal kullanıcısının (AD hesap adı) masadaki e-posta(lar)ı. Masa kullanıcılarının `username` alanı AD hesap
        adıdır (AD girişi); okunamazsa e-postanın @ öncesi hesap adıyla karşılaştırılır (**ölçülecek**)."""
        at, cache = self._agents
        if time.time() - at > 900:
            try:
                rows = self.destek()._all("User", ("name", "username"), [["user_type", "=", "System User"]], "name asc")
                cache = {str(r.get("name")).lower(): str(r.get("username") or "").lower() for r in rows}
            except Exception as e:  # noqa: BLE001
                log.info("support: masa kullanıcıları okunamadı: %s", e)
                cache = {}
            self._agents = (time.time(), cache)
        u = (user or "").lower()
        out = {e for e, name in cache.items() if name == u}
        return out

    def mine(self, t: dict[str, Any], user: str, emails: set[str]) -> bool:
        u = (user or "").lower()
        for a in src.assignees(t):
            a = a.lower()
            if a in emails or a.split("@")[0] == u:
                return True
        return False


def register(app: Any, deps: dict[str, Any]) -> Service:
    """app.py'de bağlanır. `deps`: auth(request) → (engine, tenant, user, display) · require_caller(request) ·
    can(user, key) · is_admin(user) · audit(...) · conf(key, default) · crm_connect() / logo_connect() →
    salt okunur bağlantı · llm(priority) → LLM kapısı istemcisi ya da None · engine() / tenant() → oturumsuz uçlar için."""
    from semantic_bridge import access as access_mod

    auth, require_caller, can, is_admin, audit, conf = (deps[k] for k in ("auth", "require_caller", "can", "is_admin", "audit", "conf"))
    settings = lambda: S.settings_from(conf)  # noqa: E731

    def make_client(st: dict[str, Any]) -> src.DestekClient:
        return src.DestekClient(st["destekBase"], st["destekKey"], st["destekSecret"], verify=st["destekVerify"])

    svc = Service(S.Source(deps["crm_connect"], deps["logo_connect"], make_client), settings, deps["llm"])

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        engine, tenant, user, display = auth(request)
        S.ensure(engine)
        return engine, tenant, user, display

    def system() -> tuple[Any, str]:
        engine, tenant = deps["engine"](), deps["tenant"]()
        S.ensure(engine)
        return engine, tenant

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except S.SupportError as e:
            raise HTTPException(status_code=e.status, detail={"code": "SUPPORT" if e.status != 403 else "FORBIDDEN",
                                                              "message": str(e)}) from e
        except src.DestekError as e:
            raise HTTPException(status_code=503, detail={"code": "DESTEK_UNAVAILABLE", "message": str(e)}) from e
        except SourceError as e:
            raise HTTPException(status_code=422 if "geçersiz" in str(e) or "gerekli" in str(e) or "en az" in str(e) else 503,
                                detail={"code": "DATA_SOURCE", "message": str(e)}) from e
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001 — kaynak düştüyse kişiye düz cümle, ayrıntı günlükte
            log.exception("support: istek başarısız")
            state = str(getattr(e, "args", [""])[0])
            if state in ("08S01", "08001", "HYT00", "HYT01") or "timeout" in str(e).lower():
                raise HTTPException(status_code=503, detail={"code": "DATA_SOURCE_UNAVAILABLE", "retryable": True,
                                    "message": "CRM ya da Logo şu anda yanıt vermiyor; birazdan tekrar deneyin."}) from e
            raise HTTPException(status_code=502, detail={"code": "SUPPORT", "message": "Müşteri hizmetleri verisi okunamadı."}) from e

    def flag(user: str, key: str) -> bool:
        return is_admin(user) or can(user, key)

    def need(user: str, key: str, what: str) -> None:
        if not flag(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def domains_of(user: str) -> Optional[frozenset[str]]:
        return None if is_admin(user) else access_mod.allowed_for(user)

    def tickets_by(email: str) -> list[dict[str, Any]]:
        client = svc.destek()
        if not client.configured:
            return []
        st = settings()
        rows = client.tickets(raised_by=email.strip().lower())
        return [{"ref": t.get("name"), "subject": text(t.get("subject")), "status": t.get("status"),
                 "category": t.get("status_category"), "opened": src.day(t.get("opening_date")),
                 "url": f"{st['destekLink']}/helpdesk/tickets/{t.get('name')}" if st["destekLink"] else None} for t in rows]

    def read_context(engine: Any, tenant: str, user: str, q: dict[str, Optional[str]]) -> dict[str, Any]:
        st = settings()
        email = (q.get("email") or "").strip() or None
        ticket = (q.get("ticket") or "").strip() or None
        if ticket and not email:
            t = svc.destek().ticket(ticket)
            email = text(t.get("raised_by"))
            if not q.get("order"):
                refs = S.order_refs(f"{t.get('subject') or ''}\n{t.get('description') or ''}")
                q = {**q, "orderHints": ",".join(refs)}
        out = S.context(svc.source, st, email=email, phone=q.get("phone") or None, order=q.get("order") or None,
                        account=q.get("account") or None, code=q.get("code") or None, domains=domains_of(user),
                        tickets=tickets_by)
        if q.get("orderHints"):
            out["orderHints"] = [x for x in (q["orderHints"] or "").split(",") if x]
        acc = out.get("account") or {}
        audit(engine, user, "read", "support_context", acc.get("id") or q.get("order") or ticket,
              acc.get("unvan") or "Müşteri bağlamı",
              {"by": [k for k in ("email", "phone", "order", "account", "code", "ticket") if q.get(k) or (k == "email" and email)],
               "orders": len(out.get("orders") or []), "choice": out.get("needsChoice")})
        return out

    # -------------------------------------------------------------- genel

    @app.get(f"{P}/meta")
    def support_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        st = settings()
        doms = domains_of(user)
        return {
            "me": {"username": user, "display": display, "admin": is_admin(user),
                   "canContext": flag(user, F_BAGLAM), "canSuggest": flag(user, F_ONERI), "canFaq": flag(user, F_SSS),
                   "canAll": flag(user, F_ALL), "canSettings": flag(user, F_AYAR),
                   "dataCari": doms is None or "cari" in doms, "dataSatis": doms is None or "satis" in doms},
            "destek": {"configured": bool(st["destekBase"] and st["destekKey"] and st["destekSecret"]),
                       "link": st["destekLink"] or None},
            "classes": S.list_classes(engine, tenant),
            "urgency": list(S.URGENCY),
            "gapStates": [{"key": k, "label": S.GAP_LABEL[k]} for k in S.GAP_STATES],
            "settings": {k: st[k] for k in ("orderDays", "logoMonths", "classifyMinProb", "classifyMinMargin", "slaWarnRatio",
                                             "repeatDays", "gapDays", "gapMinTickets", "cargoMatch")},
            "runs": {k: S.meta_get(engine, tenant, k) for k in ("classify", "night")},
            "zekiQuestions": ZEKI_QUESTIONS,
            "factKeys": S.FACT_KEYS,
        }

    @app.post(f"{P}/classify/run-due")
    def support_classify_due(request: Request) -> dict[str, Any]:
        """Zamanlayıcı (5 dk): masadaki yeni talepleri sınıflar."""
        require_caller(request)
        engine, tenant = system()
        return call(svc.run_due, engine, tenant)

    @app.post(f"{P}/run-due")
    def support_night_due(request: Request) -> dict[str, Any]:
        """Zamanlayıcı (gece): SSS dizini ve SSS açığı listesi."""
        require_caller(request)
        engine, tenant = system()
        return call(svc.run_night, engine, tenant)

    # -------------------------------------------------------------- bağlam ve bayi

    @app.get(f"{P}/context")
    def support_context(request: Request, email: str = "", phone: str = "", order: str = "", account: str = "",
                        code: str = "", ticket: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_BAGLAM, "Müşteri bağlamını görme yetkisi")
        return call(read_context, engine, tenant, user, {"email": email, "phone": phone, "order": order,
                                                         "account": account, "code": code, "ticket": ticket})

    @app.get(f"{P}/dealers")
    def support_dealers(request: Request, q: str = "", offset: int = 0, size: int = 25) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_BAGLAM, "Bayi görünümü yetkisi")
        doms = domains_of(user)
        if doms is not None and "cari" not in doms:
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN",
                                "message": "Bayi araması «Cari ve tahsilat» verisine dayanıyor; bu veri rolünüzde yok."})
        st = settings()
        size = max(1, min(100, int(size)))

        def read() -> dict[str, Any]:
            rows = svc.source.crm(lambda run: run(src.crm_account_search_sql(st["schema"], q, offset, size, st["dealerChannels"])))
            items = [S._account(r) for r in rows[:size]]
            return {"items": items, "offset": offset, "size": size, "hasMore": len(rows) > size,
                    "nextOffset": offset + size if len(rows) > size else None}

        return call(read)

    @app.get(P + "/dealer/{account}")
    def support_dealer(account: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_BAGLAM, "Bayi görünümü yetkisi")
        out = call(S.dealer, svc.source, settings(), account, domains=domains_of(user))
        acc = out.get("account") or {}
        audit(engine, user, "read", "support_dealer", acc.get("id"), acc.get("unvan") or "Bayi görünümü",
              {"open": len(out.get("open") or []), "risk": len(out.get("risk") or [])})
        return out

    # -------------------------------------------------------------- Zeki AI

    @app.post(f"{P}/classify")
    def support_classify(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """Tek talep ya da serbest metin: konu + aciliyet + SSS. Talep numarasıyla gelirse sonuç kaydedilir."""
        engine, tenant, user, _ = ctx(request)
        from semantic_layer.runtime.llm_queue import INTERACTIVE

        ref = str(body.get("ticket") or "").strip()
        if ref:
            t = call(svc.destek().ticket, ref)
            if not t:
                raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Talep bulunamadı."})
            out = call(svc.classify_ticket, engine, tenant, t, INTERACTIVE)
            return {**out, "ticket": ref, "insight": S.get_insight(engine, tenant, ref)}
        subject, body_text = str(body.get("subject") or ""), str(body.get("text") or "")
        if not (subject.strip() or body_text.strip()):
            raise HTTPException(status_code=422, detail={"code": "INVALID", "message": "Talep numarası ya da metin gerekli."})
        classes = S.list_classes(engine, tenant, active_only=True)
        res = call(S.classify, svc.llm(INTERACTIVE), subject, body_text, classes, settings())
        return {**res, "faq": call(svc.match_faq, engine, tenant, f"{subject}\n{body_text}")}

    @app.get(P + "/insights/{ref}")
    def support_insight(ref: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        return {"insight": S.get_insight(engine, tenant, ref)}

    @app.put(P + "/insights/{ref}/class")
    def support_set_class(ref: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(S.set_class, engine, tenant, ref, user, str(body.get("klass") or ""), body.get("urgency"),
                   S.list_classes(engine, tenant))
        audit(engine, user, "update", "support_class", ref, f"Talep {ref} sınıfı", {"klass": out.get("klass"), "urgency": out.get("urgency")})
        return {"insight": out}

    def make_draft(engine: Any, tenant: str, user: str, ref: str, body: dict[str, Any], with_context: bool) -> dict[str, Any]:
        from semantic_layer.runtime.llm_queue import INTERACTIVE

        st = settings()
        t = svc.destek().ticket(ref)
        if not t:
            raise S.SupportError("Talep bulunamadı.", 404)
        ins = S.get_insight(engine, tenant, ref) or {}
        if not ins.get("klassMethod"):
            svc.classify_ticket(engine, tenant, t, INTERACTIVE)
            ins = S.get_insight(engine, tenant, ref) or {}
        cx: dict[str, Any] = {}
        warn: list[str] = []
        if with_context:
            email = text(t.get("raised_by"))
            order = str(body.get("order") or "").strip() or None
            if not order:
                hints = S.order_refs(f"{t.get('subject') or ''}\n{t.get('description') or ''}")
                order = hints[0] if hints else None
            try:
                cx = S.context(svc.source, st, email=email if not order else None, order=order,
                               account=str(body.get("account") or "").strip() or None, domains=domains_of(user))
                if cx.get("needsChoice"):
                    warn.append("Birden çok cari eşleşti; olgular için bağlam panelinden cari seçin.")
                    cx = {}
            except S.SupportError as e:
                warn.append(str(e))
            except Exception as e:  # noqa: BLE001 — bağlam yoksa olgusuz taslak
                log.info("support: taslak bağlamı okunamadı: %s", e)
                warn.append("Müşteri bağlamı okunamadı; taslak olgusuz yazıldı.")
        else:
            warn.append("Müşteri bağlamı yetkiniz olmadığı için taslak olgusuz yazıldı.")
        faq = ins.get("faq")
        facts = S.facts_from_context(cx, faq) if cx else ({"sss_baslik": faq["matches"][0]["title"]} if faq and faq.get("matches") else {})
        labels = {c["klass"]: c["label"] for c in S.list_classes(engine, tenant)}
        ticket_text = S.model_text(text(t.get("subject")) or "", t.get("description") or "", st["modelChars"])
        llm = svc.llm(INTERACTIVE)
        if llm is None:
            raise S.SupportError("Zeki AI bağlı değil.", 503)
        raw = llm.chat(S.draft_messages(ticket_text, labels.get(ins.get("klass") or ""), facts, faq, st["signature"]))
        filled = S.fill_draft(raw, facts, ticket_text, st["signature"])
        if not filled["text"]:
            raise S.SupportError("Zeki AI kullanılabilir bir taslak yazamadı; yeniden deneyin ya da kendiniz yazın.", 502)
        S.upsert_insight(engine, tenant, ref, draft=filled["text"], draft_facts_json=S._dump(facts),
                         draft_by_model_at=S._now(), draft_by=user, final_sent=None, final_edit_ratio=None)
        audit(engine, user, "run", "support_draft", ref, f"Talep {ref} cevap taslağı",
              {"facts": sorted(facts), "dropped": filled["dropped"]})
        return {"ticket": ref, "draft": filled["text"], "facts": facts, "dropped": filled["dropped"], "used": filled["used"],
                "warnings": warn, "insight": S.get_insight(engine, tenant, ref)}

    @app.post(f"{P}/draft")
    def support_draft(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """Temsilci onaylı cevap taslağı. Hiçbir yere gönderilmez; temsilci düzeltip masadan kendisi gönderir."""
        engine, tenant, user, _ = ctx(request)
        ref = str(body.get("ticket") or "").strip()
        if not ref:
            raise HTTPException(status_code=422, detail={"code": "INVALID", "message": "Talep numarası gerekli."})
        return call(make_draft, engine, tenant, user, ref, body, flag(user, F_BAGLAM))

    @app.post(P + "/drafts/{ref}/outcome")
    def support_outcome(ref: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        """Taslak ne oldu: gönderildi mi, ne kadar değişti (son metin saklanmaz, yalnız oran)."""
        engine, tenant, user, _ = ctx(request)
        if "sent" not in body:
            raise HTTPException(status_code=422, detail={"code": "INVALID", "message": "sent alanı gerekli."})
        final = body.get("finalText")
        return {"insight": call(S.record_outcome, engine, tenant, ref, user, bool(body.get("sent")),
                                str(final) if final is not None else None)}

    # -------------------------------------------------------------- SSS

    @app.get(f"{P}/faq/match")
    def support_faq_match(request: Request, q: str = "", text_: str = Query("", alias="text")) -> dict[str, Any]:
        engine, tenant, _, _ = ctx(request)
        query = (q or text_).strip()
        if len(query) < 3:
            raise HTTPException(status_code=422, detail={"code": "INVALID", "message": "En az 3 karakter yazın."})
        return call(svc.match_faq, engine, tenant, query)

    @app.get(f"{P}/faq/gaps")
    def support_faq_gaps(request: Request, status: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return {"items": S.list_gaps(engine, tenant, status or None), "canEdit": flag(user, F_SSS),
                "night": S.meta_get(engine, tenant, "night")}

    @app.patch(P + "/faq/gaps/{gid}")
    def support_faq_gap_patch(gid: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_SSS, "SSS maddesini düzeltme ve onaylama yetkisi")
        out = call(S.patch_gap, engine, tenant, gid, user, body)
        audit(engine, user, "update", "support_faq", gid, out.get("question") or out.get("label"),
              {"status": out.get("status")})
        return out

    # -------------------------------------------------------------- kuyruk ve kalite

    @app.get(f"{P}/queue")
    def support_queue(request: Request, scope: str = "mine") -> dict[str, Any]:
        """Açık talepler SLA'ya göre sıralı (aşılan, yaklaşan, içinde, SLA'sız). Yetkisiz kişi yalnız kendine atananları
        ve atanmamışları görür."""
        engine, tenant, user, _ = ctx(request)
        st = settings()
        client = svc.destek()
        if not client.configured:
            return {"configured": False, "items": []}
        rows = call(client.open_tickets)
        all_ = flag(user, F_ALL) and scope == "all"
        emails = svc.agent_emails(user)
        if not all_:
            rows = [t for t in rows if svc.mine(t, user, emails) or not src.assignees(t)]
        now = datetime.now()
        ins = S.insights_for(engine, tenant, [t.get("name") for t in rows])
        order = {"asildi": 0, "yaklasiyor": 1, "icinde": 2, None: 3}
        items = []
        for t in rows:
            state = S.sla_state(t, now, st["slaWarnRatio"])
            due = src.parse_dt(t.get("resolution_by") if t.get("first_responded_on") else t.get("response_by"))
            i = ins.get(str(t.get("name"))) or {}
            items.append({"ref": t.get("name"), "subject": text(t.get("subject")), "status": t.get("status"),
                          "priority": t.get("priority"), "team": t.get("agent_group"), "opened": src.day(t.get("opening_date")),
                          "sla": state, "due": due.isoformat() if due else None, "assigned": src.assignees(t),
                          "mine": svc.mine(t, user, emails), "klass": i.get("klass"), "klassGuess": i.get("klassGuess"),
                          "urgency": i.get("urgency"), "hasDraft": bool(i.get("draft")),
                          "url": f"{st['destekLink']}/helpdesk/tickets/{t.get('name')}" if st["destekLink"] else None})
        items.sort(key=lambda x: (order.get(x["sla"], 3), x["due"] or "9999", x["opened"] or ""))
        return {"configured": True, "scope": "all" if all_ else "mine", "items": items, "agentMapped": bool(emails)}

    @app.get(f"{P}/quality")
    def support_quality(request: Request, frm: str = Query("", alias="from"), to: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        st = settings()
        client = svc.destek()
        if not client.configured:
            return {"configured": False}
        t_end = _day_arg(to) or S.today()
        t_start = _day_arg(frm) or (t_end - timedelta(days=29))
        if t_start > t_end:
            raise HTTPException(status_code=422, detail={"code": "INVALID", "message": "Başlangıç bitişten sonra olamaz."})
        span = (t_end - t_start).days + 1
        p_end, p_start = t_start - timedelta(days=1), t_start - timedelta(days=span)

        def read() -> dict[str, Any]:
            cur = client.tickets(opened_from=t_start.isoformat(), opened_to=t_end.isoformat())
            prev = client.tickets(opened_from=p_start.isoformat(), opened_to=p_end.isoformat())
            open_now = client.open_tickets()
            ins = S.insights_for(engine, tenant, [t.get("name") for t in cur + prev])
            out = S.quality(cur, prev, open_now, ins, S.list_classes(engine, tenant), t_start, t_end, datetime.now(), st,
                            per_agent=flag(user, F_ALL))
            out["previousWindow"] = {"from": p_start.isoformat(), "to": p_end.isoformat()}
            out["configured"] = True
            return out

        return call(read)

    # -------------------------------------------------------------- sınıf ve SLA ayarı

    @app.get(f"{P}/classes")
    def support_classes(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return {"items": S.list_classes(engine, tenant), "canEdit": flag(user, F_AYAR)}

    @app.put(P + "/classes/{klass}")
    def support_class_put(klass: str, request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, F_AYAR, "Sınıf ve SLA ayarı yetkisi")
        out = call(S.save_class, engine, tenant, user, klass, body)
        audit(engine, user, "update", "support_class_def", klass, out.get("label"),
              {k: out.get(k) for k in ("active", "slaFirstHours", "slaResolveHours", "escalateTo")})
        return out

    # -------------------------------------------------------------- destek masası paneli (sunucudan sunucuya)

    def panel_agent(request: Request, key: str) -> tuple[Any, str, str]:
        """Panel isteği: çağıran jetonu (nginx ekler) + isteğe bağlı panel anahtarı + temsilcinin AD hesap adı. Temsilcinin
        portaldaki sayfa ve işlem yetkisi burada uygulanır; veri alanları `read_context` içinde."""
        require_caller(request)
        want = (conf("DESTEK_PANEL_TOKEN", "") or "").strip()
        if want:
            import hmac

            if not hmac.compare_digest(request.headers.get("x-destek-panel-key", ""), want):
                raise HTTPException(status_code=401, detail={"code": "UNAUTHORIZED", "message": "Panel anahtarı gerekli."})
        agent = (request.headers.get("x-destek-agent") or "").strip().lower()
        if not re.match(r"^[a-z0-9._\-]{1,64}$", agent):
            raise HTTPException(status_code=422, detail={"code": "INVALID",
                                "message": "X-Destek-Agent başlığında temsilcinin AD hesap adı olmalı (e-posta değil)."})
        engine, tenant = system()
        if not (is_admin(agent) or (can(agent, "sayfa:musteri-destek") and can(agent, key))):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Bu temsilcinin portalda bu yetkisi yok."})
        return engine, tenant, agent

    @app.get(f"{P}/panel/context")
    def support_panel_context(request: Request, ticket: str = "", email: str = "", phone: str = "", order: str = "",
                              account: str = "") -> dict[str, Any]:
        engine, tenant, agent = panel_agent(request, F_BAGLAM)
        return call(read_context, engine, tenant, agent, {"ticket": ticket, "email": email, "phone": phone, "order": order,
                                                          "account": account})

    @app.get(f"{P}/panel/insight")
    def support_panel_insight(request: Request, ticket: str) -> dict[str, Any]:
        engine, tenant, agent = panel_agent(request, F_ONERI)
        ins = S.get_insight(engine, tenant, ticket)
        labels = {c["klass"]: c["label"] for c in S.list_classes(engine, tenant)}
        return {"insight": ins, "klassLabel": labels.get((ins or {}).get("klass") or ""),
                "guessLabel": labels.get((ins or {}).get("klassGuess") or "")}

    @app.post(f"{P}/panel/draft")
    def support_panel_draft(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, agent = panel_agent(request, F_ONERI)
        ref = str(body.get("ticket") or "").strip()
        if not ref:
            raise HTTPException(status_code=422, detail={"code": "INVALID", "message": "Talep numarası gerekli."})
        return call(make_draft, engine, tenant, agent, ref, body, flag(agent, F_BAGLAM))

    return svc


def _day_arg(v: str) -> Optional[date]:
    v = (v or "").strip()
    if not v:
        return None
    try:
        return date.fromisoformat(v[:10])
    except ValueError:
        raise HTTPException(status_code=422, detail={"code": "INVALID", "message": "Tarih YYYY-AA-GG olmalı."}) from None
