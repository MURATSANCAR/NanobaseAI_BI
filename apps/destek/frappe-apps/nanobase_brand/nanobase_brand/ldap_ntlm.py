"""Timaş Active Directory girişi: çatının LDAP ayarı, portal girişiyle aynı yöntemle.

Çatı basit bağlama (simple bind) yapar; etki alanı denetleyicisinde sertifika yok, basit bağlama
şifreyi VPN üzerinden açık metin taşır. Portal girişi (scripts/server/portal-login/server.py) bu
yüzden NTLM kullanır; burada da aynısı yapılır:

- Hizmet hesabı `TIMAS\\timasai` NTLM ile bağlanır, kişi etkin AD kişileri arasında hesap adıyla
  aranır, sonra kişinin kendi şifresiyle `TIMAS\\<hesap>` olarak NTLM ile yeniden bağlanılır.
- E-posta AD'de boşsa `hesap@<dns etki alanı>` kullanılır (çatının kullanıcısısı e-posta ister).
- Her AD kişisi temsilcidir: `HD Agent` kaydı ilk girişte açılır (kullanıcı kararı 2026-09-28:
  destek ekranı AD ile entegre; kim portala giriyorsa burada da temsilci).
- Şifre değiştirme buradan yapılmaz; AD şifresi yalnız AD'de değişir.

`hooks.py` → override_doctype_class["LDAP Settings"]. Ayarları `nanobase_brand.ad.ensure_ldap` yazar.
"""

from __future__ import annotations

import hashlib

import frappe
from frappe import _
from frappe.integrations.doctype.ldap_settings.ldap_settings import LDAPSettings

ACTIVE_PERSON = "(&(objectCategory=person)(objectClass=user)(sAMAccountName={0})(!(userAccountControl:1.2.840.113556.1.4.803:=2)))"


def ensure_md4() -> None:
	"""NTLM MD4 ister; OpenSSL 3 çıkardı, pycryptodome'da var (portal girişindeki yamanın aynısı)."""
	try:
		hashlib.new("md4", b"")
		return
	except ValueError:
		pass
	from Crypto.Hash import MD4

	builtin = hashlib.new

	class Md4:
		def __init__(self, data=b""):
			self.h = MD4.new(data)

		def update(self, data):
			self.h.update(data)

		def digest(self):
			return self.h.digest()

	hashlib.new = lambda name, data=b"", **kw: Md4(data) if name.lower() == "md4" else builtin(name, data, **kw)


