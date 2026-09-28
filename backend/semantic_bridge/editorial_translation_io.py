"""M4 Çeviri: dış çeviri belleği (TMX 1.4b) ve terim bankası TBX içe/dışa aktarımı.

- **TBX** (TBX-Basic; TBX v2 `martif/termEntry/langSet/tig|ntig` ve v3 `tbx/conceptEntry/langSec/termSec`,
  DCA ya da DCT biçimi): seçilen dil çiftinin terim bankasına yazılır. Kaynak dildeki her kullanılabilir terim
  bir kayıttır; hedefte tercih edilen terim ilk, kabul edilenler `|` ile ardından gelir; `deprecatedTerm` /
  `supersededTerm` / «forbidden» durumundaki hedef terimler yasak karşılık olur. `note`, `descrip`, `admin`
  alanları not olur. Aynı kaynak terim (büyük/küçük harf duyarsız, dil çiftinin genel terimi) varsa güncellenir.
  Dışa aktarım TBX-Basic (v2) — onaylı terimler.
- **TMX 1.4b**: çeviri birimleri `semantic_translation_tm` tablosuna yazılır (dil çifti seçilir; bölgesel dil
  kodu en-US → en). Aynı (normalleştirilmiş) kaynak + hedef ikinci kez yazılmaz. Dışa aktarım bir dil çiftinin
  çevrildi/onaylı segmentleri (+ isteğe bağlı içe aktarılmış bellek).
- Çeviri belleği araması (`editorial_translation._tm`) bu tabloya da `tm_matches` ile bakar; eşleşmenin kaynağı
  «Dış bellek: <dosya>» diye etiketlenir.

XML güvenliği: iç tanımlı DOCTYPE ve ENTITY bildirimi reddedilir (varlık genişletme saldırısı). Yalnız dış
kimlikli, iç tanımı olmayan DOCTYPE (`<!DOCTYPE tmx SYSTEM "tmx14.dtd">`, OmegaT/Trados dosyalarında olağan)
ayrıştırmadan önce atılır; dış DTD okunmaz.
"""
from __future__ import annotations

import difflib
import hashlib
import io
import re
from collections import Counter, defaultdict
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional
from xml.etree import ElementTree

import sqlalchemy as sa
# `from __future__ import annotations` altında FastAPI tip adını modül düzeyinde çözer: Request burada olmalı,
# yoksa `request` sorgu parametresi sanılır (422).
from fastapi import Request

from semantic_bridge import editorial_translation as tr

TranslationError = tr.TranslationError

_md = sa.MetaData()
TM = sa.Table(
    "semantic_translation_tm", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False),
    sa.Column("source_lang", sa.String(8), nullable=False),
    sa.Column("target_lang", sa.String(8), nullable=False),
    sa.Column("source", sa.Text, nullable=False),
    sa.Column("target", sa.Text, nullable=False),
    sa.Column("origin", sa.String(300), nullable=False),          # içe aktarılan dosyanın adı
    sa.Column("key_hash", sa.String(64), nullable=False),         # sha256(normal kaynak ␟ normal hedef)
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.UniqueConstraint("tenant_id", "source_lang", "target_lang", "key_hash", name="uq_semantic_translation_tm_key"),
    sa.Index("ix_semantic_translation_tm_pair", "tenant_id", "source_lang", "target_lang"),
)

#: Dosya sınırları: TMX kaynak dosya sınırı kadar, TBX CSV terim içe aktarımı kadar.
TMX_MAX_BYTES = tr.MAX_BYTES
TBX_MAX_BYTES = 20 * 1024 * 1024
_ready: set[int] = set()


def ensure(engine: sa.engine.Engine) -> None:
    with tr._lock:
        if id(engine) in _ready:
            return
        _md.create_all(engine, checkfirst=True)
        _ready.add(id(engine))


# ============================================================================================ ortak

