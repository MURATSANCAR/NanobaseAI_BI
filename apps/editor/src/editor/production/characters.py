"""Seri karakter kartı: aynı karakter dizinin her kitabında aynı görünsün diye görünüşü ve renkleri bir kez
kaydedilir, her resimde kullanılır.

Dizi (seri) kimliği `proofing/series_canon.py`'nin kurallarıyla bulunur, sıra:
1. editörün bu iş için yazdığı dizi adı (`seri.json`, ekrandan);
2. kitabın `book.universe` beyanı (okunmuş kitapta);
3. künyenin «Dizi» satırı (elle girilen, künyeden okunan) ve CRM/üst veri SERIES alanı — `series_names` ile; dizi
   ismi taşımayan yazı («<Yayınevi> Çocuk») yayınevi etiketidir, dizi sayılmaz.
Aynı dizi: `same_series` (birinin kelimeleri öbürünün sonuysa). Kart dizi düzeyinde saklanır:

    <storage>/series/<dizi>/series.json      dizi adı ve anahtarı
    <storage>/series/<dizi>/characters.json  kartlar + `rev` (her yazımda +1)
    <storage>/series/<dizi>/gecmis/<rev>.json önceki hâl (silinmez)
    <storage>/series/<dizi>/ref/<r_…>.png    referans görseller (+ görsel kimlik vektörü önbelleği)
    <storage>/series/_ayarlar.json           yeniden deneme sayısı (köprü, yönetim ekranındaki ayarı buraya yazar)

Kart kitap işine kopyalanmaz: resim hattı kartı her istemde diziden okur (images.Painter), işin klasörüne yalnız
hangi kartın hangi sürümünün kullanıldığı ve denetim sonucu yazılır (`karakter-denetimi.json`).

Kart nasıl oluşur: (a) işin sanat planındaki karakter tariflerinden ve karakter referans çiziminden öneri
(`suggest`, ana model gateway üzerinden: Türkçe tarif, tür, yaş, tariften renkler); (b) editör düzeltir ve onaylar;
(c) dizinin önceki kitabında onaylanan kart aynı dizideki her yeni işte kendiliğinden geçerlidir. Yalnız ONAYLI kart
resim üretiminde kullanılır; içeriği değişen kart taslağa döner, yeniden onay ister.

Kullanım: sayfa resmi isteminde sahnedeki karakterin kart tarifi (İngilizce) ve sabit renkleri (ad + hex) yazılır,
kartın birincil referans görseli karakter referansı olarak düzenleme ucuna gider (görsel model referans görselli
düzenlemeyi destekliyor: `/v1/chat/completions` + `image_url`; bkz. images.Painter._edit). Kıyafet: sahnenin seçtiği
kıyafet adı kartta varsa kartın tarifi, yoksa işin tarifi.

Denetim: üretilen her sayfa resmi, içindeki kartlı karakterler için «denetlenecek» olarak işin klasörüne yazılır ve
`CharacterCheck` iş akışı kuyruğa verilir (stüdyo işçisi tek sıra: resim işi bitince koşar; görsel okuyucu ile resim
modeli aynı karta birlikte sığmadığı için denetim resim başına değil, toplu yapılır). Denetim: görsel okuyucu
(gateway, `book-vision-fast`) karakterin bütün bedeninin kutusunu bulur, kesit görsel kimlik servisinde (figure_identity
ile aynı servis) kartın referanslarıyla karşılaştırılır; ölçü `series_canon`'daki eşik (`ccip_same_max`). Uymuyorsa
resim yeni tohumla yeniden üretilir; en çok `max_retries` kez (yönetim ekranı, «Kitap Tasarım Stüdyosu» grubu;
gizli tavan yok). Aşılınca en yakın sürüm seçili kalır ve resim «karakter kartına uymuyor» uyarısıyla editöre gelir.
Düzeltme (fix) sürümü ve editörün seçip onayladığı resim yeniden üretilmez, yalnız işaretlenir. Karakter resimde
bulunamazsa ya da görsel kimlik servisi açık değilse sonuç «denetlenemedi» olur (yeniden üretim yok).

Ölçüm: tek kesitle tek referans karşılaştırması gürültülüdür (series_canon: aynı karakterin 1'e 1 karşılaştırmasında
3'te 2 eşik aşıldı); kartta birden çok referans varsa uzaklıkların ortancası alınır. Bu kurulumda çizilen resimde
isabet henüz ÖLÇÜLMEDİ.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
import random
import re
import secrets
import statistics
import time
import unicodedata
from datetime import timedelta
from pathlib import Path

from temporalio import activity, workflow
from temporalio.common import RetryPolicy

SERIES_FILE = "series.json"
CARDS = "characters.json"
HISTORY = "gecmis"
REFS = "ref"
SETTINGS = "_ayarlar.json"
LINK = "seri.json"                      # işin klasöründe: editörün bu iş için yazdığı dizi adı
CHECKS = "karakter-denetimi.json"       # işin klasöründe: resim → karakter denetimi
TASKS = "karakter-isleri.json"          # işin klasöründe: öneri/çeviri/denetim iş akışlarının durumu
DEFAULT_RETRIES = 3
SERIES_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")
CARD_ID = re.compile(r"^c_[0-9a-f]{8}$")
REF_ID = re.compile(r"^r_[0-9a-f]{8}$")
HEX = re.compile(r"^#[0-9A-Fa-f]{6}$")
KINDS = ("çocuk", "genç", "yetişkin", "yaşlı", "bebek", "hayvan", "fantastik", "nesne", "diğer")
PARTS = {"hair": ("Saç", "hair"), "fur": ("Tüy / post", "fur"), "eyes": ("Göz", "eyes"), "skin": ("Ten", "skin"),
         "outfit": ("Kıyafet", "main clothing"), "accent": ("Ayırt edici ayrıntı", "distinctive detail")}
BY_SYSTEM = "Zeki AI"
MAX_REFS_IN_PROMPT = 4                  # images.MAX_REFS ile aynı: düzenleme ucu en çok 4 görsel alır


# ------------------------------------------------------------------ yardımcılar
def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def fold(s: str) -> str:
    """series_canon.fold ile aynı: Türkçe küçük harf, düzeltme işareti ve kesme ekleri atılır."""
    s = unicodedata.normalize("NFKC", s or "").replace("I", "ı").replace("İ", "i").lower()
    s = s.replace("â", "a").replace("î", "i").replace("û", "u")
    s = re.sub(r"['’]\w*", "", s)
    return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", s)).strip()


_ASCII = str.maketrans("çğıöşü", "cgiosu")


def slug(key: str) -> str:
    s = fold(key).translate(_ASCII)
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()
    s = re.sub(r"[^a-z0-9]+", "-", s).strip("-")[:60].strip("-")
    return s or "dizi-" + secrets.token_hex(3)


def _read(path: Path, default=None):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, ValueError):
        return default


def _write(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=1, default=str))
    tmp.replace(path)


@contextlib.contextmanager
def _locked(path: Path):
    """Tek sıra: stüdyo API'si ve stüdyo işçisi ayrı süreçler; aynı dosya kilidini alırlar."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


