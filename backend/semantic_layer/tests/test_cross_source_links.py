"""Veritabanları arası bağ keşfi: iki ayrı veritabanı, ortak hiçbir ad yok — yalnız değerler.

Kurgu kasten müşteriye benzemez: bir veritabanında yıl kopyalı bir ERP şekli, ikinci bir veritabanında
(ayrı bağlantı ya da aynı bağlantıya ATTACH edilmiş) bir CRM şekli. Keşif ne tablo ne kolon adı bilir; bulduğu her şey ölçülen örtüşmedendir.
"""

from __future__ import annotations

import random
import sqlite3

import pytest

from semantic_layer.models import ColumnProfile, SchemaProfile
from semantic_layer.profiler import cross_source_links as X
from semantic_layer.profiler.connectors import SQLiteConnector


def _col(name, typ, pk=False):
    return ColumnProfile(name=name, data_type=typ, is_primary_key=pk)


def _prof(schema, table, pattern, entity, cols, pk, rows, window=None, context=None):
    return SchemaProfile(datasource_id="d", table_name=table, table_pattern=pattern, entity=entity, schema_name=schema,
                         columns=cols, primary_key=pk, row_count=rows, time_window=window, context=context or {})


class _Spy(SQLiteConnector):
    """Kaydeden bağlantı: hangi veritabanına hangi cümle gitti, kaç parametreyle."""

    def __init__(self, conn):
        super().__init__(conn=conn)
        self.seen: list[tuple[str, int]] = []

    def execute(self, sql, limit):
        self.seen.append((sql, 0))
        return super().execute(sql, limit)

    def _rows(self, sql, params=()):
        self.seen.append((sql, len(params)))
        return super()._rows(sql, params)


