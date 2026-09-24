"""Eş süreli dönem: karşılaştırmanın iki tarafı aynı göreli noktada biter.

"Bu yıl geçen yıla göre" sorusu takvim yılıyla okunuyordu: bu yıl 1 Ocak–31 Aralık, geçen yıl
1 Ocak–31 Aralık. Veri ise bu yılın içinde bir günde bitiyor (kayıtların son günü; canlı bir
kaynakta dün, bir kopyada kopyanın alındığı gün). Sekiz buçuk ay on iki ayla kıyaslanınca artan ciro
"düştü" diye çıkıyordu ve cevabın altındaki "eşit kapsam doğrulanmadı" notu yanlış sayıyı
düzeltmiyordu.

Ürün sahibinin kuralı (2026-09-21): karşılaştırmada mevcut dönemin bulunan günü/ayı, önceki dönemin
AYNI gününe/ayına göre alınır. Burada iki iş var:

1. Verinin nerede bittiğini ÖLÇÜNÜN KENDİ TABLOSUNDAN okumak (`probe_sql`): ölçünün varlığı,
   ölçünün katalogdaki kendi koşulları (iptal edilmemiş, satış türleri...) ve güncel dönemle sınırlı
   `MAX(tarih)`. Sorunun daraltıcı filtreleri (bir ürün, bir müşteri) BİLEREK konmaz: o ürünün son
   satışı Haziran'daysa bu verinin Haziran'da bittiği anlamına gelmez. Tarih bugünle de kırpılır —
   ileri tarihli satırlar (2030 vadesi, yanlış girilmiş 2027) "veri bugüne kadar var" dedirtmesin.
   Profilin ölçtüğü min/max (`time_window`) bu iş için kullanılmaz: ileri tarihli satır yüzünden
   2026 satır tablosu 2027-03-23'e "uzanıyor" görünür ve gece taraması veri değişince yenilenmez.
2. Önceki dönemin bitişini aynı göreli noktaya taşımak (`aligned_end`): yıl/çeyrek/ay gibi ay başında
   başlayan dönemlerde ay kaydırılarak (31 Mart → 28/29 Şubat; ayın son günü → ayın son günü, 29 Şubat
   dahil), hafta/gün dönemlerinde gün farkıyla.

Kırpma yapılamıyorsa (ölçünün varlığı/tarih kolonu bilinmiyor, sorgu çalışmadı, dönemler hizalanamıyor)
bugünkü davranış ve "eşit kapsam doğrulanmadı" notu olduğu gibi kalır: sessizce başka bir sayı verilmez.
"""

from __future__ import annotations

import calendar
from dataclasses import replace
from datetime import date, datetime, timedelta
from typing import Any, Optional

#: resolver'ın takvim dönemi uyarısı — hizalama yapılınca yerini eş dönem notuna bırakır
_CALENDAR_NOTE = "Karşılaştırmada takvim dönemleri kullanıldı"


def _d(value: Any) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _tr(d: date) -> str:
    return d.strftime("%d.%m.%Y")


def _month_last(y: int, m: int) -> int:
    return calendar.monthrange(y, m)[1]


def _shift_months(d: date, months: int) -> date:
    """`d`'yi `months` ay geri/ileri taşır. Ayın son günü ayın son gününe gider (31 Ocak → 28/29
    Şubat, 29 Şubat 2028 → 28 Şubat 2027, 28 Şubat 2025 → 29 Şubat 2024); ayın ortasındaki bir gün,
    hedef ay kısaysa o ayın son gününe kırpılır (30 Mart → 28 Şubat)."""
    y, m = divmod(d.month - 1 + months, 12)
    y, m = d.year + y, m + 1
    last = _month_last(y, m)
    if d.day == _month_last(d.year, d.month):
        return date(y, m, last)
    return date(y, m, min(d.day, last))


def aligned_end(cur_start: date, ref_start: date, ref_end: date, last_day: date) -> Optional[date]:
    """Önceki dönemin yeni (hariç) bitişi: güncel dönem `last_day`'de bittiyse, önceki dönem kendi
    içinde aynı göreli günde biter. Hizalanamıyorsa None."""
    if cur_start.day == 1 and ref_start.day == 1:
        # yıl, çeyrek, ay, ay aralığı: takvimde aynı gün/ay ("geçen yılın aynı dönemi")
        shift = (cur_start.year - ref_start.year) * 12 + (cur_start.month - ref_start.month)
        mirror = _shift_months(last_day, -shift)
    else:
        # hafta, son N gün: aynı sayıda gün (hafta içi günü de korunur)
        mirror = last_day - (cur_start - ref_start)
    end = mirror + timedelta(days=1)
    if end <= ref_start:
        return None
    return min(end, ref_end)


