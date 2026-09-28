"""Zeki AI metin güvenliği — tek yer (ortak yapı taşları 1, 2, 3; docs/analiz/ai-firsatlari/README.md).

1. **Sayı denetçisi** (`unsupported`, `numbers_ok`, `verify`): model metnindeki her sayı verilen olgularda geçmeli.
   Rakamı model üretmez; model yalnız olguları anlatır. Türkçe yazımlar tanınır: «1.234,5», «12,5», «%12», «yüzde 12»,
   «848,1 Mn ₺», «3 milyon», «22.09.2026», «2026-09-22», «1 Ekim 2026». Karşılaştırma değer üzerindendir: metindeki
   sayı olgudaki bir değerin yazıldığı basamağa yuvarlanmış hâli olabilir («848,1 Mn» ↔ 848.110.178,82; «%43» ↔ 42,7).
   Tarih bütün olarak (gün-ay-yıl) ya da parçaları olgularda geçiyorsa kabul edilir («1 Ekim 2026» ↔ «01.10.2026»).
   Eski kopyaların hepsi buraya bağlandı (`marketing.guard`, saha/bayi/müşteri `numbers_ok`, risk/kurul
   `foreign_numbers`, okul, kargo, tedarik, dağıtım/stok bülteni, destek taslağı, e-posta taslağı, İK mektubu, ihale
   özeti, pazarlama kreatif denetimi, pazar özeti); eski adlar ince sarmalayıcı olarak kalır.
2. **Olgu yorumlayıcı** (`interpret`): «bu olguları N cümleyle anlat». Model LLM kapısından (`rt.llm_for(modül,
   öncelik)`) çağrılır; çıktı 1'den geçmezse, model yoksa ya da cevap vermezse **kural metni** döner ve nedeni yazılır.
   Dönen kaynak «zeki» ya da «kural»dır; ekranda «Zeki AI» etiketi yalnız «zeki»de gösterilir.
3. **Kişisel veri maskesi** (`mask_personal`): modele giden serbest metindeki e-posta, telefon, IBAN, kart, T.C. kimlik
   no (isteğe bağlı bağlantı ve uzun numara). Destek (M51), kurumsal e-posta (H4), İK (M55/M56/M57/M58), okur (M37) ve
   pazar yeri (M40–M42) aynı işlevi kullanır; yer tutucu adları çağıranın eski biçimiyle kalır.

Saf modül: veritabanına, ağa, modele kendisi gitmez (model nesnesi çağırandan gelir).
"""
from __future__ import annotations

import bisect
import json
import logging
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Iterable, Optional

log = logging.getLogger(__name__)

# ================================================================================ Türkçe harf katlama ve teknoloji adı

_FOLD = str.maketrans("İIıŞşĞğÜüÖöÇçÂâÎîÛû’‘`´", "iiissgguuooccaaiiuu''''")

#: Ekrana ve ekrana giden metne yazılmayan teknoloji/model/sağlayıcı adları (ürün adı «Zeki AI»dır).
TECH_NAMES = (
    "qwen", "vllm", "llama", "ollama", "openai", "chatgpt", "gpt-", "gpt4", "gpt 4", "gpt5", "claude", "anthropic", "gemini",
    "mistral", "timesfm", "temporal", "real-esrgan", "typst", "ghostscript", "hugging face", "huggingface", "transformer",
    "büyük dil modeli", "buyuk dil modeli", "dil modeli", "llm",
)


def fold(s: Any) -> str:
    """Küçük harf + Türkçe harf katlama + boşluk sadeleştirme (karşılaştırma içindir, ekrana yazılmaz)."""
    return " ".join(str(s or "").translate(_FOLD).lower().split())


def has_tech_name(s: Any) -> bool:
    f = fold(s)
    return any(re.search(r"(?<![a-z0-9])" + re.escape(n), f) for n in TECH_NAMES)


