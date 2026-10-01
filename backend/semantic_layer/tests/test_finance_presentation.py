"""Ekrana giden finans metinlerinde teknik ad yok (2026-09-25 kullanıcı kuralı).

Süzgeç: bilinen teknik terim listesi; sabit iletiler: finance_query paketindeki her ContractError iletisi ve
karşılaştırma biçim hataları kodlarıyla birlikte `public_error`'dan geçer ve iz bırakmaz.
"""
import ast
import re
from pathlib import Path

import pytest

from semantic_bridge.finance_query import presentation
from semantic_bridge.finance_query.contracts import METRICS, ContractError
from semantic_bridge.finance_query.planner import comparison_shape_error, unmet_error
from semantic_bridge.finance_query.presentation import leaks, public_error, public_response, public_text

PACKAGE = Path(presentation.__file__).parent

TECHNICAL = [
    "TRCODE IN (7,8,9) satırları", "f.LINENET toplamı", "NETTOTAL başlık toplamı", "LINETYPE=0 malzeme satırı",
    "SUM(CASE WHEN f.TRCODE IN (2,3) THEN -f.LINENET ELSE f.LINENET END)", "Ham SQL üretme", "SQL sorgusu",
    "statecode=0 olan kartlar", "statuscode alanı", "LG_211_01_STLINE tablosu", "LG_411_CLCARD", "AccountBase",
    "new_kitapBase.new_stokkodu", "new_yazartext künye metni", "crm_report dalı", "logo_report seçildi",
    "population_contract predicate", "relational_query planı", "derived alanı boş olmalı", "metrics listesi",
    "comparison.metric değerini içermelidir", "dimensions eksik", "uncovered koşul", "Qwen3.8-27B-FP8 modeli",
    "vLLM sunucusu", "LLM kapısı", "Temporal iş akışı", "TimesFM tahmini", "Power BI raporu", "SQL Server bağlantısı",
    "ITEMS.CODE -> new_kitapBase.new_stokkodu", "L_CAPIPERIOD dönemleri", "SPECODE2 satış kanalı",
    "net_sales ve invoice_amount", "lookback_days ile", "CreatedOn alanı", "created_at UTC kart oluşturma tarihi",
    "SIGN=1 alacak hareketleri", "COUNT_BIG(*)", "PostgreSQL kaydı",
]


@pytest.mark.parametrize("text", TECHNICAL)
def test_known_technical_terms_do_not_reach_the_screen(text):
    out = public_text(text)
    assert not leaks(out), (text, out, leaks(out))
    assert out.strip()


@pytest.mark.parametrize("text", [
    "Soruda dönem belirtilmediği için 2026 yılbaşından bugüne (01.01.2026–01.10.2026) hesaplandı.",
    "Yazar kırılımı kitap künyesindeki metindir; kişi kimliği veya telif sahipliği değildir.",
    "3 satış kırılımında aktif CRM kitap eşleşmesi yok; künye alanları boş bırakıldı, satışlar korunuyor.",
    "T.C. Milli Eğitim Bakanlığı için 1.250.000,50 TL; Logo ve CRM kayıtları ayrı okundu.",
    "Satış tutarıyla fatura genel toplamını mı, iskonto sonrası KDV hariç satış satırı toplamını mı istiyorsunuz?",
])
def test_business_sentences_are_kept(text):
    assert public_text(text) == text


def test_metric_definitions_are_shown_in_business_language():
    for key, metric in METRICS.items():
        assert key in presentation.PUBLIC_DEFINITIONS, f"{key}: ekrandaki iş dili tanımı yazılmalı"
        out = presentation.public_definition(key)
        assert not leaks(out) and not re.search(r"\b\d+/\d+\b|\(\d+(?:,\d+)+\)", out), (key, out)
        assert not leaks(public_text(metric.definition)), (metric.definition, public_text(metric.definition))


