"""Aylık yönetim raporu: bir önceki takvim ayının (İstanbul saati) SEO & GEO özeti, PDF olarak.

İçerik: Google arama (tıklama, gösterim, tıklama oranı, ortalama sıra) ayı önceki ay ve geçen yılın aynı ayıyla;
tıklaması en çok artan/azalan sorgu ve sayfalar; en çok satan kitaplarda ürün puanı ≥ 80 olanların payı; ayın öneri
kararları; CRM hak/yayın durumu; teknik sorun sayıları (önceki ayın raporuyla fark); yapay zekâ cevaplarında anılma
oranı (motor başına); açık uyarılar; iş listesi özeti (tablo varsa).

Veri kaynağı: Search Console aylık rakamları servis hesabı tanımlıysa Google'dan yalnız okunarak alınır (Search
Console 16 ay tutar). Tanımlı değilse izleme ekranının biriktirdiği günlük geçmiş kullanılır; ay tam değilse «veri yok».
Teknik tarama, CRM ve ürün puanı tabloları yalnız son hâli tutar; rapordaki değerleri rapor anının durumudur.

Rapor `semantic_seo_monthly`'de (kiracı + ay) özet JSON ve PDF olarak durur. Gönderim yalnız Yönetim'de girilen iç
alıcılara (SEO_MONTHLY_REPORT_TO) e-postadır; alıcı yoksa rapor yalnız ekranda kalır. Başka hiçbir yere gönderilmez.

Gece: ayın ilk gecesi önceki ayın raporu kurulur. Google'ın son günleri 2–3 gün geç kesinleştiği için rapor
«tamamlanmadı» işaretiyle kalır ve veri kesinleşene kadar her gece yeniden kurulur; tamamlanınca (alıcı varsa) bir
kez gönderilir.
"""
from __future__ import annotations

import logging
import re
import smtplib
import ssl
import threading
import time
from datetime import date, datetime, timedelta, timezone
from email.message import EmailMessage
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa
from fastapi import HTTPException, Request
from fastapi.responses import Response

from .store import CRM_BOOKS, GEO_RESULTS, PRODUCTS, PROPOSALS, _md, dumps, iso, loads, now

log = logging.getLogger("semantic.seo_geo.monthly")

GOOD_SCORE = 80               # «iyi» ürün puanı eşiği
TOP_BOOKS = 100               # en çok satan kaç kitaba bakılır (raporda yazılır)
TOP_MOVERS = 10               # en çok kazanan/kaybeden sorgu ve sayfa sayısı (raporda «ilk 10 / toplam» yazılır)
TREND_MONTHS = 12             # grafiklerde gösterilen geçmiş ay sayısı
GSC_LAG_DAYS = 3              # Search Console son günleri kesinleştirmez
PDF_ALERT_ROWS = 20           # PDF'te listelenen açık uyarı (fazlası «ve N tane daha — ekranda» diye yazılır)
NIGHTLY_SETTLE_S = 900
NIGHTLY_WAIT_S = 6 * 3600
WORKLIST_TABLE = "semantic_seo_worklist_state"
MONTH_RE = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")
MONTH_NAMES = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")

MONTHLY = sa.Table(
    "semantic_seo_monthly", _md,  # aylık yönetim raporu: özet + PDF
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("month", sa.String(7), primary_key=True),          # YYYY-MM
    sa.Column("summary_json", sa.Text, nullable=False),
    sa.Column("pdf", sa.LargeBinary),
    sa.Column("complete", sa.Boolean, nullable=False, default=False),  # Google verisi ayın sonuna kadar kesin mi
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("created_by", sa.String(120)),
    sa.Column("sent_at", sa.DateTime(timezone=True)),
    sa.Column("sent_to", sa.Text),
    sa.Column("send_result", sa.String(24)),                     # sent | no_recipient | no_smtp | failed
)

_ready: set[int] = set()
_ready_lock = threading.Lock()


def ensure_tables(engine: sa.engine.Engine) -> None:
    with _ready_lock:
        if id(engine) in _ready:
            return
        MONTHLY.create(engine, checkfirst=True)
        _ready.add(id(engine))


# ------------------------------------------------------------------ zaman: İstanbul, takvim ayı
def local_tz():
    from .watch import local_tz as _tz

    return _tz()


def _aware(v: datetime) -> datetime:
    return v if v.tzinfo else v.replace(tzinfo=timezone.utc)


def local_day(at: datetime, tz: Any = None) -> date:
    return _aware(at).astimezone(tz or local_tz()).date()


def valid_month(m: str) -> bool:
    return bool(MONTH_RE.match(m or ""))


def month_bounds(m: str) -> tuple[date, date]:
    mt = MONTH_RE.match(m or "")
    if not mt:
        raise ValueError("Ay YYYY-AA biçiminde olmalı.")
    y, mo = int(mt.group(1)), int(mt.group(2))
    first = date(y, mo, 1)
    nxt = date(y + (mo == 12), 1 if mo == 12 else mo + 1, 1)
    return first, nxt - timedelta(days=1)


def shift(m: str, n: int) -> str:
    first, _ = month_bounds(m)
    idx = first.year * 12 + first.month - 1 + n
    return f"{idx // 12:04d}-{idx % 12 + 1:02d}"


def month_of(d: date) -> str:
    return f"{d.year:04d}-{d.month:02d}"


def previous_month(at: datetime, tz: Any = None) -> str:
    """`at` anında İstanbul'da biten son tam takvim ayı."""
    return shift(month_of(local_day(at, tz)), -1)


def is_first_day(at: datetime, tz: Any = None) -> bool:
    return local_day(at, tz).day == 1


def month_range_utc(m: str, tz: Any = None) -> tuple[datetime, datetime]:
    """[ayın 1'i 00:00, sonraki ayın 1'i 00:00) İstanbul → UTC."""
    tz = tz or local_tz()
    first, last = month_bounds(m)
    nxt = last + timedelta(days=1)
    return (datetime(first.year, first.month, 1, tzinfo=tz).astimezone(timezone.utc),
            datetime(nxt.year, nxt.month, 1, tzinfo=tz).astimezone(timezone.utc))


def month_label(m: str) -> str:
    first, _ = month_bounds(m)
    return f"{MONTH_NAMES[first.month - 1]} {first.year}"


def short_label(m: str) -> str:
    first, _ = month_bounds(m)
    return f"{MONTH_NAMES[first.month - 1][:3]} {str(first.year)[2:]}"


def gsc_final_until(at: datetime, tz: Any = None) -> date:
    return local_day(at, tz) - timedelta(days=GSC_LAG_DAYS)


def gsc_complete(m: str, at: datetime, tz: Any = None) -> bool:
    return month_bounds(m)[1] <= gsc_final_until(at, tz)


