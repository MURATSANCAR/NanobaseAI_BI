"""Durable last-completed audit; readers never wait for Logo recalculation."""
import fcntl
import hashlib
import json
import logging
import os
from pathlib import Path
import re
import threading
from datetime import datetime, timezone
import uuid

log = logging.getLogger(__name__)


def now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temp = path.with_name('.' + path.name + '.' + uuid.uuid4().hex + '.tmp')
    try:
        with temp.open('x') as stream:
            os.chmod(temp, 0o600)
            json.dump(value, stream, ensure_ascii=False, default=str)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        temp.unlink(missing_ok=True)


class AuditSnapshots:
    def __init__(self, root, build):
        self.root = root
        self.build = build
        self.year = 2026  # The only reconciled source backup; never merge backup identities.
        self.interval = max(300, int(os.getenv('FINANCIAL_AUDIT_REFRESH_SECONDS', '3600')))
        self.stopping = threading.Event()
        self.scheduler = None
        files = [Path(__file__).with_name(name) for name in (
            'financial_audit.py', 'financial_audit_rules.py', 'financial_audit_evidence.py',
            'financial_audit_deep.py', 'financial_audit_snapshot.py')]
        files.append(Path(__file__).resolve().parents[2] / 'configs/financial-audit/source.json')
        self.revision = hashlib.sha256(b''.join(p.read_bytes() for p in files)).hexdigest()

    def path(self, name):
        root = self.root() / 'snapshots'
        root.mkdir(parents=True, exist_ok=True, mode=0o700)
        return root / name

    def read_json(self, path):
        try:
            return json.loads(path.read_text())
        except (FileNotFoundError, ValueError):
            return None

    def load(self):
        pointer = self.read_json(self.path('latest.json'))
        if not pointer or not re.fullmatch('[0-9a-f]{32}', pointer.get('runId', '')):
            return None
        report = self.read_json(self.root() / (pointer['runId'] + '.json'))
        if report and report.get('year') == self.year and report.get('truncated') is False:
            return report
        return None

    def status(self):
        state = self.read_json(self.path('refresh.json')) or {'state': 'idle'}
        # A killed worker cannot leave the UI saying "refreshing" forever.
        if state.get('state') == 'refreshing':
            with self.path('refresh.lock').open('a') as lock:
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError:
                    pass
                else:
                    state = dict(state, state='error', message='Yenileme yarıda kaldı. Son tamamlanan rapor korunuyor; yeniden deneyebilirsiniz.')
        pointer = self.read_json(self.path('latest.json')) or {}
        return dict(state, runId=pointer.get('runId'), computedAt=pointer.get('computedAt'),
                    refreshIntervalSeconds=self.interval,
                    calculationUpdated=pointer.get('snapshotRevision') == self.revision)

    def refresh(self, *, only_if_due=False):
        lock = self.path('refresh.lock').open('a')
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lock.close()
            return dict(self.status(), accepted=False)
        # Both the decision and the job start are protected across workers.
        previous = self.read_json(self.path('refresh.json')) or {}
        if only_if_due:
            last = previous.get('finishedAt') or previous.get('startedAt')
            age = (datetime.now(timezone.utc) - datetime.fromisoformat(last)).total_seconds() if last else self.interval
            if age < self.interval and previous.get('state') != 'refreshing' and self.load() and previous.get('snapshotRevision') == self.revision:
                lock.close()
                return dict(self.status(), accepted=False)
        job = dict(state='refreshing', jobId=uuid.uuid4().hex, startedAt=now(),
                   snapshotRevision=self.revision, message='Veriler yenileniyor. Son tamamlanan rapor gösteriliyor.')
        try:
            atomic_json(self.path('refresh.json'), job)
            threading.Thread(target=self._run, args=(lock, job), daemon=True, name='financial-audit-refresh').start()
        except Exception:
            lock.close()
            raise
        return dict(self.status(), accepted=True)

    def _run(self, lock, job):
        try:
            report = self.build(self.year)
            if report.get('truncated') is not False or report.get('year') != self.year:
                raise ValueError('Incomplete or wrong-period audit cannot replace the current report')
            # Archive is already durable. This is the single publication point.
            atomic_json(self.path('latest.json'), {**{k:report[k] for k in ('runId', 'computedAt', 'year')},
                                                  'snapshotRevision':self.revision})
            atomic_json(self.path('refresh.json'), dict(job, state='ready', finishedAt=now(), message='Veriler güncellendi.'))
        except Exception:
            log.exception('Audit refresh failed; retaining the last completed report')
            atomic_json(self.path('refresh.json'), dict(job, state='error', finishedAt=now(),
                message='Yeni veriler alınamadı. Son tamamlanan rapor korunuyor; verileri yeniden yenileyebilirsiniz.'))
        finally:
            lock.close()

    def bootstrap(self):
        # Adopt an existing complete workpaper before startup refresh. No DB read.
        with self.path('refresh.lock').open('a') as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError:
                return
            if self.load():
                return
            for meta_path in sorted(self.root().glob('*.meta.json'), key=lambda p:p.stat().st_mtime, reverse=True):
                meta = self.read_json(meta_path) or {}
                run_id = meta.get('runId', '')
                if meta.get('year') != self.year or not re.fullmatch('[0-9a-f]{32}', run_id):
                    continue
                report = self.read_json(self.root() / (run_id + '.json'))
                if report and report.get('truncated') is False and all(k in report for k in ('accounts','coverage','deepAudit','computedAt')):
                    atomic_json(self.path('latest.json'), {k:report[k] for k in ('runId','computedAt','year')})
                    return

    def start(self):
        self.bootstrap()
        def schedule():
            while not self.stopping.is_set():
                try:
                    self.refresh(only_if_due=True)
                except Exception:
                    log.exception('Audit scheduler could not start a refresh')
                self.stopping.wait(60)
        self.scheduler = threading.Thread(target=schedule, daemon=True, name='financial-audit-scheduler')
        self.scheduler.start()

    def stop(self):
        self.stopping.set()
        if self.scheduler:
            self.scheduler.join(timeout=2)
