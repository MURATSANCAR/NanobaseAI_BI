"""Editörsüz projeler (/editor-atama) turdan: eski hesap = yeni hesap (2026-09-29 hız işi).

Önce uç her açılışta üç CRM sorgusu koşturuyordu (sayı, sayfa, durum sayaçları; 11,6 sn). Şimdi tur ilk açılış
kapsamındaki bütün editörsüz projeleri bir kez okur, uç süzer. Bu test aynı sahte CRM verisinde eski üç sorguyu
(T-SQL → SQLite çevirisiyle) ve yeni yolu koşturup sonuçları karşılaştırır: sayı, sayfa (sıra dahil), sayaçlar aynı.
"""
from __future__ import annotations

import random
import sqlite3
import uuid

import pytest
import sqlglot

from semantic_bridge import editorial_assign as A
from semantic_bridge.editorial import PAGE_SIZE

SCHEMA = "main.dbo"          # _prefix → "main.dbo." ; SQLite'ta "main." olarak koşar
KITS = [str(uuid.UUID(int=i + 1)).upper() for i in range(3)]
MARKAS = [str(uuid.UUID(int=100 + i)).upper() for i in range(2)]
USERS = [str(uuid.UUID(int=200 + i)).upper() for i in range(2)]
STATUSES = [100000019, 100000020, 100000015, 100000012, 1]


def _sqlite(sql: str) -> str:
    sql = sql.replace("main.dbo.", "main.")
    return sqlglot.transpile(sql, read="tsql", write="sqlite")[0]


@pytest.fixture(scope="module")
def db():
    rnd = random.Random(7)
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.executescript("""
        CREATE TABLE new_projeBase (new_projeId TEXT PRIMARY KEY, new_name TEXT, statuscode INT, statecode INT,
            new_Kitaplik TEXT, new_yayinciid TEXT, new_editoru TEXT, new_tahminisayfasayisi INT,
            new_yayinkuruluonaytarihi TEXT, new_hedeflenenbaskitarihi TEXT, CreatedOn TEXT, ModifiedOn TEXT,
            new_olasiyazartext TEXT, new_OlasYazarYazar TEXT);
        CREATE TABLE new_kitaplikBase (new_kitaplikId TEXT PRIMARY KEY, new_name TEXT);
        CREATE TABLE new_markaBase (new_markaId TEXT PRIMARY KEY, new_name TEXT);
        CREATE TABLE SystemUserBase (SystemUserId TEXT PRIMARY KEY, FullName TEXT);
        CREATE TABLE ContactBase (ContactId TEXT PRIMARY KEY, FullName TEXT);
    """)
    c.executemany("INSERT INTO new_kitaplikBase VALUES (?, ?)", [(k, f"Kitaplık {i}") for i, k in enumerate(KITS)])
    c.executemany("INSERT INTO new_markaBase VALUES (?, ?)", [(m, f"Marka {i}") for i, m in enumerate(MARKAS)])
    c.executemany("INSERT INTO SystemUserBase VALUES (?, ?)", [(u, f"Editör {i}") for i, u in enumerate(USERS)])
    authors = [str(uuid.UUID(int=300 + i)).upper() for i in range(5)]
    c.executemany("INSERT INTO ContactBase VALUES (?, ?)", [(a, f"Yazar {i}") for i, a in enumerate(authors)])
    rows = []
    for i in range(420):
        day = f"20{rnd.choice(['23', '24', '25', '26'])}-{rnd.randint(1, 12):02d}-{rnd.randint(1, 28):02d}"
        board = None if rnd.random() < 0.5 else f"2025-{rnd.randint(1, 12):02d}-{rnd.randint(1, 5):02d}"   # eşit tarih çok
        rows.append((str(uuid.UUID(int=10_000 + i)).upper(), f"Proje {i}", rnd.choice(STATUSES),
                     0 if rnd.random() < 0.9 else 1, rnd.choice(KITS + [None]), rnd.choice(MARKAS + [None]),
                     None if rnd.random() < 0.7 else rnd.choice(USERS), rnd.choice([None, 96, 240]),
                     board, None, day, f"2026-0{rnd.randint(1, 9)}-0{rnd.randint(1, 9)}",
                     rnd.choice([None, "Serbest Yazar"]), rnd.choice(authors + [None])))
    c.executemany("INSERT INTO new_projeBase VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    return c


def run(c, sql):
    return [dict(r) for r in c.execute(_sqlite(sql)).fetchall()]


def old(c, statuses, category, page, year):
    """Eski uç: üç sorgu."""
    flt = {"statuses": statuses, "since_year": year, "q": "", "category": category}
    total = int(run(c, A.pending_count_sql(SCHEMA, **flt))[0]["n"])
    items = [A.project_row(r) for r in run(c, A.pending_list_sql(SCHEMA, page, **flt))]
    facets = [{"code": int(r["kod"] or 0), "label": None if r["statuscode"] is None else str(r["statuscode"]),
               "count": int(r["n"])} for r in run(c, A.pending_facets_sql(SCHEMA, year))]
    return total, items, facets


def new(c, statuses, category, page, year):
    snap = A.pending_snapshot(run(c, A.pending_all_sql(SCHEMA, year)), year)
    return A.pending_from_snapshot(snap, statuses=statuses, category=category, page=page)


CASES = [(list(A.WORK_STATUSES), ""), ([], ""), ([100000015], ""), (list(A.WORK_STATUSES), f"kitaplik:{KITS[0]}"),
         ([], f"marka:{MARKAS[1].lower()}"), ([1, 100000012], f"kitaplik:{KITS[2]}")]


@pytest.mark.parametrize("statuses,category", CASES)
def test_eski_hesap_yeni_hesaba_esit(db, statuses, category):
    year = 2024
    t_old, _, f_old = old(db, statuses, category, 0, year)
    pages = max(1, -(-t_old // PAGE_SIZE)) + 1          # son sayfanın bir fazlası: boş sayfa da aynı
    for page in range(pages):
        o = old(db, statuses, category, page, year)
        n = new(db, statuses, category, page, year)
        assert n[0] == o[0]
        assert n[1] == o[1], f"sayfa {page}"
        assert sorted(n[2], key=lambda f: f["code"]) == sorted(o[2], key=lambda f: f["code"])
        assert [f["count"] for f in n[2]] == sorted((f["count"] for f in n[2]), reverse=True)
    assert t_old > 0


def test_sayi_sorgusu_birlesimsiz_ayni(db):
    flt = {"statuses": list(A.WORK_STATUSES), "since_year": 2024, "q": "", "category": ""}
    lean = A.pending_count_sql(SCHEMA, **flt)
    assert "JOIN" not in lean
    full = f"SELECT COUNT(*) AS n{A._project_from(A._prefix(SCHEMA))} WHERE {A._pending_where(**flt)}"
    assert run(db, lean)[0]["n"] == run(db, full)[0]["n"]
    # aramada kişi adı gerektiği için birleşim kalır
    assert "JOIN" in A.pending_count_sql(SCHEMA, **dict(flt, q="yazar"))


def test_gecersiz_kategori_reddedilir():
    with pytest.raises(A.AssignError):
        A.pending_from_snapshot({"items": []}, statuses=[], category="tur:1")
    with pytest.raises(A.AssignError):
        A.pending_from_snapshot({"items": []}, statuses=[], category="kitaplik:x' OR 1=1 --")
