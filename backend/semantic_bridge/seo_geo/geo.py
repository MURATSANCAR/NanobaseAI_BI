"""Yapay zekâ görünürlüğü (GEO) ölçümü: izlenen sorular yapay zekâ motorlarına resmî API'leriyle sorulur, cevapta
Timaş'ın anılıp anılmadığı ve timas.com.tr'nin kaynak gösterilip gösterilmediği kaydedilir.

Motorlar (her biri anahtarı Yönetim ekranında girilince devreye girer; anahtarsız motor ölçülmez, sonuç uydurulmaz):
- Gemini (Google): `gemini-2.5-flash` + Google Search ile dayandırma — ücretsiz katman (günde ~500 aramalı istek). Günlük
  sınır `GEO_GEMINI_DAILY` (varsayılan 450) ekranda görünür; ücretsiz kotanın aşılmaması için.
- ChatGPT (OpenAI Responses API + `web_search`), Perplexity (Sonar), Claude (Messages API + web araması): ücretli;
  anahtar girilirse ölçülür. Günlük sınırları ayrı ayar.
Tüketici arayüzü (chatgpt.com vb.) kazınmaz. Sorular kamuya açık okur sorularıdır; şirket verisi gönderilmez.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Optional

import httpx

ENGINES: dict[str, dict[str, str]] = {
    "gemini": {"label": "Gemini (Google)", "key": "GEMINI_API_KEY", "daily": "GEO_GEMINI_DAILY", "model": "GEO_GEMINI_MODEL",
               "free": "1"},
    "openai": {"label": "ChatGPT (OpenAI)", "key": "GEO_OPENAI_API_KEY", "daily": "GEO_OPENAI_DAILY", "model": "GEO_OPENAI_MODEL",
               "free": ""},
    "perplexity": {"label": "Perplexity", "key": "PERPLEXITY_API_KEY", "daily": "GEO_PERPLEXITY_DAILY",
                   "model": "GEO_PERPLEXITY_MODEL", "free": ""},
    "claude": {"label": "Claude (Anthropic)", "key": "GEO_ANTHROPIC_API_KEY", "daily": "GEO_CLAUDE_DAILY",
               "model": "GEO_CLAUDE_MODEL", "free": ""},
}
BRAND = re.compile(r"tima[şs]", re.I)
SITE = re.compile(r"(^|[/.])timas\.com\.tr", re.I)


class EngineError(RuntimeError):
    pass


def _post(url: str, headers: dict[str, str], body: dict[str, Any], timeout: float = 90) -> dict[str, Any]:
    with httpx.Client(timeout=timeout) as c:
        r = c.post(url, headers=headers, json=body)
    if r.status_code == 429:
        raise EngineError("Kota doldu (429).")
    if r.status_code >= 400:
        try:
            msg = r.json().get("error", {})
            msg = msg.get("message") if isinstance(msg, dict) else msg
        except ValueError:
            msg = r.text[:200]
        raise EngineError(f"HTTP {r.status_code}: {str(msg)[:300]}")
    return r.json()


def ask_gemini(q: str, key: str, model: str) -> tuple[str, list[dict[str, str]]]:
    d = _post(f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
              {"x-goog-api-key": key, "Content-Type": "application/json"},
              {"contents": [{"parts": [{"text": q}]}], "tools": [{"google_search": {}}]})
    cand = (d.get("candidates") or [{}])[0]
    text = " ".join(p.get("text", "") for p in (cand.get("content") or {}).get("parts", []))
    chunks = (cand.get("groundingMetadata") or {}).get("groundingChunks") or []
    return text, [{"url": (c.get("web") or {}).get("uri", ""), "title": (c.get("web") or {}).get("title", "")} for c in chunks]


def ask_openai(q: str, key: str, model: str) -> tuple[str, list[dict[str, str]]]:
    d = _post("https://api.openai.com/v1/responses", {"Authorization": f"Bearer {key}"},
              {"model": model, "tools": [{"type": "web_search"}], "input": q})
    text, cites = "", []
    for item in d.get("output") or []:
        for part in item.get("content") or []:
            if part.get("type") == "output_text":
                text += part.get("text", "")
                cites += [{"url": a.get("url", ""), "title": a.get("title", "")} for a in part.get("annotations") or []
                          if a.get("type") == "url_citation"]
    return text, cites


def ask_perplexity(q: str, key: str, model: str) -> tuple[str, list[dict[str, str]]]:
    d = _post("https://api.perplexity.ai/chat/completions", {"Authorization": f"Bearer {key}"},
              {"model": model, "messages": [{"role": "user", "content": q}]})
    text = ((d.get("choices") or [{}])[0].get("message") or {}).get("content", "")
    res = d.get("search_results") or [{"url": u} for u in d.get("citations") or []]
    return text, [{"url": r.get("url", ""), "title": r.get("title", "")} for r in res]


def ask_claude(q: str, key: str, model: str) -> tuple[str, list[dict[str, str]]]:
    d = _post("https://api.anthropic.com/v1/messages",
              {"x-api-key": key, "anthropic-version": "2023-06-01"},
              {"model": model, "max_tokens": 1500, "messages": [{"role": "user", "content": q}],
               "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 3}]})
    text, cites = "", []
    for block in d.get("content") or []:
        if block.get("type") == "text":
            text += block.get("text", "")
            cites += [{"url": c.get("url", ""), "title": c.get("title", "")} for c in block.get("citations") or [] if c.get("url")]
    return text, cites


ASK: dict[str, Callable[[str, str, str], tuple[str, list[dict[str, str]]]]] = {
    "gemini": ask_gemini, "openai": ask_openai, "perplexity": ask_perplexity, "claude": ask_claude}
DEFAULT_MODEL = {"gemini": "gemini-2.5-flash", "openai": "gpt-5-mini", "perplexity": "sonar", "claude": "claude-sonnet-5"}


def analyse(text: str, cites: list[dict[str, str]], books: list[tuple[str, str]]) -> dict[str, Any]:
    """Cevapta Timaş anılıyor mu, site kaynak mı, hangi kitaplar geçiyor. `books`: (küçük harf ad, gösterilecek ad)."""
    low = text.casefold()
    hits = [name for key, name in books if key in low]
    urls = [c["url"] for c in cites if c.get("url")]
    # Gemini kaynakları yönlendirme adresi (vertexaisearch…) olarak verir; başlık alan adını taşır.
    site = any(SITE.search(u) for u in urls) or any(SITE.search(c.get("title", "")) for c in cites)
    return {"mentioned": bool(BRAND.search(text)) or bool(hits), "cited": site, "books": hits[:20], "sources": len(cites)}


def book_index(products: list[dict[str, Any]], text_of: Callable[[Any], str]) -> list[tuple[str, str]]:
    """Cevapta aranacak kitap adları: en az 2 kelimelik, 8+ karakterlik adlar (kısa ad genel kelimeyle karışır)."""
    out = {}
    for p in products:
        name = text_of(p.get("ProductName"))
        name = re.sub(r"\s*\(.*?\)\s*$", "", name).strip()
        if len(name) >= 8 and len(name.split()) >= 2:
            out[name.casefold()] = name
    return sorted(out.items(), key=lambda kv: -len(kv[0]))


def ask(engine: str, question: str, key: str, model: Optional[str]) -> tuple[str, list[dict[str, str]]]:
    return ASK[engine](question, key, model or DEFAULT_MODEL[engine])
