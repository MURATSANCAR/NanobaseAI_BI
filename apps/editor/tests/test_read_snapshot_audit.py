"""Salt okunur işlem denetim bağlamını taşımaz: `SET TRANSACTION` işlemin ilk komutu olmalı (2026-10-03: kart servisinde
POST ile gelen her okuma `ActiveSqlTransaction` ile düştü)."""
import contextlib

from editor import db, foundation


def test_read_snapshot_starts_with_set_transaction_even_inside_an_audited_request(monkeypatch):
    sent = []

    class Conn:
        def execute(self, q, *a):
            sent.append(str(q))

    @contextlib.contextmanager
    def tx():
        # db.tx'in davranışı: bağlam varsa işlemin ilk komutu olarak yazılır
        if db.audit_context.get():
            sent.append("set_config nanobase.audit")
        yield Conn()

    monkeypatch.setattr(db, "tx", tx)
    token = db.audit_context.set('{"rid": "r", "actor": "a"}')
    try:
        with foundation.read_snapshot():
            pass
        assert sent[0].startswith("SET TRANSACTION")
        assert db.audit_context.get() == '{"rid": "r", "actor": "a"}'   # istek bağlamı geri gelir
    finally:
        db.audit_context.reset(token)
