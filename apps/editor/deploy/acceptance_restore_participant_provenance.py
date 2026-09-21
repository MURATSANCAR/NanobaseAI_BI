"""Repair the observed false review on the real acceptance event, without approving it.

Preserves the fact text and old claims. The replacement starts CANDIDATE and
must pass the live Critic and actor checks again. No historical generations change.
"""
import json

from editor import db, ledger, rebuild

GID = '3a987c80-95ba-48ce-a08e-820425cf438d'
EVENT = 'edbb7da8-9435-467a-bf78-88a189936ddb'
OLD_CLAIM = '57f9e572-7249-4cfd-9ee9-bdd4cd392087'

with db.tx() as c:
    before = rebuild.ensure_open(c, GID)
    assert c.execute("SELECT count(*) n FROM current_artifact WHERE generation_id=%s", (GID,)).fetchone()['n'] == 5
    event = c.execute("SELECT * FROM event WHERE id=%s AND generation_id=%s FOR UPDATE", (EVENT, GID)).fetchone()
    assert str(event['claim_id']) == OLD_CLAIM and event['participants'] == []
    old = c.execute("SELECT * FROM claim WHERE id=%s", (OLD_CLAIM,)).fetchone()
    assert old['status'] == 'NEEDS_REVIEW' and old['critic_note'].startswith('SUPPORTED:')
    reviews = c.execute("SELECT * FROM review_item WHERE claim_id=%s AND status='OPEN'", (OLD_CLAIM,)).fetchall()
    assert len(reviews) == 1 and reviews[0]['reason'].startswith('Kim yaptı: çıkarımın listesinde yok, ikinci okumaya göre eylemi yapan: Annesi')
    proof = c.execute("SELECT revision FROM knowledge_change WHERE generation_id=%s AND source_table='event' "
        "AND before_value->>'id'=%s AND before_value->'participants'<> '[]'::jsonb "
        "AND after_value->'participants'='[]'::jsonb", (GID, EVENT)).fetchall()
    assert proof, 'The extractor list must have been explicitly invalidated'
    new_id = ledger.supersede_claim(c, GID, OLD_CLAIM, claim=old['claim'],
        payload_update={'participants_invalidated': True}, created_by='system:participant-provenance-repair',
        note='Correct missing invalidation provenance; revalidate the unchanged source-backed fact')
    assert new_id
    c.execute("UPDATE event SET claim_id=%s WHERE id=%s", (new_id, EVENT))
    c.execute("UPDATE review_item SET status='CORRECTED',decided_by='system:participant-provenance-repair',"
        "decided_at=now(),decision=%s WHERE id=%s", (db.J({
            'reason': 'Invalidated extractor list was incorrectly treated as a negative participant assertion',
            'replacement_claim': new_id, 'automatic_approval': False,
            'invalidation_revisions': [p['revision'] for p in proof]}), reviews[0]['id']))
    after = c.execute("SELECT * FROM generation_state WHERE generation_id=%s", (GID,)).fetchone()
    assert after['validated_revision'] is None
    assert c.execute("SELECT count(*) n FROM event_actor WHERE event_id=%s", (EVENT,)).fetchone()['n'] == 0
    assert c.execute("SELECT status FROM claim WHERE id=%s", (new_id,)).fetchone()['status'] == 'CANDIDATE'

print(json.dumps({'generation_id': GID, 'event_id': EVENT, 'old_claim_id': OLD_CLAIM,
    'new_claim_id': new_id, 'unchanged_fact_text': old['claim'],
    'before_revision': before['knowledge_revision'], 'after_revision': after['knowledge_revision'],
    'false_review_id': str(reviews[0]['id']), 'new_claim_status': 'CANDIDATE',
    'automatic_approval': False}, ensure_ascii=False, indent=2))
