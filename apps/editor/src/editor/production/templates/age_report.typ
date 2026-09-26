// Yaş uygunluğu raporu (age_report.pdf_data hazırlar). A4, tek sütun; tablolar sayfalar boyunca akar.
// Ekrandaki raporun aynısı: hüküm ve gerekçesi, sayfa sayfa bulgular, kelime düzeyi, okul/MEB denetimleri,
// editör kontrol listesi (kim/ne zaman), ekte ölçüler ve kaynaklar.
#let d = json(sys.inputs.at("data", default: "data.json"))
#let ink = rgb("#2C2C2A")
#let muted = rgb("#6B6A66")
#let line-c = rgb("#E4E1DA")
#let tone = (
  uygun: (rgb("#1F7A4D"), rgb("#E7F4EC")),
  sinirda: (rgb("#9A6200"), rgb("#FDF3DC")),
  uyumsuz: (rgb("#A8322A"), rgb("#FBE9E7")),
  belirtilmemis: (rgb("#4B4A8C"), rgb("#EEEDF8")),
  degerlendirilemedi: (rgb("#4B4A8C"), rgb("#EEEDF8")),
  cocuk_degil: (rgb("#4B4A8C"), rgb("#EEEDF8")),
)
#let status-c = (ok: rgb("#1F7A4D"), warn: rgb("#9A6200"), info: rgb("#4B4A8C"))
#let status-t = (ok: "Uygun", warn: "Dikkat", info: "Bilgi")

#set document(title: "Yaş uygunluğu raporu — " + d.title, author: "Zeki AI")
#set page(paper: "a4", margin: (x: 18mm, top: 20mm, bottom: 18mm),
  footer: context [
    #set text(size: 8pt, fill: muted)
    #d.title · Yaş uygunluğu raporu #h(1fr) #counter(page).display("1 / 1", both: true)
  ])
#set text(font: "Andika", size: 9.5pt, lang: "tr", fill: ink)
#set par(leading: 0.55em, justify: false)
#show heading: set text(font: "Baloo 2", weight: 700, fill: ink)
#show heading.where(level: 1): set text(size: 15pt)
#show heading.where(level: 2): it => { v(4mm); text(size: 12.5pt, it.body); v(1mm) }
#set table(stroke: (x, y) => (bottom: 0.5pt + line-c), inset: (x: 4pt, y: 5pt))
#show table.cell.where(y: 0): set text(weight: 700, size: 8.5pt, fill: muted)

#let (fg, bg) = tone.at(d.verdict.level)

= Yaş uygunluğu raporu
#text(size: 12pt, weight: 700, d.title) \
#text(fill: muted)[Hedef yaş: #d.band (#d.band_source) · Rapor: #d.at · Basım: #d.printed]

#v(3mm)
#block(fill: bg, radius: 6pt, inset: 10pt, width: 100%)[
  #text(fill: fg, weight: 700, size: 13pt, d.verdict.label)
  #v(1mm)
  #for r in d.verdict.reasons [• #r \ ]
  #if d.stale [#v(1mm) #text(fill: rgb("#A8322A"), weight: 700)[Metin rapordan sonra değişti; bulgular eski metne göredir.]]
]
#if d.book != "" [#v(2mm) #text(fill: muted, d.book)]

