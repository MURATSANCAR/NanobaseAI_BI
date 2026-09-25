// Öğretmen okuma kılavuzu (marketing.build_guide_pdf). Veri: kilavuz.json. A4, kitabın fontları ve vurgu rengi.
#let d = json(sys.inputs.at("data", default: "kilavuz.json"))
#let accent = rgb(d.accent)
#let ink = rgb("#2a2622")
#let muted = rgb("#6b645c")
#let soft = accent.lighten(90%)

#set document(title: d.title + " — Öğretmen Okuma Kılavuzu", author: d.publisher)
#set page(paper: "a4", margin: (x: 18mm, top: 18mm, bottom: 20mm),
  footer: context {
    set text(size: 8.5pt, fill: muted)
    [#d.title — Öğretmen Okuma Kılavuzu #h(1fr) #counter(page).display()]
  })
#set text(font: d.body_font, size: 10.5pt, lang: "tr", fill: ink, hyphenate: false)
#set par(leading: 0.68em, spacing: 0.95em, justify: false)
#set list(indent: 2mm, body-indent: 2.5mm, spacing: 0.6em)
#set enum(indent: 2mm, body-indent: 2.5mm, spacing: 0.6em)
#show heading.where(level: 1): it => block(above: 1.5em, below: 0.75em, sticky: true,
  text(font: d.heading_font, weight: 800, size: 15.5pt, fill: accent, it.body))
#show heading.where(level: 2): it => block(above: 1.2em, below: 0.55em, sticky: true,
  text(font: d.heading_font, weight: 700, size: 12pt, fill: ink, it.body))

// ---------------------------------------------------------------- baş
#block(fill: soft, radius: 4mm, inset: 7mm, width: 100%, breakable: false, grid(
  columns: if d.cover_image != none { (1fr, 34mm) } else { (1fr,) },
  column-gutter: 7mm,
  [
    #text(size: 8.5pt, weight: 700, tracking: 1.2pt, fill: accent, d.label)
    #v(2mm)
    #text(font: d.heading_font, weight: 800, size: 22pt, d.title)
    #v(1mm)
    #text(size: 12pt, d.author)
    #v(4mm)
    #for c in d.chips {
      box(fill: white, radius: 2mm, inset: (x: 2.5mm, y: 1.4mm), text(size: 9pt, weight: 700, c))
      h(1.5mm)
    }
  ],
  ..if d.cover_image != none { (image(d.cover_image, width: 34mm),) } else { () },
))

= Kitabın özeti
#for p in d.summary [#p #parbreak()]

= Hedef yaş ve okuma düzeyi
#grid(columns: (auto, 1fr), column-gutter: 5mm, row-gutter: 2mm,
  ..d.reading.map(r => (text(weight: 700, r.label), r.value)).flatten())

#if d.values.len() > 0 or d.outcomes.len() > 0 [
  = Değerler ve kazanımlar
  #grid(columns: (1fr, 1fr), column-gutter: 7mm,
    [== Değerler
     #for v in d.values [- #v
     ]],
    [== Kazanımlar
     #for v in d.outcomes [- #v
     ]])
]

#if d.sections.len() > 0 [
  = Bölüm bölüm okuma
  #for s in d.sections [
    == #s.title
    #grid(columns: (1fr, 1fr, 1fr), column-gutter: 4mm,
      ..(("Okumadan önce", s.before), ("Okurken", s.during), ("Okuduktan sonra", s.after)).map(((t, qs)) =>
        block(width: 100%, fill: soft, radius: 2.5mm, inset: 3.5mm)[
          #text(size: 8.5pt, weight: 700, tracking: 0.6pt, fill: accent, t)
          #v(1mm)
          #set text(size: 9.5pt)
          #for q in qs [+ #q
          ]
        ]))
  ]
]

#if d.vocabulary.len() > 0 [
  = Kelime çalışması
  #table(columns: (auto, 1fr, 1.4fr), inset: 2.4mm, stroke: 0.4pt + rgb("#d9d2c8"),
    fill: (_, y) => if y == 0 { soft } else { none },
    table.header(text(weight: 700, "Kelime"), text(weight: 700, "Anlamı"), text(weight: 700, "Kitaptaki cümle")),
    ..d.vocabulary.map(v => (text(weight: 700, v.word), v.meaning, emph(v.sentence))).flatten())
]

#if d.activities.len() > 0 [
  = Etkinlik önerileri
  #for a in d.activities [
    #block(breakable: false, below: 1em)[
      #text(font: d.heading_font, weight: 700, size: 11pt, a.title)
      #if a.duration != "" [ #h(2mm) #text(size: 9pt, fill: muted, "(" + a.duration + ")")]
      #v(0.5mm)
      #a.steps
    ]
  ]
]

#v(6mm)
#line(length: 100%, stroke: 0.4pt + rgb("#d9d2c8"))
#text(size: 8.5pt, fill: muted, d.approval)
