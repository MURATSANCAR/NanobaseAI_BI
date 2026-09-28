"""LDAP Settings'i Timaş AD'ye göre yazar (kurulum betiği çağırır).

    sudo cat /etc/nanobase/timas-ad.json | docker compose exec -T backend \
        bench --site destek execute nanobase_brand.ad.ensure_ldap
Ayar standart girişten okunur: şifre komut satırına (süreç listesine) düşmez.

Girdi portal girişinin ayar dosyasıyla aynı: host, port, netbios, dns_domain, base_dn, bind_user,
bind_password (+ isteğe bağlı admin_group, admin_users). Şifre çatının şifreli alanında saklanır.
"""

import json
import sys

import frappe

from nanobase_brand.ldap_ntlm import ACTIVE_PERSON


def ensure_ldap(config: dict | str | None = None) -> str:
	if config is None:
		config = json.load(sys.stdin)
	elif isinstance(config, str):
		config = frappe.parse_json(config)
	host, port = config["host"], int(config.get("port") or 389)
	base = config["base_dn"]
	doc = frappe.get_single("LDAP Settings")
	doc.update(
		{
			"enabled": 1,
			"ldap_directory_server": "Active Directory",
			"ldap_server_url": f"ldap://{host}:{port}",
			"base_dn": f"{config['netbios']}\\{config['bind_user']}",
			"password": config["bind_password"],
			"ldap_search_path_user": base,
			"ldap_search_path_group": base,
			"ldap_search_string": ACTIVE_PERSON,
			"ldap_username_field": "sAMAccountName",
			"ldap_email_field": "mail",
			"ldap_first_name_field": "givenName",
			"ldap_last_name_field": "sn",
			"ldap_phone_field": "telephoneNumber",
			"ldap_mobile_field": "mobile",
			"ssl_tls_mode": "Off",
			# Her etkin AD kişisi temsilcidir; yönetici grubu ayrıca yönetici rolleri alır.
			"default_user_type": "System User",
			"default_role": "Agent",
			"do_not_create_new_user": 0,
		}
	)
	group = (config.get("admin_group") or "").strip()
	doc.set("ldap_groups", [])
	if group:
		for role in ("Agent Manager", "System Manager"):
			doc.append("ldap_groups", {"ldap_group": group, "erpnext_role": role})
	doc.flags.ignore_permissions = True
	doc.save()
	if config.get("admin_users") is not None:
		from frappe.installer import update_site_config

		update_site_config("destek_admin_users", str(config["admin_users"]))
	frappe.db.commit()
	return "ok"
