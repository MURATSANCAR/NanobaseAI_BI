"""Kimlik bağları: aynı adın ötesinde, kitabın KENDİ cümlesinin söylediği birleşmeler (2026-10-03, K16–K19).

`identity.same_name_plan` aynı yazılı adı taşıyan kayıtları birleştirir. Burada onun üstüne, yine model çağrısı
olmadan ve kitaba özel hiçbir kural olmadan, dört genel sınıf:

K16 kısaltma / takma ad = tam ad, YALNIZ metinde açık eşleme kalıbı varsa («X, yani Y», «Y (X)», «X diye
    çağırdıkları Y», «asıl adı Y olan X», «X, Y'nin kısaltması», «Y isminin kısaltması olan X», «herkes ona X
    der», «X lakaplı Y» …; dipnot da sayfa metnidir). Ön ek / harf benzerliği tek başına ASLA yetmez («Ali» /
    «Alican», «Bee» / «Beatrice»): kalıp yoksa bağ yok. Bağın kanıt cümlesi ve sayfası kayda yazılır. İki ad bir
    yerde «X ve Y», «X ile Y» diye yan yana sayılıyorsa iki kişidir (ALIAS_COORDINATED). Bir ad birden çok kayıtta
    ise yalnız bağdaşan tek kayıt seçilir, yoksa bağ kurulmaz (ALIAS_AMBIGUOUS).
    Ayrıca diğer-ad çakışması: aynı diğer ad iki ayrı kişinin kaydındaysa ya da bir kaydın diğer adı başka bir
    kaydın adı / metinle bağlanmış takma adıysa (`alias_conflicts`): sahibi belliyse düzeltilir, değilse işaretlenir.
K17 anlatıcı: birinci şahıs anlatıda anlatıcının adı ANLATIM cümlesinden («benim adım X», «bana X derler») ya da
    anlatıcıya yapılan hitaptan («“X, gel,” dedi bana») okunur; tırnak ve konuşma çizgisi içindeki «benim adım X»
    (bir karakterin sözü) ve kitabın adı sayılmaz. En az iki kanıt ve TEK aday şart; iki aday (bölüm bölüm değişen
    anlatıcı) ya da kanıt yoksa hiçbir şey yapılmaz. Anlatıcı belliyse «Babam» (anlatıcının yakını, tek kayıt) ile
    «<anlatıcı>'nın babası» bir kişidir. «Lokman'ın babası» (anlatıcı Lokman değilse) «Babam» DEĞİLDİR.
K18 adsız etiket: aynı adsız etiket («anne» / «Annesi» / «annesi»; «Kadın» ×4) ve aynı sahiplik (sahipsiz ya da aynı
    sahip) tek kayda katlanır — sayfa aralıkları iç içe geçmiyorsa, aynı sayfada / aynı okuma penceresinde
    değillerse, tür / cinsiyet / yaşam evresi çelişmiyorsa. İç içe geçen iki «Kadın» iki kadındır. «X'in annesi»
    sahibine göre ayrı kalır. Unvan ve görev adları («Sultan», «Paşa», «Vali», «Bakan») etiket sayılmaz: tarihte
    aynı unvanı taşıyan farklı kişilerdir. Kişi etiketi yalnız genel kişi adları ve akrabalık kökleridir; hayvan
    etiketi yalnız kayıtların hepsi hayvansa ve etiket tek sözcükse.
    Ekranda adsız ve en çok iki kez anılan figüran ana karakter listesinde değil «diğer kişiler»de (`is_minor`);
    veri silinmez.
K19 «Ad + abla/abi/teyze…» kaydının hitaptan çıkan yaşı birleşme kararında sayılmaz (`identity.unit_stage`);
    yalnız metnin kendi yaş kanıtı (`text_stage`). Dede/nine kökleri bir kuşaktır, onların evresi sayılır.

Her şey saf fonksiyon: veritabanı, model, kitap yok. `identity_fold` (okunmuş kitap) ve okumanın pencereli kimlik
adımı (`identity.same_name_join`) aynı planı kullanır.
"""
from __future__ import annotations

import re
import unicodedata
from collections import Counter

from .identity import (_GENITIVE, _KIN, _POSSESSIVE_1SG, family_address, incompatible, interleaved,
                       is_relative_label, name_key, qualifier_refusal, same_name_plan, same_name_refusal)

