import json
import re
from pathlib import Path

import pytest

from semantic_bridge import chat_scope
from semantic_bridge.chat_scope import BI_INTRO, BI_REDIRECT, classify, is_intro


class Never:
    def chat(self, *args, **kwargs):
        raise AssertionError("unnecessary model call")


class Scripted:
    """Sınıflandırıcının yerine: istemi denetler, verilen cevabı döndürür."""

    def __init__(self, reply):
        self.reply = reply
        self.messages = None

    def chat(self, messages, **kwargs):
        self.messages = messages
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply)


# ------------------------------------------------------------------ eski davranış (korunur)
@pytest.mark.parametrize("question", ["test", "şişt", "Sen kimsin?", "Merhaba!", "..."])
def test_intro_does_not_call_model(question):
    assert is_intro(question, Never())


@pytest.mark.parametrize("question", ["test müşterisinin cirosu", "2026", "sadece Ankara", "bilinmeyen iş terimine göre rapor"])
def test_unknown_data_is_not_rejected_without_classifier(question):
    assert not is_intro(question)


@pytest.mark.parametrize("reply, expected", [('{{bad', False), ('{"intent":"UNKNOWN"}', False), ('{"intent":"DATA"}', False), ('{"intent":"INTRO"}', True)])
def test_classifier_contract(reply, expected):
    class Model:
        def chat(self, messages, **kwargs):
            assert 'hasDataContext' in messages[-1]['content']
            return reply
    assert is_intro('örnek mesaj', Model(), has_context=True) is expected


# ------------------------------------------------------------------ kimlik / model: modelsiz ret
IDENTITY_QUESTIONS = [
    "Sen kimsin?", "KİMSİN", "Adın ne?", "Senin adın ne?", "Hangi modelsin?", "Modelin adı ne?",
    "Modelin ne?", "Hangi modeli kullanıyorsun?", "Hangi modelle çalışıyorsun?", "Kullandığın model ne?",
    "Arkada hangi model var?", "Seni kim geliştirdi?", "Seni hangi şirket yaptı?", "Kim geliştirdi?",
    "Sen bir yapay zekâ mısın?", "ChatGPT misin?", "Qwen mi kullanıyorsun?", "GPT-4 müsün sen?",
    "Neler yapabilirsin?", "Ne işe yarıyorsun?", "Nasılsın?", "Kaç yaşındasın?", "Tanışalım mı?",
    "Merhaba Zeki", "İyi günler", "selam ai",
]


@pytest.mark.parametrize("question", IDENTITY_QUESTIONS)
def test_identity_questions_get_fixed_intro_without_model(question):
    scope = classify(question, Never())
    assert scope.intent == chat_scope.IDENTITY
    assert scope.is_intro and scope.answer_type == "MODULE_INTRO"
    assert scope.reply == BI_INTRO


def test_intro_text_is_the_new_scope_sentence():
    assert BI_INTRO == "Ben Zeki AI; şirketinizin verileri ve modülleri hakkındaki sorulara cevap verebilirim."
    assert "finansal" not in BI_INTRO


