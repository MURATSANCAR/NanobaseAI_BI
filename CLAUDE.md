# Oturum başlangıcı

Her oturumda şu iki dosyayı oku:

1. [PROJECT-MEMORY.md](PROJECT-MEMORY.md) — canlı özet: proje ne, mimari, stack, sunucu/port yapısı, dizin haritası.
2. [docs/GELISTIRME-GUNLUGU.md](docs/GELISTIRME-GUNLUGU.md) — kronolojik günlük, en yeni en üstte.

İş bitince ikisini de güncelle:

- **PROJECT-MEMORY.md**: değişen mimari/stack/sunucu/dizin bilgisini üzerine yazarak düzelt (eski bilgiyi silip doğrusunu yaz — bu bir özet, arşiv değil).
- **docs/GELISTIRME-GUNLUGU.md**: en üste yeni bir tarih/madde ekle (ne yapıldı, neden). Var olan girişleri silme.

Sonra işi `main`e taşı — her geliştirmenin son adımıdır, ayrıca istenmesi gerekmez: dal/worktree'de çalışıldıysa `main` üstüne rebase, `main`e ileri sarma merge, dalı iki yerden sil. Adımlar ve "taşınmamış iş var mı" denetimi: [AGENTS.md](AGENTS.md) → «Her geliştirme bitiminde: main'e taşıma».

Çalışma kuralları (mobil uyumluluk, gerçek DB ile doğrulama zorunluluğu, tek branch, vb.) için: [AGENTS.md](AGENTS.md).

Not: bu bir talimattır, hook değil — güncelleme oturumdaki Claude'un bu dosyayı okuyup uygulamasına bağlıdır, zorlayıcı bir mekanizma değildir. Gerçek zorlama isteniyorsa `.claude/settings.json`'a bir hook eklenebilir (örn. commit sonrası günlüğün değişip değişmediğini kontrol eden bir kontrol) — bu ayrı, henüz yapılmamış bir iş.