_VOWELS = 'aeıioöuü'
_HARMONY = {'a': 'ı', 'ı': 'ı', 'e': 'i', 'i': 'i', 'o': 'u', 'u': 'u', 'ö': 'ü', 'ü': 'ü'}


# ------------------------------------------------------------------ text
def fold(s: str) -> str:
    """Turkish lower case with punctuation kept (patterns need commas, parentheses, apostrophes)."""
    s = unicodedata.normalize('NFKC', s or '').replace('\xad', '')
    s = s.replace('’', "'").replace('‘', "'").replace('ʼ', "'")
    s = re.sub(r'(\w)-\s*\n\s*(\w)', r'\1\2', s)
    s = s.replace('I', 'ı').replace('İ', 'i').lower()
    return re.sub(r'\s+', ' ', s)


_OPEN, _CLOSE = '“«', '”»'


def split_speech(text: str) -> list[tuple[bool, str]]:
    """[(is_speech, segment)] in order. Speech: inside “…”, «…», "…", and a line opened by a dialogue dash
    («— Benim adım Ekin.»). Unclosed quotes end at the paragraph."""
    out: list[tuple[bool, str]] = []
    for line in (text or '').split('\n'):
        stripped = line.lstrip()
        if stripped[:1] in '—–' or stripped[:2] == '- ':
            out.append((True, line))
            continue
        buf, speech, straight = [], False, False
        for ch in line:
            if not speech and (ch in _OPEN or ch == '"'):
                if buf:
                    out.append((False, ''.join(buf)))
                buf, speech, straight = [ch], True, ch == '"'
                continue
            buf.append(ch)
            if speech and ((ch in _CLOSE and not straight) or (ch == '"' and straight)):
                out.append((True, ''.join(buf)))
                buf, speech = [], False
        if buf:
            out.append((speech, ''.join(buf)))
    return out


def sentences(s: str) -> list[str]:
    return [x for x in re.split(r'(?<=[.!?…])\s+', s) if x.strip()]


class Tagger:
    """Replaces every occurrence of a known written name in folded text by a token \x01k\x02 (k = name index),
    longest names first, so «beatrice» inside «tilki beatrice» is the longer name's (as naming.name_occurrences)."""

    def __init__(self, names: list[str]):
        self.names = names
        alts = sorted(range(len(names)), key=lambda k: -len(names[k]))
        self.index = {names[k]: k for k in alts}
        parts = [r'\s+'.join(re.escape(w) for w in names[k].split()) for k in alts if names[k]]
        self.rx = re.compile(r'(?<!\w)(' + '|'.join(parts) + r')(?!\w)') if parts else None
        self.first = {n.split()[0] for n in names if n}

    def tag(self, s: str) -> str:
        if not self.rx or not (set(re.findall(r'\w+', s)) & self.first):
            return s
        return self.rx.sub(lambda m: '\x01%d\x02' % self.index[re.sub(r'\s+', ' ', m.group(1))], s)


_T = r'\x01(?P<%s>\d+)\x02'
_SUF = r"(?:'(?!n?[ıiuü]n(?!\w))\w+)?"            # an optional case suffix, never the genitive
_NG = _SUF + r"(?!['\w])"                          # the name, not followed by a genitive
_GEN = r"'n?[ıiuü]n(?!\w)"
_SHORT = r'(?:kısaltması|kısaltılmışı|kısaltılmış\s+(?:hali|hâli|adı|biçimi)|kısa\s+(?:hali|hâli|adı|biçimi)|' \
         r'takma\s+adı|lakabı|kısaca\s+söylenişi)'


def _p(s: str) -> re.Pattern:
    return re.compile(s.replace('{X}', _T % 'x').replace('{Y}', _T % 'y'))