class Stale(Exception):
    def __init__(self, rev: int):
        super().__init__(f"kartlar güncel değil (sunucuda sürüm {rev})")
        self.rev = rev


class NoSeries(Exception):
    """İşin dizisi belirlenemedi: editörden dizi adı istenir."""


# ------------------------------------------------------------------ yer ve ayar
def series_root() -> Path:
    from ..config import settings
    return Path(settings().storage) / "series"


def series_dir(sid: str) -> Path:
    if not SERIES_ID.match(sid or ""):
        raise ValueError("geçersiz dizi")
    return series_root() / sid


def max_retries() -> int:
    """Uymayan resmin en çok kaç kez yeniden üretileceği: yönetim ekranı (köprü _ayarlar.json'a yazar) > ortam
    STUDIO_CHARACTER_RETRIES > 3. 0 = yeniden üretme, yalnız işaretle."""
    v = (_read(series_root() / SETTINGS, {}) or {}).get("max_retries")
    if v is None:
        v = os.environ.get("STUDIO_CHARACTER_RETRIES", DEFAULT_RETRIES)
    try:
        return max(0, int(v))
    except (TypeError, ValueError):
        return DEFAULT_RETRIES


def set_max_retries(n: int, by: str) -> dict:
    n = int(n)
    if n < 0:
        raise ValueError("yeniden deneme sayısı eksi olamaz")
    out = {"max_retries": n, "by": by, "at": _now()}
    with _locked(series_root() / "ayar.kilit"):
        _write(series_root() / SETTINGS, out)
    return out


# ------------------------------------------------------------------ dizi kimliği
def _series_key(text: str) -> tuple[str, str, int | None] | None:
    """(anahtar, basıldığı gibi ad, dizideki sıra) — series_canon'un dizi adı kuralı."""
    from ..proofing.series_canon import series_names
    hit = series_names(text or "")
    return hit[0] if hit else None


def _same(a: str, b: str) -> bool:
    from ..proofing.series_canon import same_series
    return a == b or same_series(a, b)


def _universe(book_id: str | None) -> str | None:
    if not book_id:
        return None
    try:
        from .. import db
        r = db.one("SELECT universe FROM ed.book WHERE id=%s", book_id)
        v = r.get("universe") if isinstance(r, dict) else None
        return v if isinstance(v, str) and v.strip() else None
    except Exception:  # noqa: BLE001 - veritabanı yoksa (Word işi, sınama) evren beyanı yok sayılır
        return None


def _find(key: str) -> str | None:
    root = series_root()
    if not root.exists():
        return None
    for p in sorted(root.iterdir()):
        if not p.is_dir():
            continue
        meta = _read(p / SERIES_FILE)
        if meta and _same(key, meta.get("key", "")):
            return p.name
    return None


def job_series(d: Path) -> dict | None:
    """İşin dizisi: {id, name, key, source, number, exists} ya da None."""
    job = _read(d / "job.json", {}) or {}
    ms = _read(d / "manuscript.json", {}) or {}
    link = _read(d / LINK)
    cands: list[tuple[str, str, str, int | None]] = []
    if link and link.get("key"):
        cands.append((link["key"], link["name"], "editör", None))
    else:
        uni = _universe((ms.get("source") or {}).get("book_id") or (job.get("source") or {}).get("book_id"))
        if uni:
            cands.append((fold(uni), uni, "kitabın evren beyanı", None))
        fr = _read(d / "front.json", {}) or {}
        texts = [((fr.get("manual") or {}).get("Dizi"), "künye (elle)"),
                 (((fr.get("kunye_fields") or {}).get("DIZI") or {}).get("value"), "künye"),
                 ((ms.get("meta") or {}).get("SERIES"), "kitap kaydı")]
        for t, src in texts:
            hit = _series_key(t or "")
            if hit:
                cands.append((hit[0], hit[2], src, hit[1]))
    if not cands:
        return None
    key, name, src, no = cands[0]
    sid = _find(key)
    return {"id": sid or slug(key), "name": name, "key": key, "source": src, "number": no, "exists": bool(sid)}


def set_job_series(d: Path, name: str, by: str) -> dict | None:
    """Editörün bu iş için yazdığı dizi adı; boş ad beyanı kaldırır (kurallı bulma geri gelir)."""
    name = " ".join((name or "").split())[:120]
    if not name:
        (d / LINK).unlink(missing_ok=True)
        return job_series(d)
    hit = _series_key(name)
    key = hit[0] if hit else fold(name)
    if not key:
        raise ValueError("dizi adı boş olamaz")
    _write(d / LINK, {"name": name, "key": key, "by": by, "at": _now()})
    return job_series(d)


# ------------------------------------------------------------------ kart deposu
def load(sid: str) -> dict:
    sd = series_dir(sid)
    data = _read(sd / CARDS)
    if data is None:
        meta = _read(sd / SERIES_FILE, {}) or {}
        return {"series": meta, "rev": 0, "cards": []}
    return data


def _commit(series: dict, data: dict, by: str, what: str) -> dict:
    sd = series_dir(series["id"])
    if not (sd / SERIES_FILE).exists():
        _write(sd / SERIES_FILE, {"id": series["id"], "name": series["name"], "key": series["key"],
                                  "created_at": _now(), "created_by": by})
    old = _read(sd / CARDS)
    if old is not None:
        _write(sd / HISTORY / f"{old.get('rev', 0)}.json", old)          # önceki hâl silinmez
    data["rev"] = int(data.get("rev") or 0) + 1
    data["series"] = {k: series[k] for k in ("id", "name", "key")}
    data["updated_at"], data["updated_by"], data["what"] = _now(), by, what
    _write(sd / CARDS, data)
    return data


def mutate(series: dict, rev: int | None, by: str, what: str, fn):
    """Kilit → rev denetimi → fn(data) → yazım. Dönen (data, fn'in dönüşü). rev None: denetlenmez (sunucu içi)."""
    with _locked(series_dir(series["id"]) / "kilit"):
        data = load(series["id"])
        if rev is not None and int(rev) != int(data.get("rev") or 0):
            raise Stale(int(data.get("rev") or 0))
        out = fn(data)
        return _commit(series, data, by, what), out


def history(sid: str) -> list[dict]:
    hd = series_dir(sid) / HISTORY
    out = []
    for p in hd.glob("*.json") if hd.exists() else []:
        h = _read(p, {}) or {}
        out.append({"rev": h.get("rev"), "at": h.get("updated_at"), "by": h.get("updated_by"), "what": h.get("what")})
    cur = load(sid)
    if cur.get("rev"):
        out.append({"rev": cur["rev"], "at": cur.get("updated_at"), "by": cur.get("updated_by"), "what": cur.get("what")})
    return sorted(out, key=lambda r: r.get("rev") or 0, reverse=True)


def _card(data: dict, cid: str) -> dict:
    c = next((c for c in data["cards"] if c["id"] == cid), None)
    if c is None:
        raise KeyError(f"kart yok: {cid}")
    return c


def _hex(v, what: str) -> str | None:
    if v in (None, ""):
        return None
    v = str(v).strip()
    if not HEX.match(v):
        raise ValueError(f"{what}: renk #RRGGBB biçiminde olmalı")
    return v.upper()


