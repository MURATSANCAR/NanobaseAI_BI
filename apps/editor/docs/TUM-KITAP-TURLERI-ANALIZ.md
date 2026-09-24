# Editör: yayınevindeki bütün kitap türleri — analiz (2026-09-24)

Durum: **analiz, kod yok.** Karar sonrası uygulanacak. Ölçümler canlı GPU veritabanından
(19 kitaplık kuyruk, 23–24 Eylül) ve canlı CRM'den (.28, salt okuma).

## 1. Neden

Editör resimli çocuk kitabı (kurgu) için kuruldu. Yayınevi bütün kitap türlerini okutacak.
23 Eylül gecesi kuyruğa giren 19 kitap (roman, tarih, psikoloji, kişisel gelişim, pedagoji,
deneme, çocuk öyküsü) üç ayrı kusuru ortaya çıkardı:

1. **Tür körlüğü** — her kitap resimli çocuk kurgusu gibi okunuyor.
2. **Uzunluk** — bütün kitabı tek model çağrısına koyan adımlar uzun kitapta düşüyor ya da sessizce kırpıyor.
3. **Türden bağımsız, 22 Eylül'den beri açık iki hata** — hiçbir kitap kabul edilemiyor.

## 2. Katalog: hangi türler var (canlı CRM, aktif kitap kartı, `new_Tip=1`: 9.091 kitap)

| Alan (`new_kitapBase`) | Doluluk | Değerler |
|---|---|---|
| `new_hedefkitle` | %98,5 | Çocuk 4.257 · Yetişkin 3.589 · Genç 1.113 |
| `new_turlertext` | %53 | Roman 804 · Hikâye 575 · Tarih 342 · Öykü 233 · Masal 207 · Etkinlik 112 · Klasik 100 · İnceleme-Araştırma 97 · Matematik 73 · Tasavvuf Klasikleri 67 · Psikoloji 56 · Dini Hikâye 55 · Bilim 55 · Kişisel Gelişim 42 · Boyama 36 … |
| `new_webkategorileritext` | %34 | "Çocuk;6 - 10 Yaş Öykü Hikaye" 646 · "Çocuk;6 Ay - 5 Yaş Masal Hikaye" 358 · "Genç;10+ Roman Öykü" 242 · "Yetişkin;Tasavvuf" 105 · "Yetişkin;Araştırma-Tarih" 86 … |
| `new_hedefkitleyasbaslangic/bitis`, `new_1Yas…new_14Yas` | — | yaş aralığı |
| `new_RenkveResim` | %16 | serbest metin — güvenilmez; resim sayfadan ölçülmeli |

19 kitabın hepsi CRM'de eşleşti ve hepsinin hedef kitlesi dolu. Örnek: Benim Adım Ekin =
Kişisel Gelişim (roman değil), Osmanlı Taşra Maliyesi = Tarih İnceleme Araştırma, Dijital
Dünyada E-beveyn Olmak = Pedagoji.

Editör bugün bu alanların hiçbirini okumuyor: `book_crm_record`'da tür/yaş kolonu yok,
`connectors/crm_covers.py` SELECT'i çekmiyor. `ed.book.age_group` / `universe` var ama boş.

## 3. Tür körlüğü — ölçülen sonuçlar

| Kitap (CRM türü) | Ne çıktı |
|---|---|
| Aile ile Bağlanma (Aile Çocuk) | "Karakterler": Yayın Yönetmeni, editör, kapak tasarımcısı, yayına hazırlayan (künyeden). "Olaylar": yazarın özgeçmişi. 190 açık inceleme kaydı. |
| Aşk Terapi (Kişisel Gelişim) | Karakterler yine künye kadrosu; 160 açık inceleme. |
| Böcekleri Seven Kadın (Roman, yetişkin) | Karakterler doğru; ama yaş uygunluğu 81 bulgu — kitap "belirtilmemiş (çocuk kitabı)" sayılıyor. |
| Hepsi | Kurgu dışı kitapta kip (plan/hayal/şaka), anlatı rolü (dönüm noktası, doruk), "kim yaptı" soruları anlamsız. |

Koddaki varsayımlar (tam envanter ajan raporunda, özet):

- İstemler sabit: "Aşağıda **resimli bir çocuk kitabının** METNİ var" (`proofing/_continuity.py:26`,
  `appearance.py:45`, `text_contradictions.py:82`, `prompts/attribute_text.md`), "Sen bir çocuk
  kitabının sayfalarını tarayan…" (`page_scan_fast.md`), yaş uygunluğu bandı yoksa
  `"belirtilmemiş (çocuk kitabı)"` (`age_fit.py:235`).
- Adım seti sabit: `workflows.py` her kitaba aynı 15 adımı uygular; `analysis_job.profile`
  kaydediliyor ama okunmuyor.
- Kapılar sabit: `NO_USABLE_EVENTS`, "hikâye dışı sayfadan olay/duygu çıkarılmadı" kurgu
  varsayar; kurgu dışı kitap bunları yapısı gereği geçemez.
