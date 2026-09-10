"""Bounded, private disk snapshots of a single database execution."""
import hashlib
import json
import os
from pathlib import Path
import tempfile


class ResultFiles:
    def __init__(self):
        parent = os.environ.get('SEMANTIC_RESULT_DIR') or None
        if parent:
            Path(parent).mkdir(parents=True, exist_ok=True, mode=0o700)
        self.directory = tempfile.TemporaryDirectory(prefix='semantic-results-', dir=parent)
        self.max_bytes = int(os.environ.get('SEMANTIC_RESULT_MAX_BYTES', str(256 * 1024 * 1024)))
        self.max_rows = int(os.environ.get('SEMANTIC_RESULT_MAX_ROWS', '1000000'))
        self.disk_budget = int(os.environ.get('SEMANTIC_RESULT_DISK_BYTES', str(1024 * 1024 * 1024)))

    def write(self, batches, preview_size=500):
        fd, name = tempfile.mkstemp(dir=self.directory.name, suffix='.jsonl')
        count = size = 0
        preview = []
        digest = hashlib.sha256()
        columns = []
        used = sum(p.stat().st_size for p in Path(self.directory.name).glob('*.jsonl'))
        try:
            with os.fdopen(fd, 'wb') as stream:
                for columns, rows in batches:
                    for row in rows:
                        encoded = (json.dumps(row, ensure_ascii=False, allow_nan=False) + '\n').encode()
                        count += 1
                        size += len(encoded)
                        if count > self.max_rows or size > self.max_bytes or used + size > self.disk_budget:
                            raise ValueError('Rapor saklama sınırını aşıyor; dönemi veya kırılımı daraltın. Kısmi sonuç yayınlanmadı.')
                        stream.write(encoded)
                        digest.update(encoded)
                        if len(preview) < preview_size:
                            preview.append(row)
            return {'columns': columns, 'records': preview, 'totalRows': count,
                    'truncated': False, '_result_file': name, 'resultFingerprint': digest.hexdigest()}
        except BaseException:
            Path(name).unlink(missing_ok=True)
            raise
        finally:
            close = getattr(batches, 'close', None)
            if close:
                close()

    def read(self, name):
        path = Path(name)
        if path.parent != Path(self.directory.name):
            raise ValueError('Invalid result path')
        with path.open() as stream:
            return [json.loads(line) for line in stream]

    def remove(self, name):
        if name and Path(name).parent == Path(self.directory.name):
            Path(name).unlink(missing_ok=True)
