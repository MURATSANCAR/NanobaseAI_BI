"""Okunmuş kitapta aynı kişinin birden çok karakter kaydını, kitabı yeniden okumadan birleştirir.

Kural, okumanın kimlik adımındakiyle aynıdır (`identity.same_name_plan`): aynı (katlanmış) adı taşıyan kayıtlar,
türleri / cinsiyetleri / birey-topluluk kapsamları uyuşuyorsa tek kişidir; okuma onları ayrı tuttuysa (aynı sayfada
ikisi de anılıyor ya da aynı okuma penceresi ikisini ayrı grup yaptı) birleştirilmez; kitabın ad gibi yazdığı ad
(cümle ortasında büyük harfle) birleşir. Anlatıcıya göreli birinci tekil akrabalık etiketi («annem», «kız
kardeşim», 2026-10-03) da birleşir, ama kayıtların sayfa aralıkları iç içe geçmiyorsa (çok anlatıcılı kitapta
aynı kesimde iki «annem» iki kişidir: RELATIVE_LABEL_INTERLEAVED). «Kadın», «annesi», «bakan» gibi etiketler
birleşmez. Aynı adın çocuk ve yetişkin kaydı (anlatıda büyüyen kişi, 2026-10-03) tür çatışması sayılmaz: aynı sayfada
birlikte geçmiyor ve sayfa sırası yaşla tutarlıysa birleşir (`identity.life_stage_refusal`); insan↔hayvan gibi öbür tür
çatışmaları reddedilir. Yazılı adlarda farklı sıra sayısı («II. Abdülhamid» / «I. Abdülhamid») ya da farklı baba adı
(«Ahmed oğlu», «bin Ahmed») varsa adaşlar birleşmez. Kısaltma = tam ad («Bee»/«Beatrice») birleştirilmez: kitapta açık eşleme olmadan ön ek benzerliği
güvenli değil. Model çağrısı yoktur.

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

from . import db, source
from .identity import proper_name_test, same_name_plan

_CHARS = ("SELECT ch.id, ch.canonical_name, ch.aliases, ch.kind, ch.traits, ch.identity_status,"
          " ch.identity_confidence, ch.first_page, cl.payload -> 'windows' AS windows,"
          " (SELECT count(*) FROM character_attribute a WHERE a.character_id = ch.id) AS attributes"
          " FROM character ch LEFT JOIN claim cl ON cl.id = ch.claim_id WHERE ch.generation_id = %s")
_PAGES = ("SELECT character_id, array_agg(DISTINCT page_no) AS pages, count(*) AS n FROM character_mention"
          " WHERE generation_id = %s AND character_id IS NOT NULL AND via IN ('TEXT','BOTH') GROUP BY 1")


def _latest_generations() -> list[dict]:
    return db.all_rows(
        "SELECT DISTINCT ON (b.id) g.id, b.title FROM generation g JOIN book_version bv ON bv.id = g.book_version_id"
        " JOIN book b ON b.id = bv.book_id WHERE EXISTS (SELECT 1 FROM character c WHERE c.generation_id = g.id)"
        " ORDER BY b.id, g.created_at DESC")


def plan(generation_id: str) -> dict:
    rows = db.all_rows(_CHARS, generation_id)
    pages = {str(r["character_id"]): r for r in db.all_rows(_PAGES, generation_id)}
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
                      "attributes": int(r["attributes"])})
    text = source.body_text(source.read(generation_id))   # sayfa başlığı/altlığı ad sayımına girmez
    clusters, refused = same_name_plan(units, proper_name_test(text))
    joins = []
    for g in clusters:
        keep, folds = units[g[0]], [units[i] for i in g[1:]]
        joins.append({"name": keep["name"], "keep": keep["id"], "keep_status": keep["status"],
                      "fold": [f["id"] for f in folds], "fold_status": [f["status"] for f in folds],
                      "blocked_by_attributes": [f["id"] for f in folds if f["attributes"]],
                      "mentions_moved": sum(f["n"] for f in folds)})
    return {"generation_id": generation_id, "characters": len(units),
            "records_folded": sum(len(j["fold"]) for j in joins),
            "records_blocked": sum(len(j["blocked_by_attributes"]) for j in joins),
            "characters_after": len(units) - sum(len(j["fold"]) - len(j["blocked_by_attributes"]) for j in joins),
            "joins": joins, "refused": refused, "_units": {u["id"]: u for u in units}}


def apply(p: dict) -> dict:
    gid, units, done = p["generation_id"], p["_units"], []
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
            aliases = list(dict.fromkeys(keep["aliases"] + [a for f in folds for a in f["aliases"]
                                                            if a != keep["name"]]))
            confirmed = keep["status"] == "CONFIRMED" or (
                keep["confidence"] >= 0.85 and any(f["status"] == "CONFIRMED" for f in folds))
            first = min([x for x in [keep["first_page"], *(f["first_page"] for f in folds)] if x is not None],
                        default=None)
            c.execute("UPDATE character SET aliases=%s, first_page=%s, identity_status=%s WHERE id=%s",
                      (aliases, first, "CONFIRMED" if confirmed else keep["status"], keep["id"]))
            done.append({"name": j["name"], "folded": len(folds)})
    return {"generation_id": gid, "applied": done}


def main() -> None:
    ap = argparse.ArgumentParser(prog="identity_fold")
    ap.add_argument("--generation", action="append", default=[])
    ap.add_argument("--apply", action="store_true", help="yaz (yoksa kuru koşu)")
    ap.add_argument("--details", action="store_true", help="birleşen ve reddedilen her çift")
    args = ap.parse_args()
    gens = [{"id": g, "title": ""} for g in args.generation] or _latest_generations()
    total = {"generations": 0, "records_folded": 0, "records_blocked": 0}
    for g in gens:
        p = plan(str(g["id"]))
        total["generations"] += 1
        total["records_folded"] += p["records_folded"]
        total["records_blocked"] += p["records_blocked"]
        line = {"title": g.get("title"), **{k: v for k, v in p.items() if k != "_units"}}
        if not args.details:
            line["joins"] = [{"name": j["name"], "records": 1 + len(j["fold"]),
                              "blocked": len(j["blocked_by_attributes"])} for j in p["joins"]]
            line["refused"] = dict(Counter(r["reason"] for r in p["refused"]))
        if args.apply and p["joins"]:
            line["result"] = apply(p)
        print(json.dumps(line, ensure_ascii=False, default=str), flush=True)
    print(json.dumps({"total": total, "dry_run": not args.apply}, ensure_ascii=False))


if __name__ == "__main__":
    main()
