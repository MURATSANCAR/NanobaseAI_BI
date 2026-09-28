"""Giden e-posta hesabı: BI'ın uyarı/rapor e-postasıyla aynı Gmail hesabı (zeki@).

Kurulum betiği SMTP ayarını köprünün yönetim ayarlarından (ALERT_SMTP_*) okuyup standart girişten verir;
şifre (Gmail uygulama şifresi) komut satırına ve depoya düşmez, sitede şifreli alanda durur.
Yalnız gönderim: gelen kutusu okunmaz (zeki@ kutusu destek adresi değil; ayrı adres gelince açılır).
Kaydederken sistem SMTP'ye giriş yapıp dener; yanlış şifre kurulumu durdurur.
"""

import json
import sys

import frappe

ACCOUNT = "NanobaseAI Destek"


def ensure_outgoing(config: dict | None = None) -> str:
	cfg = json.load(sys.stdin) if config is None else config
	port = int(cfg.get("port") or 587)
	values = {
		"email_id": cfg["user"],
		"email_account_name": ACCOUNT,
		"password": cfg["password"],
		"awaiting_password": 0,
		"enable_incoming": 0,
		"enable_outgoing": 1,
		"default_outgoing": 1,
		"smtp_server": cfg.get("host") or "smtp.gmail.com",
		"smtp_port": port,
		"use_tls": 1 if port == 587 else 0,
		"use_ssl_for_outgoing": 1 if port == 465 else 0,
		"always_use_account_email_id_as_sender": 1,
		"always_use_account_name_as_sender_name": 1,
		"add_signature": 0,
	}
	name = frappe.db.get_value("Email Account", {"email_account_name": ACCOUNT}, "name")
	if name:
		doc = frappe.get_doc("Email Account", name)
		doc.update(values)
		doc.save(ignore_permissions=True)
	else:
		doc = frappe.get_doc({"doctype": "Email Account", **values}).insert(ignore_permissions=True)
	frappe.db.commit()
	return doc.name
