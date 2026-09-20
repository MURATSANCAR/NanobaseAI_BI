"""Declared reference precedence, independent of ERP table names."""
from __future__ import annotations
import re


def reference_rule(mapping, fact, filters=()):
    rule = ((mapping.extra or {}).get('reference_resolution') or {}).get(fact)
    if rule and _via_declared_absent(rule, fact, filters):
        return None
    return rule


def _bare(name):
    return re.sub(r'^LG_', '', str(name or '').upper())


def _via_declared_absent(rule, fact, filters):
    """The question itself says the intermediate record does not exist.

    A rule reads a reference through another record (the customer of a line is its invoice's
    customer). When a filter of the same question pins that link to its empty value — lines with
    no invoice — there is no intermediate record to read through: the inner join returns nothing
    and the answer is an empty table that looks like "no such rows". The rule does not apply to
    such a question; the fact's own reference is used instead.
    """
    column, empty = str(rule.get('via_column') or '').upper(), str(rule.get('empty_value', 0))
    if not column:
        return False
    pinned = re.compile(r'(?i)\b%s\.\[?%s\]?\s*(?:=\s*%s\b|IN\s*\(\s*%s\s*\)|IS\s+NULL)'
                        % (re.escape(_bare(fact)), re.escape(column), re.escape(empty), re.escape(empty)))
    for m in filters or ():
        if m is None or _bare(getattr(m, 'entity', '')) != _bare(fact):
            continue
        values = [str(v).strip() for v in (getattr(m, 'values', None) or [])]
        if (str(getattr(m, 'column', '') or '').upper() == column and values
                and getattr(m, 'operator', '=') in ('=', 'IN') and all(v == empty for v in values)):
            return True
        for condition in (getattr(m, 'extra', None) or {}).get('conditions') or []:
            if pinned.search(re.sub(r'(?i)\bLG_', '', str(condition))):
                return True
    return False


def reference_predicate(mapping, fact, rule, quote=lambda name:name):
    via = rule['via']
    primary, fallback = rule.get('primary_column'), rule.get('fallback_column')
    target = rule['target_column']
    own = rule.get('own_column')
    if not primary and own and fallback:
        # The intermediate record is optional (a dispatch line not invoiced yet has no invoice): the
        # reference is read through it where it exists and from the fact's own column where it does
        # not. Read only through it, those rows were dropped and a breakdown no longer added up to
        # the total it breaks down.
        names = [fact, via, mapping.entity, own, fallback, target]
        if not all(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*', name or '') for name in names):
            raise ValueError('invalid reference identifier')
        return f'{mapping.entity}.{quote(target)} = COALESCE({via}.{quote(fallback)}, {fact}.{quote(own)})'
    if not primary:
        return f'{mapping.entity}.{quote(target)} = {via}.{quote(fallback)}' if fallback else None
    if not fallback or rule.get('empty_value',0) != 0:
        raise ValueError('unsupported reference precedence')
    names = [fact,via,mapping.entity,primary,fallback,target]
    if not all(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',name or '') for name in names):
        raise ValueError('invalid reference identifier')
    return (f'{mapping.entity}.{quote(target)} = COALESCE(NULLIF({fact}.{quote(primary)}, 0), '
            f'{via}.{quote(fallback)})')


def own_predicate(mapping, fact, rule, quote=lambda name:name):
    """The same reference read from the fact's own column, when the rule declares one; else None."""
    own = rule.get('own_column')
    if not own or rule.get('primary_column'):
        return None
    return f"{mapping.entity}.{quote(rule['target_column'])} = {fact}.{quote(own)}"


def via_is_optional(rule):
    return bool(rule.get('own_column')) and not rule.get('primary_column')


def via_predicate(fact, rule, quote=lambda name:name):
    return f"{fact}.{quote(rule['via_column'])} = {rule['via']}.{quote(rule['via_key'])}"
