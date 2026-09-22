"""Görünüş sürekliliği: aynı karakterin görünüşü (saç/göz/ten rengi, gözlük, şapka, üst/alt
giysi rengi, taşıdığı eşya) kitap boyunca metinde ve RESİMDE tutarlı mı. Çocuk kitabında asıl
kaynak resimdir: s.12'de kırmızı tişört, s.28'de mavi → aday bulgu.

Akış (kitabı yeniden okumaz, özellik defterini okur — proofing._attributes):
  1. DEFTER: boşsa doldurulur (idempotent; aynı nesil + aynı okuyucu sürümü için yeniden
     okunmaz). Metin satırı alıntı kanıtı, resim satırı figür kutusu (bbox 0..1000) taşır;
     resim değeri en az iki bağımsız okumanın uyuşmasıyla yazılmıştır, aksi BELIRSIZ.
  2. ÇIKARMA (deterministik, _attributes.conflicts): aynı karakter + aynı tür + farklı değer,
     iki AYRI sayfada → aday çift. BELIRSIZ çelişki kurmaz. Metin–metin, resim–resim ve
     metin–resim çiftleri aynı yoldan geçer.
  3. YARGI (text_contradictions ile aynı biçim): her çift kitabın bütün metniyle birlikte
     director'a kapalı soru olarak, iki sırada (A→B, B→A) sorulur; cevap tek harf, olasılığı
     logprobs'tan (Llm.choose). "Üstünü değiştirdi", "yeni tişört", ıslanma, rüya, kılık
     değiştirme gibi bir açıklama metinde varsa çelişki değildir. Bulgu ancak iki sırada da
     "çelişki" olasılığı JUDGE_MIN'i geçerse.
  4. Bulgu iki kanıt taşır (iki sayfa: alıntı ya da bbox). Şiddet: kalıcı özellik (saç, göz,
     ten/kürk, gözlük) ve olasılık ERROR_MIN üstü → ERROR; diğerleri WARN. Defter kapsamı
     (kaç karakter, kaç figür okundu, kaç değer belirsiz) bir INFO satırıyla bildirilir.

ÖLÇÜM BEKLİYOR: JUDGE_MIN ve ERROR_MIN gerçek kitapta ölçülmedi; okuyucuların kesinliği ve
denetimin yanlış alarm oranı docs/son-okuma/appearance.md'deki planla ölçülecek. Ölçülene
kadar bulgular yalnız editör adayıdır."""

from __future__ import annotations

import asyncio

from .. import source
from ..llm import Llm
from . import _attributes as A

NAME = "appearance"
VERSION = "1"
LABEL = "Görünüş sürekliliği"

DIRECTOR = "book-director"
# Yargının iki sırada da "çelişki" demesi gereken en düşük olasılık. text_contradictions'ta
# 0.5 ölçüldü; burada henüz ölçülmedi (aynı başlangıç değeri, doc: «Ölçüm planı»).
JUDGE_MIN = 0.5
# Kalıcı bir özellikte (saç, göz, ten/kürk, gözlük) bu olasılığın üstü ERROR. Ölçülmedi.
ERROR_MIN = 0.8
PARALLEL = 4

INTRO = ("Aşağıda resimli bir çocuk kitabının METNİ var. Her paragraf [sSAYFA pPARAGRAF] ile başlar. "
         "Künye, yazar/çizer tanıtımı ve arka kapak yazıları da metnin içinde olabilir; bunlar hikâye değildir.\n\n")

JUDGE = (
    "Soru: Aşağıdaki iki gözlem bu hikâyede AYNI karakter için İKİSİ BİRDEN doğru olabilir mi?\n"
    "Karakter: {name}. Özellik: {label}.\n"
    "Gözlem 1 (s.{p1}): {d1}\nGözlem 2 (s.{p2}): {d2}\n\n"
    "Önce kitabın tamamına bak: iki sayfa arasında metin bu değişimi açıklıyor mu (üstünü değiştirdi, "
    "yeni giysi aldı, ıslandı, kirlendi, kılık değiştirdi, büyüdü, zaman geçti, saçını kestirdi/boyadı, "
    "gözlüğünü çıkardı, eşyayı bıraktı/aldı); gözlemlerden biri rüya, hayal, oyun ya da geçmişe dönüş "
    "içinde mi; resimdeki gözlem kırpımın kestiği ya da ışığın değiştirdiği bir şey olabilir mi? "
    "Bunlardan biri varsa çelişki yoktur. Sahneden sahneye doğal olarak değişebilen bir şey (kıyafet, "
    "eşya) için metin değişimi açıklamıyorsa ve aynı gün/sahne içinde olmalıysa çelişkidir.\n\n"
    "Cevap tek harf: C = süreklilik hatası (aynı karakter, aynı özellik, iki değer birden doğru olamaz, "
    "metin açıklamıyor); U = çelişki yok (bağdaşıyor ya da metin/bağlam açıklıyor); B = karar verilemiyor.")


def book_text(pages: list[dict]) -> str:
    return "\n".join(f"[s{p['page_no']} p{s['idx']}] {s['text']}" for p in pages for s in p["spans"])


def severity(kind: str, p: float) -> str:
    return "ERROR" if A.KINDS[kind]["stable"] and p >= ERROR_MIN else "WARN"


