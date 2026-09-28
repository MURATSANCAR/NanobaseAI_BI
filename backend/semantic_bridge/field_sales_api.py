"""M30 Saha satış ve tahsilat uçları: /api/v1/field/*.

Sayfa kapısı `access.RULES` (`sayfa:saha`; ortak ziyaret uçları `sayfa:okul-tanitim` ile de açık). Ziyaret notu ve ödeme
planı taslağı `ozellik:saha.not`, müdür önceliği `ozellik:saha.oncelik-duzenle` (`FEATURE_RULES`); kapsam
`ozellik:saha.herkesinki`, ödeme planı onayı `ozellik:saha.odeme-plani-onay`, temsilci karşılaştırması
`ozellik:saha.performans` açıkça verilir ve burada denetlenir. Zamanlayıcı (`timas-field.timer`) yalnız
`POST /api/v1/field/run-due?tur=gece|hafif|haftalik` çağırır.

CRM'e ve Logo'ya yazılmaz; e-posta yalnız iç alıcılara (haftalık rapor, finans özeti) ve ayar doluysa gider; müşteriye
giden hiçbir şey otomatik gönderilmez (takip e-postası taslaktır, temsilci kendi gönderir).
"""
from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

import sqlalchemy as sa
from fastapi import HTTPException, Request
from fastapi.responses import Response

from semantic_bridge import field_sales as F
from semantic_bridge import field_sales_kaynak as K
from semantic_bridge import field_sales_sources as src
from semantic_bridge import provenance as PV
from semantic_bridge.field_sales import FieldError
from semantic_bridge.field_sales_sources import SourceError, day, guid, num, text

log = logging.getLogger("semantic.field.api")
P = "/api/v1/field"

#: Ekrandaki «Zeki AI'ya sor» örnekleri (Genel bakış soru kutusuna gider; kapsam soru hattında süzülür).
ZEKI_QUESTIONS = [
    "Bu hafta vadesi 60 günü geçen müşterilerim kimler?",
    "Bölgemde hedefin gerisinde kalan kitaplar hangileri?",
    "Geçen ay reddedilen tahsilatlarımın nedenleri neydi?",
    "Hangi müşterimin çeki bu yıl karşılıksız çıktı?",
    "Ortalama tahsilat süremiz bölgemde kaç gün?",
    "Bu müşteri geçen yıl bu dönemde ne almıştı?",
]


SLOW_WRITE_SECONDS = 2.0


def _slow_write(what: str, t0: float, marks: list[tuple[str, float]]) -> Optional[str]:
    """Kişinin kaydı `SLOW_WRITE_SECONDS`'ı geçtiyse adım adım süreyi günlüğe yazar (hangi adım bekledi görünsün)."""
    total = (marks[-1][1] if marks else time.monotonic()) - t0
    if total < SLOW_WRITE_SECONDS:
        return None
    prev, parts = t0, []
    for name, t in marks:
        parts.append(f"{name} {t - prev:.2f} sn")
        prev = t
    msg = f"field: {what} yavaş ({total:.1f} sn): " + ", ".join(parts)
    log.warning(msg)
    return msg


