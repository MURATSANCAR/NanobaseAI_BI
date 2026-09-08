# Gece kataloğu: güvenli yayın ve geri dönüş — 9 Eylül 2026

## Uygulama

- Profil, madencilik, doküman ve sertifikalama adımları özel SQLite aday kopyasında çalışır. Başarısız adım sonraki aşamaya geçmez.
- Aday mevcut sertifikalı kavramları kaybediyorsa otomatik yayın durur. Kalite tabanı yoksa yeni taban kendiliğinden oluşturulmaz.
- Kalite kapısı eksik/geçersiz ölçümü, değişmiş soru kümesini, artan reddi ve soru bazında tablo kaybını başarısız sayar. Toplamdaki başka iyileşme bu kaybı gizleyemez.
- Yayın PostgreSQL işlemi ve tablo kilitleriyle yapılır. Değerlendirme sırasında canlı katalog değiştiyse aday yayınlanmaz.
- Servis yenilemesi yönetici kimliğiyle doğrulanır. Yayın sonrası kalite veya yenileme hatasında kavramlar, eşlemeler, formüller, kanıtlar, adaylar, profiller ve öneriler geri alınır. Yeni sürüm numarası monoton artar.
- Sorgu kayıtları ve kullanıcı açıklamaları geri yüklemede değiştirilmez. Kapsam dışındaki kaynak verileri değiştirilmez. Profil/öneri tablolarının kapsamı mevcut şemadaki datasource_id anahtarıdır.
- Kalıcı günlük yarıda kesilmiş yayını sonraki başlangıçta kurtarır. Yayın sonrası eşzamanlı kullanıcı değişikliği varsa üzerine yazılmaz; iş açık hata verir.
- systemd artık aynı betiği çalıştırır. Denetim dışı, hatası yutulan ikinci reload kaldırıldı. Veritabanı bekleme komutu doğru Service bölümüne ve Bash yorumlayıcısına taşındı.

## Kanıt

- Semantik test paketi: **420 geçti**, 2 uyarı; `SEMANTIC_TABLE_SELECTOR=off`.
- Bunun içinde gece yayın/kalite kapısı için **21 test**: aday kalite hatası, yayın sonrası hata, iki reload hata yolu, sorgu kaydı korunması, eşzamanlı değişiklik, yarıda kalmış yayın, atomik işlem, sertifikalı kavram kaybı, eksik/NaN/sonsuz ölçüm ve soru bazında gerileme.
- Üretim metadata yedeği ayrı `nightly_acceptance_20260909` PostgreSQL veritabanına geri yüklendi. Gerçek katalog kopyası özel SQLite adaya taşındı, formüller/profiller değiştirildi, yayınlandı ve yayın sonrası kasıtlı hata üretildi. Geri dönüşte değişebilir tabloların SHA-256 içerik özeti başlangıçla aynı; sorgu kayıtları ve açıklamalar aynı; reload çağrısı 2; günlük durumu `rolled_back`.
- Kopyadaki kapsam: 1.017 kavram, 1.017 eşleme, 1.789 kanıt, 433 karşı kanıt, 4.352 aday, 4.121 profil, 54 öneri, 3 açıklama, 10 sürüm, 1.244 sorgu kaydı. Test veritabanı sonunda kaldırıldı. Üretim kataloğuna bu hata deneyi uygulanmadı.
- Python derleme ve Bash sözdizimi kontrolleri geçti. Sunucudaki Python modülü, kalite kapısı ve betik SHA-256 değerleri yerelle eşleşti.
- Sunucu kurulumu tamamlandı; köprü ve gece zamanlayıcısı active. Eski betik ve servis yedekleri `/data/nanobaseai/bi/backups/nightly-release-20260909` altında.

## Sınırlar

Bu çalışma tam gece taramasının tamamlandığı anlamına gelmez. Güç kesilmesi/SIGKILL durumunda kurtarma bir sonraki iş başlangıcındadır; kesinti anında çalışan bir geri dönüş garantisi yoktur. Profil → madencilik → sertifikalama akışının yeni düzenle ilk zamanlanmış çalışması ayrıca izlenmelidir. Kalite kapısı şema seçimini ölçer; iş rakamlarının doğruluğunu kanıtlamaz. Tarayıcıdan kullanıcı kabulü için mevcut giriş oturumu, bağımsız iş doğruluğu için geliştirmede kullanılmamış sorular ve onaylı referanslar hâlâ gereklidir.

Canlı 48 soruluk kalite ölçümü sonucu ayrıca kaydedilecek.