# ------------------------------------------------------------------ modül soruları: DATA
# docs/analiz/kullanici-ihtiyaclari/*.md, 5. bölüm «Zeki AI'ya soracakları örnek sorular»; her bloktan.
# Üçüncü alan: sınıflandırıcının koyması beklenen konu (chat_topics.json).
MODULE_QUESTIONS = [
    # Finans ve yönetim (DYK, M45, M47)
    ("DYK", "Net ciro geçen yılın aynı dönemine göre ne kadar arttı, iade ve iskonto hesaba katıldığında?", "finans"),
    ("DYK", "Geçen toplantıdan bu yana gecikmiş kurul aksiyonları?", "yonetim"),
    ("M45", "Ağustos gelir tablosunu geçen yılın ağustosuyla karşılaştır, brüt kâr neden düştü?", "finans"),
    ("M45", "Önümüzdeki 13 haftada nakit açığı veren hafta var mı, en büyük çıkış kalemi ne?", "finans"),
    ("M47", "Sahibi olmayan ya da 90 günden uzun süredir gözden geçirilmemiş riskler?", "risk"),
    ("M47", "Önümüzdeki 60 günde biten sigorta poliçeleri?", "risk"),
    # Pazarlama planlama (M15–M19, M24, M53)
    ("M15", "Ekim'de yayımlanacak çocuk kitaplarının toplam pazarlama bütçesi ve hedef cirosu ne?", "pazarlama"),
    ("M18", "Geçen ay planlanan sosyal medya işlerinin kaçı yapıldı?", "pazarlama"),
    ("M19", "Bu kitap için Instagram'a üç açıklama yaz, kitaptan birebir bir alıntı kullan, 5 hashtag öner.", "pazarlama"),
    ("M24", "Son üç bültenin açılma ve tıklama oranı neydi?", "pazarlama"),
    ("M53", "Son 12 ayda en çok satan setler ve marjları?", "satis"),
    # Basın, sosyal medya, reklam (M20–M23)
    ("M20", "Geçen ay hangi kitaplarımız basında çıktı?", "basin"),
    ("M21", "Geçen ay reklam harcaması kanal bazında ne kadardı?", "dijital"),
    ("M22", "Son 30 günde en çok etkileşim alan paylaşım türü hangisi?", "dijital"),
    ("M23", "Bu ay hangi işbirliklerinde yayın tarihi geçti ama bağlantı girilmedi?", "dijital"),
    # Satış ve saha (M29–M33, M38, M59)
    ("M29", "D&R'a ilk dağılımda gönderdiğimiz adetin ne kadarı 90 günde iade geldi?", "satis"),
    ("M30", "Bu hafta vadesi 60 günü geçen müşterilerim kimler?", "satis"),
    ("M31", "Üsküdar'da 1.000'den fazla öğrencisi olan ve hiç ziyaret etmediğimiz ortaokullar hangileri?", "kurumsal"),
    ("M32", "Hangi bayiler 60 gündür sipariş vermedi?", "satis"),
    ("M33", "Geçen yıl kaç ihaleye girdik, kaçını kazandık?", "kurumsal"),
    ("M59", "Son 3 ayda iade oranı %20'yi geçen bayiler?", "satis"),
    # E-ticaret ve pazar yerleri (H3, M34, M35, M40–M42)
    ("H3", "Dün sitede kaç sipariş geldi, geçen haftanın aynı gününe göre ne değişti?", "eticaret"),
    ("M34", "Sitede aktif olup Logo'da stoğu sıfır olan kaç kitap var?", "eticaret"),
    ("M34", "Geçen ay en çok görüntülenip hiç satmayan 20 kitap hangileri?", "eticaret"),
    ("M40", "Trendyol'da geçen hafta en çok iade edilen 10 kitap ve iade nedenleri?", "eticaret"),
    ("M42", "Hepsiburada'nın iade oranı son 6 ayda nasıl?", "eticaret"),
    # Depo, lojistik, tedarik (M43, M44, M52)
    ("M43", "Önümüzdeki 30 günde stoğu bitecek çocuk kitapları hangileri?", "stok"),
    ("M44", "Geçen ay Aras ile MNG'nin desi başı maliyeti ne?", "lojistik"),
    ("M44", "Tahsilatlı kargoda bekleyen tutar ne kadar?", "lojistik"),
    ("M52", "Ekim'de hangi matbaaya kaç kitap basılacak?", "tedarik"),
    # Yayın, katalog, telif (H1, M36, M54)
    ("H1", "Tasavvuf kategorisinde kaç kitabımız var, kaçı satışta?", "yayin"),
    ("M36", "Sesli kitap hakkı olan çocuk kitaplarımız hangileri?", "yayin"),
    ("M54", "Kazanılmamış avansı en yüksek 20 sözleşme hangileri?", "telif"),
    # Editoryal süreç ve üretim (M1–M4, M8, M12) — 2026-09-28'de ayrı konu oldu
    ("M1", "Hangi başvurular 30 günden fazladır değerlendirmede?", "editoryal"),
    ("M4", "Terminine bir haftadan az kalan çeviri işleri hangileri?", "editoryal"),
    # Okur, müşteri hizmetleri, kurumsal e-posta (H2, H4, M37, M51)
    ("H2", "E-posta izni olan kaç okurumuz var, geçen aya göre değişim ne?", "okur"),
    ("M37", "Fuardan gelen okur kayıtlarının kaçında KVKK onayı var?", "okur"),
    ("M51", "SLA'sı bugün dolacak kaç talep var, kimde?", "destek"),
    ("H4", "48 saati geçen ve hâlâ cevapsız iletiler kimde?", "destek"),
    # İnsan kaynakları (M55–M58)
    ("M55", "Editörya'daki açık pozisyona bu ay kaç başvuru geldi, kaçı ön elemeyi geçti?", "ik"),
    ("M55", "Satış temsilcisi mülakatı için davranışsal soru seti öner.", "ik"),
    ("M56", "Ekibimde bu çeyrek check-in yapmayan kim var?", "ik"),
    ("M57", "Önümüzdeki iki ayda iş güvenliği eğitimi dolacak kaç kişi var, hangi birimlerde?", "ik"),
    ("M58", "Bu çeyrek eNPS kaç, geçen çeyreğe göre ne değişti?", "ik"),
    # Pazar araştırması, sistem ve Zeki AI işletimi (M39, M48, M50) — «model», «Zeki AI» geçse de şirket sorusu
    ("M39", "Rakip yayınevlerinde 200–300 sayfalık kişisel gelişim kitaplarının ortalama fiyatı ne?", "pazar"),
    ("M48", "Dün gece planlı raporlardan hangileri gitmedi, neden?", "isletim"),
    ("M48", "Bu hafta Zeki AI'ın ortalama cevap süresi geçen haftaya göre nasıl?", "isletim"),
    ("M48", "Model kuyruğunda en çok bekleyen modül hangisi?", "isletim"),
    ("M50", "Model değişikliğinden sonra ortalama cevap süresi ne oldu?", "isletim"),
]


