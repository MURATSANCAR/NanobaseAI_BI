"""M48 halka denetimleri ve iş toplayıcı. Hepsi yalnız okur; hiçbir servis yeniden başlatılmaz.

Bağlantı denemeleri Yönetim → Genel durum'daki denemelerin aynısıdır (`admin.run_check`: Logo, CRM, dizin); bunlara
veri sonu sorgusu eklenir. Model halkası LLM kapısından geçer (`llm_for("sistem", BATCH)`): kuyruk doluyken «model yok»
diye yanlış alarm çıkmasın diye sırada bekleme ile modelin kendi süresi ayrı ölçülür. E-posta halkası posta sunucusuna
bağlanıp oturum açar, **gönderim yapmaz**. Şirket ağı bağlantısı arayüz + (verilmişse) ağın içindeki bir adrese doğrudan
TCP denemesiyle ölçülür — yerel tünel ağzı ağ kopukken de bağlantı kabul eder, ona bakmak yanlış yeşil verir.
"""

from __future__ import annotations

import concurrent.futures as cf
import logging
import os
import re
import shutil
import smtplib
import socket
import ssl
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_bridge import it_ops as I

log = logging.getLogger("semantic_bridge.it_ops.sources")

_NAME = re.compile(r"^[A-Za-z0-9_$-]+$")


@dataclass
class Ctx:
    """Denetimlerin ihtiyaç duyduğu her şey; köprü (`it_ops_api`) doldurur, testler sahtesini verir."""
    engine: Any
    tenant: str
    conf: Callable[[str, str], str]
    logo_file: Callable[[], str]
    crm_file: Callable[[], str]
    llm: Callable[[], Any] = lambda: None
    run_check: Optional[Callable[[str], dict[str, Any]]] = None
    in_container: Optional[bool] = None
    overrides: dict[str, Callable[["Ctx"], dict[str, Any]]] = field(default_factory=dict)


def in_container(ctx: Ctx) -> bool:
    if ctx.in_container is not None:
        return ctx.in_container
    env = (os.environ.get("ITOPS_ENV") or "").strip().lower()
    if env:
        return env == "vm"
    return Path("/.dockerenv").exists()


def _num(ctx: Ctx, key: str, default: int) -> int:
    try:
        return max(1, int(str(ctx.conf(key, str(default)) or default)))
    except ValueError:
        return default


def _res(ok: Optional[bool], detail: str, *, ms: Optional[int] = None, data_end: Optional[datetime] = None,
         sql: Optional[str] = None) -> dict[str, Any]:
    return {"ok": ok, "detail": detail, "latency_ms": ms, "data_end": data_end, "sql": sql}


def _connector(path: str, timeout: int):
    from semantic_layer.profiler.connectors import connector_from_file

    if not path or not Path(path).exists():
        raise RuntimeError("Bağlantı dosyası bu kurulumda tanımlı değil.")
    conn = connector_from_file(path)
    conn.query_timeout = timeout
    return conn


def _one(path: str, sql: str, timeout: int) -> list[dict[str, Any]]:
    conn = _connector(path, timeout)
    try:
        _cols, rows, _trunc = conn.execute(sql, 1000)
        return rows
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def _dt(v: Any) -> Optional[datetime]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v if v.tzinfo else v.replace(tzinfo=timezone(timedelta(hours=3)))   # Logo/CRM saatleri İstanbul
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day, tzinfo=timezone(timedelta(hours=3)))
    try:
        return _dt(datetime.fromisoformat(str(v)[:19]))
    except ValueError:
        return None


def crm_utc(v: Any) -> Optional[datetime]:
    """CRM `ModifiedOn` UTC'dir. Bağlantı değeri metin de döndürebilir ('2026-09-28T09:09:15'); metin de UTC okunur —
    `_dt` onu İstanbul sayıp 3 saat geri kaydırıyordu (2026-09-28 kabulü K2: 180 dk fark)."""
    if v is None or v == "":
        return None
    if not isinstance(v, datetime):
        try:
            v = datetime.fromisoformat(str(v)[:19])
        except ValueError:
            return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


# ------------------------------------------------------------------ veri sonu sorguları (kabulde birebir kullanılır)


