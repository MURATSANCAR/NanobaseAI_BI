"""Uç içi kısa bellek (`hizli_bellek`): taze → hemen, bayat → hemen + arkada, yok → beklenir, tek uçuş, düşürme."""
from __future__ import annotations

import threading
import time

from semantic_bridge import hizli_bellek as HB


def _bekle(sart, sure=2.0):
    son = time.time() + sure
    while time.time() < son:
        if sart():
            return True
        time.sleep(0.01)
    return False


def test_taze_bayat_ve_zorla():
    b = HB.Bellek("test-taze", taze=0.2, bayat=10)
    n = {"x": 0}

    def hesap():
        n["x"] += 1
        return {"n": n["x"]}

    assert b.al("a", hesap) == {"n": 1}
    assert b.al("a", hesap) == {"n": 1} and n["x"] == 1          # taze
    time.sleep(0.25)
    assert b.al("a", hesap) == {"n": 1}                          # bayat: eski değer hemen
    assert _bekle(lambda: n["x"] == 2)                           # arkada yenilendi
    assert _bekle(lambda: b.al("a", hesap) == {"n": 2})
    assert b.al("a", hesap, zorla=True) == {"n": 3}


def test_kopya_ust_anahtar_degismez():
    b = HB.Bellek("test-kopya", taze=60)
    d = b.al("k", lambda: {"a": 1})
    d["kaynaklar"] = "x"
    assert "kaynaklar" not in b.al("k", lambda: {"a": 2})


def test_tek_ucus():
    b = HB.Bellek("test-tek", taze=60)
    n = {"x": 0}
    kapı = threading.Event()

    def hesap():
        n["x"] += 1
        kapı.wait(1)
        return n["x"]

    out: list = []
    th = [threading.Thread(target=lambda: out.append(b.al("k", hesap))) for _ in range(5)]
    for t in th:
        t.start()
    time.sleep(0.1)
    kapı.set()
    for t in th:
        t.join()
    assert n["x"] == 1 and out == [1] * 5


def test_arka_hata_eskiyi_korur_ve_dusur():
    b = HB.Bellek("test-hata", taze=0.05, bayat=60)
    assert b.al("k", lambda: 1) == 1
    time.sleep(0.06)

    def bozuk():
        raise RuntimeError("kaynak yok")

    assert b.al("k", bozuk) == 1
    assert _bekle(lambda: b.sayac["hata"] == 1)
    assert b.al("k", lambda: 2) in (1, 2)
    assert b.dusur(lambda a: a == "k") == 1
    assert b.yas("k") is None
    assert b.al("k", lambda: 3) == 3
