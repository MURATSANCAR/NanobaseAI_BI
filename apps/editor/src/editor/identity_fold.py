"""Okunmuş kitapta aynı kişinin birden çok karakter kaydını, kitabı yeniden okumadan birleştirir.

Kural, okumanın kimlik adımındakiyle aynıdır (`identity_links.link_plan`, içinde `identity.same_name_plan`): aynı
(katlanmış) adı taşıyan kayıtlar, türleri / cinsiyetleri / birey-topluluk kapsamları uyuşuyorsa tek kişidir; okuma
onları ayrı tuttuysa (aynı sayfada ikisi de anılıyor ya da aynı okuma penceresi ikisini ayrı grup yaptı)
birleştirilmez; kitabın ad gibi yazdığı ad (cümle ortasında büyük harfle) birleşir. Anlatıcıya göreli birinci tekil
akrabalık etiketi («annem», «kız kardeşim», 2026-10-03) da birleşir, ama kayıtların sayfa aralıkları iç içe
geçmiyorsa (çok anlatıcılı kitapta aynı kesimde iki «annem» iki kişidir: RELATIVE_LABEL_INTERLEAVED). Aynı adın
çocuk ve yetişkin kaydı (anlatıda büyüyen kişi) tür çatışması sayılmaz: aynı sayfada birlikte geçmiyor ve sayfa sırası
yaşla tutarlıysa birleşir (`identity.life_stage_refusal`); «Ad + abla/abi/teyze…» kaydının hitaptan çıkan yaşı bu
kararda sayılmaz, yalnız metindeki yaş sayılır (K19); insan↔hayvan gibi öbür tür çatışmaları reddedilir. Yazılı
adlarda farklı sıra sayısı («II. Abdülhamid» / «I. Abdülhamid») ya da farklı baba adı («Ahmed oğlu», «bin Ahmed»)
varsa adaşlar birleşmez.

2026-10-03 (K16–K18, `identity_links`): kısaltma / takma ad = tam ad («Bee» / «Beatrice») YALNIZ kitapta açık eşleme
cümlesi varsa birleşir (kanıt cümlesi ve sayfası kayda yazılır: traits.identity_links); ön ek benzerliği tek başına
asla. Birinci şahıs anlatıda anlatıcı tek ve kanıtlıysa «Babam» ile «<anlatıcı>'nın babası» bir kişidir. Aynı adsız
etiket («anne» / «Annesi»; «Kadın» ×4) aynı sahiplikle ve iç içe geçmeyen sayfalarda tek kayda katlanır. Bir diğer
ad iki kişinin kaydındaysa: sahibi belliyse yanlış kayıttan çıkarılır (o adla yapılan anmalar sahibine taşınır),
değilse iki kayıt işaretlenir (traits.alias_conflicts). Her kayda `traits.unnamed` (kitap adı ad gibi yazmıyor)
yazılır: ekranda adsız ve az anılan figüran «diğer kişiler» altında gösterilir. Model çağrısı yoktur.

    python -m editor.identity_fold [--generation GID ...]            # kuru koşu (varsayılan): yalnız okur
    python -m editor.identity_fold --generation GID --apply           # yazar

Kuru koşu hiçbir şey yazmaz; salt okuma oturumunda da çalışır (PGOPTIONS='-c default_transaction_read_only=on').
--generation verilmezse her kitabın en son okuması.

`--apply` tek işlemde: birleşen kaydın anmaları, duyguları, olay rolleri ve özellik okuma kayıtları ana kayda
taşınır; adları ana kaydın diğer adlarına eklenir; birleşen kayıt silinir. Özellik defteri (character_attribute)
yalnız eklenir, değiştirilemez: kaydına özellik yazılmış bir kayıt birleştirilmez, raporda «özellik defteri»
olarak sayılır (o kitap yeniden okunmalıdır). Veritabanı tetikleyicileri bilgi sürümünü artırır ve çıktıların
yeniden kurulmasını ister.
"""

from __future__ import annotations

import argparse
import json
from collections import Counter

from . import batch_guard, db, source
from .identity import proper_name_test, same_name_plan  # noqa: F401 - same rule as the reading
from .identity import family_address, name_key
from . import identity_links

_CHARS = ("SELECT ch.id, ch.canonical_name, ch.aliases, ch.kind, ch.traits, ch.identity_status,"
          " ch.identity_confidence, ch.first_page, ch.description, cl.payload -> 'windows' AS windows,"
          " (SELECT count(*) FROM character_attribute a WHERE a.character_id = ch.id) AS attributes"
          " FROM character ch LEFT JOIN claim cl ON cl.id = ch.claim_id WHERE ch.generation_id = %s")
