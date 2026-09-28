"""Yapay zekâ panelinin modelini kurar: NanobaseAI modeli, LLM kapısının OpenAI uyumlu girişi.

Kurulum betiği çağırır:
    echo '{"base_url": "...", "api_key": "..."}' | bench --site destek execute nanobase_brand.ai.ensure_model
Anahtar depoda tutulmaz; sunucudaki anahtar dosyasından okunup buraya verilir ve
Frappe'nin şifreli Password alanında saklanır.
"""

import json
import sys

import frappe

PROVIDER = "openai"
TITLE = "NanobaseAI"
MODEL = "nanobaseAI"
# Uç LLM kapısıdır: model adı ve düşünme ayarı köprüden gelir. Başlık, sırada modülün adıyla
# görünmesi için (nginx de aynı başlığı koyar).
PARAMS = {"extra_headers": {"X-LLM-Module": "destek"}}


def ensure_model(base_url: str | None = None, api_key: str | None = None, model: str = MODEL) -> str:
	if base_url is None:
		# Standart girişten {"base_url", "api_key"}: anahtar komut satırına düşmez.
		given = json.load(sys.stdin)
		base_url, api_key = given["base_url"], given["api_key"]
	if not frappe.db.exists("Flow Provider", PROVIDER):
		frappe.get_doc({"doctype": "Flow Provider", "provider": PROVIDER, "enabled": 1}).insert(
			ignore_permissions=True
		)

	values = {
		"enabled": 1,
		"provider": PROVIDER,
		"model_id": f"{PROVIDER}/{model}",
		"base_url": base_url,
		"api_key": api_key,
		"params": json.dumps(PARAMS),
	}
	if frappe.db.exists("Flow Model", TITLE):
		doc = frappe.get_doc("Flow Model", TITLE)
		doc.update(values)
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc({"doctype": "Flow Model", "title": TITLE, **values})
		doc.insert(ignore_permissions=True)

	from flow.assistant import sync_builtin_assistant

	sync_builtin_assistant(doc.name)
	frappe.db.commit()
	return doc.name
