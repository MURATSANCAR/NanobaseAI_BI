app_name = "nanobase_brand"
app_title = "ZEKİ AI"
app_publisher = "ZEKİ AI"
app_description = "ZEKİ AI marka katmanı"
app_email = "destek@nanobase.ai"
app_license = "agpl-3.0"

# Masaüstü (/app, /desk) ve web sayfaları (/login vb.) aynı temayı alır.
# Destek ekranı (/helpdesk) kendi Vue derlemesinde aynı jetonları taşır:
# helpdesk/desk/src/nanobase-theme.css.
app_include_css = ["/assets/nanobase_brand/css/nanobase.css"]
web_include_css = ["/assets/nanobase_brand/css/nanobase.css"]
# Giriş sayfası portal oturumunu dener (tek oturum): nanobase_brand/sso.py
web_include_js = ["/assets/nanobase_brand/js/portal_sso.js"]
# Masaüstünde «Hakkında» penceresi markalıdır: public/js/nanobase_desk.js
app_include_js = ["/assets/nanobase_brand/js/nanobase_desk.js"]
extend_bootinfo = ["nanobase_brand.boot.extend"]

# AD girişi portal girişiyle aynı yöntemle (NTLM): nanobase_brand/ldap_ntlm.py
override_doctype_class = {
	"LDAP Settings": "nanobase_brand.ldap_ntlm.NtlmLDAPSettings",
	# Destek gelen kutusu yalnız hesabın açıldığı andan sonra geleni alır: nanobase_brand/eposta.py
	"Email Account": "nanobase_brand.eposta.NanobaseEmailAccount",
}

app_logo_url = "/assets/nanobase_brand/images/logo-mark.svg"

website_context = {
	"favicon": "/assets/nanobase_brand/images/favicon.svg",
	"splash_image": "/assets/nanobase_brand/images/logo-mark.svg",
}

# Ayarlar her göçte yeniden yazılır; ekrandan elle değiştirilen marka alanı
# bir sonraki kurulumda ZEKİ AI'ya döner (bilinçli: marka tek yerden gelir).
# Marka adı değişince (2026-09-29 NanobaseAI → ZEKİ AI) eski adlı kayıtlar göçten önce taşınır: Flow kendi göçünde
# yeni adla ikinci bir asistan açmasın.
before_migrate = ["nanobase_brand.install.eski_adlar"]
after_install = "nanobase_brand.install.apply"
after_migrate = ["nanobase_brand.install.apply"]

# Merkezi denetim kaydı (portalın Yönetim → Denetim kaydı): nanobase_brand/denetim.py
before_request = ["nanobase_brand.denetim.istek_basi"]
after_request = ["nanobase_brand.denetim.istek"]

# Yapay zekâ özellikleri: nanobase_brand/yz/
doc_events = {
	"*": {
		"after_insert": "nanobase_brand.denetim.after_insert",
		"on_update": "nanobase_brand.denetim.on_update",
		"on_trash": "nanobase_brand.denetim.on_trash",
		"on_submit": "nanobase_brand.denetim.on_submit",
		"on_cancel": "nanobase_brand.denetim.on_cancel",
	},
	"HD Ticket": {
		"after_insert": "nanobase_brand.yz.kanca.on_ticket_insert",
		"on_update": "nanobase_brand.yz.kanca.on_ticket_update",
	},
	# Otomatik çözüm önerisinden sonra talep edenin yanıtı (yz/cozum.py).
	"Communication": {
		"after_insert": "nanobase_brand.yz.kanca.on_communication_insert",
	},
}

scheduler_events = {
	"cron": {
		# Hafta içi 08:30: SLA riskindeki kayıtlar; pazartesi 08:00: haftalık rapor
		"30 8 * * 1-5": ["nanobase_brand.yz.rapor.daily_sla_risk"],
		"0 8 * * 1": ["nanobase_brand.yz.rapor.weekly"],
		# Öneriye süresinde yanıt gelmeyen kayıt BT'ye (saat başı); BT temsilcileri AD'den (her sabah).
		"5 * * * *": ["nanobase_brand.yz.cozum.zaman_asimi"],
		"15 6 * * *": ["nanobase_brand.yz.temsilci.esitle"],
		# Denetim olaylarının giden kutusu merkeze (dakikada bir).
		"* * * * *": ["nanobase_brand.denetim.gonder"],
	},
}
