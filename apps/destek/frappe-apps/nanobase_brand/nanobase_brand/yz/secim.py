"""Kapalı küme seçim + olasılık: köprüdeki LLM kapısının `choose` yönteminin masadaki eşi (frappe'siz, saf Python).

Masa köprünün Python paketini içe aktaramaz (ayrı konteyner); aynı yöntem burada kısa hâliyle durur ve model çağrısı
yine LLM kapısından (`/destek-llm/v1`, OpenAI uyumlu giriş) gider:

* Seçenekler A, B, C … etiketleriyle listelenir; model yalnız harfi yazar (tek token).
* İstek `max_tokens=1`, `temperature=0`, `structured_outputs.choice=[etiketler]`, `logprobs` + `top_logprobs=20`.
  O tek token'ın adaylarından her etiketin payı toplanıp normalize edilir (toplam 1); marj = seçilen − en yüksek diğeri.
* 26'dan çok seçenek: dengeli gruplar, her grubun galibi finale; P(c) = P(grupta c) × P(finalde grubun galibi).
* Olasılık okunamazsa (uç `structured_outputs` bilmiyor, aday yok) metin yalnız kesin eşleşmeyle seçeneğe bağlanır ve
  olasılık yok döner: çağıran bunu «emin değil» sayar, alanı doldurmaz.

Eşik çağırana aittir (`emin`). Köprü karşılığı: `backend/semantic_layer/runtime/llm_choose.py`.
"""

from __future__ import annotations

import math
import re
from typing import Any, Callable, Optional, Sequence

ETIKETLER = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
TOP_LOGPROBS = 20

#: cagir(mesajlar, ek_govde) → modelin ilk seçeneği ({"message": {...}, "logprobs": {...}}); ek_govde None ise düz istek.
Cagir = Callable[[list[dict], Optional[dict]], dict]


def mesajlar(soru: str, secenekler: Sequence[str], sistem: Optional[str] = None) -> list[dict]:
	etiket = ETIKETLER[: len(secenekler)]
	satirlar = "\n".join(f"{e}) {' '.join(str(s).split())}" for e, s in zip(etiket, secenekler))
	icerik = (f"{(soru or '').rstrip()}\n\nSeçenekler:\n{satirlar}\n\n"
			  f"Cevap olarak yalnız seçeneğin harfini yaz ({', '.join(etiket)}); başka hiçbir şey yazma.")
	out = [{"role": "system", "content": sistem}] if sistem else []
	out.append({"role": "user", "content": icerik})
	return out


def govde(etiketler: Sequence[str]) -> dict:
	return {"logprobs": True, "top_logprobs": TOP_LOGPROBS, "structured_outputs": {"choice": list(etiketler)}}


def oku(cevap: Any, etiketler: Sequence[str]) -> Optional[dict[str, float]]:
	"""İlk token adaylarından etiket olasılıkları (toplam 1); okunamazsa None."""
	try:
		ilk = (((cevap or {}).get("logprobs") or {}).get("content") or [None])[0]
	except (AttributeError, TypeError, IndexError):
		return None
	if not isinstance(ilk, dict):
		return None
	gorulen: dict[str, float] = {}
	for g in list(ilk.get("top_logprobs") or []) + [ilk]:
		if not isinstance(g, dict) or "token" not in g or str(g["token"]) in gorulen:
			continue
		try:
			lp = float(g.get("logprob"))
		except (TypeError, ValueError):
			continue
		if not math.isnan(lp):
			gorulen[str(g["token"])] = lp
	kutle = {e: 0.0 for e in etiketler}
	for token, lp in gorulen.items():
		if token.strip() in kutle:
			kutle[token.strip()] += math.exp(lp)
	toplam = sum(kutle.values())
	if toplam <= 0 or math.isinf(toplam):
		return None
	return {e: m / toplam for e, m in kutle.items()}


_THINK = re.compile(r"<think>.*?(</think>|$)", re.S | re.I)
_KENAR = " \t\r\n.,;:!?\"'`*()[]{}<>"


def _norm(s: str) -> str:
	t = str(s).replace("İ", "i").replace("I", "ı").lower()
	return " ".join(t.strip(_KENAR).split())


