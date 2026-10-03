# Sesli okuma: kendi ses kataloğumuz (2026-10-03)

Kullanıcı kararı: «mevcut seslerimizi sil, sadece bunları kullanacağız». Önce film karakteri gibi kalın sesli yaşlı
erkek sesleri istendi, beğenildi; aynı yöntemle Timaş kitap türlerine göre okuyucu sesleri üretildi.

## Yöntem

- Model: bizim seslendirme modelimiz (VoxCPM2, Apache-2.0), gateway `book-voice`. Ses yalnız yazılı İngilizce tariften
  tasarlandı (`voice.design`): gerçek kişi kaydı, klon, dış ses havuzu yok. Atıf/lisans gerektirmez.
- Her tarif 4 tohumla (11, 23, 47, 89) aynı cümleyi okudu, `measure: true` ile ölçüldü: temel frekans (f0), sesli
  oranı, Türkçe tanıyıcıyla harf hatası (cer).
- Seçim: cer ≤ %5 ve sesli oranı ≥ 0,5 olan adaylardan erkekte en kalın, kadında tarife uygun perde (alçak/kadife
  denenlerde düşük). Kullanıcı dinleyip onayladı.
- Cümleler: okuyucu seti «Kitabın ilk sayfasını açtığında…» (`voices_zeki.READER_TEXT`), film seti «Yıllar önce, bu
  dağların ardında…» (`FILM_TEXT`). Seçilen kayıt pakette sabit (`production/sesler/zeki/<ses>.wav`, sha256 kodda),
  klonda referans metni kaydın cümlesidir.
- Üretim betikleri GPU'da ayrı konteynerde koştu (editör kurulumları worker'ı yeniden başlatınca betik ölüyordu);
  ham adaylar `tt-gpu:/data/ses-tasarim/{derin-erkek,okuyucu}/` (wav + ölçüm json).

## Seçilen sesler

| Ses | Grup | Tohum | f0 (Hz) | cer |
|---|---|---|---|---|
| roman-kadin | yetişkin | 89 | 172,7 | 0,013 |
| roman-erkek | yetişkin | 23 | 95,2 | 0,026 |
| tarih-kadin | yetişkin | 11 | 177,7 | 0,026 |
| tarih-erkek | yetişkin | 23 | 93,1 | 0,026 |
| tasavvuf-kadin | yetişkin | 47 | 199,5 | 0,020 |
| tasavvuf-erkek | yetişkin | 47 | 89,9 | 0,026 |
| gelisim-kadin | yetişkin | 47 | 191,6 | 0,020 |
| gelisim-erkek | yetişkin | 23 | 132,4 | 0,033 |
| deneme-kadin | yetişkin | 11 | 167,8 | 0,033 |
| deneme-erkek | yetişkin | 47 | 92,0 | 0,020 |
| genc-kadin | genç | 23 | 216,3 | 0,020 |
| genc-erkek | genç | 23 | 136,3 | 0,026 |
| masal-anne | çocuk | 89 | 206,5 | 0,020 |
| masal-baba | çocuk | 89 | 99,7 | 0,026 |
| masal-nine | çocuk | 47 | 218,8 | 0,013 |
| masal-dede | çocuk | 11 | 99,2 | 0,039 |
| bilge-dede | karakter | 11 | 96,4 | 0,029 |
| karanlik-lord | karakter | 11 | 108,8 | 0,029 |
| yasli-kral | karakter | 11 | 120,7 | 0,039 |
| yasli-kaptan | karakter | 89 | 126,4 | 0,049 |
| fragman-anlatici | karakter | 11 | 127,9 | 0,029 |

Gözlem: «extremely deep / very deep bass» tarifinde bazı tohumlar perdeyi 150–190 Hz'e çıkardı ya da sesli oranı
0,05–0,25'e düştü (fısıltı/hırıltı) — tohum taraması bu yüzden şart. Küçük çocuk sesleri (8 yaş) kalitede tutmadı,
katalogdan çıkarıldı; çocuk karakteri genç ses okur.

## Kaldırılanlar

Tarifli 25 ses, «canlı masal anlatıcısı» 6 ses, Alania havuzundan 19 referans (CC BY 4.0 atıf yükü de kalktı).
Eski kimlikler `voices_zeki.ALIASES` ile en yakın yeni sese gider; kayıtlı kitap ayarı bozulmaz, ses değişen sayfalar
«güncel değil» olur, eski ses dosyaları silinmez. Yayınevinin yüklediği ses kütüphanesi (kutuphane) boştu.