class Service:
    """Gece/hafif/haftalık turlar ve brifing. Kaynak okuması `F.Source`; tablolar `F.*`."""

    def __init__(self, source: F.Source, settings: Callable[[], dict[str, Any]], llm: Callable[[], Any],
                 send_mail: Callable[[str, str, list[str]], str], link: Callable[[], str]):
        self.source, self.settings, self.llm, self.send_mail, self.link = source, settings, llm, send_mail, link
        self._run = threading.Lock()

    # -------------------------------------------------------------- yardımcılar

    def calendar(self, engine: Any, tenant: str) -> dict[str, Any]:
        run = F.meta_get(engine, tenant, "run")
        if not run.get("firm"):
            raise FieldError("Saha verisi henüz hazırlanmadı: gece turu bir kez koşmalı (Yönetim ya da zamanlayıcı).", 409)
        return run

    def users_map(self, fresh: bool = False) -> dict[str, dict[str, Any]]:
        from semantic_bridge.people import account

        out = {}
        for u in self.source.users(self.settings(), fresh):
            out[guid(u.get("id"))] = {"hesap": account(text(u.get("domain")) or ""), "ad": text(u.get("ad")),
                                      "bmt": bool(num(u.get("bmt"))), "tip": u.get("tip")}
        return out

    def my_ids(self, user: str) -> set[str]:
        return {k for k, v in self.users_map().items() if v["hesap"] == user}

    def accounts_map(self, engine: Any, tenant: str) -> dict[str, dict[str, Any]]:
        with engine.connect() as c:
            rows = c.execute(sa.select(F.PORTFOLIO.c.crm_account_id, F.PORTFOLIO.c.logo_code, F.PORTFOLIO.c.unvan)
                             .where(F.PORTFOLIO.c.tenant_id == tenant, F.PORTFOLIO.c.crm_account_id.isnot(None))).all()
        return {a: {"logo_code": c_, "unvan": u} for a, c_, u in rows}

    def labels(self, engine: Any) -> dict[str, dict[str, Any]]:
        with engine.connect() as c:
            return {r.tahsilat_id: {"etiket": r.etiket, "olasilik": r.olasilik} for r in c.execute(F.labels_stmt())}

    def approved_plan(self, engine: Any, tenant: str, year: int) -> Optional[dict[str, Any]]:
        try:
            from semantic_bridge import budget as B

            B.ensure(engine)
            out = B.approved_targets(engine, tenant, year, with_actuals=False)
            return out if out.get("plan") else None
        except Exception as e:  # noqa: BLE001 — M46 yoksa hedef CRM'den ya da boş
            log.info("field: M46 hedefleri okunamadı: %s", e)
            return None

    # -------------------------------------------------------------- gece turu

    def run_night(self, engine: Any, tenant: str) -> dict[str, Any]:
        if not self._run.acquire(blocking=False):
            return {"skipped": "başka bir saha turu sürüyor"}
        try:
            st = self.settings()
            t0 = time.monotonic()
            # Sorgu bilgisi: turda çalışan CRM/Logo metni tur kaydına yazılır (ekranda köken; cevaplardan ayıklanır).
            with F.recording() as reads:
                data = F.read_all(self.source, st)
            year = data["logo"]["cal"]["year"]
            plan = self.approved_plan(engine, tenant, year)
            portfolio, signals, info = F.build(data, st, plan, F.last_visit_days(engine, tenant))
            now = date.fromisoformat(data["now"])
            # Öncelik puanı gece turunda da yazılır (tahsilat listesi sıralaması, rapor); «Bugün» ekranı canlı yeniden hesaplar.
            rows = [{**p, **s} for p, s in zip(portfolio, signals)]
            promises = F.broken_promises(engine, tenant, {s["logo_code"]: s["son_odeme_tarihi"] for s in signals}, now)
            rejected = F.rejected_by_account(data["crm"]["collections"], now)
            ranked = {r["logo_code"]: r for r in F.ranked(rows, promises=promises, rejected=rejected,
                                                            boosts=F.overrides(engine, tenant, now), last_visits={},
                                                            cycle=st["visitCycleDays"], now=now)}
            for s in signals:
                r = ranked[s["logo_code"]]
                s["oncelik_puani"], s["gerekce_json"] = r["puan"], F._dump(r["gerekce"])
            F.write_snapshot(engine, tenant, portfolio, signals)
            info["ms"] = int((time.monotonic() - t0) * 1000)
            info["firm"], info["prevFirm"] = data["logo"]["cal"]["firm"], data["logo"]["cal"].get("prevFirm")
            F.meta_set(engine, tenant, "run", {**info, "sorgular": reads})
            info["events"] = self._cheque_events(engine, tenant, portfolio, signals)
            info["reasons"] = self._label_reasons(engine, data["crm"]["collections"], now)
            info["summaries"] = self._planned_summaries(engine, tenant, now)
            info["financeMail"] = self._finance_digest(data["crm"]["collections"], st)
            return {"ok": True, **info}
        finally:
            self._run.release()

    def _cheque_events(self, engine: Any, tenant: str, portfolio: list[dict[str, Any]], signals: list[dict[str, Any]]) -> int:
        """Müşterisinin çeki/senedi son 12 ayda karşılıksız ya da protestolu olaya düştüyse temsilciye (bir kez)."""
        n = 0
        by_code = {p["logo_code"]: p for p in portfolio}
        for s in signals:
            ev = int(num(s.get("karsiliksiz_olay_12ay"))) + int(num(s.get("protesto_olay_12ay")))
            p = by_code.get(s["logo_code"]) or {}
            if ev and p.get("ad_hesap"):
                key = f"cek:{s['logo_code']}:{ev}"
                n += F.add_event(engine, tenant, p["ad_hesap"], "cek-olay", key,
                                 f"{p.get('unvan') or s['logo_code']}: son 12 ayda {ev} karşılıksız/protestolu çek-senet",
                                 None, s["logo_code"])
        return n

    def _label_reasons(self, engine: Any, collections: list[dict[str, Any]], now: date) -> dict[str, Any]:
        """Reddedilen tahsilatın serbest metin nedeni (seçim listesi boş ya da «Diğer») kapalı kümeye: `QueuedLlm.choose`
        (her seçeneğin olasılığı). Öneri eşiğinin (p ≥ 0,70, marj ≥ 0,30) altındaki sonuç yazılmaz."""
        llm = self.llm()
        todo = []
        have = set(self.labels(engine))
        since = (now - timedelta(days=30)).isoformat()
        for t in collections:
            if int(num(t.get("durum"))) != src.T_REJECTED or (day(t.get("red_tarihi")) or "") < since:
                continue
            code = int(num(t.get("red_sebep"))) or None
            if code not in (None, 100000003) or not text(t.get("red_metin")) or guid(t.get("id")) in have:
                continue
            todo.append(t)
        if not todo:
            return {"labelled": 0, "waiting": 0}
        if llm is None or not callable(getattr(llm, "choose", None)):
            return {"labelled": 0, "waiting": len(todo), "note": "Zeki AI bağlı değil"}
        done = unsure = 0
        choices = list(F.REASON_CHOICES)
        for t in todo:
            try:
                res = llm.choose(F.reason_prompt(text(t.get("red_metin")) or ""), choices)
            except Exception as e:  # noqa: BLE001
                log.warning("field: red nedeni sınıflanamadı: %s", e)
                break
            if res.choice is None or not res.confident(F.REASON_MIN_PROB, F.REASON_MIN_MARGIN):
                unsure += 1
                continue
            with engine.begin() as c:
                c.execute(F.REASONS.insert().values(tahsilat_id=guid(t.get("id")), etiket=F.REASON_CHOICES[res.choice],
                                                    olasilik=round(float(res.probability or 0), 4), kaynak="zeki", zaman=F._now()))
            done += 1
        return {"labelled": done, "unsure": unsure, "waiting": len(todo) - done - unsure}

    def _planned_summaries(self, engine: Any, tenant: str, now: date) -> dict[str, Any]:
        """Bugün ve yarın planlanan cari ziyaretleri için Zeki AI özetini önceden hazırlar (ölçüt: plan; sayı tavanı yok)."""
        if self.llm() is None:
            return {"ready": 0, "note": "Zeki AI bağlı değil"}
        codes: set[str] = set()
        for d in (now, now + timedelta(days=1)):
            for v in F.list_visits(engine, tenant, "", tur="cari", day_=d.isoformat(), admin=True):
                if v["durum"] == "planlandi":
                    codes.add(v["hedef"])
        ok = 0
        for code in sorted(codes):
            try:
                self.summary(engine, tenant, "sistem", code, all_scope=True)
                ok += 1
            except Exception as e:  # noqa: BLE001
                log.info("field: %s özeti hazırlanamadı: %s", code, e)
        return {"ready": ok, "planned": len(codes)}

    def _finance_digest(self, collections: list[dict[str, Any]], st: dict[str, Any]) -> str:
        """Ayardaki süreden (varsayılan 48 saat) eski onay bekleyen tahsilat: iç alıcılara günlük özet (ayar boşsa gitmez)."""
        if not st["financeRecipients"]:
            return "alıcı yok"
        now = datetime.now(timezone.utc)
        old = []
        for t in collections:
            if int(num(t.get("durum"))) != src.T_PENDING:
                continue
            c = F.collection_out(t, {}, {}, {}, now)
            if c["yasSaat"] is not None and c["yasSaat"] >= st["pendingWarnHours"]:
                old.append(c)
        if not old:
            return "bekleyen yok"
        old.sort(key=lambda x: -(x["yasSaat"] or 0))
        lines = [f"{st['pendingWarnHours']} saatten eski onay bekleyen tahsilat: {len(old)} kayıt, toplam "
                 f"{F._tr_money(sum(x['tutar'] or 0 for x in old))}", ""]
        lines += [f"• {x['ad'] or x['id']} · {x['tip'] or '-'} · {F._tr_money(x['tutar'] or 0)} · {round((x['yasSaat'] or 0) / 24)} gün"
                  for x in old]
        return self.send_mail("Onay bekleyen tahsilatlar", "\n".join(lines), st["financeRecipients"])

    # -------------------------------------------------------------- hafif tur (15 dk)

    def run_light(self, engine: Any, tenant: str) -> dict[str, Any]:
        """CRM tahsilatı reddedilince ve sipariş riske takılınca temsilciye portal içi bildirim (kayıt başına bir kez)."""
        st = self.settings()
        cols = self.source.collections(st, fresh=True)
        users = self.users_map(fresh=True)
        accs = self.accounts_map(engine, tenant)
        since = (F.today() - timedelta(days=2)).isoformat()
        n = 0
        for t in cols:
            if int(num(t.get("durum"))) != src.T_REJECTED or (day(t.get("red_tarihi")) or day(t.get("degisme")) or "") < since:
                continue
            owner = (users.get(guid(t.get("owner_id")) or "") or {}).get("hesap")
            if not owner:
                continue
            acc = accs.get(guid(t.get("account_id")) or "") or {}
            why = src.REJECT_REASON.get(int(num(t.get("red_sebep")))) or text(t.get("red_metin")) or "neden yazılmamış"
            n += F.add_event(engine, tenant, owner, "tahsilat-red", guid(t.get("id")) or "",
                             f"Tahsilat reddedildi: {acc.get('unvan') or text(t.get('ad')) or ''} — {F._tr_money(num(t.get('tutar')))}",
                             why, acc.get("logo_code"))
        risk = self.source.crm(lambda run: src.lower_keys(run(src.crm_risk_orders_sql(st["schema"]))))
        with engine.connect() as c:
            port = {r.crm_account_id: (r.ad_hesap, r.unvan, r.logo_code) for r in c.execute(
                sa.select(F.PORTFOLIO.c.crm_account_id, F.PORTFOLIO.c.ad_hesap, F.PORTFOLIO.c.unvan, F.PORTFOLIO.c.logo_code)
                .where(F.PORTFOLIO.c.tenant_id == tenant, F.PORTFOLIO.c.crm_account_id.isnot(None)))}
        m = 0
        for r in risk:
            g = guid(r.get("account_id"))
            owner, unvan, code = port.get(g, (None, None, None))
            if not owner:
                continue
            key = f"risk:{g}:{day(r.get('en_eski'))}:{int(num(r.get('adet')))}"
            m += F.add_event(engine, tenant, owner, "siparis-risk", key,
                             f"Sipariş risk onayına takıldı: {unvan or code} ({int(num(r.get('adet')))} sipariş)",
                             src.ORDER_RISK_REASON.get(int(num(r.get("sebep")))), code)
        F.meta_set(engine, tenant, "light", {"rejected": n, "risk": m})
        return {"ok": True, "tahsilatRed": n, "siparisRisk": m}

    # -------------------------------------------------------------- haftalık

    def weekly(self, engine: Any, tenant: str, hafta: str, owner: Optional[str]) -> dict[str, Any]:
        start, end = F.week_bounds(hafta)
        rows = F.portfolio_rows(engine, tenant, owner)
        visits = F.list_visits(engine, tenant, "", tur="cari", since=start.isoformat(), admin=True)
        try:
            cols = self.source.collections(self.settings())
            users = self.users_map()
            warn = None
        except Exception as e:  # noqa: BLE001 — CRM düşse de Logo tarafı raporlanır
            log.warning("field: haftalık raporda CRM okunamadı: %s", e)
            cols, users, warn = [], {}, "CRM'e ulaşılamadı; tahsilat sütunları boş."
        items = F.weekly_report(rows, visits, cols, users, start, end)
        run = F.meta_get(engine, tenant, "run")
        return {"start": start.isoformat(), "end": end.isoformat(), "items": items, "asof": run.get("asof"),
                "dataEnd": run.get("dataEnd"), "warning": warn}

    def run_weekly(self, engine: Any, tenant: str) -> dict[str, Any]:
        st = self.settings()
        if not st["reportRecipients"]:
            return {"ok": True, "mail": "alıcı yok"}
        rep = self.weekly(engine, tenant, "", None)
        link = self.link()
        body = F.report_text(rep["items"], date.fromisoformat(rep["start"]), date.fromisoformat(rep["end"]), link)
        return {"ok": True, "mail": self.send_mail("Saha haftalık raporu", body, st["reportRecipients"]), "reps": len(rep["items"])}

    # -------------------------------------------------------------- brifing

    def live(self, engine: Any, tenant: str, row: dict[str, Any], fresh: bool) -> dict[str, Any]:
        """Tek carinin canlı okuması (5 dk bellek): son faturalar, ödemeler, kitap kırılımı, benzer cariler, yeni çıkanlar,
        CRM siparişleri."""
        st = self.settings()
        cal = self.calendar(engine, tenant)
        f, pf, year = cal["firm"], cal.get("prevFirm"), int(cal["year"])
        end = date.fromisoformat(cal["dataEnd"]) if cal.get("dataEnd") else F.today()
        code = row["logo_code"]
        codes = tuple(st["paymentTrcodes"])

        def logo_part(run):
            out: dict[str, Any] = {}
            out["invoices"] = src.read_rows(run, src.invoices_for_sql(f, code, 3))
            if len(out["invoices"]) < 3 and pf:
                out["invoices"] += src.read_rows(run, src.invoices_for_sql(pf, code, 3 - len(out["invoices"])))
            out["payments"] = src.read_rows(run, src.last_payment_sql(f, code, codes))
            if not out["payments"] and pf:
                out["payments"] = src.read_rows(run, src.last_payment_sql(pf, code, codes))
            out["cur"] = src.read_rows(run, src.items_for_sql(f, code, date(year, 1, 1), end))
            out["prev"] = src.read_rows(run, src.items_for_sql(pf, code, date(year - 1, 1, 1), date(year - 1, 12, 31))) if pf else []
            sim: list[dict[str, Any]] = []
            city, chan = row.get("logo_il"), row.get("logo_kanal")
            if city or chan:
                sim += src.read_rows(run, src.similar_items_sql(f, code, city, chan, date(year, 1, 1), end, st["codePrefix"]))
                back = end - timedelta(days=365)
                if pf and back.year < year:
                    sim += src.read_rows(run, src.similar_items_sql(pf, code, city, chan, back, date(year - 1, 12, 31), st["codePrefix"]))
            out["similar"] = sim
            return out

        logo = self.source.cached(f"logo:{code}:{end}", fresh, lambda: self.source.logo(logo_part))
        new_books = self.source.cached(f"new-books:{end}:{st['newBookDays']}", fresh, lambda: self.source.logo(
            lambda run: self._new_books(run, f, pf, end - timedelta(days=st["newBookDays"]))))
        crm: dict[str, Any] = {"orders": [], "error": None}
        if row.get("crm_account_id"):
            try:
                crm = self.source.cached(f"crm:{row['crm_account_id']}", fresh, lambda: self.source.crm(lambda run: {
                    "orders": src.lower_keys(run(src.crm_orders_for_sql(st["schema"], row["crm_account_id"], st["orderDays"], F.today()))),
                    "labels": {int(num(r.get("code"))): text(r.get("label")) for r in src.lower_keys(run(src.crm_order_status_sql(st["schema"])))},
                    "error": None}))
            except Exception as e:  # noqa: BLE001
                log.warning("field: CRM siparişleri okunamadı: %s", e)
                crm = {"orders": [], "labels": {}, "error": "CRM'e şu an ulaşılamıyor; sipariş durumu gösterilemiyor."}
        return {"logo": logo, "newBooks": new_books, "crm": crm, "cal": cal, "end": end}

    @staticmethod
    def _new_books(run, f: str, pf: Optional[str], since: date) -> dict[str, dict[str, Any]]:
        rows = src.read_rows(run, src.first_sales_sql(f, since))
        old = {text(r.get("stok")) for r in src.read_rows(run, src.sold_codes_sql(pf))} if pf else set()
        return {text(r.get("stok")): {"ad": text(r.get("ad")), "ilk": day(r.get("ilk"))} for r in rows
                if text(r.get("stok")) and text(r.get("stok")) not in old}

    def brief(self, engine: Any, tenant: str, user: str, code: str, all_scope: bool, fresh: bool = False,
              admin: bool = False) -> dict[str, Any]:
        row = F.in_scope(engine, tenant, user, code, all_scope)
        st = self.settings()
        run = F.meta_get(engine, tenant, "run")
        now = F.today()
        warnings: list[str] = []
        live: dict[str, Any] = {}
        try:
            live = self.live(engine, tenant, row, fresh)
        except FieldError:
            raise
        except Exception as e:  # noqa: BLE001 — Logo düşerse gece turunun sinyalleriyle devam
            log.warning("field: brifing canlı okuması başarısız: %s", e)
            warnings.append("Logo'ya şu an ulaşılamıyor; brifing gece turunun rakamlarıyla gösteriliyor.")
        logo = live.get("logo") or {}
        year = int(run.get("year") or now.year)
        end = live.get("end") or (date.fromisoformat(run["dataEnd"]) if run.get("dataEnd") else now)
        # Hedef açığı (kitap) ve öneri
        plan = self.approved_plan(engine, tenant, year)
        cust_prev = {text(r.get("stok")): num(r.get("adet")) for r in logo.get("prev") or []}
        cust_cur = {text(r.get("stok")): num(r.get("adet")) for r in logo.get("cur") or []}
        gaps: list[dict[str, Any]] = []
        if plan:
            gaps = F.book_target_gaps(cust_prev, self._book_prev_totals(engine, year - 1), cust_cur, plan["items"], end, year)
        bought = {k for k, v in {**cust_prev, **cust_cur}.items() if v > 0}
        sugg = F.suggestions(bought, F.merge_similar(logo.get("similar") or []), live.get("newBooks") or {}, st["similarMin"])
        # Sipariş
        crm = live.get("crm") or {}
        if crm.get("error"):
            warnings.append(crm["error"])
        orders = [{"no": text(o.get("no")), "tarih": day(o.get("tarih")), "tutar": num(o.get("tutar")),
                   "durum": (crm.get("labels") or {}).get(int(num(o.get("durum")))) or str(o.get("durum")),
                   "riskte": int(num(o.get("durum"))) in src.ORDER_RISK_STATUS,
                   "sebep": src.ORDER_RISK_REASON.get(int(num(o.get("sebep"))))} for o in crm.get("orders") or []]
        # Tahsilat (CRM onay akışı)
        cols: list[dict[str, Any]] = []
        if row.get("crm_account_id"):
            try:
                accs = {row["crm_account_id"]: {"logo_code": code, "unvan": row.get("unvan")}}
                raw = [t for t in self.source.collections(st) if guid(t.get("account_id")) == row["crm_account_id"]]
                cols = [F.collection_out(t, self.users_map(), accs, self.labels(engine), datetime.now(timezone.utc)) for t in raw]
                cols.sort(key=lambda x: x.get("olusturma") or "", reverse=True)
            except Exception as e:  # noqa: BLE001
                log.warning("field: CRM tahsilatları okunamadı: %s", e)
                warnings.append("CRM tahsilat kayıtları okunamadı.")
        visits = F.list_visits(engine, tenant, user, tur="cari", hedef=code, admin=admin)
        plans = F.list_plans(engine, tenant, codes=None, code=code)
        promises = F.broken_promises(engine, tenant, {code: row.get("son_odeme_tarihi")}, now)
        # Puan «Bugün» listesiyle aynı olsun: gecikme sırası temsilcinin bütün portföyü içinde hesaplanır.
        peers = F.portfolio_rows(engine, tenant, row.get("ad_hesap")) if row.get("ad_hesap") else [row]
        ranked = next(r for r in F.ranked(peers, promises=promises, rejected=F.rejected_by_account(self._safe_cols(st), now),
                                          boosts=F.overrides(engine, tenant, now), last_visits=F.last_visit_days(engine, tenant),
                                          cycle=st["visitCycleDays"], now=now) if r["logo_code"] == code)
        signals = {k: row.get(k) for k in ("bakiye", "vadesi_gecmis", "gelmemis", "plansiz", "k_1_30", "k_31_60", "k_61_90",
                                            "k_90p", "son_odeme_tarihi", "odeme_12ay", "karsiliksiz_olay_12ay",
                                            "protesto_olay_12ay", "cek_olay_tutar", "risk_toplam", "limit_toplam",
                                            "risk_doluluk", "siparis_riskte", "siparis_riskte_sebep", "ytd_net_ciro",
                                            "gecen_yil_ayni_donem", "gecen_yil_tam", "iade_orani", "son_fatura",
                                            "hedef_yil", "hedef_beklenen", "hedef_acigi", "hedef_kaynagi")}
        out = {
            "code": code, "unvan": row.get("unvan"), "il": row.get("il"), "kanal": row.get("kanal"),
            "temsilci": row.get("ad_hesap"), "temsilciAd": row.get("temsilci_ad"), "atama": row.get("atama_kaynagi"),
            "asof": run.get("asof"), "dataEnd": run.get("dataEnd"), "agingAsof": run.get("agingAsof"),
            "signals": signals, "puan": ranked["puan"], "gerekce": ranked["gerekce"],
            "faturalar": [{"tarih": day(i.get("tarih")), "no": text(i.get("no")), "tutar": num(i.get("tutar"))} for i in logo.get("invoices") or []],
            "odemeler": [{"tarih": day(p.get("tarih")), "tutar": num(p.get("tutar")), "tur": int(num(p.get("tur")))} for p in logo.get("payments") or []],
            "siparisler": orders, "tahsilatlar": cols,
            "sahaTahsilat": F._j(row.get("saha_tahsilat_json"), []),
            "hedefKitaplar": gaps, "hedefKurali": ("Carinin önceki yıl bu kitaptaki adet payı × kitabın yıllık hedefi × yılın geçen payı "
                                                   "− carinin bu yılki adedi (M46 yürürlükteki plan)") if plan else None,
            "oneriler": sugg, "oneriKurali": (f"24 ayda almadığı, aynı şehir ve kanaldaki en az {st['similarMin']} benzer carinin "
                                              f"aldığı kitaplar ve son {st['newBookDays']} günde çıkan kitaplar"),
            "ziyaretler": visits, "odemePlanlari": plans, "sozGecti": promises.get(code),
            "warnings": warnings,
        }
        facts = F.facts_of(out)
        cached = F.cached_brief(engine, tenant, code, run.get("asof") or "")
        h = F.input_hash(out)
        if cached and cached["girdi_hash"] == h:
            out["ozet"] = {"metin": cached["ozet_metin"], "kaynak": "zeki" if cached["model_is_kimligi"] != "kural" else "kural",
                           "zaman": F._iso(cached["olusturma"])}
        else:
            out["ozet"] = {"metin": " ".join(facts[:3]), "kaynak": "kural", "zaman": None}
        out["zekiVar"] = self.llm() is not None
        return out

    def _safe_cols(self, st: dict[str, Any]) -> list[dict[str, Any]]:
        try:
            return self.source.collections(st)
        except Exception:  # noqa: BLE001
            return []

    @staticmethod
    def _book_prev_totals(engine: Any, year: int) -> dict[str, float]:
        """Kitabın önceki yıl bütün carilere net adedi (M46'nın gerçekleşme önbelleği, aynı satır tanımı)."""
        try:
            with engine.connect() as c:
                rows = c.execute(F.book_prev_totals_stmt(year)).all()
            return {k: float(v or 0) for k, v in rows}
        except Exception as e:  # noqa: BLE001
            log.info("field: M46 satış önbelleği okunamadı: %s", e)
            return {}

    def summary(self, engine: Any, tenant: str, user: str, code: str, all_scope: bool) -> dict[str, Any]:
        """Zeki AI özeti: olgular → 3 cümle; her sayı olgularda geçmeli, geçmezse kural özeti yazılır."""
        b = self.brief(engine, tenant, user, code, all_scope, admin=True)
        llm = self.llm()
        if llm is None:
            raise FieldError("Zeki AI bu kurulumda bağlı değil.", 503)
        facts = F.facts_of(b)
        try:
            text_ = (llm.chat([{"role": "user", "content": F.summary_prompt(facts)}], max_tokens=300) or "").strip()
        except Exception as e:  # noqa: BLE001
            log.warning("field: özet üretilemedi: %s", e)
            raise FieldError("Zeki AI şu an cevap vermiyor; kural özeti gösteriliyor.", 503) from e
        ok = bool(text_) and F.numbers_ok(text_, facts)
        final = text_ if ok else " ".join(facts[:3])
        model = (getattr(llm, "model", "") or "zeki") if ok else "kural"
        F.save_brief(engine, tenant, code, b.get("asof") or "", F.input_hash(b), final, b["oneriler"], model, user)
        return {"metin": final, "kaynak": "zeki" if ok else "kural",
                "not": None if ok else "Zeki AI metninde olgularda olmayan bir sayı vardı; kural özeti gösteriliyor."}

    def followup(self, engine: Any, tenant: str, user: str, code: str, vid: str, all_scope: bool) -> dict[str, Any]:
        """Ziyaret sonrası takip e-postası TASLAĞI (gönderilmez; temsilci kendi e-postasından gönderir)."""
        v = F.get_visit(engine, tenant, vid)
        if v["sahip"] != user or v["hedef_kimlik"] != code:
            raise FieldError("Taslak yalnız kendi ziyaret kaydınızdan hazırlanır.", 403)
        row = F.in_scope(engine, tenant, user, code, all_scope)
        llm = self.llm()
        if llm is None:
            raise FieldError("Zeki AI bu kurulumda bağlı değil.", 503)
        facts = F.facts_of({"signals": row, "asof": F.today().isoformat()})
        prompt = F.followup_prompt(facts, v, row.get("unvan") or code)
        try:
            draft = (llm.chat([{"role": "user", "content": prompt}], max_tokens=400) or "").strip()
        except Exception as e:  # noqa: BLE001
            raise FieldError("Zeki AI şu an cevap vermiyor.", 503) from e
        allowed = facts + [v.get("notu") or "", v.get("sonraki_tarih") or "", v.get("soz_odeme_tarihi") or "",
                           F._tr_money(num(v.get("soz_odeme_tutari"))) if v.get("soz_odeme_tutari") else ""]
        return {"taslak": draft, "gonderilmez": True, "sayilarDogrulandi": F.numbers_ok(draft, allowed)}


