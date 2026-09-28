"""M4 Çeviri — çevirmen eşleştirme önerisi. Yalnız okur; hiçbir tabloya yazmaz, model çağırmaz.

Bir çeviri işi açılırken ya da atanırken aday çevirmenler sıralanır. Adaylar iki kaynaktan gelir:

- **Portal kullanıcıları:** M4 işlerimizde daha önce çevirmen olarak atanmış herkes (`semantic_translation_jobs`).
- **Serbest çalışanlar (M8):** «Çeviri» rolü olan aktif kişi kartları (`semantic_freelance_people`). Portala giremez;
  işi yöneten XLIFF dosyasıyla çeviriyi verir ve geri alır.

Kartın e-postası rehberde bir portal kullanıcısının e-postasıyla (ya da işe kullanıcı adı yerine yazılmış e-postayla)
aynıysa iki kayıt tek aday olur; bağ yoksa ayrı kalır ve kaynağı etikette yazar.

Her sinyal ayrı gösterilir, tek bir gizli puan yoktur:

1. **Müsaitlik:** serbest çalışanın kartındaki «müsait olmadığı günler» teslim gününü kapsıyor mu.
2. **Dil çifti deneyimi:** aynı kaynak → hedef çiftindeki işlerde çevrilen kelime. Serbest çalışanın kartındaki
   etiketlerde kaynak dilin adı geçiyorsa bu daha zayıf bir deneyim işaretidir.
3. **Yük:** portal kullanıcısının açık işlerinde çevrilmemiş (boş + taslak) kelime; son 30 günün hızıyla bu
   yük + yeni iş teslime yetişir mi. Serbest çalışanda bugün–teslim arasındaki iş günlerinde kapasiteden kalan
   boş saat (M8 kapasite hesabının aynısı); yeni işin saati «1 sayfa = 250 kelime» varsayımıyla M8 çeviri rolünün
   sayfa başı saatinden çıkar.
4. **İnceleme puanı (MQM):** onaylanan kelimeye göre hata ağırlıkları; yalnız incelenmiş kelime varsa. Önce bu
   dil çiftindeki işler, yoksa bütün işler (hangisi olduğu yazılır).
5. **Zamanında teslim:** portal işinde son segmentin onay günü ≤ teslim tarihi; serbest çalışanda ilk teslim
   günü ≤ görev termini. İki kaynak birleşince sayılar toplanır.

Sıralama sözlük sırasıdır (ağırlıklı toplam değil), `ORDER` ekranda da aynen yazılır. Bilinmeyen sinyal (ör. portal
kullanıcısının izin günü kayıtlı değil) adayı cezalandırmaz; yalnız bilinen olumsuzluk aşağı iter. Aday sayısında
tavan yok: bütün adaylar sıralı döner.
"""
from __future__ import annotations

import json
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_bridge import editorial_translation as T
from semantic_bridge import freelance as F

#: Serbest çalışan yükünü saate çevirirken kullanılan sayfa varsayımı (ekranda da yazılır).
WORDS_PER_PAGE = 250
#: Portal çevirmeninin hızı bu kadar günün «çevrildi» olaylarından ölçülür.
PACE_DAYS = 30
#: Teslim tarihi verilmemişse serbest çalışanın boş saati bu kadar günlük pencerede ölçülür (M8 önerisiyle aynı).
DEFAULT_WINDOW_DAYS = 14

ORDER = ("Sıralama: önce teslim gününde müsait olanlar; sonra bu dil çiftinde çeviri yapmış olanlar (kartında "
         "kaynak dil etiketi olan serbest çalışan ikinci sırada); sonra elindeki iş teslime sığanlar; sonra inceleme "
         "puanı yüksek olan (tam puana yuvarlanır, puanı olmayan sona); sonra zamanında teslim oranı yüksek olan; "
         "sonra açık yükü az olan. Bilinmeyen sinyal adayı aşağı itmez.")
ORDER_KEYS = ("musait", "dil-cifti", "yuk-sigar", "inceleme-puani", "zamaninda-teslim", "acik-yuk")


def _today() -> date:
    # İş günü İstanbul'a göre (UTC+3, yaz saati yok) — M8 ile aynı.
    return (datetime.now(timezone.utc) + timedelta(hours=3)).date()


def _utc(v: datetime) -> datetime:
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def _loads(v: Optional[str]) -> list[Any]:
    try:
        out = json.loads(v or "[]")
    except ValueError:
        return []
    return out if isinstance(out, list) else []


