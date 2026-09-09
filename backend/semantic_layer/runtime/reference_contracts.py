"""Declared reference precedence, independent of ERP table names."""
from __future__ import annotations
import re


def reference_rule(mapping, fact):
    return ((mapping.extra or {}).get('reference_resolution') or {}).get(fact)


def reference_predicate(mapping, fact, rule, quote=lambda name:name):
    via = rule['via']
    primary, fallback = rule.get('primary_column'), rule.get('fallback_column')
    target = rule['target_column']
    if not primary:
        return f'{mapping.entity}.{quote(target)} = {via}.{quote(fallback)}' if fallback else None
    if not fallback or rule.get('empty_value',0) != 0:
        raise ValueError('unsupported reference precedence')
    names = [fact,via,mapping.entity,primary,fallback,target]
    if not all(re.fullmatch(r'[A-Za-z_][A-Za-z0-9_]*',name or '') for name in names):
        raise ValueError('invalid reference identifier')
    return (f'{mapping.entity}.{quote(target)} = COALESCE(NULLIF({fact}.{quote(primary)}, 0), '
            f'{via}.{quote(fallback)})')


def via_predicate(fact, rule, quote=lambda name:name):
    return f"{fact}.{quote(rule['via_column'])} = {rule['via']}.{quote(rule['via_key'])}"