def _conditions(sq, entity: str, dialect) -> Optional[list[str]]:
    """Ölçülerin katalogdaki kendi koşulları, `entity` üzerinden; ölçü başına bir tane ("" = koşulsuz).
    Okunamayan bir koşul varsa None: yanlış kapsamla ölçmektense ölçmemek."""
    from semantic_layer.runtime.compiler import _pred_key_sql
    groups: list[str] = []
    for s in sq.metrics:
        m = s.mapping
        if not m or (m.entity or "").upper() != entity.upper():
            continue
        keys = (m.extra or {}).get("conditions") or []
        parts = [_pred_key_sql(m.entity, k, dialect) for k in keys]
        if any(p is None for p in parts):
            return None
        groups.append(" AND ".join(parts))
    return list(dict.fromkeys(groups)) or [""]


def _last_day_sql(entity: str, col: str, cond: list[str], lo: date, hi: date, dialect) -> str:
    """Her ölçünün [lo, hi) içindeki son günü, ölçü başına bir kolon (last_0, last_1…).

    Ölçü başına "en yeni tarihli bir satır" alt sorgusu: tarih indeksinden sondan okunur ve ilk uyan
    satırda durur. `MAX(CASE WHEN koşul THEN tarih END)` bütün satırları tarıyordu — 2021–2025'i tutan
    satır tablosunda 2025 için 6–47 sn; bu biçim 0,4 sn (gerçek DB, 2026-09-25)."""
    rng = f"{col} >= '{lo.isoformat()}' AND {col} < '{hi.isoformat()}'"
    subs = []
    for i, c in enumerate(cond):
        where = f"{rng} AND {c}" if c else rng
        inner = dialect.limit(f"SELECT {col} FROM {entity} WHERE {where} ORDER BY {col} DESC", 1)
        subs.append(f"({inner}) AS last_{i}")
    return f"SELECT {', '.join(subs)}"


def _open_current(sq, today: date) -> Optional[tuple[str, dict]]:
    """("comparison"|"single", güncel dönem).

    Karşılaştırmada güncel dönem başlamışsa yeter; kapanmış olması "tamdır" demek değil. Veri bir kopyada
    ayın ortasında biter: "geçen ay bir önceki aya göre" Ağustos'un 17 gününü Temmuz'un 31 günüyle
    kıyaslıyor, not "eşit kapsam doğrulanmadı" deyip rakamı öyle bırakıyordu. Dönem veriyle doluysa
    (2025'e karşı 2024) ölçülen son gün dönemin sonudur ve `apply` hiçbir şeyi değiştirmez.
    Tek dönemde yalnız açık dönem: kapanmış tek dönemin kapsam notu ayrı bir karar."""
    comp = sq.comparison or {}
    if comp.get("current") and comp.get("reference"):
        cur = comp["current"]
        kind = "comparison"
    elif len(sq.temporal or []) == 1 and not comp:
        cur = sq.temporal[0].to_dict()
        kind = "single"
    else:
        return None
    start, end = _d(cur.get("start")), _d(cur.get("end"))
    if not (start and end) or start > today:
        return None
    if kind == "single" and not today < end:
        return None
    return kind, cur


def probe_plan(sq, today: date, dialect) -> Optional[dict[str, Any]]:
    """Verinin nerede bittiğini ölçecek sorgu, ve neyin ölçüldüğü. Gerek yoksa ya da ölçülemezse None."""
    found = _open_current(sq, today)
    if not found:
        return None
    kind, cur = found
    comp = sq.comparison or {}
    binding = sq.temporal_binding or {}
    entity = comp.get("entity") or binding.get("entity")
    column = comp.get("dateColumn") or binding.get("column")
    if not (entity and column):
        return None
    cond = _conditions(sq, entity, dialect)
    if cond is None:
        return None
    start = _d(cur["start"])
    stop = min(_d(cur["end"]), today + timedelta(days=1))
    col = f"{entity}.{dialect.q(column)}"
    # Her ölçü kendi satırlarında biter (satış 17 Ağustos'ta, ileri tarihli üretim fişleri bugüne kadar):
    # her ölçünün son günü ayrı okunur, en erkeni alınır — iki dönemde de her ölçü dolu olsun.
    sql = _last_day_sql(entity, col, cond, start, stop, dialect)
    return {"kind": kind, "sql": sql, "period": (start, stop), "entity": entity, "column": column}


