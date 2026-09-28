"""Pazarlama planının dışa aktarımı: PDF (satış ve grafik ekibine), CSV (satırlar + takvim), yayına hazır paket (zip),
«CRM'e işlenecek» listesi (CSV). Bütçe tutarları yalnız `ozellik:pazarlama.butce-gor` olan kişiye yazılır.

PDF, projedeki tek sunucu tarafı PDF yoluyla aynı yazı tipi çözümünü kullanır (`editorial_export._resolve_fonts`,
fpdf2 + DejaVu). Metinde teknoloji adı geçmez; ürün adı «Zeki AI».
"""
from __future__ import annotations

import csv
import io
import zipfile
from datetime import date
from typing import Any, Optional

from semantic_bridge.marketing import core as C

PRODUCT = "Zeki AI"


def _tr_money(v: Any) -> str:
    if v is None:
        return "—"
    return f"{float(v):,.0f}".replace(",", ".") + " TL"


def _tr_day(v: Optional[str]) -> str:
    if not v:
        return "—"
    d = date.fromisoformat(v[:10])
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def plan_csv(plan: dict[str, Any], show_budget: bool) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Plan", plan["id"], plan["baslik"], plan["durumAdi"], f"sürüm {plan['surum']}"])
    w.writerow(["Stok kodu", plan.get("stokKodu") or "", "Yayın tarihi", plan.get("yayinTarihi") or "",
                plan.get("yayinTarihiKaynakAdi") or ""])
    w.writerow([])
    w.writerow(["Kanal", "Alt kanal", "Açıklama", "Tutar (TL)" if show_budget else "Tutar", "Başlangıç", "Bitiş", "Kaynak", "Gerekçe"])
    for ln in plan["lines"]:
        w.writerow([ln["kanalAdi"], ln.get("altKanal") or "", ln.get("aciklama") or "",
                    (f"{ln['tutar']:.2f}".replace(".", ",") if show_budget else ""), ln.get("baslangic") or "",
                    ln.get("bitis") or "", ln["kaynak"] + (" (elle düzeltildi)" if ln["elleDuzeltildi"] else ""), ln.get("gerekce") or ""])
    if show_budget:
        w.writerow(["Toplam", "", "", f"{plan['butceToplam']:.2f}".replace(".", ","), "", "", "", ""])
    w.writerow([])
    w.writerow(["Tarih", "Gün", "İş", "Kanal", "Sorumlu", "Durum"])
    for t in plan["tasks"]:
        g = t.get("gunFarki")
        w.writerow([t.get("tarih") or "", "" if g is None else (f"D{g:+d}" if g else "D"), t["is"],
                    C.CHANNELS.get(t.get("kanal") or "", ""), t.get("sorumlu") or "", C.TASK_STATUSES.get(t["durum"], t["durum"])])
    return "﻿" + buf.getvalue()


def todo_csv(items: list[dict[str, Any]], show_budget: bool) -> str:
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";")
    w.writerow(["Nereye", "Alan / tip", "Yeni değer", "CRM'deki değer", "Tutar", "Başlangıç", "Bitiş", "Kitap", "Plan onaylı mı"])
    for it in items:
        w.writerow([it["hedef"], it.get("alan") or it.get("tip") or "",
                    "" if it["tur"] == "proje-alani" and not show_budget else (it.get("deger") if it.get("deger") is not None else ""),
                    "" if it["tur"] == "proje-alani" and not show_budget else (it.get("crmDeger") or ""),
                    (f"{it['tutar']:.2f}".replace(".", ",") if show_budget and it.get("tutar") is not None else ""),
                    it.get("baslangic") or "", it.get("bitis") or "", it.get("kitap") or "", "evet" if it.get("planOnayli") else "hayır"])
    return "﻿" + buf.getvalue()


def package_zip(plan: dict[str, Any], show_budget: bool) -> bytes:
    """Onaylı materyaller (her biri ayrı metin dosyası) + plan özeti. Yalnız onaylı materyal girer."""
    out = io.BytesIO()
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as z:
        n = 0
        for m in plan["materials"]:
            if m["durum"] != "onayli":
                continue
            n += 1
            z.writestr(f"{n:02d}-{m['tur']}.txt", f"{m['turAdi']} (sürüm {m['surum']}; editoryal onay {m.get('editoryalOnaylayan') or '—'}, "
                                                  f"pazarlama onayı {m.get('onaylayan') or '—'})\n\n{m['metin']}\n")
        z.writestr("plan.csv", plan_csv(plan, show_budget))
        z.writestr("OKUBENI.txt", "Yayına hazır paket: yalnız onaylı materyaller. Gönderim ve yayın ekip tarafından yapılır; "
                                  "portal hiçbir dış kanala (sosyal medya, e-posta, reklam) kendiliğinden göndermez.\n")
    return out.getvalue()


