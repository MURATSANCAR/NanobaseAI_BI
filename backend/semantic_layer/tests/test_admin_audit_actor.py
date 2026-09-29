"""Değişiklik kaydında kişi olmayan yapan (zamanlayıcı, gece işi) ürün adıyla görünür: «ZEKİ AI», «sistem» değil."""

from __future__ import annotations

import sqlalchemy as sa

from semantic_bridge import admin as AD


def _engine():
    e = sa.create_engine("sqlite://")
    AD.ensure(e)
    return e


def test_system_actors_are_written_and_shown_as_product_name():
    e = _engine()
    AD.audit(e, None, "run", "access", "x", "zamanlı iş")
    AD.audit(e, "zamanlayıcı", "run", "access", "y", "zamanlı iş")
    AD.audit(e, "ali", "update", "setting", "z", "kişi")
    with e.begin() as c:                                   # eski kayıt: «sistem» yazılmış
        c.execute(AD.AUDIT.insert().values(at=AD._now(), actor="sistem", action="run", kind="access", object_id="w"))
    items = AD.audit_list(e)["items"]
    assert sorted(i["actor"] for i in items) == sorted(["ali", AD.LLM_DISPLAY, AD.LLM_DISPLAY, AD.LLM_DISPLAY])
    assert len(AD.audit_list(e, actor=AD.LLM_DISPLAY)["items"]) == 3
    assert [i["actor"] for i in AD.audit_list(e, actor="ali")["items"]] == ["ali"]


def test_product_name_is_not_listed_as_a_person():
    e = _engine()
    AD.audit(e, None, "run", "access", "x", "zamanlı iş")
    AD.audit(e, "ali", "update", "setting", "z", "kişi")
    with e.connect() as c:
        rows = c.execute(AD.users_stmts("t", "d")["actions"]).all()
    assert [r[0] for r in rows] == ["ali"]