def last_day_of(result: dict[str, Any]) -> tuple[bool, Optional[date]]:
    """(okundu mu, son gün). Tek satır; ölçü başına bir kolon. Kaydı olan ölçülerin en erken son günü;
    hiçbirinin kaydı yoksa None (dönemde kayıt yok)."""
    rows = (result or {}).get("records") or []
    if len(rows) != 1:
        return False, None
    row = rows[0]
    values = list(row.values()) if isinstance(row, dict) else list(row or [])
    days = [_d(v) for v in values if v is not None]
    if any(d is None for d in days):
        return False, None
    return True, (min(days) if days else None)


def apply(sq, plan: dict[str, Any], last: Optional[date]) -> bool:
    """Ölçülen son günü soruya uygular. Dönem değiştiyse True (derleme kırpılmış dönemle yapılır)."""
    entity = plan["entity"]
    if plan["kind"] == "single":
        cur = sq.temporal[0]
        label = "varsayılan dönem" if "varsay" in (cur.text or "").lower() else f"'{cur.text}' dönemi"
        if last is None:
            sq.explanation.append(
                f"Veri kapsamı: {label} içinde {entity} kaydı yok; kayıtlar bu dönemden önce bitiyor "
                "olabilir. Boş ya da sıfır sonuç, işlem olmadığı anlamına gelmeyebilir.")
        elif last + timedelta(days=1) < plan["period"][1]:
            # yalnız veri bugüne ulaşmıyorsa: canlı bir kaynakta "bu yıl bugüne kadar" zaten sorulandır
            sq.explanation.append(
                f"Veri kapsamı: {entity} kayıtları {_tr(last)} tarihinde bitiyor; {label} "
                f"{_tr(cur.start)}–{_tr(last)} arasındaki kayıtları kapsar.")
        return False

    comp = sq.comparison
    cur_d, ref_d = comp["current"], comp["reference"]
    cs, ce = _d(cur_d["start"]), _d(cur_d["end"])
    rs, re_ = _d(ref_d["start"]), _d(ref_d["end"])
    if last is None:
        # Güncel dönemde hiç kayıt yok: kırpılacak bir nokta yok. Takvim notu kalır, üstüne söylenir.
        sq.explanation.append(
            f"Karşılaştırmada güncel dönem ('{cur_d.get('text')}') için {entity} kaydı yok; veri bu dönemden "
            "önce bitiyor olabilir. Güncel dönemin sıfır görünmesi işlem olmadığı anlamına gelmeyebilir.")
        comp["dataEnd"] = None
        return False
    new_ce = last + timedelta(days=1)
    if new_ce >= ce:
        return False                      # güncel dönem sonuna kadar dolu: takvim dönemleri eş süreli
    new_re = aligned_end(cs, rs, re_, last)
    if new_re is None:
        return False
    ref_last = new_re - timedelta(days=1)

    def clip(slot, end, through):
        params = dict(slot.params or {})
        params.update(through=through.isoformat(), calendar_end=slot.end.isoformat() if slot.end else None,
                      aligned="SAME_ELAPSED")
        return replace(slot, end=end, params=params)

    new_temporal = []
    cur_slot = ref_slot = None
    for t in sq.temporal:
        if (t.start, t.end) == (cs, ce) and cur_slot is None:
            cur_slot = clip(t, new_ce, last)
            new_temporal.append(cur_slot)
        elif (t.start, t.end) == (rs, re_) and ref_slot is None:
            ref_slot = clip(t, new_re, ref_last)
            new_temporal.append(ref_slot)
        else:
            new_temporal.append(t)
    if cur_slot is None or ref_slot is None:
        return False
    sq.temporal = new_temporal
    comp.update(current=cur_slot.to_dict(), reference=ref_slot.to_dict(), alignment="SAME_ELAPSED",
                coverageComparable=True, dataEnd=last.isoformat(), dataEndSource="measure_max_date",
                calendar={"current": [cs.isoformat(), ce.isoformat()], "reference": [rs.isoformat(), re_.isoformat()]})
    sq.explanation[:] = [e for e in sq.explanation if not e.startswith(_CALENDAR_NOTE)]
    sq.explanation.append(
        f"Karşılaştırmada eş dönem kullanıldı: {entity} kayıtları {_tr(last)} tarihinde bitiyor; "
        f"'{cur_slot.text}' {_tr(cs)}–{_tr(last)}, '{ref_slot.text}' aynı dönem {_tr(rs)}–{_tr(ref_last)} alındı.")
    return True


