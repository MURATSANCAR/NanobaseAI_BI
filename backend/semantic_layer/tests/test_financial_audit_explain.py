"""Finansal denetim bulgu açıklaması ve istisna kümeleme (`financial_audit_explain`): bulgu kuraldır; açıklama sayı
denetimli (olgu dışı sayı → kural metni); kümeleme SQL'de gruplar ve kural sınıfı verir, model yalnız kuralın bilemediği
gruba kapalı küme seçimle muhtemel sınıf önerir (eşik altı «incelenecek»); uçlar ayrıntı yetkisine bağlı.

Veriler yapaydır; model yerine sahte `chat` / `choose`.
"""

from __future__ import annotations

from types import SimpleNamespace

from semantic_bridge import access as A
from semantic_bridge import financial_audit_explain as E
from semantic_bridge.financial_audit_deep import DEFINITIONS

RUN = {
    "runId": "a" * 32, "year": 2026, "lastDate": "2026-08-17",
    "checks": [{"id": "slip-balance", "title": "Fiş bazında borç–alacak eşitliği", "affected": 12, "amount": "3456.7800",
                "formula": "Her fişte |Σ borç − Σ alacak| > 0,01 TL", "status": "finding", "sql": "SELECT 1"}],
    "deepAudit": {"asOf": "2026-08-17", "checks": [
        {"id": "invoice-ledger-amount", "title": "Fatura tutarı ↔ bağlı muhasebe hesabı", "status": "finding", "affected": 40,
         "tested": 900, "formula": DEFINITIONS["invoice-ledger-amount"][3], "sql": "SELECT 2"}]},
}


class Chat:
    def __init__(self, text):
        self.text = text

    def chat(self, messages, **kw):
        return self.text


def test_every_check_has_a_guide():
    for cid in list(DEFINITIONS) + ["trial-balance", "slip-balance", "account-sign", "account-link", "null-amount", "slip-link"]:
        what, causes, docs = E.GUIDE[cid]
        assert what and causes and docs


def test_explain_uses_model_only_with_fact_numbers():
    ok = E.explain(RUN, "slip-balance", llm=Chat("Bu raporda 12 fişte borç ve alacak eşit değil. Olası neden fişe eksik "
                                                    "satır girilmesidir. İlgili fişin bütün satırlarına bakılmalıdır."))
    assert ok["kaynak"] == "zeki" and ok["sql"] == "SELECT 1" and ok["belgeler"]
    bad = E.explain(RUN, "slip-balance", llm=Chat("Bu raporda 57 fişte fark var ve zarar 9.999 TL."))
    assert bad["kaynak"] == "kural" and bad["neden"].startswith("olgu-disi-sayi")
    assert "12 kayıt" in bad["metin"] and "Olası nedenler" in bad["metin"]
    assert E.explain(RUN, "invoice-ledger-amount")["kaynak"] == "kural"        # model yok
    tech = E.explain(RUN, "slip-balance", llm=Chat("Qwen modeline göre 12 fiş hatalı."))
    assert tech["kaynak"] == "kural"


def test_cluster_sql_groups_all_exceptions_with_rule_class():
    sql = E.cluster_sql("invoice-ledger-amount", 2026, "2026-08-17")
    assert DEFINITIONS["invoice-ledger-amount"][2] in sql and "GROUP BY R.accountCode" in sql
    assert "'mukerrer'" in sql and "'eksik-belge'" in sql and "OFFSET" not in sql      # sayfalama yok
    assert "'zamanlama'" in E.cluster_sql("invoice-date", 2026, "2026-08-17")
    assert "NULL AS ruleClass" in E.cluster_sql("cash-negative-day", 2026, "2026-08-17")


def _choice(label, p=0.9, m=0.8):
    return SimpleNamespace(choice=label, probability=p, margin=m)


def test_cluster_rule_first_model_only_for_unknown_groups():
    rows = [{"accountCode": "120.01", "month": 3, "ruleClass": "eksik-belge", "rows": 5, "amount": 100, "firstDate": "2026-03-01", "lastDate": "2026-03-20"},
            {"accountCode": "120.02", "month": 4, "ruleClass": None, "rows": 7, "amount": 50, "firstDate": "2026-04-01", "lastDate": "2026-04-30"},
            {"accountCode": "320.01", "month": 5, "ruleClass": None, "rows": 2, "amount": 10, "firstDate": None, "lastDate": None}]
    asked = []

    def choose(prompt, labels):
        asked.append(prompt)
        return _choice("Zamanlama farkı") if "120.02" in prompt else _choice("Mükerrer kayıt", p=0.5, m=0.1)

    out = E.cluster("invoice-ledger-amount", rows, choose)
    assert len(asked) == 2                                                  # kural sınıflı gruba sorulmaz
    g = {x["label"]: x for x in out["groups"]}
    assert g["Hesap 120.01 · Ay 3"]["source"] == "kural" and g["Hesap 120.01 · Ay 3"]["class"] == "eksik-belge"
    assert g["Hesap 120.02 · Ay 4"]["source"] == "zeki" and g["Hesap 120.02 · Ay 4"]["class"] == "zamanlama"
    assert g["Hesap 320.01 · Ay 5"]["source"] == "incele"                   # eşik altı
    s = {x["class"]: x for x in out["summary"]}
    assert s["eksik-belge"]["rows"] == 5 and s["zamanlama"]["rows"] == 7 and s["incele"]["rows"] == 2
    assert out["totalRows"] == 14 == sum(x["rows"] for x in out["summary"])  # hiçbir satır düşmez
    none = E.cluster("invoice-ledger-amount", rows, None)
    assert [x["source"] for x in none["groups"]] == ["kural", "incele", "incele"]


def test_cluster_model_failure_leaves_group_for_review():
    def boom(prompt, labels):
        raise RuntimeError("kuyruk dolu")
    out = E.cluster("bank-unposted", [{"sourceModule": 7, "accountCode": "102", "month": 1, "ruleClass": None, "rows": 3, "amount": 5}], boom)
    assert out["groups"][0]["source"] == "incele" and out["failed"] == 1


def test_cluster_prompt_has_no_personal_fields():
    p = E.choose_prompt("invoice-unposted", {"transactionType": 8, "month": 2, "rows": 3, "amount": 10}, ("transactionType",))
    assert "İşlem türü kodu 8" in p and "Ay 2" in p


def test_access_rules_for_new_endpoints():
    assert "ozellik:denetim.detay" in A.features_for("POST", "/api/v1/financial-audit/runs/abc/clusters/invoice-date")
    assert "ozellik:denetim.detay" in A.features_for("GET", "/api/v1/financial-audit/runs/abc/clusters/invoice-date")
    assert "ozellik:denetim.detay" not in A.features_for("POST", "/api/v1/financial-audit/runs/abc/explain/slip-balance")
