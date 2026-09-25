"""Boyama/etkinlik kitabının raster yardımcıları: bağlı bileşen etiketleme, genişletme/aşındırma, küçük parça
temizliği, yaklaşık uzaklık haritası, dış kontur izleme. Yalnız numpy + PIL (stüdyo imajında başka görüntü
kütüphanesi yok); ölçüler piksel, çağıran mm'den çevirir.

Etiketleme satır koşuları (run-length) üzerinden birleşim-bul ile yapılır: Python döngüsü piksel başına değil koşu
başına döner, 1500 px'lik bir sayfada birkaç on bin koşu → saniyenin altında.
"""

from __future__ import annotations

import numpy as np
from PIL import Image, ImageFilter


def label(mask: np.ndarray, conn8: bool = True) -> tuple[np.ndarray, int]:
    """Bağlı bileşenler. Dönen: (etiket haritası int32, 0 = arka plan; bileşen sayısı)."""
    m = np.ascontiguousarray(mask, dtype=bool)
    h, w = m.shape
    pad = np.zeros((h, w + 2), np.int8)
    pad[:, 1:-1] = m
    d = np.diff(pad, axis=1)
    rs, cs = np.nonzero(d == 1)                      # koşu başı (satır, sütun)
    _, ce = np.nonzero(d == -1)                      # koşu sonu (hariç)
    n = len(rs)
    if n == 0:
        return np.zeros((h, w), np.int32), 0
    parent = np.arange(n)

    def find(i: int) -> int:
        root = i
        while parent[root] != root:
            root = parent[root]
        while parent[i] != root:
            parent[i], i = root, parent[i]
        return root

    starts = np.searchsorted(rs, np.arange(h + 1))
    slack = 1 if conn8 else 0
    cs_l, ce_l = cs.tolist(), ce.tolist()
    for r in range(1, h):
        a, a1, b, b1 = int(starts[r - 1]), int(starts[r]), int(starts[r]), int(starts[r + 1])
        while a < a1 and b < b1:
            if cs_l[a] < ce_l[b] + slack and cs_l[b] < ce_l[a] + slack:
                ra, rb = find(a), find(b)
                if ra != rb:
                    parent[max(ra, rb)] = min(ra, rb)
            if ce_l[a] < ce_l[b]:
                a += 1
            else:
                b += 1
    roots = np.array([find(i) for i in range(n)])
    uniq, lab_of_run = np.unique(roots, return_inverse=True)
    out = np.zeros((h, w), np.int32)
    lens = ce - cs
    rows = np.repeat(rs, lens)
    cols = np.concatenate([np.arange(s, e) for s, e in zip(cs_l, ce_l)]) if n else np.zeros(0, int)
    out[rows, cols] = np.repeat(lab_of_run + 1, lens)
    return out, len(uniq)


def areas(lab: np.ndarray, n: int) -> np.ndarray:
    """Bileşen alanları; dizin 0 arka plan."""
    return np.bincount(lab.ravel(), minlength=n + 1)


def _filter(mask: np.ndarray, flt) -> np.ndarray:
    im = Image.fromarray((mask.astype(np.uint8) * 255), "L").filter(flt)
    return np.asarray(im) > 127


def dilate(mask: np.ndarray, r: int) -> np.ndarray:
    """Kare yapı elemanıyla genişletme (yarıçap r px). Büyük yarıçap küçük adımlara bölünür (PIL süzgeci kare)."""
    out = mask
    while r > 0:
        k = min(r, 3)
        out = _filter(out, ImageFilter.MaxFilter(2 * k + 1))
        r -= k
    return out


def erode(mask: np.ndarray, r: int) -> np.ndarray:
    out = mask
    while r > 0:
        k = min(r, 3)
        out = _filter(out, ImageFilter.MinFilter(2 * k + 1))
        r -= k
    return out


def _cross(mask: np.ndarray) -> np.ndarray:
    out = mask.copy()
    out[1:] |= mask[:-1]
    out[:-1] |= mask[1:]
    out[:, 1:] |= mask[:, :-1]
    out[:, :-1] |= mask[:, 1:]
    return out


def round_dilate(mask: np.ndarray, r: int) -> np.ndarray:
    """Yuvarlağa yakın (sekizgen) genişletme: kare ve artı adımları sırayla. Çizgi uçları ve köşeler yuvarlanır."""
    out = mask
    for i in range(max(0, int(r))):
        out = _filter(out, ImageFilter.MaxFilter(3)) if i % 2 == 0 else _cross(out)
    return out


