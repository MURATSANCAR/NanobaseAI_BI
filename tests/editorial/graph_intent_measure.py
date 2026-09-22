"""Sohbet karakter ağı niyet kararının (GRAPH_INTENT) kararlılık/isabet ölçümü.

Test sunucusunda köprünün venv'i ve ORTAMIYLA koşar — `LLM_EXTRA_BODY_JSON` (düşünme kapalı)
yüklenmezse model boş cevap verir:
  sudo systemd-run --unit graph-intent --collect -p EnvironmentFile=/etc/nanobase/semantic-bridge.env \
    --working-directory=/tmp /data/nanobaseai/bi/semantic-venv/bin/python graph_intent_measure.py
Sonuç JSONL (OUT); özet için aynı dizindeki graph_intent_summary.py.
Karar (2026-09-22): graf yalnız karakterler ARASI bağ sorusunda çıkar; beklenen cevaplar ona göre.
"""

from __future__ import annotations
import json, os, sys, time

sys.path.insert(0, os.environ.get("BRIDGE_SRC", "/data/nanobaseai/bi/frontend/backend"))
from semantic_layer.config import SemanticSettings          # noqa: E402
from semantic_layer.candidates.llm_client import LlmClient   # noqa: E402
from semantic_bridge.editorial_cards import GRAPH_INTENT     # noqa: E402

RUNS = 5
OUT = os.environ.get("OUT", "/tmp/graph-intent/results.jsonl")

# (grup, soru, beklenen, gerekçe)
QUESTIONS = [
    ("a", "Kitapta kimler var?", True, "Doğrudan karakter listesi isteniyor."),
    ("a", "Aytek kimlerle birlikte?", True, "Bir karakterin birlikte göründüğü kişiler soruluyor."),
    ("a", "Zeynep ile Murat'ın ilişkisi nedir?", True, "İki karakter arasındaki ilişki soruluyor."),
    ("a", "Romandaki karakterleri sayar mısın?", True, "Karakter kadrosu isteniyor."),
    ("a", "Ali'nin ailesi kimlerden oluşuyor?", True, "Aile bağı bir karakter ilişkisidir."),
    ("a", "Hangi karakterler birbirine en yakın?", True, "Karakterler arası yakınlık soruluyor."),
    ("a", "Baş kahramanın arkadaşları kimler?", True, "Arkadaşlık bağı soruluyor."),
    ("a", "Selim en çok kiminle sahne paylaşıyor?", True, "Birlikte görünme sıklığı soruluyor."),
    ("a", "Kitaptaki karakterler arasındaki ilişkileri anlat", True, "Doğrudan ilişki ağı isteniyor."),
    ("a", "Defne ile babası arasında nasıl bir bağ var?", True, "İki kişi arasındaki bağ soruluyor."),
    ("a", "Anlatıda kaç karakter var ve kimler?", True, "Karakter sayısı ve adları soruluyor."),
    ("a", "Emre kimin kardeşi?", True, "Akrabalık bağı soruluyor."),

    ("b", "Kitabın teması ne?", False, "Tema, kişilerle değil metnin fikriyle ilgili."),
    ("b", "Kitap kaç sayfa?", False, "Künye bilgisi, karakterle ilgisi yok."),
    ("b", "Hangi kitaplar okundu?", False, "Kitap listesi soruluyor, kişi değil."),
    ("b", "14. sayfada ne oluyor?", False, "Belirli bir sayfadaki olay soruluyor."),
    ("b", "Kitabın dili akıcı mı?", False, "Üslup değerlendirmesi."),
    ("b", "Bu kitabın türü nedir?", False, "Tür sınıflandırması."),
    ("b", "Kitapta kaç bölüm var?", False, "Yapısal künye bilgisi."),
    ("b", "Kitabın sonu nasıl bitiyor?", False, "Olay örgüsünün sonu, ilişki ağı değil."),
    ("b", "Kitabın yayın tarihi nedir?", False, "Künye bilgisi."),
    ("b", "Metinde imla hatası var mı?", False, "Dil denetimi."),
    ("b", "Kitabın özetini çıkarır mısın?", False, "Özet isteniyor; kişi ağı sorulmuyor."),
    ("b", "Bu kitap hangi şehirde geçiyor?", False, "Mekân sorusu."),

    ("c", "Ana karakter kim?", True, "Karakterle ilgili; ağda merkez karakteri gösterir."),
    ("c", "Aytek kimdir?", True, "Tek bir karakter soruluyor, ağ bağlamı anlamlı."),
    ("c", "Kitabı kim yazdı?", False, "Yazar kitabın kişisi değil, künye bilgisi."),
    ("c", "Merhaba", False, "Selamlaşma; kitapla bile ilgili değil."),
    ("c", "Nasılsın?", False, "Sohbet açılışı."),
    ("c", "Kitabın kahramanı hangi mesleği yapıyor?", True, "Bir karakterin özelliği soruluyor."),
    ("c", "Bu kitaptaki en sevilen karakter hangisi?", True, "Karakter sorusu."),
    ("c", "Yayınevi kim?", False, "'kim' geçiyor ama kurum soruluyor; tuzak."),
    ("c", "Editör kim?", False, "Kitabın çalışanı, kurgu karakteri değil."),
    ("c", "Anlatıcı kim?", True, "Anlatıcı metnin içindeki bir kişidir (sınırda)."),
    ("c", "Teşekkürler, çok iyi oldu", False, "Kapanış cümlesi, soru bile değil."),
    ("c", "Kitapta geçen mekanlar neler?", False, "Mekân sorusu, kişi değil."),
]


def parse(raw: str):
    """Köprüdeki çözümlemenin aynısı: JSON değilse karar 'hata'."""
    try:
        text = raw.strip().removeprefix("```json").removesuffix("```").strip()
        return bool(json.loads(text).get("graph"))
    except Exception:
        return None


def main() -> None:
    s = SemanticSettings.from_env()
    llm = LlmClient(s.llm_base, s.llm_model, s.llm_key, s.llm_timeout, extra=s.llm_extra)
    print(f"model={s.llm_model} base={s.llm_base} extra={s.llm_extra} runs={RUNS} sorular={len(QUESTIONS)}", flush=True)
    with open(OUT, "w", encoding="utf-8") as f:
        for i, (group, q, expected, why) in enumerate(QUESTIONS, 1):
            for run in range(1, RUNS + 1):
                t0 = time.monotonic()
                try:
                    raw = llm.chat([{"role": "system", "content": GRAPH_INTENT},
                                    {"role": "user", "content": q}], max_tokens=20, temperature=0.0)
                    err = ""
                except Exception as e:  # ölçüm sürsün
                    raw, err = "", f"{type(e).__name__}: {e}"
                rec = {"n": i, "group": group, "question": q, "expected": expected, "why": why,
                       "run": run, "raw": raw, "decision": parse(raw) if not err else None,
                       "error": err, "sec": round(time.monotonic() - t0, 2)}
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
                f.flush()
                print(f"{i:02d}/{run} [{group}] {rec['decision']} ({rec['sec']}s) {q[:40]}", flush=True)
    print("BITTI", flush=True)


if __name__ == "__main__":
    main()
