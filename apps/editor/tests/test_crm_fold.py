"""CRM bağlayıcısının başlık katlaması: dosya adından gelen başlık CRM adıyla eşleşmeli. Çalıştır:

    python3 apps/editor/tests/test_crm_fold.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "connectors"))

import crm_covers as C  # noqa: E402


def test_file_name_titles_fold_like_crm_titles():
    assert C.fold("Dilek Agaci.indd") == C.fold("Dilek Ağacı")
    assert C.fold("babamsultanabdulhamid-arsiv.pdf") == "babamsultanabdulhamid arsiv"
    assert C.fold("anne-terligi") == C.fold("Anne Terliği")
    assert C.fold("Kitap.Adı Devam") == "kitap adi devam"          # başlık içindeki nokta uzantı değil


if __name__ == "__main__":
    test_file_name_titles_fold_like_crm_titles()
    print("ok test_file_name_titles_fold_like_crm_titles")