def remove_small(mask: np.ndarray, min_px: int, conn8: bool = True) -> tuple[np.ndarray, int]:
    """`min_px`'ten küçük bileşenleri siler. Dönen: (maske, silinen bileşen sayısı)."""
    lab, n = label(mask, conn8)
    if n == 0:
        return mask, 0
    a = areas(lab, n)
    small = a < min_px
    small[0] = False
    return mask & ~small[lab], int(small.sum())


def fill_small_holes(ink: np.ndarray, max_px: int) -> tuple[np.ndarray, int]:
    """Mürekkebin çevirdiği, `max_px`'ten küçük beyaz adacıkları doldurur (boyanamayacak kadar küçük delik).
    Kenara değen beyaz bölge doldurulmaz."""
    lab, n = label(~ink, conn8=False)
    if n == 0:
        return ink, 0
    a = areas(lab, n)
    edge = np.unique(np.concatenate([lab[0], lab[-1], lab[:, 0], lab[:, -1]]))
    small = a <= max_px
    small[0] = False
    small[edge] = False
    return ink | small[lab], int(small.sum())


def distance(mask: np.ndarray, limit: int | None = None) -> np.ndarray:
    """Yaklaşık iç uzaklık (satranç tahtası): her pikselin maskenin kenarına uzaklığı (px). Art arda aşındırma
    ile; maske bitene kadar (ya da `limit`'e kadar) sürer."""
    h, w = mask.shape
    out = np.zeros((h + 2, w + 2), np.int32)
    cur = np.zeros((h + 2, w + 2), bool)          # dış kenar boş: görüntü kenarı da sınırdır (aşındırma biter)
    cur[1:-1, 1:-1] = mask
    k = 0
    while cur.any() and (limit is None or k < limit):
        k += 1
        out[cur] = k
        cur = _filter(cur, ImageFilter.MinFilter(3))
        cur[0, :] = cur[-1, :] = cur[:, 0] = cur[:, -1] = False
    return out[1:-1, 1:-1]


def smooth_upscale(mask: np.ndarray, size: tuple[int, int], soften: float = 1.0) -> Image.Image:
    """İkili maskeyi hedef ölçüye yumuşak kenarla büyütür, sonra yeniden ikiler: merdiven basamağı kalmaz.
    Dönen «L» görsel, yalnız 0 (mürekkep) ve 255 (kâğıt)."""
    im = Image.fromarray((~mask).astype(np.uint8) * 255, "L")
    big = im.resize(size, Image.Resampling.BICUBIC)
    if soften > 0:
        big = big.filter(ImageFilter.GaussianBlur(soften))
    return big.point(lambda v: 255 if v >= 128 else 0)


def trace_outer(mask: np.ndarray) -> list[tuple[int, int]]:
    """En büyük bileşenin dış konturu (Moore komşuluğu, saat yönünde), (x, y) listesi."""
    lab, n = label(mask)
    if n == 0:
        return []
    a = areas(lab, n)
    a[0] = 0
    m = lab == int(np.argmax(a))
    ys, xs = np.nonzero(m)
    i = int(np.lexsort((xs, ys))[0])
    start = (int(xs[i]), int(ys[i]))
    h, w = m.shape

    def on(x, y):
        return 0 <= x < w and 0 <= y < h and m[y, x]

    nb = [(-1, 0), (-1, -1), (0, -1), (1, -1), (1, 0), (1, 1), (0, 1), (-1, 1)]
    out = [start]
    cur, back = start, 0                      # geliş yönü: soldan (batı)
    for _ in range(4 * m.sum() + 8):
        for k in range(8):
            d = (back + 1 + k) % 8
            nx, ny = cur[0] + nb[d][0], cur[1] + nb[d][1]
            if on(nx, ny):
                back = (d + 4) % 8
                cur = (nx, ny)
                break
        else:
            break                             # tek piksel
        if cur == start:
            break
        out.append(cur)
    return out


def rdp(points: list[tuple[float, float]], eps: float) -> list[tuple[float, float]]:
    """Ramer–Douglas–Peucker sadeleştirme (açık çizgi)."""
    if len(points) < 3:
        return list(points)
    p = np.asarray(points, dtype=float)
    stack, keep = [(0, len(p) - 1)], np.zeros(len(p), bool)
    keep[0] = keep[-1] = True
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        a, b = p[i], p[j]
        ab = b - a
        L = np.hypot(*ab)
        seg = p[i + 1:j] - a
        dist = np.abs(ab[0] * seg[:, 1] - ab[1] * seg[:, 0]) / L if L > 0 else np.hypot(seg[:, 0], seg[:, 1])
        k = int(np.argmax(dist))
        if dist[k] > eps:
            m = i + 1 + k
            keep[m] = True
            stack += [(i, m), (m, j)]
    return [tuple(x) for x in p[keep]]


