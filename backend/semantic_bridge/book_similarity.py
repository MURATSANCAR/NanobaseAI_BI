"""Ortak yapı taşı 5 + öneri 9 — kitap benzerliği araması (gömme dizini; docs/analiz/ai-firsatlari/README.md).

**Dizin** (`semantic_book_embeddings`): CRM'deki etkin kitaplar (`new_kitapBase`, `statecode = 0 AND new_Tip = 1`;
set, dergi, e-kitap hariç — M39 `own_books_sql` ile aynı kapsam) için tek metin: ad + kitaplık + web kategorileri +
türler + temalar (`new_new_kitap_new_temaBase`) + arka kapak metni (`new_ozet`, HTML temizlenmiş; boşsa kitap spotu).
Yazar adı bilerek metne girmez: aynı yazarın kitapları zaten başka yoldan bulunur, gömme konu benzerliği içindir.
Metin sunucudaki gömme servisine (`BI_EMBED_URL`; destek SSS'nin kullandığı servis) gönderilir, vektör birim uzunluğa
indirgenip float32 olarak saklanır. **Artımlı:** her kitabın metninin özeti (sha256) saklanır; metin değişmeyen kitap
yeniden gömülmez; CRM'de etkin olmaktan çıkan kitap dizinde `aktif = false` olur (silinmez).

**Arama** `similar_books(engine, tenant, stok_kodu | kitap_id | metin, n, süzgeç)`: sorgu kitabın saklı vektörü (ya da
serbest metnin gömmesi) ile bütün etkin kitapların kosinüs benzerliği; en yakın `n` kitap. **Benzerlik yalnız
sıralamadır:** ekranlarda puan değil sıra ve gerekçe (ortak kitaplık / kategori / tema) gösterilir; satış rakamları her
ekranda kendi SQL'inden gelir. Model yalnız metni vektöre çevirir; karar ya da rakam üretmez. Emsal seçimi insandadır.

Kullananlar: M15 yeni kitap planında «emsal adayı» (emsali girilmemiş kitaba), M39 «Emsal bul» aday genişletme, SEO
«Benzer kitaplar» ek aday, M1 başvuruda «katalogda benzer kitaplar». Zamanlayıcı `timas-book-similar.timer` (gece)
`POST /api/v1/books/similar/run-due`'yu çağırır.

Saf hesaplar (metin kurma, vektör kodlama, sıralama) veritabanından ve ağdan bağımsızdır ve sınanır. numpy varsa
matris çarpımı, yoksa saf Python (15 bin kitapta sorgu başına ~0,5 sn).
"""
from __future__ import annotations

import base64
import hashlib
import html as _html
import logging
import math
import operator
import os
import re
import threading
import time
from array import array
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional

import sqlalchemy as sa

log = logging.getLogger("semantic.book_similarity")

_md = sa.MetaData()

EMBEDDINGS = sa.Table(
    "semantic_book_embeddings", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("kitap_id", sa.String(40), primary_key=True),      # CRM new_kitapId (büyük harf)
    sa.Column("stok_kodu", sa.String(60), index=True),
    sa.Column("ad", sa.String(400), nullable=False),
    sa.Column("yazar", sa.String(400)),
    sa.Column("kitaplik", sa.String(200)),
    sa.Column("kategori", sa.String(500)),
    sa.Column("turler", sa.String(500)),
    sa.Column("temalar", sa.String(1000)),
    sa.Column("metin_ozeti", sa.String(64), nullable=False),      # gömülen metnin sha256'sı (artımlı karşılaştırma)
    sa.Column("ozet_var", sa.Boolean, nullable=False, default=False),
    sa.Column("boyut", sa.Integer, nullable=False),
    sa.Column("vektor", sa.Text, nullable=False),                  # birim vektör, float32, base64
    sa.Column("aktif", sa.Boolean, nullable=False, default=True),
    sa.Column("crm_degisme", sa.String(19)),
    sa.Column("guncellendi_at", sa.DateTime(timezone=True), nullable=False),
)
STATE = sa.Table(
    "semantic_book_embed_state", _md,
    sa.Column("tenant_id", sa.String(80), primary_key=True),
    sa.Column("key", sa.String(40), primary_key=True),
    sa.Column("value", sa.Text, nullable=False),
    sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
)

