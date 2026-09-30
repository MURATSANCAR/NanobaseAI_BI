"""Model çağrısı: panelin kullandığı ZEKİ AI modeli (Flow Model), LLM kapısı üzerinden.

Öncelik kapıda sıra önceliğidir: 0 etkileşimli (temsilci bekliyor), 2 arka plan (sınıflama, rapor).
"""

from __future__ import annotations

import json
import re

import frappe
import requests

MODEL_DOC = "ZEKİ AI"
INTERACTIVE, BACKGROUND = 0, 2
_THINK = re.compile(r"<think>.*?</think>", re.S)


class ModelUnavailable(Exception):
	pass


def _endpoint() -> tuple[str, str, str]:
	if not frappe.db.exists("Flow Model", MODEL_DOC):
		raise ModelUnavailable("model tanımlı değil")
	doc = frappe.get_doc("Flow Model", MODEL_DOC)
	if not doc.enabled or not doc.base_url:
		raise ModelUnavailable("model kapalı")
	model = (doc.model_id or "").split("/", 1)[-1]
	return doc.base_url.rstrip("/"), doc.get_password("api_key", raise_exception=False) or "", model


def chat(messages: list[dict], *, priority: int = INTERACTIVE, max_tokens: int = 900,
		 temperature: float = 0.2, timeout: int = 600) -> str:
	base, key, model = _endpoint()
	headers = {"Content-Type": "application/json", "X-LLM-Module": "destek", "X-LLM-Priority": str(priority)}
	if key:
		headers["Authorization"] = f"Bearer {key}"
	try:
		resp = requests.post(f"{base}/chat/completions", headers=headers, timeout=timeout,
							 json={"model": model, "messages": messages, "max_tokens": max_tokens,
								   "temperature": temperature})
	except requests.RequestException as exc:
		raise ModelUnavailable(type(exc).__name__) from exc
	if resp.status_code >= 400:
		raise ModelUnavailable(f"http {resp.status_code}")
	text = resp.json()["choices"][0]["message"].get("content") or ""
	return _THINK.sub("", text).strip()


def choose(prompt: str, choices: list[str], *, system: str | None = None, priority: int = BACKGROUND,
		   timeout: int = 600) -> dict:
	"""Kapalı küme seçim + olasılık (köprüdeki `QueuedLlm.choose` ile aynı yöntem, `secim.py`). Tek token cevap;
	dönen sözlük: choice, probability, margin, probs, method. Model yoksa `ModelUnavailable`."""
	from nanobase_brand.yz import secim

	base, key, model = _endpoint()
	headers = {"Content-Type": "application/json", "X-LLM-Module": "destek", "X-LLM-Priority": str(priority)}
	if key:
		headers["Authorization"] = f"Bearer {key}"

	def cagir(messages: list[dict], extra: dict | None) -> dict:
		body = {"model": model, "messages": messages, "max_tokens": 1, "temperature": 0, **(extra or {})}
		try:
			resp = requests.post(f"{base}/chat/completions", headers=headers, timeout=timeout, json=body)
		except requests.RequestException as exc:
			raise ModelUnavailable(type(exc).__name__) from exc
		if extra and 400 <= resp.status_code < 500 and resp.status_code not in (401, 403, 429):
			raise ValueError(f"yapılandırılmış seçim reddedildi: http {resp.status_code}")
		if resp.status_code >= 400:
			raise ModelUnavailable(f"http {resp.status_code}")
		return resp.json()["choices"][0]

	return secim.sec(cagir, prompt, choices, system)


def chat_json(messages: list[dict], **kw) -> dict:
	"""Modelden tek bir JSON nesnesi; metnin içindeki ilk {...} bloğu okunur."""
	text = chat(messages, **kw)
	start, end = text.find("{"), text.rfind("}")
	if start < 0 or end <= start:
		raise ValueError("JSON yok")
	return json.loads(text[start : end + 1])
