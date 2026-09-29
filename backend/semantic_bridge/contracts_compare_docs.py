"""Sözleşme karşılaştırma — belge metni madde madde (`/telif-sozlesme/karsilastirma`, «Belge karşılaştırma» sekmesi).

Belge arşivi dört kaynaktan oluşur, hepsi yalnız okunur (kaynağa yazılmaz):

- **CRM ekleri**: sözleşme kaydına eklenmiş dosyalar (`AnnotationBase`, nesne türü `new_sozlesme`'nin kodu `EntityView`'dan
  okunur). 2026-09-29'da 9 ek vardı: 1 PDF, 8 telefon fotoğrafı (HEIC — okunamayan biçim, listede nedeniyle görünür).
- **Portal belgeleri**: sözleşme sayfasında «belgeden şart çıkar» ile yüklenenler (`semantic_contract_extracts`).
- **Şablonlar**: şablon kütüphanesi (metin ya da Word); `{{alan}}` yer tutucusu «doldurulacak alan» sayılır, fark sayılmaz.
- **Karşılaştırma için yüklenen**: bu ekrandan yüklenen belge (`semantic_contract_compare_docs`, dosya
  `CONTRACT_DOCS_DIR/<kiracı>/karsilastirma/`). Yükleyen ya da yetkili siler.

Belge ortak okuma hattıyla okunur (`doc_read`: PDF metni, Word, taranmış sayfa OCR). Metin maddelere bölünür (`split`):
«MADDE 5», «Madde 5 —», «5.», «5.1», «Article 5», başlık satırı; hiç numara yoksa boş satırla ayrılan paragraflar. Okuma
ve bölme sonucu belge başına bir kez saklanır (içerik özeti aynıysa yeniden okunmaz).

İki belge madde sırası korunarak eşlenir (`align`: benzerlik eşiğinin üstündeki çiftler için en yüksek toplam benzerlik;
sırası değişmiş madde ikinci geçişte «yeri değişmiş» olur). Eşlenen maddede kelime düzeyinde fark çıkarılır; sayı farkı
ayrıca işaretlenir. Bir belge bütün arşivle de karşılaştırılır (`against_corpus`): her maddenin arşivdeki en yakın
karşılığı; hiçbir belgede eşiği geçen karşılığı yoksa «arşivde yok». Model kullanılmaz.
"""
from __future__ import annotations

import base64
import difflib
import hashlib
import json
import logging
import os
import re
import threading
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Optional

import sqlalchemy as sa

from semantic_bridge import doc_read as DR

log = logging.getLogger("semantic.contracts_compare")

_md = sa.MetaData()

DOCS = sa.Table(
    "semantic_contract_compare_docs", _md,
    sa.Column("id", sa.String(32), primary_key=True),
    sa.Column("tenant_id", sa.String(80), nullable=False, index=True),
    sa.Column("ref", sa.String(120), nullable=False),              # crm:<ek> | belge:<okuma> | sablon:<id>:<sürüm> | yukleme:<id>
    sa.Column("kind", sa.String(12), nullable=False),
    sa.Column("title", sa.String(300), nullable=False),
    sa.Column("filename", sa.String(300)),
    sa.Column("bytes", sa.Integer),
    sa.Column("sha256", sa.String(64)),
    sa.Column("path", sa.String(600)),                             # yalnız karşılaştırma için yüklenen belgede
    sa.Column("contract_no", sa.String(120)),
    sa.Column("status", sa.String(16), nullable=False),           # bekliyor | okunuyor | hazir | hata
    sa.Column("error", sa.Text),
    sa.Column("clauses_json", sa.Text),
    sa.Column("reading_json", sa.Text),
    sa.Column("created_by", sa.String(120), nullable=False),
    sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    sa.Column("finished_at", sa.DateTime(timezone=True)),
    sa.UniqueConstraint("tenant_id", "ref", name="uq_contract_compare_docs_ref"),
)

