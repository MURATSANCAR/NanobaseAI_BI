"""Serbest not sinyali uçları: /api/v1/not-sinyali/* (AI fırsatları öneri 16).

Kapı iki katlı: sayfa kuralı (`access.RULES`: saha, bayi-risk, musteri-iliskileri) + ekranın kendi kapsamı. `ekran`
parametresi hangi modülün kapsam kuralının uygulanacağını söyler ve o modülün **kendi** işleviyle denetlenir:
M30 `field_sales.in_scope` (`ozellik:saha.herkesinki`), M59 `dealers.scoped` (`ozellik:bayi.herkesinki`), M38
`musteri.in_scope` (`ozellik:musteri.herkesinki`). Kişi o ekranın sayfa yetkisine de sahip olmalı.

Zamanlayıcı (`timas-not-sinyali.timer`, her gece 04:40) `POST /api/v1/not-sinyali/run-due`'yu çağırır: notları okur (CRM
kaynağı `FIELD_CRM_VISIT_ACCOUNT_COLUMN` doluysa), yeni/değişen notu etiketler (BATCH), notu değişen carilerin özetini
yeniler (BATCH, süre bütçesi; kalan sonraki gece). Model yalnız LLM kapısından: `rt.llm_for("not-sinyali", …)`.
"""
from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Any, Optional

from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool

from semantic_bridge import note_signal as N

log = logging.getLogger("semantic.note_signal.api")
P = "/api/v1/not-sinyali"

#: ekran → (sayfa anahtarı, «herkesinki» özelliği)
SCREENS = {
    "saha": ("sayfa:saha", "ozellik:saha.herkesinki"),
    "bayi": ("sayfa:bayi-risk", "ozellik:bayi.herkesinki"),
    "musteri": ("sayfa:musteri-iliskileri", "ozellik:musteri.herkesinki"),
}


