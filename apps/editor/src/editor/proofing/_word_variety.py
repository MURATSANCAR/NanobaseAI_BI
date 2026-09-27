"""Kelime çeşitliliği denetiminin (word_variety) saf parçaları — model, veritabanı, sözlük yok.

Denetim modülü değildir (alt çizgi). Girdi, `_spelling_text.read_book` belirteçlerinden süzülmüş
basit kayıtlar ve sözlük çözümlemeleridir; burada:
  - belirteç sınıfı: özel ad mı, sözcük mü (`word_kind`);
  - kök seçimi: bir biçimin birden çok çözümlemesi olduğunda hangi kök (`choose_lemmas`);
  - cümle numarası (`sentence_ids`), ikileme ayıklama (`drop_reduplication`), yakın tekrar
    kümesi (`clusters`);
  - çeşitlilik ölçüsü MTLD (`mtld`);
  - anlam ayrımı için model çağrılarının paketlenmesi (`rounds`), istem (`sense_prompt`) ve
    cevabın doğrulanıp birleştirilmesi (`merge_senses`);
  - kelime haritası (`build_map`) ve tekrar pasajı (`passage`).

Kitaba özel hiçbir şey yok: sözcük listesi yok; sözcük türü Zemberek çözümlemesinden gelir.
"""

from __future__ import annotations

import collections
from dataclasses import dataclass, field

# Zemberek birincil sözcük türleri. İçerik sözcüğü = ad, sıfat, zarf, fiil: yakın tekrarın okurun
# gözüne battığı sınıf. İşlev sözcükleri (bağlaç, zamir, edat, soru eki, ünlem, sayı, belirteç)
# haritada sayılır, tekrar adayı olmaz: "ve", "bu", "bir", "mi" her cümlede geçer, redaksiyon konusu değildir.
CONTENT_POS = ("Noun", "Adj", "Adv", "Verb")
UNKNOWN_POS = "?"

APOS = "'’`"


def lower_tr(w: str) -> str:
    return w.translate(str.maketrans({"I": "ı", "İ": "i"})).lower()


# ------------------------------------------------------------------ belirteç sınıfı
def word_kind(base: str, apos: str, sent_start: bool) -> str:
    """'name' | 'word'. Kesme işaretli büyük harfli biçim ve cümle ortasında büyük harfle başlayan
    biçim özel addır (ad yazımı ayrı denetimin işi; ad tekrarı redaksiyon konusu değildir).
    Tamamı büyük harf (başlık, vurgu) sözcüktür. Cümle başındaki büyük harf karar vermez:
    orada sözlüğe bakılır (`candidates` yalnız özel ad çözümlemesi verirse ad)."""
    if not base or not base[:1].isalpha():
        return "name"
    if base.isupper() and len(base) > 1:
        return "word"
    if base[:1].isupper() and (apos or not sent_start):
        return "name"
    return "word"


# Bir kökün çözümlemelerinden biri bu türlerdense kök işlev sözcüğüdür ("bir": belirteç/sıfat/sayı/zarf;
# "o": zamir/belirteç). Sayı tek başına işlev saymaz: "yüz" hem sayı hem ad (surat).
FUNCTION_POS = ("Det", "Pron", "Conj", "Postp", "Ques", "Interj")


def candidates(analyses) -> list[tuple[str, str, int, int, bool]]:
    """Zemberek çözümlemeleri → (kök, tür, türetme sayısı, gövde uzunluğu, özel ad mı). Kök = sözlük
    maddesi (fiilde mastar: "yüzmek"; ad "yüz" ile karışmaz). Türetme sayısı çözümlemenin çekim
    grubu sınırlarından (`group_boundaries`): "gözlük" maddesi 0, göz+lük 1."""
    out = []
    for a in analyses:
        item = getattr(a, "dict_item", None)
        if item is None:
            continue
        pos = getattr(getattr(item, "primary_pos", None), "value", None) or UNKNOWN_POS
        sec = getattr(getattr(item, "secondary_pos", None), "value", None)
        stem = getattr(a, "stem", None) or item.lemma
        derivations = max(0, len(getattr(a, "group_boundaries", None) or [0]) - 1)
        out.append((lower_tr(item.lemma), pos, derivations, len(stem), sec == "Prop"))
    return list(dict.fromkeys(out))


