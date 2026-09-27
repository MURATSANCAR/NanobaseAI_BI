"""Yapay zekâ panelinin modelini kurar: NanobaseAI modeli (OpenAI uyumlu uç).

Kurulum betiği çağırır:
    bench --site destek execute nanobase_brand.ai.ensure_model \
        --kwargs '{"base_url": "...", "api_key": "..."}'
Anahtar depoda tutulmaz; sunucudaki anahtar dosyasından okunup buraya verilir ve
Frappe'nin şifreli Password alanında saklanır.
"""

import json

import frappe

PROVIDER = "openai"
TITLE = "NanobaseAI"
MODEL = "nanobaseAI"
# Düşünme kapalı: köprünün LLM_EXTRA_BODY_JSON değeriyle aynı.
PARAMS = {"extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}


def ensure_model(base_url: str, api_key: str, model: str = MODEL) -> str:
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
