"""Kapalı küme seçim (`QueuedLlm.choose`) kabulü — test sunucusunda, gerçek model ucuna karşı, kapının içinden.

Koşum (test sunucusu, köprünün env'i ile; Mac'te koşulmaz):

    cd <köprü kaynağı>/backend && set -a && . /etc/nanobase/semantic-bridge.env && set +a \
      && python3 ../scripts/acceptance/llm-choose/accept.py

Denetimler (hepsi geçmeli):
  1. Yapılandırılmış yol gerçekten çalışıyor: her vakada method == "logprobs" (yedek yola düşmüyor).
  2. Olasılıklar normalize: her vakada toplam 1 (±1e-6), hiçbiri eksi değil.
  3. Tek token: istek başına 1 çağrı; coverage raporlanıyor.
  4. Kararlılık: aynı vaka iki kez → aynı seçim, olasılık farkı ≤ 1e-3 (sıcaklık 0).
  5. Çok token'lı seçenekler (kategori yolları) harf etiketiyle seçiliyor; beklenen seçim doğru.
  6. 26'dan çok seçenek: eleme turu, toplam 1, beklenen seçim doğru.
  7. Kapı: her çağrı `sl_llm_queue`'da module='llm-choose-kabul' bileti bıraktı ve biletler DONE.
Temizlik: `--cleanup` kabulün bıraktığı bilet satırlarını siler (başka modülün satırına dokunmaz).
Çıktı: JSON (kanıt olarak docs/ altına ya da ~/llm-gate/evidence/ altına kaydedin).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "backend"))

import sqlalchemy as sa  # noqa: E402

from semantic_layer.candidates.llm_client import LlmClient  # noqa: E402
from semantic_layer.config import SemanticSettings  # noqa: E402
from semantic_layer.runtime.llm_queue import LlmQueue, QueuedLlm  # noqa: E402
from semantic_layer.store import schema as S  # noqa: E402
from semantic_layer.store.catalog_store import open_store  # noqa: E402

MODULE = "llm-choose-kabul"

CASES = [
    {"name": "evet-hayir", "prompt": "Türkiye'nin başkenti Ankara'dır. Bu cümle doğru mu?", "choices": ["evet", "hayır"], "expect": "evet"},
    {"name": "kategori-cok-token", "prompt": "Kitap: «Kanuni Sultan Süleyman ve Dönemi». Özet: 16. yüzyıl Osmanlı İmparatorluğu'nun siyasi ve askeri tarihi. Hangi kategoriye girer?",
     "choices": ["Çocuk Kitapları > Masal", "Tarih > Osmanlı Tarihi", "Kişisel Gelişim > İletişim", "Edebiyat > Şiir"], "expect": "Tarih > Osmanlı Tarihi"},
    {"name": "eposta-sinif", "prompt": "E-posta: «Siparişim 5 gündür kargoya verilmedi, iade etmek istiyorum.» Bu e-posta hangi sınıfa girer?",
     "choices": ["Sipariş / kargo şikâyeti", "Yazar başvurusu", "Basın talebi", "Fatura sorusu"], "expect": "Sipariş / kargo şikâyeti"},
    {"name": "uyum", "prompt": "Kategori: Çocuk > Masal. Özet: Borsa yatırımında teknik analiz yöntemleri. Özet ile kategori uyumlu mu?",
     "choices": ["uyumlu", "çelişkili", "belirsiz"], "expect": "çelişkili"},
]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cleanup", action="store_true", help="kabulün bilet satırlarını sil ve çık")
    args = ap.parse_args()
    s = SemanticSettings.from_env()
    store = open_store(s.store_dsn, create=False)
    Q = S.sl_llm_queue
    if args.cleanup:
        with store.engine.begin() as conn:
            n = conn.execute(Q.delete().where(Q.c.module == MODULE, Q.c.status.in_(("DONE", "ABANDONED")))).rowcount
        print(json.dumps({"cleanup": n}, ensure_ascii=False))
        return 0
    client = LlmClient(s.llm_base, s.llm_model, s.llm_key, s.llm_timeout,
                       extra={"chat_template_kwargs": {"enable_thinking": False}} | s.llm_extra)
    llm = QueuedLlm(client, LlmQueue.from_env(store.engine), purpose=f"std:{MODULE}", module=MODULE,
                    tenant_id=s.tenant_id, datasource_id=s.datasource_id)
    with store.engine.connect() as conn:
        before = conn.execute(sa.select(sa.func.count()).select_from(Q).where(Q.c.module == MODULE)).scalar() or 0

    report: dict = {"model": s.llm_model, "base": s.llm_base, "cases": [], "failures": []}
    calls = 0

    def check(ok: bool, what: str) -> None:
        if not ok:
            report["failures"].append(what)

    for case in CASES:
        first = llm.choose(case["prompt"], case["choices"])
        again = llm.choose(case["prompt"], case["choices"])
        calls += first.calls + again.calls
        report["cases"].append({"name": case["name"], "first": first.as_dict(), "again": again.as_dict()})
        check(first.method == "logprobs", f"{case['name']}: method {first.method} ({first.error})")
        if first.probs is not None:
            check(abs(sum(first.probs.values()) - 1) < 1e-6 and min(first.probs.values()) >= 0, f"{case['name']}: olasılık toplamı 1 değil")
        check(first.calls == 1, f"{case['name']}: {first.calls} çağrı (tek token beklenirdi)")
        check(first.choice == again.choice, f"{case['name']}: iki koşu farklı seçti")
        if first.probability is not None and again.probability is not None:
            check(abs(first.probability - again.probability) <= 1e-3, f"{case['name']}: olasılık oynadı")
        check(first.choice == case["expect"], f"{case['name']}: beklenen {case['expect']!r}, gelen {first.choice!r}")

    many = [f"Konu {i:02d}: {name}" for i, name in enumerate(
        ["masal", "roman", "şiir", "deneme", "tarih", "felsefe", "psikoloji", "din", "bilim", "sanat"] * 4)]
    many[23] = "Konu 23: Osmanlı tarihi"
    big = llm.choose("Kitap: «Osmanlı Devleti'nin kuruluşu». Hangi konu?", many)
    calls += big.calls
    report["rounds"] = big.as_dict()
    check(big.method == "logprobs", f"eleme turu: method {big.method}")
    check(big.probs is not None and abs(sum(big.probs.values()) - 1) < 1e-6, "eleme turu: toplam 1 değil")
    check(big.calls >= 3, f"eleme turu: {big.calls} çağrı (en az 2 grup + final)")
    check(big.choice == many[23], f"eleme turu: beklenen {many[23]!r}, gelen {big.choice!r}")

    with store.engine.connect() as conn:
        rows = conn.execute(sa.select(Q.c.status).where(Q.c.module == MODULE)).scalars().all()
    report["tickets"] = {"new": len(rows) - before, "calls": calls, "statuses": sorted(set(rows))}
    check(len(rows) - before == calls, f"kapı: {calls} çağrı, {len(rows) - before} bilet")
    check(set(rows) <= {"DONE"}, f"kapı: kapanmamış bilet {sorted(set(rows))}")
    report["ok"] = not report["failures"]
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
