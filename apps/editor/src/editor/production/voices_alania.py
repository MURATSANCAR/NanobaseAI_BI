"""Alania havuzundan alınan ses referansları (2026-10-01, kullanıcı isteği: «mevcut sesler çok robotik»).

Kaynak: «Alania Turkish Synthetic Speech», PatientDesk AI —
https://huggingface.co/datasets/cloud0day3/alania-synthetic-speech-tr, `voices` yapılandırması (2.752 tasarlanmış ses,
her birinin referans kaydı + metni + İngilizce tarifi; 48 kHz). Lisans CC BY 4.0: ticari kullanım serbest, atıf şart
(atıf metni `ATTRIBUTION`, ayrıca `sesler/alania/KAYNAK.md`). Kayıtların hepsi yapay zekâ üretimidir, gerçek kişi sesi
yoktur; üretici bizim seslendirme modelimizle aynıdır (aynı adım sayısı ve yönlendirme gücü), yani klonlama yolu değişmez,
yalnız referans kayıt değişir.

Seçim (docs/analiz/sesli-okuma-alania-sesleri.md): her sesimizin tarifine göre (cinsiyet, yaş, perde, tını, hız)
havuzdan üç aday; aynı masal parçası mevcut referansla ve her adayla aynı ayar ve tohumla okutuldu, doğallık (UTMOS22)
ve harf hatası (Türkçe tanıyıcı) ölçüldü. Aday, harf hatası ≤ %5 ve perdesi cinsiyetine uygunsa ve doğallıkta mevcut
sesi geçiyorsa alındı; geçemeyen ses (ve havuzda karşılığı olmayan çocuk sesleri) tarifli/sabit referansında kalır.

Kayıt `narration.PINNED` düzenindedir: dosya pakette (`sesler/alania/<alania kimliği>.wav`, imajla gelir), sha256 burada;
dosya yoksa ya da özeti tutmazsa ses üretilmez. Referans metni havuzdaki kaydın metnidir (tam klon kipi metinle çalışır).
"""

from __future__ import annotations

ATTRIBUTION = ("Alania Turkish Synthetic Speech, PatientDesk AI "
               "(https://huggingface.co/datasets/cloud0day3/alania-synthetic-speech-tr), CC BY 4.0 lisansıyla.")


def _p(alania: str, text: str, sha256: str) -> dict:
    return {"file": f"alania/{alania}.wav", "text": text, "sha256": sha256, "source": "alania", "alania": alania}


