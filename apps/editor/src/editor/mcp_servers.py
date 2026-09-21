"""Hermes MCP servers (NIHAI-KARAR.md §4), one Streamable HTTP app each:

  /document/mcp   book_document_mcp
  /vision/mcp     book_vision_mcp
  /knowledge/mcp  book_knowledge_mcp
  /retrieval/mcp  book_retrieval_mcp
  /quality/mcp    book_quality_mcp
  /jobs/mcp       book_jobs_mcp  (job_id + read-only views; see UYGULAMA-NOTLARI.md)

Only high-level tools. No SQL, no file paths outside the inbox, no model
switching, no write without evidence, no canon writes (canon changes only
through an editor decision, which is not a Hermes tool).
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from typing import Annotated, Any

import uvicorn
from mcp.server import MCPServer
from mcp.server.transport_security import TransportSecuritySettings
from pydantic import Field
from starlette.applications import Starlette
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, Response
from starlette.routing import Mount, Route

from . import catalog, chat_reads, db, document, jobs, knowledge, quality, retrieval, vision

KEY = os.environ.get("EDITOR_MCP_KEY", "")
Gen = Annotated[str, Field(description="generation_id (get_job_status ya da latest_generation verir)")]
Page = Annotated[int, Field(ge=1, description="1'den başlayan PDF sayfa numarası")]
Evidence = Annotated[list[dict[str, Any]], Field(
    description="Kanıt listesi: [{page, paragraph, quote}]. quote sayfa metninden KELİMESİ KELİMESİNE; "
                "yalnız görsel kanıtta paragraph=0.")]


def _t(fn, *a, **kw):
    return asyncio.to_thread(fn, *a, **kw)


# ------------------------------------------------------------ document
document_mcp = MCPServer("book_document_mcp", instructions=(
    "Kitap alma ve sayfa verisi. Dosyalar yalnız inbox klasöründen okunur."))


@document_mcp.tool()
async def list_inbox() -> list[dict]:
    """Inbox'taki analiz edilebilir PDF dosyaları."""
    return await _t(document.list_inbox)


@document_mcp.tool()
async def inspect_book(file_name: str, title: str | None = None, universe: str | None = None,
                       age_group: str | None = None) -> dict:
    """Kitabı ve içerik sürümünü (dosyanın sha256'sı) oluşturur ya da bulur."""
    return await _t(document.inspect_book, file_name, title, universe, age_group)


@document_mcp.tool()
async def create_page_manifest(book_version_id: str) -> dict:
    """Sayfa manifesti: boyut, metin katmanı, görsel sayısı, OCR gereği; sayfaları PNG'ye çizer."""
    return await _t(document.create_page_manifest, book_version_id)


@document_mcp.tool()
async def extract_text_layer(generation_id: Gen, book_version_id: str) -> dict:
    """PDF metin katmanından sayfa metni ve paragraflar."""
    return await _t(document.extract_text_layer, generation_id, book_version_id)


@document_mcp.tool()
async def render_page(book_version_id: str, page_no: Page) -> dict:
    """Sayfayı PNG olarak çizer (analiz için; dosya yolu döner)."""
    return await _t(document.render_page, book_version_id, page_no)


@document_mcp.tool()
async def run_ocr(generation_id: Gen, book_version_id: str, page_no: Page) -> dict:
    """Sayfada OCR (book-vision-fast). Resim içindeki yazılar da ayrı döner."""
    return await document.run_ocr(generation_id, book_version_id, page_no)


@document_mcp.tool()
async def get_page_bundle(generation_id: Gen, page_no: Page) -> dict:
    """Bir sayfa hakkında defterde olan her şey: paragraflar, OCR, taramalar, görsel bölgeler."""
    return await _t(document.get_page_bundle, generation_id, page_no)


# -------------------------------------------------------------- vision
vision_mcp = MCPServer("book_vision_mcp", instructions=(
    "Sayfa görsel analizi. depth='fast' book-vision-fast, depth='deep' book-vision-deep kullanır; "
    "deep yalnız belirsiz kimlik, metin-görsel çelişkisi, önemli olay, süreklilik ve editör raporu için."))


@vision_mcp.tool()
async def analyze_page_visual(generation_id: Gen, page_no: Page, depth: str = "fast") -> dict:
    """Sayfayı görsel olarak tarar (fast|deep) ve sonucu defterde saklar."""
    if depth not in ("fast", "deep"):
        raise ValueError("depth 'fast' ya da 'deep' olmalı")
    r = await vision.analyze_page_visual(generation_id, page_no, depth)
    await _t(vision.persist_page_visual, generation_id, page_no)
    return r


