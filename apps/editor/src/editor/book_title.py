"""Kitap adı: hangi kaynaktan, nasıl yazılır (kullanıcı kararı 2026-10-03).

Arşiv kipinde okunan kitapların adı dosya adından geliyordu ve bozuktu: önde sıra numarası ya da sayfa aralığı
(«1- todişin bir günü», «04-13 Selam_K47_10»), küçük/büyük harf karışık, Türkçe harf yok («Mucitler icat oykuleri»),
kelimeler bitişik («meleklerbeniseviyor»). Kural, bütün kitaplar için tek ve kitaptan bağımsız:

Öncelik (üstteki her zaman kazanır, otomatik çözüm üsttekini ezmez):
  1. ``user``     — kişinin elle verdiği ad (yüklemede yazdığı). Hiçbir otomatik adım dokunmaz.
  2. ``crm``      — yayınevinin CRM kitap kaydı (kullanıcı kararı 2026-10-03: «CRM baz al, yoksa timas.com.tr»).
                    Eşlemeyi CRM bağlayıcısı yapar (``connectors/crm_covers.py``: ISBN, ad, bitişik ad, kayıt adının
                    ilk parçası, kısmi); sonuç ``ed.book_crm_record`` ya da — kayıt birden çok baskıya düşüp hepsinin
                    adı aynıysa — son CRM aramasının ``crm_title``'ı. Kısmi eşleşme «gözden geçir» işaretlenir.
  3. ``site``     — yayınevi sitesindeki ürün adı (``ed.cover_library``; eşleme ``recommend.match``: ISBN, yoksa
                    katlanmış ad birebir ve tek ürün; o da yoksa ürün adının ilk parçası). Dış istek yok.
  4. ``metadata`` — okumanın künyesindeki TITLE iddiası; YALNIZ dosya adıyla aynı kelimeleri taşıyorsa (harf
                    büyüklüğü, Türkçe harf ve boşluk farkı dışında). Künyede alt başlık/seri adı varsa dosya adına
                    uyan parça alınır. Künye dosya adından bambaşka bir şey diyorsa (yanlış sayfa okunmuş olabilir)
                    kullanılmaz; dosya adı kalır, «gözden geçir» işaretinde künye adayı yazılır.
  5. ``file``     — temizlenmiş dosya adı: kopya eki «(2)», ölçü «135x210», forma «19f», baskı numarası, dergi
                    künye kodu «_K43_6», sondaki dosya hâli sözcükleri (baskı, özalit, iç, son…) ve BAŞTAKİ sıra
                    numarası / sayfa aralığı / yıl («1-», «01_», «04-13 », «2020. ») atılır; alt çizgi ve tire boşluk
                    olur; harf büyüklüğü tek biçimse (hepsi küçük, hepsi büyük ya da yalnız ilk harf büyük) Türkçe
                    başlık yazımına çevrilir. Bitişik kelime ve eksik Türkçe harf TAHMİN EDİLMEZ (yanlış düzeltme
                    riski); bu yüzden dosya adından gelen her ad «gözden geçirilmeli» işaretlenir.

CRM ve site adı «Kitap Adı - Seri Adı 3 (Ciltli)» biçimindedir: kitabın adı ``record_name`` ile çıkarılır.

Kayıt: ``ed.book.title_source`` (yukarıdaki beş değer; NULL = bu kuraldan önceki kayıt), ``title_review`` (gözden
geçirme nedenleri; boş = gerek yok), ``title_file`` (adın türediği özgün dosya adı). Göç 032.

Ne zaman: yüklemede (portal tekli/toplu, arşiv içe aktarma) ad hemen belirlenir — o anda yalnız dosya adı ya da
kişinin yazdığı ad vardır. Okuma bitince (``finish_job`` SUCCEEDED → ``after_reading``) site ve künye ile yeniden
çözülür; bu aktivitenin içinde olduğu için Temporal geçmişi değişmez, ``patched`` bayrağı gerekmez. CRM bağlayıcısı
her gece bir kitabın kaydını yazınca da (``catalog.store_crm_lookup`` → ``refresh``) ad yeniden çözülür.

Tek seferlik düzeltme: ``python -m editor.book_title fix --all [--apply]`` (varsayılan kuru koşu; yalnız dosya
adından gelmiş adlara dokunur).
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import unicodedata
from pathlib import Path

USER, CRM, SITE, METADATA, FILE = "user", "crm", "site", "metadata", "file"
SOURCES = (USER, CRM, SITE, METADATA, FILE)
#: Daha yüksek sıra daha güvenilir: otomatik çözüm yalnız aynı ya da daha yüksek sıraya geçer.
RANK = {FILE: 1, METADATA: 2, SITE: 3, CRM: 4, USER: 5}

# ------------------------------------------------------------------ Türkçe harf büyüklüğü
_TR_CHARS = set("çğıöşüÇĞİÖŞÜâîûÂÎÛ")
#: Başlık içinde (ilk kelime ve iki nokta / tire sonrası dışında) küçük kalan bağlaç ve edatlar.
SMALL = frozenset({"ve", "ile", "veya", "yahut", "ya", "da", "de", "ki", "mi", "mı", "mu", "mü", "ama", "fakat"})
#: Kısaltmalar: katlanmış biçim → yazımı (noktasız yazılmışsa nokta eklenir).
ABBREV = {"hz": "Hz.", "dr": "Dr.", "prof": "Prof.", "doç": "Doç."}
_ROMAN = re.compile(r"^(?=[ivxlc]{2,}$)c{0,3}(xc|xl|l?x{0,3})(ix|iv|v?i{0,3})$", re.I)


def tr_lower(s: str, ascii_text: bool = False) -> str:
    """Türkçe küçük harf: I → ı, İ → i. `ascii_text`: metin Türkçe harf hiç taşımıyorsa (dosya adını Türkçe klavye
    kullanmadan yazan) büyük I, İ yerine yazılmış sayılır → i."""
    if ascii_text:
        return s.replace("İ", "i").lower()
    return s.replace("I", "ı").replace("İ", "i").lower()


def tr_upper(s: str) -> str:
    """Türkçe büyük harf: i → İ, ı → I."""
    return s.replace("i", "İ").replace("ı", "I").upper()


def _cap(word: str, ascii_text: bool) -> str:
    """Kelimenin ilk harfi büyük, gerisi küçük; kesme işaretinden sonraki ek küçük kalır («Todi'nin»)."""
    low = tr_lower(word, ascii_text)
    for i, ch in enumerate(low):
        if ch.isalpha():
            return low[:i] + tr_upper(ch) + low[i + 1:]
    return low


def casing(s: str) -> str:
    """Harf büyüklüğü biçimi: lower | upper | sentence (yalnız ilk harf büyük) | mixed (elle yazılmış) | none."""
    letters = [ch for ch in s if ch.isalpha()]
    if not letters:
        return "none"
    if all(not ch.isupper() for ch in letters):
        return "lower"
    # «I DÜNYA SAVAŞI ve ÖNCESİ»: küçük yazılmış bağlaçlar büyük harfli adı karışık yapmaz
    big = [ch for w in s.split() if tr_lower(w.strip(".,;:!?'’")) not in SMALL for ch in w if ch.isalpha()]
    if big and all(not ch.islower() for ch in big):
        return "upper"
    ups = [i for i, ch in enumerate(letters) if ch.isupper()]
    if ups == [0] and len(s.split()) >= 2:
        return "sentence"
    return "mixed"


def title_case(s: str, typed: bool = True) -> str:
    """Türkçe başlık yazımı. Yalnız harf büyüklüğü tek biçimse (hepsi küçük / hepsi büyük / yalnız ilk harf büyük)
    çevrilir; elle karışık yazılmış ad (Ela'nın Neşeli Günlüğü) olduğu gibi kalır. Bağlaçlar (ve, ile, ya da, mi…)
    küçük; ilk kelime ve iki nokta / tire sonrası büyük; kısaltma «Hz.»; Romen rakamı (II, IV) büyük.
    `typed`: metni bir kişi klavyeden yazdı (dosya adı) — Türkçe harf hiç yoksa büyük I, İ yerine yazılmış sayılır.
    Kitabın kendi künyesi (dizilmiş Türkçe metin) için False: «NOKTACIK» → «Noktacık»."""
    s = re.sub(r"\s+", " ", s or "").strip()
    if casing(s) not in ("lower", "upper", "sentence"):
        return s
    ascii_text = typed and not any(ch in _TR_CHARS for ch in s)
    out: list[str] = []
    start = True
    for tok in s.split(" "):
        m = re.match(r"^([^\w]*)(.*?)([^\w]*)$", tok)
        pre, core, post = m.groups() if m else ("", tok, "")
        low = tr_lower(core, ascii_text)
        if not core:
            w = tok
        elif low in ABBREV and (post.startswith(".") or not post):
            w = pre + ABBREV[low] + (post[1:] if post.startswith(".") else post)
        elif _ROMAN.match(core):
            w = pre + core.upper() + post
        elif not start and low in SMALL:
            w = pre + low + post
        elif any(ch.isdigit() for ch in core):
            w = pre + tr_lower(core, ascii_text) + post
        else:
            w = pre + "-".join(_cap(p, ascii_text) for p in core.split("-")) + post
        out.append(w)
        start = bool(tok) and (tok[-1] in ":–—" or tok in ("-", "–", "—"))
    return " ".join(out)


# ------------------------------------------------------------------ dosya adından
#: Dosya adının SONUNDA kitabı değil dosyanın hâlini anlatan sözcükler (katlanmış). Ortadaki «yeni», «son», «iç»
#: kitap adının parçası olabilir («Yeni Delhi», «Son Mektup»): yalnız sondan atılır.
TAIL_NOISE = frozenset({"baski", "baskii", "baskiii", "baskiconv", "sonbaski", "baskison", "baskiozalit", "icbaski",
                        "ozalit", "tashih", "kapak", "ic", "son", "convert", "conv", "renkli", "alm", "hazir", "yeni"})
#: Baştaki sıra numarası atılınca geriye yalnız bu kalırsa numara adın kendisidir («2. Kitap», «3. Cilt»).
VOLUME_WORDS = frozenset({"kitap", "cilt", "kisim", "bolum", "sayi", "seri"})
_FOLD = str.maketrans("çğıöşüâîûÇĞİÖŞÜÂÎÛ", "cgiosuaiuCGIOSUAIU")


def fold(s: str | None) -> str:
    """Karşılaştırma anahtarı: Türkçe harf ve büyüklük farkı yok, noktalama boşluk."""
    t = unicodedata.normalize("NFKC", s or "").translate(_FOLD).lower()
    t = "".join(ch for ch in unicodedata.normalize("NFKD", t) if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def key(s: str | None) -> str:
    """Boşluksuz anahtar («meleklerbeniseviyor» = «Melekler Beni Seviyor...»); «Hz.» = «Hazreti»."""
    words = ["hazreti" if w in ("hz", "hazret") else w for w in fold(s).split()]
    return "".join(words)


# Baştaki kalıplar (sırayla, en çok üç kez): sayfa aralığı «04-13 », «104-111 »; yıl + ayraç «2020. », «2020-»;
# sıra numarası + ayraç «1-», «01_», «10.», «3)»; sıfırla başlayan ya da iki haneli sayı + boşluk «020 », «10 ».
_PREFIXES = (
    ("page_range", re.compile(r"^\d{1,3}\s*-\s*\d{1,3}\s+(?=\S)")),
    ("year", re.compile(r"^(?:19|20)\d{2}\s*[-_.)]\s*(?=[^\W\d_])")),
    ("number", re.compile(r"^\d{1,3}\s*[-_.)]+\s*(?=[^\W\d_]|\d{1,3}\.?\s)")),          # «4-1. Yok Artık»
    ("number_space", re.compile(r"^(?:0\d{1,2}|\d{1,2})\s+(?=[^\W\d_])")),
)


def strip_prefix(s: str) -> tuple[str, list[str]]:
    """Baştaki sıra numarası / sayfa aralığı / yıl (yalnız BAŞTAKİ; ortadaki yıl adın parçası olabilir).
    Döner: (kalan, atılan kalıpların adları). Geriye yalnız «kitap/cilt» kalırsa numara adın kendisidir."""
    removed: list[str] = []
    for _ in range(3):
        for name, rx in _PREFIXES:
            m = rx.match(s)
            if m:
                rest = s[m.end():]
                if fold(rest).replace(" ", "") in VOLUME_WORDS:
                    # «2.kitap» → «2. Kitap»: numara adın kendisi
                    num = re.match(r"\d+", s).group(0)
                    return f"{num}. {rest.strip()}" if name in ("number", "year") else s, removed
                s, removed = rest, removed + [name]
                break
        else:
            break
    return s, removed


def clean_stem(name: str) -> str:
    """Dosya adından ad gövdesi, harf büyüklüğüne dokunmadan (eşleme ve arşiv kesik parça anahtarı da kullanır)."""
    s = unicodedata.normalize("NFC", Path(name or "").stem if (name or "").lower().endswith(".pdf") else (name or ""))
    s = re.sub(r"\(\d+\)", " ", s)                                                # kopya eki
    s = re.sub(r"\d+([.,]\d+)?\s*[xX]\s*\d+([.,]\d+)?(\s*cm\b)?", " ", s)         # ölçü
    s = re.sub(r"\b\d+([.,]\d+)?f+\b", " ", s, flags=re.I)                         # forma «19f», «13,5F»
    s = re.sub(r"(?<=[a-zçğıöşü])BASK[IİI]+\b", " ", s)                          # bitişik «…misinBASKI»
    s = re.sub(r"(?<!\d)\d{1,2}\s*\.?\s*bask\S*", " ", s, flags=re.I)           # baskı numarası («3. Baskı»)
    s = re.sub(r"(?:^|[\s_-])K\d{2,3}(?:[\s_-]+\d{1,3}\s*\+?\s*R?)?[\s._]*$", " ", s)  # dergi künye kodu «_K43_6»
    s = re.sub(r"\s+", " ", s).strip(" ._-")
    return s


def from_file(name: str) -> dict:
    """Temizlenmiş dosya adı ve gözden geçirme nedenleri. {'title', 'review': [...], 'raw': özgün ad}."""
    raw = (name or "").strip()
    s = clean_stem(raw)
    s, removed = strip_prefix(s)
    # tire/alt çizgi boşluk; ama « - » ayraç olarak kalır (seri adı - kitap adı)
    s = re.sub(r"\s+-\s+", " \x00 ", s)
    s = re.sub(r"[_-]+", " ", s).replace("\x00", "-")
    words = s.split()
    while len(words) > 1 and fold(words[-1]).replace(" ", "") in TAIL_NOISE:
        words.pop()
    s = " ".join(words).strip(" .-")
    reasons = ["dosya adından"]
    if not s:
        s = re.sub(r"\s+", " ", Path(raw).stem).strip() or "Adsız kitap"
    if removed:
        reasons.append("baştaki numara atıldı")
    if re.search(r"\d", s):
        reasons.append("adda sayı ya da yıl var")
    shape = casing(s)
    titled = title_case(s)
    if titled != s:
        reasons.append("harf büyüklüğü düzeltildi")
    if not any(ch in _TR_CHARS for ch in titled):
        reasons.append("Türkçe harf yok")
    if any(len(w) >= 14 and w.isalpha() for w in titled.split()) or (len(titled.split()) == 1 and len(titled) >= 10):
        reasons.append("kelimeler bitişik olabilir")
    if shape == "none":
        reasons.append("ad okunamadı")
    return {"title": titled[:300], "review": reasons, "raw": raw[:300]}


# ------------------------------------------------------------------ künye adı
def _windows(words: list[str]) -> list[str]:
    """Künye adının art arda kelime parçaları, uzundan kısaya (seri adı / alt başlık ayıklanır)."""
    n = len(words)
    return [" ".join(words[i:j]) for size in range(n, 0, -1) for i in range(0, n - size + 1) for j in (i + size,)]


def metadata_fit(claim: str, file_title: str) -> str | None:
    """Künyedeki adın dosya adıyla örtüşen parçası (yazımıyla) ya da None. Örtüşme: boşluksuz anahtar birebir aynı
    («NOKTACIK» = «noktacik», «Melekler Beni Seviyor...» = «meleklerbeniseviyor»). Künye «BAŞLIK Alt başlık»
    biçimindeyse büyük harfli baş kısım da denenir."""
    want = key(file_title)
    if not want or not claim:
        return None
    text = re.sub(r"\s+", " ", claim).strip().strip(".…").strip()
    words = text.split(" ")
    if len(words) > 24:
        return None
    for part in _windows(words):
        if key(part) == want:
            return title_case(part.strip(" .,;:-–—…"), typed=False)
    return None


#: Ürün adının sonundaki cilt/kapak biçimi («(Ciltli)», «(Fleksi Cilt)», «(Karton Kapak)») kitabın adı değildir.
_BINDING = re.compile(r"\s*\((?=[^()]*\b(?:cilt\w*|kapak|karton|fleksi)\b)[^()]*\)\s*$", re.I)


def site_name(title: str) -> str:
    """Yayınevi sitesindeki ürün adı, cilt/kapak biçimi eki atılmış."""
    t = re.sub(r"\s+", " ", title or "").strip()
    return _BINDING.sub("", t).strip() or t


#: Kayıt adının sonundaki not: «(Ciltli)», «(Önceki Ebat)», «(İngilizce)», «(Pencereli Kitap)», «(10. Kitap)»,
#: «(Ön Sipariş)». Yaş/sınıf bilgisi («(4 Yaş)») adın parçası sayılır, kalır.
_NOTE = re.compile(r"\s*\((?![^()]*\b(?:ya[sş]|s[ıi]n[ıi]f)\b)[^()]*\)\s*$", re.I)
_SEGMENT = re.compile(r"\s+[-–—]\s+")


def segments(title: str) -> list[str]:
    """Kayıt adının « - » parçaları, sondaki notlar atılmış: «Gözlerini Kocaman Aç - Duyularla Rabbimi Tanıyorum 3
    (Pencereli Kitap)» → ['Gözlerini Kocaman Aç', 'Duyularla Rabbimi Tanıyorum 3']. İki noktalı alt başlık
    («Mülk ve Hukuk: Osmanlı…») parçalanmaz, adın kendisidir."""
    t = re.sub(r"\s+", " ", title or "").strip()
    while True:
        u = _NOTE.sub("", t).strip()
        if u == t or not u:
            break
        t = u
    return [p.strip() for p in _SEGMENT.split(t) if p.strip()]


def _small_words(t: str) -> str:
    """Elle yazılmış kayıt adında ortadaki bağlaç küçük harf olur («Piri Reis Ve Acayip Haritası» → «… ve …»); ilk
    kelime ve iki nokta sonrası olduğu gibi kalır."""
    words = t.split(" ")
    for i in range(1, len(words)):
        w = words[i]
        if w and tr_lower(w) in SMALL and w[:1].isupper() and not words[i - 1].endswith(":") \
                and not (len(w) > 1 and w.isupper() and casing(t) == "upper"):
            words[i] = tr_lower(w)
    return " ".join(words)


def record_name(title: str, file_title: str = "") -> str:
    """Yayınevi kaydının (CRM ya da site) adından kitabın kendi adı. «Kitap Adı - Seri Adı 3 (Ciltli)» biçiminde
    kitabın adı dosya adına uyan parçadır; uyan yoksa dosya adıyla başlayan parça (dosya adı kısaltılmış: «Rüzgârın
    Ardından» → «Rüzgarın Ardından: Ayine-i Zülcenaheyn»); dosya adı parçaları aşıyorsa kaydın tamamı (seri adı önde:
    «arsen lupen kibar hirsiz» → «Arsen Lüpen - Kibar Hırsız»); hiçbiri değilse ilk parça (seri adı « - »'den sonra).
    Harf büyüklüğü tek biçimse Türkçe başlık yazımı; bağlaçlar küçük."""
    parts = segments(title) or [re.sub(r"\s+", " ", title or "").strip()]
    want = key(file_title)
    whole = " - ".join(parts)
    pick = next((p for p in parts if want and key(p) == want), None) \
        or next((p for p in parts if want and key(p).startswith(want)), None) \
        or (whole if want and key(whole).startswith(want) else None) or parts[0]
    # dosya adındaki cilt numarası seçilen parçada yoksa ama kayıt adında varsa kitabın adı kaydın tamamıdır
    # («dangerdan2» → «Danger Dan - Milli Marşı Kurtarıyor 2», «Danger Dan» değil)
    nums = set(re.findall(r"\d+", file_title or ""))
    if nums - set(re.findall(r"\d+", pick)) and nums <= set(re.findall(r"\d+", whole)):
        pick = whole
    pick = pick.strip(" .,;-–—")
    return _small_words(title_case(pick, typed=False))[:300]


# ------------------------------------------------------------------ karar
def resolve(file_name: str = "", user: str | None = None, site: dict | None = None,
            metadata: list[str] | None = None, crm: dict | None = None) -> dict:
    """Kitabın adı. `crm`: CRM kaydı ({'title': kayıt adı, 'by': bağlayıcının eşleme yolu}), `site`:
    recommend.match sonucu ({'row': {'title'…}, 'by': 'ISBN'|'TITLE'|'TITLE_AUTHOR'|'SEGMENT'}), `metadata`:
    künyedeki TITLE iddiaları (doğrulanmış). Döner {'title', 'source', 'review': [...], 'raw'}."""
    if user and user.strip():
        return {"title": re.sub(r"\s+", " ", user).strip()[:300], "source": USER, "review": [], "raw": file_name}
    f = from_file(file_name)
    if crm and crm.get("by") == "SAME_NAME" and \
            set(re.findall(r"\d+", f["title"])) - set(re.findall(r"\d+", crm.get("title") or "")):
        # birden çok kaydın ortak adı dosya adındaki cilt numarasını taşımıyorsa kitabın adı değildir («Bilimbaz 2»
        # dosyası «Bilimbaz - …» kayıtlarının ortak adı «Bilimbaz» olmaz)
        crm = None
    if crm and (crm.get("title") or "").strip():
        # kayıt adının içinden kelime seçilmez, bütün parça alınır: «El Cezeri ve Bakır Taç» «cezeri»ye kısalmaz
        by = crm.get("by") or ""
        review = ["CRM'de kısmi ad eşleşmesi: " + crm["title"].strip()[:120]] \
            if by.startswith(("PARTIAL", "PREFIX", "SERIES_NO")) else []
        return {"title": record_name(crm["title"], f["title"]), "source": CRM, "review": review, "raw": f["raw"],
                "by": by or None}
    if site and (site.get("row") or {}).get("title"):
        return {"title": record_name(site["row"]["title"], f["title"]), "source": SITE, "review": [],
                "raw": f["raw"], "by": site.get("by")}
    others = []
    for claim in metadata or []:
        fit = metadata_fit(claim, f["title"])
        if fit:
            return {"title": fit[:300], "source": METADATA, "review": [], "raw": f["raw"]}
        others.append(claim)
    review = list(f["review"])
    if others:
        review.append("künyede farklı ad: " + re.sub(r"\s+", " ", others[0]).strip()[:120])
    return {"title": f["title"], "source": FILE, "review": review, "raw": f["raw"]}


def may_replace(current_source: str | None, new_source: str) -> bool:
    """Otomatik çözüm kişinin adını hiç ezmez; daha güvenilir kaynaktan geleni daha zayıfla değiştirmez.
    NULL (kuraldan önceki kayıt) yalnız dosya adından geldiği bilindiğinde çağrılır."""
    if current_source == USER:
        return False
    return RANK.get(new_source, 0) >= RANK.get(current_source or FILE, 0)


# ------------------------------------------------------------------ veritabanı
_COLS: dict = {"ok": False}


def has_columns(c) -> bool:
    """Göç 032 uygulanmış mı (kart servisi göçü koşturan süreçten önce kurulabilir). Evet cevabı saklanır."""
    if not _COLS["ok"]:
        _COLS["ok"] = c.execute(
            "SELECT count(*) AS n FROM information_schema.columns WHERE table_schema='ed' AND table_name='book'"
            " AND column_name IN ('title_source','title_review','title_file')").fetchone()["n"] == 3
    return bool(_COLS["ok"])


def legacy_file_derived(title: str, archive_path: str | None, requested_by: str | None) -> str | None:
    """Kuraldan önce açılmış kaydın adı dosya adından mı geldi? Geldiyse özgün dosya adı (ya da ad) döner.
    Arşiv toplu kuyruğu: ad, dosya yolunun eski temizliğine (archive.clean_title) eşitse. Portal: kişinin
    yazdığı ad bilinmiyor; ad dosya adı biçimindeyse (hepsi küçük harf, baştaki numara, alt çizgi) dosyadan sayılır.
    Elle karışık harfle yazılmış ad kişinin adı sayılır, dokunulmaz."""
    from . import archive
    if archive_path:
        return archive_path if title == archive.clean_title(archive_path) else None
    if (requested_by or "").startswith(archive.PREFIX):
        return None
    t = title or ""
    if "_" in t or re.match(r"^\d{1,3}[\s._-]", t) or casing(t) == "lower":
        return t
    return None


def evidence(c, book_id: str) -> dict:
    """Kitabın ad kanıtları (salt okuma): son okunmuş neslin doğrulanmış künye TITLE / ISBN / AUTHOR iddiaları,
    CRM kaydının adı / ISBN'i / yazarları. CRM kaydı yoksa ama son CRM araması birden çok baskıya düşüp hepsinin adı
    aynı çıktıysa (bağlayıcı o adı ``crm_title``'a yazar) ad oradan gelir."""
    rows = c.execute(
        "SELECT m.subject, m.claim FROM ed.claim m WHERE m.generation_id = ("
        "  SELECT g.id FROM ed.generation g JOIN ed.book_version bv ON bv.id=g.book_version_id"
        "  JOIN ed.analysis_job j ON j.id=g.job_id WHERE bv.book_id=%s AND j.status='SUCCEEDED'"
        "  ORDER BY g.created_at DESC LIMIT 1)"
        " AND m.kind='METADATA' AND m.subject IN ('TITLE','ISBN','AUTHOR')"
        " AND m.status IN ('VERIFIED','EDITOR_APPROVED','EDITOR_CORRECTED') ORDER BY m.subject, m.claim",
        (book_id,)).fetchall()
    crm = c.execute("SELECT isbn, authors, crm_title, matched_by FROM ed.book_crm_record WHERE book_id=%s",
                    (book_id,)).fetchone() or {}
    crm_name = {"title": crm["crm_title"], "by": crm["matched_by"]} if crm.get("crm_title") else None
    if crm_name is None:
        last = c.execute("SELECT outcome, crm_title FROM ed.cover_lookup WHERE book_id=%s AND source='CRM'"
                         " ORDER BY created_at DESC LIMIT 1", (book_id,)).fetchone()
        if last and last["outcome"] == "AMBIGUOUS" and last["crm_title"]:
            crm_name = {"title": last["crm_title"], "by": "SAME_NAME"}
    return {"crm": crm_name, "titles": [r["claim"] for r in rows if r["subject"] == "TITLE"],
            "isbns": [x for x in [crm.get("isbn"), *[r["claim"] for r in rows if r["subject"] == "ISBN"]] if x],
            "authors": [*(crm.get("authors") or []), *[r["claim"] for r in rows if r["subject"] == "AUTHOR"]]}


def decide(row: dict, ev: dict, site_ix) -> dict | None:
    """Bir kitabın yeni ad kararı ya da None (dokunulmaz: kişinin adı, dosyadan gelmediği bilinmeyen eski kayıt).
    `row`: book satırı (id, title, title_source, title_file, archive_path, requested_by)."""
    from . import recommend
    src = row.get("title_source")
    if src == USER:
        return None
    raw = row.get("title_file")
    if src is None:
        raw = legacy_file_derived(row["title"], row.get("archive_path"), row.get("requested_by"))
        if raw is None:
            return None
    raw = raw or row["title"]
    f = from_file(raw)
    names = [f["title"], clean_stem(Path(raw).name), *ev.get("titles", [])]
    m = recommend.match(site_ix, ev.get("isbns", []), [n for n in names if n], ev.get("authors", []))
    # adla eşleşme ancak ürün adı dosya adının kendisiyse kabul (künyedeki başka adla eşleşen ürün başka kitaptır)
    if m and m["by"] != "ISBN" and key(m["row"]["title"]) not in {key(f["title"]), key(clean_stem(raw))}:
        m = None
    if m is None:
        m = site_by_segment(site_ix, [f["title"], clean_stem(raw)])
    res = resolve(raw, site=m, metadata=ev.get("titles"), crm=ev.get("crm"))
    if not may_replace(src, res["source"]):
        return None
    return res


def site_by_segment(site_ix, names: list[str]) -> dict | None:
    """Sitede adla eşleşme yoksa: ürün adının İLK parçası dosya adına eşit («Emircan Tasarrufu Öğreniyor - Yaşasın
    Okuyorum» = «emircantasarrufuogreniyor»). Birden çok ürün düşerse (Ciltli, İngilizce baskı) adları aynı olduğu
    için ad yine bellidir; yalnız ad kullanılır, ürünün kategorisi değil."""
    ix = getattr(site_ix, "_first_segment", None)
    if ix is None:
        ix = {}
        for r in getattr(site_ix, "rows", []) or []:
            parts = segments(site_name(r.get("title") or ""))
            if parts and key(parts[0]):
                ix.setdefault(key(parts[0]), []).append(r)
        try:
            site_ix._first_segment = ix
        except AttributeError:
            pass
    for n in names:
        rows = ix.get(key(n)) if key(n) else None
        if rows:
            best = max(rows, key=lambda r: (r.get("sales") or 0, str(r.get("id"))))
            return {"row": {"title": segments(site_name(best["title"]))[0]}, "by": "SEGMENT"}
    return None


def apply(c, book_id: str, res: dict) -> bool:
    """Kararı yazar; kişinin adı (title_source='user') koşulla korunur (yarış: aynı anda elle ad verilirse)."""
    got = c.execute(
        "UPDATE ed.book SET title=%s, title_source=%s, title_review=%s, title_file=coalesce(title_file, %s)"
        " WHERE id=%s AND coalesce(title_source, '') <> 'user' RETURNING id",
        (res["title"], res["source"], res["review"], res.get("raw") or None, book_id)).fetchone()
    return got is not None


_BOOKS = ("SELECT b.id, b.title, {cols}, (SELECT bv.pdf_meta->>'archive_path' FROM ed.book_version bv"
          " WHERE bv.book_id=b.id ORDER BY bv.created_at LIMIT 1) AS archive_path,"
          " (SELECT j.requested_by FROM ed.analysis_job j JOIN ed.book_version bv ON bv.id=j.book_version_id"
          " WHERE bv.book_id=b.id ORDER BY j.created_at LIMIT 1) AS requested_by FROM ed.book b")


def books(c, book_id: str | None = None) -> list[dict]:
    cols = ("b.title_source, b.title_review, b.title_file" if has_columns(c)
            else "NULL::text AS title_source, '{}'::text[] AS title_review, NULL::text AS title_file")
    sql = _BOOKS.format(cols=cols) + (" WHERE b.id=%s" if book_id else "") + " ORDER BY b.title, b.id"
    return c.execute(sql, (book_id,) if book_id else ()).fetchall()


def set_on_intake(c, book_id: str, given: str | None, file_name: str) -> None:
    """Yüklemede (portal tekli/toplu, arşiv): kayıt yeniyse adın kaynağı yazılır; kişi ad verdiyse kişinin adı
    otomatik addan üstündür (aynı içerik daha önce dosya adıyla açılmışsa kişinin adına geçer)."""
    if not has_columns(c):
        return
    if given and given.strip():
        c.execute("UPDATE ed.book SET title=%s, title_source='user', title_review='{}',"
                  " title_file=coalesce(title_file, %s) WHERE id=%s AND coalesce(title_source,'') <> 'user'",
                  (re.sub(r"\s+", " ", given).strip()[:300], file_name or None, book_id))
        return
    f = from_file(file_name)
    c.execute("UPDATE ed.book SET title_source='file', title_review=%s, title_file=%s WHERE id=%s"
              " AND title_source IS NULL", (f["review"], f["raw"] or None, book_id))


def after_reading(generation_id: str) -> dict | None:
    """Okuma bitince (finish_job SUCCEEDED): CRM, site ve künye ile ad yeniden çözülür. Kişinin adına dokunmaz;
    hata okumayı düşürmez (çağıran yakalar)."""
    from . import db
    with db.tx() as c:
        bid = c.execute("SELECT bv.book_id FROM ed.generation g JOIN ed.book_version bv ON bv.id=g.book_version_id"
                        " WHERE g.id=%s", (generation_id,)).fetchone()
    return refresh(str(bid["book_id"])) if bid else None


def refresh(book_id: str) -> dict | None:
    """Bir kitabın adını eldeki kanıtla yeniden çözer (okuma sonu, CRM bağlayıcısının kaydı). Değişiklik yoksa
    None."""
    from . import db, recommend
    with db.tx() as c:
        if not has_columns(c):
            return None
        rows = books(c, book_id)
        if not rows:
            return None
        row = rows[0]
        res = decide(row, evidence(c, str(row["id"])), recommend.site_index())
        if res is None or (res["title"] == row["title"] and res["source"] == row.get("title_source")
                           and list(res["review"]) == list(row.get("title_review") or [])):
            return None
        apply(c, str(row["id"]), res)
        return {"book_id": str(row["id"]), "old": row["title"], **res}


# ------------------------------------------------------------------ komut
def plan(c, site_ix) -> list[dict]:
    """Bütün kitaplar için karar (salt okuma): değişecek ya da işareti değişecek olanlar."""
    out = []
    for row in books(c):
        res = decide(row, evidence(c, str(row["id"])), site_ix)
        if res is None:
            continue
        same = (res["title"] == row["title"] and res["source"] == row.get("title_source")
                and list(res["review"]) == list(row.get("title_review") or []))
        if not same:
            out.append({"book_id": str(row["id"]), "old": row["title"], "new": res["title"], "source": res["source"],
                        "by": res.get("by"), "review": res["review"], "file": res.get("raw")})
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m editor.book_title")
    sub = ap.add_subparsers(dest="cmd", required=True)
    f = sub.add_parser("fix", help="dosya adından gelmiş kitap adlarını düzelt (varsayılan kuru koşu)")
    f.add_argument("--all", action="store_true", required=True, help="bütün kitaplar")
    f.add_argument("--apply", action="store_true", help="gerçekten yaz")
    f.add_argument("--json", action="store_true", help="satır başına JSON")
    t = sub.add_parser("try", help="tek dosya adını çöz (veritabanına bakmaz)")
    t.add_argument("name", nargs="+")
    a = ap.parse_args(argv)
    if a.cmd == "try":
        for n in a.name:
            print(json.dumps(from_file(n), ensure_ascii=False))
        return 0
    from . import db, recommend
    with db.tx() as c:
        if not a.apply:
            c.execute("SET TRANSACTION READ ONLY")
        elif not has_columns(c):
            print("Göç 032 uygulanmamış: önce `python -m editor.foundation migrate`.", file=sys.stderr)
            return 2
        items = plan(c, recommend.SiteIndex(recommend.site_rows()))
        for it in items:
            if a.json:
                print(json.dumps(it, ensure_ascii=False), flush=True)
            else:
                mark = "  [gözden geçir: " + "; ".join(it["review"]) + "]" if it["review"] else ""
                print(f"{it['old']!r} → {it['new']!r} ({it['source']}{'/' + it['by'] if it.get('by') else ''}){mark}")
        if a.apply:
            n = sum(apply(c, it["book_id"], {"title": it["new"], "source": it["source"], "review": it["review"],
                                             "raw": it["file"]}) for it in items)
            print(f"{n} kitabın adı yazıldı.", file=sys.stderr)
        else:
            by = {}
            for it in items:
                by[it["source"]] = by.get(it["source"], 0) + 1
            print(f"Kuru koşu: {len(items)} kitap değişirdi {by}; "
                  f"{sum(1 for it in items if it['review'])} kitap «gözden geçir» işaretli. Hiçbir şey yazılmadı.",
                  file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
