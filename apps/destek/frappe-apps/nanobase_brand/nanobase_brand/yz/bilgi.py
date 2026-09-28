"""Bilgi bankası: yayımlanmış makaleler ve çözülen kayıtlar; gömme modeli BI'ın gömme servisi (kapıdan).

`ensure()` kurulumda koşar (nanobase_brand.install.apply); kaynaklar Flow'un günlük eşitlemesiyle güncel kalır.
"""

from __future__ import annotations

import frappe

KB_TITLE = "NanobaseAI Destek Bilgisi"
EMBED_DOC = "NanobaseAI Gömme"
SOURCES = [
	# (başlık, belge türü, içerik alanları, süzgeç)
	("Yayımlanmış makaleler", "HD Article", ["title", "content"], {"status": "Published"}),
	("Çözülen kayıtlar", "HD Ticket", ["subject", "description", "resolution_details"],
	 {"status": ["in", ["Resolved", "Closed"]]}),
]


def ensure_embedding_model() -> str | None:
	"""Gömme modeli sohbet modeliyle aynı uç ve anahtarla (kapı /embeddings'i BI'ın gömme servisine iletir)."""
	if not frappe.db.exists("Flow Model", "NanobaseAI"):
		return None
	chat = frappe.get_doc("Flow Model", "NanobaseAI")
	values = {"enabled": 1, "provider": chat.provider, "model_id": f"{chat.provider}/bge-m3",
			  "base_url": chat.base_url, "api_key": chat.get_password("api_key", raise_exception=False)}
	if frappe.db.exists("Flow Model", EMBED_DOC):
		doc = frappe.get_doc("Flow Model", EMBED_DOC)
		if not (doc.base_url == values["base_url"] and doc.model_id == values["model_id"] and doc.enabled):
			doc.update(values)
			doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc({"doctype": "Flow Model", "title": EMBED_DOC, **values}).insert(ignore_permissions=True)
	# Model önceden varsa da ayar ayrıca denetlenir (önceki yarım kurulum ayarı boş bırakmış olabilir).
	settings = frappe.get_single("Flow Knowledge Settings")
	if settings.embedding_model != doc.name or not settings.embedding_dimension:
		settings.embedding_model = doc.name
		settings.search_type = settings.search_type or "Hybrid"
		settings.flags.ignore_permissions = True
		settings.save()
	return doc.name


def ensure() -> str | None:
	if not frappe.db.exists("DocType", "Flow Knowledge Base") or not ensure_embedding_model():
		return None
	from flow.knowledge.knowledge import Knowledge

	kb = Knowledge(KB_TITLE, description="Destek temsilcisinin yanıt taslağı için makaleler ve çözülen kayıtlar")
	have = set(frappe.get_all("Flow Knowledge Source", filters={"knowledge_base": kb.name}, pluck="title"))
	for title, doctype, fields, filters in SOURCES:
		if title not in have:
			kb.add_doctype(doctype, content_fields=fields, filters=filters, title=title, auto_sync=True)
	return kb.name


def search(query: str, limit: int = 5) -> list[dict]:
	"""Bilgi bankasında en yakın parçalar; bilgi bankası ya da gömme yoksa boş liste (taslak yine yazılır)."""
	kb = frappe.db.get_value("Flow Knowledge Base", {"title": KB_TITLE}, "name")
	if not kb or not query.strip():
		return []
	from flow.knowledge.retriever import retrieve

	try:
		return retrieve(query, kbs=[kb], limit=limit)
	except Exception:
		frappe.log_error(title="NanobaseAI bilgi bankası araması")
		return []
