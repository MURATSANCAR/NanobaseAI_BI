"""Destek e-posta hesabı: BI'ın uyarı/rapor e-postasıyla aynı Gmail hesabı (zeki@).

Kurulum betiği SMTP ayarını köprünün yönetim ayarlarından (ALERT_SMTP_*) okuyup standart girişten verir;
şifre (Gmail uygulama şifresi) komut satırına ve depoya düşmez, sitede şifreli alanda durur.

Gönderim: temsilci yanıtları bu hesaptan gider. Otomatik alındı / memnuniyet e-postası kapalı (install.py).
Gelen kutusu (2026-09-28 kullanıcı kararı, ayrı destek adresi gelene kadar): her yeni e-posta bir destek kaydı
açar. Kutuda eski e-postalar (bildirimler, iç yazışma) var; hesap ilk açıldığında kutunun sıradaki numarası
(UIDNEXT) bir kez kaydedilir, yalnız ondan sonra gelenler alınır. Okunmamışlar okundu işaretlenmez
(eşitleme «ALL»: kutu salt okunur açılır).
Kaydederken sistem SMTP ve IMAP'e giriş yapıp dener; yanlış şifre kurulumu durdurur.
"""

import imaplib
import json
import re
import sys

import frappe
from frappe.email.doctype.email_account.email_account import get_max_email_uid
from frappe.utils import cint
from helpdesk.overrides.email_account import CustomEmailAccount

ACCOUNT = "NanobaseAI Destek"
FOLDER = "INBOX"
START_KEY = "nb_eposta_baslangic_uid::"
# IMAP'te «UID n:*» kutuda n'den büyük e-posta yokken son e-postayı döndürür; üst sınır sayıyla verilir.
UID_MAX = 4294967295


class NanobaseEmailAccount(CustomEmailAccount):
	def build_email_sync_rule(self):
		rule = super().build_email_sync_rule()
		start = cint(frappe.db.get_default(START_KEY + self.name))
		if not (start and self.use_imap and self.email_sync_option == "ALL"):
			return rule
		return f"UID {max(start, get_max_email_uid(self.name))}:{UID_MAX}"


def ensure_outgoing(config: dict | None = None) -> str:
	"""Adı kurulum betiğiyle uyum için korunur: giden + gelen hesabı birlikte kurar."""
	cfg = json.load(sys.stdin) if config is None else config
	port = int(cfg.get("port") or 587)
	smtp_host = cfg.get("host") or "smtp.gmail.com"
	imap_host = cfg.get("imap_host") or ("imap.gmail.com" if smtp_host == "smtp.gmail.com" else "")
	values = {
		"email_id": cfg["user"],
		"email_account_name": ACCOUNT,
		"password": cfg["password"],
		"awaiting_password": 0,
		"enable_outgoing": 1,
		"default_outgoing": 1,
		"smtp_server": smtp_host,
		"smtp_port": port,
		"use_tls": 1 if port == 587 else 0,
		"use_ssl_for_outgoing": 1 if port == 465 else 0,
		"always_use_account_email_id_as_sender": 1,
		"always_use_account_name_as_sender_name": 1,
		"add_signature": 0,
		"enable_incoming": 0,
	}
	name = frappe.db.get_value("Email Account", {"email_account_name": ACCOUNT}, "name")
	doc = frappe.get_doc("Email Account", name) if name else frappe.new_doc("Email Account")
	if imap_host:
		validity, uidnext = _mailbox_state(imap_host, cfg["user"], cfg["password"])
		values.update(
			{
				"enable_incoming": 1,
				"default_incoming": 1,
				"use_imap": 1,
				"use_ssl": 1,
				"email_server": imap_host,
				"incoming_port": "993",
				"email_sync_option": "ALL",
				"enable_automatic_linking": 0,
			}
		)
		row = next((r for r in doc.get("imap_folder") or [] if r.folder_name == FOLDER), None)
		if not row:
			row = doc.append("imap_folder", {"folder_name": FOLDER})
		row.append_to = "HD Ticket"
		# Başlangıç bir kez yazılır; sonraki kurulumlar ilerletmez (kurulum sırasında gelen e-posta kaybolmasın).
		if not frappe.db.get_default(START_KEY + ACCOUNT):
			frappe.db.set_default(START_KEY + ACCOUNT, str(uidnext))
			# Kutu kimliği önceden yazılır: yoksa ilk eşitleme «yeniden dizinlendi» sayıp son 100 e-postayı alır.
			row.uidvalidity = str(validity)
			row.uidnext = str(uidnext)
	doc.update(values)
	doc.flags.ignore_permissions = True
	doc.save() if name else doc.insert()
	frappe.db.commit()
	return doc.name


def _mailbox_state(host: str, user: str, password: str) -> tuple[int, int]:
	imap = imaplib.IMAP4_SSL(host, 993, timeout=30)
	try:
		imap.login(user, password)
		status = imap.status(FOLDER, "(UIDVALIDITY UIDNEXT)")[1][0].decode()
	finally:
		try:
			imap.logout()
		except Exception:
			pass
	validity = int(re.search(r"UIDVALIDITY (\d+)", status).group(1))
	uidnext = int(re.search(r"UIDNEXT (\d+)", status).group(1))
	return validity, uidnext
