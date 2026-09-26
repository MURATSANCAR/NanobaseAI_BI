"""Son okuma bulgularını kitabın metnine Word yorumu olarak işler (.docx).

Redaksiyon Word'de yapılır: editör bulguları ayrı bir listede değil, metnin kenarında görmek ister.
Belge kitabın okunan metnidir (`source.read`; sayfa başlığı + her span bir paragraf), bulgular metnin
ilgili yerine Word yorumu olarak bağlanır (yazar «Zeki AI»). Kitap geneli bulgular (sayfasız) belgenin
başında kendi paragraflarına bağlanır. HİÇBİR bulgu düşmez: metinde yeri bulunamayan bulgu o sayfanın
başlığına bağlanır ve yorumda «yer bulunamadı» yazar. Editörün «yanlış alarm» dediği bulgu aktarılmaz.

Bu modül denetim değildir (alt çizgi); kart servisi çağırır. Model ve veritabanı yazımı yok.
"""

from __future__ import annotations

import io
import unicodedata

AUTHOR = "Zeki AI"
INITIALS = "ZA"


def _norm(s: str) -> str:
    return " ".join(unicodedata.normalize("NFKC", s or "").split())


def needles(f: dict) -> list[str]:
    """Bulgunun metinde aranacak parçaları, en belirginden başlayarak: alıntının tamamı, denetimin
    işaret ettiği sözcük(ler), alıntının başı."""
    d = f.get("details") or {}
    out = [f.get("quote") or ""]
    forms = d.get("forms")
    if isinstance(forms, list) and len(forms) > 1:
        out.append(forms[1])                     # kelime tekrarı: ikinci geçiş (ilk tekrar)
    for k in ("word", "text"):
        if isinstance(d.get(k), str):
            out.append(d[k])
    occ = d.get("occurrences")
    if isinstance(occ, list) and len(occ) > 1 and isinstance(occ[1], dict):
        out.append(occ[1].get("text") or "")     # kalıp ifade: ikinci geçiş
    q = _norm(f.get("quote") or "")
    if len(q) > 60:
        out.append(q[:60])
    return [n for n in (_norm(x) for x in out) if len(n) >= 2]


def place(paragraphs: list[str], f: dict) -> tuple[int, int, int] | None:
    """(paragraf, başlangıç, bitiş) — bulgunun bağlanacağı metin aralığı; bulunamazsa None.
    Paragraf metinleri normalize edilmiş olmalı (_norm)."""
    for n in needles(f):
        for i, p in enumerate(paragraphs):
            j = p.find(n)
            if j >= 0:
                return i, j, j + len(n)
        low = n.lower()
        for i, p in enumerate(paragraphs):
            j = p.lower().find(low)
            if j >= 0:
                return i, j, j + len(n)
    return None


def cuts(text: str, spans: list[tuple[int, int, int]]) -> list[tuple[str, list[int]]]:
    """Paragraf metnini, yorumların bağlandığı aralıklara göre parçalara böler: [(parça, [yorum sırası])].
    Üst üste binen aralıklar desteklenir (bir parça birden çok yoruma ait olabilir)."""
    bounds = sorted({0, len(text)} | {s for s, _, _ in spans} | {e for _, e, _ in spans})
    out = []
    for a, b in zip(bounds, bounds[1:]):
        if a == b:
            continue
        out.append((text[a:b], [k for s, e, k in spans if s <= a and b <= e]))
    return out


def comment_text(f: dict, placed: bool) -> str:
    t = f"{f.get('label') or f.get('check')}: {f['message']}"
    if f.get("suggestion"):
        t += f"\nÖneri: {f['suggestion']}"
    if not placed:
        t += "\n(Metinde tam yeri bulunamadı; sayfaya bağlandı.)"
    return t


def build(title: str, pages: list[dict], findings: list[dict]) -> bytes:
    """pages: source.read çıktısı ({page_no, spans:[{text}]}); findings: kart servisi satırları
    ({page, check, label, message, suggestion, quote, details}). Word belgesinin baytları."""
    from docx import Document
    doc = Document()
    doc.add_heading(f"{title} — son okuma", level=1)
    doc.add_paragraph(f"Zeki AI son okuma bulguları yorum olarak metne işlendi ({len(findings)} bulgu). "
                      "Metin, kitabın okunan hâlidir; sayfa numaraları basılı kitaba göredir.")

    book_wide = [f for f in findings if f.get("page") is None]
    if book_wide:
        doc.add_heading("Kitap geneli", level=2)
        for f in book_wide:
            p = doc.add_paragraph()
            run = p.add_run(f"{f.get('label') or f.get('check')}: {f['message']}")
            doc.add_comment(run, text=comment_text(f, True), author=AUTHOR, initials=INITIALS)

    by_page: dict[int, list[dict]] = {}
    for f in findings:
        if f.get("page") is not None:
            by_page.setdefault(int(f["page"]), []).append(f)
    for pg in pages:
        no = pg["page_no"]
        head = doc.add_heading(f"Sayfa {no}", level=3)
        paras = [_norm(s.get("text") or "") for s in pg.get("spans") or []]
        spans_of: dict[int, list[tuple[int, int, int]]] = {}
        loose = []
        mine = by_page.get(no, [])
        for k, f in enumerate(mine):
            at = place(paras, f)
            if at is None:
                loose.append(k)
            else:
                spans_of.setdefault(at[0], []).append((at[1], at[2], k))
        if loose:
            for k in loose:
                doc.add_comment(head.runs, text=comment_text(mine[k], False), author=AUTHOR, initials=INITIALS)
        for i, text in enumerate(paras):
            p = doc.add_paragraph()
            runs_of: dict[int, list] = {}
            for piece, ks in cuts(text, spans_of.get(i, [])):
                r = p.add_run(piece)
                for k in ks:
                    runs_of.setdefault(k, []).append(r)
            for k, runs in runs_of.items():
                doc.add_comment(runs, text=comment_text(mine[k], True), author=AUTHOR, initials=INITIALS)
    # metni okunmamış sayfalardaki bulgular (sayfa listesinde yok) da düşmez
    known = {pg["page_no"] for pg in pages}
    orphans = [f for no, fs in sorted(by_page.items()) if no not in known for f in fs]
    if orphans:
        doc.add_heading("Metni okunmamış sayfalar", level=2)
        for f in orphans:
            p = doc.add_paragraph()
            run = p.add_run(f"s.{f['page']} — {f.get('label') or f.get('check')}: {f['message']}")
            doc.add_comment(run, text=comment_text(f, False), author=AUTHOR, initials=INITIALS)
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()