KINDS = {"crm": "CRM eki", "belge": "Portal belgesi", "sablon": "Şablon", "yukleme": "Karşılaştırma için yüklenen"}
STATUS = {"bekliyor": "Okunmadı", "okunuyor": "Okunuyor", "hazir": "Okundu", "hata": "Okunamadı"}
ALLOWED = ("pdf", "docx", "odt", "txt") + tuple(DR.IMAGES)
FILE_MAX = 10 * 1024 * 1024

#: Eşleme eşikleri (0–1): `MATCH` altındaki iki madde eşlenmez; `SAME` ve üstü (sayılar da aynıysa) «aynı»;
#: `MOVED` sırası tutmayan iki maddenin «yeri değişmiş» sayılması için gereken benzerlik.
MATCH, SAME, MOVED = 0.45, 0.97, 0.60

_ready_lock = threading.Lock()
_ensured: set[int] = set()


class DocError(ValueError):
    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    with _ready_lock:
        if id(engine) in _ensured:
            return
        _md.create_all(engine, checkfirst=True)
        _ensured.add(id(engine))


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(v: Any) -> Optional[str]:
    return v.isoformat() if isinstance(v, datetime) else (str(v) if v else None)


# ================================================================================ maddelere bölme

_HEAD = re.compile(
    r"^\s*(?:#{1,6}\s*)?(?:"
    r"(?P<madde>(?:madde|maddesi|md\.?|article|clause|section|bölüm|bolum)\s*[:\-–—.]?\s*(?P<n1>\d{1,3}(?:\.\d{1,3})*))"
    r"|(?P<n2>\d{1,2}(?:\.\d{1,2}){0,3})\s*[.)\-–—]\s+(?=\S)"
    r")",
    re.I,
)
_PLACEHOLDER = re.compile(r"\{\{\s*[a-z0-9_.]+\s*\}\}")
_TOKEN = re.compile(r"\{\{\s*[a-z0-9_.]+\s*\}\}|%?\d+(?:[.,]\d+)*%?|[^\W\d_]+", re.U)
_NUM = re.compile(r"^%?\d+(?:[.,]\d+)*%?$")


def _page_lines(pages: list[dict[str, Any]]) -> list[tuple[str, str]]:
    out = []
    for p in pages:
        for line in str(p.get("metin") or "").splitlines():
            out.append((str(p.get("sayfa") or ""), line.rstrip()))
    return out


