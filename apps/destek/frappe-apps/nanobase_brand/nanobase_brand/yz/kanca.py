"""Belge kancaları: burada ağır içe aktarma yok, hata kayıt açılışını durdurmaz.

Yeni kayıt arka planda işlenir (nanobase_brand.yz.cozum.yeni_kayit: sınıflama, sonra otomatik çözüm önerisi ya da
BT ataması); kuyruğa alınamasa da kayıt açılır.
"""

import frappe


def on_ticket_insert(doc, method=None):
	try:
		frappe.enqueue("nanobase_brand.yz.cozum.yeni_kayit", ticket=doc.name, queue="short",
					   enqueue_after_commit=True, job_id=f"nb-yeni-kayit-{doc.name}", deduplicate=True)
	except Exception:
		frappe.log_error(title=f"NanobaseAI yeni kayıt işi kuyruğa alınamadı: {doc.name}")


COZULMUS = ("Resolved", "Closed")


def on_ticket_update(doc, method=None):
	"""Kayıt çözülünce (ya da çözülmüş kayıt yeniden açılınca) bilgi bankasının «çözülen kayıtlar» kaynağı
	artımlı eşitlenir. Çözüm notu boşsa önce BT'nin yazışmasından çözüm özeti çıkarılır (yz/cozum.py `ozet`),
	eşitlemeyi o iş başlatır: bilgi bankası notsuz kaydı okumasın."""
	try:
		if not doc.has_value_changed("status"):
			return
		before = (doc.get_doc_before_save() or frappe._dict()).get("status")
		if doc.status not in COZULMUS and before not in COZULMUS:
			return
		if doc.status in COZULMUS and not doc.resolution_details:
			frappe.enqueue("nanobase_brand.yz.cozum.ozet", ticket=doc.name, queue="long",
						   enqueue_after_commit=True, job_id=f"nb-cozum-ozeti-{doc.name}", deduplicate=True)
			return
		from nanobase_brand.yz.bilgi import source_name

		source = source_name("Çözülen kayıtlar")
		if source:
			frappe.enqueue("flow.knowledge.ingest.ingest_source", source=source, queue="long",
						   enqueue_after_commit=True, job_id="nb-bilgi-cozulen-kayitlar", deduplicate=True)
	except Exception:
		frappe.log_error(title=f"NanobaseAI bilgi bankası eşitlemesi kuyruğa alınamadı: {doc.name}")


def on_communication_insert(doc, method=None):
	"""Otomatik öneriden sonra talep edenden gelen yanıt değerlendirilir (çözüldü → kapat, değilse BT)."""
	try:
		if doc.reference_doctype != "HD Ticket" or doc.sent_or_received != "Received" or not doc.reference_name:
			return
		from nanobase_brand.yz.cozum import GONDERILDI

		if frappe.db.get_value("HD Ticket", doc.reference_name, "nb_oneri_durumu") != GONDERILDI:
			return
		frappe.enqueue("nanobase_brand.yz.cozum.yanit", ticket=doc.reference_name, queue="short",
					   enqueue_after_commit=True, job_id=f"nb-oneri-yaniti-{doc.name}", deduplicate=True)
	except Exception:
		frappe.log_error(title=f"NanobaseAI öneri yanıtı kuyruğa alınamadı: {doc.reference_name}")
