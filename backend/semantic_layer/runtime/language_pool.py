"""Schema-bound generated language documents. Retrieval evidence, never certified meaning."""
from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from collections import Counter, defaultdict
from pathlib import Path

from semantic_layer.normalize import fold, stem
from semantic_layer.runtime.column_index import tokens

VERSION = 1
OPERATIONS = {"lookup", "detail", "aggregate", "rank", "compare", "absence"}
ROLES = {"measure", "dimension", "filter", "time", "key"}


def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def file_stamp(path):
    try:
        st = Path(path).stat()
        return (str(path), st.st_mtime_ns, st.st_size)
    except (OSError, TypeError, ValueError):
        return None


def schema_documents(profiles, annotations=None):
    """No sampled data. Keep source descriptions, units, coded labels and declared edges."""
    annotations = annotations or {}
    docs = {}
    for p in profiles:
        doc = docs.setdefault(p.entity, {"entity": p.entity, "descriptions": set(), "columns": {}, "relationships": set()})
        description = annotations.get((p.entity, None)) or p.description
        if description:
            doc["descriptions"].add(description)
        for c in p.columns:
            if c.sensitive:
                continue
            item = {"name": c.name.upper(), "type": c.data_type, "description": c.meaning(annotations.get((p.entity, c.name.upper()))) or "",
                    "unit": c.unit or "", "valueLabels": c.value_labels or {}}
            # A model entity can have several physical periods. Preserve differing metadata.
            doc["columns"].setdefault(c.name.upper(), {})[digest(item)] = item
        for r in p.relationships:
            if all(r.get(k) for k in ("column", "ref_entity", "ref_column")):
                doc["relationships"].add((r["column"].upper(), r["ref_entity"], r["ref_column"].upper()))
    out = {}
    for entity, d in sorted(docs.items()):
        out[entity] = {"entity": entity, "descriptions": sorted(d["descriptions"]),
                       "columns": {name: [v[k] for k in sorted(v)] for name, v in sorted(d["columns"].items())},
                       "relationships": [list(r) for r in sorted(d["relationships"])]}
    return out


def validate_candidate(raw, docs, *, source_hashes=None):
    if not isinstance(raw, dict) or set(raw) - {"phrase", "columns", "operation", "ambiguities"}:
        raise ValueError("unsupported candidate fields")
    phrase = raw.get("phrase")
    if not isinstance(phrase, str) or not 3 <= len(phrase.strip()) <= 240 or "\n" in phrase:
        raise ValueError("invalid phrase")
    if raw.get("operation") not in OPERATIONS:
        raise ValueError("invalid operation")
    refs = raw.get("columns")
    if not isinstance(refs, list) or not 1 <= len(refs) <= 24:
        raise ValueError("invalid references")
    columns = []
    for ref in refs:
        if not isinstance(ref, dict) or set(ref) != {"entity", "column", "role"}:
            raise ValueError("invalid reference fields")
        entity, column, role = ref["entity"], ref["column"], ref["role"]
        if not all(isinstance(x, str) for x in (entity, column, role)):
            raise ValueError("invalid reference types")
        column = column.upper()
        if entity not in docs or column not in docs[entity]["columns"] or role not in ROLES:
            raise ValueError("unknown or sensitive column")
        item = {"entity": entity, "column": column, "role": role}
        if item not in columns:
            columns.append(item)
    entities = {c["entity"] for c in columns}
    reached = {next(iter(entities))}
    while True:
        expanded = set(reached)
        for entity in entities:
            for column, other, target in docs[entity]["relationships"]:
                if other in entities and column in docs[entity]["columns"] and target in docs[other]["columns"]:
                    if entity in reached or other in reached:
                        expanded.update((entity, other))
        if expanded == reached:
            break
        reached = expanded
    if reached != entities:
        raise ValueError("disconnected table combination")
    ambiguities = raw.get("ambiguities", [])
    if not isinstance(ambiguities, list) or len(ambiguities) > 5 or any(not isinstance(a, str) or len(a) > 180 for a in ambiguities):
        raise ValueError("invalid ambiguities")
    result = {"phrase": phrase.strip(), "columns": sorted(columns, key=lambda c: (c["entity"], c["column"], c["role"])),
              "operation": raw["operation"], "ambiguities": ambiguities}
    result["id"] = digest({**result, "phrase": fold(result["phrase"])})[:24]
    result["sourceHashes"] = {e: source_hashes[e] if source_hashes is not None else digest(docs[e]) for e in sorted(entities)}
    result["status"] = "SCHEMA_CHECKED_CANDIDATE"
    return result


