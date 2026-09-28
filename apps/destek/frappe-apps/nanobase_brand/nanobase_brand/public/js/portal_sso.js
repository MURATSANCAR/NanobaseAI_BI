// Portal oturumuyla otomatik giriş: misafir Destek giriş sayfasına gelince portalın giriş servisine gider;
// portal oturumu varsa imzalı jetonla geri döner ve oturum açılır (nanobase_brand/sso.py).
// Portal oturumu yoksa servis ?sso=0 ile buraya geri yollar ve AD şifre formu görünür (döngü yok).
(function () {
	if (window.location.pathname !== "/login") return;
	var query = new URLSearchParams(window.location.search);
	if (query.get("sso") === "0") return;
	var status = document.documentElement.getAttribute("frappe-session-status") ||
		(document.body && document.body.getAttribute("frappe-session-status"));
	if (status === "logged-in") return;
	var next = query.get("redirect-to") || "/helpdesk";
	if (next.charAt(0) !== "/" || next.indexOf("//") === 0) next = "/helpdesk";
	// Portal aynı ana makinede, varsayılan portta (çerezi Path=/timas/).
	var portal = window.location.protocol + "//" + window.location.hostname;
	window.location.replace(portal + "/timas/auth/destek-sso?next=" + encodeURIComponent(next));
})();
