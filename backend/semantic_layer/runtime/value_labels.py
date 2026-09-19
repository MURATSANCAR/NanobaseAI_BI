"""Seçim listesi kodlarını sonuçta etikete çevirir.

Dynamics gibi kaynaklar departman, durum, tür alanlarını tamsayı kodla tutar; kodun ne demek olduğu
katalogda (`ColumnProfile.value_labels`) yazılıdır. Model bu kolonu olduğu gibi seçtiğinde insan "4"
görür, "Satış" değil. Çeviri modele bırakılmaz: sorgunun en dış SELECT'inde *yalın kolon* olarak
seçilen ve kataloğun etiketini bildiği her çıktı, sonuç satırlarında etiketiyle değiştirilir.
Hesaplanan ifadeler (SUM, CASE, aritmetik) dokunulmadan kalır; okunamayan sorguda hiçbir şey yapılmaz.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

import sqlglot
from sqlglot import exp

from semantic_layer.models import SchemaProfile
from semantic_layer.runtime.critic import _profiles_by_name, _resolve


def _sources(select: exp.Select) -> dict[str, Any]:
    """Bu SELECT'in FROM/JOIN'lerinde takma ad → tablo adı ya da iç SELECT."""
    ctes = {}
    node: Optional[exp.Expression] = select
    while node is not None:
        w = (node.args.get("with") or node.args.get("with_")) if isinstance(node, exp.Select) else None
        for cte in (w.expressions if w else []):
            ctes.setdefault(cte.alias_or_name.upper(), cte.this)
        node = node.parent
    out: dict[str, Any] = {}
    # sqlglot sürümüne göre FROM anahtarı "from" ya da "from_" olur.
    rels = [select.args.get("from") or select.args.get("from_")] + list(select.args.get("joins") or [])
    for rel in rels:
        if rel is None:
            continue
        item = rel.this
        if isinstance(item, exp.Table):
            out[item.alias_or_name.upper()] = ctes.get(item.name.upper(), item)
        elif isinstance(item, exp.Subquery) and isinstance(item.this, exp.Select):
            out[item.alias_or_name.upper()] = item.this
    return out


def _origin(select: exp.Select, column: exp.Column, names: tuple, depth: int = 0):
    """Kolonun geldiği katalog kolonu; bulunamazsa None. Türetilmiş tablo/CTE içinden yalın kolon
    olarak taşındığı sürece izlenir."""
    if depth > 6:
        return None
    sources = _sources(select)
    wanted = [column.table.upper()] if column.table else list(sources)
    for alias in wanted:
        src = sources.get(alias)
        if isinstance(src, exp.Table):
            prof = _resolve(src, *names)
            col = prof.column(column.name) if prof else None
            if col is not None:
                return col
        elif isinstance(src, exp.Select):
            for proj in src.expressions:
                if proj.alias_or_name.upper() != column.name.upper():
                    continue
                inner = proj.this if isinstance(proj, exp.Alias) else proj
                if isinstance(inner, exp.Column):
                    found = _origin(src, inner, names, depth + 1)
                    if found is not None:
                        return found
    return None


def label_map(sql: str, profiles: Iterable[SchemaProfile], dialect: str = "tsql") -> dict[str, dict[str, str]]:
    """Çıktı kolonu adı → {kod: etiket}. Boşsa çevrilecek bir şey yok."""
    try:
        tree = sqlglot.parse_one(sql, read=dialect or None)
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(tree, exp.Select):
        return {}
    profiles = list(profiles)
    by_table, by_entity = _profiles_by_name(profiles)
    # Mantıksal SQL şemayı alt çizgiyle yazar (Timas_MSCRM_dbo_X); katalogda şema noktalıdır.
    for p in profiles:
        if p.schema_name:
            by_table.setdefault(f"{p.schema_name}_{p.table_name}".replace(".", "_").upper(), p)
    names = (by_table, by_entity)
    out: dict[str, dict[str, str]] = {}
    for proj in tree.expressions:
        inner = proj.this if isinstance(proj, exp.Alias) else proj
        if not isinstance(inner, exp.Column):
            continue
        try:
            col = _origin(tree, inner, names)
        except Exception:  # noqa: BLE001
            col = None
        labels = getattr(col, "value_labels", None) if col is not None else None
        if labels:
            out[proj.alias_or_name] = {str(k): str(v) for k, v in labels.items()}
    return out


def _key(value: Any) -> Optional[str]:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    return str(value).strip()


def apply(rows: list[dict[str, Any]], mapping: dict[str, dict[str, str]]) -> list[dict[str, Any]]:
    """Kodu etiketiyle değiştirilmiş satırlar. Etiketi bilinmeyen değer olduğu gibi kalır."""
    if not mapping or not rows:
        return rows
    names = {n.lower(): n for n in rows[0].keys()}
    active = {names[c.lower()]: labels for c, labels in mapping.items() if c.lower() in names}
    if not active:
        return rows
    out = []
    for row in rows:
        new = dict(row)
        for name, labels in active.items():
            k = _key(new.get(name))
            if k is not None and k in labels:
                new[name] = labels[k]
        out.append(new)
    return out