# ------------------------------------------------------------------ uçlar


def register(app: Any, deps: dict[str, Any]) -> Service:
    """app.py'de bağlanır. `deps`: auth(request) → (engine, tenant, user, display) · require_caller(request) ·
    can(user, key) · is_admin(user) · audit(engine, user, action, kind, id, title, detail) · conf(key, default) ·
    fresh() · crm_connect() / logo_connect() → salt okunur bağlantı · llm() → LLM kapısı istemcisi ya da None ·
    engine() / tenant() → zamanlayıcı ucunun (oturumsuz) veritabanı ve kiracısı."""
    from semantic_bridge.budget_api import _send_mail

    auth, require_caller, can, is_admin, audit, conf, fresh = (
        deps[k] for k in ("auth", "require_caller", "can", "is_admin", "audit", "conf", "fresh"))
    settings = lambda: F.settings_from(conf)  # noqa: E731

    def link() -> str:
        base = (conf("ALERT_LINK") or "").split("/uyarilar")[0]
        return f"{base}/saha" if base else ""

    def internal_mail(subject: str, body: str, to: list[str]) -> str:
        """Yalnız iç alıcılar: izinli alan adı ayarı doluysa dışındaki adrese gitmez (müşteriye otomatik gönderim yok)."""
        allowed = [d.strip().lower().lstrip("@") for d in (conf("ALERT_RECIPIENT_DOMAINS") or "").split(",") if d.strip()]
        to = [x for x in to if not allowed or x.lower().rsplit("@", 1)[-1] in allowed]
        return _send_mail(subject, body, to) if to else "alıcı yok"

    svc = Service(F.Source(deps["crm_connect"], deps["logo_connect"]), settings, deps["llm"], internal_mail, link)

    def ctx(request: Request) -> tuple[Any, str, str, str]:
        engine, tenant, user, display = auth(request)
        F.ensure(engine)
        return engine, tenant, user, display

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except FieldError as e:
            # 403 ön yüzde «oturum düştü» sanılmasın (engine.ts yalnız FORBIDDEN kodlu 403'ü yetki reddi sayar): M38 kalıbı.
            raise HTTPException(status_code=e.status, detail={"code": "FORBIDDEN" if e.status == 403 else "FIELD",
                                                              "message": str(e)}) from e
        except SourceError as e:
            raise HTTPException(status_code=503, detail={"code": "DATA_SOURCE_UNAVAILABLE", "message": str(e)}) from e
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001 — kaynak düştüyse kişiye düz cümle, ayrıntı günlükte
            log.exception("field: istek başarısız")
            state = str(getattr(e, "args", [""])[0])
            if state in ("08S01", "08001", "HYT00", "HYT01") or "timeout" in str(e).lower():
                raise HTTPException(status_code=503, detail={"code": "DATA_SOURCE_UNAVAILABLE", "retryable": True,
                                    "message": "CRM ya da Logo şu anda yanıt vermiyor; birazdan tekrar deneyin."}) from e
            raise HTTPException(status_code=502, detail={"code": "FIELD", "message": "Saha verisi okunamadı."}) from e

    def flag(user: str, key: str) -> bool:
        return is_admin(user) or can(user, key)

    def need(user: str, key: str, what: str) -> None:
        if not flag(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def all_scope(user: str) -> bool:
        return flag(user, "ozellik:saha.herkesinki")

    def owner_of(user: str, temsilci: str) -> Optional[str]:
        """Kapsam: yetkisiz kişi yalnız kendisi; yetkili boş temsilciyle herkes, doluysa o temsilci."""
        if not all_scope(user):
            return user
        return temsilci.strip().lower() or None

    def scope_codes(engine, tenant, user) -> Optional[set[str]]:
        if all_scope(user):
            return None
        with engine.connect() as c:
            return {r[0] for r in c.execute(sa.select(F.PORTFOLIO.c.logo_code).where(
                F.PORTFOLIO.c.tenant_id == tenant, F.PORTFOLIO.c.ad_hesap == user))}

    # -------------------------------------------------------------- genel

    @app.get(f"{P}/meta")
    def field_meta(request: Request) -> dict[str, Any]:
        engine, tenant, user, display = ctx(request)
        st = settings()
        run = F.meta_get(engine, tenant, "run")
        mine = sa.select(sa.func.count()).select_from(F.PORTFOLIO).where(F.PORTFOLIO.c.tenant_id == tenant, F.PORTFOLIO.c.ad_hesap == user)
        with engine.connect() as c:
            my_count = int(c.execute(mine).scalar() or 0)
        out = {
            "me": {"username": user, "display": display, "admin": is_admin(user), "cari": my_count,
                   "canAll": all_scope(user), "canNote": flag(user, "ozellik:saha.not"),
                   "canOverride": flag(user, "ozellik:saha.oncelik-duzenle"),
                   "canApprovePlan": flag(user, "ozellik:saha.odeme-plani-onay"),
                   "canPerformance": flag(user, "ozellik:saha.performans"),
                   "canExport": flag(user, "ozellik:veri.disa-aktar")},
            "weights": [{"key": k, "max": w, "label": lab} for k, w, lab in F.WEIGHTS],
            "buckets": [{"key": k, "label": lab} for k, lab in F.BUCKETS],
            "tones": [{"key": k, "label": v} for k, v in F.TONES.items()],
            "planStates": [{"key": k, "label": v} for k, v in F.PLAN_STATES.items()],
            "run": {k: run.get(k) for k in ("asof", "dataEnd", "year", "agingAsof", "portfolio", "assigned", "warnings", "target", "mmx", "_at")},
            "reps": F.reps(engine, tenant) if all_scope(user) else [],
            "zekiQuestions": ZEKI_QUESTIONS,
            "settings": {k: st[k] for k in ("visitCycleDays", "collectionDays", "pendingWarnHours", "planMaxInstallments",
                                             "similarMin", "newBookDays", "agingAsof", "targetSource", "mmx")},
        }
        return PV.bagla(out, lambda: K.for_meta(engine, tenant, user, out))

    @app.post(f"{P}/run-due")
    def field_run_due(request: Request, tur: str = "gece") -> dict[str, Any]:
        """Zamanlayıcı: gece (portföy + sinyal + özet), hafif (15 dk bildirim), haftalik (rapor e-postası)."""
        require_caller(request)
        engine, tenant = deps["engine"](), deps["tenant"]()
        F.ensure(engine)
        if tur == "gece":
            out = call(svc.run_night, engine, tenant)
            warm_today()
            return out
        if tur == "hafif":
            out = call(svc.run_light, engine, tenant)
            warm_today()
            return out
        if tur == "haftalik":
            return call(svc.run_weekly, engine, tenant)
        raise HTTPException(status_code=422, detail={"code": "FIELD", "message": "tur gece, hafif ya da haftalik olmalı."})

    @app.post(f"{P}/refresh")
    def field_refresh(request: Request) -> dict[str, Any]:
        """Gece turunu elle koşturur (yönetici): ilk kurulumda zamanlayıcıdan önce bir kez."""
        engine, tenant, user, _ = ctx(request)
        if not is_admin(user):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Saha verisini yenilemek yönetici işidir."})
        out = call(svc.run_night, engine, tenant)
        warm_today()
        audit(engine, user, "run", "saha_tur", None, "Saha verisi yenilendi", {k: out.get(k) for k in ("portfolio", "assigned", "ms")})
        return out

    # -------------------------------------------------------------- liste ekranları

    # «Bugün» sıralaması. Yönetici kapsamında portföy bütün Logo carisidir (2026-09-28: 248.351); okuma + puan ≈ 15 sn,
    # bütün liste JSON'da 109 MB ve ≈ 20 sn tutuyordu. İki katman, kapsam başına bellekte:
    # - temel: gece turu (`run._at`) ve gün değişmedikçe aynı; ziyaret/söz/öncelik/red girdisi olmadan puanlanmış kartlar.
    # - sıra: girdilerden biri değişince yalnız girdisi olan cariler yeniden puanlanır (satırları DB'den), liste yeniden
    #   sıralanır. Girdisi olmayan carinin puanı girdisizle aynıdır, sonuç `F.ranked` ile birebir.
    # Ekran arar ve sayfa sayfa alır. Yönetici kapsamı zamanlayıcı turlarından (hafif 15 dk, gece) ve elle yenilemeden
    # sonra arka planda hazırlanır. Kayıt anında (modül yüklenirken) hazırlanmaz: `deps["engine"]()` çalışma ortamı henüz
    # yokken onu ikinci kez kurar (2026-09-28'de açılışı 40 sn'den 110 sn'ye çıkardı).
    today_cache: dict[tuple[str, Optional[str]], dict[str, Any]] = {}
    today_locks: dict[tuple[str, Optional[str]], threading.Lock] = {}
    today_guard = threading.Lock()

    def today_base(engine: Any, tenant: str, owner: Optional[str], run_at: Any, now: date, cycle: int) -> dict[str, Any]:
        rows = F.portfolio_rows(engine, tenant, owner)
        rank = F.overdue_ranks(rows)
        empty: dict[str, Any] = {}
        cards = [F.customer_card(F.scored(r, rank, promises=empty, rejected=empty, boosts=empty, last_visits=empty,
                                          cycle=cycle, now=now)) for r in rows]
        accounts: dict[str, list[str]] = {}
        for r in rows:
            if r.get("crm_account_id"):
                accounts.setdefault(r["crm_account_id"], []).append(r["logo_code"])
        exp = sum(num(r.get("hedef_beklenen")) for r in rows if r.get("hedef_beklenen"))
        ytd_t = sum(num(r.get("ytd_net_ciro")) for r in rows if r.get("hedef_beklenen"))
        return {
            "key": (run_at, now, cycle), "rank": rank, "accounts": accounts,
            "cards": {c["code"]: c for c in cards},
            "keys": {c["code"]: F.fold(f"{c.get('unvan') or ''} {c['code']} {c.get('il') or ''}") for c in cards},
            "payAfter": {r["logo_code"]: r.get("son_odeme_tarihi") for r in rows},
            "kpi": {"vadesiGecmis": round(sum(num(r.get("vadesi_gecmis")) for r in rows), 2),
                    "k90": round(sum(num(r.get("k_90p")) for r in rows), 2),
                    "hedefOrani": round(ytd_t / exp, 4) if exp > 0 else None, "cari": len(rows)},
            "order": None,
        }

    def today_ranked(engine: Any, tenant: str, owner: Optional[str], cols: list[dict[str, Any]],
                     st: dict[str, Any], now: date) -> dict[str, Any]:
        run_at = F.meta_get(engine, tenant, "run").get("_at")
        cycle = st["visitCycleDays"]
        with today_guard:
            lock = today_locks.setdefault((tenant, owner), threading.Lock())
        with lock:
            base = today_cache.get((tenant, owner))
            if base is None or base["key"] != (run_at, now, cycle):
                base = today_base(engine, tenant, owner, run_at, now, cycle)
                today_cache[(tenant, owner)] = base
            rejected = F.rejected_by_account(cols, now)
            boosts = F.overrides(engine, tenant, now)
            last_visits = F.last_visit_days(engine, tenant)
            promises = F.broken_promises(engine, tenant, base["payAfter"], now)
            inputs = json.dumps([promises, rejected, boosts, last_visits], sort_keys=True, default=str)
            if base["order"] is not None and base["order"]["inputs"] == inputs:
                return {**base, **base["order"]}
            cards = base["cards"]
            touched = (set(promises) | set(boosts) | set(last_visits)
                       | {c for a in rejected for c in base["accounts"].get(a, [])}) & cards.keys()
            fresh_cards = {r["logo_code"]: F.customer_card(F.scored(
                r, base["rank"], promises=promises, rejected=rejected, boosts=boosts, last_visits=last_visits,
                cycle=cycle, now=now)) for r in (F.portfolio_rows(engine, tenant, owner, codes=touched) if touched else [])}
            ordered = sorted((fresh_cards.get(k, c) for k, c in cards.items()), key=F.card_order)
            base["order"] = {"inputs": inputs, "list": ordered, "at": {c["code"]: i for i, c in enumerate(ordered)},
                             "listKeys": [base["keys"][c["code"]] for c in ordered]}
            return {**base, **base["order"]}

    def warm_today() -> None:
        """Yönetici kapsamının sırası arka planda hazırlanır (ilk açılış beklemesin). Yalnız istek içinden çağrılır."""
        def run() -> None:
            try:
                engine, tenant = deps["engine"](), deps["tenant"]()
                F.ensure(engine)
                st = settings()
                try:
                    cols = svc.source.collections(st)
                except Exception:  # noqa: BLE001 — CRM yoksa red sinyali boş, istek gelince yeniden bakılır
                    cols = []
                started = time.monotonic()
                n = today_ranked(engine, tenant, None, cols, st, F.today())["kpi"]["cari"]
                log.info("field: bugün sırası hazır (%d cari, %.1f sn)", n, time.monotonic() - started)
            except Exception as e:  # noqa: BLE001
                log.info("field: bugün sırası önceden hazırlanamadı: %s", e)

        threading.Thread(target=run, name="field-today-warm", daemon=True).start()

    @app.get(f"{P}/today")
    def field_today(request: Request, temsilci: str = "", q: str = "", offset: int = 0, limit: int = 40) -> dict[str, Any]:
        """Öncelik listesi sayfa sayfa: `items` sıralı listenin `offset`'ten `limit` kadarı, `total` aramaya uyan hepsi.
        KPI'lar bütün portföyden."""
        engine, tenant, user, _ = ctx(request)
        owner = owner_of(user, temsilci)
        st = settings()
        now = F.today()
        with F.recording() as reads:
            try:
                cols = svc.source.collections(st)
                warn = None
            except Exception as e:  # noqa: BLE001
                log.warning("field: bugün listesinde CRM okunamadı: %s", e)
                cols, warn = [], "CRM'e ulaşılamadı; reddedilen tahsilat sinyali bu listede yok."
            users_ids = ({k for k, v in svc.users_map().items() if v["hesap"] == owner} if cols else set()) if owner is not None else None
        rank = today_ranked(engine, tenant, owner, cols, st, now)
        cards = rank["list"]
        needle = F.fold(q.strip())
        if needle:
            cards = [c for c, k in zip(cards, rank["listKeys"]) if needle in k]
        offset, limit = max(0, offset), max(1, limit)
        planned = [v for v in F.list_visits(engine, tenant, user, tur="cari", owner=owner, day_=now.isoformat(), admin=is_admin(user))
                   if v["durum"] != "iptal"]
        pending = [t for t in cols if int(num(t.get("durum"))) == src.T_PENDING]
        if users_ids is not None:
            pending = [t for t in pending if guid(t.get("owner_id")) in users_ids]
        run = F.meta_get(engine, tenant, "run")
        at = rank["at"]
        out = {
            "asof": run.get("asof"), "dataEnd": run.get("dataEnd"), "warning": warn,
            "kpi": {**rank["kpi"], "onayBekleyen": len(pending), "onayBekleyenTutar": round(sum(num(t.get("tutar")) for t in pending), 2)},
            "planned": [{**v, "musteri": rank["list"][at[v["hedef"]]] if v["hedef"] in at else None} for v in planned],
            "items": cards[offset:offset + limit],
            "total": len(cards),
            "offset": offset,
            "events": F.events(engine, tenant, user, days=14),
        }
        return PV.bagla(out, lambda: K.for_today(engine, tenant, owner, out, reads, user))

    morning_cache: dict[tuple[str, Optional[str]], dict[str, Any]] = {}

    @app.get(f"{P}/today/brief")
    def field_today_brief(request: Request, temsilci: str = "") -> dict[str, Any]:
        """Sabah saha brifi: Bugün listesinin aynı kapsamı (yetkisiz kişi yalnız kendi portföyü) ve aynı sırası. Zeki AI
        4–5 cümle yazar; sayı denetiminden geçmezse ya da model yoksa olgular kural metni olarak döner. Aynı olgular için
        model yeniden çağrılmaz (kapsam başına son brif bellekte)."""
        engine, tenant, user, _ = ctx(request)
        owner = owner_of(user, temsilci)
        st = settings()
        now = F.today()
        with F.recording() as reads:
            try:
                cols = svc.source.collections(st)
            except Exception as e:  # noqa: BLE001
                log.info("field: brifte CRM okunamadı: %s", e)
                cols = []
        rank = call(today_ranked, engine, tenant, owner, cols, st, now)
        planned = [v for v in F.list_visits(engine, tenant, user, tur="cari", owner=owner, day_=now.isoformat(), admin=is_admin(user))
                   if v["durum"] != "iptal"]
        at = rank["at"]
        planned = [{**v, "musteri": rank["list"][at[v["hedef"]]] if v["hedef"] in at else None} for v in planned]
        pending = [t for t in cols if int(num(t.get("durum"))) == src.T_PENDING]
        if owner is not None:
            ids = {k for k, v in svc.users_map().items() if v["hesap"] == owner} if cols else set()
            pending = [t for t in pending if guid(t.get("owner_id")) in ids]
        kpi = {**rank["kpi"], "onayBekleyen": len(pending)}
        facts, plain, names = F.morning_facts(kpi, planned, rank["list"][:3], now.isoformat())
        digest = hashlib.sha256(json.dumps([facts, names], ensure_ascii=False).encode()).hexdigest()
        cached = morning_cache.get((tenant, owner))
        if cached and cached["digest"] == digest:
            return cached["out"]
        out = {**F.morning_brief(facts, plain, names, svc.llm()), "gun": now.isoformat(), "dataEnd": F.meta_get(engine, tenant, "run").get("dataEnd")}
        PV.bagla(out, lambda: K.for_morning(engine, tenant, owner, out, reads))
        morning_cache[(tenant, owner)] = {"digest": digest, "out": out}
        return out

    @app.get(f"{P}/portfolio")
    def field_portfolio(request: Request, temsilci: str = "", q: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        owner = owner_of(user, temsilci)
        rows = F.portfolio_rows(engine, tenant, owner)
        if q.strip():
            needle = F.fold(q)
            rows = [r for r in rows if needle in F.fold(f"{r.get('unvan') or ''} {r['logo_code']} {r.get('il') or ''}")]
        rows.sort(key=lambda r: (r.get("unvan") or "").lower())
        out = {"items": [F.customer_card({**r, "puan": r.get("oncelik_puani"), "gerekce": F._j(r.get("gerekce_json"), [])}) for r in rows],
               "count": len(rows)}
        return PV.bagla(out, lambda: K.for_portfolio(engine, tenant, owner, out))

    @app.get(f"{P}/customers/{{code}}/brief")
    def field_brief(code: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        with F.recording() as reads:
            out = call(svc.brief, engine, tenant, user, code, all_scope(user), fresh(), is_admin(user))
        return PV.bagla(out, lambda: K.for_brief(engine, tenant, out["code"], out, reads))

    @app.post(f"{P}/customers/{{code}}/brief/summary")
    def field_brief_summary(code: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        call(F.in_scope, engine, tenant, user, code, all_scope(user))
        out = call(svc.summary, engine, tenant, user, code, all_scope(user))
        audit(engine, user, "run", "saha_ozet", code, "Zeki AI brifing özeti", {"kaynak": out["kaynak"]})
        return out

    @app.get(f"{P}/collections")
    def field_collections(request: Request, kova: str = "", temsilci: str = "") -> dict[str, Any]:
        """FIFO kovaları (yaklaşık): vadesi geçmiş alacağı olan cariler, puan sırasıyla. `kova` = k_1_30 … k_90p."""
        engine, tenant, user, _ = ctx(request)
        if kova and kova not in {k for k, _ in F.BUCKETS}:
            raise HTTPException(status_code=422, detail={"code": "FIELD", "message": "Kova geçersiz."})
        owner = owner_of(user, temsilci)
        rows = [r for r in F.portfolio_rows(engine, tenant, owner) if num(r.get("vadesi_gecmis")) > 0]
        totals = {k: round(sum(num(r.get(k)) for r in rows), 2) for k, _ in F.BUCKETS}
        if kova:
            rows = [r for r in rows if num(r.get(kova)) > 0]
        rows.sort(key=lambda r: (-num(r.get(kova)) if kova else -F.weighted_overdue(r)))
        out = {"totals": totals, "count": len(rows), "total": round(sum(num(r.get("vadesi_gecmis")) for r in rows), 2),
               "items": [F.customer_card({**r, "puan": r.get("oncelik_puani"), "gerekce": F._j(r.get("gerekce_json"), [])}) for r in rows],
               "note": "Yaklaşık: Logo'da ödeme kapama kullanılmadığı için bakiye en yeni vade satırlarından geriye dağıtılır (FIFO)."}
        return PV.bagla(out, lambda: K.for_collections(engine, tenant, owner, out))

    @app.get(f"{P}/collections/crm")
    def field_collections_crm(request: Request, durum: str = "onay-bekliyor", temsilci: str = "", gun: int = 30) -> dict[str, Any]:
        """CRM tahsilat onay akışı (okuma): onay bekleyen / reddedilen. Tahsilat CRM'de girilir; portalda yeniden girilmez."""
        engine, tenant, user, _ = ctx(request)
        st = settings()
        owner = owner_of(user, temsilci)

        def build():
            items = svc.source.collections(st, fresh())
            users = svc.users_map()
            ids = {k for k, v in users.items() if v["hesap"] == owner} if owner is not None else None
            codes = scope_codes(engine, tenant, user) if owner == user else (
                {r["logo_code"] for r in F.portfolio_rows(engine, tenant, owner)} if owner else None)
            return F.collections_view(items, durum=durum, owner_ids=ids, codes=codes, users=users,
                                      accounts=svc.accounts_map(engine, tenant), labels=svc.labels(engine),
                                      reject_days=max(1, min(730, int(gun))))
        with F.recording() as reads:
            out = call(build)
        out["warnHours"] = st["pendingWarnHours"]
        return PV.bagla(out, lambda: K.for_crm_collections(engine, tenant, out, reads))

    @app.get(f"{P}/events")
    def field_events(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return {"items": F.events(engine, tenant, user)}

    @app.post(f"{P}/events/seen")
    def field_events_seen(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        return {"marked": F.mark_seen(engine, tenant, user)}

    # -------------------------------------------------------------- ziyaret (M30/M31 ortak)

    @app.get(f"{P}/visits")
    def field_visits(request: Request, musteri: str = "", tarih: str = "", tur: str = "", sahip: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        codes = scope_codes(engine, tenant, user)
        owner = sahip.strip().lower() or None
        if owner and owner != user and not all_scope(user):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Başkasının ziyaretlerini görme yetkiniz yok."})
        out = {"items": F.list_visits(engine, tenant, user, codes=codes, hedef=musteri, tur=tur, owner=owner,
                                      day_=(tarih[:10] if tarih else ""), admin=is_admin(user))}
        return PV.bagla(out, lambda: K.for_visits(engine, tenant, out, hedef=musteri, tur=tur, owner=owner,
                                                  day_=(tarih[:10] if tarih else "")))

    @app.post(f"{P}/visits", status_code=201)
    def field_visit_add(body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Ziyaret notu kaydı. Yazma yolu yalnız yerel tablolar: kapsam (portföy satırı, birincil anahtar), ekleme,
        değişiklik kaydı. CRM/Logo okuması, model çağrısı, bugün sırasının yeniden hesabı YOK — sıra bir sonraki
        «Bugün» isteğinde yalnız bu cari için yeniden puanlanır, özet gece turunda hazırlanır. Süre adım adım ölçülür;
        2 sn'yi geçerse günlüğe yazılır (kabulde 120 sn'lik bekleme görüldü)."""
        t0 = time.monotonic()
        engine, tenant, user, _ = ctx(request)
        t_ctx = time.monotonic()
        tur = str(body.get("tur") or "cari")
        name = None
        if tur == "cari":
            row = call(F.in_scope, engine, tenant, user, str(body.get("hedef") or ""), all_scope(user))
            name = row.get("unvan")
        t_scope = time.monotonic()
        out = call(F.add_visit, engine, tenant, user, body, name)
        t_write = time.monotonic()
        audit(engine, user, "create", "saha_ziyaret", out["id"], out.get("hedefAd") or out["hedef"],
              {"tur": out["tur"], "durum": out["durum"], "planlanan": out["planlanan"], "soz": out["sozOdemeTarihi"]})
        _slow_write("ziyaret notu", t0, [("oturum", t_ctx), ("kapsam", t_scope), ("kayıt", t_write), ("değişiklik kaydı", time.monotonic())])
        return out

    @app.patch(f"{P}/visits/{{vid}}")
    def field_visit_update(vid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        t0 = time.monotonic()
        engine, tenant, user, _ = ctx(request)
        t_ctx = time.monotonic()
        out, diff = call(F.update_visit, engine, tenant, user, vid, body, is_admin(user))
        t_write = time.monotonic()
        if diff:
            audit(engine, user, "update", "saha_ziyaret", vid, out.get("hedefAd") or out["hedef"], diff)
        _slow_write("ziyaret düzenleme", t0, [("oturum", t_ctx), ("kayıt", t_write), ("değişiklik kaydı", time.monotonic())])
        return out

    @app.post(f"{P}/visits/{{vid}}/followup-draft")
    def field_followup(vid: str, request: Request) -> dict[str, Any]:
        """Takip e-postası taslağı (Zeki AI). Portal göndermez."""
        engine, tenant, user, _ = ctx(request)
        v = call(F.get_visit, engine, tenant, vid)
        return call(svc.followup, engine, tenant, user, v["hedef_kimlik"], vid, all_scope(user))

    # -------------------------------------------------------------- ödeme planı

    @app.get(f"{P}/payment-plans")
    def field_plans(request: Request, durum: str = "", musteri: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        codes = None if (all_scope(user) or flag(user, "ozellik:saha.odeme-plani-onay")) else scope_codes(engine, tenant, user)
        out = {"items": F.list_plans(engine, tenant, codes=codes, durum=durum, code=musteri)}
        return PV.bagla(out, lambda: K.for_plans(engine, tenant, out, durum, musteri))

    @app.post(f"{P}/payment-plans", status_code=201)
    def field_plan_add(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        row = call(F.in_scope, engine, tenant, user, str(body.get("code") or ""), all_scope(user))
        out = call(F.create_plan, engine, tenant, user, row, body, settings()["planMaxInstallments"])
        audit(engine, user, "create", "saha_odeme_plani", out["id"], out.get("unvan") or out["code"],
              {"tutar": out["tutar"], "taksit": len(out["taksitler"])})
        return out

    @app.patch(f"{P}/payment-plans/{{pid}}")
    def field_plan_edit(pid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(F.edit_plan, engine, tenant, user, pid, body)
        audit(engine, user, "update", "saha_odeme_plani", pid, out.get("unvan") or out["code"],
              {"taksit": len(out["taksitler"]), "toplam": out["taksitToplam"]})
        return out

    @app.post(f"{P}/payment-plans/{{pid}}/submit")
    def field_plan_submit(pid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(F.submit_plan, engine, tenant, user, pid)
        audit(engine, user, "update", "saha_odeme_plani", pid, out.get("unvan") or out["code"], {"durum": "onayda"})
        return out

    @app.post(f"{P}/payment-plans/{{pid}}/approve")
    def field_plan_approve(pid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, "ozellik:saha.odeme-plani-onay", "Ödeme planı onayı")
        out = call(F.decide_plan, engine, tenant, user, pid, True, body.get("note"))
        audit(engine, user, "approve", "saha_odeme_plani", pid, out.get("unvan") or out["code"], {"not": body.get("note")})
        F.add_event(engine, tenant, out["oneren"], "plan-karar", f"{pid}:onayli", f"Ödeme planı onaylandı: {out.get('unvan') or out['code']}",
                    out.get("kararNotu"), out["code"])
        return out

    @app.post(f"{P}/payment-plans/{{pid}}/reject")
    def field_plan_reject(pid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        need(user, "ozellik:saha.odeme-plani-onay", "Ödeme planı onayı")
        out = call(F.decide_plan, engine, tenant, user, pid, False, body.get("note"))
        audit(engine, user, "reject", "saha_odeme_plani", pid, out.get("unvan") or out["code"], {"not": body.get("note")})
        F.add_event(engine, tenant, out["oneren"], "plan-karar", f"{pid}:reddedildi",
                    f"Ödeme planı geri çevrildi: {out.get('unvan') or out['code']}", out.get("kararNotu"), out["code"])
        return out

    # -------------------------------------------------------------- müdür önceliği

    @app.get(f"{P}/overrides")
    def field_overrides(request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        codes = scope_codes(engine, tenant, user)
        items = [{"code": k, **v} for k, v in F.overrides(engine, tenant).items() if codes is None or k in codes]
        out = {"items": items}
        return PV.bagla(out, lambda: K.for_overrides(engine, tenant, out))

    @app.post(f"{P}/overrides", status_code=201)
    def field_override_add(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        row = call(F.in_scope, engine, tenant, user, str(body.get("code") or ""), all_scope(user))
        out = call(F.add_override, engine, tenant, user, row["logo_code"], body)
        audit(engine, user, "create", "saha_oncelik", out["id"], row.get("unvan") or row["logo_code"],
              {"neden": out["neden"], "bitis": out["bitis"]})
        return out

    @app.delete(f"{P}/overrides/{{oid}}")
    def field_override_delete(oid: str, request: Request) -> dict[str, Any]:
        engine, tenant, user, _ = ctx(request)
        out = call(F.delete_override, engine, tenant, oid)
        audit(engine, user, "delete", "saha_oncelik", oid, out["logo_code"], None)
        return {"ok": True}

    # -------------------------------------------------------------- haftalık rapor

    def _report(request: Request, hafta: str, temsilci: str) -> tuple[Any, str, str, Optional[str], dict[str, Any]]:
        engine, tenant, user, _ = ctx(request)
        # Temsilci karşılaştırması (kişisel performans verisi) yalnız açıkça yetkili yöneticiye; öteki kişi kendi satırını görür.
        owner = (temsilci.strip().lower() or None) if flag(user, "ozellik:saha.performans") else user
        return engine, tenant, user, owner, call(svc.weekly, engine, tenant, hafta, owner)

    @app.get(f"{P}/report/weekly")
    def field_report(request: Request, hafta: str = "", temsilci: str = "") -> dict[str, Any]:
        with F.recording() as reads:
            engine, tenant, _, owner, out = _report(request, hafta, temsilci)
        return PV.bagla(out, lambda: K.for_weekly(engine, tenant, owner, out["start"], out, reads))

    @app.get(f"{P}/report/weekly.xlsx")
    def field_report_xlsx(request: Request, hafta: str = "", temsilci: str = "") -> Response:
        engine, _, user, _, out = _report(request, hafta, temsilci)
        data = F.report_xlsx(out["items"], date.fromisoformat(out["start"]), date.fromisoformat(out["end"]))
        audit(engine, user, "run", "saha_rapor_disa", None, f"Saha raporu {out['start']}", {"satir": len(out["items"])})
        return Response(data, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="saha-raporu-{out["start"]}.xlsx"'})

    return svc
