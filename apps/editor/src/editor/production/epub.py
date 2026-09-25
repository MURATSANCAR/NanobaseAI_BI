"""E-kitap (EPUB 3): basılı kitabın sayfa planından (plan.json) tek kaynaktan e-kitap.

İki biçim, kitaptan bağımsız kuralla seçilir (`decide`):
- **Sabit sayfa** (resimli kitap: her sayfa resimli ya da sayfaların en az yarısında görsel): EPUB 3 fixed-layout
  (`rendition:layout pre-paginated`). Viewport kesim ölçüsüdür (taşma payı kırpılır); 1 mm = `K` CSS pikseli. Resim
  katmanı görseldir (kutudaki görünen parça kırpılıp küçültülür), METİN GERÇEK METİNDİR: yazı kutusu, balon yazısı ve
  serbest yazı mutlak konumlu HTML. Balonun çizgisi satır içi SVG (plan.bubble_shapes'in çokgenleri), şekiller ve efekt
  yazılar dizginin vektör çiziminden SVG (templates/epub/layer.typ, elements.typ); efekt yazının ve şekil yazısının
  gerçek metni aynı kutuda saydam yazı olarak durur (seçilir, sesli okunur). Sayfa yanları basılı kitapla aynı: tek
  sayfa sağda, çift sayfa solda; kapak ortada.
- **Akışkan** (metin ağırlıklı kitap): EPUB 3 reflowable; bölümler (başlık bloğundan), içindekiler, kapak, iç kapak,
  künye, yazar tanıtımı, diyalog, dipnot (metindeki [n] / üst simge işaretiyle aynı bölümdeki not paragrafı eşleşince),
  basılı sayfa numaraları (sayfa sınırı paragrafın içinde de olsa yerinde).

Ortak: OPF üst verisi (başlık, yazar, yayınevi, dil tr, e-ISBN — basılı ISBN'den ayrı; yoksa kalıcı uuid ve uyarı,
basılı ISBN `dc:source`), kapak görseli, erişilebilirlik üst verisi (schema.org accessMode, accessModeSufficient,
accessibilityFeature, accessibilityHazard, accessibilitySummary), fontlar gömülü (lisans denetimiyle: kısıtlı font
gömülmez; açık lisans dışındaki font karartılır), her görsele Türkçe alt metin (`alt.json`: editörün yazdığı her zaman
kazanır; yoksa art planındaki sahne tarifinden model gateway üzerinden, sahnesi olmayan görselde figürün tarifinden ya
da görsel okuyucudan; model yoksa sahnenin Türkçe «an» cümlesi, gözden geçir işaretiyle).

Denetim (`check`): her üretimde yapısal denetim (zip düzeni, OPF, içerik listesi, XHTML, içindekiler, sabit sayfa
viewport'u, alt metin); tam e-kitap denetimi kuruluysa (EDITOR_EPUBCHECK_JAR + java) o da koşar, bulgular Türkçeye
çevrilir. Sonuç `epub/state.json`'da; ön kontrole bilgi satırı (`preflight_checks`). Ekrana giden metinlerde teknoloji
adı geçmez.

İş klasöründe: epub/kitap.epub, epub/state.json, epub/alt.json, epub/meta.json, epub/katman/ (vektör katman dizgisi).
"""

from __future__ import annotations

import hashlib
import html
import io
import json
import os
import re
import shutil
import subprocess
import tempfile
import time
import uuid
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from . import plan as plan_mod
from . import studio

DIR = "epub"
FILE = "kitap.epub"
STATE, ALT, META = "state.json", "alt.json", "meta.json"
K = 8.0                                   # sabit sayfada 1 mm = 8 CSS pikseli (viewport = kesim × K)
DPR = 2.0                                 # görsel çözünürlüğü: gösterilen CSS pikselinin 2 katı (yüksek yoğunluklu ekran)
PT_PX = 96 / 72                           # 1 pt = 4/3 CSS px (CSS'in sabit oranı)
PX_PER_MM = 96 / 25.4
OPF_PATH = "OEBPS/content.opf"
LAYER_TEMPLATE = Path(__file__).resolve().parent / "templates" / "epub" / "layer.typ"
KEY = re.compile(r"^(kapak|a_[0-9a-f]{8}|g_[0-9a-f]{8})$")
BUILD = re.compile(r"^[0-9a-f]{12}$")
LAYOUTS = ("auto", "fixed", "reflow")
INK = "#2C2C2A"
FOLIO_INK = "#6E6E6E"                     # plan.typ: luma(110)
PRINT_ONLY = ("Baskı", "Baskı ve Cilt", "Matbaa Sertifika No", "Matbaa Adresi")   # basılı baskıya ait künye satırları
MIME = {".xhtml": "application/xhtml+xml", ".css": "text/css", ".jpg": "image/jpeg", ".png": "image/png",
        ".svg": "image/svg+xml", ".ttf": "font/ttf", ".otf": "font/otf", ".ncx": "application/x-dtbncx+xml",
        ".opf": "application/oebps-package+xml"}
OPEN_LICENSES = (("open font license", "SIL OFL 1.1"), ("openfontlicense", "SIL OFL 1.1"), ("/ofl", "SIL OFL 1.1"),
                 ("apache", "Apache 2.0"), ("ubuntu font licence", "Ubuntu Font Licence"))


def max_mp() -> float:
    """Tek görselin en çok megapikseli (e-kitap okuyucularının sabit sayfa görsel sınırı; ayar EPUB_IMAGE_MP)."""
    try:
        return max(0.5, float(os.environ.get("EPUB_IMAGE_MP", "4")))
    except ValueError:
        return 4.0


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _dir(d: Path) -> Path:
    p = d / DIR
    p.mkdir(exist_ok=True)
    return p


def esc(s) -> str:
    return html.escape(str(s if s is not None else ""), quote=True)


def _f(v: float) -> str:
    return f"{v:.2f}".rstrip("0").rstrip(".")


# ------------------------------------------------------------------ durum, e-ISBN
def read_state(d: Path) -> dict:
    return studio.read(d / DIR, STATE) or {"status": "none"}


def set_state(d: Path, **fields) -> dict:
    st = {**read_state(d), **fields, "updated": time.time()}
    studio.write(_dir(d), STATE, st)
    return st


def isbn13(v: str | None) -> str | None:
    """ISBN-13 (tire/boşluk atılır; 10 haneli ISBN 978 önekiyle çevrilir). Denetim hanesi tutmazsa None."""
    s = re.sub(r"[\s-]", "", str(v or "")).upper()
    if re.fullmatch(r"[0-9]{9}[0-9X]", s):
        if sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(s)) % 11:
            return None
        s = "978" + s[:9]
        s += str((10 - sum((1 if i % 2 == 0 else 3) * int(c) for i, c in enumerate(s)) % 10) % 10)
    if not re.fullmatch(r"97[89][0-9]{10}", s):
        return None
    if sum((1 if i % 2 == 0 else 3) * int(c) for i, c in enumerate(s)) % 10:
        return None
    return s


def meta(d: Path) -> dict:
    return studio.read(d / DIR, META) or {}


def print_isbn(d: Path, ms=None) -> str | None:
    """Basılı kitabın ISBN'i: künyede elle girilen ya da kitabın kaydındaki."""
    ms = ms or studio._manuscript(d)
    fr = studio.read(d, "front.json") or {}
    return isbn13((fr.get("manual") or {}).get("ISBN") or ms.meta.get("ISBN"))


def set_meta(d: Path, eisbn: str | None, by: str) -> dict:
    """e-ISBN (basılı ISBN'den ayrı alan). Boş değer alanı temizler; geçersiz ISBN ve basılı ISBN'in aynısı reddedilir."""
    m = meta(d)
    raw = (eisbn or "").strip()
    if raw:
        v = isbn13(raw)
        if v is None:
            raise ValueError("e-ISBN geçersiz: 13 haneli ISBN yazın (denetim hanesi tutmuyor ya da hane sayısı eksik).")
        if v == print_isbn(d):
            raise ValueError("e-ISBN basılı kitabın ISBN'iyle aynı olamaz; e-kitap için ayrı ISBN alınır.")
        m["eisbn"] = v
    else:
        m.pop("eisbn", None)
    m.update(by=by, at=_now())
    studio.write(_dir(d), META, m)
    return m


# ------------------------------------------------------------------ biçim seçimi
def decide(d: Path, plan: dict | None, want: str = "auto") -> tuple[str, str]:
    """Sabit sayfa ya da akışkan; gerekçesiyle. Kural: her sayfa resimli kitap ya da görselli sayfa oranı ≥ %50 →
    sabit sayfa; öteki (resimsiz, bölüm başı resimli, roman) → akışkan. Editör seçerse o geçer."""
    if want not in LAYOUTS:
        raise ValueError("biçim auto, fixed ya da reflow olmalı")
    if plan is None:
        if want == "fixed":
            raise ValueError("Sabit sayfa e-kitap için önce sayfa planı kurulmalı.")
        return "reflow", "Sayfa planı yok: metin akışkan e-kitap olarak dizilir."
    n = len(plan["pages"]) or 1
    seen = sum(1 for p in plan["pages"] if p["art"] or p["figures"])
    share = seen / n
    ill = studio._spec(d).illustration
    if want == "fixed":
        return "fixed", "Editör seçimi: sabit sayfa."
    if want == "reflow":
        return "reflow", "Editör seçimi: akışkan metin."
    if ill == "HER_SAYFA" or share >= 0.5:
        why = "her sayfa resimli kitap" if ill == "HER_SAYFA" else f"sayfaların %{share * 100:.0f}'inde görsel var"
        return "fixed", f"Sabit sayfa: {why}; sayfa düzeni basılı kitaptaki gibi korunur."
    why = "resimsiz kitap" if ill == "YOK" and not seen else f"görselli sayfa oranı %{share * 100:.0f}"
    return "reflow", f"Akışkan: {why}; metin okurun ekranına ve yazı boyutuna göre akar."


# ------------------------------------------------------------------ alt metin
def _scenes(d: Path) -> dict[str, dict]:
    return {s["art_id"]: s for s in (studio.read(d, "artplan.json") or {}).get("scenes", []) if s.get("art_id")}


def images(d: Path, plan: dict) -> list[dict]:
    """E-kitaba giren görseller (alt metin ister): kapak, sayfa resimleri (a_…), sayfaya konmuş figür/fotoğraflar (g_…).
    Her biri: key, kind, pages (basılı sayfa no), basis (otomatik alt metnin dayanağı; değişince yenilenir), path."""
    sel = studio.selected_art(d)
    st = studio.studio_state(d)["pages"]
    scenes = _scenes(d)
    out: dict[str, dict] = {}
    ms = studio._manuscript(d)
    out["kapak"] = {"key": "kapak", "kind": "kapak", "pages": [], "basis": f"{ms.title}|{ms.author or ''}",
                    "path": sel.get("kapak")}
    for i, pg in enumerate(plan["pages"]):
        no = plan_mod.FRONT + i + 1
        a = pg["art"]
        if a and a.get("asset") in plan.get("assets", {}):
            _asset_item(out, a["asset"], plan, d, no)
        elif a and a.get("id"):
            key = a["id"]
            it = out.setdefault(key, {"key": key, "kind": "resim", "pages": [], "path": sel.get(key)})
            it["pages"].append(no)
            sc = scenes.get(key) or {}
            vv = st.get(key) or {}
            ver = vv["versions"][vv["selected"] - 1] if vv.get("selected") else {}
            it["scene"] = {k: sc.get(k) for k in ("scene", "moment", "characters", "setting")} if sc else None
            it["direction"] = ver.get("prompt") or ""
            it["basis"] = json.dumps([it["scene"], it["direction"], vv.get("selected")], ensure_ascii=False)
        for f in pg["figures"]:
            if f["asset"] in plan.get("assets", {}):
                _asset_item(out, f["asset"], plan, d, no)
    return list(out.values())


def _asset_item(out: dict, gid: str, plan: dict, d: Path, no: int) -> None:
    a = plan["assets"][gid]
    it = out.setdefault(gid, {"key": gid, "kind": "figür" if a.get("kind") == "figure" else "fotoğraf", "pages": [],
                              "path": str(d / a["path"]), "prompt": a.get("prompt") or "", "name": a.get("name") or "",
                              "basis": json.dumps([a.get("prompt"), a.get("path")], ensure_ascii=False)})
    if no not in it["pages"]:
        it["pages"].append(no)


def alt_store(d: Path) -> dict:
    return studio.read(d / DIR, ALT) or {}


def _basis_hash(item: dict) -> str:
    return hashlib.sha1(item.get("basis", "").encode()).hexdigest()[:12]


