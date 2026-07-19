"""Unit tests for Text2SQL endpoint selection / env wiring."""

from __future__ import annotations

import os

import pytest

from nanobase_awel.operators import llm_operator as lo


@pytest.fixture(autouse=True)
def _restore_env(monkeypatch):
    monkeypatch.setattr(lo, "LLM_BASE", "http://127.0.0.1:8010/v1")
    monkeypatch.setattr(lo, "LLM_MODEL", "qwen")
    monkeypatch.setattr(lo, "LLM_KEY", "k")
    monkeypatch.setattr(lo, "LLM_TIMEOUT_SEC", 90.0)
    monkeypatch.setattr(lo, "TEXT2SQL_TIMEOUT_SEC", 60.0)
    yield


def test_general_uses_chat_only(monkeypatch):
    monkeypatch.setattr(lo, "TEXT2SQL_BASE", "http://127.0.0.1:8091/v1")
    monkeypatch.setattr(lo, "TEXT2SQL_MODEL", "arctic-text2sql")
    monkeypatch.setattr(lo, "TEXT2SQL_FALLBACK", True)
    eps = lo._endpoints_for_purpose("general")
    assert len(eps) == 1
    assert eps[0][0].endswith(":8010/v1")
    assert eps[0][1] == "qwen"


def test_sql_plan_prefers_arctic_then_chat(monkeypatch):
    monkeypatch.setattr(lo, "TEXT2SQL_BASE", "http://127.0.0.1:8091/v1")
    monkeypatch.setattr(lo, "TEXT2SQL_MODEL", "arctic-text2sql")
    monkeypatch.setattr(lo, "TEXT2SQL_FALLBACK", True)
    monkeypatch.setattr(lo, "TEXT2SQL_TIMEOUT_SEC", 60.0)
    eps = lo._endpoints_for_purpose("sql_plan")
    assert len(eps) == 2
    assert eps[0][1] == "arctic-text2sql"
    assert eps[0][3] == 60.0
    assert eps[1][1] == "qwen"


def test_sql_repair_same_as_plan(monkeypatch):
    monkeypatch.setattr(lo, "TEXT2SQL_BASE", "http://127.0.0.1:8091/v1")
    monkeypatch.setattr(lo, "TEXT2SQL_MODEL", "arctic-text2sql")
    monkeypatch.setattr(lo, "TEXT2SQL_FALLBACK", False)
    eps = lo._endpoints_for_purpose("sql_repair")
    assert len(eps) == 1
    assert eps[0][1] == "arctic-text2sql"


def test_sql_plan_no_fallback_when_disabled(monkeypatch):
    monkeypatch.setattr(lo, "TEXT2SQL_BASE", "http://127.0.0.1:8091/v1")
    monkeypatch.setattr(lo, "TEXT2SQL_MODEL", "arctic-text2sql")
    monkeypatch.setattr(lo, "TEXT2SQL_FALLBACK", False)
    eps = lo._endpoints_for_purpose("sql_plan")
    assert len(eps) == 1
    assert eps[0][1] == "arctic-text2sql"


def test_sql_plan_without_text2sql_uses_chat(monkeypatch):
    monkeypatch.setattr(lo, "TEXT2SQL_BASE", "")
    eps = lo._endpoints_for_purpose("sql_plan")
    assert len(eps) == 1
    assert eps[0][1] == "qwen"