def _text(v, n: int, what: str = "alan") -> str:
    """Boşlukları sadeleştirir; uzunluk aşılırsa kesmez, açık hata verir."""
    t = " ".join(str(v or "").split())
    if len(t) > n:
        raise ValueError(f"{what} en çok {n} harf olabilir ({len(t)} yazıldı)")
    return t


CONTENT = ("name", "aliases", "kind", "age", "species_en", "look_tr", "look_en", "colors", "palette_color", "outfits",
           "seed")


def clean(inp: dict, old: dict | None = None) -> dict:
    """Editörden gelen kartı doğrular; sunucunun alanları (kimlik, referanslar, onay, sürüm) eski karttan gelir."""
    name = _text(inp.get("name"), 80, "ad")
    if not name:
        raise ValueError("karakterin adı boş olamaz")
    kind = _text(inp.get("kind"), 20, "tür") or "diğer"
    if kind not in KINDS:
        raise ValueError(f"tür şunlardan biri olmalı: {', '.join(KINDS)}")
    colors = {}
    for k, v in (inp.get("colors") or {}).items():
        if k not in PARTS:
            raise ValueError(f"bilinmeyen renk alanı: {k}")
        h = _hex(v, PARTS[k][0])
        if h:
            colors[k] = h
    outfits = []
    for i, o in enumerate(inp.get("outfits") or []):
        oname = _text(o.get("name"), 40, "kıyafet adı")
        if not oname:
            raise ValueError(f"{i + 1}. kıyafetin adı boş")
        outfits.append({"id": o.get("id") if re.fullmatch(r"o_[0-9a-f]{6}", str(o.get("id") or "")) else
                        f"o_{secrets.token_hex(3)}", "name": oname, "look_tr": _text(o.get("look_tr"), 600, f"{oname} tarifi"),
                        "look_en": _text(o.get("look_en"), 600, f"{oname} tarifi (model)"), "color": _hex(o.get("color"), f"{oname} rengi"),
                        "default": bool(o.get("default"))})
    if outfits and sum(o["default"] for o in outfits) != 1:
        for j, o in enumerate(outfits):
            o["default"] = j == 0
    seed = inp.get("seed")
    card = {"name": name, "aliases": [a for a in (_text(a, 80, "diğer ad") for a in inp.get("aliases") or []) if a],
            "kind": kind, "age": _text(inp.get("age"), 30, "yaş"), "species_en": _text(inp.get("species_en"), 200, "tür (model)"),
            "look_tr": _text(inp.get("look_tr"), 2000, "görünüş"), "look_en": _text(inp.get("look_en"), 2000, "görünüş (model)"),
            "colors": colors, "palette_color": _hex(inp.get("palette_color"), "kitap paletindeki rengi"),
            "outfits": outfits, "seed": int(seed) if isinstance(seed, int) or str(seed or "").isdigit() else None}
    base = dict(old or {})
    changed = [k for k in CONTENT if base.get(k) != card[k]]
    out = {**base, **card}
    if old is None:
        out.update(id=f"c_{secrets.token_hex(4)}", refs=[], status="draft", version=1, en_stale=False)
    elif changed:
        out["version"] = int(base.get("version") or 1) + 1
        out["status"] = "draft"                      # içeriği değişen kart yeniden onay ister
        tr_changed = base.get("look_tr") != card["look_tr"] or \
            [o.get("look_tr") for o in base.get("outfits") or []] != [o["look_tr"] for o in outfits]
        en_changed = base.get("look_en") != card["look_en"] or \
            [o.get("look_en") for o in base.get("outfits") or []] != [o["look_en"] for o in outfits]
        if en_changed:
            out["en_stale"] = False
        elif tr_changed:
            out["en_stale"] = True                   # Türkçe değişti, modele giden tarif eski kaldı
    return out


def _dupe(data: dict, card: dict) -> None:
    keys = {fold(card["name"]), *(fold(a) for a in card["aliases"])}
    for c in data["cards"]:
        if c["id"] != card.get("id") and keys & {fold(c["name"]), *(fold(a) for a in c.get("aliases", []))}:
            raise ValueError(f"bu dizide «{c['name']}» adlı bir kart zaten var")


def create_card(series: dict, rev: int | None, inp: dict, by: str, origin: dict | None = None) -> tuple[dict, dict]:
    name = " ".join(str(inp.get("name") or "").split())

    def fn(data):
        card = clean(inp)
        _dupe(data, card)
        card.update(created_by=by, created_at=_now(), updated_by=by, updated_at=_now(), origin=origin or {})
        data["cards"].append(card)
        return card
    return mutate(series, rev, by, f"kart eklendi: {name}", fn)


def update_card(series: dict, rev: int | None, cid: str, inp: dict, by: str) -> tuple[dict, dict]:
    name = " ".join(str(inp.get("name") or "").split())

    def fn(data):
        old = _card(data, cid)
        card = clean(inp, old)
        _dupe(data, card)
        if card != old:
            card.update(updated_by=by, updated_at=_now())
        data["cards"][data["cards"].index(old)] = card
        return card
    return mutate(series, rev, by, f"kart düzenlendi: {name}", fn)


def delete_card(series: dict, rev: int | None, cid: str, by: str) -> tuple[dict, None]:
    """Kart listeden çıkar; önceki hâl geçmişte, referans görselleri diskte kalır (geri yüklenebilsin)."""
    def fn(data):
        data["cards"].remove(_card(data, cid))
    return mutate(series, rev, by, f"kart silindi: {cid}", fn)


def approve(series: dict, cid: str, ok: bool, by: str) -> tuple[dict, dict]:
    def fn(data):
        c = _card(data, cid)
        if ok:
            if not c.get("look_en"):
                raise ValueError("Modele giden (İngilizce) tarif boş; önce tarifi yazın ya da yenileyin")
            if c.get("en_stale"):
                raise ValueError("Türkçe tarif değişti; önce modele giden tarifi yenileyin")
            c.update(status="approved", approved_by=by, approved_at=_now(), approved_version=c.get("version", 1))
        else:
            c.update(status="draft", approved_by=None, approved_at=None)
        return c
    return mutate(series, None, by, f"kart {'onaylandı' if ok else 'onayı kaldırıldı'}: {cid}", fn)


def _png(data: bytes) -> tuple[bytes, int, int]:
    """Referans görsel: yön uygulanır, üst veri atılır, PNG (saydamlık korunur)."""
    import io

    from PIL import Image, ImageOps, UnidentifiedImageError
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError):
        raise ValueError("Görsel okunamadı (JPEG, PNG ya da WebP yükleyin)") from None
    im = ImageOps.exif_transpose(im)
    im = im.convert("RGBA" if "A" in im.getbands() else "RGB")
    im.thumbnail((2048, 2048))
    buf = io.BytesIO()
    im.save(buf, "PNG", compress_level=6)
    return buf.getvalue(), im.width, im.height


