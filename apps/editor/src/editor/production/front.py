"""Ön sayfalar: künye ve yazar tanıtımı.

Künye kaynağı, kitabın kendi künye sayfasıdır (okunmuş kitabın hikâye dışı sayfaları); Word ile gelen
kitapta aynı yayınevinin en son okunmuş künyesi. Alanlar ana modelle çıkarılır, her değerin alıntısı
kaynak metinde birebir aranır; bulunmayan değer kullanılmaz. Kaynağı olmayan alan uydurulmaz, «—»
basılır, ön kontrol (`MISSING`) basımı durdurur; ekranda elle tamamlanır (`set_fields`).

Başka kitabın künyesinden yalnız yayınevine ait alanlar (adres, sertifika, matbaa…) alınır; kitaba ait
alanlar (yayın yönetmeni, editör, dizi, telif) yalnız kitabın kendi künyesinden gelir — telif cümlesi hak
sahibini (yazar/özgün yayıncı) adlandırır, başka kitabınki bu kitaba yazılmaz. Baskı bilgisi yeni baskıya
aittir, her zaman elle girilir. Resimler ve tasarım bu sistemin işidir; künyede öyle yazılır, özgün
kitabın çizeri ya da tasarımcısı yazılmaz; ürün/teknoloji adı yazılmaz, «ZEKİ AI» yazılır.

Yazar tanıtımı hikâye dışı sayfalardan aynı yolla bulunur; metin birebir eşleşmezse kullanılmaz.
"""

from __future__ import annotations

import re

from ..prompts import render
from .manuscript import Manuscript

MISSING = "—"
IMAGE_CREDIT = "Yapay zekâ ile üretilmiştir (ZEKİ AI)"   # model/ürün adı ekrana ve kitaba yazılmaz
DESIGN_CREDIT = "Yapay zekâ ile tasarlanmıştır (ZEKİ AI)"   # Resimler satırıyla aynı dil; ürün adı basılmaz
OWN_SOURCE = "kitabın künyesi"
PUBLISHER_FIELDS = ("YAYINEVI", "ADRES", "TELEFON", "EPOSTA", "SERTIFIKA", "MATBAA", "MATBAA_SERTIFIKA",
                    "MATBAA_ADRES")
# Kitaba ait alanlar: yalnız kitabın kendi künyesinden. Başka kitabın künyesinden gelmiş (eski işlerde kayıtlı)
# değer de basılmaz (`usable`).
PERSON_FIELDS = ("YAYIN_YONETMENI", "PROJE_EDITORU", "EDITOR", "DIZI", "TELIF", "CEVIRI", "DESTEK")
# Yalnız kitapta varsa basılan satırlar: çeviri kitapta çevirmen, destekli yayında destek cümlesi. Yoksa satır hiç
# yoktur (telif kitabında «Çeviri: —» basılmaz, eksik sayılmaz).
OPTIONAL = (("Çeviri", "CEVIRI"), ("Destek", "DESTEK"))
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


#: Yayınevi künyesinde «BÜYÜK HARFLİ ETİKET değer» satırları (kuralla, tam metin): model uzun değeri (telif cümlesi)
#: yarıda kesebiliyordu («…anlaşma kapsamında Ti»).
RULE_LABELS = {"YAYIN YÖNETMENİ": "YAYIN_YONETMENI", "PROJE EDİTÖRÜ": "PROJE_EDITORU", "EDİTÖR": "EDITOR",
               "EDİTÖRLER": "EDITOR", "ÇEVİRİ": "CEVIRI", "ÇEVİREN": "CEVIRI", "YAYIN HAKLARI": "TELIF"}


def rule_fields(text: str) -> dict:
    """Künye metninden etiketli satırlar {alan: {value, quote}}; değer satırın kendisinden, kısaltılmadan."""
    from .epub_source import split_label
    out: dict = {}
    for t in (" ".join(x.split()) for x in re.split(r"\n+", text or "") if x.strip()):
        label, value = split_label(t)
        field = RULE_LABELS.get((label or "").upper())
        if field and value and field not in out:
            out[field] = {"value": value, "quote": t}
    return out


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
                                     "source": OWN_SOURCE if is_own else f"yayınevinin son künyesi ({gid})"}
    return merge_rule_fields(found, own_kunye_text(ms) or own)


