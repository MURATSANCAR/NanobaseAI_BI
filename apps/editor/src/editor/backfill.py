"""Tek seferlik geri doldurma: okunmuş nesillerde sessizce düşmüş adımları yeniden koşturur.

    python -m editor.backfill steps --failed [--step proofreading|identity] [--generation G ...] [--apply]

2026-10-01..03 arasında SUCCEEDED kapanan tam okumaların çoğunda son okuma denetimleri («proofreading:
activity Heartbeat timeout») ve ikisinde karakter kimlikleri düştü (iş akışının paylaşılan olay döngüsü
senkron işle tıkanıyordu; editor.offloop). İş akışı artık bunu sessiz geçmiyor («infra-step-retry-v1»);
bu komut eski nesilleri onarır. Okuma yeniden yapılmaz: işin `progress.result.failures` alanında adı
geçen adım, o nesil üstünde iş akışının kullandığı aynı fonksiyonlarla koşturulur.

Varsayılan KURU koşudur: hiçbir şey yazılmaz, hangi nesilde hangi adımın düştüğü ve ne yapılacağı
listelenir. `--apply` ile:

- identity: `knowledge.resolve_character_identity` (altyapı hatası editöre soru olmaz, hata verir) →
  eski «kimlikler birleştirilemedi» sorusu ve iddiası kapatılır (yerini yeni okuma aldı) → çizili
  figürlerin kimliği (`figure_identity.resolve`) → tam okumada karakter sürekliliği → çıktılar yeniden
  kurulur (tam: `rebuild.run`, arşiv: `archive.run_outputs`; meşgulse `editor-rebuild` kuyruğundaki
  istek kalır) → tam okumada son okuma denetimleri baştan (karakterlere bakan denetimler 0 karakterle
  koşmuştu).
- proofreading: `proofing.run_all(resume=True)` — kayıtlı denetim atlanır, eksik olan koşar → çıktılar
  yeniden kurulur.

Adım başarıyla bitince işin `progress.result.failures` alanından o adım düşürülür ve
`progress.result.backfill.<adım>` yazılır (zaman, yapan «ZEKİ AI», özet). Başaramayan adım listede kalır.

Atlanır: mühürlü ya da izlenmeyen nesil, aynı kitap sürümünün daha yeni bir işi (sırada/süren/biten).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time

STEPS = ("identity", "proofreading")
ACTOR = "ZEKİ AI"
#: Profiles whose reading runs the final-read checks (archive defers them to a redaction job).
PROOFREAD = ("full", "redaction")


# ------------------------------------------------------------------ seçim (salt okuma)
CANDIDATES = (
    "SELECT j.id AS job_id, j.profile, j.finished_at, j.book_version_id, j.progress->'result'->'failures' AS failures,"
    " (j.progress->'result'->>'generation_id') AS generation_id, b.title, g.sealed_at, s.origin,"
    " (SELECT count(*) FROM ed.analysis_job n WHERE n.book_version_id=j.book_version_id AND n.id<>j.id"
    "   AND n.created_at>j.created_at AND n.status IN ('QUEUED','RUNNING','SUCCEEDED')"
    "   AND n.profile IS DISTINCT FROM 'redaction') AS newer"
    " FROM ed.analysis_job j JOIN ed.book_version bv ON bv.id=j.book_version_id JOIN ed.book b ON b.id=bv.book_id"
    " LEFT JOIN ed.generation g ON g.id=(j.progress->'result'->>'generation_id')::uuid"
    " LEFT JOIN ed.generation_state s ON s.generation_id=g.id"
    " WHERE j.status='SUCCEEDED' AND j.progress->'result'->'failures' ?| %s::text[]"
    " ORDER BY j.finished_at, j.id")


def failed_steps(failures: dict | None, wanted: tuple[str, ...] = STEPS) -> list[str]:
    """Adı geçen ve boş olmayan, bu komutun onarabildiği adımlar (kimlik önce: denetimler karakterleri okur)."""
    f = failures or {}
    return [s for s in STEPS if s in wanted and f.get(s)]


def skip_reason(row: dict) -> str | None:
    if not row.get("generation_id"):
        return "işte nesil yok"
    if row.get("sealed_at") is not None:
        return "nesil mühürlü"
    if row.get("origin") != "TRACKED":
        return "nesil izlenmiyor"
    if row.get("newer"):
        return "kitap sürümünün daha yeni bir işi var"
    if row.get("profile") not in ("full", "archive", "redaction"):
        return f"profil {row.get('profile')}"
    return None


def state(c, gid: str) -> dict:
    """Nesildeki karakter, çözülmemiş anma ve kayıtlı son okuma denetimi sayısı."""
    from . import proofing
    chars = c.execute("SELECT count(*) AS n FROM ed.character WHERE generation_id=%s", (gid,)).fetchone()["n"]
    loose = c.execute("SELECT count(*) AS n FROM ed.character_mention WHERE generation_id=%s AND character_id IS NULL"
                      " AND via IN ('TEXT','BOTH')", (gid,)).fetchone()["n"]
    versions = {n: str(m.VERSION) for n, m in proofing.checks().items()}
    runs = c.execute("SELECT DISTINCT check_name, check_version FROM ed.proof_run WHERE generation_id=%s"
                     " AND status='SUCCEEDED'", (gid,)).fetchall()
    have = {r["check_name"] for r in runs if versions.get(r["check_name"]) == r["check_version"]}
    return {"characters": chars, "unresolved_mentions": loose, "checks_recorded": len(have),
            "checks_total": len(versions), "checks_missing": sorted(set(versions) - have)}


def plan(wanted: tuple[str, ...] = STEPS, generations: list[str] | None = None) -> list[dict]:
    """Düşmüş adımı olan nesiller ve yapılacak iş (yazmaz)."""
    from . import foundation
    out = []
    with foundation.read_snapshot() as c:
        c.execute("SET LOCAL statement_timeout='120s'")
        for r in c.execute(CANDIDATES, (list(wanted),)).fetchall():
            row = dict(r)
            gid = row["generation_id"]
            if generations and gid not in generations:
                continue
            steps = failed_steps(row["failures"], wanted)
            if not steps:
                continue
            why = skip_reason(row)
            item = {"job_id": str(row["job_id"]), "generation_id": gid, "title": row["title"],
                    "profile": row["profile"], "finished_at": str(row["finished_at"])[:16], "steps": steps,
                    "errors": {s: (row["failures"].get(s) or [""])[0][:120] for s in steps},
                    "other_failures": sorted(k for k, v in (row["failures"] or {}).items() if v and k not in steps)}
            if why:
                item["skip"] = why
            else:
                item["state"] = state(c, gid)
                item["actions"] = actions(steps, row["profile"])
            out.append(item)
    # a generation a reading (e.g. a redaction job on it) is still working on is left alone (batch_guard)
    from . import batch_guard
    running = batch_guard.busy(x["generation_id"] for x in out if not x.get("skip"))
    for x in out:
        if x["generation_id"] in running:
            x["skip"] = running[x["generation_id"]]
            x.pop("actions", None)
    return out


def actions(steps: list[str], profile: str) -> list[str]:
    acts = []
    if "identity" in steps:
        acts += ["kimlik", "eski kimlik sorusu kapanır", "figür kimliği"]
        if profile == "full":
            acts += ["süreklilik"]
    acts.append("çıktılar yeniden kurulur")
    if profile in PROOFREAD and ("identity" in steps or "proofreading" in steps):
        acts.append("son okuma baştan" if "identity" in steps else "son okuma: eksik denetimler")
    return acts


# ------------------------------------------------------------------ uygulama (yazar)
def close_identity_question(gid: str, characters: int) -> int:
    """Kimlik adımının «birleştirilemedi» iddiası ve açık sorusu: yerini yeni okuma aldı."""
    from . import db
    with db.tx() as c:
        claims = [r["id"] for r in c.execute(
            "SELECT id FROM ed.claim WHERE generation_id=%s AND kind='CHARACTER_IDENTITY'"
            " AND (payload->>'identity_failed')::boolean IS TRUE AND status NOT IN ('SUPERSEDED','EDITOR_APPROVED',"
            "'EDITOR_REJECTED','EDITOR_CORRECTED')", (gid,)).fetchall()]
        if not claims:
            return 0
        c.execute("UPDATE ed.review_item SET status='REJECTED', decided_by=%s, decided_at=now(), decision=%s"
                  " WHERE generation_id=%s AND status='OPEN' AND claim_id = ANY(%s)",
                  (ACTOR, db.J({"reason": "kimlik adımı yeniden koşturuldu", "characters": characters}), gid, claims))
        c.execute("UPDATE ed.claim SET status='SUPERSEDED', needs_editor_review=false WHERE id = ANY(%s)", (claims,))
    return len(claims)


def mark_done(job_id: str, step: str, summary: dict) -> None:
    """Adımı işin failures alanından düşürür, backfill kaydını yazar."""
    from . import db
    note = {"at": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "by": ACTOR, **summary}
    db.one("UPDATE ed.analysis_job SET progress = jsonb_set(jsonb_set(progress, '{result,failures}',"
           " coalesce(progress->'result'->'failures', '{}'::jsonb) - %s::text),"
           " '{result,backfill}', coalesce(progress->'result'->'backfill', '{}'::jsonb) || %s)"
           " WHERE id=%s RETURNING id", step, db.J({step: note}), job_id)


def note_checks(job_id: str, lost: list[str]) -> None:
    from . import db
    if lost:
        db.one("UPDATE ed.analysis_job SET progress = jsonb_set(progress, '{result,failures,proofreading_checks}', %s)"
               " WHERE id=%s RETURNING id", db.J(lost), job_id)


#: Altyapı hatasında (bağlantı koptu, model meşgul/açılmıyor: `transient.is_transient`) yeniden denemeden önce
#: beklenen saniyeler. 2026-10-03 onarımında çıktıların yeniden üretimi «bağlantı hatası» ile düşüp öyle kalmıştı.
OUTPUT_RETRY_WAITS = (30.0, 90.0, 180.0)


async def outputs(gid: str, profile: str, waits: tuple[float, ...] | None = None, sleep=asyncio.sleep) -> dict:
    """Çıktıları yeniden kurar. Altyapı hatasında bekleyip yeniden dener; denemeler biter ya da üretici meşgulse
    (BUSY: kilit başka süreçte; CAPACITY_WAIT: kart dolu) iş `editor-rebuild` kuyruğuna bırakılır (`rebuild.requeue`)
    ve QUEUED döner — düşmez. Kitabın içeriğinden gelen hata FAILED olarak raporlanır (yeniden denenmez)."""
    from . import archive, rebuild, transient
    waits = OUTPUT_RETRY_WAITS if waits is None else waits
    for attempt in range(len(waits) + 1):
        try:
            res = await (archive.run_outputs(gid) if profile == "archive" else rebuild.run(gid))
        except Exception as e:  # noqa: BLE001 - the step itself is done; the outputs stay queued / reported
            err = f"{type(e).__name__}: {e}"[:300]
            if not transient.is_transient(e):
                return {"technical_status": "FAILED", "error": err}
            if attempt < len(waits):
                await sleep(waits[attempt])
                continue
            queued = await asyncio.to_thread(rebuild.requeue, gid, "backfill:transient")
            return {"technical_status": "QUEUED" if queued else "FAILED", "error": err, "attempts": attempt + 1}
        status = res.get("technical_status")
        if status in ("BUSY", "CAPACITY_WAIT"):
            queued = await asyncio.to_thread(rebuild.requeue, gid, "backfill:" + status.lower())
            return {"technical_status": "QUEUED" if queued else status, "reason": status}
        return {"technical_status": status}
    raise AssertionError("unreachable")


async def proofread(gid: str, resume: bool) -> tuple[dict, list[str], list[str]]:
    from . import proofing
    out = await proofing.run_all(gid, resume=resume)
    lost = sorted(k for k, v in out.items() if isinstance(v, dict) and "failed" in v)
    transient = sorted(k for k, v in out.items() if isinstance(v, dict) and v.get("transient"))
    return out, lost, transient


async def apply_one(item: dict) -> dict:
    from . import db, figure_identity, knowledge
    from .workflow import activities
    gid, job, profile, steps = item["generation_id"], item["job_id"], item["profile"], item["steps"]
    done: dict = {}
    if "identity" in steps:
        ident = await knowledge.resolve_character_identity(gid, final_attempt=False)
        if ident.get("identity_failed"):
            return {**done, "identity": {"error": "kimlik yine okunamadı (editöre soru açık kaldı)",
                                         "audit": str(ident.get("identity_audit"))[:300]}}
        closed = await asyncio.to_thread(close_identity_question, gid, ident.get("characters", 0))
        visual = await asyncio.to_thread(db.one, "SELECT count(*) AS n FROM ed.character_mention WHERE"
                                         " generation_id=%s AND via='VISUAL'", gid)
        vis = None
        if visual["n"]:
            vis = {k: v for k, v in (await figure_identity.resolve(gid)).items()
                   if k not in ("assignments", "by_figure")}
        cont = None
        if profile == "full":
            cont = len((await activities.continuity_checks(gid))["checked"])
        done["identity"] = {"characters": ident.get("characters"), "confirmed": ident.get("confirmed"),
                            "closed_questions": closed, "visual_identity": vis, "continuity_checked": cont}
    if profile in PROOFREAD and ("identity" in steps or "proofreading" in steps):
        # kimlik yeniden okunduysa karakterlere bakan denetimler de yeniden koşmalı: baştan
        out, lost, transient = await proofread(gid, resume="identity" not in steps)
        done["proofreading"] = {"checks": len(out), "failed_checks": lost, "transient": transient,
                                "resumed": sorted(k for k, v in out.items() if "resumed" in v)}
    built = await outputs(gid, profile)
    for step in steps:
        res = done.get(step)
        if res is None or (step == "proofreading" and res["transient"]):
            continue
        summary = {**res, "outputs": built["technical_status"]}
        await asyncio.to_thread(mark_done, job, step, summary)
        if step == "proofreading":
            await asyncio.to_thread(note_checks, job, res["failed_checks"])
    return {**done, "outputs": built}


# ------------------------------------------------------------------ CLI
def row_text(x: dict) -> str:
    head = f"{x['finished_at']} {x['profile']:<7} {x['generation_id'][:8]} {(x['title'] or '')[:34]:<34} " \
           f"{','.join(x['steps']):<22}"
    if x.get("skip"):
        return head + f" ATLANIR: {x['skip']}"
    s = x["state"]
    return head + (f" karakter {s['characters']}, çözülmemiş anma {s['unresolved_mentions']}, denetim "
                   f"{s['checks_recorded']}/{s['checks_total']} → {'; '.join(x['actions'])}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m editor.backfill")
    sub = ap.add_subparsers(dest="cmd", required=True)
    st = sub.add_parser("steps", help="okunmuş nesillerde düşmüş adımı yeniden koştur (varsayılan kuru)")
    st.add_argument("--failed", action="store_true", required=True,
                    help="işin progress.result.failures alanında adı geçen adımlar")
    st.add_argument("--step", choices=STEPS, action="append", help="yalnız bu adım (tekrar verilebilir)")
    st.add_argument("--generation", action="append", help="yalnız bu nesil (tekrar verilebilir)")
    st.add_argument("--apply", action="store_true", help="gerçekten koştur ve yaz (yoksa yalnız listeler)")
    st.add_argument("--json", help="sonuçları bu dosyaya jsonl yaz")
    a = ap.parse_args(argv)
    wanted = tuple(a.step or STEPS)
    items = plan(wanted, a.generation)
    todo = [x for x in items if not x.get("skip")]
    print(f"{len(items)} nesil, {len(todo)} onarılacak; {'GERÇEK KOŞU' if a.apply else 'kuru koşu (yazılmaz)'}",
          file=sys.stderr)
    out = open(a.json, "w", encoding="utf-8") if a.json else None

    def emit(x: dict, line: str) -> None:
        if out:
            out.write(json.dumps(x, ensure_ascii=False, default=str) + "\n")
            out.flush()
        print(line, flush=True)

    if not a.apply:
        for x in items:
            emit(x, row_text(x))
        return 0

    from . import batch_guard
    skipped = batch_guard.Skipped("backfill steps")
    for x in items:
        if x.get("skip") and str(x["skip"]).startswith("okuma sürüyor"):
            skipped.add(x["generation_id"], x["skip"], x.get("title"))

    async def run_all():
        # tek olay döngüsü: model istemcisi (llm.client) döngüye bağlı
        for x in todo:
            # yazmadan hemen önce yeniden: plan yapılırken bir okuma başlamış olabilir
            if not await asyncio.to_thread(skipped.check, x["generation_id"], x.get("title")):
                continue
            t0 = time.time()
            try:
                res = await apply_one(x)
            except Exception as e:  # noqa: BLE001 — bir kitap ötekileri durdurmaz
                res = {"error": f"{type(e).__name__}: {e}"[:500]}
            x = {**x, "result": res, "seconds": round(time.time() - t0, 1)}
            emit(x, json.dumps({k: x[k] for k in ("generation_id", "title", "steps", "result", "seconds")},
                               ensure_ascii=False, default=str)[:800])
    asyncio.run(run_all())
    skipped.report()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
