"""Finans sohbetinin konuşma katmanı (2026-10-01).

* Netleştirme sonrası bağlam: «Net satış ne kadar?» → netleştirme → «Bu yıl» özgün soruyla birleşip planlanır.
* Bağlam süreç belleğinde değil sorgu kaydında: yeniden başlatma / başka işçi aynı bağlamı görür; başka kişi göremez.
* Takip sözcükleri: «bunun aylık kırılımı», «ya geçen yıl?» takip; «önceki ayın net satışı», «bu yıl» takip değil.
"""
from types import SimpleNamespace

import pytest

import semantic_bridge.finance_query as fq
from semantic_bridge.finance_query import conversation
from semantic_bridge.finance_query.contracts import ContractError
from semantic_bridge.finance_query.planner import Plan, follows
from semantic_layer.store.catalog_store import open_store


# ------------------------------------------------------------------------------------------- follows
@pytest.mark.parametrize("question", [
    "Peki geçen yıl?", "Ya geçen yıl?", "ya toptan?", "Bunun aylık kırılımı", "Bunu kanal bazında göster",
    "Aynısını geçen yıl için", "aynı şekilde 2025 için", "Bunlardan ilk 5'i", "bu sonucu müşteri bazında ver",
    "Bu tabloyu yıl bazında", "Bir de iadeleri göster", "geçen yıl için de", "iadeleri de ekle",
    "önceki sonucu kanala göre böl", "az önceki tabloyu sırala", "Yukarıdaki listede en çok satan hangisi?",
    "bu kitapların stoğu ne kadar?", "onların toplamı", "şunları da göster",
])
def test_follow_up_questions_are_recognised(question):
    assert follows(question)


@pytest.mark.parametrize("question", [
    "Önceki ayın net satışı", "bir önceki çeyrek net satış", "Bu yıl net satış ne kadar?", "bu ay en çok satan kitaplar",
    "Bu yılın ilk 8 ayı net satış", "geçen yılın aynı dönemine göre net satış", "bu hafta kaç fatura kesildi",
    "Net satış ne kadar?", "Yayınevi bazında net satış", "2025 toptan fatura sayısı", "Bu çeyrekte iade tutarı",
    "Onlarca kitabın stoğu", "Ocak ayında kaç fatura kesildi?", "bu dönem net ciro",
])
def test_period_phrases_are_not_follow_ups(question):
    assert not follows(question)


# ------------------------------------------------------------------------------- netleştirme cevabı mı
SALES_AMOUNT_CLAR = ("Satış tutarıyla fatura genel toplamını mı, iskonto sonrası KDV hariç satış satırı toplamını mı "
                     "istiyorsunuz?")


@pytest.mark.parametrize("reply, clarification, original", [
    ("Bu yıl", "Hangi dönem?", "Net satış ne kadar?"),
    ("bu yıl için ver", "Hangi dönem?", "Net satış ne kadar?"),
    ("2025", "Hangi dönem?", "Net satış ne kadar?"),
    ("geçen yılın ilk 8 ayı", "Hangi dönem?", "Net satış ne kadar?"),
    ("fatura genel toplamını ver", SALES_AMOUNT_CLAR, "Satış tutarı ne kadar?"),
    ("KDV hariç satır toplamı", SALES_AMOUNT_CLAR, "Satış tutarı ne kadar?"),
    ("sadece toptan", "Toptan mı perakende mi?", "Net satış ne kadar?"),
    ("aylık olsun", "Hangi kırılımda?", "2026 net satış"),
    ("net satış bu yıl", "Hangi dönem?", "Net satış ne kadar?"),
])
def test_short_reply_answers_the_clarification(reply, clarification, original):
    assert not conversation.is_standalone(reply, clarification, original)


@pytest.mark.parametrize("reply, clarification, original", [
    ("2025 iade tutarı kaç?", "Hangi dönem?", "Net satış ne kadar?"),
    ("Stokta en çok bekleyen kitaplar", "Hangi dönem?", "Net satış ne kadar?"),
    ("Aktif yazar sayısı kaç?", SALES_AMOUNT_CLAR, "Satış tutarı ne kadar?"),
    ("Müşteri bazında tahsilat listesi", "Hangi dönem?", "Net satış ne kadar?"),
])
def test_complete_new_question_is_not_glued_to_the_clarification(reply, clarification, original):
    assert conversation.is_standalone(reply, clarification, original)


# ------------------------------------------------------------------------------- uçtan uca (answer)
class FakeExecutor:
    def __init__(self, runtime):
        self.read_retries = 0
        self.source_periods = []
        self.runs = []
        self.output_fields = []
        self.numeric_fields = []
        self.gaps = []
        self.coverage_complete = True
        self.notes = ["Ölçü LINENET ve TRCODE IN (7,8,9) ile hesaplandı."]
        self.section_results = []

    def execute(self, plan):
        return [{"net_sales": 1234.5}]


def make_runtime(store):
    return SimpleNamespace(store=store, settings=SimpleNamespace(tenant_id="t", datasource_id="d"),
                           llm_for=lambda module: object(), attach_widget=lambda *a, **k: None,
                           remember_result=lambda *a, **k: None)


@pytest.fixture
def engine(monkeypatch):
    seen = []

    def fake_build(question, llm, previous=None, trace=None, **kw):
        seen.append({"question": question, "previous": previous})
        if "Net satış ne kadar?" == question.strip():
            raise ContractError("Hangi dönem?", code="NEEDS_CLARIFICATION")
        return Plan(("net_sales",), (), (("2026-01-01", "2026-10-02"),))

    monkeypatch.setattr(fq, "build", fake_build)
    monkeypatch.setattr(fq, "Executor", FakeExecutor)
    return seen


