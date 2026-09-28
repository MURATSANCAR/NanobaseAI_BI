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