_PAGES = ("SELECT character_id, array_agg(DISTINCT page_no) AS pages, count(*) AS n FROM character_mention"
          " WHERE generation_id = %s AND character_id IS NOT NULL AND via IN ('TEXT','BOTH') GROUP BY 1")
_QUOTES = ("SELECT cm.character_id, cm.via, e.quote FROM character_mention cm JOIN evidence e ON e.id = cm.evidence_id"
           " WHERE cm.generation_id = %s AND cm.character_id IS NOT NULL")


def _latest_generations() -> list[dict]:
    return db.all_rows(
        "SELECT DISTINCT ON (b.id) g.id, b.title FROM generation g JOIN book_version bv ON bv.id = g.book_version_id"
        " JOIN book b ON b.id = bv.book_id WHERE EXISTS (SELECT 1 FROM character c WHERE c.generation_id = g.id)"
        " ORDER BY b.id, g.created_at DESC")


def _title(generation_id: str) -> str:
    r = db.one("SELECT b.title FROM generation g JOIN book_version bv ON bv.id = g.book_version_id"
               " JOIN book b ON b.id = bv.book_id WHERE g.id = %s", generation_id)
    return (r or {}).get("title") or ""


def plan(generation_id: str, title: str | None = None) -> dict:
    rows = db.all_rows(_CHARS, generation_id)
    if not rows:                # nothing read (not a book, identity unresolved): the book's text is not loaded
        return {"generation_id": generation_id, "characters": 0, "records_folded": 0, "records_blocked": 0,
                "characters_after": 0, "joins": [], "refused": [], "narrator": None, "alias_conflicts": [],
                "unnamed": 0, "minor": 0, "_unnamed": {}, "_units": {}}
    pages = {str(r["character_id"]): r for r in db.all_rows(_PAGES, generation_id)}
    addressed = {str(r["id"]) for r in rows if family_address(r["canonical_name"])}
    quotes: dict[str, list[str]] = {}        # every mention's quote: the K19 age evidence of an address record
    text_quotes: dict[str, list[str]] = {}   # text mentions' quotes: is the name written as a name there
    for q in (db.all_rows(_QUOTES, generation_id) if rows else []):
        cid = str(q["character_id"])
        quotes.setdefault(cid, []).append(q["quote"] or "")
        if q["via"] in ("TEXT", "BOTH"):
            text_quotes.setdefault(cid, []).append(q["quote"] or "")
    units = []
    for r in rows:
        tr = r["traits"] or {}
        p = pages.get(str(r["id"]))
        units.append({"id": str(r["id"]), "name": r["canonical_name"], "kind": r["kind"],
                      "sex": tr.get("sex"), "entity_scope": tr.get("entity_scope"),
                      "pages": set(p["pages"]) if p else set(), "n": int(p["n"]) if p else 0,
                      "windows": {w.get("window") for w in (r["windows"] or []) if isinstance(w, dict)} - {None},
                      "status": r["identity_status"], "confidence": float(r["identity_confidence"]),
                      "aliases": list(r["aliases"] or []), "first_page": r["first_page"],
                      "description": r["description"] or "",
                      "attributes": int(r["attributes"]), "traits": tr,
                      "quotes": text_quotes.get(str(r["id"]), []),
                      "age_evidence": identity_links.text_stage(quotes.get(str(r["id"]), []))
                      if str(r["id"]) in addressed else None})
    read = source.read(generation_id)
    text = source.body_text(read)   # sayfa başlığı/altlığı ad sayımına girmez
    by_page = {p["page_no"]: source.body_text([p]) for p in read}
    proper = proper_name_test(text)
    lp = identity_links.link_plan(units, by_page, proper, title if title is not None else _title(generation_id))
    joins = []
    for g in lp["clusters"]:
        keep, folds = units[g[0]], [units[i] for i in g[1:]]
        keys = {name_key(units[i]["name"]) for i in g}
        rules = [x for x in lp["links"] if {name_key(nm) for nm in x.get("names") or []} & keys]
        joins.append({"name": keep["name"], "keep": keep["id"], "keep_status": keep["status"],
                      "fold": [f["id"] for f in folds], "fold_status": [f["status"] for f in folds],
                      "fold_names": [f["name"] for f in folds],
                      "rules": sorted({x["rule"] for x in rules}),
                      "evidence": [{k: x[k] for k in ("rule", "pattern", "names", "page", "quote", "narrator", "owner")
                                    if x.get(k) is not None} for x in rules if x["rule"] != "SAME_NAME"],
                      "blocked_by_attributes": [f["id"] for f in folds if f["attributes"]],
                      "mentions_moved": sum(f["n"] for f in folds)})
    unnamed = {u["id"]: not proper(u["name"]) for u in units}
    conflicts = [{"alias": c["alias"], "action": c["action"], "records": c["records"],
                  "owner": units[c["owner"]]["id"] if c.get("owner") is not None else None,
                  "holders": [units[i]["id"] for i in c["holders"]]} for c in lp["alias_conflicts"]]
    return {"generation_id": generation_id, "characters": len(units),
            "records_folded": sum(len(j["fold"]) for j in joins),
            "records_blocked": sum(len(j["blocked_by_attributes"]) for j in joins),
            "characters_after": len(units) - sum(len(j["fold"]) - len(j["blocked_by_attributes"]) for j in joins),
            "joins": joins, "refused": lp["refused"], "narrator": lp["narrator"], "alias_conflicts": conflicts,
            "unnamed": sum(unnamed.values()),
            "minor": sum(1 for u in units if unnamed[u["id"]] and u["n"] <= 2),
            "_unnamed": unnamed, "_units": {u["id"]: u for u in units}}