def alt_list(d: Path, plan: dict) -> list[dict]:
    """Ekrandaki gözden geçirme listesi: görsel, sayfaları, alt metin, kaynağı, gözden geçirilmeli mi."""
    store = alt_store(d)
    out = []
    for it in images(d, plan):
        rec = store.get(it["key"]) or {}
        stale = rec.get("source") != "editor" and rec.get("basis") not in (None, _basis_hash(it))
        text = rec.get("text") or ""
        out.append({"key": it["key"], "kind": it["kind"], "pages": it["pages"], "text": text,
                    "source": rec.get("source") or "", "by": rec.get("by"), "at": rec.get("at"),
                    "review": not text or stale or rec.get("source") in ("an", "ad"), "stale": stale,
                    "has_image": bool(it.get("path")) and Path(it["path"]).exists()})
    return out


def set_alt(d: Path, key: str, text: str, by: str) -> dict:
    if not KEY.match(key or ""):
        raise KeyError(key)
    text = " ".join(str(text or "").split())
    if len(text) > 1000:
        raise ValueError("Alt metin en çok 1000 harf olabilir.")
    store = alt_store(d)
    if text:
        store[key] = {"text": text, "source": "editor", "by": by, "at": _now()}
    else:
        store.pop(key, None)                    # boş: otomatik metne döner (bir sonraki üretimde önerilir)
    studio.write(_dir(d), ALT, store)
    return store.get(key) or {}


def cover_alt(ms) -> str:
    return f"{ms.title} kitabının kapağı" + (f"; yazar {ms.author}" if ms.author else "")


def _clean_alt(s: str) -> str:
    s = " ".join(str(s or "").split()).strip().strip('"“”«»')
    s = re.sub(r"^(bu )?(resim|görsel|illüstrasyon|çizim|fotoğraf)(de|da|te|ta)?[:,]?\s+", "", s, flags=re.I)
    return (s[:1].upper() + s[1:])[:600] if s else ""


ALT_SCHEMA = {"type": "object", "additionalProperties": False, "required": ["alt"],
              "properties": {"alt": {"type": "string"}}}


async def _alt_from_scene(it: dict, llm) -> str:
    from ..prompts import render
    sc = it.get("scene") or {}
    ref, prompt = render("production_alt_text", scene=sc.get("scene") or "(yok)", moment=sc.get("moment") or "(yok)",
                         setting=sc.get("setting") or "(yok)", characters=", ".join(sc.get("characters") or []) or "(yok)",
                         direction=it.get("direction") or "(yok)")
    out, _ = await llm.chat("book-director", [{"role": "user", "content": prompt}], prompt=ref, schema=ALT_SCHEMA,
                            max_tokens=500, thinking=False, temperature=0.0)
    return _clean_alt(out["alt"])


async def _alt_from_image(it: dict, llm) -> str:
    import base64

    from PIL import Image

    from ..prompts import render
    im = Image.open(it["path"])
    im = im.convert("RGBA" if im.mode in ("RGBA", "LA", "P") else "RGB")
    if im.mode == "RGBA":                        # saydam figür beyaz zeminde
        bg = Image.new("RGB", im.size, "white")
        bg.paste(im, mask=im.getchannel("A"))
        im = bg
    im.thumbnail((1024, 1024))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=85)
    ref, prompt = render("production_alt_image", hint=it.get("prompt") or it.get("name") or "(yok)")
    msg = [{"role": "user", "content": [
        {"type": "text", "text": prompt},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()}}]}]
    out, _ = await llm.chat("book-vision-fast", msg, prompt=ref, schema=ALT_SCHEMA, max_tokens=500, thinking=False,
                            temperature=0.0)
    return _clean_alt(out["alt"])


async def suggest(d: Path, it: dict, llm) -> dict:
    """Bir görselin otomatik alt metni: sahne tarifi (model) → sahne yok, figür tarifi → görsel okuyucu (model).
    Model yanıt vermezse sahnenin Türkçe «an» cümlesi ya da figür tarifi (gözden geçir). Dönen kayıt (yazılmaz)."""
    ms = studio._manuscript(d)
    if it["kind"] == "kapak":
        return {"text": cover_alt(ms), "source": "kapak"}
    err = None
    if it.get("scene") and it["scene"].get("scene"):
        try:
            t = await _alt_from_scene(it, llm)
            if t:
                return {"text": t, "source": "sahne"}
        except Exception as e:  # noqa: BLE001 - yedek yola düşer
            err = e
    elif it.get("path") and Path(it["path"]).exists():
        try:
            t = await _alt_from_image(it, llm)
            if t:
                return {"text": t, "source": "model"}
        except Exception as e:  # noqa: BLE001
            err = e
    if it.get("prompt"):
        return {"text": _clean_alt(it["prompt"]), "source": "tarif"}
    sc = it.get("scene") or {}
    if sc.get("moment"):
        return {"text": _clean_alt(sc["moment"]), "source": "an",
                "note": "öneri alınamadı; sayfanın anından yazıldı" if err else ""}
    return {"text": "", "source": "", "note": "alt metin önerilemedi"}


async def fill_alts(d: Path, plan: dict, llm, progress=None) -> dict:
    """Eksik ya da dayanağı değişmiş otomatik alt metinleri önerir; editörün yazdığına dokunmaz. Dönen sayılar."""
    store = alt_store(d)
    todo = [it for it in images(d, plan)
            if (store.get(it["key"]) or {}).get("source") != "editor"
            and ((store.get(it["key"]) or {}).get("basis") != _basis_hash(it) or not (store.get(it["key"]) or {}).get("text"))]
    made = fell = 0
    for i, it in enumerate(todo):
        if progress:
            progress(i, len(todo))
        rec = await suggest(d, it, llm)
        store = alt_store(d)                         # bu arada editör yazdıysa onunki kalır
        if (store.get(it["key"]) or {}).get("source") == "editor":
            continue
        store[it["key"]] = {**rec, "basis": _basis_hash(it), "by": "Zeki AI", "at": _now()}
        studio.write(_dir(d), ALT, store)
        made += 1
        fell += rec.get("source") in ("an", "")
    if progress:
        progress(len(todo), len(todo))
    return {"suggested": made, "fallback": fell}


async def suggest_one(d: Path, key: str, llm) -> dict:
    plan = plan_mod.load(d)
    it = next((x for x in images(d, plan) if x["key"] == key), None) if plan else None
    if it is None:
        raise KeyError(key)
    rec = await suggest(d, it, llm)
    store = alt_store(d)
    store[key] = {**rec, "basis": _basis_hash(it), "by": "Zeki AI", "at": _now()}
    studio.write(_dir(d), ALT, store)
    return store[key]


# ------------------------------------------------------------------ fontlar
@dataclass
class Face:
    family: str
    path: Path
    weight: str                     # "400" ya da değişken fontta "100 900"
    style: str                      # normal | italic
    license: str
    rfn: bool                       # OFL «Reserved Font Name»: değiştirilmez (alt küme alınmaz), olduğu gibi gömülür
    fs_type: int
    embed: bool
    obfuscate: bool
    name: str                       # e-kitaptaki dosya adı

    def report(self) -> dict:
        note = ("gömülmesine izin yok (font kısıtlı); okuyucunun yazı tipi kullanılır" if not self.embed else
                "karartılarak gömüldü (açık lisans değil)" if self.obfuscate else "olduğu gibi gömüldü")
        return {"family": self.family, "file": self.path.name, "license": self.license, "reserved_name": self.rfn,
                "fs_type": self.fs_type, "embedded": self.embed, "obfuscated": self.obfuscate, "note": note}


def _slug(s: str) -> str:
    s = s.lower().translate(str.maketrans("çğıöşüâîû", "cgiosuaiu"))
    return re.sub(r"[^a-z0-9]+", "-", s).strip("-") or "font"


def font_faces(families: list[str], font_dir: Path | None = None) -> list[Face]:
    """Kitabın kullandığı aileler için fontlar ve lisans durumu (ad tablosunun lisans alanı ve OS/2 fsType'tan)."""
    from fontTools.ttLib import TTFont
    font_dir = font_dir or studio.fonts()
    want = {f.casefold() for f in families if f}
    out = []
    for p in sorted(font_dir.glob("*")) if font_dir.exists() else []:
        if p.suffix.lower() not in (".ttf", ".otf") or p.name.startswith("._"):
            continue
        try:
            t = TTFont(p, lazy=True)
        except Exception:  # noqa: BLE001 - okunamayan dosya atlanır
            continue
        n = t["name"]
        fam = (n.getDebugName(16) or n.getDebugName(1) or "").strip()
        if fam.casefold() not in want:
            continue
        os2 = t["OS/2"]
        italic = bool(os2.fsSelection & 1) or "italic" in (n.getDebugName(17) or n.getDebugName(2) or "").lower()
        if "fvar" in t:
            ax = next((a for a in t["fvar"].axes if a.axisTag == "wght"), None)
            weight = f"{int(ax.minValue)} {int(ax.maxValue)}" if ax else str(os2.usWeightClass)
        else:
            weight = str(os2.usWeightClass)
        text = " ".join(n.getDebugName(i) or "" for i in (0, 13, 14)).lower()
        lic = next((name for key, name in OPEN_LICENSES if key in text), "")
        fs = int(os2.fsType)
        embed = (fs & 0x000F) != 0x0002              # yalnız «kısıtlı lisans gömme» (2) gömülmez
        rfn = "reserved font name" in text
        name = f"{_slug(fam)}-{'var' if ' ' in weight else weight}{'-italic' if italic else ''}{p.suffix.lower()}"
        out.append(Face(fam, p, weight, "italic" if italic else "normal", lic or "bilinmiyor (lisans alanı boş)", rfn, fs,
                        embed, embed and not lic, name))
    return out


def obfuscate(data: bytes, uid: str) -> bytes:
    """IDPF font karartması: ilk 1040 bayt, benzersiz kimliğin (boşluksuz) SHA-1'iyle XOR (kendi tersidir)."""
    key = hashlib.sha1(re.sub(r"[ \u0009\u000d\u000a]", "", uid).encode()).digest()
    head = bytes(b ^ key[i % len(key)] for i, b in enumerate(data[:1040]))
    return head + data[1040:]


def _font_css(faces: list[Face], prefix: str) -> str:
    rules = []
    for f in faces:
        if f.embed:
            rules.append(f"@font-face {{ font-family: '{f.family}'; src: url({prefix}{f.name}); "
                         f"font-weight: {f.weight}; font-style: {f.style}; }}")
    return "\n".join(rules)


def _stack(family: str, serif: bool = True) -> str:
    return f"'{family}', {'serif' if serif else 'sans-serif'}"


# ------------------------------------------------------------------ paket
class Pack:
    """EPUB içeriği bellekte; `write` zip'e dizer (mimetype ilk ve sıkıştırmasız)."""

    def __init__(self):
        self.files: list[dict] = []           # {path (OEBPS'e göre), data, id, mt, props}
        self.spine: list[dict] = []           # {id, props, linear}
        self.encrypted: list[str] = []
        self.ids: set[str] = set()

    def add(self, path: str, data: bytes | str, *, id: str | None = None, props: str = "", mt: str | None = None) -> str:
        if isinstance(data, str):
            data = data.encode("utf-8")
        ext = Path(path).suffix.lower()
        iid = id or re.sub(r"[^A-Za-z0-9_-]", "-", path.replace("/", "-"))
        if not iid[0].isalpha():
            iid = "i-" + iid
        base, k = iid, 1
        while iid in self.ids:
            k += 1
            iid = f"{base}-{k}"
        self.ids.add(iid)
        self.files.append({"path": path, "data": data, "id": iid, "mt": mt or MIME[ext], "props": props})
        return iid

    def has(self, path: str) -> bool:
        return any(f["path"] == path for f in self.files)

    def write(self, out: Path, opf: str) -> None:
        tmp = out.with_suffix(".yeni")
        with zipfile.ZipFile(tmp, "w") as z:
            zi = zipfile.ZipInfo("mimetype", date_time=time.localtime()[:6])
            zi.compress_type = zipfile.ZIP_STORED
            z.writestr(zi, b"application/epub+zip")
            z.writestr(_zi("META-INF/container.xml"), CONTAINER)
            if self.encrypted:
                z.writestr(_zi("META-INF/encryption.xml"), _encryption(self.encrypted))
            z.writestr(_zi(OPF_PATH), opf)
            for f in self.files:
                z.writestr(_zi("OEBPS/" + f["path"]), f["data"])
        os.replace(tmp, out)


def _zi(name: str) -> zipfile.ZipInfo:
    zi = zipfile.ZipInfo(name, date_time=time.localtime()[:6])
    zi.compress_type = zipfile.ZIP_DEFLATED
    return zi


CONTAINER = ('<?xml version="1.0" encoding="UTF-8"?>\n'
             '<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">\n'
             f'  <rootfiles><rootfile full-path="{OPF_PATH}" media-type="application/oebps-package+xml"/></rootfiles>\n'
             '</container>\n')


