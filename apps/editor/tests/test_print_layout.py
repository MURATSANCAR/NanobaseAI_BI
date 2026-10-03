"""Basılı kitabın dizgisinden metnin biçimi (editor.production.print_layout) ve okunmuş paragraflara uygulanması
(manuscript._apply_layout / _finish_layout). PDF yok: satırlar elle kurulur; sayılar gerçek kitaplardan ölçülen
düzendedir (gövde 11 pt, sütun 75–369, dipnot 9 pt, üst başlık 7 pt)."""

from __future__ import annotations

from editor.production import print_layout as L
from editor.production.manuscript import Block, Chapter, Manuscript, _apply_layout, _finish_layout, normalize


def ln(text, x0=75, x1=369, y=100, size=11.0, italic=0.0, sup=None):
    return L.Line(text, x0, x1, y, y + size, size, italic, sup or [])


def page(body, notes=None, heads=None, tables=None, perde=False):
    pg = L.Page(heads=set(heads or []), notes=notes or [], body=body, refs=[s for x in body for s in x.sup],
                tables=tables or [], table_y=[300.0] * len(tables or []), perde=perde)
    pg.note_key = "".join(L.fold(t) for _, t in pg.notes)
    pg.body_folds = [L.fold(x.text) for x in body]
    pg.body_key = "".join(pg.body_folds)
    pg.table_key = "".join(L.fold(c) for t in pg.tables for r in t for c in r)
    pg.left, pg.right, pg.size = 75, 369, 11.0
    return pg


def test_poem_needs_short_lines_same_left_and_body_size():
    poem = [ln("Acayipleşti havalar,", 100, 230), ln("bir güneş, bir yağmur, bir kar.", 100, 260)]
    assert L.kind_of(poem, 75, 369, 11)[0] == "poem"
    assert L.kind_of(poem, 75, 369, 11)[1] == "Acayipleşti havalar,\nbir güneş, bir yağmur, bir kar."
    two_cols = [ln("SBE", 75, 100), ln("Sosyal Bilimler Enstitüsü", 140, 300)]
    assert L.kind_of(two_cols, 75, 369, 11)[0] != "poem"                     # iki sütunlu kısaltma listesi
    caption = [ln("Grafik 23: Konya Vilayetinde", 75, 250), ln("Kalemlerin Ağırlıkları", 75, 230)]
    assert L.kind_of(caption, 75, 369, 11)[0] != "poem"                      # grafik başlığı
    para = [ln("Uzun bir satır " * 4, 75, 369), ln("son satır.", 75, 150)]
    assert L.kind_of(para, 75, 369, 11)[0] == "para"
    signature = [ln("Yakup Akkuş", 280, 369), ln("Şişli, Ocak 2024", 290, 369)]
    assert L.kind_of(signature, 75, 369, 11)[0] == "right"
    quote = [ln("“Müslümanların idaresine ilişkin", 75, 369, italic=1), ln("ihanet etmiştir.”", 75, 200, italic=1)]
    assert L.kind_of(quote, 75, 369, 11)[0] == "italic"


def test_note_lines_join_soft_hyphen():
    assert L._join("Blu\xad", "eprints for a") == "Blueprints for a"
    assert L._join("Zür-", "cher") == "Zürcher"
    assert L._join("s. 276-7.", "27 Bakınız") == "s. 276-7. 27 Bakınız"


