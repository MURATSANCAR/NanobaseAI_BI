"""Kitabın kendisi olmayan sayfalar: künye, iç kapak, yazar tanıtımı, içindekiler, yayınevi tanıtımı.

Sorun (2026-10-02 denetimi, 22 okunmuş kitap): okumanın NON_STORY önerisi yalnız öneriydi, editör onayı
bekliyordu; arşivde onaylayan yok. Künye/yazar tanıtımı/tanıtım sayfasından olay çıktı (Rüzgârın Ardından 13,
Darwin ve Osmanlılar yazar biyografisi), kitap özeti uç olay sayfası olarak künyeyi (s.2) ya da yayınevinin
başka kitaplarının tanıtımını istedi ve 22 kitabın 22'sinde düştü; FRONT_MATTER hiç yazılmadığı için künye
(`catalog.extract_metadata`) hiç okunmadı.

Kural (kitaptan bağımsız, tam ve arşiv kipinde aynı): okumanın NON_STORY önerisi tek başına sayfayı kapsamdan
çıkarmaz. Kurgu dışı kitapta öneri gövdenin çoğunu kapsar (Osmanlı Taşra Maliyesi 544 sayfanın 440'ı, üstünde
312 olay; İbn Sina 160'ın 148'i; İstediğim İnsan 128'in 101'i) — öneriyi olduğu gibi uygulamak kitabın
kendisini silerdi. Sayfa ancak METNİ künye/iç kapak/yazar tanıtımı/içindekiler/yayınevi tanıtımı olduğunu
gösterirse çıkar: Stüdyo'nun baskı dışı sayfa kuralı (`production.manuscript.print_plan`), aynı ölçüt, tek yer.
Aday sayfalar: okumanın NON_STORY önerisi + metninde güçlü künye işareti olan her sayfa (ISBN + sertifika ya da
≥3 künye sözcüğü) + kitabın son sayfaları (tanıtım kuyruğu öneri almamış olabilir). Sayfanın yalnız bir kısmı
tanıtımsa (kalan paragraf > 0) sayfa kapsamda kalır.

Yazılan rol: künye, iç kapak, yazar tanıtımı → FRONT_MATTER (künye okuması bunları okur); içindekiler ve
yayınevi tanıtımı → NON_STORY (başka kitapların yazarı künyeye karışmasın). Kaynağı `source='auto'`
(«otomatik»): editörün kararı (`source='editor'`) hiçbir zaman ezilmez; editör sayfa sorusunda «Hayır» derse
sayfa STORY olur ve kapsama döner (review.choose). Her otomatik sayfa için editöre açık bir sayfa sorusu kalır.

Kapsam dışı sayfanın olay/duygu/tema iddiası SİLİNMEZ: çıktılar (`outputs.capture`) onu kullanmaz; rol geri
alınınca geri gelir. Yeni okumada bu sayfalardan olay hiç çıkarılmaz (`knowledge._persist`).

Yeniden üretim (yeniden okumadan): `python -m editor.page_scope rebuild --all-read [--dry-run [--model 5]]`.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
import time

#: print_plan nedeni → yazılacak sayfa rolü
ROLE_OF = {"künye": "FRONT_MATTER", "iç kapak": "FRONT_MATTER", "yazar tanıtımı": "FRONT_MATTER",
           "içindekiler": "NON_STORY", "yayınevi tanıtımı": "NON_STORY", "ithaf": "NON_STORY"}
#: İthaf: baskıda kalır (print_plan onu basar), okumada kitabın olayı değildir. Yalnız okumanın da hikâye dışı
#: dediği ön sayfada ve metni ithafsa: kısa (≤ 40 sözcük) ve ithaf sözcüğü ya da «Ad'a/'e/'ya/'ye/'na/'ne,» ile
#: açılıyor (Benim Adım Ekin s.1: «Ekin'e, ... sarıp sarmalayanlara...»). Yer/yıl satırı («İstanbul 2025») sayılmaz.
_ITHAF = re.compile(r"\bithaf|hat[ıi]ras[ıi]na|an[ıi]s[ıi]na", re.I)
_DATIVE = re.compile(r"^\W*[^\W\d_]+['’](y?[ae]|n[ae])\b")
SOURCE = "auto"
#: kapsam dışı sayfayı çıktıdan düşüren rol kaynakları (editörün kararı + otomatik kural; okumanın
#: `extract` önerisi değil)
SCOPE_SOURCES = ("editor", SOURCE)
SCOPE_ROLES = ("FRONT_MATTER", "NON_STORY")
#: sayfası kapsam dışıysa çıktıda kullanılmayan iddia türleri: okumanın metinden çıkardıkları (görsel bulgu,
#: kimlik ve künye iddiası değil) — `knowledge._persist`'in düşürdükleriyle aynı
SCOPED_KINDS = ("EVENT", "EMOTION", "THEME")
REVIEW_REASON = ("Sayfa türü: s{p} {why} — otomatik olarak kapsam dışı (künye/tanıtım sayfasından olay "
                 "çıkarılmaz). Hikâye/gövde sayfasıysa «Hayır» seçin, kapsama döner.")
META_FIELDS = ("TITLE", "AUTHOR", "AGE_RANGE", "GENRE", "ISBN", "PUBLISHER")


def _strong_kunye(texts: list[str]) -> bool:
    from .production.manuscript import _KUNYE
    low = " ".join(texts).casefold()
    return sum(1 for k in _KUNYE if re.search(k, low)) >= 3 or bool(re.search(r"\bisbn\b", low) and "sertifika" in low)


def classify(pages: dict[int, list[str]], suggested: set[int], last_page: int,
             titles: list[str], names: list[str]) -> dict[int, tuple[str, str]]:
    """{sayfa: (rol, neden)} — yalnız bütünüyle kitabın dışında kalan sayfalar (salt hesap, yazmaz)."""
    from .production.manuscript import print_plan
    back = max(5, last_page // 20)
    candidates = set(suggested) | {p for p, t in pages.items() if t and _strong_kunye(t)} \
        | {p for p in pages if p > last_page - back}
    plan_ = print_plan(pages, candidates, last_page, [t for t in titles if t], [n for n in names if n])
    out = {p: (ROLE_OF[why], why) for p, (why, keep) in sorted(plan_.items()) if keep == 0 and why in ROLE_OF}
    from .production.manuscript import _PLACE_YEAR
    front = max(10, last_page // 10)
    for p in sorted(suggested):
        ps = [t for t in pages.get(p, []) if t.strip() and not _PLACE_YEAR.match(t)]
        if p in out or p > front or not ps or len(" ".join(ps).split()) > 40:
            continue
        if _ITHAF.search(" ".join(ps)) or _DATIVE.match(ps[0]):
            out[p] = (ROLE_OF["ithaf"], "ithaf")
    return dict(sorted(out.items()))


def inputs(c, gid: str) -> dict:
    """classify'ın girdileri, tek bağlantıdan (salt okuma)."""
    g = c.execute("SELECT g.id, bv.book_id, bv.page_count, b.title FROM ed.generation g JOIN ed.book_version bv"
                  " ON bv.id=g.book_version_id JOIN ed.book b ON b.id=bv.book_id WHERE g.id=%s", (gid,)).fetchone()
    if g is None:
        raise KeyError(gid)
    pages: dict[int, list[str]] = {}
    for r in c.execute("SELECT page_no, text FROM ed.paragraph WHERE generation_id=%s ORDER BY page_no, idx", (gid,)):
        pages.setdefault(r["page_no"], []).append(r["text"])
    roles = {r["page_no"]: dict(r) for r in c.execute(
        "SELECT page_no, role, source FROM ed.page_role WHERE generation_id=%s", (gid,))}
    crm = c.execute("SELECT crm_title, authors, illustrators FROM ed.book_crm_record WHERE book_id=%s",
                    (g["book_id"],)).fetchone() or {}
    return {"pages": pages, "roles": roles, "last_page": g["page_count"] or max(pages, default=0),
            "titles": [crm.get("crm_title"), g["title"]],
            "names": [", ".join(crm.get("authors") or []), ", ".join(crm.get("illustrators") or [])]}