_XML_NS = "{http://www.w3.org/XML/1998/namespace}"
_DECL = re.compile(rb"<!\s*(?:DOCTYPE|ENTITY)", re.I)
_SAFE_DOCTYPE = re.compile(rb"<!DOCTYPE\s+[\w.:-]+(?:\s+(?:SYSTEM\s+(?:\"[^\"]*\"|'[^']*')"
                           rb"|PUBLIC\s+(?:\"[^\"]*\"|'[^']*')\s+(?:\"[^\"]*\"|'[^']*')))?\s*>")


def _local(tag: Any) -> str:
    return tag.split("}")[-1] if isinstance(tag, str) else ""


def _lang_attr(el: Any) -> str:
    return el.get(f"{_XML_NS}lang") or el.get("lang") or ""


def base_lang(code: str) -> str:
    """en-US, en_GB, zh-Hans-CN → en / zh. Tanınmayan dil boş döner."""
    b = re.split(r"[-_]", (code or "").strip().lower(), maxsplit=1)[0]
    return b if b in tr.LANGS else ""


def _pair(src: Any, tgt: Any) -> tuple[str, str]:
    s, t = tr._lang(src, "Kaynak"), tr._lang(tgt, "Hedef")
    if s == t:
        raise TranslationError("Kaynak ve hedef dil aynı olamaz.")
    return s, t


def _xml_input(data: bytes, what: str, limit: int) -> bytes:
    """Boyut sınırı, UTF-16 → UTF-8, DOCTYPE/ENTITY denetimi. Ayrıştırmaya hazır bayt döner."""
    if not data:
        raise TranslationError("Dosya boş.")
    if len(data) > limit:
        raise TranslationError(f"Dosya {limit // (1024 * 1024)} MB sınırını aşıyor.", 413)
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        # Bazı araçlar TMX'i UTF-16 yazar; bildirimdeki kodlama da UTF-8'e göre atılır.
        text = data.decode("utf-16")
        data = re.sub(r"^\s*<\?xml[^>]*\?>", "", text, count=1).encode("utf-8")
    decls = list(_DECL.finditer(data))
    if decls:
        m = _SAFE_DOCTYPE.match(data, decls[0].start())
        first_el = re.search(rb"<[A-Za-z_]", data)
        if len(decls) > 1 or m is None or first_el is None or first_el.start() < m.end():
            raise TranslationError(f"{what} dosyasında iç tanımlı DOCTYPE ya da ENTITY kabul edilmez.")
        data = data[:m.start()] + data[m.end():]
    return data


def _iterparse(data: bytes, what: str) -> Iterable[Any]:
    try:
        for _, el in ElementTree.iterparse(io.BytesIO(data), events=("end",)):
            yield el
    except ElementTree.ParseError as e:
        raise TranslationError(f"{what} dosyası okunamadı.") from e


def _one_line(s: str) -> str:
    return " ".join((s or "").split())


def _xml_text(s: str) -> str:
    return tr._xml_text(s or "")


def _attr(s: str) -> str:
    return _xml_text(s).replace('"', "&quot;")


def _stamp(v: Any) -> Optional[str]:
    """TMX tarih biçimi: YYYYMMDDThhmmssZ."""
    if not isinstance(v, datetime):
        return None
    v = v if v.tzinfo else v.replace(tzinfo=timezone.utc)
    return v.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


# ============================================================================================ TBX

_FORBIDDEN_STATUS = ("deprecated", "superseded", "forbidden", "notrecommended", "not recommended")
_NOTE_LABELS = {
    "definition": "Tanım", "context": "Bağlam", "subjectField": "Alan", "source": "Kaynak", "explanation": "Açıklama",
    "customerSubset": "Müşteri", "projectSubset": "Proje", "example": "Örnek", "usageNote": "Kullanım",
}
_NOTE_TAGS = {"note", "descrip", "admin"} | set(_NOTE_LABELS)   # DCT biçiminde alan adı öğenin kendisidir
_TERM_BOX = {"tig", "ntig", "termSec"}
_LANG_BOX = {"langSet", "langSec"}
_ENTRY = {"termEntry", "conceptEntry"}


