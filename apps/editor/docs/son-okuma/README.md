# Son okuma denetimleri — dizin

Her denetim `src/editor/proofing/<name>.py`; belge `docs/son-okuma/<name>.md`. Koşu:
`docker exec editor-mcp python -m editor.proofing <gen> [--only <name> ...] [--dry]`.

Durum sözlüğü: **ölçüldü** = kesinlik/geri çağırma sayısı kodda ve belgede var; **kısmen** =
bazı eşikler ölçülmüş, kesinlik yok; **ölçüm bekliyor** = gerçek kitapta etiketli ölçüm yok.

| denetim | LABEL | karar | belge | durum |
|---|---|---|---|---|
| `age_fit` | Yaş uygunluğu | deterministik okunabilirlik + model hassas içerik | [age_fit.md](age_fit.md) | kısmen (referans derlemi ölçüldü; kesinlik bekliyor) |
| `appearance` | Görünüş sürekliliği | defter + model yargı | [appearance.md](appearance.md) | ölçüm bekliyor |
| `dialogue` | Diyalog atfı ve ses | defter + model yargı | [dialogue.md](dialogue.md) | ölçüm bekliyor |
| `edition_diff` | Baskılar arası fark | deterministik | [edition_diff.md](edition_diff.md) | ölçülemedi (iki sürümlü kitap yok) |
| `hyphenation` | Satır sonu heceleme | deterministik (TDK) | [hyphenation.md](hyphenation.md) | ölçüm bekliyor |
| `imprint_crm` | Künye — CRM karşılaştırması | deterministik | [imprint_crm.md](imprint_crm.md) | ölçüm bekliyor |
| `layout` | Sayfa düzeni | deterministik (geometri + render) | [layout.md](layout.md) | ölçüm bekliyor |
| `name_spelling` | Ad yazımı tutarlılığı | deterministik aday + model | [name_spelling.md](name_spelling.md) | ölçüm bekliyor |
| `props` | Eşya sürekliliği | defter + model yargı | [props.md](props.md) | ölçüm bekliyor |
| `series_canon` | Dizi tutarlılığı | deterministik + CCIP | [series_canon.md](series_canon.md) | kesinlik ölçülebilir, geri çağırma ölçülemez |
| `setting` | Mekân tutarlılığı | defter + model yargı | [setting.md](setting.md) | ölçüm bekliyor |
| `spelling` | Yazım ve noktalama | kurallar + sözlük + model | [spelling.md](spelling.md) | kısmen (boşluk/hece eşikleri ölçüldü; kesinlik bekliyor) |
| `text_contradictions` | Metin içi çelişki | model öneri + deterministik doğrulama + model yargı | [text_contradictions.md](text_contradictions.md) | kısmen (window okuyucusu ölçülüp kapatıldı; kesinlik bekliyor) |
| `timeline` | Zaman çizelgesi | defter + model yargı | [timeline.md](timeline.md) | ölçüm bekliyor |
| `word_variety` | Kelime çeşitliliği ve yakın tekrar | Zemberek kök + model anlam ayrımı + model yargı; kelime haritası | [word_variety.md](word_variety.md) | kısmen (Dilek Ağacı: 122 bulgu, 866 kök; kesinlik bekliyor) |
| `word_overuse` | Sık kullanılan sözcükler (yazar tikleri) | G² derlem karşılaştırması + model yargı | [word_overuse.md](word_overuse.md) | kısmen (2 kitapta sayı; kesinlik bekliyor) |
| `sentence_starts` | Cümle başı tekdüzeliği | tesadüf olasılığı + model yargı | [sentence_starts.md](sentence_starts.md) | kısmen (2 kitapta sayı; kesinlik bekliyor) |
| `phrase_repeats` | Kalıp ifade tekrarı | kök dizisi öbekleri + model yargı | [phrase_repeats.md](phrase_repeats.md) | kısmen (2 kitapta sayı; kesinlik bekliyor) |
| `word_choice` | Yabancı ve yaşa ağır sözcükler | model aday + cümleyle doğrulama | [word_choice.md](word_choice.md) | kısmen (2 kitapta sayı; kesinlik bekliyor) |

İlk gerçek koşu (2026-09-22, «Levent Dünya Harikalarının Peşinde», nesil `60e5d717`; insan
doğrulaması yok, yalnız sayı): layout 78 (66 WARN), spelling 21 WARN, hyphenation 20 INFO,
age_fit 4 WARN + 2 INFO, name_spelling 3 WARN, imprint_crm 0, edition_diff 1 INFO,
series_canon 1 INFO.

## İsabet nasıl ölçülür (editör kararı)

Her bulgu için editör portalda (M5 Son Okuma) «Doğru» ya da «Yanlış alarm» der; ret gerekçesi kapalı
küme (TEXT_CORRECT, INTENDED_STYLE, DICTIONARY_GAP, WRONG_PAGE, EXPLAINED_IN_TEXT, NOT_AN_ISSUE, OTHER)
+ isteğe bağlı not. Karar `ed.proof_decision` tablosuna salt-ekleme yazılır; bulgunun **geçerli** kararı
en yeni satırdır (bir karar geri alınmaz, üstüne yenisi eklenir). Uygulama kitabı değiştirmez.

