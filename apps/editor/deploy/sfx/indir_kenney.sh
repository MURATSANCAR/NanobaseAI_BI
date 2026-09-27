#!/bin/bash
# Efekt havuzu — Kenney ses paketleri (https://kenney.nl/assets/category:Audio), lisans Creative Commons CC0
# (her paket sayfasında «License: Creative Commons CC0»; https://creativecommons.org/publicdomain/zero/1.0/).
# Bağlantılar paket sayfalarındaki resmî «Download» düğmesinin adresi (2026-09-27'de okundu). Konuşma paketleri
# (voiceover-pack, voiceover-pack-fighter: İngilizce seslendirme) efekt olmadığı için alınmaz.
set -u
OUT=${1:-/data/editor/sfx/_indir/kenney}
mkdir -p "$OUT"
cd "$OUT" || exit 1
while read -r pack url; do
  [ -z "$pack" ] && continue
  [ -f "$pack.zip.ok" ] && continue
  if wget -q -c --timeout=60 --tries=3 -O "$pack.zip" "$url"; then
    printf '%s\nhttps://kenney.nl/assets/%s\n' "$url" "$pack" > "$pack.zip.ok"
    echo "$(date +%T) OK $pack $(stat -c %s "$pack.zip")"
  else
    echo "$(date +%T) FAIL $pack"
  fi
done <<'LIST'
casino-audio https://kenney.nl/media/pages/assets/casino-audio/2472606a04-1721639069/kenney_casino-audio.zip
digital-audio https://kenney.nl/media/pages/assets/digital-audio/216eac4753-1677590265/kenney_digital-audio.zip
impact-sounds https://kenney.nl/media/pages/assets/impact-sounds/87b4ddecda-1677589768/kenney_impact-sounds.zip
interface-sounds https://kenney.nl/media/pages/assets/interface-sounds/fa43c1dd4d-1677589452/kenney_interface-sounds.zip
music-jingles https://kenney.nl/media/pages/assets/music-jingles/f37e530b9e-1677590399/kenney_music-jingles.zip
rpg-audio https://kenney.nl/media/pages/assets/rpg-audio/8e99002d76-1677590336/kenney_rpg-audio.zip
sci-fi-sounds https://kenney.nl/media/pages/assets/sci-fi-sounds/6b296f9ecf-1677589334/kenney_sci-fi-sounds.zip
ui-audio https://kenney.nl/media/pages/assets/ui-audio/490d233f68-1677590494/kenney_ui-audio.zip
LIST
echo "$(date +%T) BITTI"