def choose_lemmas(form_cands: dict[str, list[tuple[str, str, int, int, bool]]],
                  form_counts: dict[str, int]) -> dict[str, tuple[str, str, bool]]:
    """Her biçim için tek kök: (kök, tür, belirsiz mi).

    1. Özel ad çözümlemesi, sıradan çözümleme varken düşer ("Gül" / "gül").
    2. En az türetmeli çözümleme kalır: türetilmiş sözcük kendi maddesidir ("gözlük" ≠ göz+lük;
       "yüzdü" = yüzmek, yüz+ek fiil değil).
    0. Biçim bir işlev sözcüğünün yalın hâliyse o okuma (`closed`).
    3. Kalan birden çok kök varsa: kitapta TEK kökle çözümlenen biçimlerinin sıklığı büyük olan
       (kitabın kendi kullanımı: "gözüme", "gözü" varsa "göze" → göz, pınar anlamındaki "göze" değil);
       eşitlikte kısa gövde (yalın kök, ekli okumadan sık: "koşa" → koşmak), sonra alfabetik.
       `belirsiz` işaretlenir.
    Tür: kökün çözümlemelerinde işlev türü (FUNCTION_POS) varsa o; yoksa içerik türü önde.
    Çözümlemesi olmayan biçim listede yoktur (bilinmeyen: haritada ayrı sayılır)."""
    def trimmed(cs):
        cs = [c for c in cs if not c[4]] or cs
        low = min(c[2] for c in cs)
        return [c for c in cs if c[2] == low]

    def closed(f, cs):
        """Biçim bir işlev sözcüğünün yalın hâliyse o okuma: "de" bağlaç (demek'in emri değil),
        "ile"/"için" edat (il+e, iç+in değil), "o" zamir. Kapalı sınıf sözcükleri metinde ezici
        sıklıktadır; eş yazılı ekli okuma nadirdir."""
        return [c for c in cs if c[0] == f and c[1] in FUNCTION_POS and c[2] == 0 and not c[4]]

    pre = {f: (closed(f, cs) or trimmed(cs)) for f, cs in form_cands.items() if cs}
    sure = collections.Counter()
    for f, cs in pre.items():
        if len({c[0] for c in cs}) == 1:
            sure[cs[0][0]] += form_counts.get(f, 1)
    out = {}
    for f, cs in pre.items():
        stem_of = {}
        for c in cs:
            stem_of[c[0]] = min(stem_of.get(c[0], 99), c[3])
        lemmas = sorted(stem_of)
        best = sorted(lemmas, key=lambda lem: (-sure[lem], stem_of[lem], lem))[0]
        pos = sorted({c[1] for c in cs if c[0] == best})
        func = [p for p in pos if p in FUNCTION_POS]
        content = [p for p in pos if p in CONTENT_POS]
        out[f] = (best, (func or content or pos)[0], len(lemmas) > 1)
    return out


# ------------------------------------------------------------------ yinelenen OCR eki
def _key_text(t: str) -> str:
    return " ".join("".join(ch if ch.isalnum() else " " for ch in lower_tr(t)).split())


def duplicate_supplements(spans: list[dict], probe: int = 40) -> set[tuple[int, int]]:
    """Sayfanın metin katmanında ZATEN bulunan OCR ekleri (source.read ek span'ı; `supplement`): aynı
    paragraf iki kez okunmuş olur ve her sözcük denetiminde sahte tekrar üretir. Ekin başı ve sonu
    (`probe` karakter, noktalama ve büyük/küçük harf yok sayılarak) aynı sayfanın katman metninde geçiyorsa
    ek yinelenmiştir. Dönen: (sayfa, span idx)."""
    layer: dict[int, str] = {}
    for sp in spans:
        if not sp.get("supplement"):
            layer[sp["page"]] = layer.get(sp["page"], "") + " " + _key_text(sp["text"])
    out = set()
    for sp in spans:
        if not sp.get("supplement"):
            continue
        k = _key_text(sp["text"])
        page_text = layer.get(sp["page"], "")
        if not k or not page_text:
            continue
        head, tail = k[:probe], k[-probe:]
        if head in page_text and tail in page_text:
            out.add((sp["page"], sp["idx"]))
    return out


