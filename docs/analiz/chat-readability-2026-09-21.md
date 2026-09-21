# Kitaba sor: yanıt okunaklılığı

2026-09-21. Kullanıcının paylaştığı uzun satırlı yanıt ekranına yönelik sunum düzenlemesi.

- Kaynak metindeki boş satırlar paragraf sınırı olarak kullanılır; metin yeniden yazılmaz.
- Yanıt en fazla 65ch; balon masaüstünde en fazla min(80%,72ch).
- Mobil 15px, 768px ve üzeri 16px; satır yüksekliği 1.8; paragraflar arasında 1em.
- Sayfa referansları aynı ayrıştırıcıyla korunur; kontrastlı, satır içinde bölünmeyen rozetler.
- Avatar üstte; mobil iç boşluk 14px, masaüstünde 20px. Uzun kelimeler kapsayıcı içinde kırılır.

## Yayın

Sunucu: nanobase-direct. Kaynak: /data/nanobaseai/bi/frontend.
`VITE_BASE=/timas/ VITE_ENGINE_BASE=/timas npm run build -- --outDir /tmp/chat-readability-dist-20260921`
TypeScript/Vite derlemesi geçti. Yerel test çalıştırılmadı.
İlk derlemede eksik ENGINE_BASE tarayıcı kontrolünde yakalandı; önceki index geri alındı ve iki değişkenle yeniden derlendi.
Yayın: /data/nanobaseai/bi/cockpit/dist; index-BFs-u7jN.js / index-DEOmko_y.css.

Yerel ve sunucu kaynak SHA-256 değerleri eş:
- AskBox.tsx: 54b2e803147a121dd31a173f01b849b2ccc53dac039c14e1f0bbe86f5fc604df
- canvas.css: 43afd41dee85d3b3aac086637591d00a39d8386e3ca69bfca821697a44ad7f29

## Doğrulama

Gerçek oturumlu test portalında sunucudaki Chromium ile 320/390/768/1440px kontrolü; hiçbir ağ yanıtı taklit edilmez. Soru: Dünyanın En Korkak Hayvanı kitabının yayıncı yaş aralığı ve kaynak sayfası.

Dört genişlikte scrollWidth tam viewport genişliğine eş; yatay taşma yok. Gerçek API 502 döndürdü (390px ekran görüntüsünde Zeki AI 502). Yanıt oluşmadı; yanıt balonu, paragraf ve kaynak gösterimi gerçek veriyle **DOĞRULANAMADI**. Genel sohbet semantik/üretim kabulü verilmedi. Kanıt: `chat-readability-2026-09-21-evidence.json`; sunucuda `/tmp/chat-readability-{320,390,768,1440}.png`, koşucu `/tmp/chat-readability.cjs`.