#: (rule id, pattern). X and Y are the two written names; every pattern states that they are one person.
ALIAS_PATTERNS: list[tuple[str, re.Pattern]] = [
    ('YANI', _p(r'{X}' + _NG + r'\s*,\s*yani\s*,?\s+{Y}' + _NG)),
    ('PAREN', _p(r'{Y}\s*\(\s*{X}\s*\)')),
    ('DIYE_CAGRILAN', _p(r'{X}\s+diye\s+(?:çağır|seslen|anıl|bilin|tanın|hitap\s+ed)\w*\s+{Y}' + _NG)),
    ('DIYE_SESLENIR', _p(r'{Y}' + _SUF + r'\s+(?:(?:herkes|hep|hepimiz|hepsi|kısaca|sadece|yalnızca)\s+){0,2}'
                         r'{X}\s+diye\s+(?:çağır|seslen|hitap)\w*')),
    ('ASIL_ADI_OLAN', _p(r'(?:asıl|gerçek|tam)\s+(?:adı|ismi)\s+{Y}\s+olan\s+{X}')),
    ('ASIL_ADI', _p(r'{X}' + _GEN + r'\s+(?:asıl|gerçek|tam)\s+(?:adı|ismi)\s*(?:ise|da|de)?\s*,?\s*{Y}' + _NG)),
    ('KISALTMASI_OLAN', _p(r'{Y}(?:' + _GEN + r'|\s+(?:isminin|adının))\s+' + _SHORT + r'\s+olan\s+{X}')),
    ('KISALTMASI', _p(r'{X}' + _NG + r'\s*,?\s*(?:ise\s+)?{Y}' + _GEN + r'\s+' + _SHORT + r'(?!\s+olan)')),
    ('LAKAPLI', _p(r'{X}\s+(?:lakaplı|takma\s+adlı)\s+{Y}' + _NG)),
    ('LAKABI_OLAN', _p(r'(?:lakabı|takma\s+adı)\s+{X}\s+olan\s+{Y}')),
    ('LAKABI', _p(r'{Y}' + _GEN + r'\s+(?:lakabı|takma\s+adı)\s*(?:da|ise)?\s*,?\s*{X}' + _NG)),
]
_ONA_DER = re.compile(r'(?<!\w)ona\s+(?:kısaca\s+|sadece\s+|hep\s+)?' + (_T % 'x')
                      + r'\s+(?:der|derdi|derler|derlerdi|diyor|diyoruz|diyorlar|derdik|deriz|derim|diyordu|'
                      r'diyorduk|diyorlardı)(?!\w)(?!\s+m[iıuü]\w*)')
_COORD = re.compile((_T % 'x') + r"(?:'\w+)?\s+(?:ve|ile|veya|ya\s+da)\s+" + (_T % 'y'))
_TOKEN = re.compile(r'\x01(\d+)\x02')
_TRIGGERS = re.compile(r'yani|\(|diye|adı|ismi|kısalt|kısa |lakap|lakab|takma|ona ')


# ------------------------------------------------------------------ K18 labels
#: Words that name a person by what anyone could be («kadın», «adam», «çocuk»): a label, never a name.
GENERIC_PERSON = frozenset({'kadın', 'adam', 'kız', 'oğlan', 'erkek', 'çocuk', 'bebek', 'genç', 'delikanlı',
                            'yaşlı', 'ihtiyar', 'yabancı', 'kadıncağız', 'adamcağız'})
_KIN_ROOTS = frozenset(k.split()[-1] for k in _KIN) | {'oğul'}


def _possessive_3sg(word: str) -> str:
    """«anne» → «annesi», «kardeş» → «kardeşi», «oğul» → «oğlu»."""
    if word == 'oğul':
        return 'oğlu'
    last = [ch for ch in word if ch in _VOWELS][-1]
    v = _HARMONY[last]
    return word + 's' + v if word[-1] in _VOWELS else word + v


def _strip_3sg(word: str, known: set) -> str:
    """«annesi» → «anne», «kardeşi» → «kardeş» (only to a root in `known`); else the word itself."""
    if word == 'oğlu':
        return 'oğul'
    if len(word) > 3 and word[-2] == 's' and word[-1] in 'ıiuü' and word[-3] in _VOWELS and word[:-2] in known:
        return word[:-2]
    if len(word) > 3 and word[-1] in 'ıiuü' and word[-2] not in _VOWELS and word[:-1] in known:
        return word[:-1]
    return word