def logo_current_firm(run: Callable[[str], list[dict[str, Any]]]) -> str:
    """Bugünün yılını tutan (yoksa en yeni) Logo firması. Yıl → firma eşlemesi bütçe modülünün `firms_by_year`'ıdır
    (L_CAPIPERIOD); sabit bir firma numarası yazılmaz (bellek logo-period-prefixes-are-years)."""
    from semantic_bridge.budget_sources import firms_by_year

    firms = firms_by_year(run)
    if not firms:
        raise RuntimeError("Logo'da etkin dönem bulunamadı.")
    year = datetime.now().year
    return firms.get(year) or firms[max(firms)]


def logo_data_end_sql(firm: str) -> str:
    """Son iptal edilmemiş fatura günü. Bugünden ileri tarihli hatalı kayıt veriyi taze göstermesin diye bugünle sınırlı."""
    if not re.fullmatch(r"\d{3}", firm):
        raise ValueError("firma numarası üç haneli olmalı")
    return (f"SELECT MAX(DATE_) AS son FROM dbo.LG_{firm}_01_INVOICE "
            "WHERE CANCELLED = 0 AND DATE_ <= CAST(GETDATE() AS date)")


def crm_prefix(schema: str) -> str:
    db, _, sch = (schema or "").strip().rpartition(".")
    for part in (db, sch):
        if part and not _NAME.match(part):
            raise ValueError(f"CRM şeması «{schema}» geçerli bir ad değil.")
    if not sch:
        raise ValueError("CRM şeması girilmemiş.")
    return (f"{db}." if db else "") + f"{sch}."


def crm_data_end_sql(schema: str, table: str = "new_kitapBase") -> str:
    if not _NAME.match(table):
        raise ValueError("tablo adı geçersiz")
    return f"SELECT MAX(ModifiedOn) AS son FROM {crm_prefix(schema)}{table} WHERE ModifiedOn <= GETUTCDATE()"


# ------------------------------------------------------------------ halkalar


def _admin_check(ctx: Ctx, check_id: str) -> dict[str, Any]:
    if ctx.run_check is not None:
        return ctx.run_check(check_id)
    from semantic_bridge import admin as admin_mod

    return admin_mod.run_check(check_id)


def check_logo(ctx: Ctx) -> dict[str, Any]:
    r = _admin_check(ctx, "database")
    if not r["ok"]:
        return _res(False, r["message"], ms=r.get("ms"))
    t0 = time.monotonic()
    try:
        path = ctx.logo_file()
        timeout = _num(ctx, "ITOPS_QUERY_TIMEOUT_SEC", 60)
        firm = logo_current_firm(lambda sql: _one(path, sql, timeout))
        end_sql = logo_data_end_sql(firm)
        rows = _one(path, end_sql, timeout)
        end = _dt(rows[0].get("son")) if rows else None
    except Exception as e:  # noqa: BLE001
        log.warning("itops: Logo veri sonu okunamadı: %s", e)
        return _res(False, f"Bağlandı ama son fatura okunamadı: {str(e)[:300]}", ms=r.get("ms"))
    ms = (r.get("ms") or 0) + int((time.monotonic() - t0) * 1000)
    if end is None:
        return _res(False, "Bağlandı ama faturası olan dönem yok.", ms=ms)
    return _res(True, f"Bağlandı. Son fatura {end.date().isoformat()}.", ms=ms, data_end=end, sql=end_sql)


def check_crm(ctx: Ctx) -> dict[str, Any]:
    r = _admin_check(ctx, "crm")
    if not r["ok"]:
        return _res(False, r["message"], ms=r.get("ms"))
    t0 = time.monotonic()
    try:
        sql = crm_data_end_sql(ctx.conf("CRM_SCHEMA", "Timas_MSCRM.dbo"),
                               ctx.conf("ITOPS_CRM_FRESH_TABLE", "new_kitapBase") or "new_kitapBase")
        rows = _one(ctx.crm_file(), sql, _num(ctx, "ITOPS_QUERY_TIMEOUT_SEC", 60))
        raw = rows[0].get("son") if rows else None
        end = crm_utc(raw)
    except Exception as e:  # noqa: BLE001
        log.warning("itops: CRM veri sonu okunamadı: %s", e)
        return _res(False, f"Bağlandı ama son değişiklik okunamadı: {str(e)[:300]}", ms=r.get("ms"))
    ms = (r.get("ms") or 0) + int((time.monotonic() - t0) * 1000)
    if end is None:
        return _res(False, "Bağlandı ama kitap kaydı okunamadı.", ms=ms)
    return _res(True, "Bağlandı. Son kitap kaydı değişikliği okundu.", ms=ms, data_end=end, sql=sql)