@pytest.fixture(params=["two", "attached"])
def world(request):
    """two: ERP ve CRM iki ayrı veritabanı (iki bağlantı). attached: tek bağlantı, CRM ATTACH edilmiş."""
    rnd = random.Random(7)
    erp = sqlite3.connect(":memory:", check_same_thread=False)
    if request.param == "two":
        crm, pre = sqlite3.connect(":memory:", check_same_thread=False), ""
    else:
        erp.execute("ATTACH DATABASE ':memory:' AS crm")
        crm, pre = erp, "crm."
    erp.executescript(
        """
        CREATE TABLE LG_211_CLCARD (LOGICALREF INTEGER PRIMARY KEY, CODE TEXT, DEFINITION_ TEXT, CITY TEXT);
        CREATE TABLE LG_411_CLCARD (LOGICALREF INTEGER PRIMARY KEY, CODE TEXT, DEFINITION_ TEXT, CITY TEXT);
        CREATE TABLE LG_211_01_INVOICE (LOGICALREF INTEGER PRIMARY KEY, FICHENO TEXT, DATE_ TEXT, CLIENTREF INTEGER);
        CREATE TABLE LG_411_01_INVOICE (LOGICALREF INTEGER PRIMARY KEY, FICHENO TEXT, DATE_ TEXT, CLIENTREF INTEGER);
        CREATE TABLE LG_411_01_STLINE (LOGICALREF INTEGER PRIMARY KEY, SPECODE TEXT, DATE_ TEXT);
        """
    )
    crm.executescript(
        f"""
        CREATE TABLE {pre}AccountBase (AccountId TEXT PRIMARY KEY, new_logicalref TEXT, Name TEXT, Country TEXT);
        CREATE TABLE {pre}ShipmentBase (ShipmentId TEXT PRIMARY KEY, invoice_no TEXT, createdon TEXT, noise_ref TEXT, Title TEXT);
        """
    )
    cards = [(i, f"120.{i:05d}", f"Müşteri Adı {i}", "İstanbul") for i in range(1, 401)]
    erp.executemany("INSERT INTO LG_211_CLCARD VALUES (?,?,?,?)", cards)
    erp.executemany("INSERT INTO LG_411_CLCARD VALUES (?,?,?,?)", cards)
    old = [(i, f"GIB2023{i:09d}", f"202{1 + i % 5}-03-01", 1 + i % 400) for i in range(1, 701)]
    new = [(i, f"GIB2026{i:09d}", "2026-02-01", 1 + i % 400) for i in range(1, 301)]
    erp.executemany("INSERT INTO LG_211_01_INVOICE VALUES (?,?,?,?)", old)
    erp.executemany("INSERT INTO LG_411_01_INVOICE VALUES (?,?,?,?)", new)
    erp.executemany("INSERT INTO LG_411_01_STLINE VALUES (?,?,?)", [(i, f"S{i % 7}", "2026-01-01") for i in range(1, 6001)])
    accounts = []
    for i in range(1, 331):
        ref = str(rnd.randint(1, 400)) if i <= 320 else str(900000 + i)       # 10 of them point nowhere
        name = f"MÜŞTERİ ADI {ref}" if i <= 320 else f"Kayıp {i}"
        accounts.append((f"{i:08X}-0000-0000-0000-000000000000", ref, name, "Türkiye"))
    crm.executemany(f"INSERT INTO {pre}AccountBase VALUES (?,?,?,?)", accounts)
    ships = []
    for i in range(1, 901):
        if i <= 250:                                                            # older than the ERP keeps
            inv, created = f"TIM2019{i:09d}", "2019-05-01"
        elif i <= 880:
            inv, created = (f"GIB2023{rnd.randint(1, 700):09d}", "2023-04-01") if i % 2 else (f"GIB2026{rnd.randint(1, 300):09d}", "2026-03-01")
        else:
            inv, created = f"GIB2024{i:09d}", "2024-01-01"                      # does not exist: real misses
        ships.append((f"s{i}", inv, created, str(rnd.randint(1, 6000)), f"Sevkiyat {rnd.randint(1, 50)}"))
    crm.executemany(f"INSERT INTO {pre}ShipmentBase VALUES (?,?,?,?,?)", ships)
    erp.commit()
    crm.commit()

    erp_card = lambda t: _prof("main", t, "LG_{n0}_CLCARD", "LG_CLCARD",  # noqa: E731
                               [_col("LOGICALREF", "int", True), _col("CODE", "varchar(17)"), _col("DEFINITION_", "varchar(200)"), _col("CITY", "varchar(20)")],
                               ["LOGICALREF"], 400, ("2010-01-01", "2026-08-01"), {"n0": t[3:6]})
    erp_inv = lambda t, n, w: _prof("main", t, "LG_{n0}_{n1}_INVOICE", "LG_INVOICE",  # noqa: E731
                                    [_col("LOGICALREF", "int", True), _col("FICHENO", "varchar(17)"), _col("DATE_", "datetime"), _col("CLIENTREF", "int")],
                                    ["LOGICALREF"], n, w, {"n0": t[3:6], "n1": "01"})
    profiles = [
        erp_card("LG_211_CLCARD"), erp_card("LG_411_CLCARD"),
        erp_inv("LG_211_01_INVOICE", 700, ("2021-01-02", "2025-12-31")),
        erp_inv("LG_411_01_INVOICE", 300, ("2026-01-01", "2026-08-17")),
        _prof("main", "LG_411_01_STLINE", "LG_{n0}_{n1}_STLINE", "LG_STLINE",
              [_col("LOGICALREF", "int", True), _col("SPECODE", "varchar(10)"), _col("DATE_", "datetime")], ["LOGICALREF"], 6000),
        _prof("crm.dbo", "AccountBase", "ACCOUNTBASE", "ACCOUNTBASE",
              [_col("AccountId", "uniqueidentifier", True), _col("new_logicalref", "nvarchar(100)"), _col("Name", "nvarchar(160)"), _col("Country", "nvarchar(40)")],
              ["AccountId"], 330),
        _prof("crm.dbo", "ShipmentBase", "SHIPMENTBASE", "SHIPMENTBASE",
              [_col("ShipmentId", "uniqueidentifier", True), _col("invoice_no", "nvarchar(100)"), _col("createdon", "datetime"),
               _col("noise_ref", "nvarchar(100)"), _col("Title", "nvarchar(100)")],
              ["ShipmentId"], 900, ("2019-05-01", "2026-03-01")),
    ]
    if request.param == "two":
        erp_c, crm_c = _Spy(erp), _Spy(crm)
        probe = X.RoutedProbe({"": X.probe_for(erp_c), "CRM": X.probe_for(crm_c, database="crm")})
        return probe, profiles, (erp_c, crm_c)
    one = _Spy(erp)
    return X.RoutedProbe({"": X.probe_for(one)}), profiles, (one, None)


