"""Kişisel «Bugün» özeti (AI fırsatları öneri 19): Kampüs'te bildirim zilinin yanında, kişinin bugünkü işi.

**Kural toplama** (rakamı kod sayar; her madde ilgili ekrana bağlantı taşır). Her kaynak kişinin **yetkisiyle** süzülür:
sayfa yetkisi olmayan modülün maddesi hiç okunmaz (`can(user, "sayfa:…")`), onay kuyrukları ilgili `ozellik:*` onay
yetkisini ister; kişi kendi gönderdiği işi onay kuyruğunda görmez.

| Kaynak | Yetki | Madde |
|---|---|---|
| Uyarılar | `sayfa:uyarilar` | kişinin kurduğu, eşiği aşmış uyarı kuralları |
| Kurumsal e-posta | `sayfa:kurumsal-eposta` | bana atanan açık iletiler; ilk yanıt süresi geçmiş (SLA aşıldı) ve `BUGUN_SLA_SAAT` içinde dolacak |
| Ajanda | oturum | sorumlusu ben olan bugünkü ve geciken fuar görevleri (M27 portal kaydı) |
| Lansman | `sayfa:pazarlama-lansman` | bugün ve geciken lansman kontrol listesi maddelerim |
| Saha | `sayfa:saha` | görülmemiş saha bildirimlerim (reddedilen tahsilat, riske takılan sipariş…) |
| Onay kuyrukları | `ozellik:pazarlama.plan-onay`, `saha.odeme-plani-onay`, `bayi.limit-onay`, `topluluk.segment-onay` | onay bekleyen plan, ödeme planı, limit önerisi, okur segmenti |
| Okur sesi | `sayfa:uretim` | açık baskı/cilt hatası kümesi uyarıları (öneri 15) |

**Özet:** kural özeti her zaman vardır (üç cümle, sayılar maddelerden). Zeki AI özeti yalnız kişi paneli açınca istenir
(NORMAL), girdi (maddelerin sayıları) aynı kaldıkça gün içinde yeniden yazılmaz (`semantic_today_briefs`); metindeki her
sayı maddelerde geçmek zorunda (`marketing.guard.check`), üç cümleden fazlası kesilir; cümle kalmazsa kural özeti.
Modele yalnız madde başlığı ve sayı gider (kişi adı, e-posta konusu, gönderen gitmez).
"""
from __future__ import annotations

import hashlib
import logging
import re
import threading
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_bridge.marketing import guard as G

log = logging.getLogger("semantic.today_brief")

_md = sa.MetaData()
BRIEFS = sa.Table(
    "semantic_today_briefs", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("kullanici", sa.String(120), primary_key=True),
    sa.Column("gun", sa.String(10), nullable=False),
    sa.Column("girdi", sa.String(40), nullable=False),
    sa.Column("metin", sa.Text),
    sa.Column("dusen", sa.Integer, nullable=False, default=0),
    sa.Column("zaman", sa.DateTime(timezone=True), nullable=False),
)

SYSTEM = ("Sen TİMAŞ Yayınları çalışanına günün işlerini özetleyen Zeki AI'sın. Türkçe, samimi ama kısa yaz. Yalnız verilen "
          "maddeleri kullan; maddelerde olmayan hiçbir sayı yazma, sayıları toplama ya da yeni hesap yapma. Kişi adı ve "
          "teknoloji adı yazma. En acil işi öne al.")
PROMPT = ("Bugünkü maddeler (öncelik sırasıyla; yazabileceğin sayılar yalnız bunlar):\n{maddeler}\n\nTam üç cümlelik özet yaz: "
          "ilk cümle en acil iş, ikincisi bekleyen onay ya da yanıtlar, üçüncüsü günün geri kalanı. Başlık ya da madde işareti "
          "kullanma.")
PRIORITY = {1: "acil", 2: "bugün", 3: "bilgi"}

_ready: set[int] = set()
_lock = threading.Lock()


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        from semantic_layer.store import schema_stamp
        schema_stamp.create_all(_md, engine)
        _ready.add(id(engine))


def now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(v: Optional[datetime]) -> Optional[datetime]:
    if v is None:
        return None
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def settings(conf: Callable[[str], str]) -> dict[str, Any]:
    raw = (conf("BUGUN_SLA_SAAT") or "").strip().replace(",", ".")
    try:
        soon = max(0.5, min(72.0, float(raw))) if raw else 4.0
    except ValueError:
        soon = 4.0
    return {"slaSoonHours": soon}


def _has(engine: sa.engine.Engine, table: str) -> bool:
    try:
        return sa.inspect(engine).has_table(table)
    except Exception:  # noqa: BLE001
        return False