def buildable(m: str, at: datetime, tz: Any = None) -> bool:
    """Yalnız bitmiş takvim ayı (önceki ay ya da daha eskisi)."""
    return valid_month(m) and m <= previous_month(at, tz)


# ------------------------------------------------------------------ hesaplar (düz veri)
def totals(rows: Iterable[dict[str, Any]]) -> Optional[dict[str, Any]]:
    """Günlük satırlar → ay toplamı. Ortalama sıra gösterimle ağırlıklıdır; satırlarda sıra yoksa None."""
    rows = list(rows)
    if not rows:
        return None
    clicks = sum(float(r.get("clicks") or 0) for r in rows)
    imps = sum(float(r.get("impressions") or 0) for r in rows)
    has_pos = any(r.get("position") is not None for r in rows)
    pos = (sum(float(r.get("position") or 0) * float(r.get("impressions") or 0) for r in rows) / imps
           if has_pos and imps else None)
    return {"clicks": clicks, "impressions": imps, "ctr": (clicks / imps) if imps else None, "position": pos,
            "days": len(rows)}


def change(cur: Optional[float], ref: Optional[float]) -> Optional[float]:
    if cur is None or ref is None or not ref:
        return None
    return cur / ref - 1


def movers(prev_rows: list[dict[str, Any]], cur_rows: list[dict[str, Any]], top: int = TOP_MOVERS) -> dict[str, Any]:
    """İki ayın satırları (keys[0] = sorgu ya da sayfa) → tıklaması en çok artan / azalan."""
    def m(rows: list[dict[str, Any]]) -> dict[str, float]:
        out: dict[str, float] = {}
        for r in rows:
            k = (r.get("keys") or [""])[0]
            if k:
                out[k] = out.get(k, 0.0) + float(r.get("clicks") or 0)
        return out

    a, b = m(prev_rows), m(cur_rows)
    diffs = [{"key": k, "clicks": b.get(k, 0.0), "prevClicks": a.get(k, 0.0), "delta": b.get(k, 0.0) - a.get(k, 0.0)}
             for k in set(a) | set(b)]
    gain = sorted((d for d in diffs if d["delta"] > 0), key=lambda d: (-d["delta"], d["key"]))
    lose = sorted((d for d in diffs if d["delta"] < 0), key=lambda d: (d["delta"], d["key"]))
    return {"gainers": gain[:top], "losers": lose[:top], "top": top, "gainersTotal": len(gain), "losersTotal": len(lose)}


def book_share(rows: Iterable[tuple[float, int]], top: int = TOP_BOOKS, good: int = GOOD_SCORE) -> dict[str, Any]:
    """(satış, puan) → en çok satan `top` kitapta ve bütün etkin ürünlerde puanı ≥ good olanların payı."""
    rows = list(rows)
    selling = sorted((r for r in rows if r[0] > 0), key=lambda r: -r[0])[:top]
    g_top = sum(1 for _, s in selling if (s or 0) >= good)
    g_all = sum(1 for _, s in rows if (s or 0) >= good)
    return {"top": top, "threshold": good, "counted": len(selling), "good": g_top,
            "share": (g_top / len(selling)) if selling else None,
            "active": len(rows), "activeGood": g_all, "activeShare": (g_all / len(rows)) if rows else None}


def kpi(summary: dict[str, Any]) -> dict[str, Any]:
    """Eğilim grafiği için ayın öz rakamları."""
    g = (summary.get("google") or {}).get("current") or {}
    geo = [e for e in (summary.get("geo") or {}).get("engines", []) if e.get("measured")]
    mentioned = sum(e.get("mentioned", 0) for e in geo)
    measured = sum(e.get("measured", 0) for e in geo)
    tech = summary.get("tech") or {}
    return {"clicks": g.get("clicks") if g.get("available") else None,
            "impressions": g.get("impressions") if g.get("available") else None,
            "ctr": g.get("ctr") if g.get("available") else None,
            "position": g.get("position") if g.get("available") else None,
            "share80": (summary.get("books") or {}).get("share"),
            "techIssues": sum(i["count"] for i in tech.get("issues", [])) if tech.get("available") else None,
            "geoMention": (mentioned / measured) if measured else None,
            "alertsOpen": (summary.get("alerts") or {}).get("open") if (summary.get("alerts") or {}).get("available") else None}


# ------------------------------------------------------------------ biçim
def n(v: Optional[float], digits: int = 0) -> str:
    if v is None:
        return "—"
    s = f"{v:,.{digits}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def pct(v: Optional[float], digits: int = 1, signed: bool = False) -> str:
    if v is None:
        return "—"
    sign = ("+" if v > 0 else "−" if v < 0 else "") if signed else ("−" if v < 0 else "")
    return f"{sign}%{n(abs(v) * 100, digits)}"


# ------------------------------------------------------------------ PDF
INK, MUTED, ACCENT, SOFT = (28, 28, 38), (110, 110, 125), (255, 107, 74), (245, 243, 240)
GOOD, BAD, VIOLET, GRID = (15, 122, 81), (194, 54, 27), (124, 92, 255), (225, 222, 218)
PAGE_W, PAGE_H, MARGIN = 210, 297, 14
CONTENT_W = PAGE_W - 2 * MARGIN


