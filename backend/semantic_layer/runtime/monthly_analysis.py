"""Monthly ranking and previous-calendar-month change over certified aggregates."""
from copy import deepcopy
from datetime import timedelta
import re
from semantic_layer.normalize import fold, normalize_term
from semantic_layer.models import SemanticType


def resolve_frame(resolver, question, today):
    text = fold(question).strip().rstrip('.?')
    frame = re.fullmatch(r'(.+?)\s+gore sirala ve her (.+?) onceki aya gore yuzde degisimini goster', text)
    if not frame or 'her ay' not in frame[1]:
        return None
    base_text = frame[1].replace('her ay icin', 'aylik').replace('her ay', 'aylik')
    q = resolver.resolve(base_text, today)
    groups = { (s.mapping.entity, s.mapping.column): s for s in q.slots
               if s.semantic_type == SemanticType.COLUMN and s.mapping and s.status == 'CERTIFIED' }
    q.question = question
    q.analytics = {'kind': 'MONTHLY_RANK_CHANGE', 'baseQuestion': base_text,
                   'missingPreviousMonth': 'NULL', 'zeroDenominator': 'NULL',
                   'ranking': 'DENSE_RANK', 'direction': 'DESC'}
    if (len(groups) != 1 or len(q.metrics) != 1 or
            normalize_term(frame[2]) != normalize_term(next(iter(groups.values())).term)):
        q.clarification.append('Aylık sıralama ve değişim için tek bir boyut ve ölçü belirtin.')
        return q
    q.group_by = list(groups.values())
    q.grain = 'MONTH'
    q.explanation.append('Her ay içinde sıralama; aynı boyutun önceki takvim ayına göre yüzde değişim. Önceki ay yoksa veya değeri sıfırsa değişim boş bırakılır.')
    return q


def compile_monthly(compiler, q, catalog):
    from semantic_layer.history.sql_facts import parse_sql
    from semantic_layer.runtime.audit import unmet_obligations, audit_sql
    if compiler.d.family not in ('tsql', 'sqlite') or len(q.temporal) != 1:
        return None
    base = deepcopy(q)
    base.analytics = None
    base.question = q.analytics['baseQuestion']
    base.limit = None
    period = base.temporal[0]
    if not period.start or not period.end or period.start.day != 1:
        return None
    requested_start, requested_end = period.start, period.end
    period.start = (period.start - timedelta(days=1)).replace(day=1)
    q.analytics['lookbackStart'] = period.start.isoformat()
    result = compiler.compile(base, catalog)
    if result is None or unmet_obligations(base, result.sql) or audit_sql(base, result.sql):
        return None
    tree = parse_sql(result.sql)
    tree.set('order', None)
    names = [x.alias_or_name for x in tree.expressions]
    if len(names) != 3 or names[0] != 'ay':
        return None
    month, dimension, metric = [compiler.d.q(n) for n in names]
    previous = (f'DATEADD(month, -1, c.{month})' if compiler.d.family == 'tsql'
                else f"date(c.{month}, '-1 month')")
    inner = tree.sql(dialect='tsql' if compiler.d.family == 'tsql' else 'sqlite')
    sql = f'''WITH monthly AS ({inner})
SELECT c.{month}, c.{dimension}, c.{metric},
 DENSE_RANK() OVER (PARTITION BY c.{month} ORDER BY c.{metric} DESC) AS aylik_sira,
 p.{metric} AS onceki_ay,
 100.0 * (c.{metric} - p.{metric}) / NULLIF(ABS(p.{metric}), 0) AS yuzde_degisim
FROM monthly c LEFT JOIN monthly p
 ON (c.{dimension} = p.{dimension} OR (c.{dimension} IS NULL AND p.{dimension} IS NULL))
 AND p.{month} = {previous}
WHERE c.{month} >= '{requested_start.isoformat()}' AND c.{month} < '{requested_end.isoformat()}'
ORDER BY c.{month}, aylik_sira, c.{dimension}'''
    q.analytics.update(expectedSql=sql, baseSql=result.sql)
    result.sql = sql
    result.explain.append(q.explanation[-1])
    return result


def check(q, sql, checker, **kwargs):
    from semantic_layer.history.sql_facts import parse_sql
    expected = q.analytics.get('expectedSql')
    if not expected or parse_sql(sql) != parse_sql(expected):
        return ['Aylık sıralama/değişim planı son SQL ile eşleşmiyor']
    base = deepcopy(q)
    base.analytics = None
    base.question = q.analytics['baseQuestion']
    if q.analytics.get('lookbackStart'):
        from datetime import date
        base.temporal[0].start = date.fromisoformat(q.analytics['lookbackStart'])
    return checker(base, q.analytics['baseSql'], **kwargs)