def add_ref(series: dict, cid: str, data: bytes, source: dict, by: str) -> tuple[dict, dict]:
    png, w, h = _png(data)
    rid = f"r_{secrets.token_hex(4)}"
    rel = f"{REFS}/{rid}.png"
    path = series_dir(series["id"]) / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(png)

    def fn(d_):
        c = _card(d_, cid)
        refs = c.setdefault("refs", [])
        ref = {"id": rid, "path": rel, "w": w, "h": h, "source": source, "by": by, "at": _now(),
               "primary": not any(r.get("primary") for r in refs)}
        refs.append(ref)
        c["version"] = int(c.get("version") or 1) + 1
        c["status"] = "draft"
        return ref
    try:
        return mutate(series, None, by, f"referans eklendi: {cid}", fn)
    except Exception:
        path.unlink(missing_ok=True)
        raise


def ref_action(series: dict, cid: str, rid: str, action: str, by: str) -> tuple[dict, dict]:
    """«primary»: birincil referans yap; «remove»: karttan çıkar (dosya diskte kalır, geçmiş ona bağlı)."""
    def fn(d_):
        c = _card(d_, cid)
        ref = next((r for r in c.get("refs", []) if r["id"] == rid), None)
        if ref is None:
            raise KeyError(f"referans yok: {rid}")
        if action == "primary":
            for r in c["refs"]:
                r["primary"] = r["id"] == rid
        elif action == "remove":
            c["refs"].remove(ref)
            if c["refs"] and not any(r.get("primary") for r in c["refs"]):
                c["refs"][0]["primary"] = True
        else:
            raise ValueError("işlem yok")
        c["version"] = int(c.get("version") or 1) + 1
        c["status"] = "draft"
        return c
    return mutate(series, None, by, f"referans {action}: {cid}/{rid}", fn)


def ref_path(sid: str, cid: str, rid: str) -> Path:
    c = _card(load(sid), cid)
    ref = next((r for r in c.get("refs", []) if r["id"] == rid), None)
    if ref is None:
        raise KeyError(rid)
    return series_dir(sid) / ref["path"]


# ------------------------------------------------------------------ resim hattıyla bağ (images.Painter)
_EN_COLORS = [
    ("black", "#141414"), ("charcoal grey", "#3A3F44"), ("grey", "#8A8D91"), ("silver grey", "#C4C7CC"),
    ("white", "#F7F7F5"), ("cream", "#F2E8CF"), ("beige", "#D9C3A0"), ("sand", "#C9A66B"),
    ("light brown", "#A47148"), ("chestnut brown", "#6B3E26"), ("dark brown", "#3E2415"), ("auburn", "#8E3B26"),
    ("ginger", "#C1502E"), ("golden blonde", "#D9A441"), ("platinum blonde", "#E8DDB5"), ("honey", "#B8862F"),
    ("red", "#C62828"), ("crimson", "#9E1B32"), ("maroon", "#6D1A24"), ("pink", "#E57FA4"),
    ("light pink", "#F4C2D0"), ("peach", "#F7B58E"), ("coral", "#F0735A"), ("orange", "#E8772E"),
    ("amber", "#F2A900"), ("yellow", "#F4D03F"), ("mustard", "#C9A227"), ("lime green", "#9BC53D"),
    ("green", "#3C8D40"), ("olive green", "#6B7F2A"), ("dark green", "#1E5631"), ("teal", "#1F7A7A"),
    ("turquoise", "#3CB6B0"), ("sky blue", "#7EC8E3"), ("light blue", "#AFCBEA"), ("blue", "#2E6DB4"),
    ("royal blue", "#2340A0"), ("navy blue", "#1B2A4A"), ("lavender", "#B9A6D9"), ("purple", "#6A3D9A"),
    ("plum", "#6E2C54"),
    ("fair", "#F3D9C6"), ("light", "#E8C3A0"), ("medium", "#C69076"), ("olive", "#B08B5E"),
    ("tan", "#A0704C"), ("brown", "#7B4B2A"), ("deep brown", "#4A2E1C"),
]


def color_en(hx: str) -> str:
    """Hex'in İngilizce renk adı (görsel model hex'i tek başına iyi anlamaz; ad + hex birlikte gider)."""
    from .palette import delta_e, hex_lab
    lab = hex_lab(hx)
    return min(_EN_COLORS, key=lambda c: float(delta_e(lab, hex_lab(c[1]))))[0]


class CardSet:
    """Bir işin dizisindeki ONAYLI kartlar (resim hattının gördüğü)."""

    def __init__(self, series: dict | None = None, cards: list[dict] | None = None):
        self.series = series
        self.cards = cards or []
        self._by = {}
        for c in self.cards:
            for k in [c["name"], *c.get("aliases", [])]:
                self._by.setdefault(fold(k), c)

    @classmethod
    def for_job(cls, d: Path) -> "CardSet":
        if not (d / "job.json").exists():
            return cls()
        s = job_series(d)
        if not s or not s["exists"]:
            return cls(s)
        return cls(s, [c for c in load(s["id"])["cards"] if c.get("status") == "approved"])

    def __bool__(self) -> bool:
        return bool(self.cards)

    def card(self, name: str) -> dict | None:
        return self._by.get(fold(name))

    def refs(self, card: dict) -> list[Path]:
        out = sorted(card.get("refs", []), key=lambda r: not r.get("primary"))
        paths = [series_dir(self.series["id"]) / r["path"] for r in out]
        return [p for p in paths if p.exists()]

    def ref_paths(self, names) -> dict[str, str]:
        """Plan karakter adı → kartın birincil referansı (işin kendi referansının önüne geçer)."""
        out = {}
        for n in names:
            c = self.card(n)
            ps = self.refs(c) if c else []
            if ps:
                out[n] = str(ps[0])
        return out

    def line(self, c, outfit: str | None) -> str | None:
        """Sahnedeki karakterin istem satırı: kartın tarifi + sabit renkler + kıyafet. Kart yoksa None."""
        card = self.card(c.name)
        if card is None or not card.get("look_en"):
            return None
        species = card.get("species_en") or c.species
        cols = [f"{PARTS[k][1]} {color_en(v)} ({v})" for k, v in card.get("colors", {}).items() if k != "outfit"]
        fit = next((o for o in card.get("outfits", []) if outfit and fold(o["name"]) == fold(outfit)), None)
        wear = ""
        if fit and fit.get("look_en"):
            wear = fit["look_en"] + (f", main colour {color_en(fit['color'])} ({fit['color']})" if fit.get("color") else "")
        else:
            wear = c.outfit(outfit) if hasattr(c, "outfit") else ""
            if not wear:
                dflt = next((o for o in card.get("outfits", []) if o.get("default") and o.get("look_en")), None)
                wear = dflt["look_en"] if dflt else ""
            if card.get("colors", {}).get("outfit") and wear:
                wear += f", main colour {color_en(card['colors']['outfit'])} ({card['colors']['outfit']})"
        text = f"{c.name} is {species}: {card['look_en'].rstrip('.')}."
        if cols:
            text += " Fixed colours, identical in every picture: " + ", ".join(cols) + "."
        if wear:
            text += f" Wearing: {wear.rstrip('.')}."
        return text

    def stamp(self, names) -> dict:
        return {n: [c["id"], c.get("version", 1)] for n in names if (c := self.card(n))}


