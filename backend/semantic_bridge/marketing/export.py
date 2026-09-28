"""Pazarlama planının dışa aktarımı: PDF (satış ve grafik ekibine), CSV (satırlar + takvim), yayına hazır paket (zip),
«CRM'e işlenecek» listesi (CSV). Bütçe tutarları yalnız `ozellik:pazarlama.butce-gor` olan kişiye yazılır.

PDF, projedeki tek sunucu tarafı PDF yoluyla aynı yazı tipi çözümünü kullanır (`editorial_export._resolve_fonts`,
fpdf2 + DejaVu). Metinde teknoloji adı geçmez; ürün adı «Zeki AI».
"""
from __future__ import annotations

import csv
import io
import json
import zipfile
from datetime import date, datetime
from typing import Any, Optional

from semantic_bridge.marketing import core as C

PRODUCT = "Zeki AI"


def _num(v: Any) -> Optional[float]:
    """Sayı ya da JSON'dan metin olarak gelmiş sayı («1200», «1200.5») → float; okunamazsa None."""
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, (int, float)):
        return float(v)
    try:
        return float(str(v).strip().replace(",", "."))
    except ValueError:
        return None


def _tr_money(v: Any) -> str:
    n = _num(v)
    if n is None:
        return "—"
    return f"{n:,.0f}".replace(",", ".") + " TL"


def _tr_int(v: Any) -> str:
    n = _num(v)
    return "—" if n is None else f"{n:,.0f}".replace(",", ".")


def _tr_day(v: Any) -> str:
    if not v:
        return "—"
    if isinstance(v, datetime):
        d = v.date()
    elif isinstance(v, date):
        d = v
    else:
        try:
            d = date.fromisoformat(str(v)[:10])
        except ValueError:
            return str(v)
    return f"{d.day:02d}.{d.month:02d}.{d.year}"


def _obj(v: Any, text_key: Optional[str] = None) -> dict[str, Any]:
    """Sözlük beklenen karne/plan alanı metin gelebilir: JSON kolonunda çift kodlanmış metin ya da eski önbellekte düz tarih
    («2026-08-17»). JSON metni sözlüğe açılır; düz metin `text_key` verildiyse o anahtara konur; gerisi boş sözlük."""
    if isinstance(v, dict):
        return v
    if isinstance(v, (str, bytes)):
        raw = v.decode("utf-8", "replace") if isinstance(v, bytes) else v
        try:
            parsed = json.loads(raw)
        except ValueError:
            parsed = None
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, str) and parsed != raw:
            return _obj(parsed, text_key)
        if text_key and raw.strip():
            return {text_key: raw.strip()}
    return {}


def _items(v: Any) -> list[dict[str, Any]]:
    """Liste beklenen alan (JSON metni ya da {items: [...]} olabilir); sözlük olmayan öğeler atlanır."""
    if isinstance(v, (str, bytes)):
        try:
            v = json.loads(v)
        except ValueError:
            return []
    if isinstance(v, dict):
        v = v.get("items")
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


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

    card = _obj(card)
    k = _obj(card.get("kitap"))
    para(f"Timaş Yayınları · {C.KINDS.get(plan['kind'], plan['kind'])} pazarlama planı", 8.5)
    para(plan["baslik"], 15, "B", 1)
    para(f"{plan['id']} · sürüm {plan['surum']} · {plan['durumAdi']}"
         + (f" · onaylayan {plan['onaylayan']} ({_tr_day(plan.get('onayZamani'))})" if plan.get("onaylayan") else ""), 9)
    para(f"Kitap: {k.get('ad') or plan.get('stokKodu')} · {k.get('yazar') or '—'} · {k.get('yayinevi') or '—'} · stok kodu {plan.get('stokKodu') or '—'}")
    para(f"Yayın tarihi: {_tr_day(plan.get('yayinTarihi'))} ({plan.get('yayinTarihiKaynakAdi') or 'kaynak yok'})")
    h = _obj(plan.get("hedef"))
    if h.get("planId") and _num(h.get("adet")) is not None:
        para(f"Satış hedefi ({h.get('year')}): {_tr_int(h['adet'])} adet"
             + (f", {_tr_money(h.get('ciro'))} net ciro" if show_budget else ""))
    else:
        para(f"Satış hedefi: {h.get('not') or 'onaylı hedef yok'}")
    z = _obj(plan.get("zeki"))
    if z.get("konumlama"):
        head("Hedef okur ve konumlama")
        para(z["konumlama"])

    head("Kanal ve bütçe")
    cols = [("Kanal", 38), ("Açıklama", 62 if show_budget else 92), ("Başlangıç", 22), ("Bitiş", 22)]
    if show_budget:
        cols.insert(2, ("Tutar", 30))
    row(cols, "B")
    for ln in _items(plan.get("lines")):
        cells = [(ln.get("kanalAdi") or ln.get("kanal") or "", 38), (ln.get("aciklama") or ln.get("altKanal") or "", 62 if show_budget else 92),
                 (_tr_day(ln.get("baslangic")), 22), (_tr_day(ln.get("bitis")), 22)]
        if show_budget:
            cells.insert(2, (_tr_money(ln.get("tutar")), 30))
        row(cells)
    if show_budget:
        para(f"Toplam: {_tr_money(plan.get('butceToplam'))}", 9.5, "B")
    if z.get("kanalGerekce"):
        para(z["kanalGerekce"], 9)

    head("Takvim (yayın gününe göre)")
    row([("Tarih", 24), ("Gün", 14), ("İş", 106), ("Durum", 30)], "B")
    for t in _items(plan.get("tasks")):
        g = _num(t.get("gunFarki"))
        g = None if g is None else int(g)
        durum = t.get("durum") or ""
        row([(_tr_day(t.get("tarih")), 24), ("" if g is None else (f"D{g:+d}" if g else "D"), 14), (t.get("is") or "", 106),
             (C.TASK_STATUSES.get(durum, durum), 30)])

    approved = [m for m in _items(plan.get("materials")) if m.get("durum") == "onayli"]
    head("Onaylı materyaller")
    if not approved:
        para("Henüz onaylı materyal yok.")
    for m in approved:
        para(f"{m.get('turAdi') or m.get('tur') or ''} (sürüm {m.get('surum') or '—'})", 10, "B", 0.5)
        para(m.get("metin") or "", 9)

    em = _items(card.get("emsal"))
    if em:
        head("Emsal kitaplar (ilk 3 / 6 / 12 ay net adet)")
        row([("Kitap", 86), ("Lansman", 22), ("3 ay", 20), ("6 ay", 20), ("12 ay", 22)], "B")
        for e in em:
            row([(e.get("ad") or e.get("stokKodu") or "—", 86), (e.get("lansman") or "—", 22), (_tr_int(e.get("ilk3")), 20),
                 (_tr_int(e.get("ilk6")), 20), (_tr_int(e.get("ilk12")), 22)])
    # Eski önbellekte veriSonu düz tarih metni olarak gelebilir («2026-08-17»): Logo veri sonu sayılır.
    vs = _obj(card.get("veriSonu"), text_key="logo")
    pdf.ln(3)
    para(f"Satış rakamları Logo faturalı satıştır (iade düşülmüş). Veri sonu: {_tr_day(vs.get('logo'))}"
         + (f"; emsal verisi {vs['emsalAy']} ayına kadar." if vs.get("emsalAy") else "."), 8)
    para(f"Hazırlayan: {user or plan.get('sahip') or '—'} · {PRODUCT}", 8)
    return bytes(pdf.output())
