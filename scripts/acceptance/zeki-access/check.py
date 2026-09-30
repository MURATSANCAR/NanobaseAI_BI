"""Real chat API / Mongo group isolation checks. Only existing timasai signs in."""
import base64
import hashlib
import importlib.util
import json
import os
import secrets
import sqlite3
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

B = Path('/tmp/codex-zeki-access-0930')
os.umask(0o077)
spec = importlib.util.spec_from_file_location('directory', '/opt/timas-login/sync-directory.py')
d = importlib.util.module_from_spec(spec); spec.loader.exec_module(d)
config = json.loads(Path('/etc/nanobase/zeki-chat.json').read_text())
admin = d.Chat(config)


def mongo(script):
    return json.loads(subprocess.check_output(['docker', 'exec', 'zeki-mongo', 'mongosh', '--quiet', 'zeki', '--eval', script], text=True))


def save(state):
    d.atomic_json(B / 'state.json', state)


def call(state, method, path, body=None, **query):
    url = config['url'].rstrip('/') + '/api/v1/' + path
    if query: url += '?' + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, method=method, data=None if body is None else json.dumps(body).encode(),
        headers={'X-User-Id': state['uid'], 'X-Auth-Token': state['tokens'][-1], 'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req, timeout=20) as r: return r.status, json.load(r)
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read())


if sys.argv[1] == 'create':
    assert not (B / 'state.json').exists()
    u = admin.call('GET', 'users.info', username='timasai')['user']
    assert u['roles'] == ['user'] and u['active']
    s = {'uid': u['_id'], 'tokens': [], 'rooms': [], 'messages': [], 'initialRoles': u['roles']}; save(s)
    t = admin.call('POST', 'users.createToken', {'userId': u['_id'], 'secret': config['sso_secret']})['data']['authToken']
    s['tokens'].append(t); save(s)
    for kind, members in [('allowed', ['timasai']), ('denied', [])]:
        room = admin.call('POST', 'groups.create', {'name': 'zeki-access-' + kind + '-' + secrets.token_hex(4), 'members': members})['group']
        s[kind] = {'id': room['_id'], 'name': room['name']}; s['rooms'].append(room['_id']); save(s)
    print('Two temporary private rooms created; timasai remains ordinary user')