def _blank(key: str) -> dict[str, Any]:
    return {
        "key": key, "source": "portal", "username": None, "name": None, "personId": None, "portalLogin": True,
        "pairWords": 0, "pairJobs": 0, "otherPairs": set(), "tag": None,
        "reviewed": {"pair": 0, "all": 0}, "penalty": {"pair": 0, "all": 0},
        "onTime": 0, "late": 0,
        "openWords": 0, "openJobs": 0, "noSourceJobs": 0, "paceWords": 0, "paceWindow": None,
        "hours": None, "away": None,
    }


# ============================================================================================ portal çevirmenleri

def _portal(conn: sa.Connection, tenant: str, src: str, tgt: str, exclude_job: Optional[str], today: date) -> dict[str, dict[str, Any]]:
    jobs = conn.execute(sa.select(T.JOBS).where(T.JOBS.c.tenant_id == tenant, T.JOBS.c.translator.isnot(None))).all()
    jobs = [j for j in jobs if j.translator]
    if not jobs:
        return {}
    ids = [j.id for j in jobs]
    counts = T._counts(conn, ids)
    pen: dict[str, int] = defaultdict(int)
    for jid, sev in conn.execute(sa.select(T.ERRORS.c.job_id, T.ERRORS.c.severity).where(T.ERRORS.c.job_id.in_(ids))).all():
        pen[jid] += T.SEVERITIES.get(sev, ("", 0))[1]
    out: dict[str, dict[str, Any]] = {}
    for j in jobs:
        u = j.translator
        d = out.setdefault(u, _blank(u))
        d["username"] = u
        d["name"] = d["name"] or j.translator_name
        c = counts[j.id]
        words = c["words"]
        done = words.get("cevrildi", 0) + words.get("onaylandi", 0)
        same = j.source_lang == src and j.target_lang == tgt
        if done:
            if same:
                d["pairWords"] += done
                d["pairJobs"] += 1
            else:
                d["otherPairs"].add(f"{j.source_lang}→{j.target_lang}")
        approved = words.get("onaylandi", 0)
        d["reviewed"]["all"] += approved
        d["penalty"]["all"] += pen.get(j.id, 0)
        if same:
            d["reviewed"]["pair"] += approved
            d["penalty"]["pair"] += pen.get(j.id, 0)
        stage = T._stage(c)
        if stage == "tamamlandi":
            if j.due_date and j.completed_at:
                d["onTime" if _utc(j.completed_at).date() <= j.due_date else "late"] += 1
        elif j.id != exclude_job:
            # Açık yük: çevirmenin önündeki boş + taslak kelime. İncelemedeki iş çevirmenin elinden çıkmıştır.
            if stage == "kaynak":
                d["noSourceJobs"] += 1
            else:
                left = words.get("bos", 0) + words.get("taslak", 0)
                if left:
                    d["openWords"] += left
                    d["openJobs"] += 1
    # Hız: son 30 günde bu kişinin «çevrildi» olayları (kişi yeni başladıysa ilk olayından bugüne).
    since = datetime.combine(today - timedelta(days=PACE_DAYS - 1), datetime.min.time(), tzinfo=timezone.utc)
    rows = conn.execute(
        sa.select(T.EVENTS.c.username, sa.func.sum(T.EVENTS.c.words), sa.func.min(T.EVENTS.c.at))
        .select_from(T.EVENTS.join(T.JOBS, T.JOBS.c.id == T.EVENTS.c.job_id))
        .where(T.JOBS.c.tenant_id == tenant, T.EVENTS.c.action == "cevrildi", T.EVENTS.c.at >= since,
               T.EVENTS.c.username.in_(list(out)))
        .group_by(T.EVENTS.c.username)).all()
    for u, w, first in rows:
        if u in out and w:
            out[u]["paceWords"] = int(w)
            out[u]["paceWindow"] = max(1, min(PACE_DAYS, (today - _utc(first).date()).days + 1)) if first else PACE_DAYS
    return out


# ============================================================================================ serbest çalışanlar (M8)