def strip_thinking(s: Any) -> str:
    """Model cevabındaki düşünme bloğunu atar."""
    return re.sub(r"<think>.*?</think>", "", str(s or ""), flags=re.S).strip()


# ================================================================================ 1. sayı denetçisi

#: Ölçek sözcükleri (katlanmış). «848,1 Mn ₺» = 848.100.000.
SCALES = {"bin": 1e3, "milyon": 1e6, "mn": 1e6, "mio": 1e6, "milyar": 1e9, "mlr": 1e9, "mr": 1e9, "trilyon": 1e12}

_DATE_ISO = r"\d{4}-\d{1,2}-\d{1,2}(?:[T ]\d{1,2}:\d{2}(?::\d{2})?)?"
_DATE_TR = r"\d{1,2}[./]\d{1,2}[./]\d{4}"
_THOUSAND_SP = "[   ]"
_TOKEN = re.compile(
    rf"(?P<date>(?<![\d.,/-])(?:{_DATE_ISO}|{_DATE_TR})(?![\d/]|[.,]\d))"
    rf"|(?P<num>(?<![\d.,])(?:\d{{1,3}}(?:\.\d{{3}})+(?:,\d+)?|\d{{1,3}}(?:,\d{{3}})+(?:\.\d+)?"
    rf"|\d{{1,3}}(?:{_THOUSAND_SP}\d{{3}})+(?:,\d+)?|\d+(?:[.,]\d+)?)(?!\d))"
)
_TAIL_WORD = re.compile(r"\s*([a-zçğıöşüâîû]+)")
_PCT_BEFORE = re.compile(r"(?:%\s*|yüzde\s+|yuzde\s+)$", re.I)
_PCT_AFTER = re.compile(r"\s*%")


def parse_number(tok: str) -> list[tuple[float, int]]:
    """Bir sayı yazımının olası değerleri ve ondalık basamağı. «12.345» hem 12345 (TR binlik) hem 12,345 (EN ondalık)
    olabilir; ikisi de döner, karar olgularla karşılaştırmada verilir."""
    t = re.sub(r"[   ]", "", tok).lstrip("+")
    out: list[tuple[float, int]] = []
    neg = t.startswith("-")
    t = t.lstrip("-")
    if not t:
        return out

    def add(s: str, dec: int) -> None:
        try:
            v = float(s)
        except ValueError:
            return
        out.append((-v if neg else v, dec))

    if "," in t and "." in t:
        if t.rfind(",") > t.rfind("."):      # 1.234,5 (TR)
            add(t.replace(".", "").replace(",", "."), len(t) - t.rfind(",") - 1)
        else:                                # 1,234.5 (EN)
            add(t.replace(",", ""), len(t) - t.rfind(".") - 1)
    elif "," in t:
        parts = t.split(",")
        add(t.replace(",", "."), len(parts[-1]) if len(parts) == 2 else 0)            # 12,5 (TR ondalık)
        if all(len(p) == 3 for p in parts[1:]):
            add(t.replace(",", ""), 0)                                                  # 12,345 (EN binlik)
    elif "." in t:
        parts = t.split(".")
        if all(len(p) == 3 for p in parts[1:]):
            add(t.replace(".", ""), 0)                                                  # 12.345 (TR binlik)
        if len(parts) == 2:
            add(t, len(parts[1]))                                                       # 12.5 (EN ondalık)
    else:
        add(t, 0)
    return out


@dataclass
class Num:
    """Metindeki bir sayı ya da tarih."""
    text: str
    start: int
    end: int
    kind: str                                   # sayi | tarih
    values: list[tuple[float, int]] = field(default_factory=list)
    scale: float = 1.0
    percent: bool = False
    day: Optional[tuple[int, int, int]] = None  # tarih: (yıl, ay, gün)
    parts: list[str] = field(default_factory=list)   # boşlukla binlik ayrılmış yazımın parçaları


