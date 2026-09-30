#!/usr/bin/env python3
"""AD/CRM read-only -> local chat accounts and private CRM team rooms.

Run on the portal host. Dry-run by default; --apply writes only to the chat API
and its own checkpoint. Never grants an AD/CRM role as a chat administrator.
"""
from __future__ import annotations

import argparse
import fcntl
import importlib.util
import json
import os
import re
import secrets
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


class SyncError(RuntimeError):
    pass


def scalar(value):
    return value[0] if isinstance(value, list) and value else value if not isinstance(value, list) else None


def guid(value):
    value = scalar(value)
    if isinstance(value, bytes):
        return str(uuid.UUID(bytes_le=value))
    return str(value or '').strip('{}').lower()


def account(value):
    return str(value or '').rsplit('\\', 1)[-1].split('@', 1)[0].strip().lower()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix('.tmp')
    with temp.open('w') as stream:
        os.chmod(temp, 0o600)
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.flush()
        os.fsync(stream.fileno())
    temp.replace(path)


def read_ad(portal_path):
    spec = importlib.util.spec_from_file_location('zeki_portal_login', portal_path)
    portal = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(portal)
    cfg = portal.ad_config()
    if not cfg:
        raise SyncError('AD configuration missing')
    portal.ensure_md4()
    from ldap3 import NONE, NTLM, SUBTREE, Connection, Server
    conn = Connection(Server(cfg['host'], port=int(cfg.get('port', 389)), get_info=NONE, connect_timeout=5),
                      user=cfg['netbios'] + '\\' + cfg['bind_user'], password=cfg['bind_password'],
                      authentication=NTLM, receive_timeout=15)
    rows = {}
    try:
        if not conn.bind():
            raise SyncError('AD service bind refused')
        for entry in conn.extend.standard.paged_search(
                cfg['base_dn'], '(&(objectCategory=person)(objectClass=user))', search_scope=SUBTREE,
                attributes=['sAMAccountName', 'displayName', 'objectGUID', 'userAccountControl'],
                paged_size=100, generator=True):
            if entry.get('type') != 'searchResEntry':
                continue
            attrs = entry['attributes']
            username = str(scalar(attrs.get('sAMAccountName')) or '')
            if not username:
                raise SyncError('AD account without account name')
            key = username.lower()
            if key in rows:
                raise SyncError('Ambiguous AD account')
            rows[key] = {'username': username, 'name': str(scalar(attrs.get('displayName')) or username),
                         'guid': guid(attrs.get('objectGUID')),
                         'active': not (int(scalar(attrs.get('userAccountControl')) or 0) & 2)}
        if conn.result.get('result') != 0 or not rows:
            raise SyncError('AD snapshot incomplete or empty')
    finally:
        conn.unbind()
    return rows


def read_crm(connection_file, schema):
    from semantic_layer.profiler.connectors import connector_from_file
    if not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_]+', schema):
        raise SyncError('Invalid CRM schema')
    conn = connector_from_file(connection_file)
    conn.query_timeout = 45
    prefix = schema + '.'
    def read(sql):
        columns, rows, truncated = conn.execute(sql, 100000)
        if truncated:
            raise SyncError('CRM snapshot truncated')
        return rows
    teams = read('SELECT CAST(t.TeamId AS nvarchar(40)) AS teamId, t.Name AS name FROM ' + prefix +
                 'TeamBase t JOIN ' + prefix + 'BusinessUnitBase b ON b.BusinessUnitId=t.BusinessUnitId '
                 'WHERE b.IsDisabled=0')
    members = read('SELECT CAST(m.TeamId AS nvarchar(40)) AS teamId, '
                   'CAST(u.SystemUserId AS nvarchar(40)) AS userId, u.DomainName AS domainName, '
                   'CAST(u.ActiveDirectoryGuid AS nvarchar(40)) AS adGuid FROM ' + prefix +
                   'TeamMembership m JOIN ' + prefix + 'SystemUserBase u ON u.SystemUserId=m.SystemUserId '
                   'WHERE u.IsDisabled=0 AND u.AccessMode IN (0,1)')
    if not teams:
        raise SyncError('CRM team snapshot empty')
    return teams, members