def check_login(ctx: Ctx) -> dict[str, Any]:
    r = _admin_check(ctx, "directory")
    return _res(bool(r["ok"]), r["message"], ms=r.get("ms"))


def check_model(ctx: Ctx) -> dict[str, Any]:
    llm = ctx.llm()
    if llm is None:
        return _res(False, "Zeki AI modeli bu kurulumda tanımlı değil.")
    admitted: dict[str, float] = {}
    timeout = _num(ctx, "ITOPS_MODEL_TIMEOUT_SEC", 240)
    box: dict[str, Any] = {}

    def call() -> None:
        try:
            box["out"] = llm.chat([{"role": "user", "content": "Yalnızca TAMAM yaz."}], max_tokens=8,
                                  on_admitted=lambda *a, **k: admitted.setdefault("at", time.monotonic()))
        except TypeError:
            box["out"] = llm.chat([{"role": "user", "content": "Yalnızca TAMAM yaz."}], max_tokens=8)
        except Exception as e:  # noqa: BLE001
            box["err"] = e

    t0 = time.monotonic()
    th = threading.Thread(target=call, name="itops-model", daemon=True)
    th.start()
    th.join(timeout)
    total = int((time.monotonic() - t0) * 1000)
    if th.is_alive():
        if "at" not in admitted and hasattr(llm, "last_wait_ms"):
            # Sırada bekliyor: model yok değil, meşgul. Kopma sayılmaz (ok None), bekleme ekranda yazar.
            return _res(None, f"Zeki AI modeli meşgul: {timeout} sn sırada bekledi, deneme sonraki tura kaldı.", ms=total)
        return _res(False, f"Zeki AI modeli {timeout} sn içinde cevap vermedi.", ms=total)
    if "err" in box:
        return _res(False, f"{type(box['err']).__name__}: {str(box['err'])[:300]}", ms=total)
    wait = int((admitted["at"] - t0) * 1000) if "at" in admitted else int(getattr(llm, "last_wait_ms", 0) or 0)
    model_ms = max(0, total - wait)
    if not " ".join(str(box.get("out") or "").split()):
        return _res(False, f"Zeki AI modeli bağlandı ama boş cevap verdi ({model_ms} ms).", ms=model_ms)
    return _res(True, f"Cevap geldi: model {model_ms} ms, sırada {wait} ms bekledi.", ms=model_ms)


def check_email(ctx: Ctx) -> dict[str, Any]:
    """Posta sunucusuna bağlanır, şifreli oturum açar, NOOP, çıkar. Kimseye posta gitmez."""
    from semantic_bridge.alerts import smtp_settings

    cfg = smtp_settings()
    if not cfg:
        return _res(False, "E-posta ayarı yok: posta sunucusu ya da gönderen adresi girilmemiş.")
    t0 = time.monotonic()
    try:
        tctx = ssl.create_default_context()
        server = (smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=20, context=tctx) if cfg["ssl"]
                  else smtplib.SMTP(cfg["host"], cfg["port"], timeout=20))
        with server as s:
            if not cfg["ssl"] and cfg["starttls"]:
                s.starttls(context=tctx)
            if cfg["user"]:
                s.login(cfg["user"], cfg["password"])
            code, _ = s.noop()
        ms = int((time.monotonic() - t0) * 1000)
        if code != 250:
            return _res(False, f"Posta sunucusu beklenmeyen cevap verdi ({code}).", ms=ms)
        return _res(True, f"Posta sunucusuna bağlanıldı ve oturum açıldı ({cfg['host']}). Gönderim yapılmadı.", ms=ms)
    except Exception as e:  # noqa: BLE001
        return _res(False, f"{type(e).__name__}: {str(e)[:300]}", ms=int((time.monotonic() - t0) * 1000))