def item(kaynak: str, baslik: str, sayi: int, link: str, oncelik: int, detay: Optional[str] = None) -> dict[str, Any]:
    return {"kaynak": kaynak, "baslik": baslik, "sayi": int(sayi), "link": link, "oncelik": oncelik,
            "oncelikAdi": PRIORITY[oncelik], "detay": detay}


# ------------------------------------------------------------------ kaynaklar (her biri yalnız okuma)


def alerts_items(engine, tenant: str, user: str) -> list[dict[str, Any]]:
    if not _has(engine, "semantic_alert_rules"):
        return []
    from semantic_bridge import alerts as A

    with engine.connect() as c:
        rows = c.execute(sa.select(A.RULES.c.title).where(A.RULES.c.tenant_id == tenant, sa.func.lower(A.RULES.c.created_by) == user.lower(),
                                                          A.RULES.c.status == "active", A.RULES.c.state == "triggered")).all()
    if not rows:
        return []
    names = ", ".join(r.title for r in rows[:3]) + (" …" if len(rows) > 3 else "")
    return [item("uyari", "Eşiği aşan uyarı kuralım", len(rows), "/uyarilar", 1, names)]


def mail_items(engine, tenant: str, user: str, st: dict[str, Any], at: Optional[datetime] = None) -> list[dict[str, Any]]:
    if not _has(engine, "semantic_mail_messages"):
        return []
    from semantic_bridge import mailbox as MB

    at = at or now()
    soon = at + timedelta(hours=st["slaSoonHours"])
    with engine.connect() as c:
        rows = c.execute(sa.select(MB.MESSAGES.c.due_at, MB.MESSAGES.c.first_reply_at).where(
            MB.MESSAGES.c.tenant_id == tenant, sa.func.lower(MB.MESSAGES.c.assignee) == user.lower(),
            MB.MESSAGES.c.status.in_(MB.OPEN), MB.MESSAGES.c.historical == sa.false())).all()
    if not rows:
        return []
    late = sum(1 for r in rows if r.first_reply_at is None and r.due_at is not None and _aware(r.due_at) < at)
    near = sum(1 for r in rows if r.first_reply_at is None and r.due_at is not None and at <= _aware(r.due_at) <= soon)
    out = []
    if late:
        out.append(item("sla", "Yanıt süresi geçmiş e-posta", late, "/kurumsal-eposta?sekme=mine", 1))
    if near:
        out.append(item("sla", f"{st['slaSoonHours']:g} saat içinde yanıt süresi dolacak e-posta", near,
                        "/kurumsal-eposta?sekme=mine", 2))
    out.append(item("eposta", "Bana atanmış açık e-posta", len(rows), "/kurumsal-eposta?sekme=mine", 3))
    return out


def agenda_items(engine, tenant: str, user: str, today: date) -> list[dict[str, Any]]:
    if not _has(engine, "semantic_events_fairs"):
        return []
    from semantic_bridge import events as E

    try:
        ag = E.agenda(engine, tenant, user, [], now=today, days=0)
    except Exception as e:  # noqa: BLE001
        log.info("bugün: ajanda okunamadı: %s", e)
        return []
    tasks = [x for x in ag["items"] if x["kind"] == "gorev"]
    late = [x for x in tasks if x.get("late")]
    due = [x for x in tasks if not x.get("late") and x["day"] == today.isoformat()]
    fairs = [x for x in ag["items"] if x["kind"] == "fuar"]
    out = []
    if late:
        out.append(item("ajanda", "Süresi geçmiş fuar/etkinlik görevim", len(late), late[0]["link"], 1))
    if due:
        out.append(item("ajanda", "Bugün son günü olan görevim", len(due), due[0]["link"], 2))
    if fairs:
        out.append(item("ajanda", "Bugün süren fuar ya da etkinliğim", len(fairs), fairs[0]["link"], 3, fairs[0]["title"]))
    return out


def launch_items(engine, tenant: str, user: str) -> list[dict[str, Any]]:
    if not _has(engine, "semantic_mkt_launches"):
        return []
    from semantic_bridge.marketing import launch as L

    rows = L.today_tasks(engine, tenant, user, mine=True)
    if not rows:
        return []
    late = sum(1 for r in rows if r.get("gecikti"))
    out = []
    if late:
        out.append(item("lansman", "Geciken lansman maddem", late, "/pazarlama/lansman", 1))
    if len(rows) - late:
        out.append(item("lansman", "Bugünkü lansman maddem", len(rows) - late, "/pazarlama/lansman", 2))
    return out


