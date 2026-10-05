"""Bölüm açılışları dizgiden: punto, bölüm başı boşluğu, başlık altı boşluk ve başlık sayfası.

Büyük harf kuralı («AVOKADO») yalnız bir dizgi alışkanlığıdır; çoğu kitapta başlık normal yazımlıdır
(«Avokado», «Böcek Kapan Menekşe») ya da küçük puntolu bir numaradır («1.»). Ortak olan dizgidir: bölüm
yeni sayfada, metinden aşağıda başlar; başlık gövdeden büyük ya da altında boşluk bırakılmıştır; bazı
kitaplarda başlık kendi sayfasındadır, metin sonraki sayfada başlar. Kural kitaptan bağımsızdır; sayfa
başlığı/altlığı (≥3 sayfada aynı kısa küçük satır ve tekrarlı sayfa kenarı satırı), künye, ithaf, içindekiler ve
tanıtım sayfası bölüm sayılmaz. 2026-10-01: 26 kabul kitabında ölçüldü (eski kural Babam 150, Duvarları 199 bölüm
buluyordu).
2026-10-02: büyük puntolu başlığın kendi satır aralığı gövdeninkinden büyüktür: aynı puntolu başlık satırları
arasındaki boşluk başlığı bölmez («DUT AĞACININ / ALTINDA»); gövdeden az büyük, birden çok satırlı başlık («YER
ALTI / OYUNLARI», 24/21 pt) altındaki boşlukla tanınır; yanda duran etiket («BÖLÜM 1») başlık satırlarının arasına
karışmaz; iri puntolu konuşma («Tabii ki FİLİN!», «… beliriyordu.») cümledir, başlık değildir.
2026-10-03 (25 kitap denetimi): sayfa başlığı/altlığı okunan metinle aynı kuralla (`editor.running_head`: kenarda
tekrar, tek/çift sayfa, puntodan bağımsız; aynı yükseklikte) ayıklanır; başlık sayfasından sonraki sayfanın başlığı
bölüm adına eklenmez (ara başlıktır) — başlık sayfası yalnız etiketse («Birinci Bölüm») eklenir; bağlaçla başlayan
kısa başlık («VE TEŞEKKÜR») ≤ 4 sayfa önceki başlığın devamıdır; iç kapak kitap adıyla aksansız/i-ayrımsız
karşılaştırılır («DARWIN» = «Darwin», «SÎNÂ» = «Sina»); başlık sonundaki dipnot imi atılır; gövdeden küçük puntolu
başlık sayfası (fotoğraf altı) ve «;»/«,» ile biten satır («Bu kitabın oluşmasında;») bölüm açmaz.
2026-10-03 (K14): tasarım fontuyla süslü yazılmış başlık («BÖReKlEr, KrEdİ KaRtI DÖKÜMlErİ Ve»; bir kelimede ≥ 2
büyük↔küçük geçişi) Türkçe başlık yazımıyla gösterilir (`display_title`); bağlaçla («ve, ile, ya da, veya, ama,
de/da») BİTEN başlık sonraki kısa satırla (aynı sayfada) ya da ≤ 4 sayfa sonraki kısa başlıkla birleşir.
"""

from __future__ import annotations

import re
from collections import Counter

SINK = 0.06          # normal metin üst kenarından bu oran (sayfa yüksekliği) kadar aşağıda başlayan sayfa: bölüm başı
HEAD_BIG = 1.15      # bu oranı aşan satır boşluk aranmadan başlık adayıdır
HEAD_MIN = 1.02      # gövdeden biraz büyük satır, altında boşluk varsa başlık
HEAD_LOW = 0.85      # bölüm başı sayfasında altında boşluk olan küçük puntolu satır da başlıktır («1.», «arayış»)
GAP = 1.8            # başlık ile metin arası: satır aralığının en az bu katı
_NOT_TITLE = ("içindekiler", "contents", "kaynakça", "kaynaklar", "dizin", "indeks", "index", "notlar", "bibliyografya",
              "yeni kitap önerimiz")
_SENT_BREAK = re.compile(r"([^\W\d_]+)[.!?…]+[\"”’']?\s+\S")   # başlıkta cümle sonu + devam: konuşma/metin
_ORDINAL = re.compile(r"^(?:[IVXLC]+|[A-ZÇĞİÖŞÜ])$")   # «II. BÖLÜM», «G. Marquez»: sıra/baş harf noktası cümle sonu değil
_CONTINUED = re.compile(r"\(\s*devam[ıi]?\s*\)\s*$", re.I)   # «EK 2: … (Devam)»: önceki başlığın sürmesi
_PAREN = re.compile(r"^\(.*\)$")          # başlık sayfasında ayraç içi alt satır («(Yıldırım Bayezid Han)»)


def _sent_break(t: str) -> bool:
    return any(not (m.group(0)[len(m.group(1))] == "." and _ORDINAL.match(m.group(1)))
               for m in _SENT_BREAK.finditer(t))
_NUMBER = re.compile(r"^\d{1,3}\.?$")
_IMPRINT = re.compile(r"www\.|\.com|\.tr\b|https?:|^[^\W\d_]+ (19|20)\d\d$", re.I)   # künye/adres: «İstanbul 2026»
_UNFINISHED = re.compile(r"[;,]\s*$")     # «Bu kitabın oluşmasında;» — cümle sürüyor (teşekkür), başlık değil
_DEDICATION = re.compile(r"[’'](y?[ae]|n[ae])\W*$|\b\w+(ına|ine|una|üne)\W*$")       # ithaf: «… X'e…», «… hatırasına…»


def _norm(t: str) -> str:
    # Türkçe küçültme: «İ».casefold() noktalı «i̇» verir, «İÇİNDEKİLER» «içindekiler»e eşlenmezdi
    t = t.replace("İ", "i").replace("I", "ı").casefold()
    return " ".join(re.sub(r"[^\w\s]|\d", " ", t).split())