def _tcp(host: str, port: int, timeout: float = 5.0) -> tuple[bool, int, str]:
    t0 = time.monotonic()
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, int((time.monotonic() - t0) * 1000), ""
    except OSError as e:
        return False, int((time.monotonic() - t0) * 1000), str(e)[:200]


def check_vpn(ctx: Ctx) -> dict[str, Any]:
    if in_container(ctx):
        return _res(None, "Bu kurulum şirket ağının içinde; ayrı bir ağ bağlantısı yok.")
    iface = (ctx.conf("ITOPS_VPN_IFACE", "tun0") or "").strip()
    probe = (ctx.conf("ITOPS_VPN_PROBE", "") or "").strip()
    if not iface and not probe:
        return _res(None, "Şirket ağı bağlantısı bu kurulumda izlenmiyor.")
    if iface:
        state = Path(f"/sys/class/net/{iface}/operstate")
        if not Path(f"/sys/class/net/{iface}").exists():
            return _res(False, "Şirket ağı bağlantısı yok: bağlantı arayüzü kapalı. Telefon onayı bekleniyor olabilir.")
        try:
            op = state.read_text().strip().lower()
        except OSError:
            op = "unknown"
        if op == "down":
            return _res(False, "Şirket ağı bağlantısı kapalı.")
    if probe:
        host, _, port = probe.rpartition(":")
        ok, ms, err = _tcp(host or probe, int(port or 1433))
        if not ok:
            return _res(False, f"Bağlantı açık görünüyor ama şirket ağındaki sunucuya ulaşılamıyor ({err}).", ms=ms)
        return _res(True, "Şirket ağındaki sunucuya ulaşılıyor.", ms=ms)
    return _res(True, "Şirket ağı bağlantısı açık.")


def check_vm(ctx: Ctx) -> dict[str, Any]:
    if in_container(ctx):
        # VM'in kendisi: zamanlanmış işleri çalıştıran kapsayıcı her işten sonra köprüye bildirir.
        with ctx.engine.connect() as c:
            last = c.execute(sa.select(sa.func.max(I.JOBS.c.last_at)).where(
                I.JOBS.c.tenant_id == ctx.tenant, I.JOBS.c.source == "jobs-container")).scalar()
        last = I._aware(last)
        if last is None:
            return _res(None, "Zamanlanmış işlerden henüz bildirim gelmedi.")
        limit = _num(ctx, "ITOPS_VM_HEARTBEAT_SEC", 1200)
        age = int((I._now() - last).total_seconds())
        if age > limit:
            return _res(False, f"Zamanlanmış işler {age // 60} dk'dır bildirim göndermiyor.")
        return _res(True, f"Zamanlanmış işler çalışıyor (son bildirim {max(0, age) // 60} dk önce).")
    url = (ctx.conf("ITOPS_VM_URL", "") or "").strip()
    if not url:
        return _res(None, "Müşteri VM'i adresi girilmemiş (Yönetim → Ayarlar → Sistem durumu).")
    t0 = time.monotonic()
    try:
        req = urllib.request.Request(url, method="GET", headers={"User-Agent": "ZEKI-sistem-durumu"})
        with urllib.request.urlopen(req, timeout=15) as res:
            code = res.status
    except urllib.error.HTTPError as e:
        code = e.code
    except Exception as e:  # noqa: BLE001
        return _res(False, f"Müşteri VM'ine ulaşılamıyor: {str(e)[:200]}", ms=int((time.monotonic() - t0) * 1000))
    ms = int((time.monotonic() - t0) * 1000)
    if code >= 500:
        return _res(False, f"Müşteri VM'i açık ama uygulama hata veriyor ({code}).", ms=ms)
    return _res(True, f"Müşteri VM'i cevap veriyor ({code}).", ms=ms)


CHECKERS: dict[str, Callable[[Ctx], dict[str, Any]]] = {
    "logo": check_logo, "crm": check_crm, "giris": check_login, "model": check_model,
    "eposta": check_email, "vpn": check_vpn, "vm": check_vm,
}


