"""Sayfa planının görsel varlıkları: yüklenen fotoğraf, zemin ayıklama (figür ve fotoğraf), etkin çözünürlük.

Model yok; Pillow + numpy. Kurallar kitaptan bağımsızdır.

- Yükleme (`ingest`): EXIF yönü uygulanır, gömülü renk profili varsa sRGB'ye çevrilir, EXIF/konum ve öteki üst
  veriler atılır (kişisel veri). Saydamlığı olan dosya PNG, öteki JPEG (kalite 95, renk alt örneklemesiz) kalır.
  HEIC yalnız sunucuda okuyucusu kuruluysa okunur; değilse açık hata.
- Zemin ayıklama (`cutout`): zemin rengi kenar şeridinin ortancasından ölçülür; zemin gürültüsü kenar şeridindeki
  uzaklıkların %95'liğinden. Bir piksel zemine uzaklığı eşiğin altındaysa ve kenara zeminden bir yolla bağlıysa
  saydamdır (fotoğrafta figürün içindeki benzer renk korunur). Figürde zemin düz tek renk istendiği için (anahtar
  renk) kenara bağlı olmayan kapalı boşluklar (kol ile gövde arası) da ayıklanır. Kenar geçişi yumuşak: iki eşik
  arası kısmi saydam, zemin rengi kenardan geri alınır (renk taşması), sonra 0,8 px yumuşatma.
  Ölçüm (2026-09-25): yeni bir model eklenmedi — figürde zemin istemle düz tek renk üretildiği için renk anahtarı
  yeterli; düz olmayan fotoğraf zemini için sonuç ekranda önizlenir, kullanıcı onaylar (`info.flat`).
- Etkin çözünürlük (`dpi`): kutudaki basım ölçüsüne göre piksel yoğunluğu; kaplamada (cover) büyük katsayı,
  sığdırmada (contain) küçük katsayı.
"""

from __future__ import annotations

import io
import math

LOW_DPI = 300
KEYS = (("magenta", "#FF00FF"), ("bright green", "#00FF00"), ("cyan", "#00FFFF"))


# ------------------------------------------------------------------ yükleme
def _open(data: bytes, filename: str):
    from PIL import Image, UnidentifiedImageError
    heic = filename.lower().endswith((".heic", ".heif")) or data[4:12] in (b"ftypheic", b"ftypheix", b"ftypmif1",
                                                                           b"ftypmsf1", b"ftypheif")
    if heic:
        try:
            import pillow_heif
            pillow_heif.register_heif_opener()
        except ImportError:
            raise ValueError("HEIC fotoğrafı bu sunucuda okunamıyor; telefonda JPEG («En uyumlu») olarak "
                             "paylaşıp yeniden yükleyin") from None
    try:
        im = Image.open(io.BytesIO(data))
        im.load()
    except Image.DecompressionBombError:
        raise ValueError("Fotoğrafın piksel sayısı okunabilecek sınırın üstünde; daha küçük boyutta yükleyin") from None
    except (UnidentifiedImageError, OSError, SyntaxError):
        raise ValueError("Dosya okunamadı: JPEG, PNG ya da WebP fotoğraf yükleyin") from None
    return im


def ingest(data: bytes, filename: str) -> dict:
    """Ham dosya → {"bytes", "ext", "w_px", "h_px", "alpha"}; EXIF/konum silinmiş, sRGB, doğru yönde."""
    from PIL import Image, ImageCms, ImageOps
    im = _open(data, filename)
    fmt = (im.format or "").upper()
    im = ImageOps.exif_transpose(im)
    icc = im.info.get("icc_profile")
    has_alpha = im.mode in ("RGBA", "LA", "PA") or (im.mode == "P" and "transparency" in im.info)
    if im.mode not in ("RGB", "RGBA", "CMYK"):
        im = im.convert("RGBA" if has_alpha else "RGB")
    if icc:
        try:
            src = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            im = ImageCms.profileToProfile(im, src, ImageCms.createProfile("sRGB"),
                                           outputMode="RGBA" if im.mode == "RGBA" else "RGB")
        except (ImageCms.PyCMSError, OSError, ValueError):
            im = im.convert("RGBA" if im.mode == "RGBA" else "RGB")
    elif im.mode == "CMYK":
        im = im.convert("RGB")
    if im.mode == "RGBA" and im.getchannel("A").getextrema()[0] == 255:
        im = im.convert("RGB")                  # saydamlık kanalı var ama kullanılmıyor
    alpha = im.mode == "RGBA"
    buf = io.BytesIO()
    if alpha or (fmt != "JPEG" and _lossless(im)):
        im.save(buf, "PNG", compress_level=6)   # üst veri parametresi verilmez: EXIF ve metin parçaları yazılmaz
        ext = "png"
    else:
        im.convert("RGB").save(buf, "JPEG", quality=95, subsampling=0, optimize=True)
        ext = "jpg"
    return {"bytes": buf.getvalue(), "ext": ext, "w_px": im.width, "h_px": im.height, "alpha": alpha}


def _lossless(im) -> bool:
    """Kayıpsız kaynak (çizim, ekran görüntüsü) PNG kalır; büyük fotoğraf PNG'de gereksiz büyür."""
    return im.width * im.height <= 4_000_000


# ------------------------------------------------------------------ zemin ayıklama
def key_color(palette: list[str]) -> tuple[str, str]:
    """Figür zemini: kitabın renklerinden en uzak anahtar renk (ayıklama figürün rengine dokunmasın)."""
    def rgb(h):
        return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))

    def far(k):
        return min((math.dist(rgb(k[1]), rgb(c)) for c in palette if isinstance(c, str) and len(c) == 7),
                   default=442.0)
    name, hexv = max(KEYS, key=far)
    return name, hexv


