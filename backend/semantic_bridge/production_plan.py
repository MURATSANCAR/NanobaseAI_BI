"""M12 Üretim Yönetimi — saf hesaplar (veritabanına dokunmaz; test edilir).

Üretim kartının dört dönüm noktası, gerçekleştiği sırayla (CRM aşama sırası: (5) Matbaa belirleme → (7) Hazırda
bekliyor → Matbaada → Depo girişi yapıldı):

- `matbaa` Matbaa belirlendi     gerçekleşen: CRM «matbaa belirleme» tarihi
- `dosya`  Baskı dosyası matbaada plan: CRM «üretim teslim» tarihi (baskı ayından önceki ayın 15'i) · gerçekleşen: CRM
                                  «baskıya hazır» tarihi
- `baski`  Baskı çıkışı          plan: CRM «baskı tarihi»nin ayı (ayın son gününe kadar) · gerçekleşen: Logo'da matbaadan gelen ilk
                                  üretimden giriş fişi (gerçek fiş, PRODSTAT 0)
- `depo`   Depo girişi           plan: Logo'daki planlanan giriş fişi (PRODSTAT 1) · gerçekleşen: gerçek girişlerin toplamı
                                  emrin planlanan adedine ulaştığı gün (ulaşmadıysa ve emir kapandıysa son giriş); Logo'da
                                  eşleşme yoksa CRM «depo giriş» tarihi

Gerçekleşen tarih önceliği: Logo > CRM > portalda elle girilen. Portal kaydı CRM/Logo'daki değeri ezmez, yalnız boşu
doldurur; ekran kaynağı yazar. CRM aşaması tarihsiz ilerlemişse (ör. «Depo girişi yapıldı» ama tarih yok) nokta
gerçekleşmiş sayılır, tarihi boş kalır (gecikme sayılmaz, süre ölçümüne girmez).

**Geriye doğru takvim** (hedef yayın tarihinden): «baskı dosyaları yayın ayından önceki ayın 15'inde matbaada»
(gün ve ay farkı ayardan). Baskı tarihi ve CRM takvimindeki ara tarihler (grafik teslimi, son tarih, dağılım) dosya
teslimine CRM'in kendi kartlarında **ölçülen** uzaklıkla bağlanır; matbaa seçimi ve depo girişi gerçekleşmiş kartlarda
ölçülen sürelerle. Yeterli örnek yoksa (MIN_SAMPLES) o süre plana yazılmaz — sabit gün uydurulmaz.

Gecikme: planı geçmiş, gerçekleşmemiş nokta. Basamaklı bildirim: gecikme `escalate_days` günü aşana kadar sorumluda,
aşınca yöneticide.
"""
from __future__ import annotations

import calendar
import statistics
from datetime import date, datetime, timedelta
from typing import Any, Iterable, Optional

MILESTONES: list[tuple[str, str]] = [
    ("matbaa", "Matbaa belirlendi"),
    ("dosya", "Baskı dosyası matbaada"),
    ("baski", "Baskı çıkışı"),
    ("depo", "Depo girişi"),
]
LABEL = dict(MILESTONES)
KEYS = [k for k, _ in MILESTONES]

#: Gerçekleşen iki nokta arası süre ölçümü (önceki, sonraki).
PAIRS: list[tuple[str, str]] = [("matbaa", "dosya"), ("dosya", "baski"), ("baski", "depo")]

#: CRM takvimindeki plan tarihleri; baskı tarihine göre uzaklıkları kartlarda ölçülür.
TEMPLATE = {"grafik": "Dosyaların grafiğe teslimi", "son": "Son tarih", "dosya": "Baskı dosyası matbaada",
            "dagilim": "Dağılım"}

#: Bir süreyi plana yazmak için en az örnek sayısı (daha azı rastlantıdır).
MIN_SAMPLES = 20

STAGES = {
    "hazirlik": "Hazırlıkta",
    "matbaa-secildi": "Matbaa seçildi",
    "matbaada": "Dosya matbaada",
    "yolda": "Baskıdan çıktı",
    "tamam": "Depoya girdi",
    "eski": "Kapanmamış eski kart",
    "iptal": "İptal",
}


def parse_day(v: Any) -> Optional[date]:
    if v is None or v == "":
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    try:
        return date.fromisoformat(str(v).strip()[:10])
    except ValueError:
        return None