def run_rings(ctx: Ctx, rings: Optional[list[str]] = None) -> list[dict[str, Any]]:
    """Halkaları paralel dener (her biri kendi bağlantısıyla); asılı kalan deneme süresi dolunca «cevap yok» sayılır,
    iş parçacığı arkada kendi kendine biter. Model halkası kendi süresini yönetir."""
    ids = [r for r in (rings or [x["id"] for x in I.RINGS]) if r in CHECKERS]
    limit = _num(ctx, "ITOPS_RING_TIMEOUT_SEC", 90)
    model_limit = _num(ctx, "ITOPS_MODEL_TIMEOUT_SEC", 240) + 10
    pool = cf.ThreadPoolExecutor(max_workers=max(1, len(ids)), thread_name_prefix="itops")
    futs = {rid: pool.submit(ctx.overrides.get(rid, CHECKERS[rid]), ctx) for rid in ids}
    t0 = time.monotonic()
    out = []
    try:
        for rid, fut in futs.items():
            budget = (model_limit if rid == "model" else limit) - (time.monotonic() - t0)
            try:
                r = fut.result(timeout=max(1.0, budget))
            except cf.TimeoutError:
                r = _res(False, f"Deneme {limit} sn içinde bitmedi.", ms=int((time.monotonic() - t0) * 1000))
            except Exception as e:  # noqa: BLE001
                r = _res(False, f"{type(e).__name__}: {str(e)[:300]}")
            out.append({"ring": rid, **r})
    finally:
        pool.shutdown(wait=False)
    return out


# ------------------------------------------------------------------ iş toplayıcı

#: Test sunucusundaki zamanlayıcılar: Yönetim'deki altı zamanlayıcı + modüllerin kendi zamanlayıcıları. Kurulu
#: olmayan birim (müşteri VM'inde hiçbiri) atlanır; VM'de işleri kapsayıcı kendisi bildirir.
EXTRA_TIMERS = [
    {"unit": "timas-budget.timer", "label": "Bütçe gerçekleşmesi ve sapma uyarısı", "every": "saatte bir"},
    {"unit": "timas-distribution.timer", "label": "İlk dağılım takibi", "every": "zamanlı"},
    {"unit": "timas-corporate.timer", "label": "Kurumsal satış verisi", "every": "zamanlı"},
    {"unit": "timas-corporate-weekly.timer", "label": "Haftalık bayi özeti", "every": "haftalık"},
    {"unit": "timas-schools.timer", "label": "Okul tanıtım verisi", "every": "gece"},
    {"unit": "timas-schools-weekly.timer", "label": "Okul tanıtım haftalık", "every": "haftalık"},
    {"unit": "timas-field-gece.timer", "label": "Saha satış gece okuması", "every": "gece"},
    {"unit": "timas-web-watch.timer", "label": "Basın ve web taraması", "every": "gece 02:30"},
    {"unit": "timas-copurchase.timer", "label": "Birlikte alınan yazarlar", "every": "gece"},
    {"unit": "timas-admin-group.timer", "label": "Yetki grupları tazeleme", "every": "07:00 ve 12:00"},
    {"unit": "timas-crm-unassigned.timer", "label": "Departmansız CRM kullanıcıları e-postası", "every": "07:00 ve 12:00"},
    {"unit": "editor-crm-connector.timer", "label": "Editör CRM bağlayıcısı", "every": "gece 03:10"},
    {"unit": "timas-itops.timer", "label": "Sistem durumu denetimi", "every": "5 dk"},
]

_STAMP = re.compile(r"(\d{4}-\d{2}-\d{2}) (\d{2}:\d{2}:\d{2})")


def _stamp(v: Optional[str]) -> Optional[datetime]:
    """systemd zaman damgası («Mon 2026-09-28 08:25:29 +03») → UTC; sunucu saati İstanbul varsayılır."""
    if not v or v == "n/a":
        return None
    m = _STAMP.search(v)
    if not m:
        return None
    try:
        d = datetime.fromisoformat(f"{m.group(1)}T{m.group(2)}")
    except ValueError:
        return None
    off = re.search(r"([+-]\d{2})(\d{2})?\s*$", v.strip())
    tz = timezone(timedelta(hours=int(off.group(1)), minutes=int(off.group(2) or 0))) if off else timezone(timedelta(hours=3))
    return d.replace(tzinfo=tz).astimezone(timezone.utc)


def _loaded(unit: str) -> bool:
    try:
        out = subprocess.run(["systemctl", "show", unit, "-p", "LoadState"], capture_output=True, text=True, timeout=5).stdout
    except Exception:  # noqa: BLE001
        return False
    return "LoadState=loaded" in out