# ------------------------------------------------------------------ denetim kaydı (işin klasöründe)
def _checks(d: Path) -> dict:
    return _read(d / CHECKS, {"items": {}}) or {"items": {}}


@contextlib.contextmanager
def _checks_tx(d: Path):
    with _locked(d / "karakter.kilit"):
        data = _checks(d)
        yield data
        _write(d / CHECKS, data)


async def record(painter, rd, sc, w_mm: float, h_mm: float, direction: str, base_image: str | None) -> None:
    """images.Painter.page'in kancası: kartlı karakter içeren her yeni resim «denetlenecek» olarak yazılır ve
    denetim iş akışı kuyruğa verilir. Kart yoksa bir şey yapmaz; hiçbir hata resim üretimini düşürmez."""
    try:
        cards = painter.cards
        names = [n for n in sc.characters if cards and cards.card(n)]
        d = painter.dir.parent
        if not names or not (d / "job.json").exists():
            return
        chain = getattr(painter, "card_chain", None) or {}
        from dataclasses import asdict
        with _checks_tx(d) as data:
            data["items"][rd.path] = {
                "path": rd.path, "prefix": rd.key.rsplit(".v", 1)[0], "chars": names, "cards": cards.stamp(names),
                "series": cards.series["id"], "scene": asdict(sc), "size": [w_mm, h_mm], "direction": direction,
                "retry": base_image is None, "attempt": chain.get("attempt", 0), "root": chain.get("root", rd.path),
                "status": "pending", "at": _now()}
        await kick(d.name)
    except Exception as e:  # noqa: BLE001
        with contextlib.suppress(Exception):
            activity.logger.warning("karakter denetimi kaydedilemedi: %s", e)


async def kick(job: str) -> str | None:
    """Denetim iş akışını kuyruğa verir; zaten sıradaysa ya da koşuyorsa yenisi açılmaz (koşan iş bütün bekleyenleri
    alır). Temporal'a ulaşılamazsa kayıt «bekliyor» kalır, ekrandaki «Denetle» ya da sonraki resim yeniden dener."""
    from temporalio.exceptions import WorkflowAlreadyStartedError

    from ..jobs import temporal
    from .flow import QUEUE
    wf = f"studio-{job}-karakter"
    try:
        await (await temporal()).start_workflow("CharacterCheck", args=[job], id=wf, task_queue=QUEUE)
    except WorkflowAlreadyStartedError:
        return wf
    except Exception:  # noqa: BLE001
        return None
    return wf


def mark_selected(d: Path) -> int:
    """«Denetle»: işin seçili resimlerinden kartlı karakter içerenleri (henüz kaydı olmayanlar ve eski kartla
    denetlenenler) bekleyene alır. Dönen: bekleyen sayısı."""
    from dataclasses import asdict

    from . import studio
    cards = CardSet.for_job(d)
    if not cards:
        return 0
    plan = studio._plan(d)
    by_page = {str(s.page): s for s in plan.scenes}
    by_art = {s.art_id: s for s in plan.scenes if s.art_id}
    st = studio.studio_state(d)
    n = 0
    with _checks_tx(d) as data:
        for key, pg in st["pages"].items():
            if key == "kapak" or not pg.get("selected"):
                continue
            v = pg["versions"][pg["selected"] - 1]
            sc = by_art.get(key) or by_page.get(key)
            if sc is None:
                continue
            names = [c for c in sc.characters if cards.card(c)]
            if not names:
                continue
            old = data["items"].get(v["path"])
            stamp = cards.stamp(names)
            if old and old.get("cards") == stamp and old["status"] != "pending":
                continue
            size = (old or {}).get("size") or _size(d, key, sc)
            data["items"][v["path"]] = {
                "path": v["path"], "prefix": Path(v["path"]).stem.rsplit(".v", 1)[0], "chars": names, "cards": stamp,
                "series": cards.series["id"], "scene": asdict(sc), "size": size,
                "direction": v.get("prompt_en", ""), "retry": v.get("mode") != "fix" and size is not None,
                "attempt": (old or {}).get("attempt", 0), "root": (old or {}).get("root", v["path"]),
                "status": "pending", "at": _now()}
            n += 1
    return n


def _size(d: Path, key: str, sc) -> list[float] | None:
    """Resmin basım ölçüsü (mm): plandaki resim kutusu, yoksa akışın bant/tam sayfa ölçüsü (studio.regenerate gibi)."""
    from . import plan as plan_mod
    from . import studio
    try:
        if key.startswith("a_"):
            pl = plan_mod.load(d)
            ppg = plan_mod.page_of_art(pl, key)[1] if pl else None
            if ppg and ppg.get("art"):
                return [ppg["art"]["box"]["w"], ppg["art"]["box"]["h"]]
        spec = studio._spec(d)
        return list(studio.full_mm(spec) if sc.kind == "full" else studio.band_mm(spec, studio._pagemap(d)))
    except Exception:  # noqa: BLE001 - ölçü bulunamazsa yeniden üretilmez, yalnız işaretlenir
        return None


def _beat() -> None:
    with contextlib.suppress(Exception):
        activity.heartbeat()


# ------------------------------------------------------------------ görsel kimlik denetimi
class IdentityDown(Exception):
    pass


def _jpeg_b64(path: str, box: dict | None = None, side: int = 1280) -> str:
    import base64
    import io

    from PIL import Image
    im = Image.open(path).convert("RGB")
    if box:
        W, H = im.size
        mx, my = box["w"] * 0.06, box["h"] * 0.06
        x0, y0 = max(0, (box["x"] - mx) * W), max(0, (box["y"] - my) * H)
        x1, y1 = min(W, (box["x"] + box["w"] + mx) * W), min(H, (box["y"] + box["h"] + my) * H)
        im = im.crop((int(x0), int(y0), int(x1), int(y1)))
    im.thumbnail((side, side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode()


async def locate_body(http, path: str, who: str) -> dict | None:
    """Karakterin bütün bedeninin kutusu (0–1 oran); görsel okuyucu gateway üzerinden. Bulamazsa None."""
    from ..config import settings
    s = settings()
    schema = {"type": "object", "additionalProperties": False, "required": ["found", "box"],
              "properties": {"found": {"type": "boolean"},
                             "box": {"type": "array", "items": {"type": "integer"}, "minItems": 4, "maxItems": 4}}}
    body = {"model": "book-vision-fast", "max_tokens": 120, "temperature": 0.0,
            "chat_template_kwargs": {"enable_thinking": False},
            "response_format": {"type": "json_schema", "json_schema": {"name": "body", "schema": schema, "strict": True}},
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": f"Find {who} in this illustration. Return the bounding box of that character's "
                                         "whole visible body as [x0, y0, x1, y1] in 0-1000 coordinates of the image. "
                                         "If the character is not visible, found=false."},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + _jpeg_b64(path)}}]}]}
    try:
        r = await http.post(f"{s.gateway_url.rstrip('/')}/v1/chat/completions", json=body, timeout=600,
                            headers={"authorization": f"Bearer {s.gateway_key}"})
        r.raise_for_status()
        out = json.loads(r.json()["choices"][0]["message"]["content"])
    except Exception:  # noqa: BLE001 - okunamayan resim «denetlenemedi» olur
        return None
    x0, y0, x1, y1 = (min(max(v / 1000, 0.0), 1.0) for v in out["box"])
    if not (out["found"] and x1 - x0 > 0.02 and y1 - y0 > 0.02):
        return None
    return {"x": x0, "y": y0, "w": x1 - x0, "h": y1 - y0}