**Kural = denetim adı + sürümü.** İsabet, BÜTÜN kitaplardaki geçerli kararlardan sayılır — kuralın
isabeti kitaba özel değildir:

```sql
-- 028 sonrası: CLEAR («geri al») sayılmaz; taşınan kararı onaylayan/değiştiren karar varken aynı kuralın
-- kaynak kararı ikinci kez sayılmaz.
WITH gecerli AS (
  SELECT DISTINCT ON (finding_id) id, check_name, check_version, verdict, carried_from
  FROM ed.proof_decision ORDER BY finding_id, created_at DESC),
sayilan AS (
  SELECT * FROM gecerli x WHERE verdict IN ('ACCEPT','REJECT')
  AND NOT EXISTS (SELECT 1 FROM gecerli y WHERE y.carried_from = x.id AND y.check_name = x.check_name
                  AND y.check_version = x.check_version AND y.verdict IN ('ACCEPT','REJECT')))
SELECT check_name, check_version,
       count(*) FILTER (WHERE verdict='ACCEPT') AS dogru,
       count(*) FILTER (WHERE verdict='REJECT') AS yanlis_alarm,
       round(100.0*count(*) FILTER (WHERE verdict='ACCEPT')/count(*),1) AS isabet_yuzde
FROM sayilan GROUP BY 1,2 ORDER BY 1,2;
```

`isabet = doğru / (doğru + yanlış alarm)`; karar yoksa ölçü yok («henüz karar yok»). Önceki okumadan taşınan karar
(aşağıda «Aynı kitapta hatırlama») isabete girmez; editör onu onaylarsa kaynak karar ikinci kez sayılmaz. Kural değişince
`VERSION` artar ve yeni sürüm sıfırdan sayar; eski sürümün ölçüsü karşılaştırma için durur. Ret
gerekçelerinin dağılımı (`reason_code`) kuralın hangi yönde yanıldığını gösterir: DICTIONARY_GAP
yığılıyorsa sözlük, WRONG_PAGE yığılıyorsa kanıt eşleme, EXPLAINED_IN_TEXT yığılıyorsa yargı aşaması.

Kart servisi: `GET /v1/books/{id}/proofing` her denetimde `precision {accepted, rejected, rate}` ve `hidden`, her
bulguda `decision` (taşınmışsa `inherited` + `source`); `POST …/findings/{id}/decision` tek yazma ucu (editörün kaydı;
`verdict` ACCEPT/REJECT/CLEAR, isteğe bağlı `carriedFrom`). Köprü:
`POST /api/v1/editorial/proofing/decision`, karar veren = oturum kullanıcısı, `semantic_audit`'e düşer.

İlk karar (2026-09-23, test): «Baskılar arası fark» INFO bulgusuna timasai önce REJECT (TEXT_CORRECT,
«deneme — test kararı»), sonra ACCEPT verdi — akış doğrulaması; içerik kararı değildir.

## Aynı kitapta hatırlama (karar taşıma)

Kullanıcı kararı (2026-09-27): yeniden okumada **aynı bulgu** önceki kararı alır — «yanlış alarm» tekrar çıkmaz,
«doğru» denen işaretli gelir. Yalnız aynı kitap içinde; kurallar kendiliğinden değişmez, kitaplar arası öğrenme yok.
Kod: `src/editor/proofing/_carry.py` (saf, `tests/test_proof_carry.py`), kart servisi `_carried`.

**Bulgu parmak izi** = denetim adı (sürüm DEĞİL) + tür anahtarı + normalleştirilmiş alıntı.
- Tür anahtarı `details`in kimlik alanlarıdır (`_carry.ID_FIELDS`): tür/kural kodu (`kind`, `rule`, `style`, `field`,
  `aspect`, `op` — yalnız boşluksuz kodsa; yazımdaki `rule` bir cümle olduğu için girmez), ad yazımında
  `form`→`book_form` çifti («Hanne→Anne»), `word`, `lemma`, `phrase`, `character`, `other_book`, `forms` (hangi
  geçişler), `color` (düzende metin rengi), baskı farkında `old`/`new`. Ölçüler, olasılıklar ve model etiketleri
  (anlam adı, hassas içerik kategorisi) kimlik değildir: yeniden koşuda oynar.
- Alıntı: NFKC, Türkçe küçük harf (I→ı, İ→i), tırnaklar atılır, tire çeşitleri tek tire, yumuşak tire atılır,
  boşluk teklenir, uçlardaki noktalama atılır. **Mesaj metni parmak izine girmez** (ekran dili değişebilir).
