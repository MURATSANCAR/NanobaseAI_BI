// Değişiklik raporu (sürüm farkı): matbaa/yazar onayı için. Veri: data.json (versions_diff.report hazırlar).
// Değişen her sayfa: iki önizleme (değişen bölge kırmızı çerçeveli), kelime farkı (eklenen yeşil altı çizili,
// silinen kırmızı üstü çizili), yerleşim değişiklikleri. Değişmeyen sayfalar tek satırda aralık olarak.
#let d = json(sys.inputs.at("data", default: "data.json"))
#let ink = rgb("#1F2433")
#let muted = rgb("#5B6173")
#let ins-c = rgb("#13795B")
#let del-c = rgb("#B42318")
#let mark-c = rgb("#E5484D")
#let line-c = rgb("#E3E6EE")

#set document(title: "Değişiklik raporu — " + d.title)
#set page(paper: "a4", margin: (x: 16mm, top: 16mm, bottom: 18mm),
  footer: context [
    #set text(size: 8pt, fill: muted)
    #d.title · #d.a.label → #d.b.label #h(1fr) #counter(page).display("1 / 1", both: true)
  ])
#set text(font: "Andika", size: 9.5pt, lang: "tr", fill: ink)
#set par(leading: 0.55em, justify: false)

#let status-tr = (changed: "Değişti", added: "Eklendi", removed: "Silindi", same: "Aynı")
#let status-c = (changed: rgb("#6D4AFF"), added: ins-c, removed: del-c, same: muted)

#let pill(s) = box(inset: (x: 5pt, y: 2pt), radius: 6pt, fill: status-c.at(s).lighten(85%),
  text(size: 8pt, weight: "bold", fill: status-c.at(s), status-tr.at(s)))

#let seg(s) = {
  if s.op == "ins" { underline(stroke: 0.9pt + ins-c, offset: 2pt, text(fill: ins-c, weight: "bold", s.text)) }
  else if s.op == "del" { strike(stroke: 0.9pt + del-c, text(fill: del-c, s.text)) }
  else { text(s.text) }
}

#let shot(path, regions, w) = {
  let h = w * d.ratio
  if path == none {
    box(width: w, height: h, fill: rgb("#F4F5F8"), stroke: 0.5pt + line-c,
      align(center + horizon, text(size: 8pt, fill: muted, "bu sürümde yok")))
  } else {
    box(width: w, height: h, stroke: 0.5pt + line-c, {
      image(path, width: w, height: h, fit: "stretch")
      for r in regions {
        place(top + left, dx: r.x * w - 1pt, dy: r.y * h - 1pt,
          rect(width: r.w * w + 2pt, height: r.h * h + 2pt, stroke: 1.2pt + mark-c, radius: 1.5pt))
      }
    })
  }
}

// ---------------------------------------------------------------- kapak özeti
#text(size: 8.5pt, weight: "bold", fill: muted, tracking: 0.06em, "DEĞİŞİKLİK RAPORU")
#v(2pt)
#text(size: 20pt, weight: "bold", d.title)
#v(6pt)
#grid(columns: (auto, 1fr), column-gutter: 10pt, row-gutter: 5pt,
  text(fill: muted, "Önceki"), [#d.a.label #if d.a.at != none [· #d.a.at] #if d.a.by != none [· #d.a.by]],
  text(fill: muted, "Yeni"), [#d.b.label #if d.b.at != none [· #d.b.at] #if d.b.by != none [· #d.b.by]],
  text(fill: muted, "Hazırlayan"), [#d.by · #d.at],
)
#v(8pt)
#block(width: 100%, inset: 10pt, radius: 8pt, fill: rgb("#F6F4FF"), {
  grid(columns: (1fr, 1fr, 1fr, 1fr), column-gutter: 8pt,
    ..(("changed", "Değişen sayfa"), ("added", "Eklenen sayfa"), ("removed", "Silinen sayfa"), ("same", "Aynı kalan")).map(((k, l)) => [
      #text(size: 16pt, weight: "bold", fill: status-c.at(k), str(d.counts.at(k)))\
      #text(size: 8.5pt, fill: muted, l)
    ]))
  v(4pt)
  text(size: 8.5pt, fill: muted)[Metinde #text(fill: ins-c, weight: "bold", str(d.words.ins) + " kelime eklendi"),
    #text(fill: del-c, weight: "bold", str(d.words.del) + " kelime silindi").]
  if d.global.len() > 0 { linebreak(); text(size: 8.5pt, d.global.join(" · ")) }
})
#v(4pt)
#text(size: 8.5pt, fill: muted)[Okuma: #underline(stroke: 0.9pt + ins-c, offset: 2pt, text(fill: ins-c, weight: "bold", "eklenen")) ·
  #strike(stroke: 0.9pt + del-c, text(fill: del-c, "silinen")) · sayfa önizlemesindeki #text(fill: mark-c, weight: "bold", "kırmızı çerçeve") değişen bölge.]
#if d.same.len() > 0 [
  #v(4pt)
  #text(size: 8.5pt)[*Değişmeyen sayfalar (yeni numarayla):* #d.same.join(", ")]
]

// ---------------------------------------------------------------- sayfalar
#for p in d.pages {
  v(10pt)
  block(breakable: false, width: 100%, {
    line(length: 100%, stroke: 0.6pt + line-c)
    v(4pt)
    let no = if p.b != none { str(p.b.no) + ". sayfa" } else { str(p.a.no) + ". sayfa (önceki)" }
    let was = if p.a != none and p.b != none and p.a.no != p.b.no { " · önceki sürümde " + str(p.a.no) + "." } else { "" }
    [#text(size: 12pt, weight: "bold", no) #h(4pt) #pill(p.status) #text(size: 8.5pt, fill: muted, was)]
    v(6pt)
    grid(columns: (46mm, 46mm, 1fr), column-gutter: 8pt,
      [#text(size: 7.5pt, fill: muted, "Önceki") \ #shot(p.img_a, (), 46mm)],
      [#text(size: 7.5pt, fill: muted, "Yeni") \ #shot(p.img_b, p.regions, 46mm)],
      {
        for t in p.text {
          text(size: 8pt, weight: "bold", fill: muted, t.label)
          linebreak()
          for s in t.segments { seg(s) }
          v(5pt)
        }
        if p.layout.len() > 0 {
          text(size: 8pt, weight: "bold", fill: muted, "Yerleşim")
          list(tight: true, ..p.layout.map(l => text(size: 8.5pt, l.text)))
        }
        if p.text.len() == 0 and p.layout.len() == 0 {
          text(size: 8.5pt, fill: muted, "Yalnız görünüşte fark var (önizlemede işaretli).")
        }
      })
  })
}
