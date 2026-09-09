"""Independent live checks: SQL sums, Python ranking/calendar arithmetic, named columns."""
import ast
import json
import os
from pathlib import Path
from collections import defaultdict
from datetime import date, timedelta
from decimal import Decimal
from semantic_layer.config import SemanticSettings
from semantic_layer.profiler.connectors import connector_from_file
from result_comparison import norm, aligned_rows
from enduser_10000 import corpus

root = Path('/data/nanobaseai/bi/backups/product-quality-20260909')
settings = SemanticSettings.from_env()
c = connector_from_file(settings.connection_file)
source = Path(__file__).with_name('enduser_live_10000.py').read_text()
fn = next(n for n in ast.parse(source).body if isinstance(n, ast.FunctionDef) and n.name == 'reference')
ns = {}
exec(compile(ast.Module(body=[fn], type_ignores=[]), '<reference>', 'exec'), ns)
case = next(x for x in corpus() if x['id'] == 'P08802')
columns, rows, cut = c.execute(ns['reference'](case), 1000000)
actual = json.loads((root/'candidate-0-full.json').read_text())
truth = norm([[r[x['name']] for x in columns] for r in rows])
observed = norm(aligned_rows(actual, case))
results = [{'case': 'eight-table', 'referenceRows': len(rows), 'actualRows': len(observed),
            'passed': not cut and not actual['truncated'] and truth == observed}]

# Business metric: invoice net sales incl service and negative sales returns.
parts = []
for firm in ('211', '411'):
    parts.append(f'''SELECT DATEFROMPARTS(YEAR(F.DATE_),MONTH(F.DATE_),1) AS month,
        C.DEFINITION_ AS customer,
        SUM(CASE WHEN F.TRCODE IN (7,8,9) THEN F.NETTOTAL ELSE -F.NETTOTAL END) AS amount
        FROM dbo.LG_{firm}_01_INVOICE F
        LEFT JOIN dbo.LG_{firm}_CLCARD C ON F.CLIENTREF=C.LOGICALREF
        WHERE F.CANCELLED=0 AND F.TRCODE IN (2,3,7,8,9)
        AND F.DATE_ >= '2025-12-01' AND F.DATE_ < '2027-01-01'
        GROUP BY DATEFROMPARTS(YEAR(F.DATE_),MONTH(F.DATE_),1),C.DEFINITION_''')
sql = 'SELECT month, customer, SUM(amount) AS amount FROM ('+' UNION ALL '.join(parts)+') u GROUP BY month,customer'
columns, rows, cut = c.execute(sql, 1000000)
amounts = {(r['month'], norm([[r['customer']]])[0][0]): r['amount'] for r in rows}
monthly = defaultdict(set)
for r in rows:
    monthly[r['month']].add(r['amount'])
ranks = {month: {v: i+1 for i, v in enumerate(sorted(values, reverse=True))} for month, values in monthly.items()}
expected = []
for r in rows:
    if r['month'] < '2026-01-01':
        continue
    previous = (date.fromisoformat(r['month']) - timedelta(days=1)).replace(day=1).isoformat()
    old = amounts.get((previous, norm([[r['customer']]])[0][0]))
    change = None if old is None or old == 0 else 100.0*(r['amount']-old)/abs(old)
    expected.append([r['month'], r['customer'], r['amount'], ranks[r['month']][r['amount']], old, change])
actual = json.loads((root/'candidate-1-full.json').read_text())
keys = ['ay','muster','net_satis_tutar','aylik_sira','onceki_ay','yuzde_degisim']
observed = [[r[k] for k in keys] for r in actual['records']]
results.append({'case':'monthly-rank-change','referenceRows':len(expected),'actualRows':len(observed),
                'passed':not cut and not actual['truncated'] and norm(expected)==norm(observed)})
(root/'reference-results.json').write_text(json.dumps(results, indent=2))
print(json.dumps(results), flush=True)
c.close()
assert all(r['passed'] for r in results), results