def label_key(name: str) -> tuple[str, str] | None:
    """(owner, label) of an unnamed person/animal label, or None. «Annesi» → ('', 'anne'), «anne» → ('', 'anne'),
    «Bee'nin Annesi» → ('bee', 'anne'), «Kadın» → ('', 'kadın'), «Yaşlı kadın» → ('', 'yaşlı kadın'). Not a label:
    a first-person relative («Annem»: anlatıcıya göreli, ayrı kural), a plural, a name with a family address
    («Suna teyze»), anything whose head is not a generic person word or kinship root (unvan, görev, meslek) —
    those return ('', word) only for the animal rule (see `label_group_ok`)."""
    if is_relative_label(name) or family_address(name):
        return None
    words = name_key(name).split()
    if not words or len(words) > 4:
        return None
    owner = ''
    if len(words) >= 3 and words[-2] in _GENITIVE:
        owner, words = ' '.join(words[:-2]), words[-1:]
    head = words[-1]
    if re.search(r'(lar|ler)(ı|i)?$', head):
        return None                                   # «kadınlar»: a group
    root = _strip_3sg(head, GENERIC_PERSON | _KIN_ROOTS)
    return owner, ' '.join(words[:-1] + [root])


#: Words a label may carry before its head («yaşlı kadın», «genç adam»): how anyone may look, never an office.
#: «Kâhya Kadın», «Başkadın», «Hazinedar Usta» are offices of a palace or a guild, held by different people
#: in a history book — not labels to fold.
GENERIC_MODIFIERS = frozenset({'genç', 'yaşlı', 'küçük', 'büyük', 'ihtiyar', 'yabancı', 'güzel', 'şişman', 'zayıf',
                               'uzun', 'kısa', 'sarışın', 'esmer', 'kızıl', 'bir', 'o', 'bu', 'şu', 'öteki',
                               'diğer', 'öbür', 'tanımadığı', 'tanımadığım'})


def _is_person_label(label: str) -> bool:
    words = label.split()
    return words[-1] in GENERIC_PERSON | _KIN_ROOTS and all(w in GENERIC_MODIFIERS for w in words[:-1])


def label_group_ok(label: str, units: list[dict]) -> bool:
    """A person label (generic person word or kinship root) folds; any other single word folds only when every
    record carrying it with a known kind is an animal («Kedi», «Kuş»)."""
    if _is_person_label(label):
        return True
    kinds = {u.get('kind') for u in units if u.get('kind') not in (None, '', 'OTHER', 'UNKNOWN')}
    return len(label.split()) == 1 and kinds == {'ANIMAL'}


# ------------------------------------------------------------------ K18 display
def is_unnamed(name: str, traits: dict | None = None) -> bool:
    """A record without a name: the reading said so (traits.unnamed: the book never writes it as a name;
    name_origin DESCRIPTIVE_LABEL) or the name is a relative / generic label by its form."""
    tr = traits or {}
    if tr.get('unnamed') is not None:
        return bool(tr['unnamed'])
    if tr.get('name_origin') == 'DESCRIPTIVE_LABEL':
        return True
    n = (name or '').strip()
    if not n or n[:1].islower():
        return True
    lk = label_key(n)
    return is_relative_label(n) or bool(lk and _is_person_label(lk[1]))


def is_minor(name: str, traits: dict | None, mentions: int | None, limit: int = 2) -> bool:
    """K18: an unnamed figure mentioned at most `limit` times goes under «diğer kişiler»."""
    return mentions is not None and mentions <= limit and is_unnamed(name, traits)


# ------------------------------------------------------------------ K19 helper: age the text states
_AGE = re.compile(r'(\d{1,3})\s*yaş(?:ında|ındaki|larında)')


def text_stage(quotes: list[str]) -> str | None:
    """Life stage the TEXT states («on iki yaşında», «bebek», «yaşlı»): HUMAN_CHILD / HUMAN_ADULT, None when it
    states none or both."""
    found = set()
    for q in quotes or []:
        f = fold(q)
        for m in _AGE.finditer(f):
            found.add('HUMAN_CHILD' if int(m.group(1)) < 18 else 'HUMAN_ADULT')
        if re.search(r'(?<!\w)(bebek|bebeği|bebekken|çocukken)(?!\w)', f):
            found.add('HUMAN_CHILD')
        if re.search(r'(?<!\w)(yaşlı|ihtiyar|emekli)(?!\w)', f):
            found.add('HUMAN_ADULT')
    return next(iter(found)) if len(found) == 1 else None


# ------------------------------------------------------------------ the plan
class _UF:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, i: int) -> int:
        while self.p[i] != i:
            self.p[i] = self.p[self.p[i]]
            i = self.p[i]
        return i

    def members(self, i: int, n: int) -> list[int]:
        r = self.find(i)
        return [k for k in range(n) if self.find(k) == r]


def _written(u: dict) -> list[str]:
    return [x for x in dict.fromkeys([u['name'], *(u.get('aliases') or [])]) if x]


