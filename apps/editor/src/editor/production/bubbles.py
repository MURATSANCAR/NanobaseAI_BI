"""Konuşma balonu: diyaloğu sayfa metninden balona taşır ve balonu resmin boş alanına yerleştirir.

Balon ve yazı resmin içine çizilmez; dizgi resmin üstüne vektör olarak basar (sayfa planı sözleşmesi). Burada
yalnız balonun metni, konuşanı, biçimi, kutusu ve kuyruğu hesaplanır; hepsi deterministiktir.

Konuşanı bulma (kitaptan bağımsız, basit Türkçe kalıplar; bulamazsa None — yanlış kuyruk boş kuyruktan kötüdür):
1. Konuşma satırının içindeki etiket: «Bak, bir yıldız! dedi Elif.», «Gel, diye seslendi Ayşe, hemen gel!»,
   «Elif heyecanla sordu.» Etiket balon metninden çıkarılır (kuyruk konuşanı gösterir).
2. Sonraki anlatı satırının başındaki etiket: «diye sordu Ayşe.», «Ayşe gülümseyerek ekledi.»; satır yalnız
   etiketse sayfa metninden de çıkar.
3. Önceki anlatı satırı iki noktayla bitiyor ve son cümlesinde yalın hâlde (eksiz) tek bir karakter adı geçiyorsa
   o karakter: «Elif pencereye koşup seslendi:». «Annesi Elif'e seslendi:» Elif'i konuşan yapmaz.
Konuşan adı etikette eksiz geçmeli: «Elif'in annesi sordu» Elif'e bağlanmaz.

Uzun konuşma (`LONG_CHARS`'tan uzun, en az iki cümle) cümle sınırından, iki yarısı en dengeli olacak yerden iki
balona bölünür; sıra korunur.
"""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np

from .colorize import find_names, fold, name_pattern

LONG_CHARS = 90                    # bundan uzun konuşma iki balona bölünür (çocuk okurun tek bakışta okuduğu)
_VERB = (r"(?:diye\s+[^\W\d_]+(?:\s+(?:etti|verdi|attı))?|dedi|diyor|sordu|soruyor|bağırdı|bağırıyor|haykırdı|"
         r"fısıldadı|fısıldıyor|seslendi|sesleniyor|söyledi|söylendi|yanıtladı|yanıt\s+verdi|cevap\s+verdi|"
         r"cevapladı|ekledi|mırıldandı|homurdandı|sızlandı|atıldı|güldü|kıkırdadı|açıkladı|anlattı|itiraz\s+etti|"
         r"uyardı|inledi|kekeledi|çığlık\s+attı|düşündü|sevindi|araya\s+girdi|onayladı|tekrarladı|diye\s+düşündü)")
_SHOUT = re.compile(r"bağır|haykır|çığlık")
_THOUGHT = re.compile(r"düşün")
_DASH = re.compile(r"^\s*[-–—]\s*")
_QUOTES = "“”\"«»"
_CLOSE = "[”\"»]?"                 # konuşmayı kapatan tırnak: «“Neredesin?” diye bağırdı Ayşe.»


def _text(b) -> str:
    if isinstance(b, dict):
        if b.get("runs") is not None:
            return "".join(r.get("text", "") for r in b["runs"])
        return b.get("text", "") or ""
    return getattr(b, "text", "") or ""


def _kind(b) -> str:
    return (b.get("kind") if isinstance(b, dict) else getattr(b, "kind", "")) or ""


def _names_alt(names: list[str]) -> str | None:
    pats = sorted({name_pattern(n) for n in names if n and n.strip()}, key=lambda p: (-len(p), p))
    return "(?:" + "|".join(pats) + ")" if pats else None


def _who(folded_match: str, names: list[str]) -> str | None:
    for n in sorted(names, key=lambda n: -len(n)):
        if re.fullmatch(name_pattern(n), folded_match.strip()):
            return n
    return None


