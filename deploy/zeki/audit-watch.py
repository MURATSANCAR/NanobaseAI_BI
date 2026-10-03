#!/usr/bin/env python3
"""Merkezi denetim kaydı — Zeki AI sohbet: veritabanındaki her değişiklik → portal köprüsü (`/api/v1/audit/ingest`).

Sohbetin Mongo'su dışarıya kapalı; `audit-watch.cjs` sohbet konteynerinin içinde değişiklik akışını okur (mention-worker
ile aynı yol). Her olay merkeze satır değişikliği olarak gider: koleksiyon, kayıt kimliği, işlem, önceki/sonraki hâl,
değişen alanlar, kişi (mesajda gönderen/düzenleyen; kişisi belgede yazmayan değişiklikte boş). Sohbetin kendi denetim
olayları (`zeki_server_events`: ayar değişikliği, başarısız giriş…) işlem kaydı olarak gider.

Kaldığı yer (akışın devam jetonu) yalnız merkez yazdığını söyledikten sonra kaydedilir: kopma/yeniden başlatmada olay
kaybolmaz, ikinci kez gelirse merkez kimliğinden tanır ve atlar. Jeton sohbetin işlem günlüğünden düşmüşse (uzun
kesinti) baştan değil «şimdi»den sürer ve bu boşluk merkeze işlem olarak yazılır.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = Path(os.environ.get('ZEKI_AUDIT_STATE', '/var/lib/zeki-audit'))
BRIDGE = os.environ.get('AUDIT_INGEST_URL', 'http://127.0.0.1:8795/api/v1/audit/ingest')
BRIDGE_ENV = os.environ.get('BRIDGE_ENV', '/etc/nanobase/semantic-bridge.env')
CONTAINER = os.environ.get('ZEKI_CONTAINER', 'zeki-chat')
BATCH = 200
FLUSH_SEC = 2.0

#: Kullanıcı kaydında yalnız çevrimiçi durumu/son görülme değişiyorsa kişinin işi değildir.
_PRESENCE = {'status', 'statusConnection', 'statusDefault', '_updatedAt', 'lastLogin', 'statusText'}


def caller_token() -> str:
    try:
        for line in Path(BRIDGE_ENV).read_text().splitlines():
            if line.startswith('SEMANTIC_CALLER_TOKEN='):
                return line.split('=', 1)[1].strip()
    except OSError:
        pass
    return ''


def post(events: list[dict]) -> None:
    req = urllib.request.Request(BRIDGE, data=json.dumps({'source': 'sohbet', 'events': events}, default=str).encode(),
                                 headers={'Content-Type': 'application/json', 'X-Semantic-Caller': caller_token()})
    with urllib.request.urlopen(req, timeout=60) as r:  # noqa: S310 — yerel köprü
        json.loads(r.read() or b'{}')


def _username(doc: dict | None) -> str | None:
    if not isinstance(doc, dict):
        return None
    for path in (('editedBy', 'username'), ('u', 'username'), ('actor', 'username')):
        v = doc
        for p in path:
            v = v.get(p) if isinstance(v, dict) else None
        if v:
            return str(v)
    return None


def _id(ch: dict) -> str:
    return hashlib.sha256(json.dumps(ch.get('token'), sort_keys=True).encode()).hexdigest()[:40]


def event(ch: dict) -> dict | None:
    op = ch.get('op')
    coll = ch.get('coll') or '?'
    before, after = ch.get('before'), ch.get('after')
    if op in ('drop', 'rename', 'dropDatabase', 'invalidate', 'create', 'createIndexes', 'dropIndexes', 'modify'):
        return {'type': 'action', 'id': _id(ch), 'at': ch.get('at'), 'action': 'run', 'kind': 'sohbet',
                'title': f'Sohbet veritabanı: {op} {coll}'}
    changed = ch.get('changed')
    if coll == 'users' and op == 'update' and changed and {c.split('.')[0] for c in changed} <= _PRESENCE:
        return None
    if coll == 'zeki_server_events' and op == 'insert' and isinstance(after, dict):
        actor = (after.get('actor') or {}).get('username') or (after.get('actor') or {}).get('ip')
        return {'type': 'action', 'id': _id(ch), 'at': after.get('ts') or ch.get('at'), 'actor': actor,
                'action': str(after.get('t') or 'run').split('.')[-1][:16], 'kind': 'sohbet',
                'title': f"Sohbet: {after.get('t')}", 'ip': (after.get('actor') or {}).get('ip'),
                'detail': {k: v for k, v in after.items() if k not in ('_id',)}}
    mop = {'insert': 'INSERT', 'update': 'UPDATE', 'replace': 'UPDATE', 'delete': 'DELETE'}.get(op)
    if not mop:
        return None
    if mop == 'UPDATE' and isinstance(before, dict) and isinstance(after, dict):
        keys = sorted({c.split('.')[0] for c in (changed or [])} or {k for k in set(before) | set(after) if before.get(k) != after.get(k)})
        old = {k: before.get(k) for k in keys}
        new = {k: after.get(k) for k in keys}
    else:
        keys, old, new = changed, before if mop != 'INSERT' else None, after if mop != 'DELETE' else None
    return {'type': 'row', 'id': _id(ch), 'at': ch.get('at'), 'actor': _username(after) or _username(before),
            'table': coll, 'op': mop, 'pk': ch.get('key'), 'changed': keys, 'old': old, 'new': new}


def load_resume():
    p = STATE / 'resume.json'
    return json.loads(p.read_text()).get('resume') if p.exists() else None


def save_resume(token) -> None:
    p = STATE / 'resume.json'
    tmp = p.with_suffix('.tmp')
    tmp.write_text(json.dumps({'resume': token, 'at': time.time()}))
    tmp.replace(p)


def run_once() -> None:
    import queue
    import threading

    resume = load_resume()
    proc = subprocess.Popen(['docker', 'exec', '-i', CONTAINER, 'node', '-e', (HERE / 'audit-watch.cjs').read_text()],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1)
    proc.stdin.write(json.dumps({'resume': resume}) + '\n')
    proc.stdin.flush()
    q: queue.Queue = queue.Queue()

    def pump(stream, kind):
        for line in stream:
            q.put((kind, line))
        q.put((kind, None))

    threading.Thread(target=pump, args=(proc.stdout, 'out'), daemon=True).start()
    threading.Thread(target=pump, args=(proc.stderr, 'err'), daemon=True).start()
    pending: list[dict] = []
    last_token = None
    saved_token = resume
    last_flush = time.monotonic()
    done = 0

    def flush():
        nonlocal pending, saved_token, last_flush
        if pending:
            post(pending)
        if last_token is not None and last_token != saved_token:
            save_resume(last_token)
            saved_token = last_token
        pending, last_flush = [], time.monotonic()

    while done < 2:
        try:
            kind, line = q.get(timeout=FLUSH_SEC)
        except queue.Empty:
            flush()
            continue
        if line is None:
            done += 1
            continue
        if kind == 'err':
            print('izleyici:', line.rstrip(), file=sys.stderr, flush=True)
            if 'ChangeStreamHistoryLost' in line or 'no longer be in the oplog' in line:
                # Jeton günlükten düşmüş: boşluk merkeze yazılır, akış «şimdi»den sürer.
                flush()
                post([{'type': 'action', 'id': f'bosluk:{time.time()}', 'action': 'run', 'kind': 'sohbet',
                       'title': 'Sohbet denetim akışında kesinti: bu aralıktaki değişiklikler alınamadı',
                       'detail': {'resume': resume}}])
                save_resume(None)
            continue
        ch = json.loads(line)
        if ch.get('ready'):
            continue
        last_token = ch.get('token')
        ev = event(ch)
        if ev:
            pending.append(ev)
        if len(pending) >= BATCH or time.monotonic() - last_flush >= FLUSH_SEC:
            flush()
    flush()
    raise RuntimeError(f'izleyici süreci çıktı: {proc.wait()}')


def main() -> None:
    os.umask(0o077)
    STATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    while True:
        try:
            run_once()
        except Exception as e:  # noqa: BLE001 — sohbet/köprü yeniden başlarken: bekle, kaldığı yerden sür
            print('denetim izleyicisi:', e, file=sys.stderr, flush=True)
            time.sleep(15)


if __name__ == '__main__':
    main()
