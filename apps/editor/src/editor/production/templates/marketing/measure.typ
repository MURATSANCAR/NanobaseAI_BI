// Arka kapak yazı alanının ölçümü (marketing.back_heights). Yazı biçimi cover.typ'nin arka kapak bloğuyla
// birebir aynıdır (başlık 17 pt, 5 mm boşluk, gövde 11,5 pt, satır aralığı 0,62em, paragraf arası 1em);
// cover.typ'de bu blok değişirse burası da değişir. Her aday metnin yüksekliği mm olarak <olcu> etiketine yazılır.
#let d = json(sys.inputs.at("data", default: "olcu.json"))
#set text(font: d.body_font, lang: "tr", hyphenate: false)
#context {
  let hs = ()
  for t in d.texts {
    let b = block(width: d.width * 1mm)[
      #set par(leading: 0.62em, spacing: 1em, justify: false)
      #text(font: d.heading_font, weight: 800, size: 17pt, d.title)
      #v(5mm)
      #text(size: 11.5pt)[#for p in t [#p #parbreak()]]
    ]
    hs.push(measure(b).height.mm())
  }
  [#metadata(hs) <olcu>]
}
