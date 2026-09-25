// Kapak açılımı: arka | sırt | ön, taşma paylı tek sayfa. Veri: cover.json (cover.py yazar).
#let d = json(sys.inputs.at("data", default: "cover.json"))
#let b = d.bleed * 1mm
#let tw = d.trim_w * 1mm
#let th = d.trim_h * 1mm
#let sp = d.spine * 1mm
#let W = 2 * tw + sp + 2 * b
#let H = th + 2 * b
#let accent = rgb(d.accent)
#let front-x = b + tw + sp          // ön kapağın kesim çizgisi (solda)

#set page(width: W, height: H, margin: 0pt)
#set text(font: d.body_font, lang: "tr", hyphenate: false)

// ---------------------------------------------------------------- ön kapak
#if d.front_image != none {
  place(top + left, dx: front-x, image(d.front_image, width: tw + b, height: H, fit: "cover"))
} else {
  // Tipografik kapak (resimsiz kitap): düz zemin, açık tonda daire deseni, başlık ve yazar ortada.
  let ft = d.front_type
  let bg = rgb(ft.bg)
  let ink = rgb(ft.ink)
  place(top + left, dx: front-x, box(width: tw + b, height: H, clip: true, {
    place(top + left, rect(width: tw + b, height: H, fill: bg, stroke: none))
    for c in ft.dots {
      place(top + left, dx: (c.at(0) - c.at(2)) * 1mm, dy: (c.at(1) - c.at(2)) * 1mm,
        circle(radius: c.at(2) * 1mm, fill: bg.lighten(9%), stroke: none))
    }
  }))
  let inner = tw - 2 * d.safe * 1mm
  place(top + left, dx: front-x + d.safe * 1mm, dy: b + th * 0.22, box(width: inner, align(center)[
    #set par(leading: 0.45em, justify: false)
    #text(font: d.heading_font, weight: 800, size: ft.title_size * 1pt, fill: ink, d.title)
    #if d.author != "" [
      #v(8mm)
      #box(width: 18mm, line(length: 100%, stroke: 1.2pt + ink))
      #v(6mm)
      #text(font: d.heading_font, weight: 600, size: ft.author_size * 1pt, fill: ink, d.author)
    ]
  ]))
  place(top + left, dx: front-x + d.safe * 1mm, dy: b + th - d.safe * 1mm - 8mm, box(width: inner,
    align(center, text(size: 10pt, weight: "bold", tracking: 1.5pt, fill: ink, upper(d.publisher)))))
}
#for blk in d.front_text {
  for (i, ln) in blk.lines.enumerate() {
    place(top + left, dx: front-x, dy: blk.top * 1mm + i * blk.step * 1mm,
      box(width: tw, align(center, text(font: blk.font, weight: blk.weight, size: blk.size * 1pt,
        fill: rgb(blk.ink), ln))))
  }
}

// ---------------------------------------------------------------- arka kapak
#place(top + left, rect(width: b + tw, height: H, fill: rgb(d.back.bg), stroke: none))
#place(top + left, dx: b + d.safe * 1mm, dy: b + d.safe * 1mm + 4mm,
  box(width: tw - 2 * d.safe * 1mm)[
    #set par(leading: 0.62em, spacing: 1em, justify: false)
    #text(font: d.heading_font, weight: 800, size: 17pt, fill: accent, d.title)
    #v(5mm)
    #text(size: 11.5pt, fill: rgb("#2a2622"))[#for p in d.back.paragraphs [#p #parbreak()]]
  ])
#if d.back.age != none {
  place(top + left, dx: b + d.safe * 1mm, dy: b + th - d.safe * 1mm - 30mm,
    box(fill: accent, radius: 3mm, inset: (x: 3.5mm, y: 2mm),
      text(font: d.heading_font, weight: 800, size: 12pt, fill: white, d.back.age)))
}
#if d.back.series != none {
  place(top + left, dx: b + d.safe * 1mm, dy: b + th - d.safe * 1mm - 18mm,
    text(size: 9pt, fill: rgb("#4a443c"), d.back.series))
}
#place(top + left, dx: b + d.safe * 1mm, dy: b + th - d.safe * 1mm - 8mm,
  text(size: 10pt, weight: "bold", tracking: 1pt, fill: rgb("#2a2622"), upper(d.publisher)))
#if d.barcode != none {
  place(top + left, dx: b + tw - d.safe * 1mm - 38mm, dy: b + th - d.safe * 1mm - 26mm,
    image(d.barcode, width: 38mm))
}

// ---------------------------------------------------------------- sırt
#if d.spine > 3 {
  place(top + left, dx: b + tw, rect(width: sp, height: H, fill: accent, stroke: none))
  place(top + left, dx: b + tw, dy: b, box(width: sp, height: th,
    align(center + horizon, rotate(90deg, reflow: true,
      text(font: d.heading_font, weight: 800, size: calc.min(11, d.spine * 1.8) * 1pt, fill: white,
        if d.author != "" { d.title + "  ·  " + d.author } else { d.title })))))
}