@vision_mcp.tool()
async def detect_characters(generation_id: Gen, page_no: Page) -> list[dict]:
    """Sayfadaki figürler: ad (dayanağıyla), görünüm, eylem, kimlik belirsizliği, bbox."""
    return await vision.detect_characters(generation_id, page_no)


@vision_mcp.tool()
async def detect_objects(generation_id: Gen, page_no: Page) -> list[dict]:
    """Sayfadaki nesneler (bbox ile)."""
    return await vision.detect_objects(generation_id, page_no)


@vision_mcp.tool()
async def detect_scene(generation_id: Gen, page_no: Page) -> dict:
    """Sahne: mekân, zaman, atmosfer, önemli olay, resim içi yazılar."""
    return await vision.detect_scene(generation_id, page_no)


@vision_mcp.tool()
async def compare_character_appearances(generation_id: Gen, character: str,
                                        pages: Annotated[list[int], Field(min_length=1)],
                                        character_id: str | None = None) -> dict:
    """Seçilen sayfalardaki tüm doğrulanmış figürleri altışar görüntülü partilerde karşılaştırır.
    Aynı adlı kişilerde character_id gerekir; kapsam ve aday farklar ayrı döner."""
    return await vision.compare_character_appearances(generation_id, character, pages, character_id=character_id)


@vision_mcp.tool()
async def check_text_visual_consistency(generation_id: Gen, page_no: Page) -> dict:
    """Metin ile görselin uyumu. Uyuşmazlık aday bulgudur."""
    return await vision.check_text_visual_consistency(generation_id, page_no)


# ----------------------------------------------------------- knowledge
knowledge_mcp = MCPServer("book_knowledge_mcp", instructions=(
    "Karakter, olay, duygu kayıtları. Her yazma kanıt ister; alıntı sayfa metninde birebir "
    "bulunmazsa kayıt reddedilir. Plan/hayal/şaka REALIZED yazılmaz."))


@knowledge_mcp.tool()
async def save_character_candidate(generation_id: Gen, name: str, page: Page, description: str,
                                   evidence: Evidence, confidence: Annotated[float, Field(ge=0, le=1)],
                                   via: str = "TEXT") -> dict:
    """Karakter anması adayı kaydeder (kimlik çözümüne kadar UNRESOLVED)."""
    return await _t(knowledge.save_character_candidate, generation_id, name, page, description,
                    evidence, confidence, via)


@knowledge_mcp.tool()
async def resolve_character_identity(generation_id: Gen) -> dict:
    """Çözülmemiş anmaları karakterlere birleştirir. CONFIRMED yalnız güven >= 0.85 ve iki sayfa kanıtla."""
    return await knowledge.resolve_character_identity(generation_id)


@knowledge_mcp.tool()
async def save_event(generation_id: Gen, summary: str,
                     modality: Annotated[str, Field(pattern="^(REALIZED|PLAN|DREAM|IMAGINATION|JOKE|LIE|HYPOTHETICAL|MEMORY|UNCERTAIN)$")],
                     page_from: Page, page_to: Page, participants: list[str], evidence: Evidence,
                     confidence: Annotated[float, Field(ge=0, le=1)],
                     importance: Annotated[float, Field(ge=0, le=1)] = 0.5) -> dict:
    """Olay kaydeder; kip zorunlu."""
    return await _t(knowledge.save_event, generation_id, summary, modality, page_from, page_to,
                    participants, evidence, confidence, importance)


@knowledge_mcp.tool()
async def merge_events(generation_id: Gen) -> dict:
    """Tekrarlanan olayları birleştirir (farklı kipleri asla), gerçekleşmiş olayları sıralar."""
    return await knowledge.merge_events(generation_id)


@knowledge_mcp.tool()
async def save_emotion(generation_id: Gen, character: str, page: Page, emotion: str,
                       intensity: Annotated[float, Field(ge=0, le=1)], trigger: str,
                       evidence: Evidence, confidence: Annotated[float, Field(ge=0, le=1)]) -> dict:
    """Duygu kaydeder."""
    return await _t(knowledge.save_emotion, generation_id, character, page, emotion, intensity,
                    trigger, evidence, confidence)


@knowledge_mcp.tool()
async def build_timeline(generation_id: Gen) -> list[dict]:
    """Yalnız gerçekleşmiş (ve hatırlanan) olaylar, hikâye sırasıyla."""
    return await _t(knowledge.build_timeline, generation_id)


