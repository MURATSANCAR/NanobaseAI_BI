"""Sorgu bilgisi yardımcısı: ayardan gelen rakamlar (eşik günü, pencere, baskı süresi…) ve yardımcı kayıt kalıpları.

Ayarın geçerli değeri «Yönetim ekranında kaydedilen > ortam değişkeni > varsayılan» sırasıyla okunur (`admin.conf`).
Ekrandaki «i» bu rakamlarda ayar kaydının okumasını (`admin.settings_stmt`, çalışan ifadenin kendisi) ve hangi anahtarın
kullanıldığını gösterir. Lojistik ve İK modüllerinin `*_kaynak.py` dosyaları ortak kullanır.
"""
from __future__ import annotations

from typing import Any, Iterable, Optional

from semantic_bridge import admin as A
from semantic_bridge import provenance as P


def ayar(k: P.Kaynaklar, engine: Any, sid: str, keys: Iterable[str], what: str = "") -> str:
    """Ayar kaydı okuması; `keys` bu rakamda kullanılan ayar anahtarları."""
    names = ", ".join(keys)
    return k.portal(sid, "Ayar kaydı" + (f" · {what}" if what else ""), A.settings_stmt(), engine,
                    description=f"Yönetim ekranında kaydedilen ayarlar. Bu rakamda kullanılan anahtar: {names}. Kayıt "
                                "yoksa sunucu ortam değeri, o da yoksa varsayılan geçerlidir.")


def h(k: P.Kaynaklar, name: str, text: str, inputs: Iterable[Optional[str]]) -> Optional[str]:
    """Girdisi olan hesap; hiçbir girdisi okunmamışsa (kaynak o okumada düştüyse) None — alan bağlanmaz, «i» çıkmaz,
    olmayan bir sorgu gösterilmez."""
    ins = [i for i in inputs if i]
    if not ins:
        return None
    return k.hesap(name, text, ins)


def bind(k: P.Kaynaklar, mapping: dict[str, Optional[str]]) -> None:
    """Kaynağı olan alanları bağlar (None olanlar atlanır)."""
    k.alanlar({path: ref for path, ref in mapping.items() if ref})
