import frappe
from frappe.desk.form.assign_to import add as add_assign

AUTHOR_EMAIl = "ornek.musteri@example.com"
AUTHOR_NAME = "Örnek Müşteri"
CONTENT = """
<div style="font-family: 'DM Sans', 'Segoe UI', sans-serif; font-size: 15px; line-height: 1.8; color: #1b1f2a; max-width: 560px; margin: 0 auto;">
Merhaba{{ " " + first_name if first_name else "" }},
<br><br>
Bu örnek kayıt, ZEKİ AI destek ekranının nasıl çalıştığını göstermek için oluşturuldu.
<br><br>
<b>Etkinlik alanı:</b> kayda verdiğiniz her yanıt hemen altta, kaydın geçmişinde görünür; bütün yazışma tek yerde durur.
<br><br>
<b>Yanıtla</b> dediğinizde mesajınız doğrudan kişinin e-posta kutusuna gider.
<br><br>
<b>Yorum</b> yalnız ekip arkadaşlarınızın gördüğü iç nottur; müşteriye gitmez.
<br><br>
<b>Kayıt kenar çubuğunda</b> kaydı kendinize ya da bir arkadaşınıza atar, önceliği, türü ve durumu değiştirirsiniz.
<br><br>
<b>Kayıt başlığında</b> ilk yanıt ve çözüm süreleri ile kaydın nereden geldiği (e-posta ya da destek portalı) görünür.
<br><br>
Sonraki adımlar:<br>
<ul style="padding-left: 20px; margin: 0;">
  <li>Destek e-posta adresinizi bağlayın; gerçek kayıtlar gelmeye başlasın.</li>
  <li>Ekibinizi davet edin, atama kurallarıyla kayıtları otomatik dağıtın.</li>
  <li>Yanıt sürelerini yönetmek için hizmet seviyesi (SLA) tanımlayın.</li>
  <li>Kendi kendine yardım için bilgi bankası makaleleri ekleyin.</li>
</ul>
<br>
ZEKİ AI
</div>
"""


def create_welcome_ticket():
    create_contact()
    create_ticket()


def create_ticket():
    if frappe.db.count("HD Ticket"):
        return

    # Render template with the current user's information
    user_doc = frappe.get_doc("User", frappe.session.user)
    if (user_doc.name or "").strip().lower() == "administrator":
        first_name = ""
    else:
        first_name = (user_doc.first_name or "").strip()
    rendered_content = frappe.render_template(
        CONTENT,
        {
            "first_name": first_name,
        },
        safe_render=True,
    )

    d = frappe.new_doc("HD Ticket")
    d.subject = "ZEKİ AI'ya hoş geldiniz"
    d.description = rendered_content
    d.raised_by = AUTHOR_EMAIl
    d.contact = AUTHOR_NAME
    d.via_customer_portal = True
    d.insert()
    add_assign(
        {
            "doctype": "HD Ticket",
            "name": d.name,
            "assign_to": ["Administrator"],
        }
    )


def create_contact():
    frappe.get_doc(
        {
            "doctype": "Contact",
            "first_name": AUTHOR_NAME,
            "email_ids": [{"email_id": AUTHOR_EMAIl, "is_primary": 1}],
        }
    ).insert()