def _term_status(box: Any) -> str:
    for el in box.iter():
        tag = _local(el.tag)
        if tag == "termNote" and (el.get("type") or "") in ("administrativeStatus", "normativeAuthorization", "usageStatus"):
            return (el.text or "").strip()
        if tag in ("administrativeStatus", "normativeAuthorization", "usageStatus"):   # DCT
            return (el.text or "").strip()
    return ""


def _terms_of(lang_box: Any) -> list[tuple[str, str]]:
    """Bir dil bölümündeki (terim, durum) listesi; tig/ntig/termSec yoksa doğrudan <term>."""
    out: list[tuple[str, str]] = []
    boxes = [c for c in lang_box.iter() if _local(c.tag) in _TERM_BOX]
    for box in boxes:
        term = next((e for e in box.iter() if _local(e.tag) == "term"), None)
        if term is not None and _one_line("".join(term.itertext())):
            out.append((_one_line("".join(term.itertext())), _term_status(box)))
    if not boxes:
        for term in (e for e in lang_box.iter() if _local(e.tag) == "term"):
            if _one_line("".join(term.itertext())):
                out.append((_one_line("".join(term.itertext())), ""))
    return out


def _notes_in(el: Any, into: list[str]) -> None:
    """Not, tanım, bağlam, alan… Terim durumları (termNote) not sayılmaz; terim kutusunun içi de gezilir."""
    for c in el.iter():
        tag = _local(c.tag)
        if tag not in _NOTE_TAGS:
            continue
        text = _one_line("".join(c.itertext()))
        if not text:
            continue
        kind = c.get("type") or (tag if tag in _NOTE_LABELS else "")
        label = _NOTE_LABELS.get(kind, "")
        line = f"{label}: {text}" if label else text
        if line not in into:
            into.append(line)


def _forbidden_status(status: str) -> bool:
    s = status.lower()
    return any(k in s for k in _FORBIDDEN_STATUS)


def _preferred_rank(status: str) -> int:
    s = status.lower()
    return 0 if "preferred" in s else 1