def apply(p: dict) -> dict:
    gid, units, done = p["generation_id"], p["_units"], []
    alias_now: dict[str, list] = {}
    with db.tx() as c:
        for j in p["joins"]:
            keep = units[j["keep"]]
            folds = [units[f] for f in j["fold"] if f not in j["blocked_by_attributes"]]
            if not folds:
                continue
            for f in folds:
                c.execute("UPDATE character_mention SET character_id=%s WHERE generation_id=%s AND character_id=%s",
                          (keep["id"], gid, f["id"]))
                c.execute("UPDATE emotion SET character_id=%s WHERE generation_id=%s AND character_id=%s",
                          (keep["id"], gid, f["id"]))
                c.execute("UPDATE character_attribute_read SET character_id=%s WHERE generation_id=%s"
                          " AND character_id=%s", (keep["id"], gid, f["id"]))
                # one row per (event, character): the main record's own reading stands
                c.execute("DELETE FROM event_actor f USING event_actor k WHERE f.generation_id=%s AND"
                          " f.character_id=%s AND k.character_id=%s AND k.event_id=f.event_id",
                          (gid, f["id"], keep["id"]))
                c.execute("UPDATE event_actor SET character_id=%s WHERE generation_id=%s AND character_id=%s",
                          (keep["id"], gid, f["id"]))
                c.execute("DELETE FROM character WHERE id=%s AND generation_id=%s", (f["id"], gid))
            # a folded record's own name becomes another name of the person — unless it is no name («anne»)
            aliases = list(dict.fromkeys(keep["aliases"] + [
                a for f in folds for a in ([] if p["_unnamed"].get(f["id"]) else [f["name"]]) + f["aliases"]
                if a != keep["name"]]))
            alias_now[keep["id"]] = aliases
            confirmed = keep["status"] == "CONFIRMED" or (
                keep["confidence"] >= 0.85 and any(f["status"] == "CONFIRMED" for f in folds))
            first = min([x for x in [keep["first_page"], *(f["first_page"] for f in folds)] if x is not None],
                        default=None)
            c.execute("UPDATE character SET aliases=%s, first_page=%s, identity_status=%s WHERE id=%s",
                      (aliases, first, "CONFIRMED" if confirmed else keep["status"], keep["id"]))
            if j["evidence"]:
                # the sentence of the book that joined them stays with the record (K16/K17/K18)
                c.execute("UPDATE character SET traits = traits || jsonb_build_object('identity_links',"
                          " coalesce(traits->'identity_links', '[]'::jsonb) || %s::jsonb) WHERE id=%s",
                          (json.dumps(j["evidence"], ensure_ascii=False), keep["id"]))
            done.append({"name": j["name"], "folded": len(folds)})
        gone = {f for j in p["joins"] for f in j["fold"] if f not in j["blocked_by_attributes"]}
        fixed = []
        for cf in p["alias_conflicts"]:
            holders = [h for h in cf["holders"] if h not in gone]
            if cf["action"] == "fix" and cf["owner"] not in gone:
                # the book says whose name it is: off the wrong record, the mentions made with it to the owner
                for h in holders:
                    moved = [r["id"] for r in c.execute(
                        "SELECT id, surface_name FROM character_mention WHERE generation_id=%s AND character_id=%s",
                        (gid, h)).fetchall() if name_key(r["surface_name"] or "") == cf["alias"]]
                    if moved:
                        c.execute("UPDATE character_mention SET character_id=%s WHERE id = ANY(%s)",
                                  (cf["owner"], moved))
                    c.execute("UPDATE character SET aliases=%s WHERE id=%s",
                              ([a for a in alias_now.get(h, units[h]["aliases"]) if name_key(a) != cf["alias"]], h))
                fixed.append(cf["alias"])
                continue
            mark = {"alias": cf["alias"], "records": cf["records"]}
            for h in holders:
                # once per conflict: the fold runs again on every output rebuild (rebuild.validate)
                if mark in (units[h]["traits"].get("alias_conflicts") or []):
                    continue
                c.execute("UPDATE character SET traits = traits || jsonb_build_object('alias_conflicts',"
                          " coalesce(traits->'alias_conflicts', '[]'::jsonb) || %s::jsonb) WHERE id=%s",
                          (json.dumps([{"alias": cf["alias"], "records": cf["records"]}], ensure_ascii=False), h))
        for cid, flag in p["_unnamed"].items():
            if cid not in gone and units[cid]["traits"].get("unnamed") != flag:
                c.execute("UPDATE character SET traits = traits || jsonb_build_object('unnamed', %s::boolean)"
                          " WHERE id=%s", (flag, cid))
    return {"generation_id": gid, "applied": done, "alias_fixed": fixed}


