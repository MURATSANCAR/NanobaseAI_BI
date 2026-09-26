"""What the label columns really hold — every value, from every copy of the table.

The resolver matches a name in the question ("Portakal Kitap", "Timaş Okul", "İstanbul") against the values
of certified columns. Those values came from the scan profile, and the scan reads one physical table per
shape: `ITEMS.SPECODE` was profiled on an older firm's copy that holds one-letter codes, while the 2026
copy holds the publisher names people ask about. `CLCARD.CITY` has too many values to be profiled as an
enum at all, so "İstanbul" was only ever found in the small `CITYCODE` column (132 cards against 86.145).

So the label columns are read once a day in full — the distinct values with their row counts, summed over
every physical copy — and written to one file the resolver reads. The resolver stays free of database
calls; this module is the only thing that goes to the database, on its own connections.

A column with more distinct values than `MAX_DISTINCT` is free text (titles, names, addresses), not a label:
it is recorded as such and left out. Nothing is dropped silently — every column that was not read says why
in the file.

Logo writes label codes into fixed-width fields and cuts them: the publisher "Antik Kitap" is stored as
"Antik Kita". A value as long as the longest value of its column may be such a cut, and the matcher lets a
longer name in the question start with it.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from semantic_layer.normalize import tokenize

log = logging.getLogger(__name__)

PATH = os.environ.get("SEMANTIC_LABEL_VALUES", "/data/nanobaseai/bi/var/label-values.json")
MAX_DISTINCT = int(os.environ.get("SEMANTIC_LABEL_VALUES_MAX_DISTINCT", "5000"))
REFRESH_SECONDS = int(os.environ.get("SEMANTIC_LABEL_VALUES_REFRESH_SECONDS", "86400"))
QUERY_TIMEOUT = int(os.environ.get("SEMANTIC_LABEL_VALUES_QUERY_TIMEOUT", "300"))
# The resolver looks for phrases of up to four words; a value of more words (a book blurb stored in a CRM
# field) can never be matched, so it is counted but not written.
MAX_WORDS = 4
_TEXT_TYPES = ("char", "text")
# "Antik Yayınları", "Portakal Kitap", "Timaş Yayınevi": the words after the name say what kind of company it
# is. A question that names a publisher this way is matched on the name, when one value alone starts with it.
ORG_SUFFIX = frozenset("""
    yayinlari yayinlarinin yayinlarindan yayinlarina yayinevi yayinevinin yayinevinden yayincilik
    kitap kitaplari kitaplarinin kitaplarindan kitapcilik yayin yayinlar