def _tag_res(alt: str) -> list[re.Pattern]:
    # etiket: «dedi Elif» | «diye sordu Elif» | «Elif (en çok iki kelime) sordu»; ad eksiz (ardından boşluk/nokta)
    tag = rf"(?:(?P<v>{_VERB})\s+(?P<n1>{alt})|(?P<n2>{alt})(?:\s+[^\W\d_]+){{0,2}}?\s+(?P<v2>{_VERB}))(?![\w'])"
    return [
        re.compile(rf"^(?P<a>.*?[,.!?…]){_CLOSE}\s*[-–—]?\s*{tag}\s*[.!?…]*\s*$"),              # sonda
        re.compile(rf"^(?P<a>.*?[,!?…]){_CLOSE}\s*[-–—]?\s*{tag}\s*(?P<p>[,.;])\s*[-–—]?\s*(?P<b>\S.*)$"),  # arada
    ]


def _nameless_tag(folded: str) -> re.Match | None:
    return re.search(rf"(?P<a>[,.!?…]){_CLOSE}\s*[-–—]?\s*{_VERB}\s*[.!?…]*\s*$", folded)


def _clean(s: str) -> str:
    s = _DASH.sub("", s).strip()
    while s and s[0] in _QUOTES:
        s = s[1:].strip()
    while s and s[-1] in _QUOTES:
        s = s[:-1].strip()
    return s


def parse(text: str, names: list[str]) -> tuple[str, str | None, str | None]:
    """Konuşma satırı → (konuşma, etiketteki konuşan|None, etiket fiili|None)."""
    raw = _clean(text)
    folded = fold(raw)
    alt = _names_alt(names)
    if alt:
        for i, rx in enumerate(_tag_res(alt)):
            m = rx.match(folded)
            if not m:
                continue
            who = _who(m.group("n1") or m.group("n2"), names)
            verb = m.group("v") or m.group("v2")
            a = raw[:m.end("a")].strip()
            if i == 0:
                speech = a[:-1] + "." if a.endswith(",") else a
            else:
                b = raw[m.start("b"):].strip()
                if m.group("p") == "," and a.endswith(","):
                    speech = f"{a} {b}"
                else:
                    speech = f"{a[:-1] + '.' if a.endswith(',') else a} {b[:1].upper() + b[1:]}"
            return speech.strip(), who, verb
    m = _nameless_tag(folded)
    if m and m.start() > 0:
        a = raw[:m.start("a") + 1].strip()
        return (a[:-1] + "." if a.endswith(",") else a), None, None
    return raw, None, None


def _lead_tag(text: str, names: list[str]) -> tuple[str | None, bool]:
    """Anlatı satırının başındaki etiket → (konuşan, satır yalnız etiket mi)."""
    alt = _names_alt(names)
    if not alt:
        return None, False
    folded = fold(text.strip())
    m = re.match(rf"^(?:{_VERB}\s+(?P<n1>{alt})|(?P<n2>{alt})(?:\s+[^\W\d_]+){{0,2}}?\s+{_VERB})(?![\w'])", folded)
    if not m:
        return None, False
    return _who(m.group("n1") or m.group("n2"), names), not folded[m.end():].strip(" .!?…")


def _colon_speaker(text: str, names: list[str]) -> str | None:
    t = text.strip()
    if not t.endswith(":"):
        return None
    last = re.split(r"(?<=[.!?…])\s+", t)[-1]
    bare = {n for s, e, n in find_names(last, names) if not any(c in "'’" for c in last[s:e])}
    return bare.pop() if len(bare) == 1 else None


def speakers(blocks: list, names: list[str]) -> list[str | None]:
    """Her blok için konuşan (konuşma bloğu değilse None). Kurallar modül belgesinde."""
    out: list[str | None] = []
    for i, b in enumerate(blocks):
        if _kind(b) != "dialogue":
            out.append(None)
            continue
        _, who, _ = parse(_text(b), names)
        if who is None and i + 1 < len(blocks) and _kind(blocks[i + 1]) != "dialogue":
            who, _ = _lead_tag(_text(blocks[i + 1]), names)
        if who is None and i > 0 and _kind(blocks[i - 1]) != "dialogue":
            who = _colon_speaker(_text(blocks[i - 1]), names)
        out.append(who)
    return out