class Chat:
    def __init__(self, config):
        self.config = config
        url = urllib.parse.urlparse(config['url'])
        if url.hostname not in ('127.0.0.1', 'localhost', '::1'):
            raise SyncError('Chat API must be local to the portal host')

    def call(self, method, endpoint, body=None, **query):
        url = self.config['url'].rstrip('/') + '/api/v1/' + endpoint
        if query:
            url += '?' + urllib.parse.urlencode(query)
        req = urllib.request.Request(url, method=method,
            data=None if body is None else json.dumps(body).encode(), headers={
                'X-User-Id': self.config['user_id'], 'X-Auth-Token': self.config['token'],
                'Content-Type': 'application/json'})
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                result = json.load(response)
        except urllib.error.HTTPError as exc:
            try:
                error = json.loads(exc.read()).get('errorType', 'request-refused')
            except ValueError:
                error = 'request-refused'
            raise SyncError(f'{endpoint}: HTTP {exc.code} {error}') from None
        if not result.get('success'):
            raise SyncError(f'{endpoint}: {result.get("errorType", "request-refused")}')
        return result

    def pages(self, endpoint, key, **query):
        rows = []
        while True:
            result = self.call('GET', endpoint, offset=len(rows), count=100, **query)
            batch = result[key]
            rows.extend(batch)
            if len(rows) >= result['total']:
                if len(rows) != result['total']:
                    raise SyncError('Chat pagination changed during read')
                return rows
            if not batch:
                raise SyncError('Chat pagination incomplete')