== Sayfa sayfa bulgular
#if d.findings.len() == 0 [Bulgu yok.] else [
  #table(columns: (16%, 17%, 1fr, 18%),
    [Sayfa], [Tür], [Bulgu ve öneri], [Editör kararı],
    ..d.findings.map(f => (
      [#f.page],
      [#text(fill: if f.severity == "WARN" { rgb("#A8322A") } else { muted }, weight: 700, f.kind)],
      [#f.message #if f.quote != "" [\ #text(style: "italic", fill: muted)[“#f.quote”]] #if f.suggestion != "" [\ #text(fill: muted)[Öneri: #f.suggestion]]],
      [#text(size: 8.5pt, f.decision)],
    )).flatten())
]

== Kelime düzeyi
#if d.reference == none [Bu yaş bandı için kelime derlemi yok; seyrek kelime listesi çıkarılmadı.] else [
  #text(fill: muted)[Bu yaş için yayımlanmış #d.word_stats.books kitabın en çok #d.word_stats.K tanesinde geçen kökler
  seyrek sayılır (derlemden ölçülen eşik). Kitapta #d.words.len() seyrek kök; içerik sözcükleri içindeki payı
  %#str(calc.round(d.word_stats.rare_share * 100, digits: 1)).replace(".", ",").]
  #v(1mm)
  #if d.words.len() > 0 [
    #table(columns: (15%, 9%, 16%, 1fr, 18%),
      [Kök], [Kitap], [Sayfalar], [Anlam ve sade karşılık], [Karar],
      ..d.words.map(w => (
        [*#w.lemma* \ #text(size: 8pt, fill: muted, w.forms)],
        [#w.books],
        [#text(size: 8.5pt, w.pages)],
        [#w.meaning #if w.options != "" [\ #text(fill: muted, w.options)] #if w.applied != "" [\ #text(fill: rgb("#1F7A4D"))[Uygulandı: #w.applied]]],
        [#text(size: 8.5pt, w.decision)],
      )).flatten())
  ]
]

== Okul ve MEB ölçütleri: otomatik denetim
#table(columns: (1fr, 12%, 20%),
  [Ölçüt ve sonuç], [Durum], [Kaynak],
  ..d.checks.map(c => (
    [*#c.title* \ #text(fill: muted, c.detail)],
    [#text(fill: status-c.at(c.status), weight: 700, status-t.at(c.status))],
    [#text(size: 8.5pt, c.source)],
  )).flatten())

== Editör kontrol listesi
#text(fill: muted)[Otomatik denetlenemeyen maddeler; editör işaretler.]
#table(columns: (6%, 1fr, 20%, 22%),
  [], [Madde], [Kaynak], [İşaretleyen],
  ..d.checklist.map(c => (
    [#if c.state == "ok" [☑] else if c.state == "not_ok" [☒] else [☐]],
    [#c.title #if c.note != "" [\ #text(fill: muted, c.note)]],
    [#text(size: 8.5pt, c.source)],
    [#text(size: 8.5pt, c.decision)],
  )).flatten())

#pagebreak(weak: true)
== Ek: ölçüler
#if d.measures.len() > 0 [
  #table(columns: (1fr, 18%, 22%),
    [Ölçü], [Kitap], [Bant içindeki yeri (yüzdelik)],
    [Ateşman (1997) okunabilirlik], [#d.measures.at("atesman", default: "")], [#d.percentile.at("atesman", default: "—")],
    [Çetinkaya–Uzun (2010)], [#d.measures.at("cetinkaya", default: "")], [#d.percentile.at("cetinkaya", default: "—")],
    [Bezirci–Yılmaz (2010) okunabilirlik düzeyi], [#d.measures.at("yod", default: "")], [#d.percentile.at("yod", default: "—")],
    [Ortalama cümle uzunluğu (kelime)], [#d.measures.at("asl", default: "")], [#d.percentile.at("asl", default: "—")],
    [Kelime başına hece], [#d.measures.at("asw", default: "")], [—],
  )
  #text(size: 8.5pt, fill: muted)[Karşılaştırma: yayınevinin kendi kitaplarından künyesinde bu yaş bandı basılı olanlar
  (#if d.reference_books != none [#d.reference_books kitap]); yüzdelikler kitap ağırlıklıdır. Formüllerin kendi sınıf
  tabloları kullanılmaz (ders kitaplarında kurulmuştur); kitap geneli ölçü tek başına hüküm değildir.]
]

== Ek: kaynaklar
#for s in d.sources [
  *#s.key* — #s.title \ #text(size: 8pt, fill: muted, link(s.url, s.url)) \
]
