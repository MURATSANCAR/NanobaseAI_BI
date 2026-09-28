// Masaüstü «Hakkında» penceresi: yalnız NanobaseAI adı ve sürüm.
// Üst kaynağın penceresi çatı adını, dış bağlantıları ve telif satırını gösterir; burada hiçbiri yok.
frappe.provide("frappe.ui.misc");

frappe.ui.misc.about = function () {
	if (!frappe.ui.misc.nb_about) {
		const dialog = new frappe.ui.Dialog({ title: __("About") });
		const version = frappe.boot.nanobase_version;
		$(dialog.body).html(
			`<div class="nb-about">
				<img src="/assets/nanobase_brand/images/logo-mark.svg" alt="NanobaseAI" width="48" height="48">
				<div class="nb-about-name">NanobaseAI</div>
				${version ? `<div class="nb-about-sub">${__("Version")} ${frappe.utils.escape_html(version)}</div>` : ""}
			</div>`
		);
		frappe.ui.misc.nb_about = dialog;
	}
	frappe.ui.misc.nb_about.show();
};