""".split())


def _form(raw: str) -> str:
    """The shape question tokens have: folded, split on non-word characters ("E-TİCARET" → "e ticaret")."""
    return " ".join(tokenize(raw or ""))


def _quote(name: str) -> str:
    return "[" + name.replace("]", "]]") + "]"


def _table_ref(prof: Any) -> str:
    schema = getattr(prof, "schema_name", "") or "dbo"
    return ".".join(_quote(p) for p in schema.split(".") if p) + "." + _quote(prof.table_name)


def is_crm(prof: Any) -> bool:
    return "timas_mscrm" in (getattr(prof, "schema_name", "") or "").lower()


def label_columns(index: dict, by_entity: dict, tables_of: dict) -> list[dict]:
    """Certified COLUMN concepts on text columns — never sensitive, never a key or a reference."""
    from semantic_layer.models import SemanticType
    out: dict[tuple[str, str], dict] = {}
    for senses in index.values():
        for concept, maps in senses:
            if concept.semantic_type != SemanticType.COLUMN:
                continue
            for m in maps:
                prof = by_entity.get(m.entity)
                col = prof.column(m.column) if prof and m.column else None
                if col is None or col.sensitive or col.is_primary_key or col.ref_entity:
                    continue
                if not any(t in (col.data_type or "").lower() for t in _TEXT_TYPES):
                    continue
                tables = [t for t in (tables_of.get(m.entity) or [prof]) if t.column(col.name) is not None]
                out.setdefault((m.entity, col.name), {"entity": m.entity, "column": col.name, "tables": tables or [prof],
                                                      "source": "crm" if is_crm(prof) else "logo"})
    return list(out.values())


def _meta(spec: dict) -> dict:
    return {"entity": spec["entity"], "column": spec["column"], "source": spec["source"],
            "tables": [t.table_name for t in spec["tables"]]}


def build(columns: Iterable[dict], connector_for: Callable[[str], Any], *, max_distinct: int = MAX_DISTINCT) -> dict:
    """Read each label column in full. `connector_for("logo"|"crm")` gives a connection used only here."""
    result: dict[str, dict] = {}
    started = time.time()
    for spec in columns:
        key = f"{spec['entity']}.{spec['column']}"
        conn = connector_for(spec["source"])
        if conn is None:
            result[key] = {**_meta(spec), "status": f"bağlantı yok ({spec['source']})"}
            continue
        counts: dict[str, int] = {}
        status = "ok"
        for prof in spec["tables"]:
            sql = (f"SELECT TOP ({max_distinct + 1}) {_quote(spec['column'])} AS v, COUNT(*) AS n "
                   f"FROM {_table_ref(prof)} GROUP BY {_quote(spec['column'])} ORDER BY COUNT(*) DESC")
            try:
                _, rows, _ = conn.execute(sql, max_distinct + 1)
            except Exception as e:  # noqa: BLE001 — one unreadable copy is reported, not guessed around
                status = f"okunamadı: {prof.table_name}: {str(e)[:160]}"
                break
            if len(rows) > max_distinct:
                status = f"serbest metin: {prof.table_name} içinde {max_distinct}'den fazla farklı değer"
                break
            for r in rows:
                v = r.get("v")
                if v is None:
                    continue
                v = str(v).strip()
                if v:
                    counts[v] = counts.get(v, 0) + int(r.get("n") or 0)
        if status == "ok" and len(counts) > max_distinct:
            status = f"serbest metin: kopyalar birlikte {len(counts)} farklı değer"
        entry = {**_meta(spec), "status": status}
        if status == "ok":
            entry["maxlen"] = max((len(v) for v in counts), default=0)
            entry["distinct"] = len(counts)
            kept = {v: n for v, n in counts.items() if len(_form(v).split()) <= MAX_WORDS}
            if len(kept) < len(counts):
                entry["longer_than_words"] = {"words": MAX_WORDS, "values": len(counts) - len(kept)}
            entry["values"] = sorted(([v, n] for v, n in kept.items()), key=lambda x: -x[1])
        result[key] = entry
    return {"built_at": time.time(), "seconds": round(time.time() - started, 1), "max_distinct": max_distinct, "columns": result}


def write(data: dict, path: Optional[str] = None) -> None:
    p = Path(path or PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, p)


_cache: dict[str, Any] = {"key": None, "matcher": None}
_cache_lock = threading.Lock()


def matcher(path: Optional[str] = None) -> Optional["LabelMatcher"]:
    """The current dictionary, re-read when the file changes; None when there is none yet."""
    path = path or PATH
    try:
        key = (path, os.stat(path).st_mtime)
    except OSError:
        return None
    with _cache_lock:
        if _cache["key"] != key:
            try:
                _cache.update(key=key, matcher=LabelMatcher(json.loads(Path(path).read_text(encoding="utf-8"))))
            except (OSError, ValueError) as e:
                log.warning("label values unreadable, keeping the previous dictionary: %s", e)
                _cache["key"] = key
        return _cache["matcher"]


@dataclass(frozen=True)
class LabelHit:
    entity: str
    column: str
    source: str
    value: str
    rows: int
    how: str            # exact | cut (a stored value cut to the field width) | name (company name + kind word)


class LabelMatcher:
    def __init__(self, data: dict):
        self.exact: dict[str, list[LabelHit]] = {}
        self.cut: list[tuple[str, LabelHit]] = []
        self.first: dict[tuple[str, str, str], list[LabelHit]] = {}
        for col in (data.get("columns") or {}).values():
            if col.get("status") != "ok":
                continue
            maxlen = int(col.get("maxlen") or 0)
            for raw, rows in col.get("values") or []:
                form = _form(raw)
                bare = form.replace(" ", "")
                if len(bare) < 3 or bare.isdigit():
                    continue
                args = (col["entity"], col["column"], col.get("source", "logo"), raw, int(rows))
                self.exact.setdefault(form, []).append(LabelHit(*args, "exact"))
                if maxlen >= 6 and len(raw) == maxlen:
                    self.cut.append((form, LabelHit(*args, "cut")))
                self.first.setdefault((col["entity"], col["column"], form.split()[0]), []).append(LabelHit(*args, "name"))

    def find(self, tokens: list[str], sources: Optional[set] = None, entities: Optional[set] = None) -> list[LabelHit]:
        """Every column that holds the phrase, among the given databases and tables — most rows first.

        The filters apply before anything is decided: "Portakal Kitap" is also a CRM value word for word, and
        a Logo question must still find the Logo publisher code cut to "Portakal K"."""
        def keep(h: LabelHit) -> bool:
            return (sources is None or h.source in sources) and (entities is None or h.entity in entities)

        phrase = " ".join(tokens)
        hits = [h for h in self.exact.get(phrase, []) if keep(h)]
        # A stored value cut at the field width is the start of the longer name that was asked for; the cut
        # ends inside the last word asked ("Antik Kita" ⊂ "antik kitap", never "antik"). Weighed with the
        # word-for-word values by rows: "Timaş Çocu" on 1.500 books outweighs a label on a handful.
        seen = {(h.entity, h.column) for h in hits}
        hits += [h for form, h in self.cut if keep(h) and (h.entity, h.column) not in seen and len(phrase) > len(form)
                 and phrase.startswith(form) and len(form.split()) == len(tokens)]
        if not hits and len(tokens) >= 2 and all(t in ORG_SUFFIX for t in tokens[1:]):
            # "antik yayınları": the name and the kind of company. One value alone in a column starting
            # with the name is that company; two ("Antik Dünya", "Antik Okul") is not decided here.
            for (_, _, head), found in self.first.items():
                if head == tokens[0] and len(found) == 1 and keep(found[0]):
                    hits.append(found[0])
        return sorted(hits, key=lambda h: -h.rows)


def refresh(rt: Any) -> dict:
    """Build the dictionary on connections of its own and write it; the previous file stays if this fails."""
    from semantic_layer.profiler.connectors import connector_from_file
    r = rt.resolver
    index = r.store.certified_index(r.tenant_id, r.datasource_id)
    specs = label_columns(index, r.by_entity, r.tables_of)
    files = {"logo": rt.settings.connection_file,
             "crm": os.environ.get("SEMANTIC_CRM_CONNECTION_FILE", "/data/nanobaseai/bi/secrets/crm-mssql-connection.json")}
    conns: dict[str, Any] = {}

    def connector_for(source: str):
        if source not in conns:
            path = files.get(source)
            conns[source] = None
            if path and Path(path).exists():
                c = connector_from_file(path)
                c.query_timeout = QUERY_TIMEOUT
                conns[source] = c
        return conns[source]

    try:
        data = build(specs, connector_for)
    finally:
        for c in conns.values():
            close = getattr(c, "close", None)
            if callable(close):
                try:
                    close()
                except Exception:  # noqa: BLE001
                    pass
    write(data)
    cols = list(data["columns"].values())
    log.info("label values built: %d columns read, %d free text, %d unreadable, %.0fs",
             sum(c["status"] == "ok" for c in cols), sum(c["status"].startswith("serbest") for c in cols),
             sum(c["status"].startswith(("okunamadı", "bağlantı")) for c in cols), data["seconds"])
    return data


def start_refresher(get_runtime: Callable[[], Any], stop: threading.Event) -> threading.Thread:
    """Build the dictionary when it is missing or a day old, then once a day."""
    def loop():
        while not stop.is_set():
            try:
                age: Optional[float] = time.time() - os.stat(PATH).st_mtime
            except OSError:
                age = None
            if age is None or age >= REFRESH_SECONDS:
                try:
                    refresh(get_runtime())
                except Exception as e:  # noqa: BLE001 — a failed build keeps yesterday's file
                    log.warning("label values build failed, keeping the previous file: %s", e)
                wait = float(REFRESH_SECONDS)
            else:
                wait = REFRESH_SECONDS - age
            stop.wait(max(60.0, wait))
    t = threading.Thread(target=loop, name="label-values", daemon=True)
    t.start()
    return t