@knowledge_mcp.tool()
async def get_event_actors(generation_id: Gen) -> list[dict]:
    """Kim ne yaptı: olay başına eylemi YAPAN ve olayda YER ALAN karakterler, olasılıklarıyla.
    UNCERTAIN okumalar kesin bilgi değildir; çıkarımın kendi katılımcı listesi ayrıca verilir."""
    return await _t(knowledge.event_actors, generation_id)


@knowledge_mcp.tool()
async def detect_contradictions(generation_id: Gen) -> dict:
    """Zaman çizelgesi, karakter, metin-görsel ve süreklilik çelişki ADAYLARI."""
    return await knowledge.detect_contradictions(generation_id)


# ----------------------------------------------------------- retrieval
retrieval_mcp = MCPServer("book_retrieval_mcp", instructions=(
    "Kanıt arama: book-embedding ile aday, book-reranker ile sıralama. Cevaplar yalnız dönen "
    "pasajlara dayanır ve sayfa numarasıyla atıf yapar."))


@retrieval_mcp.tool()
async def embed_passages(generation_id: Gen) -> dict:
    """Paragraf, OCR, olay, sahne ve karakter kayıtlarını arama indeksine ekler."""
    return await retrieval.embed_passages(generation_id)


@retrieval_mcp.tool()
async def search_book_evidence(generation_id: Gen, query: str,
                               k: Annotated[int, Field(ge=1, le=20)] = 8,
                               kinds: list[str] | None = None) -> list[dict]:
    """Soruya kanıt olabilecek pasajlar (sayfa ve paragrafıyla, reranker puanıyla)."""
    return await retrieval.search_book_evidence(generation_id, query, k, kinds)


@retrieval_mcp.tool()
async def rerank_evidence(query: str, candidates: list[str]) -> list[dict]:
    """Aday metinleri soruya göre sıralar (book-reranker)."""
    return await retrieval.rerank_evidence(query, candidates)


@retrieval_mcp.tool()
async def search_character_history(generation_id: Gen, name: str) -> dict:
    """Bir karakterin anmaları, duyguları ve katıldığı olaylar, sayfa sırasıyla."""
    return await _t(retrieval.search_character_history, generation_id, name)


@retrieval_mcp.tool()
async def search_universe_canon(universe: str, query: str = "",
                                k: Annotated[int, Field(ge=1, le=30)] = 8) -> list[dict]:
    """Evrenin editör onaylı kanon kayıtları (salt okunur)."""
    return await retrieval.search_universe_canon(universe, query, k)


@retrieval_mcp.tool()
async def search_books(query: str, k: Annotated[int, Field(ge=1, le=20)] = 5,
                       age: Annotated[int | None, Field(ge=0, le=18)] = None) -> list[dict]:
    """Katalogda isteğe uyan kitaplar: doğrulanmış tema/özet/kilit olaylara göre, her gerekçe
    sayfa atıflı; kapak adresiyle. Kitap önerisi için."""
    return await catalog.search_books(query, k, age)


@retrieval_mcp.tool()
async def get_book_card(book_id: str) -> dict | None:
    """Bir kitabın güncel kartı: künye, yaş, özet, temalar, karakterler, kilit olaylar, kapak."""
    return await _t(catalog.get_book_card, book_id)


# ------------------------------------------------------------- quality
quality_mcp = MCPServer("book_quality_mcp", instructions=(
    "Kanıt ve güven kontrolü, editör kuyruğu, regresyon, rapor. Rapor bölümlerindeki her iddia "
    "doğrulanmış kanıt taşımalıdır."))


@quality_mcp.tool()
async def validate_claim(generation_id: Gen, claim: dict[str, Any] | None = None,
                         claim_id: str | None = None) -> dict:
    """İddiayı kalite kurallarına göre denetler. claim biçimi: {claim, source_pages, evidence
    ([{page, paragraph, quote}] ya da metin), confidence, status, needs_editor_review}."""
    if not claim and not claim_id:
        raise ValueError("claim ya da claim_id gerekli")
    return await _t(quality.validate_claim, generation_id, claim, claim_id)


@quality_mcp.tool()
async def calculate_confidence(claim_id: str) -> dict:
    """Kayıtlı iddianın güvenini kanıt doğrulaması, sayfa sayısı ve Critic sonucundan hesaplar."""
    return await _t(quality.calculate_confidence, claim_id)