def _date_of(s: str) -> Optional[tuple[int, int, int]]:
    m = re.match(r"(\d{4})-(\d{1,2})-(\d{1,2})", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    else:
        m = re.match(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", s)
        if not m:
            return None
        d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    return (y, mo, d) if 1 <= mo <= 12 and 1 <= d <= 31 else None


def tokens(text: Any) -> list[Num]:
    """Metindeki sayılar ve tarihler (yazım, olası değerler, ölçek sözcüğü, yüzde işareti)."""
    s = str(text or "")
    out: list[Num] = []
    for m in _TOKEN.finditer(s):
        raw = m.group(0)
        if m.group("date"):
            day = _date_of(raw)
            if day:
                out.append(Num(raw, m.start(), m.end(), "tarih", [], 1.0, False, day))
                continue
            # geçersiz tarih («31.13.2026»): parçaları ayrı sayı sayılır
            for p in re.finditer(r"\d+", raw):
                out.append(Num(p.group(0), m.start() + p.start(), m.start() + p.end(), "sayi", [(float(p.group(0)), 0)]))
            continue
        tail = _TAIL_WORD.match(s[m.end(): m.end() + 16].translate(_FOLD).lower())
        scale = SCALES.get(tail.group(1), 1.0) if tail else 1.0
        before = s[max(0, m.start() - 8): m.start()]
        pct = bool(_PCT_BEFORE.search(before) or _PCT_AFTER.match(s[m.end(): m.end() + 3]))
        parts = re.split(_THOUSAND_SP, raw) if re.search(_THOUSAND_SP, raw) else []
        out.append(Num(raw, m.start(), m.end(), "sayi", parse_number(raw), scale, pct, None, parts))
    return out


def _flatten(facts: Any, out_text: list[str], out_vals: list[float]) -> None:
    if facts is None or isinstance(facts, bool):
        return
    if isinstance(facts, (int, float)):
        if facts == facts:           # NaN değil
            out_vals.append(float(facts))
        return
    if isinstance(facts, (datetime, date)):
        out_text.append(facts.isoformat())
        return
    if isinstance(facts, dict):
        for k, v in facts.items():
            out_text.append(str(k))
            _flatten(v, out_text, out_vals)
        return
    if isinstance(facts, (list, tuple, set, frozenset)):
        for v in facts:
            _flatten(v, out_text, out_vals)
        return
    out_text.append(str(facts))


_DM = re.compile(r"^(\d{1,2})[./](\d{2})$")


class Facts:
    """Olgulardaki değerlerin dizini. Olgular metin, sayı, sözlük ya da liste olabilir (iç içe). Sözlüğün anahtarları
    da metin sayılır. Bir kez kurulur, çok metin denetlenir."""

    def __init__(self, facts: Any = ()):
        texts: list[str] = []
        vals: list[float] = []
        _flatten(facts, texts, vals)
        keys: set[str] = set()
        days: set[tuple[int, int, int]] = set()
        day_month: set[tuple[int, int]] = set()
        for t in texts:
            for n in tokens(t):
                if n.kind == "tarih" and n.day:
                    y, mo, d = n.day
                    days.add(n.day)
                    day_month.add((mo, d))
                    vals.extend((float(y), float(mo), float(d)))
                    continue
                for v, _dec in n.values:
                    vals.append(abs(v))
                    if n.scale != 1.0:
                        vals.append(abs(v) * n.scale)
                    if n.percent:
                        vals.append(abs(v) / 100.0)
                for p in n.parts:
                    vals.append(float(p))
                keys.add(_key(n.text))
                dm = _DM.match(n.text)
                if dm and 1 <= int(dm.group(1)) <= 31 and 1 <= int(dm.group(2)) <= 12:
                    d, mo = int(dm.group(1)), int(dm.group(2))
                    day_month.add((mo, d))
                    vals.extend((float(d), float(mo)))
        for v in list(vals):
            vals.append(abs(v))
        self.values = sorted(set(round(v, 9) for v in vals))
        self.keys = keys
        self.days = days
        self.day_month = day_month

    def has(self, value: float, tol: float) -> bool:
        v = abs(value)
        i = bisect.bisect_left(self.values, v - tol - 1e-9)
        return i < len(self.values) and self.values[i] <= v + tol + 1e-9

    def supports(self, n: Num, *, free_upto: Optional[float] = None, free_years: bool = False) -> bool:
        if n.kind == "tarih":
            y, mo, d = n.day  # type: ignore[misc]
            if n.day in self.days or (y, mo, d) in self.days:
                return True
            if free_years and 1900 <= y <= 2100 and (mo, d) in self.day_month:
                return True
            return all(self.has(float(x), 0.0) or (free_upto is not None and x <= free_upto) or
                       (free_years and x == y and 1900 <= y <= 2100) for x in (y, mo, d))
        for v, dec in n.values:
            tol = 0.5 * (10 ** -dec)
            if self.has(v * n.scale, tol * n.scale) or self.has(v, tol):
                return True
            if n.percent and self.has(v / 100.0, tol / 100.0):
                return True
            if free_upto is not None and abs(v) <= free_upto:
                return True
            if free_years and dec == 0 and n.scale == 1.0 and not n.percent and 1900 <= abs(v) <= 2100:
                return True
        if _key(n.text) in self.keys:
            return True
        dm = _DM.match(n.text)
        if dm and (int(dm.group(2)), int(dm.group(1))) in self.day_month:
            return True
        if n.parts:   # «12 345»: bütün hâliyle tutmadıysa parçalar ayrı ayrı olgularda olmalı
            return all(self.supports(Num(p, 0, 0, "sayi", [(float(p), 0)]), free_upto=free_upto, free_years=free_years)
                       for p in n.parts)
        return False


def _key(s: str) -> str:
    """Eski denetçilerin yazım anahtarı: ayraçlar atılır («1.250» = «1250», «12,5» = «1.25»); ayraçsız tam sayıda baştaki
    sıfır yok sayılır («09» = «9»). «0,5» ile «5» aynı sayılmaz."""
    k = re.sub(r"[.,\s  ]", "", s)
    return (k.lstrip("0") or "0") if k == s else k


def as_facts(facts: Any) -> Facts:
    return facts if isinstance(facts, Facts) else Facts(facts)


def unsupported(text: Any, facts: Any, *, free_upto: Optional[float] = None, free_years: bool = False) -> list[str]:
    """Metinde geçip olgularda karşılığı olmayan sayıların yazımları (sırasıyla, tekrarsız).

    `free_upto`: bu değere kadar olan sayılar serbest (ör. risk brifinginde ≤ 31: gün, çeyrek, sıra).
    `free_years`: 1900–2100 arası tam sayılar yıl sayılır, serbest (pazar özeti)."""
    idx = as_facts(facts)
    bad: list[str] = []
    for n in tokens(text):
        if not idx.supports(n, free_upto=free_upto, free_years=free_years) and n.text not in bad:
            bad.append(n.text)
    return bad


def numbers_ok(text: Any, facts: Any, **kw: Any) -> bool:
    """Metindeki her sayı olgularda geçiyor mu."""
    return not unsupported(text, facts, **kw)


def verify(text: Any, facts: Any, *, max_chars: Optional[int] = None, allow_tech_names: bool = False,
           **kw: Any) -> Optional[str]:
    """Olgular + model metni → denetlenmiş metin ya da None. Düşünme bloğu atılır; boş metin, teknoloji adı ya da
    olgularda olmayan sayı varsa None (çağıran kural metnini kullanır). `max_chars` aşılırsa son tam cümlede kesilir."""
    t = strip_thinking(text)
    if not t:
        return None
    if not allow_tech_names and has_tech_name(t):
        return None
    if unsupported(t, facts, **kw):
        return None
    return clip_sentences(t, max_chars) if max_chars else t


_SENT = re.compile(r"(?<=[.!?…])\s+(?=\S)")


def sentences(text: str) -> list[str]:
    return [s.strip() for s in _SENT.split(text or "") if s.strip()]


def clip_sentences(text: str, max_chars: int) -> str:
    if len(text) <= max_chars:
        return text
    out = ""
    for s in sentences(text):
        if len(out) + len(s) + 1 > max_chars:
            break
        out = (out + " " + s).strip()
    return out or text[:max_chars]


def drop_unsupported_sentences(text: Any, facts: Any, **kw: Any) -> tuple[str, list[str]]:
    """Cümle düzeyinde denetim: olgularda olmayan sayı taşıyan cümle düşer. Dönen: (kalan metin, düşen cümleler)."""
    idx = as_facts(facts)
    kept, dropped = [], []
    for s in sentences(strip_thinking(text)):
        (dropped if unsupported(s, idx, **kw) else kept).append(s)
    return " ".join(kept), dropped


# ================================================================================ 2. olgu yorumlayıcı

DEFAULT_SYSTEM = ("Sen Zeki AI'sın; Timaş Yayınları'nın iç ekranları için verilen olguları sade Türkçeyle anlatırsın. "
                  "Yalnız verilen olgulardaki sayıları ve tarihleri aynen (ya da aynı değeri yuvarlayarak) kullan; yeni "
                  "sayı, oran, tarih, tahmin ya da neden uydurma; hesap yapma. Olgularda olmayan bir neden bilinmiyorsa "
                  "söyleme. Başlık, madde işareti ve tablo kullanma; düz paragraf yaz. Kendinden, yazılımdan ya da "
                  "teknolojiden söz etme.")


@dataclass
class Interpretation:
    metin: str
    kaynak: str                     # zeki | kural
    neden: Optional[str] = None     # kural metnine düşüldüyse nedeni (ekranda «kural metni» notu)
    olgular: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"metin": self.metin, "kaynak": self.kaynak, "neden": self.neden}


def facts_text(facts: Any) -> str:
    """Modele giden olgu metni: sözlük/liste JSON, metin olduğu gibi."""
    if isinstance(facts, str):
        return facts
    if isinstance(facts, (list, tuple)) and all(isinstance(x, str) for x in facts):
        return "\n".join(f"- {x}" for x in facts)
    return json.dumps(facts, ensure_ascii=False, default=str, indent=1)


def model_for(rt: Any, module: str, priority: Optional[int] = None) -> Any:
    """LLM kapısından modül adına model (öncelikli). Model tanımlı değilse None. `LlmClient` doğrudan kurulmaz."""
    if rt is None or not hasattr(rt, "llm_for"):
        return None
    try:
        return rt.llm_for(module, priority)
    except Exception as e:  # noqa: BLE001 — model yoksa kural metni
        log.info("zeki_text: %s için model alınamadı: %s", module, e)
        return None


def _ask(llm: Any, messages: list[dict[str, str]], max_tokens: int, temperature: float) -> str:
    if hasattr(llm, "chat"):
        try:
            return str(llm.chat(messages, max_tokens=max_tokens, temperature=temperature) or "")
        except TypeError:           # anahtar sözcük almayan istemci
            return str(llm.chat(messages) or "")
    return str(llm(messages) or "")


def interpret(facts: Any, rule_text: str, *, llm: Any = None, rt: Any = None, module: Optional[str] = None,
              priority: Optional[int] = None, task: str = "Bu olguları 3–5 cümleyle anlat.", system: Optional[str] = None,
              min_sentences: int = 1, max_sentences: int = 5, max_chars: int = 1500, max_tokens: int = 500,
              temperature: float = 0.2, free_upto: Optional[float] = None, free_years: bool = False,
              check_facts: Any = None) -> Interpretation:
    """Olguları model ile anlatır; olmazsa kural metni.

    `llm`: LLM kapısı sarmalayıcısı (`.chat`) ya da `messages → metin` çağrılabilir. Verilmezse `rt.llm_for(module,
    priority)` kullanılır. `check_facts`: sayı denetiminde olgulara ek kaynak (ör. kural metni) — verilmezse olgular +
    kural metni. Dönen `kaynak` «zeki» yalnız model metni bütün denetimlerden geçtiyse."""
    rule = (rule_text or "").strip()
    ftxt = facts_text(facts)
    model = llm if llm is not None else (model_for(rt, module, priority) if module else None)
    if model is None:
        return Interpretation(rule, "kural", "model-yok", ftxt)
    messages = [{"role": "system", "content": system or DEFAULT_SYSTEM},
                {"role": "user", "content": f"{task}\nEn az {min_sentences}, en çok {max_sentences} cümle.\n\nOLGULAR:\n{ftxt}"}]
    try:
        raw = _ask(model, messages, max_tokens, temperature)
    except Exception as e:  # noqa: BLE001 — model cevap vermezse kural metni
        log.info("zeki_text: model cevap vermedi (%s): %s", module or "-", e)
        return Interpretation(rule, "kural", "model-cevap-vermedi", ftxt)
    text = strip_thinking(raw)
    if not text:
        return Interpretation(rule, "kural", "bos-cevap", ftxt)
    if has_tech_name(text):
        return Interpretation(rule, "kural", "teknoloji-adi", ftxt)
    idx = Facts([facts, rule] if check_facts is None else [facts, check_facts])
    bad = unsupported(text, idx, free_upto=free_upto, free_years=free_years)
    if bad:
        return Interpretation(rule, "kural", "olgu-disi-sayi: " + ", ".join(bad[:10]), ftxt)
    sents = sentences(text)
    if len(sents) > max_sentences:
        text = " ".join(sents[:max_sentences])
    return Interpretation(clip_sentences(text, max_chars), "zeki", None, ftxt)


# ================================================================================ 3. kişisel veri maskesi

EMAIL = re.compile(r"[\w.%+\-]+@[\w\-]+(?:\.[\w\-]+)*\.[A-Za-z]{2,}")
URL = re.compile(r"(https?://|www\.)\S+", re.I)
IBAN = re.compile(r"\bTR\s?\d{2}(?:\s?\d{4}){5}\s?\d{2}\b", re.I)
CARD = re.compile(r"(?<!\d)(?:\d{4}[\s\-]?){3}\d{4}(?!\d)")
TCKN = re.compile(r"(?<!\d)([1-9]\d{10})(?!\d)")
#: Türkiye telefonu (sıkı): cep önekli/öneksiz, sabit hat yalnız +90 / 0 önekiyle. Yıl, adet, stok kodu gibi sayılara
#: ve öneksiz 10 haneli kodlara dokunmaz (okur verisi: kayıt/stok numaraları bozulmasın).
PHONE_STRICT = re.compile(
    r"(?<!\d)(?:\+?90[\s\-.]?|0)?\(?5\d{2}\)?[\s\-.]?\d{3}[\s\-.]?\d{2}[\s\-.]?\d{2}(?!\d)"
    r"|(?<!\d)(?:\+?90[\s\-.]?|0)\s?\(?[2-4]\d{2}\)?[\s\-.]?\d{3}[\s\-.]?\d{2}[\s\-.]?\d{2}(?!\d)")
#: Türkiye telefonu (geniş, varsayılan): sıkı kalıp + öneksiz sabit hat («212 123 45 67»; serbest yazışma metni).
PHONE = re.compile(
    r"(?<![\w])(?:\+?90[\s\-.]?)?\(?0?[2-5]\d{2}\)?[\s\-.]?\d{3}[\s\-.]?\d{2}[\s\-.]?\d{2}(?!\d)|" + PHONE_STRICT.pattern)
#: Ayraçlı uzun numara (pazar yeri metinlerinde sipariş/telefon/kimlik parçası): 10+ hane.
LOOSE_NUMBER = re.compile(r"(\+?\d[\d\s().-]{8,}\d)")
LONG_NUMBER = re.compile(r"\b\d{10,}\b")

#: Yer tutucular (varsayılan: M51 destek biçimi).
LABELS = {"email": "[e-posta]", "url": "[bağlantı]", "iban": "[IBAN]", "card": "[kart]", "tckn": "[kimlik no]",
          "phone": "[telefon]", "number": "[numara]"}
#: «… gizlendi» biçimi (okur, İK).
LABELS_HIDDEN = {k: v[:-1] + " gizlendi]" for k, v in LABELS.items()}
DEFAULT_KINDS = ("email", "iban", "card", "tckn", "phone")
_ORDER = ("email", "url", "iban", "card", "tckn", "phone", "number")


def tckn_valid(s: str) -> bool:
    """T.C. kimlik numarası sağlaması."""
    d = [int(ch) for ch in s if ch.isdigit()]
    if len(d) != 11 or d[0] == 0:
        return False
    if ((sum(d[0:9:2]) * 7 - sum(d[1:8:2])) % 10) != d[9]:
        return False
    return sum(d[:10]) % 10 == d[10]


def mask_personal(text: Any, *, kinds: Iterable[str] = DEFAULT_KINDS, labels: Optional[dict[str, str]] = None,
                  tckn: str = "any", phone: str = "broad", counts: Optional[dict[str, int]] = None) -> str:
    """Serbest metindeki kişisel veriyi yer tutucuyla değiştirir. Modele giden her serbest metin buradan geçer.

    `kinds`: email, url, iban, card, tckn, phone, number (ayraçlı 10+ hane ve uzun numara). `tckn`: «any» 11 haneli
    her numara, «checksum» yalnız sağlaması tutan. `phone`: «broad» (öneksiz sabit hat dahil) ya da «strict».
    `counts` verilirse tür → gizlenen sayısı eklenir. Ad soyad bu işlevle ayıklanmaz (ad maskesi rehberle yapılır:
    `hr_engagement_text.mask_names`)."""
    lab = {**LABELS, **(labels or {})}
    want = set(kinds)
    s = str(text or "")

    def bump(kind: str, n: int) -> None:
        if counts is not None and n:
            counts[kind] = counts.get(kind, 0) + n

    for kind in _ORDER:
        if kind not in want:
            continue
        if kind == "tckn":
            def _t(m: re.Match) -> str:
                if tckn == "checksum" and not tckn_valid(m.group(1)):
                    return m.group(0)
                bump("tckn", 1)
                return lab["tckn"]
            s = TCKN.sub(_t, s)
            continue
        if kind == "number":
            def _n(m: re.Match) -> str:
                if sum(ch.isdigit() for ch in m.group(0)) >= 10:
                    bump("number", 1)
                    return lab["number"]
                return m.group(0)
            s = LOOSE_NUMBER.sub(_n, s)
            s, k = LONG_NUMBER.subn(lab["number"], s)
            bump("number", k)
            continue
        rx = {"email": EMAIL, "url": URL, "iban": IBAN, "card": CARD,
              "phone": PHONE_STRICT if phone == "strict" else PHONE}[kind]
        s, k = rx.subn(lab[kind], s)
        bump(kind, k)
    return s


def has_personal(text: Any, kinds: Iterable[str] = ("email", "phone")) -> bool:
    s = str(text or "")
    rx = {"email": EMAIL, "url": URL, "iban": IBAN, "card": CARD, "phone": PHONE, "tckn": TCKN}
    return any(rx[k].search(s) for k in kinds if k in rx)


def mask_address(addr: Any) -> str:
    """E-posta adresinin gösterim/istem biçimi: «a***@alan.com» (alan adı sınıflamada işe yarar, kişi görünmez)."""
    local, _, dom = str(addr or "").partition("@")
    if not dom:
        return "***"
    return (local[:1] + "***@" + dom)[:200]

