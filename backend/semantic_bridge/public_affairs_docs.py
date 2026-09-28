"""M28 belgeleri: teklif dosyası taslağı ve etki raporu (PDF).

PDF yolu M32 teklif belgesiyle aynıdır (`editorial_export._resolve_fonts`, fpdf2 + Unicode TTF). Belge hiçbir yere
gönderilmez; indirilir, kuruma sorumlu verir. Onaylanmamış teklif dosyasının her sayfasında «TASLAK» yazar.
Girdi düz metindir: «# » başlık, «## » bölüm, «- » madde, boş satır paragraf.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from semantic_bridge import public_affairs as PA
from semantic_bridge.editorial_export import _fold, _resolve_fonts

INK = (24, 22, 46)
MUTED = (110, 110, 135)
ACCENT = (124, 92, 255)
DRAFT = (185, 28, 28)
PAGE_W = 210.0
MARGIN = 16.0
CONTENT_W = PAGE_W - 2 * MARGIN


def text_pdf(text: str, *, company: str, title: str, draft: bool = False, footer: str = "") -> bytes:
    try:
        from fpdf import FPDF
    except ImportError as e:  # pragma: no cover
        raise RuntimeError("PDF üretici sunucuda kurulu değil.") from e
    regular, bold = _resolve_fonts()
    uni = regular is not None
    fam = "IliskiSans" if uni else "Helvetica"
    T = (lambda s: s) if uni else _fold

    class Doc(FPDF):
        def header(self) -> None:
            self.set_font(fam, "B", 9)
            self.set_text_color(*ACCENT)
            self.set_xy(MARGIN, 9)
            self.cell(CONTENT_W / 2, 5, T(company), align="L")
            self.set_font(fam, "", 8.5)
            self.set_text_color(*MUTED)
            self.cell(CONTENT_W / 2, 5, T(datetime.now().strftime("%d.%m.%Y")), align="R")
            self.set_draw_color(*ACCENT)
            self.set_line_width(0.5)
            self.line(MARGIN, 15.5, PAGE_W - MARGIN, 15.5)
            if draft:
                self.set_font(fam, "B", 9)
                self.set_text_color(*DRAFT)
                self.set_xy(MARGIN, 17)
                self.cell(CONTENT_W, 5, T("TASLAK — onaylanmamış metin, kuruma verilmez"), align="C")
            self.set_y(24)
            self.set_text_color(*INK)

        def footer(self) -> None:
            self.set_y(-13)
            self.set_font(fam, "", 7.5)
            self.set_text_color(*MUTED)
            self.cell(CONTENT_W * 0.75, 5, T(footer), align="L")
            self.cell(CONTENT_W * 0.25, 5, T(f"Sayfa {self.page_no()} / {{nb}}"), align="R")

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
    for raw in (text or "").splitlines():
        line = raw.rstrip()
        if not line.strip():
            p.ln(2.5)
            continue
        if line.startswith("# "):
            p.set_font(fam, "B", 16)
            p.multi_cell(CONTENT_W, 8, T(line[2:].strip()), align="L")
            p.ln(1)
        elif line.startswith("## "):
            p.ln(2)
            p.set_font(fam, "B", 12)
            p.set_text_color(*ACCENT)
            p.multi_cell(CONTENT_W, 6.5, T(line[3:].strip()), align="L")
            p.set_text_color(*INK)
        elif line.lstrip().startswith("- "):
            p.set_font(fam, "", 10)
            p.set_x(MARGIN + 3)
            p.multi_cell(CONTENT_W - 3, 5.2, T("•  " + line.lstrip()[2:].strip()), align="L")
        else:
            p.set_font(fam, "", 10)
            p.multi_cell(CONTENT_W, 5.2, T(line.strip()), align="L")
    return bytes(p.output())


def _n(v: Optional[float]) -> str:
    if v is None:
        return "—"
    return f"{int(round(v)):,}".replace(",", ".")


def report_text(rep: dict[str, Any]) -> str:
    """Etki raporunun metni (PDF ve ekran aynı sayılardan). CRM toplamları okunamadıysa bunu yazar."""
    y = rep["year"]
    lines = [f"# Kurumsal ilişkiler etki raporu {y}", ""]
    ppl = rep["people"]
    lines += ["## Kişiler", f"- Kişi kartı: {_n(ppl['total'])} (kritik {_n(ppl['critical'])}, kamu görevlisi {_n(ppl['publicOfficials'])})"]
    lines += [f"- {x['label']}: {_n(x['count'])}" for x in ppl["byField"]]
    c = rep["contacts"]
    lines += ["", "## Temas", f"- Temas notu: {_n(c['notes'])} · temas edilen kişi {_n(c['people'])} · kurum {_n(c['orgs'])}"]
    g = rep["gifts"]
    lines += ["", "## Hediye kitap programı (portal kaydı)",
              f"- Gönderilen kitap: {_n(g['sentBooks'])} · kişi {_n(g['sentPeople'])} · geri dönüş {_n(g['feedback'])}",
              "- Durumlar: " + (", ".join(f"{PA.GIFT_STATUS.get(k, k)} {_n(v)}" for k, v in g["byStatus"].items() if v) or "kayıt yok"),
              f"- Aynı kişiye aynı kitap tekrarı: {_n(g['duplicates'])}"]
    crm = rep.get("crm") or {}
    lines += ["", "## CRM tanıtım ve bağış siparişleri"]
    if crm.get("error"):
        lines.append(f"- CRM okunamadı: {crm['error']}")
    else:
        for t in crm.get("types", []):
            lines.append(f"- {t['label']}: {_n(t['orders'])} sipariş, {_n(t['books'])} kitap")
        if not crm.get("types"):
            lines.append("- Bu yıl kayıt yok.")
    pr = rep["projects"]
    reach = pr["reach"]
    lines += ["", "## Kamu projeleri",
              "- Aşamalar: " + (", ".join(f"{PA.STAGES.get(k, k)} {_n(v)}" for k, v in pr["byStage"].items() if v) or "kayıt yok"),
              f"- Erişim (proje kayıtlarından): okul {_n(reach['schools'])}, öğrenci {_n(reach['students'])}, kitap {_n(reach['books'])}, "
              f"katılımcı {_n(reach['participants'])}"]
    for p in pr["items"]:
        lines.append(f"- {p['title']} — {p['orgName'] or 'kurum seçilmedi'} · {p['stageLabel']}")
    return "\n".join(lines) + "\n"