def _encryption(paths: list[str]) -> str:
    items = "".join('  <enc:EncryptedData><enc:EncryptionMethod Algorithm="http://www.idpf.org/2008/embedding"/>'
                    f'<enc:CipherData><enc:CipherReference URI="{esc(p)}"/></enc:CipherData></enc:EncryptedData>\n'
                    for p in paths)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<encryption xmlns="urn:oasis:names:tc:opendocument:xmlns:container" '
            'xmlns:enc="http://www.w3.org/2001/04/xmlenc#">\n' + items + '</encryption>\n')


def xhtml(title: str, body: str, *, css: list[str], head: str = "", body_attr: str = "") -> str:
    links = "".join(f'<link rel="stylesheet" type="text/css" href="{c}"/>' for c in css)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<!DOCTYPE html>\n'
            '<html xmlns="http://www.w3.org/1999/xhtml" xmlns:epub="http://www.idpf.org/2007/ops" lang="tr" xml:lang="tr">\n'
            f'<head><meta charset="utf-8"/><title>{esc(title)}</title>{head}{links}</head>\n'
            f'<body{body_attr}>\n{body}\n</body>\n</html>\n')


# ------------------------------------------------------------------ görseller
def _save_image(im, alpha: bool) -> tuple[bytes, str]:
    buf = io.BytesIO()
    if alpha:
        im.save(buf, "PNG", optimize=True)
        return buf.getvalue(), ".png"
    im.convert("RGB").save(buf, "JPEG", quality=84, optimize=True, progressive=True)
    return buf.getvalue(), ".jpg"


def _fit_px(w_css: float, h_css: float, src_w: int, src_h: int) -> tuple[int, int]:
    """Hedef piksel: gösterilen CSS pikselinin DPR katı; kaynaktan büyük değil; en çok `max_mp()` megapiksel."""
    tw, th = max(1.0, w_css * DPR), max(1.0, h_css * DPR)
    s = min(1.0, tw / src_w, th / src_h) if src_w and src_h else 1.0
    w, h = src_w * s, src_h * s
    cap = max_mp() * 1e6
    if w * h > cap:
        c = (cap / (w * h)) ** 0.5
        w, h = w * c, h * c
    return max(1, int(round(w))), max(1, int(round(h)))


def crop_visible(path: Path, draw: dict, clip: dict, trim: dict) -> tuple[bytes, str, dict] | None:
    """Kutuya çizilen görselin (draw: görselin sayfadaki dikdörtgeni, mm) kutu (clip) ve kesim (trim) içinde kalan
    parçası; e-kitapta bu parça yerine konur. Dönen: (bayt, uzantı, kesimdeki yeri mm) ya da görünür parça yoksa None."""
    from PIL import Image
    x0 = max(draw["x"], clip["x"], trim["x"])
    y0 = max(draw["y"], clip["y"], trim["y"])
    x1 = min(draw["x"] + draw["w"], clip["x"] + clip["w"], trim["x"] + trim["w"])
    y1 = min(draw["y"] + draw["h"], clip["y"] + clip["h"], trim["y"] + trim["h"])
    if x1 - x0 < 0.2 or y1 - y0 < 0.2:
        return None
    im = Image.open(path)
    alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    im = im.convert("RGBA" if alpha else "RGB")
    sx, sy = im.width / draw["w"], im.height / draw["h"]
    box = (int(round((x0 - draw["x"]) * sx)), int(round((y0 - draw["y"]) * sy)),
           int(round((x1 - draw["x"]) * sx)), int(round((y1 - draw["y"]) * sy)))
    part = im.crop(box)
    w, h = _fit_px((x1 - x0) * K, (y1 - y0) * K, part.width, part.height)
    if (w, h) != part.size:
        part = part.resize((w, h), Image.Resampling.LANCZOS)
    data, ext = _save_image(part, alpha)
    return data, ext, {"x": x0 - trim["x"], "y": y0 - trim["y"], "w": x1 - x0, "h": y1 - y0}


def scaled(path: Path, w_css: float, h_css: float) -> tuple[bytes, str, int, int]:
    from PIL import Image
    im = Image.open(path)
    alpha = im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info)
    im = im.convert("RGBA" if alpha else "RGB")
    w, h = _fit_px(w_css, h_css, im.width, im.height)
    if (w, h) != im.size:
        im = im.resize((w, h), Image.Resampling.LANCZOS)
    data, ext = _save_image(im, alpha)
    return data, ext, w, h


def contain_rect(bx: dict, pw: int, ph: int) -> dict:
    k = min(bx["w"] / pw, bx["h"] / ph)
    w, h = pw * k, ph * k
    return {"x": bx["x"] + (bx["w"] - w) / 2, "y": bx["y"] + (bx["h"] - h) / 2, "w": w, "h": h}