def _median(xs: list[float]) -> float:
    xs = sorted(xs)
    return xs[len(xs) // 2] if xs else 0.0


def _sentence(t: str) -> bool:
    """Başlık değil, iri puntolu cümle: noktayla ya da ünlemle biter (üç nokta değil) ve ilk kelimeden sonra
    küçük harfle başlayan bir kelime taşır («Tabii ki FİLİN!», «O sırada sanki … beliriyordu.»). Başlıklar
    büyük harfli ya da her kelimesi büyük harfle başlar; tek kelimelik ünlem («GECELER!», «sensİz!») ve büyük
    harfsiz dizgi («razıyım yâ rab!») başlıktır. Birden çok satır cümle olarak sürüyorsa («… sanırsın? Küllerin
    …», şiir) ya da son kelime bölünmüşse («izledi-») metindir."""
    t = t.strip()
    if len(t.split()) > 1 and (_sent_break(t) or re.search(r"(?:^|\s)[^\W\d_]+[-­]$", t)):
        return True                     # satırlar cümle olarak sürüyor ya da kelime bölünmüş: metin
    if not re.search(r"[^.!…][.!]$", t) or _NUMBER.match(t) or not any(c.isupper() for c in t):
        return False                    # küçük harfli dizgi («razıyım yâ rab!») başlık olabilir
    words = re.findall(r"[^\W\d_][\w’'-]*", t)
    return len(words) >= 2 and any(w[0].islower() for w in words[1:])


def _title_like(t: str) -> bool:
    t = t.strip()
    if not t or len(t) > 80 or t[0] in "“\"'‘«-–—…(" or _IMPRINT.search(t):
        return False
    if _NUMBER.match(t):
        return True
    return bool(re.search(r"[^\W\d_]", t)) and not _sent_break(t)


def _strip_running_heads(raw: dict[int, list[dict]], names=()) -> dict[int, list[dict]]:
    """Sayfa başlığı/altlığı (`editor.running_head`, okunan metinle aynı kural): sayfanın en üst ve en alt harfli
    satırı, kitap boyunca aynı konumda tekrar ediyorsa. Puntodan bağımsız: gövde puntosunda dizilmiş sayfa başlığı
    («AYŞE OSMANOĞLU» 11,5 pt) da ayıklanır."""
    from . import running_head

    def lettered(ls):
        return sorted((ln for ln in ls if re.search(r"[^\W\d_]", ln["text"])), key=lambda l: l["y0"])

    edges, at = {}, {}
    for i, ls in raw.items():
        lt = lettered(ls)
        if len(lt) >= 2:                  # yalnız tek satırı olan sayfa (başlık sayfası) sayfa başlığı taşımaz
            edges[i] = {"top": lt[0]["text"], "bottom": lt[-1]["text"]}
            at[i] = {"top": lt[0], "bottom": lt[-1]}
    marks = running_head.detect(edges, len(edges), names)
    # Sayfa başlığı hep aynı yükseklikte durur: bölüm adı sağ sayfanın başlığıysa, bölümün açılış sayfasındaki aynı
    # ad (aşağıda, başlık olarak) ayıklanmaz.
    ys: dict[tuple, list[float]] = {}
    for i, m in marks.items():
        for pos in m:
            ys.setdefault((pos, running_head.key(at[i][pos]["text"])), []).append(at[i][pos]["y0"])
    out = {}
    for i, ls in raw.items():
        drop = set()
        for pos in marks.get(i, ()):
            ln = at[i][pos]
            y = _median(ys[(pos, running_head.key(ln["text"]))])
            if abs(ln["y0"] - y) <= max(ln["size"], 1.0) * 1.5:
                drop.add(id(ln))
        out[i] = [ln for ln in ls if id(ln) not in drop] if drop else ls
    return out


def page_layout(doc, page_lines, names=()) -> dict:
    """Kitabın gövde puntosu, satır aralığı ve normal metnin üst kenarı; sayfa başlığı/altlığı ayıklanmış satırlar.
    `names`: kitabın adı/yazarı — kenarda tekrar eden bu satır az sayfada olsa da sayfa başlığıdır."""
    raw = _strip_running_heads({i: [ln for ln in page_lines(p) if ln["text"].strip() and not ln["text"].strip().isdigit()]
                                for i, p in enumerate(doc, 1)}, names)
    sizes: Counter = Counter()
    for ls in raw.values():
        for ln in ls:
            sizes[round(ln["size"], 1)] += len(ln["text"])
    body = sizes.most_common(1)[0][0] if sizes else 0.0
    rep = Counter(_norm(ln["text"]) for ls in raw.values() for ln in ls if ln["size"] < body * 0.9)
    pages, steps, tops = {}, [], []
    for i, p in enumerate(doc, 1):
        ls = [ln for ln in raw[i]
              if not (ln["size"] < body * 0.9 and rep[_norm(ln["text"])] >= 3 and len(_norm(ln["text"])) < 60)]
        pages[i] = {"lines": ls, "h": p.rect.height}
        bl = [ln for ln in ls if abs(ln["size"] - body) < 0.6]
        if len(bl) >= 8:
            tops.append(bl[0]["y0"] / p.rect.height)
            steps += [b["y0"] - a["y0"] for a, b in zip(bl, bl[1:]) if 0 < b["y0"] - a["y0"] < body * 3]
    return {"pages": pages, "body": body, "step": _median(steps) or body * 1.4, "top": _median(tops)}


def _opening(v: dict, L: dict) -> dict | None:
    ls, body, step = v["lines"], L["body"], L["step"]
    if not ls:
        return None
    sunk = ls[0]["y0"] / v["h"] > L["top"] + SINK

    def is_body(ln):
        return abs(ln["size"] - body) < 0.6 and len(ln["text"]) > 25

    if sum(map(is_body, ls)) < 3 and (len(ls) <= 6 or sum(
            len(ln["text"]) > 25 and ln["size"] > body + 0.6 for ln in ls) < 3):
        # başlık sayfası: yalnız kısa satırlar (bölüm adı, kısım adı); metin sonraki sayfada. Metni gövdeden
        # İRİ puntolu sayfa («Evet Selin, …» 20/14 pt) başlık sayfası değildir: açılışı aşağıda aranır.
        # Gövdeden küçük puntolu metin (arka kapak tanıtımı, yazar özgeçmişi) bölüm açmaz.
        lines = [ln for ln in ls if _title_like(ln["text"])]
        # ayraç içi alt satır (perde altı «(Yıldırım Bayezid Han)»): en çok 3 satırlık başlığın altındaki son satır;
        # sayfayı bozmaz, ada girmez
        last = max(ls, key=lambda l: l["y0"])
        paren = [last] if (last not in lines and _PAREN.match(last["text"].strip()) and len(lines) <= 3) else []
        words = sum(len(ln["text"].split()) for ln in lines + paren)
        text = " ".join(ln["text"].strip() for ln in _reading_order(lines))
        # gövdeden belirgin küçük satır (yan çevrilmiş tablonun başlık hücresi «MİLADİ MALI») sayfayı bozmaz ama ada
        # girmez; denetimler (cümle, kelime sayısı) bütün satırlara bakar
        named = [ln for ln in lines if ln["size"] >= body * HEAD_LOW] or lines
        # gövdeden küçük puntolu kısa satırlar fotoğraf altı ya da künye notudur («Hatıratın yazarı … resmi»)
        if (lines and len(lines) + len(paren) == len(ls) and len(ls) <= 6 and words <= 12
                and not _DEDICATION.search(text) and not _sentence(text)
                and max(ln["size"] for ln in lines) >= body - 0.6 and not _UNFINISHED.search(text)):
            return {"title": " ".join(ln["text"].strip() for ln in _reading_order(named)),
                    "size": max(ln["size"] for ln in named), "kind": "page"}
        return None
    head, i = [], 0
    while i < len(ls) and len(head) < 5:
        ln = ls[i]
        nxt = ls[i + 1] if i + 1 < len(ls) else None
        gap = (nxt["y0"] - ln["y0"]) if nxt else 1e9
        big = ln["size"] >= body * HEAD_BIG
        sized = ln["size"] >= body * HEAD_MIN or (sunk and ln["size"] >= body * HEAD_LOW)
        ok = _title_like(ln["text"]) and (
            big or (gap >= step * GAP and sized)
            or (head and abs(ln["size"] - head[-1]["size"]) < 0.3)
            or (not head and sized and _run_then_gap(ls, i, step)))
        if not ok:
            break
        head.append(ln)
        i += 1
        if gap >= step * GAP and not _title_continues(ln, nxt, gap):
            break
    # Bağlaçla biten başlık («… DÖKÜMlErİ Ve») yarımdır: hemen altındaki kısa satır (puntosu ya da aradaki boşluk
    # farklı olsa da) başlığın devamıdır («BeN»).
    while (head and i < len(ls) and len(head) < 6 and ends_with_conjunction(" ".join(ln["text"] for ln in head))
           and _title_like(ls[i]["text"]) and len(ls[i]["text"].split()) <= 4 and not is_body(ls[i])):
        head.append(ls[i])
        i += 1
    if not head:
        return {"title": "", "size": 0, "kind": "sunk"} if sunk else None
    title = " ".join(ln["text"].strip() for ln in _reading_order(head))
    if title[:1].islower() and not sunk:
        return None
    if _sentence(title) or _UNFINISHED.search(title):
        return {"title": "", "size": 0, "kind": "sunk"} if sunk else None
    return {"title": title, "size": max(ln["size"] for ln in head), "kind": "sunk" if sunk else "head"}


def _title_continues(ln: dict, nxt: dict | None, gap: float) -> bool:
    """Büyük puntolu başlığın kendi satır aralığı: aynı puntodaki sonraki başlık satırı, puntonun 1,6 katı
    içinde («BEYNİMDEN» 34 pt, 40 pt aşağıda «CIZIRTILAR GELİYOR»). Gövde satır aralığıyla ölçülen boşluk
    başlığı ortasından bölerdi."""
    return (nxt is not None and abs(nxt["size"] - ln["size"]) < 0.3 and gap <= ln["size"] * 1.6
            and _title_like(nxt["text"]))


def _run_then_gap(ls: list[dict], i: int, step: float) -> bool:
    """Gövdeden az büyük (HEAD_MIN), birden çok satırlı başlık: aynı puntoda, başlık satırı gibi 2–4 satır, ardından
    gövde satır aralığının GAP katı boşluk («YER ALTI / OYUNLARI» 24 pt, gövde 21 pt). Tek satırlıyı eski kural tanır."""
    j = i
    while (j + 1 < len(ls) and j - i < 3 and abs(ls[j + 1]["size"] - ls[i]["size"]) < 0.3
           and _title_like(ls[j + 1]["text"])
           and ls[j + 1]["y0"] - ls[j]["y0"] <= max(step * GAP, ls[i]["size"] * 1.6)):
        j += 1
    after = (ls[j + 1]["y0"] - ls[j]["y0"]) if j + 1 < len(ls) else 1e9
    return j > i and after >= step * GAP


def _reading_order(lines: list[dict]) -> list[dict]:
    """Başlık satırları okuma sırasıyla. Yatayda öbürleriyle hiç örtüşmeyen satır ayrı bir sütundur (sağda duran
    «BÖLÜM 1» etiketi, başlığın iki satırının arasına düşen yüksekliktedir): sütunlar ayrı okunur, tek satırlık kısa
    etiket sütunu önce. Konumu bilinmeyen satırlar geldikleri sırada kalır."""
    if len(lines) < 2 or any(ln.get("x0") is None or ln.get("x1") is None for ln in lines):
        return lines
    cols: list[list[dict]] = []
    for ln in sorted(lines, key=lambda l: l["y0"]):
        for col in cols:
            if any(min(ln["x1"], c["x1"]) > max(ln["x0"], c["x0"]) for c in col):
                col.append(ln)
                break
        else:
            cols.append([ln])
    if len(cols) == 1:
        return lines
    # harf harf dizilmiş tek satır («R», «TA», «İ»…) ayrı sütunlar gibi görünür: satır satır, soldan sağa
    if len(cols) > 3:
        return sorted(lines, key=lambda l: (round(l["y0"] / max(l["size"], 1.0)), l["x0"]))
    label = [c for c in cols if len(c) == 1 and len(c[0]["text"].split()) <= 2]
    rest = [c for c in cols if c not in label]
    if not rest:
        return lines
    # etiket öbür satırların yüksekliği içinde durur; sayfanın dibindeki tablo başlığı («MİLADİ MALI») etiket değil
    top, bottom = min(ln["y0"] for c in rest for ln in c), max(ln["y0"] for c in rest for ln in c)
    keep = [c for c in label if not top <= c[0]["y0"] <= bottom]
    label = [c for c in label if c not in keep]
    rest += keep
    return [ln for c in label + sorted(rest, key=lambda c: c[0]["y0"]) for ln in c]


def page_headings(doc, page_lines, names=()) -> dict[int, dict]:
    """Sayfa no → açılış ({title, size, kind: page|sunk|head|empty}). Açılış olmayan sayfa yoktur."""
    L = page_layout(doc, page_lines, names)
    out = {}
    for i, v in L["pages"].items():
        o = _opening(v, L)
        if o:
            out[i] = o
        elif not v["lines"]:
            out[i] = {"title": "", "size": 0, "kind": "empty"}
    return out


def _front(page: int, last_page: int) -> bool:
    """İç kapak/künye bölgesi: ilk 6 sayfa ya da kitabın ilk onda biri."""
    return page <= max(6, last_page // 10)


def _titles(book_title) -> list[str]:
    return [t for t in ([book_title] if isinstance(book_title, str) else list(book_title or ())) if t and t.strip()]


def _is_book_title(title: str, book_title) -> bool:
    """Başlık kitabın kendi adı mı. Harf karşılaştırması aksansız, boşluksuz, noktalama/kesme işaretsiz ve noktalı/
    noktasız i ayrımsız: «DARWIN VE OSMANLILAR» (Türkçe küçültmede «darwın») = «Darwin ve Osmanlılar», «İBN SÎNÂ» =
    «İbn Sina», «Dİjİtal Dünyada e-beveyn» = «Dijital Dünyada Ebeveyn» (2026-10-03: üçü bölüm oldu). Kitabın adı
    seri adıyla başlıyorsa iç kapakta yalnız adın kendisi durur («ADANA’DA» ↔ «Levent Adana'da», K16): adın baş ya
    da son kelimeleri, harflerinin en az yarısını taşıyorsa, kitabın adı sayılır («Giriş» ↔ «Giriş Sanatı» değil)."""
    from .running_head import key
    kt = key(title)
    if not kt:
        return False
    for bt in _titles(book_title):
        kb = key(bt)
        if not kb:
            continue
        if kt.startswith(kb):
            return True
        words = [key(w) for w in bt.split() if key(w)]
        for n in range(1, len(words)):
            for part in ("".join(words[:n]), "".join(words[n:])):
                if part == kt and 2 * len(kt) >= len(kb):
                    return True
    return False


def _skip(title: str, book_title, page: int, last_page: int) -> bool:
    from .running_head import key
    # aksansız ve i/ı ayrımsız: «İÇINDEKILER» (karışık yazım) da içindekilerdir
    if any(key(title).startswith(key(x)) for x in _NOT_TITLE):
        return True
    # kitabın kendi adı ilk sayfalarda: iç kapak, bölüm değil
    return _front(page, last_page) and _is_book_title(title, book_title)


#: Künye/imza satırının etiketi («Çizer: Derya …», «Yazar: …», «Çeviren: …»): iki noktayla. «Yazarın Dönüşü» değil.
_CREDIT = re.compile(
    r"(?:^|(?<=\s))(?:yazar|yazan|yazanlar|çizer|çizen|çizim|çizimler|resim|resimler|resimleyen|resimlendiren|"
    r"illüstrasyon|illüstrasyonlar|illüstratör|illüstre eden|görseller|çeviren|çeviri|çevirmen|türkçesi|"
    r"türkçeleştiren|editör|editörler|yayına hazırlayan|hazırlayan|hazırlayanlar|derleyen|derleyenler|"
    r"yayın yönetmeni|genel yayın yönetmeni|kapak tasarımı|kapak tasarım|kapak|mizanpaj|mizanpaj tasarım|"
    r"sayfa tasarımı|redaksiyon|düzelti|son okuma|anlatan|uyarlayan|seslendiren|sunan)\s*[:：]",
    re.I)


def _strip_byline(title: str, names: list[str] = ()) -> str:
    """Bölüm adından künye/imza kısmı (K16, «ADANA’DA Mustafa Orakçı Çizer: Derya Işık Özbay»): etiketli künye satırı
    («Çizer:», «Resimleyen:», «Çeviren:», «Yazan:», «Editör:» …) ve sonrası; başta ya da sonda bütün kelimeleriyle
    duran, en az iki kelimelik yazar/çizer adı (künyeden ya da CRM'den). Ekli ad («Mustafa Kemal'in Çocukluğu») ad
    değildir: anahtarı farklıdır («kemalin»)."""
    from .running_head import key
    t = " ".join((title or "").split())
    m = _CREDIT.search(t.replace("İ", "i").replace("I", "ı"))
    cut = m is not None
    if m:
        t = t[:m.start()].rstrip(" ,;:-–—/|·•")
    words = t.split()
    keys = [key(w) for w in words]
    for name in names or ():
        nk = [key(w) for w in (name or "").split() if key(w)]
        if len(nk) < 2 or len(nk) > len(words):
            continue                    # tek kelimelik ad («Derya») sıradan kelimeyle karışır
        if keys[-len(nk):] == nk:
            words, keys, cut = words[:-len(nk)], keys[:-len(nk)], True
        elif keys[:len(nk)] == nk:
            words, keys, cut = words[len(nk):], keys[len(nk):], True
    if not cut:
        return title                    # imza yok: başlık olduğu gibi («–Kuruş-» sonundaki çizgi dahil)
    return " ".join(words).strip(" ,;:-–—/|·•")


#: Yalnız bölüm etiketi olan başlık («Birinci Bölüm», «BÖLÜM 3», «II. Kısım», «1.»): adı sonraki sayfadadır.
_LABEL_WORDS = {"birinci", "ikinci", "üçüncü", "dördüncü", "beşinci", "altıncı", "yedinci", "sekizinci", "dokuzuncu",
                "onuncu", "yirminci", "otuzuncu", "on", "yirmi", "otuz", "ilk", "son", "sonuncu", "bölüm", "kısım",
                "kitap", "cilt", "fasıl", "fasl", "bab", "perde", "ünite", "part", "chapter", "book"}
_ROMAN = re.compile(r"^[ıivxlc]+$")
#: Bağlaçla başlayan başlık («VE TEŞEKKÜR») önceki başlığın devamıdır («ÖNSÖZ» iki sayfa önce).
_CONJ = re.compile(r"^(ve|ile|veya|ya da|yahut)\b")
#: başlık sonundaki dipnot imi: «DERSAADET’TE1», «… DARWIN Mİ YIKTI?1» (boşluksuz, harf ya da soru/ünlem/tırnaktan sonra)
_NOTE_MARK = re.compile(r"(?:(?<=[^\W\d_])|(?<=[?!’”\"')]))\d{1,2}$")


#: Başlığı bitiren bağlaç («BÖReKlEr, KrEdİ KaRtI DÖKÜMlErİ Ve»): başlık bir sonraki kısa satırda/başlıkta sürer.
_CONJ_END = frozenset({"ve", "ile", "veya", "yahut", "ama", "de", "da"})


def ends_with_conjunction(title: str) -> bool:
    """Son kelime ayrı yazılmış bağlaç («… Ve», «… ya da»). Kesmeyle bitişik ek («Ankara'da») bağlaç değildir."""
    words = title.replace("İ", "i").replace("I", "ı").casefold().split()
    last = words[-1].strip(".,;:!?…\"”“«»()") if words else ""
    return len(words) >= 2 and last in _CONJ_END          # «ya da» de «da» ile biter


def _irregular_word(word: str) -> bool:
    """Aynı kelimede (harf öbeğinde) en az iki büyük↔küçük geçişi: tasarım fontunun süslü yazımı («BÖReKlEr»,
    «KaRtI»). «Kulağım» (bir geçiş), «GİRİŞ» (hiç) ve kesmeyle ayrılmış ek («ALİ'nin») olağandır."""
    for part in re.findall(r"[^\W\d_]+", word):
        flips = sum(1 for a, b in zip(part, part[1:]) if a.isupper() != b.isupper())
        if flips >= 2:
            return True
    return False


def display_title(title: str) -> str:
    """Bölüm adının gösterilen yazımı. Harf büyüklüğü düzensiz başlık (bir kelimede ≥ 2 büyük↔küçük geçişi) Türkçe
    başlık yazımına çevrilir (`book_title.title_case`, dizilmiş metin: «I» → «ı»); tümü büyük («GİRİŞ») ve olağan
    karışık («Kulağım Kapıda») başlık olduğu gibi kalır."""
    title = " ".join((title or "").split())
    if not any(_irregular_word(w) for w in title.split()):
        return title
    from .book_title import title_case, tr_lower
    return title_case(tr_lower(title), typed=False)


def _scattered(title: str) -> bool:
    """Yalnız tek harflerden oluşan, en az iki parçalı başlık («G İ D İ E», «U Ğ»)."""
    words = title.split()
    return len(words) >= 2 and all(len(w) == 1 and w.isalpha() for w in words)


#: Türkçede tek başına yazılan 1–2 harfli sözcükler (bağlaç, soru eki, zamir, ünlem, sık ad): bunlar dağılmış harf
#: sayılmaz («Ali ve Su», «O da Ben»).
_SHORT_WORDS = frozenset({
    "o", "a", "ı", "ve", "de", "da", "ki", "mi", "mı", "mu", "mü", "ne", "ya", "bu", "şu", "en", "ey", "ah", "of",
    "oh", "eh", "ha", "he", "hu", "iç", "ön", "üç", "su", "ay", "an", "el", "ev", "iş", "ok", "ip", "at", "ad", "ak",
    "al", "ar", "aş", "az", "iz", "öz", "uç", "ün", "us", "ot", "it", "il", "is", "on", "un", "ağ"})


_GARBLED = re.compile(r"[\x00-\x08\x0b-\x1f$%+{}<>#@~^|\\=±²³§]")


def _garbled(title: str) -> bool:
    """Yazı tipi kodlaması bozuk PDF'in okunamaz başlığı («ýaý.$%+ý,%2», «L{9KJ\x03F7Hw7B7H?»): denetim karakteri ya da
    başlıkta bulunmayan simge taşır."""
    return bool(_GARBLED.search(title))


def _sentence_like(title: str) -> bool:
    """Başlık değil, iri puntolu cümle (resimli kitabın ilk satırı «Çengel zıplaya zıplaya zıpladı», «Atlar alçalıp
    yükseldikçe çocuklar…»): ≥ 4 kelime, ilk kelime büyük harfle başlar, sonrakilerin dörtte üçü küçük harfle.
    Küçük harfle başlayan satırı `_mid_sentence` yakalar; Başlık Yazımı ve büyük harfli başlık bu değildir."""
    words = re.findall(r"[^\W\d_][\w’'‛-]*", title)
    if len(words) < 4 or not words[0][0].isupper():
        return False
    rest = words[1:]
    return sum(w[0].islower() for w in rest) >= 0.75 * len(rest)


def _scattered_weak(title: str) -> bool:
    """Harfleri dağılmış başlık, parçaları 1–2 harfli («KS DE T O», «LARI UN K A MU», «e v miş git», «M Zİ Bİ
    ÜKOSMAN Y»): en az üç harfli parça, yarısı ya da fazlası 1–2 harfli ve en az biri sözcük olmayan tek harf.
    Rakamlı etiket («1. BÖLÜM», «BÖLÜM 12»), kısa gerçek ad («Ali ve Su», «NE YAPMALI?»), kesmeyle ekli tek harf
    («A'dan Z'ye») yakalanmaz."""
    low = title.replace("İ", "i").replace("I", "ı").casefold()
    parts = [w for w in (re.sub(r"[^\w'’]|\d|_", "", t) for t in low.split()) if re.search(r"[^\W\d_]", w)]
    if len(parts) < 3:
        return False
    short = [p for p in parts if len(p) <= 2]
    return 2 * len(short) >= len(parts) and any(len(p) == 1 and p not in _SHORT_WORDS for p in short)


#: Satır sonunda bölünmüş kelime («uyuyama- dı»): gövde metni, başlık değil.
_BROKEN_WORD = re.compile(r"[^\W\d_][-­]\s+[^\W\d_]")


def _mid_sentence(title: str, book_lower: bool) -> bool:
    """Küçük harfle başlayan, cümle ortası görünümlü satır (sayfa başı satırından sonraki gövde satırı: «nasıl
    kaçabileceğini düşünürken … uyuyama- dı ancak»): içinde satır sonu bölünmesi var, ya da kitabın başlıkları küçük
    harfle dizilmiyorken (`book_lower` değil) dört ve daha çok kelime. Başlıkları bilerek küçük harfle dizilmiş
    kitapta («yol içre yol, sır içre sır», «birinci bölüm BABAM VE …») küçük harf başlık olağandır."""
    t = title.strip()
    if not t[:1].islower():
        return False
    return bool(_BROKEN_WORD.search(t)) or (not book_lower and len(t.split()) >= 4)


#: Tek başına bölüm adı olamayan, tekrarlanan etiket: tek karakter ya da yalnız roma rakamı («I» ×7).
_REPEAT_MIN = 3


def _number_repeats(starts: list[dict]) -> list[dict]:
    """Aynı ad ≥ 3 bölümde ve ad tek karakter ya da yalnız roma rakamıysa (dizgide her bölümün numarası «I»
    okunmuş): o bölümler sırayla numaralanır — roma rakamıysa «I», «II», «III» …, değilse «1. Bölüm», «2. Bölüm» …
    Anlamlı tekrar eden ad («NE YAPMALI?») değişmez."""
    count = Counter(_norm(s["title"]) or s["title"].strip() for s in starts)
    out, seen = [], Counter()
    for s in starts:
        t = s["title"].strip()
        k = _norm(t) or t
        bare = t.rstrip(".")
        if count[k] >= _REPEAT_MIN and (len(bare) == 1 or _ROMAN.match(_norm(bare) or "-")):
            seen[k] += 1
            n = seen[k]
            roman = _ROMAN.match(_norm(bare) or "-") and bare.isupper()
            s = {**s, "title": _to_roman(n) if roman else f"{n}. Bölüm"}
        out.append(s)
    return out


def _to_roman(n: int) -> str:
    out = ""
    for v, r in ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"), (50, "L"), (40, "XL"),
                 (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I")):
        while n >= v:
            out, n = out + r, n - v
    return out


#: «ithaf» sözü başlıkta («Siyah Lale’ye ithaf olunur…»)
_ITHAF_WORD = re.compile(r"\bithaf", re.I)


def _dedication(title: str, lines: list[str], page: int, last_page: int) -> bool:
    """İthaf sayfası (56 kitap denetimi: «… ithaf olunur…» ilk bölümün adı oldu): başlıkta «ithaf» sözü, ya da ön
    bölgedeki kısa sayfanın metni `page_scope.is_dedication` ile ithaf (ilk iki sayfadan sonra güçlü kanıtla)."""
    if _ITHAF_WORD.search(title.replace("İ", "i")):
        return True
    if not _front(page, last_page):
        return False
    from .page_scope import is_dedication
    return is_dedication([t for t in lines if t], strict=page > 2)


def _label_only(title: str) -> bool:
    return all(w in _LABEL_WORDS or _ROMAN.match(w) for w in _norm(title).split())


def _clean_title(title: str) -> str:
    return _NOTE_MARK.sub("", " ".join(title.split())).strip()


def _join_continuations(starts: list[dict]) -> list[dict]:
    """Bağlaçla başlayan kısa başlık, en çok 4 sayfa önceki aynı puntolu kısa başlığın devamıdır: tek bölüm.
    Bağlaçla BİTEN başlık («… DÖKÜMlErİ Ve») yarımdır: en çok 4 sayfa sonraki kısa (≤ 6 kelime) başlık devamıdır
    (punto aynı olmayabilir: süslü dizgide satırlar farklı büyüklükte)."""
    out: list[dict] = []
    for s in starts:
        prev = out[-1] if out else None
        near = prev is not None and s["page"] - prev["page"] <= 4
        if (near and _CONJ.match(_norm(s["title"])) and abs(s["size"] - prev["size"]) < 0.6
                and len((prev["title"] + " " + s["title"]).split()) <= 6):
            prev["title"] = prev["title"] + " " + s["title"]
            continue
        if near and ends_with_conjunction(prev["title"]) and 0 < len(s["title"].split()) <= 6:
            prev["title"] = prev["title"] + " " + s["title"]
            continue
        out.append(dict(s))
    return out


def chapters_from_pages(pages: list[dict], headings: dict[int, dict], book_title: str | list[str] = "",
                        names: list[str] = ()) -> list[dict]:
    """Sayfalar (page_no + spans) ve dizgi açılışlarından bölümler: [{title, page_from, page_to}]. Sayfa
    başlığı/altlığı spanları (`source.RUNNING_HEAD`) sayfanın metni sayılmaz. `book_title`: kitabın adı ya da
    adları (kayıt, künye TITLE, CRM); `names`: yazar/çizer/çevirmen adları (künye, CRM) — başlıktaki imza atılır."""
    by_page = {p["page_no"]: [s["text"].strip() for s in p["spans"]
                              if s["text"].strip() and s.get("role") != "running_head"] for p in pages}
    last_page = max(by_page, default=0)
    starts, pending = [], None
    for p in sorted(by_page):
        h = headings.get(p)
        if h and h["kind"] == "empty":
            continue
        if h and h["title"]:
            # künye/imza satırı bölüm adına girmez (K16); başlıkta yalnız imza kaldıysa (iç kapakta yazar adı,
            # «Çizer: …») sayfa başlıksızdır
            title = _strip_byline(h["title"], names)
            if title != h["title"]:
                h = {**h, "title": title}
                if not title and h["kind"] == "page":
                    pending = None
                    continue
        if h and h["title"] and _dedication(h["title"], by_page[p], p, last_page):
            pending = None              # ithaf sayfası bölüm açmaz (page_scope'un ithaf kuralı)
            continue
        near = pending is not None and p - pending["last"] <= 2
        if h and h["title"] and _CONTINUED.search(h["title"]):
            # «(Devam)» sayfası önceki başlığın sürmesidir (yan çevrilmiş ek tablonun ikinci sayfası): bölüm açmaz,
            # ada eklenmez
            if pending is not None:
                pending["last"] = p
            continue
        if h and h["kind"] == "page":
            if _skip(h["title"], book_title, p, last_page):
                pending = None
            elif near:
                pending.update(title=pending["title"] + " " + h["title"], last=p)
            else:
                pending = {"page": p, "title": h["title"], "size": h["size"], "last": p, "kind": "page"}
            continue
        if near and by_page[p]:
            # Başlık sayfasından sonraki sayfanın açılışı bölümün ilk ara başlığıdır («AŞKIN MAHİYETİ» sayfasından
            # sonra «AŞK, İNSANIN YAŞADIĞI…»): başlığa eklenmez. Başlık sayfası yalnız etiketse («Birinci Bölüm»)
            # bölümün adı odur.
            sub = h["title"] if h and _label_only(pending["title"]) else ""
            starts.append({**pending, "title": (pending["title"] + " " + sub).strip()})
        elif h and h["title"]:
            n = _norm(h["title"])
            paras = by_page[p]
            bio = any(_norm(t).startswith(n) and len(t) > 60 for t in paras[1:2]) if n else False
            # Sahne arasından sonra büyük puntolu ilk satır («Dükkânı için özel bir e-posta hesabı oluşturduktan
            # sonra») aynı paragrafta cümle olarak sürer: başlık değil, başlık kendi paragrafıdır.
            bio = bio or (h["kind"] == "head" and bool(n) and any(
                _norm(t).startswith(n) and len(t) > len(h["title"]) + 40 for t in paras[:1]))
            if (n or _NUMBER.match(h["title"].strip())) and not _skip(h["title"], book_title, p, last_page) and not bio:
                starts.append({"page": p, "title": h["title"], "size": h["size"], "kind": h["kind"]})
        pending = None
    # Bölüm başlıkları bir kitapta aynı dizgide: güçlü açılışların (başlık sayfası / bölüm başı boşluğu) puntosundan
    # sapan zayıf aday (yalnız büyük punto) konuşma balonu ya da ara başlıktır.
    # Harf harf dağılmış zayıf aday («G İ D İ E»: dalgalı dizilmiş resimli kitap başlığı, okuma sırası bozuk)
    # okunabilir bir ad değildir. K16'da iç kapak artık bölüm sayılmayınca güçlü açılışı kalmayan kitapta bunlar
    # bölüm oluyordu (önce iç kapağın puntosu onları ayıklıyordu).
    # 2026-10-03 (56 kitap): çoğu parçası 1–2 harfli dağılmış başlık («KS DE T O», «e v miş git») her açılış
    # türünde zayıftır; küçük harfle başlayan cümle ortası satır («… uyuyama- dı ancak») başlık değildir.
    lettered = [s for s in starts if re.search(r"[^\W\d_]", s["title"])]
    book_lower = bool(lettered) and 2 * sum(s["title"].strip()[:1].islower() for s in lettered) >= len(lettered)
    starts = [s for s in starts if not ((s["kind"] == "head" and _scattered(s["title"])) or _scattered_weak(s["title"])
                                        or _mid_sentence(s["title"], book_lower))]
    strong = [s["size"] for s in starts if s["kind"] in ("page", "sunk")]
    if strong:
        keep = {k for k, _ in Counter(round(x) for x in strong).most_common(2)}
        starts = [s for s in starts if s["kind"] != "head" or round(s["size"]) in keep or s["size"] > max(keep)]
    # Okunamaz (bozuk kodlamalı) başlık bölüm açmaz. İri puntolu cümle («Çengel zıplaya zıplaya zıpladı») kitabın
    # başlık yazımı değilse bölüm açmaz: kitapta en çok iki açılış varsa (resimli tek öykü) ya da cümle biçimli
    # açılışlar azınlıksa (< %25) ve konuşma işareti taşıyorsa. Şiir kitabının dize başlıkları, cümle biçimli
    # başlıklı kitap (çoğunluk) ve isim öbeği başlık («Yeniden imparator olma girişimi») kalır.
    starts = [s for s in starts if not _garbled(s["title"])]
    sentences = [s for s in starts if s["kind"] != "page" and _sentence_like(s["title"])]
    if sentences and len(starts) <= 2:
        drop = {id(s) for s in sentences}
    else:                                      # azınlıkta, konuşma işaretli («Genç adam dedi ki, ‘Sen…»)
        talk = [s for s in sentences if re.search(r"[,‘“”\"]", s["title"])]   # kesme (’ ') iyeliktir, konuşma değil
        drop = {id(s) for s in talk} if len(sentences) < 0.25 * len(starts) else set()
    if sentences:
        starts = [s for s in starts if id(s) not in drop]
    # Kitabın son %15'inde ≥ 3 kez geçen aynı ad (rakamıyla birlikte) bölüm değil, yayınevi tanıtım sayfasının
    # öğesidir («Eğitimi» ×10); «BÖLÜM 22», «BÖLÜM 23» ayrı adlardır.
    back = last_page - max(5, last_page * 15 // 100)
    tail = Counter(" ".join(s["title"].casefold().split()) for s in starts if s["page"] > back)
    starts = [s for s in starts if not (s["page"] > back and tail[" ".join(s["title"].casefold().split())] >= 3)]
    starts = _number_repeats([{**s, "title": display_title(s["title"])}
                              for s in _join_continuations([{**s, "title": _clean_title(s["title"])} for s in starts])])
    # Kitabın tek açılışı ilk sayfalardaki başlık sayfasıysa o iç kapaktır (adı kitap adına uymasa da): bölüm yok.
    if (len(starts) == 1 and starts[0]["kind"] == "page" and _front(starts[0]["page"], last_page)
            and not _label_only(" ".join(starts[0]["title"].split()[:2]))):
        # «Birinci Bölüm …» başlık sayfası iç kapak değil, bölümdür
        starts = []
    if not starts:
        return [{"title": "Kitap", "page_from": 1, "page_to": last_page}]
    out = []
    for i, s in enumerate(starts):
        end = starts[i + 1]["page"] - 1 if i + 1 < len(starts) else last_page
        out.append({"title": s["title"], "page_from": s["page"], "page_to": max(s["page"], end)})
    if starts[0]["page"] > 1:
        out.insert(0, {"title": "Başlıksız başlangıç", "page_from": 1, "page_to": starts[0]["page"] - 1})
    return out


def for_generation(generation_id: str, pages: list[dict] | None = None) -> list[dict] | None:
    """Okunmuş kitabın bölümleri, kitabın kendi PDF dizgisinden. PDF açılamazsa None (çağıran eski kurala döner)."""
    from . import db, source
    from .document import _open_version, _page_lines
    g = db.one("SELECT g.book_version_id, b.id AS book_id, b.title FROM generation g "
               "JOIN book_version bv ON bv.id=g.book_version_id JOIN book b ON b.id=bv.book_id WHERE g.id=%s",
               generation_id)
    if g is None:
        return None
    titles, names = book_names(generation_id, str(g["book_id"]), g["title"] or "")
    try:
        doc, _ = _open_version(str(g["book_version_id"]))
    except Exception:  # noqa: BLE001 - dosya taşınmış/silinmiş: dizgi yok, eski kural
        return None
    with doc:
        headings = page_headings(doc, _page_lines, [*titles, *names])
    return chapters_from_pages(pages if pages is not None else source.read(generation_id), headings, titles, names)


def book_names(generation_id: str, book_id: str, title: str) -> tuple[list[str], list[str]]:
    """Kitabın adları (kayıt adı, künyenin TITLE iddiaları, CRM kayıt adının parçaları) ve imza adları (künyenin
    AUTHOR/ILLUSTRATOR iddiaları, CRM yazarları/çizerleri). Salt okuma; okunamazsa yalnız kayıt adı."""
    from . import db
    from .book_title import segments
    titles, names = [title], []
    try:
        for r in db.all_rows("SELECT subject, claim FROM claim WHERE generation_id=%s AND kind='METADATA'"
                             " AND subject IN ('TITLE','AUTHOR','ILLUSTRATOR')"
                             " AND status IN ('VERIFIED','EDITOR_APPROVED','EDITOR_CORRECTED')", generation_id):
            (titles if r["subject"] == "TITLE" else names).append(r["claim"] or "")
        crm = db.one("SELECT crm_title, authors, illustrators FROM book_crm_record WHERE book_id=%s", book_id) or {}
        titles += segments(crm.get("crm_title") or "")
        names += [*(crm.get("authors") or []), *(crm.get("illustrators") or [])]
    except Exception:  # noqa: BLE001 - künye/CRM okunamazsa kural kayıt adıyla sürer
        pass
    # «Ad Soyad, Ad Soyad» tek iddiada birden çok kişi
    names = [n.strip() for x in names for n in re.split(r"[,;/&]| ve ", x or "") if n.strip()]
    return [t for t in dict.fromkeys(titles) if t], list(dict.fromkeys(names))
