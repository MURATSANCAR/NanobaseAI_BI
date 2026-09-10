# Üç açık tema

`index.html` karşılaştırma sayfasıdır. Her tasarım ayrı HTML dosyası olarak açılır.

1. `01-porcelain.html`: Porselen / Kobalt, beyaz sol menü ve mavi analitik ekran.
2. `02-emerald.html`: Krem / Zümrüt, üst menü ve editoryal finans görünümü.
3. `03-lavender.html`: Buz / Lavanta, dar ikon menüsü ve merkezde soru alanı.

Üç tasarım Stitch API ile aynı projede üretildi:
https://stitch.withgoogle.com/projects/9228120035083968175

## ZEKİ AI

Orijinal GIF, Git geçmişindeki `a8dd0e6aa57bc497128ee710bfafa8db831f7528`
commit'inin `apps/cockpit/public/zeki-ai.gif` dosyasından değiştirilmeden alındı.
Aynı sürümün Sidebar ve Splash bileşenleri bu dosyayı kullanıyordu.
GIF `assets/zeki-ai.gif` konumundadır; üç HTML'deki `brand-motion-slot` alanına
kırpılmadan yerleştirilmiştir.

Stitch ekranları ilk üretimde orbital yer tutucu içerir. Yerel HTML dosyaları
gerçek GIF eklenen son sürümlerdir. `*-stitch.png` dosyaları orijinal Stitch
görselleri; diğer PNG'ler GIF eklenmiş HTML'lerin tarayıcı görüntüleridir.

Bu dosyalar örnek verili görsel prototiplerdir. API/DB bağlantısı ve canlı portala
dağıtım yapılmamıştır. Harici Tailwind CDN ve fontlar için internet gerekir.
API anahtarı kaydedilmemiştir.
