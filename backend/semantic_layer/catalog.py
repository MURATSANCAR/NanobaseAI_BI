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
    for p in profiles:
        seen = newest.get(p.table_pattern)
        if seen is None or p.scanned_at > seen[0]:
            newest[p.table_pattern] = (p.scanned_at, p.entity)
    chosen = {pattern: anchors.get(pattern) or label for pattern, (_, label) in newest.items()}
    renamed = sum(1 for p in profiles if p.entity != chosen[p.table_pattern])
    for p in profiles:
        p.entity = chosen[p.table_pattern]
    if renamed:
        log.info("catalog: %d profiles relabelled so one pattern is one entity under the name the "
                 "certified catalog uses", renamed)
    return profiles