def plan(c, gid: str) -> dict:
    """Bu nesilde yazılacak otomatik roller (salt okuma). Editörün karar verdiği sayfaya dokunulmaz; aynı rol
    zaten otomatik yazılmışsa yazılmaz."""
    x = inputs(c, gid)
    suggested = {p for p, r in x["roles"].items() if r["role"] in SCOPE_ROLES}
    found = classify(x["pages"], suggested, x["last_page"], x["titles"], x["names"])
    writes, kept = {}, {}
    for p, (role, why) in found.items():
        cur = x["roles"].get(p)
        if cur and cur["source"] == "editor":
            kept[p] = cur["role"]
            continue
        if cur and cur["source"] == SOURCE and cur["role"] == role:
            continue
        writes[p] = (role, why)
    return {"found": found, "writes": writes, "editor_kept": kept, "roles": x["roles"]}


def apply(c, gid: str, writes: dict[int, tuple[str, str]], *, queue: bool = True) -> int:
    """Rolleri yazar (editörün kararı ezilmez) ve her sayfa için editörün geri alabileceği sayfa sorusunu açık
    tutar. Çağıranın işlemi içinde; doğrulama jetonu varsa bilgi değişikliği o yazana sayılır."""
    from . import ledger
    n = 0
    for p, (role, why) in sorted(writes.items()):
        row = c.execute(
            "INSERT INTO page_role(generation_id, page_no, role, source) VALUES (%s,%s,%s,%s)"
            " ON CONFLICT (generation_id, page_no) DO UPDATE SET role=EXCLUDED.role, source=EXCLUDED.source"
            " WHERE page_role.source <> 'editor' RETURNING page_no", (gid, p, role, SOURCE)).fetchone()
        if row is None:
            continue
        n += 1
        if queue:
            reason = REVIEW_REASON.format(p=p, why=why)
            c.execute("UPDATE review_item SET reason=%s WHERE generation_id=%s AND page_role_page_no=%s"
                      " AND status='OPEN' AND reason IS DISTINCT FROM %s", (reason, gid, p, reason))
            ledger.queue_review(c, gid, reason=reason, priority=3, page_role_page_no=p)
    return n


