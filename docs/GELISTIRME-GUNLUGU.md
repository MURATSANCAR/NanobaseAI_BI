# Geliştirme Günlüğü

Kronolojik kayıt. En yeni en üstte. Hiç silinmez, sadece eklenir. "Ne zaman ne oldu" sorusunun cevabı — canlı özet için [PROJECT-MEMORY.md](../PROJECT-MEMORY.md)'ye bak.

Her giriş: tarih, ne yapıldı/değişti, neden (varsa).

---

## 2026-09-14

- Girişten sonraki ilk ekran **Kampüs** oldu: Stitch ekranı "Timaş Intranet · Kampüs & ZEKİ Akıllı Rehber Tuvali" (`projects/13426839861607265553/screens/a6864de4…`) JSX'e çevrildi → `src/canvas/kampus/KampusPage.tsx`, görseller `src/assets/kampus/`. Tasarıma tek ekleme "Modüller" kartı: kanvas ekranlarına geçiş + `modules.json`'daki 67 modülün listesi (açık/yakında).
- Rota değişti: `/` = Kampüs, BI genel bakış (CFO kanvası) `/genel-bakis`'e taşındı. Ray, dock ve modül menüsündeki "Genel bakış" bağlantıları güncellendi; raya "Kampüs" dönüş bağlantısı eklendi.
- Kampüs'teki ZEKİ soru kutusu `/genel-bakis?soru=…` adresine gider; BiCanvasPage soruyu bir kez motora gönderip adresten siler.
- Sınır: rehber, odalar, kutlamalar, ajanda, bülten, yemekhane içerikleri tasarımdaki sabit metinler; henüz bir veri kaynağına bağlı değil. Tarayıcıda doğrulama sunucuda yapılmadı.

## 2026-09-13

- portal.nanobase.ai/timas/ veri getirmiyor → teşhis: sunucudaki `openvpn-client@timas` 2026-09-12 06:29'dan beri WatchGuard `AUTH_FAILED` ile kapalı, `tun0` yok; socat `:14330` TCP kabul ettiği için port açık görünüyor ama köprü (:8795) FreeTDS `08001 Unable to connect` alıyor. `muratsancar` hesabı MFA (push/OTP) istediği için servis kendi kendine bağlanamıyor; 12 Eylül 22:08/22:14'te başlatılmış iki interaktif openvpn işlemi kod bekleyerek asılı. Düzeltme kullanıcı/TİMAŞ BT tarafında (servis hesabı şifresi + MFA muafiyeti). Erişim bilgileri kullanıcı isteğiyle yerel proje belleğine (`timas-access-credentials`) kaydedildi; güvenlik nedeniyle repo'ya yazılmadı. Doğrulama: DOĞRULANAMADI — VPN açılana kadar canlı veri kontrolü yapılamaz.
- Tüm dallar `main`e merge edildi (`perf/full-overhaul-2026-08`, `claude/interesting-dhawan-1fa99d`, `claude/timesfm-repo-review-a60864`, `claude/vpn-crm-database-connection-91863b`, `claude/whatlaunched-dashboard-submit-1b30a9`, `claude/zeki-timas-planning-b75b7f`, `claude/project-memory-dev-log-5c3fa0`) ve kaynak dallar silindi (worktree'de checkout'lu olanlar hariç — onlar ilgili oturumlar kapanınca silinecek). Karar: bundan sonra tek trunk `main`, kalıcı ikinci dal açılmayacak. Kural: [AGENTS.md](../AGENTS.md#tek-branch-kuralı-yalnız-main). Sınır: remote'a push/silme, bu ortamda GitHub kimlik doğrulaması (gh CLI) olmadığı için henüz yapılamadı — yalnız local main güncel.
- CLAUDE.md + PROJECT-MEMORY.md + bu günlük kuruldu. Amaç: her oturumun proje mimarisini/geçmişini otomatik okuyup güncel tutması. Sınır: bu bir talimat, hook değil — oturumdaki Claude talimatı okuyup uygularsa çalışır, zorlayıcı bir mekanizma değil. Gerçek zorlama (`.claude/settings.json` hook, örn. commit sonrası günlük kontrolü) istenirse ayrı bir iş olarak yapılabilir.