def _discover(world, **th):
    probe, profiles, _ = world
    times = {"SHIPMENTBASE": "createdon"}
    d = X.CrossSourceLinkDiscovery(profiles, probe, thresholds=X.LinkThresholds(**th),
                                   time_column=lambda p: times.get(p.entity), progress=lambda m: None)
    return d, d.run()


def test_values_decide_the_family_not_the_declared_type():
    th = X.LinkThresholds(min_distinct=3)
    assert X.profile_values(["14330", "14332", "292001"], "text", th).family == X.INT       # sayı metin olarak saklanmış
    assert X.profile_values(["00123", "00124", "00125"], "text", th).family == X.CODE        # baştaki sıfır: kod
    assert X.profile_values(["TIM2020000010552", "GIB2024000000001", "GIB2024000000002"], "text", th).family == X.CODE
    names = X.profile_values(["AYDIN TOK - KİTABEVİ", "HALE TAŞ", "ERHAN ÖZ"], "text", th)
    assert names.family is None and "free text" in names.reason                              # isim bir anahtar değildir
    assert X.profile_values(["1", "2"], "text", X.LinkThresholds()).family is None           # çok az farklı değer
    assert X.value_mask("GİB2024-01") == "AAA9999-99"


def test_a_source_is_the_database_in_front_of_the_schema():
    assert X.source_of("Timas_MSCRM.dbo") == "TIMAS_MSCRM"
    assert X.source_of("dbo") == X.source_of("") == ""


def test_catalog_step_counts_every_type_compatible_pair_without_touching_the_database(world):
    _, profiles, _ = world
    cat = X.catalog_candidates(profiles)
    assert cat.shapes_by_source == {"": 3, "CRM": 2}
    assert cat.pairs > 0 and set(cat.pairs_by_direction) == {"CRM->default", "default->CRM"}


def test_both_links_are_found_and_nothing_else(world):
    _, report = _discover(world)
    accepted = {(p.ref_entity, p.ref_column, p.key_entity, p.key_column) for p in report.accepted()}
    assert accepted == {("ACCOUNTBASE", "new_logicalref", "LG_CLCARD", "LOGICALREF"),
                        ("SHIPMENTBASE", "invoice_no", "LG_INVOICE", "FICHENO")}, [
        (p.ref_entity, p.ref_column, p.key_entity, p.key_column, p.stage, p.reason) for p in report.pairs]


def test_a_counter_contained_in_a_bigger_counter_is_not_a_link(world):
    """noise_ref 1..6000: STLINE'ın anahtarında tamamen var, ama birleşen satırlar hiçbir şeyde anlaşmıyor."""
    _, report = _discover(world)
    noise = [p for p in report.pairs if p.ref_column == "noise_ref" and p.key_entity == "LG_STLINE"]
    assert noise and all(p.stage != "accepted" for p in noise)
    assert any(p.sample_containment and p.sample_containment > 0.9 for p in noise)          # içerilme tek başına yetmezdi


def test_coverage_is_judged_inside_the_target_window_and_periods_are_told_apart(world):
    _, report = _discover(world)
    ship = next(p for p in report.accepted() if p.ref_entity == "SHIPMENTBASE")
    allc, inwin = ship.coverage["all"], ship.coverage["in_window"]
    assert allc["matched"] / allc["distinct"] < 0.9 <= inwin["matched"] / inwin["distinct"]   # eskiler pencere dışında
    assert ship.coverage["window"] == {"column": "createdon", "from": "2021-01-02"}
    assert set(allc["per_table"]) == {"LG_211_01_INVOICE", "LG_411_01_INVOICE"} and all(allc["per_table"].values())
    assert ship.period_semantics == "periodic"
    card = next(p for p in report.accepted() if p.ref_entity == "ACCOUNTBASE")
    assert card.period_semantics == "replicated"                                             # aynı kartın iki kopyası
    assert card.corroboration["columns"] == ["Name", "DEFINITION_"] and card.corroboration["rate"] >= 0.9


