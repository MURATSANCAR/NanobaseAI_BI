// Sayfa planı şablonu. Veri: data.json (plan.render_data hazırlar; ölçüler mm, köken taşma paylı sayfanın sol üstü).
// Ön sayfalar book.typ ile aynı (front.typ). İç sayfalar akışsız: her plan sayfası kendi kutularıyla dizilir.
// Katmanlar: resim → yazı kutusu → balonlar → figür/fotoğraf/serbest yazı (z sırasıyla; Python sıralar).
// Yazı kutusuna sığmayan metin kesilmez; `overflow` işareti Python'a döner (plan.py sayfaya yazar).
#import "front.typ": mark, front-pages
#let d = json(sys.inputs.at("data", default: "data.json"))
#let s = d.spec
#let b = s.bleed * 1mm
#let W = s.trim_w * 1mm + 2 * b
#let H = s.trim_h * 1mm + 2 * b
#let accent = rgb(d.accent)
#let fonts = (body: s.body_font, heading: s.heading_font)

#set document(title: d.book.title, author: d.book.author)
#set text(font: s.body_font, size: d.body_size * 1pt, lang: "tr", hyphenate: s.hyphenate,
          costs: (widow: 100%, orphan: 100%))
#set par(leading: (s.leading - 0.7) * 1em, spacing: (s.leading - 0.2) * 1em, justify: s.justify,
         first-line-indent: 0pt)
#set page(width: W, height: H, binding: left, margin: 0pt, footer: none, background: none)

#front-pages(d, accent, b)

#let mm(v) = v * 1mm
#let at(bx, body) = place(top + left, dx: mm(bx.x), dy: mm(bx.y), body)
#let pts(ps) = ps.map(p => (mm(p.at(0)), mm(p.at(1))))

// ---------------------------------------------------------------- yazı
#let run(r) = {
  let a = (:)
  if r.at("color", default: none) != none { a.insert("fill", rgb(r.color)) }
  if r.at("weight", default: none) != none { a.insert("weight", r.weight) }
  if r.at("size", default: none) != none { a.insert("size", r.size * 1pt) }
  if r.at("font", default: none) != none { a.insert("font", fonts.at(r.font)) }
  text(..a, r.text)
}
#let runs(rs) = { for r in rs { run(r) } }

#let blk(k) = {
  let body = runs(k.runs)
  if k.kind == "heading" {
    block(below: 1.1em, sticky: true,
          text(font: s.heading_font, weight: 800, size: 1.55em, fill: accent, hyphenate: false, body))
  } else if k.kind == "sound" {
    par(text(font: s.heading_font, weight: 800, size: 1.35em, fill: accent, body))
  } else if k.kind == "dialogue" { par[– #body] } else { par(body) }
}

// t: {box, align, size, ink, background, pad, blocks | runs}; kutudan taşan metin kesilmez, işaretlenir.
#let textbox(t, pid, id, what) = {
  let pad = mm(t.pad)
  let w = mm(t.box.w) - 2 * pad
  let h = mm(t.box.h) - 2 * pad
  let body = {
    set text(size: t.size * 1pt, fill: rgb(t.ink))
    set par(justify: t.align == "justify")
    set align(if t.align == "center" { center } else { left })
    if "blocks" in t { for k in t.blocks { blk(k) } } else { par(runs(t.runs)) }
  }
  at(t.box, context {
    let need = measure(block(width: w, body)).height
    if need > h + 0.3mm {
      metadata((kind: "overflow", page: pid, id: id, what: what, need: (need + 2 * pad) / 1mm))
    }
    box(width: mm(t.box.w), height: mm(t.box.h), inset: pad, radius: if t.background != none { 2mm } else { 0mm },
        fill: if t.background != none { rgb(t.background) } else { none }, block(width: w, body))
  })
}

// ---------------------------------------------------------------- resim, figür, fotoğraf
// a: {box, path | none, fit, iw, ih, dx, dy, label}; kaplama kırpması (odak) Python'da hesaplanır.
#let art-item(a) = at(a.box, box(width: mm(a.box.w), height: mm(a.box.h), clip: true,
  if a.path == none {
    rect(width: 100%, height: 100%, fill: accent.lighten(82%), stroke: none,
         align(center + horizon, text(font: s.heading_font, size: 13pt, fill: accent.darken(10%), a.label)))
  } else if a.fit == "contain" {
    image(a.path, width: 100%, height: 100%, fit: "contain")
  } else {
    place(top + left, dx: mm(a.dx), dy: mm(a.dy), image(a.path, width: mm(a.iw), height: mm(a.ih)))
  }))

#let figure-item(f) = at(f.box, box(width: mm(f.box.w), height: mm(f.box.h),
  rotate(f.rotate * 1deg, scale(x: if f.flip { -100% } else { 100% },
    image(f.path, width: mm(f.box.w), height: mm(f.box.h), fit: "contain")))))

// ---------------------------------------------------------------- balon
// bb: {outline, tail | none, tail_fill | none, dots, stroke, text}; şekiller mm cinsinden çokgen (Python hesaplar).
#let bubble(bb, pid) = {
  let st = 0.8pt + rgb(bb.stroke)
  if bb.tail != none { place(top + left, polygon(fill: white, stroke: st, ..pts(bb.tail))) }
  for c in bb.dots {
    place(top + left, dx: mm(c.at(0) - c.at(2)), dy: mm(c.at(1) - c.at(2)),
          circle(radius: mm(c.at(2)), fill: white, stroke: st))
  }
  place(top + left, polygon(fill: white, stroke: st, ..pts(bb.outline)))
  if bb.tail_fill != none { place(top + left, polygon(fill: white, stroke: none, ..pts(bb.tail_fill))) }
  textbox(bb.text, pid, bb.id, "bubble")
}

// ---------------------------------------------------------------- sayfalar
#for pg in d.pages {
  page[
    #mark((kind: "plan", id: pg.id))
    #if pg.art != none { art-item(pg.art) }
    #if pg.text != none { textbox(pg.text, pg.id, pg.id, "text") }
    #for bb in pg.bubbles { bubble(bb, pg.id) }
    #for it in pg.items {
      if it.type == "text" { textbox(it, pg.id, it.id, "free") } else { figure-item(it) }
    }
    #if pg.folio {
      place(top + left, dy: H - b - 12mm, box(width: W, align(center,
        context text(size: 10pt, fill: luma(110), str(here().page())))))
    }
  ]
}