async def _features(http, images_b64: list[str]) -> list[list[float]]:
    from ..config import settings
    try:
        r = await http.post(f"{settings().embed_url.rstrip('/')}/features", json={"images": images_b64}, timeout=300)
        r.raise_for_status()
        return r.json()["features"]
    except Exception as e:  # noqa: BLE001
        raise IdentityDown(str(e)[:200]) from None


async def _distances(http, feats: list[list[float]]) -> list[list[float]]:
    from ..config import settings
    try:
        r = await http.post(f"{settings().embed_url.rstrip('/')}/differences", json={"features": feats}, timeout=300)
        r.raise_for_status()
        return r.json()["matrix"]
    except Exception as e:  # noqa: BLE001
        raise IdentityDown(str(e)[:200]) from None


async def ref_features(http, cards: CardSet, card: dict) -> list[list[float]]:
    """Kartın referanslarının görsel kimlik vektörleri; referansın yanında önbellekte (model adıyla)."""
    out = []
    for p in cards.refs(card)[:MAX_REFS_IN_PROMPT]:
        cache = p.with_suffix(".kimlik.json")
        c = _read(cache)
        if c is None or c.get("mtime") != p.stat().st_mtime:
            f = (await _features(http, [_jpeg_b64(str(p), side=1024)]))[0]
            c = {"mtime": p.stat().st_mtime, "feature": f}
            _write(cache, c)
        out.append(c["feature"])
    return out


def _who(card: dict) -> str:
    return f"{card['name']} ({card.get('species_en') or card.get('kind', '')}; {card.get('look_en', '')[:200]})"


async def check_items(items: list[dict], cards: CardSet, threshold: float) -> None:
    """Her bekleyen resimde kartlı her karakter: kutu → kesit → referanslara uzaklık (ortanca). Sonuç kayda yazılır.
    Görsel kimlik servisi kapalıysa IdentityDown; o turdaki resimler «denetlenemedi» olur."""
    import httpx
    async with httpx.AsyncClient(timeout=httpx.Timeout(600.0, connect=10.0)) as http:
        for it in items:
            res = {}
            for n in it["chars"]:
                _beat()
                card = cards.card(n)
                if card is None or not cards.refs(card):
                    res[n] = {"state": "noref"}
                    continue
                box = await locate_body(http, it["path"], _who(card))
                if box is None:
                    res[n] = {"state": "notfound"}
                    continue
                refs = await ref_features(http, cards, card)
                crop = (await _features(http, [_jpeg_b64(it["path"], box, side=1024)]))[0]
                m = await _distances(http, [crop] + refs)
                dist = statistics.median(m[0][1:])
                res[n] = {"state": "ok" if dist < threshold else "mismatch", "distance": round(dist, 4), "box": box}
            it["result"] = res
            states = {r["state"] for r in res.values()}
            it["status"] = ("mismatch" if "mismatch" in states else "ok" if states == {"ok"} else "unchecked")
            it["threshold"] = threshold
            it["checked_at"] = _now()


def _worst(it: dict) -> float:
    ds = [r.get("distance") for r in (it.get("result") or {}).values() if r.get("distance") is not None]
    return max(ds) if ds else 9.0


def _key_of(st: dict, path: str) -> tuple[str | None, int | None, dict | None]:
    """Resim yolunun stüdyo kaydındaki anahtarı ve sürümü."""
    for key, pg in st["pages"].items():
        for v in pg["versions"]:
            if v["path"] == path:
                return key, v["v"], pg
    return None, None, None


async def run_check(d: Path, by: str = BY_SYSTEM) -> dict:
    """Bekleyen bütün resimleri denetler; uymayanı (yeniden üretilebilir, seçili, onaysız, hakkı kalan) yeni tohumla
    yeniden üretir ve yeni sürümü de denetler. Bitince hakkı biten zincirde en yakın sürümü seçili bırakır."""
    from ..config import settings
    from . import studio
    from .art import Scene
    from .images import Painter
    threshold = settings().ccip_same_max
    limit = max_retries()
    cards = CardSet.for_job(d)
    summary = {"checked": 0, "ok": 0, "mismatch": 0, "unchecked": 0, "regenerated": 0, "limit": limit}
    painter = None
    rebuilt = False
    try:
        while True:
            items = [it for it in _checks(d)["items"].values() if it["status"] == "pending"]
            if not items:
                break
            if not cards:
                with _checks_tx(d) as data:
                    for it in items:
                        data["items"][it["path"]].update(status="unchecked", note="kart onayı kalktı", checked_at=_now())
                break
            try:
                await check_items(items, cards, threshold)
            except IdentityDown as e:
                for it in items:
                    it.update(status="unchecked", note="Görsel kimlik denetimi şu an yapılamıyor", error=str(e),
                              checked_at=_now())
            with _checks_tx(d) as data:
                for it in items:
                    data["items"][it["path"]] = {**data["items"].get(it["path"], {}), **it}
            for it in items:
                summary["checked"] += 1
                summary[it["status"]] = summary.get(it["status"], 0) + 1
            st = studio.studio_state(d)
            again = []
            for it in items:
                if it["status"] != "mismatch" or not it.get("retry") or not it.get("size") or it["attempt"] >= limit:
                    continue
                key, v, pg = _key_of(st, it["path"])
                if key is None or pg.get("selected") != v or pg.get("approved"):
                    continue                     # editör başka sürüm seçti ya da onayladı: dokunulmaz
                again.append((it, key, v))
            if not again:
                break
            if painter is None:
                painter = Painter(d / "resim", studio._plan(d))
                painter.refs = dict(st.get("characters", {}))
            for it, key, v in again:
                _beat()
                painter.card_chain = {"attempt": it["attempt"] + 1, "root": it["root"]}
                v_next = len(studio.studio_state(d)["pages"][key]["versions"]) + 1
                seed = random.randint(1, 2**31 - 1)
                sc = Scene(**it["scene"])
                rd = await painter.page(sc, *it["size"], version=v_next, seed=seed, direction=it.get("direction", ""),
                                        key=it["prefix"])
                prev = studio.studio_state(d)["pages"][key]["versions"][v - 1]
                studio.add_version(d, key, rd.path, mode="new", prompt=prev.get("prompt", ""), seed=seed, by=by,
                                   dpi=rd.dpi, prompt_en=it.get("direction", ""))
                summary["regenerated"] += 1
                rebuilt = True
            painter.card_chain = None
        # hakkı biten zincir: en yakın sürüm seçili kalır (editör başka sürüm seçmediyse)
        st = studio.studio_state(d)
        chains: dict[str, list[dict]] = {}
        for it in _checks(d)["items"].values():
            chains.setdefault(it["root"], []).append(it)
        for chain in chains.values():
            last = max(chain, key=lambda x: x["attempt"])
            if last["status"] != "mismatch" or last["attempt"] < limit or len(chain) < 2:
                continue
            key, v, pg = _key_of(st, last["path"])
            if key is None or pg.get("selected") != v or pg.get("approved"):
                continue
            best = min((x for x in chain if x.get("result")), key=_worst)
            bk, bv, _ = _key_of(st, best["path"])
            if bk == key and bv and bv != v:
                studio.select(d, key, bv, by)
                rebuilt = False                   # select dizgiyi kendisi yeniler
    finally:
        if painter is not None:
            await painter.close()
    if rebuilt:
        import asyncio
        await asyncio.to_thread(studio.rebuild, d)
    return summary


