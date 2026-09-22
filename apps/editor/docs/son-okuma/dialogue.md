# Diyalog atfı ve ses (`dialogue`) — ÖLÇÜM BEKLİYOR

Durum (2026-09-22): kod yazıldı, saf parçalar sentetik testle doğrulandı
(`tests/test_dialogue.py`, 5 test). **Gerçek kitapta hiç koşmadı; replik okuyucunun kesinliği,
katılımcı kümesinin kapsamı ve eşikler ölçülmedi.** Ölçülene kadar bulgular yalnız editör adayıdır.

## 1. Editör ne bakar

- **Atıf:** replik sahnede olmayan birine verilmiş (Ali odada tek başınayken «Ayşe» konuşuyor).
- **Ses/hitap:** bir karakterin birine hitabı açıklamasız değişiyor (hep «abla» diyen birden
  «Ayşe» diyor; hep «hocam» diyen «Ali» diyor).

Çelişki OLMAYANLAR: uzaktan konuşma (telefon, mektup, ses), aktarılan/hatırlanan söz, rüya/hayal,
sonradan sahneye girme; hitapta kızgınlık, şaka, resmiyet, kimliğin öğrenilmesi, büyüme, başka
birine seslenme.

## 2. Replik okuma (`dialogue.read_lines`)

Director, parça başına 1 çağrı (düşünme kapalı, sıcaklık 0): `speaker`, `addressee`, `address_term`
(repliğin içindeki seslenme sözü, olduğu gibi), sayfa/paragraf/alıntı. Alıntı sayfada bulunmazsa
(`locate`) kayıt yok. Konuşan/hitap edilen karakter listesine `resolve_subject` ile eşlenir;
eşlenmeyen tahmin edilmez (`unknown_speaker` sayılır, satır konuşansız kalır ve aday olmaz).

## 3. A. Atıf (ölçülebilir tanım)

**Katılımcı kümesi** (sayfa → karakter kimlikleri, `dialogue.presence`):
o sayfayı kapsayan (`page_from ≤ p ≤ page_to`) kullanılabilir olayların `event_actor` satırları
(ACTOR/INVOLVED); olayın `event_actor` satırı yoksa çıkarımın `participants` adları eşlenir;
ayrıca o sayfada metinde anılan çözülmüş karakterler (`character_mention`, via TEXT/BOTH). Bütün
kipler dahil (rüyada da konuşulur).

**Aday:** konuşanı çözülmüş replik; konuşan `s.p ± DIALOGUE_PRESENCE_WINDOW` sayfalarının kümesinde
yok; küme boş değil (veri yoksa aday yok — kaçırma, yanlış alarm değil).

**Yargı:** iki farklı kapalı soru (her biri tek harf, logprobs):
1. «X bu sahnede var mı?» — V (var / uzaktan / aktarılan) · Y (yok) · B;
2. «Bu replik X'e ait olabilir mi?» — E (evet) · H (hayır, yanlış kişiye verilmiş) · B.

Bulgu ancak `min(P(Y), P(H)) ≥ DIALOGUE_JUDGE_MIN`. Kanıt: sayfa+alıntı (replik) ve o sayfanın
katılımcı listesi + kapsayan olay özetleri (`details.b`). Şiddet: olasılık ≥ `DIALOGUE_ERROR_MIN`
→ ERROR, aksi WARN.

## 4. B. Hitap/ses (ölçülebilir tanım)

Serbest «konuşma tarzı» ölçülemez; ölçülen, **hitap teriminin sınıfı**:

