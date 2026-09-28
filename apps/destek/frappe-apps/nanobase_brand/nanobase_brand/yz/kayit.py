"""Destek kaydı üzerinde yapay zekâ: sınıflama, özet, yanıt taslağı, makale taslağı.

Kurallar:
- Model hiçbir şeyi müşteriye göndermez; taslak temsilcinin yanıt kutusuna gelir, temsilci gönderir.
- Sınıflama yalnız boş alanı doldurur; temsilcinin ya da müşterinin seçtiği değer ezilmez. Öncelik yalnız
  varsayılan değerdeyse değişir. Önerilen değer sistemde tanımlı değilse yazılmaz.
- Kaydın içeriği modele kapıdan gider; model kendi GPU'muzda, veri dışarı çıkmaz.
"""

from __future__ import annotations

import frappe
from frappe import _
from frappe.core.utils import html2text
from frappe.utils import escape_html, now_datetime, strip_html

from nanobase_brand.yz import bilgi, llm

DUYGULAR = ("Olumlu", "Nötr", "Olumsuz", "Öfkeli")
ACIK_DURUMLAR = ("Open", "Replied", "Paused")
MAX_METIN = 12000

KIMLIK = (
	"Sen NanobaseAI'sin, bir müşteri destek ekibinin asistanısın. Kendinden ve altyapıdan bahsetme, "
	"model ya da ürün adı verme. Yalnız verilen bilgiye dayan, bilmediğini uydurma."
)


# ---------------------------------------------------------------- yardımcılar

def _text(html: str | None, limit: int = MAX_METIN) -> str:
	return (html2text(html or "") if html and "<" in html else (html or "")).strip()[:limit]


def _check(ticket: str, ptype: str = "read"):
	doc = frappe.get_doc("HD Ticket", ticket)
	if not frappe.has_permission("HD Ticket", ptype, doc=doc):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return doc


def _conversation(ticket: str, limit_chars: int = MAX_METIN) -> str:
	"""Kaydın yazışması eskiden yeniye: müşteri/temsilci mesajları ve iç yorumlar."""
	rows = []
	for c in frappe.get_all(
		"Communication",
		filters={"reference_doctype": "HD Ticket", "reference_name": ticket},
		fields=["sent_or_received", "sender", "content", "creation"],
		order_by="creation asc",
	):
		who = "Müşteri" if c.sent_or_received == "Received" else "Temsilci"
		rows.append((c.creation, f"[{who}] {_text(c.content, 3000)}"))
	for c in frappe.get_all(
		"HD Ticket Comment", filters={"reference_ticket": ticket}, fields=["content", "creation"], order_by="creation asc"
	):
		rows.append((c.creation, f"[İç not] {_text(c.content, 1500)}"))
	rows.sort(key=lambda r: r[0])
	text = "\n\n".join(r[1] for r in rows)
	return text[-limit_chars:]


def _options(doctype: str, field: str = "name", filters: dict | None = None) -> list[str]:
	return frappe.get_all(doctype, filters=filters or {}, pluck=field, order_by="name asc")


def _activity(ticket: str, action: str) -> None:
	from helpdesk.helpdesk.doctype.hd_ticket_activity.hd_ticket_activity import log_ticket_activity

	log_ticket_activity(ticket, action)


# ---------------------------------------------------------------- 1. sınıflama

