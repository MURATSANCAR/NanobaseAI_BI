"""DYK kurul paketi PDF'i (A4 dikey, telefonda okunur punto).

PDF yolu diğer belgelerle aynıdır (`editorial_export._resolve_fonts`, fpdf2 + Unicode TTF). PDF yalnız dondurma anında
bir kez üretilir (`kurul.freeze_package`); üretimde «bugün» kullanılmaz, damga (sürüm, dondurma zamanı, içerik özeti)
girdiden gelir. Renk yalnız renkle değil yazıyla da verilir (Dikkat / İzlenmeli / Yolunda / Eşik yok / Kaynak yok).
Ekranda ve belgede teknoloji adı geçmez; model metni «Zeki AI» diye anılır.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from semantic_bridge.editorial_export import _fold, _resolve_fonts

INK = (24, 22, 46)
MUTED = (100, 100, 125)
ACCENT = (124, 92, 255)
LINE = (225, 225, 235)
PAGE_W = 210.0
MARGIN = 16.0
CONTENT_W = PAGE_W - 2 * MARGIN

TONE = {"kirmizi": ((220, 38, 38), "Dikkat"), "sari": ((217, 119, 6), "İzlenmeli"), "yesil": ((5, 150, 105), "Yolunda"),
        "esik_yok": ((148, 163, 184), "Eşik yok")}
GRAY = ((203, 213, 225), "Kaynak yok")
ERR = ((148, 163, 184), "Okunamadı")


def _stamp_day(iso: Optional[str]) -> str:
    if not iso:
        return "—"
    try:
        return datetime.fromisoformat(iso).strftime("%d.%m.%Y %H:%M")
    except ValueError:
        return iso[:16]


def _date_tr(v: Optional[str]) -> str:
    if not v:
        return "—"
    try:
        return datetime.fromisoformat(v[:10]).strftime("%d.%m.%Y")
    except ValueError:
        return v


def render(content: dict[str, Any], summary: Optional[str], stamp: dict[str, Any]) -> bytes:
    try:
        from fpdf import FPDF
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("PDF üretici sunucuda kurulu değil.") from e
    regular, bold = _resolve_fonts()
    uni = regular is not None
    fam = "KurulSans" if uni else "Helvetica"
    T = (lambda s: s) if uni else _fold
    kapak = content.get("kapak") or {}
    top = kapak.get("toplanti") or {}
    company = kapak.get("sirket") or ""
    footer = (f"Kurul paketi · sürüm {stamp.get('surum')} · donduruldu {_stamp_day(stamp.get('dondurma'))} "
              f"({stamp.get('donduran') or '—'}) · içerik {str(stamp.get('icerikSha256') or '')[:12]}")

    class Doc(FPDF):
        def header(self) -> None:
            self.set_font(fam, "B", 9)
            self.set_text_color(*ACCENT)
            self.set_xy(MARGIN, 9)
            self.cell(CONTENT_W * 0.6, 5, T(company), align="L")
            self.set_font(fam, "B", 8.5)
            self.set_text_color(185, 28, 28)
            self.cell(CONTENT_W * 0.4, 5, T("GİZLİ — yalnız kurul üyeleri"), align="R")
            self.set_draw_color(*ACCENT)
            self.set_line_width(0.5)
            self.line(MARGIN, 15.5, PAGE_W - MARGIN, 15.5)
            self.set_y(20)
            self.set_text_color(*INK)

        def footer(self) -> None:
            self.set_y(-13)
            self.set_font(fam, "", 7.2)
            self.set_text_color(*MUTED)
            self.cell(CONTENT_W * 0.82, 5, T(footer), align="L")
            self.cell(CONTENT_W * 0.18, 5, T(f"Sayfa {self.page_no()} / {{nb}}"), align="R")

    p = Doc(orientation="P", unit="mm", format="A4")
    p.alias_nb_pages()
    title = top.get("baslik") or "Kurul paketi"
    p.set_title(title)
    p.set_author(company)
    p.set_creator(company)
    p.set_margins(MARGIN, 20, MARGIN)
    p.set_auto_page_break(auto=True, margin=18)
    if uni:
        p.add_font(fam, "", str(regular))
        p.add_font(fam, "B", str(bold or regular))
    p.add_page()

    def h1(text: str) -> None:
        p.set_x(MARGIN)
        p.set_font(fam, "B", 18)
        p.set_text_color(*INK)
        p.multi_cell(CONTENT_W, 8.5, T(text), align="L")
        p.ln(1)

    def h2(text: str) -> None:
        if p.get_y() > 250:
            p.add_page()
        p.ln(3)
        p.set_x(MARGIN)
        p.set_font(fam, "B", 13.5)
        p.set_text_color(*ACCENT)
        p.multi_cell(CONTENT_W, 7, T(text), align="L")
        p.set_draw_color(*LINE)
        p.set_line_width(0.3)
        p.line(MARGIN, p.get_y() + 0.5, PAGE_W - MARGIN, p.get_y() + 0.5)
        p.ln(2.5)
        p.set_text_color(*INK)

    def para(text: str, size: float = 10.5, color: tuple[int, int, int] = INK, style: str = "", indent: float = 0.0) -> None:
        p.set_font(fam, style, size)
        p.set_text_color(*color)
        p.set_x(MARGIN + indent)
        p.multi_cell(CONTENT_W - indent, size * 0.5, T(text), align="L")
        p.set_text_color(*INK)

    def bullet(text: str, size: float = 10.5, indent: float = 0.0) -> None:
        p.set_font(fam, "", size)
        p.set_x(MARGIN + indent)
        p.cell(4, size * 0.5, T("•"))
        p.multi_cell(CONTENT_W - indent - 4, size * 0.5, T(text), align="L")

    def markdown(text: str) -> None:
        for raw in (text or "").splitlines():
            line = raw.rstrip()
            if not line.strip():
                p.ln(2)
            elif line.startswith("# "):
                para(line[2:].strip(), 13, style="B")
            elif line.startswith("## ") or line.startswith("### "):
                para(line.lstrip("#").strip(), 11.5, style="B")
                p.ln(0.5)
            elif line.lstrip().startswith(("- ", "* ")):
                bullet(line.lstrip()[2:].strip())
            else:
                para(line.replace("**", ""))

    # ---- kapak
    h1(title)
    para(f"{top.get('turAdi') or ''} · {_date_tr(top.get('tarih'))}{(' ' + top['saat']) if top.get('saat') else ''}"
         f"{(' · ' + top['yer']) if top.get('yer') else ''}", 11, MUTED)
    p.ln(2)
    para(f"Gösterge dönemi: {kapak.get('donemAdi') or '—'}. Paket derlendi: {_stamp_day(kapak.get('derleme'))}.", 10.5)
    if kapak.get("katilimcilar"):
        para("Katılımcılar: " + ", ".join(kapak["katilimcilar"]), 10.5)
    ends = kapak.get("veriSonGunleri") or {}
    if ends:
        p.ln(1.5)
        para("Verinin son günü (kaynak başına):", 10, MUTED, "B")
        for k, v in ends.items():
            bullet(f"{k}: {_date_tr(v)}", 10)
        if kapak.get("enEskiVeri"):
            para(f"En eski veri {_date_tr(kapak['enEskiVeri'])} tarihlidir; rakamlar o güne kadardır, «bugün» değildir.", 9.5, MUTED)
    n = content.get("sayilar") or {}
    p.ln(1.5)
    para(f"{n.get('toplam', 0)} göstergeden {n.get('hazir', 0)} hazır, {n.get('gri', 0)} kaynak yok, {n.get('hata', 0)} okunamadı; "
         f"{n.get('kirmizi', 0)} dikkat, {n.get('sari', 0)} izlenmeli.", 10.5)

    # ---- yönetici özeti
    h2("Yönetici özeti")
    if summary:
        markdown(summary)
        if stamp.get("ozetOnaylayan"):
            para(f"Onaylayan: {stamp['ozetOnaylayan']}. Taslağı Zeki AI yazdıysa her sayısı paketteki olgularla denetlendi.", 9, MUTED)
    else:
        para("Bu sürümde yönetici özeti yok.", 10.5, MUTED)

    # ---- göstergeler
    h2("Gösterge tablosu")
    for b in content.get("gostergeler") or []:
        if p.get_y() > 255:
            p.add_page()
        p.ln(1)
        para(b.get("ad") or "", 12, style="B")
        p.ln(0.5)
        for g in b.get("gostergeler") or []:
            if p.get_y() > 262:
                p.add_page()
            if g.get("durum") == "ok":
                color, label = TONE.get(g.get("renk") or "esik_yok", TONE["esik_yok"])
            elif g.get("durum") == "hata":
                color, label = ERR
            else:
                color, label = GRAY
            y = p.get_y()
            p.set_fill_color(*color)
            p.rect(MARGIN, y + 1.2, 3.2, 3.2, style="F")
            p.set_xy(MARGIN + 5, y)
            p.set_font(fam, "B", 10.5)
            value = g.get("degerMetin") if g.get("durum") == "ok" else label
            p.cell(CONTENT_W * 0.62 - 5, 5.6, T(g.get("ad") or ""), align="L")
            p.cell(CONTENT_W * 0.38, 5.6, T(f"{value}  ·  {label}" if g.get("durum") == "ok" else value), align="R")
            p.ln(5.8)
            bits = []
            if g.get("oncekiMetin"):
                bits.append(f"Önceki: {g['oncekiMetin']}" + (f" ({g['oncekiEtiket']})" if g.get("oncekiEtiket") else ""))
            if g.get("hedefMetin"):
                bits.append(f"Hedef: {g['hedefMetin']}")
            if g.get("veriSonGunu"):
                bits.append(f"Veri: {_date_tr(g['veriSonGunu'])}")
            if g.get("kaynak"):
                bits.append(g["kaynak"])
            if g.get("not"):
                bits.append(g["not"])
            if bits:
                para(" · ".join(bits), 8.8, MUTED, indent=5)
            if g.get("yorum"):
                yv = g["yorum"]
                para(f"Yorum ({yv.get('onaylayan') or yv.get('yazan') or '—'}): {yv.get('metin') or ''}", 9.6, INK, indent=5)
            elif g.get("renk") in ("kirmizi", "sari"):
                para("Yorum bekleniyor.", 9, (185, 28, 28), indent=5)
            p.ln(1.2)

    # ---- önceki kararlar
    h2("Önceki kararların durumu")
    prev = content.get("oncekiKararlar") or []
    if not prev:
        para("Önceki toplantılardan izlenen karar yok.", 10.5, MUTED)
    for d in prev:
        para(f"{_date_tr(d.get('tarih'))} · {d.get('toplanti') or ''}", 9, MUTED, "B")
        para(d.get("karar") or "", 10.5)
        for a in d.get("aksiyonlar") or []:
            bullet(f"{a.get('eylem')} — {a.get('sahip') or 'sahip yok'}, termin {_date_tr(a.get('termin'))}: {a.get('durum')}"
                   + (f". Not: {a['sonNot']}" if a.get("sonNot") else ""), 9.8, indent=3)
        p.ln(1.5)
    ak = content.get("aksiyonOzeti") or {}
    para(f"Açık kurul aksiyonu {ak.get('acik', 0)}, geciken {ak.get('geciken', 0)}.", 10, MUTED)

    # ---- gündem
    h2("Gündem")
    ag = content.get("gundem") or []
    if not ag:
        para("Gündem girilmedi.", 10.5, MUTED)
    for it in ag:
        extra = " · ".join(x for x in (it.get("turAdi"), it.get("sunan"), f"{it['sureDk']} dk" if it.get("sureDk") else None) if x)
        bullet(f"{it.get('sira')}. {it.get('baslik')}" + (f" ({extra})" if extra else ""))

    # ---- risk ve pazar
    risk = (content.get("risk") or {}).get("brifing")
    h2("Risk brifingi")
    if risk and risk.get("metin"):
        para(f"Dönem {risk.get('donem')} · onaylayan {risk.get('onaylayan') or '—'}", 9, MUTED)
        markdown(risk["metin"])
    else:
        para("Onaylı risk brifingi yok.", 10.5, MUTED)
    market = content.get("pazar")
    h2("Pazar ve rekabet özeti")
    if market and market.get("metin"):
        para(f"{market.get('donemAd') or market.get('donem')} · onaylayan {market.get('onaylayan') or '—'}", 9, MUTED)
        markdown(market["metin"])
    else:
        para("Onaylı pazar özeti yok.", 10.5, MUTED)
    out = p.output()
    return bytes(out)
