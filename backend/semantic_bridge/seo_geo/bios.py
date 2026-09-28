"""Yazar biyografileri: CRM özgeçmişinden yazar sayfası için biyografi taslağı (ZEKİ AI yazar, insan onaylar).

Neden: "bu yazar kim?" sorusunda Google ve yapay zekâ cevap motorları yazarı anlatan, kaynağı belli bir sayfa arar;
T-soft yazar sayfalarında tanıtım metni yok (authors.py güven sinyali "bio").

Kaynak (2026-09-28 canlı CRM ölçümü, yalnız okuma):
- Yazar ↔ kitap bağı `new_kitapBase.new_yazarid` DEĞİL (satıştaki kitaplarda boş). Bağ `new_eserkatilimBase`:
  `new_Kitap` → kitap, `new_Katilimsaglayan` → kişi (`ContactBase`), `new_katilimciTipi` → `new_katilimcitipiBase`
  (adı Yazar, Çizer, Editör, Tercüme …). Yalnız adı "Yazar" olan tür alınır; tür kimliği tablodan okunur, kodda
  GUID yok. `new_OncelikliYazar` ana yazar işaretidir.
- Özgeçmiş: `ContactBase.new_ozgecmis`, `new_kisaozgecmis`, `new_Biyografi` (HTML olabilir → düz metin).
- Saklanan yalnız: kişi kimliği, ad, özgeçmiş metni, kitap barkodları. Telefon, e-posta, adres okunmaz, saklanmaz.

Sıra: T-soft'ta satıştaki kitaplarının toplam satışı. CRM'de özgeçmişi olmayan yazar taslak almaz; ekranda
"özgeçmiş yok — CRM'e girilmeli" iş maddesi olarak görünür.

Taslak: ZEKİ AI (LLM kapısı, `llm_for("seo", …)`) 120–220 kelimelik tarafsız, üçüncü şahıs biyografi ve tek cümlelik
özet (meta açıklama sınırları) yazar. "Timaş'tan çıkan kitapları" listesi ve Person JSON-LD'yi kod kurar (model
değil). Gerçeklik denetimi (`propose.unsupported`) özgeçmişte ve kitap adlarında geçmeyen sayı/özel adı işaretler.
Karar yalnız kayıttır; T-soft'a ve CRM'e yazılmaz, sayfaya site yöneticisi dışa aktarılan HTML ile elle girer.

T-soft yazar sayfası eşleşmesi: CRM kişi adı ↔ T-soft ürününün `Model` adı, Türkçe harf katlamasıyla ("İlber
Ortaylı" = "ILBER ORTAYLI" = "Prof. Dr. İlber Ortaylı"). Eşleşmeyen yazar ayrıca sayılır ve süzülebilir.

Gece: önce CRM okuması, sonra taslağı olmayan en çok satan yazarlar için süre bütçesi içinde (BATCH) taslak.
"""
from __future__ import annotations

import html as html_mod
import json
import logging
import os
import re
import threading
import time
import uuid
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa
from fastapi import HTTPException, Request
from pydantic import BaseModel, Field

from . import crm, propose, rules
from .entity import ENTITY, fold, split_authors
from .store import _md, dumps, iso, loads, now

log = logging.getLogger("semantic.seo_geo.bios")

BIOS_SRC = sa.Table(
    "semantic_seo_bios_src", _md,  # CRM yazar özgeçmişi (yalnız ad + metin + kitap barkodları). İletişim bilgisi yok.
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("author_key", sa.String(40), primary_key=True),   # aynı adlı kişi kayıtlarının en küçük ContactId'si
    sa.Column("name", sa.String(300), nullable=False),
    sa.Column("bio_long", sa.Text),                              # new_ozgecmis
    sa.Column("bio_short", sa.Text),                             # new_kisaozgecmis
    sa.Column("biography", sa.Text),                             # new_Biyografi
    sa.Column("books_json", sa.Text, nullable=False),            # [{"ean": "...", "primary": bool}]
    sa.Column("synced_at", sa.DateTime(timezone=True), nullable=False),
)
BIOS = sa.Table(
    "semantic_seo_bios", _md,  # biyografi taslağı → insan kararı. Hiçbir yere gönderilmez.
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("author_key", sa.String(40), nullable=False, index=True),
    sa.Column("name", sa.String(300)),
    sa.Column("status", sa.String(16), nullable=False),        # hazir | onaylandi | reddedildi
    sa.Column("fields_json", sa.Text, nullable=False),          # {"Bio": "...", "Summary": "..."}
    sa.Column("books_json", sa.Text, nullable=False),           # taslak anındaki satıştaki kitaplar (satışa göre)
    sa.Column("source_json", sa.Text, nullable=False),          # taslak anındaki özgeçmiş (gerçeklik denetimi kaynağı)
    sa.Column("jsonld_json", sa.Text, nullable=False),          # kodla kurulan Person
    sa.Column("unsupported_json", sa.Text, nullable=False),     # kaynakta geçmeyen sayı/özel adlar
    sa.Column("model", sa.String(120)),
    sa.Column("created_by", sa.String(120)),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("decided_by", sa.String(120)),
    sa.Column("decided_at", sa.DateTime(timezone=True)),
    sa.Column("note", sa.String(1000)),
)
STATUSES = ("hazir", "onaylandi", "reddedildi")
#: Liste süzgeçleri: taslak durumları + kaynak/eşleşme durumları.
FILTERS = STATUSES + ("kaynak_yok", "taslak_yok", "eslesmedi")
#: Özgeçmiş bu kadar karakterden kısaysa kaynak sayılmaz (authors.py BIO_MIN ile aynı ölçü). `SEO_BIO_MIN_CHARS`.
BIO_MIN = 200
BIO_WORDS = (120, 220)
#: Katılımcı türünün adı (katlanmış). Tür kimliği CRM tablosundan bu adla bulunur.
AUTHOR_TYPE = "yazar"
NO_BIO_TASK = "Özgeçmiş yok — CRM'e girilmeli"
_ready: set[int] = set()
_ready_lock = threading.Lock()