def own_kunye_text(ms: Manuscript) -> str:
    """Okunmuş kitabın künye sayfalarının metni, satır satır (baskı kuralının «künye» dediği sayfalar; e-kitabın
    basılı künyesiyle aynı kaynak). Sayfa rolü (`_front_text`) künye sayfasını kaçırabiliyor."""
    from .epub_compare import source_pages
    from .epub_source import kunye_pages
    src = ms.source or {}
    if not src.get("generation_id"):
        return ""
    pages = source_pages(src["generation_id"])
    keep = set(kunye_pages({**src, "title": ms.title}, pages))
    return "\n".join(t for p, text in pages if p in keep for t in text.split("\n") if t.strip())


def merge_rule_fields(fields: dict, own_text: str) -> dict:
    """Kitabın kendi künyesinde etiketli satır varsa onun tam metni kazanır: model alanı bulamadıysa ya da modelin
    değeri onun kısaltılmışıysa. Başka kitabın künyesine bakılmaz."""
    out = dict(fields)
    for field, r in rule_fields(own_text).items():
        cur = (out.get(field) or {}).get("value") or ""
        if not cur or (len(r["value"]) > len(cur) and _norm(cur)[:40] in _norm(r["value"])):
            out[field] = {**r, "source": OWN_SOURCE}
    return out


def usable(f: dict) -> dict:
    """Basılabilir alanlar: kitaba ait alan (`PERSON_FIELDS`) yalnız kitabın kendi künyesinden okunduysa kalır.
    Eski işlerin front.json'ında başka kitabın künyesinden alınmış telif vb. kayıtlı olabilir; yeniden dizilince
    düşer, «—» basılır."""
    return {k: v for k, v in (f or {}).items()
            if k not in PERSON_FIELDS or (v or {}).get("source") == OWN_SOURCE}


def kunye(ms: Manuscript, f: dict, manual: dict | None = None) -> list[list[str]]:
    """Künye satırları [etiket, değer]; `manual` ekranda elle girilen değerler (etiket → değer). Kitap adı ve yazar
    el yazmasından (editörün düzeltmesi oraya yazılır); editör yazarı bilerek boş bıraktıysa «Yazar» satırı yok."""
    from .manuscript import author_cleared
    m = manual or {}
    f = usable(f)

    def v(label, key=None, fallback=None):
        return m.get(label) or (f.get(key, {}).get("value") if key else None) or fallback or MISSING

    author = [] if not ms.author and author_cleared(ms.source or {}) else [["Yazar", ms.author or MISSING]]
    rows = [
        ["Kitap", ms.title], *author,
        ["Resimler", IMAGE_CREDIT], ["Kapak ve İç Tasarım", DESIGN_CREDIT],
        ["Dizi", v("Dizi", "DIZI", ms.meta.get("SERIES"))],
        ["Yayın Yönetmeni", v("Yayın Yönetmeni", "YAYIN_YONETMENI")],
        ["Proje Editörü", v("Proje Editörü", "PROJE_EDITORU")],
        ["Editör", v("Editör", "EDITOR")],
        *[[label, v(label, key)] for label, key in OPTIONAL[:1] if m.get(label) or f.get(key)],
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
        *[[label, v(label, key)] for label, key in OPTIONAL[1:] if m.get(label) or f.get(key)],
    ]
    return rows


# Ekranda düzenlenebilen etiketler. Kitap adı ve yazar da düzenlenir ama künye alanı olarak değil: el yazmasının
# kendisi düzeltilir (studio.set_kunye `book`); resim/tasarım satırları sistemindir.
EDITABLE =("Dizi", "Yayın Yönetmeni", "Proje Editörü", "Editör", "Çeviri", "Baskı", "ISBN", "Yayınevi", "Adres", "Telefon",
            "E-posta", "Sertifika No", "Baskı ve Cilt", "Matbaa Sertifika No", "Matbaa Adresi", "Telif", "Destek")


def bios_for_author(bios: list[dict], author: str | None) -> list[dict]:
    """Yazar değişince tanıtım sayfası: kitabın kendi künyesinden bulunmuş tanıtımlardan yalnız yeni yazar adında
    geçen kişininki kalır; hiçbiri kalmazsa yer tutucu yeni adla (tanıtım uydurulmaz)."""
    keep = [b for b in bios or [] if author and b.get("text") not in (None, "", MISSING)
            and b.get("name") and b["name"] in author]
    return keep or [{"name": author or MISSING, "text": MISSING}]


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