def test_the_apply_plan_carries_evidence_and_how_to_compare_the_two_sides(world):
    _, profiles, _ = world
    _, report = _discover(world)
    plan = X.apply_plan(report, profiles)
    by_col = {row["relationship"]["column"]: row for row in plan}
    card = by_col["new_logicalref"]
    assert card["table_name"] == "AccountBase" and card["action"] == "add"
    rel = card["relationship"]
    assert rel["ref_entity"] == "LG_CLCARD" and rel["ref_column"] == "LOGICALREF" and rel["cross_source"]
    assert rel["join_cast"] == "int" and rel["join_collate"] is False                        # metinde saklı sayı
    assert rel["evidence"]["coverage"]["all"]["ref_rows"] == 330 and rel["evidence"]["measured_at"]
    inv = by_col["invoice_no"]["relationship"]
    assert inv["join_cast"] is None and inv["join_collate"] is True                          # iki harmanlama
    assert inv["ref_pattern"] == "LG_{n0}_{n1}_INVOICE" and inv["period_semantics"] == "periodic"


def test_stricter_coverage_rejects_with_the_measured_reason(world):
    _, report = _discover(world, confirmed_coverage=0.999)
    card = next(p for p in report.pairs if p.ref_entity == "ACCOUNTBASE" and p.key_entity == "LG_CLCARD")
    assert card.stage == "confirm" and card.reason.startswith("coverage ")


def test_keys_meet_in_python_whatever_each_side_stores():
    assert X.norm_key(" 14330 ", X.INT) == X.norm_key(14330, X.INT) == X.norm_key("14330.0", X.INT) == "14330"
    assert X.norm_key("ABC", X.INT) is None and X.norm_key(None, X.CODE) is None and X.norm_key(" ", X.CODE) is None
    assert X.norm_key("Kitapçı Işık", X.CODE) == X.norm_key("KİTAPCI ISIK", X.CODE)     # Turkish_CI_AI eşitliği
    assert X.norm_key("{0a1b2c3d-0000-0000-0000-000000000000}", X.GUID) == X.norm_key("0A1B2C3D-0000-0000-0000-000000000000", X.GUID)
    assert X._SqlProbe.params(["12", " 12", "x", "013"], X.INT) == [12, 13]                # int anahtara metin gitmez


def test_no_statement_touches_both_databases(world):
    probe, _, (erp_c, crm_c) = world
    if crm_c is None:
        pytest.skip("tek bağlantı kurgusu")
    _, report = _discover(world)
    assert len(report.accepted()) == 2
    assert erp_c.seen and crm_c.seen
    assert not any(n in sql for sql, _ in erp_c.seen for n in ("AccountBase", "ShipmentBase"))
    assert not any("LG_" in sql for sql, _ in crm_c.seen)
    assert report.queries == len(erp_c.seen) + len(crm_c.seen)


def test_long_value_lists_are_split_never_cut(world, monkeypatch):
    """Parametre sınırı küçükken de sonuç aynı: her cümle sınırın altında, hiçbir değer düşmüyor."""
    probe, profiles, spies = world
    _, before = _discover(world)
    for s in spies:
        if s is not None:
            s.seen.clear()
    monkeypatch.setattr(X, "PARAM_CHUNK", 7)
    _, after = _discover(world)
    key = lambda r: {(p.ref_entity, p.ref_column, p.key_entity, p.key_column): p.coverage["all"] for p in r.accepted()}  # noqa: E731
    assert key(before) == key(after)
    assert max(n for s in spies if s is not None for _, n in s.seen) <= 7


def test_a_non_key_target_is_read_once_and_compared_in_python(world, monkeypatch):
    """Anahtar olmayan hedefte (FICHENO) birden çok parça gerekiyorsa değerler bir kez okunur; büyük/küçük
    harf ve aksan farkı Python'da eşitlenir (CRM'in CI_AI harmanı gibi)."""
    probe, profiles, _ = world
    by = {p.table_name: p for p in profiles}
    monkeypatch.setattr(X, "PARAM_CHUNK", 5)
    targets = [by["LG_211_01_INVOICE"], by["LG_411_01_INVOICE"]]
    ship = by["ShipmentBase"]
    measure = lambda: X.measure_coverage(probe, ship, "invoice_no", X.CODE, targets, "FICHENO",  # noqa: E731
                                         key_declared=False, since=("createdon", "2021-01-02"))
    base, _ = measure()
    crm = probe.of(ship)
    crm.c._rows(f"INSERT INTO {crm.table(ship)} VALUES ('lower', ' gib2026000000001', '2026-05-01', '1', 'x')")
    full, win = measure()
    assert full["ref_distinct_raw"] == base["ref_distinct_raw"] + 1              # veritabanı için ayrı bir değer
    assert full["distinct"] == base["distinct"] and full["matched"] == base["matched"]   # karşılaştırmada aynı
    assert full["distinct"] > win["distinct"] and win["matched"] / win["distinct"] >= 0.9
    assert full["ref_rows"] == 901 and win["ref_rows"] == 651
    assert full["multi_period"] == 0 and all(full["per_table"].values())


