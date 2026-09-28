"""Satış föyünün PDF'i: her föy tek A4 sayfa (paket = onaylı föylerin birleşimi, sayfa sayısı = föy sayısı) ve ay
özeti PDF'i.

Yazı tipi köprüdeki PDF yolundan (`editorial_export._resolve_fonts`, fpdf2 + DejaVu). Sayfa taşmaz: metin blokları
ayrılan kutuya sığacak kadar gösterilir, kesilen blokta «… (tam metin portalda)» yazar — kesme görünürdür. Barkod
EAN-13 olarak çizilir (denetim hanesi yanlışsa çizilmez, rakamları yazılır). Fiyat «tavsiye edilen satış fiyatı»
ifadesiyle (satış biriminin dili ölçülecek). Metinde teknoloji adı yok; oluşturan «Zeki AI».
"""
from __future__ import annotations

import io
from datetime import date
from typing import Any, Callable, Optional

from semantic_bridge.marketing import core as C
from semantic_bridge.marketing import foy as F

PRODUCT = "Zeki AI"
_L = ["0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011"]
_G = ["0100111", "0110011", "0011011", "0100001", "0011101", "0111001", "0000101", "0010001", "0001001", "0010111"]
_R = ["1110010", "1100110", "1101100", "1000010", "1011100", "1001110", "1010000", "1000100", "1001000", "1110100"]
_PARITY = ["LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL"]


def ean13_modules(code: str) -> Optional[str]:
    """13 hane → 95 modüllük çizgi deseni ('1' siyah). Geçersiz kodda None."""
    d = F.digits(code)
    if not F.ean13_ok(d):
        return None
    par = _PARITY[int(d[0])]
    left = "".join((_L if par[i] == "L" else _G)[int(x)] for i, x in enumerate(d[1:7]))
    right = "".join(_R[int(x)] for x in d[7:13])
    return "101" + left + "01010" + right + "101"


def _tr_money(v: Any) -> str:
    if v is None:
        return "—"
    s = f"{float(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return (s[:-3] if s.endswith(",00") else s) + " TL"


def _tr_day(v: Optional[str]) -> str:
    if not v:
        return "—"
    d = date.fromisoformat(str(v)[:10])
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def _pdf():
    try:
        from fpdf import FPDF
    except ImportError as e:  # pragma: no cover
        raise C.MarketingError("PDF üretici sunucuda kurulu değil.", 503) from e
    from semantic_bridge.editorial_export import _fold, _resolve_fonts

    regular, bold = _resolve_fonts()
    fam = "Body" if regular else "Helvetica"
    T = (lambda s: str(s or "")) if regular else (lambda s: _fold(str(s or "")))
    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_author(PRODUCT)
    pdf.set_creator(PRODUCT)
    pdf.set_margins(14, 12, 14)
    if regular:
        pdf.add_font(fam, "", str(regular))
        pdf.add_font(fam, "B", str(bold or regular))
    return pdf, fam, T


def _fit(pdf: Any, fam: str, T: Callable[[Any], str], text: str, w: float, size: float, max_lines: int,
         style: str = "") -> tuple[list[str], bool]:
    """Metni `max_lines` satıra sığdırır; kesildiyse son satır «…» ile biter."""
    pdf.set_font(fam, style, size)
    lines: list[str] = []
    for para in str(text or "").splitlines() or [""]:
        got = pdf.multi_cell(w, size * 0.45, T(para), dry_run=True, output="LINES") if para.strip() else [""]
        lines.extend(got)
    cut = len(lines) > max_lines
    if cut:
        lines = lines[:max_lines]
        last = lines[-1].rstrip()
        suffix = T(" … (tam metin portalda)")
        while last and pdf.get_string_width(last + suffix) > w - 1:
            last = last[:-1]
        lines[-1] = last + suffix
    return lines, cut