def _freelancers(conn: sa.Connection, tenant: str, src: str, due: Optional[date], today: date) -> dict[str, dict[str, Any]]:
    if "ceviri" not in F.ROLES:
        return {}
    people = [p for p in conn.execute(sa.select(F.PEOPLE).where(F.PEOPLE.c.tenant_id == tenant, F.PEOPLE.c.status == "aktif")).all()
              if "ceviri" in _loads(p.roles_json)]
    if not people:
        return {}
    ids = [p.id for p in people]
    tasks = conn.execute(sa.select(F.TASKS).where(F.TASKS.c.tenant_id == tenant, F.TASKS.c.person_id.in_(ids),
                                                  F.TASKS.c.status != "iptal")).all()
    by_person: dict[str, list[Any]] = defaultdict(list)
    for t in tasks:
        by_person[t.person_id].append(t)
    lang = T.fold(T.LANGS.get(src, src))
    start = today
    end = due if due and due >= today else today + timedelta(days=DEFAULT_WINDOW_DAYS - 1)
    out: dict[str, dict[str, Any]] = {}
    for p in people:
        d = _blank(f"m8:{p.id}")
        d.update(source="serbest", name=p.name, personId=p.id, portalLogin=False)
        d["email"] = (p.email or "").lower() or None
        tags = [str(s) for s in _loads(p.styles_json)]
        hit = next((s for s in tags if lang and lang in T.fold(s)), None)
        d["tag"] = hit
        mine = by_person.get(p.id, [])
        for t in mine:
            if t.first_delivered_at is not None and t.due is not None:
                d["onTime" if (_utc(t.first_delivered_at) + timedelta(hours=3)).date() <= t.due else "late"] += 1
        away = F._away_ranges(p)
        days = F._workdays(start, end, away)
        daily = F.load_by_day(mine, away, today)
        cap = p.weekly_hours / F.WORKDAYS * len(days)
        busy = sum(daily.get(x, 0.0) for x in days)
        d["hours"] = {"from": start.isoformat(), "to": end.isoformat(), "workdays": len(days), "capacity": round(cap, 1),
                      "busy": round(busy, 1), "free": round(cap - busy, 1), "weeklyHours": p.weekly_hours,
                      "activeTasks": sum(1 for t in mine if t.status in F.ACTIVE)}
        overlap = [(a, b) for a, b in away if a <= end and b >= start]
        d["away"] = {"onDue": (any(a <= due <= b for a, b in away) if due else None),
                     "ranges": [{"from": a.isoformat(), "to": b.isoformat()} for a, b in overlap]}
        out[d["key"]] = d
    return out


# ============================================================================================ birleştirme ve sinyaller

def _merge(portal: dict[str, dict[str, Any]], free: dict[str, dict[str, Any]],
           directory: Optional[Callable[[], dict[str, str]]]) -> list[dict[str, Any]]:
    """Serbest çalışan kartı bir portal kullanıcısına bağlıysa (aynı e-posta) tek aday yapar."""
    by_email: dict[str, str] = {}
    for u in portal:
        if "@" in u:                                   # işe kullanıcı adı yerine e-posta yazılmış olabilir
            by_email[u] = u
    if portal and any(d.get("email") for d in free.values()) and directory is not None:
        try:
            for u, mail in (directory() or {}).items():
                u, mail = str(u or "").lower(), str(mail or "").lower()
                if u in portal and "@" in mail:
                    by_email.setdefault(mail, u)
        except Exception:  # noqa: BLE001 — rehber okunamazsa kayıtlar ayrı kalır, öneri yine döner
            pass
    items = list(portal.values())
    for f in free.values():
        u = by_email.get(f.get("email") or "")
        if not u:
            items.append(f)
            continue
        d = portal[u]
        d.update(source="ikisi", personId=f["personId"], tag=f["tag"], hours=f["hours"], away=f["away"])
        d["name"] = d["name"] or f["name"]
        d["onTime"] += f["onTime"]
        d["late"] += f["late"]
    return items