# ------------------------------------------------------------------ konum
def sentence_ids(sent_starts: list[bool]) -> list[int]:
    """Belirteç akışında cümle numarası; sayfa sınırı cümleyi bölmez (cümle sayfadan taşar)."""
    out, sid = [], -1
    for i, s in enumerate(sent_starts):
        if s or i == 0:
            sid += 1
        out.append(sid)
    return out


@dataclass
class Occ:
    idx: int            # belirteç akışındaki sıra (bütün belirteçler; bitişiklik buna göre)
    page: int
    span: int
    start: int
    end: int
    sent: int
    form: str           # küçük harf, kesmesiz biçim ("gözüme")
    word: str           # basıldığı gibi ("Gözüme")
    lemma: str
    pos: str
    ambiguous: bool = False
    sense: int | None = None          # anlam sırası (lemma içinde); None = atanmadı
    extra: dict = field(default_factory=dict)


def drop_reduplication(occs: list[Occ]) -> tuple[list[Occ], int]:
    """İkileme tekrar değildir: art arda iki belirteç aynı kökse ("yavaş yavaş", "göz göze",
    "koşa koşa") ikincisi sayılmaz. Girdi aynı kökün sıralı geçişleri."""
    kept, dropped = [], 0
    for o in occs:
        if kept and o.idx - kept[-1].idx == 1:
            dropped += 1
            continue
        kept.append(o)
    return kept, dropped


def chance_near(gap: int, rate: float) -> float:
    """Sözcük kitaba rastgele serpilmiş olsaydı, bir geçişten sonraki `gap` belirteç içinde yeniden
    görünme olasılığı: 1 − (1 − oran)^gap. Oran = sözcüğün (o anlamda) kitaptaki geçişi / kitabın
    sözcük sayısı. «olmak» her 50 sözcükte bir geçiyorsa 10 sözcük arayla yeniden görünmesi olağandır
    (≈0,18); kitapta 5 kez geçen bir sözcüğün 20 sözcük arayla yinelenmesi değildir (≈0,003)."""
    if gap <= 0 or rate <= 0:
        return 0.0
    return 1.0 - (1.0 - min(rate, 1.0)) ** gap


def clusters(occs: list[Occ], window: int, rate: float | None = None, alpha: float | None = None
             ) -> list[list[Occ]]:
    """Yakın tekrar: ardışık iki geçiş arasında en çok `window` cümle varsa (0 = aynı cümle, 1 = aynı ya
    da bir sonraki cümle) VE — `rate` verilmişse — bu yakınlığın tesadüf olasılığı `alpha`'dan küçükse
    aynı küme. Sık sözcüğün (yardımcı fiil, kitabın konusu) olağan yakınlığı tekrar sayılmaz.
    Girdi sıralı; ≥2 geçişli kümeler döner."""
    out, cur = [], []
    for o in occs:
        near = bool(cur) and o.sent - cur[-1].sent <= window
        if near and rate is not None and alpha is not None:
            near = chance_near(o.idx - cur[-1].idx, rate) < alpha
        if near:
            cur.append(o)
            continue
        if len(cur) >= 2:
            out.append(cur)
        cur = [o]
    if len(cur) >= 2:
        out.append(cur)
    return out


# ------------------------------------------------------------------ çeşitlilik
def mtld(seq: list[str], threshold: float = 0.72) -> float | None:
    """MTLD (McCarthy & Jarvis 2010): tür/belirteç oranının `threshold` altına düşmeden
    sürdüğü ortalama uzunluk; ileri ve geri okumanın ortalaması. TTR'nin aksine metin
    uzunluğundan büyük ölçüde bağımsızdır; 0,72 yazındaki ölçünün kendi sabitidir, ayar değildir.
    Metin boşsa None."""
    if not seq:
        return None

    def one(s):
        factors, types, n = 0.0, set(), 0
        for w in s:
            n += 1
            types.add(w)
            if len(types) / n <= threshold:
                factors += 1
                types, n = set(), 0
        if n:
            ttr = len(types) / n
            factors += (1 - ttr) / (1 - threshold) if ttr < 1 else 0
        return len(s) / factors if factors else float(len(s))

    return round((one(seq) + one(list(reversed(seq)))) / 2, 1)