@quality_mcp.tool()
async def send_to_editor_queue(generation_id: Gen, reason: str, claim_id: str | None = None,
                               contradiction_id: str | None = None,
                               priority: Annotated[int, Field(ge=1, le=3)] = 2) -> dict:
    """İddiayı ya da çelişki adayını NEEDS_REVIEW olarak editör kuyruğuna gönderir."""
    return await _t(quality.send_to_editor_queue, generation_id, reason, claim_id,
                    contradiction_id, priority)


@quality_mcp.tool()
async def run_regression_suite(generation_id: Gen) -> dict:
    """Kalite kuralları, altın beklentiler ve önceki nesille karşılaştırma."""
    return await _t(quality.run_regression_suite, generation_id)


@quality_mcp.tool()
async def create_analysis_report(generation_id: Gen,
                                 kind: Annotated[str, Field(pattern="^(ANALYSIS|AGE_GROUP|PUBLISHER|EDITOR)$")] = "ANALYSIS",
                                 sections: list[dict[str, Any]] | None = None) -> dict:
    """Atıflı rapor üretir (yeni kayıt; eskisinin üzerine yazmaz). sections: [{title, claims:
    [{claim, evidence:[{page, paragraph, quote}], confidence, needs_editor_review}]}]."""
    return await _t(quality.create_analysis_report, generation_id, kind, sections)


# ---------------------------------------------------------------- jobs
jobs_mcp = MCPServer("book_jobs_mcp", instructions=(
    "Uzun analiz Temporal iş akışında koşar: start_analysis_job job_id döndürür, durum "
    "get_job_status ile izlenir. Sohbet turunda analiz yapılmaz."))


@jobs_mcp.tool()
async def start_analysis_job(file_name: str, title: str | None = None, universe: str | None = None,
                             age_group: str | None = None) -> dict:
    """Tam analiz işini başlatır (15 adım). job_id ve book_version_id döner."""
    return await jobs.start_analysis_job(file_name, title, universe, age_group)


@jobs_mcp.tool()
async def get_job_status(job_id: str) -> dict:
    """İşin durumu, adımı, ilerlemesi, generation_id, açık editör kalemleri."""
    return await _t(jobs.get_job_status, job_id)


@jobs_mcp.tool()
async def cancel_job(job_id: str) -> dict:
    """İşi iptal eder."""
    return await jobs.cancel_job(job_id)


@jobs_mcp.tool()
async def list_books() -> list[dict]:
    """Defterdeki kitaplar ve son nesilleri; nesil varlığı analitik kabul değildir."""
    return await _t(jobs.list_books)


@jobs_mcp.tool()
async def latest_generation(book_version_id: str) -> dict | None:
    """Bir içerik sürümünün son analiz nesli."""
    return await _t(jobs.latest_generation, book_version_id)


@jobs_mcp.tool()
async def list_review_queue(generation_id: Gen, status: str = "OPEN",
                            limit: Annotated[int, Field(ge=1, le=200)] = 50) -> list[dict]:
    """Editör kuyruğu (salt okunur; karar editörün)."""
    return await _t(jobs.list_review_queue, generation_id, status, limit)


@jobs_mcp.tool()
async def get_report(generation_id: Gen, kind: str = "ANALYSIS") -> dict | None:
    """Güncel doğrulanmış revizyonun rapor taslağı; available=false ise eski rapor verilmez."""
    return await _t(jobs.get_report, generation_id, kind)


chat_mcp = MCPServer("book_chat_mcp", instructions=(
    "Salt okunur kitap sohbeti. Önce list_books/get_book_status. Sonra güncel neslin "
    "sayfalı bölümlerini ve gerçek kaynak sayfalarını oku. next_offset varsa kapsam eksiktir. "
    "Taslak analitik kabul değildir. Bu araçlar analiz veya model işi başlatmaz."))
Offset = Annotated[int, Field(ge=0)]
Limit = Annotated[int, Field(ge=1, le=20)]


@chat_mcp.tool(name="list_books")
async def chat_books(offset: Offset = 0, limit: Limit = 8) -> dict:
    """Kitaplar, içerik sürümleri ve en yeni analiz kimliği; sayfalı."""
    return await _t(chat_reads.books, offset, limit)


@chat_mcp.tool()
async def get_book_status(book_id: str) -> dict:
    """En yeni nesil ve güncel çıktı/iş durumu. FAILED işten kurtarılmış çıktı bulunabilir."""
    return await _t(chat_reads.status, book_id)


