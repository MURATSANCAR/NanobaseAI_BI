"""M50 Zeki AI kalitesi uçları: /api/v1/model-quality/*.

Sayfa kapısı `access.RULES` (`sayfa:zeki-kalite`, açıkça verilir — «Herkes»e girmez). İşlem yetkileri ucun içinde:
koşu başlatma `ozellik:zeki-kalite.kosu`, geri bildirim sınıflama ve sınıf kuralı `ozellik:zeki-kalite.karar`
(ikisi de açıkça verilir). Cevabın altındaki Doğru/Kısmen/Yanlış düğmesi `ozellik:zeki.geri-bildirim` (ortak; sayfa
yetkisi istemez; `access.FEATURE_RULES`).

Sistem uçları (çerezsiz jeton ya da yönetici): `POST report` (kapı betiklerinin `--report`u), `POST run-due`
(zamanlayıcı: sıradaki koşu istekleri, günlük özet, yarıda kalan koşu), `POST versions` (kurulum sonu sürüm kaydı).

Rakamı model üretmez: model yalnız başarısız soru kümelerine sınıf önerir (`model_quality_clusters`, `QueuedLlm.choose`, onay insanda). Kapı hükmü betiğin referans SQL karşılaştırmasıdır; karne tablolardan
sayılır. Dış gönderim yalnız iç ekibe e-posta (`MODEL_QUALITY_RECIPIENTS`, izinli alan adı süzgeciyle).
"""
from __future__ import annotations

import logging
import os
import re
import smtplib
import ssl
import threading
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any, Callable

from fastapi import HTTPException, Request
from starlette.concurrency import run_in_threadpool

from semantic_bridge import model_quality as MQ
from semantic_bridge import model_quality_sources as src


from semantic_bridge import sorgu_izi as IZ  # noqa: E402

F_KARNE = 'Karne: soru-cevap satırında cevaplama oranı = cevaplanan ÷ sorulan (soru kayıtları), isabet = Doğru ÷ (Doğru + Kısmen + Yanlış) geri bildirim, bozulan/düzelen = son iki kalite koşusunun vaka karşılaştırması; SEO, çeviri ve redaksiyon satırları kendi öneri kayıtlarından kabul/düzeltme oranları; ms değerleri kayıttaki süre medyanı; 4 haftalık eğilim haftalık aynı hesap. Pencere dışı satırlar sayılmaz; yetkisi olmayan modülün satırı gösterilmez (sayısı ayrıca yazılır).'
F_KOSU = 'Koşu satırı: sağlam = durumu geçen vakalar ÷ bütün vakalar; bozulan/düzelen = bir önceki koşuda geçip bu koşuda kalan ya da tersi; süre = koşunun başı ile sonu arası.'
F_SINIF = 'Hata sınıfları: incelenen soru = penceredeki sınıflanmış sorular; isabetsizlik sayılan = hata sayılan sınıflardaki sorular; geri bildirimden = kaynağı kullanıcı geri bildirimi olanlar; kapı vakası = son kalite koşusunda o sınıfa düşen vakalar; eğilim son 4 haftanın haftalık sayısı.'
F_KUYRUK = 'Geri bildirim kuyruğu: süzgece uyan kayıt sayısı ve her kaydın sorusunun satır sayısı (soru kaydından).'
F_SURUM = 'Sürümler: katalog sürümü ve onaylı terim sayısı sürüm kaydında; kurulum listesi kurulum kayıtlarından.'

log = logging.getLogger("semantic.model_quality.api")

_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _int(v: Any, default: int, lo: int, hi: int) -> int:
    try:
        return max(lo, min(hi, int(str(v).strip())))
    except (TypeError, ValueError):
        return default


class Service:
    """app.state.model_quality: `/api/v1/feedback` (eski uç) bu nesne üzerinden yazar."""

    def __init__(self, feedback: Callable[[Request, dict[str, Any]], dict[str, Any]]):
        self.feedback = feedback