def render_pdf(s: dict[str, Any], company: str = "Timaş Yayınları") -> bytes:
    """Özet → PDF (fpdf2 + Unicode TTF; TTF yoksa Helvetica ve Türkçe harf sadeleştirme). Grafikler fpdf çizimleriyle."""
    try:
        from fpdf import FPDF
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("PDF üretici sunucuda kurulu değil.") from e
    from semantic_bridge.editorial_export import _fold, _resolve_fonts

    regular, bold = _resolve_fonts()
    uni = regular is not None
    fam = "RaporSans" if uni else "Helvetica"
    T: Callable[[str], str] = (lambda x: x) if uni else _fold
    ELL = "…" if uni else "..."
    month = s["month"]
    title = f"SEO & GEO aylık rapor — {month_label(month)}"

    class MonthlyPdf(FPDF):
        def header(self) -> None:
            self.set_font(fam, "B", 9)
            self.set_text_color(*ACCENT)
            self.set_xy(MARGIN, 9)
            self.cell(CONTENT_W / 2, 5, T(company), align="L")
            self.set_font(fam, "", 8.5)
            self.set_text_color(*MUTED)
            self.cell(CONTENT_W / 2, 5, T(title), align="R")
            self.set_draw_color(*ACCENT)
            self.set_line_width(0.5)
            self.line(MARGIN, 15.5, PAGE_W - MARGIN, 15.5)
            self.set_y(21)
            self.set_text_color(*INK)

        def footer(self) -> None:
            self.set_y(-13)
            self.set_font(fam, "", 7.5)
            self.set_text_color(*MUTED)
            self.cell(CONTENT_W * 0.75, 5, T("ZEKİ AI · SEO & GEO. Rapor yalnız okunan veriden hazırlanır; hiçbir sisteme yazılmaz."), align="L")
            self.cell(CONTENT_W * 0.25, 5, T(f"Sayfa {self.page_no()} / {{nb}}"), align="R")

    p = MonthlyPdf(orientation="P", unit="mm", format="A4")
    p.alias_nb_pages()
    p.set_title(title)
    p.set_author(company)
    p.set_creator("ZEKİ AI")
    p.set_margins(MARGIN, 21, MARGIN)
    p.set_auto_page_break(auto=True, margin=18)
    if uni:
        p.add_font(fam, "", str(regular))
        p.add_font(fam, "B", str(bold or regular))
    p.add_page()

    def room(h: float) -> None:
        if p.get_y() + h > PAGE_H - 20:
            p.add_page()

    def heading(text: str) -> None:
        room(22)
        p.ln(3)
        p.set_font(fam, "B", 12)
        p.set_text_color(*INK)
        p.cell(CONTENT_W, 7, T(text), align="L")
        p.ln(8)

    def note(text: str) -> None:
        p.set_font(fam, "", 8.5)
        p.set_text_color(*MUTED)
        p.multi_cell(CONTENT_W, 4.6, T(text), align="L")
        p.set_text_color(*INK)

    def table(cols: list[tuple[str, float, str]], rows: list[list[str]]) -> None:
        def head() -> None:
            p.set_font(fam, "B", 8)
            p.set_fill_color(*SOFT)
            p.set_text_color(*MUTED)
            for name, w, al in cols:
                p.cell(w, 6.5, T(name), border=0, align=al, fill=True)
            p.ln(6.5)
            p.set_text_color(*INK)
            p.set_font(fam, "", 8.5)

        room(14)
        head()
        for r in rows:
            if p.get_y() + 6 > PAGE_H - 20:
                p.add_page()
                head()
            for (name, w, al), v in zip(cols, r):
                txt, cut = T(v), False
                while len(txt) > 3 and p.get_string_width(txt + (ELL if cut else "")) > w - 1.5:
                    txt, cut = txt[:-1].rstrip(), True
                txt += ELL if cut else ""
                p.cell(w, 6, txt, border="B", align=al)
            p.ln(6)

    def hbars(items: list[tuple[str, Optional[float], str]], vmax: Optional[float] = None, color=ACCENT) -> None:
        """Yatay çubuklar: (etiket, değer, sağdaki yazı)."""
        vals = [v for _, v, _ in items if v is not None]
        top = vmax or (max(vals) if vals else 0) or 1
        label_w, text_w = 58, 30
        bar_w = CONTENT_W - label_w - text_w
        p.set_font(fam, "", 8.5)
        for label, v, right in items:
            room(7)
            y = p.get_y()
            p.cell(label_w, 6, T(label[:40]), align="L")
            p.set_fill_color(*SOFT)
            p.rect(MARGIN + label_w, y + 1.2, bar_w, 3.6, style="F")
            if v:
                p.set_fill_color(*color)
                p.rect(MARGIN + label_w, y + 1.2, max(0.6, bar_w * min(1.0, v / top)), 3.6, style="F")
            p.set_xy(MARGIN + label_w + bar_w, y)
            p.cell(text_w, 6, T(right), align="R")
            p.ln(6.5)

    def vbars(labels: list[str], values: list[Optional[float]], height: float = 42, highlight_last: bool = True) -> None:
        room(height + 12)
        x0, y0 = MARGIN, p.get_y()
        vals = [v for v in values if v is not None]
        top = max(vals) if vals else 0
        top = top or 1
        p.set_draw_color(*GRID)
        p.set_line_width(0.2)
        p.line(x0, y0 + height, x0 + CONTENT_W, y0 + height)
        slot = CONTENT_W / max(1, len(labels))
        bw = min(12, slot * 0.6)
        p.set_font(fam, "", 6.8)
        for i, (lab, v) in enumerate(zip(labels, values)):
            cx = x0 + slot * i + slot / 2
            if v is not None and v > 0:
                h = height * v / top
                p.set_fill_color(*(ACCENT if (highlight_last and i == len(labels) - 1) else VIOLET))
                p.rect(cx - bw / 2, y0 + height - h, bw, h, style="F")
                p.set_text_color(*MUTED)
                p.set_xy(cx - slot / 2, y0 + height - h - 4)
                p.cell(slot, 3.5, T(n(v)), align="C")
            p.set_text_color(*MUTED)
            p.set_xy(cx - slot / 2, y0 + height + 1)
            p.cell(slot, 3.5, T(lab), align="C")
        p.set_text_color(*INK)
        p.set_y(y0 + height + 7)

    def line_chart(points: list[tuple[str, float]], height: float = 38) -> None:
        if len(points) < 2:
            return
        room(height + 12)
        x0, y0 = MARGIN + 12, p.get_y()
        w = CONTENT_W - 12
        top = max(v for _, v in points) or 1
        p.set_draw_color(*GRID)
        p.set_line_width(0.2)
        for k in range(5):
            y = y0 + height * k / 4
            p.line(x0, y, x0 + w, y)
            p.set_font(fam, "", 6.5)
            p.set_text_color(*MUTED)
            p.set_xy(MARGIN, y - 1.8)
            p.cell(11, 3.5, T(n(top * (4 - k) / 4)), align="R")
        step = w / (len(points) - 1)
        p.set_draw_color(*ACCENT)
        p.set_line_width(0.6)
        coords = [(x0 + i * step, y0 + height - height * v / top) for i, (_, v) in enumerate(points)]
        for (xa, ya), (xb, yb) in zip(coords, coords[1:]):
            p.line(xa, ya, xb, yb)
        p.set_font(fam, "", 6.5)
        every = max(1, len(points) // 8)
        for i, (lab, _) in enumerate(points):
            if i % every == 0 or i == len(points) - 1:
                p.set_xy(coords[i][0] - 6, y0 + height + 1)
                p.cell(12, 3.5, T(lab), align="C")
        p.set_text_color(*INK)
        p.set_line_width(0.2)
        p.set_y(y0 + height + 7)

    # ---- kapak
    p.set_font(fam, "B", 18)
    p.cell(CONTENT_W, 9, T(f"{month_label(month)} aylık rapor"), align="L")
    p.ln(10)
    first, last = month_bounds(month)
    note(f"Dönem {first.strftime('%d.%m.%Y')} – {last.strftime('%d.%m.%Y')} (İstanbul saati). "
         f"Hazırlandı {_local_str(s.get('generatedAt'))}."
         + ("" if s.get("complete", True) else " Google verisinin son günleri henüz kesinleşmedi; rapor kesinleşince yeniden hazırlanır."))
    p.ln(2)

    # ---- Google
    g = s.get("google") or {}
    heading("Google arama")
    cur, prev, ly = g.get("current") or {}, g.get("previous") or {}, g.get("lastYear") or {}
    if not cur.get("available"):
        note(cur.get("reason") or "Veri yok.")
    else:
        boxes = [("Tıklama", "clicks", lambda v: n(v)), ("Gösterim", "impressions", lambda v: n(v)),
                 ("Tıklama oranı", "ctr", lambda v: pct(v, 2)), ("Ortalama sıra", "position", lambda v: n(v, 1))]
        bw, bh = (CONTENT_W - 9) / 4, 25
        room(bh + 4)
        y = p.get_y()
        for i, (label, key, f) in enumerate(boxes):
            x = MARGIN + i * (bw + 3)
            p.set_fill_color(*SOFT)
            p.rect(x, y, bw, bh, style="F")
            p.set_xy(x + 2.5, y + 2)
            p.set_font(fam, "", 7.5)
            p.set_text_color(*MUTED)
            p.cell(bw - 5, 4, T(label))
            p.set_xy(x + 2.5, y + 6.5)
            p.set_font(fam, "B", 13)
            p.set_text_color(*INK)
            p.cell(bw - 5, 7, T(f(cur.get(key))))
            for row, (lbl, ref) in enumerate((("Önceki ay", prev), ("Geçen yıl", ly))):
                p.set_xy(x + 2.5, y + 14.5 + row * 4.5)
                p.set_font(fam, "", 7)
                if not ref.get("available"):
                    p.set_text_color(*MUTED)
                    p.cell(bw - 5, 4, T(f"{lbl}: veri yok"))
                    continue
                ch = change(cur.get(key), ref.get(key))
                better = (ch or 0) < 0 if key == "position" else (ch or 0) > 0
                p.set_text_color(*(MUTED if not ch else GOOD if better else BAD))
                p.cell(bw - 5, 4, T(f"{lbl}: {f(ref.get(key))} ({pct(ch, 1, True)})"))
        p.set_text_color(*INK)
        p.set_y(y + bh + 4)
        if cur.get("position") is None:
            note("Ortalama sıra yalnız Google'dan doğrudan okunduğunda hesaplanır.")
        daily = g.get("daily") or []
        if len(daily) >= 2:
            p.set_font(fam, "B", 9)
            p.cell(CONTENT_W, 6, T("Günlük tıklama"))
            p.ln(7)
            line_chart([(str(d["d"])[8:10] + "." + str(d["d"])[5:7], float(d.get("clicks") or 0)) for d in daily])
    trend = s.get("trend") or []
    if sum(1 for t in trend if t.get("clicks") is not None) >= 2:
        p.set_font(fam, "B", 9)
        p.cell(CONTENT_W, 6, T(f"Aylara göre tıklama (son {len(trend)} ay)"))
        p.ln(7)
        vbars([short_label(t["month"]) for t in trend], [t.get("clicks") for t in trend])

    for kind, label in (("queries", "sorgular"), ("pages", "sayfalar")):
        mv = s.get(kind) or {}
        heading(f"Tıklaması en çok değişen {label}")
        if not mv.get("available"):
            note(mv.get("reason") or "Veri yok.")
            continue
        for part, lab, total in (("gainers", "Artan", "gainersTotal"), ("losers", "Azalan", "losersTotal")):
            rows = mv.get(part) or []
            p.set_font(fam, "B", 9)
            p.cell(CONTENT_W, 6, T(f"{lab} — ilk {mv.get('top')} / {n(mv.get(total))}"))
            p.ln(6.5)
            if not rows:
                note("Yok.")
                continue
            table([("Sorgu" if kind == "queries" else "Sayfa", CONTENT_W - 66, "L"), ("Önceki ay", 22, "R"),
                   ("Bu ay", 22, "R"), ("Fark", 22, "R")],
                  [[_short_key(r["key"]), n(r["prevClicks"]), n(r["clicks"]),
                    ("+" if r["delta"] > 0 else "−") + n(abs(r["delta"]))] for r in rows])
            p.ln(2)

    # ---- kitap sayfaları ve öneriler
    b = s.get("books") or {}
    heading("Kitap sayfalarının durumu")
    if b.get("counted"):
        hbars([(f"En çok satan {b['counted']} kitap", b.get("share"), pct(b.get("share"), 0)),
               (f"Bütün etkin ürünler ({n(b.get('active'))})", b.get("activeShare"), pct(b.get("activeShare"), 0))],
              vmax=1.0, color=GOOD)
        note(f"Ürün puanı {b.get('threshold')} ve üstü olanların payı; puan rapor anındaki durumdur.")
    else:
        note("Satış verisi olan ürün yok.")
    pr = s.get("proposals") or {}
    p.ln(1)
    table([("Öneri kararları (bu ay)", CONTENT_W - 40, "L"), ("Sayı", 40, "R")],
          [["Hazırlanan öneri", n(pr.get("created"))], ["Onaylanan", n(pr.get("approved"))],
           ["Reddedilen", n(pr.get("rejected"))], ["Şu an onay bekleyen", n(pr.get("pending"))]])

    # ---- CRM
    crm_ = s.get("crm") or {}
    heading("Haklar ve yayın durumu (satıştaki kitaplar)")
    if crm_.get("available"):
        items = [(crm_.get("labels", {}).get(k, k), float(v), n(v)) for k, v in (crm_.get("rights") or {}).items()]
        items += [(crm_.get("flagLabels", {}).get(k, k), float(v), n(v)) for k, v in (crm_.get("flags") or {}).items()]
        hbars(items, color=VIOLET) if items else note("Kayıt yok.")
    else:
        note("CRM henüz okunmadı.")

    # ---- teknik
    t = s.get("tech") or {}
    heading("Teknik sorunlar")
    if t.get("available"):
        note(f"{n(t.get('checked'))} sayfa tarandı. Fark, bir önceki ayın raporuna göredir.")
        rows = [[i["title"], i["severity"], n(i["count"]),
                 "—" if i.get("previous") is None else (("+" if i["count"] - i["previous"] > 0 else "−" if i["count"] < i["previous"] else "") + n(abs(i["count"] - i["previous"])))]
                for i in t.get("issues", [])]
        table([("Sorun", CONTENT_W - 66, "L"), ("Önem", 22, "L"), ("Sayfa", 22, "R"), ("Fark", 22, "R")], rows) if rows else note("Sorun bulunmadı.")
    else:
        note("Tarama henüz yapılmadı.")

    # ---- GEO
    geo_ = s.get("geo") or {}
    heading("Yapay zekâ cevaplarında anılma")
    engines = [e for e in geo_.get("engines", []) if e.get("measured")]
    if engines:
        hbars([(e["label"], e.get("mentionRate"), f"{pct(e.get('mentionRate'), 0)} · {n(e['measured'])} ölçüm") for e in engines],
              vmax=1.0)
        prev_rates = {e["engine"]: e.get("mentionRate") for e in geo_.get("previous", [])}
        if any(prev_rates.get(e["engine"]) is not None for e in engines):
            note("Önceki ay: " + " · ".join(f"{e['label']} {pct(prev_rates.get(e['engine']), 0)}" for e in engines))
    else:
        note("Bu ay ölçüm yok.")

    # ---- uyarılar ve iş listesi
    al = s.get("alerts") or {}
    heading("Uyarılar")
    if al.get("available"):
        bs = al.get("bySeverity") or {}
        note(f"Şu an açık {n(al.get('open'))} (kritik {n(bs.get('kritik', 0))}, yüksek {n(bs.get('yüksek', 0))}, "
             f"orta {n(bs.get('orta', 0))}). Bu ay açılan {n(al.get('openedInMonth'))}, kapanan {n(al.get('resolvedInMonth'))}.")
        items = al.get("items") or []
        if items:
            table([("Önem", 22, "L"), ("Uyarı", CONTENT_W - 22, "L")],
                  [[i["severity"], i["title"]] for i in items[:PDF_ALERT_ROWS]])
            if len(items) > PDF_ALERT_ROWS:
                note(f"ve {n(len(items) - PDF_ALERT_ROWS)} uyarı daha — tamamı İzleme ekranında.")
    else:
        note("İzleme henüz çalışmadı.")
    wl = s.get("worklist") or {}
    if wl.get("available"):
        heading("İş listesi")
        rows = [[str(k), n(v)] for k, v in (wl.get("byStatus") or {}).items()]
        rows.append(["Toplam", n(wl.get("total"))])
        if wl.get("changedInMonth") is not None:
            rows.append(["Bu ay güncellenen", n(wl.get("changedInMonth"))])
        table([("Durum", CONTENT_W - 40, "L"), ("Sayı", 40, "R")], rows)

    return bytes(p.output())


def _short_key(k: str) -> str:
    m = re.match(r"^https?://[^/]+(/.*)?$", k or "")
    return (m.group(1) or "/") if m else (k or "")


def _local_str(iso_str: Optional[str]) -> str:
    if not iso_str:
        return "—"
    try:
        return datetime.fromisoformat(iso_str).astimezone(local_tz()).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return iso_str


# ------------------------------------------------------------------ e-posta
def render_mail(s: dict[str, Any]) -> tuple[str, str]:
    m = s["month"]
    g = (s.get("google") or {})
    cur, prev = g.get("current") or {}, g.get("previous") or {}
    lines = [f"SEO & GEO aylık yönetim raporu — {month_label(m)}", ""]
    if cur.get("available"):
        lines.append(f"Google tıklaması: {n(cur.get('clicks'))} ({pct(change(cur.get('clicks'), prev.get('clicks')), 1, True)} önceki aya göre)")
        lines.append(f"Google gösterimi: {n(cur.get('impressions'))} ({pct(change(cur.get('impressions'), prev.get('impressions')), 1, True)})")
    b = s.get("books") or {}
    if b.get("counted"):
        lines.append(f"En çok satan {b['counted']} kitapta puanı {b['threshold']}+ olan: {pct(b.get('share'), 0)}")
    al = s.get("alerts") or {}
    if al.get("available"):
        lines.append(f"Açık uyarı: {n(al.get('open'))}")
    lines += ["", "Ayrıntılar ekteki PDF'te."]
    return f"SEO & GEO aylık rapor — {month_label(m)}", "\n".join(lines)


def send_pdf_mail(to: list[str], subject: str, text: str, pdf: bytes, filename: str) -> str:
    """watch.send_mail ile aynı ayar ve akış, PDF ekli. → sent | no_recipient | no_smtp | failed."""
    if not to:
        return "no_recipient"
    from semantic_bridge import alerts as alerts_mod

    cfg = alerts_mod.smtp_settings()
    if not cfg:
        return "no_smtp"
    try:
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, cfg["sender"], ", ".join(to)
        msg.set_content(text)
        msg.add_attachment(pdf, maintype="application", subtype="pdf", filename=filename)
        ctx = ssl.create_default_context()
        server = (smtplib.SMTP_SSL(cfg["host"], cfg["port"], timeout=30, context=ctx) if cfg["ssl"]
                  else smtplib.SMTP(cfg["host"], cfg["port"], timeout=30))
        with server as s:
            if not cfg["ssl"] and cfg["starttls"]:
                s.starttls(context=ctx)
            if cfg["user"]:
                s.login(cfg["user"], cfg["password"])
            s.send_message(msg)
        return "sent"
    except Exception as e:  # noqa: BLE001
        log.warning("aylık rapor e-postası gönderilemedi: %s", e)
        return "failed"


# ------------------------------------------------------------------ çalışan kısım
class Monthly:
    def __init__(self, seo: Any) -> None:
        self.seo = seo
        self.lock = threading.Lock()
        self.state: dict[str, Any] = {"running": False, "month": None, "startedAt": None, "finishedAt": None, "error": None}

    def engine(self) -> sa.engine.Engine:
        eng = self.seo.engine()
        ensure_tables(eng)
        return eng

    # ---- Google
    def _api(self) -> bool:
        from . import connections

        return bool(connections.service_account_email()) and bool(self.seo.conf("GSC_SITE"))

    def _history_rows(self, m: str) -> list[dict[str, Any]]:
        """İzleme ekranının biriktirdiği günlük geçmiş (sıra bilgisi yok)."""
        from .watch import DAILY, ensure_tables as watch_tables

        eng = self.engine()
        watch_tables(eng)
        first, last = month_bounds(m)
        with eng.connect() as c:
            rows = c.execute(sa.select(DAILY.c.day, DAILY.c.clicks, DAILY.c.impressions).where(
                DAILY.c.tenant_id == self.seo.tenant(), DAILY.c.day >= first.isoformat(), DAILY.c.day <= last.isoformat())
                .order_by(DAILY.c.day)).all()
        return [{"keys": [d], "clicks": cl, "impressions": im} for d, cl, im in rows]

    def gsc_month(self, m: str, api: bool) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        first, last = month_bounds(m)
        days = (last - first).days + 1
        try:
            if api:
                from . import connections

                rows = connections.gsc_query(first.isoformat(), last.isoformat(), ["date"])
                source = "google"
            else:
                rows = self._history_rows(m)
                source = "gecmis"
                if len(rows) < days:
                    return {"month": m, "available": False,
                            "reason": "Veri yok: Google bağlantısı tanımlı değil ve bu ayın günlük geçmişi tam değil."}, []
        except Exception as e:  # noqa: BLE001 — rapor Google'sız da çıkar
            return {"month": m, "available": False, "reason": f"Search Console okunamadı: {str(e)[:200]}"}, []
        t = totals(rows)
        if not t:
            return {"month": m, "available": False, "reason": "Veri yok."}, []
        daily = [{"d": str((r.get("keys") or [""])[0])[:10], "clicks": float(r.get("clicks") or 0),
                  "impressions": float(r.get("impressions") or 0)} for r in rows]
        return {"month": m, "available": True, "source": source, **t}, sorted(daily, key=lambda d: d["d"])

    def gsc_movers(self, m: str, dim: str) -> dict[str, Any]:
        from . import connections

        try:
            a, b = month_bounds(m)
            pa, pb = month_bounds(shift(m, -1))
            cur = connections.gsc_all(a.isoformat(), b.isoformat(), [dim])
            prev = connections.gsc_all(pa.isoformat(), pb.isoformat(), [dim])
        except Exception as e:  # noqa: BLE001
            return {"available": False, "reason": f"Search Console okunamadı: {str(e)[:200]}"}
        return {"available": True, **movers(prev, cur)}

    # ---- rapor
    def stored(self, m: str) -> Optional[dict[str, Any]]:
        with self.engine().connect() as c:
            r = c.execute(sa.select(MONTHLY.c.summary_json).where(MONTHLY.c.tenant_id == self.seo.tenant(),
                                                                  MONTHLY.c.month == m)).scalar()
        return loads(r, None) if r else None

    def build(self, m: str, at: Optional[datetime] = None) -> dict[str, Any]:
        from . import EAN, SALES, crm, geo
        from .tech import CHECKS, TECH
        from .watch import EVENTS, FLAG_TEXT, RIGHTS_LABEL, SEV_ORDER

        at = at or now()
        tenant, eng = self.seo.tenant(), self.engine()
        a, b = month_range_utc(m)
        api = self._api()
        out: dict[str, Any] = {"month": m, "label": month_label(m), "generatedAt": iso(at), "tz": "Europe/Istanbul",
                               "complete": (not api) or gsc_complete(m, at)}

        cur, daily = self.gsc_month(m, api)
        prev, _ = self.gsc_month(shift(m, -1), api)
        ly, _ = self.gsc_month(shift(m, -12), api)
        out["google"] = {"current": cur, "previous": prev, "lastYear": ly, "daily": daily}
        if not api:
            reason = "Veri yok: Google bağlantısı tanımlı değil; sorgu ve sayfa kırılımı yalnız Google'dan okunur."
            out["queries"] = {"available": False, "reason": reason}
            out["pages"] = {"available": False, "reason": reason}
        else:
            out["queries"] = self.gsc_movers(m, "query")
            out["pages"] = self.gsc_movers(m, "page")

        insp = sa.inspect(eng)
        with eng.connect() as c:
            active = sa.and_(PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.active.is_(True))
            rows = c.execute(sa.select(SALES, PRODUCTS.c.score).where(active)).all()
            out["books"] = book_share((float(s or 0), int(sc or 0)) for s, sc in rows)

            pc = PROPOSALS.c

            def cnt(*cond: Any) -> int:
                return c.execute(sa.select(sa.func.count()).select_from(PROPOSALS).where(pc.tenant_id == tenant, *cond)).scalar() or 0

            out["proposals"] = {"created": cnt(pc.created_at >= a, pc.created_at < b),
                                "approved": cnt(pc.status == "onaylandi", pc.decided_at >= a, pc.decided_at < b),
                                "rejected": cnt(pc.status == "reddedildi", pc.decided_at >= a, pc.decided_at < b),
                                "pending": cnt(pc.status == "hazir")}

            books = c.execute(sa.select(sa.func.count()).select_from(CRM_BOOKS).where(CRM_BOOKS.c.tenant_id == tenant)).scalar() or 0
            if books:
                j = PRODUCTS.join(CRM_BOOKS, sa.and_(CRM_BOOKS.c.tenant_id == PRODUCTS.c.tenant_id, CRM_BOOKS.c.ean == EAN))
                rights = dict(c.execute(sa.select(CRM_BOOKS.c.rights, sa.func.count()).select_from(j).where(active)
                                        .group_by(CRM_BOOKS.c.rights)).all())
                flags = dict(c.execute(sa.select(CRM_BOOKS.c.status_flag, sa.func.count()).select_from(j).where(
                    active, CRM_BOOKS.c.status_flag.isnot(None)).group_by(CRM_BOOKS.c.status_flag)).all())
                out["crm"] = {"available": True, "rights": {k: rights[k] for k in crm.RIGHTS if rights.get(k)},
                              "flags": flags, "labels": RIGHTS_LABEL,
                              "flagLabels": {k: f"CRM'de: {v}" for k, v in FLAG_TEXT.items()}}
            else:
                out["crm"] = {"available": False}

            if insp.has_table(TECH.name):
                tech_rows = c.execute(sa.select(TECH.c.issues).where(TECH.c.tenant_id == tenant)).all()
            else:
                tech_rows = []
            if tech_rows:
                counts: dict[str, int] = {}
                for (issues,) in tech_rows:
                    for k in (issues or "").split(","):
                        if k:
                            counts[k] = counts.get(k, 0) + 1
                prev_rep = self.stored(shift(m, -1)) or {}
                prev_counts = {i["id"]: i["count"] for i in (prev_rep.get("tech") or {}).get("issues", [])} \
                    if (prev_rep.get("tech") or {}).get("available") else None
                out["tech"] = {"available": True, "checked": len(tech_rows), "issues": sorted(
                    ({"id": k, "title": CHECKS[k][1], "severity": CHECKS[k][0], "count": v,
                      "previous": (prev_counts.get(k, 0) if prev_counts is not None else None)}
                     for k, v in counts.items() if k in CHECKS),
                    key=lambda x: (SEV_ORDER.get(x["severity"], 9), -x["count"]))}
            else:
                out["tech"] = {"available": False}

            def geo_rates(lo: datetime, hi: datetime) -> list[dict[str, Any]]:
                g = GEO_RESULTS.c
                rs = c.execute(sa.select(g.engine, sa.func.count(),
                                         sa.func.sum(sa.case((g.mentioned.is_(True), 1), else_=0)),
                                         sa.func.sum(sa.case((g.cited.is_(True), 1), else_=0)))
                               .where(g.tenant_id == tenant, g.ok.is_(True), g.asked_at >= lo, g.asked_at < hi)
                               .group_by(g.engine)).all()
                return [{"engine": e, "label": geo.ENGINES.get(e, {}).get("label", e), "measured": k,
                         "mentioned": int(mm or 0), "cited": int(ci or 0),
                         "mentionRate": (int(mm or 0) / k) if k else None, "citeRate": (int(ci or 0) / k) if k else None}
                        for e, k, mm, ci in sorted(rs, key=lambda r: r[0])]

            pa, pb = month_range_utc(shift(m, -1))
            out["geo"] = {"engines": geo_rates(a, b), "previous": geo_rates(pa, pb)}

            if insp.has_table(EVENTS.name):
                e = EVENTS.c
                open_rows = c.execute(sa.select(e.id, e.severity, e.title, e.link, e.first_seen).where(
                    e.tenant_id == tenant, e.resolved_at.is_(None))).all()
                opened = c.execute(sa.select(sa.func.count()).select_from(EVENTS).where(
                    e.tenant_id == tenant, e.first_seen >= a, e.first_seen < b)).scalar() or 0
                resolved = c.execute(sa.select(sa.func.count()).select_from(EVENTS).where(
                    e.tenant_id == tenant, e.resolved_at >= a, e.resolved_at < b)).scalar() or 0
                items = sorted(({"id": i, "severity": sv, "title": t, "link": l, "firstSeen": iso(f)}
                                for i, sv, t, l, f in open_rows),
                               key=lambda x: (SEV_ORDER.get(x["severity"], 9), x["firstSeen"] or ""))
                by: dict[str, int] = {}
                for it in items:
                    by[it["severity"]] = by.get(it["severity"], 0) + 1
                out["alerts"] = {"available": True, "open": len(items), "bySeverity": by, "openedInMonth": opened,
                                 "resolvedInMonth": resolved, "items": items}
            else:
                out["alerts"] = {"available": False}

            out["worklist"] = self._worklist(c, insp, tenant, a, b)

        out["kpi"] = kpi(out)
        out["trend"] = self._trend(m, out["kpi"])
        return out

    def _worklist(self, c: Any, insp: Any, tenant: str, a: datetime, b: datetime) -> dict[str, Any]:
        """İş listesi tablosu başka modülündür; şeması bilinmediği için yansıtılarak genel sayılır."""
        if not insp.has_table(WORKLIST_TABLE):
            return {"available": False}
        try:
            t = sa.Table(WORKLIST_TABLE, sa.MetaData(), autoload_with=c)
            cond = [t.c.tenant_id == tenant] if "tenant_id" in t.c else []
            total = c.execute(sa.select(sa.func.count()).select_from(t).where(*cond)).scalar() or 0
            col = next((t.c[k] for k in ("status", "state", "decision") if k in t.c), None)
            by = ({str(k): v for k, v in c.execute(sa.select(col, sa.func.count()).where(*cond).group_by(col)).all()}
                  if col is not None else {})
            tcol = next((t.c[k] for k in ("updated_at", "decided_at", "changed_at", "done_at") if k in t.c), None)
            changed = (c.execute(sa.select(sa.func.count()).select_from(t).where(*cond, tcol >= a, tcol < b)).scalar() or 0
                       if tcol is not None else None)
            return {"available": True, "total": total, "byStatus": by, "changedInMonth": changed}
        except Exception as e:  # noqa: BLE001 — iş listesi okunamazsa rapor yine çıkar
            log.warning("aylık rapor: iş listesi okunamadı: %s", e)
            return {"available": False}

    def _trend(self, m: str, current: dict[str, Any]) -> list[dict[str, Any]]:
        lo = shift(m, -(TREND_MONTHS - 1))
        with self.engine().connect() as c:
            rows = c.execute(sa.select(MONTHLY.c.month, MONTHLY.c.summary_json).where(
                MONTHLY.c.tenant_id == self.seo.tenant(), MONTHLY.c.month >= lo, MONTHLY.c.month < m)
                .order_by(MONTHLY.c.month)).all()
        out = [{"month": mm, **(loads(raw, {}).get("kpi") or {})} for mm, raw in rows]
        return out + [{"month": m, **current}]

    def save(self, summary: dict[str, Any], by: str) -> dict[str, Any]:
        """Ay başına tek satır; yeniden kurulursa üzerine yazılır, gönderim bilgisi korunur."""
        try:
            pdf: Optional[bytes] = render_pdf(summary)
        except Exception as e:  # noqa: BLE001 — PDF üretilemese de özet kaydedilir
            log.warning("aylık rapor PDF'i üretilemedi: %s", e)
            pdf = None
        tenant, m = self.seo.tenant(), summary["month"]
        vals = dict(summary_json=dumps(summary), pdf=pdf, complete=bool(summary.get("complete")), created_at=now(),
                    created_by=by)
        with self.engine().begin() as c:
            n_ = c.execute(MONTHLY.update().where(MONTHLY.c.tenant_id == tenant, MONTHLY.c.month == m).values(**vals)).rowcount
            if not n_:
                c.execute(MONTHLY.insert().values(tenant_id=tenant, month=m, **vals))
        return self.row(m)  # type: ignore[return-value]

    def row(self, m: str, with_summary: bool = True) -> Optional[dict[str, Any]]:
        cols = [MONTHLY.c.month, MONTHLY.c.complete, MONTHLY.c.created_at, MONTHLY.c.created_by, MONTHLY.c.sent_at,
                MONTHLY.c.sent_to, MONTHLY.c.send_result, MONTHLY.c.summary_json, (MONTHLY.c.pdf.isnot(None)).label("has_pdf")]
        with self.engine().connect() as c:
            r = c.execute(sa.select(*cols).where(MONTHLY.c.tenant_id == self.seo.tenant(), MONTHLY.c.month == m)).mappings().first()
        return _view(r, with_summary) if r else None

    def run_build(self, m: str, by: str) -> dict[str, Any]:
        if not self.lock.acquire(blocking=False):
            raise _err(409, "Bir aylık rapor şu an hazırlanıyor; biraz sonra yeniden deneyin.")
        self.state.update(running=True, month=m, startedAt=iso(now()), finishedAt=None, error=None)
        try:
            return self.save(self.build(m), by)
        except HTTPException:
            raise
        except Exception as e:  # noqa: BLE001
            self.state["error"] = str(e)[:500]
            log.exception("aylık rapor kurulamadı")
            raise
        finally:
            self.state.update(running=False, finishedAt=iso(now()))
            self.lock.release()

    def recipients(self) -> list[str]:
        from .watch import recipients

        return recipients(self.seo.conf("SEO_MONTHLY_REPORT_TO"))

    def send(self, m: str) -> str:
        with self.engine().connect() as c:
            r = c.execute(sa.select(MONTHLY.c.summary_json, MONTHLY.c.pdf).where(
                MONTHLY.c.tenant_id == self.seo.tenant(), MONTHLY.c.month == m)).first()
        if not r:
            return "missing"
        summary, pdf = loads(r[0], {}), r[1]
        if pdf is None:
            pdf = render_pdf(summary)
        to = self.recipients()
        subject, text = render_mail(summary)
        result = send_pdf_mail(to, subject, text, bytes(pdf), f"seo-geo-aylik-{m}.pdf")
        vals: dict[str, Any] = {"send_result": result}
        if result == "sent":
            vals.update(sent_at=now(), sent_to=", ".join(to))
        with self.engine().begin() as c:
            c.execute(MONTHLY.update().where(MONTHLY.c.tenant_id == self.seo.tenant(), MONTHLY.c.month == m).values(**vals))
        return result

    def run_due(self, at: Optional[datetime] = None) -> str:
        """Gece: önceki ayın raporu yoksa ya da Google verisi kesinleşmemişken kurulduysa (gönderilmediyse) kurulur;
        tamamlanmışsa ve alıcı varsa bir kez gönderilir. Gönderilemeyen sonraki gecelerde yeniden denenir."""
        at = at or now()
        m = previous_month(at)
        r = self.row(m, with_summary=False)
        if r and r["sentAt"]:
            return "already_sent"
        if r is None or not r["complete"]:
            try:
                r = self.run_build(m, "zamanlayıcı")
            except HTTPException:
                return "busy"
        if not r["complete"]:
            return "waiting_final_data"
        if not self.recipients():
            return "no_recipient"
        return self.send(m)


def _view(r: Any, with_summary: bool = True) -> dict[str, Any]:
    s = loads(r["summary_json"], {})
    out = {"month": r["month"], "label": month_label(r["month"]), "complete": bool(r["complete"]),
           "createdAt": iso(r["created_at"]), "createdBy": r["created_by"], "sentAt": iso(r["sent_at"]),
           "sentTo": r["sent_to"], "sendResult": r["send_result"], "hasPdf": bool(r["has_pdf"]), "kpi": s.get("kpi") or {}}
    if with_summary:
        out["summary"] = s
    return out


def _err(status: int, message: str) -> HTTPException:
    return HTTPException(status, {"code": "SEO", "message": message})


def register(app, ctx) -> None:
    seo = ctx.seo
    monthly = Monthly(seo)

    def settings() -> dict[str, Any]:
        from semantic_bridge import alerts as alerts_mod

        return {"recipients": len(monthly.recipients()), "smtp": bool(alerts_mod.smtp_settings()),
                "google": monthly._api()}

    @app.get("/api/v1/seo-geo/monthly")
    def seo_monthly(request: Request, month: str = "") -> dict[str, Any]:
        """Kayıtlı raporlar (yeniden eskiye) ve seçilen ayın özeti (verilmezse en yenisi)."""
        ctx.gate(request)
        if month and not valid_month(month):
            raise _err(422, "Ay YYYY-AA biçiminde olmalı.")
        eng = monthly.engine()
        cols = [MONTHLY.c.month, MONTHLY.c.complete, MONTHLY.c.created_at, MONTHLY.c.created_by, MONTHLY.c.sent_at,
                MONTHLY.c.sent_to, MONTHLY.c.send_result, MONTHLY.c.summary_json, (MONTHLY.c.pdf.isnot(None)).label("has_pdf")]
        with eng.connect() as c:
            rows = c.execute(sa.select(*cols).where(MONTHLY.c.tenant_id == seo.tenant())
                             .order_by(MONTHLY.c.month.desc())).mappings().all()
        items = [_view(r, with_summary=False) for r in rows]
        chosen = next((r for r in rows if r["month"] == month), None) if month else (rows[0] if rows else None)
        return {"items": items, "selected": _view(chosen) if chosen else None,
                "defaultMonth": previous_month(now()), "settings": settings(), "state": monthly.state}

    @app.get("/api/v1/seo-geo/monthly/{month}.pdf")
    def seo_monthly_pdf(month: str, request: Request) -> Response:
        ctx.gate(request)
        if not valid_month(month):
            raise _err(422, "Ay YYYY-AA biçiminde olmalı.")
        with monthly.engine().connect() as c:
            r = c.execute(sa.select(MONTHLY.c.pdf, MONTHLY.c.summary_json).where(
                MONTHLY.c.tenant_id == seo.tenant(), MONTHLY.c.month == month)).first()
        if not r:
            raise _err(404, "Bu ayın raporu henüz hazırlanmadı.")
        pdf = r[0]
        if pdf is None:
            try:
                pdf = render_pdf(loads(r[1], {}))
            except RuntimeError as e:
                raise _err(503, str(e)) from None
        return Response(bytes(pdf), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="seo-geo-aylik-{month}.pdf"'})

    @app.post("/api/v1/seo-geo/monthly/build")
    def seo_monthly_build(request: Request, month: str = "") -> dict[str, Any]:
        user = ctx.gate(request)
        m = month or previous_month(now())
        if not buildable(m, now()):
            raise _err(422, "Yalnız bitmiş bir ay seçilebilir (YYYY-AA).")
        rep = monthly.run_build(m, user)
        seo.audit(user, "run", "monthly-report", f"Aylık SEO/GEO raporu {m}", {"complete": rep["complete"]})
        return rep

    @app.post("/api/v1/seo-geo/monthly/{month}/send")
    def seo_monthly_send(month: str, request: Request) -> dict[str, Any]:
        from semantic_bridge import alerts as alerts_mod

        user = ctx.approver(request)
        if not valid_month(month):
            raise _err(422, "Ay YYYY-AA biçiminde olmalı.")
        if not monthly.recipients():
            raise _err(409, "Aylık rapor alıcısı tanımlı değil (Yönetim → SEO & GEO).")
        if not alerts_mod.smtp_settings():
            raise _err(409, "E-posta sunucusu tanımlı değil (Yönetim → Uyarılar).")
        if not monthly.row(month, with_summary=False):
            raise _err(404, "Bu ayın raporu henüz hazırlanmadı.")
        result = monthly.send(month)
        seo.audit(user, "send", "monthly-report", f"Aylık SEO/GEO raporu {month}", {"result": result})
        if result != "sent":
            raise _err(502, "E-posta gönderilemedi; e-posta ayarlarını denetleyin.")
        return {"result": result, "report": monthly.row(month, with_summary=False)}

    def nightly() -> None:
        """Öteki gece işleri (T-soft/CRM okuması, tarama, ölçüm) bitene kadar bekler; arka planda, gece işini bekletmez."""
        def busy() -> bool:
            flags = [seo.state, seo.crawl, seo.geo_state, getattr(seo, "crm_state", {})]
            tech = getattr(seo, "tech", None)
            if tech is not None:
                flags += [getattr(tech, "state", {}), getattr(tech, "snap_state", {})]
            return any(bool((f or {}).get("running")) for f in flags)

        def job() -> None:
            time.sleep(NIGHTLY_SETTLE_S)
            waited = time.monotonic()
            while busy() and time.monotonic() - waited < NIGHTLY_WAIT_S:
                time.sleep(60)
            try:
                log.info("seo monthly report: %s", monthly.run_due())
            except Exception:  # noqa: BLE001
                log.exception("seo monthly report failed")

        threading.Thread(target=job, name="seo-monthly-nightly", daemon=True).start()

    seo.nightly.append(("monthly", nightly))
