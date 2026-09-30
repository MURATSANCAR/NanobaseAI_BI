#!/usr/bin/env python3
"""Bir .po dosyasındaki boş Türkçe çevirileri ZEKİ AI modeliyle doldurur.

Model LLM kapısından gider (arka plan önceliği, modül `destek-ceviri`): BI'ın
etkileşimli sorularının önüne geçmez. Test sunucusunda koşar:

    PYTHONPATH=/data/nanobaseai/bi/frontend/backend:<polib yolu> \
    /data/nanobaseai/bi/semantic-venv/bin/python cevir.py <po> [<po> ...] \
        --env /etc/nanobase/semantic-bridge.env [--sozluk <po>] [--parti 40]

Kurallar:
- Yalnız msgstr'ı boş girdiler çevrilir; dolu çeviriye dokunulmaz.
- Yer tutucular ({0}, {name}, %s, %(x)s), HTML etiketleri, baştaki/sondaki boşluk ve
  satır sonları birebir korunmalı; tutmayan cevap bir kez yeniden sorulur, yine
  tutmazsa girdi boş kalır (İngilizce görünür) ve rapora yazılır.
- Ürün/teknoloji adı ekrana çıkmaz: çatı ve ürün adları → ZEKİ AI.
- Her parti bitince dosya diske yazılır; yarıda kalan koşu kaldığı yerden devam eder.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time

import polib

GLOSSARY = """\
Terim sözlüğü (tutarlı kullan):
- Ticket → Kayıt (çoğul: Kayıtlar); Tickets → Kayıtlar
- Agent (destek personeli) → Temsilci; Agent (yapay zekâ ajanı, Flow Agent) → Ajan
- Customer → Müşteri; Contact → Kişi; Team → Ekip
- Knowledge Base → Bilgi Bankası; Article → Makale; Category → Kategori
- Canned Response / Saved Reply → Hazır Yanıt
- SLA → SLA (hizmet seviyesi); Priority → Öncelik; Status → Durum
- Assignment Rule → Atama Kuralı; Escalation → Yükseltme
- Doctype/DocType → Belge Türü; Record → Kayıt; Field → Alan; Workspace → Çalışma Alanı
- Desk → Masaüstü; Portal → Portal; Dashboard → Pano; Report → Rapor
- Frappe, Frappe Framework, Helpdesk (ürün adı), Flow (ürün adı), ERPNext dışı ürün adları → ZEKİ AI
- E-posta, e-posta hesabı; Settings → Ayarlar
"""

SYSTEM = (
	"Sen bir yazılım arayüzü çevirmenisin. İngilizce arayüz metinlerini doğal, kısa ve resmî "
	"(siz diliyle) Türkçeye çevirirsin. Düğme ve başlıklarda kısa kal, cümle ise cümle çevir.\n"
	"KESİN KURALLAR:\n"
	"1. {0}, {1}, {name}, %s, %d, %(x)s gibi yer tutucuları ve <b>, <a href=...>, <br> gibi HTML "
	"etiketlerini aynen koru; sıraları cümleye göre değişebilir ama hiçbiri silinmez ya da eklenmez.\n"
	"2. Baştaki/sondaki boşlukları ve satır sonlarını koru.\n"
	"3. Kod, alan adı, URL, e-posta, dosya yolu, `backtick` içi metin çevrilmez.\n"
	"4. Frappe, Helpdesk ve Flow ürün adları ZEKİ AI olur.\n"
	"5. Yalnız istenen JSON'u döndür, açıklama yazma.\n\n" + GLOSSARY
)

PLACEHOLDER = re.compile(r"\{[a-zA-Z0-9_]*\}|%\([a-zA-Z0-9_]+\)[sd]|%[sd]")
TAG = re.compile(r"</?([a-zA-Z][a-zA-Z0-9]*)\b")
BRAND_LEAK = re.compile(r"\b(Frappe|Helpdesk|Flow)\b")


def load_env(path: str) -> None:
	"""Kabuğun `source`u JSON tırnaklarını yer; dosya satır satır okunur."""
	for line in open(path, encoding="utf-8"):
		line = line.strip()
		if not line or line.startswith("#") or "=" not in line:
			continue
		key, value = line.split("=", 1)
		value = value.strip()
		if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
			value = value[1:-1]
		os.environ.setdefault(key.strip(), value)


def make_llm():
	from semantic_layer.candidates.llm_client import LlmClient
	from semantic_layer.config import SemanticSettings
	from semantic_layer.runtime.llm_queue import BATCH, LlmQueue, QueuedLlm
	from semantic_layer.store.catalog_store import open_store

	s = SemanticSettings.from_env()
	extra = json.loads(os.environ.get("LLM_EXTRA_BODY_JSON") or "{}")
	store = open_store(s.store_dsn)
	client = LlmClient(s.llm_base, s.llm_model, s.llm_key, max(s.llm_timeout, 600), extra=extra, stream=False)
	return QueuedLlm(client, LlmQueue.from_env(store.engine), purpose="bg:destek-ceviri",
					 module="destek-ceviri", priority=BATCH)


def shape(text: str):
	return (
		sorted(PLACEHOLDER.findall(text)),
		sorted(t.lower() for t in TAG.findall(text)),
		text[: len(text) - len(text.lstrip())],
		text[len(text.rstrip()) :],
		text.count("\n"),
	)


def valid(src: str, dst: str) -> bool:
	if not dst or not dst.strip():
		return False
	if shape(src) != shape(dst):
		return False
	# Kaynakta marka adı yokken çeviriye girmesin; varsa ZEKİ AI'ya dönmüş olmalı.
	return not BRAND_LEAK.search(dst)


def examples(sozluk: list[polib.POFile], limit: int = 60) -> str:
	seen, rows = set(), []
	for po in sozluk:
		for e in po:
			if e.msgstr and not e.msgid_plural and len(e.msgid) < 40 and e.msgid not in seen and not BRAND_LEAK.search(e.msgid):
				seen.add(e.msgid)
				rows.append(f"{e.msgid} → {e.msgstr}")
	return "\n".join(rows[:limit])


def ask(llm, items: list[str], shots: str) -> list[str]:
	user = (
		("Önceki çevirilerden örnekler (üsluba uy):\n" + shots + "\n\n" if shots else "")
		+ f"Aşağıdaki {len(items)} metni çevir. Aynı sırayla, aynı sayıda öğe içeren bir JSON dizi döndür "
		+ '(ör. ["...", "..."]).\n\n'
		+ json.dumps(items, ensure_ascii=False, indent=0)
	)
	reply = llm.chat([{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}],
					 max_tokens=8192, temperature=0.1)
	start, end = reply.find("["), reply.rfind("]")
	out = json.loads(reply[start : end + 1])
	if not isinstance(out, list) or len(out) != len(items):
		raise ValueError(f"beklenen {len(items)} öğe, gelen {len(out) if isinstance(out, list) else '?'}")
	return [str(x) for x in out]


def translate_file(path: str, llm, shots: str, batch: int, report: dict) -> None:
	po = polib.pofile(path, wrapwidth=0)
	todo = [e for e in po if not e.obsolete and not e.msgid_plural and not e.msgstr and e.msgid.strip()]
	print(f"{path}: {len(todo)} boş girdi", flush=True)
	done = failed = 0
	for i in range(0, len(todo), batch):
		part = todo[i : i + batch]
		src = [e.msgid for e in part]
		try:
			out = ask(llm, src, shots)
		except Exception as exc:  # noqa: BLE001
			print(f"  parti {i // batch + 1}: {exc}; tek tek denenecek", flush=True)
			out = [""] * len(part)
		retry = [k for k, (s, d) in enumerate(zip(src, out)) if not valid(s, d)]
		if retry:
			try:
				again = ask(llm, [src[k] for k in retry], shots)
				for k, d in zip(retry, again):
					out[k] = d
			except Exception as exc:  # noqa: BLE001
				print(f"  yeniden deneme: {exc}", flush=True)
		for e, s, d in zip(part, src, out):
			if valid(s, d):
				e.msgstr = d
				if "fuzzy" in e.flags:
					e.flags.remove("fuzzy")
				done += 1
			else:
				failed += 1
				report.setdefault(path, []).append(s)
		po.save(path)
		print(f"  {min(i + batch, len(todo))}/{len(todo)} · çevrilen {done} · kalan {failed}", flush=True)
	report.setdefault("_ozet", {})[path] = {"bos": len(todo), "cevrilen": done, "kalan": failed}


def main() -> int:
	ap = argparse.ArgumentParser()
	ap.add_argument("po", nargs="+")
	ap.add_argument("--env", default="/etc/nanobase/semantic-bridge.env")
	ap.add_argument("--sozluk", action="append", default=[], help="üslup örneği alınacak dolu .po")
	ap.add_argument("--parti", type=int, default=40)
	ap.add_argument("--rapor", default="ceviri-raporu.json")
	args = ap.parse_args()

	load_env(args.env)
	llm = make_llm()
	shots = examples([polib.pofile(p, wrapwidth=0) for p in args.sozluk])
	report: dict = {}
	started = time.time()
	for path in args.po:
		translate_file(path, llm, shots, args.parti, report)
	report["_sure_sn"] = round(time.time() - started)
	with open(args.rapor, "w", encoding="utf-8") as f:
		json.dump(report, f, ensure_ascii=False, indent=1)
	print(json.dumps(report["_ozet"], ensure_ascii=False))
	return 0


if __name__ == "__main__":
	sys.exit(main())