def out_of_scope(roles: dict[int, dict]) -> set[int]:
    """Çıktıların kullanmadığı sayfalar: editörün ya da otomatik kuralın kapsam dışı dediği sayfalar."""
    return {p for p, r in roles.items() if r["source"] in SCOPE_SOURCES and r["role"] in SCOPE_ROLES}


def scoped(claim: dict, pages: set[int]) -> bool:
    """İddia kapsam dışı sayfaya dayanıyor mu (okumanın _persist kuralıyla aynı: sayfalarından biri yeter)."""
    return claim["kind"] in SCOPED_KINDS and bool(set(claim.get("source_pages") or []) & pages)


def ensure(gid: str) -> dict:
    """Bütün kitap için kuralı uygular (okuma sonu doğrulamasında; doğrulama jetonu çağıranın bağlamında)."""
    from . import db
    with db.tx() as c:
        p = plan(c, gid)
        n = apply(c, gid, p["writes"])
    return {"auto_pages": {k: v[1] for k, v in p["found"].items()}, "written": n,
            "editor_kept": sorted(p["editor_kept"])}


def for_chunk(c, gid: str, page_from: int, page_to: int, suggested: set[int]) -> set[int]:
    """Okuma sırasında (`knowledge._persist`): bu parçanın sayfalarından kapsam dışı olanlar, rolleri yazılmış
    olarak. Parçalar yan yana okunduğundan kitabın kalanının önerileri henüz gelmemiş olabilir; eksik kalanı
    okuma sonu doğrulaması (`ensure`) bütün kitapla tamamlar (çıktılar orada süzülür)."""
    x = inputs(c, gid)
    sug = {p for p, r in x["roles"].items() if r["role"] in SCOPE_ROLES} | set(suggested)
    found = classify(x["pages"], sug, x["last_page"], x["titles"], x["names"])
    mine = {p: v for p, v in found.items() if page_from <= p <= page_to
            and (x["roles"].get(p) or {}).get("source") != "editor"}
    apply(c, gid, mine)
    return set(mine)