def _shape(speech: str, verb: str | None) -> str:
    if verb and _THOUGHT.search(verb):
        return "thought"
    letters = [c for c in speech if c.isalpha()]
    if (verb and _SHOUT.search(verb)) or "!!" in speech or (len(letters) >= 4 and all(c.isupper() for c in letters)):
        return "shout"
    return "oval"


def split_long(speech: str) -> list[str]:
    if len(speech) <= LONG_CHARS:
        return [speech]
    parts = [s for s in re.split(r"(?<=[.!?…])\s+", speech) if s.strip()]
    if len(parts) < 2:
        return [speech]
    best = min(range(1, len(parts)), key=lambda k: (abs(len(" ".join(parts[:k])) - len(" ".join(parts[k:]))), k))
    return [" ".join(parts[:best]), " ".join(parts[best:])]


def _bid(key: str, part: int, text: str) -> str:
    return "b_" + hashlib.sha1(f"{key}|{part}|{text}".encode()).hexdigest()[:8]


def from_dialogue(blocks: list, speakers_: list[str]) -> tuple[list, list[dict]]:
    """Konuşma bloklarını balona taşır: (kalan bloklar, balonlar). Balonun `box`/`tail`'ı `place` doldurur.
    Yalnız etiketten ibaret anlatı satırı («diye sordu Ayşe.») konuşanı verdiyse kalan bloklardan da çıkar."""
    names = list(speakers_ or [])
    who = speakers(blocks, names)
    drop: set[int] = set()
    bubbles: list[dict] = []
    for i, b in enumerate(blocks):
        if _kind(b) != "dialogue":
            continue
        speech, tag_who, verb = parse(_text(b), names)
        spk = who[i]
        if tag_who is None and spk and i + 1 < len(blocks) and _kind(blocks[i + 1]) != "dialogue":
            lead, only = _lead_tag(_text(blocks[i + 1]), names)
            if lead == spk and only:
                drop.add(i + 1)
                m = re.search(_VERB, fold(_text(blocks[i + 1])))
                verb = verb or (m.group(0) if m else None)
        drop.add(i)
        if not speech:
            continue
        key = (b.get("id") if isinstance(b, dict) else None) or f"#{i}"
        for part, piece in enumerate(split_long(speech)):
            bubbles.append({"id": _bid(str(key), part, piece), "speaker": spk, "text": piece,
                            "shape": _shape(piece, verb), "box": None, "tail": None, "color": None,
                            "source": "auto"})
    return [b for i, b in enumerate(blocks) if i not in drop], bubbles


def wanted(profile) -> bool:
    """Balon kuralı hangi kitapta: çocuk profili (okur yaşı en çok 12) ve her sayfada resim. `profile` Profile,
    sözlük ya da iş klasöründeki profile.json yolu olabilir."""
    if isinstance(profile, (str, Path)):
        try:
            profile = json.loads(Path(profile).read_text())
        except (OSError, ValueError):
            return False
    get = profile.get if isinstance(profile, dict) else (lambda k: getattr(profile, k, None))
    age = get("age_max")
    return age is not None and int(age) <= 12 and get("illustration") == "HER_SAYFA"


# ------------------------------------------------------------------ yerleşim
PT_MM = 25.4 / 72
CHAR_EM = 0.55             # ortalama harf genişliği (em): çocuk kitabı fontlarında
LINE_EM = 1.25
OVAL = 1.3                 # yazının oval içine sığması için kutu payı (dikdörtgen yazı, elips kutu)
ASPECT = 2.0               # tercih edilen balon en/boy oranı
GAP = 2.0                  # balonlar ve yazı kutusu arasında en az boşluk (mm)
FACE_PAD = 0.15            # yüz kutusu bu oranda büyütülüp korunur
W_DIST, W_TOP, W_ORDER = 0.35, 0.2, 0.3   # puan ağırlıkları: konuşana yakınlık, üstte olma, okuma sırası
W_LEFT = 0.1               # sıkı dizilim stratejisinde soldan başlama


