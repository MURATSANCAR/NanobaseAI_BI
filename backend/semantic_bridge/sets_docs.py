"""M53 belgeleri: kurumsal hediye teklifi (PDF) ve «açılacak kart» listesi (PDF).

Teklif belgesinde yalnız kurumun görmesi gerekenler vardır: seçenek, içerik, kişi başı liste fiyatı, indirim, kişi başı net
fiyat, toplam. Maliyet ve marj iç bilgidir, belgeye yazılmaz. Onaylanmamış teklifin (taslak, onay bekliyor) her sayfasında
«TASLAK» yazar. Belge hiçbir yere gönderilmez; indirilir, gönderimi satış yapar. PDF yolu `editorial_export` ile aynıdır
(fpdf2 + Unicode TTF). Belgede teknoloji adı geçmez.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable, Optional

from semantic_bridge.editorial_export import _fold, _resolve_fonts

INK = (24, 22, 46)
MUTED = (110, 110, 135)
ACCENT = (124, 92, 255)
LINE = (226, 226, 240)
SOFT = (246, 244, 255)
DRAFT = (185, 28, 28)
PAGE_W = 210.0
MARGIN = 16.0
CONTENT_W = PAGE_W - 2 * MARGIN
FINAL = ("onaylandi", "gonderildi", "kazanildi", "kaybedildi")


def money(v: Optional[float]) -> str:
    if v is None:
        return "—"
    s = f"{float(v):,.2f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".") + " TL"


def pct(v: Optional[float]) -> str:
    if v is None:
        return "—"
    s = f"{float(v) * 100:.1f}".rstrip("0").rstrip(".")
    return "%" + s.replace(".", ",")


def _int(v: Any) -> str:
    return "—" if v is None else f"{float(v):,.0f}".replace(",", ".")


def _day(iso: Optional[str]) -> str:
    if not iso:
        return "—"
    try:
        d = datetime.fromisoformat(iso[:19]).date() if "T" in iso else date.fromisoformat(iso[:10])
    except ValueError:
        return iso
    return d.strftime("%d.%m.%Y")


def _doc(company: str, title: str, right: str, draft_note: Optional[str]) -> tuple[Any, Callable[[str], str], str]:
    try:
        from fpdf import FPDF
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("PDF üretici sunucuda kurulu değil.") from e
    regular, bold = _resolve_fonts()
    uni = regular is not None
    fam = "SetSans" if uni else "Helvetica"
    T = (lambda s: s) if uni else _fold

    class Doc(FPDF):
        def header(self) -> None:
            self.set_font(fam, "B", 9)
            self.set_text_color(*ACCENT)
            self.set_xy(MARGIN, 9)
            self.cell(CONTENT_W / 2, 5, T(company), align="L")
            self.set_font(fam, "", 8.5)
            self.set_text_color(*MUTED)
            self.cell(CONTENT_W / 2, 5, T(right), align="R")
            self.set_draw_color(*ACCENT)
            self.set_line_width(0.5)
            self.line(MARGIN, 15.5, PAGE_W - MARGIN, 15.5)
            if draft_note:
                self.set_font(fam, "B", 9)
                self.set_text_color(*DRAFT)
                self.set_xy(MARGIN, 17)
                self.cell(CONTENT_W, 5, T(draft_note), align="C")
            self.set_y(24)
            self.set_text_color(*INK)

        def footer(self) -> None:
            self.set_y(-13)
            self.set_font(fam, "", 7.5)
            self.set_text_color(*MUTED)
            self.cell(CONTENT_W, 5, T(f"Sayfa {self.page_no()} / {{nb}}"), align="R")

    p = Doc(orientation="P", unit="mm", format="A4")
    p.alias_nb_pages()
    p.set_title(title)
    p.set_author(company)
    p.set_creator(company)
    p.set_margins(MARGIN, 24, MARGIN)
    p.set_auto_page_break(auto=True, margin=18)
    if uni:
        p.add_font(fam, "", str(regular))
        p.add_font(fam, "B", str(bold or regular))
    p.add_page()
    return p, T, fam


def _table(p: Any, T: Callable[[str], str], fam: str, head: list[str], widths: list[float], rows: list[list[str]],
           aligns: list[str]) -> None:
    p.set_font(fam, "B", 8.5)
    p.set_fill_color(*SOFT)
    p.set_text_color(*INK)
    for h, w, a in zip(head, widths, aligns):
        p.cell(w, 7, T(h), border=0, align=a, fill=True)
    p.ln(7)
    p.set_font(fam, "", 8.5)
    p.set_draw_color(*LINE)
    for row in rows:
        y0 = p.get_y()
        if y0 > 270:
            p.add_page()
            y0 = p.get_y()
        x = MARGIN
        heights = []
        for cell, w, a in zip(row, widths, aligns):
            p.set_xy(x, y0)
            p.multi_cell(w, 5, T(cell), align=a)
            heights.append(p.get_y() - y0)
            x += w
        h = max(heights + [5])
        p.set_y(y0 + h)
        p.line(MARGIN, y0 + h + 0.5, PAGE_W - MARGIN, y0 + h + 0.5)
        p.ln(1.5)


def offer_pdf(o: dict[str, Any], company: str) -> bytes:
    draft = o.get("durum") not in FINAL
    p, T, fam = _doc(company, f"Kurumsal hediye teklifi {o['id']}", f"Teklif {o['id']}",
                     "TASLAK — onaylanmamış teklif, kuruma gönderilmez" if draft else None)
    p.set_font(fam, "B", 16)
    p.multi_cell(CONTENT_W, 8, T(o.get("firmaAdi") or "Kurum"), align="L")
    p.set_font(fam, "", 10)
    p.set_text_color(*MUTED)
    p.multi_cell(CONTENT_W, 5.5, T(f"Kurumsal hediye teklifi · {_int(o.get('adet'))} kişi · "
                                   f"kişi başı bütçe {money(o.get('kisiBasiButce'))} · geçerlilik {_day(o.get('gecerlilik'))}"))
    p.set_text_color(*INK)
    p.ln(3)
    if o.get("mektup"):
        p.set_font(fam, "", 10)
        for para in [x.strip() for x in str(o["mektup"]).split("\n") if x.strip()]:
            p.multi_cell(CONTENT_W, 5.5, T(para))
            p.ln(1.5)
        p.ln(2)
    p.set_font(fam, "B", 11)
    p.cell(CONTENT_W, 7, T("Seçenekler"), new_x="LMARGIN", new_y="NEXT")
    rows = []
    chosen = set(o.get("secili") or [])
    for s in o.get("secenekler") or []:
        if chosen and s["no"] not in chosen:
            continue
        content = "\n".join((k.get("ad") or k["stok"]) + (f" — {k['yazar']}" if k.get("yazar") else "") for k in s.get("kalemler") or [])
        rows.append([str(s["no"]), f"{s['ad']}\n{content}", money(s.get("birimListe")), pct(s.get("indirim")),
                     money(s.get("birimNet")), money(s.get("toplamNet"))])
    _table(p, T, fam, ["No", "Seçenek ve içerik", "Kişi başı liste", "İndirim", "Kişi başı net", f"Toplam ({_int(o.get('adet'))} kişi)"],
           [10, 70, 26, 18, 26, 28], rows, ["C", "L", "R", "R", "R", "R"])
    tiers = o.get("kademeler") or []
    if tiers:
        p.ln(2)
        p.set_font(fam, "", 8.5)
        p.set_text_color(*MUTED)
        p.multi_cell(CONTENT_W, 4.5, T("Adet kademeleri: " + "; ".join(f"{_int(t['adet'])} ve üstü {pct(t['indirim'])}" for t in tiers)))
    p.ln(2)
    p.set_font(fam, "", 8.5)
    p.set_text_color(*MUTED)
    p.multi_cell(CONTENT_W, 4.5, T("Fiyatlar KDV dahildir. Stok durumu teklif tarihindeki durumdur; teslim tarihi sipariş onayında "
                                   "kesinleşir. Teklif yazılı sipariş ve fatura ile kesinleşir."))
    return bytes(p.output())


def card_pdf(todo: dict[str, Any], company: str) -> bytes:
    p, T, fam = _doc(company, f"Açılacak kart {todo['setId']}", f"Set {todo['setId']}", None)
    p.set_font(fam, "B", 15)
    p.multi_cell(CONTENT_W, 8, T(f"CRM ve Logo'da açılacak set kartı: {todo['ad']}"))
    p.set_font(fam, "", 10)
    p.ln(1)
    for k, v in (("Set tipi", todo.get("setTipi")), ("Satış kanalı", ", ".join(todo.get("satisKanallari") or []) or "—"),
                 ("Önerilen fiyat (KDV dahil)", money(todo.get("onerilenFiyat"))), ("Hedef set adedi", _int(todo.get("hedefAdet"))),
                 ("Ambalaj", todo.get("ambalaj") or "—"), ("Özel gün", todo.get("sezon") or "—"), ("Barkod", todo.get("barkod")),
                 ("Onaylayan", f"{todo.get('onaylayan') or '—'} · {_day(todo.get('onayTarihi'))}")):
        p.set_font(fam, "B", 9.5)
        p.cell(55, 6, T(k))
        p.set_font(fam, "", 9.5)
        p.multi_cell(CONTENT_W - 55, 6, T(str(v)))
    p.ln(2)
    _table(p, T, fam, ["Stok kodu", "Bileşen", "Adet", "KDV %", "Logo stoku"], [34, 86, 18, 18, 22],
           [[b["stok"], b.get("ad") or "", _int(b.get("adet")), _int(b.get("kdv")), _int(b.get("stokAdet"))] for b in todo.get("bilesenler") or []],
           ["L", "L", "R", "R", "R"])
    p.ln(2)
    p.set_font(fam, "B", 10)
    p.cell(CONTENT_W, 6, T("Adımlar"), new_x="LMARGIN", new_y="NEXT")
    p.set_font(fam, "", 9.5)
    for n, step in enumerate(todo.get("adimlar") or [], 1):
        p.multi_cell(CONTENT_W, 5.2, T(f"{n}. {step}"))
    return bytes(p.output())
