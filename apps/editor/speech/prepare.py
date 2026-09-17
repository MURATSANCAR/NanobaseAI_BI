"""Acquire immutable source audio; never train or synthesize implicitly."""
import argparse
import hashlib
import json
from pathlib import Path
import urllib.request

import pyarrow.parquet as pq
from mutagen import File


def digest(path):
    result = hashlib.sha256()
    with path.open('rb') as stream:
        while block := stream.read(1024 * 1024):
            result.update(block)
    return result.hexdigest()


def fetch(url):
    with urllib.request.urlopen(url, timeout=120) as response:
        return response.read()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', type=Path, default=Path(__file__).with_name('source.json'))
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--max-shards', type=int, help='Acquire a bounded pilot subset')
    args = parser.parse_args()
    if args.max_shards is not None and args.max_shards < 1:
        parser.error('--max-shards must be positive')
    config = json.loads(args.config.read_text())
    root = args.output / config['revision']
    root.mkdir(parents=True, exist_ok=True)
    base = 'https://huggingface.co/datasets/' + config['dataset']
    tree = json.loads(fetch('https://huggingface.co/api/datasets/' + config['dataset']
                            + '/tree/' + config['revision'] + '/data'))
    (root / 'source-tree.json').write_text(json.dumps(tree, indent=2))
    (root / 'README.source.md').write_bytes(fetch(base + '/raw/' + config['revision'] + '/README.md'))
    counts = {}
    seconds = 0.0
    files = []
    manifest = root / 'clips.jsonl.partial'
    with manifest.open('w') as out:
        for item in tree:
            if not item['path'].endswith('.parquet'):
                continue
            if args.max_shards is not None and len(files) >= args.max_shards:
                break
            name = Path(item['path']).name
            target = root / name
            expected = item['lfs']['oid']
            if not target.exists() or digest(target) != expected:
                partial = target.with_suffix('.partial')
                print('Downloading', name, flush=True)
                with urllib.request.urlopen(base + '/resolve/' + config['revision'] + '/' + item['path'], timeout=120) as response, partial.open('wb') as dest:
                    while block := response.read(1024 * 1024):
                        dest.write(block)
                if partial.stat().st_size != item['size'] or digest(partial) != expected:
                    raise RuntimeError('Source integrity mismatch: ' + name)
                partial.replace(target)
            files.append({'path': name, 'sha256': expected, 'bytes': target.stat().st_size})
            split = name.split('-')[0]
            folder = root / 'audio' / split
            folder.mkdir(parents=True, exist_ok=True)
            counts.setdefault(split, 0)
            for batch in pq.ParquetFile(target).iter_batches(batch_size=128):
                for row in batch.to_pylist():
                    index = counts[split]
                    payload = row['audio']['bytes']
                    extension = '.ogg' if payload.startswith(b'OggS') else '.flac' if payload.startswith(b'fLaC') else '.wav' if payload.startswith(b'RIFF') else '.mp3'
                    audio = folder / f'{index:06d}{extension}'
                    sha = hashlib.sha256(payload).hexdigest()
                    if audio.exists():
                        if digest(audio) != sha:
                            raise RuntimeError('Existing clip differs: ' + str(audio))
                    else:
                        audio.write_bytes(payload)
                    info = File(audio).info
                    seconds += info.length
                    record = {'split': split, 'row_index': index, 'audio': str(audio.relative_to(root)),
                              'sha256': sha, 'source_parquet': name, 'source_audio_path': row['audio']['path'],
                              'transcription': row[config.get('text_column', 'transcription')], 'duration_seconds': info.length,
                              'sample_rate': getattr(info, 'sample_rate', None), 'channels': info.channels,
                              'speaker_id': row.get('speaker'), 'voice_approved': False}
                    out.write(json.dumps(record, ensure_ascii=False) + '\n')
                    counts[split] += 1
            print('Extracted', name, counts, flush=True)
    if args.max_shards is None and counts != config['expected_rows']:
        raise RuntimeError('Unexpected row counts: ' + str(counts))
    manifest.replace(root / 'clips.jsonl')
    report = {**config, 'counts': counts, 'duration_hours': seconds / 3600,
              'files': files, 'manifest_sha256': digest(root / 'clips.jsonl'),
              'status': 'SOURCE_ACQUIRED' if counts == config['expected_rows'] else 'SUBSET_ACQUIRED',
              'synthesis_validated': False}
    (root / 'acquisition.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2), flush=True)


if __name__ == '__main__':
    main()