def test_apply_layout_drops_heads_and_notes_links_refs_and_places_table():
    p20 = page([ln("uyumludur.18 Benzer bir şekilde Haeckel da", sup=["18"]),
                ln("Darwinizmi kullanmıştır ve Osmanlıda yankı buldu")],
               notes=[["18", "Gregory, Scientific Materialism, s. 184."], ["19", "Corsi, Darwinism in Germany"]],
               heads=[L.fold("DARWIN VE OSMANLILAR"), "20"])
    p21 = page([ln("okuma imkânı buldular.22 Aydınlanmanın hayranları", sup=["22"])],
               notes=[[None, "France and Italy, s. 693."], ["22", "Zürcher, The Young Turks, s. 283."]],
               heads=[L.fold("DARWIN DERSAADET’TE")],
               tables=[[["Gelir", "Gider"], ["10", "5"]]])
    paras = [(20, "DARWIN VE OSMANLILAR"), (20, "uyumludur.18 Benzer bir şekilde Haeckel da Darwinizmi kullanmıştır ve"),
             (20, "18 Gregory, Scientific Materialism, s. 184. 19 Corsi, Darwinism in Germany"),
             (21, "DARWIN DERSAADET’TE"), (21, "Osmanlıda yankı buldu, okuma imkânı buldular.22 Aydınlanmanın hayranları"),
             (21, "Gelir Gider 10 5"), (21, "France and Italy, s. 693. 22 Zürcher, The Young Turks, s. 283.")]
    out, notes = _apply_layout(paras, {20: p20, 21: p21})
    texts = [t for _, t, _ in out]
    assert not any("DARWIN" in t for t in texts)                                 # üst başlık gövdeye girmez
    assert not any(t.startswith("18 Gregory") or t.startswith("France") for t in texts)   # dipnot gövdeye girmez
    assert "uyumludur.[[20:18]] Benzer" in texts[0] and "buldular.[[21:22]] Aydınlanmanın" in texts[1]
    assert any(k == "table" and "<th>Gelir</th>" in t for _, t, k in out)
    assert notes[(20, "19")].endswith("Darwinism in Germany France and Italy, s. 693.")   # sonraki sayfaya taşan not
    chapters = [Chapter(h, b) for h, b in normalize([x for x in out], None)]
    ms = Manuscript("K", chapters=chapters)
    _finish_layout(ms, {20: p20, 21: p21}, notes)
    body = [b.text for c in ms.chapters for b in c.blocks]
    # Not 19'un metinde göndermesi yok: kaybolmaz, sayfanın son paragrafının sonuna bağlanır.
    assert any("uyumludur.[1] Benzer" in t for t in body) and any("buldular.[3] Aydınlanmanın" in t for t in body)
    assert body[-3] == "[1] Gregory, Scientific Materialism, s. 184."
    assert body[-2].startswith("[2] Corsi") and body[-1] == "[3] Zürcher, The Young Turks, s. 283."


def test_finish_layout_epigraph_and_perde():
    perde = page([], perde=True)
    ch = Chapter("I. BÖLÜM DEHŞETİN SINIRLARI", [
        Block("para", "(Muhammed Sancar Yiğit Bey)", [5]),
        Block("italic", "Bir mıh bir nalı kurtarır, bir nal bir atı kurtarır.", [7]),
        Block("right", "Anonim", [7]),
        Block("para", "Sislerin arasından avlarını pusulayan bir grup aslan kadar kararlıydık.", [7]),
        Block("italic", "Ortadaki alıntı epigraf değildir.", [8])])
    ms = Manuscript("K", chapters=[ch])
    _finish_layout(ms, {5: perde, 7: page([]), 8: page([])}, {})
    # Bölüm perde sayfasından yeniden kesilir: perde sayfasındaki ilk satır bölüm adı, alt satır perde altı.
    assert [(c.title, c.kind) for c in ms.chapters] == [("I. BÖLÜM DEHŞETİN SINIRLARI", "perde")]
    assert [b.kind for b in ms.chapters[0].blocks] == ["perde_alti", "epigraph", "epigraph", "para", "italic"]


def test_section_heading_and_ornament_break():
    sub = [ln("II", 223, 235, size=14)]
    assert L.kind_of(sub, 89, 372, 12)[0] == "subhead"
    pg = page([ln("Sonu.", y=100), ln("Yeni sahne başlıyor.", y=145)])
    assert L.para_lines(pg, "II") == []
    pg2 = page([ln("II", 223, 235, y=80, size=14)])
    assert L.para_lines(pg2, "II")[0].text == "II"                               # kısa paragraf satırla eşleşir


def test_print_style_notes_are_superscript_at_chapter_end():
    """Stüdyonun basılı tasarımı: üst başlık ve dipnot gövdeden çıkar, gönderme üst simge rakam, notlar bölüm sonunda
    «¹ metin»; tür yeni dizgi türü değil (para)."""
    p20 = page([ln("uyumludur.18 Benzer bir şekilde", sup=["18"])],
               notes=[["18", "Gregory, Scientific Materialism, s. 184."]], heads=[L.fold("DARWIN VE OSMANLILAR")])
    paras = [(20, "DARWIN VE OSMANLILAR"), (20, "uyumludur.18 Benzer bir şekilde"),
             (20, "18 Gregory, Scientific Materialism, s. 184.")]
    out, notes = _apply_layout(paras, {20: p20}, tables=False)
    ms = Manuscript("K", chapters=[Chapter(h, b) for h, b in normalize([(p, t) for p, t, _ in out], None)])
    _finish_layout(ms, {20: p20}, notes, print_style=True)
    body = [b.text for c in ms.chapters for b in c.blocks]
    assert body == ["uyumludur.¹ Benzer bir şekilde", "¹ Gregory, Scientific Materialism, s. 184."]