# ------------------------------------------------------------------ yeniden üretim (yeniden okumadan)
def read_generations(c, profile: str | None = None) -> list[dict]:
    """Okuması bitmiş, çıktısı kurulabilir nesiller: iş SUCCEEDED, nesil izlenen ve mühürsüz."""
    q = ("SELECT g.id, b.title, j.profile FROM ed.generation g JOIN ed.analysis_job j ON j.id=g.job_id"
         " JOIN ed.generation_state s ON s.generation_id=g.id JOIN ed.book_version bv ON bv.id=g.book_version_id"
         " JOIN ed.book b ON b.id=bv.book_id WHERE j.status='SUCCEEDED' AND s.origin='TRACKED'"
         " AND g.sealed_at IS NULL AND j.profile IN ('full','archive')")
    rows = c.execute(q + (" AND j.profile=%s" if profile else "") + " ORDER BY b.title",
                     (profile,) if profile else ()).fetchall()
    return [{"id": str(r["id"]), "title": r["title"], "profile": r["profile"]} for r in rows]


def _artifact(c, gid: str, kind: str) -> dict | None:
    row = c.execute("SELECT v.content FROM ed.current_artifact a JOIN ed.artifact_version v ON v.generation_id="
                    "a.generation_id AND v.kind=a.kind AND v.input_digest=a.input_digest WHERE a.generation_id=%s"
                    " AND a.kind=%s ORDER BY v.created_at DESC LIMIT 1", (gid, kind)).fetchone()
    return (row or {}).get("content")


def state(c, gid: str) -> dict:
    """Şu an yayımlanmış özet ve kartın künyesi."""
    return {"book_summary": summary_facts(_artifact(c, gid, "book_summary")),
            "metadata": metadata_facts((_artifact(c, gid, "catalog") or {}).get("metadata") or [])}


def summary_facts(content: dict | None) -> dict:
    if not content:
        return {"status": None}
    pages = sorted({p for s in content.get("sentences", []) for p in s.get("pages", [])})
    return {"status": content.get("status"), "sentences": len(content.get("sentences", [])),
            "pages": [pages[0], pages[-1]] if pages else None, "distinct_pages": len(pages),
            "first": (content.get("sentences") or [{}])[0].get("text", "")[:120]}


def metadata_facts(rows: list[dict]) -> dict:
    out: dict[str, list] = {}
    for r in rows:
        out.setdefault(r.get("subject"), []).append(r.get("claim") or r.get("value"))
    return {k: out[k] for k in META_FIELDS if k in out}


def _light_validation(gid: str) -> dict:
    """Yeniden üretimin doğrulaması: iddialar önceki revizyonda Critic'ten geçti, sayfa yeniden okunmaz;
    değişen yalnız sayfa rolleri ve künye iddiaları (künye iddiası sayfada birebir bulunmadan yazılmaz).
    Regresyon yine koşar; yazanın jetonu dondurmada eşzamanlı editör düzeltmesini yakalar."""
    import uuid
    from . import db, quality
    token = str(uuid.uuid4())
    ctx = db.validation_token.set(token)
    try:
        start = db.one("SELECT knowledge_revision FROM ed.generation_state WHERE generation_id=%s",
                       gid)["knowledge_revision"]
        scope = ensure(gid)
        regression = quality.run_regression_suite(gid)
        return {"critic": None, "actors": None, "contradictions": None, "queued": None,
                "regression_passed": regression["passed"], "writer_token": token, "start_revision": start,
                "mode": "page_scope_rebuild", "page_scope": scope,
                "reason": "yeniden okuma yok: iddialar önceki revizyonda doğrulandı; değişen sayfa rolü ve künye"}
    finally:
        db.validation_token.reset(ctx)