| sınıf | tanım (genel Türkçe sözlük, kitaba özel değil) |
|---|---|
| `AD` | hitap edilenin adı/takma adı (karakter kaydındaki ad ve alias'lar; kök eşleşir: «Ayşecik») |
| `AKRABALIK` | abla, abi/ağabey, anne, baba, dede, nine, teyze, amca, hala, dayı, kardeş, oğul, kız, yenge, enişte, torun, yavru, evlat (+ekler: «ablacığım») |
| `SAYGI` | efendi(m), hoca(m), öğretmen(im), bey, hanım, usta, doktor, müdür, sayın, komutan, kaptan |
| `LAKAP` | diğerleri |

Adı «Anne»/«Dede» olan karaktere «anne»/«dede» demek AD sayılır (sınıf değişmez, aday çıkmaz).

**Aday:** konuşan→hitap edilen çifti için en az `DIALOGUE_MIN_USES` hitap; bir sınıfın payı ≥
`DIALOGUE_DOMINANT_SHARE` → baskın sınıf; başka sınıftan her hitap (baskın örneğin sayfasından farklı
sayfada) aday. Aynı sınıf içi değişim («abla» → «ablacığım») aday değil.

**Yargı:** iki sırada kapalı soru (C/U/B); bulgu ancak `min(C_ileri, C_geri) ≥ DIALOGUE_JUDGE_MIN`.
Kanıt: baskın örnek (sayfa+alıntı+terim) ve sapan hitap (sayfa+alıntı+terim). Şiddet WARN.

Yazılmayan kısım: hitap dışındaki «konuşma tarzı» (cümle uzunluğu, argo, çocuksu dil) için
ölçülebilir, kitaptan bağımsız bir tanım kurulamadı — tarz iki sayfada doğal olarak değişir ve
eşik kitaba göre ayarlanmak zorunda kalırdı (proje kuralına aykırı). Yalnız hitap sınıfı yazıldı.

## 5. Eşikler (ayardan; hepsi ölçülmedi)

| ad | env | varsayılan | anlamı |
|---|---|---|---|
| `dialogue_judge_min` | `EDITOR_DIALOGUE_JUDGE_MIN` | 0.5 | iki soruda/sırada gereken «çelişki» olasılığı |
| `dialogue_error_min` | `EDITOR_DIALOGUE_ERROR_MIN` | 0.8 | atıfta bu üstü ERROR |
| `dialogue_parallel` | `EDITOR_DIALOGUE_PARALLEL` | 4 | eşzamanlı yargı çağrısı |
| `dialogue_presence_window` | `EDITOR_DIALOGUE_PRESENCE_WINDOW` | 1 | katılımcı kümesi kaç komşu sayfayı kapsar |
| `dialogue_min_uses` | `EDITOR_DIALOGUE_MIN_USES` | 3 | hitap adayı için çiftin en az hitap sayısı |
| `dialogue_dominant_share` | `EDITOR_DIALOGUE_DOMINANT_SHARE` | 0.6 | baskın sınıfın en az payı |

## 6. Model çağrısı sayısı

Replik okuyucu: parça başına 1 (director; 1–4). Yargı: aday başına 2 (atıfta iki farklı soru,
hitapta iki sıra). Kitap metni önek olduğu için önbellek çalışır.

## 7. Yanlış alarm / kaçırma riskleri

1. Katılımcı kümesi olay çıkarımına bağlı: olay çıkarımı eksikse (sahnede olan ama olaya
   yazılmayan karakter) yanlış aday; `character_mention` eklemesi bunu azaltır (metinde adı geçen
   herkes «var» sayılır — bu da tersine «anılıyor ama yok» durumunu kaçırır, kabul edildi).
2. Konuşanı çözülmemiş replikler (anlatıcı «dedi» yazmıyor) aday olmaz → kaçırma;
   `unknown_speaker` INFO'da görünür.
3. Hitap terimi model tarafından yanlış kesilebilir («Ayşe abla» → hangi sınıf? AD önce denenir).
4. Çoğul hitap («çocuklar») hitap edilen tek karaktere eşlenmez → dışarıda kalır.

## 8. ÖLÇÜM BEKLİYOR — ölçüm planı (gerçek kitap, GPU sunucusu)

```sh
ssh tt-gpu 'docker exec -i editor-mcp python -m editor.proofing <generation_id> --only dialogue --dry' > dialogue-<kitap>.json
ssh tt-gpu 'docker exec -i editor-mcp python -m editor.proofing <generation_id> --only dialogue'
```

Ölçülecekler (altı kitap; «Ekrana Sığmayan Macera» nesli `37527916` event_actor'ı dolu, ilk kitap o):
1. **Replik okuyucu kesinliği:** rastgele 30 replik: konuşan, hitap edilen, terim, alıntı doğru mu.
   Kabul ≥ 0.9; `unverified_quote`/`unknown_speaker` oranı yazılır.
2. **Katılımcı kümesi kapsamı:** kaç sayfada küme var (`pages_with_presence`); event_actor'sız
   nesilde ad eşlemesinin payı.
3. **Atıf kesinliği:** `candidates_detail` (rule A) etiketlenir (gerçek / uzaktan konuşma /
   olay eksik / anılıyor-yok); eşikler ve pencere bu kümede seçilir.
4. **Hitap kesinliği:** rule B adayları etiketlenir (gerçek / açıklanan / terim kesme hatası);
   `MIN_USES`/`DOMINANT_SHARE` seçilir.
5. **Geri çağırma (enjekte):** sahnede olmayan karaktere bir replik yazılır → A bulgusu; üç «abla»
   sonra bir «Ayşe» → B bulgusu; araya «kızgınlıkla adıyla seslendi» eklenince çıkmamalı.
6. **Maliyet.**

## 9. Açık kararlar

- Pencere 1 sayfa: resimli kitapta olay sayfa aralığı ±1 kayabilir; ölçümde 0/1/2 karşılaştırılır.
- Rüya/hayal kipli olayların katılımcıları kümeye giriyor; ölçümde ayrı sayılır.
- Konuşma tarzı (hitap dışı) — tanım kurulamadı, yazılmadı (§4).