def _component_refusal(units: list[dict], a: list[int], b: list[int], *, strict_stage: bool = False) -> str | None:
    """Kind / sex / scope / ordinal / father of two components (every member)."""
    bad = incompatible([units[i] for i in a], [units[j] for j in b], life_stages=not strict_stage)
    if bad:
        return bad
    return qualifier_refusal([n for i in a for n in _written(units[i])], [n for j in b for n in _written(units[j])])


def _snippet(t: str, at: int, names: list[str], words: int = 15) -> str:
    """≤15 words of the tagged sentence `t` from just before position `at`, names written back — the record keeps a
    short quote of the sentence, never a page."""
    plain = lambda x: _TOKEN.sub(lambda m: names[int(m.group(1))], x)  # noqa: E731
    before = plain(t[:at]).split()
    return ' '.join((before[-3:] + plain(t[at:]).split())[:words])


def alias_evidence(units: list[dict], pages: dict[int, str], proper=None) -> tuple[list[dict], set]:
    """Every explicit «X = Y» statement of the book between two written names of two records, and the pairs the
    book lists side by side («X ve Y»). Names: each record's name and other names that the book writes as a name
    (`proper`)."""
    names, owners = [], {}
    for i, u in enumerate(units):
        if (u.get('entity_scope') or 'UNKNOWN') in ('COLLECTIVE', 'CONCEPT'):
            continue
        for n in _written(u):
            k = name_key(n)
            if len(k) < 2 or (proper is not None and not proper(n)):
                continue
            if k not in owners:
                owners[k] = set()
                names.append(k)
            owners[k].add(i)
    if not names:
        return [], set()
    tagger = Tagger(names)
    found, coordinated = [], set()
    for page_no in sorted(pages):
        text = fold(pages[page_no])
        if not text:
            continue
        sents = sentences(text)
        tagged = [None] * len(sents)
        for si, s in enumerate(sents):
            if not _TRIGGERS.search(s) and not (' ve ' in s or ' ile ' in s or ' veya ' in s or 'ya da' in s):
                continue
            t = tagged[si] = tagger.tag(s)
            if '\x01' not in t:
                continue
            for m in _COORD.finditer(t):
                x, y = int(m.group('x')), int(m.group('y'))
                coordinated.add(frozenset((names[x], names[y])))
            if not _TRIGGERS.search(s):
                continue
            for rule, rx in ALIAS_PATTERNS:
                for m in rx.finditer(t):
                    x, y = int(m.group('x')), int(m.group('y'))
                    if x != y:
                        found.append({'x': names[x], 'y': names[y], 'rule': rule, 'page': page_no,
                                      'quote': _snippet(t, m.start(), names)})
            for m in _ONA_DER.finditer(t):
                x = int(m.group('x'))
                before = {int(k) for k in _TOKEN.findall(t[:m.start()])} - {x}
                if not before and si > 0:
                    prev = tagged[si - 1] if tagged[si - 1] is not None else tagger.tag(sents[si - 1])
                    before = {int(k) for k in _TOKEN.findall(prev)} - {x}
                if len(before) == 1:
                    found.append({'x': names[x], 'y': names[before.pop()], 'rule': 'ONA_DER', 'page': page_no,
                                  'quote': _snippet(t, m.start(), names)})
    for f in found:
        f['x_units'], f['y_units'] = sorted(owners[f['x']]), sorted(owners[f['y']])
        # a join rests on records' OWN names: another name a reading attached («Salih Bozok» listed on «Mahmut
        # Bey») is no ground to join that record with «Salih»; such a sentence still tells whose name it is
        f['x_canon'] = sorted(i for i in owners[f['x']] if name_key(units[i]['name']) == f['x'])
        f['y_canon'] = sorted(i for i in owners[f['y']] if name_key(units[i]['name']) == f['y'])
    return found, coordinated


# K17 narrator
_SELF = re.compile(r'(?<!\w)(?:(?:benim\s+)?(?:adım|ismim)\s+(?:da\s+)?' + (_T % 'x') + _NG
                   + r"|bana\s+" + (_T % 'y') + r'\s+(?:derler|derlerdi|der|derdi|diyorlar|diyordu|diyorlardı)(?!\w)'
                   + r"|(?:adımı|ismimi)\s+" + (_T % 'z') + r'\s+koy)')