- Sayfa: alıntılı bulguda alıntı kazanır; sayfa yalnız aynı anahtarlı birden çok geçişi ayırır (en yakın sayfa;
  nesiller arası yeniden dizgide sayfa kayması, iki tarafta tek geçen alıntıların sayfa farkının çoğunluğundan
  bulunur). Aynı sayfadaki geçişler işaret kutusunun yerine göre sıralanır. Alıntısız bulguda (ör. sayfa düzeni)
  sayfa anahtarın parçasıdır: aynı sayfa (kaymayla) + aynı tür.
- Eşleme her kaynak koşuyla (eski nesil ya da aynı nesilde eski koşu) anahtar başına **bire bir**: karşılıklı ve
  tek en yakın aday eşleşir. Eşit kalan adaylar belirsizdir → **taşınmaz**; yalnız adayların hepsi aynı kararı
  (karar + gerekçe) taşıyorsa sonuç değişmediği için taşınır. Birden çok okumadan öneri gelirse en YENİ karar
  geçerli; en yenisi «geri al» ise taşınmaz.

**Taşıma okumada yapılır, veritabanına yazılmaz.** `GET …/proofing` kendi kararı olmayan bulguya aynı kitabın önceki
okumalarındaki geçerli kararı eşler; bulgu `decision` alanında `inherited: true` ve `source` (karar kimliği, kaynak
bulgu, nesil, aynı okuma mı, sayfa, **kararın verildiği kural sürümü**, okuma zamanı) ile gelir. Neden okumada:
`proof_decision` insanın kaydıdır (karar veren = oturumdaki kişi); makinenin yazdığı satır bu sözleşmeyi ve salt-ekleme
tabloyu kirletir, yanlış eşleme kalıcı veri olur, isabet çift sayılırdı. Okumada ise eşleme kuralı iyileşince eski
kararlar kendiliğinden doğru bağlanır ve hiçbir koşu adımı (worker) değişmez.

**Editörün cevabı yazılır (028):** taşınan kararı gördüğü bulguda «Doğru»/«Yanlış alarm» (onay ya da değişiklik) ya da
«Geri al» (`verdict='CLEAR'`: bu bulgunun kararı yok) normal karar olarak yazılır, `carried_from` = kaynak karar.
**İsabet çift saymaz:** taşınan karar tek başına isabete girmez; onaylanırsa aynı kural (ad+sürüm) için kaynak karar
sayımdan düşer, yalnız yenisi sayılır (sürüm farklıysa ikisi kendi sürümünde sayılır). CLEAR isabete girmez.

**Ekran:** taşınan «yanlış alarm» varsayılan listede yok, sayaçlara (hata/uyarı/bilgi, denetim çipleri, KPI) girmez;
«N bulgu önceki okumadaki yanlış alarm kararıyla gizlendi» notu; «karar verilenler» süzgecinde «önceki okumada yanlış alarm»
rozetiyle ve satırın altındaki «Geri al» ile. Taşınan «doğru» listede kalır («önceki okumada doğru»). Word'e aktarımda taşınan
yanlış alarm da hariç. Denetim çipinde `hidden` = gizlenen sayısı.

**Kuru koşu (2026-09-27, canlı veritabanı, yalnız okuma):**
- Gerçek karar: veritabanındaki tek karar (Levent, «Baskılar arası fark» özet bulgusu, nesil `60e5d717`, timasai
  önce REJECT sonra ACCEPT) şimdiki okumaya (`371f11cd`) «önceki okumada doğru» olarak taşınıyor; yeni kodla 23
  kitabın raporu 3–116 ms.
- Sanal karar (önceki koşunun her bulgusu kararlı sayıldı): aynı koşu kendine 18.907 bulgunun 18.662'si taşındı,
  245 belirsiz (aynı sayfada iki kez geçen aynı sözcük; ad/yazım bulgularında işaret kutusu yok; kararlar ayrışırsa
  taşınmaz). Nesiller arası (Levent `60e5d717`→`371f11cd`): 101 bulgunun 100'ü taşındı, belirsiz 0. Sürüm değişimi
  (`word_variety` 2→3, `word_choice` 1→2; 25 kitap/denetim): 14.493 bulgunun 12.729'u taşındı, 24 belirsiz, geri
  kalanı yeni kuralın yeni bulgusu. Dilek Ağacı `word_variety` 2→3: 93 bulgunun 80'i taşındı, 80 çiftin hepsi elle
  bakıldı — aynı kök, aynı pasaj; yalnız modelin anlam etiketi değişmiş («erkek ebeveyn» ↔ «Baba, anne-baba»), yanlış
  eşleşme görülmedi; eşleşmeyen 13 bulgu yeni kuralın geçişleri farklı öbeklediği bulgular.

## Word'e aktarım

`GET /v1/books/{id}/proofing/export.docx` (kart servisi; `_export_docx.py`): kitabın okunan metni, bulgular
Word yorumu (yazar «Zeki AI»). «Yanlış alarm» denenler (önceki okumadan taşınanlar dahil) hariç; yeri bulunamayan bulgu sayfa başlığına bağlanır,
hiçbiri düşmez. Köprü `GET /api/v1/editorial/proofing/export.docx?bookId=`, Son Okuma panelinde «Word'e aktar».
