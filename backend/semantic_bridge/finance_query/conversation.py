"""Finans sohbetinin konuşma bağlamı: netleştirme cevabı ve takip sorusu.

Bağlam süreç belleğinde değil sorgu kaydındadır (`sl_query_log`: thread_id, username, answer_type, resolved_json):
köprü yeniden başlasa ya da istek başka bir işçiye düşse de aynı konuşma aynı bağlamı görür. Kişi eşleşmesi kayıt
okumasında zorunludur (`CatalogStore.thread_turns`): başkasının thread kimliğini bilen biri onun bağlamını okuyamaz.

Üç durum:

* **Netleştirme cevabı** — thread'in son kaydı bu motorun netleştirme sorusuysa yeni mesaj o sorunun cevabıdır; özgün
  soru ile cevap birleştirilip planlanır. Cevap kendi başına yeni bir soruysa (`is_standalone`) yeni soru gibi işlenir.
* **Takip** — mesaj önceki cevaba açıkça gönderme yapıyorsa (`planner.follows`) son başarılı cevabın planı planlayıcıya
  bağlam olarak gider.
* **Yeni soru** — bağlam yok.

Ortak nokta `previous_turn` — thread'deki son başarılı finans cevabının `{"question", "plan", ...}` bağlamı. Takip
isteyen başka mekanizma (ör. «iadeleri de ekle») önceki planı buradan alır, kendi önbelleğini tutmaz.
"""
from __future__ import annotations

from dataclasses import dataclass
import logging
import re
from typing import Any, Optional

from .language import fold
from .planner import follows

log = logging.getLogger(__name__)

ENGINE = "finance_contract_v1"
ANSWERED_TYPES = ("TEXT_TO_SQL", "PARTIAL_ANSWER")
NEW, FOLLOWUP, CLARIFICATION_ANSWER = "new", "followup", "clarification_answer"


@dataclass(frozen=True)
class Turn:
    """Sorgu kaydındaki bir tur."""
    query_id: str
    question: str
    answer_type: Optional[str]
    summary: Optional[str]
    compiler: Optional[str]
    resolved: dict

    @classmethod
    def from_row(cls, row: Optional[dict]) -> Optional["Turn"]:
        if not row:
            return None
        resolved = row.get("resolved") if isinstance(row.get("resolved"), dict) else {}
        return cls(str(row.get("id") or ""), str(row.get("question") or ""), row.get("answer_type"),
                   row.get("answer_summary"), row.get("compiler"), resolved)

    @property
    def effective_question(self) -> str:
        """Planlanan soru: netleştirme cevabıyla birleşmişse birleşik hâli."""
        return str(self.resolved.get("effectiveQuestion") or self.question)

    @property
    def plan(self) -> Optional[dict]:
        plan = self.resolved.get("plan")
        return plan if isinstance(plan, dict) else None

    @property
    def awaiting_answer(self) -> bool:
        """Bu motorun kullanıcıya sorduğu netleştirme sorusu, cevap bekliyor."""
        return self.compiler == ENGINE and self.answer_type == "CLARIFICATION" and bool(self.resolved.get("awaitingAnswer"))

    def as_previous(self) -> dict[str, Any]:
        """Planlayıcının `previous` bağlamı."""
        return {"question": self.effective_question, "plan": self.plan, "queryId": self.query_id,
                "answerType": self.answer_type}


def thread_turns(runtime, thread_id: Optional[str], username: Optional[str]) -> tuple[Optional[Turn], Optional[Turn]]:
    """(thread'in son kaydı, son başarılı finans cevabı). Kayıt okunamazsa bağlamsız devam edilir."""
    store = getattr(runtime, "store", None)
    read = getattr(store, "thread_turns", None)
    if not thread_id or not callable(read):
        return None, None
    try:
        got = read(runtime.settings.tenant_id, runtime.settings.datasource_id, thread_id, username,
                   answered_compiler=ENGINE, answered_types=ANSWERED_TYPES)
    except Exception:  # noqa: BLE001 — bağlam okunamadı diye soru reddedilmez
        log.warning("finance thread context unavailable", exc_info=True)
        return None, None
    return Turn.from_row(got.get("last")), Turn.from_row(got.get("answered"))


def previous_turn(runtime, thread_id: Optional[str], username: Optional[str]) -> Optional[dict[str, Any]]:
    """Ortak arayüz: thread'deki son başarılı finans cevabının bağlamı (`question`, `plan`, `queryId`, `answerType`)
    ya da None. Yalnız aynı kişinin kaydı okunur."""
    _, answered = thread_turns(runtime, thread_id, username)
    return answered.as_previous() if answered and answered.plan else None


