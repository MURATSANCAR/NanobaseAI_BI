"""Run only on the real test server. Uses timasai; cleanup mode removes exact owned artifacts."""
import base64
import hashlib
import importlib.util
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

BASE = Path('/tmp/codex-zeki-mention-0930')
os.umask(0o077)
spec = importlib.util.spec_from_file_location('directory', '/opt/timas-login/sync-directory.py')
d = importlib.util.module_from_spec(spec)
spec.loader.exec_module(d)
config = json.loads(Path('/etc/nanobase/zeki-chat.json').read_text())
admin = d.Chat(config)


def mongo(script):
    return json.loads(subprocess.check_output(['docker', 'exec', 'zeki-mongo', 'mongosh', '--quiet', 'zeki',
                                              '--eval', script], text=True))


def save(state):
    d.atomic_json(BASE / 'accept-state.json', state)


if sys.argv[1] == 'create':
    assert not (BASE / 'accept-state.json').exists(), 'Clean previous acceptance first'
    user = admin.call('GET', 'users.info', username='timasai')['user']
    state = {'userId': user['_id'], 'messages': [], 'tokens': [], 'rooms': []}
    save(state)
    issued = admin.call('POST', 'users.createToken', {'userId': user['_id'], 'secret': config['sso_secret']})['data']
    state['tokens'].append(issued['authToken']); save(state)
    api = d.Chat({'url': config['url'], 'user_id': user['_id'], 'token': issued['authToken']})
    room = api.call('POST', 'groups.create', {'name': 'zeki-mention-kabul-' + secrets.token_hex(4), 'members': []})['group']
    state['rooms'].append(room['_id']); save(state)
    state['existingDM'] = mongo('print(JSON.stringify(db.zeki_room.findOne({t:"d",uids:{$all:[' +
                                 json.dumps(user['_id']) + ',"zeki.bot"]}},{_id:1})));')
    save(state)
    for label, question in [('plain', 'Bu mesaj botu etiketlemiyor.'), ('intro', '@zeki.bot Merhaba'),
                            ('empty', '@zeki.bot'), ('data', '@zeki.bot 2026 toptan satış faturası sayısı')]:
        mid = 'accept' + secrets.token_hex(12)
        state['messages'].append({'id': mid, 'label': label}); save(state)
        api.call('POST', 'chat.sendMessage', {'message': {'_id': mid, 'rid': room['_id'], 'msg': question}})
    request = urllib.request.Request('http://127.0.0.1:8795/api/v1/chat/mention-answer',
        data=json.dumps({'username': 'timasai', 'question': 'Merhaba', 'messageId': 'unauthenticated'}).encode(),
        headers={'Content-Type': 'application/json'})
    try:
        urllib.request.urlopen(request, timeout=10)
        raise AssertionError('Unauthenticated worker accepted')
    except urllib.error.HTTPError as e:
        assert e.code == 401
        state['unauthenticatedStatus'] = e.code; save(state)
    print(json.dumps({'sent': len(state['messages']), 'unauthenticatedStatus': 401}))
elif sys.argv[1] == 'check':
    state = json.loads((BASE / 'accept-state.json').read_text())
    rows = []
    with sqlite3.connect('/var/lib/zeki-mention/queue.sqlite') as db:
        for item in state['messages']:
            job = db.execute('SELECT status,reply,query_id,room_id FROM jobs WHERE id=?', (item['id'],)).fetchone()
            reply_id = 'zekiai' + hashlib.sha256(item['id'].encode()).hexdigest()[:40]
            reply = mongo('print(JSON.stringify(db.zeki_message.findOne({_id:' + json.dumps(reply_id) +
                          '},{_id:1,rid:1,msg:1,u:1})));')
            row = {'label': item['label'], 'job': job, 'reply': reply}
            if item['label'] == 'plain':
                row['passed'] = job is None and reply is None
            else:
                row['passed'] = bool(job and job[0] == 'sent' and reply and reply['u']['_id'] == 'zeki.bot'
                                     and reply['rid'] != state['rooms'][0] and reply['msg'] == job[1])
                if item['label'] in ('intro', 'data'):
                    row['passed'] = row['passed'] and bool(job[2])
            rows.append(row)
    result = {'passed': all(r['passed'] for r in rows), 'checks': rows,
              'unauthenticatedStatus': state['unauthenticatedStatus']}
    d.atomic_json(BASE / 'api-evidence.json', result)
    print(json.dumps(result, ensure_ascii=False))
