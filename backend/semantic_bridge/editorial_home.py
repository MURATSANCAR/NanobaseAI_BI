"""Durable, prewarmed editorial summaries. User-specific desk data stays outside this cache.

Liste ekranlarının açılış görünümleri (arama metni yok, ilk sayfa) de aynı turda yeniden okunur:
ekran bir görünümü istediğinde `remember` onu kaydeder, tur `warmers` üzerinden sorgusunu çalıştırır
ve sonuç köprünün SQL önbelleğine düşer. Kişi ekranı açtığında CRM'i beklemez. Bir gün istenmeyen
görünüm turdan çıkar; kayıt diskte durur, yeniden başlatmada kaybolmaz.
"""
from __future__ import annotations
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import threading
import time
import uuid

log = logging.getLogger(__name__)
INTERVAL = 300
VIEW_IDLE = 24 * 3600


class EditorialHomeSnapshots:
    def __init__(self, scope, builders, warmers=None):
        self.scope = scope
        self.builders = builders
        self.warmers = warmers or (lambda: {})
        self.views_lock = threading.Lock()
        self.stopping = threading.Event()
        self.thread = None
        self.revision = hashlib.sha256(Path(__file__).read_bytes() + Path(__file__).with_name('editorial.py').read_bytes()).hexdigest()

    def directory(self):
        key = hashlib.sha256(json.dumps([self.revision, self.scope()], sort_keys=True).encode()).hexdigest()
        root = Path(os.environ.get('EDITORIAL_HOME_CACHE_DIR', '/data/nanobaseai/bi/var/editorial-home')) / key
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        return root

    @staticmethod
    def load(path):
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError):
            return {}

    @staticmethod
    def save(path, value):
        temp = path.with_name('.' + uuid.uuid4().hex + '.tmp')
        try:
            with temp.open('x') as stream:
                os.chmod(temp, 0o600)
                json.dump(value, stream, ensure_ascii=False, default=str)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp, path)
        finally:
            temp.unlink(missing_ok=True)

    def read(self):
        root = self.directory()
        parts = {name: self.load(root / (name + '.json')) for name in self.builders()}
        return {'parts': parts, 'refreshIntervalSeconds': INTERVAL, 'revision': self.revision,
                'loading': any('data' not in part for part in parts.values()),
                'stale': any(time.time() - part.get('updatedAt', 0) > INTERVAL * 2 for part in parts.values())}

    def remember(self, name, params):
        """Bir liste ekranının açılış görünümü istendi: sonraki turlarda önceden okunur."""
        key = json.dumps([name, params], sort_keys=True, ensure_ascii=False)
        path = self.directory() / 'views.json'
        with self.views_lock:
            views = self.load(path)
            known = key in views
            # Aynı görünüm için diske her istekte yazılmaz; saat bir saatte bir tazelenir.
            if known and time.time() - views[key].get('askedAt', 0) < 3600:
                return
            views[key] = {'name': name, 'params': params, 'askedAt': time.time()}
            self.save(path, views)

    def warm(self, root):
        warmers = self.warmers()
        with self.views_lock:
            views = self.load(root / 'views.json')
            live = {k: v for k, v in views.items() if time.time() - v.get('askedAt', 0) < VIEW_IDLE}
            if len(live) != len(views):
                self.save(root / 'views.json', live)
        for view in live.values():
            if self.stopping.is_set():
                return
            fn = warmers.get(view.get('name'))
            if fn is None:
                continue
            try:
                fn(**view.get('params', {}))
            except Exception:
                log.exception('Editorial view warm-up failed: %s', view.get('name'))

    def refresh(self, force=False):
        root = self.directory()
        with (root / 'refresh.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return  # tur zaten sürüyor; düğmeyle gelen istek de onun sonucunu okur
            previous_attempt = self.load(root / 'attempt.json')
            last = previous_attempt.get('at', 0)
            # A shutdown/crash before completion must not postpone recovery by five minutes.
            if not force and previous_attempt.get('finishedAt') and time.time() - last < INTERVAL:
                return
            started = time.time()
            self.save(root / 'attempt.json', {'at': started})
            for name, build in self.builders().items():
                if self.stopping.is_set():
                    return
                path = root / (name + '.json')
                previous = self.load(path)
                try:
                    data = build()
                    if isinstance(data, dict) and data.get('truncated'):
                        raise ValueError('Incomplete editorial summary')
                    self.save(path, {'data': data, 'updatedAt': time.time(), 'error': None})
                except Exception:
                    log.exception('Editorial home refresh failed: %s; preserving last success', name)
                    self.save(path, dict(previous, error='Yeni veriler alınamadı; son başarılı kayıt korunuyor.', failedAt=time.time()))
            if not force:
                # Düğmeyle istenen yenileme yalnız özetleri bekletir; liste görünümleri kendi isteğinde tazelenir.
                self.warm(root)
            self.save(root / 'attempt.json', {'at': started, 'finishedAt': time.time()})

    def start(self):
        def schedule():
            while not self.stopping.is_set():
                try:
                    self.refresh()
                except Exception:
                    log.exception('Editorial home refresh unavailable')
                self.stopping.wait(5)
        self.thread = threading.Thread(target=schedule, daemon=True, name='editorial-home-refresh')
        self.thread.start()

    def stop(self):
        self.stopping.set()