def split(pages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Sayfa metinleri → maddeler [{no, baslik, metin, sayfa}]. Numaralı madde başı en az iki kez bulunursa ona göre
    bölünür (ilk maddeden önceki kısım «Giriş»); bulunmazsa boş satırla ayrılan paragraflar madde sayılır."""
    lines = _page_lines(pages)
    heads = [i for i, (_, ln) in enumerate(lines) if _HEAD.match(ln)]
    clauses: list[dict[str, Any]] = []
    if len(heads) >= 2:
        if heads[0] > 0:
            pre = "\n".join(ln for _, ln in lines[:heads[0]]).strip()
            if pre:
                clauses.append({"no": None, "baslik": "Giriş", "metin": pre, "sayfa": lines[0][0]})
        for k, i in enumerate(heads):
            j = heads[k + 1] if k + 1 < len(heads) else len(lines)
            m = _HEAD.match(lines[i][1])
            no = m.group("n1") or m.group("n2")
            rest = lines[i][1][m.end():].strip(" :-–—.\t")
            body = [ln for _, ln in lines[i + 1:j]]
            title = rest if rest and len(rest) <= 80 and body else None
            text = "\n".join(([rest] if rest and not title else []) + body).strip()
            clauses.append({"no": no, "baslik": title, "metin": text or rest, "sayfa": lines[i][0]})
    else:
        buf: list[str] = []
        page = None
        for pg, ln in lines + [("", "")]:
            if ln.strip():
                if not buf:
                    page = pg
                buf.append(ln)
            elif buf:
                clauses.append({"no": None, "baslik": None, "metin": "\n".join(buf).strip(), "sayfa": page})
                buf = []
    for n, c in enumerate(clauses, start=1):
        c["sira"] = n
        c["metin"] = c["metin"].strip()
    return [c for c in clauses if c["metin"] or c["baslik"]]


def tokens(text: str) -> list[str]:
    """Karşılaştırma birimi: katlanmış kelime, sayı (yüzde işaretiyle) ya da yer tutucu (`□`)."""
    out = []
    for t in _TOKEN.findall(text or ""):
        if t.startswith("{{"):
            out.append("□")
        elif _NUM.match(t):
            out.append(t.replace(",", ".").strip("."))
        else:
            f = DR.fold(t)
            if f:
                out.append(f)
    return out


def similarity(a: list[str], b: list[str]) -> float:
    """Sıra duyarlı benzerlik (0–1); yer tutucular sayılmaz."""
    a2 = [t for t in a if t != "□"]
    b2 = [t for t in b if t != "□"]
    if not a2 and not b2:
        return 1.0
    if not a2 or not b2:
        return 0.0
    return difflib.SequenceMatcher(None, a2, b2, autojunk=False).ratio()


def _numbers(toks: list[str]) -> list[str]:
    return [t for t in toks if _NUM.match(t)]


def word_diff(a_text: str, b_text: str) -> list[dict[str, str]]:
    """Kelime düzeyinde fark (a = incelenen, b = karşılaştırılan): eq | ins (yalnız a'da) | del (yalnız b'de) | fill
    (b'deki yer tutucunun a'daki karşılığı)."""
    a_raw = re.findall(r"\{\{\s*[a-z0-9_.]+\s*\}\}|\S+", a_text or "")
    b_raw = re.findall(r"\{\{\s*[a-z0-9_.]+\s*\}\}|\S+", b_text or "")
    a_key = [("□" if _PLACEHOLDER.fullmatch(t) else DR.fold(t) or t) for t in a_raw]
    b_key = [("□" if _PLACEHOLDER.fullmatch(t) else DR.fold(t) or t) for t in b_raw]
    ops = []
    for tag, i1, i2, j1, j2 in difflib.SequenceMatcher(None, a_key, b_key, autojunk=False).get_opcodes():
        if tag == "equal":
            ops.append({"op": "eq", "text": " ".join(a_raw[i1:i2])})
            continue
        b_part = b_raw[j1:j2]
        if b_part and all(_PLACEHOLDER.fullmatch(t) for t in b_part):
            ops.append({"op": "fill", "text": " ".join(a_raw[i1:i2]), "alan": " ".join(b_part)})
            continue
        if j2 > j1:
            ops.append({"op": "del", "text": " ".join(b_part)})
        if i2 > i1:
            ops.append({"op": "ins", "text": " ".join(a_raw[i1:i2])})
    merged: list[dict[str, str]] = []
    for o in ops:
        if merged and merged[-1]["op"] == o["op"] and o["op"] != "fill":
            merged[-1]["text"] += " " + o["text"]
        else:
            merged.append(o)
    return merged


def _prep(clauses: list[dict[str, Any]]) -> list[dict[str, Any]]:
    for c in clauses:
        if "_t" not in c:
            c["_t"] = tokens(((c.get("baslik") or "") + " " + (c.get("metin") or "")).strip())
    return clauses


def align(a: list[dict[str, Any]], b: list[dict[str, Any]]) -> list[tuple[Optional[int], Optional[int], float]]:
    """Sıra korunarak eşleme (en yüksek toplam benzerlik, eşik altı çift eşlenmez); sonra kalanlar arasında sırası
    değişmiş eşler. Dönüş: (a sırası | None, b sırası | None, benzerlik)."""
    _prep(a)
    _prep(b)
    n, m = len(a), len(b)
    sim = [[similarity(a[i]["_t"], b[j]["_t"]) for j in range(m)] for i in range(n)]
    score = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(n - 1, -1, -1):
        for j in range(m - 1, -1, -1):
            best = max(score[i + 1][j], score[i][j + 1])
            if sim[i][j] >= MATCH:
                best = max(best, sim[i][j] + score[i + 1][j + 1])
            score[i][j] = best
    pairs: list[tuple[Optional[int], Optional[int], float]] = []
    i = j = 0
    while i < n and j < m:
        if sim[i][j] >= MATCH and abs(score[i][j] - (sim[i][j] + score[i + 1][j + 1])) < 1e-9:
            pairs.append((i, j, sim[i][j]))
            i += 1
            j += 1
        elif score[i + 1][j] >= score[i][j + 1]:
            pairs.append((i, None, 0.0))
            i += 1
        else:
            pairs.append((None, j, 0.0))
            j += 1
    pairs += [(x, None, 0.0) for x in range(i, n)] + [(None, y, 0.0) for y in range(j, m)]
    # sırası değişmiş maddeler
    lone_a = [p[0] for p in pairs if p[1] is None]
    lone_b = [p[1] for p in pairs if p[0] is None]
    moved: dict[int, tuple[int, float]] = {}
    used_b: set[int] = set()
    for x in lone_a:
        cands = sorted(((sim[x][y], y) for y in lone_b if y not in used_b and sim[x][y] >= MOVED), reverse=True)
        if cands:
            s, y = cands[0]
            moved[x] = (y, s)
            used_b.add(y)
    out: list[tuple[Optional[int], Optional[int], float]] = []
    for x, y, s in pairs:
        if y is None and x in moved:
            out.append((x, moved[x][0], -moved[x][1]))      # eksi: yeri değişmiş
        elif x is None and y in used_b:
            continue
        else:
            out.append((x, y, s))
    return out


def _clause_out(c: Optional[dict[str, Any]]) -> Optional[dict[str, Any]]:
    if c is None:
        return None
    return {k: c.get(k) for k in ("sira", "no", "baslik", "metin", "sayfa")}


def diff(a: list[dict[str, Any]], b: list[dict[str, Any]], b_is_template: bool = False) -> dict[str, Any]:
    """İki belgenin madde madde farkı: aynı | degismis | yeri-degismis | eklenmis (yalnız incelenende) | cikarilmis
    (yalnız karşılaştırılanda). Değişmişte kelime farkı ve sayı farkı."""
    rows = []
    counts = {"ayni": 0, "degismis": 0, "yeri-degismis": 0, "eklenmis": 0, "cikarilmis": 0}
    for x, y, s in align(a, b):
        ca = a[x] if x is not None else None
        cb = b[y] if y is not None else None
        if ca is not None and cb is not None:
            moved = s < 0
            s = abs(s)
            na, nb = _numbers(ca["_t"]), _numbers(cb["_t"])
            numbers_same = na == nb or (b_is_template and not nb)
            ops = word_diff(ca["metin"], cb["metin"])
            only_fill = b_is_template and all(o["op"] in ("eq", "fill") for o in ops)
            if moved:
                status = "yeri-degismis"
            elif (s >= SAME and numbers_same) or only_fill:
                status = "ayni"                   # şablonda yalnız yer tutucular doldurulmuşsa da aynı
            else:
                status = "degismis"
            row = {"durum": status, "benzerlik": round(s, 3), "a": _clause_out(ca), "b": _clause_out(cb)}
            if status != "ayni" or only_fill:
                row["fark"] = ops
            if status != "ayni" and not numbers_same:
                row["sayilar"] = {"a": na, "b": nb}
        elif ca is not None:
            status = "eklenmis"
            row = {"durum": status, "benzerlik": 0.0, "a": _clause_out(ca), "b": None}
        else:
            status = "cikarilmis"
            row = {"durum": status, "benzerlik": 0.0, "a": None, "b": _clause_out(cb)}
        counts[status] += 1
        rows.append(row)
    return {"maddeler": rows, "sayim": counts, "esik": {"eslesme": MATCH, "ayni": SAME, "yeri": MOVED}}


def against_corpus(a: list[dict[str, Any]], corpus: list[tuple[dict[str, Any], list[dict[str, Any]]]]) -> dict[str, Any]:
    """Her maddenin arşivdeki en yakın karşılığı (belge başına en iyi madde). `corpus`: [(belge özeti, maddeler)]."""
    _prep(a)
    for _, cl in corpus:
        _prep(cl)
    rows = []
    counts = {"ayni": 0, "benzer": 0, "arsivde-yok": 0}
    for ca in a:
        best: list[tuple[float, dict[str, Any], dict[str, Any]]] = []
        ta = set(ca["_t"])
        for doc, cl in corpus:
            top = None
            for cb in cl:
                tb = cb["_t"]
                if ta and tb and len(ta & set(tb)) / max(1, len(ta | set(tb))) < MATCH / 2:
                    continue   # kelime kümesi bu kadar uzaksa sıra benzerliği eşiği geçemez
                s = similarity(ca["_t"], tb)
                if s >= MATCH and (top is None or s > top[0]):
                    top = (s, doc, cb)
            if top:
                best.append(top)
        best.sort(key=lambda t: -t[0])
        same_docs = sum(1 for s, _, cb in best if s >= SAME and _numbers(ca["_t"]) == _numbers(cb["_t"]))
        if not best:
            status = "arsivde-yok"
        elif same_docs:
            status = "ayni"
        else:
            status = "benzer"
        counts[status] += 1
        row: dict[str, Any] = {"durum": status, "a": _clause_out(ca), "ayniBelge": same_docs, "benzerBelge": len(best)}
        if best:
            s, doc, cb = best[0]
            row["enYakin"] = {"belge": doc, "madde": _clause_out(cb), "benzerlik": round(s, 3)}
            if status != "ayni":
                row["fark"] = word_diff(ca["metin"], cb["metin"])
        rows.append(row)
    return {"maddeler": rows, "sayim": counts, "belgeSayisi": len(corpus)}


# ================================================================================ arşiv

def crm_docs_sql(p: str) -> str:
    """CRM'de sözleşme kaydına eklenmiş dosyalar (gövde okunmaz; yalnız liste)."""
    return ("SELECT a.AnnotationId AS id, a.FileName AS ad, a.FileSize AS boyut, a.MimeType AS tur, a.CreatedOn AS tarih,"
            " s.new_name AS sozlesme, s.new_sozlesmeId AS sid"
            f" FROM {p}AnnotationBase a JOIN {p}new_sozlesmeBase s ON s.new_sozlesmeId = a.ObjectId"
            f" WHERE a.IsDocument = 1 AND a.ObjectTypeCode = (SELECT e.ObjectTypeCode FROM {p}EntityView e WHERE e.Name = 'new_sozlesme')"
            " ORDER BY a.CreatedOn DESC")


def crm_body_sql(p: str, annotation_id: str) -> str:
    g = _guid(annotation_id)
    return (f"SELECT a.FileName AS ad, a.DocumentBody AS govde, s.new_name AS sozlesme FROM {p}AnnotationBase a"
            f" LEFT JOIN {p}new_sozlesmeBase s ON s.new_sozlesmeId = a.ObjectId WHERE a.AnnotationId = '{g}'")


_GUID = re.compile(r"^[0-9a-fA-F]{8}-(?:[0-9a-fA-F]{4}-){3}[0-9a-fA-F]{12}$")
_HEX = re.compile(r"^[0-9a-f]{32}$")


def _guid(v: str) -> str:
    t = str(v or "").strip().strip("{}")
    if not _GUID.match(t):
        raise DocError("Belge kimliği geçerli değil.")
    return t.lower()


def _row_out(r: Any) -> dict[str, Any]:
    clauses = json.loads(r.clauses_json) if r.clauses_json else None
    return {"ref": r.ref, "kind": r.kind, "kindLabel": KINDS.get(r.kind, r.kind), "title": r.title, "filename": r.filename,
            "bytes": r.bytes, "contractNo": r.contract_no, "status": r.status, "statusLabel": STATUS.get(r.status, r.status),
            "error": r.error, "maddeSayisi": len(clauses) if clauses is not None else None,
            "okuma": json.loads(r.reading_json) if r.reading_json else None, "createdBy": r.created_by,
            "createdAt": _iso(r.created_at), "finishedAt": _iso(r.finished_at)}


def stored(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    ensure(engine)
    with engine.connect() as c:
        rows = c.execute(sa.select(DOCS).where(DOCS.c.tenant_id == tenant)).all()
    return {r.ref: r for r in rows}


def archive(engine: sa.engine.Engine, tenant: str, crm_rows: list[dict[str, Any]], extracts: list[Any],
            templates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Arşivin bütün belgeleri ve okunma durumu (okunmamış olan «Okunmadı» görünür; sessizce atlanmaz)."""
    have = stored(engine, tenant)
    out = []

    def item(ref: str, kind: str, title: str, filename: Optional[str], size: Optional[int], no: Optional[str],
             created: Any, readable: bool, why: Optional[str] = None) -> dict[str, Any]:
        r = have.get(ref)
        if r is not None:
            d = _row_out(r)
            # Kaynağın kendi bilgisi (ad, boyut, sözleşme) önce gelir; okuma kaydından durum, madde ve okuma özeti
            d.update({k: v for k, v in (("title", title), ("filename", filename), ("bytes", size), ("contractNo", no)) if v})
        else:
            d = {"ref": ref, "kind": kind, "kindLabel": KINDS[kind], "title": title, "filename": filename, "bytes": size,
                 "contractNo": no, "status": "bekliyor", "statusLabel": STATUS["bekliyor"], "error": None, "maddeSayisi": None,
                 "okuma": None, "createdBy": None, "createdAt": _iso(created), "finishedAt": None}
        d["okunabilir"] = readable
        if not readable:
            d["error"] = why
            d["statusLabel"] = "Okunamaz biçim"
        return d

    for r in crm_rows:
        name = str(r.get("ad") or "ek")
        ok = DR.ext_of(name) in ALLOWED
        out.append(item(f"crm:{str(r.get('id')).strip('{}').lower()}", "crm", name, name, r.get("boyut"),
                        r.get("sozlesme"), r.get("tarih"), ok,
                        None if ok else f"Bu dosya türü okunmuyor (.{DR.ext_of(name) or '?'}); desteklenen: {', '.join(ALLOWED)}."))
    for e in extracts:
        out.append(item(f"belge:{e.id}", "belge", e.filename, e.filename, e.bytes, e.contract_key, e.created_at, True))
    for t in templates:
        out.append(item(f"sablon:{t['id']}:{t['version']}", "sablon", t["name"], t.get("docxName"), None, None, t.get("updatedAt"), True))
    for ref, r in have.items():
        if r.kind == "yukleme":
            d = _row_out(r)
            d["okunabilir"] = True
            out.append(d)
    order = {"yukleme": 0, "belge": 1, "crm": 2, "sablon": 3}
    out.sort(key=lambda d: (order.get(d["kind"], 9), str(d.get("createdAt") or "")), reverse=False)
    return out


def claim(engine: sa.engine.Engine, tenant: str, user: str, ref: str, kind: str, title: str, *, filename: Optional[str] = None,
          contract_no: Optional[str] = None) -> Optional[dict[str, Any]]:
    """Okuma sırası: satır yoksa açılır, «okunuyor»a çekilir. Zaten okunuyorsa None (ikinci iş başlamaz)."""
    ensure(engine)
    with engine.begin() as c:
        r = c.execute(sa.select(DOCS).where(DOCS.c.tenant_id == tenant, DOCS.c.ref == ref).with_for_update()).first()
        if r is None:
            c.execute(DOCS.insert().values(id=uuid.uuid4().hex, tenant_id=tenant, ref=ref, kind=kind, title=title[:300],
                                           filename=(filename or None) and filename[:300], contract_no=contract_no,
                                           status="okunuyor", created_by=user, created_at=_now()))
        elif r.status == "okunuyor":
            return None
        else:
            c.execute(sa.update(DOCS).where(DOCS.c.id == r.id).values(status="okunuyor", error=None, finished_at=None))
        return _row_out(c.execute(sa.select(DOCS).where(DOCS.c.tenant_id == tenant, DOCS.c.ref == ref)).first())


def finish(engine: sa.engine.Engine, tenant: str, ref: str, *, clauses: Optional[list[dict[str, Any]]] = None,
           reading: Optional[dict[str, Any]] = None, sha: Optional[str] = None, size: Optional[int] = None,
           error: Optional[str] = None, title: Optional[str] = None, filename: Optional[str] = None,
           contract_no: Optional[str] = None) -> None:
    vals: dict[str, Any] = {"status": "hata" if error else "hazir", "error": error, "finished_at": _now()}
    if title:
        vals["title"] = title[:300]
    if filename:
        vals["filename"] = filename[:300]
    if contract_no:
        vals["contract_no"] = contract_no[:120]
    if clauses is not None:
        vals["clauses_json"] = json.dumps([_clause_out(c) for c in clauses], ensure_ascii=False)
    if reading is not None:
        vals["reading_json"] = json.dumps(reading, ensure_ascii=False, default=str)
    if sha:
        vals["sha256"] = sha
    if size is not None:
        vals["bytes"] = size
    with engine.begin() as c:
        c.execute(sa.update(DOCS).where(DOCS.c.tenant_id == tenant, DOCS.c.ref == ref).values(**vals))


def reset_stale(engine: sa.engine.Engine) -> int:
    ensure(engine)
    with engine.begin() as c:
        return c.execute(sa.update(DOCS).where(DOCS.c.status == "okunuyor").values(
            status="hata", error="Okuma sürerken sunucu yeniden başladı; yeniden okutun.", finished_at=_now())).rowcount


def read_clauses(engine: sa.engine.Engine, tenant: str, ref: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    ensure(engine)
    with engine.connect() as c:
        r = c.execute(sa.select(DOCS).where(DOCS.c.tenant_id == tenant, DOCS.c.ref == ref)).first()
    if r is None or r.status != "hazir" or not r.clauses_json:
        raise DocError("Belge henüz okunmadı; önce okutun.", 409)
    return _row_out(r), json.loads(r.clauses_json)


def ready_corpus(engine: sa.engine.Engine, tenant: str, exclude_ref: str) -> list[tuple[dict[str, Any], list[dict[str, Any]]]]:
    """Arşivin okunmuş belgeleri (incelenen belge ve içeriği birebir aynı olanlar hariç)."""
    ensure(engine)
    with engine.connect() as c:
        rows = c.execute(sa.select(DOCS).where(DOCS.c.tenant_id == tenant, DOCS.c.status == "hazir")).all()
    me = next((r for r in rows if r.ref == exclude_ref), None)
    out = []
    for r in rows:
        if r.ref == exclude_ref or (me is not None and me.sha256 and r.sha256 == me.sha256) or not r.clauses_json:
            continue
        d = _row_out(r)
        out.append(({"ref": d["ref"], "title": d["title"], "kindLabel": d["kindLabel"], "contractNo": d["contractNo"]},
                    json.loads(r.clauses_json)))
    return out


def read_bytes(filename: str, data: bytes) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Belge baytları → maddeler ve okuma özeti."""
    reading = DR.read(filename, data, allowed=ALLOWED)
    pages = reading.pages
    clauses = split(pages)
    if not clauses:
        why = " ".join(reading.errors)
        raise DocError("Belgeden metin okunamadı." + (f" {why}" if why else ""))
    return clauses, reading.summary()


def template_clauses(body: str, docx: Optional[bytes], docx_name: Optional[str]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Şablon: Word dosyası varsa o, yoksa metin (yer tutucular korunur)."""
    if docx:
        return read_bytes(docx_name or "sablon.docx", docx)
    text = re.sub(r"^#{1,6}\s*", "", body or "", flags=re.M)
    clauses = split([{"sayfa": "1", "metin": text, "okuma": DR.METIN}])
    if not clauses:
        raise DocError("Şablonun metni boş.")
    return clauses, {"sayfa": 1, "not": None}


def crm_bytes(run: Callable[[str], list[dict[str, Any]]], prefix: str, ref: str) -> tuple[str, bytes, Optional[str]]:
    """CRM ekinin adı, içeriği ve bağlı olduğu sözleşmenin numarası."""
    rows = run(crm_body_sql(prefix, ref.split(":", 1)[1]))
    if not rows or not rows[0].get("govde"):
        raise DocError("CRM'deki ekin içeriği okunamadı.", 404)
    try:
        return (str(rows[0].get("ad") or "ek"), base64.b64decode(rows[0]["govde"]),
                str(rows[0].get("sozlesme") or "").strip() or None)
    except (ValueError, TypeError) as e:
        raise DocError("CRM'deki ekin içeriği çözülemedi.") from e


# ================================================================================ karşılaştırma için yüklenen

def _upload_root() -> str:
    return os.path.join(os.environ.get("CONTRACT_DOCS_DIR", "/data/nanobaseai/bi/var/contract-docs"))


def upload(engine: sa.engine.Engine, tenant: str, user: str, filename: str, data: bytes) -> dict[str, Any]:
    ensure(engine)
    name = os.path.basename(str(filename or "").replace("\\", "/")).strip()[:300]
    if len(data) > FILE_MAX:
        raise DocError("Belge 10 MB sınırını aşıyor.", 413)
    try:
        DR.check(name, data, ALLOWED)
    except DR.ReadError as e:
        raise DocError(str(e), e.status) from None
    did = uuid.uuid4().hex
    folder = os.path.join(_upload_root(), tenant, "karsilastirma")
    path = os.path.join(folder, f"{did}.{DR.ext_of(name)}")
    try:
        os.makedirs(folder, exist_ok=True)
        with open(path, "wb") as fh:
            fh.write(data)
    except OSError as e:
        log.error("karşılaştırma belgesi yazılamadı (%s): %s", path, e)
        raise DocError("Belge sunucuya kaydedilemedi; yöneticiye bildirin.", 503) from e
    ref = f"yukleme:{did}"
    with engine.begin() as c:
        c.execute(DOCS.insert().values(id=did, tenant_id=tenant, ref=ref, kind="yukleme", title=name, filename=name,
                                       bytes=len(data), sha256=hashlib.sha256(data).hexdigest(), path=path,
                                       status="bekliyor", created_by=user, created_at=_now()))
        return _row_out(c.execute(sa.select(DOCS).where(DOCS.c.id == did)).first())


def upload_path(engine: sa.engine.Engine, tenant: str, ref: str) -> tuple[str, str]:
    ensure(engine)
    with engine.connect() as c:
        r = c.execute(sa.select(DOCS).where(DOCS.c.tenant_id == tenant, DOCS.c.ref == ref)).first()
    if r is None or r.kind != "yukleme" or not r.path or not os.path.isfile(r.path):
        raise DocError("Belge bulunamadı.", 404)
    return r.path, r.filename or "belge"


def forget(engine: sa.engine.Engine, tenant: str, ref: str) -> dict[str, Any]:
    """Yüklenen belge silinir (dosya + satır); öbür kaynakların okuması silinir (kaynağın kendisine dokunulmaz)."""
    ensure(engine)
    with engine.begin() as c:
        r = c.execute(sa.select(DOCS).where(DOCS.c.tenant_id == tenant, DOCS.c.ref == ref)).first()
        if r is None:
            raise DocError("Belge bulunamadı.", 404)
        if r.status == "okunuyor":
            raise DocError("Okuma sürerken silinmez; bitince silin.", 409)
        c.execute(DOCS.delete().where(DOCS.c.id == r.id))
    if r.path:
        try:
            os.remove(r.path)
        except OSError as e:
            log.warning("karşılaştırma belgesi diskten silinemedi (%s): %s", r.path, e)
    return {"ref": r.ref, "title": r.title, "kind": r.kind}


def docs_stmt(tenant: str) -> sa.Select:
    return sa.select(DOCS.c.ref, DOCS.c.kind, DOCS.c.title, DOCS.c.status, DOCS.c.sha256, DOCS.c.finished_at).where(
        DOCS.c.tenant_id == tenant)


__all__ = ["DOCS", "DocError", "KINDS", "STATUS", "against_corpus", "align", "archive", "claim", "diff", "finish",
           "forget", "read_bytes", "read_clauses", "ready_corpus", "split", "template_clauses", "tokens", "upload", "word_diff"]
