"""Portal oturumuyla otomatik giriş (tek oturum).

Portal oturum çerezi `Path=/timas/` ile yazılır; Destek (ayrı port, kök yol) onu göremez. Akış:

1. Destek'in giriş sayfası misafiri portalın `/timas/auth/destek-sso?next=…` adresine yollar
   (`public/js/portal_sso.js`); tarayıcı oraya portal çerezini gönderir.
2. Portal giriş servisi (scripts/server/portal-login/server.py) oturumu okur, 60 sn'lik tek kullanımlık
   imzalı jetonla buraya döner: `/api/method/nanobase_brand.sso.login?t=…&next=…`.
3. Burada imza (`destek_sso_secret`, iki tarafta aynı anahtar), süre ve tek kullanım denetlenir; kişi AD'den
   bulunur (ilk gelişte kaydı açılır, temsilci olur) ve oturum açılır.

Portal oturumu yoksa servis kişiyi `/login?sso=0` ile Destek'in kendi AD girişine geri yollar.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import re
import sys
import time
from urllib.parse import quote

import frappe
from frappe import _

ACCOUNT = re.compile(r"^[A-Za-z0-9._-]{1,64}$")
NONCE_TTL = 300


def _b64(raw: str) -> bytes:
	return base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))


def _safe_next(value: str | None) -> str:
	value = value or "/helpdesk"
	return value if value.startswith("/") and not value.startswith("//") and "\\" not in value else "/helpdesk"


def verify(token: str, secret: str, now: float | None = None) -> dict:
	"""Jetonun imzası, süresi ve biçimi doğruysa içeriği; değilse ValueError."""
	if not secret or not token or token.count(".") != 1:
		raise ValueError("biçim")
	payload, sig = token.split(".")
	good = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
	if not hmac.compare_digest(_b64(sig), good):
		raise ValueError("imza")
	data = json.loads(_b64(payload))
	if not isinstance(data, dict) or int(data.get("exp", 0)) < (now or time.time()):
		raise ValueError("süre")
	if not ACCOUNT.match(str(data.get("u", ""))) or not data.get("n"):
		raise ValueError("içerik")
	return data


@frappe.whitelist(allow_guest=True, methods=["GET"])
def login(t: str | None = None, next: str | None = None):
	target = _safe_next(next)
	try:
		data = verify(t or "", frappe.conf.get("destek_sso_secret") or "")
	except (ValueError, TypeError, json.JSONDecodeError):
		return _to_form(target)
	# Tek kullanım: aynı jeton ikinci kez oturum açmaz.
	key = f"nanobase_sso_nonce:{data['n']}"
	if frappe.cache.get_value(key):
		return _to_form(target)
	frappe.cache.set_value(key, 1, expires_in_sec=NONCE_TTL)

	user = _user_for(data["u"])
	if not user:
		return _to_form(target)
	frappe.local.login_manager.login_as(user)
	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = target


def _to_form(target: str):
	"""Portal oturumu kullanılamadı: Destek'in kendi AD giriş formu (sso=0 döngüyü keser)."""
	frappe.local.response["type"] = "redirect"
	frappe.local.response["location"] = f"/login?sso=0&redirect-to={quote(target, safe='/')}"


def _user_for(account: str) -> str | None:
	name = frappe.db.get_value("User", {"username": account}, "name")
	if name:
		return name if frappe.db.get_value("User", name, "enabled") else None
	# İlk geliş: AD'den (hizmet hesabıyla, şifresiz arama) kaydı aç; portal oturumu kişiyi zaten doğruladı.
	ldap = frappe.get_doc("LDAP Settings")
	if not ldap.enabled:
		return None
	user = ldap.provision(account)
	frappe.db.commit()
	return user.name if user else None


def set_secret() -> str:
	"""Kurulum betiği anahtarı standart girişten verir: komut satırına düşmez."""
	from frappe.installer import update_site_config

	secret = sys.stdin.read().strip()
	if len(secret) < 32:
		frappe.throw(_("SSO key is too short."))
	update_site_config("destek_sso_secret", secret)
	return "ok"
