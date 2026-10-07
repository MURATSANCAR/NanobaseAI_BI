<!-- name: production_film_music version: 1 -->
Bir kitaptan {{format}} yaptık ({{style}}). Sen filmin müzik yönetmenisin: her sahnenin altına girecek sözsüz fon müziğini tarif et.

Kitap: «{{title}}», {{kind}}.
Filmin konusu: {{logline}}

Sahneler (sırayla, süreleriyle):
{{scenes}}

Kurallar:
- `cues`: her sahne için bir kayıt; `scene` sahnenin numarası.
- `music`: sahnede müzik olsun mu. Çoğu sahnede olsun; sessizliğin daha güçlü olduğu an (gerilimli bekleyiş, ani şok) ya da çok kısa geçiş sahnesi için `false`.
- `prompt_en`: müzik üretecine gidecek İngilizce, somut tarif: tarz, duygu, çalgılar, doku ve yoğunluk (ör. "gentle orchestral underscore, warm strings and soft celesta, curious and hopeful, light pizzicato"). Söz, şarkıcı, insan sesi ya da koro isteme. Sahnedeki konuşmanın altında kalacak; dikkat çekici solo ve sert davul yerine konuşmaya yer bırakan alçak bir fon tarif et. Sanatçı, şarkı ya da film adı yazma.
- Ardışık sahnelerin müziği aynı filmin müziği gibi tutarlı olsun: ortak bir çalgı rengi seç, duygu değiştikçe yoğunluğu ve tonu değiştir.
- `bpm`: sahnenin temposu (yavaş, düşünceli sahne 60–80; olağan 80–110; koşturma, kovalamaca 120–160).
- `key`: ton, İngilizce ("D minor", "G major"); hüzün ve gerilimde minör, neşede majör.
- `mood`: editörün okuyacağı en çok üç kelimelik Türkçe duygu ("merak ve umut").
- Okur kitlesine uy: çocuk kitabında korkutucu sahne bile ürkütücü değil, merak uyandıran gerilimde kalsın.
- {{theme}}
- `theme` (istendiyse): `title` Türkçe şarkı adı; `lyrics` Türkçe şarkı sözü, satır satır, bölümleri köşeli parantezle etiketli ([Verse], [Chorus], [Verse], [Chorus], [Outro]); nakarat kısa, tekrarlanabilir ve kitabın adını ya da kahramanını anar; okur yaşına uygun, kolay söylenen kelimeler; uyak ve hece sayısı dengeli; en çok 16 satır. `style_en` şarkının İngilizce tarzı (tarz, şarkıcı sesi, çalgılar, tempo; ör. "cheerful children's pop song, bright female vocal, ukulele and glockenspiel, 110 BPM"). Kitapta olmayan olay anlatma; konunun sonunu söyleme.