def cover_image(d: Path, spec, ms) -> tuple[bytes, str] | None:
    """Kapak görseli: dizilmiş kapağın ön yüzü (başlık ve yazar yazısıyla), yoksa seçili kapak resmi, yoksa iç kapak."""
    import pymupdf
    from PIL import Image
    mmpt = 72 / 25.4
    cpdf = d / "kapak" / "kapak.pdf"
    width_px = 1600
    if cpdf.exists():
        info = studio.read(d, "cover.json") or {}
        spine = float(info.get("spine_mm") or 0)
        x0 = (spec.bleed + spec.trim_w + spine) * mmpt
        clip = pymupdf.Rect(x0, spec.bleed * mmpt, x0 + spec.trim_w * mmpt, (spec.bleed + spec.trim_h) * mmpt)
        doc = pymupdf.open(cpdf)
        if clip.x1 <= doc[0].rect.x1 + 0.5:
            z = width_px / clip.width
            pix = doc[0].get_pixmap(matrix=pymupdf.Matrix(z, z), clip=clip, alpha=False)
            return pix.tobytes("jpeg", jpg_quality=88), ".jpg"
    art = studio.selected_art(d).get("kapak")
    if art and Path(art).exists():
        im = Image.open(art).convert("RGB")
        want = spec.trim_w / spec.trim_h
        if im.width / im.height > want:
            nw = int(im.height * want)
            im = im.crop(((im.width - nw) // 2, 0, (im.width - nw) // 2 + nw, im.height))
        else:
            nh = int(im.width / want)
            im = im.crop((0, (im.height - nh) // 2, im.width, (im.height - nh) // 2 + nh))
        im.thumbnail((width_px, width_px * 2))
        return _save_image(im, False)
    ipdf = d / "dizgi" / "ic-sayfalar.pdf"
    if ipdf.exists():
        doc = pymupdf.open(ipdf)
        r = doc[0].rect
        b = spec.bleed * mmpt
        clip = pymupdf.Rect(r.x0 + b, r.y0 + b, r.x1 - b, r.y1 - b)
        z = width_px / clip.width
        return doc[0].get_pixmap(matrix=pymupdf.Matrix(z, z), clip=clip, alpha=False).tobytes("jpeg", jpg_quality=88), ".jpg"
    return None


# ------------------------------------------------------------------ ortak yazı biçimi
def run_html(r: dict, fonts: dict, scale_pt=None) -> str:
    st = []
    if r.get("color"):
        c = r["color"]
        st.append(f"color:{c[:7]}" + (f";opacity:{int(c[7:9], 16) / 255:.2f}" if len(c) == 9 else ""))
    if r.get("weight"):
        st.append(f"font-weight:{int(r['weight'])}")
    if r.get("size"):
        st.append(f"font-size:{scale_pt(r['size']) if scale_pt else _f(r['size']) + 'pt'}")
    if r.get("font") in fonts:
        st.append(f"font-family:{fonts[r['font']]}")
    t = esc(r.get("text", ""))
    return f'<span style="{";".join(st)}">{t}</span>' if st else t


def runs_html(runs: list[dict], fonts: dict, scale_pt=None) -> str:
    return "".join(run_html(r, fonts, scale_pt) for r in runs)


def runs_text(runs: list[dict]) -> str:
    return "".join(r.get("text", "") for r in runs or [])


def _rgba(hex8: str | None) -> str:
    if not hex8:
        return "transparent"
    r, g, b = (int(hex8[i:i + 2], 16) for i in (1, 3, 5))
    a = int(hex8[7:9], 16) / 255 if len(hex8) == 9 else 1.0
    return f"rgba({r},{g},{b},{a:.3f})"


def kunye_rows(front: dict, eisbn: str | None, pisbn: str | None) -> list[tuple[str, str]]:
    """E-kitabın künyesi: basılı künyeden, basıma ait satırlar (baskı, matbaa) çıkar, kaynağı olmayan («—») satır
    yazılmaz; ISBN «ISBN (basılı)» olur, e-ISBN eklenir."""
    from .front import MISSING
    rows = []
    for label, value in front.get("kunye") or []:
        if not label or label in PRINT_ONLY or value in (MISSING, "", None):
            continue
        if label == "ISBN":
            continue
        rows.append((label, value))
    if pisbn:
        rows.append(("ISBN (basılı)", _isbn_fmt(pisbn)))
    if eisbn:
        rows.append(("e-ISBN", _isbn_fmt(eisbn)))
    return rows


def _isbn_fmt(s: str) -> str:
    return f"{s[:3]}-{s[3:]}" if len(s) == 13 else s


# ------------------------------------------------------------------ sabit sayfa
class Fixed:
    """Sabit sayfa e-kitap: plan.render_data'nın kutularından mutlak konumlu HTML."""

    def __init__(self, d: Path, plan: dict, pack: Pack, alts: dict, warn: list[str]):
        self.d, self.plan, self.pack, self.alts, self.warn = d, plan, pack, alts, warn
        self.spec = studio._spec(d)
        self.b = self.spec.bleed
        self.vw = int(round(self.spec.trim_w * K))
        self.vh = int(round(self.spec.trim_h * K))
        self.trim = {"x": self.b, "y": self.b, "w": self.spec.trim_w, "h": self.spec.trim_h}
        self.data = plan_mod.render_data(d, plan)
        self.fonts = {"body": _stack(self.spec.body_font), "heading": _stack(self.spec.heading_font, False)}
        self.layers: dict[tuple[str, int], str] = {}
        self.img_n = 0

    # -- birimler
    def px(self, mm: float) -> str:
        return _f(mm * K) + "px"

    def pt(self, size: float) -> str:
        return _f(size * PT_PX * K / PX_PER_MM) + "px"

    def pos(self, bx: dict, trim_rel: bool = False) -> str:
        x, y = (bx["x"], bx["y"]) if trim_rel else (bx["x"] - self.b, bx["y"] - self.b)
        return f"left:{self.px(x)};top:{self.px(y)};width:{self.px(bx['w'])};height:{self.px(bx['h'])}"

    def head(self) -> str:
        return f'<meta name="viewport" content="width={self.vw}, height={self.vh}"/>'

    def image(self, name: str, data: bytes, ext: str) -> str:
        path = f"images/{name}{ext}"
        if not self.pack.has(path):
            self.pack.add(path, data)
        return "../" + path

    # -- parçalar
    def art(self, a: dict, key: str | None, z: int = 0) -> str:
        if not a.get("path"):
            return ""
        src = self.d / "dizgi" / a["path"]
        if a["fit"] == "contain":
            from PIL import Image
            with Image.open(src) as im:
                draw = contain_rect(a["box"], *im.size)
        else:
            draw = {"x": a["box"]["x"] + a["dx"], "y": a["box"]["y"] + a["dy"], "w": a["iw"], "h": a["ih"]}
        got = crop_visible(src, draw, a["box"], self.trim)
        if got is None:
            return ""
        data, ext, at = got
        self.img_n += 1
        href = self.image(f"{key or 'resim'}-{self.img_n:03d}", data, ext)
        alt = self.alts.get(key or "", "")
        return f'<img class="art" src="{href}" alt="{esc(alt)}" style="{self.pos(at, True)};z-index:{z}"/>'

    def textbox(self, t: dict, z: int, extra_class: str = "", ghost: bool = False) -> str:
        pad = t.get("pad") or 0
        st = [self.pos(t["box"]), f"z-index:{z}", f"font-size:{self.pt(t['size'])}", f"color:{t['ink']}",
              f"text-align:{'justify' if t['align'] == 'justify' else 'center' if t['align'] == 'center' else 'left'}",
              f"padding:{self.px(pad)}"]
        if t.get("background") and not ghost:
            st += [f"background:{_rgba(t['background'])}", f"border-radius:{self.px(2)}"]
        if t.get("valign") == "horizon":
            st.append("display:flex;flex-direction:column;justify-content:center")
        if t.get("leading") is not None:
            st.append(f"line-height:{_f(0.7 + t['leading'])}")
        if "blocks" in t:
            inner = "".join(self.block(k) for k in t["blocks"])
        else:
            inner = f"<p>{runs_html(t.get('runs') or [], self.fonts, self.pt)}</p>"
        cls = "tb" + (" ghost" if ghost else "") + (f" {extra_class}" if extra_class else "")
        return f'<div class="{cls}" style="{";".join(st)}">{inner}</div>'

    def block(self, k: dict) -> str:
        body = runs_html(k["runs"], self.fonts, self.pt)
        if k["kind"] == "heading":
            return f'<h2 class="bh">{body}</h2>'
        if k["kind"] == "sound":
            return f'<p class="ses">{body}</p>'
        if k["kind"] == "dialogue":
            return f"<p>– {body}</p>"
        return f"<p>{body}</p>"

    def bubble(self, bb: dict, speaker: str | None) -> str:
        W, H = self.spec.trim_w + 2 * self.b, self.spec.trim_h + 2 * self.b
        pts = lambda ps: " ".join(f"{_f(x)},{_f(y)}" for x, y in ps)  # noqa: E731
        sw = _f(0.8 / 72 * 25.4)
        shapes = []
        if bb["tail"]:
            shapes.append(f'<polygon points="{pts(bb["tail"])}" fill="#FFFFFF" stroke="{bb["stroke"]}" stroke-width="{sw}"/>')
        for cx, cy, r in bb["dots"]:
            shapes.append(f'<circle cx="{_f(cx)}" cy="{_f(cy)}" r="{_f(r)}" fill="#FFFFFF" stroke="{bb["stroke"]}" '
                          f'stroke-width="{sw}"/>')
        shapes.append(f'<polygon points="{pts(bb["outline"])}" fill="#FFFFFF" stroke="{bb["stroke"]}" stroke-width="{sw}"/>')
        if bb["tail_fill"]:
            shapes.append(f'<polygon points="{pts(bb["tail_fill"])}" fill="#FFFFFF"/>')
        svg = (f'<svg xmlns="http://www.w3.org/2000/svg" class="bbl" viewBox="0 0 {_f(W)} {_f(H)}" aria-hidden="true" '
               f'style="left:{self.px(-self.b)};top:{self.px(-self.b)};width:{self.px(W)};height:{self.px(H)};z-index:2">'
               + "".join(shapes) + "</svg>")
        t = bb["text"]
        label = f'<span class="sr">{esc(speaker)}: </span>' if speaker else ""
        t2 = {**t, "runs": t["runs"]}
        box = self.textbox(t2, 2, "balon")
        return svg + box.replace('<p>', f'<p>{label}', 1)

    def figure(self, it: dict, gid: str | None) -> str:
        from PIL import Image
        src = self.d / "dizgi" / it["path"]
        with Image.open(src) as im:
            pw, ph = im.size
        inner = contain_rect({"x": 0, "y": 0, "w": it["box"]["w"], "h": it["box"]["h"]}, pw, ph)
        data, ext, _, _ = scaled(src, inner["w"] * K, inner["h"] * K)
        self.img_n += 1
        href = self.image(f"{gid or 'figur'}-{self.img_n:03d}", data, ext)
        tf = []
        if it.get("rotate"):
            tf.append(f"rotate({_f(it['rotate'])}deg)")
        if it.get("flip"):
            tf.append("scaleX(-1)")
        wrap = f"{self.pos(it['box'])};z-index:{it['z']}" + (f";transform:{' '.join(tf)}" if tf else "")
        return (f'<div class="fig" style="{wrap}"><img src="{href}" alt="{esc(self.alts.get(gid or "", ""))}" '
                f'style="{self.pos(inner, True)}"/></div>')

    def layer(self, pid: str, idx: int, items: list[dict]) -> str:
        """Vektör katmanı (şekil, efekt yazı) görseli + gerçek metni saydam yazı olarak."""
        W, H = self.spec.trim_w + 2 * self.b, self.spec.trim_h + 2 * self.b
        svg = self.layers.get((pid, idx))
        out = []
        z = items[0]["z"]
        if svg:
            path = f"images/katman-{pid}-{idx}.svg"
            self.pack.add(path, svg)
            out.append(f'<img class="katman" src="../{path}" alt="" style="left:{self.px(-self.b)};top:{self.px(-self.b)};'
                       f'width:{self.px(W)};height:{self.px(H)};z-index:{z}"/>')
        for it in items:
            words = runs_text(it.get("runs") or [])
            if not words.strip():
                continue
            if svg:
                t = {"box": it["box"], "align": it.get("align") or "center", "size": it.get("size") or it.get("text_size")
                     or self.data["body_size"], "ink": INK, "background": None, "pad": 0, "valign": "horizon",
                     "leading": None, "runs": [{"text": words}]}
                out.append(self.textbox(t, it["z"], ghost=True))
            elif it["type"] == "text":                 # vektör çizim yok: efekt yazı düz yazı (baskıdaki gibi)
                out.append(self.textbox(it, it["z"]))
        return "".join(out)

    # -- sayfalar
    def page(self, i: int, rd: dict, pg: dict) -> tuple[str, bool]:
        no = plan_mod.FRONT + i + 1
        parts = [f'<span epub:type="pagebreak" role="doc-pagebreak" id="s{no}" aria-label="{no}"></span>']
        if rd["art"]:
            key = pg["art"].get("asset") or pg["art"].get("id")
            parts.append(self.art(rd["art"], key))
        if rd["text"]:
            parts.append(self.textbox(rd["text"], 1, "metin"))
        svg = False
        for bb, src in zip(rd["bubbles"], pg["bubbles"]):
            parts.append(self.bubble(bb, src.get("speaker")))
            svg = True
        figs = {f["id"]: f["asset"] for f in pg["figures"]}
        run: list[dict] = []
        idx = 0

        def flush():
            nonlocal run, idx
            if run:
                parts.append(self.layer(pg["id"], idx, run))
                idx += 1
                run = []

        for it in rd["items"]:
            if self._vector(it):
                run.append(it)
                continue
            flush()
            if it["type"] == "figure":
                parts.append(self.figure(it, figs.get(it["id"])))
            elif it["type"] == "text":
                parts.append(self.textbox(it, it["z"], "serbest"))
            elif it["type"] == "shape":
                pass                                     # çizim modülü yok: baskıda da çizilmez
        flush()
        if rd["folio"]:
            parts.append(f'<div class="folio" aria-hidden="true" style="left:0;top:{self.px(self.spec.trim_h - 12)};'
                         f'width:{self.px(self.spec.trim_w)}">{no}</div>')
        return "\n".join(p for p in parts if p), svg

    def _vector(self, it: dict) -> bool:
        from .typeset import has_elements
        if not has_elements():
            return False
        return it["type"] == "shape" or (it["type"] == "text" and bool(it.get("effect")))

    def build_layers(self) -> None:
        """Bütün sayfaların vektör katmanları tek dizgide: her katman bir sayfa, SVG olarak."""
        from .typeset import Typesetter, has_elements
        if not has_elements():
            return
        order, layers = [], []
        for rd in self.data["pages"]:
            run, idx = [], 0
            for it in rd["items"] + [None]:
                if it is not None and self._vector(it):
                    run.append(it)
                    continue
                if run:
                    order.append((rd["id"], idx))
                    layers.append({"items": run})
                    idx += 1
                    run = []
        if not layers:
            return
        import typst
        ts = Typesetter(_dir(self.d) / "katman", studio.fonts(), LAYER_TEMPLATE)
        name = ts._write({"spec": self.data["spec"], "palette": self.data["palette"], "layers": layers}, "data.json")
        try:
            out = typst.compile(str(ts.dir / ts.main), root=str(ts.dir), font_paths=ts.fonts, ignore_system_fonts=True,
                                format="svg", sys_inputs={"data": name})
        except Exception as e:  # noqa: BLE001 - katmansız sürer, yazı düz basılır
            (_dir(self.d) / "hata-katman.txt").write_text(f"{type(e).__name__}: {e}")
            self.warn.append("Şekil ve efekt yazı çizilemedi; efekt yazılar düz yazı olarak kondu.")
            return
        out = out if isinstance(out, list) else [out]
        for key, svg in zip(order, out):
            self.layers[key] = svg.decode() if isinstance(svg, bytes) else svg

    def front_pages(self, ms, front: dict, rows) -> list[tuple[str, str, str, str]]:
        """İç kapak, künye, yazar tanıtımı (front.typ'deki yerleşimle): [(dosya, başlık, gövde, epub:type)]."""
        s, acc = self.spec, self.data["accent"]
        mx, top, bottom = s.safe + 6, 28, 22
        box = f"left:{self.px(mx)};top:{self.px(top)};width:{self.px(s.trim_w - 2 * mx)};height:{self.px(s.trim_h - top - bottom)}"
        out = []
        pub = ms.meta.get("PUBLISHER") or dict(rows).get("Yayınevi") or ""
        body = (f'<span epub:type="pagebreak" role="doc-pagebreak" id="s1" aria-label="1"></span>'
                f'<div class="on" style="{box};text-align:center">'
                f'<h1 class="ic-baslik" style="margin-top:{self.px(18)};font-size:{self.pt(30)};color:{acc}">{esc(ms.title)}</h1>'
                f'<p style="margin-top:{self.px(10)};font-size:{self.pt(15)}">{esc(ms.author or "")}</p></div>'
                f'<p class="on yayinevi" style="left:{self.px(mx)};width:{self.px(s.trim_w - 2 * mx)};'
                f'top:{self.px(s.trim_h - bottom - 6)};font-size:{self.pt(11)}">{esc(pub.upper())}</p>')
        out.append(("ic-kapak.xhtml", "İç kapak", body, "titlepage"))
        kun = "".join(f"<p><b>{esc(k)}</b> {esc(v)}</p>" for k, v in rows)
        body = (f'<span epub:type="pagebreak" role="doc-pagebreak" id="s2" aria-label="2"></span>'
                f'<div class="on kunye" style="{box};display:flex;flex-direction:column;justify-content:flex-end;'
                f'font-size:{self.pt(8.5)}">{kun}</div>')
        out.append(("kunye.xhtml", "Künye", body, "copyright-page"))
        bios = "".join(f'<h2 style="font-size:{self.pt(15)};color:{acc}">{esc(b.get("name"))}</h2>'
                       + "".join(f"<p>{esc(p)}</p>" for p in str(b.get("text") or "").split("\n\n") if p.strip() and p != "—")
                       for b in front.get("bios") or [] if b.get("name") and b.get("name") != "—")
        body = (f'<span epub:type="pagebreak" role="doc-pagebreak" id="s3" aria-label="3"></span>'
                f'<div class="on bio" style="{box};font-size:{self.pt(11)}">{bios}</div>')
        out.append(("yazar.xhtml", "Yazar hakkında", body, "contributors"))
        return out

    def css(self, faces: list[Face]) -> str:
        s = self.spec
        lead = s.leading
        hy = "auto" if s.hyphenate else "manual"
        return f"""{_font_css(faces, "../fonts/")}
html, body {{ margin: 0; padding: 0; }}
body {{ width: {self.vw}px; height: {self.vh}px; position: relative; overflow: hidden; background: #FFFFFF;
  font-family: {self.fonts['body']}; color: {INK}; -webkit-hyphens: {hy}; hyphens: {hy}; }}
img, svg, .tb, .fig, .folio, .on {{ position: absolute; }}
img {{ display: block; }}
.art {{ object-fit: fill; }}
.fig img {{ object-fit: fill; }}
.tb {{ box-sizing: border-box; line-height: {_f(lead)}; overflow: visible; }}
.tb p {{ margin: 0 0 0.5em 0; }}
.tb p:last-child {{ margin-bottom: 0; }}
.tb .bh {{ font-family: {self.fonts['heading']}; font-weight: 800; font-size: 1.55em; line-height: 1.2; color: {self.data['accent']};
  margin: 0 0 0.7em 0; }}
.tb .ses {{ font-family: {self.fonts['heading']}; font-weight: 800; font-size: 1.35em; color: {self.data['accent']}; }}
.balon p {{ margin: 0; }}
.ghost, .ghost * {{ color: transparent !important; }}
.folio {{ text-align: center; font-size: {self.pt(10)}; color: {FOLIO_INK}; }}
.on p {{ margin: 0 0 0.4em 0; }}
.on h1, .on h2 {{ font-family: {self.fonts['heading']}; font-weight: 800; margin: 0; line-height: 1.15; }}
.on h2 {{ font-weight: 700; margin: 0 0 {self.px(1)} 0; }}
.bio p {{ margin: 0 0 {self.px(8)} 0; line-height: 1.35; }}
.kunye p {{ margin: 0 0 0.25em 0; line-height: 1.3; }}
.yayinevi {{ text-align: center; letter-spacing: 0.14em; color: #5A5A5A; margin: 0; }}
.sr {{ position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0); white-space: nowrap; }}
"""


# ------------------------------------------------------------------ akışkan
NOTE_MARK = re.compile(r"\[(\d{1,3})\]|([¹²³⁴⁵⁶⁷⁸⁹⁰]+)")
NOTE_HEAD = re.compile(r"^\s*(?:\[(\d{1,3})\]|([¹²³⁴⁵⁶⁷⁸⁹⁰]+))\s+")
SUP = str.maketrans("¹²³⁴⁵⁶⁷⁸⁹⁰", "1234567890")


def _note_no(m) -> str:
    return m.group(1) or m.group(2).translate(SUP)


def flow_docs(plan: dict, ms) -> list[dict]:
    """Planın sayfalarından akışkan bölümler: [{title, nodes}]. Düğümler: ("pb", no) basılı sayfa başı, ("h", başlık),
    ("img", anahtar, no), ("p", tür, parçalar); parça ("runs", runs) ya da ("pb", no). Başlık bloğu yeni bölüm açar.
    Sayfa sınırından bölünen blok (kimlik «X», «X-2») tek paragraf olur, sınır paragrafın içinde işaretlenir. Yazısız
    sayfaların (tam sayfa resim) düğümleri sonraki yazılı sayfayla aynı bölüme girer (bölüm başı resmi başlığın önünde)."""
    docs: list[dict] = []
    cur: dict | None = None
    pending: list = []
    last_base = None

    def open_doc(title):
        nonlocal cur
        cur = {"title": title, "nodes": []}
        docs.append(cur)

    def has_para(doc) -> bool:
        return any(n[0] in ("p", "img") for n in doc["nodes"])

    for i, pg in enumerate(plan["pages"]):
        no = plan_mod.FRONT + i + 1
        blocks = (pg["text"] or {}).get("blocks") or []
        media = []
        if pg["art"]:
            media.append(("img", pg["art"].get("asset") or pg["art"].get("id"), no))
        media += [("img", f["asset"], no) for f in pg["figures"]]
        extra = [("p", "dialogue", [("runs", [{"text": bb["text"]}])]) for bb in pg["bubbles"] if bb.get("text")]
        for x in sorted(pg["texts"] + [s for s in pg.get("shapes", []) if s.get("runs")], key=lambda x: x.get("z", 0)):
            if runs_text(x.get("runs")).strip():
                extra.append(("p", "free", [("runs", x["runs"])]))
        if not blocks and not extra:
            pending += [("pb", no)] + media
            continue
        head = next((k for k in blocks if k["kind"] == "heading"), None)
        if cur is None or (head is not None and has_para(cur)):
            open_doc(runs_text(head["runs"]).strip() if head is not None else None)
            last_base = None
        elif head is not None and not cur["title"]:
            cur["title"] = runs_text(head["runs"]).strip() or None
        target = cur["nodes"]
        target += pending
        pending = []
        page_nodes: list = []
        carried = False
        for j, k in enumerate(blocks):
            if k["kind"] == "heading":
                page_nodes.append(("h", runs_text(k["runs"]).strip()))
                last_base = None
                continue
            m = re.match(r"^(.*)-(\d+)$", str(k["id"]))
            base = m.group(1) if m else str(k["id"])
            if j == 0 and m and base == last_base and target and target[-1][0] == "p":
                target[-1][2].extend([("pb", no), ("runs", [{"text": " "}] + k["runs"])])
                carried = True
            else:
                page_nodes.append(("p", k["kind"], [("runs", k["runs"])]))
            last_base = base
        target += ([] if carried else [("pb", no)]) + media + page_nodes + extra
    if pending:
        if cur is None:
            open_doc(None)
        cur["nodes"] += pending
    for n, doc in enumerate(docs):
        if not doc["title"]:
            ch = ms.chapters[n].title if len(docs) == len(ms.chapters) else None
            doc["title"] = ch or (ms.title if len(docs) == 1 else f"Bölüm {n + 1}")
    return docs


def _strip_note_head(parts: list) -> list:
    """Not paragrafının başındaki «[n] » / «¹ » işaretini ilk yazılı parçadan atar."""
    out, done = [], False
    for p in parts:
        if not done and p[0] == "runs":
            runs = [dict(r) for r in p[1]]
            for r in runs:
                if r.get("text", "").strip():
                    r["text"] = NOTE_HEAD.sub("", r["text"], count=1)
                    done = True
                    break
            out.append(("runs", runs))
        else:
            out.append(p)
    return out


def flow_html(doc: dict, di: int, img_href: dict, alts: dict, fonts: dict) -> tuple[str, list[int]]:
    """Bölüm gövdesi ve içindeki basılı sayfa numaraları. Dipnot: aynı bölümde «[n] …» ya da «¹ …» ile başlayan paragraf
    not olur (bölüm sonunda), metindeki aynı işaret ona bağlanır; işareti metinde olmayan paragraf not sayılmaz."""
    def flat(n) -> str:
        return "".join(runs_text(p[1]) for p in n[2] if p[0] == "runs")

    heads = {}
    for idx, n in enumerate(doc["nodes"]):
        if n[0] == "p" and (m := NOTE_HEAD.match(flat(n))):
            heads.setdefault(_note_no(m), idx)
    body_text = " ".join(flat(n) for i, n in enumerate(doc["nodes"]) if n[0] == "p" and i not in heads.values())
    marks = {_note_no(m) for m in NOTE_MARK.finditer(body_text)}
    notes = {k: i for k, i in heads.items() if k in marks}
    pages: list[int] = []
    refs: set[str] = set()

    def pb(no: int) -> str:
        pages.append(no)
        return f'<span epub:type="pagebreak" role="doc-pagebreak" id="s{no}" aria-label="{no}"></span>'

    def ref(m) -> str:
        k = _note_no(m)
        if k not in notes:
            return m.group(0)
        rid = "" if k in refs else f' id="dr-{di}-{k}"'
        refs.add(k)
        return f'<a class="dn" epub:type="noteref" role="doc-noteref" href="#dn-{di}-{k}"{rid}>{esc(k)}</a>'

    def inline(parts, link: bool) -> str:
        buf = []
        for p in parts:
            if p[0] == "pb":
                buf.append(pb(p[1]))
            else:
                h = runs_html(p[1], fonts)
                buf.append(NOTE_MARK.sub(ref, h) if link and notes else h)
        return "".join(buf)

    out, bodies = [], {}
    for idx, n in enumerate(doc["nodes"]):
        if n[0] == "pb":
            out.append(pb(n[1]))
        elif n[0] == "h":
            out.append(f"<h1>{esc(n[1])}</h1>")
        elif n[0] == "img":
            if n[1] in img_href:
                out.append(f'<figure class="resim"><img src="{img_href[n[1]]}" alt="{esc(alts.get(n[1], ""))}"/></figure>')
        elif n[0] == "p":
            k = next((k for k, i in notes.items() if i == idx), None)
            if k is not None:
                bodies[k] = inline(_strip_note_head(n[2]), False)
                continue
            cls = {"dialogue": ' class="diyalog"', "sound": ' class="ses"', "free": ' class="serbest"'}.get(n[1], "")
            out.append(f"<p{cls}>{'– ' if n[1] == 'dialogue' else ''}{inline(n[2], True)}</p>")
    if bodies:
        out.append('<section class="notlar" aria-label="Dipnotlar">')
        for k, body in bodies.items():
            back = f'<a href="#dr-{di}-{k}" role="doc-backlink">{esc(k)}</a> ' if k in refs else f"{esc(k)} "
            out.append(f'<aside epub:type="footnote" role="doc-footnote" id="dn-{di}-{k}"><p>{back}{body}</p></aside>')
        out.append("</section>")
    return "\n".join(out), pages


def flow_css(spec, faces: list[Face], accent: str) -> str:
    body, head = _stack(spec.body_font), _stack(spec.heading_font, False)
    return f"""{_font_css(faces, "../fonts/")}
body {{ font-family: {body}; line-height: {_f(spec.leading)}; margin: 0 5%; }}
h1 {{ font-family: {head}; font-weight: 800; font-size: 1.6em; line-height: 1.2; color: {accent}; margin: 2em 0 1em 0;
  page-break-after: avoid; break-after: avoid; }}
h2 {{ font-family: {head}; font-weight: 700; font-size: 1.25em; color: {accent}; margin: 1.2em 0 0.4em 0; }}
p {{ margin: 0 0 0.6em 0; text-align: {'justify' if spec.justify else 'left'}; -webkit-hyphens: {'auto' if spec.hyphenate else 'manual'};
  hyphens: {'auto' if spec.hyphenate else 'manual'}; orphans: 2; widows: 2; }}
p.ses {{ font-family: {head}; font-weight: 800; font-size: 1.3em; color: {accent}; }}
p.serbest {{ font-family: {head}; text-align: center; }}
figure.resim {{ margin: 1em 0; text-align: center; page-break-inside: avoid; break-inside: avoid; }}
figure.resim img {{ max-width: 100%; max-height: 95vh; }}
.baslik {{ text-align: center; margin-top: 20%; }}
.baslik h1 {{ margin: 0 0 0.6em 0; font-size: 2em; }}
.baslik .yazar {{ text-align: center; font-size: 1.2em; }}
.baslik .yayinevi {{ text-align: center; letter-spacing: 0.12em; margin-top: 3em; font-size: 0.85em; }}
.kunye p {{ font-size: 0.8em; margin: 0 0 0.3em 0; text-align: left; }}
.notlar {{ margin-top: 2em; border-top: 1px solid #999; font-size: 0.85em; }}
a.dn {{ vertical-align: super; font-size: 0.7em; line-height: 0; text-decoration: none; }}
.kapak {{ text-align: center; margin: 0; padding: 0; }}
.kapak img {{ max-width: 100%; max-height: 100vh; }}
"""


# ------------------------------------------------------------------ içindekiler, OPF
def nav_xhtml(toc: list[tuple[str, str]], pagelist: list[tuple[int, str]], landmarks: list[tuple[str, str, str]],
              css: str | None, head: str = "") -> str:
    li = "".join(f'<li><a href="{esc(h)}">{esc(t)}</a></li>' for t, h in toc)
    pl = "".join(f'<li><a href="{esc(h)}">{no}</a></li>' for no, h in pagelist)
    lm = "".join(f'<li><a epub:type="{t}" href="{esc(h)}">{esc(label)}</a></li>' for t, h, label in landmarks)
    body = (f'<nav epub:type="toc" id="toc" role="doc-toc"><h1>İçindekiler</h1><ol>{li}</ol></nav>\n'
            + (f'<nav epub:type="page-list" id="page-list" hidden=""><h2>Sayfalar</h2><ol>{pl}</ol></nav>\n' if pl else "")
            + (f'<nav epub:type="landmarks" id="landmarks" hidden=""><h2>Bölümler</h2><ol>{lm}</ol></nav>' if lm else ""))
    return xhtml("İçindekiler", body, css=[css] if css else [], head=head)


def ncx(uid: str, title: str, toc: list[tuple[str, str]]) -> str:
    pts = "".join(f'<navPoint id="n{i}" playOrder="{i}"><navLabel><text>{esc(t)}</text></navLabel>'
                  f'<content src="{esc(h)}"/></navPoint>' for i, (t, h) in enumerate(toc, 1))
    return ('<?xml version="1.0" encoding="UTF-8"?>\n<ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1" '
            f'xml:lang="tr"><head><meta name="dtb:uid" content="{esc(uid)}"/><meta name="dtb:depth" content="1"/>'
            '<meta name="dtb:totalPageCount" content="0"/><meta name="dtb:maxPageNumber" content="0"/></head>'
            f'<docTitle><text>{esc(title)}</text></docTitle><navMap>{pts}</navMap></ncx>\n')


def a11y(fixed: bool, has_images: bool, alts_ok: bool, has_pagelist: bool) -> dict:
    """schema.org erişilebilirlik üst verisi (EPUB Accessibility 1.1). Sabit sayfada yazı boyutu okurca değiştirilemez;
    bu özetle söylenir ve WCAG uygunluk beyanı yalnız akışkan kitapta, bütün görsellerin alt metni varken yapılır."""
    modes = ["textual"] + (["visual"] if has_images else [])
    suff = ["textual,visual"] if has_images else []
    if not has_images or alts_ok:
        suff.insert(0, "textual")
    feats = ["readingOrder", "structuralNavigation", "tableOfContents"]
    if has_images and alts_ok:
        feats.append("alternativeText")
    if has_pagelist:
        feats.append("printPageNumbers")
    if not fixed:
        feats.append("displayTransformability")
    summary = ("Bu e-kitap basılı kitabın sayfa düzenini korur (sabit sayfa); metin gerçek metindir, seçilebilir ve sesli "
               "okunabilir, okuma sırası ve içindekiler tanımlıdır" if fixed else
               "Bu e-kitabın metni okurun ekranına ve yazı boyutu ayarına göre akar; bölümler, içindekiler ve okuma sırası "
               "tanımlıdır")
    summary += ("; bütün görsellerin Türkçe alt metni vardır" if has_images and alts_ok else
                "; bazı görsellerin alt metni eksiktir" if has_images else "")
    summary += ("; basılı sayfa numaraları korunmuştur" if has_pagelist else "")
    summary += (". Sabit sayfa düzeninde yazı boyutu ve renkleri okur tarafından değiştirilemez." if fixed else ".")
    summary += " Yanıp sönen içerik, hareket ve ses yoktur."
    return {"accessMode": modes, "accessModeSufficient": suff, "accessibilityFeature": feats,
            "accessibilityHazard": ["none"], "accessibilitySummary": summary,
            "conformsTo": "EPUB Accessibility 1.1 - WCAG 2.1 Level AA" if (not fixed and (alts_ok or not has_images)) else None}


def opf(pack: Pack, *, uid: str, title: str, authors: list[str], publisher: str, rights: str, source_isbn: str | None,
        fixed: bool, access: dict, cover_id: str | None) -> str:
    m = [f'<dc:identifier id="uid">{esc(uid)}</dc:identifier>', f"<dc:title>{esc(title)}</dc:title>",
         "<dc:language>tr</dc:language>", f'<meta property="dcterms:modified">{_now()}</meta>']
    for i, a in enumerate(authors, 1):
        m.append(f'<dc:creator id="yazar{i}">{esc(a)}</dc:creator>')
        m.append(f'<meta refines="#yazar{i}" property="role" scheme="marc:relators">aut</meta>')
    if publisher:
        m.append(f"<dc:publisher>{esc(publisher)}</dc:publisher>")
    if rights:
        m.append(f"<dc:rights>{esc(rights)}</dc:rights>")
    if source_isbn:
        m.append(f"<dc:source>urn:isbn:{source_isbn}</dc:source>")
    if cover_id:
        m.append(f'<meta name="cover" content="{cover_id}"/>')
    for k in ("accessMode", "accessModeSufficient", "accessibilityFeature", "accessibilityHazard"):
        for v in access[k]:
            m.append(f'<meta property="schema:{k}">{esc(v)}</meta>')
    m.append(f'<meta property="schema:accessibilitySummary">{esc(access["accessibilitySummary"])}</meta>')
    if access.get("conformsTo"):
        m.append(f'<meta property="dcterms:conformsTo">{esc(access["conformsTo"])}</meta>')
    if fixed:
        m += ['<meta property="rendition:layout">pre-paginated</meta>', '<meta property="rendition:orientation">auto</meta>',
              '<meta property="rendition:spread">landscape</meta>']
    m.append('<meta property="ibooks:specified-fonts">true</meta>')
    items = []
    for f in pack.files:
        props = f' properties="{f["props"]}"' if f["props"] else ""
        items.append(f'<item id="{f["id"]}" href="{esc(f["path"])}" media-type="{f["mt"]}"{props}/>')
    spine = "".join(f'<itemref idref="{s["id"]}"' + (f' properties="{s["props"]}"' if s.get("props") else "")
                    + ("" if s.get("linear", True) else ' linear="no"') + "/>" for s in pack.spine)
    toc = next((f["id"] for f in pack.files if f["path"] == "toc.ncx"), None)
    return ('<?xml version="1.0" encoding="UTF-8"?>\n'
            '<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="uid" xml:lang="tr" '
            'prefix="ibooks: http://vocabulary.itunes.apple.com/rdf/ibooks/vocabulary-extensions-1.0/">\n'
            '<metadata xmlns:dc="http://purl.org/dc/elements/1.1/">\n' + "\n".join(m) + "\n</metadata>\n"
            "<manifest>\n" + "\n".join(items) + "\n</manifest>\n"
            + "<spine" + (f' toc="{toc}"' if toc else "") + f">{spine}</spine>\n</package>\n")


# ------------------------------------------------------------------ üretim
def uid_of(d: Path, eisbn: str | None) -> str:
    return f"urn:isbn:{eisbn}" if eisbn else f"urn:uuid:{uuid.uuid5(uuid.NAMESPACE_URL, 'zeki-ai-studio:' + d.name)}"


def inputs_hash(d: Path) -> str:
    """E-kitabın girdileri (plan sürümü, alt metinler, e-ISBN, künye, seçili resimler, kapak): değişince «eski» olur."""
    h = hashlib.sha1()
    pl = plan_mod.load(d) or {}
    h.update(str(pl.get("rev")).encode())
    for name in (DIR + "/" + ALT, DIR + "/" + META, "front.json", "cover.json"):
        p = d / name
        h.update(p.read_bytes() if p.exists() else b"-")
    h.update(json.dumps(studio.selected_art(d), sort_keys=True).encode())
    return h.hexdigest()[:16]


def build(d: Path, want: str = "auto", by: str = "", progress=None) -> dict:
    """E-kitabı üretir (alt metinler önceden `fill_alts` ile hazırlanır). Dönen: özet (biçim, sayfalar, uyarılar)."""
    t0 = time.time()
    plan = plan_mod.load(d)
    layout, reason = decide(d, plan, want)
    ms, spec = studio._manuscript(d), studio._spec(d)
    front = studio.read(d, "front.json") or {}
    m = meta(d)
    eisbn, pisbn = m.get("eisbn"), print_isbn(d, ms)
    uid = uid_of(d, eisbn)
    warn: list[str] = []
    if not eisbn:
        warn.append("e-ISBN girilmedi: e-kitap kalıcı bir iç kimlikle üretildi; satışa çıkmadan önce e-ISBN yazın.")
    if eisbn and pisbn and eisbn == pisbn:
        warn.append("e-ISBN basılı ISBN'le aynı; e-kitap için ayrı ISBN gerekir.")
    alts_rec = alt_store(d)
    alts = {k: v.get("text") or "" for k, v in alts_rec.items()}
    alts.setdefault("kapak", cover_alt(ms))
    rows = kunye_rows(front, eisbn, pisbn)
    faces = font_faces([spec.body_font, spec.heading_font])
    faces = [f for f in faces if f.style == "normal"] or faces        # dizgide eğik yazı yok
    for f in faces:
        if not f.embed:
            warn.append(f"{f.family} yazı tipinin lisansı gömmeye izin vermiyor; okuyucunun yazı tipi kullanılır.")
    missing_fam = [x for x in (spec.body_font, spec.heading_font) if x and not any(f.family.casefold() == x.casefold() for f in faces)]
    for x in dict.fromkeys(missing_fam):
        warn.append(f"{x} yazı tipi sunucuda bulunamadı; okuyucunun yazı tipi kullanılır.")
    pack = Pack()
    fonts_used = []
    for f in faces:
        if not f.embed:
            continue
        data = f.path.read_bytes()
        if f.obfuscate:
            data = obfuscate(data, uid)
            pack.encrypted.append(f"OEBPS/fonts/{f.name}")
        pack.add(f"fonts/{f.name}", data)
        fonts_used.append(f)
    cov = cover_image(d, spec, ms)
    cover_id = None
    if cov:
        cover_id = pack.add(f"images/kapak{cov[1]}", cov[0], id="kapak-gorsel", props="cover-image")
    else:
        warn.append("Kapak görseli yok (kapak dizilmemiş); e-kitap kapaksız üretildi.")
    fixed = layout == "fixed"
    pages_meta: list[dict] = []
    toc: list[tuple[str, str]] = []
    pagelist: list[tuple[int, str]] = []
    landmarks: list[tuple[str, str, str]] = []
    img_keys: set[str] = set()
    if fixed:
        fx = Fixed(d, plan, pack, alts, warn)
        fx.build_layers()
        pack.add("css/fxl.css", fx.css(fonts_used))
        head = fx.head()
        if cov:
            body = (f'<img class="art" src="../images/kapak{cov[1]}" alt="{esc(alts["kapak"])}" '
                    f'style="left:0;top:0;width:{fx.vw}px;height:{fx.vh}px"/>')
            cid = pack.add("text/kapak.xhtml", xhtml(ms.title, body, css=["../css/fxl.css"], head=head,
                                                     body_attr=' epub:type="cover"'))
            pack.spine.append({"id": cid, "props": "rendition:page-spread-center"})
            pages_meta.append({"href": "text/kapak.xhtml", "title": "Kapak", "side": "center", "no": None})
            toc.append(("Kapak", "text/kapak.xhtml"))
            landmarks.append(("cover", "text/kapak.xhtml", "Kapak"))
            img_keys.add("kapak")
        for n, (fn, title, body, etype) in enumerate(fx.front_pages(ms, front, rows), 1):
            iid = pack.add(f"text/{fn}", xhtml(title, body, css=["../css/fxl.css"], head=head,
                                               body_attr=f' epub:type="frontmatter {etype}"'))
            side = "right" if n % 2 else "left"
            pack.spine.append({"id": iid, "props": f"page-spread-{side}"})
            pages_meta.append({"href": f"text/{fn}", "title": title, "side": side, "no": n})
            pagelist.append((n, f"text/{fn}#s{n}"))
            toc.append((title, f"text/{fn}"))
        started = False
        for i, (rd, pg) in enumerate(zip(fx.data["pages"], plan["pages"])):
            if progress:
                progress(i, len(plan["pages"]))
            no = plan_mod.FRONT + i + 1
            body, svg = fx.page(i, rd, pg)
            fn = f"s{no:03d}.xhtml"
            heading = next((runs_text(k["runs"]).strip() for k in ((pg["text"] or {}).get("blocks") or [])
                            if k["kind"] == "heading"), None)
            iid = pack.add(f"text/{fn}", xhtml(f"Sayfa {no}" + (f" — {heading}" if heading else ""), body,
                                               css=["../css/fxl.css"], head=head,
                                               body_attr=' epub:type="bodymatter"' if not started else ""),
                           props="svg" if svg else "")
            side = "right" if no % 2 else "left"
            pack.spine.append({"id": iid, "props": f"page-spread-{side}"})
            pages_meta.append({"href": f"text/{fn}", "title": f"Sayfa {no}", "side": side, "no": no})
            pagelist.append((no, f"text/{fn}#s{no}"))
            if not started:
                landmarks.append(("bodymatter", f"text/{fn}", "Öykü"))
                if not heading:
                    toc.append((ms.title if len(ms.chapters) <= 1 else "Öykü", f"text/{fn}"))
                started = True
            if heading:
                toc.append((heading, f"text/{fn}"))
            if pg["art"]:
                img_keys.add(pg["art"].get("asset") or pg["art"].get("id"))
            img_keys.update(f["asset"] for f in pg["figures"])
        nav_css, nav_head = None, ""
    else:
        acc = ((studio.read(d, "pagemap.json") or {}).get("layout") or {}).get("accent") or \
            ((studio.read(d, "artplan.json") or {}).get("style") or {}).get("accent") or "#264653"
        pack.add("css/akis.css", flow_css(spec, fonts_used, acc))
        fonts = {"body": _stack(spec.body_font), "heading": _stack(spec.heading_font, False)}
        css = ["../css/akis.css"]
        if cov:
            cid = pack.add("text/kapak.xhtml", xhtml(ms.title, f'<div class="kapak"><img src="../images/kapak{cov[1]}" '
                                                     f'alt="{esc(alts["kapak"])}"/></div>', css=css,
                                                     body_attr=' epub:type="cover"'))
            pack.spine.append({"id": cid})
            toc.append(("Kapak", "text/kapak.xhtml"))
            landmarks.append(("cover", "text/kapak.xhtml", "Kapak"))
            pages_meta.append({"href": "text/kapak.xhtml", "title": "Kapak", "side": None, "no": None})
            img_keys.add("kapak")
        pub = ms.meta.get("PUBLISHER") or dict(rows).get("Yayınevi") or ""
        fronts = [("ic-kapak.xhtml", "İç kapak", "titlepage",
                   f'<div class="baslik"><h1>{esc(ms.title)}</h1><p class="yazar">{esc(ms.author or "")}</p>'
                   f'<p class="yayinevi">{esc(pub.upper())}</p></div>'),
                  ("kunye.xhtml", "Künye", "copyright-page",
                   '<div class="kunye">' + "".join(f"<p><b>{esc(k)}</b> {esc(v)}</p>" for k, v in rows) + "</div>")]
        bios = "".join(f'<h2>{esc(b.get("name"))}</h2>' + "".join(
            f"<p>{esc(p)}</p>" for p in str(b.get("text") or "").split("\n\n") if p.strip() and p != "—")
            for b in front.get("bios") or [] if b.get("name") and b.get("name") != "—" and b.get("text") not in (None, "—"))
        if bios:
            fronts.append(("yazar.xhtml", "Yazar hakkında", "contributors", bios))
        for fn, title, etype, body in fronts:
            iid = pack.add(f"text/{fn}", xhtml(title, body, css=css, body_attr=f' epub:type="frontmatter {etype}"'))
            pack.spine.append({"id": iid})
            toc.append((title, f"text/{fn}"))
            pages_meta.append({"href": f"text/{fn}", "title": title, "side": None, "no": None})
        docs = flow_docs(plan, ms) if plan else _docs_from_manuscript(ms)
        href: dict[str, str] = {}
        sel = studio.selected_art(d)
        for n_ in docs:
            for node in n_["nodes"]:
                if node[0] != "img" or node[1] in href:
                    continue
                src = _image_path(d, plan, sel, node[1])
                if src is None:
                    continue
                data, ext, _, _ = scaled(src, 800, 1200)
                p = f"images/{node[1]}{ext}"
                pack.add(p, data)
                href[node[1]] = "../" + p
                img_keys.add(node[1])
        for di, doc in enumerate(docs, 1):
            if progress:
                progress(di - 1, len(docs))
            body, nos = flow_html(doc, di, href, alts, fonts)
            fn = f"bolum-{di:03d}.xhtml"
            iid = pack.add(f"text/{fn}", xhtml(doc["title"], body, css=css,
                                               body_attr=' epub:type="bodymatter"' if di == 1 else ""))
            pack.spine.append({"id": iid})
            toc.append((doc["title"], f"text/{fn}"))
            pagelist += [(no, f"text/{fn}#s{no}") for no in nos]
            pages_meta.append({"href": f"text/{fn}", "title": doc["title"], "side": None, "no": nos[0] if nos else None})
            if di == 1:
                landmarks.append(("bodymatter", f"text/{fn}", "Metin"))
        nav_css, nav_head = "css/akis.css", ""
    pagelist.sort(key=lambda x: x[0])
    if not fixed:                              # içindekiler yalnız akışkanda okuma sırasında (bağlantı spine'a gitmeli)
        landmarks.append(("toc", "nav.xhtml", "İçindekiler"))
    pack.add("nav.xhtml", nav_xhtml(toc, pagelist, landmarks, nav_css, nav_head), id="nav", props="nav")
    if not fixed:                              # sabit sayfada içindekiler okuma sırasına girmez (okuyucunun menüsünde)
        pack.spine.insert(1 if cov else 0, {"id": "nav"})
        pages_meta.insert(1 if cov else 0, {"href": "nav.xhtml", "title": "İçindekiler", "side": None, "no": None})
    pack.add("toc.ncx", ncx(uid, ms.title, toc), id="ncx")
    shown = {k for k in img_keys if k}
    lacking = sorted(k for k in shown if not alts.get(k))
    if lacking:
        warn.append(f"{len(lacking)} görselin alt metni yok (e-kitap bölümündeki listeden yazın).")
    access = a11y(fixed, bool(shown), not lacking, bool(pagelist))
    front_rows = dict(front.get("kunye") or [])
    authors = [a.strip() for a in (ms.author or "").split(",") if a.strip()]
    doc_opf = opf(pack, uid=uid, title=ms.title, authors=authors,
                  publisher=ms.meta.get("PUBLISHER") or front_rows.get("Yayınevi", "").replace("—", ""),
                  rights=front_rows.get("Telif", "").replace("—", ""), source_isbn=pisbn, fixed=fixed, access=access,
                  cover_id=cover_id)
    out = _dir(d) / FILE
    pack.write(out, doc_opf)
    data = out.read_bytes()
    return {"layout": layout, "reason": reason, "uid": uid, "eisbn": eisbn, "print_isbn": pisbn,
            "build": hashlib.sha1(data).hexdigest()[:12], "size": len(data), "pages": pages_meta,
            "viewport": [int(round(spec.trim_w * K)), int(round(spec.trim_h * K))] if fixed else None,
            "fonts": [f.report() for f in faces], "images": len(shown), "alt_missing": len(lacking),
            "a11y": access, "warnings": warn, "seconds": round(time.time() - t0, 2), "by": by}


def _image_path(d: Path, plan: dict | None, sel: dict, key: str) -> Path | None:
    if key.startswith("g_") and plan and key in plan.get("assets", {}):
        p = d / plan["assets"][key]["path"]
    else:
        p = Path(sel[key]) if key in sel else None
    return p if p is not None and p.exists() else None


def _docs_from_manuscript(ms) -> list[dict]:
    """Sayfa planı yoksa el yazmasının bölümlerinden (sayfa numarasız)."""
    docs = []
    for ci, ch in enumerate(ms.chapters):
        nodes = [("p", b.kind, [("runs", [{"text": b.text}])]) for b in ch.blocks]
        docs.append({"title": ch.title or (ms.title if len(ms.chapters) == 1 else f"Bölüm {ci + 1}"), "nodes": nodes})
    return docs


async def build_job(d: Path, want: str, by: str, llm=None) -> dict:
    """Stüdyo işçisinde: alt metinler → e-kitap → denetim. Durum epub/state.json'da (ekran bekler)."""
    import asyncio
    set_state(d, status="running", step="alt", progress=[0, 0], started=time.time(), error=None, by=by, layout_want=want)
    try:
        plan = plan_mod.load(d)
        if plan is not None:
            if llm is None:
                from .run import FileLlm
                llm = FileLlm(d / "provenance.jsonl")
            await fill_alts(d, plan, llm, lambda n, t: set_state(d, step="alt", progress=[n, t]))
        set_state(d, step="dizgi", progress=[0, 0])
        res = await asyncio.to_thread(build, d, want, by, lambda n, t: set_state(d, step="dizgi", progress=[n, t]))
        set_state(d, step="denetim", progress=[0, 0])
        rep = await asyncio.to_thread(check, _dir(d) / FILE)
        st = set_state(d, status="done", step=None, progress=None, finished=time.time(), result=res, check=rep,
                       inputs=inputs_hash(d), error=None)
        from . import studio as st_mod
        try:
            st_mod.refresh_preflight(d)
        except Exception:  # noqa: BLE001 - ön kontrol bir sonraki yazımda yenilenir
            pass
        return st
    except Exception as e:
        import traceback
        (_dir(d) / "hata.txt").write_text(traceback.format_exc())           # ayrıntı dosyada; ekrana yalnız ileti
        msg = str(e) if isinstance(e, (ValueError, KeyError, FileNotFoundError)) else ""
        set_state(d, status="fail", step=None, finished=time.time(),
                  error=(msg or "E-kitap üretilemedi; ayrıntı iş klasöründe (epub/hata.txt).")[:400])
        raise


# ------------------------------------------------------------------ denetim
TR = {
    "PKG-001": "Paket sürümü beklenenden farklı.", "PKG-003": "Zip başlığı okunamadı.",
    "PKG-004": "Zip dosyası bozuk.", "PKG-005": "«mimetype» dosyasında ek alan var.",
    "PKG-006": "«mimetype» dosyası paketin ilk dosyası değil.", "PKG-007": "«mimetype» içeriği yanlış.",
    "PKG-008": "Dosya okunamadı.", "PKG-009": "Dosya adında izin verilmeyen karakter var.",
    "PKG-010": "Dosya adında boşluk var.", "PKG-012": "Dosya adında ASCII dışı karakter var.",
    "PKG-016": "Uzantı küçük harf olmalı.", "PKG-022": "Dosya uzantısı yanlış.",
    "OPF-003": "Pakette listede olmayan bir dosya var.", "OPF-004": "Paket belgesinin önek bildirimi hatalı.",
    "OPF-007": "Ayrılmış bir önek yeniden tanımlanmış.", "OPF-014": "Sayfada betik/SVG gibi bir özellik var ama listede bildirilmemiş.",
    "OPF-015": "Listede bildirilen bir özellik sayfada kullanılmıyor.", "OPF-025": "Kapak görseli tanımı hatalı.",
    "OPF-030": "Benzersiz kimlik bulunamadı.", "OPF-031": "Belirtilen dosya listede yok.",
    "OPF-033": "Okuma sırasında (spine) hiç içerik yok.", "OPF-034": "Okuma sırasında aynı içerik iki kez var.",
    "OPF-035": "Metin belgesinin türü yanlış bildirilmiş.", "OPF-043": "Okuma sırasında desteklenmeyen dosya türü var.",
    "OPF-049": "Kimlik listede bulunamadı.", "OPF-053": "Tarih biçimi geçersiz.", "OPF-054": "Tarih geçersiz.",
    "OPF-060": "Aynı dosya pakette iki kez var.", "OPF-085": "Kimlik bir UUID değil.",
    "OPF-086": "Kullanımdan kalkmış bir özellik kullanılmış.", "OPF-092": "Dil etiketi geçersiz.",
    "OPF-096": "Okuma sırasında doğrusal olmayan içeriğe erişim yok.", "OPF-097": "Listedeki bir dosyaya hiçbir yerden bağlantı yok.",
    "RSC-001": "Dosya bulunamadı.", "RSC-002": "Paket belgesi bulunamadı.", "RSC-003": "Paket belgesinin yeri bulunamadı.",
    "RSC-004": "Şifreli dosya okunamadı.", "RSC-005": "Belge biçim kuralına uymuyor.",
    "RSC-006": "Uzak kaynağa izin verilmeyen bir bağlantı var.", "RSC-007": "Başvurulan dosya pakette yok.",
    "RSC-008": "Başvurulan dosya listede bildirilmemiş.", "RSC-009": "Bağlantı bir parça tanımlayıcısı içermemeli.",
    "RSC-010": "Bağlantı metin belgesi olmayan bir dosyaya gidiyor.", "RSC-011": "Bağlantı okuma sırasında olmayan bir belgeye gidiyor.",
    "RSC-012": "Bağlantının hedefi (parça) bulunamadı.", "RSC-016": "Belge ciddi bir biçim hatası içeriyor.",
    "RSC-017": "Belge biçim uyarısı.", "RSC-020": "Bağlantı adresi geçersiz.", "RSC-032": "Yedek içerik zinciri hatalı.",
    "HTM-001": "Sayfa geçerli bir XML değil.", "HTM-004": "Sayfanın belge türü bildirimi hatalı.",
    "HTM-009": "Sayfanın belge türü bildirimi eski.", "HTM-046": "Sabit sayfa belgesinde viewport tanımı yok.",
    "HTM-047": "Sabit sayfa viewport tanımı hatalı.", "HTM-048": "Sabit sayfa SVG'sinde viewBox yok.",
    "HTM-053": "Dış kaynağa bağlantı var.", "HTM-055": "Kullanımdan kalkmış bir öğe var.",
    "HTM-060": "Viewport tanımı birden fazla.", "HTM-061": "Viewport genişlik/yükseklik değeri geçersiz.",
    "CSS-001": "Stil dosyasında desteklenmeyen özellik var.", "CSS-002": "Stil dosyasında boş ya da hatalı yazı tipi tanımı var.",
    "CSS-003": "Stil dosyasının kodlaması yanlış.", "CSS-006": "Stil «position: fixed» kullanıyor.",
    "CSS-007": "Yazı tipi dosyasının türü desteklenmiyor.", "CSS-008": "Stil dosyasında sözdizimi hatası var.",
    "CSS-019": "Stil kuralı boş.", "CSS-028": "Yazı tipi tanımı kullanılıyor.",
    "NAV-001": "İçindekiler bulunamadı.", "NAV-010": "İçindekilerde yanlış türde bağlantı var.",
    "NAV-011": "İçindekiler okuma sırasıyla uyuşmuyor.", "NCX-001": "Eski içindekiler (NCX) kimliği paket kimliğiyle uyuşmuyor.",
    "NCX-006": "Eski içindekilerde boş başlık var.", "MED-003": "Görsel dosyası bozuk ya da türü yanlış.",
    "MED-004": "Görsel dosyasının başlığı bozuk.", "ACC-001": "Görselin alt metni yok.",
    "ACC-004": "Bağlantının metni yok.", "ACC-005": "Tablo başlığı eksik.", "ACC-011": "SVG bağlantısının başlığı yok.",
    "OCF-001": "Paket yapısı hatalı.", "OCF-002": "Paket yapısı hatalı.", "INF-001": "Bilgi.",
    "CHK-008": "Denetim sırasında beklenmeyen bir durum oldu.",
}
SEV = {"FATAL": "error", "ERROR": "error", "WARNING": "warning", "USAGE": "info", "INFO": "info", "SUPPRESSED": None}
FAMILY_TR = {"PKG": "Paket", "OPF": "Paket belgesi", "RSC": "Kaynak", "HTM": "Sayfa", "CSS": "Stil", "NAV": "İçindekiler",
             "NCX": "Eski içindekiler", "MED": "Görsel", "ACC": "Erişilebilirlik", "OCF": "Paket", "SCP": "Betik",
             "CHK": "Denetim", "INF": "Bilgi"}


def _where(loc: dict | None) -> str:
    if not loc or not loc.get("path"):
        return ""
    p = str(loc["path"]).removeprefix("OEBPS/")
    line = loc.get("line")
    return p + (f", satır {line}" if line and int(line) > 0 else "")


def _tr_message(code: str, msg: str) -> str:
    if code in TR:
        return TR[code]
    fam = FAMILY_TR.get(code.split("-")[0], "E-kitap")
    return f"{fam} kuralı sağlanmadı."


def full_checker() -> list[str] | None:
    """Tam e-kitap denetiminin komutu (EDITOR_EPUBCHECK_JAR + java); kurulu değilse None."""
    jar = os.environ.get("EDITOR_EPUBCHECK_JAR", "")
    java = shutil.which("java")
    return [java, "-jar", jar] if jar and Path(jar).exists() and java else None


def run_full(path: Path, cmd: list[str]) -> list[dict]:
    with tempfile.TemporaryDirectory() as tmp:
        out = Path(tmp) / "rapor.json"
        subprocess.run(cmd + [str(path), "--json", str(out)], capture_output=True, text=True, timeout=600)
        rep = json.loads(out.read_text())
    found = []
    for m in rep.get("messages", []):
        sev = SEV.get(str(m.get("severity")).upper())
        if sev is None:
            continue
        code = str(m.get("ID") or "")
        locs = m.get("locations") or [None]
        found.append({"severity": sev, "code": code, "message": _tr_message(code, m.get("message") or ""),
                      "where": "; ".join(dict.fromkeys(w for w in (_where(x) for x in locs[:5]) if w)),
                      "count": len(locs), "original": (m.get("message") or "")[:300]})
    return found


def basic_check(path: Path) -> list[dict]:
    """Yapısal denetim (her üretimde): zip düzeni, kök belge, OPF alanları, içerik listesi ↔ zip, okuma sırası, XHTML
    biçimi, içindekiler, sabit sayfa viewport'u, alt metin, SVG özelliği."""
    from lxml import etree
    out = []

    def add(sev, code, message, where=""):
        out.append({"severity": sev, "code": code, "message": message, "where": where, "count": 1})

    try:
        z = zipfile.ZipFile(path)
    except zipfile.BadZipFile:
        add("error", "PKG-004", "Zip dosyası bozuk.")
        return out
    infos = z.infolist()
    if not infos or infos[0].filename != "mimetype":
        add("error", "PKG-006", "«mimetype» dosyası paketin ilk dosyası değil.")
    else:
        mi = infos[0]
        if mi.compress_type != zipfile.ZIP_STORED:
            add("error", "PKG-007", "«mimetype» sıkıştırılmış; sıkıştırmasız olmalı.")
        if mi.extra:
            add("error", "PKG-005", "«mimetype» dosyasında ek alan var.")
        if z.read("mimetype") != b"application/epub+zip":
            add("error", "PKG-007", "«mimetype» içeriği yanlış.")
    names = set(z.namelist())
    NS = {"c": "urn:oasis:names:tc:opendocument:xmlns:container", "o": "http://www.idpf.org/2007/opf",
          "dc": "http://purl.org/dc/elements/1.1/", "x": "http://www.w3.org/1999/xhtml",
          "e": "http://www.idpf.org/2007/ops"}
    try:
        cont = etree.fromstring(z.read("META-INF/container.xml"))
        root = cont.find(".//c:rootfile", NS).get("full-path")
        doc = etree.fromstring(z.read(root))
    except Exception:  # noqa: BLE001
        add("error", "RSC-002", "Paket belgesi bulunamadı ya da okunamadı.")
        return out
    base = root.rsplit("/", 1)[0] + "/" if "/" in root else ""
    uid_ref = doc.get("unique-identifier")
    ident = doc.find(f".//dc:identifier[@id='{uid_ref}']", NS)
    if ident is None or not (ident.text or "").strip():
        add("error", "OPF-030", "Benzersiz kimlik bulunamadı.")
    for tag, label in (("title", "başlık"), ("language", "dil")):
        if doc.find(f".//dc:{tag}", NS) is None:
            add("error", "RSC-005", f"Üst veride {label} yok.")
    if doc.find(".//o:meta[@property='dcterms:modified']", NS) is None:
        add("error", "RSC-005", "Üst veride değiştirilme tarihi yok.")
    for k in ("accessMode", "accessibilityFeature", "accessibilityHazard", "accessibilitySummary"):
        if doc.find(f".//o:meta[@property='schema:{k}']", NS) is None:
            add("warning", "ACC-002", f"Erişilebilirlik üst verisi eksik ({k}).")
    fixed = (doc.findtext(".//o:meta[@property='rendition:layout']", namespaces=NS) or "") == "pre-paginated"
    items = {i.get("id"): i for i in doc.findall(".//o:manifest/o:item", NS)}
    listed = set()
    for iid, it in items.items():
        full = base + it.get("href")
        listed.add(full)
        if full not in names:
            add("error", "RSC-001", "Listede olan dosya pakette yok.", it.get("href"))
    for n in names:
        if n in ("mimetype", root) or n.startswith("META-INF/"):
            continue
        if n not in listed:
            add("warning", "OPF-003", "Pakette listede olmayan bir dosya var.", n.removeprefix(base))
    if not any("cover-image" in (i.get("properties") or "") for i in items.values()):
        add("warning", "OPF-025", "Kapak görseli tanımlı değil.")
    navs = [i for i in items.values() if "nav" in (i.get("properties") or "").split()]
    if not navs:
        add("error", "NAV-001", "İçindekiler bulunamadı.")
    spine = doc.findall(".//o:spine/o:itemref", NS)
    if not spine:
        add("error", "OPF-033", "Okuma sırasında hiç içerik yok.")
    for ref in spine:
        if ref.get("idref") not in items:
            add("error", "OPF-049", "Okuma sırasındaki bir kimlik listede yok.", ref.get("idref"))
    in_spine = {base + items[r.get("idref")].get("href") for r in spine if r.get("idref") in items}
    for iid, it in items.items():
        if it.get("media-type") != "application/xhtml+xml":
            continue
        name = base + it.get("href")
        if name not in names:
            continue
        raw = z.read(name)
        try:
            x = etree.fromstring(raw)
        except etree.XMLSyntaxError as e:
            add("error", "HTM-001", "Sayfa geçerli bir XML değil.", f"{it.get('href')}, satır {e.lineno}")
            continue
        props = (it.get("properties") or "").split()
        if x.find(".//x:title", NS) is None or not (x.findtext(".//x:title", namespaces=NS) or "").strip():
            add("warning", "RSC-017", "Sayfanın başlığı yok.", it.get("href"))
        has_svg = x.find(".//{http://www.w3.org/2000/svg}svg") is not None
        if has_svg and "svg" not in props:
            add("error", "OPF-014", "Sayfada SVG var ama listede bildirilmemiş.", it.get("href"))
        if fixed and "nav" not in props:
            vp = x.find(".//x:meta[@name='viewport']", NS)
            if vp is None or not re.search(r"width=\d+.*height=\d+", vp.get("content") or ""):
                add("error", "HTM-046", "Sabit sayfa belgesinde viewport tanımı yok.", it.get("href"))
        for img in x.findall(".//x:img", NS):
            if img.get("alt") is None:
                add("error", "RSC-005", "Görselde alt metin özniteliği yok.", it.get("href"))
            src = img.get("src") or ""
            target = os.path.normpath(os.path.join(os.path.dirname(name), src)).replace("\\", "/")
            if target not in names:
                add("error", "RSC-007", "Başvurulan görsel pakette yok.", f"{it.get('href')} → {src}")
            elif target not in listed:
                add("error", "RSC-008", "Başvurulan görsel listede bildirilmemiş.", f"{it.get('href')} → {src}")
        if "nav" in props:
            if x.find(".//x:nav[@e:type='toc']", NS) is None:
                add("error", "NAV-001", "İçindekiler (toc) bulunamadı.", it.get("href"))
            for a in x.findall(".//x:nav//x:a", NS):
                href = (a.get("href") or "").split("#")[0]
                target = os.path.normpath(os.path.join(os.path.dirname(name), href)).replace("\\", "/")
                if href and target not in in_spine:
                    add("error", "RSC-011", "İçindekilerdeki bir bağlantı okuma sırasında olmayan bir belgeye gidiyor.",
                        f"{it.get('href')} → {href}")
    return out


def check(path: Path) -> dict:
    """Yapısal denetim + (kuruluysa) tam denetim. Dönen: {status, full, errors, warnings, infos, at}."""
    issues = basic_check(path)
    full = False
    cmd = full_checker()
    note = ""
    if cmd:
        try:
            issues = [i for i in issues if i["severity"] != "error"] + run_full(path, cmd)
            full = True
        except Exception as e:  # noqa: BLE001 - yapısal denetim sonucu kalır
            note = "Tam e-kitap denetimi tamamlanamadı; yapısal denetim sonucu gösteriliyor."
            (path.parent / "hata-denetim.txt").write_text(f"{type(e).__name__}: {e}")
    else:
        note = "Tam e-kitap denetimi bu sunucuda kurulu değil; yapısal denetim yapıldı."
    seen, uniq = set(), []
    for i in issues:
        k = (i["severity"], i["code"], i["where"])
        if k not in seen:
            seen.add(k)
            uniq.append(i)
    errs = [i for i in uniq if i["severity"] == "error"]
    warns = [i for i in uniq if i["severity"] == "warning"]
    return {"status": "FAIL" if errs else "WARN" if warns else "OK", "full": full, "note": note, "errors": errs,
            "warnings": warns, "infos": [i for i in uniq if i["severity"] == "info"], "at": _now()}


# ------------------------------------------------------------------ görünüm, ön kontrol, içerik
def view(d: Path) -> dict:
    st = read_state(d)
    plan = plan_mod.load(d)
    try:
        auto = decide(d, plan, "auto")
    except Exception:  # noqa: BLE001
        auto = ("reflow", "")
    alts = alt_list(d, plan) if plan else []
    m = meta(d)
    fresh = st.get("status") == "done" and st.get("inputs") == inputs_hash(d)
    return {"status": st.get("status", "none"), "step": st.get("step"), "progress": st.get("progress"),
            "error": st.get("error"), "started": st.get("started"), "finished": st.get("finished"), "by": st.get("by"),
            "result": st.get("result"), "check": st.get("check"), "stale": st.get("status") == "done" and not fresh,
            "auto": {"layout": auto[0], "reason": auto[1]}, "has_plan": plan is not None,
            "meta": {"eisbn": m.get("eisbn"), "print_isbn": print_isbn(d) if (d / "manuscript.json").exists() else None},
            "alt": {"total": len(alts), "missing": sum(1 for a in alts if not a["text"]),
                    "review": sum(1 for a in alts if a["review"])},
            "checker_full": full_checker() is not None}


def preflight_checks(d: Path) -> list[dict]:
    """Ön kontrole bilgi satırı: e-kitap üretildiyse denetim sonucu (basımı durdurmaz)."""
    st = read_state(d)
    if st.get("status") != "done":
        return []
    rep, res = st.get("check") or {}, st.get("result") or {}
    kind = "sabit sayfa" if res.get("layout") == "fixed" else "akışkan"
    ne, nw = len(rep.get("errors") or []), len(rep.get("warnings") or [])
    if st.get("inputs") != inputs_hash(d):
        return [{"name": "E-kitap", "status": "WARN",
                 "detail": f"e-kitap ({kind}) sonraki değişikliklerden önce üretildi; stüdyoda yeniden üretin"}]
    if ne:
        return [{"name": "E-kitap", "status": "WARN", "detail": f"e-kitap ({kind}) denetiminde {ne} hata"
                 + (f", {nw} uyarı" if nw else "") + " (stüdyoda E-kitap bölümü)"}]
    miss = res.get("alt_missing") or 0
    return [{"name": "E-kitap", "status": "WARN" if (nw or miss or not res.get("eisbn")) else "OK",
             "detail": f"e-kitap ({kind}) denetimden geçti" + (f"; {nw} uyarı" if nw else "")
             + (f"; {miss} görselin alt metni yok" if miss else "") + ("; e-ISBN yok" if not res.get("eisbn") else "")}]


def content(d: Path, build: str, path: str) -> tuple[bytes, str]:
    """Önizleme için e-kitabın içinden dosya (yalnız bu üretimin kimliğiyle; karartılmış font açılır)."""
    st = read_state(d)
    if not BUILD.match(build or "") or (st.get("result") or {}).get("build") != build:
        raise FileNotFoundError("üretim değişti")
    if ".." in path or path.startswith("/") or not re.fullmatch(r"[A-Za-z0-9_./-]{1,200}", path):
        raise FileNotFoundError(path)
    ext = Path(path).suffix.lower()
    if ext not in MIME or ext == ".opf":
        raise FileNotFoundError(path)
    with zipfile.ZipFile(_dir(d) / FILE) as z:
        name = "OEBPS/" + path
        try:
            data = z.read(name)
        except KeyError:
            raise FileNotFoundError(path) from None
        if "META-INF/encryption.xml" in z.namelist() and name in z.read("META-INF/encryption.xml").decode():
            data = obfuscate(data, st["result"]["uid"])
    return data, MIME[ext]