def register(app, deps: dict[str, Any]) -> Service:
    auth = deps["auth"]                       # (request) -> (engine, tenant, user, display)
    require_caller = deps["require_caller"]
    can: Callable[[str, str], bool] = deps["can"]
    is_admin: Callable[[str], bool] = deps["is_admin"]
    audit = deps["audit"]
    conf: Callable[..., str] = deps["conf"]
    rt = deps["rt"]

    def ctx(request: Request) -> tuple[Any, str, str, str, str]:
        engine, tenant, user, display = auth(request)
        MQ.ensure(engine)
        return engine, tenant, rt().settings.datasource_id, user, display

    def system(request: Request) -> tuple[Any, str, str]:
        """Zamanlayıcı/betik ucu: jeton; çerezle gelen kişi yalnız yöneticiyse geçer (sayfa kapısı SYSTEM kuralı)."""
        require_caller(request)
        cookie = request.headers.get("cookie", "")
        if "timas_session" in cookie:
            _, _, user, _ = auth(request)
            if not is_admin(user):
                raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": "Bu işlem zamanlayıcıya aittir."})
            by = user
        else:
            by = "zamanlayici"
        r = rt()
        MQ.ensure(r.store.engine)
        return r.store.engine, r.settings.tenant_id, by

    def call(fn, *a, **kw):
        try:
            return fn(*a, **kw)
        except MQ.QualityError as e:
            code = {401: "UNAUTHORIZED", 403: "FORBIDDEN", 404: "NOT_FOUND", 409: "CONFLICT"}.get(e.status, "INVALID")
            raise HTTPException(status_code=e.status, detail={"code": code, "message": str(e)}) from e

    def need(user: str, key: str, what: str) -> None:
        if not can(user, key):
            raise HTTPException(status_code=403, detail={"code": "FORBIDDEN", "message": f"{what} rolünüzde yok."})

    def window_days(v: Any = None) -> int:
        return _int(v if v not in (None, "") else conf("MODEL_QUALITY_WINDOW_DAYS"), 30, 1, 3650)

    # ------------------------------------------------------------------ e-posta (yalnız iç ekip)

    def recipients() -> list[str]:
        allowed = [d.strip().lower().lstrip("@") for d in (conf("ALERT_RECIPIENT_DOMAINS") or "").split(",") if d.strip()]
        out = []
        for x in re.split(r"[,;\s]+", conf("MODEL_QUALITY_RECIPIENTS") or ""):
            x = x.strip()
            if not x or not _EMAIL.match(x):
                continue
            if allowed and x.rsplit("@", 1)[1].lower() not in allowed:
                log.warning("model_quality: %s izinli alan adında değil, atlandı", x)
                continue
            if x.lower() not in {o.lower() for o in out}:
                out.append(x)
        return out

    def send_mail(subject: str, text: str) -> str:
        from semantic_bridge.alerts import smtp_settings

        to = recipients()
        if not to:
            return "no_recipients"
        cfg = smtp_settings()
        if not cfg:
            return "no_smtp"
        try:
            msg = EmailMessage()
            msg["Subject"], msg["From"], msg["To"] = subject, cfg["sender"], ", ".join(to)
            msg.set_content(text)
            ctx_ssl = ssl.create_default_context()
            server = (smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=20, context=ctx_ssl) if cfg["ssl"]
                      else smtplib.SMTP(cfg["host"], cfg["port"], timeout=20))
            with server as s:
                if not cfg["ssl"] and cfg["starttls"]:
                    s.starttls(context=ctx_ssl)
                if cfg["user"]:
                    s.login(cfg["user"], cfg["password"])
                s.send_message(msg)
            return "sent"
        except Exception as e:  # noqa: BLE001
            log.warning("model_quality: e-posta gönderilemedi: %s", e)
            return "failed"

    def link(path: str) -> str:
        base = (conf("ALERT_LINK") or "").split("/uyarilar")[0].rstrip("/")
        return f"{base}{path}" if base else ""

    def notify_broken(run: dict[str, Any]) -> str:
        lines = [f"{run['suiteLabel']} koşusunda {run['broken']} soru bozuldu (önceki koşuda sağlamdı).", ""]
        for cid in run.get("brokenIds", [])[:50]:
            lines.append(f"- {cid}")
        if len(run.get("brokenIds", [])) > 50:
            lines.append(f"… ve {len(run['brokenIds']) - 50} soru daha (ekranda tam liste).")
        if run.get("installsInWindow"):
            lines += ["", "Uyarı: ölçüm sırasında kurulum ya da katalog değişikliği oldu; fark başka bir işten gelmiş olabilir."]
        url = link(f"/zeki-kalite?sekme=kosular&kosu={run['id']}")
        if url:
            lines += ["", url]
        return send_mail(f"Zeki AI kalitesi: {run['broken']} soru bozuldu", "\n".join(lines))

    # ------------------------------------------------------------------ genel

    @app.get("/api/v1/model-quality/meta")
    def mq_meta(request: Request) -> dict[str, Any]:
        engine, tenant, ds, user, display = ctx(request)
        return {"suites": MQ.SUITES, "startable": list(MQ.STARTABLE), "caseStatuses": MQ.CASE_STATUSES,
                "runStatuses": MQ.RUN_STATUSES, "verdicts": MQ.VERDICTS, "triage": MQ.TRIAGE,
                "kindLabels": MQ.KIND_LABELS, "classes": MQ.load_classes(engine, active_only=False),
                "unclassified": MQ.UNCLASSIFIED, "windowDays": window_days(),
                "me": {"username": user, "display": display, "canRun": can(user, "ozellik:zeki-kalite.kosu"),
                       "canDecide": can(user, "ozellik:zeki-kalite.karar")}}

    # Karne kişiden bağımsız hesaplanır (hız 4. tur, 2026-09-29): soru kaydının pencere satırları (≈10 bin), geri
    # bildirim, SEO/çeviri/redaksiyon sayımları. Eskiden her açılışta yeniden kuruluyordu (tek başına 0,6 sn, ekran
    # başka uçlarla aynı anda açılınca 5–8 sn). Şimdi ortak bellekte: `KARNE_TAZE` (120 sn) tazeyse hemen; eskiyse eldeki
    # hemen + arkada yeniden hesap; «Verileri yenile» 60 sn'den eskiyse arkada; bu modülde yazma olunca düşer. Kişinin
    # göremediği modül satırı (sayfa yetkisi) bellekteki sonuçtan her istekte ayrı süzülür.
    from semantic_bridge import hizli_kaynak as HK

    karne = HK.bellek("kalite.karne", float(os.environ.get("MODEL_QUALITY_SCORECARD_FRESH_SEC") or 120), en_cok=32)

    def karne_hesap(engine, tenant: str, ds: str, d: int) -> Callable[[], dict[str, Any]]:
        def build() -> dict[str, Any]:
            # Sorgu bilgisi: karnenin koşan okumaları yakalanır (gösterilen = çalışan).
            return IZ.izli(engine, lambda: _karne_raw(engine, tenant, ds, d), prefix="portal.kalite.karne",
                           title="Kalite karnesi", text=F_KARNE, skip=("days",))
        return build

    def _karne_raw(engine, tenant: str, ds: str, d: int) -> dict[str, Any]:
        now, since = src.window(d)
        trend_since = min(since, now - timedelta(days=28))
        runs = src.last_finished(engine, tenant)
        rows: list[dict[str, Any]] = []

        def safe(rid: str, label: str, page: Any, fn):
            try:
                rows.append(fn())
            except Exception as e:  # noqa: BLE001
                log.warning("model_quality: karne satırı %s okunamadı: %s", rid, e)
                rows.append(MQ.unmeasured_row(rid, label, page, "okunamadı: " + str(e)[:160]))

        safe("bi", "Soru-cevap (Zeki AI)", "genel-bakis", lambda: MQ.bi_row(
            src.query_rows(engine, tenant, ds, trend_since), src.feedback_rows(engine, tenant, trend_since), runs,
            now=now, since=since))
        safe("seo", "SEO önerileri", "seo-urun", lambda: MQ.seo_row(src.seo_stats(engine, tenant, since)))
        safe("ceviri", "Çeviri taslağı", "ceviri", lambda: MQ.translation_row(src.translation_stats(engine, tenant, since)))
        safe("redaksiyon", "Redaksiyon önerileri", "redaksiyon", lambda: MQ.redaction_row(src.redaction_stats(engine, tenant, since)))
        rows.append(MQ.unmeasured_row("son-okuma", "Son okuma denetimleri", "son-okuma",
                                      "ölçülmedi — sonraki sürüm: editörün Doğru/Yanlış alarm kararlarından denetim başına isabet"))
        rows.append(MQ.unmeasured_row("destek", "Destek talebi sınıflandırma", None,
                                      "ölçülmedi — destek masasının talep sınıflandırması bağlandığında"))
        latest = MQ.list_versions(engine, tenant, page=0, size=1)["items"]
        return {"days": d, "rows": rows, "runs": runs, "version": latest[0] if latest else None,
                "generatedAt": now.isoformat()}

    def karne_gorunur(shared: dict[str, Any], user: str) -> dict[str, Any]:
        """Kişinin sayfa yetkisine göre satırlar (yetkisi olmayan modülün satırı gösterilmez, sayısı yazılır)."""
        seo_pages = ("sayfa:seo-urun", "sayfa:seo-geo")
        visible = []
        for r in shared["rows"]:
            page = r.get("page")
            ok = page is None or can(user, "sayfa:" + page) or (r["id"] == "seo" and any(can(user, p) for p in seo_pages))
            if ok:
                visible.append(r)
        return {**shared, "rows": visible, "hidden": len(shared["rows"]) - len(visible)}

    def karne_isit() -> None:
        r = rt()
        if HK.sqlite_mi(r.store.engine):
            return
        MQ.ensure(r.store.engine)
        d = window_days()
        karne.isit_gerekirse((r.settings.tenant_id, r.settings.datasource_id, d),
                             karne_hesap(r.store.engine, r.settings.tenant_id, r.settings.datasource_id, d))

    HK.acilista("kalite.karne", karne_isit)

    @app.get("/api/v1/model-quality/scorecard")
    async def mq_scorecard(request: Request, days: int | None = None) -> dict[str, Any]:
        engine, tenant, ds, user, _ = await run_in_threadpool(ctx, request)
        d = window_days(days)
        durt = request.headers.get("x-data-refresh") == "1"
        shared = await run_in_threadpool(HK.oku, karne, (tenant, ds, d), karne_hesap(engine, tenant, ds, d), durt=durt)
        return await run_in_threadpool(karne_gorunur, shared, user)

    # ------------------------------------------------------------------ koşular

    @app.get("/api/v1/model-quality/runs")
    def mq_runs(request: Request, suite: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _, _ = ctx(request)
        return IZ.izli(engine, lambda: MQ.list_runs(engine, tenant, suite=suite, page=page),
                       prefix="portal.kalite.kosular", title="Kalite koşuları", text=F_KOSU, skip=("page", "size"))

    @app.get("/api/v1/model-quality/runs/{run_id}")
    def mq_run(run_id: str, request: Request) -> dict[str, Any]:
        engine, tenant, _, _, _ = ctx(request)
        return IZ.izli(engine, lambda: call(MQ.get_run, engine, tenant, run_id),
                       prefix="portal.kalite.kosu", title="Kalite koşusu", text=F_KOSU)

    @app.get("/api/v1/model-quality/runs/{run_id}/cases")
    def mq_run_cases(run_id: str, request: Request, status: str = "", change: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _, _ = ctx(request)
        if change and change not in ("bozulan", "duzelen"):
            raise HTTPException(status_code=422, detail={"code": "INVALID", "message": "change bozulan ya da duzelen olmalı."})
        if status and status not in MQ.CASE_STATUSES:
            raise HTTPException(status_code=422, detail={"code": "INVALID", "message": "Geçersiz durum."})
        return IZ.izli(engine, lambda: call(MQ.run_cases, engine, tenant, run_id, status=status, change=change, page=page),
                       prefix="portal.kalite.vakalar", title="Koşunun vakaları", skip=("page", "size"),
                       text="Durum süzgeci sayaçları ve vaka satırları koşunun vaka kayıtlarından (durum başına sayım).")

    @app.post("/api/v1/model-quality/runs/start", status_code=201)
    def mq_run_start(body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, _, user, _ = ctx(request)
        need(user, "ozellik:zeki-kalite.kosu", "Kalite koşusu başlatma")
        out = call(MQ.request_run, engine, tenant, str(body.get("suite") or ""), user)
        audit(engine, user, "run", "model_quality_run", out["id"], f"{out['suiteLabel']} istendi", {"durum": "sirada"})
        return out

    @app.post("/api/v1/model-quality/run-due")
    def mq_run_due(request: Request, kind: str = "claim") -> dict[str, Any]:
        """Zamanlayıcı. kind=claim: sıradaki istekleri verir (betik koşturur, `--request` ile raporlar);
        stale: rapor getirmeyen koşuyu kapatır; digest: günlük geri bildirim özeti (günde bir kez)."""
        engine, tenant, by = system(request)
        out: dict[str, Any] = {"kind": kind}
        if kind in ("claim", "all"):
            out["jobs"] = MQ.claim_due(engine, tenant)
        if kind in ("stale", "all"):
            out["expired"] = MQ.expire_stale(engine, tenant, float(_int(conf("MODEL_QUALITY_STALE_HOURS"), 6, 1, 72)))
        if kind in ("digest", "all"):
            out["digest"] = digest(engine, tenant)
        if not set(out) - {"kind"}:
            raise HTTPException(status_code=422, detail={"code": "INVALID", "message": "kind claim, stale, digest ya da all olmalı."})
        return out

    def digest(engine, tenant: str) -> dict[str, Any]:
        today = datetime.now(timezone.utc).date().isoformat()
        if MQ.state_get(engine, tenant, "digest") == today:
            return {"sent": "already"}
        ds = rt().settings.datasource_id
        since = datetime.now(timezone.utc) - timedelta(days=1)
        fb = [f for f in src.feedback_rows(engine, tenant, since) if f["verdict"] != "dogru"]
        stale_days = _int(conf("MODEL_QUALITY_QUEUE_STALE_DAYS"), 7, 1, 365)
        q = src.feedback_queue(engine, tenant, ds, state="yeni", size=200)
        cutoff = datetime.now(timezone.utc) - timedelta(days=stale_days)
        old = sum(1 for it in q["items"] if it["at"] and MQ._parse_dt(it["at"]) < cutoff)
        if not fb and not old:
            MQ.state_set(engine, tenant, "digest", today)
            return {"sent": "nothing", "new": 0, "stale": 0}
        qs = src.queries_by_id(engine, tenant, ds, [f["query_id"] for f in fb])
        lines = [f"Son 24 saatte {len(fb)} geri bildirim: "
                 f"{sum(1 for f in fb if f['verdict'] == 'yanlis')} «Yanlış», {sum(1 for f in fb if f['verdict'] == 'kismen')} «Kısmen».", ""]
        for f in fb:
            qq = qs.get(f["query_id"]) or {}
            lines.append(f"- [{MQ.VERDICTS[f['verdict']]}] {str(qq.get('question') or '')[:160]}"
                         + (f" — not: {str(f.get('comment'))[:200]}" if f.get("comment") else ""))
        if old:
            lines += ["", f"Kuyrukta {stale_days} günden eski, sınıflanmamış {old} bildirim var."]
        url = link("/zeki-kalite?sekme=geri-bildirim")
        if url:
            lines += ["", url]
        sent = send_mail("Zeki AI kalitesi: günlük geri bildirim özeti", "\n".join(lines))
        if sent in ("sent", "no_recipients", "no_smtp"):
            MQ.state_set(engine, tenant, "digest", today)
        return {"sent": sent, "new": len(fb), "stale": old}

    @app.post("/api/v1/model-quality/report")
    def mq_report(body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Kapı betiğinin koşu raporu (`--report`). Köprü rapor anındaki sürümü kendisi kaydeder."""
        engine, tenant, by = system(request)
        code = str(body.get("codeSha") or "").strip() or None
        try:
            snap, inner = src.snapshot(rt, conf, code=code)
            if not snap.get("code_sha"):
                snap["code_sha"] = src.last_code_sha(engine, tenant)
            version = MQ.record_version(engine, tenant, snap, source="kosu", by=by, env=src.env_name(conf))
        except Exception as e:  # noqa: BLE001
            log.warning("model_quality: sürüm anlık görüntüsü alınamadı: %s", e)
            version, inner = None, {}
        out = call(MQ.ingest_report, engine, tenant, body, version=version, model_ref=inner.get("model_ref"),
                   env=src.env_name(conf), by=by,
                   releases_between=lambda a, b: src.itops_releases(engine, tenant, a, b))
        audit(engine, by, "run", "model_quality_run", out["id"], f"{out['suiteLabel']}: {out['total']} soru",
              {"bozulan": out["broken"], "duzelen": out["fixed"], "tally": out["tally"], "kirli": out["polluted"]})
        if out["broken"] > 0:
            threading.Thread(target=notify_broken, args=(out,), name="mq-broken-mail", daemon=True).start()
        karne.dusur()                       # karnenin son koşu satırı değişti
        return out

    # ------------------------------------------------------------------ sürümler

    @app.get("/api/v1/model-quality/versions")
    def mq_versions(request: Request, page: int = 0) -> dict[str, Any]:
        engine, tenant, _, _, _ = ctx(request)

        def read() -> dict[str, Any]:
            out = MQ.list_versions(engine, tenant, page=page)
            out["installs"] = src.itops_release_list(engine, tenant, limit=100) if page == 0 else []
            return out
        return IZ.izli(engine, read, prefix="portal.kalite.surumler", title="Sürümler", text=F_SURUM,
                       skip=("page", "size"))

    @app.post("/api/v1/model-quality/versions", status_code=201)
    def mq_version_record(body: dict[str, Any], request: Request) -> dict[str, Any]:
        """Kurulum sonu (`scripts/server/model-quality-version.sh`): kod sürümü + köprünün o anki durumu tek satır."""
        engine, tenant, by = system(request)
        code = str(body.get("codeSha") or "").strip()[:64] or None
        if code and not re.fullmatch(r"[0-9a-fA-F]{7,64}", code):
            raise HTTPException(status_code=422, detail={"code": "INVALID", "message": "Kod sürümü bir git kimliği (sha) olmalı."})
        env = str(body.get("env") or "").strip().lower() or src.env_name(conf)
        if env and env not in ("test", "vm"):
            raise HTTPException(status_code=422, detail={"code": "INVALID", "message": "Ortam test ya da vm olmalı."})
        snap, _ = src.snapshot(rt, conf, code=code)
        out = MQ.record_version(engine, tenant, snap, source="kurulum", by=str(body.get("by") or by)[:120], env=env,
                                note=body.get("note"), force=True)
        audit(engine, by, "create", "model_quality_version", str(out["id"]), f"Sürüm kaydı {str(code or '')[:12]}",
              {"kinds": out["kinds"], "env": env})
        karne.dusur()                       # karnenin sürüm satırı değişti
        return out

    # ------------------------------------------------------------------ hata sınıfları

    @app.get("/api/v1/model-quality/classes")
    async def mq_classes(request: Request, days: int | None = None) -> dict[str, Any]:
        engine, tenant, ds, _, _ = await run_in_threadpool(ctx, request)
        d = window_days(days)

        def build():
            return IZ.izli(engine, build_raw, prefix="portal.kalite.siniflar", title="Hata sınıfları", text=F_SINIF,
                           skip=("days",))

        def build_raw():
            now, since = src.window(d)
            classes = MQ.load_classes(engine, active_only=False)
            items = src.classified_items(engine, tenant, ds, min(since, now - timedelta(days=28)))
            in_window = [i for i in items if (MQ._aware(i["at"]) or now) >= since]
            board = MQ.class_board(items, classes, now=now, gate_cases=src.recent_gate_cases(engine, tenant))
            # Sayılar pencereye göre; eğilim son 4 hafta.
            per = {}
            for i in in_window:
                per[i["klass"]] = per.get(i["klass"], 0) + 1
            for r in board["items"]:
                r["questions"] = per.get(r["klass"], 0)
                r["fromFeedback"] = sum(1 for i in in_window if i["klass"] == r["klass"] and i["source"] == "geri-bildirim")
            board["errorQuestions"] = sum(r["questions"] for r in board["items"] if r["countsAsError"])
            board["total"] = len(in_window)
            board["days"] = d
            board["classes"] = classes
            return board

        return await run_in_threadpool(build)

    @app.get("/api/v1/model-quality/classes/{klass}/questions")
    async def mq_class_questions(klass: str, request: Request, days: int | None = None, page: int = 0) -> dict[str, Any]:
        engine, tenant, ds, _, _ = await run_in_threadpool(ctx, request)
        d = window_days(days)

        def build():
            return IZ.izli(engine, build_raw, prefix="portal.kalite.sinif", title="Sınıfın soruları", text=F_SINIF,
                           skip=("page", "size"))

        def build_raw():
            now, since = src.window(d)
            items = [i for i in src.classified_items(engine, tenant, ds, since) if i["klass"] == klass]
            size = 50
            p = max(0, int(page or 0))
            gate = [c for c in src.recent_gate_cases(engine, tenant) if (c.get("klass") or MQ.UNCLASSIFIED) == klass]
            return {"klass": klass, "total": len(items), "page": p, "size": size,
                    "items": [{**i, "at": MQ._iso(i["at"])} for i in items[p * size:(p + 1) * size]],
                    "gateCases": gate}

        return await run_in_threadpool(build)

    @app.patch("/api/v1/model-quality/classes/{klass}")
    def mq_class_update(klass: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, _, user, _ = ctx(request)
        need(user, "ozellik:zeki-kalite.karar", "Hata sınıfı kuralı düzenleme")
        out = call(MQ.update_class, engine, klass, body, user)
        audit(engine, user, "update", "model_quality_class", klass, out["label"],
              {k: body[k] for k in ("label", "active", "countsAsError", "rule", "sort") if k in body})
        return out

    # ------------------------------------------------------------------ başarısız soru kümeleri (öneri 20)

    from semantic_bridge import model_quality_clusters as MC

    cluster_job: dict[str, Any] = {"thread": None, "state": {"running": False, "startedAt": None, "finishedAt": None,
                                                             "error": None, "result": None}}
    cluster_lock = threading.Lock()

    def cluster_running() -> bool:
        t = cluster_job["thread"]
        return bool(t and t.is_alive())

    @app.get("/api/v1/model-quality/clusters")
    def mq_clusters(request: Request, status: str = "oneri") -> dict[str, Any]:
        engine, tenant, _, user, _ = ctx(request)
        if status not in ("", "oneri", "onaylandi", "reddedildi"):
            raise HTTPException(status_code=400, detail={"code": "INVALID", "message": "Bilinmeyen durum."})
        out = MC.listing(engine, tenant, status=status)
        out["job"] = {**cluster_job["state"], "running": cluster_running()}
        out["canDecide"] = can(user, "ozellik:zeki-kalite.karar")
        out["classes"] = [{"klass": k["klass"], "label": k["label"]} for k in MQ.load_classes(engine)]
        return out

    @app.post("/api/v1/model-quality/clusters/build", status_code=202)
    def mq_clusters_build(request: Request, days: int | None = None) -> dict[str, Any]:
        engine, tenant, ds, user, _ = ctx(request)
        need(user, "ozellik:zeki-kalite.karar", "Soru kümeleme")
        from semantic_bridge import book_similarity as BS
        from semantic_layer.runtime import llm_queue

        embed = BS.embedder()
        if embed is None:
            raise HTTPException(status_code=503, detail={"code": "UNAVAILABLE", "message": "Gömme servisi bu kurulumda tanımlı değil."})
        try:
            llm = rt().llm_for("zeki-kalite", llm_queue.BATCH)
        except Exception:  # noqa: BLE001
            llm = None
        choose = (lambda p, ch: llm.choose(p, ch)) if llm is not None and hasattr(llm, "choose") else None
        d = window_days(days)
        with cluster_lock:
            if cluster_running():
                return {"started": False, "job": cluster_job["state"]}
            stt = cluster_job["state"]

            def work() -> None:
                stt.update(running=True, startedAt=MQ._iso(MQ._now()), finishedAt=None, error=None, result=None)
                try:
                    stt["result"] = MC.build(engine, tenant, ds, days=d, embed=embed, choose=choose, conf=conf)
                except Exception as e:  # noqa: BLE001
                    log.warning("soru kümeleme başarısız: %s", e)
                    stt["error"] = str(e)[:400]
                finally:
                    stt.update(running=False, finishedAt=MQ._iso(MQ._now()))

            cluster_job["thread"] = threading.Thread(target=work, name="mq-clusters", daemon=True)
            cluster_job["thread"].start()
        audit(engine, user, "run", "model_quality_clusters", None, "Başarısız soru kümeleme", {"gun": d})
        return {"started": True, "job": cluster_job["state"]}

    @app.post("/api/v1/model-quality/clusters/{cid}/decide")
    def mq_cluster_decide(cid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, _, user, _ = ctx(request)
        need(user, "ozellik:zeki-kalite.karar", "Küme sınıflama")
        out = call(MC.decide, engine, tenant, cid, user, str(body.get("action") or ""),
                   str(body.get("klass") or "") or None, str(body.get("note") or "")[:1000] or None)
        audit(engine, user, "update", "model_quality_cluster", cid, "Soru kümesi kararı",
              {"islem": body.get("action"), "sinif": out.get("klass"), "soru": out.get("written")})
        src.clear_cache()
        return out

    # ------------------------------------------------------------------ geri bildirim kuyruğu

    @app.get("/api/v1/model-quality/queue")
    def mq_queue(request: Request, type: str = "feedback", verdict: str = "", state: str = "", page: int = 0) -> dict[str, Any]:
        engine, tenant, ds, _, _ = ctx(request)
        if type != "feedback":
            raise HTTPException(status_code=422, detail={"code": "INVALID",
                                                         "message": "Bu sürümde kuyrukta yalnız kullanıcı geri bildirimi var."})
        return IZ.izli(engine, lambda: src.feedback_queue(engine, tenant, ds, verdict=verdict, state=state, page=page),
                       prefix="portal.kalite.kuyruk", title="Geri bildirim kuyruğu", text=F_KUYRUK, skip=("page", "size"))

    @app.patch("/api/v1/model-quality/queue/feedback/{fid}")
    def mq_queue_decide(fid: str, body: dict[str, Any], request: Request) -> dict[str, Any]:
        engine, tenant, _, user, _ = ctx(request)
        need(user, "ozellik:zeki-kalite.karar", "Geri bildirim sınıflama")
        out = call(MQ.triage_feedback, engine, tenant, fid, body, user)
        audit(engine, user, "update", "model_quality_feedback", fid, out["verdictLabel"] or "",
              {k: body[k] for k in ("klass", "triageState", "note") if k in body})
        return out

    # ------------------------------------------------------------------ cevap altındaki düğme

    def give_feedback(request: Request, body: dict[str, Any]) -> dict[str, Any]:
        engine, tenant, ds, user, _ = ctx(request)
        qid = str(body.get("queryId") or "").strip()
        if not qid:
            raise HTTPException(status_code=422, detail={"code": "INVALID", "message": "Cevap kimliği (queryId) gerekli."})
        verdict = body.get("verdict")
        if not verdict and body.get("validated") is not None:
            verdict = "dogru" if body.get("validated") else "yanlis"        # eski gövde: {queryId, validated}
        row = src.query_row(engine, tenant, ds, qid)
        if row is None:
            raise HTTPException(status_code=404, detail={"code": "NOT_FOUND", "message": "Bu cevabın kaydı bulunamadı."})
        out = call(MQ.record_feedback, engine, tenant, row, user, str(verdict or ""), body.get("comment"),
                   is_admin=is_admin(user))
        if out["verdict"] == "yanlis":
            threading.Thread(target=repeat_alert, args=(engine, tenant, ds, row), name="mq-repeat", daemon=True).start()
        karne.dusur()                       # karnenin geri bildirim sayıları değişti
        return out

    def repeat_alert(engine, tenant: str, ds: str, row: dict[str, Any]) -> None:
        """Aynı soruya pencere içinde eşik kadar «Yanlış» geldiyse model ekibine anında bir kez yazılır."""
        try:
            threshold = _int(conf("MODEL_QUALITY_REPEAT_WRONG"), 3, 2, 1000)
            since = datetime.now(timezone.utc) - timedelta(days=window_days())
            n = src.same_question_wrong(engine, tenant, ds, row.get("normalized_question") or "", since)
            if n < threshold:
                return
            key = "repeat:" + MQ.digest_of(row.get("normalized_question") or "")[:24]
            if MQ.state_get(engine, tenant, key):
                return
            url = link("/zeki-kalite?sekme=geri-bildirim")
            text = (f"Aynı soruya son {window_days()} günde {n} kez «Yanlış» dendi:\n\n{str(row.get('question') or '')[:500]}\n"
                    + (f"\n{url}" if url else ""))
            if send_mail("Zeki AI kalitesi: aynı soruya tekrarlanan «Yanlış»", text) in ("sent", "no_recipients"):
                MQ.state_set(engine, tenant, key, datetime.now(timezone.utc).isoformat())
        except Exception as e:  # noqa: BLE001
            log.warning("model_quality: tekrar uyarısı yazılamadı: %s", e)

    @app.post("/api/v1/model-quality/feedback")
    def mq_feedback(body: dict[str, Any], request: Request) -> dict[str, Any]:
        return give_feedback(request, body)

    @app.get("/api/v1/model-quality/feedback/mine")
    def mq_feedback_mine(request: Request, queryId: str) -> dict[str, Any]:
        engine, tenant, _, user, _ = ctx(request)
        return {"feedback": MQ.my_feedback(engine, tenant, queryId, user)}

    return Service(feedback=give_feedback)