def metinden(metin: str, secenekler: Sequence[str]) -> Optional[int]:
	"""Yedek yol: yalnız kesin eşleşme — tek harf etiket ya da seçeneğin tamamı."""
	etiket = ETIKETLER[: len(secenekler)]
	t = _THINK.sub("", metin or "").strip().strip(_KENAR)
	if len(t) == 1 and t in etiket:
		return etiket.index(t)
	hedef = _norm(t)
	isabet = [i for i, s in enumerate(secenekler) if _norm(s) == hedef]
	return isabet[0] if len(isabet) == 1 else None


def _sonuc(secim: Optional[str], olasiliklar: Optional[dict[str, float]], yontem: str) -> dict[str, Any]:
	p = marj = None
	if olasiliklar is not None and secim is not None:
		p = olasiliklar.get(secim)
		digerleri = [v for k, v in olasiliklar.items() if k != secim]
		marj = p - (max(digerleri) if digerleri else 0.0)
	return {"choice": secim, "probability": p, "margin": marj, "probs": olasiliklar, "method": yontem}


def _tek(cagir: Cagir, soru: str, secenekler: list[str], sistem: Optional[str]) -> dict[str, Any]:
	if len(secenekler) == 1:
		return _sonuc(secenekler[0], {secenekler[0]: 1.0}, "single")
	etiket = list(ETIKETLER[: len(secenekler)])
	msj = mesajlar(soru, secenekler, sistem)
	try:
		cevap = cagir(msj, govde(etiket))
	except ValueError:
		# Uç yapılandırılmış seçimi reddetti (4xx): düz istek, olasılıksız.
		cevap = cagir(msj, None)
	olas = oku(cevap, etiket)
	metin = str(((cevap or {}).get("message") or {}).get("content") or "")
	if olas is not None:
		soylenen = metin.strip().strip(_KENAR)
		en = max(olas.values())
		esit = [e for e in etiket if olas[e] == en]
		e = soylenen if soylenen in esit else esit[0]
		return _sonuc(secenekler[etiket.index(e)], {secenekler[i]: olas[x] for i, x in enumerate(etiket)}, "logprobs")
	i = metinden(metin, secenekler)
	return _sonuc(secenekler[i] if i is not None else None, None, "text" if i is not None else "none")


def gruplar(ogeler: Sequence[str], boy: int = len(ETIKETLER)) -> list[list[str]]:
	n = len(ogeler)
	k = max(1, math.ceil(n / boy))
	taban, artan = divmod(n, k)
	out, at = [], 0
	for i in range(k):
		adim = taban + (1 if i < artan else 0)
		out.append(list(ogeler[at: at + adim]))
		at += adim
	return out


def sec(cagir: Cagir, soru: str, secenekler: Sequence[str], sistem: Optional[str] = None) -> dict[str, Any]:
	"""Kapalı küme seçim; sayı tavanı yok (26'dan çok seçenekte eleme turu)."""
	secenekler = [str(s) for s in secenekler]
	if not secenekler or len(set(secenekler)) != len(secenekler):
		raise ValueError("seçenekler boş ya da tekrarlı olamaz")
	if len(secenekler) <= len(ETIKETLER):
		return _tek(cagir, soru, secenekler, sistem)
	gs = gruplar(secenekler)
	turlar = [sec(cagir, soru, g, sistem) for g in gs]
	galipler = [t["choice"] for t in turlar if t["choice"] is not None]
	if not galipler:
		return _sonuc(None, None, "none")
	final = sec(cagir, soru, galipler, sistem)
	if final["choice"] is None or final["probs"] is None or any(t["probs"] is None for t in turlar if t["choice"]):
		return _sonuc(final["choice"], None, "text" if final["choice"] else "none")
	olas: dict[str, float] = {}
	for g, t in zip(gs, turlar):
		gecis = final["probs"].get(t["choice"], 0.0) if t["choice"] else 0.0
		for s in g:
			olas[s] = (t["probs"] or {}).get(s, 0.0) * gecis
	toplam = sum(olas.values())
	if toplam > 0:
		olas = {s: v / toplam for s, v in olas.items()}
	return _sonuc(final["choice"], olas, "logprobs")


def emin(r: dict[str, Any], min_p: float, min_marj: float) -> bool:
	"""Seçim var, olasılık okunmuş, p ≥ eşik ve marj ≥ eşik. Olasılıksız yedek yol her zaman «emin değil»."""
	p, m = r.get("probability"), r.get("margin")
	return r.get("choice") is not None and p is not None and m is not None and p >= min_p and m >= min_marj
