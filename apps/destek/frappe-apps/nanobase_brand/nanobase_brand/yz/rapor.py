"""Yönetici raporları: SLA riski (hafta içi her sabah) ve haftalık özet (pazartesi sabahı).

Alıcılar «Agent Manager» rolündeki etkin kullanıcılar. Rapor ayrıca masaüstünde herkese açık Not olarak
kalır (e-posta hesabı bağlı değilse de okunabilsin). Sayılar veritabanından; model yalnız yorum yazar.
"""

from __future__ import annotations

from collections import Counter

import frappe
from frappe.utils import add_days, add_to_date, escape_html, format_datetime, get_datetime, now_datetime

from nanobase_brand.yz import llm
from nanobase_brand.yz.kayit import ACIK_DURUMLAR, KIMLIK

URL = "/helpdesk/tickets/{}"


def _managers() -> list[str]:
	users = frappe.get_all("Has Role", filters={"role": "Agent Manager", "parenttype": "User"}, pluck="parent")
	return sorted(
		u for u in set(users)
		if u not in ("Administrator", "Guest") and frappe.db.get_value("User", u, "enabled")
	)


def sla_risk(hours: int = 24) -> list[dict]:
	"""Açık kayıtlardan çözüm süresi `hours` içinde dolan ya da dolmuş olanlar; ilk yanıtı gecikenler dahil."""
	limit = add_to_date(now_datetime(), hours=hours)
	rows = frappe.get_all(
		"HD Ticket",
		filters={"status": ["in", ACIK_DURUMLAR]},
		fields=["name", "subject", "priority", "agent_group", "response_by", "resolution_by",
				"first_responded_on", "_assign"],
		order_by="resolution_by asc",
	)
	out = []
	now = now_datetime()
	for r in rows:
		why = []
		if r.resolution_by and get_datetime(r.resolution_by) <= limit:
			why.append("çözüm süresi doldu" if get_datetime(r.resolution_by) < now else "çözüm süresi dolmak üzere")
		if not r.first_responded_on and r.response_by and get_datetime(r.response_by) <= limit:
			why.append("ilk yanıt gecikti" if get_datetime(r.response_by) < now else "ilk yanıt süresi dolmak üzere")
		if why:
			out.append({**r, "neden": ", ".join(why)})
	return out


def _risk_table(rows: list[dict]) -> str:
	if not rows:
		return "<p>SLA riskinde açık kayıt yok.</p>"
	body = "".join(
		f"<tr><td><a href='{URL.format(r['name'])}'>#{r['name']}</a></td><td>{escape_html(r['subject'] or '')}</td>"
		f"<td>{escape_html(r['agent_group'] or '—')}</td><td>{escape_html(r['priority'] or '')}</td>"
		f"<td>{format_datetime(r['resolution_by']) if r['resolution_by'] else '—'}</td><td>{r['neden']}</td></tr>"
		for r in rows
	)
	return ("<table border='1' cellpadding='6' style='border-collapse:collapse'><tr><th>Kayıt</th><th>Konu</th>"
			f"<th>Ekip</th><th>Öncelik</th><th>Çözüm süresi</th><th>Durum</th></tr>{body}</table>")


def _publish(title: str, html: str, subject: str) -> str:
	note = frappe.get_doc({"doctype": "Note", "title": title, "content": html, "public": 1}).insert(ignore_permissions=True)
	recipients = _managers()
	if recipients:
		# Giden e-posta hesabı yoksa rapor yine Not olarak kalır.
		try:
			frappe.sendmail(recipients=recipients, subject=subject, message=html, reference_doctype="Note",
							reference_name=note.name)
		except frappe.OutgoingEmailError:
			frappe.log_error(title="NanobaseAI raporu e-postayla gönderilemedi (giden e-posta hesabı yok)")
	frappe.db.commit()
	return note.name


