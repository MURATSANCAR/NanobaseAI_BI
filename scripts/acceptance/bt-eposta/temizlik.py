#!/usr/bin/env python3
"""Bilgi İşlem e-postaları kabulünün temizliği.

`kabul.py` veritabanına yazmaz; köprünün açılış kaydı (`semantic_itops_state.bridge_boots`) uygulamanın kendi
kaydıdır, test verisi değildir ve silinmez. Bu betik yalnız kabulün yerel çıktılarını (JSON, `--html-dir` kopyaları)
siler; `--gonder` ile gerçekten gönderilen e-postalar alıcının kutusundadır, geri alınamaz.

    python3 scripts/acceptance/bt-eposta/temizlik.py /tmp/claude-<oturum>/bt-eposta.json /tmp/claude-<oturum>/bt-eposta
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path


def main(paths: list[str]) -> int:
    for p in map(Path, paths):
        if not str(p).startswith(("/tmp/", "/private/tmp/")):
            print(f"atlandı (yalnız /tmp altı silinir): {p}")
            continue
        if p.is_dir():
            shutil.rmtree(p)
            print(f"silindi: {p}/")
        elif p.exists():
            p.unlink()
            print(f"silindi: {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
