"""One authorized, source-backed edit on the 2026-09-21 real acceptance generation.

Run only on tt-gpu after all five initial outputs are current. This is an actual
editorial clarification, not an injected false fact or a synthetic fixture.
Uses the production ledger, evidence checks and canonical event transaction.
"""
import json

from editor import db, ledger, rebuild

GID = '3a987c80-95ba-48ce-a08e-820425cf438d'
EVENT = 'edbb7da8-9435-467a-bf78-88a189936ddb'
OLD = "Annesi, merak eden ve merakının peşinden gidenlere 'Bilim Vombatı' denildiğini açıklar."
NEW = "Yavru Vombat'ın annesi, merak eden ve merakının peşinden gidenlere 'Bilim Vombatı' denildiğini açıklar."
NOTE = "Gerçek kaynak s6 p3–p6: 'Annesi' öznesinin hangi karaktere ait olduğunu açıklaştırma."

with db.tx() as c:
    state = rebuild.ensure_open(c, GID)
    assert state['producer_completed'] and state['knowledge_revision'] == state['validated_revision']
    assert c.execute("SELECT count(*) n FROM current_artifact WHERE generation_id=%s", (GID,)).fetchone()['n'] == 5
    event = c.execute("SELECT * FROM event WHERE id=%s AND generation_id=%s FOR UPDATE", (EVENT, GID)).fetchone()
    assert event['summary'] == OLD, 'Correction already applied or source event changed'
    snapshot = c.execute("SELECT * FROM knowledge_snapshot WHERE generation_id=%s AND revision=%s",
                         (GID, state['knowledge_revision'])).fetchone()
    old_output = c.execute("SELECT * FROM current_artifact WHERE generation_id=%s AND kind='report'", (GID,)).fetchone()
    actor_count = c.execute("SELECT count(*) n FROM event_actor WHERE event_id=%s", (EVENT,)).fetchone()['n']
    idx = ledger.PageIndex.load(c, GID)
    extra = []
    for paragraph, quote in ((3, 'Yavru Vombat, bunu da merak etmişti:'), (5, 'Annesi gülümseyerek yanıtladı:')):
        assert idx.verify(6, quote, 'TEXT', paragraph), 'Actual source quote must match exactly'
        eid, verified = ledger.save_evidence(c, GID, idx, page=6, quote=quote, paragraph_idx=paragraph)
        assert verified
        extra.append(eid)
    new_id = ledger.supersede_claim(c, GID, str(event['claim_id']), claim=NEW,
        payload_update={'editorial_clarification': NOTE}, created_by='editor:controlled-acceptance', note=NOTE)
    assert new_id
    for eid in extra:
        c.execute("INSERT INTO claim_evidence(claim_id,evidence_id) VALUES(%s,%s)", (new_id, eid))
    c.execute("UPDATE event SET claim_id=%s,summary=%s,participants='{}'::text[] WHERE id=%s",
              (new_id, NEW, EVENT))
    after = c.execute("SELECT * FROM generation_state WHERE generation_id=%s", (GID,)).fetchone()
    actors_after = c.execute("SELECT count(*) n FROM event_actor WHERE event_id=%s", (EVENT,)).fetchone()['n']
    assert after['knowledge_revision'] > state['knowledge_revision']
    assert after['validated_revision'] is None and actors_after == 0
    assert c.execute("SELECT count(*) n FROM current_artifact WHERE generation_id=%s", (GID,)).fetchone()['n'] == 0

# Real old output publication attempt: the production writer must refuse it.
try:
    rebuild.publish(snapshot['content'], snapshot['input_digest'], 'report',
                    old_output['build_key'], old_output['content'])
except rebuild.Superseded as exc:
    refused = str(exc)
else:
    raise AssertionError('Old revision publication was not refused')

print(json.dumps({'generation_id': GID, 'event_id': EVENT, 'old_claim_id': str(event['claim_id']),
    'new_claim_id': new_id, 'old_text': OLD, 'new_text': NEW, 'source_note': NOTE,
    'before_revision': state['knowledge_revision'], 'after_revision': after['knowledge_revision'],
    'actors_before': actor_count, 'actors_after': actors_after, 'old_publish_refused': refused,
    'all_current_outputs_invalidated': True}, ensure_ascii=False, indent=2))
