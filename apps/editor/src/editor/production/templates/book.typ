// İç sayfa şablonu. Veri: data.json (typeset.py yazar). Ölçüler taşma paylı sayfa üzerinden:
// sayfa = kesim + 2×taşma; resim bandı taşma payına kadar uzanır, yazı güvenli alanın içinde kalır.
#let d = json(sys.inputs.at("data", default: "data.json"))
#let s = d.spec
#let L = d.layout
#let b = s.bleed * 1mm
#let W = s.trim_w * 1mm + 2 * b
#let H = s.trim_h * 1mm + 2 * b
#let arth = L.art_ratio * s.trim_h * 1mm
#let accent = rgb(L.accent)
#let art = d.art
#let body-size = L.body_size * 1pt

#set document(title: d.book.title, author: d.book.author)
#set text(font: s.body_font, size: body-size, lang: "tr", hyphenate: s.hyphenate,
          costs: (widow: 100%, orphan: 100%))
// Taban çizgisi aralığı = leading × punto; Typst satır kutusu büyük harf yüksekliği (~0,7 em) + leading.
#set par(leading: (s.leading - 0.7) * 1em, spacing: (s.leading - 0.2) * 1em, justify: s.justify,
         first-line-indent: 0pt)

#let placeholder(w, h, label) = rect(width: w, height: h, fill: accent.lighten(82%), stroke: none,
  align(center + horizon, text(font: s.heading_font, size: 13pt, fill: accent.darken(10%), label)))

#let mark(v) = context metadata(v + (page: here().page()))

#let flow-bg = context {
  let n = str(here().page())
  if n in art { place(top + left, image(art.at(n), width: W, height: b + arth, fit: "cover")) }
  else { place(top + left, placeholder(W, b + arth, [Resim · s. #n])) }
}

#set page(width: W, height: H, binding: left,
  margin: (top: b + arth + 9mm, bottom: b + 18mm, inside: b + s.safe * 1mm + s.gutter * 1mm,
           outside: b + s.safe * 1mm),
  background: if L.art_ratio > 0 { flow-bg } else { none },
  footer: context align(center, text(size: 10pt, fill: luma(110), str(here().page()))),
  footer-descent: 7mm)

#let full-art(key) = page(margin: 0pt, footer: none, background: context {
  let n = str(here().page())
  if n in art { image(art.at(n), width: W, height: H, fit: "cover") }
  else { placeholder(W, H, [Tam sayfa resim · s. #n]) }
})[#mark((kind: "full", key: key))]

#let quiet(body) = page(background: none, footer: none,
  margin: (x: b + s.safe * 1mm + 6mm, top: b + 28mm, bottom: b + 22mm), body)

// ---------------------------------------------------------------- ön sayfalar
#quiet[
  #mark((kind: "front", key: "ic_kapak"))
  #align(center)[
    #v(18mm)
    #text(font: s.heading_font, weight: 800, size: 30pt, fill: accent, hyphenate: false, d.book.title)
    #v(10mm)
    #text(size: 15pt, d.book.author)
  ]
  #place(bottom + center, text(size: 11pt, tracking: 1.5pt, fill: luma(90), upper(d.book.publisher)))
]
#quiet[
  #mark((kind: "front", key: "kunye"))
  #set text(size: 8.5pt)
  #set par(leading: 0.5em, spacing: 0.9em, justify: false)
  #place(bottom + left, block(width: 100%)[
    #for row in d.front.kunye [
      #if row.at(0) == "" [#v(2mm)] else [*#row.at(0)* #h(1mm) #row.at(1) \ ]
    ]
  ])
]
#quiet[
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
#if L.opening_full { full-art("acilis") } else { quiet[#mark((kind: "front", key: "bos"))] }

// ---------------------------------------------------------------- öykü
#for (ci, ch) in d.chapters.enumerate() {
  for k in range(L.pads.at(str(ci), default: 0)) { full-art("oncesi-" + str(ci) + "-" + str(k)) }
  pagebreak(weak: true)
  if ch.title != none {
    block(below: 1.1em, sticky: true)[
      #mark((kind: "chapter", ci: ci))
      #text(font: s.heading_font, weight: 800, size: 1.55em, fill: accent, hyphenate: false, ch.title)
    ]
  }
  for blk in ch.blocks {
    let body = if blk.kind == "dialogue" [– #blk.text]
      else if blk.kind == "sound" { text(font: s.heading_font, weight: 800, size: 1.35em, fill: accent, blk.text) }
      else [#blk.text]
    par[#mark((kind: "s", id: blk.id))#body#mark((kind: "e", id: blk.id))]
  }
}
#for k in range(L.pads.at("end", default: 0)) { full-art("son-" + str(k)) }