def classify(ticket: str) -> dict:
	doc = frappe.get_doc("HD Ticket", ticket)
	types = _options("HD Ticket Type")
	priorities = _options("HD Ticket Priority")
	teams = _options("HD Team")
	text = f"Konu: {doc.subject}\n\n{_text(doc.description, 6000)}"
	prompt = (
		"Aşağıdaki destek kaydını sınıflandır. Yalnız listelerdeki değerlerden seç; uygun değer yoksa null yaz.\n"
		f"Türler: {types}\nÖncelikler: {priorities}\nEkipler: {teams}\n"
		f"Duygu: {list(DUYGULAR)}\n\n"
		'Yalnız şu JSON\'u döndür: {"ticket_type": ..., "priority": ..., "agent_group": ..., '
		'"duygu": ..., "gerekce": "tek cümle, Türkçe"}\n\n'
		f"KAYIT:\n{text}"
	)
	try:
		out = llm.chat_json([{"role": "system", "content": KIMLIK}, {"role": "user", "content": prompt}],
							priority=llm.BACKGROUND, max_tokens=300, temperature=0)
	except (llm.ModelUnavailable, ValueError):
		frappe.log_error(title=f"NanobaseAI sınıflama: {ticket}")
		return {}

	applied = {}
	# Sistem kendi varsayılanını doldurur (tür, öncelik); o değerlerde kalan alan «seçilmemiş» sayılır.
	default_type = frappe.db.get_single_value("HD Settings", "default_ticket_type")
	default_priority = frappe.db.get_single_value("HD Settings", "default_priority")
	if out.get("ticket_type") in types and doc.ticket_type in (None, "", default_type) and doc.ticket_type != out["ticket_type"]:
		doc.ticket_type = applied["ticket_type"] = out["ticket_type"]
	if out.get("agent_group") in teams and not doc.agent_group:
		doc.agent_group = applied["agent_group"] = out["agent_group"]
	if out.get("priority") in priorities and doc.priority in (None, "", default_priority) and doc.priority != out["priority"]:
		doc.priority = applied["priority"] = out["priority"]
	duygu = out.get("duygu") if out.get("duygu") in DUYGULAR else None
	doc.nb_duygu = duygu
	doc.nb_yz_not = str(out.get("gerekce") or "")[:500]
	doc.flags.ignore_permissions = True
	try:
		# Tam kayıt: ekip değişince ekibin atama kuralı da çalışsın.
		doc.save()
	except Exception:
		# Atama kuralı çalışamazsa (ör. ekipte temsilci yok, üst kaynakta boş listede IndexError) sınıflama
		# kaybolmasın: alanlar kancasız yazılır, atama yapılmaz.
		frappe.db.rollback()
		frappe.log_error(title=f"NanobaseAI sınıflama: atama kuralı çalışmadı ({ticket})")
		frappe.db.set_value("HD Ticket", ticket, {
			**applied, "nb_duygu": doc.nb_duygu, "nb_yz_not": doc.nb_yz_not}, update_modified=False)
	names = {"ticket_type": "tür", "priority": "öncelik", "agent_group": "ekip"}
	parts = [f"{names[k]}: {v}" for k, v in applied.items()]
	if duygu:
		parts.append(f"duygu: {duygu}")
	if parts:
		_activity(ticket, "NanobaseAI sınıflandırdı — " + ", ".join(parts))
	frappe.db.commit()
	return {**applied, "duygu": duygu}


# ---------------------------------------------------------------- panel verisi

@frappe.whitelist()
def panel(ticket: str) -> dict:
	doc = _check(ticket)
	return {
		"duygu": doc.get("nb_duygu"),
		"not": doc.get("nb_yz_not"),
		"ozet": doc.get("nb_yz_ozet"),
		"ozet_zamani": doc.get("nb_yz_ozet_zamani"),
		"cozuldu": doc.status in ("Resolved", "Closed"),
		"makale": frappe.db.get_value("HD Article", {"nb_kaynak_kayit": ticket}, "name"),
	}


# ---------------------------------------------------------------- 3. özet

@frappe.whitelist()
def summarize(ticket: str) -> dict:
	doc = _check(ticket)
	conv = _conversation(ticket)
	replies = conv.count("[Temsilci]")
	prompt = (
		"Bu destek kaydını devralacak temsilci için en çok 3 satırlık Türkçe özet yaz:\n"
		"1) Müşteri ne istiyor / sorun ne, 2) şu ana kadar ne yapıldı, 3) sıradaki adım ne.\n"
		"Her satır tek cümle. Başlık ya da giriş cümlesi yazma.\n"
		f"Temsilci yanıtı sayısı: {replies}. Yalnız yazışmada geçen işlemi yaz; "
		"temsilci yanıtı yoksa 2. satır «Henüz yanıt verilmedi.» olsun, yapılmamış işlemi yapılmış gibi yazma.\n\n"
		f"Konu: {doc.subject}\nİlk mesaj: {_text(doc.description, 3000)}\n\nYazışma:\n{conv or '(yok)'}"
	)
	try:
		text = llm.chat([{"role": "system", "content": KIMLIK}, {"role": "user", "content": prompt}],
						max_tokens=400, temperature=0.1)
	except llm.ModelUnavailable:
		frappe.throw(_("The assistant is unavailable right now. Please try again shortly."))
	frappe.db.set_value("HD Ticket", ticket, {"nb_yz_ozet": text[:2000], "nb_yz_ozet_zamani": now_datetime()},
						update_modified=False)
	return {"ozet": text, "ozet_zamani": str(now_datetime())}


# ---------------------------------------------------------------- 2. yanıt taslağı

