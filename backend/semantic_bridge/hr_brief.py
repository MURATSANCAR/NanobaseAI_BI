"""İK'nın Kampüs katkısı: kişisel «Bugün» maddeleri (today_brief kaynağı «İK») ve Kampüs'ün ortak insan kartları.

Kullanıcı kararı 2026-09-29:
- **Kişiye özel maddeler yalnız o kişinin kendi verisinden** gelir: kendi izin talebi ve bakiyesi, kendi evrak talebi,
  kendi açık anketi ve önerisi, kendi performans görevi. Başkasının kaydı hiçbir koşulda girmez.
- **Yönetici maddeleri rol bazlıdır**, rol veriden çıkar: kişi ancak özlük kaydında (izin, doğum günü/yıldönümü) ya da İK-0
  çalışan kaydında (performans) birilerinin yöneticisiyse görür ve yalnız kendi ekibini görür. Mülakat notu yalnız
  görüşmecisi olduğu görüşmeler için, aday adı olmadan.
- **Ortak kartlar** (herkes): şirket içi duyurular, aramıza katılanlar (bu ay son işe giriş), doğum günleri (gün/ay),
  iş yıldönümleri (bu hafta, yalnız ad ve yıl), bugün izinde (tür yok). Yaş, doğum yılı, izin türü, özlük alanı yok.

Her madde `today_brief.item` biçimindedir (kaynak «ik»); bağlantı yalnız kişinin açabildiği sayfaya verilir (`flag`).
"""
from __future__ import annotations

import logging
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_bridge.hr_core import load

log = logging.getLogger("semantic_bridge.hr.brief")

RECENT_DAYS = 3        # «talebim onaylandı/reddedildi», «evrak hazır» ne kadar süre görünür


def _day(v: Any) -> Optional[date]:
    if v is None:
        return None
    if isinstance(v, datetime):
        return (v if v.tzinfo else v.replace(tzinfo=timezone.utc)).astimezone(timezone(timedelta(hours=3))).date()
    return v


def _start(d: dict[str, Any]) -> Optional[date]:
    from semantic_bridge import hr_portal as PT

    return PT.to_date(d.get("s_ise_giris_tarihi")) or PT.to_date(d.get("f_ise_giris_tarihi"))


def _names(xs: list[str], n: int = 3) -> str:
    return ", ".join(xs[:n]) + (f" ve {len(xs) - n} kişi" if len(xs) > n else "")


# ------------------------------------------------------------------ kişisel «Bugün» maddeleri