# ------------------------------------------------------------------ kitap geneli sıklık (anahtar sözcük)
# Log-likelihood (Dunning 1993) ki-kare dağılımında 1 serbestlik derecesiyle; 15,13 = p < 0,0001.
# Derlem dilbiliminde anahtar sözcük için alışılmış kesim; kitapta ayarlanmadı.
KEYNESS_G2 = 15.13


def log_likelihood(a: int, n_book: int, b: int, n_corpus: int) -> float:
    """Sözcüğün kitaptaki (a / n_book) ve derlemdeki (b / n_corpus) sıklığı arasındaki farkın G² değeri."""
    import math
    if a + b == 0 or n_book <= 0 or n_corpus <= 0:
        return 0.0
    e1 = n_book * (a + b) / (n_book + n_corpus)
    e2 = n_corpus * (a + b) / (n_book + n_corpus)
    g = 0.0
    if a:
        g += a * math.log(a / e1)
    if b:
        g += b * math.log(b / e2)
    return 2 * g


def overused(book: dict[str, int], n_book: int, corpus: dict[str, int], n_corpus: int,
             g2: float = KEYNESS_G2) -> list[dict]:
    """Kitapta derleme göre anlamlı ölçüde SIK kullanılan kökler (G² ≥ g2 ve kitap oranı derlemden büyük).
    Derlemde hiç geçmeyen sözcük de sayılır (oran sonsuz); sıralama G²'ye göre."""
    out = []
    for lem, a in book.items():
        b = corpus.get(lem, 0)
        if a * n_corpus <= b * n_book:
            continue
        g = log_likelihood(a, n_book, b, n_corpus)
        if g >= g2:
            out.append({"lemma": lem, "count": a, "corpus_count": b, "g2": round(g, 1),
                        "per10k": round(a / n_book * 10000, 1), "corpus_per10k": round(b / n_corpus * 10000, 2),
                        "ratio": round((a / n_book) / (b / n_corpus), 1) if b else None})
    return sorted(out, key=lambda x: -x["g2"])


# ------------------------------------------------------------------ cümle başı
def start_runs(starts: list[str], alpha: float) -> list[tuple[int, int, float]]:
    """Art arda aynı sözcükle başlayan cümle dizileri: (ilk, son+1, olasılık). Sözcüğün kitapta cümle
    başlatma oranı p ise art arda k cümlenin onunla başlaması tesadüfen p^(k−1); bu `alpha`'dan küçükse
    tekdüzelik. «Ben» cümlelerin %10'unu başlatıyorsa iki «Ben…» olağan (0,1), üç tanesi değil (0,01)."""
    freq = collections.Counter(starts)
    n = len(starts)
    out, i = [], 0
    while i < n:
        j = i + 1
        while j < n and starts[j] == starts[i]:
            j += 1
        k = j - i
        if k >= 2:
            p = (freq[starts[i]] / n) ** (k - 1)
            if p < alpha:
                out.append((i, j, p))
        i = j
    return out