def _fits(d: dict[str, Any], words: int, due: Optional[date], today: date) -> tuple[Optional[bool], dict[str, Any]]:
    """Elindeki iş + yeni iş teslime sığar mı. Portal: hız × kalan gün; serbest: boş saat ≥ gereken saat."""
    load: dict[str, Any] = {"openWords": d["openWords"], "openJobs": d["openJobs"], "noSourceJobs": d["noSourceJobs"],
                            "perDay": None, "daysNeeded": None, "daysLeft": None, "hours": d["hours"]}
    verdicts: list[bool] = []
    days_left = (due - today).days + 1 if due else None
    load["daysLeft"] = days_left
    if d["source"] != "serbest" and d["paceWords"] and d["paceWindow"]:
        per_day = d["paceWords"] / d["paceWindow"]
        load["perDay"] = round(per_day, 1)
        need = d["openWords"] + max(words, 0)
        if need:
            load["daysNeeded"] = int(-(-need // per_day))
            if days_left is not None:
                verdicts.append(load["daysNeeded"] <= max(days_left, 0))
    if d["hours"] is not None:
        needed = round(max(words, 0) / WORDS_PER_PAGE * F.ROLES["ceviri"][2], 1)
        d["hours"]["needed"] = needed
        verdicts.append(d["hours"]["free"] >= needed and d["hours"]["workdays"] > 0)
    return (all(verdicts) if verdicts else None), load


def _signals(d: dict[str, Any], words: int, due: Optional[date], today: date) -> dict[str, Any]:
    pair_tier = 2 if d["pairWords"] else (1 if d["tag"] else 0)
    scope = "cift" if d["reviewed"]["pair"] else ("genel" if d["reviewed"]["all"] else None)
    key = {"cift": "pair", "genel": "all"}.get(scope or "")   # ekrana giden etiket ≠ sözlük anahtarı
    reviewed = d["reviewed"][key] if key else 0
    penalty = d["penalty"][key] if key else 0
    mqm = round((1 - penalty / reviewed) * 100, 2) if reviewed else None
    delivered = d["onTime"] + d["late"]
    fits, load = _fits(d, words, due, today)
    return {
        "pair": {"words": d["pairWords"], "jobs": d["pairJobs"], "tier": pair_tier, "tag": d["tag"],
                 "otherPairs": sorted(d["otherPairs"])},
        "quality": {"mqm": mqm, "reviewedWords": reviewed, "penalty": penalty, "scope": scope},
        "onTime": {"onTime": d["onTime"], "total": delivered, "rate": round(d["onTime"] / delivered, 3) if delivered else None},
        "load": {**load, "fits": fits},
        "availability": {"awayOnDue": (d["away"] or {}).get("onDue"), "ranges": (d["away"] or {}).get("ranges", [])},
    }


def _key(c: dict[str, Any]) -> tuple:
    s = c["signals"]
    mqm, rate = s["quality"]["mqm"], s["onTime"]["rate"]
    hours = s["load"]["hours"]
    return (
        1 if s["availability"]["awayOnDue"] is True else 0,
        -s["pair"]["tier"],
        1 if s["load"]["fits"] is False else 0,
        (0, -round(mqm)) if mqm is not None else (1, 0),
        (0, -rate) if rate is not None else (1, 0),
        s["load"]["openWords"],
        -(hours["free"] if hours else 0.0),
        -s["pair"]["words"],
        (c["name"] or c["username"] or "").lower(),
    )


def _fmt(n: float) -> str:
    return f"{n:,.0f}".replace(",", ".")


def _notes(c: dict[str, Any], src: str, tgt: str) -> list[dict[str, str]]:
    """Her sinyal için tek satır Türkçe açıklama; ton: iyi | uyari | notr."""
    s = c["signals"]
    pair = f"{T.LANGS.get(src, src)} → {T.LANGS.get(tgt, tgt)}"
    out: list[dict[str, str]] = []
    av = s["availability"]
    if av["awayOnDue"] is True:
        out.append({"key": "musait", "tone": "uyari", "text": "Teslim gününde müsait değil (kartındaki izin günleri)."})
    elif av["ranges"]:
        r = av["ranges"][0]
        more = f" ve {len(av['ranges']) - 1} aralık daha" if len(av["ranges"]) > 1 else ""
        out.append({"key": "musait", "tone": "notr", "text": f"Arada müsait olmadığı günler var: {r['from']} – {r['to']}{more}."})
    p = s["pair"]
    if p["words"]:
        out.append({"key": "dil-cifti", "tone": "iyi", "text": f"{pair}: {_fmt(p['words'])} kelime, {p['jobs']} iş."})
    elif p["tag"]:
        out.append({"key": "dil-cifti", "tone": "notr", "text": f"Bu çiftte işimiz yok; kartında «{p['tag']}» etiketi var."})
    else:
        other = ", ".join(" → ".join(T.LANGS.get(x, x) for x in op.split("→")) for op in p["otherPairs"])
        out.append({"key": "dil-cifti", "tone": "notr",
                    "text": f"Bu çiftte işimiz yok{'; başka çiftler: ' + other if other else ''}."})
    ld = s["load"]
    if ld["hours"] is not None:
        h = ld["hours"]
        out.append({"key": "yuk-sigar", "tone": "uyari" if ld["fits"] is False else "iyi",
                    "text": f"{h['from']} – {h['to']} arası {h['workdays']} iş günü: {h['free']:g} saat boş "
                            f"({h['busy']:g} / {h['capacity']:g} saat dolu), bu iş yaklaşık {h['needed']:g} saat."})
    if c["source"] != "serbest":
        parts = []
        parts.append(f"Açık işlerinde {_fmt(ld['openWords'])} kelime çevrilmemiş" if ld["openWords"] else "Açık işinde çevrilmemiş kelime yok")
        if ld["noSourceJobs"]:
            parts.append(f"{ld['noSourceJobs']} işin kaynağı henüz yüklenmemiş")
        if ld["perDay"]:
            parts.append(f"son günlerde günde {_fmt(ld['perDay'])} kelime")
            if ld["daysNeeded"] is not None:
                parts.append(f"bu hızla yeni işle birlikte {ld['daysNeeded']} günde biter")
        else:
            parts.append("son 30 günde çeviri hızı ölçülemedi")
        tone = "uyari" if ld["fits"] is False else ("iyi" if ld["fits"] else "notr")
        out.append({"key": "acik-yuk", "tone": tone, "text": "; ".join(parts) + "."})
    q = s["quality"]
    if q["mqm"] is not None:
        where = "bu dil çiftinde" if q["scope"] == "cift" else "bütün işlerde"
        score = f"{q['mqm']:.1f}".replace(".", ",")
        out.append({"key": "inceleme-puani", "tone": "notr",
                    "text": f"İnceleme puanı {score} ({where}, {_fmt(q['reviewedWords'])} kelime incelendi)."})
    else:
        out.append({"key": "inceleme-puani", "tone": "notr", "text": "İncelenmiş çevirisi yok."})
    o = s["onTime"]
    if o["total"]:
        out.append({"key": "zamaninda-teslim", "tone": "iyi" if o["onTime"] == o["total"] else "notr",
                    "text": f"Zamanında teslim: {o['onTime']} / {o['total']}."})
    return out


def match(engine: sa.engine.Engine, tenant: str, src: Any, tgt: Any, words: Any = 0, due: Any = None, *,
          exclude_job: Optional[str] = None, directory: Optional[Callable[[], dict[str, str]]] = None,
          today: Optional[date] = None) -> dict[str, Any]:
    """Sıralı aday listesi. `exclude_job` atanmakta olan işin kendisi (açık yükten düşülür). `directory` gerekirse
    çağrılan kullanıcı adı → e-posta eşlemesidir (rehber); yalnız e-postalı serbest çalışan varsa okunur."""
    s, t = T._lang(src, "Kaynak"), T._lang(tgt, "Hedef")
    if s == t:
        raise T.TranslationError("Kaynak ve hedef dil aynı olamaz.")
    try:
        n = max(0, int(float(str(words or 0))))
    except ValueError as e:
        raise T.TranslationError("Kelime sayısı sayı olmalı.") from e
    d_due = T._date(due)
    today = today or _today()
    F.ensure(engine)
    with engine.connect() as conn:
        portal = _portal(conn, tenant, s, t, exclude_job, today)
        free = _freelancers(conn, tenant, s, d_due, today)
    items = _merge(portal, free, directory)
    out = []
    for d in items:
        c = {"key": d["key"], "source": d["source"], "username": d["username"], "name": d["name"] or d["username"],
             "personId": d["personId"], "portalLogin": d["source"] != "serbest"}
        c["signals"] = _signals(d, n, d_due, today)
        out.append(c)
    out.sort(key=_key)
    for i, c in enumerate(out, 1):
        c["rank"] = i
        c["notes"] = _notes(c, s, t)
    return {"items": out, "total": len(out), "order": ORDER, "orderKeys": list(ORDER_KEYS),
            "assumptions": {"wordsPerPage": WORDS_PER_PAGE, "hoursPerPage": F.ROLES["ceviri"][2] if "ceviri" in F.ROLES else None,
                            "paceDays": PACE_DAYS, "windowDays": DEFAULT_WINDOW_DAYS},
            "sourceLang": s, "targetLang": t, "words": n, "dueDate": d_due.isoformat() if d_due else None,
            "today": today.isoformat()}
