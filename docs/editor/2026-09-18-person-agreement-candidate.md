# Birinci kişi–ad uyumu kapısı — aday, üretime bağlı değil (18 Eylül 2026)

## Genel sorun

Bir iddianın bütün sözcükleri kaynakta bulunabilir, yine de özne değişmiş olabilir. Kaynakta birinci kişi çekimli bir yüklem ("bayılırım") o konuşmanın sahibine aittir. Aynı konuşmanın içinde üçüncü kişi olarak adı geçen katılımcı o konuşmacı değildir. İddia bu yüklemi alıp öznesine o adı koyarsa (V16-r5'te kabul edilmiş gerçek örnek: PDF27) literal dayanak, isim yüzeyi ve belirsizlik kapıları bunu göremez. LLM tabanlı rol grafı (`source_role_bindings.py`) aynı hatayı iddia başına üç model çağrısıyla ve yanlış retlerle arıyor.

## Genel çözüm

`apps/editor/backend/editor/source_person_agreement.py` (`source-person-agreement-v2`), model çağırmadan, Türkçe biçimbilim çözümlemesiyle yalnız şu pozitif sinyali raporlar:

1. Kaynakta, bir konuşma aralığının içinde, **bütün çözümlemeleri** fiil köklü ve A1sg/A1pl çekimli olan yüklem bulunur. Belirsiz sözcük sayılmaz ("evim": ad+iyelik ya da ad+yüklem).
2. İddia aynı fiil kökünü kullanıyorsa (çekimli, ortaç ya da ad-fiil) aktarım vardır.
3. İddiada o yüklemden önce özne olabilecek ad benzeri sözcük aranır: yalın büyük harfli sözcük ya da kesme işaretli ilgi hâli (-(n)In). İlgi hâli yalnız en yakın iyelikli başı bir ortaçsa özne sayılır; önce her çözümlemesi iyelikli bir ad geliyorsa ("Max'in denge programını") tamlayandır. "A ve B'yi" yapısında durum eki son öğeden alınır. İddianın kendi tırnak içi sözcükleri atlanır.
4. Bu ad kaynakta **yalnız** aynı konuşma aralığının içinde geçiyorsa sonuç `NEEDS_REVIEW / FIRST_PERSON_PREDICATE_ASSIGNED_TO_NAME_INSIDE_SAME_UTTERANCE` olur. Ad konuşmanın dışında da geçiyorsa (olası aktaran: "dedi X") bu kapı karışmaz; o soru konuşmacı kapılarınındır.

Konuşma aralığı tırnak işaretlerinden çıkar; hiç tırnak yoksa metin tek konuşmadır (balon birimi). Açılıp kapanmadan yeniden açılan tırnağın sınırı belirsiz sayılır ve o aralıktaki yüklem kullanılmaz. Büyük harf küçültme Türkçe kurallıdır (I→ı, İ→i).

Kapı hiçbir iddiayı kanıtlamaz (`proves_claim=false`): Türkçede üçüncü tekil kişi eksizdir, sinyal yokluğu kanıt değildir. Ad listesi, sözlük eklemesi, kitap/sayfa/karakter kuralı yoktur. Dile bağlı sabitler belgelidir: kişi/iyelik/ortaç ek kimlikleri, ilgi hâli eki deseni, `ve/ile/veya` bağlaçları, tırnak karakterleri. Çözümleyici dışarıdan verilir; sondada `zeyrek 0.1.3` (MIT, Zemberek portu) kullanıldı. İkinci kişi (A2sg/A2pl) bilinçli olarak kapsam dışıdır: konuşmanın içindeki ad hitap edilen kişi olabilir.

`tense_shifts` yalnız rapordur: cümle sonundaki kaynak fiili ile iddia fiilinin zaman eki farkı. Cümle ortasındaki fiil atlanır, çünkü Türkçede zaman eki sıralı fiillerin sonuncusunda taşınabilir ("parlıyor, ... geliyordu"). İlk sürüm bunu yanlış işaretlemişti.

## Gerçek doğrulama

Ortam: `nanobase-direct`, ayrı sanal ortam `/data/nanobaseai/editor/runtime/morph-probe` (uygulama imajlarına ve servislerine dokunulmadı). Sürücü `apps/editor/scripts/probe-person-agreement.py`. Girdi, önceki gerçek API/PG salt okunur kanıt dosyalarındaki kabul edilmiş iddialar ve kayıtlı kaynak metinleridir. Model çağrısı 0, uygulama/DB yazımı 0, beklenen cevap girdisi yok.

| Girdi | İddia | Birinci kişi yüklemli kaynak | Yüklemi taşıyan iddia | İşaretlenen |
|---|---:|---:|---:|---:|
| `v16-r5-eligible-claims-readonly.json` (nesil `116bb4a8`) | 91 | 17 | 17 | 1 |
| `v15-r7-eligible-claims-readonly-v2.json` (nesil `382da5b3`) | 100 | 17 | 14 | 0 |

İşaretlenen tek iddia, içerik incelemesinde kesin yanlış bulunan PDF27 iddiasıdır (`BAYILIRIM [A1sg] → Bilge'nin GENITIVE`). Birinci kişi yüklemini taşıyan diğer 30 iddia işaretlenmedi; bunlar gözle okundu, çoğu adı konuşmanın dışında geçen aktaranla kurulmuş dolaylı anlatımdır. Bu okuma bağımsız bir anlamsal kabul değildir. Kanıt: `evidence/person-agreement-probe-20260918T115155713533Z.json`, `…T115159465397Z.json`; modül SHA-256 `501f4f8f…`, sürücü `4d24276a…`.

Ara sürümlerin yanlış işaretleri korunur ve her biri genel bir kural düzeltmesine dönüştü: ikinci kişi + hitap adı, kapanmamış tek tırnak, tamlayan ilgi hâli, iddianın kendi alıntısındaki büyük harfli sözcük, "yeni" sözcüğünün ad+iyelik çözümlemesi, bağlaçlı nesne ("Robobi ve Max'i").

## Açık kapsam

- Kural R5 setine bakılarak geliştirildi; R7 seti ilk koşuda bir yanlış işaret verdi ve bağlaç kuralı ondan sonra eklendi. **Hiç görülmemiş veride ölçüm yok.**
- Bilinen gerçek pozitif örnek sayısı 1. Yakalama oranı ölçülmüş sayılmaz.
- Başka kitaplarda analiz nesli olmadığı için farklı kitapta kabul **DOĞRULANAMADI**.
- Yakalamadığı sınıflar: ad yerine ortak ad öznesi ("robot"), adın hem içeride hem dışarıda geçtiği durumlar, ikinci kişi, konum/sahiplik eklemesi, örnek listenin tam liste sunulması, zamir eşgönderimi.
- R7 ham kaynağında satır sonu tireleri birleşmemiş olduğu için 46 parça çözümlenemedi; üretimde `reading_view` metni kullanılmalı.
- Üretim entegrasyonu, imaj bağımlılığı (zeyrek/Zemberek) ve offline paket yapılmadı. `semantic_acceptance=false`.

## v3 — konuşma çizgisi ve açık uygulanamadı raporu

Diğer iki gerçek kitap diyaloğu konuşma çizgisiyle veriyor; kapı orada sessizce devre dışı kalıyordu. v3 bu durumda `NOT_APPLICABLE` ve nedenini döndürür. Ölçüm ve sınırlar: [genellik ölçümleri](2026-09-18-generality-measurements.md).
