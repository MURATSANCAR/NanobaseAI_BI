"""Belge kancaları: burada ağır içe aktarma yok, hata kayıt açılışını durdurmaz.

Sınıflama arka planda koşar (nanobase_brand.yz.kayit.classify); kuyruğa alınamasa da kayıt açılır.
"""

import frappe


def on_ticket_insert(doc, method=None):
	try:
		frappe.enqueue("nanobase_brand.yz.kayit.classify", ticket=doc.name, queue="short",
					   enqueue_after_commit=True, job_id=f"nb-siniflama-{doc.name}", deduplicate=True)
	except Exception:
		frappe.log_error(title=f"NanobaseAI sınıflama kuyruğa alınamadı: {doc.name}")


COZULMUS = ("Resolved", "Closed")


def on_ticket_update(doc, method=None):
	"""Kayıt çözülünce (ya da çözülmüş kayıt yeniden açılınca) bilgi bankasının «çözülen kayıtlar» kaynağı
	artımlı eşitlenir: benzer kayıt önerisi günlük eşitlemeyi beklemez."""
	try:
		if not doc.has_value_changed("status"):
			return
		before = (doc.get_doc_before_save() or frappe._dict()).get("status")
		if doc.status not in COZULMUS and before not in COZULMUS:
			return
		from nanobase_brand.yz.bilgi import source_name

		source = source_name("Çözülen kayıtlar")
		if source:
			frappe.enqueue("flow.knowledge.ingest.ingest_source", source=source, queue="long",
						   enqueue_after_commit=True, job_id="nb-bilgi-cozulen-kayitlar", deduplicate=True)
	except Exception:
		frappe.log_error(title=f"NanobaseAI bilgi bankası eşitlemesi kuyruğa alınamadı: {doc.name}")