def _rect(b) -> tuple[float, float, float, float] | None:
    if not b:
        return None
    return float(b["x"]), float(b["y"]), float(b["x"]) + float(b["w"]), float(b["y"]) + float(b["h"])


def bubble_size(text: str, size_pt: float, max_w: float) -> tuple[float, float]:
    """Metnin uzunluğundan ve puntodan balon ölçüsü (mm): en/boy oranı `ASPECT`'e en yakın satır sayısı,
    genişlik alanı aşmıyorsa."""
    em = size_pt * PT_MM
    n = max(1, len(text))
    pad = 0.6 * em
    best = None
    for lines in range(1, n + 1):
        w = n * CHAR_EM * em * 1.1 / lines * OVAL + 2 * pad
        h = lines * LINE_EM * em * OVAL + 2 * pad
        key = (w > max_w, abs(w / h - ASPECT))
        if best is None or key < best[0]:
            best = (key, w, h)
        if w / h < ASPECT and w <= max_w:
            break
    return round(best[1] * 2) / 2, round(best[2] * 2) / 2


def _energy(image_path) -> np.ndarray | None:
    """Resmin ayrıntı haritası (0–1): parlaklık ve renk geçişlerinin büyüklüğü, yumuşatılmış. Gökyüzü/duvar ~0."""
    from PIL import Image
    try:
        with Image.open(image_path) as im:
            im = im.convert("RGB")
            im.thumbnail((384, 384))
            a = np.asarray(im, dtype=float) / 255.0
    except (OSError, ValueError, TypeError):
        return None
    gray = a @ np.array([0.299, 0.587, 0.114])
    g = np.zeros_like(gray)
    for ch in (gray, a[..., 0] - a[..., 1], a[..., 2] - (a[..., 0] + a[..., 1]) / 2):
        gy, gx = np.gradient(ch)
        g += np.hypot(gx, gy)
    r = max(1, round(max(g.shape) * 0.02))
    g = _box_blur(g, r)
    top = np.percentile(g, 95)
    return np.clip(g / top, 0, 1) if top > 0 else np.zeros_like(g)


def _box_blur(a: np.ndarray, r: int) -> np.ndarray:
    p = np.pad(a, r + 1, mode="edge")
    s = p.cumsum(0).cumsum(1)
    k = 2 * r + 1
    return (s[k:, k:] - s[:-k, k:] - s[k:, :-k] + s[:-k, :-k])[: a.shape[0], : a.shape[1]] / (k * k)


def _mapping(art: dict, iw: int, ih: int):
    """Sayfa mm → resim pikseli (kutuya cover/contain yerleşim, odakla)."""
    box = art.get("box", art)
    bx, by, bw, bh = (float(box[k]) for k in ("x", "y", "w", "h"))
    fit = art.get("fit", "cover")
    focus = art.get("focus") or {"x": 0.5, "y": 0.5}
    s = max(bw / iw, bh / ih) if fit == "cover" else min(bw / iw, bh / ih)
    fx, fy = (float(focus["x"]), float(focus["y"])) if fit == "cover" else (0.5, 0.5)
    ox, oy = bx + (bw - iw * s) * fx, by + (bh - ih * s) * fy
    return s, ox, oy


def _head_box(bb, iw: int, ih: int, s: float, ox: float, oy: float):
    """`locate` sonucu (resme göre 0–1 oran; 1'den büyük değer piksel sayılır) → sayfa mm kutusu."""
    if not bb:
        return None
    x, y, w, h = (float(bb[k]) for k in ("x", "y", "w", "h"))
    if max(x, y, w, h) <= 1.5:
        x, y, w, h = x * iw, y * ih, w * iw, h * ih
    return ox + x * s, oy + y * s, ox + (x + w) * s, oy + (y + h) * s


def _grow(r, pad_ratio: float, pad_mm: float = 0.0):
    x0, y0, x1, y1 = r
    dx, dy = (x1 - x0) * pad_ratio + pad_mm, (y1 - y0) * pad_ratio + pad_mm
    return x0 - dx, y0 - dy, x1 + dx, y1 + dy


