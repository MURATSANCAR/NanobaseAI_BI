#!/usr/bin/env python3
"""Explicit chat mentions -> existing Zeki engine -> private bot response.

Only the host reads AD. Mongo adapter is read-only; chat writes use the real API.
Queue and deterministic reply IDs survive restarts. No historical message replay.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import re
import select
import sqlite3
import subprocess
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = Path(os.environ.get('ZEKI_MENTION_STATE', '/var/lib/zeki-mention'))
BOT = 'zeki.bot'
MENTION = re.compile(r'(?<![\w@])@zeki\.bot(?![\w.])', re.IGNORECASE)

spec = importlib.util.spec_from_file_location('directory_sync', HERE / 'sync-directory.py')
directory = importlib.util.module_from_spec(spec)
spec.loader.exec_module(directory)


class Mongo:
    def __init__(self):
        self.process = subprocess.Popen(['docker', 'exec', '-i', 'zeki-chat', 'node', '-e',
                                         (HERE / 'mention-mongo.cjs').read_text()],
                                        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True, bufsize=1)

    def call(self, op, **body):
        self.process.stdin.write(json.dumps({'op': op, **body}) + '\n')
        self.process.stdin.flush()
        if not select.select([self.process.stdout], [], [], 30)[0]:
            raise RuntimeError('Mongo adapter timeout')
        line = self.process.stdout.readline()
        if not line:
            raise RuntimeError('Mongo adapter stopped')
        out = json.loads(line)
        if 'error' in out:
            raise RuntimeError('Mongo adapter query failed')
        return out['result']


def valid_context(context):
    message, user = context.get('message'), context.get('user')
    return bool(message and user and context['member'] and user.get('active') is True
                and user.get('type') != 'bot' and user['_id'] != BOT and not message.get('t')
                and not message.get('e2e') and not message.get('encrypted')
                and any(m.get('_id') == BOT for m in message.get('mentions', []))
                and MENTION.search(message.get('msg', '')))


def text_answer(answer):
    # Never expose SQL/internal prompts or invent an answer on engine failure.
    slots = ((answer.get('semantic') or {}).get('query') or {}).get('slots') or []
    if any(s.get('semanticType') == 'METRIC' and
           (s.get('explain') or {}).get('source') == 'count_cue' for s in slots):
        # Generic count inference can select line grain for a document-count question.
        # Do not publish that number as a verified measure; no question/table-specific exceptions.
        return ('Sayım birimini güvenle doğrulayamadığım için bu rakamı paylaşmıyorum. '
                'Bu soru için veri tanımı netleştirilmeli.\n\nSorgu kaydı: ' + str(answer.get('queryId') or '—'))
    text = answer.get('summary') or answer.get('explanation')
    if not isinstance(text, str) or not text.strip():
        return 'Bu soru için yanıt oluşturulamadı. Lütfen sorunuzu yeniden yazın.'
    lines = [text.strip()]
    records = answer.get('records') or []
    columns = answer.get('columns') or []
    names = [c.get('name') if isinstance(c, dict) else str(c) for c in columns]
    if records and names:
        lines.append('\nSonuçlar:')
        for row in records:
            values = [row.get(n) for n in names] if isinstance(row, dict) else row
            lines.append(' • ' + '; '.join(f'{n}: {v}' for n, v in zip(names, values)))
        total = answer.get('totalRows', answer.get('rowCount', len(records)))
        if answer.get('truncated') or total != len(records):
            lines.append(f'Gösterilen: {len(records)} / {total}. Bu liste tam sonuç değildir.')
    if answer.get('queryId'):
        lines.append('\nSorgu kaydı: ' + str(answer['queryId']))
    # Avoid incidental @all/@here/user mentions originating in model or database text.
    return '\n'.join(lines).replace('@', '@\u200b')


def ask(user, question, message_id):
    key = Path('/etc/nanobase/zeki-mention.key').read_text().strip()
    request = urllib.request.Request('http://127.0.0.1:8795/api/v1/chat/mention-answer',
        data=json.dumps({'username': user, 'question': question, 'messageId': message_id}).encode(),
        headers={'Content-Type': 'application/json', 'X-Zeki-Mention-Key': key})
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            answer = json.load(response)
        return text_answer(answer), answer.get('queryId')
    except urllib.error.HTTPError as exc:
        if exc.code == 403:
            return 'Bu soruyu yanıtlama veya ilgili veriye erişme yetkiniz bulunmuyor.', None
        return 'Zeki AI şu anda yanıt oluşturamadı. Lütfen biraz sonra yeniden etiketleyin.', None
    except (OSError, ValueError):
        # An ambiguous engine timeout is not automatically re-executed.
        return 'Soru tamamlanamadı. Lütfen biraz sonra yeniden etiketleyin.', None


def main():
    os.umask(0o077)
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    import fcntl
    lock = (STATE / 'worker.lock').open('w')
    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    db = sqlite3.connect(STATE / 'queue.sqlite')
    db.execute('CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL)')
    db.execute('CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, status TEXT NOT NULL, '
               'reply TEXT, query_id TEXT, user_id TEXT, username TEXT, room_id TEXT, error TEXT)')
    if not db.execute("SELECT 1 FROM meta WHERE key='cursor'").fetchone():
        from datetime import datetime, timezone
        db.execute('INSERT INTO meta VALUES (?,?)', ('cursor', json.dumps({'after': datetime.now(timezone.utc).isoformat(), 'id': ''})))
    # Restart during execution is an uncertain outcome, never silently run the same question twice.
    db.execute("UPDATE jobs SET status='ready', reply=? WHERE status='asking'",
               ('Yanıt hazırlanırken servis yeniden başladı. Lütfen sorunuzu yeniden etiketleyin.',))
    db.commit()
    config = json.loads(Path('/etc/nanobase/zeki-chat.json').read_text())
    admin = directory.Chat(config)
    credentials = STATE / 'bot.json'
    if not credentials.exists():
        user = admin.call('GET', 'users.info', userId=BOT)['user']
        if user.get('type') != 'bot' or user.get('username') != BOT or not user.get('active'):
            raise RuntimeError('Expected active built-in bot missing')
        token = admin.call('POST', 'users.createToken', {'userId': BOT, 'secret': config['sso_secret']})['data']
        directory.atomic_json(credentials, {'url': config['url'], 'user_id': BOT, 'token': token['authToken']})
    bot = directory.Chat(json.loads(credentials.read_text()))
    mongo = Mongo()
    while True:
        cursor = json.loads(db.execute("SELECT value FROM meta WHERE key='cursor'").fetchone()[0])
        messages = mongo.call('poll', **cursor)
        for message in messages:
            db.execute('INSERT OR IGNORE INTO jobs(id,status) VALUES (?,?)', (message['_id'], 'pending'))
            cursor = {'after': message['ts'], 'id': message['_id']}
        if messages:
            db.execute("UPDATE meta SET value=? WHERE key='cursor'", (json.dumps(cursor),))
            db.commit()
        jobs = db.execute("SELECT id,status,reply,user_id,username,room_id FROM jobs WHERE status IN ('pending','ready') ORDER BY rowid LIMIT 10").fetchall()
        for mid, status, reply, uid, username, rid in jobs:
            context = mongo.call('context', id=mid)
            if not valid_context(context):
                db.execute("UPDATE jobs SET status='cancelled' WHERE id=?", (mid,))
                db.commit()
                continue
            # Validate a fresh complete AD snapshot; do not use a disabled/stale directory identity.
            people = directory.read_ad('/opt/timas-login/server.py')
            matched = [p for p in people.values() if p['active'] and
                       p['chatUsername'].lower() == context['user']['username'].lower()]
            if len(matched) != 1:
                db.execute("UPDATE jobs SET status='cancelled',error='AD identity unavailable' WHERE id=?", (mid,))
                db.commit()
                continue
            person = matched[0]
            if status == 'pending':
                uid, username = context['user']['_id'], person['username'].lower()
                question = MENTION.sub('', context['message']['msg']).strip()
                db.execute("UPDATE jobs SET status='asking',user_id=?,username=? WHERE id=?", (uid, username, mid))
                db.commit()
                reply, query = ask(username, question, mid) if question else ('Bana sormak istediğiniz soruyu @zeki.bot etiketinden sonra yazın.', None)
                # Keep the source mention identifiable privately; never copy unrelated room history.
                reply = 'Zeki AI — size özel yanıt\n\n' + reply
                db.execute("UPDATE jobs SET status='ready',reply=?,query_id=? WHERE id=?", (reply, query, mid))
                db.commit()
            elif uid != context['user']['_id'] or username != person['username'].lower():
                db.execute("UPDATE jobs SET status='cancelled',error='Identity changed' WHERE id=?", (mid,))
                db.commit()
                continue
            # A deleted mention, removed member, or disabled account must not receive a late answer.
            if not valid_context(mongo.call('context', id=mid)):
                db.execute("UPDATE jobs SET status='cancelled' WHERE id=?", (mid,))
                db.commit()
                continue
            fresh = directory.read_ad('/opt/timas-login/server.py').get(username)
            if not fresh or not fresh['active'] or fresh['guid'] != person['guid']:
                db.execute("UPDATE jobs SET status='cancelled',error='AD identity changed' WHERE id=?", (mid,))
                db.commit()
                continue
            if not rid:
                rid = bot.call('POST', 'im.create', {'username': context['user']['username']})['room']['_id']
                db.execute('UPDATE jobs SET room_id=? WHERE id=?', (rid, mid))
                db.commit()
            reply_id = 'zekiai' + hashlib.sha256(mid.encode()).hexdigest()[:40]
            existing = mongo.call('message', id=reply_id)
            if existing and (existing['rid'] != rid or existing['u']['_id'] != BOT):
                raise RuntimeError('Reply identity conflict')
            if not existing:
                bot.call('POST', 'chat.sendMessage', {'message': {'_id': reply_id, 'rid': rid, 'msg': reply}})
            db.execute("UPDATE jobs SET status='sent' WHERE id=?", (mid,))
            db.commit()
            print(json.dumps({'event': 'answered', 'messageId': mid}), flush=True)
        time.sleep(3)


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Credentials, message contents and DB connection strings must never reach journald.
        print(json.dumps({'event': 'worker_failed', 'type': type(error).__name__}), flush=True)
        raise SystemExit(1)