async def _build_outputs(gid: str) -> dict:
    """rebuild.run ile aynı sözleşme (kilit, dondurma, sürümlü yayın, aynı dönüş durumları); doğrulaması
    `_light_validation`."""
    from . import outputs, rebuild
    lock, owner = await asyncio.to_thread(rebuild._lock, gid)
    if lock is None:
        return {"generation_id": gid, "technical_status": "BUSY"}
    try:
        await asyncio.to_thread(rebuild.activate, gid)
        validation = await asyncio.to_thread(_light_validation, gid)
        snap, digest = await asyncio.to_thread(rebuild.freeze, gid, validation)
        built = {}
        for kind in outputs.ORDER:
            key = rebuild.key_for(snap, digest, kind)
            cached = await asyncio.to_thread(rebuild.begin, snap, digest, kind, key)
            if cached is None:
                cached = await rebuild.build(kind, snap, built, key)
            await asyncio.to_thread(rebuild.publish, snap, digest, kind, key, cached)
            built[kind] = cached
        return await asyncio.to_thread(rebuild.finish, snap, digest)
    except rebuild.Superseded as exc:
        return {"generation_id": gid, "technical_status": "SUPERSEDED", "reason": str(exc)}
    except Exception as exc:
        await asyncio.to_thread(rebuild.failed, gid, exc)
        raise
    finally:
        await asyncio.shield(asyncio.to_thread(rebuild._unlock, gid, lock, owner))


async def regenerate(gid: str) -> dict:
    """Gerçek koşu (DB'ye yazar): kural → künye okuması (model; yalnız künye sayfaları) → özet, dizin, rapor,
    katalog. Arşiv nesli arka plandaki tam yeniden kurucuya bırakılmaz (archive._quiet)."""
    from . import archive, catalog, db
    t0 = time.time()
    scope = await asyncio.to_thread(ensure, gid)
    meta = await catalog.extract_metadata(gid)
    built = await _build_outputs(gid)
    if await asyncio.to_thread(archive.hint_of_generation, gid) is not None:
        await asyncio.to_thread(archive._quiet, gid)
    with db.tx() as c:
        after = state(c, gid)
    return {"generation_id": gid, "scope": scope, "metadata_fields": sorted(meta), "outputs": built,
            "after": after, "seconds": round(time.time() - t0, 1)}


# ------------------------------------------------------------------ kuru koşu (yalnız okuma)
class NoRecord:
    """Kuru koşuda model çağrısı ed.model_call'a yazılmaz (oturum salt okuma); kimliği eksi sayıdır."""

    def __enter__(self):
        from . import llm
        self._orig = llm.Llm._record
        seq = iter(range(-1, -10**9, -1))

        async def _record(self_, *a, **k):  # noqa: ANN001
            return next(seq)
        llm.Llm._record = _record
        return self

    def __exit__(self, *exc):
        from . import llm
        llm.Llm._record = self._orig


async def dry_run(gid: str, *, model: bool) -> dict:
    """Ne değişeceği, DB'ye yazmadan: roller, kapsam dışı iddialar, önce/sonra özet ve künye. `model`: özet ve
    künye model çağrısıyla gerçekten denenir (yazılmaz); yoksa özetin girdisi ve yedek özet hesaplanır."""
    from . import catalog, foundation, outputs
    t0 = time.time()
    with foundation.read_snapshot() as c:
        before = state(c, gid)
        p = plan(c, gid)
        roles = {k: dict(v) for k, v in p["roles"].items()}
        for pg, (role, _) in p["writes"].items():
            roles[pg] = {"page_no": pg, "role": role, "source": SOURCE}
        new_out = out_of_scope(roles)
        snap = outputs.capture(c, gid, roles_override=roles)
        rows = c.execute("SELECT kind, source_pages FROM ed.usable_claim WHERE generation_id=%s"
                         " AND kind = ANY(%s)", (gid, list(SCOPED_KINDS))).fetchall()
        excluded = [r for r in rows if scoped(dict(r), new_out)]
    front = sorted(pg for pg, r in roles.items() if r["role"] == "FRONT_MATTER" and r["source"] in SCOPE_SOURCES)
    res = {"generation_id": gid, "before": before,
           "auto_pages": {k: v[1] for k, v in p["found"].items()}, "role_writes": len(p["writes"]),
           "editor_kept": sorted(p["editor_kept"]), "out_of_scope_pages": sorted(new_out),
           "excluded": {k: sum(1 for r in excluded if r["kind"] == k) for k in SCOPED_KINDS},
           "front_matter_pages": front,
           "summary_input_events": sum(1 for cl in snap["claims"] if cl["kind"] == "EVENT")}
    fb = outputs.extractive(snap, [cl for cl in snap["claims"] if cl["kind"] == "EVENT"])
    res["fallback_summary"] = summary_facts({"status": "EXTRACTIVE_FALLBACK", "sentences": fb})
    if model:
        with NoRecord():
            t1 = time.time()
            out = await outputs.summarize(snap, snap["claims"], "Kitabın olay örgüsü özeti", plot_only=True)
            res["after_summary"] = {**summary_facts(out), "attempts": out.get("attempts"),
                                    "seconds": round(time.time() - t1, 1),
                                    "rejected": [f.get("error") for r in out.get("rejected_attempts", [])
                                                 for f in r.get("feedback", [])][:6],
                                    "sentences_text": [(s["pages"], s["text"][:140]) for s in out["sentences"]]}
            if out.get("condensed"):
                res["after_summary"]["parts"] = out["condensed"]["parts"]
            meta = await catalog.ask_metadata(gid, front)
            res["after_metadata"] = {k: v for k, v in meta.items() if k in META_FIELDS}
    res["seconds"] = round(time.time() - t0, 1)
    return res