def collect_timers(ctx: Ctx) -> int:
    """Kurulu zamanlayıcıların son koşusu ve sonucu. Zamanlayıcının değil çağırdığı servisin sonucuna bakılır."""
    from semantic_bridge import admin as admin_mod

    if in_container(ctx) or shutil.which("systemctl") is None:
        return 0
    base = admin_mod.system_status()["timers"]
    times = admin_mod._timer_times()
    n = 0
    seen = {t["unit"] for t in base}
    items = list(base) + [{**t, **admin_mod._unit(t["unit"])} for t in EXTRA_TIMERS if t["unit"] not in seen]
    for t in items:
        if t.get("state") == "unknown" or not _loaded(t["unit"]):
            continue
        nxt, last = times.get(t["unit"], (t.get("next"), t.get("last")))
        svc = admin_mod._unit(t["unit"].replace(".timer", ".service"))
        failed = svc.get("state") == "failed" or (svc.get("result") not in (None, "", "success"))
        I.upsert_job(ctx.engine, ctx.tenant, t["unit"], label=t["label"], source="systemd", every=t.get("every"),
                     last_at=_stamp(last), next_at=_stamp(nxt), last_ok=None if not last else not failed,
                     last_error=(f"Son koşu başarısız ({svc.get('result') or svc.get('state')})." if failed else None))
        n += 1
    return n


def collect_tables(ctx: Ctx, datasource: str) -> int:
    """Modüllerin kendi tablolarındaki son durum: planlı rapor, uyarı kuralı, pano kartı, SEO eşitlemesi."""
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import alerts as alerts_mod

    n = 0
    try:
        reps = admin_mod.all_reports(ctx.engine, ctx.tenant, datasource)
        active = [r for r in reps if r.get("status") == "active"]
        bad = [r for r in reps if r.get("lastStatus") == "failed"]
        last = max((I._aware(r.get("lastRunAt")) for r in reps if r.get("lastRunAt")), default=None)
        I.upsert_job(ctx.engine, ctx.tenant, "tablo:planli-raporlar", label="Planlı raporlar", source="table", every="5 dk",
                     last_at=last, last_ok=not bad if reps else None, failed_count=len(bad), total_count=len(active),
                     last_error=("; ".join(f"{r.get('title')}: {r.get('lastError') or 'başarısız'}" for r in bad[:5])
                                 + (f" (+{len(bad) - 5})" if len(bad) > 5 else "")) if bad else None)
        n += 1
    except Exception as e:  # noqa: BLE001
        log.warning("itops: planlı raporlar okunamadı: %s", e)
    try:
        alerts_mod.ensure(ctx.engine)
        rules = alerts_mod.list_rules(ctx.engine, ctx.tenant, datasource)
        bad = [r for r in rules if r.get("state") == "error"]
        last = max((I._aware(r.get("last_checked_at")) for r in rules if r.get("last_checked_at")), default=None)
        I.upsert_job(ctx.engine, ctx.tenant, "tablo:uyarilar", label="Uyarı kuralları", source="table", every="15 dk",
                     last_at=last, last_ok=not bad if rules else None, failed_count=len(bad),
                     total_count=sum(1 for r in rules if r.get("status") == "active"),
                     last_error="; ".join(f"{r.get('title')}: {r.get('last_error')}" for r in bad[:5]) or None)
        n += 1
    except Exception as e:  # noqa: BLE001
        log.warning("itops: uyarı kuralları okunamadı: %s", e)
    try:
        cards = admin_mod.all_cards(ctx.engine, ctx.tenant, datasource)
        bad = [r for r in cards if r.get("lastError")]
        last = max((I._aware(r.get("lastAutoAt")) for r in cards if r.get("lastAutoAt")), default=None)
        I.upsert_job(ctx.engine, ctx.tenant, "tablo:pano-kartlari", label="Pano kartı tazeleme", source="table", every="15 dk",
                     last_at=last, last_ok=not bad if cards else None, failed_count=len(bad), total_count=len(cards),
                     last_error="; ".join(f"{r.get('title')}: {r.get('lastError')}" for r in bad[:5]) or None)
        n += 1
    except Exception as e:  # noqa: BLE001
        log.warning("itops: pano kartları okunamadı: %s", e)
    try:
        if sa.inspect(ctx.engine).has_table("semantic_seo_runs"):
            from semantic_bridge.seo_geo.store import RUNS

            with ctx.engine.connect() as c:
                rows = c.execute(sa.select(RUNS).where(RUNS.c.tenant_id == ctx.tenant)
                                 .order_by(RUNS.c.started_at.desc()).limit(20)).mappings().all()
            latest: dict[str, Any] = {}
            for r in rows:
                latest.setdefault(r["kind"], r)
            if latest:
                bad = [r for r in latest.values() if r["error"]]
                I.upsert_job(ctx.engine, ctx.tenant, "tablo:seo", label="SEO & GEO eşitlemesi", source="table",
                             every="gece", last_at=max(I._aware(r["finished_at"] or r["started_at"]) for r in latest.values()),
                             last_ok=not bad, failed_count=len(bad), total_count=len(latest),
                             last_error="; ".join(f"{r['kind']}: {r['error']}" for r in bad) or None)
                n += 1
    except Exception as e:  # noqa: BLE001
        log.warning("itops: SEO koşuları okunamadı: %s", e)
    return n