def test_module_questions_cover_every_block():
    assert len(MODULE_QUESTIONS) >= 30
    used = {t for _, _, t in MODULE_QUESTIONS}
    assert used == {t["id"] for t in chat_scope.topics()}, "her konudan en az bir soru"


@pytest.mark.parametrize("module, question, expected_topic", MODULE_QUESTIONS)
def test_module_question_is_never_rejected_without_model(module, question, expected_topic):
    scope = classify(question)
    assert scope.intent == chat_scope.DATA
    assert not scope.is_intro and scope.reply is None
    assert not is_intro(question)


@pytest.mark.parametrize("module, question, expected_topic", MODULE_QUESTIONS)
def test_module_question_goes_to_data_or_honest_no_data(module, question, expected_topic):
    model = Scripted({"intent": "DATA", "topic": expected_topic})
    connected = chat_scope.connected_topic_ids("")
    scope = classify(question, model, connected=connected)
    system, user = model.messages[0]["content"], json.loads(model.messages[-1]["content"])
    assert user["message"] == question
    assert all(f"- {t['id']}:" in system for t in chat_scope.topics())
    assert scope.intent == chat_scope.DATA and not scope.is_intro
    assert scope.topic["id"] == expected_topic
    if expected_topic in connected:
        assert scope.reply is None and scope.answer_type is None       # veri hattına gider (Logo/CRM ya da portal)
    elif scope.topic.get("closed"):
        assert scope.not_connected and scope.answer_type == "DATA_UNAVAILABLE"
        assert scope.reply == scope.topic["closed"]                     # İK: bilerek kapalı, kendi metni
    else:
        assert scope.not_connected and scope.answer_type == "DATA_UNAVAILABLE"
        assert scope.reply.startswith("Bu konuda henüz veri bağlı değil")
        assert scope.topic["label"] in scope.reply


