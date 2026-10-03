# Sesli okuma: Alania havuzundan ses referansları (2026-10-01)

Kullanıcı isteği: «https://huggingface.co/datasets/cloud0day3/alania-synthetic-speech-tr … buradaki sesleri al bizim
sisteme ekle ve değiştir, bizdeki mevcut sesler çok robotik.»

## Veri seti

- «Alania Turkish Synthetic Speech», PatientDesk AI. 3.451 saat, 2.051.810 kayıt, 48 kHz; 2.752 tasarlanmış ses
  (`voices` yapılandırması: her sesin referans kaydı + metni + İngilizce tarifi).
- Lisans: `cc-by` ve `voices` CC BY 4.0, `cc-by-sa` CC BY-SA 4.0. Ticari kullanım serbest, **atıf şart**. Atıf metni
  `apps/editor/src/editor/production/voices_alania.py` → `ATTRIBUTION` ve `sesler/alania/KAYNAK.md`.
- Kayıtların hepsi yapay zekâ üretimi; gerçek kişi sesi yok. **Üretici bizim seslendirme modelimizle aynı** (VoxCPM2,
  10 adım, yönlendirme 2,0). Bu yüzden modeli değiştirmiyoruz, yalnız klonlamada kullanılan referans kaydı
  değiştiriyoruz. Robotiklik modelin kendisinden geliyorsa referans değiştirmek bunu tamamen gidermez. Ölçüm,
  referans seçiminin büyük fark yarattığını gösterdi (aşağıda).
- Havuzda çocuk sesi yok (yaş en düşük «young adult»). «Küçük kız» ve «Küçük oğlan» tarifli seste kaldı.

## Yöntem

1. Aday: her sesimizin tarifinden cinsiyet (zorunlu), yaş, perde, tını ve hız; havuzun tarifleri üzerinde puanlama,
   ses başına 3 aday (bir aday iki sese verilmez). Betik: GPU `/data/editor/ses-havuzu/alania/sec.py`.