def mismatches(d: Path) -> dict:
    """Ekran için: bu kitapta seçili olup karta uymayan ya da denetlenemeyen resimler."""
    from . import plan as plan_mod
    from . import studio
    st = studio.studio_state(d)
    data = _checks(d)
    pl = plan_mod.load(d)
    out, pending, unchecked, ok = [], 0, 0, 0
    for key, pg in st["pages"].items():
        if not pg.get("selected"):
            continue
        v = pg["versions"][pg["selected"] - 1]
        it = data["items"].get(v["path"])
        if not it:
            continue
        if it["status"] == "pending":
            pending += 1
            continue
        if it["status"] == "ok":
            ok += 1
            continue
        if it["status"] == "unchecked":
            unchecked += 1
        page = None
        if pl is not None and plan_mod.ART_ID.match(key):
            page = plan_mod.page_of_art(pl, key)[0]
        elif key.isdigit():
            page = int(key)
        out.append({"key": key, "v": v["v"], "page": page, "status": it["status"], "attempt": it["attempt"],
                    "approved": bool(pg.get("approved")), "note": it.get("note"),
                    "characters": [{"name": n, **{k: r.get(k) for k in ("state", "distance")}}
                                   for n, r in (it.get("result") or {}).items()],
                    "threshold": it.get("threshold")})
    out.sort(key=lambda r: (r["status"] != "mismatch", r["page"] or 0))
    return {"items": out, "pending": pending, "unchecked": unchecked, "ok": ok}


# ------------------------------------------------------------------ öneri ve çeviri (ana model)
CARD_SCHEMA = {"type": "object", "additionalProperties": False,
               "required": ["kind", "age", "look_tr", "outfits", "colors"],
               "properties": {
                   "kind": {"type": "string", "enum": list(KINDS)}, "age": {"type": "string"},
                   "look_tr": {"type": "string"},
                   "outfits": {"type": "array", "items": {
                       "type": "object", "additionalProperties": False, "required": ["name", "look_tr", "color"],
                       "properties": {"name": {"type": "string"}, "look_tr": {"type": "string"},
                                      "color": {"type": "string", "pattern": "^(#[0-9A-Fa-f]{6})?$"}}}},
                   "colors": {"type": "object", "additionalProperties": False, "required": list(PARTS),
                              "properties": {k: {"type": "string", "pattern": "^(#[0-9A-Fa-f]{6})?$"} for k in PARTS}}}}
EN_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["look_en", "outfits"],
             "properties": {"look_en": {"type": "string"},
                            "outfits": {"type": "array", "items": {"type": "string"}}}}


def _task(d: Path, **fields) -> None:
    with _locked(d / "karakter.kilit"):
        cur = _read(d / TASKS, {}) or {}
        cur.update(fields, updated_at=_now())
        _write(d / TASKS, cur)


async def suggest(d: Path, names: list[str] | None, by: str) -> dict:
    """(a) İşin sanat planındaki karakterlerden taslak kart: İngilizce tarif ve kıyafetler plandan, Türkçe tarif,
    tür, yaş ve tariften okunan renkler ana modelden; işin karakter referans çizimi birincil referans olur; kitap
    paletindeki karakter rengi bağlanır. Dizide aynı adlı kart varsa (önceki kitaptan gelen) dokunulmaz."""
    from ..prompts import render
    from . import plan as plan_mod
    from . import studio
    from .run import FileLlm
    series = job_series(d)
    if not series:
        raise NoSeries(d.name)
    ap = studio.read(d, "artplan.json") or {}
    ms = studio.read(d, "manuscript.json") or {}
    prof = studio.read(d, "profile.json") or {}
    pl = plan_mod.load(d) or {}
    pal = (pl.get("palette") or {}).get("characters") or {}
    sheets = studio.studio_state(d).get("characters", {})
    have = load(series["id"])
    llm = FileLlm(d / "provenance.jsonl")
    made, skipped = [], []
    wanted = {fold(n) for n in names or []}
    for c in ap.get("characters", []):
        if wanted and fold(c["name"]) not in wanted:
            continue
        if any(fold(c["name"]) in {fold(x["name"]), *map(fold, x.get("aliases", []))} for x in have["cards"]):
            skipped.append(c["name"])
            continue
        outfits = "\n".join(f"- «{o['name']}»{' (varsayılan)' if o['name'] == c.get('default_outfit') else ''}: "
                            f"{o['look']}" for o in c.get("outfits", [])) or "(yok)"
        ref, prompt = render("production_character_card", title=ms.get("title") or "", name=c["name"],
                             age=f"{prof.get('age_min', '')}-{prof.get('age_max', '')}", species=c.get("species", ""),
                             look=c.get("look", ""), outfits=outfits,
                             quotes="\n".join(f"- {q}" for q in c.get("from_text", [])) or "(yok)")
        out, _ = await llm.chat("book-director", [{"role": "user", "content": prompt}], prompt=ref,
                                schema=CARD_SCHEMA, max_tokens=1500, thinking=False, temperature=0.2)
        by_name = {o["name"]: o for o in out["outfits"]}
        card_in = {"name": c["name"], "kind": out["kind"], "age": out["age"], "species_en": c.get("species", ""),
                   "look_tr": out["look_tr"], "look_en": c.get("look", ""),
                   "colors": {k: v for k, v in out["colors"].items() if v}, "palette_color": pal.get(c["name"]),
                   "outfits": [{"name": o["name"], "look_en": o["look"],
                                "look_tr": (by_name.get(o["name"]) or {}).get("look_tr", ""),
                                "color": (by_name.get(o["name"]) or {}).get("color") or None,
                                "default": o["name"] == c.get("default_outfit")} for o in c.get("outfits", [])]}
        _, card = create_card(series, None, card_in, by, origin={"job": d.name, "title": ms.get("title"),
                                                                  "from": "sanat planı"})
        sheet = sheets.get(c["name"])
        if sheet and Path(sheet).exists():
            add_ref(series, card["id"], Path(sheet).read_bytes(), {"kind": "sheet", "job": d.name}, by)
        made.append(c["name"])
    return {"made": made, "skipped": skipped, "series": series["id"]}


