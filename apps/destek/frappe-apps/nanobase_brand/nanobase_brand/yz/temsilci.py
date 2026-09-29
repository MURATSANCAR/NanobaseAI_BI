"""Rol modeli (2026-09-29 kullanıcı: «BT her şeyi görecek, kullanıcılar sadece kendi tasklarını»).

Temsilci (bütün kayıtları görür, masayı kullanır): AD birimi `nb_temsilci_birimleri` listesinde olan (vars. «BT»),
portalın yönetici listesindeki (`destek_admin_users`) ya da AD yönetici grubundan yönetici rolü almış kişi.
Talep eden (diğer herkes): temsilci kaydı ve temsilci rolleri yoktur; talep portalında yalnız kendi kayıtlarını görür.

`esitle` her sabah (hooks) ve kurulumda koşar: BT birimindekileri, hiç giriş yapmamış olsalar da, kullanıcı + temsilci +
BT ekibi üyesi yapar (ekibin atama kuralı onlara iş dağıtır); artık temsilci olmaması gerekenleri talep edene indirir.
Girişte ve portal oturumuyla girişte aynı kural ldap_ntlm.rol_uygula ile uygulanır.
"""

from __future__ import annotations

import frappe

YONETICI_ROLLERI = ("System Manager", "Agent Manager")


def birimler() -> set[str]:
	from nanobase_brand.ldap_ntlm import _fold

	return {_fold(b) for b in str(frappe.conf.get("nb_temsilci_birimleri") or "BT").split(",") if b.strip()}


def yoneticiler() -> set[str]:
	return {a.strip().lower() for a in (frappe.conf.get("destek_admin_users") or "").split(",") if a.strip()}


def temsilci_mi(account: str, department: str, user=None) -> bool:
	from nanobase_brand.ldap_ntlm import _fold

	if _fold(department or "") in birimler() or (account or "").lower() in yoneticiler():
		return True
	roller = {r.role for r in user.get("roles")} if user is not None else set()
	return bool(roller & set(YONETICI_ROLLERI))


def talep_eden_yap(user) -> bool:
	"""Temsilci kaydını ve temsilci rollerini kaldırır; kişi talep portalını kullanır. Değişiklik olduysa True."""
	degisti = False
	if frappe.db.exists("HD Agent", user.name):
		# Ekip kaydedilerek çıkarılır: ekibin atama kuralı da güncellenir, kişiye iş atanmaz.
		for ekip in set(frappe.get_all("HD Team Member", filters={"user": user.name, "parenttype": "HD Team"}, pluck="parent")):
			doc = frappe.get_doc("HD Team", ekip)
			doc.set("users", [u for u in doc.users if u.user != user.name])
			doc.save(ignore_permissions=True)
		frappe.delete_doc("HD Agent", user.name, force=True, ignore_permissions=True)
		degisti = True
	kaldir = [r.role for r in user.get("roles") if r.role in ("Agent",)]
	if kaldir:
		user.remove_roles(*kaldir)
		degisti = True
	if user.user_type != "Website User" and not ({r.role for r in user.get("roles")} & set(YONETICI_ROLLERI)):
		frappe.db.set_value("User", user.name, "user_type", "Website User")
		degisti = True
	return degisti


def esitle() -> dict:
	"""AD'deki BT birimini temsilci yapar, fazlalığı talep edene indirir."""
	from nanobase_brand.ldap_ntlm import ACTIVE_PERSON, _department, _fold, ensure_admin, ensure_agent, ensure_team
	from nanobase_brand.yz.cozum import bt_ekibi

	ldap = frappe.get_doc("LDAP Settings")
	if not ldap.enabled:
		return {"atlandi": "AD kapalı"}
	bt_ekibi()
	conn = ldap.connect_to_ldap(ldap.base_dn, ldap.get_password(raise_exception=False))
	temsilciler: set[str] = set()
	eklenen = 0
	try:
		kayitlar = conn.extend.standard.paged_search(
			search_base=ldap.ldap_search_path_user, search_filter=ACTIVE_PERSON.format("*"),
			attributes=ldap.get_ldap_attributes(), paged_size=500, generator=False)
		sam_alani = ldap.ldap_username_field
		for e in kayitlar:
			if e.get("type") != "searchResEntry":
				continue
			attrs = e.get("attributes") or {}
			sam = attrs.get(sam_alani)
			sam = (sam[0] if isinstance(sam, list) and sam else sam) or ""
			dep = attrs.get("department")
			dep = (dep[0] if isinstance(dep, list) and dep else dep) or ""
			if not dep:
				ous = [p.split("=", 1)[1] for p in e["dn"].split(",") if p.strip().upper().startswith("OU=")]
				dep = ous[0] if ous else ""
			if not (_fold(dep) in birimler() or str(sam).lower() in yoneticiler()):
				continue
			conn.search(search_base=e["dn"], search_filter="(objectClass=person)", attributes=ldap.get_ldap_attributes())
			if len(conn.entries) != 1:
				continue
			entry = conn.entries[0]
			yeni = not frappe.db.exists("User", {"username": str(sam)})
			# AD grupları da verilir: boş listeyle çağrılırsa yönetici grubundan gelen roller düşerdi (sync_roles).
			user = ldap.create_or_update_user(ldap.convert_ldap_entry_to_dict(entry),
											  groups=ldap.fetch_ldap_groups(entry, conn))
			ensure_agent(user)
			ensure_admin(user, str(sam))
			if _fold(dep) in birimler():
				ensure_team(user, dep)
			temsilciler.add(user.name)
			eklenen += int(yeni)
	finally:
		conn.unbind()

	indirilen = 0
	for ajan in frappe.get_all("HD Agent", pluck="name"):
		if ajan in temsilciler or ajan == "Administrator":
			continue
		user = frappe.get_doc("User", ajan)
		if temsilci_mi(user.username or "", "", user):
			continue
		indirilen += int(talep_eden_yap(user))
	frappe.db.commit()
	return {"temsilci": len(temsilciler), "yeni_kullanici": eklenen, "talep_edene_indirilen": indirilen}