elif sys.argv[1] == 'check':
    s = json.loads((B / 'state.json').read_text()); checks = []
    def record(label, passed, **details):
        checks.append({'label': label, 'passed': bool(passed), **details})
        d.atomic_json(B / 'api-evidence.json', {'passed': all(r['passed'] for r in checks), 'checks': checks})
    groups = mongo('print(JSON.stringify(db.zeki_room.find({zekiCrmTeamId:{$exists:true}},{_id:1,t:1,name:1,fname:1}).toArray()));')
    subs = mongo('print(JSON.stringify(db.zeki_subscription.find({"u._id":' + json.dumps(s['uid']) + '},{rid:1}).toArray()));')
    joined = {r['rid'] for r in subs}
    forbidden = [r for r in groups if r['_id'] not in joined]
    record('CRM groups private', len(groups) == 12 and all(g['t'] == 'p' for g in groups), groupCount=len(groups))
    code, out = call(s, 'GET', 'groups.list', count=100)
    visible = {r['_id'] for r in out.get('groups', [])}
    record('Nonmember groups absent from list', code == 200 and not visible.intersection(g['_id'] for g in forbidden), forbiddenCount=len(forbidden))
    for g in forbidden:
        code, out = call(s, 'GET', 'groups.info', roomId=g['_id'])
        record('CRM nonmember group info', code in (400, 403, 404) and 'group' not in out, group=g['fname'], status=code)
    rid = s['denied']['id']
    for endpoint, query in [('groups.info', {'roomId': rid}), ('rooms.info', {'roomId': rid}),
                            ('groups.history', {'roomId': rid}), ('groups.members', {'roomId': rid}),
                            ('groups.messages', {'roomId': rid}), ('chat.search', {'roomId': rid, 'searchText': 'erişim'})]:
        code, out = call(s, 'GET', endpoint, **query)
        record('Denied ' + endpoint, code in (400, 403, 404) and not any(out.get(k) for k in ['messages', 'members', 'group', 'room']), status=code, error=out.get('errorType', out.get('error')))
    code, out = call(s, 'GET', 'groups.listAll')
    record('Global group administration denied', code in (400, 403), status=code)
    for endpoint in ['chat.sendMessage', 'chat.postMessage']:
        code, _ = call(s, 'POST', endpoint, {})
        record('Empty write rejected ' + endpoint, code in (400, 422), status=code)
    mid = 'access' + secrets.token_hex(12); s['messages'].append(mid); save(s)
    code, out = call(s, 'POST', 'chat.sendMessage', {'message': {'_id': mid, 'rid': rid, 'msg': 'Erişim doğrulaması'}})
    count = mongo('print(JSON.stringify(db.zeki_message.countDocuments({_id:' + json.dumps(mid) + '})));')
    record('Nonmember send rejected without DB write', code in (400, 403) and count == 0, status=code, storedMessages=count)
    mid = 'access' + secrets.token_hex(12); s['messages'].append(mid); save(s)
    code, out = call(s, 'POST', 'chat.sendMessage', {'message': {'_id': mid, 'rid': s['allowed']['id'], 'msg': 'Üyesi olduğum grupta erişim doğrulaması'}})
    count = mongo('print(JSON.stringify(db.zeki_message.countDocuments({_id:' + json.dumps(mid) + ',"u._id":' + json.dumps(s['uid']) + '})));')
    record('Member send accepted and persisted', code == 200 and count == 1, status=code, storedMessages=count)
    code, out = call(s, 'GET', 'groups.history', roomId=s['allowed']['id'])
    record('Member reads own message', code == 200 and any(m['_id'] == mid for m in out.get('messages', [])), status=code)
    print(json.dumps({'passed': all(c['passed'] for c in checks), 'total': len(checks), 'failed': [c for c in checks if not c['passed']]}, ensure_ascii=False))
elif sys.argv[1] == 'cleanup':
    s = json.loads((B / 'state.json').read_text()); counts = {'rooms': 0, 'tokens': 0}
    for rid in s['rooms']:
        if mongo('print(JSON.stringify(db.zeki_room.countDocuments({_id:' + json.dumps(rid) + '})));'):
            admin.call('POST', 'rooms.delete', {'roomId': rid}); counts['rooms'] += 1
    tokens = s['tokens']
    if (B / 'browser-tokens.json').exists(): tokens += json.loads((B / 'browser-tokens.json').read_text())
    hashes = [base64.b64encode(hashlib.sha256(t.encode()).digest()).decode() for t in tokens]
    script = 'const uid=' + json.dumps(s['uid']) + ';const h=' + json.dumps(hashes) + ';'
    script += 'const count=()=>db.users.findOne({_id:uid}).services.resume.loginTokens.filter(t=>h.includes(t.hashedToken)).length;const n=count();db.users.updateOne({_id:uid},{$pull:{"services.resume.loginTokens":{hashedToken:{$in:h}}}});print(JSON.stringify({removed:n,remaining:count()}));'
    counts['tokens'] = mongo(script)
    counts['trash'] = mongo('print(JSON.stringify(db.zeki__trash.deleteMany({$or:[{_id:{$in:' + json.dumps(s['messages']) + '}},{rid:{$in:' + json.dumps(s['rooms']) + '}}]}).deletedCount));')
    p = B / 'session.json'
    if p.exists():
        with sqlite3.connect('/var/lib/timas-login/sessions.sqlite') as db:
            counts['portalSessions'] = db.execute('DELETE FROM sessions WHERE token=?', (hashlib.sha256(json.loads(p.read_text())['token'].encode()).hexdigest(),)).rowcount
        p.unlink()
    (B / 'browser-tokens.json').unlink(missing_ok=True); (B / 'state.json').unlink()
    d.atomic_json(B / 'cleanup-evidence.json', counts); print(json.dumps(counts))
