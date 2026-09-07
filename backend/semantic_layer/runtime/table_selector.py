"""Which of the candidate tables a question actually needs.

Retrieval hands back everything it scored above a floor. On this deployment that is ten tables for a
question that needs one: the lexical index sees "ciro" in a column of every table that has ever held
money, and each one arrives with its columns, its keys and its period note attached. The right table
is in there — recall is 1.00 — but so are nine others, and a model reading them all writes a join
nobody asked for and returns a plausible number from the wrong place.

So a smaller, cheaper model reads the shortlist first and says which of them the question is about.
This is the step the schema-linking literature keeps arriving at (CHESS calls it table pruning) and
the reason a 3B model with the right ten tables beats a large one with four hundred.

Three properties matter more than the selection itself:

  * A table the resolver placed is never up for selection. Those came from the question's own terms
    matched against certified vocabulary — they are established, not proposed, and a selector that
    can discard them can discard the answer.
  * A name the model invents is dropped. It picks from the shortlist or it picks nothing.
  * Any failure keeps everything. A timeout, a truncated reply, malformed JSON — the prompt goes out
    as it would have without a selector. Losing the right table to a parse error is a worse failure
    than sending nine extra tables, because it is silent and the answer still looks like an answer.
"""
from __future__ import annotations

import json
import logging
import re
import time
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

log = logging.getLogger(__name__)

_JSON = re.compile(r"\{.*\}", re.S)

SYSTEM = (
    "Sen bir veritabanı şema seçicisin. Sana bir soru ve aday tablo listesi verilir. "
    "Soruyu yanıtlamak için GEREKEN tabloları seç — gerekmeyeni alma.\n"
    "Kurallar:\n"
    "- Yalnız listedeki adları kullan. Liste dışı ad uydurma.\n"
    "- Bir tabloyu yalnız soruya doğrudan katkısı varsa seç: ölçü, kırılım, filtre ya da zorunlu bağlantı.\n"
    "- Hiçbir aday soruyu karşılamıyorsa decision NONE ver ve tables boş kalsın.\n"
    "- Yalnız JSON döndür, başka metin yazma:\n"
    '{"decision":"SELECT","tables":[{"name":"X","reason":"..."}]}'
)


@dataclass(frozen=True)
class Selection:
    """What the selector decided, and enough about it to audit the decision after the fact."""
    tables: list[str]
    decision: str                                  # SELECT | NONE | KEPT
    reasons: dict[str, str] = field(default_factory=dict)
    dropped: list[str] = field(default_factory=list)
    invented: list[str] = field(default_factory=list)
    ms: int = 0
    note: str = ""

    @property
    def applied(self) -> bool:
        return self.decision in ("SELECT", "NONE")


def _parse(text: str) -> Optional[dict]:
    m = _JSON.search(text or "")
    if not m:
        return None
    try:
        out = json.loads(m.group(0))
    except json.JSONDecodeError:
        return None
    return out if isinstance(out, dict) else None


class TableSelector:
    """Narrows an ordered shortlist. Construct with the small model; `pinned` never leaves the list."""

    def __init__(self, llm, *, max_reason_chars: int = 120):
        self.llm = llm
        self.max_reason_chars = max_reason_chars

    def _shortlist(self, candidates: Sequence[str], describe: Callable[[str], str]) -> str:
        lines = []
        for name in candidates:
            note = (describe(name) or "").strip().replace("\n", " ")
            lines.append(f"- {name}: {note[:200]}" if note else f"- {name}")
        return "\n".join(lines)

    def select(self, question: str, candidates: Sequence[str], describe: Callable[[str], str],
               *, pinned: Sequence[str] = ()) -> Selection:
        cands = [c for c in candidates]
        keep = [c for c in pinned if c in cands]
        # Nothing to narrow: one candidate, or every candidate already established by the resolver.
        if len(cands) <= 1 or len(keep) == len(cands):
            return Selection(list(cands), "KEPT", note="narrowing not needed")

        offered = [c for c in cands if c not in keep]
        prompt = [f"Soru: {question}", ""]
        if keep:
            prompt.append("Zaten seçilmiş (bunları tekrar yazma, kesin kullanılacak):\n" +
                          "\n".join(f"- {k}" for k in keep) + "")
        prompt.append("Aday tablolar:\n" + self._shortlist(offered, describe))

        t0 = time.perf_counter()
        try:
            text = self.llm.chat([{"role": "system", "content": SYSTEM},
                                  {"role": "user", "content": "\n".join(prompt)}])
        except Exception as exc:                                    # noqa: BLE001
            log.warning("table selector unavailable, keeping all %d candidates: %s", len(cands), exc)
            return Selection(list(cands), "KEPT", ms=int((time.perf_counter() - t0) * 1000),
                             note=f"selector failed: {type(exc).__name__}")
        ms = int((time.perf_counter() - t0) * 1000)

        data = _parse(text)
        if data is None:
            log.warning("table selector returned no json, keeping all %d candidates: %r",
                        len(cands), (text or "")[:200])
            return Selection(list(cands), "KEPT", ms=ms, note="unparseable reply")

        decision = str(data.get("decision") or "").strip().upper()
        raw = data.get("tables") or []
        picked: list[str] = []
        reasons: dict[str, str] = {}
        invented: list[str] = []
        by_upper = {c.upper(): c for c in cands}
        for item in raw if isinstance(raw, list) else []:
            name = (item.get("name") if isinstance(item, dict) else item) or ""
            real = by_upper.get(str(name).strip().upper())
            if real is None:
                if str(name).strip():
                    invented.append(str(name).strip())
                continue
            if real not in picked:
                picked.append(real)
            if isinstance(item, dict) and item.get("reason"):
                reasons[real] = str(item["reason"])[:self.max_reason_chars]
        if invented:
            log.info("table selector named %d tables that are not candidates: %s", len(invented), invented[:5])

        if decision == "NONE" and not picked:
            # Nothing offered fits. With something already established the question is still
            # answerable from that; with nothing, this is a real "not in this schema".
            return Selection(list(keep), "NONE", reasons, dropped=[c for c in cands if c not in keep],
                             invented=invented, ms=ms, note="selector found no fitting table")
        if not picked:
            return Selection(list(cands), "KEPT", ms=ms, invented=invented,
                             note="selector picked nothing recognisable")

        # Resolver-placed tables lead, then the selector's picks in the order retrieval had them —
        # the selector says which, not in what order; retrieval already measured that.
        chosen = keep + [c for c in cands if c in picked and c not in keep]
        return Selection(chosen, "SELECT", reasons, dropped=[c for c in cands if c not in chosen],
                         invented=invented, ms=ms)