@frappe.whitelist()
def draft_reply(ticket: str) -> dict:
	doc = _check(ticket, "write")
	conv = _conversation(ticket, 8000)
	last = conv.rsplit("[Müşteri]", 1)[-1] if "[Müşteri]" in conv else _text(doc.description, 3000)
	hits = bilgi.search(f"{doc.subject}\n{last[:1500]}", limit=5)
	facts = "\n\n".join(
		f"[{i + 1}] ({h.get('reference_doctype') or 'belge'} {h.get('reference_name') or ''})\n{h['content'][:1500]}"
		for i, h in enumerate(hits)
	)
	agent = frappe.db.get_value("User", frappe.session.user, "first_name") or ""
	prompt = (
		"Müşteriye gönderilecek yanıtın TASLAĞINI yaz. Temsilci okuyup düzeltecek.\n"
		"- Müşterinin yazdığı dilde, kibar ve kısa yaz (Türkçe yazdıysa Türkçe).\n"
		"- Yalnız aşağıdaki bilgi bankası parçalarına ve yazışmaya dayan; bilgi yoksa uydurma, "
		"netleştirmek için soru sor ya da ekibin inceleyeceğini söyle.\n"
		"- Tarih, fiyat, iade/garanti sözü verme; bilgi bankasında açıkça yoksa yazma.\n"
		"- Selamlama ile başla, imza olarak yalnız temsilcinin adını yaz.\n"
		"- Düz metin; paragraflar arasında boş satır.\n\n"
		f"Temsilci adı: {agent}\nKonu: {doc.subject}\n\nYazışma:\n{conv or _text(doc.description)}\n\n"
		f"Bilgi bankası:\n{facts or '(ilgili parça bulunamadı)'}"
	)
	try:
		text = llm.chat([{"role": "system", "content": KIMLIK}, {"role": "user", "content": prompt}],
						max_tokens=700, temperature=0.3)
	except llm.ModelUnavailable:
		frappe.throw(_("The assistant is unavailable right now. Please try again shortly."))
	html = "".join(f"<p>{escape_html(p.strip()).replace(chr(10), '<br>')}</p>"
				   for p in text.split("\n\n") if p.strip())
	sources = []
	for h in hits:
		dt, name = h.get("reference_doctype"), h.get("reference_name")
		if dt == "HD Article" and name:
			sources.append({"tur": "makale", "ad": name, "baslik": frappe.db.get_value("HD Article", name, "title")})
		elif dt == "HD Ticket" and name and str(name) != str(ticket):
			sources.append({"tur": "kayit", "ad": name, "baslik": frappe.db.get_value("HD Ticket", name, "subject")})
	_activity(ticket, "NanobaseAI yanıt taslağı hazırladı")
	return {"html": html, "kaynaklar": sources}


# ---------------------------------------------------------------- 4. makale taslağı

