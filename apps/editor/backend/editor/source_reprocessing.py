"""Read-only reprocessing proposal; never schedules work or changes source records."""
import hashlib
import json
from pathlib import Path

VERSION = 'source-reprocessing-plan-v1'


def plan(generation, source_sha256, impact):
    """A partial dependency graph cannot authorize partial recomputation or reuse."""
    if str(generation['id']) != impact['generation_id']:
        raise ValueError('REPROCESSING_GENERATION_MISMATCH')
    result = {
        'version': VERSION,
        'generation_id': str(generation['id']),
        'content_version_id': str(generation['content_version_id']),
        'source_sha256': source_sha256,
        'target': impact['target'],
        'snapshot_sha256': impact['snapshot_sha256'],
        'strategy': 'FULL_GENERATION_FROM_ORIGINAL_SOURCE',
        'reason': 'DEPENDENCY_GRAPH_INCOMPLETE',
        'graph_scope': impact['graph_scope'],
        'graph_complete': False,
        'known_impacted_records': impact['total'],
        'known_impacted_records_are_complete': False,
        'requires_new_generation': True,
        'preserve_original_source': True,
        'preserve_existing_records': True,
        'preserve_existing_reviews': True,
        'reuse_policy': 'NOT_AUTHORIZED',
        'reuse_measurement': None,
        'execution_available': False,
        'job_created': False,
        'accepted': False,
        'semantic_acceptance': False,
        'plan_code_sha256': hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    result['plan_sha256'] = hashlib.sha256(json.dumps(result, sort_keys=True,
        ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()
    return result
