"""«Aranan kelimeler ve sayfalar» için tarih aralığı (ZEKI-50).

Saklanan veri: `semantic_seo_gsc` tür başına (günlük/sorgu/sayfa) **tek bir** özet tutar — gece okunan son 28 kesin
gün, satırlar o aralığın toplamıdır (gün kırılımı yok). Bu yüzden başka bir aralık saklanandan süzülemez: seçilen
aralık saklananla aynı değilse Search Console'dan o aralık için okunur (yalnız okuma, T-soft'a/CRM'e dokunmaz) ve
kısa süre bellekte tutulur. Google son 3 günü kesinleştirmez; 16 aydan eskisini hiç tutmaz. Aralık bu sınırların
dışına taşarsa kırpılır ve neden kırpıldığı cevapta yazar; tamamen dışındaysa açık bir hata döner.

Saf kurallar burada (test: backend/semantic_layer/tests/test_seo_search_range.py); uç `seo_geo/__init__.py`.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Callable, Optional

from .store import iso, now

#: Search Console son günleri kesinleştirmez (monthly.GSC_LAG_DAYS ile aynı).
LAG_DAYS = 3
#: Google Search Console performans verisini 16 ay tutar.
KEEP_MONTHS = 16
#: Karşılaştırma türleri: bir önceki eşit uzunlukta dönem, geçen yılın aynı günleri.
COMPARE = ("onceki", "gecen_yil")
#: Tür → Search Console boyutu.
DIMENSION = {"daily": "date", "queries": "query", "pages": "page"}


class RangeError(ValueError):
    """Kullanıcıya olduğu gibi gösterilecek aralık hatası."""


def latest_final(today: date) -> date:
    return today - timedelta(days=LAG_DAYS)


def months_back(d: date, months: int) -> date:
    y, m = divmod(d.year * 12 + (d.month - 1) - months, 12)
    m += 1
    # Ayın son gününü aşma (31 Mart − 1 ay = 28/29 Şubat).
    for day in (d.day, 30, 29, 28):
        try:
            return date(y, m, day)
        except ValueError:
            continue
    raise AssertionError("unreachable")


def earliest_kept(today: date) -> date:
    """Google'ın hâlâ tuttuğu en eski gün (bugünden 16 ay önce; sınırdaki gün eksik olabilir diye +1)."""
    return months_back(today, KEEP_MONTHS) + timedelta(days=1)


def parse_day(v: Optional[str], what: str) -> Optional[date]:
    if v is None or v == "":
        return None
    try:
        return date.fromisoformat(v[:10])
    except ValueError:
        raise RangeError(f"{what} tarihi YYYY-AA-GG biçiminde olmalı: {v!r}.") from None


@dataclass
class Window:
    start: date
    end: date
    notes: list[str] = field(default_factory=list)

    @property
    def days(self) -> int:
        return (self.end - self.start).days + 1

    def iso(self) -> tuple[str, str]:
        return self.start.isoformat(), self.end.isoformat()


def resolve(start: Optional[str], end: Optional[str], today: date) -> Window:
    """İstenen aralığı Google'ın verebileceği aralığa oturtur; kırpılan her uç için not yazar."""
    s, e = parse_day(start, "Başlangıç"), parse_day(end, "Bitiş")
    if s is None or e is None:
        raise RangeError("Tarih aralığı için başlangıç ve bitiş birlikte verilmeli.")
    if s > e:
        raise RangeError("Başlangıç tarihi bitişten sonra olamaz.")
    last, first = latest_final(today), earliest_kept(today)
    if s > last:
        raise RangeError(f"Seçilen aralık henüz kesinleşmedi: Google son {LAG_DAYS} günü sonradan düzeltir; "
                         f"en yeni kesin gün {last.isoformat()}.")
    if e < first:
        raise RangeError(f"Seçilen aralık Google'ın tuttuğu {KEEP_MONTHS} aydan eski; en eski gün {first.isoformat()}.")
    w = Window(s, e)
    if e > last:
        w.end = last
        w.notes.append(f"Bitiş {e.isoformat()} yerine {last.isoformat()}: son {LAG_DAYS} gün Google'da kesinleşmediği "
                       "için dahil edilmez.")
    if s < first:
        w.start = first
        w.notes.append(f"Başlangıç {s.isoformat()} yerine {first.isoformat()}: Google {KEEP_MONTHS} aydan eski veriyi "
                       "tutmaz.")
    return w


def previous(w: Window, kind: str) -> Window:
    """Karşılaştırma dönemi: `onceki` = hemen önceki eşit uzunlukta dönem; `gecen_yil` = geçen yılın aynı günleri."""
    if kind == "onceki":
        end = w.start - timedelta(days=1)
        return Window(end - timedelta(days=w.days - 1), end)
    if kind == "gecen_yil":
        return Window(months_back(w.start, 12), months_back(w.end, 12))
    raise RangeError(f"Bilinmeyen karşılaştırma: {kind!r}.")


class RangeCache:
    """Search Console'dan okunan aralıklar: aynı aralık kısa sürede yeniden istenirse Google'a tekrar gidilmez.
    Satırlar kesilmez; yalnız eski aralıklar bellekten düşer (en çok `slots` aralık, her biri `ttl` saniye)."""

    def __init__(self, ttl: float = 6 * 3600, slots: int = 48):
        self.ttl, self.slots = ttl, slots
        self._lock = threading.Lock()
        self._data: dict[tuple[str, str, str, str], tuple[float, str, list[dict[str, Any]]]] = {}

    def get(self, key: tuple[str, str, str, str], fetch: Callable[[], list[dict[str, Any]]],
            clock: Callable[[], float] = time.time) -> tuple[list[dict[str, Any]], str]:
        """(satırlar, okunma anı ISO) döner; `fetch` hata verirse hata olduğu gibi çıkar, önbelleğe bir şey yazılmaz."""
        t = clock()
        with self._lock:
            hit = self._data.get(key)
            if hit and t - hit[0] < self.ttl:
                return hit[2], hit[1]
        rows = fetch()
        at = iso(now())
        with self._lock:
            self._data[key] = (t, at, rows)
            if len(self._data) > self.slots:
                for k, _ in sorted(self._data.items(), key=lambda kv: kv[1][0])[: len(self._data) - self.slots]:
                    self._data.pop(k, None)
        return rows, at
