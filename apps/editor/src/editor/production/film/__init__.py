"""Kitaptan film: çizgi film, kitap fragmanı ve sosyal medya kısa videosu (reels) — tek hat (2026-10-04).

Kullanıcı kararı: «paralelde hem sosyal medya paylaşımları hem de çizgi film için uçtan uca yapı». İki ürün aynı hattır;
farkı biçimdir (`spec.FORMATS`): en-boy oranı, süre, altyazının görüntüye basılması, ilk saniyelerin kancası.

Hat (bir film = stüdyo işinin altında `film/<fid>/`, store.py):

    1. senaryo   (script.py)   ana model kitabın özetinden çekim listesini yazar; her çekim kitaptaki bir cümleye bağlı
    2. oyuncular (cast.py)     karakter kartı (characters.py) + ses kataloğundan ses (voices_zeki)    → EDİTÖR ONAYI
    3. ses       (dialogue.py) replikler duygusuyla seslendirme servisinde okunur; çekim süresi sese göre ayarlanır
    4. kareler   (frames.py)   her çekimin ilk karesi görsel modelde, karakter kartı referansıyla      → EDİTÖR ONAYI
    5. çekim     (shoot.py)    ilk kare video modelinde hareketlenir (gateway `book-video`), gece kuyruğu
    6. kurgu     (mix.py)      çekimler + replik + efekt + ortam sesi; konuşmada kısma, ses düzeyi; altyazı
    7. paylaşım  (social.py)   platform kesitleri, kapak karesi, açıklama ve etiket taslağı             → EDİTÖR ONAYI

Hiçbir adım dışarıya gönderim yapmaz: sosyal medyaya otomatik paylaşım yoktur, onaylı dosya indirilir. Ekranda model ya
da teknoloji adı geçmez («Zeki AI»). Kurallar kitaptan bağımsızdır; kitaba özel ayar yoktur.
Sözleşme: docs/analiz/film-ve-sosyal-medya-hatti.md.
"""
