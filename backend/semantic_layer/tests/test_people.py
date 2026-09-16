"""Kişi rehberi: CRM satırı, kişinin kendi alanları, fotoğraf ve "CRM önce gelir" kuralı."""

from __future__ import annotations

import base64
import uuid
from datetime import datetime, timezone

import pytest

from semantic_bridge import people as P
from semantic_layer.store.catalog_store import open_store

T = "t1"
JPEG = "data:image/jpeg;base64," + base64.b64encode(b"\xff\xd8\xff\xe0" + b"0" * 64).decode()

ROWS = [
    {"SystemUserId": "a1", "FullName": "Ahmet Yıldız", "DomainName": "TIMAS\\AhmetY", "JobTitle": "",
     "Title": "Sanat Yönetmeni", "new_gorevbirimi": "Tasarım", "InternalEMailAddress": "ahmety@timas.com.tr",
     "MobilePhone": None, "HomePhone": None},
    {"SystemUserId": "b2", "FullName": "Büşra Aksoy", "DomainName": "busraa@timas.com.tr", "JobTitle": None,
     "Title": None, "new_gorevbirimi": None, "InternalEMailAddress": None, "MobilePhone": "0555 000 00 00",
     "HomePhone": None},
]


@pytest.fixture
def engine():
    e = open_store("sqlite://").engine
    P._ready.discard(id(e))
    P.ensure(e)
    return e


def _dir(rows=ROWS):
    calls = []
    d = P.Directory()

    def run(sql):
        calls.append(sql)
        return {"records": rows}

    return d, run, calls


def test_directory_reads_only_real_active_users_and_caches():
    d, run, calls = _dir()
    rows, _ = d.rows("Timas_MSCRM.dbo", run)
    d.rows("Timas_MSCRM.dbo", run)
    assert len(calls) == 1
    sql = calls[0]
    assert " FROM Timas_MSCRM.dbo.SystemUserBase " in sql and "ActiveDirectoryGuid" in sql
    assert "IsDisabled = 0" in sql and "AccessMode IN (0, 1)" in sql and "DomainName IS NOT NULL" in sql
    assert [(r["username"], r["title"], r["unit"]) for r in rows] == [
        ("ahmety", "Sanat Yönetmeni", "Tasarım"), ("busraa", "", "")]
    d.rows("Timas_MSCRM.dbo", run, fresh=True)
    assert len(calls) == 2


def test_bad_schema_is_refused():
    d, run, _ = _dir()
    with pytest.raises(P.ProfileError):
        d.rows("x]; DROP TABLE y--.dbo", run)
    with pytest.raises(P.ProfileError):
        d.rows("", run)


def test_own_fields_fill_only_what_crm_leaves_empty(engine):
    d, run, _ = _dir()
    rows, _ = d.rows("Timas_MSCRM.dbo", run)
    P.save_fields(engine, T, "BusraA", {"extension": "1055", "floor": "4. Kat", "mobile": "0532 111 22 33"})
    people = {p["username"]: p for p in P.people(engine, T, rows)}
    assert people["busraa"]["extension"] == "1055"
    assert people["busraa"]["floor"] == "4. Kat"
    assert people["busraa"]["mobile"] == "0555 000 00 00"   # CRM dolu: kişinin yazdığı görünmez
    assert people["ahmety"]["extension"] == "" and people["ahmety"]["photoVersion"] is None

    me = P.me(engine, T, "busraa", "Büşra Aksoy", rows)
    assert me["inCrm"] and me["fields"]["mobile"] == "0532 111 22 33"
    assert P.me(engine, T, "yok", "Yok Kişi", rows)["inCrm"] is False


def test_field_validation(engine):
    with pytest.raises(P.ProfileError):
        P.save_fields(engine, T, "u", {"extension": "abc"})
    with pytest.raises(P.ProfileError):
        P.save_fields(engine, T, "u", {"about": "x" * 401})
    with pytest.raises(P.ProfileError):
        P.save_fields(engine, T, "u", {"floor": {"a": 1}})


def test_photo_roundtrip_and_rejects_non_images(engine):
    v = P.save_photo(engine, T, "AhmetY", JPEG)
    blob, mime = P.photo(engine, T, "ahmety")
    assert mime == "image/jpeg" and blob.startswith(b"\xff\xd8\xff")
    d, run, _ = _dir()
    rows, _ = d.rows("Timas_MSCRM.dbo", run)
    assert {p["username"]: p for p in P.people(engine, T, rows)}["ahmety"]["photoVersion"] == v

    # Fotoğraf yüklemek alanları silmez, alan kaydı fotoğrafı silmez.
    P.save_fields(engine, T, "ahmety", {"extension": "1134"})
    assert P.photo(engine, T, "ahmety") is not None

    with pytest.raises(P.ProfileError):
        P.save_photo(engine, T, "ahmety", "data:image/jpeg;base64," + base64.b64encode(b"<svg>").decode())
    with pytest.raises(P.ProfileError):
        P.save_photo(engine, T, "ahmety", "data:image/svg+xml;base64,PHN2Zz4=")

    P.delete_photo(engine, T, "ahmety")
    assert P.photo(engine, T, "ahmety") is None
    assert P.me(engine, T, "ahmety", "Ahmet", [])["fields"]["extension"] == "1134"