# ----------------------------------------------------------------------------------------------------
# Boş cevap: dönem veriden sonra mı kalıyor?
#
# "Bugün en çok satan kitap" boş döndüğünde cevap "kayıtlar bu dönemden önce bitiyor olabilir"
# diyordu: ne zaman bittiğini söylemiyor, ne sorulabileceğini göstermiyordu. Boş cevaptan SONRA
# (yalnız o zaman; dolu cevaba bir sorgu eklenmez) ölçünün kendi tablosunda, sorunun dönemi bitmeden
# önceki son gün ölçülür. O gün dönemin başından önceyse dönem veriden sonra kalıyordur: açıklama
# tarihi söyler ve aynı soru, sorudaki dönem ifadesi verinin son gününü içeren AYNI TÜRDEN döneme
# çevrilerek önerilir (gün → o gün, hafta → o hafta, ay → o ay, son N gün → son güne biten N gün).
# Öneri kalıp değil, sorunun kendi metni: ifade yerinde değiştirilir ve yeni soru ayrıştırıcıdan
# geri geçirilir; beklenen dönemi vermezse öneri hiç gösterilmez, yalnız tarihli açıklama kalır.
# ----------------------------------------------------------------------------------------------------

_AY = ("ocak", "şubat", "mart", "nisan", "mayıs", "haziran", "temmuz", "ağustos", "eylül", "ekim",
       "kasım", "aralık")


def _day_text(d: date) -> str:
    return f"{d.day} {_AY[d.month - 1]} {d.year}"


def _next_month_start(d: date) -> date:
    return date(d.year + (d.month == 12), d.month % 12 + 1, 1)


def _unit_of(slot, last: date) -> Optional[tuple[date, date, Optional[str]]]:
    """Sorunun dönemi tam bir takvim birimiyse (bir gün, bir hafta, bir ay, bir çeyrek, bir yıl) verinin
    son gününü içeren aynı birim: (başlangıç, hariç bitiş, birimin adı ya da None). Değilse None."""
    s, e, g = slot.start, slot.end, (slot.grain or "").upper()
    if (e - s).days == 1:
        return last, last + timedelta(days=1), None
    if g == "WEEK" and (e - s).days == 7 and s.weekday() == 0:
        mon = last - timedelta(days=last.weekday())
        return mon, mon + timedelta(days=7), None
    if s.day == 1 and e.day == 1:
        months = (e.year - s.year) * 12 + (e.month - s.month)
        if months == 1:
            ms = date(last.year, last.month, 1)
            return ms, _next_month_start(ms), f"{_AY[last.month - 1]} {last.year}"
        if months == 3 and s.month % 3 == 1:
            qm = (last.month - 1) // 3 * 3 + 1
            qs = date(last.year, qm, 1)
            qe = _next_month_start(date(last.year, qm + 2, 1))
            return qs, qe, f"{last.year} {_AY[qm - 1]}-{_AY[qm + 1]}"
        if months == 12 and s.month == 1:
            return date(last.year, 1, 1), date(last.year + 1, 1, 1), str(last.year)
    return None


def target_period(slot, last: date) -> tuple[date, date, str]:
    """Önerilecek dönem ve onu söyleyen ifade. Birim verinin son gününde bitmiyorsa (ay 17'sinde bitti)
    ifade tarih aralığıdır: "ağustos 2026" diye sormak veri dışındaki günleri de soruyor olurdu."""
    unit = _unit_of(slot, last)
    if unit:
        s, e, name = unit
        stop = min(e, last + timedelta(days=1))
        if stop == e and name:
            return s, e, name
    else:
        # son 7 gün, son 3 ay, yılbaşından bugüne...: aynı uzunlukta, verinin son gününde biten pencere
        length = (slot.end - slot.start).days
        s, stop = last - timedelta(days=length - 1), last + timedelta(days=1)
    if stop - s == timedelta(days=1):
        return s, stop, _day_text(s)
    return s, stop, f"{_day_text(s)} ile {_day_text(stop - timedelta(days=1))} arası"