# ------------------------------------------------------------------ kalıp ifade
def repeated_phrases(seq: list[tuple[int, int, str, bool]], min_n: int = 3, min_content: int = 2
                     ) -> list[tuple[int, list[int]]]:
    """Kitapta en az iki kez geçen söz öbekleri, kök dizisi üstünden: (uzunluk, başlangıç konumları).

    `seq`: (belirteç sırası, cümle, kök, içerik mi) — okuma sırasıyla. Öbek bitişik belirteçlerden ve
    tek cümleden oluşur (arada özel ad ya da atlanan belirteç varsa kopar). En az `min_n` sözcük ve en az
    `min_content` içerik sözcüğü («bir gün daha» gibi işlev ağırlıklı öbekler sayılmaz). Üst üste binen
    geçişler tek sayılır. Yalnız EN UZUN hâl döner: aynı geçişlerle daha uzun bir öbeğin parçası olan
    kısa öbek bildirilmez. Uzunluk sınırı yok."""
    def ok_at(i: int, n: int) -> bool:
        if i + n > len(seq):
            return False
        for k in range(1, n):
            if seq[i + k][0] != seq[i + k - 1][0] + 1 or seq[i + k][1] != seq[i][1]:
                return False
        return sum(1 for k in range(n) if seq[i + k][3]) >= min_content

    def groups(n: int, starts) -> dict[tuple, list[int]]:
        by: dict[tuple, list[int]] = {}
        for i in starts:
            if ok_at(i, n):
                by.setdefault(tuple(seq[i + k][2] for k in range(n)), []).append(i)
        out = {}
        for key, pos in by.items():
            kept = []
            for i in pos:                       # üst üste binen geçişler tek sayılır
                if not kept or i >= kept[-1] + n:
                    kept.append(i)
            if len(kept) >= 2:
                out[key] = kept
        return out

    found: list[tuple[int, list[int]]] = []
    cur = groups(min_n, range(len(seq)))
    n = min_n
    while cur:
        nxt = groups(n + 1, sorted({i for pos in cur.values() for i in pos} | {i - 1 for pos in cur.values() for i in pos if i > 0}))
        longer = {i for pos in nxt.values() for i in pos}
        for key, pos in cur.items():
            # bir uzun öbek (aynı yerden ya da bir önceki sözcükten başlayan) bu öbeğin BÜTÜN geçişlerini
            # kapsıyorsa kısa olan bildirilmez; bir geçiş bile açıkta kalırsa kısa öbek de bildirilir
            if not all(i in longer or i - 1 in longer for i in pos):
                found.append((n, pos))
        cur, n = nxt, n + 1
    return sorted(found, key=lambda x: (x[1][0], -x[0]))


# ------------------------------------------------------------------ anlam ayrımı
def rounds(units: dict[str, list], batch: int) -> list[list[list[tuple[str, list]]]]:
    """Anlam çağrılarının planı. Her kök geçişleriyle `batch`'lik parçalara bölünür; r. tur her
    kökün r. parçasıdır (bir kökün sonraki parçası, önceki parçada bulunan anlam etiketleriyle
    sorulur, bu yüzden turlar sıralı). Bir tur içinde parçalar `batch` geçişi aşmayan çağrılara
    paketlenir. Hiçbir geçiş dışarıda kalmaz; sınır yalnız çağrı boyudur."""
    chunks = {lem: [occ[i:i + batch] for i in range(0, len(occ), batch)] for lem, occ in units.items() if occ}
    depth = max((len(c) for c in chunks.values()), default=0)
    plan = []
    for r in range(depth):
        calls, cur, size = [], [], 0
        for lem in sorted(chunks, key=lambda k: (-len(units[k]), k)):
            if r >= len(chunks[lem]):
                continue
            part = chunks[lem][r]
            if cur and size + len(part) > batch:
                calls.append(cur)
                cur, size = [], 0
            cur.append((lem, part))
            size += len(part)
        if cur:
            calls.append(cur)
        plan.append(calls)
    return plan


SENSE_INTRO = (
    "Bir kitabın redaksiyonu için kelime haritası çıkarıyorsun. Aşağıda her sözcüğün kitapta geçtiği "
    "yerler numaralı; sözcük [[ ]] içinde. Her sözcüğün geçişlerini ANLAMA göre grupla.\n"
    "- Aynı biçim farklı anlamda olabilir: organ olarak «göz», «dolabın gözü» (bölme), «göze girmek» "
    "(deyim, beğenilmek) üç ayrı anlamdır.\n"
    "- Bir geçiş bir deyimin parçasıysa `deyim` alanına deyimi mastar hâliyle yaz («göze girmek»); "
    "değilse boş bırak. Aynı deyimin bütün geçişleri bir grupta olur.\n"
    "- `etiket` kısa ve genel olsun (2-5 sözcük, ör. «organ, görme», «bölme, çekmece»).\n"
    "- Anlamları KABA tut: yalnız sözlükte ayrı madde ya da ayrı anlam olacak kadar farklı kullanımları ayır. "
    "Aynı anlamın farklı nesnelerle, farklı zaman ya da kişi ekleriyle kullanımı tek anlamdır "
    "(bir şeyi satın almak ile başka bir şeyi satın almak aynı anlam). Deyimler her zaman ayrı anlamdır.\n"
    "- Her numara tam bir grupta yer alır; hiçbirini atlama.\n")