def ensure(engine: sa.engine.Engine) -> None:
    with _ready_lock:
        if id(engine) in _ready:
            return
        # Kimlik önbelleği (sameAs) entity.py'nindir; store.ensure o modül yüklenmeden koştuysa burada kurulur.
        for t in (BIOS_SRC, BIOS, ENTITY):
            t.create(engine, checkfirst=True)
        _ready.add(id(engine))


# ------------------------------------------------------------------ ad eşleşmesi
#: Adın başındaki unvanlar eşleşmede yok sayılır ("Prof. Dr. İlber Ortaylı" = "İlber Ortaylı").
HONORIFICS = {"prof", "dr", "doc", "yrd", "ars", "gor", "ogr", "uyesi", "uzm", "av", "op", "hafiz", "sn"}


def name_key(name: Any) -> str:
    """Türkçe harf katlaması + baştaki unvanlar atılır: "ŞULE GÜRBÜZ", "Şule Gürbüz", "sule gurbuz" aynı anahtar."""
    tokens = fold(rules.text_of(name)).split()
    while len(tokens) > 1 and tokens[0] in HONORIFICS:
        tokens = tokens[1:]
    return " ".join(tokens)


def model_keys(model: Any) -> set[str]:
    """T-soft `Model` alanındaki (bir ya da birden çok) yazarın anahtarları."""
    return {k for k in (name_key(n) for n in split_authors(model)) if k}


# ------------------------------------------------------------------ CRM okuması (yalnız SELECT)
_GUID = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$")


def type_sql(p: str) -> str:
    return f"SELECT CAST(t.new_katilimcitipiId AS nvarchar(40)) AS id, t.new_name AS name FROM {p}new_katilimcitipiBase t"


def participation_sql(p: str) -> str:
    """Etkin kitap kartlarındaki bütün katılımlar (tür kimliğiyle); yazar süzgeci Python'da, tür adıyla."""
    return (
        "SELECT CAST(e.new_Katilimsaglayan AS nvarchar(40)) AS contact_id, CAST(e.new_katilimciTipi AS nvarchar(40)) AS type_id,"
        " k.new_ean13 AS ean, CAST(ISNULL(e.new_OncelikliYazar, 0) AS int) AS is_primary"
        f" FROM {p}new_eserkatilimBase e JOIN {p}new_kitapBase k ON k.new_kitapId = e.new_Kitap"
        " WHERE e.statecode = 0 AND k.statecode = 0 AND k.new_ean13 IS NOT NULL AND e.new_Katilimsaglayan IS NOT NULL"
    )


def contact_sql(p: str, type_ids: Iterable[str]) -> str:
    """Yazar türünde katılımı olan kişilerin yalnız adı ve özgeçmiş alanları. İletişim alanları seçilmez."""
    ids = sorted({i for i in type_ids if _GUID.match(i or "")})
    if not ids:
        raise ValueError("CRM'de 'Yazar' katılımcı türü bulunamadı.")
    inlist = ", ".join(f"'{i}'" for i in ids)
    return (
        "SELECT CAST(c.ContactId AS nvarchar(40)) AS contact_id, c.FullName AS name,"
        " CAST(c.new_ozgecmis AS nvarchar(max)) AS bio_long, CAST(c.new_kisaozgecmis AS nvarchar(max)) AS bio_short,"
        " CAST(c.new_Biyografi AS nvarchar(max)) AS biography"
        f" FROM {p}ContactBase c WHERE c.ContactId IN (SELECT e.new_Katilimsaglayan FROM {p}new_eserkatilimBase e"
        f" WHERE e.statecode = 0 AND e.new_katilimciTipi IN ({inlist}))"
    )


def author_type_ids(type_rows: Iterable[dict[str, Any]]) -> set[str]:
    """Adı "Yazar" olan katılımcı türleri (Çizer, Editör, Uzman Editör, Tercüme … değil)."""
    return {str(r["id"]).upper() for r in type_rows if r.get("id") and fold(r.get("name")) == AUTHOR_TYPE}


def author_books(rows: Iterable[dict[str, Any]], type_ids: set[str]) -> dict[str, list[dict[str, Any]]]:
    """Kişi → yazarı olduğu kitapların barkodları. Yazar dışındaki katılım (çizer, çevirmen …) alınmaz."""
    out: dict[str, dict[str, dict[str, Any]]] = {}
    for r in rows:
        if str(r.get("type_id") or "").upper() not in type_ids:
            continue
        ean = crm.ean_key(r.get("ean"))
        cid = str(r.get("contact_id") or "").upper()
        if len(ean) < 8 or not cid:
            continue
        books = out.setdefault(cid, {})
        prev = books.get(ean)
        books[ean] = {"ean": ean, "primary": bool(r.get("is_primary")) or bool(prev and prev["primary"])}
    return {cid: list(b.values()) for cid, b in out.items()}