@chat_mcp.tool()
async def get_book_summary(generation_id: Gen) -> dict:
    """Tam güncel özet ve sayfa atıfları. Özet sorularında bunu kullan; bölümün ilk sayfasını
    kitabın tamamı sanma. summary_complete yalnız özet kapsamıdır, kitabın analitik kabulü değildir."""
    return await _t(chat_reads.summary, generation_id)


@chat_mcp.tool()
async def read_book_section(generation_id: Gen, section: str = "summary",
                            offset: Offset = 0, limit: Limit = 8) -> dict:
    """Güncel taslak bölümü: summary, characters, events, emotions, claims, reviews,
    contradictions, blockers. next_offset ile devam et; sayfa atıflarını koru."""
    return await _t(chat_reads.section, generation_id, section, offset, limit)


@chat_mcp.tool()
async def read_source_page(generation_id: Gen, page_no: Page,
                           offset: Offset = 0, limit: Limit = 8) -> dict:
    """Orijinal kaynak alıntıları; değiştirilmemiş metin, sayfa/paragraf ve hash. Sayfalı."""
    return await _t(chat_reads.source_page, generation_id, page_no, offset, limit)


@chat_mcp.tool()
async def find_book_claims(generation_id: Gen, query: str,
                            offset: Offset = 0, limit: Limit = 8) -> dict:
    """Doğrulanmış iddialarda sözcük/isim ara. Tam normalize eşleşme; semantik arama değildir.
    Boş sonuç yokluk kanıtı sayılmaz; başka sözcük veya kaynak sayfası ile kontrol et."""
    return await _t(chat_reads.find, generation_id, query, offset, limit)


@chat_mcp.tool(name="search_book_evidence")
async def chat_search(generation_id: Gen, query: str,
                       k: Annotated[int, Field(ge=1, le=8)] = 5) -> dict:
    """Güncel indekste anlamsal kanıt araması. Sayfa atfını koru; düşük puanı kesin bilgi sayma."""
    from . import outputs
    selected = await _t(outputs.current, generation_id, 'search_index')
    if not selected['available']:
        return {k:v for k,v in selected.items() if k != 'artifact'}
    rows = await retrieval.search_book_evidence(generation_id, query, k)
    return {**{k:v for k,v in selected.items() if k != 'artifact'},
            'retrieval_mode': 'SEMANTIC_RERANKED', **chat_reads.page(rows, 0, k)}


SERVERS = {"document": document_mcp, "vision": vision_mcp, "knowledge": knowledge_mcp,
           "retrieval": retrieval_mcp, "quality": quality_mcp, "jobs": jobs_mcp,
           "chat": chat_mcp}


class BearerAuth(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.url.path == "/health":
            return await call_next(request)
        tok = request.headers.get("authorization", "").removeprefix("Bearer ").strip()
        if not KEY or tok != KEY:
            return Response("unauthorized", status_code=401)
        return await call_next(request)


security = TransportSecuritySettings(
    allowed_hosts=["editor-mcp", "editor-mcp:*", "127.0.0.1:*", "localhost:*"], allowed_origins=[])
async def cover_image(request: Request) -> Response:
    """Current cover of a book (uploaded, else the stand-in PDF page) for the UI."""
    cov = await asyncio.to_thread(catalog.current_cover, request.path_params["book_id"])
    if cov is None:
        return Response("no cover", status_code=404)
    return FileResponse(cov["file_path"], headers={"x-cover-source": cov["source"]})


async def cover_requests(_request: Request) -> Response:
    return JSONResponse({"books": await asyncio.to_thread(catalog.cover_requests)})


async def cover_store(request: Request) -> Response:
    return JSONResponse(await asyncio.to_thread(catalog.store_crm_lookup, await request.json()))


routes = [Route("/catalog/cover-requests", cover_requests),
          Route("/catalog/covers", cover_store, methods=["POST"]),
          Route("/health", lambda _r: JSONResponse({"ok": True, "servers": list(SERVERS)})),
          Route("/covers/{book_id}", cover_image)]
routes += [Mount(f"/{name}", app=srv.streamable_http_app(transport_security=security))
           for name, srv in SERVERS.items()]


@asynccontextmanager
async def lifespan(_app: Starlette) -> AsyncIterator[None]:
    await asyncio.to_thread(db.pool)
    async with AsyncExitStack() as stack:
        for srv in SERVERS.values():
            await stack.enter_async_context(srv.session_manager.run())
        yield


app = Starlette(routes=routes, lifespan=lifespan)
app.add_middleware(BearerAuth)

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")