def ask(runtime, question, thread="th1", user="ali"):
    return fq.answer(runtime, question, thread, 50, True, lambda stage: None, user)


def test_clarification_answer_is_planned_with_the_original_question(engine):
    store = open_store("sqlite://")
    first = ask(make_runtime(store), "Net satış ne kadar?")
    assert first["type"] == "CLARIFICATION" and first["explanation"] == "Hangi dönem?"
    # Yeni süreç (yeniden başlatma / başka işçi): bağlam kayıttan okunur.
    second = ask(make_runtime(store), "Bu yıl")
    assert engine[-1]["question"] == "Net satış ne kadar? Bu yıl"
    assert second["type"] == "TEXT_TO_SQL"
    assert second["semantic"]["conversation"]["mode"] == conversation.CLARIFICATION_ANSWER
    assert second["semantic"]["effectiveQuestion"] == "Net satış ne kadar? Bu yıl"
    # Netleştirme cevaplandı: bir sonraki kısa mesaj artık o soruya eklenmez.
    ask(make_runtime(store), "2025")
    assert engine[-1]["question"] == "2025"


def test_other_users_thread_is_not_read(engine):
    store = open_store("sqlite://")
    ask(make_runtime(store), "Net satış ne kadar?", user="ali")
    ask(make_runtime(store), "Bu yıl", user="veli")
    assert engine[-1]["question"] == "Bu yıl"
    ask(make_runtime(store), "Bu yıl", user="ALI")      # AD adı büyük/küçük harf farkıyla gelebilir
    assert engine[-1]["question"] == "Net satış ne kadar? Bu yıl"


def test_standalone_reply_after_clarification_is_a_new_question(engine):
    store = open_store("sqlite://")
    ask(make_runtime(store), "Net satış ne kadar?")
    ask(make_runtime(store), "Stokta en çok bekleyen kitaplar hangileri?")
    assert engine[-1]["question"] == "Stokta en çok bekleyen kitaplar hangileri?"


def test_follow_up_gets_the_previous_plan_from_the_record(engine):
    store = open_store("sqlite://")
    ask(make_runtime(store), "2026 net satış")
    ask(make_runtime(store), "Bunun aylık kırılımı")
    previous = engine[-1]["previous"]
    assert previous and previous["question"] == "2026 net satış"
    assert previous["plan"]["metrics"] == ["net_sales"]
    ask(make_runtime(store), "Önceki ayın net satışı")
    assert engine[-1]["previous"] is None
    # Başka thread'de bağlam yok.
    ask(make_runtime(store), "Bunun aylık kırılımı", thread="th2")
    assert engine[-1]["previous"] is None


def test_previous_turn_is_the_shared_lookup(engine):
    store = open_store("sqlite://")
    rt = make_runtime(store)
    assert conversation.previous_turn(rt, "th1", "ali") is None
    ask(rt, "2026 net satış")
    got = conversation.previous_turn(rt, "th1", "ali")
    assert got["question"] == "2026 net satış" and got["plan"]["metrics"] == ["net_sales"] and got["queryId"]
    assert conversation.previous_turn(rt, "th1", "veli") is None


def test_answer_notes_reach_the_screen_without_technical_names(engine):
    store = open_store("sqlite://")
    got = ask(make_runtime(store), "2026 net satış")
    shown = " ".join(n["message"] for n in got["dataNotes"]) + got["summary"]
    assert "LINENET" not in shown and "TRCODE" not in shown
    # Teknik ayrıntı kayıtta (semantic durumu) kalır.
    row = store.list_query_log("t", "d", limit=1)["items"][0]
    full = store.get_query_log("t", "d", row["id"])
    assert "LINENET" in full["resolved"]["internalNotes"][0]


def test_store_is_unavailable_keeps_answering(engine):
    rt = make_runtime(SimpleNamespace(log_query=lambda *a, **k: "q1"))
    got = ask(rt, "2026 net satış")
    assert got["type"] == "TEXT_TO_SQL"


# ------------------------------------------------------------- «iadeleri de ekle» (iade kapsamı takibi)
def test_include_returns_follow_up_widens_the_previous_invoice_count(monkeypatch):
    """Kullanıcı kararı 2026-10-01: fatura sayısı iadesiz; «iadeleri de ekle» önceki planı modelsiz genişletir."""
    built, executed = [], []

    def fake_build(question, llm, previous=None, trace=None, **kw):
        built.append(question)
        return Plan(("invoice_count",), ("channel",), (("2026-09-01", "2026-10-01"),), limit=None, order_by="invoice_count")

    class CountingExecutor(FakeExecutor):
        def execute(self, plan):
            executed.append(plan)
            return [{"channel": "Toptan", **{m: 1 for m in plan.metrics}}]

    monkeypatch.setattr(fq, "build", fake_build)
    monkeypatch.setattr(fq, "Executor", CountingExecutor)
    store = open_store("sqlite://")
    ask(make_runtime(store), "Eylül 2026 kanal bazında fatura sayısı")
    got = ask(make_runtime(store), "iadeleri de ekle")
    assert built == ["Eylül 2026 kanal bazında fatura sayısı"]          # takipte model planı yok
    widened = executed[-1]
    assert widened.metrics[:3] == ("invoice_count", "return_invoice_count", "invoice_count_with_returns")
    assert widened.dimensions == ("channel",) and widened.periods == (("2026-09-01", "2026-10-01"),)
    assert got["type"] == "TEXT_TO_SQL"
    # Başka thread'de önceki fatura sayısı yok: tahmin değil netleştirme.
    other = ask(make_runtime(store), "iadeleri de ekle", thread="th9")
    assert other["type"] == "CLARIFICATION"
