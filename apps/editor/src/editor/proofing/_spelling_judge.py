"""The two model questions of the spelling checks, both closed-set (Llm.choose: one token,
read as probabilities) and both asked in the two answer orders and averaged, so the letter
the model prefers does not decide.

1. `printed`: what does the PAGE IMAGE show - the form our text has, or the proposed one?
   Checkable against the page: the answer is a reading of pixels, not an opinion. It
   removes readings that are not the book: OCR slips ("kitapşık" read for a printed
   "kitapçık") and text-layer interleaving on artwork.
2. `is_error`: given the sentence, is the form a slip or the author's choice (sound
   imitation, dialect, invented name, reduplication)? Asked only for candidates the
   deterministic rules could not settle, never to invent corrections: the candidate and its
   suggestion come from the rules and the dictionaries.
"""

from __future__ import annotations

from pathlib import Path

from ..llm import Llm, image_part

MODEL = "book-director"
# a candidate is kept when the averaged probability is at least this; 0.5 is the argmax of a
# two-way choice, not a tuned value
KEEP = 0.5


def _page_png(book_version_id: str, page_no: int) -> bytes:
    from ..document import render_page
    return Path(render_page(book_version_id, page_no)["path"]).read_bytes()


async def _ab(llm: Llm, content_for, a: str, b: str, pages: list[int]) -> tuple[float, list[int]]:
    """P(first option `a` is right), averaged over both orders."""
    p1, c1 = await llm.choose(MODEL, [{"role": "user", "content": content_for(a, b)}], ["A", "B"], pages=pages)
    p2, c2 = await llm.choose(MODEL, [{"role": "user", "content": content_for(b, a)}], ["A", "B"], pages=pages)
    return (p1["A"] + p2["B"]) / 2, [c1, c2]


async def printed(llm: Llm, book_version_id: str, page_no: int, shown: str, alternatives: list[str]) -> dict:
    """P(the page shows `shown`) against every proposed alternative at once (a letter each),
    asked in forward and reversed option order and averaged. With a single wrong-looking
    alternative the model picks the lesser evil ("Hepsı" over "Heps" when "Hepsi" is
    printed - measured), so all dictionary proposals are offered together. Without any
    alternative: a yes/no in both polarities."""
    png = _page_png(book_version_id, page_no)
    alts = [a for a in dict.fromkeys(alternatives) if a and a != shown]
    if alts:
        opts = [shown] + alts
        letters = "ABCDEFG"[:len(opts)]
        probs = []
        calls = []
        for order in (opts, list(reversed(opts))):
            body = ("Bu kitap sayfasının görüntüsüne bak. Basılı metinde aşağıdakilerden hangisi harfi "
                    "harfine, noktalama ve büyük/küçük harf dahil aynen yazıyor?\n"
                    + "\n".join(f"{l}) {o}" for l, o in zip(letters, order))
                    + f"\nYalnız harfi yaz ({', '.join(letters)}).")
            p, c = await llm.choose(MODEL, [{"role": "user", "content": [image_part(png), {"type": "text", "text": body}]}],
                                    list(letters), pages=[page_no])
            probs.append(p[letters[order.index(shown)]])
            calls.append(c)
        return {"p_printed": round(sum(probs) / 2, 3), "calls": calls, "options": len(opts)}

    def content(x, y):
        return [image_part(png), {"type": "text", "text":
                "Bu kitap sayfasının görüntüsüne bak. Şu ifade basılı metinde harfi harfine aynen "
                f"geçiyor mu?\n«{shown}»\nA) {x}\nB) {y}\nYalnız A ya da B yaz."}]
    p, calls = await _ab(llm, content, "Evet, aynen böyle basılmış.", "Hayır, basılı hâli farklı.", [page_no])
    return {"p_printed": round(p, 3), "calls": calls}


ERROR = "Yazım/dizgi hatası: düzeltilmeli."
CHOICE = ("Bilinçli ya da doğru kullanım (ses taklidi, uzatma, ağız ya da konuşma dili, çocuk dili, "
          "uydurma sözcük ya da ad, tekerleme, yabancı sözcük, ikileme).")


async def is_error(llm: Llm, page_no: int, sentence: str, question: str) -> dict:
    def content(x, y):
        return ("Bir çocuk kitabının son okumasını yapan deneyimli bir editörsün. TDK yazım "
                "kurallarına göre değerlendir; yazarın bilinçli üslup tercihlerini hata sayma.\n\n"
                f"Cümle: «{sentence}»\n{question}\n\nA) {x}\nB) {y}\nYalnız A ya da B yaz.")
    p, calls = await _ab(llm, content, ERROR, CHOICE, [page_no])
    return {"p_error": round(p, 3), "calls": calls}