class NtlmLDAPSettings(LDAPSettings):
	@property
	def netbios(self) -> str:
		# Bağlanan hesap `ETKİALANI\hesap` biçiminde yazılır; etki alanı oradan okunur.
		return (self.base_dn or "").split("\\", 1)[0]

	@property
	def dns_domain(self) -> str:
		parts = [p.split("=", 1)[1] for p in (self.ldap_search_path_user or "").split(",") if p.strip().upper().startswith("DC=")]
		return ".".join(parts)

	def connect_to_ldap(self, base_dn, password, read_only=True):
		import ldap3
		from ldap3.core.exceptions import LDAPBindError, LDAPInvalidCredentialsResult, LDAPException

		ensure_md4()
		host = (self.ldap_server_url or "").removeprefix("ldap://")
		host, _sep, port = host.partition(":")
		server = ldap3.Server(host, port=int(port or 389), get_info=ldap3.NONE, connect_timeout=5)
		try:
			return ldap3.Connection(
				server,
				user=base_dn,
				password=password,
				authentication=ldap3.NTLM,
				auto_bind=True,
				read_only=read_only,
				raise_exceptions=True,
				receive_timeout=10,
			)
		except (LDAPBindError, LDAPInvalidCredentialsResult):
			frappe.throw(_("Invalid username or password"))
		except LDAPException as exc:
			frappe.log_error(title="AD bağlantısı kurulamadı")
			frappe.throw(_("Directory is unreachable right now. Please try again later."))

	def authenticate(self, username: str, password: str):
		import ldap3
		from ldap3.core.exceptions import LDAPBindError, LDAPInvalidCredentialsResult
		from ldap3.utils.conv import escape_filter_chars

		if not self.enabled:
			frappe.throw(_("LDAP is not enabled."))
		account = (username or "").strip()
		if "\\" in account:
			account = account.split("\\", 1)[1]
		if "@" in account:
			account = account.split("@", 1)[0]
		if not account or not password:
			frappe.throw(_("Invalid username or password"))

		conn = self.connect_to_ldap(self.base_dn, self.get_password(raise_exception=False))
		try:
			conn.search(
				search_base=self.ldap_search_path_user,
				search_filter=self.ldap_search_string.format(escape_filter_chars(account)),
				attributes=self.get_ldap_attributes() + ["userPrincipalName"],
				size_limit=2,
			)
			if len(conn.entries) != 1:
				frappe.throw(_("Invalid username or password"))
			entry = conn.entries[0]
			groups = self.fetch_ldap_groups(entry, conn)
			sam = str(entry[self.ldap_username_field].value)
			try:
				ok = conn.rebind(user=f"{self.netbios}\\{sam}", password=password, authentication=ldap3.NTLM)
			except (LDAPBindError, LDAPInvalidCredentialsResult):
				ok = False
			if not ok:
				frappe.throw(_("Invalid username or password"))
			user = self.create_or_update_user(self.convert_ldap_entry_to_dict(entry), groups=groups)
			ensure_agent(user)
			ensure_admin(user, sam)
			return user
		finally:
			conn.unbind()

	def provision(self, account: str):
		"""Portal oturumuyla gelen kişiyi şifresiz bulur ve açar (kimliği portal girişi AD'ye karşı doğruladı).
		Yalnız etkin AD kişisi; bulunamazsa None."""
		from ldap3.utils.conv import escape_filter_chars

		conn = self.connect_to_ldap(self.base_dn, self.get_password(raise_exception=False))
		try:
			conn.search(
				search_base=self.ldap_search_path_user,
				search_filter=self.ldap_search_string.format(escape_filter_chars(account)),
				attributes=self.get_ldap_attributes() + ["userPrincipalName"],
				size_limit=2,
			)
			if len(conn.entries) != 1:
				return None
			entry = conn.entries[0]
			groups = self.fetch_ldap_groups(entry, conn)
			user = self.create_or_update_user(self.convert_ldap_entry_to_dict(entry), groups=groups)
			ensure_agent(user)
			ensure_admin(user, str(entry[self.ldap_username_field].value))
			return user
		finally:
			conn.unbind()

	def convert_ldap_entry_to_dict(self, user_entry):
		def value(field):
			if not field or field not in user_entry.entry_attributes:
				return None
			v = user_entry[field].value
			return str(v).strip() if v not in (None, "", []) else None

		sam = value(self.ldap_username_field)
		mail = value(self.ldap_email_field) or f"{sam}@{self.dns_domain}"
		data = {"username": sam, "email": mail.lower(), "first_name": value(self.ldap_first_name_field) or sam}
		for key, field in (("last_name", self.ldap_last_name_field), ("phone", self.ldap_phone_field),
						   ("mobile_no", self.ldap_mobile_field)):
			if v := value(field):
				data[key] = v
		return data

	def reset_password(self, user: str, password: str, logout_sessions: int = 0):
		frappe.throw(_("Directory passwords are changed in Active Directory, not here."))


def ensure_admin(user, account: str) -> None:
	"""Portalın yönetici listesi (TIMAS_ADMIN_USERS) burada da yönetici: site ayarı `destek_admin_users`."""
	admins = {a.strip().lower() for a in (frappe.conf.get("destek_admin_users") or "").split(",") if a.strip()}
	if account.lower() in admins:
		missing = {"Agent Manager", "System Manager"} - {r.role for r in user.get("roles")}
		if missing:
			user.add_roles(*missing)


def ensure_agent(user) -> None:
	"""AD'den gelen kişi temsilcidir: HD Agent kaydı yoksa açılır, pasifse bırakılır (yönetici kararı)."""
	if not frappe.db.exists("DocType", "HD Agent") or frappe.db.exists("HD Agent", user.name):
		return
	frappe.get_doc(
		{
			"doctype": "HD Agent",
			"user": user.name,
			"agent_name": user.full_name or user.first_name or user.name,
			"is_active": 1,
		}
	).insert(ignore_permissions=True)
