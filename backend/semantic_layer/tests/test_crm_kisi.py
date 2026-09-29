"""Saklanmış kişi → CRM kullanıcısı eşlemesi (hız 2. tur, 2026-09-29).

Sözleşme: eşleme kuralı eski = yeni. Eski yol `editorial_assign.crm_me` — kişi başına `me_sql` (CRM'de
`LOWER(DomainName) LIKE …`) + Python seçimi. Yeni yol `crm_kisi`: bütün kullanıcılar tek sorguda (`all_users_sql`),
kişi bellekten. Aşağıdaki sahte SQL Server `me_sql`'in ÜRETTİĞİ metni ayrıştırıp LIKE'ı SQL Server kurallarıyla
değerlendirir (`%`, `[x]` kaçışı, `''`, eşlenen ifadenin sonundaki boşluk sayılmaz, `LOWER` harmanlamaya göre — Türkçe
harmanlamada `I` → `ı`); yeni yol aynı sahte sunucunun `LOWER` çıktısını alır. Rastgele (sabit tohumlu) ve elle seçilmiş
zor satırlarla her hesap adı için iki yol birebir karşılaştırılır. Veriler yapaydır; gerçek CRM'de kabul:
`scripts/acceptance/hiz2-ilk-acilis/kisi_esleme.py`.
"""
from __future__ import annotations

import random
import re
import threading
import uuid
from typing import Any, Optional

import pytest
import sqlalchemy as sa

from semantic_bridge import crm_kisi as K
from semantic_bridge import editorial_assign as M2
from semantic_bridge import sorgu_izi as IZ
from semantic_layer.store.catalog_store import open_store

SCHEMA = "Timas_MSCRM.dbo"
T = "t1"


# ------------------------------------------------------------------ sahte SQL Server


def sql_lower(v: Optional[str], turkish: bool) -> Optional[str]:
    if v is None:
        return None
    if turkish:   # Turkish_CI_AS: I → ı, İ → i
        v = v.replace("I", "ı").replace("İ", "i")
    return v.lower()


def like(value: Optional[str], pattern: str) -> bool:
    """SQL Server LIKE (ESCAPE yok): % _ [x]; eşlenen ifadenin sonundaki boşluklar sayılmaz. İki taraf zaten LOWER."""
    if value is None:
        return False
    rx, i = "", 0
    while i < len(pattern):
        ch = pattern[i]
        if ch == "%":
            rx += ".*"
        elif ch == "_":
            rx += "."
        elif ch == "[" and i + 2 < len(pattern) and pattern[i + 2] == "]":
            rx += re.escape(pattern[i + 1])
            i += 2
        else:
            rx += re.escape(ch)
        i += 1
    return re.fullmatch(rx, value.rstrip(" "), re.S) is not None


def me_sql_run(rows: list[dict[str, Any]], turkish: bool):
    """`me_sql` metnini ayrıştırıp WHERE'i değerlendiren sahte çalıştırıcı (satırlar tablo sırasıyla)."""
    def run(sql: str) -> dict[str, Any]:
        m = re.search(r"WHERE LOWER\(DomainName\) LIKE N'(.*)' OR LOWER\(DomainName\) LIKE N'(.*)'$", sql)
        assert m, sql
        p1, p2 = (x.replace("''", "'") for x in m.groups())
        out = []
        for r in rows:
            low = sql_lower(r["DomainName"], turkish)
            if like(low, p1) or like(low, p2):
                out.append({k: r[k] for k in ("SystemUserId", "FullName", "IsDisabled", "DomainName")})
        return {"records": out}
    return run


def all_users_run(rows: list[dict[str, Any]], turkish: bool, calls: Optional[list] = None):
    def run(sql: str) -> list[dict[str, Any]]:
        assert sql == K.all_users_sql(SCHEMA)
        if calls is not None:
            calls.append(sql)
        return [{**{k: r[k] for k in ("SystemUserId", "FullName", "IsDisabled", "DomainName")},
                 "DomainNameLower": sql_lower(r["DomainName"], turkish)}
                for r in rows if r["DomainName"] not in (None, "")]
    return run


# ------------------------------------------------------------------ veri


def _uid(rnd: random.Random) -> uuid.UUID:
    return uuid.UUID(int=rnd.getrandbits(128))


ELLE = [   # zor durumlar: pasif/etkin çift, önek tuzağı, büyük harf, Türkçe I, boşluk, alan içinde @, kaçış karakterleri
    ("TIMAS\\ayse", False), ("TIMAS\\xayse", False), ("TIMAS\\Ayse", True), ("ayse@timas.com.tr", True),
    ("TIMAS\\ISMAIL", False), ("TIMAS\\ismail2", False), ("TIMAS\\ali ", False), (" TIMAS\\veli", False),
    ("X\\ahmet@foo", False), ("ahmet", False), ("TIMAS\\a_b", False), ("TIMAS\\axb", False), ("TIMAS\\a%b", False),
    ("TIMAS\\o'neil", False), ("OTHER\\SUB\\mehmet", False), ("mehmet@x", True), ("TIMAS\\mehmet", True),
    ("", False), (None, False), ("TIMAS\\", False), ("@timas", False), ("TIMAS\\zeynep@timas.com.tr", False),
]