def brief(p: dict) -> dict:
    """A plan's report without the private fields: joined names and refusals by reason."""
    return {**{k: v for k, v in p.items() if not k.startswith("_") and k not in ("joins", "refused")},
            "joins": [{"name": j["name"], "records": 1 + len(j["fold"]), "rules": j["rules"],
                       "blocked": len(j["blocked_by_attributes"])} for j in p["joins"]],
            "refused": dict(Counter(r["reason"] for r in p["refused"]))}


def run(generation_id: str, title: str | None = None) -> dict:
    """Plan and apply for one generation, for the process that owns it: the reading's own step after identity
    (workflow «identity-fold-v1») and every output validation (rebuild.validate, archive.validate). No
    batch_guard here: the caller's own job is the QUEUED/RUNNING one it would refuse. Running it again is
    harmless: a folded record is gone, a flagged conflict is not flagged twice, `unnamed` is written only when it
    changes — a second run writes nothing."""
    p = plan(generation_id, title)
    out = brief(p)
    if p["joins"] or p["alias_conflicts"] or p["_unnamed"]:
        out["result"] = apply(p)
    return out


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="identity_fold")
    ap.add_argument("--generation", action="append", default=[])
    ap.add_argument("--apply", action="store_true", help="yaz (yoksa kuru koşu)")
    ap.add_argument("--details", action="store_true", help="birleşen ve reddedilen her çift")
    args = ap.parse_args(argv)
    gens = [{"id": g, "title": None} for g in args.generation] or _latest_generations()
    total = {"generations": 0, "records_folded": 0, "records_blocked": 0}
    rules: Counter = Counter()
    # a generation a reading is still working on is never folded (2026-10-05: --apply deleted the characters of
    # a running reading → FK error and SUPERSEDED, two readings failed); listed at the end
    skipped = batch_guard.Skipped("identity_fold")
    for g in gens:
        if not skipped.check(str(g["id"]), g.get("title")):
            continue
        p = plan(str(g["id"]), g.get("title"))
        total["generations"] += 1
        total["records_folded"] += p["records_folded"]
        total["records_blocked"] += p["records_blocked"]
        for j in p["joins"]:
            rules.update(j["rules"])
        line = {"title": g.get("title"), **({k: v for k, v in p.items() if not k.startswith("_")}
                                             if args.details else brief(p))}
        if args.apply and (p["joins"] or p["alias_conflicts"] or p["_unnamed"]):
            # checked again right before writing: a reading may have started while the plan was made
            if skipped.check(str(g["id"]), g.get("title")):
                line["result"] = apply(p)
            else:
                line["result"] = {"skipped": skipped.items[-1]["reason"]}
        print(json.dumps(line, ensure_ascii=False, default=str), flush=True)
    print(json.dumps({"total": {**total, "joins_by_rule": dict(rules)}, "dry_run": not args.apply,
                      "skipped_running": [x["generation_id"] for x in skipped.items]}, ensure_ascii=False))
    skipped.report()


if __name__ == "__main__":
    main()
