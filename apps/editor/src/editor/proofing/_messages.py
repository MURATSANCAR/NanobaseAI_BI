"""Son okuma bulgu metinleri — TEK YER.

Bulguyu okuyan editör ve yazardır; teknik bilgisi yoktur. Her bulgu türü aynı kalıpla anlatılır:

    ne sorun (sade cümle) + nerede (sayfa, satır, alıntı) + neden önemli (yarım cümle)
    + ne yapılabilir (somut öneri)

Ana metinde teknik terim, kısaltma, standart adı, renk kodu, oran, ölçü birimi kısaltması yoktur. Sayısal
ayrıntı gerekiyorsa ayrı, küçük bir «ayrıntı» alanına gider (ekranda katlanır, Word yorumunun sonunda parantez
içinde tek satır) ve orada da sade karşılığıyla yazılır («okunurluk oranı 2,4; en az 4,5 olmalı»). Sayılar
Türkçe yazılır (2,4 · 27.748), renkler adıyla («açık pembe»).

Metin bulgunun KAYITLI alanlarından (`details`, `quote`, `page`, `severity`, ham `suggestion`) üretilir; bu
yüzden aynı işlev hem denetimde (kaydedilen `message`) hem rapor okunurken (ekran, Word) çalışır ve eski
raporlar da yeni dille görünür. Veritabanındaki eski metin değiştirilmez. Eski bir bulgunun `details`'i bir
alanı taşımıyorsa, alan eski metnin kendi kalıbından okunur (`_old_fields`); o da yoksa kayıtlı metin olduğu
gibi gösterilir ve eksik alan adı `missing`'de döner.

Bu modül hiçbir denetim modülünü yüklemez (kart servisi ağır bağımlılıkları çekmez); denetimler bunu çağırır.
Kitaba özel hiçbir ifade yoktur. Bulgunun kimliği ve parmak izi bu metne dayanmaz: tür anahtarı `kind_of`.
"""

from __future__ import annotations

import colorsys
import re

# ------------------------------------------------------------------ önem düzeyi
SEVERITY_WORD = {"ERROR": "hata", "WARN": "uyarı", "INFO": "bilgi"}              # ekranda
SEVERITY_LEAD = {"ERROR": "Mutlaka düzeltin", "WARN": "Bakmanız önerilir", "INFO": "Bilginize"}   # Word yorumu


# ------------------------------------------------------------------ biçim yardımcıları
_SWAP = str.maketrans(",.", ".,")


def num(x, nd: int = 1) -> str:
    """Türkçe sayı: 2.4 → «2,4», 27748 → «27.748», 19.0 → «19», 0.25 (nd=2) → «0,25»."""
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    s = f"{v:,.{nd}f}".translate(_SWAP)
    if "," in s:
        s = s.rstrip("0").rstrip(",")
    return s


def pct(share, nd: int = 0) -> str:
    """0.099 → «%10»."""
    return "%" + num(round(float(share) * 100, nd), nd)


def pages_txt(pages, most: int = 8) -> str:
    """[24, 42, 126] → «s. 24, 42 ve 126»; çoksa «… ve 5 sayfa daha»."""
    ps = sorted({int(p) for p in pages or [] if p is not None})
    if not ps:
        return ""
    if len(ps) == 1:
        return f"s. {ps[0]}"
    if len(ps) > most:
        return "s. " + ", ".join(map(str, ps[:most])) + f" ve {len(ps) - most} sayfa daha"
    return "s. " + ", ".join(map(str, ps[:-1])) + f" ve {ps[-1]}"


