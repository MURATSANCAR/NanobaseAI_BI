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


def _open_current(sq, today: date) -> Optional[tuple[str, dict]]:
    """("comparison"|"single", güncel dönem) — yalnız bugünü içeren (açık) bir güncel dönem için.
    Kapanmış bir dönem (2025'e karşı 2024) takvimle kıyaslanır: ikisi de tamdır."""
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
    if not (start and end) or not (start <= today < end):
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
    # tek taramada her ölçünün son günü okunur, en erkeni alınır — iki dönemde de her ölçü dolu olsun.
    picks = [f"MAX(CASE WHEN {c} THEN {col} END) AS last_{i}" if c else f"MAX({col}) AS last_{i}"
             for i, c in enumerate(cond)]
    where = f"{col} >= '{start.isoformat()}' AND {col} < '{stop.isoformat()}'"
    sql = f"SELECT {', '.join(picks)} FROM {entity} WHERE {where}"
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


__all__ = ["aligned_end", "probe_plan", "last_day_of", "apply"]