def sense_prompt(call: list[tuple[str, list]], contexts: dict[int, str], prior: dict[str, list[dict]]
                 ) -> tuple[str, dict[int, tuple[str, Occ]]]:
    """İstem metni ve numara → (kök, geçiş) eşlemi. `contexts`: geçiş idx → [[ ]] işaretli bağlam."""
    lines, ids, n = [SENSE_INTRO], {}, 0
    for lem, part in call:
        lines.append(f"\n## {lem}")
        if prior.get(lem):
            lines.append("Bu sözcük için önceki bölümlerde bulunan anlamlar (aynı anlamsa etiketi AYNEN kullan): "
                         + "; ".join(f"«{s['label']}»" + (f" (deyim: {s['idiom']})" if s["idiom"] else "")
                                     for s in prior[lem]))
        for o in part:
            n += 1
            ids[n] = (lem, o)
            lines.append(f"{n}. s.{o.page}: {contexts[o.idx]}")
    return "\n".join(lines), ids


def sense_schema(n_lemmas: int, n_items: int) -> dict:
    """Listelerin üst sınırı çağrıdaki öğe sayısıdır: model doğru cevapta sınıra çarpamaz,
    yalnız döngüye giren bir kod çözmeyi durdurur (bkz. schemas.arr)."""
    from .. import schemas
    sense = schemas.obj({"etiket": {"type": "string", "maxLength": 120},
                         "deyim": {"type": "string", "maxLength": 120},
                         "numaralar": schemas.arr({"type": "integer", "minimum": 1, "maximum": n_items},
                                                  1, n_items)})
    return schemas.obj({"sozcukler": schemas.arr(schemas.obj({
        "sozcuk": {"type": "string", "maxLength": 120},
        "anlamlar": schemas.arr(sense, 1, n_items)}), 1, max(n_lemmas, 1) * 2)})


def _norm_label(s: str) -> str:
    return " ".join(lower_tr(s or "").replace("«", "").replace("»", "").split()).strip(" .,;")


def merge_senses(out: dict, ids: dict[int, tuple[str, Occ]], senses: dict[str, list[dict]]) -> list[int]:
    """Model cevabını geçişlere işler: `senses[kök]` anlam listesine (etiket, deyim) ekler ya da
    var olanla (aynı etiket veya aynı deyim) birleştirir, `occ.sense` atar. Doğrulama: numara
    bu çağrıda olmalı; bir numara iki grupta ise ilki geçer; bir grup başka köklerin numaralarını
    da taşıyorsa her kök kendi numaralarını alır (cevaptaki `sozcuk` alanına güvenilmez).
    Atanmamış numaraları döndürür (yeniden sorulur)."""
    seen: set[int] = set()
    for w in (out or {}).get("sozcukler", []):
        for s in w.get("anlamlar", []):
            label, idiom = (s.get("etiket") or "").strip(), (s.get("deyim") or "").strip()
            by_lemma: dict[str, list[int]] = collections.defaultdict(list)
            for i in s.get("numaralar", []):
                if i in ids and i not in seen:
                    seen.add(i)
                    by_lemma[ids[i][0]].append(i)
            for lem, nums in by_lemma.items():
                lst = senses.setdefault(lem, [])
                key_l, key_i = _norm_label(label), _norm_label(idiom)
                hit = next((k for k, x in enumerate(lst)
                            if (key_i and _norm_label(x["idiom"]) == key_i)
                            or (not key_i and not x["idiom"] and _norm_label(x["label"]) == key_l)), None)
                if hit is None:
                    lst.append({"label": label or "?", "idiom": idiom})
                    hit = len(lst) - 1
                for i in nums:
                    ids[i][1].sense = hit
    return sorted(set(ids) - seen)