def add_months(d: date, months: int) -> date:
    y, m = divmod(d.month - 1 + months, 12)
    y += d.year
    m += 1
    return date(y, m, min(d.day, calendar.monthrange(y, m)[1]))


def month_end(d: date) -> date:
    return date(d.year, d.month, calendar.monthrange(d.year, d.month)[1])


def files_due(publication: date, files_day: int = 15, months_before: int = 1) -> date:
    """«Baskı dosyaları yayın ayından `months_before` ay önce, ayın `files_day`'inde matbaada.»"""
    first = add_months(date(publication.year, publication.month, 1), -months_before)
    return date(first.year, first.month, min(max(1, files_day), calendar.monthrange(first.year, first.month)[1]))


def _stat(diffs: list[int], negative: int = 0) -> dict[str, Any]:
    if len(diffs) < MIN_SAMPLES:
        return {"days": None, "p25": None, "p75": None, "samples": len(diffs), "negative": negative}
    q = statistics.quantiles(diffs, n=4)
    return {"days": int(round(statistics.median(diffs))), "p25": int(round(q[0])), "p75": int(round(q[2])),
            "samples": len(diffs), "negative": negative}


def measure_leads(cards: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """Gerçekleşmiş iki nokta arasındaki gün farkının ortancası. Negatif fark (sonraki nokta öncekinden önce girilmiş)
    veri giriş sırasıdır, süre sayılmaz; sayısı ayrıca verilir."""
    rows = list(cards)
    out: dict[str, dict[str, Any]] = {}
    for a, b in PAIRS:
        diffs, negative = [], 0
        for c in rows:
            da = parse_day((c["actual"].get(a) or {}).get("day"))
            db = parse_day((c["actual"].get(b) or {}).get("day"))
            if not da or not db:
                continue
            d = (db - da).days
            if d < 0:
                negative += 1
            else:
                diffs.append(d)
        out[f"{a}>{b}"] = {"from": a, "to": b, **_stat(diffs, negative)}
    return out


def measure_template(cards: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    """CRM takviminin kuralı, CRM'in kendi kartlarından: plan tarihlerinin baskı tarihine uzaklığı (gün, ortanca).
    Yalnız yeni kitap kartları (baskı tekrarı kartları önceki karttan kopyalanır, takvimi farklıdır)."""
    diffs: dict[str, list[int]] = {k: [] for k in TEMPLATE}
    for c in cards:
        if not c.get("firstPrint"):
            continue
        base = parse_day(c.get("crmPlan", {}).get("baski"))
        if not base:
            continue
        for k in TEMPLATE:
            d = parse_day(c.get("crmPlan", {}).get(k))
            if d:
                diffs[k].append((d - base).days)
    return {k: {"label": TEMPLATE[k], **_stat(v)} for k, v in diffs.items()}


def backward(publication: date, leads: dict[str, dict[str, Any]], template: dict[str, dict[str, Any]],
             files_day: int = 15, months_before: int = 1) -> dict[str, Any]:
    """Yayın ayından geriye takvim. CRM'de baskı tarihi ay düzeyindedir (kartların %99'unda ayın 1'i): baskı yayın
    ayı içinde, en geç ayın son günü çıkar. Dosya teslimi 15 kuralıyla; matbaa seçimi dosyadan ölçülen süre kadar önce;
    `expected` = ölçülen sürelerle beklenen gerçek tarihler (dosya zamanında teslim edilirse). CRM takviminin ara
    tarihleri (grafik teslimi, son tarih, dağılım) ayın 1'ine ölçülen uzaklıkla. Süresi ölçülemeyen nokta None."""
    first = date(publication.year, publication.month, 1)
    dosya = files_due(publication, files_day, months_before)
    ml = leads.get("matbaa>dosya", {}).get("days")
    bl = leads.get("dosya>baski", {}).get("days")
    dl = leads.get("baski>depo", {}).get("days")
    baski = month_end(publication)
    plan = {"matbaa": dosya - timedelta(days=ml) if ml is not None else None, "dosya": dosya, "baski": baski,
            "depo": baski + timedelta(days=dl) if dl is not None else None}
    exp_baski = dosya + timedelta(days=bl) if bl is not None else None
    expected = {"baski": exp_baski, "depo": exp_baski + timedelta(days=dl) if exp_baski is not None and dl is not None else None}
    extra = []
    for k in ("grafik", "son", "dagilim"):
        off = template.get(k, {}).get("days")
        if off is not None:
            extra.append({"key": k, "label": TEMPLATE[k], "day": (first + timedelta(days=off)).isoformat()})
    risk = []
    if exp_baski is not None and exp_baski > baski:
        risk.append(f"Dosya teslimiyle baskı çıkışı arasında ortanca {bl} gün geçiyor: baskı yayın ayına yetişmiyor.")
    if expected["depo"] is not None and expected["depo"] > publication:
        risk.append("Ölçülen sürelerle kitap depoya yayın tarihinden sonra giriyor.")
    iso = lambda d: d.isoformat() if d else None  # noqa: E731
    return {"publication": publication.isoformat(), "rule": {"day": files_day, "monthsBefore": months_before},
            "plan": {k: iso(v) for k, v in plan.items()}, "expected": {k: iso(v) for k, v in expected.items()},
            "extra": extra, "risk": risk}


def resolve_actual(logo: dict[str, Optional[str]], crm: dict[str, Optional[str]], manual: dict[str, dict[str, Any]],
                   status_done: Iterable[str] = ()) -> dict[str, dict[str, Any]]:
    """Her noktanın gerçekleşen tarihi ve kaynağı. Öncelik: Logo > CRM > portal; CRM aşaması tarihsiz ilerlemişse
    `status_done`'daki noktalar tarihsiz gerçekleşmiş sayılır."""
    out: dict[str, dict[str, Any]] = {}
    for k in KEYS:
        if logo.get(k):
            out[k] = {"day": logo[k], "source": "logo"}
        elif crm.get(k):
            out[k] = {"day": crm[k], "source": "crm"}
        elif manual.get(k):
            m = manual[k]
            out[k] = {"day": m["day"], "source": "portal", "by": m.get("by"), "note": m.get("note")}
    for k in status_done:
        out.setdefault(k, {"day": None, "source": "crm"})
    return out


def delays(plan: dict[str, Optional[str]], actual: dict[str, dict[str, Any]], today: date,
           escalate_days: int = 7) -> list[dict[str, Any]]:
    """Planı geçmiş, gerçekleşmemiş noktalar. Sonraki bir nokta gerçekleşmişse öncekiler gecikme sayılmaz
    (iş ilerlemiş; tarihi girilmemiş olabilir)."""
    last_done = max((i for i, k in enumerate(KEYS) if k in actual), default=-1)
    out = []
    for i, k in enumerate(KEYS):
        if i <= last_done:
            continue
        due = parse_day(plan.get(k))
        if not due or due >= today:
            continue
        late = (today - due).days
        out.append({"milestone": k, "label": LABEL[k], "due": due.isoformat(), "days": late,
                    "level": "yonetici" if late > escalate_days else "sorumlu"})
    return out


def stage(actual: dict[str, dict[str, Any]]) -> str:
    """Kartın aşaması: gerçekleşen en ileri nokta."""
    if "depo" in actual:
        return "tamam"
    if "baski" in actual:
        return "yolda"
    if "dosya" in actual:
        return "matbaada"
    if "matbaa" in actual:
        return "matbaa-secildi"
    return "hazirlik"


def unit_price(price: Optional[float], qty: Optional[float]) -> Optional[float]:
    if not price or not qty or qty <= 0:
        return None
    return round(float(price) / float(qty), 4)


def printer_stats(cards: Iterable[dict[str, Any]], today: date) -> list[dict[str, Any]]:
    """Matbaa başına: iş sayısı, süren iş (kapasite yükü), zamanında teslim oranı (baskı çıkışı — yoksa depo girişi —
    planlanan baskı ayının sonundan geç değil), ortanca süre (dosya matbaada → depo girişi), birim fiyat ortancası ve son 12
    ayın bir önceki 12 aya göre eğilimi, kalite (portalda işaretlenen). İptal kartlar sayılmaz."""
    by: dict[str, dict[str, Any]] = {}
    for c in cards:
        m = c.get("printer")
        if not m or c.get("stage") in ("iptal", "eski"):
            continue
        s = by.setdefault(m, {"printer": m, "jobs": 0, "open": 0, "done": 0, "onTime": 0, "measured": 0, "leads": [],
                              "unit": [], "unitRecent": [], "unitOld": [], "quality": 0, "qualityIssues": 0,
                              "copies": 0, "last": None})
        s["jobs"] += 1
        act = c["actual"]
        if "depo" in act:
            s["done"] += 1
        else:
            s["open"] += 1
        s["copies"] += int(c.get("qty") or 0)
        promised = parse_day((c.get("plan") or {}).get("baski"))
        got = parse_day((act.get("baski") or {}).get("day")) or parse_day((act.get("depo") or {}).get("day"))
        if promised and got:
            s["measured"] += 1
            if got <= promised:
                s["onTime"] += 1
        f = parse_day((act.get("dosya") or {}).get("day"))
        d = parse_day((act.get("depo") or {}).get("day"))
        if f and d and d >= f:
            s["leads"].append((d - f).days)
        u = c.get("unitPrice") if c.get("unitPrice") is not None else unit_price(c.get("price"), c.get("qty"))
        created = parse_day(c.get("created"))
        if u is not None:
            s["unit"].append(u)
            if created and created >= today - timedelta(days=365):
                s["unitRecent"].append(u)
            elif created and created >= today - timedelta(days=730):
                s["unitOld"].append(u)
        q = c.get("quality")
        if q in ("sorunsuz", "sorun"):
            s["quality"] += 1
            s["qualityIssues"] += 1 if q == "sorun" else 0
        if created and (s["last"] is None or created.isoformat() > s["last"]):
            s["last"] = created.isoformat()

    def med(xs: list[float]) -> Optional[float]:
        return round(statistics.median(xs), 4) if xs else None

    out = []
    for s in by.values():
        recent, old = med(s["unitRecent"]), med(s["unitOld"])
        out.append({
            "printer": s["printer"], "jobs": s["jobs"], "open": s["open"], "done": s["done"], "copies": s["copies"],
            "onTimeRate": round(s["onTime"] / s["measured"], 4) if s["measured"] else None, "measured": s["measured"],
            "leadDays": int(round(statistics.median(s["leads"]))) if s["leads"] else None, "leadSamples": len(s["leads"]),
            "unitPrice": med(s["unit"]), "unitSamples": len(s["unit"]), "unitRecent": recent, "unitPrevious": old,
            "unitTrend": round((recent - old) / old, 4) if recent is not None and old else None,
            "qualityRate": round(1 - s["qualityIssues"] / s["quality"], 4) if s["quality"] else None,
            "qualityMarked": s["quality"], "last": s["last"],
        })
    out.sort(key=lambda x: (-x["jobs"], x["printer"]))
    return out


#: Az işi olan matbaanın oranı genel orana bu kadar iş ağırlığıyla çekilir (2 işte %100, 900 işte %21'den iyi görünmesin).
PRIOR_JOBS = 10


def overall_on_time(stats: Iterable[dict[str, Any]]) -> Optional[float]:
    rows = [s for s in stats if s.get("measured")]
    n = sum(s["measured"] for s in rows)
    return round(sum(s["onTimeRate"] * s["measured"] for s in rows) / n, 4) if n else None


def score(p: dict[str, Any], price_ref: Optional[float], prior: Optional[float] = None) -> dict[str, Any]:
    """Matbaa puanı (0–100): zamanında teslim 50, fiyat 30 (birim fiyatın genel ortancaya oranı), kalite 20. Zamanında
    teslim oranı, `prior` (bütün matbaaların oranı) verilirse `PRIOR_JOBS` iş ağırlığıyla ona doğru çekilir. Ölçülemeyen
    parça yarım puan alır ve «ölçülemedi» diye yazılır; puan uydurulmaz, gerekçesi döner."""
    parts, notes = {}, []
    if p.get("onTimeRate") is not None:
        rate, n = p["onTimeRate"], p.get("measured") or 0
        if prior is not None:
            rate = (rate * n + prior * PRIOR_JOBS) / (n + PRIOR_JOBS)
        parts["onTime"] = round(50 * rate, 1)
    else:
        parts["onTime"] = 25.0
        notes.append("zamanında teslim ölçülemedi")
    if p.get("unitPrice") and price_ref:
        # Ortancadan ucuz ya da eşit: tam puan; pahalıysa oranla düşer, iki katında sıfır.
        ratio = p["unitPrice"] / price_ref
        parts["price"] = round(30.0 if ratio <= 1 else max(0.0, 30 * (2 - ratio)), 1)
    else:
        parts["price"] = 15.0
        notes.append("birim fiyat ölçülemedi")
    if p.get("qualityRate") is not None:
        parts["quality"] = round(20 * p["qualityRate"], 1)
    else:
        parts["quality"] = 10.0
        notes.append("kalite kaydı yok")
    return {"score": round(sum(parts.values())), "parts": parts, "notes": notes}