def test_priority_orders_the_work_and_drops_nothing(world):
    """Öncelik bir sıralamadır: önce iki ucu da öncelikli şekillerdeki çiftler, sonra kalanlar; sonuç aynı."""
    probe, profiles, _ = world
    _, plain = _discover(world)
    seen = []
    times = {"SHIPMENTBASE": "createdon"}
    d = X.CrossSourceLinkDiscovery(profiles, probe, time_column=lambda p: times.get(p.entity), progress=lambda m: None)
    report = d.run(priority={"ACCOUNTBASE", "LG_{n0}_CLCARD"},
                   on_batch=lambda name, r: seen.append((name, {(p.ref_entity, p.key_entity) for p in r.accepted()})))
    assert seen[0] == ("priority", {("ACCOUNTBASE", "LG_CLCARD")})
    assert seen[-1][0] == "rest"
    key = lambda r: sorted((p.ref_entity, p.ref_column, p.key_entity, p.key_column, p.stage) for p in r.pairs)  # noqa: E731
    assert key(report) == key(plain)


def test_many_values_against_a_scanned_column_read_the_table_once(world, monkeypatch):
    """Taranan hedefte birden çok parça gerekiyorsa tablo bir kez akışla okunur; sonuç aynı kalır."""
    probe, profiles, spies = world
    _, before = _discover(world)
    monkeypatch.setattr(X, "PARAM_CHUNK", 7)
    streamed = []
    real = X._SqlProbe.scan_values
    monkeypatch.setattr(X._SqlProbe, "scan_values", lambda self, t, c, w: streamed.append(t.table_name) or real(self, t, c, w))
    _, after = _discover(world)
    key = lambda r: sorted((p.ref_entity, p.ref_column, p.key_entity, p.key_column, p.stage) for p in r.pairs)  # noqa: E731
    assert key(before) == key(after) and streamed


def test_an_unreadable_target_is_reported_and_retried_not_counted_as_a_miss(world, monkeypatch):
    probe, profiles, _ = world
    real = X.SqliteLinkProbe.contained_many
    failed = []

    def flaky(self, table, columns, seek):
        if table.table_name.endswith("_CLCARD") and self.read_budget:    # yalnız bütçeli turda
            failed.append(table.table_name)
            raise TimeoutError("too slow")
        return real(self, table, columns, seek)

    monkeypatch.setattr(X.SqliteLinkProbe, "contained_many", flaky)
    seen = []
    times = {"SHIPMENTBASE": "createdon"}
    d = X.CrossSourceLinkDiscovery(profiles, probe, time_column=lambda p: times.get(p.entity), progress=lambda m: None)
    reasons = []
    report = d.run(on_batch=lambda name, r: (seen.append((name, [dict(x) for x in r.lookup_failures])),
                                             reasons.append({(p.ref_entity, p.key_entity): p.reason for p in r.pairs})))
    assert reasons[0][("ACCOUNTBASE", "LG_CLCARD")].startswith("unreadable: LG_211_CLCARD, LG_411_CLCARD")
    assert failed and seen[0][1] == [{"table": f"main.LG_{n}_CLCARD", "error": "too slow"} for n in (211, 411)]
    assert [n for n, _ in seen] == ["all", "retry"] and seen[-1][1] == []
    assert ("ACCOUNTBASE", "LG_CLCARD") in {(p.ref_entity, p.key_entity) for p in report.accepted()}
    assert not any(p.reason.startswith("unreadable") for p in report.pairs)