def field_items(engine, tenant: str, user: str) -> list[dict[str, Any]]:
    if not _has(engine, "semantic_field_events"):
        return []
    from semantic_bridge import field_sales as F

    with engine.connect() as c:
        n = c.execute(sa.select(sa.func.count()).select_from(F.EVENTS).where(
            F.EVENTS.c.tenant_id == tenant, F.EVENTS.c.sahip == user, F.EVENTS.c.goruldu.is_(None))).scalar() or 0
    return [item("saha", "Görülmemiş saha bildirimim", n, "/saha", 2)] if n else []


def approval_items(engine, tenant: str, user: str, flag: Callable[[str], bool]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    u = user.lower()
    with engine.connect() as c:
        if flag("ozellik:pazarlama.plan-onay") and _has(engine, "semantic_mkt_plans"):
            from semantic_bridge.marketing import core as C

            rows = c.execute(sa.select(C.PLANS.c.id, C.PLANS.c.kind, C.PLANS.c.donem).where(
                C.PLANS.c.tenant_id == tenant, C.PLANS.c.durum == "onayda",
                sa.func.lower(sa.func.coalesce(C.PLANS.c.gonderen, "")) != u)).all()
            if rows:
                r0 = rows[0]
                link = f"/pazarlama/aylik-plan/{r0.donem}" if r0.kind == "aylik" and r0.donem else f"/pazarlama/plan/{r0.id}"
                out.append(item("onay", "Onayımı bekleyen pazarlama planı", len(rows), link, 2))
        if flag("ozellik:saha.odeme-plani-onay") and _has(engine, "semantic_field_payment_plans"):
            from semantic_bridge import field_sales as F

            n = c.execute(sa.select(sa.func.count()).select_from(F.PLANS).where(
                F.PLANS.c.tenant_id == tenant, F.PLANS.c.durum == "onayda",
                sa.func.lower(sa.func.coalesce(F.PLANS.c.gonderen, F.PLANS.c.oneren)) != u)).scalar() or 0
            if n:
                out.append(item("onay", "Onayımı bekleyen ödeme planı", n, "/saha?sekme=plan", 2))
        if flag("ozellik:bayi.limit-onay") and _has(engine, "semantic_dealer_limit_proposals"):
            from semantic_bridge import dealers as D

            n = c.execute(sa.select(sa.func.count()).select_from(D.PROPOSALS).where(
                D.PROPOSALS.c.tenant_id == tenant, D.PROPOSALS.c.durum == "oneri")).scalar() or 0
            if n:
                out.append(item("onay", "Karar bekleyen bayi limit önerisi", n, "/bayi-risk?sekme=limit", 2))
        if flag("ozellik:topluluk.segment-onay") and _has(engine, "semantic_okur_segments"):
            from semantic_bridge import okur as O

            n = c.execute(sa.select(sa.func.count()).select_from(O.SEGMENTS).where(
                O.SEGMENTS.c.tenant_id == tenant, O.SEGMENTS.c.durum == "onay_bekliyor",
                sa.func.lower(O.SEGMENTS.c.yazan) != u)).scalar() or 0
            if n:
                out.append(item("onay", "KVKK onayımı bekleyen okur segmenti", n, "/okur-toplulugu/segmentler", 2))
    return out


def voice_items(engine, tenant: str, reviews_page: bool) -> list[dict[str, Any]]:
    if not _has(engine, "semantic_reader_voice_alerts"):
        return []
    from semantic_bridge import reader_voice as V

    rows = V.alerts(engine, tenant, open_only=True)
    if not rows:
        return []
    return [item("okur-sesi", "Okur metinlerinde baskı/cilt hatası kümesi olan kitap", len(rows),
                 "/okur-toplulugu/yorumlar" if reviews_page else "/uretim", 1,
                 ", ".join((r["ad"] or r["anahtar"]) for r in rows[:3]) + (" …" if len(rows) > 3 else ""))]


def collect(engine, tenant: str, user: str, flag: Callable[[str], bool], st: dict[str, Any],
            today: Optional[date] = None, at: Optional[datetime] = None) -> dict[str, Any]:
    """Bütün kaynaklar, yetkiyle süzülmüş. Bir kaynak okunamazsa diğerleri sürer; hata adıyla döner (sessiz değil)."""
    today = today or now().astimezone(timezone(timedelta(hours=3))).date()
    items: list[dict[str, Any]] = []
    errors: list[str] = []
    steps: list[tuple[str, bool, Callable[[], list[dict[str, Any]]]]] = [
        ("Uyarılar", flag("sayfa:uyarilar"), lambda: alerts_items(engine, tenant, user)),
        ("Kurumsal e-posta", flag("sayfa:kurumsal-eposta"), lambda: mail_items(engine, tenant, user, st, at)),
        ("Ajanda", True, lambda: agenda_items(engine, tenant, user, today)),
        ("Lansman", flag("sayfa:pazarlama-lansman"), lambda: launch_items(engine, tenant, user)),
        ("Saha", flag("sayfa:saha"), lambda: field_items(engine, tenant, user)),
        ("Onaylar", True, lambda: approval_items(engine, tenant, user, flag)),
        ("Okur sesi", flag("sayfa:uretim"), lambda: voice_items(engine, tenant, flag("sayfa:okur-yorumlar"))),
    ]
    for name, allowed, fn in steps:
        if not allowed:
            continue
        try:
            items += fn()
        except Exception as e:  # noqa: BLE001 — bir modül kurulu değilse ya da okunamazsa özet diğerleriyle sürer
            log.warning("bugün: %s okunamadı: %s", name, e)
            errors.append(name)
    items.sort(key=lambda x: (x["oncelik"], -x["sayi"], x["baslik"]))
    return {"gun": today.isoformat(), "items": items, "okunamayan": errors, "kuralOzeti": rule_summary(items)}


# ------------------------------------------------------------------ özet


def rule_summary(items: list[dict[str, Any]]) -> str:
    if not items:
        return "Bugün için bekleyen bir işin görünmüyor. Onay kuyruklarında sana düşen iş yok. İyi çalışmalar."
    urgent = [x for x in items if x["oncelik"] == 1]
    approvals = [x for x in items if x["kaynak"] in ("onay", "eposta", "sla") and x["oncelik"] != 1]
    rest = [x for x in items if x not in urgent and x not in approvals]

    def join(xs: list[dict[str, Any]]) -> str:
        return ", ".join(f"{x['baslik'].lower()} {x['sayi']}" for x in xs)

    s1 = f"Öncelik: {join(urgent)}." if urgent else "Acil görünen bir iş yok."
    s2 = f"Bekleyenler: {join(approvals)}." if approvals else "Onayını ya da yanıtını bekleyen iş yok."
    s3 = f"Günün geri kalanı: {join(rest)}." if rest else "Diğer modüllerde sana düşen yeni iş yok."
    return " ".join((s1, s2, s3))


def facts(items: list[dict[str, Any]]) -> list[str]:
    return [f"{x['oncelikAdi']}: {x['baslik']}: {x['sayi']}" for x in items]


def input_hash(items: list[dict[str, Any]]) -> str:
    return hashlib.sha1("\n".join(facts(items)).encode("utf-8")).hexdigest()


def cached(engine, tenant: str, user: str, day: str, items: list[dict[str, Any]]) -> Optional[dict[str, Any]]:
    ensure(engine)
    with engine.connect() as c:
        r = c.execute(sa.select(BRIEFS).where(BRIEFS.c.tenant_id == tenant, BRIEFS.c.kullanici == user.lower())).first()
    if r is None or r.gun != day or not r.metin:
        return None
    return {"metin": r.metin, "dusen": r.dusen, "zaman": _aware(r.zaman).isoformat(), "guncel": r.girdi == input_hash(items)}


def write(engine, tenant: str, user: str, day: str, items: list[dict[str, Any]], llm: Any) -> dict[str, Any]:
    """Zeki AI üç cümle. Girdi aynıysa model çağrılmaz. Denetim `guard.check`; cümle kalmazsa kayıt boş, kural özeti."""
    ensure(engine)
    hit = cached(engine, tenant, user, day, items)
    if hit and hit["guncel"]:
        return {**hit, "onbellek": True}
    metin, dusen = None, 0
    if items and llm is not None:
        fx = facts(items)
        raw = str(llm.chat([{"role": "system", "content": SYSTEM},
                            {"role": "user", "content": PROMPT.format(maddeler="\n".join(f"- {f}" for f in fx))}], max_tokens=260) or "")
        raw = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
        res = G.check(raw, [x["baslik"] for x in items], fx)
        dusen = res["dusenSayisi"]
        sents = [s for s in re.split(r"(?<=[.!?…])\s+", res["metin"].replace("\n", " ")) if s.strip()]
        metin = " ".join(sents[:3]) or None
    with engine.begin() as c:
        c.execute(BRIEFS.delete().where(BRIEFS.c.tenant_id == tenant, BRIEFS.c.kullanici == user.lower()))
        c.execute(BRIEFS.insert().values(tenant_id=tenant, kullanici=user.lower(), gun=day, girdi=input_hash(items), metin=metin,
                                         dusen=dusen, zaman=now()))
    return {"metin": metin, "dusen": dusen, "zaman": now().isoformat(), "guncel": True, "onbellek": False}
