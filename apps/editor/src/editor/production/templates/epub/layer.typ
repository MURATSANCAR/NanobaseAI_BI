// E-kitabın vektör katmanları (epub.py → Fixed.build_layers). Her katman taşma paylı tam sayfa, saydam zemin:
// şekiller ve efekt yazılar plan.typ'deki gibi kutularına çizilir (kutu, döndürme, aynalama burada; çizim
// elements.typ'de). Çıktı SVG; e-kitapta sayfanın üstüne görsel olarak konur, gerçek metin HTML'de ayrıca durur.
#import "elements.typ": draw-shape, effect-text
#let d = json(sys.inputs.at("data", default: "data.json"))
#let s = d.spec
#let b = s.bleed * 1mm
#let W = s.trim_w * 1mm + 2 * b
#let H = s.trim_h * 1mm + 2 * b
#let fonts = (body: s.body_font, heading: s.heading_font)

#set text(font: s.body_font, lang: "tr", hyphenate: false)
#set page(width: W, height: H, margin: 0pt, fill: none, footer: none, header: none)

#let mm(v) = v * 1mm
#let at(bx, body) = place(top + left, dx: mm(bx.x), dy: mm(bx.y), body)
#let turned(it, body) = at(it.box, box(width: mm(it.box.w), height: mm(it.box.h),
  rotate(it.rotate * 1deg, scale(x: if it.flip { -100% } else { 100% }, body))))

#for layer in d.layers {
  page[
    #for it in layer.items {
      if it.type == "shape" {
        turned(it, box(width: mm(it.box.w), height: mm(it.box.h), draw-shape(it, d.palette, fonts)))
      } else {
        at(it.box, box(width: mm(it.box.w), height: mm(it.box.h), effect-text(it, d.palette, fonts)))
      }
    }
  ]
}