def _rows(seed: int) -> list[dict[str, Any]]:
    rnd = random.Random(seed)
    names = ["ayse", "ali", "mehmet", "ismail", "zeynep", "a_b", "x.y", "Irmak", "busra", "ali2", "can"]
    forms = ["TIMAS\\{}", "{}@timas.com.tr", "OTHER\\{}", "TIMAS\\{} ", "{}", "X\\{}@y", "TIMAS\\{}x", "{}@"]
    rows = []
    for dn, dis in ELLE:
        rows.append({"SystemUserId": _uid(rnd), "FullName": f"Elle {dn}", "IsDisabled": dis, "DomainName": dn})
    for _ in range(120):
        n = rnd.choice(names)
        n = n.upper() if rnd.random() < 0.15 else (n.title() if rnd.random() < 0.15 else n)
        rows.append({"SystemUserId": _uid(rnd), "FullName": rnd.choice([None, "", f"K {n}"]),
                     "IsDisabled": rnd.choice([True, False, 1, 0, "1", "0"]), "DomainName": rnd.choice(forms).format(n)})
    # Liste = tablo sırası: iki sahte sorgu da satırları bu sırayla döndürür (yeni sorgu `ORDER BY SystemUserId`;
    # eski sorgu sırasız — aynı hesaba iki etkin kullanıcı düşerse gerçek CRM'de fark kabul betiğinde listelenir).
    return rows


USERNAMES = ["ayse", "Ayse", "AYSE", "ali", "ALI", "mehmet", "ismail", "ISMAIL", "zeynep", "ahmet", "a_b", "axb", "a%b",
             "o'neil", "veli", "irmak", "Irmak", "busra", "ali2", "can", "x.y", "yok", "timas", ""]


@pytest.mark.parametrize("turkish", [False, True])
@pytest.mark.parametrize("seed", [1, 2, 3, 7, 42])
def test_mapping_rule_old_equals_new(seed, turkish):
    rows = _rows(seed)
    dizin = K.dizin_kur([K._norm(r) for r in all_users_run(rows, turkish)(K.all_users_sql(SCHEMA))])
    old_run = me_sql_run(rows, turkish)
    derived = {K.hesap_kismi(r["DomainName"]) for r in rows if r["DomainName"]}
    checked = 0
    for u in sorted(set(USERNAMES) | derived | {d.upper() for d in derived}):
        old = M2.crm_me(SCHEMA, old_run, u)
        if not K.uygun(u):
            with pytest.raises(K.Bilinmiyor):
                K.eslestir(dizin, u)
            continue
        assert K.eslestir(dizin, u) == old, (u, turkish)
        checked += 1
    assert checked > 20


def test_hand_picked_cases():
    rows = _rows(5)
    dizin = K.dizin_kur([K._norm(r) for r in all_users_run(rows, False)(K.all_users_sql(SCHEMA))])
    ayse = K.eslestir(dizin, "Ayse")
    assert ayse and ayse["disabled"] is False                       # etkin olan pasiften önce
    only_passive = [{"SystemUserId": "P1", "FullName": "Eski", "IsDisabled": True, "DomainName": "TIMAS\\eski"}]
    pd = K.dizin_kur([K._norm(r) for r in all_users_run(only_passive, False)(K.all_users_sql(SCHEMA))])
    assert K.eslestir(pd, "eski") == {"id": "P1", "name": "Eski", "disabled": True}      # yalnız pasif varsa pasif
    assert M2.crm_me(SCHEMA, me_sql_run(only_passive, False), "eski") == K.eslestir(pd, "eski")
    assert K.eslestir(dizin, "ahmet") is None                       # 'X\ahmet@foo' eski süzgeçten geçmez
    assert K.eslestir(dizin, "a_b")["name"] == "Elle TIMAS\\a_b"    # _ joker değil
    # Türkçe harmanlama: 'TIMAS\ISMAIL' LOWER → 'tımas\ısmaıl', eski sorgu bulmaz; yeni de bulmaz.
    tr = K.dizin_kur([K._norm(r) for r in all_users_run(rows, True)(K.all_users_sql(SCHEMA))])
    assert M2.crm_me(SCHEMA, me_sql_run(rows, True), "ismail") == K.eslestir(tr, "ismail")


def test_unsuitable_usernames_go_to_the_live_path():
    for u in (" ayse", "ayse ", "ayşe", "a" * 81, ""):
        assert not K.uygun(u)
        with pytest.raises(K.Bilinmiyor):
            K.eslestir({}, u)