# ------------------------------------------------------------------ şirket dışı sohbet: kibar yönlendirme
OFFTOPIC_QUESTIONS = ["Bugün hava nasıl?", "Bana bir fıkra anlat", "Galatasaray maçı kaç kaç bitti?",
                      "Mercimek çorbası tarifi ver", "Türkiye'nin başkenti neresi?", "Bana bir aşk şiiri yaz"]


@pytest.mark.parametrize("question", OFFTOPIC_QUESTIONS)
def test_offtopic_is_redirected_politely(question):
    scope = classify(question, Scripted({"intent": "OFFTOPIC", "topic": "none"}))
    assert scope.intent == chat_scope.OFFTOPIC and scope.is_intro
    assert scope.answer_type == "MODULE_INTRO"
    assert scope.reply == BI_REDIRECT and scope.reply.startswith(BI_INTRO)
    assert is_intro(question, Scripted('{"intent":"OFFTOPIC","topic":"none"}'))


def test_offtopic_never_carries_a_topic():
    scope = classify("Bugün hava nasıl?", Scripted({"intent": "OFFTOPIC", "topic": "ik"}), connected=())
    assert scope.topic is None and not scope.not_connected and scope.reply == BI_REDIRECT


# ------------------------------------------------------------------ sağlamlık
def test_greeting_with_a_data_question_is_data():
    assert classify("Merhaba, 2026 net ciro ne kadar?").intent == chat_scope.DATA


@pytest.mark.parametrize("reply", ['```json\n{"intent":"DATA","topic":"ik"}\n```', 'Cevap: {"intent": "DATA", "topic": "ik"}'])
def test_classifier_reply_wrapped_in_text_is_read(reply):
    scope = classify("Bu çeyrek eNPS kaç?", Scripted(reply), connected=())
    assert scope.topic["id"] == "ik" and scope.not_connected


@pytest.mark.parametrize("reply", ['{"intent":"DATA","topic":"uydurma"}', '{"intent":"DATA","topic":"none"}',
                                   '{"intent":"DATA"}', '{"intent":"BELKI"}', '', 'null', '[1, 2]'])
def test_unknown_topic_or_intent_keeps_the_data_pipeline(reply):
    scope = classify("Bu kitabın durumu ne?", Scripted(reply), connected=())
    assert scope.intent in (chat_scope.DATA, chat_scope.UNKNOWN)
    assert scope.topic is None and scope.reply is None


def test_classifier_failure_keeps_the_data_pipeline():
    class Broken:
        def chat(self, *args, **kwargs):
            raise TimeoutError("kuyruk dolu")
    assert classify("Bu çeyrek eNPS kaç?", Broken()).intent == chat_scope.DATA


def test_unknown_intent_in_unconnected_topic_is_answered_honestly():
    scope = classify("çeyrek puanı", Scripted({"intent": "UNKNOWN", "topic": "ik"}), connected={"finans"})
    assert scope.not_connected and scope.answer_type == "DATA_UNAVAILABLE"


# ------------------------------------------------------------------ konu listesi ve ayar
def test_topics_registry_is_well_formed():
    raw = json.loads(chat_scope.TOPICS_FILE.read_text(encoding="utf-8"))
    ids = [t["id"] for t in raw["topics"]]
    assert len(ids) == len(set(ids))
    domains = json.loads(Path(chat_scope.__file__).with_name("data_domains.json").read_text(encoding="utf-8"))
    known = {d["id"] for d in domains["domains"]}
    for t in raw["topics"]:
        assert re.fullmatch(r"[a-z]+", t["id"])
        assert t["label"] and t["hint"] and t["modules"]
        assert set(t["data"]) <= known, t["id"]


def test_connected_topics_default_and_override():
    default = chat_scope.connected_topic_ids("")
    assert default == {t["id"] for t in chat_scope.topics() if (t["data"] or t.get("portal")) and not t.get("closed")}
    assert {"finans", "satis", "stok"} <= default and "ik" not in default
    # 2026-09-28: modül verisi portal veri alanlarıyla bağlı (chat_portal)
    assert {"pazarlama", "dijital", "eticaret", "okur", "destek", "risk", "yonetim", "isletim", "editoryal"} <= default
    assert chat_scope.connected_topic_ids(" risk , Finans, uydurma ") == {"risk", "finans"}
    # İK bilerek kapalı: ayarla da bağlanmaz
    assert chat_scope.connected_topic_ids(" ik , Finans ") == {"finans"}


