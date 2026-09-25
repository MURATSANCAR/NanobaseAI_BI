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

    pre = {f: trimmed(cs) for f, cs in form_cands.items() if cs}
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


def clusters(occs: list[Occ], window: int) -> list[list[Occ]]:
    """Yakın tekrar: ardışık iki geçiş arasında en çok `window` cümle varsa aynı küme
    (0 = aynı cümle, 1 = aynı ya da bir sonraki cümle). Girdi sıralı; ≥2 geçişli kümeler döner."""
    out, cur = [], []
    for o in occs:
        if cur and o.sent - cur[-1].sent <= window:
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


# ------------------------------------------------------------------ yargı
FLAW = ("Evet: tekrar okurken göze batıyor; eş anlamlı bir sözcük, zamir ya da cümleyi yeniden kurmakla "
        "giderilmeli.")
FINE = ("Hayır: bilinçli ya da gerekli (vurgu, tekrar sanatı, tekerleme, şiir, diyalogda doğal konuşma, "
        "terim ya da başka söylenişi olmayan sözcük, çocuk kitabında bilinçli yineleme).")


def flaw_prompt(lemma: str, sense: dict, marked: str, x: str, y: str) -> str:
    what = f"«{lemma}»" + (f" (anlamı: {sense['label']}" + (f"; deyim: {sense['idiom']}" if sense["idiom"] else "")
                           + ")" if sense else "")
    return ("Bir kitabın redaksiyonunu yapan deneyimli bir editörsün. Aşağıdaki pasajda " + what
            + " sözcüğü AYNI ANLAMDA kısa aralıkla birden çok kez geçiyor; geçtiği yerler [[ ]] içinde.\n\n"
            f"Pasaj: «{marked}»\n\nBu yakın tekrar düzeltilmeli mi?\nA) {x}\nB) {y}\nYalnız A ya da B yaz.")


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


def passage(span_keys: list[tuple[int, int]], span_text: dict[tuple[int, int], str], occs: list[Occ]
            ) -> tuple[str, str]:
    """Tekrarın geçtiği metin: ilk geçişin span'ından sonuncunun span'ına kadar (arada ne varsa).
    (düz metin, geçişleri [[ ]] ile işaretli metin)."""
    pos = {k: i for i, k in enumerate(span_keys)}
    a = min(pos[(o.page, o.span)] for o in occs)
    b = max(pos[(o.page, o.span)] for o in occs)
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