def _border(a, frac: float = 0.02):
    import numpy as np
    h, w = a.shape[:2]
    k = max(2, int(round(min(h, w) * frac)))
    return np.concatenate([a[:k].reshape(-1, a.shape[2]), a[-k:].reshape(-1, a.shape[2]),
                           a[:, :k].reshape(-1, a.shape[2]), a[:, -k:].reshape(-1, a.shape[2])])


def _connected_to_border(cand):
    """`cand` (bool) içinde kenara bağlı bölge. Önce 4× küçültülmüş ızgarada yayılır (blok tamamen adaysa),
    sonra tam çözünürlükte kenar pikselleri tamamlanır. Yayılma yakınsayana kadar sürer (tur sınırı yok)."""
    import numpy as np
    h, w = cand.shape
    s = 4
    H, W = -(-h // s) * s, -(-w // s) * s
    pad = np.zeros((H, W), bool)
    pad[:h, :w] = cand
    small = pad.reshape(H // s, s, W // s, s).all(axis=(1, 3))

    def grow(reach, allowed):
        while True:
            n = reach.copy()
            n[1:] |= reach[:-1]
            n[:-1] |= reach[1:]
            n[:, 1:] |= reach[:, :-1]
            n[:, :-1] |= reach[:, 1:]
            n &= allowed
            if (n == reach).all():
                return reach
            reach = n

    seed = np.zeros_like(small)
    seed[0], seed[-1], seed[:, 0], seed[:, -1] = small[0], small[-1], small[:, 0], small[:, -1]
    reach = grow(seed, small)
    full = np.repeat(np.repeat(reach, s, 0), s, 1)[:h, :w] & cand
    edge = np.zeros_like(cand)
    edge[0], edge[-1], edge[:, 0], edge[:, -1] = cand[0], cand[-1], cand[:, 0], cand[:, -1]
    return grow(full | edge, cand)


def cutout(data: bytes, keyed: bool = False) -> tuple[bytes, dict]:
    """Düz zeminli görsel → saydam PNG (figüre kırpılmış). `keyed`: zemin istemle tek renk üretildi (figür);
    kapalı boşluklar da ayıklanır. Dönen bilgi: zemin rengi, düzlüğü, ayıklanan pay, kırpma kutusu."""
    import numpy as np
    from PIL import Image, ImageFilter
    im = Image.open(io.BytesIO(data)).convert("RGB")
    a = np.asarray(im).astype(np.float32)
    border = _border(a)
    bg = np.median(border, axis=0)
    bd = np.linalg.norm(border - bg, axis=1)
    noise = float(np.percentile(bd, 95))
    t0 = max(noise * 1.5, 18.0)                # bunun altı kesin zemin
    t1 = t0 + 45.0                             # bunun üstü kesin figür; arası kısmi saydam
    dist = np.linalg.norm(a - bg, axis=2)
    cand = dist < t1
    region = cand if keyed else _connected_to_border(cand)
    alpha = np.where(region, np.clip((dist - t0) / (t1 - t0), 0.0, 1.0), 1.0)
    # Kenar geçişinde zeminin rengi figüre taşar: kısmi saydam pikselde zemin payı geri alınır.
    part = (alpha > 0.04) & (alpha < 1.0)
    rgb = a.copy()
    rgb[part] = np.clip((a[part] - (1.0 - alpha[part, None]) * bg) / alpha[part, None], 0, 255)
    am = Image.fromarray((alpha * 255).astype(np.uint8), "L").filter(ImageFilter.MedianFilter(3)) \
        .filter(ImageFilter.GaussianBlur(0.8))
    out = Image.fromarray(rgb.astype(np.uint8), "RGB")
    out.putalpha(am)
    bbox = am.point(lambda v: 255 if v > 5 else 0).getbbox()
    if bbox:
        m = max(4, int(round(max(out.size) * 0.01)))
        bbox = (max(0, bbox[0] - m), max(0, bbox[1] - m), min(out.width, bbox[2] + m), min(out.height, bbox[3] + m))
        out = out.crop(bbox)
    buf = io.BytesIO()
    out.save(buf, "PNG", compress_level=6)
    removed = float((np.asarray(am) < 128).mean())
    return buf.getvalue(), {"bg": "#%02X%02X%02X" % tuple(int(round(v)) for v in bg), "noise": round(noise, 1),
                            "flat": noise < 25.0, "removed": round(removed, 3), "crop": list(bbox or (0, 0, *out.size)),
                            "w_px": out.width, "h_px": out.height}


# ------------------------------------------------------------------ çözünürlük
def dpi(w_px: int, h_px: int, box: dict, fit: str = "contain") -> float:
    """Kutuda basılan görselin etkin çözünürlüğü (piksel / inç)."""
    if not (w_px and h_px and box.get("w") and box.get("h")):
        return 0.0
    mm_per_px = (max if fit == "cover" else min)(box["w"] / w_px, box["h"] / h_px)
    return 25.4 / mm_per_px


def upscale_factor(current_dpi: float, target: int = LOW_DPI) -> int:
    """Kaliteyi artırma katsayısı: hedefe yetecek en küçük tam sayı, 2 ile 4 arası (büyütücü en çok 4×)."""
    need = math.ceil(target / current_dpi) if current_dpi > 0 else 4
    return min(4, max(2, need))