- Künye/ön sayfa kişileri karakter oluyor (yalnız kurgu dışında değil, romanda da künye
  kadrosu çıkıyor — Aşk Terapi'de kapak tasarımcısı).
- `setting` denetimi resimsiz sayfaya da derin görsel model çağırıyor (`alias<>'deferred-to-deep'`
  koşulu `no-illustration` sayfaları da alıyor). Ölçüm: Böcekleri 97 çağrı / 5,9 dk,
  Beni de Kalbinde Götür 40 çağrı / 4,9 dk — hepsi resimsiz sayfada. (Düzeltme: ilk sürüm
  Aile ile Bağlanma'nın 693 dk'sını buna bağlamıştı; o süre kitabın 76 resimli sayfasının
  olağan derin taramasıdır — sorgu `pass='DEEP'` yerine küçük harfle yazılmıştı.)

Resimsiz sayfa ayrımı zaten ucuz ve doğru çalışıyor (`nontext_ink < 0.02` → model çağrısı yok);
taranmış (metin katmansız) PDF'te her sayfa resimli sayılıyor.

## 4. Uzunluk — ölçülen sonuçlar

Model bağlamı 131.072 token. Bütün kitabı tek çağrıya koyan adımlar:

| Adım | Girdi | Kitabı düşürür mü | Ölçüm |
|---|---|---|---|
| Karakter kimlikleri (`identity.propose` + denetçi + uzlaştırma) | tüm anmalar + anma geçen her sayfanın tam metni | **evet** | Babam Abdülhamid ~200k token → düştü. Benim Adım Ekin girdi sığdı, cevap (456 anma) 12k'yı aştı, bütçe 24k'ya katlanınca bağlam aştı → düştü. Böcekleri 357 token payla geçti; denetçi çağrısı 115k. |
| Olay birleştirme/sıra (`merge_events`) | tüm olaylar | evet | Böcekleri 30k; olay başına ~45 token |
| Anlatı rolleri (`narrative_roles`) | tüm olaylar | evet | |
| Tema birleştirme, çelişkiler | tüm tema/karakter/olay | evet | |
| Son okuma hakemleri (süreklilik, görünüş, metin içi çelişki, diyalog, eşya, mekân, zaman) | **tüm kitap metni** her çağrıda | hayır — sessizce boş | Böcekleri 116k; 130k üstü kitapta hiç çalışmaz |

**Sessiz kırpma (başarılı görünen kitaplarda):** `schemas.arr` her listeyi 120 öğeyle sınırlıyor
(`schemas.py:12`, "yalnız döngüyü durdurur" varsayımıyla). Tüm-kitap çıktılarında bu gerçek sınır:

| Kitap | Olay | Sıraya konan | Rol verilen | Bağlanmamış anma |
|---|---|---|---|---|
| Böcekleri Seven Kadın | 677 | 102 | 120 | 256 / 507 |
| Beni de Kalbinde Götür | 429 | 110 | 120 | 104 / 342 |
| Aşk Terapi | 220 | 113 | 120 | 72 / 194 |

**Tekrar deneme israfı:** bağlam aşımı (HTTP 400) belirleyicidir ama `llm.chat` 3 kez, Temporal
4 kez dener → aynı istek 12 kez. `finish_reason=length`'te bütçe ikiye katlanırken girdi boyu
hesaba katılmıyor (`llm.py:180`) — 98k üstü girdide katlama kendisi bağlamı aşar. Kodda
hiçbir yerde token sayılmıyor; geçit `/tokenize`'ı zaten geçiriyor (`gateway.py:48`).

Kalan kitapların metin boyu (token ≈ karakter/2,8): 62k–130k arası 9 kitap, Rüzgârın
Ardından ~198k, Osmanlı Taşra Maliyesi ~482k (544 sayfa).

## 5. Türden bağımsız, 22 Eylül 15:00'ten beri açık

`regression_run`: 19–21 Eylül her kitap geçiyor; 22 Eylül 15:00'ten beri resimli çocuk
kitabı dahil **hiçbiri** geçmiyor. İki denetim:

1. "model kayıtlarında gerçek model ve sürüm var" — OCR modeli `dots-studio/dots.mocr`
   `revision='unknown'` kaydediliyor (ölçüldü).
2. "hikâye dışı sayfadan olay/duygu çıkarılmadı" — çıkarıcının NON_STORY önerisi sayfa
   rolü olarak yazılıyor ama olaylar düşürülmüyor (kod okumasıyla; kök neden doğrulanmadı).

`REGRESSION_NOT_PASSED` feragat edilemez (`foundation.py`) → 22 Eylül'den beri hiçbir kitap
kabul edilemez.

## 6. Önerilen yapı

### 6.1 Tür belirleme (kitaba özel değil, veriden)

- **Kaynak 1 — CRM (yayınevinin kaydı):** `new_hedefkitle`, `new_turlertext`,
  `new_webkategorileritext`, yaş aralığı. Bağlayıcı SELECT'i + `book_crm_record` kolonları.
- **Kaynak 2 — kitabın kendisi (ölçüm):** resimli sayfa oranı (`nontext_ink`, var), sayfa
  sayısı, metin boyu; tür CRM'de boşsa (%47) tek bir sınıflandırma çağrısı (künye + 3 örnek
  sayfa, kapalı seçenek + olasılık — `choose`).
