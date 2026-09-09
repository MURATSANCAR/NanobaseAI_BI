"""Candidate code against a private catalog copy and the connected real datasource."""
import json
import os
from pathlib import Path
import time
from semantic_layer.config import SemanticSettings
from semantic_layer.store.catalog_store import open_store
from semantic_layer.nightly import Release
from semantic_bridge.app import build_runtime

root = Path('/data/nanobaseai/bi/backups/product-quality-20260909')
settings = SemanticSettings.from_env()
stage = root / 'catalog.sqlite'
if not stage.exists():
    Release(open_store(settings.store_dsn, create=False), settings.tenant_id, settings.datasource_id,
            root / 'catalog-journal.json').prepare('sqlite:///' + str(stage))
settings.store_dsn = 'sqlite:///' + str(stage)
os.environ['SEMANTIC_LLM'] = '0'
os.environ['SEMANTIC_REFRESH_SEC'] = '0'
r = build_runtime(settings)
questions = [
    'Ocak 2024 için müşteri, ürün, ödeme planı, satış temsilcisi, teslimat şehri ve birim bazında satılan adet göster.',
    '2026 yılında her ay için müşterileri net satış tutarına göre sırala ve her müşterinin önceki aya göre yüzde değişimini göster.',
]
for i, question in enumerate(questions):
    started = time.monotonic()
    answer = r.ask(question, thread_id=None, sample_size=50)
    snapshot = r.stored_result(answer['resultId']) if answer.get('resultId') else None
    if snapshot:
        (root / f'candidate-{i}-full.json').write_text(json.dumps(snapshot, ensure_ascii=False, default=str))
    (root / f'candidate-{i}.json').write_text(json.dumps(answer, ensure_ascii=False, default=str))
    print(json.dumps({'case': i, 'seconds': round(time.monotonic()-started, 2),
        'type': answer.get('type'), 'rows': answer.get('totalRows'), 'reason': answer.get('explanation'),
        'truncated': answer.get('truncated'), 'savedRows': len(snapshot['records']) if snapshot else None,
        'semantic': answer.get('semantic') if not snapshot else None}, ensure_ascii=False), flush=True)
r.connector.close()