# ses kimliği → havuzdaki ses (ölçüm tablosu: docs/analiz/sesli-okuma-alania-sesleri.md)
PINNED: dict[str, dict] = {
    # Male speaker, in their forties, deep and rich and resonant, soft; calm and matter-of-fact delivery a…
    # 5.0 sn; doğallık bugünkü 3.66/3.70 → 4.02/3.94 (iki metin)
    "anlatici-erkek-masalci": _p("d2-01970", "İyi günler, işleminizi hemen kontrol ediyorum, lütfen bir saniye bekleyin.",
                                  "067e4b3d818d904d7f480fffed6f6da514ee526c1e4a97264cd5b64ca88fdc04"),
    # A crisp, clear, medium-pitched female voice: a woman in her forties, speaking at a measured pace in …
    # 5.0 sn; doğallık bugünkü 3.88/3.75 → 4.03/4.03 (iki metin)
    "anlatici-kadin-berrak": _p("d1-01705", "Günaydın, aradığınız için teşekkür ederim. Randevunuzu birlikte ayarlayalım.",
                                 "9b501a79e3648c5d25fe9d6b889e3ce6019cdf29bf4c06eccb20ef0c43d8aaac"),
    # Female speaker, in their fifties, medium-pitched and warm, velvety; lively and kind delivery at a sl…
    # 5.1 sn; doğallık bugünkü 3.71/3.66 → 4.00/3.99 (iki metin)
    "anlatici-kadin-kadife": _p("d2-01501", "Günaydın, aradığınız için teşekkür ederim. Randevunuzu birlikte ayarlayalım.",
                                 "8cb6ceba63f1a7687e998fe690e00fe6f52cf44978376df1bed879da880a93dc"),
    # A clear, high-pitched female voice: a woman in her thirties, speaking at a measured pace in a animat…
    # 5.8 sn; doğallık bugünkü 3.51/2.93 → 3.92/3.52 (iki metin)
    "anlatici-kadin-canli": _p("d1-01247", "Şehrin eski sokaklarında yürürken her köşede başka bir güzellikle karşılaşıyorsunuz.",
                                "35d64b547989ae7885742f09d3ea1ceba01125a2294a8fdb3027fa1522826775"),
    # A man in his thirties with a high-pitched, soft voice, gentle and calm, speaking at a slow pace like…
    # 4.5 sn; doğallık bugünkü 3.99/3.92 → 4.07/4.16 (iki metin)
    "anlatici-erkek-abi": _p("d2-00325", "Günaydın, aradığınız için teşekkür ederim. Randevunuzu birlikte ayarlayalım.",
                              "d3941f8bb77d38611d929ffaf330fbc37d39e0efba937d6b3081eac94a490ef5"),
    # A woman in her thirties with a medium-pitched, warm voice, kind and relaxed, speaking at a slow pace…
    # 6.6 sn; doğallık bugünkü 3.36/3.50 → 4.19/4.25 (iki metin)
    "masal-kadin-anne": _p("d1-00082", "Yeni dönemde müşterilerimize daha hızlı ve daha kolay bir hizmet sunmayı hedefliyoruz.",
                            "3931c60f1156732580c0b4bdcb286368d718d07a5087e8c19a3dd5e8d5c5cf85"),
    # Female speaker, young adult, medium-high and bright; animated and kind delivery at a slow pace; clea…
    # 5.3 sn; doğallık bugünkü 2.80/2.02 → 3.64/4.00 (iki metin)
    "masal-kadin-ogretmen": _p("d2-01558", "Yeni dönemde müşterilerimize daha hızlı ve daha kolay bir hizmet sunmayı hedefliyoruz.",
                                "547497ea0ea0c317cd8105b51749c4b3b675ed018c5a65ba03577d5254934f9f"),
    # A man in his thirties with a low-pitched, breathy voice, reassuring and calm, speaking at a moderate…
    # 4.8 sn; doğallık bugünkü 3.71/3.61 → 3.93/3.94 (iki metin)
    "masal-erkek-baba": _p("d1-02563", "Toplantıyı perşembe gününe erteledik, yeni saat bilgisini size mesajla göndereceğim.",
                            "7b9bb142f93be864d43239efdeed11ff81d5df3f6570b849fc1cc263d242009b"),
    # A breathy, low-pitched male voice: a man in his forties, speaking at a slow pace in a composed, kind…
    # 5.3 sn; doğallık bugünkü 3.03/2.86 → 3.97/4.00 (iki metin)
    "masal-erkek-ogretmen": _p("d2-01366", "Yeni dönemde müşterilerimize daha hızlı ve daha kolay bir hizmet sunmayı hedefliyoruz.",
                                "c98aef1c29a0bdd6df83328a7b45a414317e3a11e742d3990e49920796bf6a62"),
    # A clear, medium-high female voice: a woman in her fifties, speaking at a slow pace in a even, though…
    # 5.0 sn; doğallık bugünkü 3.47/3.48 → 3.83/4.09 (iki metin)
    "yetiskin-kadin-deneme": _p("d1-01100", "Bahçedeki elma ağaçları bu yıl her zamankinden daha erken çiçek açtı.",
                                 "4816113acc0837686b5ea05c48ebfb808ae2a7ab0913c1d840da05ef8481b704"),
    # A soft, crisp, medium-pitched female voice: a woman in her thirties, speaking at a slow pace in a re…
    # 5.4 sn; doğallık bugünkü 3.44/3.15 → 3.66/3.63 (iki metin)
    "yetiskin-kadin-cagdas": _p("d2-00819", "Sabah erkenden yola çıktık ve öğleye doğru küçük bir sahil kasabasına vardık.",
                                 "1e97d8a44b257360adb4964e57368df026a7e99647b27be643e534ba3df3198d"),
    # Male speaker, in their forties, low-pitched and clear; lively and thoughtful delivery at a moderate …
    # 5.4 sn; doğallık bugünkü 2.90/2.90 → 4.05/3.71 (iki metin)
    "yetiskin-erkek-deneme": _p("d1-00890", "İyi günler, işleminizi hemen kontrol ediyorum, lütfen bir saniye bekleyin.",
                                 "3a001774005e9001070ac4b045a76f0c9b648775e69d1e707d3643529f3035f4"),
    # Male speaker, in their thirties, medium-pitched and smooth, clear; relaxed and confident delivery at…
    # 5.4 sn; doğallık bugünkü 3.02/3.12 → 3.75/4.01 (iki metin)
    "yetiskin-erkek-cagdas": _p("d2-00496", "Bu akşam hava biraz serinleyecek, yanınıza ince bir ceket almanızı öneririm.",
                                 "5c76bed11c2d6b0bc942d09fb680e6c6df9dff87e3ca1e8f7deae8e5d3f0f283"),
    # A soft, medium-pitched female voice: a young adult woman, speaking at a measured pace in a animated,…
    # 4.5 sn; doğallık bugünkü 3.46/3.68 → 4.11/3.78 (iki metin)
    "genc-kadin": _p("d2-00980", "Bahçedeki elma ağaçları bu yıl her zamankinden daha erken çiçek açtı.",
                      "9c6e7ce3fa228d0038905eee498fc75c75e5204106ed0da832250dabcc9d5916"),
    # A clear, medium-pitched male voice: a young adult man, speaking at a slow pace in a lively, enthusia…
    # 4.8 sn; doğallık bugünkü 2.60/2.35 → 3.68/3.90 (iki metin)
    "genc-erkek": _p("d2-01852", "Bu akşam hava biraz serinleyecek, yanınıza ince bir ceket almanızı öneririm.",
                      "77899aaa238e89bf28f99e7dc21c0744f3bad30940ffb4f084ee74f66d9a4cc8"),
    # A gentle, medium-pitched female voice: an elderly woman, speaking at a slow pace in a composed, conf…
    # 6.6 sn; doğallık bugünkü 2.63/2.43 → 3.98/3.87 (iki metin)
    "yasli-kadin": _p("d2-00651", "Sabah erkenden yola çıktık ve öğleye doğru küçük bir sahil kasabasına vardık.",
                       "e0ee7aafca746a315497b7505e4ed736a41aadce2d1f373f779369cc74679968"),
    # An elderly man with a low-pitched, full-bodied voice, confident and relaxed, speaking at a slow pace…
    # 6.2 sn; doğallık bugünkü 2.91/2.82 → 3.75/3.54 (iki metin)
    "yasli-erkek": _p("d2-01420", "Bu akşam hava biraz serinleyecek, yanınıza ince bir ceket almanızı öneririm.",
                       "0b329225e1f66a336cfeaaf98f0148c172a9b98747a8b181c4d450c1292ef801"),
    # Female speaker, in their forties, low-pitched and warm; soft-spoken and thoughtful delivery at a mod…
    # 4.8 sn; doğallık bugünkü 3.64/3.71 → 3.79/3.87 (iki metin)
    "canli-kadin-sahne": _p("d1-02676", "Merhaba, ben sizin sesli asistanınızım. Size bugün nasıl yardımcı olabilirim?",
                             "f87f2b691358507436f753cabd16d82a32eb447fe1857b05cdc2e51b8fcb4a24"),
    # A woman in her sixties with a medium-pitched, soft, smooth voice, matter-of-fact and even, speaking …
    # 5.1 sn; doğallık bugünkü 3.67/3.54 → 4.01/4.05 (iki metin)
    "canli-kadin-nine": _p("d2-00665", "Siparişiniz hazırlandı ve yarın öğleden sonra adresinize teslim edilecek.",
                            "94e82acc48a5cb3414bf3604f717cf9ec4a9761f273af512d43b6e09190fb1bb"),
}
