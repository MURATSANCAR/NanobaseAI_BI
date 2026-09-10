"""Compare result bags without losing the identity of their columns."""
from collections import Counter
from decimal import Decimal
import math


def cell(value):
    if value is None:
        return ('null', '')
    if isinstance(value, bool):
        return ('bool', str(value))
    if isinstance(value, (int, float, Decimal)):
        if not math.isfinite(float(value)):
            raise ValueError('Nonfinite result cannot be certified')
        return ('number', str(Decimal(str(value)).quantize(Decimal('0.00001'))))
    return ('text', str(value).rstrip().translate(str.maketrans({'I': 'ı', 'İ': 'i'})).lower())


def norm(rows):
    return sorted(tuple(cell(v) for v in row) for row in rows)


def aligned_rows(response, case):
    # Output aliases are a contract, not a guessed permutation of values.
    aliases = {'müşteri': 'muster', 'ürün': 'urun', 'ödeme planı': 'odem_pla',
               'satış temsilcisi': 'satis_temsilc', 'teslimat şehri': 'teslimat_sehr', 'birim': 'bir'}
    dimensions = [aliases[d] for d in case['dimensions']]
    names = [c['name'] for c in response['columns']]
    measures = [n for n in names if n not in dimensions]
    if not set(dimensions) <= set(names) or len(measures) != 1 or len(set(names)) != len(names):
        raise ValueError(f'Output column contract differs: {names}; dimensions={dimensions}')
    ordered = dimensions + measures
    return [[row[name] for name in ordered] for row in response['records']]
