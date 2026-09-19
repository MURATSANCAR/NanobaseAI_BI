"""Doğrulanmış cevaplar bozuldu mu? Bir test koşusunu, soruların daha önceki cevaplarıyla karşılaştırır.

    testset_regress.py <questions.jsonl> <run.jsonl> --before "2026-09-18 08:30+00" [--tolerance 0.005]

Sunucuda koşar (gerçek köprünün `sl_query_log` kaydını okur; SEMANTIC_STORE_DSN gerekir). Temel çizgi,
her sorunun `--before` anından önceki SON cevabıdır: o an, doğrulamanın bittiği andır (karne). Bir
düzeltme bir soruyu açarken başka bir soruyu kapatabiliyor — kural bütçesi, kaynak oylaması, yeni bir
eş anlamlı — ve bu ancak bütün set yeniden sorulup eski cevapla karşılaştırılınca görünür.

Çıkış kodu: bozulan doğrulanmış cevap varsa 1. Satır sayısı canlı veride oynar; `--tolerance` kadar
fark bozulma sayılmaz. Cevap tipinin değişmesi (cevap → ret, ret → cevap) her zaman listelenir.
"""
import json
import os
import sys

import sqlalchemy as sa


def _arg(name: str, default: str) -> str:
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


def main() -> int:
    questions, run = sys.argv[1], sys.argv[2]
    before = _arg("--before", "")
    tolerance = float(_arg("--tolerance", "0.005"))
    if not before:
        print("--before <zaman> gerekli: temel çizginin bittiği an")
        return 2
    order = {json.loads(line)["id"]: n for n, line in enumerate(open(questions, encoding="utf-8"), 1)}
    rows = [json.loads(line) for line in open(run, encoding="utf-8")]
    engine = sa.create_engine(os.environ["SEMANTIC_STORE_DSN"])
    broken, opened, same, unknown = [], [], 0, 0
    with engine.connect() as conn:
        for rec in sorted(rows, key=lambda r: order.get(r["id"], 0)):
            base = conn.execute(sa.text(
                "select answer_type, row_count from sl_query_log where question = :q and created_at < :t "
                "order by created_at desc limit 1"), {"q": rec["soru"], "t": before}).fetchone()
            if base is None or base[0] is None:
                unknown += 1
                continue
            old_type, old_rows = base[0], base[1]
            new_type, new_rows = rec.get("type"), rec.get("rows")
            label = f"Q{order.get(rec['id'], 0)} {rec['id']}"
            if old_type == "TEXT_TO_SQL" and new_type != "TEXT_TO_SQL":
                broken.append(f"{label}: cevap ({old_rows} satır) → {new_type}: {(rec.get('explanation') or '')[:140]}")
            elif old_type != "TEXT_TO_SQL" and new_type == "TEXT_TO_SQL":
                opened.append(f"{label}: {old_type} → cevap ({new_rows} satır)")
            elif old_type == new_type == "TEXT_TO_SQL" and old_rows is not None and new_rows is not None \
                    and abs(new_rows - old_rows) > max(1, tolerance * max(old_rows, 1)):
                broken.append(f"{label}: satır sayısı {old_rows} → {new_rows}")
            else:
                same += 1
    print(f"aynı {same} · bozulan {len(broken)} · açılan {len(opened)} · temel çizgisi olmayan {unknown}")
    for line in broken:
        print("  BOZULDU ", line)
    for line in opened:
        print("  AÇILDI  ", line)
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
