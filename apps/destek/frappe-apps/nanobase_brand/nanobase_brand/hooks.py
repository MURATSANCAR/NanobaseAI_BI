app_name = "nanobase_brand"
app_title = "NanobaseAI"
app_publisher = "NanobaseAI"
app_description = "NanobaseAI marka katmanı"
app_email = "destek@nanobase.ai"
app_license = "agpl-3.0"

# Masaüstü (/app, /desk) ve web sayfaları (/login vb.) aynı temayı alır.
# Destek ekranı (/helpdesk) kendi Vue derlemesinde aynı jetonları taşır:
# helpdesk/desk/src/nanobase-theme.css.
app_include_css = ["/assets/nanobase_brand/css/nanobase.css"]
web_include_css = ["/assets/nanobase_brand/css/nanobase.css"]
# Giriş sayfası portal oturumunu dener (tek oturum): nanobase_brand/sso.py
web_include_js = ["/assets/nanobase_brand/js/portal_sso.js"]

# AD girişi portal girişiyle aynı yöntemle (NTLM): nanobase_brand/ldap_ntlm.py
override_doctype_class = {"LDAP Settings": "nanobase_brand.ldap_ntlm.NtlmLDAPSettings"}

app_logo_url = "/assets/nanobase_brand/images/logo-mark.svg"

website_context = {
	"favicon": "/assets/nanobase_brand/images/favicon.svg",
	"splash_image": "/assets/nanobase_brand/images/logo-mark.svg",
}

# Ayarlar her göçte yeniden yazılır; ekrandan elle değiştirilen marka alanı
# bir sonraki kurulumda NanobaseAI'ye döner (bilinçli: marka tek yerden gelir).
after_install = "nanobase_brand.install.apply"
after_migrate = ["nanobase_brand.install.apply"]

# Yapay zekâ özellikleri: nanobase_brand/yz/
doc_events = {
	"HD Ticket": {
		"after_insert": "nanobase_brand.yz.kanca.on_ticket_insert",
		"on_update": "nanobase_brand.yz.kanca.on_ticket_update",
	},
}

scheduler_events = {
	"cron": {
		# Hafta içi 08:30: SLA riskindeki kayıtlar; pazartesi 08:00: haftalık rapor
		"30 8 * * 1-5": ["nanobase_brand.yz.rapor.daily_sla_risk"],
		"0 8 * * 1": ["nanobase_brand.yz.rapor.weekly"],
	},
}
