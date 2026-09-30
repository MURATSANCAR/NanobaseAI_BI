"""M30 saha «Bugün» hızı (2026-09-29): `GET /field/today` 5,1 / 5,1 sn.

Neden: öncelik sırası gece/hafif turda hazır (`today_ranked` belleği), ama uç her açılışta CRM tahsilat onay akışını ve
CRM kullanıcılarını istiyordu; bunlar 5 dk'lık bellekteydi ve bellek dolunca okuma ekranı açanın isteğinde koşuyordu
(hafif tur 15 dk'da bir). Şimdi liste okumaları «eskiyse hemen ver, arkada yenile»; hafif tur ve «yenile» bekler.

Burada: ilk okuma beklenir; taze bellekten; bayat değer hemen döner ve CRM arkada bir kez okunur; `fresh` bekler; bayat
sınırını aşınca beklenir; okuma metni (sorgu bilgisi) her dönüşte kaydedilir; kayıt değeri aynıdır.
"""
from __future__ import annotations

import threading
import time
from datetime import timedelta

from semantic_bridge import field_sales as F
from semantic_bridge import field_sales_sources as S
from semantic_layer.tests.test_field_sales import USERS, _settings

SCHEMA = "Timas_MSCRM.dbo"
TAHSILAT = [{"id": "c1", "ad": "T1", "durum": S.T_PENDING, "tutar": 1000}]


class _Crm:
    """Sayan sahte CRM bağlantısı; `gate` verilirse okuma o açılana kadar bekler (arkada okuma sırasında ekran beklemez)."""

    calls: list[str] = []
    gate: threading.Event | None = None
    version = 1

    def __init__(self):
        self.cfg = {"database": "CRMDB"}

    def execute(self, sql, limit):
        tag = S.query_tag(sql)
        _Crm.calls.append(tag)
        if _Crm.gate is not None:
            _Crm.gate.wait(5)
        if tag == "crm.kullanicilar":
            return ["x"], [dict(u, v=_Crm.version) for u in USERS], False
        if tag == "crm.tahsilat":
            return ["x"], [dict(t, v=_Crm.version) for t in TAHSILAT], False
        return ["x"], [], False

    def close(self):
        pass


def _bekle(sart, sure=3.0):
    son = time.time() + sure
    while time.time() < son:
        if sart():
            return True
        time.sleep(0.01)
    return False


def _source(taze=0.05, bayat=60.0):
    _Crm.calls, _Crm.gate, _Crm.version = [], None, 1
    s = F.Source(lambda: _Crm(), lambda: _Crm())
    s._lists.taze, s._lists.bayat = taze, bayat
    return s


def test_list_reads_are_served_stale_and_refreshed_in_background():
    s = _source(taze=0.5)
    st = {**_settings(), "schema": SCHEMA}
    with F.recording() as first:
        a = s.collections(st)
    assert _Crm.calls == ["crm.tahsilat"] and a[0]["v"] == 1
    with F.recording() as again:
        assert s.collections(st) == a                                   # taze: CRM'e gidilmez
    assert _Crm.calls == ["crm.tahsilat"] and again == first            # okuma metni yine kaydedilir
    time.sleep(0.55)
    _Crm.version = 2
    _Crm.gate = threading.Event()
    t0 = time.monotonic()
    with F.recording() as stale:
        b = s.collections(st)                                           # bayat: eldeki değer hemen
    assert time.monotonic() - t0 < 1.0 and b[0]["v"] == 1 and stale == first
    assert _bekle(lambda: _Crm.calls == ["crm.tahsilat", "crm.tahsilat"])  # arkada tek okuma
    s.collections(st)
    assert _Crm.calls.count("crm.tahsilat") == 2                          # arkada okuma sürerken ikinci okuma başlamaz
    _Crm.gate.set()
    assert _bekle(lambda: s.collections(st)[0]["v"] == 2)
    _Crm.gate = None


def test_fresh_waits_and_expired_value_is_not_served():
    s = _source(taze=0.05, bayat=0.1)
    st = {**_settings(), "schema": SCHEMA}
    s.users(st)
    s.users(st, fresh=True)                                             # hafif tur / «yenile»: beklenir
    assert _Crm.calls == ["crm.kullanicilar", "crm.kullanicilar"]
    time.sleep(0.15)
    _Crm.version = 3
    assert s.users(st)[0]["v"] == 3                                     # bayat sınırı aştı: beklenerek okunur
    assert _Crm.calls.count("crm.kullanicilar") == 3


def test_value_is_the_same_as_a_direct_read():
    s = _source(taze=60)
    st = {**_settings(), "schema": SCHEMA}
    since = F.today() - timedelta(days=st["collectionDays"])
    direct = s.crm(lambda run: S.lower_keys(run(S.crm_collections_sql(SCHEMA, since))))
    assert s.collections(st) == direct
