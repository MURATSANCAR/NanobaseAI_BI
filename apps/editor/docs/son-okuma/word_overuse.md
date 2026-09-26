# Sık kullanılan sözcükler / yazar tikleri (`word_overuse`) — ÖLÇÜM BEKLİYOR

Kaynak: `src/editor/proofing/word_overuse.py`, `_word_variety.py` (`log_likelihood`, `overused`) (v1).

## Kural
Bir zarf, sıfat ya da fiil kitap boyunca yayınevinin öbür kitaplarından **anlamlı ölçüde sık** kullanılıyor
(«aslında», «sanki», «birden», «gülümsemek») ve model bunu yazarın dil alışkanlığı sayıyorsa: kitap geneli
WARN (sayfa yok). Adlar aday değildir: çoğunlukla kitabın konusudur («insan», «dünya»).

## Karar
1. Kök: `word_variety._read` (Zemberek; özel ad, bozuk span, hikâye dışı sayfa dışarıda).
2. Derlem: öbür kitapların en yeni başarılı `word_variety` koşusunun `stats.map` sayıları (bu kitap hariç).
   En az `EDITOR_WORD_OVERUSE_MIN_BOOKS` (3) kitap yoksa karşılaştırma yapılmaz (`stats.reason`).
3. Anahtar sözcük testi: log-likelihood G² ≥ 15,13 (1 sd, p < 0,0001) ve kitap oranı > derlem oranı.
4. Model (iki sıralı kapalı soru; kitap türü istemde, `book_type.describe`), üç örnek bağlamla (baş/orta/son):
   yazarın alışkanlığı mı, konunun/türün gereği mi. `p ≥ 0,5`.

## Eşikler
| eşik | değer | yer |
|---|---|---|
| `KEYNESS_G2` | 15,13 | `_word_variety` — p < 0,0001, alışılmış kesim |
| `MIN_BOOKS` | 3 | env `EDITOR_WORD_OVERUSE_MIN_BOOKS` |
| `J.KEEP` | 0,5 | iki yönlü seçimin argmax'ı |

## Bulgu
`page: null`, mesaj ««aslında» kitapta 212 kez geçiyor (10.000 sözcükte 61); yayınevinin öbür 15 kitabında
10.000 sözcükte 9 — 6,8 kat.», `details`: g2, per10k, corpus_per10k, ratio, pages, forms, examples, group.

## Bilinen sınırlar
Derlem yayınevinin okunmuş kitaplarıdır (tür karışık); çocuk kitabı yetişkin romanıyla kıyaslanır. Derlem
büyüdükçe ve tür bazında yeterli kitap oldukça tür içi karşılaştırma eklenebilir. «Hep dedi» gibi konuşma
fiili tekdüzeliği bu denetimde görünür (fiil).
