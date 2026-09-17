"""Explicit single-clip pilot; source text is never rewritten."""
import argparse
import hashlib
import json
import time
from importlib.metadata import version
from pathlib import Path

import torch
import soundfile as sf
from chatterbox.mtl_tts import ChatterboxMultilingualTTS
from huggingface_hub import snapshot_download


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--text', type=Path, required=True)
    p.add_argument('--reference', type=Path, required=True)
    p.add_argument('--output', type=Path, required=True)
    p.add_argument('--language', default='tr')
    p.add_argument('--threads', type=int, default=8)
    p.add_argument('--model-revision', default='5bb1f6ee58e50c3b8d408bc82a6d3740c2db6e18')
    args = p.parse_args()
    if args.output.exists():
        raise SystemExit('Output exists; choose a new generation path')
    text = args.text.read_text()
    if not text.strip():
        raise SystemExit('Empty source text')
    torch.set_num_threads(args.threads)
    torch.manual_seed(42)
    started = time.monotonic()
    checkpoint = snapshot_download('ResembleAI/chatterbox', revision=args.model_revision,
        allow_patterns=['ve.pt', 't3_mtl23ls_v2.safetensors', 's3gen.pt',
                        'grapheme_mtl_merged_expanded_v1.json', 'conds.pt', 'Cangjie5_TC.json'])
    model = ChatterboxMultilingualTTS.from_local(checkpoint, device='cpu')
    wav = model.generate(text, language_id=args.language,
                         audio_prompt_path=str(args.reference),
                         exaggeration=0.4, cfg_weight=0.5)
    samples = wav.squeeze(0).cpu().numpy()
    args.output.parent.mkdir(parents=True, exist_ok=True)
    sf.write(args.output, samples, model.sr)
    report = {'text_sha256': hashlib.sha256(args.text.read_bytes()).hexdigest(),
              'reference_sha256': hashlib.sha256(args.reference.read_bytes()).hexdigest(),
              'output_sha256': hashlib.sha256(args.output.read_bytes()).hexdigest(),
              'sample_rate': model.sr, 'duration_seconds': len(samples) / model.sr,
              'elapsed_seconds': time.monotonic() - started, 'device': 'cpu',
              'language': args.language, 'seed': 42, 'chatterbox_version': version('chatterbox-tts'),
              'model_revision': args.model_revision,
              'listening_accepted': False, 'production_accepted': False}
    args.output.with_suffix('.json').write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