def _tail(box, head):
    """Kuyruğun ucu: konuşanın başını çevreleyen (payla büyütülmüş) kutunun balona en yakın noktası."""
    if head is None:
        return None
    x0, y0, x1, y1 = _grow(head, 0.0, 1.5)
    cx, cy = box[0] + box[2] / 2, box[1] + box[3] / 2
    px, py = min(max(cx, x0), x1), min(max(cy, y0), y1)
    return {"x": round(px, 1), "y": round(py, 1)}


def place(bubbles: list[dict], art_box, text_box, image_path, locate, *, page: dict | None = None,
          size: float = 14.0) -> list[dict]:
    """Balonları resmin boş alanına yerleştirir (yeni liste). `art_box` kutu ya da {"box","fit","focus"};
    `text_box` yazı kutusu ya da None; `locate(image_path, ad) -> {"x","y","w","h"}|None` konuşanın başı (resme göre
    0–1 oran). `page` ({"w","h","bleed","safe"}) verilirse balon güvenli alanın içinde kalır; `size` balon puntosu.

    Sert şartlar: güvenli alan ve resim kutusunun içi, yazı kutusunun ve öteki balonların `GAP` mm dışı, sayfada
    yeri bulunan konuşanların yüzünün dışı. Puan (küçük iyi): kutunun ortalama ayrıntısı + konuşanın başına uzaklık +
    üstte olma + okuma sırası (sonraki balon öncekinin altında ya da aynı satırda sağında). Balonlar sırayla konur;
    iki strateji (konuşana yakın / soldan sıkı dizilim) denenir, toplam maliyeti küçük olan seçilir. Yer yoksa önce yüz şartı gevşer,
    o da yetmezse balonlar çakışır; ikisi de balonun `warning` alanına yazılır. `source:"editor"` balon yerinde
    kalır, ötekilerine engel olur."""
    art = dict(art_box) if art_box else None
    ar = _rect(art.get("box", art)) if art else None
    region = ar
    if page:
        m = float(page.get("bleed", 0)) + float(page.get("safe", 0))
        safe = (m, m, float(page["w"]) - m, float(page["h"]) - m)
        region = (max(ar[0], safe[0]), max(ar[1], safe[1]), min(ar[2], safe[2]), min(ar[3], safe[3])) if ar else safe
    out = [dict(b) for b in bubbles]
    if region is None or region[2] - region[0] < 1 or region[3] - region[1] < 1:
        for b in out:
            if b.get("source") != "editor":
                b["warning"] = "Balona yer yok: sayfada resim alanı yok."
        return out
    energy = _energy(image_path) if image_path else None
    ih, iw = (energy.shape if energy is not None else (1, 1))
    s, ox, oy = _mapping(art, iw, ih) if art else (1.0, 0.0, 0.0)

    # 1 mm ızgara
    x0, y0 = region[0], region[1]
    nx, ny = int(region[2] - x0), int(region[3] - y0)
    gx, gy = x0 + 0.5 + np.arange(nx), y0 + 0.5 + np.arange(ny)
    if energy is not None:
        px = np.clip(((gx - ox) / s).astype(int), 0, iw - 1)
        py = np.clip(((gy - oy) / s).astype(int), 0, ih - 1)
        grid = energy[py[:, None], px[None, :]]
    else:
        grid = np.zeros((ny, nx))
    integ = np.zeros((ny + 1, nx + 1))
    integ[1:, 1:] = grid.cumsum(0).cumsum(1)

    heads: dict[str, tuple | None] = {}
    for b in out:
        n = b.get("speaker")
        if n and n not in heads:
            try:
                heads[n] = _head_box(locate(image_path, n), iw, ih, s, ox, oy) if (locate and image_path) else None
            except Exception:                         # görsel okuma düşse de balon yerleşir (kuyruksuz)
                heads[n] = None
    faces = [_grow(h, FACE_PAD) for h in heads.values() if h]
    tb = _grow(_rect(text_box), 0.0, GAP) if text_box else None
    diag = float(np.hypot(nx, ny)) or 1.0

    def greedy(w_dist: float, w_left: float) -> tuple[float, list[dict]]:
        """Balonları sırayla en iyi yere koyar. Dönen: (maliyet, balonlar); maliyet = kutuların ortalama
        ayrıntısı + konuşana uzaklık + uyarı başına 10 (uyarılı sonuç her zaman kaybeder)."""
        res = [dict(b) for b in out]
        placed = [_grow(_rect(b["box"]), 0.0, GAP) for b in res if b.get("source") == "editor" and b.get("box")]
        prev, cost = None, 0.0
        for b in res:
            if b.get("source") == "editor":
                if b.get("box"):
                    prev = _rect(b["box"])
                continue
            w, h = bubble_size(b.get("text", ""), size, 0.8 * nx)
            w, h = min(w, nx), min(h, ny)
            wi, hi = int(np.ceil(w)), int(np.ceil(h))
            X, Y = np.meshgrid(x0 + np.arange(nx - wi + 1), y0 + np.arange(ny - hi + 1))   # aday sol üst köşeler
            iy, ix = (Y - y0).astype(int), (X - x0).astype(int)
            mean = (integ[iy + hi, ix + wi] - integ[iy, ix + wi] - integ[iy + hi, ix] + integ[iy, ix]) / (wi * hi)
            CX, CY = X + w / 2, Y + h / 2
            head = heads.get(b.get("speaker")) if b.get("speaker") else None
            dist = np.zeros_like(mean)
            if head:
                dist = np.hypot(CX - (head[0] + head[2]) / 2, CY - (head[1] + head[3]) / 2) / diag
            score = mean + W_TOP * (Y - y0) / max(1, ny) + w_dist * dist + w_left * (X - x0) / max(1, nx)
            if prev:
                pcx, pcy = (prev[0] + prev[2]) / 2, (prev[1] + prev[3]) / 2
                half = (prev[3] - prev[1]) / 2      # okuma sırası: sonraki balon ya alt satırda ya aynı satırda sağda
                score = score + W_ORDER * ((CY < pcy - half) | ((np.abs(CY - pcy) <= half) & (CX < pcx)))

            def free(rects):
                ok = np.ones_like(score, dtype=bool)
                for r in rects:
                    ok &= ~((X < r[2]) & (X + w > r[0]) & (Y < r[3]) & (Y + h > r[1]))
                return ok
            base = free([tb] if tb else [])
            for ok, warn in ((base & free(placed) & free(faces), None),
                             (base & free(placed), "Balon bir karakterin yüzüne biniyor; elle kaydırın."),
                             (base, "Balona boş yer bulunamadı, başka bir balonla çakışıyor; elle yerleştirin."),
                             (np.ones_like(base), "Balona boş yer bulunamadı, yazı kutusuyla çakışıyor; elle yerleştirin.")):
                if ok.any():
                    k = int(np.argmin(np.where(ok, score, np.inf)))     # eşitlikte ızgara sırası: üst, sonra sol
                    break
            bx, by = float(X.flat[k]), float(Y.flat[k])
            b["box"] = {"x": round(bx, 1), "y": round(by, 1), "w": w, "h": h}
            b["tail"] = _tail((bx, by, w, h), head)
            if warn:
                b["warning"] = warn
            else:
                b.pop("warning", None)
            cost += float(mean.flat[k]) + W_DIST * float(dist.flat[k]) + (10.0 if warn else 0.0)
            prev = (bx, by, bx + w, by + h)
            placed.append(_grow(prev, 0.0, GAP))
        return cost, res

    # İki strateji: konuşana yakın (varsayılan) ve okuma sırasıyla soldan sıkı dizilim (dar boş alanda balonlar
    # birbirinin yerini parçalamasın). Maliyeti küçük olan kazanır; eşitlikte ilki.
    tries = [greedy(W_DIST, 0.0), greedy(W_DIST / 4, W_LEFT)]
    return min(tries, key=lambda t: t[0])[1]