#: CRM kişi satırından alınan alanlar. Başka hiçbir alan (telefon, e-posta, adres …) kayda geçmez.
SOURCE_FIELDS = ("contact_id", "name", "bio_long", "bio_short", "biography")


def source_record(row: dict[str, Any], books: list[dict[str, Any]]) -> dict[str, Any]:
    """Kişi satırı → saklanacak kayıt: yalnız kimlik, ad, özgeçmiş metinleri (HTML'siz), kitap barkodları."""
    r = {k: row.get(k) for k in SOURCE_FIELDS}
    return {"contactId": str(r["contact_id"] or "").lower().strip("{}"), "name": crm.clean(r["name"]) or "",
            "bioLong": plain(r["bio_long"]), "bioShort": plain(r["bio_short"]), "biography": plain(r["biography"]),
            "books": books}


def merge_same_name(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """CRM'de aynı adlı birden çok kişi kaydı (mükerrer kart) tek yazar sayılır: anahtar en küçük kimlik, metinler
    ve kitaplar birleşir."""
    groups: dict[str, dict[str, Any]] = {}
    for r in sorted(records, key=lambda x: x["contactId"]):
        k = name_key(r["name"])
        if not k:
            continue
        g = groups.get(k)
        if g is None:
            groups[k] = {**r, "books": list(r["books"])}
            continue
        for f in ("bioLong", "bioShort", "biography"):
            if r.get(f) and (not g.get(f) or len(r[f]) > len(g[f])):
                g[f] = r[f]
        have = {b["ean"] for b in g["books"]}
        g["books"] += [b for b in r["books"] if b["ean"] not in have]
    return list(groups.values())


def read(schema: str, execute: Callable[[str, int], Any], active_eans: Optional[set[str]] = None) -> list[dict[str, Any]]:
    """CRM → yazar kayıtları. `active_eans` verilirse yalnız T-soft'ta satıştaki kitabı olan yazarlar."""
    p = crm._prefix(schema)

    def rows(sql: str) -> list[dict[str, Any]]:
        _, out, truncated = execute(sql, crm.LIMIT)
        if truncated:
            raise RuntimeError("CRM sonucu kesildi; eksik veriyle yazılmaz.")
        return out

    types = author_type_ids(rows(type_sql(p)))
    books = author_books(rows(participation_sql(p)), types)
    if active_eans:
        books = {cid: [b for b in bs if b["ean"] in active_eans] for cid, bs in books.items()}
        books = {cid: bs for cid, bs in books.items() if bs}
    out = []
    for r in rows(contact_sql(p, types)):
        cid = str(r.get("contact_id") or "").upper()
        if cid in books:
            out.append(source_record(r, books[cid]))
    return merge_same_name(out)


# ------------------------------------------------------------------ metin
_BLOCK = re.compile(r"<\s*/?\s*(p|br|div|li|h\d)\b[^>]*>", re.I)


def plain(v: Any) -> Optional[str]:
    """HTML → düz metin; paragraf sınırı (boş satır) korunur."""
    if v is None:
        return None
    t = _BLOCK.sub("\n\n", str(v))
    t = html_mod.unescape(re.sub(r"<[^>]+>", " ", t)).replace("\r", "")
    paras = [re.sub(r"[ \t ]+", " ", x).strip() for x in re.split(r"\n\s*\n|\n", t)]
    out = "\n\n".join(x for x in paras if x)
    return out or None


def bio_text(src: dict[str, Any]) -> str:
    """Özgeçmiş alanları (uzun, kısa, biyografi): birbirinin tekrarı olan atılır."""
    parts: list[str] = []
    for f in ("bioLong", "biography", "bioShort"):
        t = (src.get(f) or "").strip()
        if t and not any(fold(t) in fold(x) for x in parts):
            parts.append(t)
    return "\n\n".join(parts)


def paragraphs(text: Any) -> list[str]:
    return [p.strip() for p in re.split(r"\n\s*\n", str(text or "")) if p.strip()]


def words(text: Any) -> int:
    return len(re.findall(r"\w+", str(text or "")))


# ------------------------------------------------------------------ yazar listesi (saf)
def _num(v: Any) -> int:
    try:
        return int(float(str(v or 0).replace(",", ".")))
    except ValueError:
        return 0


def product_brief(p: dict[str, Any], site: str) -> dict[str, Any]:
    link = p.get("SeoLink") or p.get("Url") or p.get("ProductUrl") or ""
    url = link if str(link).startswith("http") else (f"{site.rstrip('/')}/{str(link).lstrip('/')}" if link and site else None)
    return {"id": str(p.get("ProductId") or ""), "ean": crm.ean_key(p.get("Barcode")), "name": rules.text_of(p.get("ProductName")),
            "url": url, "isbn": crm.ean_key(p.get("Barcode")) or None, "sales": _num(p.get("CountTotalSales")),
            "model": rules.text_of(p.get("Model")), "modelId": str(p.get("ModelId") or "")}


def build_authors(sources: list[dict[str, Any]], products: list[dict[str, Any]], links: list[dict[str, Any]],
                  same_as: dict[str, dict[str, Any]], site: str, bio_min: int = BIO_MIN) -> list[dict[str, Any]]:
    """CRM yazarları × satıştaki T-soft ürünleri → yazar satırı, satıştan aza.

    `products`: `product_brief` çıktıları (aktif). `links`: T-soft yazar sayfaları {link, table_id, title}.
    `same_as`: entity önbelleği, katlanmış ad → {wikidata, wikipedia}."""
    by_ean: dict[str, list[dict[str, Any]]] = {}
    for b in products:
        if b["ean"] and b["id"]:
            by_ean.setdefault(b["ean"], []).append(b)
    by_tid = {str(l["table_id"]): l for l in links if l.get("table_id") not in (None, "", "0")}
    by_name: dict[str, dict[str, Any]] = {}
    for l in links:
        nm = rules.text_of(l.get("title")).split("|")[0].strip()
        for k in (name_key(nm), name_key(str(l.get("link") or "").replace("-", " "))):
            if k:
                by_name.setdefault(k, l)
    out = []
    for s in sources:
        nk = name_key(s["name"])
        seen: dict[str, dict[str, Any]] = {}
        for bk in s.get("books") or []:
            for b in by_ean.get(bk["ean"], []):
                seen.setdefault(b["id"], b)
        books = sorted(seen.values(), key=lambda b: (-b["sales"], b["name"]))
        if not books:
            continue  # satışta kitabı yok
        matched = any(nk in model_keys(b["model"]) for b in books)
        page = next((by_tid[b["modelId"]] for b in books
                     if b["modelId"] in by_tid and model_keys(b["model"]) == {nk}), None) or by_name.get(nk)
        text = bio_text(s)
        ent = same_as.get(fold(s["name"])) or next(
            (same_as[fold(n)] for b in books for n in split_authors(b["model"]) if name_key(n) == nk and fold(n) in same_as), None) or {}
        has_bio = len(text) >= bio_min
        out.append({
            "key": s["key"], "name": s["name"], "sales": sum(b["sales"] for b in books), "bookCount": len(books),
            "books": [{k: b[k] for k in ("id", "name", "url", "isbn", "sales")} for b in books],
            "bioLength": len(text), "hasBio": has_bio, "task": None if has_bio else NO_BIO_TASK,
            "matched": matched, "page": {"link": page["link"], "url": f"{site.rstrip('/')}/{page['link']}", "id": str(page["table_id"])} if page else None,
            "sameAs": [u for u in (ent.get("wikidata"), ent.get("wikipedia")) if u],
        })
    out.sort(key=lambda a: (-a["sales"], a["name"]))
    return out


def queue(authors: list[dict[str, Any]], drafted: set[str]) -> list[dict[str, Any]]:
    """Gece sırası: özgeçmişi olan, taslağı olmayan yazarlar, satıştan aza."""
    return [a for a in sorted(authors, key=lambda a: (-a["sales"], a["name"])) if a["hasBio"] and a["key"] not in drafted]


def match_report(authors: list[dict[str, Any]]) -> dict[str, int]:
    return {"matched": sum(1 for a in authors if a["matched"]), "unmatched": sum(1 for a in authors if not a["matched"])}


# ------------------------------------------------------------------ taslak
PROMPT = """Sen Timaş Yayınları'nın sitesi (timas.com.tr) için yazar biyografisi yazan editörsün.
Aşağıdaki yazar için yazar sayfasında yayımlanacak Türkçe bir biyografi yaz. Kurallar:
- YALNIZ aşağıdaki özgeçmiş metnini ve kitap adlarını kullan. Metinde olmayan doğum yeri/tarihi, okul, görev,
  ödül, sayı, kişi, kurum ya da kitap adı UYDURMA. Emin olmadığın bilgiyi yazma.
- Tarafsız, ansiklopedik dil; üçüncü tekil şahıs. Övgü ve reklam dili yok ("usta", "eşsiz", "mutlaka okunmalı").
- Satış bilgisi şirket içidir: satış rakamı ya da "çok satan" yazma.
- Bio: {bio_min}–{bio_max} kelime, düz metin, 1–3 paragraf; paragraflar arasında boş satır.
- Summary: yazarın kim olduğunu söyleyen TEK cümle, {meta_min}–{meta_max} karakter; tırnak ve emoji yok.
Sadece şu JSON'u döndür, başka hiçbir şey yazma:
{{"Bio": "...", "Summary": "..."}}

YAZAR: {name}
ÖZGEÇMİŞ (CRM kaydı):
{bio}

TİMAŞ'TAN ÇIKAN KİTAPLARI: {books}
"""


def build_prompt(src: dict[str, Any], books: list[dict[str, Any]], lim: dict[str, int]) -> str:
    return PROMPT.format(name=src["name"], bio=src["text"], books="; ".join(b["name"] for b in books if b.get("name")) or "-",
                         bio_min=BIO_WORDS[0], bio_max=BIO_WORDS[1], meta_min=lim["meta_min"], meta_max=lim["meta_max"])


def parse(raw: Optional[str]) -> dict[str, str]:
    if not raw:
        raise ValueError("Model cevap vermedi.")
    text = re.sub(r"<think>.*?</think>", "", raw, flags=re.S).strip()
    m = re.search(r"\{.*\}", text, flags=re.S)
    if not m:
        raise ValueError("Model cevabında JSON bulunamadı.")
    data = json.loads(m.group(0))
    out = {"Bio": "\n\n".join(rules.text_of(p) for p in paragraphs(data.get("Bio"))),
           "Summary": rules.text_of(data.get("Summary"))}
    if not out["Bio"]:
        raise ValueError("Model boş biyografi döndürdü.")
    return out


def violations(fields: dict[str, str], lim: dict[str, int]) -> list[str]:
    out = []
    n = words(fields.get("Bio"))
    if not BIO_WORDS[0] <= n <= BIO_WORDS[1]:
        out.append(f"Bio {n} kelime, {BIO_WORDS[0]}–{BIO_WORDS[1]} olmalı")
    s = fields.get("Summary") or ""
    if not lim["meta_min"] <= len(s) <= lim["meta_max"]:
        out.append(f"Summary {len(s)} karakter, {lim['meta_min']}–{lim['meta_max']} olmalı")
    return out


def suggest(llm: Any, src: dict[str, Any], books: list[dict[str, Any]], lim: dict[str, int]) -> dict[str, str]:
    """Taslak; kural dışıysa model bir kez, neyin yanlış olduğu söylenerek düzeltmeye çağrılır. İkinci cevap daha
    iyi değilse ilki kalır (ekran sayaçları kırmızı gösterir, editör düzenler)."""
    messages = [{"role": "user", "content": build_prompt(src, books, lim)}]
    raw = llm.chat(messages, max_tokens=2500, temperature=0.2)
    fields = parse(raw)
    wrong = violations(fields, lim)
    if wrong:
        messages += [{"role": "assistant", "content": raw},
                     {"role": "user", "content": "Düzelt: " + "; ".join(wrong) + ". Aynı JSON biçiminde yalnız düzeltilmiş hâli döndür."}]
        try:
            fixed = parse(llm.chat(messages, max_tokens=2500, temperature=0.2))
            if len(violations(fixed, lim)) < len(wrong):
                fields = fixed
        except ValueError:
            pass
    if fields["Summary"]:
        fields["Summary"] = propose._cut(fields["Summary"], lim["meta_max"])
    return fields


def _html(*parts: Any) -> str:
    return "".join(f"<p>{html_mod.escape(str(p))}</p>" for p in parts if p)


def source_text(src: dict[str, Any], books: list[dict[str, Any]]) -> str:
    return " ".join([src["name"], src.get("text") or "", " ".join(b.get("name") or "" for b in books), "Timaş Yayınları Timaş"])


def reality(src: dict[str, Any], books: list[dict[str, Any]], fields: dict[str, str]) -> list[str]:
    """Biyografi ve özetteki sayılar ve cümle ortası özel adlar CRM özgeçmişinde ya da kitap adlarında geçiyor mu."""
    return propose.unsupported({"ProductName": src["name"], "Details": source_text(src, books)},
                               {"Details": _html(*paragraphs(fields.get("Bio")), fields.get("Summary"))})


# ------------------------------------------------------------------ JSON-LD ve dışa aktarım (kodla)
def person_jsonld(name: str, summary: Optional[str], url: Optional[str], same_as: list[str]) -> dict[str, Any]:
    ld: dict[str, Any] = {"@context": "https://schema.org", "@type": "Person", "name": name}
    if summary:
        ld["description"] = summary
    if url:
        ld["url"] = url
        ld["mainEntityOfPage"] = url
    if same_as:
        ld["sameAs"] = list(dict.fromkeys(same_as))
    return ld


def export_html(name: str, fields: dict[str, str], books: list[dict[str, Any]], ld: dict[str, Any], status: str) -> str:
    e = html_mod.escape
    paras = "\n".join(f"<p>{e(p)}</p>" for p in paragraphs(fields.get("Bio")))
    items = "\n".join(f'  <li><a href="{e(b["url"])}">{e(b.get("name") or "")}</a></li>' if b.get("url")
                      else f"  <li>{e(b.get('name') or '')}</li>" for b in books)
    script = '<script type="application/ld+json">\n' + json.dumps(ld, ensure_ascii=False, indent=2).replace("</", "<\\/") + "\n</script>"
    note = "" if status == "onaylandi" else "<!-- DİKKAT: bu taslak henüz onaylanmadı. -->\n"
    return (f"<!doctype html>\n{note}<html lang=\"tr\">\n<head>\n<meta charset=\"utf-8\">\n<title>{e(name)}</title>\n"
            f"<meta name=\"description\" content=\"{e(fields.get('Summary') or '')}\">\n{script}\n</head>\n<body>\n<article>\n"
            f"<h1>{e(name)}</h1>\n{paras}\n"
            + (f"<h2>Timaş'tan çıkan kitapları</h2>\n<ul>\n{items}\n</ul>\n" if books else "")
            + "</article>\n</body>\n</html>\n")


def clean_fields(raw: dict[str, Any]) -> dict[str, str]:
    out: dict[str, str] = {}
    if "Bio" in raw:
        out["Bio"] = "\n\n".join(rules.text_of(p) for p in paragraphs(raw.get("Bio")))
    if "Summary" in raw:
        out["Summary"] = rules.text_of(raw.get("Summary"))
    return out


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", fold(text)).strip("-")[:80] or "yazar"


# ------------------------------------------------------------------ uçlar
# Modül düzeyinde: `from __future__ import annotations` ile FastAPI tipleri modülün globallerinde arar.
class BioDecision(BaseModel):
    action: str = Field(pattern="^(approve|reject)$")
    fields: dict[str, Any] = Field(default_factory=dict)
    note: str = Field(default="", max_length=1000)


def register(app, ctx) -> None:  # noqa: C901 — uçlar tek yerde
    from fastapi.responses import HTMLResponse

    seo = ctx.seo
    run: dict[str, Any] = {"running": False, "phase": None, "read": None, "done": 0, "failed": 0, "startedAt": None,
                           "finishedAt": None, "error": None}
    run_lock = threading.Lock()
    cache: dict[str, Any] = {}
    cache_lock = threading.Lock()

    def err(status: int, message: str) -> HTTPException:
        return HTTPException(status, {"code": "SEO", "message": message})

    def eng():
        e = seo.engine()
        ensure(e)
        return e

    def site() -> str:
        return (seo.conf("SEO_SITE_URL") or "https://timas.com.tr").rstrip("/")

    def bio_min() -> int:
        try:
            return max(1, int(seo.conf("SEO_BIO_MIN_CHARS") or BIO_MIN))
        except ValueError:
            return BIO_MIN

    def crm_ready() -> bool:
        from semantic_bridge import admin as admin_mod

        return bool(admin_mod.conf("CRM_SCHEMA")) and bool(crm.CONNECTION_FILE) and os.path.exists(crm.CONNECTION_FILE)

    # ---- CRM okuması
    def read_crm() -> int:
        from semantic_bridge import admin as admin_mod

        from .store import PRODUCTS

        tenant = seo.tenant()
        with eng().connect() as c:
            active = {crm.ean_key(loads(r[0], {}).get("Barcode")) for r in c.execute(
                sa.select(PRODUCTS.c.data_json).where(PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.active.is_(True)))}
        active.discard("")
        con = crm.connector()  # kendi bağlantısı; köprünün ortak bağlantısı sohbetle paylaşılmaz
        try:
            recs = read(admin_mod.conf("CRM_SCHEMA"), con.execute, active or None)
        finally:
            try:
                con.close()
            except Exception:  # noqa: BLE001
                pass
        at = now()
        vals = [dict(tenant_id=tenant, author_key=r["contactId"][:40], name=r["name"][:300], bio_long=r["bioLong"],
                     bio_short=r["bioShort"], biography=r["biography"], books_json=dumps(r["books"]), synced_at=at)
                for r in recs if r["contactId"]]
        with eng().begin() as c:
            c.execute(BIOS_SRC.delete().where(BIOS_SRC.c.tenant_id == tenant))
            for i in range(0, len(vals), 1000):
                c.execute(BIOS_SRC.insert(), vals[i:i + 1000])
        return len(vals)

    # ---- yazar listesi (eşitleme damgası değişene kadar bellekte)
    def authors() -> tuple[list[dict[str, Any]], dict[str, str]]:
        from .store import LINKS, PRODUCTS

        tenant = seo.tenant()
        with eng().connect() as c:
            stamp = tuple(c.execute(sa.select(sa.func.max(t.c.synced_at if t is not ENTITY else t.c.checked_at))
                                    .where(t.c.tenant_id == tenant)).scalar() for t in (PRODUCTS, BIOS_SRC, LINKS, ENTITY))
        stamp = stamp + (bio_min(), site())
        with cache_lock:
            hit = cache.get(tenant)
            if hit and hit[0] == stamp:
                return hit[1], hit[2]
        with eng().connect() as c:
            src_rows = c.execute(sa.select(BIOS_SRC).where(BIOS_SRC.c.tenant_id == tenant)).mappings().all()
            prods = [product_brief(loads(r[0], {}), site()) for r in c.execute(
                sa.select(PRODUCTS.c.data_json).where(PRODUCTS.c.tenant_id == tenant, PRODUCTS.c.active.is_(True)))]
            links = [dict(r) for r in c.execute(sa.select(LINKS.c.link, LINKS.c.table_id, LINKS.c.title).where(
                LINKS.c.tenant_id == tenant, LINKS.c.type == "model")).mappings()]
            ents = c.execute(sa.select(ENTITY.c.name, ENTITY.c.data_json).where(
                ENTITY.c.tenant_id == tenant, ENTITY.c.kind == "author")).all()
        same_as = {n: loads(d, {}) for n, d in ents}
        sources = [{"key": r["author_key"], "name": r["name"], "bioLong": r["bio_long"], "bioShort": r["bio_short"],
                    "biography": r["biography"], "books": loads(r["books_json"], [])} for r in src_rows]
        texts = {s["key"]: bio_text(s) for s in sources}
        rows = build_authors(sources, prods, links, same_as, site(), bio_min())
        with cache_lock:
            cache[tenant] = (stamp, rows, texts)
        return rows, texts

    def author(key: str) -> tuple[dict[str, Any], str]:
        rows, texts = authors()
        a = next((x for x in rows if x["key"] == key), None)
        if a is None:
            raise err(404, "Yazar bulunamadı; CRM okuması yenilenmiş ya da kitapları satıştan kalkmış olabilir.")
        return a, texts.get(key, "")

    def drafts_by_author() -> dict[str, dict[str, Any]]:
        with eng().connect() as c:
            rows = c.execute(sa.select(BIOS.c.author_key, BIOS.c.id, BIOS.c.status).where(
                BIOS.c.tenant_id == seo.tenant()).order_by(BIOS.c.created_at)).all()
        return {k: {"id": i, "status": s} for k, i, s in rows}   # yazar başına en yenisi

    def row(bid: str) -> dict[str, Any]:
        with eng().connect() as c:
            r = c.execute(sa.select(BIOS).where(BIOS.c.tenant_id == seo.tenant(), BIOS.c.id == bid)).mappings().first()
        if not r:
            raise err(404, "Biyografi taslağı bulunamadı.")
        return dict(r)

    def view(r: dict[str, Any], full: bool = True) -> dict[str, Any]:
        out = {"id": r["id"], "authorKey": r["author_key"], "name": r["name"], "status": r["status"], "model": r["model"],
               "createdBy": r["created_by"], "createdAt": iso(r["created_at"]), "decidedBy": r["decided_by"],
               "decidedAt": iso(r["decided_at"]), "note": r["note"]}
        if full:
            out.update(fields=loads(r["fields_json"], {}),
                       books=[{k: b.get(k) for k in ("id", "name", "url", "isbn")} for b in loads(r["books_json"], [])],
                       jsonld=loads(r["jsonld_json"], {}), unsupported=loads(r["unsupported_json"], []),
                       limits={**rules.thresholds(seo.conf), "bio_min_words": BIO_WORDS[0], "bio_max_words": BIO_WORDS[1]})
        return out

    def make(key: str, user: str, priority: Optional[int] = None) -> dict[str, Any]:
        gen_key = f"bio:{key}"
        with seo._gen_lock:
            if gen_key in seo._generating:
                raise err(409, "Bu yazar için taslak şu an yazılıyor.")
            seo._generating.add(gen_key)
        try:
            a, text = author(key)
            if not a["hasBio"]:
                raise err(422, f"{NO_BIO_TASK}: taslak ancak CRM özgeçmişinden yazılır.")
            llm = seo.runtime().llm_for("seo", priority)
            if llm is None:
                raise err(503, "Yapay zekâ modeli bu kurulumda tanımlı değil.")
            lim = rules.thresholds(seo.conf)
            src = {"name": a["name"], "text": text}
            try:
                fields = suggest(llm, src, a["books"], lim)
            except ValueError as e:
                raise err(502, f"Taslak üretilemedi: {e}") from None
            books = [{k: b.get(k) for k in ("id", "name", "url", "isbn", "sales")} for b in a["books"]]
            ld = person_jsonld(a["name"], fields.get("Summary"), (a.get("page") or {}).get("url"), a["sameAs"])
            bid, tenant = uuid.uuid4().hex, seo.tenant()
            with eng().begin() as c:
                # Aynı yazarın bekleyen eski taslağı yenisiyle değişir; karar verilmişler kalır.
                c.execute(BIOS.delete().where(BIOS.c.tenant_id == tenant, BIOS.c.author_key == key, BIOS.c.status == "hazir"))
                c.execute(BIOS.insert().values(
                    id=bid, tenant_id=tenant, author_key=key, name=a["name"][:300], status="hazir",
                    fields_json=dumps(fields), books_json=dumps(books),
                    source_json=dumps({**src, "page": a.get("page"), "sameAs": a["sameAs"]}), jsonld_json=dumps(ld),
                    unsupported_json=dumps(reality(src, books, fields)),
                    model=(getattr(llm, "model", None) or seo.conf("LLM_MODEL_NAME") or "")[:120] or None,
                    created_by=user, created_at=now()))
            seo.audit(user, "create", f"bio:{bid}", a["name"][:200], {"bio": bid, "author": key})
            return view(row(bid))
        finally:
            with seo._gen_lock:
                seo._generating.discard(gen_key)

    @app.get("/api/v1/seo-geo/bios")
    def bios_list(request: Request, status: str = "", q: str = "", start: int = 0, limit: int = 50) -> dict[str, Any]:
        ctx.gate(request)
        if status and status not in FILTERS:
            raise err(422, "Bilinmeyen süzgeç.")
        rows, _ = authors()
        drafts = drafts_by_author()
        items = [{**{k: v for k, v in a.items() if k != "books"}, "topBooks": [b["name"] for b in a["books"][:3]],
                  "draft": drafts.get(a["key"])} for a in rows]
        counts = {"yazar": len(items), "kaynak_var": sum(1 for a in items if a["hasBio"]),
                  "kaynak_yok": sum(1 for a in items if not a["hasBio"]),
                  "taslak_yok": sum(1 for a in items if a["hasBio"] and not a["draft"]),
                  "eslesmedi": sum(1 for a in items if not a["matched"])}
        for s in STATUSES:
            counts[s] = sum(1 for a in items if a["draft"] and a["draft"]["status"] == s)
        if status == "kaynak_yok":
            items = [a for a in items if not a["hasBio"]]
        elif status == "taslak_yok":
            items = [a for a in items if a["hasBio"] and not a["draft"]]
        elif status == "eslesmedi":
            items = [a for a in items if not a["matched"]]
        elif status:
            items = [a for a in items if a["draft"] and a["draft"]["status"] == status]
        if q.strip():
            needle = name_key(q)
            items = [a for a in items if needle in name_key(a["name"])]
        with eng().connect() as c:
            last = c.execute(sa.select(sa.func.max(BIOS_SRC.c.synced_at)).where(BIOS_SRC.c.tenant_id == seo.tenant())).scalar()
        s = max(0, start)
        return {"total": len(items), "start": s, "counts": counts, "crmRead": iso(last), "crmReady": crm_ready(),
                "bioMinChars": bio_min(), "run": run, "items": items[s:s + max(1, limit)]}

    @app.post("/api/v1/seo-geo/bios/refresh")
    def bios_refresh(request: Request) -> dict[str, Any]:
        """CRM yazar özgeçmişlerini yeniden okur (arka planda). Taslak üretmez."""
        user = ctx.gate(request)
        started = start_run(generate=False)
        seo.audit(user, "run", "bios", "Yazar biyografileri: CRM okuması", {"started": started})
        return {"started": started, "run": run}

    @app.get("/api/v1/seo-geo/bios/drafts/{bid}/export.html")
    def bios_export(bid: str, request: Request):
        ctx.gate(request)
        r = row(bid)
        body = export_html(r["name"] or "", loads(r["fields_json"], {}), loads(r["books_json"], []),
                           loads(r["jsonld_json"], {}), r["status"])
        return HTMLResponse(body, headers={"Content-Disposition": f'attachment; filename="yazar-{slug(r["name"] or "")}.html"'})

    @app.post("/api/v1/seo-geo/bios/drafts/{bid}/decide")
    def bios_decide(bid: str, body: BioDecision, request: Request) -> dict[str, Any]:
        """Karar yalnız kaydedilir; siteye, T-soft'a ya da CRM'e hiçbir şey gönderilmez."""
        user = ctx.approver(request)
        r = row(bid)
        if r["status"] != "hazir":
            raise err(409, "Bu taslak için karar zaten verilmiş.")
        approve = body.action == "approve"
        vals: dict[str, Any] = dict(status="onaylandi" if approve else "reddedildi", decided_by=user, decided_at=now(),
                                    note=body.note or None)
        if approve:
            fields = {**loads(r["fields_json"], {}), **clean_fields(body.fields or {})}
            if not fields.get("Bio"):
                raise err(422, "Biyografi boş olamaz.")
            src, books = loads(r["source_json"], {}), loads(r["books_json"], [])
            ld = person_jsonld(r["name"] or "", fields.get("Summary"), (src.get("page") or {}).get("url"), src.get("sameAs") or [])
            vals.update(fields_json=dumps(fields), jsonld_json=dumps(ld),
                        unsupported_json=dumps(reality({"name": r["name"] or "", "text": src.get("text") or ""}, books, fields)))
        with eng().begin() as c:
            c.execute(BIOS.update().where(BIOS.c.id == bid).values(**vals))
        seo.audit(user, body.action, f"bio:{bid}", (r["name"] or "")[:200], {"bio": bid, "kind": "bio"})
        return view(row(bid))

    @app.get("/api/v1/seo-geo/bios/{key}")
    def bios_get(key: str, request: Request) -> dict[str, Any]:
        ctx.gate(request)
        a, text = author(key)
        with eng().connect() as c:
            rows = c.execute(sa.select(BIOS).where(BIOS.c.tenant_id == seo.tenant(), BIOS.c.author_key == key)
                             .order_by(BIOS.c.created_at.desc())).mappings().all()
        return {**a, "source": text, "draft": view(dict(rows[0])) if rows else None,
                "history": [view(dict(r), full=False) for r in rows[1:]]}

    @app.post("/api/v1/seo-geo/bios/{key}/draft")
    def bios_draft(key: str, request: Request) -> dict[str, Any]:
        user = ctx.gate(request)
        return make(key, user)

    # ---- gece: CRM okuması + ön üretim (arka planda; hemen döner)
    def work(generate: bool) -> None:
        from semantic_layer.runtime.llm_queue import BATCH

        try:
            budget = int(seo.conf("SEO_BIOS_BUDGET") or 1800)
        except ValueError:
            budget = 1800
        run.update(running=True, phase="crm", read=None, done=0, failed=0, startedAt=iso(now()), finishedAt=None, error=None)
        try:
            if crm_ready():
                run["read"] = read_crm()
            elif not generate:
                raise RuntimeError("CRM bağlantısı tanımlı değil.")
            if generate:
                run["phase"] = "taslak"
                deadline = time.monotonic() + max(60, budget)
                rows, _ = authors()
                for a in queue(rows, set(drafts_by_author())):
                    if time.monotonic() > deadline:
                        break
                    try:
                        make(a["key"], "zamanlayıcı", BATCH)
                        run["done"] += 1
                    except HTTPException as e:
                        if e.status_code == 503:
                            raise
                        run["failed"] += 1
        except Exception as e:  # noqa: BLE001 — tur durur, üretilenler kalır
            run["error"] = str(getattr(e, "detail", e))[:500]
            log.exception("seo bios run failed")
        finally:
            run.update(running=False, phase=None, finishedAt=iso(now()))
            run_lock.release()

    def start_run(generate: bool) -> bool:
        if not run_lock.acquire(blocking=False):
            return False
        threading.Thread(target=work, args=(generate,), name="seo-bios", daemon=True).start()
        return True

    def nightly() -> None:
        start_run(generate=True)

    seo.nightly.append(("bios", nightly))