@frappe.whitelist()
def article_draft(ticket: str) -> dict:
	doc = _check(ticket)
	if doc.status not in ("Resolved", "Closed"):
		frappe.throw(_("An article draft can be made from a resolved ticket."))
	if not frappe.has_permission("HD Article", "create"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	conv = _conversation(ticket)
	prompt = (
		"Bu çözülmüş destek kaydından, başka müşterilerin de kullanabileceği bir bilgi bankası makalesi taslağı yaz.\n"
		"- Kişisel veri yazma: müşteri adı, e-posta, telefon, sipariş/fatura numarası çıkar.\n"
		"- Başlık soru ya da sorun cümlesi olsun; gövde: Sorun, Çözüm (adım adım), Not.\n"
		"- Türkçe. Yalnız kayıtta geçen çözümü yaz, uydurma.\n"
		'Yalnız şu JSON\'u döndür: {"title": "...", "html": "<h3>Sorun</h3><p>..</p><h3>Çözüm</h3><ol><li>..</li></ol>"}\n\n'
		f"Konu: {doc.subject}\nÇözüm notu: {_text(doc.get('resolution_details'), 3000) or '(yok)'}\n\nYazışma:\n{conv}"
	)
	try:
		out = llm.chat_json([{"role": "system", "content": KIMLIK}, {"role": "user", "content": prompt}],
							max_tokens=1200, temperature=0.2)
	except (llm.ModelUnavailable, ValueError):
		frappe.throw(_("The assistant is unavailable right now. Please try again shortly."))
	title = strip_html(str(out.get("title") or doc.subject))[:120]
	category = frappe.get_all("HD Article Category", filters={"category_name": "General"}, pluck="name",
							  order_by="creation asc", limit=1)
	article = frappe.get_doc({
		"doctype": "HD Article",
		"title": title,
		"nb_kaynak_kayit": ticket,
		"content": str(out.get("html") or ""),
		"status": "Draft",
		"author": frappe.session.user,
		"category": category[0] if category else None,
	}).insert()
	_activity(ticket, f"NanobaseAI makale taslağı oluşturdu: {article.name}")
	return {"name": article.name, "title": article.title}


# ---------------------------------------------------------------- 6. benzer kayıtlar ve uygulanan çözümler

def _applied(ticket: str, limit_chars: int = 2500) -> str:
	"""Çözülmüş bir kayıtta ne yapıldığı: çözüm notu + temsilci yanıtları + iç notlar (son kısımlar)."""
	doc = frappe.db.get_value("HD Ticket", ticket, ["resolution_details"], as_dict=True) or {}
	parts = []
	if doc.get("resolution_details"):
		parts.append(f"[Çözüm notu] {_text(doc.resolution_details, 1500)}")
	for c in frappe.get_all(
		"Communication",
		filters={"reference_doctype": "HD Ticket", "reference_name": ticket, "sent_or_received": "Sent"},
		fields=["content"], order_by="creation desc", limit=3,
	):
		parts.append(f"[Temsilci] {_text(c.content, 800)}")
	for c in frappe.get_all("HD Ticket Comment", filters={"reference_ticket": ticket}, fields=["content"],
							order_by="creation desc", limit=2):
		parts.append(f"[İç not] {_text(c.content, 500)}")
	return "\n".join(parts)[:limit_chars]


def _candidates(doc, limit: int) -> tuple[list[str], str]:
	"""Anlamca en yakın çözülmüş kayıtlar; bilgi bankası boşsa aynı türdeki son çözülenler."""
	query = f"{doc.subject}\n{_text(doc.description, 1500)}"
	names: list[str] = []
	for hit in bilgi.search(query, limit=limit * 3):
		name = hit.get("reference_name")
		if hit.get("reference_doctype") == "HD Ticket" and name and str(name) != str(doc.name) and name not in names:
			names.append(name)
	if names:
		return names[:limit], "anlam"
	filters = {"status": ["in", ["Resolved", "Closed"]], "name": ["!=", doc.name]}
	if doc.ticket_type:
		filters["ticket_type"] = doc.ticket_type
	return frappe.get_all("HD Ticket", filters=filters, pluck="name", order_by="modified desc", limit=limit), "tür"


@frappe.whitelist()
def similar(ticket: str, limit: int = 5) -> dict:
	doc = _check(ticket)
	names, how = _candidates(doc, min(int(limit or 5), 10))
	rows = []
	for name in names:
		if not frappe.has_permission("HD Ticket", "read", doc=name):
			continue
		info = frappe.db.get_value("HD Ticket", name, ["name", "subject", "status", "modified", "customer"], as_dict=True)
		if info:
			rows.append({**info, "yapilan": _applied(name)})
	if not rows:
		return {"kayitlar": [], "oneri": "", "yontem": how}

	listing = "\n\n".join(f"KAYIT #{r['name']} — {r['subject']}\n{r['yapilan'] or '(çözüm kaydı yok)'}" for r in rows)
	prompt = (
		"Yeni bir destek kaydını çözecek temsilciye, geçmişteki benzer kayıtlarda ne yapıldığını anlat.\n"
		"- Her kayıt için tek cümle: o kayıtta uygulanan çözüm. Kayıtta çözüm bilgisi yoksa «Çözüm kaydı yok» yaz.\n"
		"- Sonra yeni kayıt için en çok 3 maddelik önerilen yol; yalnız bu kayıtlarda geçen çözümlere dayan, uydurma.\n"
		"- Türkçe. Yalnız şu JSON'u döndür: "
		'{"kayitlar": {"<kayıt no>": "uygulanan çözüm"}, "oneri": ["...", "..."]}\n\n'
		f"YENİ KAYIT: {doc.subject}\n{_text(doc.description, 1500)}\n\nGEÇMİŞ KAYITLAR:\n{listing}"
	)
	try:
		out = llm.chat_json([{"role": "system", "content": KIMLIK}, {"role": "user", "content": prompt}],
							max_tokens=900, temperature=0.1)
	except (llm.ModelUnavailable, ValueError):
		out = {}
	applied = {str(k).lstrip("#"): str(v) for k, v in (out.get("kayitlar") or {}).items()}
	advice = [str(x) for x in (out.get("oneri") or []) if str(x).strip()][:3]
	return {
		"yontem": how,
		"oneri": advice,
		"kayitlar": [
			{"ad": r["name"], "konu": r["subject"], "durum": r["status"], "musteri": r.get("customer"),
			 "tarih": str(r["modified"])[:10], "uygulanan": applied.get(str(r["name"])) or ("" if r["yapilan"] else "Çözüm kaydı yok")}
			for r in rows
		],
	}