def atomic_write(path, document):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=path.name + ".", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            json.dump(document, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


class LanguagePool:
    def __init__(self, entries=(), *, pool_hash="", rejected=0):
        self.entries = list(entries)
        self.content_hash = pool_hash or digest(self.entries)
        self.rejected = rejected
        self.bags = [Counter({stem(t) for t in tokens(e["phrase"])}) for e in self.entries]
        self.postings = defaultdict(set)
        for i, bag in enumerate(self.bags):
            for word in bag:
                self.postings[word].add(i)

    def __bool__(self):
        return bool(self.entries)

    @classmethod
    def load(cls, path, profiles, datasource_id, annotations=None):
        if not path or not Path(path).is_file():
            return cls()
        if Path(path).stat().st_size > 32 * 1024 * 1024:
            raise ValueError("language pool exceeds 32 MiB")
        payload = json.loads(Path(path).read_text())
        if not isinstance(payload, dict):
            raise ValueError("invalid pool document")
        if payload.get("version") != VERSION or payload.get("datasourceId") != datasource_id:
            raise ValueError("language pool version/data source differs")
        rows = payload.get("entries")
        if not isinstance(rows, list) or len(rows) > 20000:
            raise ValueError("invalid pool size")
        docs = schema_documents(profiles, annotations)
        hashes = {e: digest(d) for e, d in docs.items()}
        accepted, seen, rejected = [], set(), 0
        for entry in rows:
            try:
                if not isinstance(entry, dict) or entry.get("status") != "SCHEMA_CHECKED_CANDIDATE":
                    raise ValueError("invalid candidate status")
                checked = validate_candidate({k: entry[k] for k in ("phrase", "columns", "operation", "ambiguities")}, docs, source_hashes=hashes)
                if checked["id"] != entry.get("id") or not entry.get("sourceHashes") or any(hashes.get(e) != h for e, h in entry["sourceHashes"].items()) or checked["sourceHashes"] != entry["sourceHashes"]:
                    raise ValueError("stale or modified source")
                if checked["id"] not in seen:
                    seen.add(checked["id"])
                    accepted.append(checked)
            except (KeyError, TypeError, ValueError):
                rejected += 1
        return cls(accepted, pool_hash=digest(accepted), rejected=rejected)

    def search(self, question, limit=4):
        words = {stem(t) for t in tokens(question)}
        candidates = set().union(*(self.postings.get(w, set()) for w in words)) if words else set()
        scored = []
        for i in candidates:
            bag = self.bags[i]
            shared = words & bag.keys()
            if len(shared) < min(2, len(bag)) or len(shared) / max(1, len(bag)) < 0.3:
                continue
            score = sum(math.log(1 + len(self.entries) / (1 + len(self.postings[w]))) for w in shared)
            score *= len(shared) / max(1, len(bag))
            if fold(question).strip(" ?.! ") == fold(self.entries[i]["phrase"]).strip(" ?.! "):
                score += 10
            scored.append((score, i))
        out = []
        for score, i in sorted(scored, key=lambda x: (-x[0], self.entries[x[1]]["id"]))[:limit]:
            e = self.entries[i]
            out.append({"id": e["id"], "phrase": e["phrase"], "columns": [dict(c) for c in e["columns"]],
                        "operation": e["operation"], "ambiguities": list(e["ambiguities"]),
                        "status": e["status"], "score": round(score, 4), "poolHash": self.content_hash})
        return out
