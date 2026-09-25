"""Ön sayfalar: künye ve yazar tanıtımı.

Künye kaynağı, kitabın kendi künye sayfasıdır (okunmuş kitabın hikâye dışı sayfaları); Word ile gelen
kitapta aynı yayınevinin en son okunmuş künyesi. Alanlar ana modelle çıkarılır, her değerin alıntısı
kaynak metinde birebir aranır; bulunmayan değer kullanılmaz. Kaynağı olmayan alan uydurulmaz, «—»
basılır, ön kontrol (`MISSING`) basımı durdurur; ekranda elle tamamlanır (`set_fields`).

Başka kitabın künyesinden yalnız yayınevine ait alanlar (adres, sertifika, matbaa…) alınır; kişi
alanları (yayın yönetmeni, editör) yalnız kitabın kendi künyesinden gelir. Baskı bilgisi yeni baskıya
aittir, her zaman elle girilir. Resimler ve tasarım bu sistemin işidir; künyede öyle yazılır, özgün
kitabın çizeri ya da tasarımcısı yazılmaz.

Yazar tanıtımı hikâye dışı sayfalardan aynı yolla bulunur; metin birebir eşleşmezse kullanılmaz.
"""

from __future__ import annotations

import re

from ..prompts import render
from .manuscript import Manuscript

MISSING = "—"
IMAGE_CREDIT = "Yapay zekâ ile üretilmiştir (Zeki AI)"   # model/ürün adı ekrana ve kitaba yazılmaz
DESIGN_CREDIT = "NanobaseAI Editör · Kitap Tasarım Stüdyosu"
PUBLISHER_FIELDS = ("YAYINEVI", "ADRES", "TELEFON", "EPOSTA", "SERTIFIKA", "MATBAA", "MATBAA_SERTIFIKA",
                    "MATBAA_ADRES", "TELIF")
PERSON_FIELDS = ("YAYIN_YONETMENI", "PROJE_EDITORU", "EDITOR", "DIZI")
KUNYE_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["fields"], "properties": {
    "fields": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                          "required": ["field", "value", "quote"],
                                          "properties": {"field": {"type": "string", "enum": list(PUBLISHER_FIELDS + PERSON_FIELDS)},
                                                         "value": {"type": "string"}, "quote": {"type": "string"}}}}}}
BIO_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["bios"], "properties": {
    "bios": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                        "required": ["name", "text"],
                                        "properties": {"name": {"type": "string"}, "text": {"type": "string"}}}}}}


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().casefold()


def _front_text(generation_id: str) -> str:
    from .. import db
    pages = [r["page_no"] for r in db.all_rows(
        "SELECT DISTINCT ON (page_no) page_no, role FROM ed.page_role WHERE generation_id=%s "
        "ORDER BY page_no, (source='editor') DESC", generation_id) if r["role"] == "NON_STORY"]
    if not pages:
        return ""
    rows = db.all_rows("SELECT text FROM ed.paragraph WHERE generation_id=%s AND page_no = ANY(%s) ORDER BY page_no, idx",
                       generation_id, pages)
    return "\n\n".join(r["text"] for r in rows)


def _latest_publisher_text(publisher: str | None) -> tuple[str, str | None]:
    """Word ile gelen kitap için: yayınevinin adı geçen, sertifika yazan en yeni okunmuş künye."""
    from .. import db
    rows = db.all_rows(
        "SELECT p.generation_id, string_agg(p.text, E'\\n\\n' ORDER BY p.page_no, p.idx) AS t, max(g.created_at) AS at "
        "FROM ed.paragraph p JOIN ed.generation g ON g.id=p.generation_id WHERE p.page_no <= 4 "
        "GROUP BY p.generation_id HAVING string_agg(p.text, ' ') ILIKE '%%sertifika%%' ORDER BY at DESC LIMIT 40")
    key = (publisher or "").casefold()
    for r in rows:
        if not key or key.split()[0] in r["t"].casefold():
            return r["t"], str(r["generation_id"])
    return "", None


