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

app_logo_url = "/assets/nanobase_brand/images/logo-mark.svg"

website_context = {
	"favicon": "/assets/nanobase_brand/images/favicon.svg",
	"splash_image": "/assets/nanobase_brand/images/logo-mark.svg",
}

# Ayarlar her göçte yeniden yazılır; ekrandan elle değiştirilen marka alanı
# bir sonraki kurulumda NanobaseAI'ye döner (bilinçli: marka tek yerden gelir).
after_install = "nanobase_brand.install.apply"
after_migrate = ["nanobase_brand.install.apply"]