_VOCATIVE = re.compile(r'^\W*' + (_T % 'x') + r'\s*[,!]')
_SPEECH_VERB = re.compile(r'(?<!\w)(dedi|diyor|der|derdi|diye|seslendi|sesleniyor|sordu|soruyor|bağırdı|bağırıyor|'
                          r'fısıldadı|fısıldıyor|söyledi|söylüyor)(?!\w)')


def narrator_evidence(units: list[dict], pages: dict[int, str], proper=None, title: str = '') -> list[dict]:
    """[{name, page, how, quote}]: where the book's narration names its «I». Speech is never the narrator's
    self-naming (a character says «benim adım X»); the book's title is not a sentence of the narration."""
    names, owners = [], {}
    for i, u in enumerate(units):
        if (u.get('entity_scope') or 'UNKNOWN') in ('COLLECTIVE', 'CONCEPT'):
            continue
        for n in _written(u):
            k = name_key(n)
            if len(k) >= 2 and (proper is None or proper(n)) and k not in owners:
                owners[k] = i
                names.append(k)
    if not names:
        return []
    tagger, ft = Tagger(names), fold(title)
    out = []
    for page_no in sorted(pages):
        segs = [(sp, fold(s)) for sp, s in split_speech(pages[page_no])]
        for k, (speech, seg) in enumerate(segs):
            if not speech:
                if not re.search(r'adım|ismim|bana ', seg):
                    continue
                for s in sentences(seg):
                    if ft and len(ft) > 4:
                        # the book's title written anywhere (cover, contents, «Benim Adım Ekin öyle bir hediye…»
                        # naming the book) is the title, not the narrator speaking
                        s = s.replace(ft, ' \x03 ')
                    t = tagger.tag(s)
                    for m in _SELF.finditer(t):
                        x = int(m.group('x') or m.group('y') or m.group('z'))
                        out.append({'name': names[x], 'page': page_no, 'how': 'SELF',
                                    'quote': _snippet(t, m.start(), names)})
                continue
            # «“X, gel,” dedi bana»: the quote opens by calling X, the narration right after says «bana»
            m = _VOCATIVE.match(tagger.tag(seg.lstrip('"“«—–- ')))
            if not m or k + 1 >= len(segs) or segs[k + 1][0]:
                continue
            after = re.findall(r'\w+', segs[k + 1][1])[:6]
            if 'bana' in after and _SPEECH_VERB.search(' '.join(after)):
                out.append({'name': names[int(m.group('x'))], 'page': page_no, 'how': 'ADDRESSED',
                            'quote': ' '.join((seg + ' ' + ' '.join(after)).split()[:15])})
    for e in out:
        e['unit'] = owners[e['name']]
    return out


_KIN_3SG = {}
for _k in _KIN:
    _w = _k.split()
    _one = _POSSESSIVE_1SG.get(_k)
    if _one is None:
        _last = [ch for ch in _k if ch in _VOWELS][-1]
        _one = _k + 'm' if _k[-1] in _VOWELS else _k + _HARMONY[_last] + 'm'
    _KIN_3SG[_one] = ' '.join(_w[:-1] + [_possessive_3sg(_w[-1])])