async def kunye_fields(ms: Manuscript, llm) -> dict:
    """{alan: {value, quote, source}}; kaynağı kitabın kendi künyesi ya da (yalnız yayınevi alanları)
    yayınevinin en son künyesi."""
    own_gid = ms.source.get("generation_id")
    own = _front_text(own_gid) if own_gid else ""
    found: dict = {}
    sources = [(own, own_gid, True)]
    if not own or "sertifika" not in own.casefold():
        text, gid = _latest_publisher_text(ms.meta.get("PUBLISHER"))
        sources.append((text, gid, False))
    for text, gid, is_own in sources:
        if not text:
            continue
        ref, prompt = render("production_kunye", pages=text[:20000])
        out, _ = await llm.chat("book-director", [{"role": "user", "content": prompt}], prompt=ref,
                                schema=KUNYE_SCHEMA, max_tokens=2500, thinking=False)
        for f in out["fields"]:
            if f["field"] in found or (not is_own and f["field"] in PERSON_FIELDS):
                continue
            if _norm(f["quote"]) in _norm(text) and _norm(f["value"]) in _norm(f["quote"]):
                found[f["field"]] = {"value": f["value"].strip(), "quote": f["quote"],
                                     "source": "kitabın künyesi" if is_own else f"yayınevinin son künyesi ({gid})"}
    return found


def kunye(ms: Manuscript, f: dict, manual: dict | None = None) -> list[list[str]]:
    """Künye satırları [etiket, değer]; `manual` ekranda elle girilen değerler (etiket → değer)."""
    m = manual or {}

    def v(label, key=None, fallback=None):
        return m.get(label) or (f.get(key, {}).get("value") if key else None) or fallback or MISSING

    rows = [
        ["Kitap", ms.title], ["Yazar", ms.author or MISSING],
        ["Resimler", IMAGE_CREDIT], ["Kapak ve İç Tasarım", DESIGN_CREDIT],
        ["Dizi", v("Dizi", "DIZI", ms.meta.get("SERIES"))],
        ["Yayın Yönetmeni", v("Yayın Yönetmeni", "YAYIN_YONETMENI")],
        ["Proje Editörü", v("Proje Editörü", "PROJE_EDITORU")],
        ["Editör", v("Editör", "EDITOR")],
        ["Baskı", v("Baskı")],
        ["ISBN", ms.meta.get("ISBN") or v("ISBN")],
        ["", ""],
        ["Yayınevi", v("Yayınevi", "YAYINEVI", ms.meta.get("PUBLISHER"))],
        ["Adres", v("Adres", "ADRES")], ["Telefon", v("Telefon", "TELEFON")],
        ["E-posta", v("E-posta", "EPOSTA")], ["Sertifika No", v("Sertifika No", "SERTIFIKA")],
        ["", ""],
        ["Baskı ve Cilt", v("Baskı ve Cilt", "MATBAA")],
        ["Matbaa Sertifika No", v("Matbaa Sertifika No", "MATBAA_SERTIFIKA")],
        ["Matbaa Adresi", v("Matbaa Adresi", "MATBAA_ADRES")],
        ["", ""],
        ["Telif", v("Telif", "TELIF")],
    ]
    return rows


# Ekranda düzenlenebilen etiketler (kitap adı, yazar, resim/tasarım satırları sistemden gelir).
EDITABLE = ("Dizi", "Yayın Yönetmeni", "Proje Editörü", "Editör", "Baskı", "ISBN", "Yayınevi", "Adres", "Telefon",
            "E-posta", "Sertifika No", "Baskı ve Cilt", "Matbaa Sertifika No", "Matbaa Adresi", "Telif")


def missing(rows: list[list[str]]) -> list[str]:
    return [label for label, value in rows if label and value == MISSING]


async def bios(ms: Manuscript, llm) -> list[dict]:
    gid = ms.source.get("generation_id")
    src = _front_text(gid) if gid else ""
    if not (src and ms.author):
        return [{"name": ms.author or MISSING, "text": MISSING}]
    ref, prompt = render("production_bios", pages=src, names=ms.author)
    out, _ = await llm.chat("book-director", [{"role": "user", "content": prompt}], prompt=ref,
                            schema=BIO_SCHEMA, max_tokens=2000, thinking=False)
    found = []
    for b in out["bios"]:
        paras = [p for p in b["text"].split("\n\n") if p.strip()]
        if b["name"] in ms.author and paras and all(_norm(p) in _norm(src) for p in paras):
            found.append({"name": b["name"], "text": "\n\n".join(paras)})
    return found or [{"name": ms.author, "text": MISSING}]