def test_connected_topics_read_from_settings(monkeypatch):
    monkeypatch.setattr(chat_scope, "_conf", lambda key: "finans" if key == "CHAT_CONNECTED_TOPICS" else "")
    scope = classify("Önümüzdeki 60 günde biten sigorta poliçeleri?", Scripted({"intent": "DATA", "topic": "risk"}))
    assert scope.not_connected and scope.reply.startswith("Bu konuda henüz veri bağlı değil")
    monkeypatch.setattr(chat_scope, "_conf", lambda key: "risk" if key == "CHAT_CONNECTED_TOPICS" else "")
    scope = classify("Önümüzdeki 60 günde biten sigorta poliçeleri?", Scripted({"intent": "DATA", "topic": "risk"}))
    assert not scope.not_connected and scope.reply is None


def test_hr_topic_is_closed_with_its_own_reply(monkeypatch):
    monkeypatch.setattr(chat_scope, "_conf", lambda key: "")
    ik = chat_scope.topic("ik")
    assert ik["closed"] and not ik["data"] and not ik.get("portal")
    scope = classify("Bu çeyrek eNPS kaç?", Scripted({"intent": "DATA", "topic": "ik"}))
    assert scope.not_connected and scope.answer_type == "DATA_UNAVAILABLE" and scope.reply == ik["closed"]
    assert "kişisel veri" in scope.reply


# ------------------------------------------------------------------ ekrana giden metinde teknoloji adı yok
_TECH = re.compile(r"qwen|vllm|nvidia|gpt|llama|openai|anthropic|claude|gemini|mistral|temporal|timesfm|llm|sql",
                   re.IGNORECASE)


def test_replies_carry_no_technology_names():
    texts = [BI_INTRO, BI_REDIRECT] + [chat_scope.not_connected_reply(t) for t in chat_scope.topics()]
    for text in texts:
        assert not _TECH.search(text), text


def test_weak_placements_are_not_business_evidence():
    """2026-09-28 kabulü: şirket dışı sorular tek bir zayıf yerleşimle sınıflandırıcıyı atlıyordu. Örnekler canlı çözücünün
    o gün verdiği yerleşimler; kanıt yalnız sertifikalı (ya da açık) kavram, varsayılan filtre sayılmaz."""
    from semantic_layer.models import Mapping, ResolvedSlot

    def slot(term, stype, status):
        return ResolvedSlot(term=term, semantic_type=stype, status=status, mapping=Mapping(concept_id="c", entity="E", table_pattern="E"))

    tarif = [slot("tarifi", "COLUMN", "INFERRED")]                       # «Mercimek çorbası tarifi ver»
    turkiye = [slot("TÜRKİYE", "DIMENSION_VALUE", "PROFILE")]            # «Türkiye'nin başkenti neresi?»
    ask = [slot("ask", "COLUMN", "INFERRED")]                            # «Bana bir aşk şiiri yaz»
    only_filter = [slot("stline default cancelled", "DEFAULT_FILTER", "CERTIFIED")]
    satan = [slot("kitap", "COLUMN", "CERTIFIED"), slot("satan", "METRIC", "INFERRED"),
             slot("stline default cancelled", "DEFAULT_FILTER", "CERTIFIED")]   # «Bu ay en çok satan 10 kitap hangisi?»
    iade = [slot("iade orani", "METRIC", "CERTIFIED")]
    for weak in (tarif, turkiye, ask, only_filter, []):
        assert not chat_scope.has_business_evidence(weak)
    for strong in (satan, iade, [slot("x", "COLUMN", "explicit")]):
        assert chat_scope.has_business_evidence(strong)
    assert not chat_scope.has_business_evidence([ResolvedSlot(term="y", semantic_type="METRIC", status="CERTIFIED")])  # yerleşmemiş