elif sys.argv[1] == 'cleanup':
    state = json.loads((BASE / 'accept-state.json').read_text())
    mids = [m['id'] for m in state['messages']]
    replies = ['zekiai' + hashlib.sha256(m.encode()).hexdigest()[:40] for m in mids]
    # API deletes whole temporary source room. Only delete newly created DM if every message is ours.
    counts = {'rooms': 0, 'messages': 0, 'tokens': 0, 'queue': 0}
    for rid in state['rooms']:
        exists = mongo('print(JSON.stringify(db.zeki_room.countDocuments({_id:' + json.dumps(rid) + '})));')
        if exists:
            admin.call('POST', 'rooms.delete', {'roomId': rid}); counts['rooms'] += 1
    if not state.get('existingDM'):
        dm = mongo('print(JSON.stringify(db.zeki_room.findOne({t:"d",uids:{$all:[' +
                   json.dumps(state['userId']) + ',"zeki.bot"]}},{_id:1})));')
        if dm:
            others = mongo('print(JSON.stringify(db.zeki_message.countDocuments({rid:' + json.dumps(dm['_id']) +
                           ',_id:{$nin:' + json.dumps(replies) + '}})));')
            if others == 0:
                admin.call('POST', 'rooms.delete', {'roomId': dm['_id']}); counts['rooms'] += 1
    for mid in replies:
        msg = mongo('print(JSON.stringify(db.zeki_message.findOne({_id:' + json.dumps(mid) + '},{rid:1})));')
        if msg:
            admin.call('POST', 'chat.delete', {'roomId': msg['rid'], 'msgId': mid})
            counts['messages'] += 1
    if not state.get('existingDM'):
        dm = mongo('print(JSON.stringify(db.zeki_room.findOne({t:"d",uids:{$all:[' +
                   json.dumps(state['userId']) + ',"zeki.bot"]}},{_id:1})));')
        if dm:
            left = mongo('print(JSON.stringify(db.zeki_message.countDocuments({rid:' + json.dumps(dm['_id']) + '})));')
            if left == 0:
                admin.call('POST', 'rooms.delete', {'roomId': dm['_id']}); counts['rooms'] += 1
    hashes = [base64.b64encode(hashlib.sha256(t.encode()).digest()).decode() for t in state['tokens']]
    browser_tokens = BASE / 'chat-tokens.json'
    if browser_tokens.exists():
        hashes += [base64.b64encode(hashlib.sha256(t.encode()).digest()).decode() for t in json.loads(browser_tokens.read_text())]
    script = 'const id=' + json.dumps(state['userId']) + ';const hashes=' + json.dumps(hashes) + ';'
    script += 'const before=(db.users.findOne({_id:id}).services.resume.loginTokens||[]).filter(t=>hashes.includes(t.hashedToken)).length;'
    script += 'db.users.updateOne({_id:id},{$pull:{"services.resume.loginTokens":{hashedToken:{$in:hashes}}}});print(JSON.stringify(before));'
    counts['tokens'] = mongo(script)
    with sqlite3.connect('/var/lib/zeki-mention/queue.sqlite') as db:
        for mid in mids:
            counts['queue'] += db.execute('DELETE FROM jobs WHERE id=?', (mid,)).rowcount
    # Delete only acceptance trash IDs generated by normal API cleanup.
    counts['trash'] = mongo('print(JSON.stringify(db.zeki__trash.deleteMany({"_id":{$in:' + json.dumps(mids + replies + state['rooms']) + '}}).deletedCount));')
    d.atomic_json(BASE / 'cleanup-evidence.json', counts)
    (BASE / 'accept-state.json').unlink()
    browser_tokens.unlink(missing_ok=True)
    print(json.dumps(counts))