def items(engine: sa.engine.Engine, tenant: str, user: str, flag: Callable[[str], bool], today: date,
          item: Callable[..., dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for name, fn in (("izin ve evrak", _leave_and_docs), ("anket ve öneri", _engagement), ("performans", _performance),
                     ("mülakat notu", _interviews), ("ekip kutlamaları", _team_people)):
        try:
            out += fn(engine, tenant, user, flag, today, item)
        except Exception as e:  # noqa: BLE001 — bir İK modülü kurulu değilse ya da okunamazsa öbürleri sürer
            log.info("bugün/İK: %s okunamadı: %s", name, e)
    return out


def _leave_and_docs(engine, tenant, user, flag, today, item) -> list[dict[str, Any]]:
    from semantic_bridge import hr_leave as LV
    from semantic_bridge import hr_portal as PT

    LV.ensure(engine)
    out = []
    me = PT.person_of(engine, tenant, user)
    since = today - timedelta(days=RECENT_DAYS)
    if me is not None and flag("sayfa:ik-izin"):
        with engine.connect() as c:
            mine = c.execute(sa.select(LV.REQUESTS.c.status, LV.REQUESTS.c.decided_at, LV.REQUESTS.c.start).where(
                LV.REQUESTS.c.tenant_id == tenant, LV.REQUESTS.c.person_id == me.id,
                LV.REQUESTS.c.status.in_(("onaylandi", "reddedildi")))).all()
        ok = [r for r in mine if r.status == "onaylandi" and (_day(r.decided_at) or date.min) >= since]
        no = [r for r in mine if r.status == "reddedildi" and (_day(r.decided_at) or date.min) >= since]
        if no:
            out.append(item("ik", "İzin talebim reddedildi", len(no), "/ik/izin", 2))
        if ok:
            out.append(item("ik", "İzin talebim onaylandı", len(ok), "/ik/izin", 3))
        s = LV.summary_for(engine, tenant, me, today)
        if s["hasOpening"] or s["balance"]:
            out.append(item("ik", "Kullanılabilir yıllık iznim (gün)", int(s["available"]), "/ik/izin", 3,
                            f"{s['available']:g} gün".replace(".", ",")))
        # Yönetici: onayımı bekleyen izinler ve ekibimden bugün izinde olanlar (özlük kaydındaki yönetici bağı).
        waiting = LV.team_waiting(engine, tenant, me.id_no)
        if waiting and flag("sayfa:ik-izin-ekip"):
            # kaynak «onay»: kural özetinde «Bekleyenler» cümlesine girer (öbür onay kuyruklarıyla birlikte).
            out.append(item("onay", "Onayımı bekleyen izin talebi", waiting, "/ik/izin/ekip", 2))
        team = {p.id for p in LV._people(engine, tenant) if p.durum == "Aktif" and p.id != me.id
                and load(p.data_json, {}).get("yonetici_id_no") == me.id_no}
        off = [x for x in LV.on_leave_today(engine, tenant, today) if x["id"] in team]
        if off and flag("sayfa:ik-izin-ekip"):
            out.append(item("ik", "Ekibimden bugün izinde", len(off), "/ik/izin/ekip", 3, _names([x["adSoyad"] for x in off])))
    if flag("sayfa:ik-evrak"):
        reqs = [r for r in PT.list_requests(engine, tenant, user=user)
                if r["status"] in ("hazir", "red") and (_day(datetime.fromisoformat(r["handledAt"])) if r["handledAt"] else date.min) >= since]
        ready = [r for r in reqs if r["status"] == "hazir"]
        rejected = [r for r in reqs if r["status"] == "red"]
        if ready:
            out.append(item("ik", "Evrak talebim hazır", len(ready), "/ik/evrak?sekme=talep", 2, ready[0]["docType"]))
        if rejected:
            out.append(item("ik", "Evrak talebim karşılanamadı", len(rejected), "/ik/evrak?sekme=talep", 2,
                            (rejected[0]["answer"] or "")[:120] or None))
    return out


def _engagement(engine, tenant, user, flag, today, item) -> list[dict[str, Any]]:
    from semantic_bridge import hr_engagement as EN

    out = []
    if flag("sayfa:ik-anketlerim"):
        open_ = [s for s in EN.my_surveys(engine, tenant, user) if not s["responded"]]
        if open_:
            out.append(item("ik", "Cevap bekleyen çalışan anketim", len(open_), "/ik/anketlerim", 2, open_[0]["title"]))
    if flag("sayfa:ik-oneriler"):
        since = today - timedelta(days=7)
        ans = [s for s in EN.my_suggestions(engine, tenant, user)
               if s["state"] == "cevaplandi" and s["answeredAt"] and _day(datetime.fromisoformat(s["answeredAt"])) >= since]
        if ans:
            out.append(item("ik", "Önerim cevaplandı", len(ans), "/ik/oneriler", 3))
    return out


def _performance(engine, tenant, user, flag, today, item) -> list[dict[str, Any]]:
    from semantic_bridge import admin as admin_mod
    from semantic_bridge import hr_core as H
    from semantic_bridge import hr_performance as PF

    PF.ensure(engine)
    sc = PF.Scope(engine, tenant, H.Who(user=user, display=user, admin=admin_mod.is_admin(user)))
    out = []
    if sc.me_id and flag("sayfa:ik-performansim"):
        tasks = PF.me_view(engine, tenant, sc)["tasks"]
        self_ = [t for t in tasks if t["kind"] == "oz"]
        if self_:
            soon = any(t["daysLeft"] is not None and t["daysLeft"] <= 3 for t in self_)
            out.append(item("ik", "Öz değerlendirme formum açık", len(self_), "/ik/performansim", 1 if soon else 2))
        shared = [t for t in tasks if t["kind"] == "yorum"]
        if shared:
            out.append(item("ik", "Yöneticimin değerlendirmesi paylaşıldı", len(shared), "/ik/performansim", 2))
        checks = [t for t in tasks if t["kind"] == "checkin"]
        if checks:
            out.append(item("ik", "Hedef check-in zamanım geldi", len(checks), "/ik/performansim", 3))
    if sc.me_id and sc.direct and flag("sayfa:ik-ekibim"):
        team = PF.team_view(engine, tenant, sc, direct_only=True)["people"]
        no_ck = sum(p["noCheckin"] for p in team)
        # Yöneticinin sırası: çalışan öz değerlendirmesini verdi (yonetici) ya da görüşme ve paylaşım bekliyor (gorusme).
        my_revs = sum(1 for p in team for r in p["reviews"] if r["mine"] and r["state"] in ("yonetici", "gorusme"))
        if my_revs:
            out.append(item("onay", "Yazmam gereken ekip değerlendirmesi", my_revs, "/ik/ekibim", 2))
        if no_ck:
            out.append(item("ik", "Ekibimde check-in'i eksik hedef", no_ck, "/ik/ekibim", 3))
    return out


def _interviews(engine, tenant, user, flag, today, item) -> list[dict[str, Any]]:
    """Görüşmecisi olduğum, saati geçmiş ve notunu teslim etmediğim görüşmeler — aday adı yok, yalnız sayı."""
    if not flag("sayfa:ik-ise-alim"):
        return []
    from semantic_bridge import hr_recruit as R

    R.ensure(engine)
    u = (user or "").strip().lower()
    now = datetime.now(timezone.utc)
    with engine.connect() as c:
        ivs = c.execute(sa.select(R.INTERVIEWS.c.id, R.INTERVIEWS.c.starts_at, R.INTERVIEWS.c.interviewers_json).where(
            R.INTERVIEWS.c.tenant_id == tenant, R.INTERVIEWS.c.starts_at <= now)).all()
        mine = [r.id for r in ivs if u in [str(x).lower() for x in (load(r.interviewers_json, []) or [])]]
        done = {r.interview_id for r in c.execute(sa.select(R.NOTES.c.interview_id).where(
            R.NOTES.c.tenant_id == tenant, R.NOTES.c.author == u, R.NOTES.c.submitted_at.isnot(None),
            R.NOTES.c.interview_id.in_(mine or [""]))).all()}
    missing = [i for i in mine if i not in done]
    return [item("ik", "Teslim etmediğim mülakat notu", len(missing), "/ik/ise-alim", 2)] if missing else []


def _team_people(engine, tenant, user, flag, today, item) -> list[dict[str, Any]]:
    """Yönetici: ekibimin bu ayki doğum günü ve iş yıldönümü (gün/ay, yıl sayısı; yaş yok)."""
    from semantic_bridge import hr_portal as PT

    me = PT.person_of(engine, tenant, user)
    if me is None:
        return []
    with engine.connect() as c:
        rows = c.execute(sa.select(PT.PEOPLE.c.id, PT.PEOPLE.c.ad_soyad, PT.PEOPLE.c.data_json).where(
            PT.PEOPLE.c.tenant_id == tenant, PT.PEOPLE.c.durum == "Aktif", PT.PEOPLE.c.id != me.id)).all()
    team = [(r, load(r.data_json, {})) for r in rows]
    team = [(r, d) for r, d in team if d.get("yonetici_id_no") == me.id_no]
    if not team:
        return []
    bday_ok = PT.birthdays_allowed(engine, tenant)
    bdays = [r.ad_soyad for r, d in team if bday_ok and (b := PT.to_date(d.get("dogum_tarihi"))) and b.month == today.month]
    anniv = [f"{r.ad_soyad} ({today.year - s.year}. yıl)" for r, d in team
             if (s := _start(d)) and s.month == today.month and s.year < today.year]
    out = []
    if bdays:
        out.append(item("ik", "Ekibimde bu ay doğum günü", len(bdays), "/ik/dogum-gunleri", 3, _names(bdays)))
    if anniv:
        out.append(item("ik", "Ekibimde bu ay iş yıldönümü", len(anniv), "/ik", 3, _names(anniv)))
    return out


# ------------------------------------------------------------------ Kampüs ortak kartları


def kampus(engine: sa.engine.Engine, tenant: str, today: Optional[date] = None) -> dict[str, Any]:
    """Herkese aynı insan kartları. Yalnız aktif kişiler; yaş/doğum yılı/izin türü/özlük alanı gönderilmez."""
    from semantic_bridge import hr_leave as LV
    from semantic_bridge import hr_portal as PT

    today = today or datetime.now(timezone(timedelta(hours=3))).date()
    LV.ensure(engine)
    photo_ok = PT.directory_photo_allowed(engine, tenant)
    with engine.connect() as c:
        rows = c.execute(sa.select(PT.PEOPLE.c.id, PT.PEOPLE.c.ad_soyad, PT.PEOPLE.c.data_json).where(
            PT.PEOPLE.c.tenant_id == tenant, PT.PEOPLE.c.durum == "Aktif")).all()
        with_photo = {r.person_id for r in c.execute(sa.select(PT.PFILES.c.person_id).where(
            PT.PFILES.c.tenant_id == tenant, PT.PFILES.c.field_key == "fotograf")).all()} if photo_ok else set()
    month0 = today.replace(day=1)
    week_end = today + timedelta(days=6)
    newcomers, anniv = [], []
    for r in rows:
        d = load(r.data_json, {})
        base = {"id": r.id, "adSoyad": r.ad_soyad, "departman": d.get("departman"), "unvan": d.get("unvan"), "hasPhoto": r.id in with_photo}
        s = PT.to_date(d.get("s_ise_giris_tarihi"))
        if s and month0 <= s <= today:
            newcomers.append({**base, "day": s.day, "month": s.month})
        st = _start(d)
        if st and st.year < today.year:
            try:
                ad = st.replace(year=today.year)
            except ValueError:
                ad = date(today.year, 3, 1)
            if today <= ad <= week_end:
                anniv.append({**base, "years": today.year - st.year, "day": ad.day, "month": ad.month, "inDays": (ad - today).days})
    newcomers.sort(key=lambda x: (-x["month"], -x["day"], x["adSoyad"].casefold()))
    anniv.sort(key=lambda x: (x["inDays"], x["adSoyad"].casefold()))
    b = PT.birthdays(engine, tenant, today)
    return {
        "today": today.isoformat(),
        "posts": [dict(p, body=p["body"][:200]) for p in PT.list_posts(engine, tenant, limit=3, today=today)],
        "newcomers": newcomers,
        "birthdays": [dict(x, hasPhoto=x["id"] in with_photo) for x in b["upcoming"]],
        "anniversaries": anniv,
        "onLeave": LV.on_leave_today(engine, tenant, today),
    }