_ready: set[int] = set()
_lock = threading.Lock()
CRM_FILE_DEFAULT = "/data/nanobaseai/bi/secrets/crm-mssql-connection.json"
SOURCE_NOTE = ("Benzerlik: CRM kitap kartının adı, kitaplığı, kategorileri, türleri, temaları ve arka kapak metninden "
               "anlam benzerliği (yalnız sıralama). Satış rakamları benzerlikten bağımsız, her ekranda ayrıca okunur.")

Embed = Callable[[list[str]], list[list[float]]]


class SimilarityError(ValueError):
    def __init__(self, message: str, status: int = 422):
        super().__init__(message)
        self.status = status


def ensure(engine: sa.engine.Engine) -> None:
    with _lock:
        if id(engine) in _ready:
            return
        from semantic_layer.store import schema_stamp
        schema_stamp.create_all(_md, engine)
        _ready.add(id(engine))


def now() -> datetime:
    return datetime.now(timezone.utc)


def settings() -> dict[str, Any]:
    from semantic_bridge import admin as admin_mod

    def num(key: str, default: int, lo: int, hi: int) -> int:
        try:
            return max(lo, min(hi, int(admin_mod.conf(key) or default)))
        except ValueError:
            return default

    return {"textChars": num("BOOK_SIMILAR_TEXT_CHARS", 3000, 200, 20000), "batch": num("BOOK_SIMILAR_BATCH", 32, 1, 512)}


# ================================================================================ gömme servisi


def embedder() -> Optional[Embed]:
    """Sunucudaki gömme servisi (destek SSS ile aynı: `BI_EMBED_URL`); tanımlı değilse None."""
    url = os.environ.get("BI_EMBED_URL", "").strip()
    if not url:
        return None
    from semantic_layer.runtime.table_router import embed_request

    key = os.environ.get("BI_EMBED_API_KEY") or os.environ.get("CONTRACT_API_KEY", "")
    timeout = float(os.environ.get("BOOK_SIMILAR_EMBED_TIMEOUT_SEC", "120") or 120)
    return lambda texts: embed_request(url, texts, key, timeout)


# ================================================================================ saf yardımcılar

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def clean(v: Any) -> str:
    """HTML etiketi ve varlıkları temizlenmiş, tek boşluklu metin."""
    if v is None:
        return ""
    return _WS.sub(" ", _html.unescape(_TAG.sub(" ", str(v)))).strip()


def guid(v: Any) -> str:
    return str(v or "").strip().strip("{}").upper()


def book_text(b: dict[str, Any], max_chars: int) -> str:
    """Gömülecek tek metin (yazar hariç). Alanlar etiketli: model alanı ayırt eder, boş alan yazılmaz."""
    parts = [clean(b.get("ad"))]
    for label, key in (("Kitaplık", "kitaplik"), ("Kategori", "kategori"), ("Tür", "turler"), ("Tema", "temalar")):
        v = clean(b.get(key))
        if v:
            parts.append(f"{label}: {v}")
    body = clean(b.get("ozet")) or clean(b.get("spot"))
    if body:
        parts.append(body)
    text = ". ".join(p for p in parts if p)
    if len(text) > max_chars:
        cut = text[:max_chars]
        j = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
        text = cut[:j + 1] if j > max_chars * 0.6 else cut
    return text


