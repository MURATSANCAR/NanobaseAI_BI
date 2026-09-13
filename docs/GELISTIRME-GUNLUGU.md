# Geliştirme Günlüğü

Kronolojik kayıt. En yeni en üstte. Hiç silinmez, sadece eklenir. "Ne zaman ne oldu" sorusunun cevabı — canlı özet için [PROJECT-MEMORY.md](../PROJECT-MEMORY.md)'ye bak.

Her giriş: tarih, ne yapıldı/değişti, neden (varsa).

---

## 2026-09-13

- Tüm dallar `main`e merge edildi (`perf/full-overhaul-2026-08`, `claude/interesting-dhawan-1fa99d`, `claude/timesfm-repo-review-a60864`, `claude/vpn-crm-database-connection-91863b`, `claude/whatlaunched-dashboard-submit-1b30a9`, `claude/zeki-timas-planning-b75b7f`, `claude/project-memory-dev-log-5c3fa0`) ve kaynak dallar silindi (worktree'de checkout'lu olanlar hariç — onlar ilgili oturumlar kapanınca silinecek). Karar: bundan sonra tek trunk `main`, kalıcı ikinci dal açılmayacak. Kural: [AGENTS.md](../AGENTS.md#tek-branch-kuralı-yalnız-main). Sınır: remote'a push/silme, bu ortamda GitHub kimlik doğrulaması (gh CLI) olmadığı için henüz yapılamadı — yalnız local main güncel.
- CLAUDE.md + PROJECT-MEMORY.md + bu günlük kuruldu. Amaç: her oturumun proje mimarisini/geçmişini otomatik okuyup güncel tutması. Sınır: bu bir talimat, hook değil — oturumdaki Claude talimatı okuyup uygularsa çalışır, zorlayıcı bir mekanizma değil. Gerçek zorlama (`.claude/settings.json` hook, örn. commit sonrası günlük kontrolü) istenirse ayrı bir iş olarak yapılabilir.