def _page(pdf: Any, fam: str, T: Callable[[Any], str], foy: dict[str, Any], donem_label: str, cover: Optional[bytes]) -> None:
    pdf.add_page()
    f = {a["key"]: a.get("deger") for a in foy["alanlar"]}
    W = pdf.w - pdf.l_margin - pdf.r_margin
    x0, y0 = pdf.l_margin, pdf.t_margin

    # başlık bandı
    pdf.set_font(fam, "", 8.5)
    pdf.set_text_color(90, 90, 110)
    pdf.set_xy(x0, y0)
    pdf.cell(W * 0.7, 5, T(f"Timaş Yayınları · Satış föyü · {donem_label}"))
    state = "ONAYLI" if foy["durum"] == "onayli" and not foy.get("eski") else "TASLAK — onaylı değil"
    pdf.set_font(fam, "B", 8.5)
    pdf.set_text_color(160, 30, 30) if state != "ONAYLI" else pdf.set_text_color(20, 120, 70)
    pdf.cell(W * 0.3, 5, T(state), align="R")
    pdf.set_text_color(20, 20, 30)
    pdf.set_draw_color(200, 200, 215)
    pdf.line(x0, y0 + 6.5, x0 + W, y0 + 6.5)

    # kapak
    top = y0 + 10
    cw, ch = 52.0, 78.0
    placed = False
    if cover:
        try:
            pdf.image(io.BytesIO(cover), x=x0, y=top, w=cw, h=ch, keep_aspect_ratio=True)
            placed = True
        except Exception:  # noqa: BLE001 — bozuk görsel: kutu çizilir
            placed = False
    if not placed:
        pdf.set_fill_color(242, 242, 247)
        pdf.rect(x0, top, cw, ch, style="F")
        pdf.set_font(fam, "", 8)
        pdf.set_text_color(120, 120, 135)
        pdf.set_xy(x0, top + ch / 2 - 3)
        pdf.cell(cw, 6, T("Kapak görseli yok"), align="C")
        pdf.set_text_color(20, 20, 30)

    # künye
    rx = x0 + cw + 7
    rw = W - cw - 7
    lines, _ = _fit(pdf, fam, T, f.get("ad") or foy["stokKodu"], rw, 17, 3, "B")
    pdf.set_xy(rx, top)
    pdf.set_font(fam, "B", 17)
    for ln in lines:
        pdf.set_x(rx)
        pdf.cell(rw, 7.6, ln, new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(fam, "", 11)
    pdf.set_x(rx)
    pdf.cell(rw, 6, T(f.get("yazar") or "—"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(fam, "", 8.8)
    pdf.set_text_color(90, 90, 110)
    pdf.set_x(rx)
    pdf.cell(rw, 5, T(" · ".join(x for x in (f.get("yayinevi"), f.get("kitaplik"), f.get("dizi")) if x) or "—"),
             new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(20, 20, 30)
    pdf.ln(1.5)
    rows = [("Yayın tarihi", _tr_day(f.get("yayinTarihi"))), ("Hedef kitle", f.get("hedefKitle") or "—"),
            ("Sayfa", str(f.get("sayfa") or "—")), ("Ebat", f.get("ebat") or "—"), ("Cilt", f.get("cilt") or "—"),
            ("ISBN", f.get("isbn") or "—"), ("Stok kodu", foy["stokKodu"])]
    for k, v in rows:
        pdf.set_x(rx)
        pdf.set_font(fam, "", 8.5)
        pdf.set_text_color(110, 110, 125)
        pdf.cell(26, 5, T(k))
        pdf.set_text_color(20, 20, 30)
        pdf.set_font(fam, "B", 8.8)
        t = T(v)
        while pdf.get_string_width(t) > rw - 27 and len(t) > 2:
            t = t[:-2] + "…"
        pdf.cell(rw - 26, 5, t, new_x="LMARGIN", new_y="NEXT")
    # fiyat kutusu
    py = pdf.get_y() + 2
    pdf.set_fill_color(245, 243, 255)
    pdf.rect(rx, py, rw, 13, style="F")
    pdf.set_xy(rx + 3, py + 1.5)
    pdf.set_font(fam, "", 7.8)
    pdf.set_text_color(90, 70, 160)
    pdf.cell(rw - 6, 4, T("Tavsiye edilen satış fiyatı (KDV dahil)"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_xy(rx + 3, py + 5.8)
    pdf.set_font(fam, "B", 14)
    pdf.set_text_color(20, 20, 30)
    pdf.cell(rw - 6, 6, T(_tr_money(f.get("fiyat"))))

    # barkod
    by = max(top + ch, py + 13) + 5
    mods = ean13_modules(str(f.get("barkod") or ""))
    if mods:
        mw = 0.33
        bx = x0
        for i, m in enumerate(mods):
            if m == "1":
                guard = i < 3 or 45 <= i < 50 or i >= 92
                pdf.rect(bx + i * mw, by, mw, 15 if guard else 13, style="F")
        pdf.set_font(fam, "", 8)
        pdf.set_xy(x0, by + 15.5)
        pdf.cell(95 * mw, 4, T(F.digits(f.get("barkod"))), align="C")
    else:
        pdf.set_font(fam, "", 8.5)
        pdf.set_xy(x0, by + 4)
        pdf.cell(60, 5, T(f"Barkod: {f.get('barkod') or '—'}" + (" (geçersiz)" if f.get("barkod") else "")))
    y = by + 22

    def block(title: str, text: str, max_lines: int, size: float = 9.3) -> None:
        nonlocal y
        if not text:
            return
        pdf.set_xy(x0, y)
        pdf.set_font(fam, "B", 10.5)
        pdf.cell(W, 6, T(title), new_x="LMARGIN", new_y="NEXT")
        lines, _ = _fit(pdf, fam, T, text, W, size, max_lines)
        pdf.set_font(fam, "", size)
        for ln in lines:
            pdf.set_x(x0)
            pdf.cell(W, size * 0.45, ln, new_x="LMARGIN", new_y="NEXT")
        y = pdf.get_y() + 3

    args = f.get("argumanlar") or []
    if isinstance(args, str):
        args = F.split_args(args)
    block("Neden satılır", "\n".join(f"• {a}" for a in args), 9, 9.6)
    block("Tanıtım", f.get("tanitim") or "", 10)
    remaining = int(max(0, (pdf.h - 24 - y - 7) / (9 * 0.45)))
    if remaining >= 3:
        block("Arka kapak", f.get("ozet") or "", remaining, 9)

    # alt bilgi
    pdf.set_xy(x0, pdf.h - 16)
    pdf.set_draw_color(200, 200, 215)
    pdf.line(x0, pdf.h - 17, x0 + W, pdf.h - 17)
    pdf.set_font(fam, "", 7.3)
    pdf.set_text_color(110, 110, 125)
    who = f"onaylayan {foy['onaylayan']} ({_tr_day(foy.get('onayZamani'))})" if foy.get("onaylayan") else "onay bekliyor"
    pdf.multi_cell(W, 3.4, T(f"Föy sürümü {foy['surum']} · {who} · Alanlar CRM kitap kartından; fiyat ve barkod "
                             f"CRM ile karşılaştırıldı. Hazırlayan: {PRODUCT}."))
    pdf.set_text_color(20, 20, 30)


def foy_pdf(foys: list[dict[str, Any]], donem_label: str, covers: dict[str, Optional[bytes]]) -> bytes:
    """Her föy bir sayfa."""
    pdf, fam, T = _pdf()
    pdf.set_auto_page_break(auto=False)
    pdf.set_title(T(f"Satış föyleri · {donem_label}" if len(foys) != 1 else f"Satış föyü · {foys[0]['stokKodu']}"))
    if not foys:
        pdf.add_page()
        pdf.set_font(fam, "", 11)
        pdf.cell(0, 10, T(f"{donem_label} için onaylı föy yok."))
    for f in foys:
        _page(pdf, fam, T, f, donem_label, covers.get(f["stokKodu"]))
    return bytes(pdf.output())


def summary_pdf(view: dict[str, Any], show_budget: bool, user: str, ozet: Optional[str]) -> bytes:
    """Ay özeti: plan–hedef–gerçekleşen, bütçe dağılımı, kalemler, çakışmalar."""
    pdf, fam, T = _pdf()
    pdf.set_auto_page_break(auto=True, margin=14)
    pdf.set_title(T(f"{view['donemAdi']} pazarlama planı özeti"))
    pdf.add_page()
    W = pdf.w - pdf.l_margin - pdf.r_margin

    def para(s: str, size: float = 9.5, style: str = "", gap: float = 1.5) -> None:
        pdf.set_font(fam, style, size)
        pdf.multi_cell(W, size * 0.5, T(s), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(gap)

    def row(cells: list[tuple[str, float]], style: str = "") -> None:
        pdf.set_font(fam, style, 8.5)
        for txt, w in cells:
            t = T(txt)
            while pdf.get_string_width(t) > w - 1.5 and len(t) > 1:
                t = t[:-2] + "…" if len(t) > 2 else t[:-1]
            pdf.cell(w, 5.5, t, border="B")
        pdf.ln(5.5)

    p = view.get("plan") or {}
    pct = lambda v: "—" if v is None else f"%{v * 100:.1f}".replace(".", ",")  # noqa: E731
    para("Timaş Yayınları · Aylık pazarlama planı", 8.5)
    para(f"{view['donemAdi']} pazarlama planı", 15, "B", 1)
    para(f"{p.get('id') or '—'} · sürüm {p.get('surum') or '—'} · {p.get('durumAdi') or 'plan yok'}"
         + (f" · onaylayan {p['onaylayan']}" if p.get("onaylayan") else ""), 9)
    o = view["oncekiAy"]
    para(f"Önceki ay ({o['donemAdi']}): hedefli kitaplarda hedefe oran {pct(o.get('oran'))}"
         + (f", gerçekleşen {_tr_money(o.get('gercek'))} / hedef {_tr_money(o.get('hedef'))}" if show_budget else "")
         + f"; plan işleri {o['isler'].get('yapildi', 0)} / {o['isler'].get('toplam', 0)} yapıldı."
         + (f" {o['not']}" if o.get("not") else ""), 9.5)
    if ozet:
        para("Özet", 12, "B", 1)
        para(ozet, 9.5)
    para("Bütçe dağılımı", 12, "B", 1)
    if show_budget:
        row([("Segment", 40), ("Kanal", 50), ("Öneri", 30), ("Onaylı", 30), ("Hedef payı", 32)], "B")
        for b in view["budget"]:
            row([(b["segmentAdi"], 40), (b["kanalAdi"], 50), (_tr_money(b["oneri"]), 30),
                 (_tr_money(b["onayli"]) if b["onayli"] is not None else "—", 30), (pct(b.get("hedefPayi")), 32)])
        para(f"Toplam: {_tr_money(p.get('butceToplam'))}", 9.5, "B")
    else:
        para("Bütçe tutarlarını görme yetkiniz yok.", 9)
    para("Takvim", 12, "B", 1)
    row([("Tarih", 26), ("Tür", 28), ("Kalem", 92), ("Kanal", 36)], "B")
    for x in view["items"]:
        d = _tr_day(x.get("baslangic")) + ("" if not x.get("bitis") or x["bitis"] == x.get("baslangic") else "–" + _tr_day(x["bitis"])[:5])
        row([(d, 26), (x["turAdi"], 28), (("(!) " if x["cakisma"] else "") + x["baslik"], 92), (x.get("kanalAdi") or "—", 36)])
    conf = [x for x in view["items"] if x["cakisma"]]
    if conf:
        para("Çakışmalar", 12, "B", 1)
        for x in conf:
            for k in x["cakisma"]:
                para(f"{x['baslik']}: {k['neden']} — {', '.join(k.get('ileAd') or [])}", 8.8, gap=0.5)
    pdf.ln(2)
    para(f"Satış rakamları Logo faturalı satıştır (iade düşülmüş). Veri sonu: {_tr_day(o.get('veriSonu'))}. "
         f"Hazırlayan: {user} · {PRODUCT}", 8)
    return bytes(pdf.output())