def digest(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def unit(vec: Iterable[float]) -> array:
    a = array("f", (float(x) for x in vec))
    n = math.sqrt(sum(x * x for x in a))
    if n <= 0:
        raise SimilarityError("Gömme servisi boş vektör döndürdü.", 502)
    return array("f", (x / n for x in a))


def encode(vec: array) -> str:
    return base64.b64encode(vec.tobytes()).decode("ascii")


def decode(s: str) -> array:
    a = array("f")
    a.frombytes(base64.b64decode(s))
    return a


def _dot(a: array, b: array) -> float:
    return sum(map(operator.mul, a, b))


def token_set(*values: Any) -> set[str]:
    """Gerekçe için karşılaştırılan etiketler (kitaplık, kategori, tür, tema): virgül/noktalı virgülle ayrılır."""
    out = set()
    for v in values:
        for part in re.split(r"[;,|/>]+", clean(v)):
            p = part.strip()
            if len(p) >= 2:
                out.add(p)
    return out


def _fold(s: str) -> str:
    return s.replace("İ", "i").replace("I", "ı").lower()


def reasons(q: dict[str, Any], c: dict[str, Any]) -> list[str]:
    """Kurallı gerekçe: sorgu kitabıyla ortak kitaplık, kategori, tür ve temalar (puan gösterilmez)."""
    g = []
    if q.get("kitaplik") and _fold(q["kitaplik"]) == _fold(c.get("kitaplik") or ""):
        g.append(f"aynı kitaplık ({c['kitaplik']})")
    for label, key in (("ortak kategori", "kategori"), ("ortak tür", "turler"), ("ortak tema", "temalar")):
        a = {_fold(x): x for x in token_set(q.get(key))}
        b = {_fold(x) for x in token_set(c.get(key))}
        common = [a[k] for k in sorted(set(a) & b)]
        if common:
            g.append(f"{label}: " + ", ".join(common[:4]))
    return g


# ================================================================================ bellekteki dizin


class _Index:
    """Kiracının etkin vektörleri; tablo değişince (satır sayısı + son güncelleme) yeniden yüklenir."""

    def __init__(self) -> None:
        self.lock = threading.Lock()
        self.key: Optional[tuple] = None
        self.rows: list[dict[str, Any]] = []
        self.vecs: list[array] = []
        self.matrix: Any = None
        self.by_id: dict[str, int] = {}
        self.by_code: dict[str, int] = {}


_indexes: dict[tuple[int, str], _Index] = {}


def _fingerprint(c: Any, tenant: str) -> tuple:
    E = EMBEDDINGS.c
    r = c.execute(sa.select(sa.func.count(), sa.func.max(E.guncellendi_at)).where(E.tenant_id == tenant, E.aktif.is_(True))).first()
    return (int(r[0] or 0), str(r[1]))


def load_index(engine: sa.engine.Engine, tenant: str) -> _Index:
    ensure(engine)
    idx = _indexes.setdefault((id(engine), tenant), _Index())
    with idx.lock:
        with engine.connect() as c:
            fp = _fingerprint(c, tenant)
            if idx.key == fp:
                return idx
            rows = c.execute(sa.select(EMBEDDINGS).where(EMBEDDINGS.c.tenant_id == tenant, EMBEDDINGS.c.aktif.is_(True))
                             .order_by(EMBEDDINGS.c.kitap_id)).mappings().all()
        idx.rows = [{k: r[k] for k in ("kitap_id", "stok_kodu", "ad", "yazar", "kitaplik", "kategori", "turler", "temalar",
                                       "ozet_var")} for r in rows]
        idx.vecs = [decode(r["vektor"]) for r in rows]
        idx.by_id = {r["kitap_id"]: i for i, r in enumerate(idx.rows)}
        idx.by_code = {str(r["stok_kodu"]).strip().upper(): i for i, r in enumerate(idx.rows) if r.get("stok_kodu")}
        idx.matrix = None
        try:
            import numpy as np  # noqa: F401 — varsa hızlı yol

            if idx.vecs:
                idx.matrix = np.frombuffer(b"".join(v.tobytes() for v in idx.vecs), dtype=np.float32).reshape(len(idx.vecs), -1)
        except Exception:  # noqa: BLE001 — numpy yoksa saf Python
            idx.matrix = None
        idx.key = fp
        return idx


def scores(idx: _Index, q: array) -> list[float]:
    if idx.matrix is not None:
        import numpy as np

        return (idx.matrix @ np.frombuffer(q.tobytes(), dtype=np.float32)).tolist()
    return [_dot(v, q) for v in idx.vecs]


def rank(rows: list[dict[str, Any]], sims: list[float], n: int, exclude: set[int], keep: Optional[Callable[[dict[str, Any]], bool]] = None) -> list[tuple[int, float]]:
    """Benzerliğe göre ilk `n` (eşitlikte kitap kimliği; kararlı sıra). `exclude`: dizin sırası; `keep`: süzgeç."""
    order = sorted((i for i in range(len(rows)) if i not in exclude and (keep is None or keep(rows[i]))),
                   key=lambda i: (-sims[i], rows[i]["kitap_id"]))
    return [(i, sims[i]) for i in order[:max(0, n)]]


# ================================================================================ arama


def status(engine: sa.engine.Engine, tenant: str) -> dict[str, Any]:
    ensure(engine)
    E = EMBEDDINGS.c
    with engine.connect() as c:
        total, last = c.execute(sa.select(sa.func.count(), sa.func.max(E.guncellendi_at)).where(E.tenant_id == tenant)).first()
        active = c.execute(sa.select(sa.func.count()).where(E.tenant_id == tenant, E.aktif.is_(True))).scalar()
        run = c.execute(sa.select(STATE.c.value).where(STATE.c.tenant_id == tenant, STATE.c.key == "son_kosu")).scalar()
    import json

    return {"kitap": int(active or 0), "toplam": int(total or 0), "guncellendi": last.isoformat() if last else None,
            "sonKosu": json.loads(run) if run else None, "gommeServisi": bool(os.environ.get("BI_EMBED_URL", "").strip())}


def similar_books(engine: sa.engine.Engine, tenant: str, *, stok_kodu: Optional[str] = None, kitap_id: Optional[str] = None,
                  metin: Optional[str] = None, n: int = 10, suzgec: Optional[dict[str, Any]] = None,
                  embed: Optional[Embed] = None) -> dict[str, Any]:
    """En yakın `n` kitap. Sorgu: dizindeki bir kitap (stok kodu ya da CRM kimliği) ya da serbest metin (başvuru özeti,
    emsal arama cümlesi). `suzgec`: {"haric": [stok kodu | kitap kimliği], "yalniz": [kitap kimliği] (aday kümesini
    daraltır), "stokluOlsun": True (stok kodu dolu)}. Dönen satırlarda `sira` ve kurallı `gerekce`; `puan` yalnız
    sıralama içindir, ekrana yazılmaz. Dizin boşsa ya da sorgu kitabı dizinde yoksa `hazir: False` + neden."""
    if n < 1:
        raise SimilarityError("Kaç kitap istendiği 1 ya da daha büyük olmalı.")
    idx = load_index(engine, tenant)
    base = {"items": [], "kaynak": SOURCE_NOTE, "dizin": {"kitap": len(idx.rows)}}
    if not idx.rows:
        return {**base, "hazir": False, "not": "Kitap benzerliği dizini henüz kurulmadı (gece kurulur)."}
    f = suzgec or {}
    exclude: set[int] = set()
    for x in f.get("haric") or []:
        k = str(x or "").strip().upper()
        for m in (idx.by_code, idx.by_id):
            if k in m:
                exclude.add(m[k])
    only = {guid(x) for x in f.get("yalniz") or []} if f.get("yalniz") is not None else None
    need_code = bool(f.get("stokluOlsun"))
    query_row: dict[str, Any] = {}
    qi = None
    if stok_kodu or kitap_id:
        qi = idx.by_code.get(str(stok_kodu or "").strip().upper()) if stok_kodu else idx.by_id.get(guid(kitap_id))
    if qi is not None:
        qv = idx.vecs[qi]
        query_row = idx.rows[qi]
        exclude.add(qi)
    elif metin and clean(metin):
        emb = embed or embedder()
        if emb is None:
            return {**base, "hazir": False, "not": "Gömme servisi bu kurulumda tanımlı değil."}
        try:
            qv = unit(emb([clean(metin)[:settings()["textChars"]]])[0])
        except SimilarityError:
            raise
        except Exception as e:  # noqa: BLE001
            log.warning("benzerlik: sorgu gömmesi alınamadı: %s", e)
            return {**base, "hazir": False, "not": "Gömme servisi cevap vermedi; birazdan yeniden deneyin."}
        query_row = {k: (f.get("baglam") or {}).get(k) for k in ("kitaplik", "kategori", "turler", "temalar")}
    else:
        return {**base, "hazir": False, "not": "Bu kitap benzerlik dizininde yok (CRM kartında özet ve kategori boş olabilir)."}
    sims = scores(idx, qv)

    def keep(r: dict[str, Any]) -> bool:
        if only is not None and r["kitap_id"] not in only:
            return False
        if need_code and not r.get("stok_kodu"):
            return False
        return True

    items = []
    for sira, (i, s) in enumerate(rank(idx.rows, sims, n, exclude, keep), start=1):
        r = idx.rows[i]
        g = reasons(query_row, r) if query_row else []
        items.append({"sira": sira, "kitapId": r["kitap_id"], "stokKodu": r.get("stok_kodu"), "ad": r["ad"],
                      "yazar": r.get("yazar"), "kitaplik": r.get("kitaplik"), "kategori": r.get("kategori"),
                      "turler": r.get("turler"), "temalar": r.get("temalar"), "ozetVar": bool(r.get("ozet_var")),
                      "gerekce": g or ["özet benzerliği"], "puan": round(float(s), 4)})
    return {**base, "hazir": True, "sorgu": {"kitapId": query_row.get("kitap_id"), "ad": query_row.get("ad"),
                                             "stokKodu": query_row.get("stok_kodu")} if qi is not None else {"metin": True},
            "items": items}


# ================================================================================ dizin kurma (artımlı)


def crm_sql(p: str) -> tuple[str, str]:
    books = ("SELECT k.new_kitapId AS id, k.new_StokKodu AS stok, k.new_name AS ad, k.new_yazartext AS yazar,"
             " kl.new_name AS kitaplik, k.new_webkategorileritext AS kategori, k.new_turlertext AS turler,"
             " CAST(k.new_ozet AS nvarchar(max)) AS ozet, CAST(k.new_kitapspotu AS nvarchar(max)) AS spot,"
             " k.ModifiedOn AS degisme"
             f" FROM {p}new_kitapBase k LEFT JOIN {p}new_kitaplikBase kl ON kl.new_kitaplikId = k.new_kitaplikid"
             " WHERE k.statecode = 0 AND k.new_Tip = 1")
    themes = (f"SELECT kt.new_kitapid AS kitap, t.new_name AS tema FROM {p}new_new_kitap_new_temaBase kt"
              f" JOIN {p}new_temaBase t ON t.new_temaId = kt.new_temaid WHERE t.statecode = 0")
    return books, themes


def read_crm(schema: str, run: Callable[[str], list[dict[str, Any]]]) -> list[dict[str, Any]]:
    from semantic_bridge.editorial import _prefix

    books_sql, themes_sql = crm_sql(_prefix(schema))
    themes: dict[str, list[str]] = {}
    try:
        for r in run(themes_sql):
            k, t = guid(r.get("kitap")), clean(r.get("tema"))
            if k and t:
                themes.setdefault(k, []).append(t)
    except Exception as e:  # noqa: BLE001 — tema bağı okunamazsa temasız devam; neden günlükte
        log.warning("benzerlik: tema bağı okunamadı: %s", str(e)[:300])
    out = []
    for r in run(books_sql):
        k = guid(r.get("id"))
        if not k:
            continue
        deg = r.get("degisme")
        out.append({"kitap_id": k, "stok_kodu": clean(r.get("stok"))[:60] or None, "ad": clean(r.get("ad"))[:400] or k,
                    "yazar": clean(r.get("yazar"))[:400] or None, "kitaplik": clean(r.get("kitaplik"))[:200] or None,
                    "kategori": clean(r.get("kategori"))[:500] or None, "turler": clean(r.get("turler"))[:500] or None,
                    "temalar": ", ".join(sorted(set(themes.get(k, []))))[:1000] or None,
                    "ozet": r.get("ozet"), "spot": r.get("spot"),
                    "crm_degisme": str(deg)[:19] if deg is not None else None})
    return out


def build_index(engine: sa.engine.Engine, tenant: str, books: list[dict[str, Any]], embed: Embed,
                cfg: Optional[dict[str, Any]] = None, progress: Optional[Callable[[int, int], None]] = None,
                deadline: Optional[float] = None) -> dict[str, Any]:
    """Artımlı dizin: metni değişen/yeni kitaplar gömülür, değişmeyen atlanır, CRM'de artık etkin olmayanlar pasif olur.
    `deadline` (time.monotonic) verilirse süre dolunca durur, kalan sonraki tura kalır (yazılanlar kalıcıdır)."""
    ensure(engine)
    st = cfg or settings()
    E = EMBEDDINGS.c
    with engine.connect() as c:
        have = {r.kitap_id: (r.metin_ozeti, r.aktif) for r in c.execute(
            sa.select(E.kitap_id, E.metin_ozeti, E.aktif).where(E.tenant_id == tenant)).all()}
    todo, meta_only = [], []
    seen = set()
    for b in books:
        seen.add(b["kitap_id"])
        text = book_text(b, st["textChars"])
        h = digest(text)
        old = have.get(b["kitap_id"])
        if old and old[0] == h:
            if not old[1]:
                meta_only.append(b)
            continue
        todo.append((b, text, h))
    gone = [k for k, (_, act) in have.items() if act and k not in seen]
    t = now()
    with engine.begin() as c:
        for k in gone:
            c.execute(EMBEDDINGS.update().where(E.tenant_id == tenant, E.kitap_id == k).values(aktif=False, guncellendi_at=t))
        for b in meta_only:
            c.execute(EMBEDDINGS.update().where(E.tenant_id == tenant, E.kitap_id == b["kitap_id"]).values(aktif=True, guncellendi_at=t))
    done, stopped = 0, None
    size = st["batch"]
    for i in range(0, len(todo), size):
        if deadline is not None and time.monotonic() > deadline:
            stopped = "süre doldu; kalan kitaplar sonraki turda"
            break
        part = todo[i:i + size]
        vecs = embed([x[1] for x in part])
        if len(vecs) != len(part):
            raise SimilarityError("Gömme servisi eksik vektör döndürdü.", 502)
        with engine.begin() as c:
            for (b, _text, h), v in zip(part, vecs):
                u = unit(v)
                vals = dict(stok_kodu=b.get("stok_kodu"), ad=b["ad"], yazar=b.get("yazar"), kitaplik=b.get("kitaplik"),
                            kategori=b.get("kategori"), turler=b.get("turler"), temalar=b.get("temalar"), metin_ozeti=h,
                            ozet_var=bool(clean(b.get("ozet")) or clean(b.get("spot"))), boyut=len(u), vektor=encode(u),
                            aktif=True, crm_degisme=b.get("crm_degisme"), guncellendi_at=now())
                n = c.execute(EMBEDDINGS.update().where(E.tenant_id == tenant, E.kitap_id == b["kitap_id"]).values(**vals)).rowcount
                if not n:
                    c.execute(EMBEDDINGS.insert().values(tenant_id=tenant, kitap_id=b["kitap_id"], **vals))
        done += len(part)
        if progress:
            progress(done, len(todo))
    dims = {x for x, in _dims(engine, tenant)}
    out = {"crmKitap": len(books), "gomulen": done, "degismeyen": len(books) - len(todo), "bekleyen": len(todo) - done,
           "pasif": len(gone), "boyutlar": sorted(dims), "durdu": stopped, "bitis": now().isoformat()}
    if len(dims) > 1:
        # Gömme modeli değişmiş: iki farklı boyut aynı dizinde karşılaştırılamaz → eskiler yeniden gömülmeli
        out["uyari"] = "Dizinde farklı boyutta vektörler var; gömme servisi değişmiş olabilir. Dizini sıfırdan kurun."
    _put_state(engine, tenant, "son_kosu", out)
    return out


def _dims(engine: sa.engine.Engine, tenant: str) -> list[tuple[int]]:
    with engine.connect() as c:
        return [(int(r[0]),) for r in c.execute(sa.select(EMBEDDINGS.c.boyut).where(
            EMBEDDINGS.c.tenant_id == tenant, EMBEDDINGS.c.aktif.is_(True)).distinct()).all()]


def reset(engine: sa.engine.Engine, tenant: str) -> int:
    """Dizini boşaltır (gömme modeli değiştiğinde). Yalnız portal tablosu; CRM'e dokunmaz."""
    ensure(engine)
    with engine.begin() as c:
        return c.execute(EMBEDDINGS.delete().where(EMBEDDINGS.c.tenant_id == tenant)).rowcount or 0


def _put_state(engine: sa.engine.Engine, tenant: str, key: str, value: Any) -> None:
    import json

    v = json.dumps(value, ensure_ascii=False, default=str)
    with engine.begin() as c:
        n = c.execute(STATE.update().where(STATE.c.tenant_id == tenant, STATE.c.key == key).values(value=v, updated_at=now())).rowcount
        if not n:
            c.execute(STATE.insert().values(tenant_id=tenant, key=key, value=v, updated_at=now()))


def crm_runner() -> Callable[[str], list[dict[str, Any]]]:
    from semantic_bridge import budget_sources as bsrc

    return bsrc.runner(os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", CRM_FILE_DEFAULT))


def crm_schema() -> str:
    from semantic_bridge import admin as admin_mod

    return admin_mod.conf("CRM_SCHEMA") or "Timas_MSCRM.dbo"


def refresh(engine: sa.engine.Engine, tenant: str, *, embed: Optional[Embed] = None, seconds: Optional[float] = None,
            progress: Optional[Callable[[int, int], None]] = None) -> dict[str, Any]:
    """CRM'den oku + artımlı dizin (zamanlayıcı ve yönetici düğmesi)."""
    emb = embed or embedder()
    if emb is None:
        raise SimilarityError("Gömme servisi bu kurulumda tanımlı değil (BI_EMBED_URL).", 503)
    books = read_crm(crm_schema(), crm_runner())
    return build_index(engine, tenant, books, emb, progress=progress,
                       deadline=(time.monotonic() + seconds) if seconds else None)