def finding_of(c: dict, verdict: dict) -> dict:
    """Bir yargılanmış çiftten bulgu: sayfa ve kanıt ikinci (sonraki) gözlemin, ilki mesajda."""
    a, b = c["a"], c["b"]
    label = A.KINDS[c["kind"]]["label"]
    p = verdict["p_contradiction"]
    return {
        "page": b["page_no"], "severity": severity(c["kind"], p),
        "quote": b["quote"] if b["source"] == "TEXT" else None,
        "bbox": b["bbox"] if b["source"] == "IMAGE" else None,
        "message": (f"Görünüş sürekliliği ({label}) — «{c['character_name']}»: s.{a['page_no']} {A.describe(a)}; "
                    f"s.{b['page_no']} {A.describe(b)}. Hikâye bu değişikliği açıklamıyor."
                    + (f" (Aynı değer s.{', s.'.join(map(str, c['pages_a']))} sayfalarında da okundu.)"
                       if len(c["pages_a"]) > 1 else "")),
        "suggestion": "İki sayfayı yan yana karşılaştırın; çizimi ya da metni düzeltin veya değişimi açıklayan "
                      "bir cümle ekleyin.",
        "details": {"character": c["character_name"], "character_id": c["character_id"], "kind": c["kind"],
                    "stable": A.KINDS[c["kind"]]["stable"],
                    "a": _ev(a), "b": _ev(b), "pages_a": c["pages_a"], "pages_b": c["pages_b"],
                    "judge": {k: verdict[k] for k in ("forward", "reverse")},
                    "p_contradiction": round(p, 3)}}


def _ev(r: dict) -> dict:
    return {"page": r["page_no"], "source": r["source"], "value": r["value"], "quote": r.get("quote"),
            "bbox": r.get("bbox"), "evidence_id": str(r["evidence_id"]) if r.get("evidence_id") else None,
            "mention_id": str(r["mention_id"]) if r.get("mention_id") else None,
            "confidence": round(float(r.get("confidence") or 0), 3)}


async def judge(llm: Llm, text: str, c: dict, sem: asyncio.Semaphore) -> dict:
    label = A.KINDS[c["kind"]]["label"]

    async def ask(x: dict, y: dict) -> dict:
        body = INTRO + text + "\n\n" + JUDGE.format(name=c["character_name"], label=label,
                                                     p1=x["page_no"], d1=A.describe(x),
                                                     p2=y["page_no"], d2=A.describe(y))
        async with sem:
            probs, _ = await llm.choose(DIRECTOR, [{"role": "user", "content": body}], ["C", "U", "B"],
                                        pages=sorted({x["page_no"], y["page_no"]}))
        return probs
    fwd, rev = await asyncio.gather(ask(c["a"], c["b"]), ask(c["b"], c["a"]))
    return {"forward": fwd, "reverse": rev, "p_contradiction": min(fwd["C"], rev["C"])}


async def check(rows: list[dict], pages: list[dict], llm: Llm) -> tuple[list[dict], dict]:
    """Defter satırlarından bulgular (defteri doldurmaz; run() doldurur)."""
    cands = A.conflicts(rows)
    stats = {"rows": len(rows), "rows_text": sum(r["source"] == "TEXT" for r in rows),
             "rows_image": sum(r["source"] == "IMAGE" for r in rows),
             "uncertain": sum(r["value"] == A.UNCERTAIN for r in rows),
             "characters": len({str(r["character_id"]) for r in rows}),
             "candidates": len(cands), "judge_failed": 0, "confirmed": 0, "candidates_detail": []}
    findings: list[dict] = []
    if cands:
        text = book_text(pages)
        sem = asyncio.Semaphore(PARALLEL)
        verdicts = await asyncio.gather(*(judge(llm, text, c, sem) for c in cands), return_exceptions=True)
        for c, v in zip(cands, verdicts):
            detail = {"character": c["character_name"], "kind": c["kind"], "a": _ev(c["a"]), "b": _ev(c["b"])}
            if isinstance(v, BaseException):
                stats["judge_failed"] += 1
                stats["candidates_detail"].append({**detail, "p": None})
                continue
            stats["candidates_detail"].append({**detail, "p": round(v["p_contradiction"], 3)})
            if v["p_contradiction"] >= JUDGE_MIN:
                findings.append(finding_of(c, v))
    stats["confirmed"] = len(findings)
    return findings, stats


async def run(generation_id: str):
    llm = Llm(generation_id)
    fill = await A.fill(generation_id, llm)
    rows = await asyncio.to_thread(A.rows, generation_id)
    pages = await asyncio.to_thread(source.read, generation_id)
    findings, stats = await check(rows, pages, llm)
    stats["ledger"] = fill
    img = fill["image"]
    findings.append({
        "page": None, "severity": "INFO",
        "message": (f"Özellik defteri: {stats['characters']} karakter, {stats['rows_text']} metin ve "
                    f"{stats['rows_image']} resim kaydı ({img['figures']} çözülmüş figür, "
                    f"{img.get('not_visible', 0)} kırpım okunamadı), {stats['uncertain']} değer belirsiz; "
                    f"{stats['candidates']} aday çift yargılandı, {stats['confirmed']} bulgu. "
                    "Eşikler henüz gerçek kitapta ölçülmedi.")})
    return findings, stats