def _span(question: str, slot_text: str) -> Optional[tuple[int, int]]:
    """Ayrıştırıcının bulduğu dönem ifadesinin (katlanmış metin) sorudaki yeri."""
    import re
    from semantic_layer.normalize import fold
    want = re.findall(r"[^\W_]+", slot_text or "")
    toks = [(m.start(), m.end(), fold(m.group(0))) for m in re.finditer(r"[^\W_]+", question or "")]
    n = len(want)
    if not n:
        return None
    for i in range(len(toks) - n + 1):
        if [t[2] for t in toks[i:i + n]] == want:
            return toks[i][0], toks[i + n - 1][1]
    return None


def rephrase(question: str, slot_text: str, phrase: str) -> Optional[str]:
    """Sorudaki dönem ifadesi yerine `phrase`. İfadeye kesme işaretiyle bağlı ek ("bugün'ün") da gider:
    yeni ifadenin ünlüsüyle uyuşmaz. İfade bulunamazsa None."""
    import re
    span = _span(question, slot_text)
    if not span:
        return None
    a, b = span
    tail = re.match(r"['’][^\W_]+", question[b:])
    if tail:
        b += tail.end()
    head = question[a]
    text = phrase[0].upper() + phrase[1:] if head.isupper() else phrase
    return re.sub(r"\s{2,}", " ", question[:a] + text + question[b:]).strip()


def empty_probe(sq, today: date, dialect) -> Optional[dict[str, Any]]:
    """Boş cevaptan sonra: tek dönemli soruda ölçünün son gününü ölçecek sorgu üreticisi.
    Karşılaştırma, dönemi olmayan soru, gelecek dönem (tahmin sorusu) ve ölçülemeyen ölçü: None."""
    if sq.comparison or len(sq.temporal or []) != 1:
        return None
    slot = sq.temporal[0]
    if not (slot.start and slot.end) or slot.start > today:
        return None
    binding = sq.temporal_binding or {}
    entity, column = binding.get("entity"), binding.get("column")
    if not (entity and column):
        return None
    cond = _conditions(sq, entity, dialect)
    if cond is None:
        return None
    col = f"{entity}.{dialect.q(column)}"

    def sql_for(lo: date, hi: date) -> str:
        return _last_day_sql(entity, col, cond, lo, hi, dialect)

    return {"slot": slot, "entity": entity, "stop": min(slot.end, today + timedelta(days=1)), "sql_for": sql_for}


def empty_hint(question: str, slot, last: Optional[date], today: date) -> Optional[dict[str, Any]]:
    """Ölçülen son günle açıklama ve öneri. Veri dönemin içinde de varsa (boşluk sorunun süzgecinden)
    None: o boşluk gerçek bir "yok"tur. Hiç veri bulunmadıysa yalnız açıklama."""
    from semantic_layer.runtime.temporal import parse_temporal
    if last is not None and last >= slot.start:
        return None
    span = _span(question, slot.text)
    shown = question[span[0]:span[1]] if span else f"{_tr(slot.start)}–{_tr(slot.end - timedelta(days=1))}"
    if last is None:
        return {"lastDay": None, "suggestion": None,
                "note": f"Veri kapsamı: '{shown}' ve öncesinde bu ölçünün kaydı yok."}
    note = f"Veri kapsamı: veri {_tr(last)} tarihinde bitiyor; '{shown}' için kayıt yok."
    s, e, phrase = target_period(slot, last)
    asked = rephrase(question, slot.text, phrase)
    suggestion = None
    if asked:
        got = parse_temporal(asked, today)[0]
        # Kurulan soru ayrıştırıcıdan geri geçmeli: tek dönem, tam olarak önerilen dönem.
        if len(got) == 1 and (got[0].start, got[0].end) == (s, e):
            suggestion = {"question": asked, "start": s.isoformat(), "end": e.isoformat()}
    return {"lastDay": last.isoformat(), "note": note, "suggestion": suggestion}


__all__ = ["aligned_end", "probe_plan", "last_day_of", "apply", "empty_probe", "empty_hint",
           "target_period", "rephrase"]