def link_plan(units: list[dict], pages: dict[int, str] | None = None, proper=None, title: str = '',
              min_narrator_evidence: int = 2) -> dict:
    """Clusters of records that are one person (index lists, largest record first), with every link's rule and
    evidence, the refused pairs, the narrator decision and the other-name conflicts.

    Order: same name (identity.same_name_plan, with the K15 family address rule and the K19 address-stage rule),
    unnamed labels (K18), explicit alias statements (K16), the narrator's relatives (K17). Every join between two
    components is checked against EVERY member of both (kind / sex / scope / ordinal / father): no chaining across
    a conflict."""
    pages = pages or {}
    n = len(units)
    clusters, refused = same_name_plan(units, proper)
    uf = _UF(n)
    links: list[dict] = []
    for g in clusters:
        for i in g[1:]:
            uf.p[uf.find(i)] = uf.find(g[0])
        links.append({'rule': 'SAME_NAME', 'names': [units[i]['name'] for i in g]})

    def join(a: int, b: int, entry: dict, strict_stage: bool = False) -> bool:
        ra, rb = uf.find(a), uf.find(b)
        if ra == rb:
            return False
        why = _component_refusal(units, uf.members(a, n), uf.members(b, n), strict_stage=strict_stage)
        if why:
            refused.append({**{k: v for k, v in entry.items() if k != 'rule'}, 'rule': entry['rule'], 'reason': why})
            return False
        uf.p[rb] = ra
        links.append(entry)
        return True

    # ---- K18: one unnamed label, one owner
    by_label: dict[tuple, list[int]] = {}
    named = {i for g in clusters for i in g}      # already one person by name: not a label
    for i, u in enumerate(units):
        if i in named or (proper is not None and proper(u['name'])):
            continue
        if (u.get('entity_scope') or 'UNKNOWN') in ('COLLECTIVE', 'CONCEPT'):
            continue
        lk = label_key(u['name'])
        if lk:
            by_label.setdefault(lk, []).append(i)
    for (owner, label), idx in by_label.items():
        if len(idx) < 2:
            continue
        if not label_group_ok(label, [units[i] for i in idx]):
            refused.append({'name': units[idx[0]]['name'], 'records': len(idx), 'rule': 'LABEL',
                            'reason': 'LABEL_NOT_A_PERSON_WORD'})
            continue
        groups: list[list[int]] = []
        for i in sorted(idx, key=lambda i: (-units[i].get('n', 0), i)):
            for g in groups:
                why = None
                for j in g:
                    why = (same_name_refusal(units[i], units[j])
                           or incompatible([units[i]], [units[j]])            # labels: no child↔adult guess
                           or ('LABEL_INTERLEAVED' if interleaved(units[i], units[j]) else None))
                    if why:
                        break
                if why is None:
                    g.append(i)
                    break
                refused.append({'name': units[i]['name'], 'with': units[g[0]]['name'], 'rule': 'LABEL',
                                'reason': why})
            else:
                groups.append([i])
        for g in groups:
            for i in g[1:]:
                join(g[0], i, {'rule': 'LABEL', 'names': [units[g[0]]['name'], units[i]['name']],
                               'owner': owner or None}, strict_stage=True)

    # ---- K16: explicit «X = Y» in the book
    found, coordinated = alias_evidence(units, pages, proper) if pages else ([], set())
    alias_links: list[dict] = []
    seen_pairs: set = set()
    for f in found:
        pair = frozenset((f['x'], f['y']))
        if pair in seen_pairs:
            continue
        if pair in coordinated:
            refused.append({'rule': 'ALIAS', 'names': [f['x'], f['y']], 'reason': 'ALIAS_COORDINATED',
                            'page': f['page']})
            seen_pairs.add(pair)
            continue
        if not f['x_canon'] or not f['y_canon']:
            refused.append({'rule': 'ALIAS', 'names': [f['x'], f['y']], 'page': f['page'],
                            'reason': 'ALIAS_NOT_A_RECORD_NAME'})
            seen_pairs.add(pair)
            continue
        roots_x = {uf.find(i) for i in f['x_canon']}
        roots_y = {uf.find(i) for i in f['y_canon']}
        if roots_x & roots_y:
            seen_pairs.add(pair)                       # already one record
            continue
        ok = [(a, b) for a in roots_x for b in roots_y
              if _component_refusal(units, uf.members(a, n), uf.members(b, n), strict_stage=True) is None]
        if len(ok) != 1:
            refused.append({'rule': 'ALIAS', 'names': [f['x'], f['y']], 'page': f['page'],
                            'reason': 'ALIAS_AMBIGUOUS' if ok else 'ALIAS_INCOMPATIBLE'})
            continue
        seen_pairs.add(pair)
        a, b = ok[0]
        entry = {'rule': 'ALIAS', 'pattern': f['rule'], 'names': [f['x'], f['y']], 'page': f['page'],
                 'quote': f['quote']}
        if join(a, b, entry, strict_stage=True):
            alias_links.append(entry)

    # ---- K17: the narrator's relatives
    narrator: dict = {'decided': False}
    labels_1sg = {}
    for i, u in enumerate(units):
        if is_relative_label(u['name']):
            k = ' '.join(w for w in name_key(u['name']).split() if w not in ('benim', 'sevgili', 'canım'))
            labels_1sg.setdefault(k, set()).add(uf.find(i))
    if labels_1sg and pages:
        ev = narrator_evidence(units, pages, proper, title)
        roots = Counter(uf.find(e['unit']) for e in ev)
        if len(roots) > 1:
            narrator = {'decided': False, 'reason': 'NARRATOR_SEVERAL',
                        'candidates': sorted({units[r]['name'] for r in roots})}
        elif not roots or len({e['page'] for e in ev}) < min_narrator_evidence:   # pages, not repeats
            narrator = {'decided': False, 'reason': 'NARRATOR_UNKNOWN', 'evidence': len(ev)}
        else:
            root = next(iter(roots))
            members = uf.members(root, n)
            own = {name_key(x) for i in members for x in _written(units[i])}
            narrator = {'decided': True, 'name': units[max(members, key=lambda i: units[i].get('n', 0))]['name'],
                        'evidence': [{k: e[k] for k in ('page', 'how', 'quote')} for e in ev[:5]],
                        'evidence_count': len(ev)}
            for label, rs in labels_1sg.items():
                third = _KIN_3SG.get(label)
                if not third:
                    continue
                if len(rs) != 1:
                    refused.append({'rule': 'NARRATOR', 'name': label, 'reason': 'RELATIVE_LABEL_NOT_ONE'})
                    continue
                lr = next(iter(rs))
                tw = third.split()
                for j, u in enumerate(units):
                    w = name_key(u['name']).split()
                    if len(w) >= len(tw) + 2 and w[-len(tw):] == tw and w[-len(tw) - 1] in _GENITIVE \
                            and ' '.join(w[:-len(tw) - 1]) in own:
                        join(lr, j, {'rule': 'NARRATOR', 'names': [units[lr]['name'], u['name']],
                                     'narrator': narrator['name']})

    # ---- clusters (largest record first)
    comps: dict[int, list[int]] = {}
    for i in range(n):
        comps.setdefault(uf.find(i), []).append(i)
    out = [sorted(g, key=lambda i: (-units[i].get('n', 0), i)) for g in comps.values() if len(g) > 1]
    statements = [{'names': [f['x'], f['y']]} for f in found if frozenset((f['x'], f['y'])) not in coordinated]
    conflicts = alias_conflicts(units, [sorted(g, key=lambda i: (-units[i].get('n', 0), i)) for g in comps.values()],
                                statements)
    return {'clusters': out, 'refused': refused, 'links': links, 'alias_links': alias_links,
            'narrator': narrator, 'alias_conflicts': conflicts}


