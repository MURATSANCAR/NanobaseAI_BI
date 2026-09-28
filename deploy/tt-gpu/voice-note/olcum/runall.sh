#!/usr/bin/env bash
# Tam ölçüm: indirme bitince sırayla dört model, GPU 0, tek süreç. Çıktı /data/voice-olcum-claude/out.
W=/data/voice-olcum-claude
while docker ps --format '{{.Names}}' | grep -q '^voice-olcum-indir$'; do sleep 20; done
run() {
  docker run --rm --name voice-olcum-olc --gpus "device=0" -v $W:/w "${@:3}" --entrypoint python3 editor-voice:4 /w/olc.py "/w/models/$1" "$2" 2>&1 \
    | grep -v -E "max_new_tokens|logits processor|Loading weights|Warn" >> $W/out/log.txt
}
run openai__whisper-large-v3-turbo turbo
run openai__whisper-large-v3 large-v3
run turkmedstt__whisper-large-v3-turkish-general tr-general
run Qwen__Qwen3-ASR-1.7B-hf qwen3-asr-1.7b
echo "HEPSI BITTI" >> $W/out/log.txt