RECENT = int((datetime.now(timezone.utc) - datetime(1601, 1, 1, tzinfo=timezone.utc)).total_seconds() * 10**7)
OLD = RECENT - 400 * 86400 * 10**7
G_AHMET = uuid.UUID("681de71b-f659-4a32-a61b-b4721270d41c")


def _ad_entries():
    # ldap3 ham biçimi: değerler liste, GUID küçük uçlu bayt.
    return [
        {"sAMAccountName": ["ahmet.yildiz"], "objectGUID": [G_AHMET.bytes_le], "lastLogonTimestamp": [str(RECENT)],
         "distinguishedName": ["CN=Ahmet,OU=Cocuk_Editorya,DC=timas,DC=local"], "title": ["AD unvanı"],
         "ipPhone": ["1134"], "physicalDeliveryOfficeName": ["3. Kat"]},
        {"sAMAccountName": ["busraa"], "objectGUID": [], "lastLogonTimestamp": [str(RECENT)],
         "distinguishedName": ["CN=Büşra,OU=Satis,DC=timas,DC=local"], "department": ["Yayın"]},
        {"sAMAccountName": ["amazon"], "lastLogonTimestamp": [], "distinguishedName": ["CN=Amazon,OU=Satis,DC=timas,DC=local"]},
        {"sAMAccountName": ["kasa01"], "lastLogonTimestamp": [str(OLD)], "distinguishedName": ["CN=kasa,OU=depo,DC=timas,DC=local"]},
    ]


def test_ad_match_by_guid_then_account_and_drop_idle_accounts():
    rows = [dict(ROWS[0], AdGuid="{" + str(G_AHMET).upper() + "}"),   # hesap adı AD'de değişmiş, GUID tutar
            dict(ROWS[1], AdGuid=None),
            {"SystemUserId": "c3", "FullName": "Amazon Amazon", "DomainName": "TIMAS\\amazon"},
            {"SystemUserId": "d4", "FullName": "kasa 01", "DomainName": "TIMAS\\kasa01"},
            {"SystemUserId": "e5", "FullName": "Ayrılan Kişi", "DomainName": "TIMAS\\ayrilan"}]
    idx = P.index_ad(_ad_entries())
    d, run, _ = _dir(rows)
    out, _ = d.rows("Timas_MSCRM.dbo", run, ad=lambda: idx, max_idle_days=365)
    assert d.ad_checked
    by = {r["username"]: r for r in out}
    assert set(by) == {"ahmet.yildiz", "busraa"}         # hiç giriş yok, 400 gün önce, AD'de yok: girmez
    assert by["ahmet.yildiz"]["title"] == "Sanat Yönetmeni"  # CRM dolu: AD ezmez
    assert (by["ahmet.yildiz"]["extension"], by["ahmet.yildiz"]["floor"]) == ("1134", "3. Kat")
    assert by["busraa"]["unit"] == "Yayın"
    assert P.index_ad(_ad_entries())["amazon"]["unit"] == "Satis"

    # Süreye bakılmazsa ortak hesaplar da gelir (AD'de etkin oldukları için).
    d2, run2, _ = _dir(rows)
    out, _ = d2.rows("Timas_MSCRM.dbo", run2, ad=lambda: idx, max_idle_days=0)
    assert {r["username"] for r in out} == {"ahmet.yildiz", "busraa", "amazon", "kasa01"}
    assert {r["username"]: r for r in out}["ahmet.yildiz"]["unit"] == "Tasarım"


def test_ou_and_logon_parsing():
    assert P._ou("CN=A\\, B,OU=Cocuk_Editorya,OU=Timas,DC=timas,DC=local") == "Cocuk Editorya"
    assert P._ou("CN=yok,CN=Users,DC=timas,DC=local") == ""
    assert P._logon(["0"]) is None and P._logon([]) is None
    assert P._logon([str(RECENT)]).year == datetime.now(timezone.utc).year


def test_ad_failure_falls_back_to_crm_only():
    d, run, _ = _dir()

    def broken():
        raise RuntimeError("dizin kapalı")

    out, _ = d.rows("Timas_MSCRM.dbo", run, ad=broken)
    assert len(out) == 2 and d.ad_checked is False
    d2, run2, _ = _dir()
    out, _ = d2.rows("Timas_MSCRM.dbo", run2, ad=lambda: None)   # ayar yok
    assert len(out) == 2 and d2.ad_checked is False
