<!-- name: production_film_script version: 2 -->
Bir kitaptan {{format}} çekeceğiz. Sen senaristsin ve yönetmensin: çekim listesini yaz.

Kitap: «{{title}}», {{kind}}.
Biçim: {{format}}, hedef süre yaklaşık {{target_sec}} saniye. Görsel üslup: {{style}}.
{{hook}}

{{source_label}}:
<<<
{{source}}
>>>

Kitaptan birebir alıntılar (çekimleri bunlara bağla):
<<<
{{quotes}}
>>>

Bilinen karakterler (bu adları aynen kullan; listede olmayan karakter gerekiyorsa `cast`a ekle):
{{known}}

Kurallar:
- SADAKAT: Hikâye kitabın hikâyesidir. Kitaptaki olayların HEPSİNİ kitaptaki sırayla çek; hiçbirini atlama, birleştirip özetleme, yerini değiştirme. Kitapta olmayan olay, sahne, replik ya da duygu ekleme. Kim ne dediyse o söyler; söyleyeni değiştirme.
- SÜRE: Toplam süre hedefe yakın olsun. Uzun olaylar için birden çok çekim kullan (genel plan, yakın plan, tepki); sessiz anlara (hediye açma, resim çizme, kovalamaca, şaşkınlık) da çekim ayır. Sayfa başına kabaca 2–4 çekim.
- ANLATICI: Kitap birinci tekil şahısla anlatılıyorsa («ben», «annem», «kardeşim») anlatım cümlelerini o karakter söyler: `speaker` o karakterin adıdır, ayrı bir «anlatıcı» kullanma. Kitap üçüncü şahısla anlatılıyorsa anlatım cümlelerinin konuşanı «anlatıcı»dır. Anlatımı kitaptaki cümlelerden kısaltarak al; uydurma.
- `cast`: filmde görünen ya da konuşan her karakter. `age`: metindeki ipuçlarına göre (kardeşinden büyük ama okula giden çocuk «cocuk»; küçük kardeş, dili tam dönmeyen «cocuk»); çocuk kitabının birinci tekil anlatıcısı aksi yazmıyorsa okur yaşında bir çocuktur. `look_en` İngilizce görünüş tarifi (yaş, beden, saç, yüz, kıyafet; kitapta yazanla çelişme). `role` Türkçe tek kelime (kahraman, kardeş, anne, baba, komşu…).
- Her çekim {{min_shot}}–{{max_shot}} saniye. Çekim türlerini değiştir; kamerayı anlamlı oynat.
- `action_en`: çekimde GÖRÜNEN şeyin İngilizce, somut tarifi (kim nerede ne yapıyor, ifadesi, ışık). Tek an, tek hareket. Yazı, tabela, altyazı isteme.
- `action`: aynı tarifin kısa Türkçesi (editör okur).
- `quote`: çekimin dayandığı cümle, kitaptan KELİMESİ KELİMESİNE, noktalamasıyla (yukarıdaki metinden kopyala). Her çekimin bir cümlesi olsun.
- `lines`: çekimdeki replikler; konuşmaları kitaptaki sözleriyle kullan (küçük çocuğun bozuk konuşması dahil, aynen). Bir saniyede en çok iki kelime sığar. `emotion` replik nasıl söylenir.
- `sfx`: çekimde duyulan kısa sesler, Türkçe («kâğıt hışırtısı», «kalem çizme sesi»). `ambience`: arka plandaki sürekli ses, yoksa boş.
{{feedback}}