def run(args):
    os.umask(0o077)
    state_path = Path(args.state)
    state_path.parent.mkdir(parents=True, exist_ok=True)
    lock = state_path.with_suffix('.lock').open('a')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    state = json.loads(state_path.read_text()) if state_path.exists() else {'users': {}, 'groups': {}}
    ad = read_ad(args.portal)
    teams, memberships = read_crm(args.crm, args.schema)
    active = {key: value for key, value in ad.items() if value['active']}
    if not active:
        raise SyncError('No active AD accounts; refusing changes')
    by_guid = {u['guid']: key for key, u in active.items() if u['guid']}
    if len(by_guid) != sum(bool(u['guid']) for u in active.values()):
        raise SyncError('Duplicate AD identities')
    desired = {guid(t['teamId']): {'name': t['name'], 'members': set()} for t in teams}
    unmatched = 0
    for row in memberships:
        team_id = guid(row['teamId'])
        if team_id not in desired:
            continue
        ad_guid = guid(row['adGuid'])
        key = by_guid.get(ad_guid) if ad_guid else account(row['domainName'])
        if key not in active:
            unmatched += 1
            continue
        desired[team_id]['members'].add(key)
    config = json.loads(Path(args.chat).read_text())
    chat = Chat(config)
    existing = {u['username'].lower(): u for u in chat.pages('users.list', 'users') if u.get('username')}
    rooms = chat.pages('groups.listAll', 'groups')
    owned_rooms = {}
    for room in rooms:
        if room.get('zekiCrmTeamId'):
            marker = room['zekiCrmTeamId']
            if marker in owned_rooms:
                raise SyncError('Duplicate managed CRM team rooms')
            owned_rooms[marker] = room
    report = {'apply': args.apply, 'activeAD': len(active), 'missingAccounts': sum(k not in existing for k in active),
              'crmTeams': len(desired), 'nonemptyTeams': sum(bool(t['members']) for t in desired.values()),
              'unmatchedCRMMemberships': unmatched, 'createdUsers': 0, 'updatedUsers': 0, 'disabledUsers': 0,
              'createdGroups': 0, 'renamedGroups': 0, 'invitedMembers': 0, 'removedMembers': 0, 'blockedAccounts': 0, 'groups': []}
    def save():
        if args.apply:
            atomic_json(state_path, state)
    for key, person in sorted(active.items()):
        user = existing.get(key)
        tracked = state['users'].get(key)
        if tracked and tracked['guid'] != person['guid']:
            raise SyncError('AD account identity changed; manual review required')
        if not user and args.apply:
            user = chat.call('POST', 'users.create', {
                'username': person['username'], 'name': person['name'],
                'email': f"{person['username']}@{config.get('email_domain', 'timas.local')}",
                'password': secrets.token_urlsafe(48), 'roles': ['user'], 'verified': True,
                'requirePasswordChange': False, 'sendWelcomeEmail': False, 'joinDefaultChannels': True})['user']
            existing[key] = user
            state['users'][key] = {'id': user['_id'], 'guid': person['guid'], 'disabledBySync': False}
            report['createdUsers'] += 1
            save()
        if user and (user.get('type') == 'bot' or user['_id'] == config['user_id']):
            raise SyncError('AD account collides with a protected chat account')
        if user and not user.get('active', True):
            if tracked and tracked.get('disabledBySync') and args.apply:
                chat.call('POST', 'users.setActiveStatus', {'userId': user['_id'], 'activeStatus': True})
                user['active'] = True
                tracked['disabledBySync'] = False
                save()
            else:
                report['blockedAccounts'] += 1
                continue
        if args.apply and user and user.get('name') != person['name']:
            chat.call('POST', 'users.update', {'userId': user['_id'], 'data': {'name': person['name']}})
            report['updatedUsers'] += 1
    # Only accounts created by this synchronizer are disabled; unrelated local accounts are never touched.
    for key, tracked in state['users'].items():
        if key not in active and not tracked.get('disabledBySync') and args.apply:
            user = existing.get(key)
            if not user or user['_id'] != tracked['id'] or user['_id'] == config['user_id']:
                raise SyncError('Managed chat identity changed')
            chat.call('POST', 'users.setActiveStatus', {'userId': tracked['id'], 'activeStatus': False})
            user['active'] = False
            tracked['disabledBySync'] = True
            report['disabledUsers'] += 1
            save()
    for team_id in sorted(set(desired) | set(owned_rooms)):
        team = desired.get(team_id)
        if team is None:
            old_room = owned_rooms[team_id]
            team = {'name': old_room.get('fname') or old_room['name'], 'members': set()}
        room = owned_rooms.get(team_id)
        keys = {k for k in team['members'] if k not in existing or existing[k].get('active', True)}
        if not keys and not room:
            continue
        if args.apply and not room:
            room = chat.call('POST', 'groups.create', {'name': team['name'],
                'members': [active[k]['username'] for k in sorted(keys)],
                'extraData': {'zekiCrmTeamId': team_id, 'description': 'CRM ekip üyeliğine göre eşitlenen şirket içi sohbet.'}})['group']
            owned_rooms[team_id] = room
            state['groups'][team_id] = {'id': room['_id'], 'members': sorted(keys)}
            report['createdGroups'] += 1
            save()
        if room:
            prior = state['groups'].setdefault(team_id, {'id': room['_id'], 'members': []})
            if prior['id'] != room['_id']:
                raise SyncError('Managed room identity changed')
            if args.apply:
                if team_id in desired and (room.get('fname') or room['name']) != team['name']:
                    chat.call('POST', 'groups.rename', {'roomId': room['_id'], 'name': team['name']})
                    report['renamedGroups'] += 1
                current = {u['_id'] for u in chat.pages('groups.members', 'members', roomId=room['_id'])}
                desired_ids = {existing[k]['_id'] for k in keys} | {config['user_id']}
                for uid in sorted(current - desired_ids):
                    chat.call('POST', 'groups.kick', {'roomId': room['_id'], 'userId': uid})
                    report['removedMembers'] += 1
                for uid in sorted(desired_ids - current):
                    chat.call('POST', 'groups.invite', {'roomId': room['_id'], 'userId': uid})
                    report['invitedMembers'] += 1
                prior['members'] = sorted(keys)
                save()
        report['groups'].append({'teamId': team_id, 'name': team['name'], 'members': len(keys),
                                 'roomId': room['_id'] if room else None})
    report['completedAt'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())
    atomic_json(Path(args.report), report)
    print(json.dumps(report, ensure_ascii=False), flush=True)
    return report


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--portal', default='/opt/timas-login/server.py')
    parser.add_argument('--chat', default='/etc/nanobase/zeki-chat.json')
    parser.add_argument('--crm', default='/data/nanobaseai/bi/secrets/crm-mssql-connection.json')
    parser.add_argument('--schema', default='Timas_MSCRM.dbo')
    parser.add_argument('--state', default='/var/lib/zeki-directory-sync/state.json')
    parser.add_argument('--report', default='/var/lib/zeki-directory-sync/last-run.json')
    args = parser.parse_args()
    try:
        run(args)
    except Exception as exc:
        # Never log bind credentials, tokens, driver DSNs or personal directory data on failure.
        print(json.dumps({'success': False, 'errorType': type(exc).__name__,
                          'detail': str(exc) if isinstance(exc, SyncError) else 'Synchronization failed; no source credentials logged'}), flush=True)
        sys.exit(1)