def row_text(r: dict) -> str:
    b = r["before"]["book_summary"]
    a = r.get("after_summary") or r.get("fallback_summary") or {}
    return (f"{(r.get('title') or '')[:28]:<28} önce {b.get('status')} {b.get('pages')} → sonra {a.get('status')} "
            f"{a.get('pages')} ({a.get('distinct_pages')} sayfa) | kapsam dışı {len(r['out_of_scope_pages'])} s.,"
            f" olay {r['excluded']['EVENT']} | künye s. {r['front_matter_pages']} | meta önce "
            f"{r['before']['metadata'] or '-'} sonra {r.get('after_metadata', '(model denenmedi)')}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m editor.page_scope")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("rebuild", help="okunmuş nesillerde sayfa kuralı + künye + özet/dizin/rapor/kart (okumadan)")
    g = r.add_mutually_exclusive_group(required=True)
    g.add_argument("--generation", action="append")
    g.add_argument("--all-read", action="store_true", help="okuması bitmiş bütün nesiller (tam + arşiv)")
    r.add_argument("--profile", choices=["full", "archive"])
    r.add_argument("--dry-run", action="store_true", help="hiçbir şey yazma; ne değişeceğini raporla")
    r.add_argument("--model", type=int, default=0,
                   help="kuru koşuda ilk N kitapta özet+künye model çağrısıyla gerçekten denenir (yazılmaz)")
    r.add_argument("--json", help="sonuçları bu dosyaya jsonl yaz")
    a = ap.parse_args(argv)
    from . import foundation
    with foundation.read_snapshot() as c:
        gens = read_generations(c, a.profile)
    if a.generation:
        gens = [x for x in gens if x["id"] in set(a.generation)]
    out = open(a.json, "w", encoding="utf-8") if a.json else None
    print(f"{len(gens)} nesil; {'kuru koşu (yazılmaz)' if a.dry_run else 'GERÇEK KOŞU'}", file=sys.stderr)

    async def run_all():
        # tek olay döngüsü: model istemcisi (llm.client) döngüye bağlı
        for i, x in enumerate(gens):
            try:
                res = await (dry_run(x["id"], model=i < a.model) if a.dry_run else regenerate(x["id"]))
            except Exception as e:  # noqa: BLE001 — bir kitap ötekileri durdurmaz
                res = {"generation_id": x["id"], "error": f"{type(e).__name__}: {e}"[:500]}
            res.update(title=x["title"], profile=x["profile"])
            if out:
                out.write(json.dumps(res, ensure_ascii=False, default=str) + "\n")
                out.flush()
            print(row_text(res) if a.dry_run and "error" not in res
                  else json.dumps(res, ensure_ascii=False, default=str)[:600], flush=True)
    asyncio.run(run_all())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
