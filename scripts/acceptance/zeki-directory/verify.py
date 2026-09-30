"""Read-only acceptance against live AD, CRM SQL, chat API and independent Mongo.
Run on the test server after sync. No fixtures, accounts, messages or groups are created.
"""
import hashlib
import importlib.util
import json
import re
import subprocess
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from ldap3 import Connection, NONE, NTLM, Server, SUBTREE
from semantic_layer.profiler.connectors import connector_from_file

BASE = Path('/tmp/codex-zeki-directory-0930')
config = json.load(open('/etc/nanobase/zeki-chat.json'))
ad_config = json.load(open('/etc/nanobase/timas-ad.json'))
spec = importlib.util.spec_from_file_location('portal', '/opt/timas-login/server.py')
portal = importlib.util.module_from_spec(spec)
spec.loader.exec_module(portal)
portal.ensure_md4()  # cryptographic adapter only; reference selection/mapping below is independent.


def one(value):
    return value[0] if isinstance(value, list) and value else value


def norm_guid(value):
    value = one(value)
    return str(uuid.UUID(bytes_le=value)) if isinstance(value, bytes) else str(value or '').strip('{}').lower()


def api(endpoint, **query):
    url = config['url'].rstrip('/') + '/api/v1/' + endpoint
    if query:
        url += '?' + urllib.parse.urlencode(query)
    req = urllib.request.Request(url, headers={'X-User-Id': config['user_id'], 'X-Auth-Token': config['token']})
    with urllib.request.urlopen(req, timeout=30) as response:
        return json.load(response)


def pages(endpoint, key, **query):
    rows = []
    total = None
    while total is None or len(rows) < total:
        data = api(endpoint, count=100, offset=len(rows), **query)
        assert data['success'] and data[key]
        rows += data[key]
        total = data['total']
    assert len(rows) == total
    return rows


conn = Connection(Server(ad_config['host'], port=int(ad_config.get('port', 389)), get_info=NONE, connect_timeout=5),
                  user=ad_config['netbios'] + '\\' + ad_config['bind_user'], password=ad_config['bind_password'],
                  authentication=NTLM, receive_timeout=15)
assert conn.bind()
people = {}
try:
    for entry in conn.extend.standard.paged_search(ad_config['base_dn'],
            '(&(objectCategory=person)(objectClass=user)(!(userAccountControl:1.2.840.113556.1.4.803:=2)))',
            SUBTREE, attributes=['sAMAccountName', 'displayName', 'objectGUID'], paged_size=100, generator=True):
        if entry.get('type') != 'searchResEntry':
            continue
        data = entry['attributes']
        username = str(one(data['sAMAccountName']))
        if username.lower() in {'admin', 'administrator', 'system', 'user', 'all', 'here'}:
            chat_name = 'ad-' + username.lower()
        elif re.fullmatch('[0-9a-zA-Z-_.]+', username):
            chat_name = username
        else:
            chat_name = 'ad-' + hashlib.sha256(username.lower().encode()).hexdigest()[:20]
        people[username.lower()] = {'guid': norm_guid(data['objectGUID']), 'chatName': chat_name.lower(),
                                     'name': str(one(data.get('displayName')) or username)}
    assert conn.result['result'] == 0 and people
finally:
    conn.unbind()

users = {u['username'].lower(): u for u in pages('users.list', 'users') if u.get('username')}
for source in people.values():
    user = users[source['chatName']]
    assert user['active'] and user['name'] == source['name']

sql = '''SELECT CAST(t.TeamId AS nvarchar(40)) AS teamId, t.Name AS name,
CAST(u.ActiveDirectoryGuid AS nvarchar(40)) AS adGuid, u.DomainName AS domainName
FROM Timas_MSCRM.dbo.TeamBase t
JOIN Timas_MSCRM.dbo.BusinessUnitBase b ON b.BusinessUnitId=t.BusinessUnitId
JOIN Timas_MSCRM.dbo.TeamMembership m ON m.TeamId=t.TeamId
JOIN Timas_MSCRM.dbo.SystemUserBase u ON u.SystemUserId=m.SystemUserId
WHERE b.IsDisabled=0 AND u.IsDisabled=0 AND u.AccessMode IN (0,1)'''
crm = connector_from_file('/data/nanobaseai/bi/secrets/crm-mssql-connection.json')
crm.query_timeout = 45
columns, records, truncated = crm.execute(sql, 100000)
assert not truncated
by_guid = {p['guid']: p for p in people.values()}
expected = {}
for row in records:
    ag = norm_guid(row['adGuid'])
    p = by_guid.get(ag) if ag else people.get(str(row['domainName'] or '').rsplit('\\', 1)[-1].split('@')[0].lower())
    if not p:
        continue
    team = expected.setdefault(norm_guid(row['teamId']), {'name': row['name'], 'members': set()})
    team['members'].add(users[p['chatName']]['_id'])
rooms = {r['zekiCrmTeamId']: r for r in pages('groups.listAll', 'groups') if r.get('zekiCrmTeamId')}
assert set(rooms) == set(expected)
checks = []
for key, reference in expected.items():
    room = rooms[key]
    assert room['t'] == 'p' and room['fname'] == reference['name']
    expected_ids = reference['members'] | {config['user_id']}
    actual = {u['_id'] for u in pages('groups.members', 'members', roomId=room['_id'])}
    mongo_query = 'print(JSON.stringify(db.zeki_subscription.find({rid:' + json.dumps(room['_id']) + '},{"u._id":1}).toArray().map(x=>x.u._id)));'
    mongo = set(json.loads(subprocess.check_output(['docker', 'exec', 'zeki-mongo', 'mongosh', '--quiet', 'zeki', '--eval', mongo_query], text=True)))
    assert actual == expected_ids == mongo
    checks.append({'name': reference['name'], 'crmActiveADMembers': len(reference['members']),
                   'apiMembersIncludingServiceOwner': len(actual), 'matchesIndependentCRMAndMongo': True})
state = json.load(open('/var/lib/zeki-directory-sync/state.json'))
for tracked in state['users'].values():
    user = next(u for u in users.values() if u['_id'] == tracked['id'])
    assert user['roles'] == ['user']
result = {'passed': True, 'activeAD': len(people), 'mappedActiveAccounts': len(people),
          'createdManagedAccounts': len(state['users']), 'privateCRMGroups': len(checks),
          'groups': checks, 'newAccountsAreOrdinaryUsers': True, 'sourcesReadOnly': True}
(BASE / 'acceptance.json').write_text(json.dumps(result, ensure_ascii=False, indent=2))
print(json.dumps(result, ensure_ascii=False))