def parse_tbx(data: bytes, src: str, tgt: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """TBX → terim kayıtları ({source, target, forbidden, note}) ve sayım. Veritabanına dokunmaz."""
    data = _xml_input(data, "TBX", TBX_MAX_BYTES)
    records: list[dict[str, Any]] = []
    langs: Counter = Counter()
    entries = skipped = 0
    for el in _iterparse(data, "TBX"):
        if _local(el.tag) not in _ENTRY:
            continue
        entries += 1
        by_lang: dict[str, list[Any]] = defaultdict(list)
        notes: list[str] = []
        for c in el:
            ctag = _local(c.tag)
            if ctag in _LANG_BOX:
                lang = base_lang(_lang_attr(c))
                langs[lang or (_lang_attr(c) or "?").lower()] += 1
                by_lang[lang].append(c)
            elif ctag in _NOTE_TAGS or ctag.endswith("Grp"):
                _notes_in(c, notes)
        src_terms = [t for box in by_lang.get(src, []) for t in _terms_of(box)]
        tgt_terms = [t for box in by_lang.get(tgt, []) for t in _terms_of(box)]
        for box in by_lang.get(src, []) + by_lang.get(tgt, []):
            _notes_in(box, notes)          # dil ve terim düzeyindeki tanım/bağlam/not (termNote durumdur, not değil)
        allowed = sorted([t for t in tgt_terms if not _forbidden_status(t[1])], key=lambda t: _preferred_rank(t[1]))
        target = " | ".join(dict.fromkeys(t for t, _ in allowed))
        forbidden = list(dict.fromkeys(t for t, st in tgt_terms if _forbidden_status(st)))
        sources = [t for t, st in src_terms if not _forbidden_status(st)]
        if not sources or not target:
            skipped += 1
            el.clear()
            continue
        for s in dict.fromkeys(sources):
            records.append({"source": s, "target": target, "forbidden": forbidden, "note": " · ".join(notes)})
        el.clear()
    if not entries:
        raise TranslationError("Dosyada terim kaydı (termEntry / conceptEntry) yok.")
    return records, {"entries": entries, "skipped": skipped, "languages": dict(langs)}


def import_tbx(engine: sa.engine.Engine, tenant: str, user: str, src: Any, tgt: Any, data: bytes) -> dict[str, Any]:
    """TBX'i dil çiftinin genel terimlerine yazar: var olan (aynı kaynak terim) güncellenir, yoksa eklenir."""
    src, tgt = _pair(src, tgt)
    records, info = parse_tbx(data, src, tgt)
    if not records:
        seen = ", ".join(sorted(k for k in info["languages"] if k)) or "yok"
        raise TranslationError(f"Dosyada {tr.LANGS[src]} → {tr.LANGS[tgt]} terim çifti bulunamadı. Dosyadaki diller: {seen}.")
    added = updated = unchanged = 0
    now = tr._now()
    with engine.begin() as conn:
        for r in records:
            v = tr._clean_term(r)
            old = tr._dup(conn, tenant, src, tgt, v["source_term"], None)
            if old is not None:
                same = (old.status == "onayli" and old.source_term == v["source_term"] and old.target_term == v["target_term"]
                        and (old.forbidden_json or "[]") == v["forbidden_json"] and (old.note or None) == v["note"])
                if same:
                    unchanged += 1
                    continue
                conn.execute(sa.update(tr.TERMS).where(tr.TERMS.c.id == old.id).values(
                    status="onayli", updated_by=user.lower(), updated_at=now, **v))
                updated += 1
            else:
                conn.execute(sa.insert(tr.TERMS).values(id=tr._new(), tenant_id=tenant, source_lang=src, target_lang=tgt,
                                                        job_id=None, status="onayli", created_by=user.lower(),
                                                        created_at=now, **v))
                added += 1
    return {"added": added, "updated": updated, "unchanged": unchanged, "skipped": info["skipped"],
            "entries": info["entries"]}


def export_tbx(engine: sa.engine.Engine, tenant: str, src: Any, tgt: Any) -> tuple[bytes, str]:
    """Dil çiftinin onaylı terimleri TBX-Basic (v2) olarak. İşe özel terim `projectSubset` ile işaretlenir."""
    src, tgt = _pair(src, tgt)
    items = [t for t in tr.list_terms(engine, tenant, src, tgt)["items"] if t["status"] == "onayli"]
    out = ['<?xml version="1.0" encoding="UTF-8"?>',
           f'<martif type="TBX-Basic" xml:lang="{src}">',
           f'<martifHeader><fileDesc><titleStmt><title>{_xml_text(f"Terim bankası {tr.LANGS[src]} → {tr.LANGS[tgt]}")}</title>'
           '</titleStmt><sourceDesc><p>ZEKİ AI</p></sourceDesc></fileDesc>'
           '<encodingDesc><p type="XCSURI">TBXBasicXCSV02.xcs</p></encodingDesc></martifHeader>',
           "<text><body>"]
    for t in items:
        out.append(f'<termEntry id="t{_attr(t["id"])}">')
        if t.get("note"):
            out.append(f"<note>{_xml_text(t['note'])}</note>")
        if t.get("jobId"):
            out.append(f'<admin type="projectSubset">{_xml_text(t.get("jobTitle") or t["jobId"])}</admin>')
        out.append(f'<langSet xml:lang="{src}"><tig><term>{_xml_text(t["source"])}</term></tig></langSet>')
        out.append(f'<langSet xml:lang="{tgt}">')
        alts = [a.strip() for a in (t["target"] or "").split("|") if a.strip()]
        for i, a in enumerate(alts):
            status = "preferredTerm-admn-sts" if i == 0 else "admittedTerm-admn-sts"
            out.append(f'<tig><term>{_xml_text(a)}</term><termNote type="administrativeStatus">{status}</termNote></tig>')
        for bad in t["forbidden"]:
            out.append(f'<tig><term>{_xml_text(bad)}</term>'
                       '<termNote type="administrativeStatus">deprecatedTerm-admn-sts</termNote></tig>')
        out.append("</langSet></termEntry>")
    out.append("</body></text></martif>")
    return "\n".join(out).encode("utf-8"), f"terim-bankasi-{src}-{tgt}.tbx"


# ============================================================================================ TMX

_INLINE_KEEP = {"hi", "g", "mrk"}          # metni çeviriye ait satır içi öğeler
# bpt / ept / ph / it / ut / sub: biçim kodu (ör. <b>, {1}); düz metne alınmaz, ardındaki metin (tail) alınır.


def _seg_text(el: Any) -> str:
    parts = [el.text or ""]
    for c in el:
        if _local(c.tag) in _INLINE_KEEP:
            parts.append(_seg_text(c))
        parts.append(c.tail or "")
    return "".join(parts)


def _key(source: str, target: str) -> str:
    return hashlib.sha256((tr._norm_src(source) + "\x1f" + tr._norm_src(target)).encode("utf-8")).hexdigest()


def parse_tmx(data: bytes, src: str, tgt: str) -> tuple[list[tuple[str, str]], dict[str, Any]]:
    """TMX → (kaynak, hedef) çiftleri ve sayım. Bölgesel kod temel dile indirgenir. Veritabanına dokunmaz."""
    data = _xml_input(data, "TMX", TMX_MAX_BYTES)
    pairs: list[tuple[str, str]] = []
    langs: Counter = Counter()
    units = skipped = 0
    for el in _iterparse(data, "TMX"):
        if _local(el.tag) != "tu":
            continue
        units += 1
        texts: dict[str, str] = {}
        for tuv in el:
            if _local(tuv.tag) != "tuv":
                continue
            raw = _lang_attr(tuv)
            lang = base_lang(raw)
            langs[lang or (raw or "?").lower()] += 1
            seg = next((c for c in tuv if _local(c.tag) == "seg"), None)
            text = _one_line(_seg_text(seg)) if seg is not None else ""
            if lang and text and lang not in texts:
                texts[lang] = text
        el.clear()
        if texts.get(src) and texts.get(tgt):
            pairs.append((texts[src], texts[tgt]))
        else:
            skipped += 1
    if not units:
        raise TranslationError("Dosyada çeviri birimi (tu) yok.")
    return pairs, {"units": units, "skipped": skipped, "languages": dict(langs)}


def import_tmx(engine: sa.engine.Engine, tenant: str, user: str, src: Any, tgt: Any, filename: str, data: bytes) -> dict[str, Any]:
    """TMX birimlerini dış çeviri belleğine yazar. Bellekte ya da dosyada tekrar eden çift ikinci kez yazılmaz."""
    src, tgt = _pair(src, tgt)
    pairs, info = parse_tmx(data, src, tgt)
    if not pairs:
        seen = ", ".join(sorted(k for k in info["languages"] if k)) or "yok"
        raise TranslationError(f"Dosyada {tr.LANGS[src]} → {tr.LANGS[tgt]} çifti bulunamadı. Dosyadaki diller: {seen}.")
    origin = (filename or "").strip().rsplit("/", 1)[-1][:300] or "adsız.tmx"
    now = tr._now()
    rows: dict[str, dict[str, Any]] = {}
    in_file = 0
    for s, t in pairs:
        k = _key(s, t)
        if k in rows:
            in_file += 1
            continue
        rows[k] = {"id": tr._new(), "tenant_id": tenant, "source_lang": src, "target_lang": tgt, "source": s, "target": t,
                   "origin": origin, "key_hash": k, "created_by": user.lower(), "created_at": now}
    keys = list(rows)
    known = 0
    try:
        with engine.begin() as conn:
            for i in range(0, len(keys), 500):
                chunk = keys[i:i + 500]
                for (k,) in conn.execute(sa.select(TM.c.key_hash).where(
                        TM.c.tenant_id == tenant, TM.c.source_lang == src, TM.c.target_lang == tgt, TM.c.key_hash.in_(chunk))).all():
                    if rows.pop(k, None) is not None:
                        known += 1
            fresh = list(rows.values())
            for i in range(0, len(fresh), 1000):
                conn.execute(sa.insert(TM), fresh[i:i + 1000])
    except sa.exc.IntegrityError as e:
        raise TranslationError("Aynı anda başka bir bellek içe aktarımı sürüyor; birazdan yeniden deneyin.", 409) from e
    return {"added": len(rows), "duplicates": known + in_file, "skipped": info["skipped"], "units": info["units"],
            "origin": origin}


def tm_matches(conn: sa.Connection, tenant: str, src: str, tgt: str, source: str) -> list[dict[str, Any]]:
    """Dış bellekte ≥%70 benzer kaynak. `_tm` ile aynı ön süzgeç (en uzun kelime, uzunluk 0,6–1,6×) ve difflib oranı."""
    ensure(conn.engine)
    words = sorted(set(tr._WORD.findall(source or "")), key=len, reverse=True)
    if not words or len(words[0]) < 4:
        return []
    n = len(source)
    q = sa.select(TM.c.source, TM.c.target, TM.c.origin).where(
        TM.c.tenant_id == tenant, TM.c.source_lang == src, TM.c.target_lang == tgt,
        sa.func.length(TM.c.source).between(int(n * 0.6), int(n * 1.6) + 1), TM.c.source.ilike(f"%{words[0]}%"))
    norm = tr._norm_src(source)
    best: dict[str, dict[str, Any]] = {}
    for r in conn.execute(q).all():
        ratio = difflib.SequenceMatcher(a=norm, b=tr._norm_src(r.source), autojunk=False).ratio()
        if ratio < 0.7:
            continue
        k = " ".join(r.target.split())
        if k not in best or ratio > best[k]["_r"]:
            best[k] = {"_r": ratio, "source": r.source, "target": r.target, "score": round(ratio * 100),
                       "status": "onaylandi", "job": f"Dış bellek: {r.origin}", "sameJob": False, "origin": "dis",
                       "file": r.origin}
    return [{k: v for k, v in m.items() if k != "_r"} for m in best.values()]


def memory_summary(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    """Dil çifti başına: işlerdeki çevrildi/onaylı segment sayısı, dış bellek kaydı ve içe aktarılan dosyalar."""
    pairs: dict[tuple[str, str], dict[str, Any]] = {}

    def slot(s: str, t: str) -> dict[str, Any]:
        return pairs.setdefault((s, t), {"sourceLang": s, "targetLang": t, "segments": 0, "external": 0, "files": []})

    with engine.connect() as conn:
        for s, t, n in conn.execute(sa.select(tr.JOBS.c.source_lang, tr.JOBS.c.target_lang, sa.func.count())
                                    .select_from(tr.SEGMENTS.join(tr.JOBS, tr.JOBS.c.id == tr.SEGMENTS.c.job_id))
                                    .where(tr.JOBS.c.tenant_id == tenant, tr.SEGMENTS.c.status.in_(tr.DONE))
                                    .group_by(tr.JOBS.c.source_lang, tr.JOBS.c.target_lang)).all():
            slot(s, t)["segments"] = int(n)
        for s, t, origin, n, first, last, who in conn.execute(
                sa.select(TM.c.source_lang, TM.c.target_lang, TM.c.origin, sa.func.count(), sa.func.min(TM.c.created_at),
                          sa.func.max(TM.c.created_at), sa.func.max(TM.c.created_by))
                .where(TM.c.tenant_id == tenant).group_by(TM.c.source_lang, TM.c.target_lang, TM.c.origin)).all():
            p = slot(s, t)
            p["external"] += int(n)
            p["files"].append({"origin": origin, "count": int(n), "firstAt": tr._iso(first), "lastAt": tr._iso(last),
                               "by": who})
    for p in pairs.values():
        p["files"].sort(key=lambda f: f["lastAt"] or "", reverse=True)
    return {"pairs": sorted(pairs.values(), key=lambda p: -(p["segments"] + p["external"])), "languages": tr.LANGS}


def delete_origin(engine: sa.engine.Engine, tenant: str, src: Any, tgt: Any, origin: str) -> int:
    """Bir dosyadan içe aktarılan bellek kayıtlarını kaldırır (yanlış dosya yüklendiyse)."""
    src, tgt = _pair(src, tgt)
    if not (origin or "").strip():
        raise TranslationError("Dosya adı gerekli.")
    with engine.begin() as conn:
        n = conn.execute(sa.delete(TM).where(TM.c.tenant_id == tenant, TM.c.source_lang == src, TM.c.target_lang == tgt,
                                             TM.c.origin == origin)).rowcount
    if not n:
        raise TranslationError("Bu dosyadan içe aktarılmış kayıt yok.", 404)
    return int(n)


def export_tmx(engine: sa.engine.Engine, tenant: str, src: Any, tgt: Any, external: bool = False) -> tuple[bytes, str, int]:
    """TMX 1.4b: dil çiftindeki bütün işlerin çevrildi/onaylı segmentleri; `external` ise içe aktarılan bellek de.
    Aynı (normalleştirilmiş) kaynak + hedef bir kez yazılır; onaylı olan önce gelir."""
    src, tgt = _pair(src, tgt)
    units: list[str] = []
    seen: set[str] = set()

    def unit(source: str, target: str, props: list[tuple[str, str]], who: Optional[str], at: Any) -> None:
        k = _key(source, target)
        if k in seen or not source.strip() or not target.strip():
            return
        seen.add(k)
        stamp = _stamp(at)
        attrs = (f' creationid="{_attr(who)}"' if who else "") + (f' creationdate="{stamp}"' if stamp else "")
        prop = "".join(f'<prop type="{_attr(t)}">{_xml_text(v)}</prop>' for t, v in props if v)
        units.append(f"<tu{attrs}>{prop}<tuv xml:lang=\"{src}\"><seg>{_xml_text(source)}</seg></tuv>"
                     f"<tuv xml:lang=\"{tgt}\"><seg>{_xml_text(target)}</seg></tuv></tu>")

    ensure(engine)
    with engine.connect() as conn:
        q = (sa.select(tr.SEGMENTS.c.source, tr.SEGMENTS.c.target, tr.SEGMENTS.c.status, tr.SEGMENTS.c.approved_by,
                       tr.SEGMENTS.c.translated_by, tr.SEGMENTS.c.updated_at, tr.JOBS.c.title)
             .join(tr.JOBS, tr.JOBS.c.id == tr.SEGMENTS.c.job_id)
             .where(tr.JOBS.c.tenant_id == tenant, tr.JOBS.c.source_lang == src, tr.JOBS.c.target_lang == tgt,
                    tr.SEGMENTS.c.status.in_(tr.DONE))
             .order_by(sa.case((tr.SEGMENTS.c.status == "onaylandi", 0), else_=1), tr.JOBS.c.created_at, tr.SEGMENTS.c.no))
        for r in conn.execute(q).all():
            unit(r.source, r.target or "", [("x-eser", r.title), ("x-durum", "onaylı" if r.status == "onaylandi" else "çevrildi")],
                 r.approved_by or r.translated_by, r.updated_at)
        if external:
            for r in conn.execute(sa.select(TM).where(TM.c.tenant_id == tenant, TM.c.source_lang == src,
                                                      TM.c.target_lang == tgt).order_by(TM.c.created_at)).all():
                unit(r.source, r.target, [("x-kaynak-dosya", r.origin)], r.created_by, r.created_at)
    head = ('<?xml version="1.0" encoding="UTF-8"?>\n<tmx version="1.4">\n'
            f'<header creationtool="ZEKİ AI" creationtoolversion="1" segtype="sentence" o-tmf="ZEKI" adminlang="tr" '
            f'srclang="{src}" datatype="plaintext" creationdate="{_stamp(tr._now())}"/>\n<body>')
    body = head + "\n" + "\n".join(units) + "\n</body>\n</tmx>\n"
    return body.encode("utf-8"), f"ceviri-bellegi-{src}-{tgt}.tmx", len(units)


# ============================================================================================ uçlar

def register(app: Any, ctx: Callable[[Any], tuple[Any, str, str, bool]], call: Callable[..., Any],
             attachment: Callable[[bytes, str, str], Any], audit: Callable[..., None]) -> None:
    """Uçları köprüye ekler. `ctx` = app.py `_tr`, `call` = `_tr_call`, `attachment` = `_attachment`,
    `audit` = `admin.audit`. Yetki desenleri access.py FEATURE_RULES'ta."""
    from fastapi import HTTPException, Request
    from starlette.concurrency import run_in_threadpool

    base = "/api/v1/editorial/translation"

    def _ctx(request: Request) -> tuple[Any, str, str, bool]:
        out = ctx(request)
        ensure(out[0])
        return out

    async def _body(request: Request, limit: int) -> bytes:
        if int(request.headers.get("content-length") or 0) > limit:
            raise HTTPException(status_code=413, detail={"code": "TRANSLATION",
                                                         "message": f"Dosya {limit // (1024 * 1024)} MB sınırını aşıyor."})
        return await request.body()

    @app.get(f"{base}/memory")
    def tr_memory(request: Request) -> dict[str, Any]:
        engine, tenant, _user, _ = _ctx(request)
        return memory_summary(engine, tenant)

    @app.put(f"{base}/memory/import")
    async def tr_memory_import(request: Request, src: str = "", tgt: str = "", filename: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(_ctx, request)
        data = await _body(request, TMX_MAX_BYTES)
        out = await run_in_threadpool(call, import_tmx, engine, tenant, user, src, tgt, filename, data)
        audit(engine, user, "upload", "translation_tm", None, filename, {"src": src, "tgt": tgt, **out})
        return out

    @app.delete(f"{base}/memory")
    def tr_memory_delete(request: Request, src: str = "", tgt: str = "", origin: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = _ctx(request)
        n = call(delete_origin, engine, tenant, src, tgt, origin)
        audit(engine, user, "delete", "translation_tm", None, origin, {"src": src, "tgt": tgt, "deleted": n})
        return {"deleted": n}

    @app.get(f"{base}/memory/export.tmx")
    def tr_memory_export(request: Request, src: str = "", tgt: str = "", external: int = 0) -> Any:
        engine, tenant, user, _ = _ctx(request)
        body, name, n = call(export_tmx, engine, tenant, src, tgt, bool(external))
        audit(engine, user, "export", "translation_tm", None, name, {"src": src, "tgt": tgt, "units": n, "external": bool(external)})
        return attachment(body, name, "application/x-tmx+xml")

    @app.put(f"{base}/terms/import.tbx")
    async def tr_terms_import_tbx(request: Request, src: str = "", tgt: str = "", filename: str = "") -> dict[str, Any]:
        engine, tenant, user, _ = await run_in_threadpool(_ctx, request)
        data = await _body(request, TBX_MAX_BYTES)
        out = await run_in_threadpool(call, import_tbx, engine, tenant, user, src, tgt, data)
        audit(engine, user, "upload", "translation_terms_tbx", None, filename, {"src": src, "tgt": tgt, **out})
        return out

    @app.get(f"{base}/terms/export.tbx")
    def tr_terms_export_tbx(request: Request, src: str = "", tgt: str = "") -> Any:
        engine, tenant, user, _ = _ctx(request)
        body, name = call(export_tbx, engine, tenant, src, tgt)
        audit(engine, user, "export", "translation_terms_tbx", None, name, {"src": src, "tgt": tgt})
        return attachment(body, name, "application/x-tbx+xml")
