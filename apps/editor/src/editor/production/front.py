"""Ön sayfalar: künye ve yazar tanıtımı.

Künye = yayınevi sabitleri (EDITOR_PUBLISHER_JSON dosyası; adres, sertifika…) + kitap alanları (CRM) +
bu baskının kişileri. Kaynağı olmayan alan uydurulmaz, «—» basılır ve ön kontrol (`MISSING`) basımı
durdurur. Resimler üretildiği için çizer satırı özgün kitabın çizerini değil, resmin kaynağını yazar.

Yazar tanıtımı, okunmuş kitabın hikâye dışı sayfalarından ana modelle bulunur; metin birebir
eşleşmezse kullanılmaz (tanıtım sayfası «—» ile kalır).
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

from ..prompts import render
from .manuscript import Manuscript

MISSING = "—"
IMAGE_CREDIT = "Yapay zekâ ile üretilmiştir (Qwen-Image-2.1, NanobaseAI Editör)"
BIO_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["bios"], "properties": {
    "bios": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                                        "required": ["name", "text"],
                                        "properties": {"name": {"type": "string"}, "text": {"type": "string"}}}}}}


def publisher() -> dict:
    path = os.environ.get("EDITOR_PUBLISHER_JSON")
    return json.loads(Path(path).read_text()) if path and Path(path).exists() else {}


def kunye(ms: Manuscript, pub: dict, edition: dict | None = None) -> list[list[str]]:
    e = edition or {}
    rows = [
        ["Kitap", ms.title], ["Yazar", ms.author or MISSING],
        ["Resimler", IMAGE_CREDIT],
        ["Dizi", ms.meta.get("SERIES") or MISSING],
        ["Yayın Yönetmeni", e.get("yayin_yonetmeni") or MISSING], ["Editör", e.get("editor") or MISSING],
        ["Baskı", e.get("baski") or MISSING],
        ["ISBN", ms.meta.get("ISBN") or MISSING],
        ["", ""],
        [pub.get("name") or ms.meta.get("PUBLISHER") or MISSING, ""],
        ["Adres", pub.get("address") or MISSING], ["Telefon", pub.get("phone") or MISSING],
        ["E-posta", pub.get("email") or MISSING], ["Sertifika No", pub.get("certificate") or MISSING],
        ["", ""],
        ["Baskı ve Cilt", e.get("matbaa") or MISSING],
        ["", ""],
        ["", ""],
    ]
    rows.append([f"© {e.get('telif_yili') or MISSING}", pub.get("rights") or MISSING])
    return rows


def missing(rows: list[list[str]]) -> list[str]:
    return [r[0] for r in rows if MISSING in (r[0], r[1]) and r[0]]


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", s).strip().casefold()


async def bios(ms: Manuscript, llm) -> list[dict]:
    pages = ms.source.get("non_story_pages") or []
    gid = ms.source.get("generation_id")
    if not (pages and gid and ms.author):
        return [{"name": ms.author or MISSING, "text": MISSING}]
    from .. import db
    rows = db.all_rows("SELECT page_no, text FROM ed.paragraph WHERE generation_id=%s AND page_no = ANY(%s) "
                       "ORDER BY page_no, idx", gid, pages)
    src = "\n\n".join(r["text"] for r in rows)
    ref, prompt = render("production_bios", pages=src, names=ms.author)
    out, _ = await llm.chat("book-director", [{"role": "user", "content": prompt}], prompt=ref,
                            schema=BIO_SCHEMA, max_tokens=2000, thinking=False)
    found = []
    for b in out["bios"]:
        paras = [p for p in b["text"].split("\n\n") if p.strip()]
        if b["name"] in ms.author and paras and all(_norm(p) in _norm(src) for p in paras):
            found.append({"name": b["name"], "text": "\n\n".join(paras)})
    return found or [{"name": ms.author, "text": MISSING}]