def register(app: Any, deps: dict[str, Any]) -> dict[str, Any]:
    """`deps`: auth(request) → (engine, tenant, user, display) · require_caller · can · is_admin · audit · conf ·
    crm_connect / logo_connect · llm(priority) · engine() / tenant()."""
    from semantic_bridge import dealers as D
    from semantic_bridge import field_sales as F
    from semantic_bridge import musteri as M

    auth, require_caller, can, is_admin, audit, conf = (
        deps[k] for k in ("auth", "require_caller", "can", "is_admin", "audit", "conf"))
    source = F.Source(deps["crm_connect"], deps["logo_connect"])

    def st() -> dict[str, Any]:
        return N.settings(lambda k: conf(k) or "")

    def llm(batch: bool):
        try:
            from semantic_layer.runtime.llm_queue import BATCH, NORMAL
            return deps["llm"](BATCH if batch else NORMAL)
        except Exception:  # noqa: BLE001 — model tanımlı değil
            return None

    def flag(user: str, key: str) -> bool:
        return is_admin(user) or can(user, key)

    def scoped(engine, tenant: str, user: str, code: str, ekran: str) -> None:
        """Ekranın kendi kapsam kuralı; yetkisizse 403, kayıt yoksa 404 (modülün kendi mesajıyla)."""
        if ekran not in SCREENS:
            raise HTTPException(400, detail={"code": "NOT_SINYALI", "message": "Ekran saha, bayi ya da musteri olmalı."})
        page, every = SCREENS[ekran]
        if not flag(user, page):
            raise HTTPException(403, detail={"code": "FORBIDDEN", "message": "Bu ekran rolünüzde yok."})
        try:
            if ekran == "saha":
                F.ensure(engine)
                F.in_scope(engine, tenant, user, code, flag(user, every))
            elif ekran == "bayi":
                D.ensure(engine)
                D.scoped(engine, tenant, user, code, flag(user, every))
            else:
                M.ensure(engine)
                M.in_scope(engine, tenant, user, code, flag(user, every))
        except (F.FieldError, D.DealerError, M.MusteriError) as e:
            raise HTTPException(status_code=e.status, detail={"code": "NOT_SINYALI", "message": str(e)}) from e

    def ctx(request: Request) -> tuple[Any, str, str]:
        engine, tenant, user, _display = auth(request)
        N.ensure(engine)
        return engine, tenant, user

    def crm_one(engine, tenant: str, code: str, s: dict[str, Any]) -> list[dict[str, Any]]:
        """Tek carinin CRM notları (ekrandaki «özeti yenile»); ayar boşsa ya da CRM düştüyse boş."""
        if not s["crmColumn"]:
            return []
        acc = next((a for a, c in N.account_map(engine, tenant).items() if c == code), None)
        if not acc:
            return []
        from semantic_bridge import field_sales_sources as fsrc

        since = N.now().date() - timedelta(days=s["crmDays"])
        try:
            rows = source.crm(lambda run: fsrc.lower_keys(run(N.crm_notes_sql(s["schema"], s["crmColumn"], since, acc))))
        except Exception as e:  # noqa: BLE001 — CRM yoksa portal notlarıyla sürer
            log.warning("not sinyali: CRM notları okunamadı (%s): %s", code, e)
            return []
        return N.crm_notes(rows, {acc: code})

    # ------------------------------------------------------------------ ekran

    @app.get(P + "/cari/{code}")
    def note_signal_view(code: str, request: Request, ekran: str = "") -> dict[str, Any]:
        engine, tenant, user = ctx(request)
        scoped(engine, tenant, user, code, ekran)
        portal = N.portal_notes(engine, tenant, {code})
        return N.view(engine, tenant, code, portal, st())

    @app.post(P + "/cari/{code}/ozet")
    async def note_signal_summary(code: str, request: Request, ekran: str = "") -> dict[str, Any]:
        engine, tenant, user = await run_in_threadpool(ctx, request)
        await run_in_threadpool(scoped, engine, tenant, user, code, ekran)
        s = st()

        def work() -> dict[str, Any]:
            notes = N.portal_notes(engine, tenant, {code}) + crm_one(engine, tenant, code, s)
            return N.write_summary(engine, tenant, code, notes, llm(False), s, N.known_names(engine, tenant))

        out = await run_in_threadpool(work)
        if not out.get("onbellek"):
            audit(engine, user, "run", "not_sinyali_ozet", code, "Not özeti", {"kaynak": out["kaynak"], "dusen": out["dusen"]})
        portal = N.portal_notes(engine, tenant, {code})
        return N.view(engine, tenant, code, portal, s)

    # ------------------------------------------------------------------ zamanlayıcı

    def run_due(engine, tenant: str, force: bool = False) -> dict[str, Any]:
        s = st()
        t0 = time.monotonic()
        out: dict[str, Any] = {"kaynak": {}}
        notes = N.portal_notes(engine, tenant)
        full = ["saha-ziyaret", "bayi-aksiyon", "musteri-aksiyon"]
        out["kaynak"]["portal"] = len(notes)
        if s["crmColumn"]:
            from semantic_bridge import field_sales_sources as fsrc

            since = N.now().date() - timedelta(days=s["crmDays"])
            try:
                rows = source.crm(lambda run: fsrc.lower_keys(run(N.crm_notes_sql(s["schema"], s["crmColumn"], since))))
                crm = N.crm_notes(rows, N.account_map(engine, tenant))
                notes += crm
                full.append("crm-etkinlik")
                out["kaynak"]["crm"] = len(crm)
            except Exception as e:  # noqa: BLE001 — CRM düştüyse portal notları yine etiketlenir, CRM etiketi silinmez
                out["kaynak"]["crm"] = {"hata": str(e)[:200]}
        else:
            out["kaynak"]["crm"] = "FIELD_CRM_VISIT_ACCOUNT_COLUMN boş: CRM notları okunmadı (ölçülecek)"
        crm_failed = isinstance(out["kaynak"].get("crm"), dict)
        names = N.known_names(engine, tenant)
        m = llm(True)
        cls = N.classify(engine, tenant, notes, m, s, names=names, force=force)
        out["etiket"] = {k: v for k, v in cls.items() if k != "degisenCari"}
        out["silinen"] = N.prune(engine, tenant, notes, full)
        # Özet: notu olan her cari; girdisi değişmeyen için model çağrılmaz (dün süre biten cari bu gece yazılır).
        # CRM okunamadıysa özet adımı atlanır: CRM notu eksik girdiyle özet yeniden yazılmasın.
        codes = [] if crm_failed else sorted({n["cari"] for n in notes})
        done, left = 0, 0
        for code in codes:
            if time.monotonic() - t0 > s["budgetSec"]:
                left += 1
                continue
            try:
                if not N.write_summary(engine, tenant, code, notes, m, s, names, force=force).get("onbellek"):
                    done += 1
            except Exception as e:  # noqa: BLE001 — model düştüyse özet sonraki gece
                log.warning("not sinyali: özet yazılamadı (%s): %s", code, e)
                left += 1
        out["ozet"] = {"yazilan": done, "kalan": left, "atlandi": "CRM okunamadı" if crm_failed else None}
        return out

    @app.post(P + "/run-due")
    async def note_signal_run_due(request: Request, force: bool = False) -> dict[str, Any]:
        require_caller(request)
        engine, tenant = deps["engine"](), deps["tenant"]()
        N.ensure(engine)
        return await run_in_threadpool(run_due, engine, tenant, force)

    return {"run_due": run_due}