def adjacency(lab: np.ndarray, weight: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Bölge komşulukları: (çiftler (m, 2) a<b, ortak sınır uzunluğu, sınırdaki `weight` toplamı)."""
    pairs, ws = [], []
    for a, b, wa, wb in ((lab[:, :-1], lab[:, 1:], weight[:, :-1], weight[:, 1:]),
                         (lab[:-1], lab[1:], weight[:-1], weight[1:])):
        m = a != b
        lo, hi = np.minimum(a[m], b[m]), np.maximum(a[m], b[m])
        pairs.append(np.stack([lo, hi], 1))
        ws.append(np.maximum(wa[m], wb[m]))
    p = np.concatenate(pairs) if pairs else np.zeros((0, 2), np.int64)
    w = np.concatenate(ws) if ws else np.zeros(0)
    if not len(p):
        return np.zeros((0, 2), np.int64), np.zeros(0), np.zeros(0)
    key = p[:, 0].astype(np.int64) * (int(lab.max()) + 1) + p[:, 1]
    uk, inv = np.unique(key, return_inverse=True)
    cnt = np.bincount(inv)
    tot = np.bincount(inv, weights=w)
    first = np.zeros(len(uk), np.int64)
    first[inv[::-1]] = np.arange(len(inv))[::-1]
    return p[first], cnt.astype(float), tot


def merge_regions(lab: np.ndarray, n: int, weight: np.ndarray, color: np.ndarray, *, weak: float, min_area: int,
                  keep_small=None) -> np.ndarray:
    """Bölge birleştirme (komşuluk grafiği): önce sınır gücü (`weight` ortalaması) `weak`'in altındaki en zayıf
    sınırdan başlayarak komşular birleşir (yumuşak geçiş bantları, gölge); sonra `min_area`'dan küçük bölge en uzun
    sınırı paylaştığı komşuya katılır. `keep_small(alan, renk, komşunun rengi) -> bool` doğruysa küçük bölge korunur.
    Dönen: kök etiket haritası (bölgeler kapalı, her sınır iki bölgeyi ayırır)."""
    import heapq
    pairs, cnt, tot = adjacency(lab, weight)
    area = np.bincount(lab.ravel(), minlength=n + 1).astype(float)
    csum = np.stack([np.bincount(lab.ravel(), weights=color[..., i].ravel(), minlength=n + 1) for i in range(3)], 1)
    parent = list(range(n + 1))
    nbr: dict[int, dict[int, list[float]]] = {i: {} for i in range(n + 1)}
    for (a, b), c, t in zip(pairs.tolist(), cnt.tolist(), tot.tolist()):
        nbr[a][b] = nbr[b][a] = [c, t]

    def merge(a: int, b: int) -> int:
        """b'yi a'ya katar."""
        parent[b] = a
        area[a] += area[b]
        csum[a] += csum[b]
        for x, (c, t) in nbr.pop(b).items():
            nbr[x].pop(b, None)
            if x == a:
                continue
            e = nbr[a].setdefault(x, [0.0, 0.0])
            e[0] += c
            e[1] += t
            nbr[x][a] = e
        return a

    heap = [(t / c, a, b) for (a, b), c, t in zip(pairs.tolist(), cnt.tolist(), tot.tolist()) if a and b and t / c < weak]
    heapq.heapify(heap)
    while heap:
        g, a, b = heapq.heappop(heap)
        if parent[a] != a or parent[b] != b or b not in nbr[a]:
            continue
        c, t = nbr[a][b]
        if abs(t / c - g) > 1e-6:                     # sınır büyüdü: güncel değerle yeniden sıraya
            if t / c < weak:
                heapq.heappush(heap, (t / c, a, b))
            continue
        keep, gone = (a, b) if area[a] >= area[b] else (b, a)
        k = merge(keep, gone)
        for x, (c2, t2) in nbr[k].items():
            if x and t2 / c2 < weak:
                heapq.heappush(heap, (t2 / c2, min(k, x), max(k, x)))
    order = sorted((i for i in range(1, n + 1) if parent[i] == i), key=lambda i: area[i])
    for i in order:
        if parent[i] != i or area[i] >= min_area or not nbr[i]:
            continue
        j = max((x for x in nbr[i] if x), key=lambda x: nbr[i][x][0], default=None)
        if j is None:
            continue
        if keep_small is not None and keep_small(area[i], csum[i] / max(area[i], 1), csum[j] / max(area[j], 1)):
            continue
        merge(j, i)
    roots = np.arange(n + 1)
    for i in range(n + 1):
        r = i
        while parent[r] != r:
            r = parent[r]
        roots[i] = r
    return roots[lab]