def test_all_users_sql_reads_disabled_users_too():
    sql = K.all_users_sql(SCHEMA)
    assert "FROM Timas_MSCRM.dbo.SystemUserBase" in sql and "IsDisabled" in sql and "IsDisabled =" not in sql
    assert "LOWER(DomainName) AS DomainNameLower" in sql and "ORDER BY SystemUserId" in sql


# ------------------------------------------------------------------ saklama, bellek, arkada yenileme


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    K._ready.discard(id(e))
    K.sifirla()
    yield e
    K.sifirla()


def _wait() -> None:
    for t in threading.enumerate():
        if t.name == "crm-kisi" and t is not threading.current_thread():
            t.join(10)


def test_read_once_store_restart_and_refresh_behind(engine, monkeypatch):
    rows = [{"SystemUserId": "A1", "FullName": "Ayşe", "IsDisabled": False, "DomainName": "TIMAS\\ayse"},
            {"SystemUserId": "B2", "FullName": "Mehmet", "IsDisabled": False, "DomainName": "mehmet@timas.com.tr"}]
    calls: list = []
    state = {"down": False}
    gate = threading.Event()
    gate.set()

    def okuyucu():
        gate.wait(10)                  # arkadaki okuma, istek eldeki değeri döndürene kadar bekletilebilir
        if state["down"]:
            raise RuntimeError("CRM kapalı")
        return SCHEMA, all_users_run(rows, False, calls)

    assert K.bul(engine, T, "ayse", okuyucu)["id"] == "A1" and len(calls) == 1
    assert K.bul(engine, T, "mehmet", okuyucu)["id"] == "B2" and len(calls) == 1      # herkes aynı okumadan
    assert K.bul(engine, T, "zeynep", okuyucu) is None and len(calls) == 1            # CRM'de yok
    assert K.durum(engine, T)["satir"] == 2

    K.sifirla()                                                                        # köprü yeniden kalktı
    assert K.bul(engine, T, "ayse", okuyucu)["id"] == "A1" and len(calls) == 1         # tablodan, CRM beklenmez

    rows.append({"SystemUserId": "C3", "FullName": "Zeynep", "IsDisabled": False, "DomainName": "TIMAS\\zeynep"})
    gate.clear()
    assert K.bul(engine, T, "zeynep", okuyucu, taze=-1) is None                        # eldeki hemen döner
    gate.set()
    _wait()
    assert len(calls) == 2 and K.bul(engine, T, "zeynep", okuyucu)["id"] == "C3"      # arkadaki okuma geldi

    state["down"] = True
    assert K.bul(engine, T, "ayse", okuyucu, taze=-1)["id"] == "A1"                    # CRM kapalı: eldeki kalır
    _wait()


def test_nothing_stored_and_crm_down_raises(engine):
    def okuyucu():
        raise RuntimeError("CRM kapalı")

    with pytest.raises(RuntimeError):
        K.bul(engine, T, "ayse", okuyucu)
    assert K.durum(engine, T) == {"okundu": None}


def test_mapping_reads_stay_out_of_query_info(engine):
    rows = [{"SystemUserId": "A1", "FullName": "Ayşe", "IsDisabled": False, "DomainName": "TIMAS\\ayse"}]
    K.oku(engine, T, lambda: (SCHEMA, all_users_run(rows, False)))
    K.sifirla()
    with IZ.izle(engine) as ran:
        assert K.bul(engine, T, "ayse", lambda: (SCHEMA, all_users_run(rows, False)))["id"] == "A1"
        with engine.connect() as c:                    # dıştaki izleme sürer
            c.execute(sa.select(sa.literal(1)))
    assert len(ran) == 1


def test_concurrent_first_lookups_read_once(engine, monkeypatch):
    """Hiç okuma yokken aynı anda bakan dört kişi tek CRM sorgusunu bekler."""
    rows = [{"SystemUserId": "A1", "FullName": "Ayşe", "IsDisabled": False, "DomainName": "TIMAS\\ayse"}]
    calls: list = []
    gate = threading.Event()

    def slow_run(sql):
        gate.wait(5)
        return all_users_run(rows, False, calls)(sql)

    K.ensure(engine)
    monkeypatch.setattr(K, "_yukle", lambda e, t, d: None)   # tablo boş; bellek içi SQLite tek bağlantı paylaşılmasın
    out: list = []
    ts = [threading.Thread(target=lambda: out.append(K.bul(engine, T, "ayse", lambda: (SCHEMA, slow_run)))) for _ in range(4)]
    for t in ts:
        t.start()
    import time
    time.sleep(0.3)                    # hepsi okuma kilidine gelsin
    gate.set()
    for t in ts:
        t.join(10)
    assert [o["id"] for o in out] == ["A1"] * 4 and len(calls) == 1