def clip(s, n: int = 90) -> str:
    """Uzun alıntıyı sözcük sınırında kısaltır."""
    s = " ".join(str(s or "").split())
    if len(s) <= n:
        return s
    cut = s[:n].rsplit(" ", 1)[0]
    return (cut if len(cut) > n // 2 else s[:n]) + "…"


def q(s, n: int = 90) -> str:
    """«alıntı»"""
    return f"«{clip(s, n)}»"


def cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def _sentence(*parts: str | None) -> str:
    """Parçaları cümle olarak birleştirir: boşları atar, her parça nokta ile biter."""
    out = []
    for p in parts:
        p = (p or "").strip()
        if not p:
            continue
        out.append(p if p[-1] in ".!?…" else p + ".")
    return " ".join(out)


# ------------------------------------------------------------------ renk adı
_GRAYS = ((0.93, "beyaz"), (0.72, "açık gri"), (0.42, "gri"), (0.16, "koyu gri"), (-1, "siyah"))
# (ton başlangıcı derece, ad); sıra önemli
_HUES = ((0, "kırmızı"), (12, "turuncu"), (42, "sarı"), (68, "yeşil"), (162, "turkuaz"), (190, "mavi"),
         (256, "mor"), (292, "pembe"), (346, "kırmızı"))


def color_name(hex_code: str) -> str:
    """Renk kodu → en yakın Türkçe renk adı (genel eşleme; kitaba özel değil). «#f38aa5» → «açık pembe»."""
    h = str(hex_code or "").lstrip("#")
    if not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        return "renkli"
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    hue, light, sat = colorsys.rgb_to_hls(r, g, b)
    if sat < 0.18 or max(r, g, b) - min(r, g, b) < 0.08:
        return next(name for lim, name in _GRAYS if light > lim)
    deg = hue * 360
    name = next(n for start, n in reversed(_HUES) if deg >= start)
    if name == "turuncu" and light < 0.36:
        return "kahverengi"
    if name == "sarı" and light < 0.32:
        return "koyu sarı"
    if name == "mavi" and light < 0.26:
        return "lacivert"
    if name == "kırmızı" and light > 0.74:
        name = "pembe"
    if light > 0.72:
        return "açık " + name
    if light < 0.28:
        return "koyu " + name
    return name


def _ground(lum) -> str:
    """Zeminin göreli parlaklığından (0 koyu … 1 açık) sade ad."""
    try:
        v = float(lum)
    except (TypeError, ValueError):
        return "zeminde"
    if v >= 0.9:
        return "beyaz zeminde"
    if v >= 0.4:
        return "açık renkli zeminde"
    if v >= 0.06:
        return "koyu renkli zeminde"
    return "siyah zeminde"


# ------------------------------------------------------------------ sade sözlükler
SIDE = {"top": "üst", "bottom": "alt", "gutter": "cilt tarafındaki", "outer": "dış"}
ROLE = {"AUTHOR": "yazar", "ILLUSTRATOR": "çizer", "TRANSLATOR": "çevirmen", "EDITOR": "editör",
        "PROJECT_EDITOR": "proje editörü", "DIRECTOR": "yayın yönetmeni"}
ATTRIBUTE = {"SAC_RENGI": "saç rengi", "GOZ_RENGI": "göz rengi", "TEN_KURK_RENGI": "ten, kürk ya da tüy rengi",
             "GOZLUK": "gözlük", "SAPKA": "şapka", "UST_GIYSI_RENGI": "üst giysisinin rengi",
             "ALT_GIYSI_RENGI": "alt giysisinin rengi", "ESYA": "taşıdığı eşya"}
STABLE_ATTRIBUTES = {"SAC_RENGI", "GOZ_RENGI", "TEN_KURK_RENGI", "GOZLUK"}
VALUE = {"SIYAH": "siyah", "BEYAZ": "beyaz", "GRI": "gri", "KAHVERENGI": "kahverengi", "SARI": "sarı",
         "TURUNCU": "turuncu", "KIRMIZI": "kırmızı", "PEMBE": "pembe", "MOR": "mor", "MAVI": "mavi",
         "YESIL": "yeşil", "BEJ": "bej", "COK_RENKLI": "çok renkli", "DIGER": "başka", "YOK": "yok",
         "BELIRSIZ": "belirsiz", "KIZIL": "kızıl", "GRI_BEYAZ": "kır ya da beyaz", "VAR": "var",
         "CANTA": "çanta", "SIRT_CANTASI": "sırt çantası", "SEMSIYE": "şemsiye", "KITAP": "kitap", "TOP": "top",
         "OYUNCAK": "oyuncak", "BASTON": "baston", "ASA": "asa", "CICEK": "çiçek", "YIYECEK": "yiyecek",
         "ALET": "alet", "IC": "içeride", "DIS": "dışarıda", "GUNDUZ": "gündüz", "GECE": "gece",
         "GUNESLI": "güneşli", "YAGMURLU": "yağmurlu", "KARLI": "karlı"}
ITEM_STATE = {"YANINDA": "yanında", "YOK": "yanında değil", "BIRAKTI": "bırakıyor", "KAYBOLDU": "kaybediyor",
              "KIRILDI": "kırılıyor", "BULDU": "buluyor", "TAMIR_EDILDI": "tamir ediliyor"}
PLACE_ASPECT = {"KONUM": "bulunduğu yer", "DUZEN": "içindeki düzen", "KAPI_YONU": "kapının yeri",
                "PENCERE_YONU": "pencerenin yeri", "KAT": "katı", "IC_DIS": "içeride mi dışarıda mı olduğu",
                "ISIK": "gündüz mü gece mi olduğu", "HAVA": "havası"}
TIME_KIND = {"GUN_VAKTI": "günün saati", "MEVSIM": "mevsim", "YAS": "yaş", "TARIH": "yaş ya da tarih"}
CONTRADICTION_KIND = {"ZAMAN": "zaman sırası", "KARAKTER": "karakter bilgisi", "YER": "yer",
                      "NESNE": "bir nesnenin durumu", "SAYI": "sayı"}
ADDRESS = {"AD": "adıyla", "AKRABALIK": "akrabalık sözüyle", "SAYGI": "saygı sözüyle", "LAKAP": "takma adıyla"}
BEING = {"HUMAN_CHILD": "çocuk", "HUMAN_ADULT": "yetişkin", "ANIMAL": "hayvan", "ROBOT_OR_MACHINE": "robot ya da makine",
         "FANTASY_CREATURE": "masal yaratığı", "OTHER": "başka bir varlık", "UNKNOWN": "belirsiz"}
SEX = {"MALE": "erkek", "FEMALE": "kadın ya da kız", "UNKNOWN": "belirsiz"}
AGE_GROUP = {"CHILD": "çocuk", "TEEN": "genç", "ADULT": "yetişkin", "ELDERLY": "yaşlı", "UNKNOWN": "belirsiz"}
SENSITIVE = {"VIOLENCE": "şiddet", "FEAR": "yoğun korku", "UNSAFE_IMITABLE": "çocuğun taklit edebileceği tehlikeli bir davranış",
             "SUBSTANCE": "alkol, sigara ya da uyuşturucu", "DEATH_GRIEF": "ölüm, yas ya da ağır hastalık",
             "INSULT_DISCRIMINATION": "aşağılama ya da ayrımcılık", "SEXUAL": "cinsellik"}
STYLE_MARK = {"kesme_işareti": "kesme işareti", "üç_nokta": "üç nokta", "tırnak": "tırnak işareti",
              "konuşma_çizgisi": "konuşma çizgisi"}
MONTHS = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık")


def value_tr(code) -> str:
    c = str(code or "")
    return VALUE.get(c.upper(), c.replace("_", " ").lower())


class Missing(KeyError):
    """Bulguda metni kurmak için gereken alan yok."""


def need(d: dict, *keys):
    """d'den alanlar; biri yoksa Missing (eksik alanın adıyla)."""
    out = []
    for k in keys:
        if d.get(k) in (None, "", [], {}):
            raise Missing(k)
        out.append(d[k])
    return out[0] if len(out) == 1 else out


# ================================================================== tür anahtarı
def _imprint_issue(f: dict, d: dict) -> str:
    """Künye bulgusunun türü: yeni koşularda details.issue; eskilerde alanlardan ve eski metnin başından."""
    if d.get("issue"):
        return d["issue"]
    m = f.get("message") or ""
    starts = (("Kitabın CRM kaydı yok", "no_record"), ("CRM'deki ISBN'in denetim hanesi", "record_isbn_invalid"),
              ("Künyede ISBN bulunamadı", "isbn_missing"), ("Künyedeki ISBN'in denetim hanesi", "printed_isbn_invalid"),
              ("Künyedeki ISBN (", "isbn_differs"), ("CRM'deki kitap adı", "title_not_found"),
              ("Künyede baskı tarihi", "edition_date"), ("Künyedeki raf yaşı", "shelf_age"),
              ("CRM kendi içinde tutarsız", "record_ages_inconsistent"), ("CRM'de kitap «", "series_missing"),
              ("Künyede dizi numarası", "series_no_differs"), ("Künyede dizi «", "series_differs"),
              ("Künyedeki yayın numarası", "publication_no_differs"), ("PDF ", "page_count"))
    for s, k in starts:
        if m.startswith(s):
            return k
    if re.match(r"Künyede \d+\. baskı", m):
        return "edition_differs"
    if re.match(r"Künyede \d+-\d+ yaş", m):
        return "target_age"
    if "role" in d:
        if "printed" in d and isinstance(d.get("crm"), list):
            return "person_not_in_record"
        return "person_differs" if "printed" in d else "person_absent"
    return "other"


def _series_issue(f: dict, d: dict) -> str:
    if d.get("issue"):
        return d["issue"]
    m = f.get("message") or ""
    if f.get("page") is None or not d:
        if m.startswith("Kitabın dizisi belirlenemedi"):
            return "no_series"
        if "analiz edilmiş başka kitap yok" in m:
            return "no_peers"
        if "ortak karakter yok" in m:
            return "no_common"
        if "yazarları farklı" in m:
            return "different_authors"
        return "other"
    if "ccip_median" in d:
        return "drawing_differs"
    if "description" in d or m.startswith("Akrabalık farklı"):
        return "relation_differs"
    if m.startswith("Ad yazımı dizideki öbür kitaptan farklı"):
        return "name_differs"
    if "bir harf farklı" in m:
        return "name_near"
    if " için cinsiyet farklı" in m:
        return "sex_differs"
    if " için yaş grubu farklı" in m:
        return "age_group_differs"
    return "being_differs"


def _kind(check: str, f: dict, d: dict) -> str:
    page_none = f.get("page") is None
    if check in ("layout", "hyphenation"):
        return d.get("rule") or "other"
    if check in ("spelling", "name_spelling", "age_fit", "word_choice"):
        return d.get("kind") or "other"
    if check == "imprint_crm":
        return _imprint_issue(f, d)
    if check == "series_canon":
        return _series_issue(f, d)
    if check in ("appearance", "props", "setting", "timeline", "dialogue"):
        if "summary" in d or (page_none and not d):
            return "summary"
        if check == "appearance":
            return "change"
        if check in ("props", "dialogue"):
            return d.get("rule") or "other"
        if check == "setting":
            return d.get("kind") or "other"
        return "order"
    if check == "edition_diff":
        if "op" in d:
            return "text_" + d["op"]
        if "share" in d:
            return "picture"
        if "new_page" in d:
            return "page_added"
        if "field" in d:
            return "imprint_" + str(d["field"])
        if "old_page" in d:
            return "page_removed"
        return "no_previous"
    return {"text_contradictions": "contradiction", "word_variety": "near_repeat", "word_overuse": "overuse",
            "sentence_starts": "same_start", "phrase_repeats": "phrase"}.get(check, "other")


def kind_of(check: str, f: dict) -> str:
    """Bulgunun tür anahtarı («layout:contrast_low»): metne değil kayıtlı alanlara dayanır (eski künye/dizi
    bulgularında türü taşıyan alan yoksa eski metnin başı). Parmak izi = alıntı + bu anahtar."""
    return f"{check}:{_kind(check, f, f.get('details') or {})}"


# ================================================================== eski metinden alan (yalnız eski kayıtlar)
_OLD = {
    ("appearance", "summary"): r"Özellik defteri: (?P<characters>\d+) karakter, (?P<rows_text>\d+) metin ve "
                               r"(?P<rows_image>\d+) resim kaydı.*?(?P<candidates>\d+) aday çift yargılandı, (?P<confirmed>\d+) bulgu",
    ("props", "summary"): r"Eşya sürekliliği: (?P<ledger_rows>\d+) defter ve (?P<state_rows>\d+) metin durum kaydı, "
                          r"(?P<scenes>\d+) sahne; (?P<candidates>\d+) aday yargılandı, (?P<confirmed>\d+) bulgu",
    ("setting", "summary"): r"Mekân tutarlılığı: (?P<facts>\d+) mekân bilgisi okundu; (?P<candidates>\d+) metin–metin "
                            r"adayı yargılandı \((?P<confirmed_text>\d+) bulgu\), (?P<visual_facts>\d+) bilgi resimle "
                            r"karşılaştırıldı \((?P<confirmed_image>\d+) bulgu\)",
    ("timeline", "summary"): r"Zaman çizelgesi: (?P<expressions>\d+) zaman ifadesi okundu.*?(?P<unreal>\d+) sayfa anı/rüya"
                             r".*?(?P<candidates>\d+) aday yargılandı, (?P<confirmed>\d+) bulgu",
    ("dialogue", "summary"): r"Diyalog: (?P<lines>\d+) replik okundu \((?P<lines_resolved>\d+) konuşanı çözülmüş\).*?atıf "
                             r"adayı (?P<candidates_attribution>\d+) \((?P<confirmed_attribution>\d+) bulgu\), hitap adayı "
                             r"(?P<candidates_address>\d+) \((?P<confirmed_address>\d+) bulgu\)",
    ("series_canon", "no_peers"): r"Dizi: (?P<series>.+?)\. Bu diziden",
    ("series_canon", "no_common"): r"Dizi: (?P<series>.+?)\. «(?P<other_book>.+?)» ile karşılaştırıldı",
    ("series_canon", "different_authors"): r"«(?P<other_book>.+?)» aynı dizide.*?tesadüf sayıldı: (?P<names>.+?)\.$",
    ("series_canon", "being_differs"): r"bu kitapta (?P<being>[A-Z_]+), .*? kitabında (?P<other_being>[A-Z_]+)\.",
    ("series_canon", "sex_differs"): r"farklı: bu kitapta (?P<value>[A-Z_]+), .*? kitabında (?P<other_value>[A-Z_]+)\.",
    ("series_canon", "age_group_differs"): r"farklı: bu kitapta (?P<value>[A-Z_]+), .*? kitabında (?P<other_value>[A-Z_]+)\.",
    ("series_canon", "relation_differs"): r"«(?P<other_name>[^»]+)» için (?P<relation>[^;]+); .*? kitabında (?P<other_relation>[^.]+)\.",
    ("edition_diff", "page_removed"): r"Başı: «(?P<start>.*)»",
    ("layout", "folio_position"): r"\((?P<mm>[\d.]+) mm\)",
    ("imprint_crm", "publication_no_differs"): r"(?P<same_as_series>dizi numarasıyla aynı)",
    ("imprint_crm", "isbn_missing"): r"(?P<_>)",
}


def _old_fields(check: str, kind: str, f: dict) -> dict:
    out: dict = {}
    m = f.get("message") or ""
    rx = _OLD.get((check, kind))
    if rx:
        hit = re.search(rx, m, re.S)
        if hit:
            out = {k: v for k, v in hit.groupdict().items() if v is not None and not k.startswith("_")}
            if check in ("appearance", "props", "setting", "timeline", "dialogue") and kind == "summary":
                out = {"summary": {k: int(v) for k, v in out.items()}}
    if check == "age_fit" and kind == "SENSITIVE" and "): " in m:
        out["reason"] = m.split("): ", 1)[1]
    if check == "imprint_crm" and kind == "printed_isbn_invalid" and f.get("suggestion"):
        out["record_isbn"] = re.sub(r"^CRM'deki ISBN:\s*", "", f["suggestion"])
    return out


# ================================================================== metinler
# Her işlev (f, d, sev) → (metin, öneri, ayrıntı). f: bulgu; d: details (+ eski metinden alanlar);
# sev: denetimin bulduğu düzey (öneriye çevrilmişse asıl düzey). Eksik alan → Missing.

def _layout(kind, f, d, sev):
    lines = d.get("lines")
    n_lines = f" ({num(lines, 0)} satır)" if lines else ""
    if kind == "contrast_low":
        color = cap(color_name(need(d, "color")))
        ratio = need(d, "c_med")
        where = "arkadaki resmin üstünde" if d.get("over_picture") else _ground(d.get("bg_lum_med"))
        light_text = float(d.get("text_lum") or 0) > float(d.get("bg_lum_med") or 0)
        low = sev == "WARN"
        text = _sentence(f"{color} yazı {where} zor okunuyor{n_lines}",
                         "Yazıyla arkası arasındaki renk farkı çok az; okur zorlanır" if low else
                         "Küçük yazıda bu renk farkı yetersiz; okumak göz yorar")
        fix = ("yazıyı açın ya da arkasını koyulaştırın" if light_text else "yazıyı koyulaştırın")
        sugg = (cap(fix) + ", yazının arkasına sade bir zemin koyun ya da yazıyı resmin sade bir yerine taşıyın."
                if d.get("over_picture") else cap(fix) + " ya da zemin rengini değiştirin.")
        detail = (f"Okunurluk oranı {num(ratio)}; en az 3, küçük yazıda en az 4,5 olmalı." if low else
                  f"Okunurluk oranı {num(ratio)}; küçük yazıda en az 4,5 olmalı.")
        return text, sugg, detail
    if kind == "contrast_busy":
        color = cap(color_name(need(d, "color")))
        return (_sentence(f"{color} yazının bir kısmı resmin yazıyla aynı tonda olan bir yerine denk geliyor{n_lines}",
                          "O kısım zor seçiliyor"),
                "Yazıyı resmin sade bir yerine kaydırın ya da yazının arkasına hafif bir zemin koyun.",
                f"En zayıf yerde okunurluk oranı {num(need(d, 'c_p10'))}; en az 3 olmalı.")
    if kind == "text_hidden":
        return (_sentence("Bu yazı sayfada görünmüyor; resmin ya da başka bir öğenin altında kalmış olabilir",
                          "Okur bu metni göremez"),
                "Sayfanın basılacak hâlini kontrol edin; yazıyı öne alın ya da resmi kaydırın.", None)
    if kind == "folio_duplicate":
        printed, other = need(d, "printed", "other_page")
        return (_sentence(f"Sayfa numarası {printed} iki kez basılmış (s. {other} ve bu sayfa)",
                          "Bir sayfa eksik, fazla ya da yer değiştirmiş olabilir"),
                "Sayfa numaralarını ve sayfaların sırasını kontrol edin.", None)
    if kind == "folio_sequence":
        printed, expected = need(d, "printed", "expected")
        return (_sentence(f"Sayfa numarası sıradan kopuyor: burada {expected} olmalıyken {printed} basılmış",
                          "Bir sayfa eksik, fazla ya da yer değiştirmiş olabilir"),
                f"Numarayı {expected} yapın ya da sayfaların sırasını kontrol edin.", None)
    if kind == "folio_parity":
        return (_sentence("Tek sayfa numaraları sol sayfalara düşüyor",
                          "Kitapta tek numaralar sağ sayfada olur; baştan bir sayfa kaymış olabilir"),
                "Kitabın başındaki boş ve ön sayfaları sayın; gerekirse bir boş sayfa ekleyin ya da çıkarın.", None)
    if kind == "folio_position":
        mm = d.get("mm")
        return (_sentence("Bu sayfanın numarası öbür sayfalardakinden farklı yükseklikte duruyor",
                          "Sayfa çevrilirken göze batar"),
                "Numarayı öbür sayfalardaki yüksekliğe taşıyın.",
                f"Öbür sayfalardan {num(mm)} mm farklı." if mm else None)
    if kind == "margin_outside_trim":
        side, mm = need(d, "side", "mm")
        return (_sentence(f"Yazı sayfanın {SIDE.get(side, side)} kenarında kesilecek yerin dışına taşıyor",
                          "Baskıda bu kısım kesilip gider"),
                "Yazıyı sayfanın içine doğru çekin.", f"Kesim çizgisinin {num(abs(float(mm)))} mm dışında.")
    if kind == "margin_safe_zone":
        side, mm, limit = need(d, "side", "mm", "limit_mm")
        why = ("Cilt tarafında yazı sayfa kıvrımına girebilir" if side == "gutter" else
               "Baskıda kesim biraz kayarsa yazı kesilebilir")
        return (_sentence(f"Yazı sayfanın {SIDE.get(side, side)} kenarına çok yakın", why),
                f"Yazıyı kenardan en az {num(limit)} mm içeri alın.",
                f"Kenara uzaklık {num(mm)} mm; en az {num(limit)} mm olmalı.")
    if kind == "body_size":
        size, book = need(d, "size", "book_size")
        bigger = float(size) > float(book)
        return (_sentence(f"Bu sayfada metnin yazısı kitabın geri kalanından {'büyük' if bigger else 'küçük'}",
                          "Okur sayfa geçişinde farkı hisseder"),
                "Yazı boyunu kitabın geri kalanıyla aynı yapın.",
                f"Bu sayfada {num(size)} punto, kitapta {num(book)} punto.")
    if kind == "leading":
        lead, book = need(d, "leading", "book_leading")
        wider = float(lead) > float(book)
        diff = abs(float(lead) - float(book)) / float(book) * 100
        return (_sentence(f"Bu sayfada satır aralığı kitabın geri kalanından {'geniş' if wider else 'sıkışık'}",
                          "Sayfa öbürlerinden farklı görünür"),
                "Satır aralığını öbür sayfalarla aynı yapın.",
                f"Bu sayfada {num(lead)} punto, kitapta {num(book)} punto; fark %{num(diff, 0)}.")
    if kind == "age_type_size":
        xh, conv, age = need(d, "xheight_mm", "conventional_mm", "age_min")
        return (_sentence("Metnin yazısı bu yaştaki okur için küçük",
                          "Okumayı yeni söken çocuk küçük harflerde zorlanır"),
                "Yazı boyunu büyütmeyi düşünün.",
                f"Küçük harf yüksekliği {num(xh)} mm; {age} yaş kitaplarında alışılan yaklaşık {num(conv)} mm.")
    if kind == "orphan":
        nxt = need(d, "next_page")
        return (_sentence(f"Paragrafın ilk satırı sayfanın en altında tek başına kalmış; paragraf sonraki sayfada (s. {nxt}) sürüyor",
                          "Kopuk tek satır okumayı böler"),
                "Satırı sonraki sayfaya alın ya da bu sayfaya bir satır daha sığdırın.", None)
    if kind == "widow":
        prev = need(d, "prev_page")
        return (_sentence(f"Paragrafın son satırı sayfanın en üstünde tek başına kalmış; paragraf önceki sayfada (s. {prev}) başlıyor",
                          "Kopuk tek satır okumayı böler"),
                "Satırı önceki sayfaya sığdırın ya da önceki sayfadan bir satır daha buraya alın.", None)
    raise Missing("rule")


def _split_hint(sugg) -> str | None:
    s = (sugg or "").strip()
    if not s:
        return None
    if s.endswith("(bölmeden)"):
        return "Sözcüğü bölmeden alt satıra alın."
    return f"Şöyle bölün: «{s}»."


def _hyphenation(kind, f, d, sev):
    sugg = f.get("suggestion")
    if kind == "not_syllable_boundary":
        word, syl = need(d, "word", "syllables")
        return (_sentence(f"«{word}» satır sonunda hecesinin ortasından bölünmüş",
                          "Yanlış bölme okumayı aksatır ve yazım kuralına aykırıdır"),
                _split_hint(sugg) or "Sözcüğü hece sınırından bölün.", f"Heceleri: {syl}.")
    if kind == "single_letter":
        word = need(d, "word")
        return (_sentence(f"«{word}» bölünürken satır sonunda ya da başında tek harf kalmış",
                          "Tek harf bırakmak yazım kuralına aykırıdır"),
                _split_hint(sugg) or "Sözcüğü bölmeden alt satıra alın.", None)
    if kind == "stray_hyphen":
        return (_sentence("Satırın ortasında bir bölme çizgisi kalmış",
                          "Metin yeniden dizilince eski çizgi yerinde kalmış olabilir"),
                f"Çizgiyi silin: «{sugg}»." if sugg else "Çizgiyi silin.", None)
    if kind == "lookalike_dash":
        return (_sentence("Satır sonunda bölme için kısa çizgi yerine daha uzun bir çizgi kullanılmış",
                          "Göze farklı görünür"),
                f"Kısa çizgi (-) kullanın: «{sugg}»." if sugg else "Kısa çizgi (-) kullanın.", None)
    if kind == "apostrophe_hyphen":
        return (_sentence("Kesme işaretinden sonra satır sonuna bir de bölme çizgisi konmuş",
                          "Kurala göre satır sonunda yalnız kesme işareti kalır"),
                f"Çizgiyi kaldırın: «{sugg}»." if sugg else "Çizgiyi kaldırın.", None)
    if kind == "apostrophe_suffix":
        return (_sentence("Özel adın eki satır sonunda ortasından bölünmüş",
                          "Kesme işaretinden bölünürse daha düzgün okunur"),
                f"Kesme işaretinden bölün: «{sugg}»." if sugg else "Kesme işaretinden bölün.", None)
    if kind == "ladder":
        n = d.get("lines") or 4                        # eski kayıtlarda yok: kural 3'ten fazlasında (4) uyarır
        return (_sentence(f"Art arda {num(n, 0)} satır bölme çizgisiyle bitiyor",
                          "Sağ kenarda merdiven gibi bir görüntü oluşur"),
                "Bu satırlardan birkaçını bölmeden dizmeyi deneyin.", None)
    if kind == "proper_noun":
        word = need(d, "word")
        return (_sentence(f"Özel ad «{word}» satır sonunda bölünmüş",
                          "Kurala aykırı değil, ama özel adlar genellikle bölünmez"),
                "İsterseniz adı bölmeden alt satıra alın.", None)
    if kind in ("page_turn", "spread_break"):
        nxt = need(d, "next_page")
        where = f"sayfa çevrilince (s. {nxt})" if kind == "page_turn" else f"karşı sayfada (s. {nxt})"
        return (_sentence(f"Sayfanın son sözcüğü bölünmüş; devamı {where} geliyor",
                          "Okur sözcüğün yarısını sayfa değiştirdikten sonra okur" if kind == "page_turn" else
                          "Göz sayfadan sayfaya geçerken sözcük kopuk kalır"),
                "Sayfanın son satırını bölmeden dizin.", None)
    raise Missing("rule")


_HARMONY = {"soru eki": "Soru eki önceki sözcüğün sesine uymuyor",
            "bağlaç da/de": "«de/da» bağlacı önceki sözcüğün sesine uymuyor",
            "ünsüz benzeşmesi": "Ekin ilk harfi sözcüğün son sesine uymuyor",
            "kaynaştırma harfi": "Ekte araya girmesi gereken harf eksik",
            "uyum": "Ekin ünlüsü sözcüğün sesine uymuyor"}
_PUNCT = {"noktalama_öncesi_boşluk": ("Noktalama işaretinden önce boşluk bırakılmış", "Boşluğu silin."),
          "noktalama_sonrası_boşluk_yok": ("Virgül, noktalı virgül ya da iki noktadan sonra boşluk yok",
                                           "İşaretten sonra bir boşluk bırakın."),
          "cümle_sonu_bitişik": ("Cümle sonundaki işaretten sonra boşluk yok; iki cümle bitişik",
                                 "İşaretten sonra bir boşluk bırakın."),
          "çift_nokta": ("İki nokta yan yana yazılmış", "Tek nokta ya da üç nokta (…) kullanın."),
          "çift_virgül": ("Aynı noktalama işareti iki kez yazılmış", "Birini silin."),
          "dört_nokta": ("Üç nokta yerine dört nokta yazılmış", "Üç nokta (…) kullanın.")}


def _spelling(kind, f, d, sev):
    sugg = f.get("suggestion")
    word = d.get("word") or f.get("quote")
    if kind == "bilinmeyen_kelime":
        return (_sentence(f"«{need(d, 'word')}» sözlükte yok; yazım ya da dizgi yanlışı olabilir",
                          "Böyle bir yanlış okurun gözüne takılır"),
                f"«{sugg}» olmalı mı, kontrol edin." if sugg else "Sözcüğün doğru yazımını kontrol edin.", None)
    if kind == "tekrarlanan_hece":
        return (_sentence(f"«{need(d, 'word')}» sözcüğünde bir hece iki kez yazılmış olabilir"),
                f"«{sugg}» olmalı mı, kontrol edin." if sugg else "Sözcüğü kontrol edin.", None)
    if kind == "tekrarlanan_kelime":
        where = " (satır sonunda ve sonraki satırın başında)" if d.get("across_line") else ""
        return (_sentence(f"«{need(d, 'word')}» art arda iki kez yazılmış{where}"), "Birini silin.", None)
    if kind == "ek_uyumu":
        rule = need(d, "rule")
        prev = d.get("previous")
        shown = f"«{prev} {word}»" if prev else f"«{word}»"
        return (_sentence(f"{_HARMONY.get(rule, 'Ek sözcüğün sesine uymuyor')}: {shown}",
                          "Ek, sözcüğün okunuşuna göre değişir"),
                f"«{sugg}» yazın." if sugg else "Eki kontrol edin.", None)
    if kind == "kesme_eksik":
        return (_sentence(f"Özel ada gelen ek kesme işaretiyle ayrılmamış: «{need(d, 'word')}»"),
                f"«{sugg}» yazın." if sugg else "Adla eki kesme işaretiyle ayırın.", None)
    if kind == "gereksiz_kesme":
        return (_sentence(f"Özel ad olmayan bir sözcükte kesme işareti kullanılmış: «{need(d, 'word')}»"),
                f"«{sugg}» yazın." if sugg else "Kesme işaretini kaldırın.", None)
    if kind == "büyük_harf":
        return (_sentence(f"Cümle küçük harfle başlıyor: «{word}»"),
                f"«{sugg}» yazın." if sugg else "İlk harfi büyük yazın.", None)
    if kind == "tutarlılık":
        style, used, major = need(d, "style", "used", "book_majority")
        counts = d.get("book_counts") or {}
        mark = STYLE_MARK.get(style, str(style).replace("_", " "))
        detail = ("Kitapta " + ", ".join(f"«{k}» {num(v, 0)} kez" for k, v in counts.items()) + "."
                  if counts else None)
        return (_sentence(f"Burada {mark} kitabın geri kalanından farklı biçimde yazılmış: «{used}» "
                          f"(kitapta çoğunlukla «{major}»)",
                          "Aynı işaretin iki biçimi dizgide tutarsız görünür"),
                f"«{major}» kullanın.", detail)
    if kind == "tırnak_içi_boşluk":
        opening = "Açılan" in (d.get("rule") or "")
        return (_sentence(f"{'Açılan tırnaktan sonra' if opening else 'Kapanan tırnaktan önce'} boşluk bırakılmış"),
                "Boşluğu silin.", None)
    if kind in _PUNCT:
        t, s = _PUNCT[kind]
        return _sentence(t), s, None
    raise Missing("kind")


def _name_spelling(kind, f, d, sev):
    form, book_form, n = need(d, "form", "book_form", "book_form_count")
    sugg = f.get("suggestion")
    pages = d.get("book_form_pages")
    detail = f"«{book_form}» yazılan sayfalar: {pages_txt(pages)}." if pages else None
    if kind == "ad_varyantı":
        return (_sentence(f"Bu ad burada «{form}» diye yazılmış; kitabın geri kalanında {num(n, 0)} kez «{book_form}»",
                          "Aynı kişinin ya da yerin adı iki türlü yazılınca okur karışır"),
                f"Hangisi doğruysa her yerde onu kullanın (burada «{sugg}» olabilir)." if sugg else
                "Hangisi doğruysa her yerde onu kullanın.", detail)
    if kind == "küçük_harf":
        return (_sentence(f"Özel ad küçük harfle yazılmış: «{form}» (kitapta {num(n, 0)} kez «{book_form}»)"),
                f"«{sugg}» yazın." if sugg else "İlk harfi büyük yazın.", detail)
    raise Missing("kind")


def _band_txt(band) -> str:
    if isinstance(band, (list, tuple)) and len(band) == 2 and band[0] is not None:
        return f"{band[0]}-{band[1]} yaş"
    return ""


def _age_fit(kind, f, d, sev):
    ref = d.get("reference")
    if kind == "LONG_SENTENCE":
        words, thr = need(d, "words", "threshold")
        return (_sentence(f"Bu cümle bu yaştaki okur için çok uzun ({num(words, 0)} sözcük)",
                          "Uzun cümlede küçük okur ipi kaçırır"),
                "Cümleyi iki ya da üç kısa cümleye bölün.",
                f"{ref} yaş için yayımlanmış kitaplarda cümleler çoğunlukla en çok {num(thr, 0)} sözcük." if ref else
                f"Bu yaş için yayımlanmış kitaplarda cümleler çoğunlukla en çok {num(thr, 0)} sözcük.")
    if kind == "HARD_PAGE":
        m = need(d, "measures")
        return (_sentence("Bu sayfanın metni bu yaştaki okur için zor",
                          "Cümleler uzun, sözcükler çok heceli; okur yorulur"),
                "Cümleleri kısaltın, uzun sözcükleri sadeleştirin.",
                f"Ortalama cümle {num(m.get('asl'))} sözcük." if m.get("asl") is not None else None)
    if kind == "BOOK_MEASURES":
        m = need(d, "measures")
        base = (f"Kitabın okunabilirliği ölçüldü: ortalama cümle {num(m.get('asl'))} sözcük, "
                f"metnin {pct(m.get('dialogue_share') or 0)} kadarı konuşma")
        if not ref:
            verdict = "Aynı yaş için karşılaştırılacak kitap olmadığından sayfa ve cümle uyarısı verilmedi"
        elif d.get("harder"):
            verdict = f"{ref} yaş için yayımlanmış kitapların çoğundan daha zor okunuyor"
        else:
            verdict = f"{ref} yaş için yayımlanmış kitaplarla benzer düzeyde"
        return (_sentence(base, verdict), None,
                f"{num(m.get('words'), 0)} sözcük, {num(m.get('sentences'), 0)} cümle; sözcük başına "
                f"{num(m.get('asw'))} hece.")
    if kind == "NO_BAND":
        return (_sentence("Kitabın hangi yaş için olduğu bilgisi bulunamadı",
                          "Bu yüzden sayfa ve cümle uzunluğu yaşa göre değerlendirilmedi"),
                "Yaş aralığını künyeye ya da yayınevinin kitap kaydına ekleyin.", None)
    if kind == "SENSITIVE":
        cat = SENSITIVE.get(need(d, "category"), "hassas bir konu")
        band = _band_txt(d.get("band"))
        who = f"{band} okur" if band else "çocuk okur"
        reason = clip(d.get("reason") or "", 240)
        return (_sentence(f"Bu bölümde {cat} anlatılıyor; {who} için hassas olabilir", reason),
                "Bölümü okuyup yaşa uygun olup olmadığına karar verin; gerekirse anlatımı yumuşatın.",
                f"Eminlik {pct(d['probability'])}." if d.get("probability") is not None else None)
    raise Missing("kind")


def _src(o: dict) -> str:
    return "resimde" if (o or {}).get("source") == "IMAGE" else "metinde"


def _appearance(kind, f, d, sev):
    if kind == "summary":
        s = need(d, "summary")
        return (_sentence(f"Karakterlerin görünüşü (saç, göz, giysi, eşya) metinle resimler arasında karşılaştırıldı: "
                          f"{num(s.get('characters', 0), 0)} karakter, {num(s.get('confirmed', 0), 0)} tutarsızlık"),
                None, f"Metinden {num(s.get('rows_text', 0), 0)}, resimlerden {num(s.get('rows_image', 0), 0)} kayıt; "
                      f"{num(s.get('candidates', 0), 0)} olası çelişki incelendi.")
    ch, attr, a, b = need(d, "character", "kind", "a", "b")
    label = ATTRIBUTE.get(attr, str(attr).lower())
    qa = f" ({q(a.get('quote'), 60)})" if a.get("source") == "TEXT" and a.get("quote") else ""
    pa = d.get("pages_a") or []
    return (_sentence(f"«{ch}» için {label} sayfalar arasında değişiyor: {a.get('page')}. sayfada {_src(a)} "
                      f"«{value_tr(a.get('value'))}»{qa}, bu sayfada {_src(b)} «{value_tr(b.get('value'))}»",
                      ("Bu özellik hikâye içinde kolay değişmez; " if attr in STABLE_ATTRIBUTES else "")
                      + "hikâye değişikliği açıklamıyor"),
            "İki sayfayı yan yana karşılaştırın; çizimi ya da metni düzeltin veya değişikliği açıklayan bir cümle ekleyin.",
            f"Önceki değer {pages_txt(pa)} sayfalarında da görülüyor." if len(pa) > 1 else None)


def _item_state(o: dict) -> str:
    st = str(o.get("state") or "")
    if o.get("source") == "IMAGE":
        return "resimde yanında yok" if st == "YOK" else "resimde yanında"
    return "metinde " + ITEM_STATE.get(st, st.lower())


def _props(kind, f, d, sev):
    if kind == "summary":
        s = need(d, "summary")
        return (_sentence(f"Karakterlerin taşıdığı eşyalar sahneden sahneye izlendi: {num(s.get('scenes', 0), 0)} "
                          f"sahne, {num(s.get('confirmed', 0), 0)} tutarsızlık"),
                None, f"{num(s.get('candidates', 0), 0)} olası çelişki incelendi.")
    ch, a, b = need(d, "character", "a", "b")
    item = a.get("item") if a.get("item") and a.get("item") != "eşya yok" else b.get("item") or "eşya"
    if kind == "A":
        what = "aynı sahnede birden kayboluyor" if str(b.get("state")) == "YOK" else "aynı sahnede birden beliriyor"
    else:
        what = "açıklama olmadan yeniden yerinde"
    return (_sentence(f"«{ch}» ile ilgili eşya tutarsızlığı: {item} {what} ({a.get('page')}. sayfada "
                      f"{_item_state(a)}, bu sayfada {_item_state(b)})",
                      "Hikâye bu değişikliği açıklamıyor"),
            "İki yeri yan yana karşılaştırın; çizimi ya da metni düzeltin veya değişikliği açıklayan bir cümle ekleyin.",
            None)


def _setting(kind, f, d, sev):
    if kind == "summary":
        s = need(d, "summary")
        found = s.get("confirmed_text", 0) + s.get("confirmed_image", 0)
        return (_sentence(f"Mekânların tarifi kitap boyunca karşılaştırıldı: {num(s.get('facts', 0), 0)} bilgi, "
                          f"{num(found, 0)} tutarsızlık",
                          "Oda düzeni, kapı ve pencerenin yeri, kat ve şehir resimlerden değil yalnız metinden karşılaştırılır"),
                None, f"{num(s.get('candidates', 0), 0)} olası çelişki incelendi; "
                      f"{num(s.get('visual_facts', 0), 0)} bilgi resimle karşılaştırıldı.")
    aspect, a = need(d, "aspect", "a")
    what = PLACE_ASPECT.get(aspect, str(aspect).lower())
    if kind == "TEXT_IMAGE":
        b = need(d, "b")
        img = d.get("image") or {}
        return (_sentence(f"Metinle resim uyuşmuyor ({what}): metin «{value_tr(a.get('value'))}» diyor, "
                          f"resim «{value_tr(b.get('seen'))}» gösteriyor",
                          "Okur resimle metni birlikte okur"),
                "Sayfanın resmiyle metnini karşılaştırın; çizimi ya da cümleyi düzeltin.",
                f"Eminlik {pct(img['p_against'])}." if img.get("p_against") is not None else None)
    b = need(d, "b")
    place = d.get("place") or a.get("place") or "mekân"
    return (_sentence(f"«{place}» iki yerde farklı anlatılıyor ({what}): {a.get('page')}. sayfada "
                      f"{q(a.get('quote'), 70)}, bu sayfada {q(b.get('quote'), 70)}",
                      "Hikâye bu farkı açıklamıyor"),
            "İki tarifi karşılaştırıp birini düzeltin ya da değişikliği açıklayan bir cümle ekleyin.", None)


def _timeline(kind, f, d, sev):
    if kind == "summary":
        s = need(d, "summary")
        return (_sentence(f"Zaman ifadeleri (günün saati, mevsim, yaş) sırayla izlendi: {num(s.get('expressions', 0), 0)} "
                          f"ifade, {num(s.get('confirmed', 0), 0)} tutarsızlık",
                          "Anı ve rüya sayfaları sıraya katılmadı"),
                None, f"{num(s.get('candidates', 0), 0)} olası çelişki incelendi.")
    a, b = need(d, "a", "b")
    what = TIME_KIND.get(d.get("kind"), "zaman")
    why = f" ({d['why']})" if d.get("why") else ""
    return (_sentence(f"Zaman bilgisi tutmuyor ({what}): {a.get('page')}. sayfada {q(a.get('quote'), 70)}, "
                      f"sonra bu sayfada {q(b.get('quote'), 70)}{why}",
                      "Metin geri dönüşü açıklamıyor"),
            "İki yeri karşılaştırın; zaman ifadesini düzeltin ya da geçişi («ertesi gün», «o sırada», «anımsadı») açıkça yazın.",
            None)


def _dialogue(kind, f, d, sev):
    if kind == "summary":
        s = need(d, "summary")
        found = s.get("confirmed_attribution", 0) + s.get("confirmed_address", 0)
        return (_sentence(f"Konuşmaların kime ait olduğu ve karakterlerin birbirine nasıl seslendiği izlendi: "
                          f"{num(s.get('lines', 0), 0)} konuşma, {num(found, 0)} tutarsızlık"),
                None, f"{num(s.get('candidates_attribution', 0) + s.get('candidates_address', 0), 0)} olası çelişki incelendi.")
    if kind == "A":
        a, b = need(d, "a", "b")
        speaker = need(a, "speaker")
        present = ", ".join(b.get("present") or []) or "kimse görünmüyor"
        return (_sentence(f"Bu konuşma «{speaker}» adına yazılmış, ama o bu sahnede görünmüyor "
                          f"(sahnedekiler: {present})",
                          "Konuşanın adı karışmış olabilir"),
                "Konuşmanın kime ait olduğunu ve sahnede kimlerin bulunduğunu kontrol edin; adı ya da anlatımı düzeltin.",
                None)
    if kind == "B":
        a, b, dom, dev = need(d, "a", "b", "dominant", "deviant")
        uses = d.get("uses")
        return (_sentence(f"«{a.get('speaker')}», «{a.get('addressee')}» adlı karaktere genellikle "
                          f"{ADDRESS.get(dom, dom)} sesleniyor (s. {a.get('page')}: «{a.get('address_term')}»); burada "
                          f"{ADDRESS.get(dev, dev)}: «{b.get('address_term')}»",
                          "Hikâye bu değişikliği açıklamıyor"),
                "Hitabı öteki konuşmalarla aynı yapın ya da değişikliğin nedenini metinde gösterin.",
                f"{num(uses, 0)} konuşmada bakıldı." if uses else None)
    raise Missing("rule")


def _text_contradictions(kind, f, d, sev):
    a, b = need(d, "a", "b")
    what = CONTRADICTION_KIND.get(d.get("kind"), "bilgi")
    return (_sentence(f"Metin kendisiyle çelişiyor ({what}): {a.get('page')}. sayfadaki {q(a.get('quote'), 70)} "
                      f"ile bu sayfadaki {q(b.get('quote'), 70)} birlikte doğru olamaz", d.get("why")),
            "İki yeri karşılaştırıp birini düzeltin ya da değişikliği açıklayan bir cümle ekleyin.", None)


def _series_canon(kind, f, d, sev):
    other = d.get("other_book")
    in_other = f"dizinin öbür kitabında («{other}»)" if other else "dizinin öbür kitabında"
    sugg = f.get("suggestion")
    if kind == "no_series":
        return (_sentence("Kitabın hangi diziye ait olduğu bilinmiyor; dizinin öbür kitaplarıyla karşılaştırılmadı"),
                "Dizi adını künyeye ya da kitap kaydına ekleyin.", None)
    if kind == "no_peers":
        s = d.get("series")
        return (_sentence((f"Dizi: {s}. " if s else "") + "Bu diziden incelenmiş başka kitap yok; karşılaştırma yapılmadı"),
                None, None)
    if kind == "no_common":
        s = d.get("series")
        return (_sentence((f"Dizi: {s}. " if s else "") + f"«{need(d, 'other_book')}» ile karşılaştırıldı; ortak karakter yok"),
                None, None)
    if kind == "different_authors":
        names = d.get("names")
        return (_sentence(f"«{need(d, 'other_book')}» aynı dizide ama yazarı farklı; aynı adlı karakterler"
                          + (f" ({names})" if names else "") + " ayrı kişiler sayıldı"), None, None)
    ch = need(d, "character")
    if kind == "name_differs":
        at = f", s. {d['other_first_page']}" if d.get("other_first_page") else ""
        in_other = f"dizinin öbür kitabında («{other}»{at})" if other else in_other
        return (_sentence(f"«{f.get('quote') or ch}» adı {in_other} «{sugg}» diye yazılmış",
                          "Aynı karakterin adı dizide tek biçimde yazılmalı"),
                "Hangisi doğruysa iki kitapta da onu kullanın.", None)
    if kind == "name_near":
        return (_sentence(f"«{f.get('quote') or ch}» adı {in_other} geçen «{sugg}» adına çok benziyor; bir harf farklı olabilir"),
                "Aynı karakterse yazımı birleştirin; farklı karakterse bu uyarıyı geçin.", None)
    if kind == "being_differs":
        a, b = need(d, "being", "other_being")
        return (_sentence(f"«{ch}» bu kitapta {BEING.get(a, a.lower())}, {in_other} {BEING.get(b, b.lower())} olarak anlatılıyor",
                          "Hikâye bu değişikliği açıklamıyorsa okur karışır"),
                "İki kitabı karşılaştırıp karakterin tanıtımını birleştirin.", None)
    if kind in ("sex_differs", "age_group_differs"):
        a, b = need(d, "value", "other_value")
        names, what = (SEX, "cinsiyeti") if kind == "sex_differs" else (AGE_GROUP, "yaş grubu")
        return (_sentence(f"«{ch}» karakterinin {what} farklı: bu kitapta {names.get(a, a.lower())}, "
                          f"{in_other} {names.get(b, b.lower())}",
                          "Hikâye bunu açıklamıyorsa (ör. aradan yıllar geçmesi) okur karışır"),
                "İki kitabı karşılaştırıp karakterin anlatımını birleştirin.", None)
    if kind == "relation_differs":
        y, r1, r2 = need(d, "other_name", "relation", "other_relation")
        return (_sentence(f"«{ch}» ile «{y}» arasındaki akrabalık farklı: bu kitapta {r1.lower()}, {in_other} {r2.lower()}",
                          "Aynı ailenin bağları dizide aynı kalmalı"),
                "İki kitabı karşılaştırıp akrabalığı birleştirin.", None)
    if kind == "drawing_differs":
        pa, pb = d.get("pages"), d.get("other_pages")
        detail = (f"Karşılaştırılan sayfalar: bu kitapta {pages_txt(pa)}; öbür kitapta {pages_txt(pb)}."
                  if pa and pb else None)
        return (_sentence(f"«{ch}» bu kitapta {in_other} çizildiğinden farklı görünüyor",
                          "Karakterin görünüşü dizide aynı kalmalı"),
                "Saçı, teni, gözleri ve ayırt edici işaretleri iki kitabın sayfalarında karşılaştırın.", detail)
    raise Missing("issue")


def _edition_diff(kind, f, d, sev):
    old_page = d.get("old_page")
    moved = (f" (önceki baskıda s. {old_page})"
             if old_page and old_page != f.get("page") and (kind.startswith("text_") or kind == "picture") else "")
    if kind == "no_previous":
        return _sentence("Bu kitabın önceki baskısının dosyası yok; baskılar karşılaştırılmadı"), None, None
    if kind.startswith("text_"):
        area = "Künyede" if sev == "INFO" else "Metinde"
        if kind == "text_replace":
            what = f"«{need(d, 'old')}» yerine «{need(d, 'new')}» yazılmış"
        elif kind == "text_delete":
            what = f"önceki baskıdaki «{need(d, 'old')}» çıkarılmış"
        else:
            what = f"«{need(d, 'new')}» eklenmiş"
        srcs = d.get("sources") or []
        detail = ("Metin iki baskıda farklı yollarla okundu; fark okuma farkından da olabilir."
                  if len(srcs) == 2 and srcs[0] != srcs[1] else None)
        return (_sentence(f"{area} önceki baskıya göre değişiklik{moved}: {what}"),
                "Değişikliğin bilerek yapıldığını teyit edin.", detail)
    if kind == "picture":
        share = need(d, "share")
        return (_sentence(f"Sayfanın resmi (ya da resimdeki yazı) önceki baskıya göre değişmiş{moved}"),
                "İşaretli bölgeyi iki baskıda karşılaştırın.",
                f"Sayfanın yazı dışındaki alanının {pct(share, 1)} kadarı farklı.")
    if kind == "page_added":
        return (_sentence("Bu sayfa önceki baskıda yok"), "Sayfanın bilerek eklendiğini teyit edin.", None)
    if kind == "page_removed":
        start = d.get("start")
        return (_sentence(f"Önceki baskının s. {need(d, 'old_page')} sayfası bu baskıda yok"
                          + (f" (başı: «{start}»)" if start else "")),
                "Sayfanın bilerek çıkarıldığını teyit edin.", None)
    if kind.startswith("imprint_"):
        field, old, new = need(d, "field", "old", "new")
        name = {"isbn": "ISBN", "edition": "Baskı numarası", "date": "Baskı tarihi"}.get(field, field)
        j = lambda v: ", ".join(map(str, v)) if isinstance(v, list) else str(v)  # noqa: E731
        return (_sentence(f"{name} önceki baskıya göre değişmiş: {j(old)} → {j(new)}",
                          "ISBN değişince kitap yeni bir kayıt sayılır" if field == "isbn" else None),
                "Değişikliğin doğru olduğunu teyit edin.", None)
    raise Missing("kind")


def _imprint_crm(kind, f, d, sev):
    rec = "yayınevinin kitap kaydında"
    if kind == "no_record":
        return (_sentence("Bu kitabın yayınevi kaydı bulunamadı; künye karşılaştırılamadı"), None, None)
    if kind == "record_isbn_invalid":
        return (_sentence(f"Yayınevi kaydındaki ISBN hatalı görünüyor: {need(d, 'crm_isbn')}",
                          "Son hanesi öbür hanelerle tutmuyor; numara yanlış girilmiş olabilir"),
                "Kayıttaki ISBN'i düzeltin.", None)
    if kind == "isbn_missing":
        isbn = d.get("crm_isbn")
        return (_sentence("Künyede ISBN yok", "Her basılı kitabın künyesinde ISBN bulunmalı"),
                f"Künyeye ISBN'i ekleyin ({rec}: {isbn})." if isbn else "Künyeye ISBN'i ekleyin.", None)
    if kind == "printed_isbn_invalid":
        printed = need(d, "printed")
        isbn = d.get("record_isbn")
        return (_sentence(f"Künyedeki ISBN hatalı görünüyor: {printed}",
                          "Son hanesi tutmuyor; bir hane yanlış basılmış olabilir"),
                f"ISBN'i kontrol edin ({rec}: {isbn})." if isbn else "ISBN'i kontrol edin.", None)
    if kind == "isbn_differs":
        printed, crm = need(d, "printed", "crm")
        if sev == "INFO":
            return (_sentence(f"Künyedeki ISBN ({printed}) yayınevi kaydındaki ana ISBN değil ({crm}); bu kitabın "
                              "başka bir ISBN alanında (ör. e-kitap) kayıtlı"),
                    "Künyede doğru ISBN'in basıldığını teyit edin.", None)
        return (_sentence(f"Künyedeki ISBN ({printed}) yayınevi kaydındakinden ({crm}) farklı",
                          "Yanlış ISBN kitabın satış ve dağıtım kaydını karıştırır"),
                "Hangisi doğruysa künyeyi ya da kaydı düzeltin.", None)
    if kind == "title_not_found":
        return (_sentence(f"Yayınevi kaydındaki kitap adı («{need(d, 'crm_title')}») kitabın metninde bulunamadı",
                          "Ad kapakta resim olarak basılmışsa bu normaldir"),
                "Kapaktaki adla kayıttaki adı karşılaştırın.", None)
    if kind in ("person_differs", "person_absent", "person_not_in_record"):
        role = ROLE.get(need(d, "role"), "kişi")
        if kind == "person_differs":
            printed, crm = need(d, "printed", "crm")
            return (_sentence(f"{cap(role)} adı kitapta «{printed}», yayınevi kaydında «{crm}» diye yazılmış",
                              "Künyedeki adlar kayıttakiyle aynı olmalı"),
                    "Doğru yazımı yazarla ya da yayınevi kaydıyla teyit edin.", None)
        if kind == "person_absent":
            return (_sentence(f"Yayınevi kaydında {role} olarak «{need(d, 'crm')}» var, ama kitapta bu ad geçmiyor"),
                    "Künyeyi ya da yayınevi kaydını kontrol edin.", None)
        return (_sentence(f"Künyede {role} olarak «{need(d, 'printed')}» yazıyor; yayınevi kaydında bu görevde böyle biri yok"),
                "Künyeyi ya da yayınevi kaydını kontrol edin.", None)
    if kind == "edition_differs":
        printed, crm = need(d, "printed", "crm")
        older = int(printed) < int(crm)
        return (_sentence(f"Künyede {printed}. baskı yazıyor; yayınevi kaydındaki son baskı {crm}",
                          "Bu dosya eski bir baskıya ait olabilir" if older else None),
                f"Yeni baskıysa künyeyi «{crm}. Baskı» yapın; değilse kaydı düzeltin.", None)
    if kind == "edition_date":
        printed, crm = need(d, "printed", "crm")
        m = re.match(r"(\d{4})-(\d{2})", str(crm))
        crm_txt = f"{MONTHS[int(m.group(2)) - 1]} {m.group(1)}" if m else str(crm)
        return (_sentence(f"Künyedeki baskı tarihi ({printed}) yayınevi kaydındakinden ({crm_txt}) farklı"),
                "Doğru tarihi künyede ya da kayıtta düzeltin.", None)
    if kind == "shelf_age":
        printed, crm = need(d, "printed", "crm")
        return (_sentence(f"Künyedeki yaş aralığı ({printed[0]}-{printed[1]}) yayınevi kaydındaki raf bilgisinden («{crm}») farklı"),
                "Yaş aralığını künyede ya da kayıtta düzeltin.", None)
    if kind == "target_age":
        printed, crm = need(d, "printed", "crm")
        return (_sentence(f"Künyede {printed[0]}-{printed[1]} yaş yazıyor; yayınevi kaydındaki hedef yaş "
                          f"({crm[0]}-{crm[1]}) bu aralığın dışına taşıyor"),
                "Hedef yaşı kayıtta ya da künyede düzeltin.", None)
    if kind == "record_ages_inconsistent":
        t, ages = need(d, "crm_target", "crm_ages")
        return (_sentence(f"Yayınevi kaydı kendi içinde tutarsız: hedef yaş {t[0]}-{t[1]}, yaş etiketleri «{ages}»"),
                "Kayıttaki yaş bilgilerini birbirine uydurun.", None)
    if kind == "series_missing":
        no = f" ({d['crm_no']}. kitap)" if d.get("crm_no") else ""
        return (_sentence(f"Yayınevi kaydına göre kitap «{need(d, 'crm')}» dizisinde{no}, ama künyede dizi adı bulunamadı"),
                "Dizi adını künyeye eklemeyi düşünün.", None)
    if kind == "series_differs":
        printed, crm = need(d, "printed", "crm")
        crm = crm[0] if isinstance(crm, list) and crm else crm
        other = d.get("record_other")
        return (_sentence(f"Künyedeki dizi adı («{printed}») yayınevi kaydındakinden («{crm}») farklı",
                          f"Kaydın öbür dizi alanında ise «{other}» yazıyor; kaydın iki alanı birbirini tutmuyor"
                          if other else None),
                "Dizi adını künyede ve kayıtta aynı yapın.", None)
    if kind == "series_no_differs":
        printed, crm = need(d, "printed", "crm")
        return (_sentence(f"Künyedeki dizi numarası ({printed}) yayınevi kaydındakinden ({crm}) farklı"),
                "Doğru numarayı künyede ya da kayıtta düzeltin.", None)
    if kind == "publication_no_differs":
        printed, crm = need(d, "printed", "crm")
        return (_sentence(f"Künyedeki yayın numarası ({printed}) yayınevi kaydındakinden ({crm}) farklı",
                          "Basılı numara dizi numarasıyla aynı; dizi numarası yayın numarasının yerine yazılmış olabilir"
                          if d.get("same_as_series") else None),
                f"Yayın numarasını {crm} yapın ya da kaydı düzeltin.", None)
    if kind == "page_count":
        printed, crm = need(d, "printed", "crm")
        return (_sentence(f"Kitap dosyası {num(printed, 0)} sayfa; yayınevi kaydında sayfa sayısı {num(crm, 0)}",
                          "Kayıt ya da dosya güncel olmayabilir"),
                "Doğru sayfa sayısını kayda işleyin.", None)
    raise Missing("issue")


def _word_variety(kind, f, d, sev):
    lemma, count = need(d, "lemma", "count")
    forms = d.get("forms") or []
    what = f"«{d['idiom']}» deyimi" if d.get("idiom") else f"«{lemma}» sözcüğü"
    sense = f" aynı anlamda ({d['sense']})" if d.get("sense") and not d.get("idiom") else ""
    shown = ": " + ", ".join(f"«{w}»" for w in forms) if forms else ""
    alts = f.get("suggestion")
    return (_sentence(f"{cap(what)}{sense} birbirine yakın {num(count, 0)} kez geçiyor{shown}",
                      "Kısa aralıkla aynı sözcük anlatımı tekdüzeleştirir"),
            "Birini değiştirmeyi düşünün; örneğin " + ", ".join(f"«{a.strip()}»" for a in alts.split(",") if a.strip()) + "."
            if alts else
            "Birini değiştirmeyi ya da cümleyi yeniden kurmayı düşünün.", None)


def _word_overuse(kind, f, d, sev):
    lemma, count = need(d, "lemma", "count")
    books, scope = d.get("corpus_books"), d.get("corpus_scope")
    others = f"yayınevinin {scope + ' ' if scope else ''}öbür {num(books, 0) + ' ' if books else ''}kitabında"
    if d.get("corpus_count"):
        ratio = d.get("ratio")
        why = (f"{others} bu kadar sık değil ({num(ratio)} kat); yazarın bir alışkanlığı gibi görünüyor" if ratio else
               f"{others} bu kadar sık değil; yazarın bir alışkanlığı gibi görünüyor")
        detail = (f"10.000 sözcükte {num(d.get('per10k'))} kez; öbür kitaplarda {num(d.get('corpus_per10k'))}."
                  if d.get("per10k") is not None else None)
    else:
        why = f"{others} hiç geçmiyor; yazarın bir alışkanlığı gibi görünüyor"
        detail = f"10.000 sözcükte {num(d.get('per10k'))} kez." if d.get("per10k") is not None else None
    return (_sentence(f"«{lemma}» kitapta çok sık kullanılmış: {num(count, 0)} kez", why),
            "Bir kısmını çıkarmayı ya da başka sözcüklerle değiştirmeyi düşünün.", detail)


def _sentence_starts(kind, f, d, sev):
    count = need(d, "count")
    m = re.search(r"\[\[(.+?)\]\]", d.get("passage_marked") or "")
    word = m.group(1) if m else need(d, "lemma")
    return (_sentence(f"Art arda {num(count, 0)} cümle aynı sözcükle başlıyor: «{word}»",
                      "Okurken tekdüze bir ritim oluşur"),
            "Cümlelerden birinin başını değiştirin ya da iki cümleyi birleştirin.", None)


def _phrase_repeats(kind, f, d, sev):
    count = need(d, "count")
    occ = d.get("occurrences") or []
    phrase = (occ[0].get("text") if occ and isinstance(occ[0], dict) else None) or f.get("quote") or \
        " ".join(need(d, "phrase"))
    where = pages_txt(d.get("pages"))
    return (_sentence(f"«{phrase}» söz öbeği kitapta {num(count, 0)} kez geçiyor" + (f" ({where})" if where else ""),
                      "Aynı kalıp ifadenin tekrarı göze batar"),
            "Tekrarlardan birini başka bir anlatımla değiştirin.", None)


def _word_choice(kind, f, d, sev):
    if kind == "age_summary":
        count, words = need(d, "count", "words")
        reader = d.get("reader") or "bu yaştaki okur"
        shown = ", ".join(f"{w['word']} → {w['alternative']}" for w in words[:8] if isinstance(w, dict))
        more = f" ve {len(words) - 8} sözcük daha" if len(words) > 8 else ""
        return (_sentence(f"Kitapta {reader} için ağır olabilecek {num(count, 0)} sözcük var: {shown}{more}",
                          "Okur bu sözcüklere takılabilir; kitabın yaş aralığı da gözden geçirilmeli"),
                "Listeyi gözden geçirip uygun yerlerde daha basit karşılıklarını kullanın.",
                f"1.000 sözcükte {num(d['per1000'])} tane." if d.get("per1000") is not None else None)
    word, alt = need(d, "word", "alternative")
    count = d.get("count")
    where = (f" (kitapta {num(count, 0)} kez: {pages_txt(d.get('pages'))})" if count and d.get("pages") else
             f" (kitapta {num(count, 0)} kez)" if count else "")
    if kind == "foreign":
        return (_sentence(f"«{word}» yabancı kökenli bir sözcük; Türkçesi «{alt}»{where}",
                          "Türkçe karşılığı okura daha tanıdık gelir"),
                f"«{alt}» kullanmayı düşünün.", None)
    if kind == "age":
        return (_sentence(f"«{word}» bu yaştaki okur için ağır olabilir; daha basit karşılığı «{alt}»{where}"),
                f"«{alt}» kullanmayı düşünün.", None)
    raise Missing("kind")


_RENDER = {"layout": _layout, "hyphenation": _hyphenation, "spelling": _spelling, "name_spelling": _name_spelling,
           "age_fit": _age_fit, "appearance": _appearance, "props": _props, "setting": _setting,
           "timeline": _timeline, "dialogue": _dialogue, "text_contradictions": _text_contradictions,
           "series_canon": _series_canon, "edition_diff": _edition_diff, "imprint_crm": _imprint_crm,
           "word_variety": _word_variety, "word_overuse": _word_overuse, "sentence_starts": _sentence_starts,
           "phrase_repeats": _phrase_repeats, "word_choice": _word_choice}


# ================================================================== dış yüz
def render(check: str, f: dict) -> dict:
    """Bulgunun sade metni: {text, suggestion, detail, kind, fresh, missing}.

    f: {page, severity, quote, suggestion (kayıtlı, ham), message (kayıtlı), details}. `fresh` = metin şablondan
    üretildi; False ise kayıtlı metin olduğu gibi döner ve `missing` eksik alanı söyler."""
    d = dict(f.get("details") or {})
    kind = _kind(check, f, d)
    for k, v in _old_fields(check, kind, f).items():
        d.setdefault(k, v)
    sev = d.get("severity_as_found") or f.get("severity") or "WARN"
    fn = _RENDER.get(check)
    try:
        if fn is None:
            raise Missing("check")
        text, sugg, detail = fn(kind, f, d, sev)
        return {"text": text, "suggestion": sugg, "detail": detail, "kind": f"{check}:{kind}",
                "fresh": True, "missing": []}
    except (Missing, KeyError, TypeError, ValueError, IndexError, AttributeError) as e:
        field = e.args[0] if isinstance(e, KeyError) and e.args else type(e).__name__
        return {"text": (f.get("message") or "").strip(), "suggestion": f.get("suggestion"), "detail": None,
                "kind": f"{check}:{kind}", "fresh": False, "missing": [str(field)]}


def text(check: str, f: dict) -> str:
    """Denetimin kaydedeceği metin (bulgu kurulurken)."""
    r = render(check, {**f, "message": ""})
    if not r["fresh"]:
        raise ValueError(f"{check}: bulgu metni kurulamadı, eksik alan {r['missing']}")
    return r["text"]


def put(check: str, f: dict, advice: bool = False) -> dict:
    """Bulguya metnini yazar (f['message']) ve bulguyu döndürür. `advice=True`: öneri cümlesi de buradan
    (f['suggestion']); verilmezse suggestion denetimin ham önerisi (doğru yazım, doğru bölme) olarak kalır."""
    r = render(check, {**f, "message": ""})
    if not r["fresh"]:
        raise ValueError(f"{check}: bulgu metni kurulamadı, eksik alan {r['missing']}")
    f["message"] = r["text"]
    if advice:
        f["suggestion"] = r["suggestion"]
    return f


def word_comment(f: dict, label: str, placed: bool = True) -> str:
    """Word yorumu: önem + denetim adı; «s. N — metin»; öneri; en sonda parantez içinde ayrıntı."""
    r = f if "text" in f else {**f, "text": f.get("message")}
    head = f"{SEVERITY_LEAD.get(f.get('severity') or 'WARN', 'Bakmanız önerilir')} — {label}"
    body = (f"s. {f['page']} — " if f.get("page") is not None else "") + (r.get("text") or "")
    out = head + "\n" + body
    if not placed:
        out += "\nMetinde tam yeri bulunamadı; yorum sayfa başlığına bağlandı."
    if r.get("suggestion"):
        out += "\nÖneri: " + r["suggestion"]
    if r.get("detail"):
        out += "\n(" + r["detail"].rstrip(".") + ".)"
    return out
