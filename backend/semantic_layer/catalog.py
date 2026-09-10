"""How the catalog's rows are read, by everything that reads them.

An entity's name is worked out per scan from the patterns that scan saw, so two runs over different
scopes disagree about what a table is called while the vocabulary written against it does not change.
Reconciling that is not the bridge's business — it is what reading the catalog means, and any entry
point that skips it sees a catalog whose concepts point at entities that appear not to exist. The
certify command did skip it, and deprecated every certified concept in the deployment on one run.
"""
from __future__ import annotations

import logging
from typing import Optional

from semantic_layer.models import SchemaProfile

log = logging.getLogger(__name__)


def one_entity_per_pattern(profiles: list[SchemaProfile], anchors: Optional[dict[str, str]] = None) -> list[SchemaProfile]:
    """Two profiles of the same physical pattern are the same entity, whatever they are labelled.

    An entity's name is worked out per scan from the patterns that scan saw: a run scoped to one firm
    calls LG_{n0}_ITEMS "ITEMS", and a run over the whole schema — where LV_, VW_ and DV_ copies of the
    same table also appear — calls it "LG_ITEMS" to keep them apart. Both are reasonable and they
    disagree, so while a scan rewrites the catalog table by table the two live side by side and one
    entity splits in half: the 2021-2025 items under one name, the 2026 items under another. Nothing
    can then read across the years of it.

    The pattern is the stable thing — derived from the table name and recomputed by nothing — so it
    decides both which profiles are one entity and what that entity is called. `anchors` maps a
    pattern to the name the certified vocabulary uses for it; every concept, mapping and annotation in
    the deployment refers to that name and nothing rewrites them, so it outranks whatever a scan has
    since worked out. Keyed by pattern rather than by name, this holds even after a rescan has
    replaced every row it started from — matching on names alone let go the moment the old rows were
    pruned, and preferring the newest label renamed the deployment's busiest entities out from under
    the certified catalog while the scan was still running.
    """
    anchors = anchors or {}
    newest: dict[str, tuple] = {}
    # Which patterns a label has ever been used for, before anything is overwritten. A relationship
    # records only the *name* of the table it points at, written by whichever scan wrote that row —
    # so once the labels move, the graph still speaks the old generation's names.
    patterns_of_label: dict[str, set[str]] = {}
    for p in profiles:
        seen = newest.get(p.table_pattern)
        if seen is None or p.scanned_at > seen[0]:
            newest[p.table_pattern] = (p.scanned_at, p.entity)
        patterns_of_label.setdefault(p.entity, set()).add(p.table_pattern)
    chosen = {pattern: anchors.get(pattern) or label for pattern, (_, label) in newest.items()}
    renamed = sum(1 for p in profiles if p.entity != chosen[p.table_pattern])
    for p in profiles:
        p.entity = chosen[p.table_pattern]

    # The join graph is relabelled by the same rule, or it points at entities that no longer exist
    # under that name. Nothing errors when it does: joins simply stop being recognised, and every
    # check that reads the graph — "is this a join the catalog knows?" among them — goes quiet on the
    # tables the deployment uses most. A label that was used for more than one pattern is left alone;
    # there is no way to tell which one was meant, and guessing would assert a join nobody recorded.
    rewired = 0
    for p in profiles:
        for rel in p.relationships or []:
            ref = rel.get("ref_entity")
            pats = patterns_of_label.get(ref) if ref else None
            if not pats or len(pats) != 1:
                continue
            target = chosen.get(next(iter(pats)))
            if target and target != ref:
                rel["ref_entity"] = target
                rewired += 1
    if renamed or rewired:
        log.info("catalog: %d profiles relabelled so one pattern is one entity under the name the "
                 "certified catalog uses (%d relationship targets relabelled with them)", renamed, rewired)
    return profiles