2. Metin 1 (4 cümle, ünlem + soru + fısıltı): bugünkü referansla ve her adayla aynı ayar ve tohumla (7) okutuldu
   (tam klon: kayıt + metni). Ölçüm: doğallık UTMOS22 (SpeechMOS, 1–5), harf hatası (servisin `measure`'ı), perde.
3. Uygun aday: harf hatası ≤ %5 ve perde cinsiyete uygun (kadın > 165 Hz, erkek < 150 Hz). En yüksek doğallıklı uygun
   aday metin 2 (diyalog, 4 cümle, tohum 11) ile bugünkü sesle yeniden karşılaştırıldı.
4. Karar kuralı: aday **iki metinde de** bugünkü sesi geçer ve ortalama fark **≥ +0,15** ise ses değişir. Tek ölçümdeki
   +0,05–0,10 farkları gürültü sayıldı.

Dinleme sayfası (116 kayıt): https://claude.ai/artifact/NFxDuoqaFeHeer3NML14dB. Ham çıktılar GPU
`/data/editor/ses-havuzu/alania/` (`out/`, `out2/`, `mos*.json`, `rapor.json`, `karar.json`, `secim.json`).

## Sonuç: 19 ses değişti, 12 ses aynı kaldı

Varsayılan anlatıcılar (Kadın anlatıcı 4,21/4,00; radyo oyuncusu 4,06/3,98) havuzdaki adaylardan iyi ölçüldü, aynı
kaldı. En büyük kazanç bugün zayıf olan seslerde: karakter sesleri (Genç erkek +1,32, Yaşlı kadın +1,39), anaokulu
öğretmeni +1,41, sınıf öğretmeni +1,04, deneme okuyucusu (erkek) +0,98.

| Ses | Kimlik | Bugünkü (metin 1 / 2) | En iyi uygun aday | Aday (metin 1 / 2) | Ortalama fark | Karar |
|---|---|---|---|---|---:|---|
| Kadın anlatıcı | `anlatici-kadin` | 4.21 / 4.00 | `d1-02397` | 3.68 / 3.97 | -0.28 | aynı |
| Erkek anlatıcı · sıcak masalcı | `anlatici-erkek-masalci` | 3.66 / 3.70 | `d2-01970` | 4.02 / 3.94 | +0.29 | **değişti** |
| Kadın · berrak anlatıcı | `anlatici-kadin-berrak` | 3.88 / 3.75 | `d1-01705` | 4.03 / 4.03 | +0.22 | **değişti** |
| Kadın · kadife ses | `anlatici-kadin-kadife` | 3.71 / 3.66 | `d2-01501` | 4.00 / 3.99 | +0.32 | **değişti** |
| Kadın · canlı anlatıcı | `anlatici-kadin-canli` | 3.51 / 2.93 | `d1-01247` | 3.92 / 3.52 | +0.50 | **değişti** |
| Erkek · anlatıcı ağabey | `anlatici-erkek-abi` | 3.99 / 3.92 | `d2-00325` | 4.07 / 4.16 | +0.16 | **değişti** |
| Erkek · radyo tiyatrosu | `anlatici-erkek-radyo` | 3.89 / 3.80 | `d2-00786` | 3.96 / 3.95 | +0.11 | aynı |
| Kadın · masal okuyan anne | `masal-kadin-anne` | 3.36 / 3.50 | `d1-00082` | 4.19 / 4.25 | +0.79 | **değişti** |
| Kadın · anaokulu öğretmeni | `masal-kadin-ogretmen` | 2.80 / 2.02 | `d2-01558` | 3.64 / 4.00 | +1.41 | **değişti** |
| Kadın · masalcı nine | `masal-kadin-nine` | 4.10 / 4.14 | `d2-00177` | 4.17 / 3.70 | -0.19 | aynı |
| Erkek · masal okuyan baba | `masal-erkek-baba` | 3.71 / 3.61 | `d1-02563` | 3.93 / 3.94 | +0.28 | **değişti** |
| Erkek · sınıf öğretmeni | `masal-erkek-ogretmen` | 3.03 / 2.86 | `d2-01366` | 3.97 / 4.00 | +1.04 | **değişti** |
| Erkek · masalcı dede | `masal-erkek-dede` | 3.79 / 3.93 | `d1-02100` | 3.78 / 3.33 | -0.30 | aynı |
| Kadın · roman okuyucusu | `yetiskin-kadin-roman` | 4.12 / 4.18 | `d1-02387` | 4.17 / 4.27 | +0.07 | aynı |
| Kadın · deneme okuyucusu | `yetiskin-kadin-deneme` | 3.47 / 3.48 | `d1-01100` | 3.83 / 4.09 | +0.49 | **değişti** |
| Kadın · çağdaş anlatı | `yetiskin-kadin-cagdas` | 3.44 / 3.15 | `d2-00819` | 3.66 / 3.63 | +0.35 | **değişti** |
| Erkek · roman okuyucusu | `yetiskin-erkek-roman` | 3.91 / 3.72 | `d2-01201` | 3.83 / 3.74 | -0.03 | aynı |
| Erkek · deneme okuyucusu | `yetiskin-erkek-deneme` | 2.90 / 2.90 | `d1-00890` | 4.05 / 3.71 | +0.98 | **değişti** |
| Erkek · çağdaş anlatı | `yetiskin-erkek-cagdas` | 3.02 / 3.12 | `d2-00496` | 3.75 / 4.01 | +0.81 | **değişti** |
| Genç kadın | `genc-kadin` | 3.46 / 3.68 | `d2-00980` | 4.11 / 3.78 | +0.38 | **değişti** |
| Genç erkek | `genc-erkek` | 2.60 / 2.35 | `d2-01852` | 3.68 / 3.90 | +1.32 | **değişti** |
| Yaşlı kadın | `yasli-kadin` | 2.63 / 2.43 | `d2-00651` | 3.98 / 3.87 | +1.39 | **değişti** |
| Yaşlı adam | `yasli-erkek` | 2.91 / 2.82 | `d2-01420` | 3.75 / 3.54 | +0.78 | **değişti** |
| Kadın · canlı masalcı | `canli-kadin-masalci` | 3.94 / 3.71 | `d2-00656` | 3.87 / 3.38 | -0.20 | aynı |
| Kadın · sahne anlatıcısı | `canli-kadin-sahne` | 3.64 / 3.71 | `d1-02676` | 3.79 / 3.87 | +0.15 | **değişti** |
| Kadın · heyecanlı nine | `canli-kadin-nine` | 3.67 / 3.54 | `d2-00665` | 4.01 / 4.05 | +0.42 | **değişti** |
| Erkek · canlı masalcı | `canli-erkek-masalci` | 3.82 / 3.98 | `d1-01202` | 3.66 / 3.75 | -0.20 | aynı |
| Erkek · radyo oyuncusu | `canli-erkek-radyo` | 4.06 / 3.98 | `d1-02436` | 3.52 / 3.68 | -0.42 | aynı |
| Erkek · macera anlatan dede | `canli-erkek-dede` | 4.04 / 4.03 | `d1-02386` | 3.88 / 3.82 | -0.18 | aynı |
| Küçük kız | `cocuk-kiz` | – | havuzda çocuk sesi yok | – | – | aynı |
| Küçük oğlan | `cocuk-erkek` | – | havuzda çocuk sesi yok | – | – | aynı |

## Etki

- Bu sesleri seçmiş kitaplarda sayfa sesleri «güncel değil» görünür (sayfa özeti referansın özetini taşır); yeniden
  seslendirme editörün işidir, kendiliğinden yapılmaz. İfade örnekleri (`_ses/ornek/`) referans özetine bağlı olduğu
  için yeni referansla kendiliğinden yenilenir.
- Referans metinleri havuzun cümleleridir (hizmet dili: «Günaydın, aradığınız için…»). Tam klon kipi bu metni
  referansla birlikte verir; ölçümde masal metnindeki doğallık yine de yükseldi.
- Eski «sıcak masalcı» sabit kaydı (`sesler/anlatici-erkek-masalci.wav`) silindi; ses artık Alania kaydıyla okur.

## Sınırlar

- Doğallık puanı otomatik bir tahmindir, dinlemenin yerini tutmaz; dinleme sayfasından kulakla itiraz edilen ses
  değiştirilir.
- İki metin, ses başına iki ölçüm. Çocuk kitabı diyaloğu ve uzun paragraf ayrıca dinlenmeli.