def alias_conflicts(units: list[dict], comps: list[list[int]], statements: list[dict]) -> list[dict]:
    """An other-name carried by the records of two people. When the book itself states whose name it is (a K16
    link) and another record merely lists it, that record is wrong: `fix` (owner = the stated person's main
    record; `statements`: every «X = Y» sentence of the book, joined or not — «Küçük Arı» stated as the girl's
    name stays hers even though the fox record that lists it can never join her). Every other case — two records carry it, or one carries another record's own name — is `flag`ged
    only: which of them is right is not written in the book. Unit indices refer to each component's main record
    (`comps` sorted largest first)."""
    comp_of = {i: c for c, g in enumerate(comps) for i in g}
    own: dict[str, set] = {}
    carried: dict[str, set] = {}
    for i, u in enumerate(units):
        own.setdefault(name_key(u['name']), set()).add(comp_of[i])
        for a in u.get('aliases') or []:
            k = name_key(a)
            if k and k != name_key(u['name']):
                carried.setdefault(k, set()).add(comp_of[i])
    stated: dict[str, set] = {}
    for e in statements:
        x, y = e['names']
        for i, u in enumerate(units):
            ks = {name_key(w) for w in _written(u)}
            if y in ks:
                stated.setdefault(x, set()).add(comp_of[i])
            if x in ks:
                stated.setdefault(y, set()).add(comp_of[i])
    out = []
    for k, cs in carried.items():
        st = stated.get(k, set())
        rec = lambda cc: [units[comps[c][0]]['name'] for c in sorted(cc)]  # noqa: E731
        if len(st) == 1 and cs - st:
            o = next(iter(st))
            out.append({'alias': k, 'action': 'fix', 'owner': comps[o][0],
                        'holders': [comps[c][0] for c in sorted(cs - st)], 'records': rec(cs | st)})
            continue
        every = cs | own.get(k, set()) | st
        if len(every) >= 2:
            out.append({'alias': k, 'action': 'flag', 'holders': [comps[c][0] for c in sorted(cs)],
                        'records': rec(every)})
    return out