def daily_sla_risk() -> str | None:
	"""Hafta içi sabah: riskte kayıt varsa yöneticilere liste (yoksa sessiz)."""
	rows = sla_risk(24)
	if not rows:
		return None
	title = f"NanobaseAI SLA riski — {format_datetime(now_datetime(), 'dd.MM.yyyy')}"
	html = f"<h3>SLA riskindeki kayıtlar ({len(rows)})</h3>" + _risk_table(rows)
	return _publish(title, html, title)


def weekly(days: int = 7) -> str:
	since = add_days(now_datetime(), -days)
	opened = frappe.get_all(
		"HD Ticket", filters={"creation": [">=", since]},
		fields=["name", "subject", "status", "agent_group", "ticket_type", "priority", "nb_duygu",
				"first_responded_on", "creation", "agreement_status"],
	)
	resolved = frappe.db.count("HD Ticket", {"status": ["in", ["Resolved", "Closed"]], "modified": [">=", since]})
	open_now = frappe.db.count("HD Ticket", {"status": ["in", ACIK_DURUMLAR]})
	failed = sum(1 for t in opened if t.agreement_status == "Failed")
	firsts = [(get_datetime(t.first_responded_on) - get_datetime(t.creation)).total_seconds() / 3600
			  for t in opened if t.first_responded_on]
	avg_first = f"{sum(firsts) / len(firsts):.1f} saat" if firsts else "—"

	def dist(field, empty="(boş)"):
		c = Counter((t.get(field) or empty) for t in opened)
		return ", ".join(f"{escape_html(str(k))}: {v}" for k, v in c.most_common()) or "—"

	comment = ""
	if opened:
		subjects = "\n".join(f"- {t.subject}" for t in opened[:300])
		try:
			comment = llm.chat(
				[{"role": "system", "content": KIMLIK},
				 {"role": "user", "content": (
					 "Destek yöneticisine bu haftanın kayıt konularından en çok 5 maddelik Türkçe yorum yaz: "
					 "tekrar eden konular, dikkat çeken sorunlar, bilgi bankasına makale önerisi. "
					 "Her madde tek cümle, '- ' ile başlasın. Sayı uydurma.\n\n"
					 f"Konular:\n{subjects}")}],
				priority=llm.BACKGROUND, max_tokens=500, temperature=0.2)
		except llm.ModelUnavailable:
			comment = ""
	comment_html = "".join(f"<li>{escape_html(line.lstrip('-• ').strip())}</li>"
						   for line in comment.splitlines() if line.strip())
	risk = sla_risk(24)
	period = f"{format_datetime(since, 'dd.MM.yyyy')} – {format_datetime(now_datetime(), 'dd.MM.yyyy')}"
	html = (
		f"<h3>Haftalık destek özeti ({period})</h3>"
		f"<ul><li>Açılan kayıt: {len(opened)}</li><li>Çözülen/kapanan: {resolved}</li>"
		f"<li>Şu an açık: {open_now}</li><li>SLA ihlali (bu hafta açılanlarda): {failed}</li>"
		f"<li>Ortalama ilk yanıt: {avg_first}</li></ul>"
		f"<p><b>Ekip:</b> {dist('agent_group')}<br><b>Tür:</b> {dist('ticket_type')}<br>"
		f"<b>Öncelik:</b> {dist('priority')}<br><b>Müşteri duygusu:</b> {dist('nb_duygu', 'ölçülmedi')}</p>"
		+ (f"<h4>NanobaseAI yorumu</h4><ul>{comment_html}</ul>" if comment_html else "")
		+ f"<h4>SLA riskindeki açık kayıtlar ({len(risk)})</h4>" + _risk_table(risk)
	)
	title = f"NanobaseAI haftalık destek raporu — {period}"
	return _publish(title, html, title)


@frappe.whitelist()
def weekly_now() -> str:
	"""Yönetici elle üretir (masaüstünden ya da panelden)."""
	frappe.only_for(("Agent Manager", "System Manager"))
	return weekly()