def _literal_messages():
    """ContractError(...) çağrılarının ilk argümanındaki sabit metin parçaları ve kodları."""
    found = []
    for path in sorted(PACKAGE.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and getattr(node.func, "id", None) in ("ContractError", "unmet_error") and node.args:
                code = next((k.value.value for k in node.keywords if k.arg == "code" and isinstance(k.value, ast.Constant)),
                            "PLAN_INVALID" if node.func.id == "unmet_error" else "UNSUPPORTED_CAPABILITY")
                parts = [n.value for n in ast.walk(node.args[0]) if isinstance(n, ast.Constant) and isinstance(n.value, str)]
                if parts:
                    found.append((path.name, " ".join(parts), code))
    return found


MESSAGES = _literal_messages()


def test_message_scan_finds_the_package_messages():
    assert len(MESSAGES) > 100


@pytest.mark.parametrize("source, message, code", MESSAGES, ids=[f"{m[0]}:{i}" for i, m in enumerate(MESSAGES)])
def test_fixed_messages_reach_the_screen_without_technical_names(source, message, code):
    shown = public_error(ContractError(message, code=code))
    assert shown.strip()
    assert not leaks(shown), (source, message, shown, leaks(shown))


def test_comparison_shape_messages_stay_internal():
    for data in ({"comparison": {"metric": "net_sales"}, "derived": [{"id": "x"}]},
                 {"comparison": {"metric": "net_sales"}, "metrics": ["net_sales", "return_amount"]}):
        internal = comparison_shape_error(data)
        if internal:
            shown = public_error(ContractError(internal, code="PLAN_INVALID"))
            assert shown == presentation.PLAN_REJECTED


def test_unmet_conditions_are_listed_in_business_language():
    err = unmet_error("Sorunun bütün koşulları plana taşınamadı: ",
                      ["toptan süzgeci (TRCODE 8) plana yok", "metrics içinde return_amount eksik"])
    assert "TRCODE" in str(err)                       # iç ileti onarım turu için teknik kalır
    shown = public_error(err)
    assert "toptan süzgeci" in shown and not leaks(shown)


def test_model_written_uncovered_is_filtered():
    err = unmet_error("Bu kapsam için doğrulanmış hesap tanımı eksik: ", ["Brüt kâr için OUTCOST ve LINENET maliyet tanımı yok"],
                      code="UNSUPPORTED_CAPABILITY")
    shown = public_error(err)
    assert shown.startswith("Bu soru için henüz doğrulanmış bir hesap tanımı yok") and not leaks(shown)


def test_response_filter_keeps_records_sql_and_semantic():
    resp = {"type": "TEXT_TO_SQL", "summary": "1 satır.", "sql": "SELECT SUM(f.LINENET) FROM LG_211_01_STLINE f",
            "records": [{"book_name": "SQL ile Veri Analizi", "net_sales": 1.0}],
            "semantic": {"plan": {"metrics": ["net_sales"]}},
            "dataNotes": [{"message": "LINENET toplamı", "severity": "info"}],
            "definitions": ["SUM(f.NETTOTAL)"], "gaps": [{"status": "X", "reason": "crm_report dalı eksik"}],
            "columns": [{"name": "kitap_sayisi", "label": "kitap_sayisi"}, {"name": "net_sales", "label": "Net satış tutarı",
                         "definition": "TRCODE IN (2,3) iade"}],
            "sections": [{"title": "Bölüm", "explanation": "statecode=0", "dataNotes": [{"message": "new_yazartext"}]}]}
    out = public_response(resp)
    assert out["sql"] == resp["sql"] and out["records"] == resp["records"] and out["semantic"] == resp["semantic"]
    shown = [out["dataNotes"][0]["message"], *out["definitions"], out["gaps"][0]["reason"], out["columns"][0]["label"],
             out["columns"][1]["definition"], out["sections"][0]["explanation"], out["sections"][0]["dataNotes"][0]["message"]]
    assert all(not leaks(s) for s in shown), shown
    assert out["columns"][0]["label"] == "Kitap sayisi"


def test_fixed_user_messages_in_the_answer_flow_are_clean():
    source = (PACKAGE / "__init__.py").read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and any(getattr(t, "id", None) == "message" for t in node.targets):
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                assert not leaks(node.value.value), node.value.value
                assert "Finans" not in node.value.value.split()[0]
