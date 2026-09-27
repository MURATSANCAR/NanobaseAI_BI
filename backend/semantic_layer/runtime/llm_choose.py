"""Kapalı küme seçim: bir soru, sabit bir seçenek listesi; cevap listeden biri ve her seçeneğin olasılığı.

Kategori önerisi, e-posta sınıflama, müşteri segmenti, SSS eşleştirme gibi işlerin hepsi aynı biçimdedir:
model serbest metin yazmaz, verilen seçeneklerden birini seçer. Uydurma sınıf imkânsız olur, ve cevabın ne
kadar emin verildiği tek çağrıda okunur.

Nasıl:

* Seçenekler kısa etiketlerle (A, B, C … Z) listelenir; model yalnız etiketi yazar. Etiket tek karakterdir,
  dolayısıyla tek token'dır — seçeneğin kendisi kaç token olursa olsun ("Çocuk Kitapları > Masal").
* İstek `max_tokens=1`, `temperature=0`, `structured_outputs.choice=[etiketler]` (vLLM cevabı etiketlere
  kilitler) ve `logprobs`/`top_logprobs` ile gider. O tek token'ın aday olasılıklarından her etiketin payı
  toplanır ve etiketler arasında normalize edilir: olasılıklar toplamı 1.
* 26'dan çok seçenek varsa eleme turu: seçenekler dengeli gruplara bölünür, her grubun galibi finale
  kalır. Olasılık P(c) = P(grup içinde c) × P(finalde c'nin grubunun galibi) — toplamı yine 1'dir.
  Sayı tavanı yok; tur sayısı seçenek sayısıyla büyür.
* Uç `structured_outputs`/`logprobs` bilmiyorsa (4xx), cevapta olasılık yoksa ya da etiketlerin hiçbiri ilk
  token adayları arasında değilse: yedek yol. Modelin metni etikete ya da seçeneğin kendisine eşlenir,
  `probs=None` döner. Çağıran bunu «emin değil» sayar. Eşlenemezse `choice=None`.
* Model hiç cevap veremezse (bağlantı, zaman aşımı, 5xx) istisna yükselir: bu «emin değil» değil,
  «sonra dene»dir; toplu iş kuyruğa «belirsiz» diye yüzlerce kayıt yazmasın.

Eşik çağırana aittir: bu modül karar vermez, yalnız olasılığı söyler (`Choice.confident(...)`).
Bu dosya modeli çağırmaz; çağrı `QueuedLlm.choose` içinde, kapının sırası ve slotu içinde yapılır.
Kullanım belgesi: docs/analiz/llm-choose.md.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any, Optional, Sequence

#: tek karakter, tek token etiketler. Küçük harf ve rakam eklenmez: "a"/"A" karışır, "10" iki token'dır.
LABELS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"

#: vLLM'in varsayılan `max_logprobs` değeri 20'dir; fazlası 400 döner.
DEFAULT_TOP_LOGPROBS = 20

LOGPROBS, TEXT, NONE, SINGLE = "logprobs", "text", "none", "single"


@dataclass(frozen=True)
class Choice:
    """Bir kapalı küme kararının sonucu.

    choice    seçilen seçeneğin kendisi (çağıranın verdiği metin); eşlenemediyse None
    index     `choices` içindeki sırası; eşlenemediyse None
    probs     seçenek → olasılık, toplamı 1; olasılık okunamadıysa (yedek yol) None
    method    "logprobs" | "text" (yedek yol, olasılık yok) | "none" (cevap eşlenemedi) | "single" (tek seçenek)
    margin    p(seçilen) − en yüksek diğer olasılık; olasılık yoksa None. Eleme turunda eksi olabilir.
    coverage  ilk token olasılık kütlesinin etiketlere düşen payı (0–1); düşükse model başka şey yazmak istemiş
    calls     kaç model çağrısı yapıldı (eleme turları dahil)
    raw       modelin son cevap metni
    error     yapılandırılmış yolun neden kullanılamadığı; kullanıldıysa None
    """

    choice: Optional[str]
    index: Optional[int]
    probs: Optional[dict[str, float]]
    method: str
    margin: Optional[float] = None
    coverage: Optional[float] = None
    calls: int = 1
    raw: str = ""
    error: Optional[str] = None

    @property
    def probability(self) -> Optional[float]:
        """Seçilen seçeneğin olasılığı; olasılık yoksa None."""
        if self.probs is None or self.choice is None:
            return None
        return self.probs.get(self.choice)

    def confident(self, min_prob: float, min_margin: float = 0.0, min_coverage: float = 0.0) -> bool:
        """Çağıranın eşiğiyle: seçim var, olasılık okunmuş, p ≥ min_prob, marj ≥ min_margin ve (istenirse)
        etiket kütlesi ≥ min_coverage. Yedek yol (olasılık yok) ve eşlenemeyen cevap her zaman False —
        «emin değil» kuyruğuna. Tek seçenek (`method="single"`) her eşiği geçer: başka seçenek yoktur."""
        p = self.probability
        if p is None or self.margin is None:
            return False
        if min_coverage > 0 and self.coverage is not None and self.coverage < min_coverage:
            return False
        return p >= min_prob and self.margin >= min_margin

    def as_dict(self) -> dict[str, Any]:
        return {"choice": self.choice, "index": self.index, "probs": self.probs, "method": self.method,
                "probability": self.probability, "margin": self.margin, "coverage": self.coverage,
                "calls": self.calls, "raw": self.raw, "error": self.error}


# ---------------------------------------------------------------------------------------------- girdi
def check_choices(choices: Sequence[str]) -> list[str]:
    """Seçenekler boş olamaz, tekrar edemez (olasılık sözlüğü seçenekle anahtarlanır)."""
    if isinstance(choices, str):
        raise ValueError("choices: metin listesi olmalı, tek metin değil")
    out = [str(c) for c in (choices or [])]
    if not out:
        raise ValueError("choices: en az bir seçenek gerekli")
    if any(not c.strip() for c in out):
        raise ValueError("choices: boş seçenek olamaz")
    seen: set[str] = set()
    for c in out:
        if c in seen:
            raise ValueError(f"choices: tekrar eden seçenek: {c!r}")
        seen.add(c)
    return out


def split_groups(items: Sequence[str], size: int = len(LABELS)) -> list[list[str]]:
    """Dengeli gruplar: 30 seçenek 26+4 değil 15+15 olur — küçük grubun galibi kolay kazanmasın."""
    n = len(items)
    k = max(1, math.ceil(n / size))
    base, extra = divmod(n, k)
    out, at = [], 0
    for i in range(k):
        step = base + (1 if i < extra else 0)
        out.append(list(items[at:at + step]))
        at += step
    return out


def build_messages(prompt: str, choices: Sequence[str], *, system: Optional[str] = None) -> list[dict[str, str]]:
    """Sorunun sonuna etiketli seçenek listesi ve «yalnız harfi yaz» eklenir."""
    labels = LABELS[:len(choices)]
    lines = "\n".join(f"{label}) {_one_line(c)}" for label, c in zip(labels, choices))
    content = (f"{(prompt or '').rstrip()}\n\nSeçenekler:\n{lines}\n\n"
               f"Cevap olarak yalnız seçeneğin harfini yaz ({', '.join(labels)}); başka hiçbir şey yazma.")
    messages = [{"role": "system", "content": system}] if system else []
    messages.append({"role": "user", "content": content})
    return messages


def request_body(labels: Sequence[str], top_logprobs: int = DEFAULT_TOP_LOGPROBS) -> dict[str, Any]:
    """Tek token + aday olasılıkları. `guided_choice` gönderilmez: bu vLLM sürümünde etkisiz."""
    return {"logprobs": True, "top_logprobs": max(1, int(top_logprobs)), "structured_outputs": {"choice": list(labels)}}


# ---------------------------------------------------------------------------------------------- çıktı
def read_logprobs(reply: Any, labels: Sequence[str]) -> tuple[Optional[dict[str, float]], float]:
    """Cevabın ilk token'ındaki adaylardan her etiketin normalize olasılığı ve etiketlerin toplam kütlesi.
    Olasılık yoksa ya da hiçbir etiket aday değilse (None, 0). Hiçbir girdide istisna atmaz."""
    try:
        content = ((reply or {}).get("logprobs") or {}).get("content") or []
        first = content[0] if content else None
    except (AttributeError, TypeError, IndexError):
        return None, 0.0
    if not isinstance(first, dict):
        return None, 0.0
    # Üretilen token çoğu zaman top_logprobs içinde de vardır: ham token metniyle bir kez sayılır.
    seen: dict[str, float] = {}
    for entry in list(first.get("top_logprobs") or []) + [first]:
        if not isinstance(entry, dict) or "token" not in entry:
            continue
        token = str(entry.get("token"))
        if token in seen:
            continue
        try:
            lp = float(entry.get("logprob"))
        except (TypeError, ValueError):
            continue
        if math.isnan(lp):
            continue
        seen[token] = lp
    mass = {label: 0.0 for label in labels}
    for token, lp in seen.items():
        key = token.strip()                 # "A" ile " A" ayrı token'lardır; ikisi de A'nın payıdır
        if key in mass:
            mass[key] += math.exp(lp)
    total = sum(mass.values())
    if total <= 0 or math.isinf(total):
        return None, 0.0
    return {label: m / total for label, m in mass.items()}, min(1.0, total)


_THINK = re.compile(r"<think>.*?(</think>|$)", re.S | re.I)
_EDGE = " \t\r\n.,;:!?\"'`*()[]{}<>"
#: "B) Roman", "B. Roman", "B: ..." — etiketten hemen sonra işaret şart: "A veya B" A sayılmasın
_LEADING_LABEL = re.compile(r"^\(?([A-Z])[).:]")
_SAID_LABEL = re.compile(r"(?:cevap|yanıt|seçenek|seçim|answer|option)\s*[:=]?\s*\(?([A-Z])\b", re.I)


def match_text(text: str, choices: Sequence[str]) -> Optional[int]:
    """Yedek yol: serbest cevap metnini seçeneğe eşler. Yalnız kesin eşleşme — etiketin kendisi
    ("B", "B)", "(B)", "Cevap: B") ya da seçeneğin tamamı (Türkçe büyük/küçük harf farkı gözetmeden).
    "Roman değil" gibi metinde geçen seçenek adı eşleşme sayılmaz. Belirsizse None."""
    labels = LABELS[:len(choices)]
    t = _THINK.sub("", text or "").strip()
    if not t:
        return None
    bare = t.strip(_EDGE)
    if len(bare) == 1 and bare in labels:
        return labels.index(bare)
    # Seçeneğin tamamı etiket kalıbından önce: "E-kitap" yazan model E seçeneğini kastetmiyor.
    wanted = _norm(bare)
    hits = [i for i, c in enumerate(choices) if _norm(c) == wanted]
    if len(hits) == 1:
        return hits[0]
    m = _LEADING_LABEL.match(t.lstrip("*` "))
    if m and m.group(1) in labels:
        return labels.index(m.group(1))
    said = {g for g in _SAID_LABEL.findall(t) if g in labels}
    return labels.index(said.pop()) if len(said) == 1 else None


def decide(labels: Sequence[str], probs: dict[str, float], said: Optional[str]) -> str:
    """En olası etiket; eşitlikte modelin yazdığı, o da yoksa listede önce gelen."""
    best = max(probs.values())
    tied = [label for label in labels if probs[label] == best]
    return said if said in tied else tied[0]


def margin_of(probs: dict[str, float], choice: str) -> float:
    others = [p for c, p in probs.items() if c != choice]
    return probs[choice] - (max(others) if others else 0.0)


def combine_rounds(groups: Sequence[Sequence[str]], group_results: Sequence[Choice], final: Choice) -> Choice:
    """Eleme turlarını tek sonuca indirger. Olasılık: P(c) = P_grup(c) × P_final(grubun galibi); her grubun
    içi 1'e, finalin içi 1'e toplandığından toplam 1'dir. Seçim finalin seçimidir (doğrudan karşılaştırma);
    olasılığı birleşik değerdir ve marjı eksi çıkabilir — o zaman `confident` False döner."""
    calls = sum(r.calls for r in group_results) + final.calls
    error = next((r.error for r in list(group_results) + [final] if r.error), None)
    choices = [c for g in groups for c in g]
    index = choices.index(final.choice) if final.choice is not None else None
    have_probs = final.probs is not None and all(r.probs is not None for r in group_results if r.choice is not None)
    if final.choice is None or not have_probs:
        method = NONE if final.choice is None else TEXT
        return Choice(final.choice, index, None, method, None, None, calls, final.raw, error)
    probs: dict[str, float] = {}
    for group, result in zip(groups, group_results):
        through = final.probs.get(result.choice, 0.0) if result.choice is not None else 0.0
        for c in group:
            probs[c] = (result.probs or {}).get(c, 0.0) * through
    total = sum(probs.values())
    if total > 0:
        probs = {c: p / total for c, p in probs.items()}   # eşlenemeyen grup varsa kalan kütle yeniden dağılır
    coverages = [r.coverage for r in list(group_results) + [final] if r.coverage is not None]
    return Choice(final.choice, index, probs, LOGPROBS, margin_of(probs, final.choice),
                  min(coverages) if coverages else None, calls, final.raw, error)


def _one_line(text: str) -> str:
    return " ".join(str(text).split())


def _norm(text: str) -> str:
    """Türkçe küçük harf: "I".lower() "i" verir, doğrusu "ı"; "İ".lower() noktalı i artığı bırakır."""
    t = str(text).replace("İ", "i").replace("I", "ı").lower()
    return " ".join(t.strip(_EDGE).split())