# ------------------------------------------------------------------------------- netleştirme cevabı mı, yeni soru mu
#: Cevabın kendi içeriğini saymazken atılan sözcükler: bağlaç/zamir, soru/istek sözcükleri, dönem ve kırılım sözcükleri.
#: Bunlar bir netleştirme cevabının tipik parçalarıdır («bu yıl için ver», «aylık», «sadece toptan olsun»); yeni bir
#: sorunun konusunu taşımazlar.
_FUNCTION = set("""
bu su o ve veya ya ile icin de da mi mu ne en cok az daha gibi olarak olan sadece yalniz yalnizca tum tumu hepsi her
bir ama ise ki lutfen evet hayir tamam olsun olur istiyorum isterim ayni sekilde kadar gore bazinda bazli dahil haric
ver verir goster gosterir getir getirir listele listeler hesapla hesaplar sirala siralar bul say yaz cikar ozetle
kac kaci nedir neler nelerdir hangi hangisi hangileri kim kimler nasil neden niye misin musun misiniz musunuz midir mudur
yil yili yilin yillik sene senesi ay ayi ayin aylik hafta haftasi haftalik gun gunu gunluk ceyrek ceyregi ceyreklik
donem donemi donemin yariyil gecen onceki sonraki son ilk sonu basi baslangic itibaren beri arasi arasinda bugun dun
yarin ocak subat mart nisan mayis haziran temmuz agustos eylul ekim kasim aralik kirilim kirilimi kirilimli dagilim
dagilimi toplam
""".split())
_STEM = 5


def _content(text: str) -> list[str]:
    words = re.findall(r"[a-z]+", fold(text))
    return [w for w in words if len(w) >= 3 and w not in _FUNCTION]


def is_standalone(reply: str, clarification: str, original: str) -> bool:
    """Netleştirme sorusunun ardından gelen mesaj kendi başına yeni bir soru mu?

    Genel kural: mesajın netleştirme sorusunda ve özgün soruda geçmeyen en az iki içerik sözcüğü varsa yeni bir konu
    getirmiştir (yeni soru); yoksa netleştirmenin cevabıdır. Dönem, kırılım, istek ve bağlaç sözcükleri içerik sayılmaz;
    sözcükler Türkçe ekleri tolere etmek için ilk beş harfiyle karşılaştırılır. «Bu yıl», «fatura genel toplamını ver»,
    «sadece toptan» cevaptır; «Stokta en çok bekleyen kitaplar» yeni sorudur."""
    known = {w[:_STEM] for w in _content(clarification) + _content(original)}
    new = {w[:_STEM] for w in _content(reply)} - known
    return len(new) >= 2


@dataclass(frozen=True)
class Context:
    """Bir mesajın planlanacak hâli ve bağlamı."""
    question: str                       # planlanacak soru (netleştirme cevabıyla birleşmiş olabilir)
    previous: Optional[dict] = None     # planlayıcıya giden önceki cevap bağlamı (yalnız takipte)
    mode: str = NEW
    answered_clarification: Optional[str] = None   # cevaplanan netleştirme kaydının kimliği
    has_history: bool = False           # thread'de bu kişinin başarılı bir finans cevabı var

    def to_state(self) -> dict[str, Any]:
        out = {"mode": self.mode, "hasHistory": self.has_history}
        if self.previous:
            out["previousQueryId"] = self.previous.get("queryId")
        if self.answered_clarification:
            out["answeredClarificationId"] = self.answered_clarification
        return out


def resolve(runtime, question: str, thread_id: Optional[str], username: Optional[str]) -> Context:
    """Mesajın bağlamını sorgu kaydından kurar."""
    last, answered = thread_turns(runtime, thread_id, username)
    has_history = bool(answered and answered.plan)
    if last is not None and last.awaiting_answer:
        original = last.effective_question
        if not is_standalone(question, last.summary or "", original):
            combined = f"{original.rstrip()} {question.strip()}"
            previous = answered.as_previous() if has_history and follows(combined) else None
            return Context(combined, previous, CLARIFICATION_ANSWER, last.query_id, has_history)
    if has_history and follows(question):
        return Context(question, answered.as_previous(), FOLLOWUP, None, has_history)
    return Context(question, None, NEW, None, has_history)