def plan_pdf(plan: dict[str, Any], card: Optional[dict[str, Any]], show_budget: bool, user: str = "") -> bytes:
    try:
        from fpdf import FPDF
    except ImportError as e:  # pragma: no cover
        raise C.MarketingError("PDF üretici sunucuda kurulu değil.", 503) from e
    from semantic_bridge.editorial_export import _fold, _resolve_fonts

    regular, bold = _resolve_fonts()
    fam = "Body" if regular else "Helvetica"
    T = (lambda s: str(s or "")) if regular else (lambda s: _fold(str(s or "")))

    pdf = FPDF(orientation="P", unit="mm", format="A4")
    pdf.set_title(T(plan["baslik"]))
    pdf.set_author(PRODUCT)
    pdf.set_creator(PRODUCT)
    pdf.set_margins(14, 14, 14)
    pdf.set_auto_page_break(auto=True, margin=14)
    if regular:
        pdf.add_font(fam, "", str(regular))
        pdf.add_font(fam, "B", str(bold or regular))
    pdf.add_page()
    W = pdf.w - pdf.l_margin - pdf.r_margin

    def para(s: str, size: float = 9.5, style: str = "", gap: float = 1.5) -> None:
        pdf.set_font(fam, style, size)
        pdf.multi_cell(W, size * 0.5, T(s), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(gap)

    def head(s: str) -> None:
        pdf.ln(2)
        para(s, 12, "B", 1)

    def row(cells: list[tuple[str, float]], style: str = "") -> None:
        pdf.set_font(fam, style, 8.5)
        for txt, w in cells:
            t = T(txt)
            while pdf.get_string_width(t) > w - 1.5 and len(t) > 1:
                t = t[:-2] + "…" if len(t) > 2 else t[:-1]
            pdf.cell(w, 5.5, t, border="B")
        pdf.ln(5.5)

    k = (card or {}).get("kitap") or {}
    para(f"Timaş Yayınları · {C.KINDS.get(plan['kind'], plan['kind'])} pazarlama planı", 8.5)
    para(plan["baslik"], 15, "B", 1)
    para(f"{plan['id']} · sürüm {plan['surum']} · {plan['durumAdi']}"
         + (f" · onaylayan {plan['onaylayan']} ({_tr_day(plan.get('onayZamani'))})" if plan.get("onaylayan") else ""), 9)
    para(f"Kitap: {k.get('ad') or plan.get('stokKodu')} · {k.get('yazar') or '—'} · {k.get('yayinevi') or '—'} · stok kodu {plan.get('stokKodu') or '—'}")
    para(f"Yayın tarihi: {_tr_day(plan.get('yayinTarihi'))} ({plan.get('yayinTarihiKaynakAdi') or 'kaynak yok'})")
    h = plan.get("hedef") or {}
    if h.get("planId") and h.get("adet") is not None:
        para(f"Satış hedefi ({h.get('year')}): {h['adet']:,.0f} adet".replace(",", ".")
             + (f", {_tr_money(h.get('ciro'))} net ciro" if show_budget else ""))
    else:
        para(f"Satış hedefi: {h.get('not') or 'onaylı hedef yok'}")
    z = plan.get("zeki") or {}
    if z.get("konumlama"):
        head("Hedef okur ve konumlama")
        para(z["konumlama"])

    head("Kanal ve bütçe")
    cols = [("Kanal", 38), ("Açıklama", 62 if show_budget else 92), ("Başlangıç", 22), ("Bitiş", 22)]
    if show_budget:
        cols.insert(2, ("Tutar", 30))
    row(cols, "B")
    for ln in plan["lines"]:
        cells = [(ln["kanalAdi"], 38), (ln.get("aciklama") or ln.get("altKanal") or "", 62 if show_budget else 92),
                 (_tr_day(ln.get("baslangic")), 22), (_tr_day(ln.get("bitis")), 22)]
        if show_budget:
            cells.insert(2, (_tr_money(ln["tutar"]), 30))
        row(cells)
    if show_budget:
        para(f"Toplam: {_tr_money(plan['butceToplam'])}", 9.5, "B")
    if z.get("kanalGerekce"):
        para(z["kanalGerekce"], 9)

    head("Takvim (yayın gününe göre)")
    row([("Tarih", 24), ("Gün", 14), ("İş", 106), ("Durum", 30)], "B")
    for t in plan["tasks"]:
        g = t.get("gunFarki")
        row([(_tr_day(t.get("tarih")), 24), ("" if g is None else (f"D{g:+d}" if g else "D"), 14), (t["is"], 106),
             (C.TASK_STATUSES.get(t["durum"], t["durum"]), 30)])

    approved = [m for m in plan["materials"] if m["durum"] == "onayli"]
    head("Onaylı materyaller")
    if not approved:
        para("Henüz onaylı materyal yok.")
    for m in approved:
        para(f"{m['turAdi']} (sürüm {m['surum']})", 10, "B", 0.5)
        para(m["metin"], 9)

    em = ((card or {}).get("emsal") or {}).get("items") or []
    if em:
        head("Emsal kitaplar (ilk 3 / 6 / 12 ay net adet)")
        row([("Kitap", 86), ("Lansman", 22), ("3 ay", 20), ("6 ay", 20), ("12 ay", 22)], "B")
        f = lambda v: "—" if v is None else f"{v:,.0f}".replace(",", ".")  # noqa: E731
        for e in em:
            row([(e.get("ad") or e["stokKodu"], 86), (e.get("lansman") or "—", 22), (f(e.get("ilk3")), 20), (f(e.get("ilk6")), 20),
                 (f(e.get("ilk12")), 22)])
    vs = (card or {}).get("veriSonu") or {}
    pdf.ln(3)
    para(f"Satış rakamları Logo faturalı satıştır (iade düşülmüş). Veri sonu: {_tr_day(vs.get('logo'))}"
         + (f"; emsal verisi {vs['emsalAy']} ayına kadar." if vs.get("emsalAy") else "."), 8)
    para(f"Hazırlayan: {user or plan.get('sahip') or '—'} · {PRODUCT}", 8)
    return bytes(pdf.output())
