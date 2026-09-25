// Ön sayfalar (iç kapak, künye, yazar/çizer): book.typ (akışlı dizgi) ve plan.typ (sayfa planı) ortak kullanır,
// iki yolda ön sayfalar birebir aynı dizilir. Veri: d.book, d.spec, d.front (typeset.book_data / plan.render_data).

#let mark(v) = context metadata(v + (page: here().page()))

#let quiet-page(b, s, body) = page(background: none, footer: none,
  margin: (x: b + s.safe * 1mm + 6mm, top: b + 28mm, bottom: b + 22mm), body)

#let front-pages(d, accent, b) = {
  let s = d.spec
  quiet-page(b, s)[
    #mark((kind: "front", key: "ic_kapak"))
    #align(center)[
      #v(18mm)
      #text(font: s.heading_font, weight: 800, size: 30pt, fill: accent, hyphenate: false, d.book.title)
      #v(10mm)
      #text(size: 15pt, d.book.author)
    ]
    #place(bottom + center, text(size: 11pt, tracking: 1.5pt, fill: luma(90), upper(d.book.publisher)))
  ]
  quiet-page(b, s)[
    #mark((kind: "front", key: "kunye"))
    #set text(size: 8.5pt)
    #set par(leading: 0.5em, spacing: 0.9em, justify: false)
    #place(bottom + left, block(width: 100%)[
      #for row in d.front.kunye [
        #if row.at(0) == "" [#v(2mm)] else [*#row.at(0)* #h(1mm) #row.at(1) \ ]
      ]
    ])
  ]
  quiet-page(b, s)[
    #mark((kind: "front", key: "yazar_cizer"))
    #set text(size: 11pt)
    #set par(leading: 0.55em, spacing: 1em, justify: false)
    #for bio in d.front.bios [
      #text(font: s.heading_font, weight: 700, size: 15pt, fill: accent, bio.name)
      #v(1mm)
      #bio.text
      #v(8mm)
    ]
  ]
}
