#!/bin/bash
# Efekt havuzu — OpenGameArt'ta lisans alanı YALNIZ CC0 olan seçilmiş ses paketleri (sayfanın «License(s)» alanı
# 2026-09-27'de tek tek okundu). Toplu tarama/kazıma yok: aşağıdaki liste elle seçilmiş sayfalar ve o sayfadaki resmî
# dosya bağlantısıdır. Lisans: https://creativecommons.org/publicdomain/zero/1.0/
set -u
OUT=${1:-/data/editor/sfx/_indir/opengameart}
mkdir -p "$OUT"
cd "$OUT" || exit 1
while read -r page url; do
  [ -z "$page" ] && continue
  f=$(basename "$url")
  [ -f "$f.ok" ] && continue
  if wget -q -c --timeout=60 --tries=3 -O "$f" "$url"; then
    printf '%s\nhttps://opengameart.org/content/%s\n' "$url" "$page" > "$f.ok"
    echo "$(date +%T) OK $page $f $(stat -c %s "$f")"
  else
    echo "$(date +%T) FAIL $page"
  fi
done <<'LIST'
100-cc0-sfx https://opengameart.org/sites/default/files/100-CC0-SFX_0.zip
100-cc0-sfx-2 https://opengameart.org/sites/default/files/sfx_100_v2.zip
80-cc0-creature-sfx https://opengameart.org/sites/default/files/80-CC0-creature-SFX_0.zip
75-cc0-breaking-falling-hit-sfx https://opengameart.org/sites/default/files/sfx_breaking_and_falling.zip
40-cc0-water-splash-slime-sfx https://opengameart.org/sites/default/files/water-splash-slime-sfx.zip
50-cc0-retro-synth-sfx https://opengameart.org/sites/default/files/50-CC0-retro-synth-SFX.zip
51-ui-sound-effects-buttons-switches-and-clicks https://opengameart.org/sites/default/files/UI_SFX_Set.zip
30-cc0-sfx-loops https://opengameart.org/sites/default/files/sfx_loops.zip
50-cc0-sci-fi-sfx https://opengameart.org/sites/default/files/sci-fi-sfx.zip
forest-ambience https://opengameart.org/sites/default/files/Forest_Ambience.mp3
fire-crackling https://opengameart.org/sites/default/files/fire-1.wav
LIST
echo "$(date +%T) BITTI"