def marked_context(text: str, start: int, end: int, width: int) -> str:
    """Geçişin çevresi, sözcük [[ ]] içinde; iki yanda `width` karakter."""
    a, b = max(0, start - width), min(len(text), end + width)
    s = ("…" if a else "") + text[a:start] + "[[" + text[start:end] + "]]" + text[end:b] + ("…" if b < len(text) else "")
    return " ".join(s.split())


# ------------------------------------------------------------------ sayfadaki yer
def norm_word(w: str) -> str:
    """Sayfa sözcüğü ile belirteci karşılaştırmak için: baştaki/sondaki harf olmayanlar atılır
    (noktalama, tırnak, konuşma çizgisi), Türkçe küçük harf, kesme işaretleri birleşir."""
    import unicodedata
    w = unicodedata.normalize("NFKC", w or "")
    a, b = 0, len(w)
    while a < b and not w[a].isalpha():
        a += 1
    while b > a and not w[b - 1].isalpha():
        b -= 1
    return lower_tr(w[a:b]).translate(str.maketrans({"’": "'", "`": "'"}))


def pick_box(page_words: list[tuple[str, list[int]]], word: str, nth: int, total: int) -> list[int] | None:
    """Belirtecin sayfadaki kutusu: sayfanın basılı sözcükleri (okuma sırasıyla, normalize) içinde aynı
    sözcüğün `nth`. geçişi — yalnız sayfadaki geçiş sayısı bizim metnimizdekiyle aynıysa (yoksa sıra
    eşleşmez, yanlış yeri işaretlemektense işaret yok). Tek geçiş varsa o."""
    hits = [b for w, b in page_words if w == norm_word(word)]
    if hits and len(hits) == total and 0 <= nth < total:
        return hits[nth]
    if len(hits) == 1 and total == 1:
        return hits[0]
    return None


def to1000(rect, page_rect) -> list[int]:
    """PDF noktası → sayfa görselinde 0..1000 (öbür denetimlerin bbox biçimi)."""
    w, h = page_rect[2] - page_rect[0], page_rect[3] - page_rect[1]
    return [int(round((rect[0] - page_rect[0]) / w * 1000)), int(round((rect[1] - page_rect[1]) / h * 1000)),
            int(round((rect[2] - page_rect[0]) / w * 1000)), int(round((rect[3] - page_rect[1]) / h * 1000))]


def valid_suggestion(s: str, valid) -> bool:
    """Öneri sözlükte var olan sözcüklerden oluşmalı ("anlasayd" gibi bozuk biçim atılır). `valid`:
    sözcük → bool (Lexicon.valid)."""
    words = [w for w in s.replace("-", " ").split() if w]
    return bool(words) and all(valid(w.strip(".,;:!?…\"'«»()")) for w in words)


# ------------------------------------------------------------------ yargı
FLAW = ("Evet: tekrar okurken göze batıyor; eş anlamlı bir sözcük, zamir ya da cümleyi yeniden kurmakla "
        "giderilmeli.")
FINE = ("Hayır: bilinçli ya da gerekli (hikâyenin konusu olan nesne/kişi, hitap, başka adı olmayan somut ad, "
        "terim, vurgu, tekrar sanatı, tekerleme, şiir, diyalogda doğal konuşma, çocuk kitabında bilinçli yineleme).")


def flaw_prompt(lemma: str, sense: dict, marked: str, x: str, y: str, book_count: int | None = None) -> str:
    what = f"«{lemma}»" + (f" (anlamı: {sense['label']}" + (f"; deyim: {sense['idiom']}" if sense["idiom"] else "")
                           + ")" if sense else "")
    freq = (f" Bu sözcük kitabın tamamında {book_count} kez geçiyor." if book_count else "")
    return ("Bir kitabın redaksiyonunu yapan deneyimli bir editörsün. Aşağıdaki pasajda " + what
            + " sözcüğü AYNI ANLAMDA kısa aralıkla birden çok kez geçiyor; geçtiği yerler [[ ]] içinde." + freq
            + " Yalnız okurun gözüne batan, yerine başka söyleyiş konabilecek tekrar düzeltilir; hikâyenin konusu "
            "olan nesne ya da kişi, hitap sözcüğü, başka adı olmayan somut ad, terim ve bilinçli yineleme düzeltilmez.\n\n"
            f"Pasaj: «{marked}»\n\nBu yakın tekrar düzeltilmeli mi?\nA) {x}\nB) {y}\nYalnız A ya da B yaz.")