# ------------------------------------------------------------------ kapasite (ilk sürüm: anlık okuma, projeksiyon yok)


def _median(xs: list[float]) -> Optional[float]:
    xs = sorted(x for x in xs if x is not None)
    if not xs:
        return None
    m = len(xs) // 2
    return float(xs[m]) if len(xs) % 2 else (xs[m - 1] + xs[m]) / 2.0


def disk_paths(ctx: Ctx) -> list[str]:
    raw = (ctx.conf("ITOPS_DISK_PATHS", "") or "").strip()
    if raw:
        return [p.strip() for p in raw.split(",") if p.strip()]
    for p in ("/data/nanobaseai/bi", "/data", "/"):
        if Path(p).exists():
            return [p]
    return ["/"]


def capacity(ctx: Ctx, days: int = 7) -> dict[str, Any]:
    from semantic_layer.store import schema as S

    disks = []
    for p in disk_paths(ctx):
        try:
            u = shutil.disk_usage(p)
            disks.append({"path": p, "total": u.total, "used": u.used, "free": u.free, "ratio": u.used / u.total if u.total else None})
        except OSError as e:
            disks.append({"path": p, "error": str(e)[:200]})
    since = I._now() - timedelta(days=days)
    modules: dict[str, dict[str, list[float]]] = {}
    queries: list[float] = []
    q_count = q_err = 0
    with ctx.engine.connect() as c:
        insp = sa.inspect(ctx.engine)
        if insp.has_table("sl_llm_job"):
            for mod, wait, llm_ms in c.execute(sa.select(S.sl_llm_job.c.module, S.sl_llm_job.c.queue_wait_ms, S.sl_llm_job.c.llm_ms)
                                               .where(S.sl_llm_job.c.created_at > since, S.sl_llm_job.c.status == "DONE")):
                d = modules.setdefault(mod or "—", {"wait": [], "llm": []})
                if wait is not None:
                    d["wait"].append(float(wait))
                if llm_ms is not None:
                    d["llm"].append(float(llm_ms))
        if insp.has_table("sl_query_log"):
            cols = {x["name"] for x in insp.get_columns("sl_query_log")}
            if {"latency_ms", "created_at"} <= cols:
                err_col = S.sl_query_log.c.error if "error" in cols else sa.null()
                for lat, err in c.execute(sa.select(S.sl_query_log.c.latency_ms, err_col).where(S.sl_query_log.c.created_at > since)):
                    q_count += 1
                    if err:
                        q_err += 1
                    elif lat is not None:
                        queries.append(float(lat))
    return {
        "since": I._iso(since), "days": days, "disks": disks,
        "modules": sorted(({"module": m, "jobs": len(v["llm"]) or len(v["wait"]), "waitP50Ms": _median(v["wait"]),
                            "modelP50Ms": _median(v["llm"])} for m, v in modules.items()), key=lambda x: -(x["jobs"] or 0)),
        "questions": {"count": q_count, "errors": q_err, "latencyP50Ms": _median(queries)},
    }