async def translate(d: Path, cid: str, by: str) -> dict:
    """Editörün Türkçe tarifinden modele giden İngilizce tarif (kart ve kıyafetler)."""
    from ..prompts import render
    from .run import FileLlm
    series = job_series(d)
    if not series:
        raise NoSeries(d.name)
    card = _card(load(series["id"]), cid)
    outfits = "\n".join(f"{i + 1}. «{o['name']}»: {o.get('look_tr') or o.get('look_en') or ''}"
                        for i, o in enumerate(card.get("outfits", []))) or "(yok)"
    ref, prompt = render("production_character_card_en", name=card["name"], look=card.get("look_tr", ""),
                         outfits=outfits)
    out, _ = await FileLlm(d / "provenance.jsonl").chat(
        "book-director", [{"role": "user", "content": prompt}], prompt=ref, schema=EN_SCHEMA, max_tokens=1200,
        thinking=False, temperature=0.0)

    def fn(data):
        c = _card(data, cid)
        c["look_en"] = out["look_en"].strip() or c.get("look_en", "")
        for o, en in zip(c.get("outfits", []), out["outfits"]):
            if en.strip():
                o["look_en"] = en.strip()
        c.update(en_stale=False, status="draft", version=int(c.get("version") or 1) + 1, updated_by=by,
                 updated_at=_now())
        return c
    _, card = mutate(series, None, by, f"modele giden tarif yenilendi: {card['name']}", fn)
    return {"card": cid}


def apply_palette(d: Path, cid: str, by: str) -> dict:
    """Kartın kitap paletindeki rengini bu işin sayfa planı paletine yazar (karakterin konuşma/ad rengi)."""
    from . import plan as plan_mod
    series = job_series(d)
    if not series:
        raise NoSeries(d.name)
    card = _card(load(series["id"]), cid)
    if not card.get("palette_color"):
        raise ValueError("Kartta kitap paleti rengi yok")
    pl = plan_mod.load(d)
    if pl is None:
        raise plan_mod.NoPlan(d.name)
    pal = dict(pl.get("palette") or {})
    chars = dict(pal.get("characters") or {})
    ap = _read(d / "artplan.json", {}) or {}
    names = [c["name"] for c in ap.get("characters", []) if fold(c["name"]) in
             {fold(card["name"]), *map(fold, card.get("aliases", []))}] or [card["name"]]
    for n in names:
        chars[n] = card["palette_color"]
    pal["characters"] = chars
    plan, _ = plan_mod.set_palette(d, pl["rev"], pal, by)
    return {"palette": plan["palette"], "rev": plan["rev"]}


# ------------------------------------------------------------------ ekran görünümü
def view(d: Path) -> dict:
    from . import studio
    series = job_series(d)
    data = load(series["id"]) if series and series["exists"] else {"rev": 0, "cards": []}
    ap = studio.read(d, "artplan.json") or {}
    st = studio.studio_state(d)
    sheets = st.get("characters", {})
    by_art = {s.get("art_id"): s for s in ap.get("scenes", []) if s.get("art_id")}
    by_page = {str(s["page"]): s for s in ap.get("scenes", [])}
    cardset = CardSet(series, data["cards"])
    book = []
    for i, c in enumerate(ap.get("characters", [])):
        card = cardset.card(c["name"])
        cands = []
        if c["name"] in sheets and Path(sheets[c["name"]]).exists():
            cands.append({"from": "sheet", "name": c["name"], "i": i})
        for key, pg in st["pages"].items():
            sc = by_art.get(key) or by_page.get(key)
            if not sc or c["name"] not in sc.get("characters", []) or not pg.get("selected") or not pg.get("approved"):
                continue
            cands.append({"from": "art", "key": key, "v": pg["selected"]})
        book.append({"name": c["name"], "role": c.get("role"), "species": c.get("species"), "card": card and card["id"],
                     "card_status": card and card.get("status"), "candidates": cands})
    return {"series": series, "rev": data.get("rev", 0), "cards": data["cards"], "book": book,
            "kinds": list(KINDS), "parts": {k: v[0] for k, v in PARTS.items()},
            "max_retries": max_retries(), "check": mismatches(d), "task": _read(d / TASKS),
            "palette": ((_read(d / "plan.json", {}) or {}).get("palette") or {})}


# ------------------------------------------------------------------ Temporal (stüdyo işçisi, editor-production)
CHECK_RETRY = RetryPolicy(initial_interval=timedelta(seconds=30), maximum_attempts=2,
                          non_retryable_error_types=["ValueError", "KeyError", "FileNotFoundError"])
BEAT = timedelta(minutes=3)


@activity.defn(name="production_character_check")
async def check_activity(job: str) -> dict:
    """Karakter denetimi (GPU: görsel okuyucu + gerekirse resim modeli). busy.json tutar; bitince sırada başka
    stüdyo işi yoksa görsel modeli kapatır (flow._release_if_idle)."""
    from . import flow, studio
    d = studio.job_dir(job)
    studio.set_busy(d, {"key": "karakter", "mode": "check", "since": time.time(), "queued": False,
                        "workflow_id": activity.info().workflow_id})
    _task(d, check={"status": "running", "workflow": activity.info().workflow_id})
    try:
        out = await flow._beating(run_check(d))
    except Exception as e:
        final = flow._last(CHECK_RETRY) or isinstance(e, (ValueError, KeyError, FileNotFoundError))
        _task(d, check={"status": "fail" if final else "running", "error": str(e)[:300]})
        if final:
            studio.set_busy(d, None)
            await flow._release_if_idle(d)
        raise
    _task(d, check={"status": "done", "result": out})
    studio.set_busy(d, None)
    if out.get("regenerated"):
        await flow._release_if_idle(d)
    return out


@activity.defn(name="production_character_cards")
async def cards_activity(job: str, op: str, names: list[str], cid: str, by: str) -> dict:
    """Öneri (sanat planından taslak kartlar) ya da çeviri (Türkçe → modele giden tarif); yalnız ana model."""
    from . import flow, studio
    d = studio.job_dir(job)
    tag = {"workflow": activity.info().workflow_id, **({"card": cid} if cid else {})}
    _task(d, **{op: {"status": "running", **tag}})
    try:
        out = await flow._beating(suggest(d, names, by) if op == "suggest" else translate(d, cid, by))
    except Exception as e:
        final = flow._last(CHECK_RETRY) or isinstance(e, (ValueError, KeyError, FileNotFoundError, NoSeries))
        _task(d, **{op: {"status": "fail" if final else "running", "error": str(e)[:300], **tag}})
        raise
    _task(d, **{op: {"status": "done", "result": out, **tag}})
    return out


@workflow.defn(name="CharacterCheck")
class CharacterCheck:
    @workflow.run
    async def run(self, job: str) -> dict:
        return await workflow.execute_activity("production_character_check", job,
                                               start_to_close_timeout=timedelta(hours=2),
                                               heartbeat_timeout=BEAT, retry_policy=CHECK_RETRY)


@workflow.defn(name="CharacterCards")
class CharacterCards:
    @workflow.run
    async def run(self, job: str, op: str, names: list[str], cid: str, by: str) -> dict:
        return await workflow.execute_activity("production_character_cards", args=[job, op, names, cid, by],
                                               start_to_close_timeout=timedelta(minutes=30),
                                               heartbeat_timeout=BEAT, retry_policy=CHECK_RETRY)


ACTIVITIES = [check_activity, cards_activity]
WORKFLOWS = [CharacterCheck, CharacterCards]