SAME = "Evet: cümle aynı anlamı korur ve doğru Türkçe olur."
DIFFERENT = "Hayır: anlam değişir, başka bir şey anlatılır ya da cümle bozulur."


def keeps_meaning_prompt(marked: str, second: str, suggestion: str, x: str, y: str) -> str:
    return ("Bir kitabın redaksiyonunu yapıyorsun. Aşağıdaki pasajda tekrarlanan sözcük [[ ]] içinde. "
            f"İkinci geçiş olan «{second}» yerine «{suggestion}» yazılırsa ne olur?\n\n"
            f"Pasaj: «{marked}»\n\nA) {x}\nB) {y}\nYalnız A ya da B yaz.")


# ------------------------------------------------------------------ harita ve pasaj
def build_map(occs: list[Occ], senses: dict[str, list[dict]], contexts: dict[int, str]) -> list[dict]:
    """Kitabın tekil kelime haritası: her kök bir kez, sıklığa göre. Her kökte biçimler, sayfalar
    ve (anlamı sorulmuşsa) anlamlar — her anlamın sıklığı, sayfaları ve ilk örneği. Kesme yok:
    bütün kökler, bütün sayfalar."""
    by = collections.defaultdict(list)
    for o in occs:
        by[o.lemma].append(o)
    rows = []
    for lem, os_ in by.items():
        pos = collections.Counter(o.pos for o in os_).most_common(1)[0][0]
        row = {"lemma": lem, "pos": pos, "count": len(os_),
               "forms": dict(collections.Counter(o.form for o in os_).most_common()),
               "pages": sorted({o.page for o in os_}),
               "ambiguous": any(o.ambiguous for o in os_)}
        if lem in senses:
            ss = []
            for k, s in enumerate(senses[lem]):
                mine = [o for o in os_ if o.sense == k]
                if mine:
                    ss.append({"label": s["label"], "idiom": s["idiom"], "count": len(mine),
                               "pages": sorted({o.page for o in mine}), "example": contexts.get(mine[0].idx, "")})
            unassigned = [o for o in os_ if o.sense is None]
            if unassigned:
                ss.append({"label": "belirsiz (model atamadı)", "idiom": "", "count": len(unassigned),
                           "pages": sorted({o.page for o in unassigned}),
                           "example": contexts.get(unassigned[0].idx, "")})
            row["senses"] = sorted(ss, key=lambda s: -s["count"])
        rows.append(row)
    return sorted(rows, key=lambda r: (-r["count"], r["lemma"]))


def passage(span_keys: list[tuple[int, int]], span_text: dict[tuple[int, int], str], occs: list[Occ],
            until: tuple[int, int] | None = None) -> tuple[str, str]:
    """Tekrarın geçtiği metin: ilk geçişin span'ından sonuncunun span'ına (ya da `until` span'ına) kadar,
    arada ne varsa. (düz metin, geçişleri [[ ]] ile işaretli metin)."""
    pos = {k: i for i, k in enumerate(span_keys)}
    a = min(pos[(o.page, o.span)] for o in occs)
    b = max([pos[(o.page, o.span)] for o in occs] + ([pos[until]] if until in pos else []))
    plain, marked = [], []
    for k in span_keys[a:b + 1]:
        txt = span_text[k]
        cuts = sorted((o.start, o.end) for o in occs if (o.page, o.span) == k)
        m, last = [], 0
        for s, e in cuts:
            m.append(txt[last:s] + "[[" + txt[s:e] + "]]")
            last = e
        m.append(txt[last:])
        plain.append(" ".join(txt.split()))
        marked.append(" ".join("".join(m).split()))
    return " ".join(plain), " ".join(marked)