- CRM ile ölçüm çelişirse editöre tek soru (inceleme kuyruğu).

### 6.2 İki eksen, adım seti eksenlerden

| Eksen | Değerler | Neyi açar/kapar |
|---|---|---|
| Anlatı biçimi | kurgu · gerçek kişi anlatısı (tarih, biyografi, anı) · fikir/rehber (psikoloji, kişisel gelişim, pedagoji, deneme, din) · etkinlik/eğitim (etkinlik, boyama, matematik, ders) · şiir | karakter/olay/kip/rol/kim yaptı/süreklilik yalnız kurgu (+ anlatıda kişi/olay/kronoloji) |
| Resim | sayfa sayfa ölçülür | görsel adımlar yalnız resimli sayfada (bugün de böyle; `setting` hatası düzeltilir) |
| Okur | çocuk · genç · yetişkin + yaş aralığı (CRM) | yaş uygunluğu yalnız çocuk/genç, CRM bandıyla |

Her türe ortak: metin/OCR, sayfa rolü (künye ve ön sayfa kişileri karakter olmaz), yazım,
heceleme, ad yazımı, sayfa düzeni, baskı farkı, künye–CRM, özet (kurguda olay örgüsü, kurgu
dışında bölüm bölüm ana fikir), katalog kartı, arama indeksi, kitaba sor. Kapılar
(`NO_USABLE_EVENTS`, hikâye dışı sayfa denetimi) yalnız ilgili türde çalışır. İstemlerdeki
"resimli bir çocuk kitabı" sabiti tür değişkenine döner.

### 6.3 Uzunluk (bütün türler)

- Her tüm-kitap çağrısından önce geçitteki `/tokenize` ile gerçek sayım; bütçe aşılıyorsa
  pencere (ardışık tam sayfalar) + birleştirme adımı. Sığan kitap bugünkü yoldan geçer.
- Kimlik: pencere başına bugünkü öneri/onarım/denetçi/kurtarma aynen; pencere içi `m0…`
  kimlikleri kitap geneline çevrilir; pencereler arası birleştirme grup tablosu üzerinden
  (sayfa metni yok), kodla engeller: aynı pencere, tür/cinsiyet çelişkisi, topluluk↔birey.
- Olay sırası, anlatı rolleri, temalar, çelişkiler: aynı pencere + birleştirme düzeni.
- Son okuma hakemleri: bütün kitap yerine aday çiftin çevresindeki sayfalar.
- Tüm-kitap listelerinde 120 sınırı kalkar (parça parça istenir); sınıra çarpan her çıktı
  sayılır ve raporlanır — sessiz kırpma yok.
- `llm.chat`: bağlam aşımı tekrar denenmez; katlama `usage.prompt_tokens` ile sınırlanır.
  Temporal: bağlam aşımı tekrar denenmez hata türü.

## 7. Aşamalar ve sıra

| Aşama | İçerik | Tahmin |
|---|---|---|
| 0 | 22 Eylül'den beri kapı hatası (OCR sürümü, hikâye dışı sayfa); `llm.chat` 400/katlama; `setting` resimsiz sayfa hatası | ~yarım gün |
| 1 | Tür belirleme (CRM + ölçüm) + eksenlere göre adım/kapı/istem; künye kişileri | 2–3 gün |
| 2 | Uzunluk: token bütçesi, pencereleme, 120 sınırı | 2–3 gün |
| 3 | Kurgu dışı için yeni çıktılar (bölüm ana fikirleri, kavramlar, atıf/kaynak) | ürün kararı sonrası |

Tahminler kaba; aşama 1 ve 2 birbirinden bağımsız ilerleyebilir.

## 8. Doğrulama

- **Tür test seti** (katalogdaki dağılımdan): resimli çocuk (mevcut 6), çocuk/genç roman
  (Gölge Tilki), yetişkin roman (Böcekleri, Beni de Kalbinde Götür), tarih (Osmanlı Taşra
  Maliyesi, Babam Abdülhamid), kişisel gelişim/psikoloji (Aşk Terapi, Benim Adım Ekin),
  pedagoji (Dijital Dünyada Ebeveyn Olmak), deneme (Duvarları Yıkmak). **Eksik:** etkinlik,
  boyama, matematik/ders, şiir, çizgi roman — PDF gerekiyor.
- Ölçüt: her kitap biter; sınıra çarpan çıktı 0; tür doğru belirlenir (CRM ile karşılaştırma);
  kurgu dışında karakter/olay çıkmaz; kapılar türüne göre geçer; GPU süresi kitap başına.
- Kimlik pencerelemesi: Böcekleri zorla pencereli yoldan geçirilir, bugünkü tek parça
  sonucuyla karşılaştırılır.
