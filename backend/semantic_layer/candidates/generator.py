"""Candidate Generator — deterministic (history + docs + profile) and offline LLM (Qwen) candidates.

Everything produced here is CANDIDATE with attached evidence. Certification is the Evidence Engine's job.
"""

from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Iterable, Optional

from semantic_layer.candidates.doc_miner import DocFact, mine_annotation, mine_profiles, mine_project_docs
from semantic_layer.models import (
    Candidate,
    ConceptStatus,
    CounterEvidence,
    Evidence,
    EvidenceType,
    Mapping,
    SchemaProfile,
    SemanticType,
)
from semantic_layer.normalize import normalize_term
from semantic_layer.store.catalog_store import CatalogStore

log = logging.getLogger(__name__)


class CandidateGenerator:
    def __init__(self, store: CatalogStore, tenant_id: str, datasource_id: str, profiles: list[SchemaProfile], conventions: Any = None):
        from semantic_layer.conventions import Conventions

        self.store = store
        self.tenant_id = tenant_id
        self.datasource_id = datasource_id
        self.profiles = profiles
        self.by_entity = {p.entity: p for p in profiles}
        self.conventions = conventions or Conventions.from_profiles(profiles)

    # ------------------------------------------------------------------ doc facts → concepts/evidence
    def _entity_for(self, fact: DocFact) -> Optional[str]:
        """Which table a documented fact is about.

        A column name alone does not name a table: in a real schema dozens of tables share one code
        column, and
        attaching a documented meaning to whichever one came first silently splits the evidence for a
        term across unrelated tables, so none of them reaches the gate. When the fact carries values,
        the tables whose profiled inventory actually contains those values are preferred — the data
        decides. Where nothing can be confirmed (a table profiled shallowly has no inventory), the
        existing convention applies.
        """
        if fact.entity and fact.entity in self.by_entity:
            return fact.entity
        if fact.column:
            owners = [p.entity for p in self.profiles if p.column(fact.column)]
            if len(owners) == 1:
                return owners[0]
            if fact.values:
                wanted = {str(v) for v in fact.values}
                observed = [e for e in owners
                            if (col := self.by_entity[e].column(fact.column)) is not None
                            and col.top_values and wanted <= {str(v) for v, _ in col.top_values}]
                if observed:
                    owners = observed
                    if len(owners) == 1:
                        return owners[0]
            if owners:
                return self.conventions.preferred_entity(owners)
        return None

    def ingest_doc_facts(self, facts: Iterable[DocFact], *, evidence_type: str = EvidenceType.DOC, weight: float = 1.0) -> dict[str, int]:
        created = evidence = 0
        for f in facts:
            entity = self._entity_for(f)
            if f.kind == "value":
                if not entity or not f.column or not f.values:
                    continue
                prof = self.by_entity[entity]
                if not prof.column(f.column):
                    continue
                op = "IN" if f.operator == "IN" else f.operator
                mapping = Mapping(concept_id="", entity=entity, table_pattern=prof.table_pattern, column=f.column.upper(), operator=op, values=[str(v) for v in f.values])
                concept, was_new = self.store.upsert_concept(self.tenant_id, self.datasource_id, f.term, SemanticType.DIMENSION_VALUE, mapping=mapping, status=ConceptStatus.CANDIDATE)
                created += int(was_new)
                self.store.add_evidence(Evidence(concept.id, evidence_type, f.source, support_count=1, weight=weight, payload={"snippet": f.snippet}))
                self.store.add_candidate(Candidate(concept.id, "doc_miner" if evidence_type == EvidenceType.DOC else "human", payload={"source": f.source, "snippet": f.snippet}))
                evidence += 1
                # the same term documented with *different* values on the same column → counter-evidence there
                for sib in self.store.find_concepts(self.tenant_id, self.datasource_id, normalized_term=normalize_term(f.term), semantic_type=SemanticType.DIMENSION_VALUE):
                    if sib.id == concept.id:
                        continue
                    for m in self.store.list_mappings(sib.id):
                        if m.entity == entity and (m.column or "").upper() == f.column.upper() and set(m.values) != set(mapping.values):
                            self.store.add_counter_evidence(CounterEvidence(sib.id, f.source, "DOC_CONTRADICTION", payload={"documented_values": list(mapping.values), "snippet": f.snippet}, severity="MEDIUM"))
            elif f.kind == "column":
                if not entity or not f.column:
                    continue
                prof = self.by_entity[entity]
                if not prof.column(f.column):
                    continue
                mapping = Mapping(concept_id="", entity=entity, table_pattern=prof.table_pattern, column=f.column.upper(), operator="COLUMN")
                concept, was_new = self.store.upsert_concept(self.tenant_id, self.datasource_id, f.term, SemanticType.COLUMN, mapping=mapping, status=ConceptStatus.CANDIDATE)
                created += int(was_new)
                self.store.add_evidence(Evidence(concept.id, evidence_type, f.source, support_count=1, weight=weight, payload={"snippet": f.snippet}))
                evidence += 1
                if f.extra.get("synonyms"):
                    self.store.update_concept(concept.id, explain={"declared_synonyms": sorted(set(f.extra["synonyms"]))})
                if f.extra.get("documented_values"):
                    known = set(concept.explain.get("documented_values") or [])
                    self.store.update_concept(concept.id, explain={"documented_values": sorted(known | set(f.extra["documented_values"]))})
                # a documented measure column also backs metric formulas over it ("satış tutarı" = INVOICE.NETTOTAL)
                ref = f"{entity}.{f.column.upper()}"
                for mc in self.store.find_concepts(self.tenant_id, self.datasource_id, normalized_term=normalize_term(f.term), semantic_type=SemanticType.METRIC):
                    if any(ref in (m.formula or "") for m in self.store.list_mappings(mc.id)):
                        self.store.add_evidence(Evidence(mc.id, evidence_type, f.source, support_count=1, weight=weight, payload={"snippet": f.snippet}))
                        evidence += 1
            elif f.kind == "unit":
                prof = self.by_entity.get(entity or "")
                col = prof.column(f.column) if prof and f.column else None
                if col is not None and not col.unit:
                    col.unit = str(f.extra.get("unit") or f.term)[:60]
                    evidence += 1
            elif f.kind == "column_values":
                # value inventory documented for a column that already has a certified/candidate name
                if not entity or not f.column:
                    continue
                for c in self.store.mappings_for_column(self.tenant_id, self.datasource_id, entity, f.column.upper()):
                    concept, mapping = c
                    if concept.semantic_type != SemanticType.COLUMN:
                        continue
                    known = set(concept.explain.get("documented_values") or [])
                    self.store.update_concept(concept.id, explain={"documented_values": sorted(known | set(f.extra["documented_values"]))})
                    self.store.add_evidence(Evidence(concept.id, evidence_type, f.source, support_count=1, weight=weight, payload={"snippet": f.snippet, "values": f.extra["documented_values"]}))
                    evidence += 1
            elif f.kind == "metric":
                # attach DOC evidence to existing metric senses with the same term whose formula uses a column
                # the doc mentions (never invent a formula from prose; never back the wrong sense)
                snippet_up = (f.snippet or "").upper()
                for c in self.store.find_concepts(self.tenant_id, self.datasource_id, normalized_term=normalize_term(f.term), semantic_type=SemanticType.METRIC):
                    for m in self.store.list_mappings(c.id):
                        cols = {tok.split(".")[1] for tok in re.findall(r"\b([A-Z][A-Z0-9_]*\.[A-Z][A-Z0-9_]*)\b", m.formula or "")}
                        if not cols or any(col in snippet_up for col in cols):
                            self.store.add_evidence(Evidence(c.id, evidence_type, f.source, support_count=1, weight=weight, payload={"snippet": f.snippet}))
                            evidence += 1
                            break
        return {"created": created, "evidence": evidence}

    def ingest_project_docs(self, project_dir: Optional[Path]) -> dict[str, int]:
        facts = list(mine_profiles(self.profiles, self.conventions))
        if project_dir:
            facts += mine_project_docs(Path(project_dir), self.conventions)
        return self.ingest_doc_facts(facts)

    def ingest_annotation(self, table_pattern: str, column: Optional[str], text: str, source: str) -> dict[str, int]:
        prof = next((p for p in self.profiles if p.table_pattern == table_pattern), None)
        if prof is None:
            return {"created": 0, "evidence": 0}
        facts = mine_annotation(text, prof.entity, column, source, self.conventions)
        return self.ingest_doc_facts(facts, evidence_type=EvidenceType.HUMAN_ANNOTATION, weight=1.0)

    def propose_column_meanings(self, llm, *, max_columns: int = 200, model_version: Optional[str] = None) -> dict[str, Any]:
        """Read the schema the way a person would and write down what each column looks like it means.

        A table name, a column name, its type and the values actually in it say a great deal — enough
        for a reader to say "this is the document type, 8 is wholesale". Nobody was doing that reading
        here: a column no question had ever mentioned stayed nameless for ever, and with tens of
        thousands of them, waiting for someone to describe each one is waiting for nothing.

        What comes back is a *proposal*, filed as LLM_CANDIDATE and weighted so it cannot pass the gate
        on its own. It reaches a person as a suggestion to accept or correct, and accepting it is what
        makes it a definition. The machine reads; a person still decides.
        """
        described = {(m.entity, (m.column or "").upper())
                     for c in self.store.find_concepts(self.tenant_id, self.datasource_id, limit=100000)
                     for m in self.store.list_mappings(c.id) if m.column}
        # fullest tables first, and only columns whose values give the reader something to go on
        ranked = sorted(self.profiles, key=lambda p: -(p.row_count or 0))
        todo: list[tuple[Any, Any]] = []
        for prof in ranked:
            for col in prof.columns:
                if (prof.entity, col.name.upper()) in described or col.sensitive or col.is_primary_key or col.ref_entity:
                    continue
                if not col.meaningful_values():
                    continue
                todo.append((prof, col))
                if len(todo) >= max_columns:
                    break
            if len(todo) >= max_columns:
                break
        if not todo:
            return {"asked": 0, "proposed": 0}

        # asked in batches: a hundred columns with their values is more than a local model can read at
        # once, and one oversized request answers nothing at all
        batch = max(5, int(os.environ.get("SEMANTIC_PROPOSE_BATCH", "20")))
        proposed = 0
        asked = 0
        for start in range(0, len(todo), batch):
            chunk = todo[start : start + batch]
            asked += len(chunk)
            try:
                proposed += self._propose_batch(llm, chunk, model_version)
            except Exception as e:  # noqa: BLE001
                log.warning("column proposal batch failed: %s", str(e)[:200])
        return {"asked": asked, "proposed": proposed}

    # ------------------------------------------------------------------ vetting a reading
    #: glosses that say nothing. A reader who writes these has run out of evidence and kept writing.
    _FILLER = {"diğer", "digger", "diger", "diğerleri", "bilinmiyor", "bilinmeyen", "tanımsız",
               "tanimsiz", "belirsiz", "yok", "other", "unknown", "misc", "n/a", "na", "none"}
    #: a reading hedged in words is a guess wearing a sentence
    _HEDGES = ("muhtemelen", "olabilir", "edebilir", "belki", "sanır", "tahmin", "görünüyor",
               "gibi duruyor", "olasılıkla", "sanılır")

    @staticmethod
    def _vet_reading(col, meaning: str, glosses: dict[str, str], confidence: float) -> tuple[str, dict[str, str], float, list[str]]:
        """Check a proposed reading against what was actually measured, and cut back what it cannot support.

        Everything here is a property of the numbers, not of any particular database: a gloss that only
        repeats the code says nothing whatever the code is; a code list written for a column with
        thousands of distinct values is a category error in any schema; two codes appearing an equal
        number of times are one thing seen twice, not two unrelated things. The model is left free to
        read — this only stops a reading being filed as if it were measured.
        """
        notes: list[str] = []
        counts = {str(v): n for v, n in col.top_values}
        whole = sum(counts.values()) or 1

        # A column with more distinct values than we could enumerate is a free field. Whatever list
        # came back for it is a handful of examples mistaken for a code list.
        if glosses and not col.is_enum():
            glosses = {}
            notes.append("kod listesi değil, serbest alan")

        # Strip each gloss of its own code. If two of them then read the same, the list carries no
        # information — "47 = Kullanıcı 47, 3 = Kullanıcı 3" is the column name repeated, not a reading.
        if len(glosses) >= 2:
            stripped = {k: " ".join(w for w in str(v).lower().split() if w.strip(".,:;") != k.lower())
                        for k, v in glosses.items()}
            if len(set(stripped.values())) < len(stripped):
                glosses = {}
                notes.append("kod açıklamaları kodun kendisini tekrar ediyordu")

        # Placeholder glosses, dropped one by one; a partial list is worth more than a padded one.
        glosses = {k: v for k, v in glosses.items()
                   if {w.strip(".,:;()").lower() for w in str(v).split()} - CandidateGenerator._FILLER}

        # Codes seen an all but equal number of times are almost always two sides of one movement.
        # Read as independent categories they invert whatever they are used to decide.
        eq = [(a, b) for i, a in enumerate(glosses) for b in list(glosses)[i + 1:]
              if counts.get(a) and counts.get(b)
              and counts[a] >= 0.01 * whole
              and abs(counts[a] - counts[b]) <= 0.02 * max(counts[a], counts[b])]
        for a, b in eq[:2]:
            notes.append(f"{a} ve {b} eşit sayıda geçiyor, aynı işlemin iki ayağı olabilir")
            confidence = min(confidence, 0.4)

        # A reading that explains the rare codes and passes over the one holding most of the column is
        # not wrong so much as beside the point. Say what the rest of the rows hold — except on a flag,
        # where naming one side already says what the other side is and spelling it out is noise.
        if glosses and (col.distinct_count or 0) > 2:
            for v, n in col.top_values:
                if str(v) not in glosses and n >= 0.2 * whole:
                    notes.append(f"satırların %{100 * n / whole:.3g}'inde değer {v}, bu okumada yok")
                    confidence = min(confidence, 0.5)
                    break

        if any(h in meaning.lower() for h in CandidateGenerator._HEDGES):
            confidence = min(confidence, 0.35)

        return meaning, glosses, confidence, notes

    def _propose_batch(self, llm, todo: list[tuple[Any, Any]], model_version: Optional[str]) -> int:
        """One batch of columns, asked the way a person reads an unfamiliar schema.

        A reader does not look at a column alone. They see what kind of record the table holds, what
        the column is called, what is actually in it, and whether the values confirm the name or
        contradict it. They tell a code list from a free field by how many distinct values there are.
        And they say nothing when the name is opaque and the values do not help — which is the part a
        model has to be told, because its instinct is to produce something for every line.
        """
        blocks = []
        for prof, col in todo:
            siblings = [c.name for c in prof.columns if c.name != col.name][:12]
            # Percentages must be shares of the whole column, not of what survived filtering. Taken
            # over the filtered list, a code holding 0.6% of the rows shows up as "52%" and reads like
            # the main case — which is how a rarity came to be described as the column's meaning.
            whole = sum(n for _, n in col.top_values) or prof.row_count or 1
            vals = col.meaningful_values()[:8]
            shown = ", ".join(f"{v} (%{100 * n / whole:.3g})" for v, n in vals)
            lines = [
                f"### {prof.entity}.{col.name}",
                f"- tablo: {prof.entity} ({prof.table_name}), {prof.row_count or 0} satır",
                f"- aynı tablodaki diğer kolonlar: {', '.join(siblings) or '—'}",
                f"- tip: {col.data_type}, farklı değer sayısı: "
                f"{col.distinct_count if col.distinct_count is not None else 'bilinmiyor'}",
                f"- en sık değerler: {shown or '—'}",
            ]
            # A value we suppressed as a placeholder is still most of the column. Saying so is the
            # difference between "1 means average cost" and "almost every row leaves this unset".
            hidden = [(v, n) for v, n in col.top_values
                      if v in col.sentinel_values and n >= 0.2 * whole]
            for v, n in hidden:
                lines.append(f"- satırların %{100 * n / whole:.3g}'inde bu alan {v} (boş/atanmamış sayılıyor)")
            # Whether the shown list is the whole list. Without this a truncated top-N reads as a
            # complete code list, and free-text columns get written up as enumerations.
            if col.is_enum():
                lines.append("- bu bir kod listesi: yukarıdaki değerler alanın tamamıdır")
            else:
                lines.append("- bu bir kod listesi DEĞİL (çok sayıda farklı değer var, liste kesilmiştir): "
                             "kod anlamı yazma, yalnız ne tuttuğunu yaz")
            blocks.append("\n".join(lines))

        prompt = (
            "Tanımadığın bir veritabanını okuyor ve kolonların ne işe yaradığını yazıyorsun.\n\n"
            "Nasıl okuyacaksın:\n"
            "1. Önce tablonun ne tuttuğuna bak (adı ve diğer kolonları söyler).\n"
            "2. Kolon adının ne ima ettiğine bak.\n"
            "3. İçindeki değerlerin bunu doğrulayıp doğrulamadığına bak. Değerler adı yalanlıyorsa değerlere güven.\n"
            "4. Az sayıda tekrar eden değer varsa bu bir kod listesidir: hangi kodun ne demek olduğunu yaz. "
            "Çok sayıda farklı değer varsa serbest alandır: yalnız ne tuttuğunu yaz, kod listesi yazma.\n\n"
            "Kurallar:\n"
            "- Emin değilsen o kolonu listeye HİÇ koyma. Eksik bırakmak, uydurmaktan iyidir.\n"
            "- Yalnız sana gösterilen değerler için anlam yaz; gösterilmeyen bir kod uydurma.\n"
            "- Anlamı tek cümlede, işi bilen birine anlatır gibi yaz. Kolon adını tekrar etme "
            "(\"CANCELLED: iptal edilmiş\" değil, \"Fişin iptal edilip edilmediği\").\n"
            "- Şirkete, sektöre ya da bu veritabanına dair bilmediğin şeyi varsayma.\n\n"
            # The examples are deliberately about a table that is not in the batch. An illustration
            # drawn from the very column being asked about is an answer key, and a model will copy it.
            "Örnek — iyi (bu tablo aşağıdaki listede yok, yalnız biçimi göstermek için):\n"
            '{"entity":"KARGO","column":"TESLIM_DURUMU","meaning":"Gönderinin teslim aşaması",'
            '"values":{"H":"hazırlanıyor","Y":"yolda","T":"teslim edildi"},"confidence":0.8}\n'
            "Örnek — kötü (kolon adını tekrar ediyor, gösterilmeyen bir kod uyduruyor):\n"
            '{"entity":"KARGO","column":"TESLIM_DURUMU","meaning":"TESLIM_DURUMU alanı",'
            '"values":{"Z":"özel durum"},"confidence":0.9}\n\n'
            "Çıktı: yalnız JSON listesi, başka hiçbir şey yazma.\n"
            '[{"entity":..., "column":..., "meaning":"tek cümle", "values":{"kod":"anlamı"} ya da {}, "confidence":0-1}]\n\n'
            "## Kolonlar\n" + "\n\n".join(blocks)
        )
        text = llm.chat([{"role": "user", "content": prompt}], max_tokens=1800)
        m = re.search(r"\[.*\]", text, re.S)
        if not m:
            return 0
        try:
            items = json.loads(m.group(0))
        except Exception:  # noqa: BLE001
            return 0

        by_key = {(p.entity, c.name.upper()): (p, c) for p, c in todo}
        n = 0
        for it in items if isinstance(items, list) else []:
            entity, column = str(it.get("entity") or ""), str(it.get("column") or "").upper()
            found = by_key.get((entity, column))
            meaning = str(it.get("meaning") or "").strip()
            if not found or not meaning:
                continue
            prof, col = found
            observed = {str(v) for v, _ in col.meaningful_values()}
            glosses = {str(k): str(v) for k, v in (it.get("values") or {}).items() if str(k) in observed}
            conf = float(it.get("confidence") or 0.5)
            meaning, glosses, conf, notes = self._vet_reading(col, meaning, glosses, conf)
            text_out = meaning if not glosses else meaning + " — " + ", ".join(f"{k} = {v}" for k, v in glosses.items())
            if notes:
                text_out += " (" + "; ".join(notes) + ")"
            self.store.add_suggestion(self.datasource_id, prof.table_pattern, col.name, text_out,
                                      confidence=conf, model=model_version or "llm")
            facts = mine_annotation(text_out, prof.entity, col.name, f"llm:{prof.entity}.{col.name}", self.conventions)
            self.ingest_doc_facts(facts, evidence_type=EvidenceType.LLM_CANDIDATE, weight=0.1)
            n += 1
        return n

    # ------------------------------------------------------------------ profile fit evidence
    def attach_profile_evidence(self) -> int:
        n = 0
        for c in self.store.find_concepts(self.tenant_id, self.datasource_id, semantic_type=SemanticType.DIMENSION_VALUE, limit=100000):
            for m in self.store.list_mappings(c.id):
                prof = self.by_entity.get(m.entity)
                col = prof.column(m.column) if prof and m.column else None
                if not col:
                    continue
                if col.top_values:
                    known = {v for v, _ in col.top_values}
                    present = [v for v in m.values if v in known]
                    fit = len(present) / len(m.values) if m.values else 0.0
                    counts = {v: n_ for v, n_ in col.top_values if v in m.values}
                    self.store.add_evidence(Evidence(c.id, EvidenceType.PROFILE, f"profile:{m.entity}.{m.column}", support_count=1, weight=fit, payload={"fit": round(fit, 3), "counts": counts, "distinct": col.distinct_count}))
                    n += 1
        return n

    # ------------------------------------------------------------------ LLM candidates (offline only)
    def llm_candidates(self, llm, terms: Iterable[str], *, model_version: Optional[str] = None, max_terms: int = 20) -> dict[str, Any]:
        """Ask the LLM what unresolved terms could mean, given the profile. Results are CANDIDATE with
        LLM_CANDIDATE evidence (weight 0.1). They cannot pass the hard gate on their own."""
        terms = [t for t in dict.fromkeys(terms) if t][:max_terms]
        if not terms:
            return {"asked": 0, "candidates": 0}
        # The whole schema does not fit in a model's context — 837 tables came to a hundred thousand
        # tokens against sixteen, so this stage had been failing on every run and saying so only in a
        # field nobody reads. The tables anyone has already named come first, then the fullest.
        named = {m.entity for c in self.store.find_concepts(self.tenant_id, self.datasource_id, limit=100000)
                 for m in self.store.list_mappings(c.id)}
        ordered = sorted(self.profiles, key=lambda p: (p.entity not in named, -(p.row_count or 0)))
        ctx_lines = []
        for p in ordered[:12]:
            enum_cols = [f"{c.name} {{{', '.join(v for v, _ in c.top_values[:8])}}}" for c in p.columns if c.is_enum()]
            ctx_lines.append(f"- {p.entity} ({p.table_pattern}): {', '.join(c.name for c in p.columns[:30])}" + (f" | enum: {'; '.join(enum_cols[:6])}" if enum_cols else ""))
        prompt = (
            "Sen bir ERP semantik analistisin. Aşağıdaki şema profiline bakarak verilen Türkçe iş terimlerinin olası fiziksel karşılıklarını öner. "
            "Yalnız JSON listesi döndür: [{\"term\":..., \"semantic_type\": \"DIMENSION_VALUE|COLUMN|METRIC\", \"entity\":..., \"column\":..., \"operator\": \"IN\", \"values\": [..], \"formula\": null, \"confidence\": 0-1, \"rationale\": ...}]. "
            "Emin değilsen confidence düşük ver; uydurma değer yazma.\n\n## Şema profili\n" + "\n".join(ctx_lines) + "\n\n## Terimler\n" + "\n".join(f"- {t}" for t in terms)
        )
        text = llm.chat([{"role": "user", "content": prompt}], max_tokens=1500)
        m = re.search(r"\[.*\]", text, re.S)
        if not m:
            return {"asked": len(terms), "candidates": 0, "raw": text[:200]}
        try:
            items = json.loads(m.group(0))
        except Exception:  # noqa: BLE001
            return {"asked": len(terms), "candidates": 0, "raw": text[:200]}
        n = 0
        for it in items if isinstance(items, list) else []:
            try:
                term = str(it.get("term") or "").strip()
                st = str(it.get("semantic_type") or "DIMENSION_VALUE").upper()
                entity = str(it.get("entity") or "").upper()
                prof = self.by_entity.get(entity)
                if not term or prof is None:
                    continue
                column = str(it.get("column") or "").upper() or None
                if st in (SemanticType.DIMENSION_VALUE, SemanticType.COLUMN) and (not column or not prof.column(column)):
                    continue
                if st == SemanticType.DIMENSION_VALUE:
                    values = [str(v) for v in (it.get("values") or [])]
                    if not values:
                        continue
                    mapping = Mapping(concept_id="", entity=entity, table_pattern=prof.table_pattern, column=column, operator="IN", values=values)
                elif st == SemanticType.COLUMN:
                    mapping = Mapping(concept_id="", entity=entity, table_pattern=prof.table_pattern, column=column, operator="COLUMN")
                elif st == SemanticType.METRIC and it.get("formula"):
                    mapping = Mapping(concept_id="", entity=entity, table_pattern=prof.table_pattern, formula=str(it["formula"]))
                else:
                    continue
                concept, _ = self.store.upsert_concept(self.tenant_id, self.datasource_id, term, st, mapping=mapping, status=ConceptStatus.CANDIDATE)
                self.store.add_evidence(Evidence(concept.id, EvidenceType.LLM_CANDIDATE, f"llm:{getattr(llm, 'model', 'llm')}", support_count=1, weight=0.1, payload={"confidence": float(it.get("confidence") or 0), "rationale": str(it.get("rationale") or "")[:300]}))
                self.store.add_candidate(Candidate(concept.id, "qwen", model_version=model_version or getattr(llm, "model", None), payload=it))
                n += 1
            except Exception as e:  # noqa: BLE001
                log.debug("llm candidate skipped: %s", e)
        return {"asked": len(terms), "candidates": n}
