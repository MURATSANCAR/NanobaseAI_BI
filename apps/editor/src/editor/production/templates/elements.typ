// Öğeler: süs/şekil katmanı ve efekt yazı (sayfa planı sözleşmesi, «Efekt yazılar ve süs/şekiller»).
//   draw-shape(s, palette, fonts, mirror: s.flip)   plan sayfasının shapes[] öğesini kutusunun içine (0,0,w,h) çizer
//   effect-text(t, palette, fonts)  effect'li serbest yazıyı (texts[] öğesi) kutusunun içine çizer
// Kutunun sayfadaki yeri, döndürme ve z sırası çağıranındır (plan.typ); aynalamayı draw-shape yapar (yazı düz kalır,
// çağıran kutuyu aynalamaz). Her şey vektör; harfler metin
// olarak kalır (Türkçe doğru, PDF'te aranır, düzeltilebilir). Rastgelelik yalnız tohumlu: aynı girdi → aynı çizim.
// Renk alanı "#RRGGBB" ya da rol adıdır (roles); rol kitabın paletinden türetilir. Varsayılanlar SHAPE-DEFAULTS
// ve EFFECT-DEFAULTS'ta; elements.py'deki katalogla aynı oldukları test_elements'ta sınanır.
// Sabit yazı puntosuyla kutuya sığmayan yazı kesilmez; çizim `metadata((kind: "element-overflow", id))` bırakır.

// ================================================================ yardımcılar
#let _get(d, k, def) = {
  if type(d) != dictionary { return def }
  let v = d.at(k, default: none)
  if v == none { def } else { v }
}

#let _hexes(palette) = {
  let out = ()
  for c in _get(palette, "colors", ()) {
    let h = if type(c) == dictionary { c.at("hex", default: none) } else { c }
    if h != none and upper(h) not in out { out.push(upper(h)) }
  }
  out
}

// Aynı ton, verilen açıklık (OKLCH L, 0–1) ve en çok verilen kroma: açık zeminler ve canlı dolgular için.
// Kroma üst sınırı baskı güvenliğidir (açık tonda yüksek kroma CMYK dışına taşar). hue verilirse ton o açıya çekilir.
// cmin: canlı rollerde (güneş, gül, canlı dolgu) soluk paletten gelen renk en az bu kromaya çıkarılır (ton korunur).
#let _tone(hex, l, cmax, hue: none, cmin: 0) = {
  let (_, c, h, ..) = oklch(rgb(hex)).components()
  upper(rgb(oklch(l * 100%, calc.max(cmin, calc.min(c, cmax)), if hue == none { h } else { hue })).to-hex())
}

#let _hue(hex) = oklch(rgb(hex)).components().at(2).deg()

// Paletten, verilen tona (OKLCH açısı) en yakın renk; 50°'den uzaksa yedek.
#let _nearest-hue(hexes, target, fallback) = {
  let pick = fallback
  let best = 50.0
  for h in hexes {
    let d = calc.abs(_hue(h) - target)
    let d = calc.min(d, 360 - d)
    if d < best { best = d; pick = h }
  }
  pick
}

#let WARM-HUE = 75          // sarı-turuncu (OKLCH ton açısı); «güneş», «kâğıt», «ahşap» bu tona en yakın renkten
#let WARM-FALLBACK = "#8A6500"   // palette sıcak renk yoksa Timaş çocuk paletinin «Hardal»ı
#let ROSE-HUE = 25          // kırmızı; «gül» (kalp) bu tona en yakın renkten
#let ROSE-FALLBACK = "#B0341C"   // yoksa Timaş «Kiremit»
#let WOOD-HUE = 68          // ahşap tonu: sıcak rengin tonuyla bu açının ortası (turuncu palette pembe ahşap olmasın)

// Paletten roller. Karakterlere verilmemiş renkler önce; palette.roles verilmişse o anahtarlar kazanır.
#let roles(palette) = {
  let hexes = _hexes(palette)
  let chars = _get(palette, "characters", (:)).values().map(upper)
  let pool = hexes.filter(h => h not in chars) + hexes.filter(h => h in chars)
  let accent = upper(_get(palette, "accent", if pool.len() > 0 { pool.first() } else { "#B0341C" }))
  let rest = pool.filter(h => h != accent)
  let accent2 = if rest.len() > 0 { rest.first() } else { "#1F3B73" }
  let warm = _nearest-hue(hexes, WARM-HUE, WARM-FALLBACK)
  let rose = _nearest-hue(hexes, ROSE-HUE, ROSE-FALLBACK)
  let wh = (_hue(warm) + WOOD-HUE) / 2 * 1deg
  let r = (
    accent: accent, accent2: accent2, ink: upper(_get(palette, "text", "#2C2C2A")),
    pop: _tone(accent, 0.64, 0.17, cmin: 0.09), pop2: _tone(accent2, 0.64, 0.15, cmin: 0.09),
    sun: _tone(warm, 0.86, 0.16, cmin: 0.13), rose: _tone(rose, 0.62, 0.18, cmin: 0.14),
    soft: _tone(accent, 0.94, 0.04), soft2: _tone(accent2, 0.94, 0.04), paper: _tone(warm, 0.975, 0.025),
    wood: _tone(warm, 0.8, 0.07, hue: wh), bark: _tone(warm, 0.42, 0.06, hue: wh), deep: _tone(accent, 0.34, 0.09),
    white: "#FFFFFF",
  )
  for (k, v) in _get(palette, "roles", (:)) { if type(v) == str { r.insert(k, upper(v)) } }
  // canlı dolgu listesi (serpiştirme, konfeti) ve harf harf renk listesi (gökkuşağı, zıplayan)
  let bright = (r.pop, r.sun, r.pop2)
  for h in rest.slice(calc.min(1, rest.len())) {
    let t = _tone(h, 0.66, 0.15, cmin: 0.09)
    if t not in bright { bright.push(t) }
  }
  r.insert("bright", bright)
  r.insert("letters", if pool.len() > 0 { (accent,) + rest } else { (accent, accent2) })
  r
}

#let _col(v, R, def) = {
  let v = if v == none { def } else { v }
  if v == none or v == "none" { return none }
  if type(v) == color { return v }
  if type(v) == str and v in R and type(R.at(v)) == str { return rgb(R.at(v)) }
  if type(v) == str and v.starts-with("#") { return rgb(v) }
  rgb(R.accent)                          // tanınmayan değeri doğrulama reddeder; çizim düşmesin
}

#let _stk(paint, w, dash: none, join: "round") = {
  if paint == none or w <= 0pt { return none }
  let s = (paint: paint, thickness: w, cap: "round", join: join)
  if dash != none { s.insert("dash", dash) }
  s
}

#let _alpha(c, op) = if c == none or op >= 1 { c } else { c.transparentize((1 - op) * 100%) }

#let _dark(c) = {
  if c == none { return false }
  let (r, g, b, ..) = rgb(c).components()
  (0.2126 * r + 0.7152 * g + 0.0722 * b) / 100% < 0.5
}

#let _mix(a, b, t) = color.mix((a, (1 - t) * 100%), (b, t * 100%), space: oklab)

// noktalar: (x, y) uzunluk çiftleri
#let _add(a, b) = (a.at(0) + b.at(0), a.at(1) + b.at(1))
#let _sub(a, b) = (a.at(0) - b.at(0), a.at(1) - b.at(1))
#let _mul(a, k) = (a.at(0) * k, a.at(1) * k)

// Noktalardan geçen yumuşak eğri (Catmull-Rom → kübik Bézier).
#let _smooth(pts, closed: true, fill: none, stroke: none) = {
  let n = pts.len()
  let segs = (curve.move(pts.at(0)),)
  let last = if closed { n } else { n - 1 }
  for i in range(last) {
    let p0 = if closed { pts.at(calc.rem(i - 1 + n, n)) } else { pts.at(calc.max(i - 1, 0)) }
    let p1 = pts.at(i)
    let p2 = pts.at(calc.rem(i + 1, n))
    let p3 = if closed { pts.at(calc.rem(i + 2, n)) } else { pts.at(calc.min(i + 2, n - 1)) }
    segs.push(curve.cubic(_add(p1, _mul(_sub(p2, p0), 1 / 6)), _sub(p2, _mul(_sub(p3, p1), 1 / 6)), p2))
  }
  if closed { segs.push(curve.close(mode: "straight")) }
  place(top + left, curve(fill: fill, stroke: stroke, ..segs))
}

#let _poly(pts, fill: none, stroke: none) = place(top + left, polygon(fill: fill, stroke: stroke, ..pts))

// Yuvarlak köşeli dikdörtgenin çevresi ve çevre üzerindeki nokta (x, y, dış normal x, y); saat yönünde,
// üst kenarın solundan başlar.
#let _rr-len(w, h, r) = 2 * (w - 2 * r) + 2 * (h - 2 * r) + 2 * calc.pi * r

#let _rr-point(x0, y0, w, h, r, t) = {
  let t = t
  let e1 = w - 2 * r
  let e2 = h - 2 * r
  let q = calc.pi / 2 * r
  let arc(cx, cy, a0, t) = {
    let a = a0 + 90deg * (if q > 0pt { t / q } else { 0 })
    (cx + r * calc.cos(a), cy + r * calc.sin(a), calc.cos(a), calc.sin(a))
  }
  if t <= e1 { return (x0 + r + t, y0, 0.0, -1.0) }
  t -= e1
  if t <= q { return arc(x0 + w - r, y0 + r, -90deg, t) }
  t -= q
  if t <= e2 { return (x0 + w, y0 + r + t, 1.0, 0.0) }
  t -= e2
  if t <= q { return arc(x0 + w - r, y0 + h - r, 0deg, t) }
  t -= q
  if t <= e1 { return (x0 + w - r - t, y0 + h, 0.0, 1.0) }
  t -= e1
  if t <= q { return arc(x0 + r, y0 + h - r, 90deg, t) }
  t -= q
  if t <= e2 { return (x0, y0 + h - r - t, -1.0, 0.0) }
  t -= e2
  arc(x0 + r, y0 + r, 180deg, calc.min(t, q))
}

// Yıldız köşeleri; köşe yuvarlaklığı aynı renkte yuvarlak birleşimli çizgiyle verilir.
#let _star-pts(cx, cy, r, n: 5, inner: 0.5, rot: 0deg) = {
  let pts = ()
  for i in range(2 * n) {
    let a = -90deg + rot + 180deg / n * i
    let rr = if calc.even(i) { r } else { r * inner }
    pts.push((cx + rr * calc.cos(a), cy + rr * calc.sin(a)))
  }
  pts
}

#let _star(cx, cy, r, fill, stroke: none, n: 5, inner: 0.5, rot: 0deg, round: 0.14) = {
  let pts = _star-pts(cx, cy, r * (1 - round * 0.5), n: n, inner: inner, rot: rot)
  let st = if stroke != none { stroke } else if fill != none { _stk(fill, r * round) } else { none }
  _poly(pts, fill: fill, stroke: st)
}

// Kalp: genişliği s, merkez (cx, cy).
#let _heart(cx, cy, s, fill, stroke: none) = {
  let P(u, v) = (cx + (u - 0.5) * s, cy + (v - 0.47) * s)
  place(top + left, curve(fill: fill, stroke: stroke,
    curve.move(P(0.5, 0.94)),
    curve.cubic(P(0.2, 0.72), P(0.0, 0.5), P(0.0, 0.3)),
    curve.cubic(P(0.0, 0.12), P(0.13, 0.0), P(0.28, 0.0)),
    curve.cubic(P(0.4, 0.0), P(0.47, 0.07), P(0.5, 0.17)),
    curve.cubic(P(0.53, 0.07), P(0.6, 0.0), P(0.72, 0.0)),
    curve.cubic(P(0.87, 0.0), P(1.0, 0.12), P(1.0, 0.3)),
    curve.cubic(P(1.0, 0.5), P(0.8, 0.72), P(0.5, 0.94)),
    curve.close(mode: "straight")))
}

#let _dot(cx, cy, r, fill, stroke: none) = place(top + left, dx: cx - r, dy: cy - r,
  circle(radius: r, fill: fill, stroke: stroke))

// Yaprak (badem): tabandan uca iki kuadratik eğri.
#let _leaf(b, t, wid, fill, stroke: none) = {
  let d = _sub(t, b)
  let n = (d.at(1) * -1, d.at(0))                  // dik yön (uzunluk)
  let L = calc.sqrt(calc.pow(d.at(0) / 1pt, 2) + calc.pow(d.at(1) / 1pt, 2))
  let k = if L > 0 { wid / 1pt / L } else { 0 }
  let m = _add(b, _mul(d, 0.5))
  place(top + left, curve(fill: fill, stroke: stroke,
    curve.move(b), curve.quad(_add(m, _mul(n, k)), t), curve.quad(_sub(m, _mul(n, k)), b),
    curve.close(mode: "straight")))
}

// Dört köşeli pırıltı.
#let _sparkle(cx, cy, r, fill) = {
  let P(a, rr) = (cx + rr * calc.cos(a), cy + rr * calc.sin(a))
  let segs = (curve.move(P(-90deg, r)),)
  for i in range(4) {
    let a = -90deg + 90deg * i
    segs.push(curve.quad((cx, cy), P(a + 90deg, r)))
  }
  segs.push(curve.close(mode: "straight"))
  place(top + left, curve(fill: fill, stroke: _stk(fill, r * 0.08), ..segs))
}

// Elips çevresinde kabarcıklı kenar (bulut, rozet). sizes: kabarcık büyüklük deseni (döngüsel).
#let _bumps(cx, cy, rx, ry, n, bulge, fill, stroke, sizes: (1.0,), rot: 0deg) = {
  let pts = ()
  for i in range(n) {
    let a = -90deg + rot + 360deg / n * i
    pts.push((cx + rx * calc.cos(a), cy + ry * calc.sin(a), calc.cos(a), calc.sin(a)))
  }
  let segs = (curve.move((pts.at(0).at(0), pts.at(0).at(1))),)
  for i in range(n) {
    let a = pts.at(i)
    let b = pts.at(calc.rem(i + 1, n))
    let chord = calc.sqrt(calc.pow((b.at(0) - a.at(0)) / 1pt, 2) + calc.pow((b.at(1) - a.at(1)) / 1pt, 2)) * 1pt
    let k = chord * bulge * sizes.at(calc.rem(i, sizes.len()))
    segs.push(curve.cubic((a.at(0) + a.at(2) * k, a.at(1) + a.at(3) * k),
                          (b.at(0) + b.at(2) * k, b.at(1) + b.at(3) * k), (b.at(0), b.at(1))))
  }
  segs.push(curve.close(mode: "straight"))
  place(top + left, curve(fill: fill, stroke: stroke, ..segs))
}

// Patlama köşeleri: sivri uçlar, uç uzunlukları tohumla hafif değişir.
#let _burst-pts(cx, cy, rx, ry, n, inner, seed, rot: 0deg) = {
  let st = calc.rem(seed * 7919 + 104729, 2147483648)
  let pts = ()
  for i in range(2 * n) {
    st = calc.rem(st * 1103515245 + 12345, 2147483648)
    let j = st / 2147483648.0
    let a = -90deg + rot + 180deg / n * i + (j - 0.5) * (60deg / n)
    let k = if calc.even(i) { 0.86 + 0.14 * j } else { inner * (0.92 + 0.12 * j) }
    pts.push((cx + rx * k * calc.cos(a), cy + ry * k * calc.sin(a)))
  }
  pts
}

// ================================================================ yazı
#let _font(fonts, key) = {
  if key == "body" { _get(fonts, "body", _get(fonts, "body_font", "Andika")) }
  else { _get(fonts, "heading", _get(fonts, "heading_font", "Baloo 2")) }
}

// Boş olmayan run'lar; rengi (hex ya da rol) renge çevrilmiş.
#let _runs(x, R) = {
  let rs = _get(x, "runs", ())
  if type(rs) != array { return () }
  let out = ()
  for r in rs {
    if type(r) == dictionary and type(r.at("text", default: none)) == str and r.text != "" {
      let r2 = r
      let c = r.at("color", default: none)
      if c != none { r2.insert("color", _col(c, R, none)) }
      out.push(r2)
    }
  }
  out
}

// Bir run'ın biçimi: font, kalınlık, punto (taban × k).
#let _style(r, base, k, fonts) = (
  font: _font(fonts, _get(r, "font", "heading")), weight: _get(r, "weight", 700),
  size: _get(r, "size", base) * k * 1pt,
)

// Metin katmanı (paragraf düzeni). paint: bütün harfler tek renk (dış çizgi/gölge katmanı); colors: harf harf
// dönen renkler; bounce: harfler sırayla yukarı/aşağı ve hafif dönük; stroke: harf dış çizgisi.
#let _layer(runs, base, k, fonts, ink, paint: none, colors: none, bounce: false, stroke: none) = {
  let i = 0
  for r in runs {
    let st = _style(r, base, k, fonts)
    let own = _get(r, "color", none)
    let lines = r.text.split("\n")
    for (li, line) in lines.enumerate() {
      if li > 0 { linebreak() }
      if colors == none and not bounce {
        let f = if paint != none { paint } else if own != none { own } else { ink }
        text(..st, fill: f, stroke: stroke, line)
      } else {
        for (wi, word) in line.split(" ").enumerate() {
          if wi > 0 { text(..st, " ") }
          let letters = ()
          for ch in word.clusters() {
            let f = if paint != none { paint } else if colors != none { colors.at(calc.rem(i, colors.len())) }
                    else if own != none { own } else { ink }
            let t = text(..st, fill: f, stroke: stroke, ch)
            if bounce {
              let up = if calc.even(i) { -1 } else { 1 }
              let tilt = (if calc.rem(i, 3) == 0 { 7deg } else if calc.rem(i, 3) == 1 { -5deg } else { 3deg })
              letters.push(box(baseline: up * 0.09em, rotate(tilt * up, reflow: false, t)))
            } else { letters.push(t) }
            i += 1
          }
          box(letters.join())                 // kelime bölünmez
        }
      }
    }
  }
}

#let _para(body, W, align-x) = block(width: W, {
  set par(leading: 0.42em, spacing: 0.42em, justify: false, first-line-indent: 0pt)
  set text(lang: "tr", hyphenate: false, top-edge: "cap-height", bottom-edge: "baseline")
  align(align-x, body)
})

#let _align(a) = if a == "left" { left } else if a == "right" { right } else { center }

#let _max-size(runs, base) = calc.max(..runs.map(r => _get(r, "size", base)))

// Kutuya sığan en büyük ölçek (context içinde). Yükseklik payı: büyük harf üstü işaretler (Ü, Ş, Ğ) için 0,3 em,
// alt uzantılar için 0,27 em. Kelime bölünmez: en geniş kelime kutu genişliğini aşamaz.
#let _fit(runs, base, fonts, W, H, align-x, bounce: false) = {
  let ww = 0pt
  for r in runs {
    let st = _style(r, base, 1, fonts)
    for word in r.text.split(regex("\s+")) {
      if word != "" { ww = calc.max(ww, measure(text(..st, word)).width * (if bounce { 1.08 } else { 1 })) }
    }
  }
  let big = _max-size(runs, base)
  let lo = 0.0
  let hi = if ww > 0pt { calc.min(40.0, W / ww) } else { 40.0 }
  for _ in range(22) {
    let mid = (lo + hi) / 2
    let m = measure(_para(_layer(runs, base, mid, fonts, black, bounce: bounce), W, align-x))
    if m.height + 0.57 * big * mid * 1pt <= H { lo = mid } else { hi = mid }
  }
  lo
}

// Yazıyı alanın içine yerleştirir: katmanlar (layers) aynı düzenle üst üste basılır.
//   layers: big → ((dx, dy, paint, colors, stroke), …); big = en büyük harf puntosu; son katman asıl yazı.
#let _text-in(runs, area, size, fonts, ink, align-x, id, layers: none, bounce: false, colors: none) = context {
  let (x, y, W, H) = area
  if runs.len() > 0 and W > 0pt and H > 0pt {
  let fixed = size != none
  let base = if fixed { size } else { 20 }
  let k = if fixed { 1.0 } else { _fit(runs, base, fonts, W, H, align-x, bounce: bounce) }
  let big = _max-size(runs, base) * k * 1pt
  let make(paint, cols, stroke) = _para(_layer(runs, base, k, fonts, ink, paint: paint, colors: cols,
                                                bounce: bounce, stroke: stroke), W, align-x)
  let m = measure(make(none, colors, none))
  if fixed and m.height + 0.57 * big > H + 0.5pt { metadata((kind: "element-overflow", id: id)) }
  let ty = y + (H - m.height - 0.57 * big) / 2 + 0.3 * big
  let ls = if layers == none { ((0pt, 0pt, none, colors, none),) } else { layers(big) }
  for (i, (dx, dy, paint, cols, stroke)) in ls.enumerate() {
    let body = make(paint, cols, stroke)
    // süs katmanları (gölge, dış çizgi, derinlik) PDF'te yapaylık (artifact) olarak işaretlenir; metin asıl katmandır
    place(top + left, dx: x + dx, dy: ty + dy, if i < ls.len() - 1 { pdf.artifact(body) } else { body })
  }
  }
}

// ================================================================ şekiller
// Her çizici c = (w, h, F, S, sw, p, R, fonts) alır; (body, area, ink) döner. area: yazı alanı (x, y, w, h)
// ya da none; ink: yazının varsayılan rengi.

#let _frame(c) = {
  let (w, h, F, S, sw, p, R) = (c.w, c.h, c.F, c.S, c.sw, c.p, c.R)
  let orn = p.ornament
  let osz = if orn == "none" { 0pt } else { calc.max(sw * 5, 5mm) }
  let ins = calc.max(sw / 2, osz / 2)
  let (x0, y0, fw, fh) = (ins, ins, w - 2 * ins, h - 2 * ins)
  let r = calc.min(p.radius * 1mm, calc.min(fw, fh) / 2)
  let st = p.style
  let body = {
    if st == "plain" or st == "dashed" {
      let dash = if st == "dashed" { (sw * 2.2, sw * 2.4) } else { none }
      place(top + left, dx: x0, dy: y0, rect(width: fw, height: fh, radius: r, fill: F, stroke: _stk(S, sw, dash: dash)))
    } else if st == "double" {
      let g = sw * 2.2
      place(top + left, dx: x0, dy: y0, rect(width: fw, height: fh, radius: r, fill: F, stroke: _stk(S, sw)))
      place(top + left, dx: x0 + g, dy: y0 + g, rect(width: fw - 2 * g, height: fh - 2 * g,
        radius: calc.max(r - g, 0pt), stroke: _stk(S, sw * 0.45)))
    } else if st == "dotted" {
      if F != none { place(top + left, dx: x0, dy: y0, rect(width: fw, height: fh, radius: r, fill: F)) }
      let d = sw * 1.5
      let P = _rr-len(fw, fh, r)
      let n = calc.max(4, int(calc.round(P / (sw * 3.2))))
      for i in range(n) {
        let q = _rr-point(x0, y0, fw, fh, r, P * i / n)
        _dot(q.at(0), q.at(1), d / 2, S)
      }
    } else {                                           // dalgalı
      let a = sw * 1.2
      let lam = sw * 8
      let rr = calc.max(r - a, lam / 2)
      let (ax, ay, aw, ah) = (x0 + a, y0 + a, fw - 2 * a, fh - 2 * a)
      let rr = calc.min(rr, calc.min(aw, ah) / 2)
      let P = _rr-len(aw, ah, rr)
      let n = calc.max(4, int(calc.round(P / lam)))
      let pts = ()
      for i in range(n * 8) {
        let q = _rr-point(ax, ay, aw, ah, rr, P * i / (n * 8))
        let o = a * calc.sin(2 * calc.pi * i / 8)
        pts.push((q.at(0) + q.at(2) * o, q.at(1) + q.at(3) * o))
      }
      _smooth(pts, fill: F, stroke: _stk(S, sw))
    }
    if orn != "none" {
      let oc = rgb(R.pop2)
      for (cx, cy) in ((x0 + r, y0 + r), (x0 + fw - r, y0 + r), (x0 + fw - r, y0 + fh - r), (x0 + r, y0 + fh - r)) {
        let ox = if cx < w / 2 { cx - r * 0.7071 } else { cx + r * 0.7071 }
        let oy = if cy < h / 2 { cy - r * 0.7071 } else { cy + r * 0.7071 }
        if orn == "star" { _star(ox, oy, osz / 2, oc) }
        else if orn == "heart" { _heart(ox, oy, osz, oc) }
        else { _dot(ox, oy, osz * 0.32, oc) }
      }
    }
  }
  (body: body, area: none, ink: rgb(R.ink))
}

#let _corner(c) = {
  let (w, h, F, S, sw, p, R) = (c.w, c.h, c.F, c.S, c.sw, c.p, c.R)
  let cr = p.corner
  let m = calc.min(w, h)
  let P(u, v) = (if cr.ends-with("r") { w - u * w } else { u * w }, if cr.starts-with("b") { h - v * h } else { v * h })
  let st = p.style
  let body = {
    if st == "swirl" {
      // köşeye doğru kıvrılan asma, iki kolunda yapraklar
      let arm = ((0.94, 0.07), (0.7, 0.07), (0.47, 0.12), (0.3, 0.22), (0.22, 0.3), (0.12, 0.47), (0.07, 0.7), (0.07, 0.94))
      _smooth(arm.map(((u, v)) => P(u, v)), closed: false, stroke: _stk(S, sw))
      // asmanın köşeye en yakın noktasından içeri dönen sarmal
      let curl = ()
      for i in range(29) {
        let t = i / 28
        let a = 45deg + 400deg * t
        let rr = 0.141 * (1 - 0.74 * t)
        curl.push(P(0.16 + rr * calc.cos(a), 0.16 + rr * calc.sin(a)))
      }
      _smooth(curl, closed: false, stroke: _stk(S, sw * 0.9))
      for (b, t) in (((0.62, 0.08), (0.56, 0.2)), ((0.8, 0.07), (0.88, 0.16)), ((0.08, 0.62), (0.2, 0.56)),
                     ((0.07, 0.8), (0.16, 0.88)), ((0.44, 0.13), (0.4, 0.02)), ((0.13, 0.44), (0.02, 0.4))) {
        _leaf(P(..b), P(..t), m * 0.035, F, stroke: none)
      }
      _dot(..P(0.95, 0.07), sw * 1.4, S)
      _dot(..P(0.07, 0.95), sw * 1.4, S)
      _dot(..P(0.4, 0.4), m * 0.022, F)
      _dot(..P(0.49, 0.49), m * 0.014, F)
    } else if st == "flower" {
      let cx = 0.2
      _smooth(((0.2, 0.2), (0.45, 0.1), (0.7, 0.08), (0.93, 0.06)).map(((u, v)) => P(u, v)), closed: false, stroke: _stk(S, sw))
      _smooth(((0.2, 0.2), (0.1, 0.45), (0.08, 0.7), (0.06, 0.93)).map(((u, v)) => P(u, v)), closed: false, stroke: _stk(S, sw))
      for (b, t) in (((0.5, 0.09), (0.58, 0.2)), ((0.74, 0.08), (0.8, 0.17)), ((0.09, 0.5), (0.2, 0.58)), ((0.08, 0.74), (0.17, 0.8))) {
        _leaf(P(..b), P(..t), m * 0.035, F)
      }
      let petal = rgb(R.pop)
      for i in range(6) {
        let a = 60deg * i + 15deg
        let tip = (cx + 0.15 * calc.cos(a), cx + 0.15 * calc.sin(a))
        _leaf(P(cx, cx), P(..tip), m * 0.055, petal)
      }
      _dot(..P(cx, cx), m * 0.05, rgb(R.sun), stroke: _stk(rgb(R.pop), sw * 0.5))
      _dot(..P(0.96, 0.06), m * 0.02, petal)
      _dot(..P(0.06, 0.96), m * 0.02, petal)
    } else if st == "dots" {
      // köşeden uzaklaştıkça küçülen noktalar (yarım ton)
      let col = if F != none { F } else { rgb(R.pop) }
      let n = 9
      for i in range(n) {
        for j in range(n) {
          let d = calc.sqrt(i * i + j * j) / n
          let rr = 0.045 * (1 - d * 1.05)
          if rr > 0.006 { _dot(..P(0.06 + i * 0.105, 0.06 + j * 0.105), m * rr, col) }
        }
      }
    } else {                                           // yıldızlar
      let a = rgb(R.sun)
      let b = if F != none { F } else { rgb(R.pop2) }
      _star(..P(0.22, 0.22), m * 0.16, a, stroke: _stk(rgb(R.pop), m * 0.018), rot: -8deg)
      _star(..P(0.56, 0.12), m * 0.075, b, rot: 12deg)
      _star(..P(0.12, 0.56), m * 0.065, b, rot: -14deg)
      _sparkle(..P(0.78, 0.2), m * 0.06, a)
      _sparkle(..P(0.2, 0.8), m * 0.05, a)
      _dot(..P(0.44, 0.34), m * 0.018, b)
      _dot(..P(0.34, 0.44), m * 0.014, b)
      _dot(..P(0.9, 0.08), m * 0.014, b)
      _dot(..P(0.08, 0.9), m * 0.014, b)
    }
  }
  (body: body, area: none, ink: rgb(R.ink))
}

#let _scatter(c) = {
  let (w, h, F, S, sw, p, R) = (c.w, c.h, c.F, c.S, c.sw, c.p, c.R)
  let n = calc.max(1, int(p.count))
  let cols = if F != none { (F,) } else { R.bright.map(rgb) }
  let size = p.size * 1mm
  let gx = calc.max(1, int(calc.round(calc.sqrt(n * (w / h)))))
  let gy = int(calc.ceil(n / gx))
  let (cw, ch) = (w / gx, h / gy)
  let st = calc.rem(int(p.seed) * 7919 + 104729, 2147483648)
  let cells = range(gx * gy)
  // hücre seçimi: tohumlu karıştırma (Fisher–Yates), ilk n hücre
  for i in range(cells.len() - 1, 0, step: -1) {
    st = calc.rem(st * 1103515245 + 12345, 2147483648)
    let j = calc.rem(st, i + 1)
    let t = cells.at(i)
    cells.at(i) = cells.at(j)
    cells.at(j) = t
  }
  let body = {
    for (i, cell) in cells.slice(0, n).sorted().enumerate() {
      let rnd = ()
      for _ in range(4) {
        st = calc.rem(st * 1103515245 + 12345, 2147483648)
        rnd.push(st / 2147483648.0)
      }
      let s = size * (0.62 + 0.38 * rnd.at(0))
      let s = calc.min(s, calc.min(cw, ch))
      let cx = calc.rem(cell, gx) * cw + s / 2 + (cw - s) * rnd.at(1)
      let cy = calc.floor(cell / gx) * ch + s / 2 + (ch - s) * rnd.at(2)
      let rot = (rnd.at(3) - 0.5) * 50deg
      let col = cols.at(calc.rem(i, cols.len()))
      let stroke = _stk(S, sw)
      let item = p.item
      if item == "star" { _star(cx, cy, s / 2, col, rot: rot) }
      else if item == "heart" { _heart(cx, cy, s, col, stroke: stroke) }
      else if item == "dot" { _dot(cx, cy, s * 0.32, col, stroke: stroke) }
      else if item == "sparkle" { _sparkle(cx, cy, s / 2, col) }
      else {                                           // konfeti: şerit, daire, kıvrım, üçgen
        let kind = calc.rem(i, 4)
        if kind == 0 {
          place(top + left, dx: cx - s / 2, dy: cy - s * 0.16, rotate(rot * 2, reflow: false,
            rect(width: s, height: s * 0.32, radius: s * 0.1, fill: col)))
        } else if kind == 1 { _dot(cx, cy, s * 0.22, col) }
        else if kind == 2 {
          let pts = ()
          for k in range(7) {
            let u = k / 6
            pts.push((cx + (u - 0.5) * s * calc.cos(rot) - calc.sin(u * 2 * calc.pi) * s * 0.16 * calc.sin(rot),
                      cy + (u - 0.5) * s * calc.sin(rot) + calc.sin(u * 2 * calc.pi) * s * 0.16 * calc.cos(rot)))
          }
          _smooth(pts, closed: false, stroke: _stk(col, s * 0.13))
        } else { _star(cx, cy, s * 0.4, col, n: 3, inner: 0.5, rot: rot * 3, round: 0.2) }
      }
    }
  }
  (body: body, area: none, ink: rgb(R.ink))
}

#let _arrow-head(tip, ang, L, col) = {
  let Q(dx, dy) = (tip.at(0) + dx * calc.cos(ang) - dy * calc.sin(ang), tip.at(1) + dx * calc.sin(ang) + dy * calc.cos(ang))
  _poly((Q(0pt, 0pt), Q(-L, L * 0.55), Q(-L * 0.78, 0pt), Q(-L, -L * 0.55)), fill: col, stroke: _stk(col, L * 0.16))
}

#let _arrow(c) = {
  let (w, h, F, S, sw, p, R) = (c.w, c.h, c.F, c.S, c.sw, c.p, c.R)
  let col = if S != none { S } else { F }
  let L = calc.max(sw * 4.2, calc.min(h * 0.42, w * 0.2))
  let dash = if p.dashed { (sw * 1.6, sw * 2.4) } else { none }
  let both = p.heads == "both"
  let pad = L * 0.62
  let pts = if p.style == "straight" {
    ((pad, h / 2), (w - pad, h / 2))
  } else if p.style == "loop" {
    // alttan gelir, ortada bir tur atıp (kendini keserek) sağa iner
    let (x0, x1) = (pad, w - pad)
    let span = x1 - x0
    let (rx, ry) = (calc.min(span * 0.17, h * 0.3), h * 0.3)
    let out = ((x0, h * 0.84), (x0 + span * 0.22, h * 0.8))
    for i in range(1, 24) {
      let t = i / 24
      let a = 90deg - 360deg * t
      let cx = x0 + span * 0.46 + span * 0.08 * t
      out.push((cx + rx * calc.cos(a), h * 0.46 + ry * calc.sin(a)))
    }
    out + ((x0 + span * 0.78, h * 0.78), (x1, h * 0.6))
  } else {
    let out = ()
    for i in range(25) {
      let t = i / 24
      out.push((pad + (w - 2 * pad) * t, h * 0.78 - (h * 0.62) * calc.sin(t * calc.pi) * (1 - 0.35 * t)))
    }
    out
  }
  let body = {
    if pts.len() == 2 {
      place(top + left, line(start: pts.at(0), end: pts.at(1), stroke: _stk(col, sw, dash: dash)))
    } else { _smooth(pts, closed: false, stroke: _stk(col, sw, dash: dash)) }
    let e = pts.last()
    let e0 = pts.at(pts.len() - 2)
    let ang = calc.atan2((e.at(0) - e0.at(0)) / 1pt, (e.at(1) - e0.at(1)) / 1pt)
    _arrow-head(_add(e, (L * 0.5 * calc.cos(ang), L * 0.5 * calc.sin(ang))), ang, L, col)
    if both {
      let s = pts.at(0)
      let s0 = pts.at(1)
      let bang = calc.atan2((s.at(0) - s0.at(0)) / 1pt, (s.at(1) - s0.at(1)) / 1pt)
      _arrow-head(_add(s, (L * 0.5 * calc.cos(bang), L * 0.5 * calc.sin(bang))), bang, L, col)
    }
  }
  (body: body, area: none, ink: rgb(R.ink))
}

#let _sign(c) = {
  let (w, h, F, S, sw, p, R) = (c.w, c.h, c.F, c.S, c.sw, c.p, c.R)
  let posts = int(p.posts)
  let bh = if posts > 0 { h * 0.66 } else { h }
  let pw = calc.max(w * 0.075, sw * 3)
  let post = if F != none { _mix(F, if S != none { S } else { black }, 0.18) } else { none }
  let tip = if p.point == "none" { 0pt } else { calc.min(bh * 0.45, w * 0.2) }
  let (x0, y0, x1, y1) = (sw / 2, sw / 2, w - sw / 2, bh - sw / 2)
  let body = {
    let xs = if posts == 1 { (w / 2,) } else if posts >= 2 { (w * 0.24, w * 0.76) } else { () }
    for x in xs {
      place(top + left, dx: x - pw / 2, dy: bh * 0.5, rect(width: pw, height: h - bh * 0.5 - sw / 2,
        radius: (top: 0pt, bottom: pw * 0.3), fill: post, stroke: _stk(S, sw)))
    }
    if tip == 0pt {
      place(top + left, dx: x0, dy: y0, rect(width: x1 - x0, height: y1 - y0, radius: calc.min(bh * 0.14, 3mm),
        fill: F, stroke: _stk(S, sw)))
    } else {
      let pts = if p.point == "right" {
        ((x0, y0), (x1 - tip, y0), (x1, bh / 2), (x1 - tip, y1), (x0, y1))
      } else { ((x0 + tip, y0), (x1, y0), (x1, y1), (x0 + tip, y1), (x0, bh / 2)) }
      _poly(pts, fill: F, stroke: _stk(S, sw))
    }
    // ahşap damarı ve çiviler
    if F != none {
      let g = _mix(F, if S != none { S } else { black }, 0.28)
      let lx = if p.point == "left" { tip } else { 0pt }
      let rx = if p.point == "right" { tip } else { 0pt }
      for (u0, u1, v) in ((0.08, 0.3, 0.1), (0.56, 0.84, 0.09), (0.18, 0.46, 0.9), (0.66, 0.9, 0.91)) {   // kenara yakın: yazının altına girmez
        let xa = lx + (w - lx - rx) * u0
        let xb = lx + (w - lx - rx) * u1
        _smooth(((xa, bh * v), ((xa + xb) / 2, bh * (v + 0.03)), (xb, bh * v)), closed: false,
          stroke: _stk(g, sw * 0.55))
      }
      let nx = (lx + w * 0.07, w - rx - w * 0.07)
      for x in nx { _dot(x, bh / 2, sw * 1.05, if S != none { S } else { g }) }
    }
  }
  let lx = if p.point == "left" { tip * 0.8 } else { 0pt }
  let rx = if p.point == "right" { tip * 0.8 } else { 0pt }
  (body: body, area: (lx + w * 0.13, bh * 0.14, w - lx - rx - w * 0.26, bh * 0.72), ink: if S != none { S } else { rgb(R.ink) })
}

#let _note(c) = {
  let (w, h, F, S, sw, p, R) = (c.w, c.h, c.F, c.S, c.sw, c.p, c.R)
  let tp = if p.pin == "tape" { h * 0.07 } else if p.pin == "pin" { h * 0.04 } else { sw / 2 }
  let e = calc.min(w, h) * 0.15
  let (x0, x1, y1) = (sw / 2, w - sw / 2, h - sw / 2)
  let fold = if F != none { _mix(F, if S != none { S } else { black }, 0.2) } else { none }
  let body = {
    _poly(((x0, tp), (x1, tp), (x1, y1 - e), (x1 - e, y1), (x0, y1)), fill: F, stroke: _stk(S, sw))
    if p.lines {
      let lc = _mix(if F != none { F } else { white }, rgb(R.accent2), 0.3)
      let yy = tp + h * 0.3
      while yy < y1 - e * 0.6 {
        place(top + left, line(start: (w * 0.09, yy), end: (w * 0.91 - (if yy > y1 - e { e } else { 0pt }), yy),
          stroke: _stk(lc, sw * 0.6)))
        yy += h * 0.12
      }
    }
    _poly(((x1, y1 - e), (x1 - e, y1), (x1 - e * 0.92, y1 - e * 0.92)), fill: fold, stroke: _stk(S, sw))
    if p.pin == "tape" {
      let tc = rgb(_tone(R.accent2, 0.86, 0.06))
      let (tw, th) = (w * 0.36, h * 0.13)
      let teeth = 4
      let pts = ()
      for i in range(teeth + 1) { pts.push((tw * (if calc.even(i) { 0.0 } else { 0.035 }), th * i / teeth)) }
      let right = ()
      for i in range(teeth + 1) { right.push((tw - tw * (if calc.even(i) { 0.0 } else { 0.035 }), th * (teeth - i) / teeth)) }
      place(top + left, dx: w / 2 - tw / 2, dy: tp - th * 0.55, rotate(-4deg, reflow: false,
        box(width: tw, height: th, polygon(fill: tc, stroke: none, ..pts, ..right))))
    } else if p.pin == "pin" {
      let r = calc.min(w, h) * 0.055
      _dot(w / 2 + r * 0.2, tp + r * 1.3, r, rgb(R.deep))
      _dot(w / 2, tp + r, r, rgb(R.pop), stroke: _stk(rgb(R.deep), sw * 0.6))
      _dot(w / 2 - r * 0.32, tp + r * 0.7, r * 0.28, white)
    }
  }
  let ty = tp + (if p.pin == "none" { h * 0.1 } else { h * 0.13 })
  (body: body, area: (w * 0.11, ty, w * 0.78, y1 - e * 0.7 - ty), ink: rgb(R.ink))
}

#let _envelope(c) = {
  let (w, h, F, S, sw, p, R) = (c.w, c.h, c.F, c.S, c.sw, c.p, c.R)
  let (x0, y0, x1, y1) = (sw / 2, sw / 2, w - sw / 2, h - sw / 2)
  let shade = if F != none { _mix(F, if S != none { S } else { black }, 0.14) } else { none }
  let seal = rgb(R.rose)
  let m = calc.min(w, h)
  let body = {}
  let area = none
  if p.open {
    let E = h * 0.46
    let apex = (w / 2, E + (y1 - E) * 0.42)
    body = {
      _poly(((x0, E), (w / 2, y0), (x1, E)), fill: shade, stroke: _stk(S, sw))
      place(top + left, dx: w * 0.1, dy: h * 0.07, rect(width: w * 0.8, height: h * 0.8, fill: white,
        stroke: _stk(S, sw * 0.6)))
      _poly(((x0, E), apex, (x1, E), (x1, y1), (x0, y1)), fill: F, stroke: _stk(S, sw))
      place(top + left, line(start: (x0, y1), end: (w * 0.4, E + (y1 - E) * 0.55), stroke: _stk(shade, sw * 0.8)))
      place(top + left, line(start: (x1, y1), end: (w * 0.6, E + (y1 - E) * 0.55), stroke: _stk(shade, sw * 0.8)))
      if p.seal == "heart" { _heart(apex.at(0), apex.at(1), m * 0.2, seal) }
      else if p.seal == "circle" { _dot(apex.at(0), apex.at(1), m * 0.085, seal, stroke: _stk(rgb(R.deep), sw * 0.6)) }
    }
    area = (w * 0.16, h * 0.13, w * 0.68, E - h * 0.15)
  } else {
    body = {
      place(top + left, dx: x0, dy: y0, rect(width: x1 - x0, height: y1 - y0, radius: m * 0.03, fill: F, stroke: _stk(S, sw)))
      // pul: kesik kenarlı kare, içinde kalp
      let (sx, sy, ss) = (w - m * 0.3, m * 0.08, m * 0.22)
      place(top + left, dx: sx, dy: sy, rect(width: ss, height: ss * 1.15, fill: rgb(R.soft2),
        stroke: _stk(rgb(R.pop2), sw * 0.8, dash: (sw * 0.3, sw * 1.2))))
      _heart(sx + ss / 2, sy + ss * 0.6, ss * 0.5, seal)
      // damga: iki halka, dalgalı çizgiler
      let (dx, dy) = (w - m * 0.52, m * 0.2)
      place(top + left, dx: dx - m * 0.1, dy: dy - m * 0.1, circle(radius: m * 0.1, stroke: _stk(shade, sw * 0.6)))
      for k in range(3) {
        let yy = dy - m * 0.05 + k * m * 0.05
        _smooth(((dx - m * 0.24, yy), (dx - m * 0.19, yy - m * 0.015), (dx - m * 0.14, yy)), closed: false,
          stroke: _stk(shade, sw * 0.5))
      }
      if p.seal == "heart" { _heart(m * 0.14, m * 0.14, m * 0.12, seal) }
      else if p.seal == "circle" { _dot(m * 0.14, m * 0.14, m * 0.05, seal) }
    }
    area = (w * 0.18, h * 0.46, w * 0.64, h * 0.42)
  }
  (body: body, area: area, ink: rgb(R.ink))
}

#let _scroll(c) = {
  let (w, h, F, S, sw, p, R) = (c.w, c.h, c.F, c.S, c.sw, c.p, c.R)
  let horiz = p.orient == "horizontal"
  // dikey tasarlanır; yatayda eksenler yer değiştirir
  let (W, H) = if horiz { (h, w) } else { (w, h) }
  let T(x, y) = if horiz { (y, x) } else { (x, y) }
  let rh = calc.min(H * 0.12, W * 0.2)
  let roll = if F != none { _mix(F, if S != none { S } else { black }, 0.16) } else { none }
  let bow = W * 0.035
  let (sx0, sx1, sy0, sy1) = (W * 0.1, W * 0.9, rh / 2, H - rh / 2)
  let body = {
    let seg = (curve.move(T(sx0, sy0)), curve.line(T(sx1, sy0)),
      curve.cubic(T(sx1 - bow, sy0 + (sy1 - sy0) * 0.33), T(sx1 - bow, sy0 + (sy1 - sy0) * 0.66), T(sx1, sy1)),
      curve.line(T(sx0, sy1)),
      curve.cubic(T(sx0 + bow, sy0 + (sy1 - sy0) * 0.66), T(sx0 + bow, sy0 + (sy1 - sy0) * 0.33), T(sx0, sy0)),
      curve.close(mode: "straight"))
    place(top + left, curve(fill: F, stroke: _stk(S, sw), ..seg))
    for ry in (0pt, H - rh) {
      let (rx, ryy) = T(W * 0.04, ry)
      let (rw, rhh) = if horiz { (rh, W * 0.92) } else { (W * 0.92, rh) }
      place(top + left, dx: rx, dy: ryy, rect(width: rw, height: rhh, radius: rh / 2, fill: roll, stroke: _stk(S, sw)))
      for ex in (W * 0.04 + rh / 2, W * 0.96 - rh / 2) {
        let (cx, cy) = T(ex, ry + rh / 2)
        _dot(cx, cy, rh * 0.3, F, stroke: _stk(S, sw * 0.7))
        _dot(cx, cy, rh * 0.1, S)
      }
      let (ax, ay) = T(W * 0.04 + rh, ry + rh * 0.32)
      let (bx, by) = T(W * 0.96 - rh, ry + rh * 0.32)
      place(top + left, line(start: (ax, ay), end: (bx, by), stroke: _stk(F, sw * 0.7)))
    }
  }
  let (ax, ay) = T(W * 0.17, rh + H * 0.05)
  let (aw, ah) = if horiz { (H - 2 * rh - H * 0.1, W * 0.66) } else { (W * 0.66, H - 2 * rh - H * 0.1) }
  (body: body, area: (ax, ay, aw, ah), ink: if S != none { S } else { rgb(R.ink) })
}

#let _badge(c) = {
  let (w, h, F, S, sw, p, R) = (c.w, c.h, c.F, c.S, c.sw, c.p, c.R)
  let tails = p.tails
  let D = if tails { calc.min(w, h / 1.25) } else { calc.min(w, h) }
  let cx = w / 2
  let cy = (h - (if tails { D * 1.25 } else { D })) / 2 + D / 2
  let tc = rgb(R.pop2)
  let tdark = _mix(tc, black, 0.25)
  let fill = if F != none { F } else { rgb(R.accent) }
  let body = {
    if tails {
      for sx in (-1, 1) {
        let a = (cx + sx * D * 0.05, cy)
        let b = (cx + sx * D * 0.3, cy)
        let e = cy + D * 0.72
        _poly((a, b, (cx + sx * D * 0.4, e), (cx + sx * D * 0.27, e - D * 0.08), (cx + sx * D * 0.15, e)),
          fill: if sx < 0 { tc } else { tdark }, stroke: none)
      }
    }
    if p.style == "rosette" {
      _bumps(cx, cy, D * 0.42, D * 0.42, 16, 0.42, fill, _stk(S, sw))
      _dot(cx, cy, D * 0.33, white, stroke: _stk(S, sw))
      place(top + left, dx: cx - D * 0.37, dy: cy - D * 0.37, circle(radius: D * 0.37,
        stroke: _stk(white, sw * 0.7, dash: (sw * 1.2, sw * 1.4))))
    } else if p.style == "star" {
      _star(cx, cy, D * 0.5, fill, stroke: _stk(if S != none { S } else { fill }, D * 0.06), inner: 0.6)
    } else {
      _dot(cx, cy, D / 2 - sw / 2, fill, stroke: _stk(S, sw))
      place(top + left, dx: cx - D * 0.4, dy: cy - D * 0.4, circle(radius: D * 0.4,
        stroke: _stk(white, sw * 0.8, dash: (sw * 1.3, sw * 1.5))))
    }
  }
  let a = if p.style == "rosette" { D * 0.44 } else if p.style == "star" { D * 0.4 } else { D * 0.56 }
  let ink = if p.style == "rosette" { fill } else if _dark(fill) { white } else { rgb(R.ink) }
  (body: body, area: (cx - a / 2, cy - a / 2 + (if p.style == "star" { D * 0.04 } else { 0pt }), a, a), ink: ink)
}

// Şerit: kavis (curve) verilirse bant ve yazısı birlikte bükülür.
#let _ribbon-geo(w, h, curve-k) = {
  let sag = calc.abs(curve-k) * h * 0.28
  let (L, Rr) = (w * 0.13, w * 0.87)
  let bt = h * 0.08 + (if curve-k > 0 { sag } else { 0pt })
  let bb = bt + h * 0.56
  let bend(x) = {
    let u = (x - L) / (Rr - L) * 2 - 1
    sag * (1 - u * u) * (if curve-k > 0 { -1 } else { 1 })
  }
  (L: L, R: Rr, top: bt, bot: bb, drop: h * 0.2, bend: bend, sag: sag)
}

#let _ribbon(c) = {
  let (w, h, F, S, sw, p, R) = (c.w, c.h, c.F, c.S, c.sw, c.p, c.R)
  let g = _ribbon-geo(w, h, p.curve)
  let fill = if F != none { F } else { rgb(R.accent) }
  let tail = fill.darken(22%)
  let fold = fill.darken(45%)
  let body = {
    let d = g.drop
    let notch = w * 0.06
    let fw = w * 0.07
    // uçlar (arkada)
    _poly(((sw / 2, g.top + d), (g.L + fw, g.top + d), (g.L + fw, g.bot + d), (sw / 2, g.bot + d),
           (sw / 2 + notch, (g.top + g.bot) / 2 + d)), fill: tail, stroke: _stk(S, sw))
    _poly(((w - sw / 2, g.top + d), (g.R - fw, g.top + d), (g.R - fw, g.bot + d), (w - sw / 2, g.bot + d),
           (w - sw / 2 - notch, (g.top + g.bot) / 2 + d)), fill: tail, stroke: _stk(S, sw))
    _poly(((g.L, g.bot), (g.L + fw, g.bot + d), (g.L + fw, g.bot)), fill: fold, stroke: _stk(S, sw))
    _poly(((g.R, g.bot), (g.R - fw, g.bot + d), (g.R - fw, g.bot)), fill: fold, stroke: _stk(S, sw))
    // bant
    let n = 32
    let topp = ()
    let botp = ()
    for i in range(n + 1) {
      let x = g.L + (g.R - g.L) * i / n
      topp.push((x, g.top + (g.bend)(x)))
      botp.push((x, g.bot + (g.bend)(x)))
    }
    _poly(topp + botp.rev(), fill: fill, stroke: _stk(S, sw))
    // ince iç çizgi (dikiş)
    let stitch = _mix(fill, white, 0.55)
    let up = ()
    let dn = ()
    for i in range(n + 1) {
      let x = g.L + (g.R - g.L) * (0.02 + 0.96 * i / n)
      up.push((x, g.top + h * 0.05 + (g.bend)(x)))
      dn.push((x, g.bot - h * 0.05 + (g.bend)(x)))
    }
    place(top + left, curve(stroke: _stk(stitch, sw * 0.5, dash: (sw * 1.2, sw * 1.2)), curve.move(up.first()), ..up.slice(1).map(q => curve.line(q))))
    place(top + left, curve(stroke: _stk(stitch, sw * 0.5, dash: (sw * 1.2, sw * 1.2)), curve.move(dn.first()), ..dn.slice(1).map(q => curve.line(q))))
  }
  let ink = if _dark(fill) { white } else { rgb(R.ink) }
  (body: body, area: (g.L + w * 0.05, g.top + h * 0.1, g.R - g.L - w * 0.1, g.bot - g.top - h * 0.2), ink: ink,
   path: if calc.abs(p.curve) > 0.01 { g } else { none })
}

#let _star-shape(c) = {
  let (w, h, F, S, sw, p, R) = (c.w, c.h, c.F, c.S, c.sw, c.p, c.R)
  let n = calc.max(3, int(p.points))
  let r = calc.min(w, h) / 2
  let cy = h / 2 + r * 0.06
  let body = _star(w / 2, cy, r - sw, F, stroke: if S != none { _stk(S, sw) } else { none }, n: n, inner: p.inner,
    round: if p.rounded { 0.14 } else { 0.0 })
  let a = r * p.inner * 1.15
  (body: body, area: (w / 2 - a / 2, cy - a / 2, a, a), ink: if _dark(F) { white } else { rgb(R.ink) })
}

#let _heart-shape(c) = {
  let (w, h, F, S, sw, p, R) = (c.w, c.h, c.F, c.S, c.sw, c.p, c.R)
  let s = calc.min(w - sw, (h - sw) / 0.94)
  let body = _heart(w / 2, h / 2 + s * 0.0, s, F, stroke: _stk(S, sw))
  (body: body, area: (w / 2 - s * 0.3, h / 2 - s * 0.26, s * 0.6, s * 0.38), ink: if _dark(F) { white } else { rgb(R.ink) })
}

#let _cloud(c) = {
  let (w, h, F, S, sw, p, R) = (c.w, c.h, c.F, c.S, c.sw, c.p, c.R)
  let n = calc.max(5, int(p.puffs))
  let body = _bumps(w / 2, h * 0.53, w * 0.36, h * 0.3, n, 0.62, F, _stk(S, sw),
    sizes: (1.0, 0.8, 1.15, 0.9, 1.05, 0.75), rot: 12deg)
  (body: body, area: (w * 0.18, h * 0.3, w * 0.64, h * 0.46), ink: if _dark(F) { white } else { rgb(R.ink) })
}

#let _burst(c) = {
  let (w, h, F, S, sw, p, R) = (c.w, c.h, c.F, c.S, c.sw, c.p, c.R)
  let n = calc.max(5, int(p.spikes))
  let body = {
    _poly(_burst-pts(w / 2, h / 2, w / 2 - sw, h / 2 - sw, n, 0.7, int(p.seed)), fill: F,
      stroke: _stk(S, sw, join: "miter"))
    if p.inner {
      _poly(_burst-pts(w / 2, h / 2, w * 0.36, h * 0.36, n, 0.76, int(p.seed) + 1, rot: 180deg / n),
        fill: rgb(R.rose), stroke: none)
    }
  }
  let ink = if p.inner { white } else if _dark(F) { white } else { rgb(R.ink) }
  (body: body, area: (w * 0.24, h * 0.3, w * 0.52, h * 0.4), ink: ink)
}

#let _line(c) = {
  let (w, h, F, S, sw, p, R) = (c.w, c.h, c.F, c.S, c.sw, c.p, c.R)
  let col = if S != none { S } else { F }
  let ends = p.ends
  let es = if ends == "none" { 0pt } else { calc.min(h * 0.9, calc.max(sw * 4, 3mm)) }
  let (x0, x1) = (sw + es, w - sw - es)
  let y = h / 2
  let a = calc.max(0pt, calc.min(h / 2 - sw, h * 0.36))
  let len = x1 - x0
  let waves = if p.waves > 0 { int(p.waves) } else { calc.max(1, int(calc.round(len / (h * 1.3)))) }
  let body = {
    if p.style == "straight" or p.style == "dashed" {
      place(top + left, line(start: (x0, y), end: (x1, y),
        stroke: _stk(col, sw, dash: if p.style == "dashed" { (sw * 2.4, sw * 2.2) } else { none })))
    } else if p.style == "dotted" {
      let n = calc.max(2, int(calc.round(len / (sw * 3))))
      for i in range(n + 1) { _dot(x0 + len * i / n, y, sw * 0.75, col) }
    } else if p.style == "zigzag" {
      let pts = ()
      for i in range(2 * waves + 1) { pts.push((x0 + len * i / (2 * waves), y + (if calc.even(i) { a } else { -a }))) }
      place(top + left, curve(stroke: _stk(col, sw), curve.move(pts.first()), ..pts.slice(1).map(q => curve.line(q))))
    } else if p.style == "loops" {
      let pts = ()
      // uzamış sikloid: her turda üstte bir halka (el yazısı «llll»)
      let waves = if p.waves > 0 { waves } else { calc.max(1, int(calc.round(len / (h * 1.5)))) }
      let k = waves * 32
      for i in range(k + 1) {
        let t = calc.pi + i / k * waves * 2 * calc.pi       // alttan başlar, alta biter; halkalar arada
        let u = (t - 2.4 * calc.sin(t) - calc.pi) / (waves * 2 * calc.pi)
        pts.push((x0 + len * u, y - a * 0.9 * calc.cos(t) + a * 0.1))
      }
      _smooth(pts, closed: false, stroke: _stk(col, sw))
    } else {                                           // dalga
      let pts = ()
      let k = waves * 8
      for i in range(k + 1) { pts.push((x0 + len * i / k, y - a * calc.sin(i / 8 * 2 * calc.pi))) }
      _smooth(pts, closed: false, stroke: _stk(col, sw))
    }
    if ends != "none" {
      let ec = rgb(R.pop)
      for x in (es / 2 + sw / 2, w - es / 2 - sw / 2) {
        if ends == "star" { _star(x, y, es / 2, ec) }
        else if ends == "heart" { _heart(x, y, es, ec) }
        else { _dot(x, y, es * 0.32, ec) }
      }
    }
  }
  (body: body, area: none, ink: rgb(R.ink))
}

#let SHAPES = (frame: _frame, corner: _corner, scatter: _scatter, arrow: _arrow, sign: _sign, note: _note,
  envelope: _envelope, scroll: _scroll, badge: _badge, ribbon: _ribbon, star: _star-shape, heart: _heart-shape,
  cloud: _cloud, burst: _burst, line: _line)

// Varsayılanlar (elements.py CATALOG ile aynı; test sınar). Renkler rol adı; stroke_w mm.
#let SHAPE-DEFAULTS = (
  frame: (fill: "none", stroke: "accent", stroke_w: 1.2, params: (style: "plain", radius: 4, ornament: "none")),
  corner: (fill: "pop2", stroke: "accent", stroke_w: 0.9, params: (corner: "tl", style: "swirl")),
  scatter: (fill: none, stroke: "none", stroke_w: 0, params: (item: "star", count: 14, seed: 7, size: 7)),
  arrow: (fill: "none", stroke: "accent", stroke_w: 1.6, params: (style: "curved", heads: "end", dashed: false)),
  sign: (fill: "wood", stroke: "bark", stroke_w: 0.7, params: (posts: 1, point: "none")),
  note: (fill: "paper", stroke: "wood", stroke_w: 0.4, params: (pin: "tape", lines: false)),
  envelope: (fill: "wood", stroke: "bark", stroke_w: 0.5, params: (open: true, seal: "heart")),
  scroll: (fill: "paper", stroke: "bark", stroke_w: 0.6, params: (orient: "vertical")),
  badge: (fill: "accent", stroke: "none", stroke_w: 0.6, params: (style: "rosette", tails: true)),
  ribbon: (fill: "accent", stroke: "none", stroke_w: 0.5, params: (curve: 0)),
  star: (fill: "sun", stroke: "none", stroke_w: 0.6, params: (points: 5, inner: 0.5, rounded: true)),
  heart: (fill: "rose", stroke: "none", stroke_w: 0.6, params: (:)),
  cloud: (fill: "white", stroke: "pop2", stroke_w: 0.7, params: (puffs: 9)),
  burst: (fill: "sun", stroke: "ink", stroke_w: 0.7, params: (spikes: 12, seed: 3, inner: true)),
  line: (fill: "none", stroke: "accent", stroke_w: 1.0, params: (style: "wave", waves: 0, ends: "none")),
)

// mirror: true → şeklin çizimi yatayda aynalanır, üstündeki yazı aynalanmaz (çağıran s.flip'i buraya verir, kutuyu
// kendisi aynalamaz; yoksa yazı ters okunur).
#let draw-shape(s, palette, fonts, mirror: false) = {
  let R = roles(palette)
  let kind = _get(s, "kind", "star")
  let D = SHAPE-DEFAULTS.at(kind, default: SHAPE-DEFAULTS.star)
  let p = D.params + _get(s, "params", (:))
  let bx = _get(s, "box", (w: 40, h: 40))
  let (w, h) = (bx.w * 1mm, bx.h * 1mm)
  let op = _get(s, "opacity", 1)
  let F = _alpha(_col(s.at("fill", default: none), R, D.fill), op)
  let S = _alpha(_col(s.at("stroke", default: none), R, D.stroke), op)
  let sw = _get(s, "stroke_w", D.stroke_w) * 1mm
  let c = (w: w, h: h, F: F, S: S, sw: sw, p: p, R: R, fonts: fonts)
  let out = SHAPES.at(kind, default: _star-shape)(c)
  let runs = _runs(s, R).map(r => if r.at("color", default: none) != none { r + (color: _alpha(r.color, op)) } else { r })
  box(width: w, height: h, {
    if mirror { place(top + left, scale(x: -100%, reflow: false, box(width: w, height: h, out.body))) }
    else { out.body }
    if out.area != none and runs.len() > 0 {
      let ink = _alpha(out.ink, op)
      let size = _get(s, "text_size", none)
      let path = out.at("path", default: none)
      if path == none {
        let (ax, ay, aw, ah) = out.area
        let area = if mirror { (w - ax - aw, ay, aw, ah) } else { out.area }
        _text-in(runs, area, size, fonts, ink, center, _get(s, "id", ""))
      } else {
        // kavisli şerit: harfler bandın orta çizgisi üzerinde
        context {
          let (ax, ay, aw, ah) = out.area
          let mid = (path.top + path.bot) / 2
          let base = if size != none { size } else { 20 }
          let letters = ()
          let total = 0pt
          for r in runs {
            let st = _style(r, base, 1, fonts)
            for ch in r.text.replace("\n", " ").clusters() {
              let wd = measure(text(..st, ch)).width
              letters.push((ch: ch, st: st, w: wd, fill: if _get(r, "color", none) != none { r.color } else { ink }))
              total += wd
            }
          }
          let k = if size != none { 1.0 } else { calc.min(aw / total, (path.bot - path.top) * 0.5 / (0.72 * base * 1pt)) }
          if size != none and total > aw { metadata((kind: "element-overflow", id: _get(s, "id", ""))) }
          let x = w / 2 - total * k / 2
          for l in letters {
            let cx = x + l.w * k / 2
            let eps = 0.5mm
            let dy = ((path.bend)(cx + eps) - (path.bend)(cx - eps)) / (2 * eps)
            let ang = calc.atan2(1.0, dy)
            let by = mid + (path.bend)(cx) + 0.36 * base * k * 1pt
            place(top + left, dx: cx, dy: by, rotate(ang, origin: top + left, reflow: false,
              box(width: 0pt, height: 0pt, place(top + left, dx: -l.w * k / 2,
                text(..(l.st + (size: l.st.size * k)), fill: l.fill, top-edge: "baseline", bottom-edge: "baseline", l.ch)))))
            x += l.w * k
          }
        }
      }
    }
  })
}

// ================================================================ efekt yazı
#let EFFECT-DEFAULTS = (
  burst: (burst_fill: "sun", burst_stroke: "ink", angle: -8, outline: "white", outline_w: 0.7, spikes: 12, seed: 3),
  wave: (curve: 0.5, waves: 1.5, outline: "white", outline_w: 0.6),
  arc: (curve: 0.6, outline: "white", outline_w: 0.6),
  shadow: (shadow: "sun", shadow_dx: 0.8, shadow_dy: 0.8),
  outline: (outline: "white", outline_w: 0.8, shadow: "deep", shadow_dx: 0, shadow_dy: 0),
  stacked: (shadow: "pop2", depth: 0.09, outline: "white", outline_w: 0.6),
  bounce: (colors: none, outline: "white", outline_w: 0.5),
  rainbow: (colors: none, outline: none, outline_w: 0.6),
)

// Harf harf yerleşim için yol (birim uzayda çoklu çizgi, float çiftleri).
#let _path-units(style, k, waves) = {
  let n = 180
  let pts = ()
  if style == "arc" and calc.abs(k) > 0.01 {
    let th = calc.min(calc.abs(k), 1.0) * calc.pi
    for i in range(n + 1) {
      let f = -th / 2 + th * i / n
      pts.push(if k > 0 { (calc.sin(f), -calc.cos(f)) } else { (calc.sin(f), calc.cos(f)) })
    }
  } else if style == "wave" and calc.abs(k) > 0.01 {
    for i in range(n + 1) {
      let x = 2 * calc.pi * waves * i / n
      pts.push((x, -k * 0.9 * calc.sin(x)))
    }
  } else {
    for i in range(n + 1) { pts.push((i / n, 0.0)) }
  }
  pts
}

// Harfleri yola dizer: [(x, y, açı, harf)], x/y pt (float). Harf taban çizgisi yolun üstünde, ortası yol noktasında.
#let _along(letters, pts) = {
  let cum = (0.0,)
  for i in range(1, pts.len()) {
    let (a, b) = (pts.at(i - 1), pts.at(i))
    cum.push(cum.last() + calc.sqrt(calc.pow(b.at(0) - a.at(0), 2) + calc.pow(b.at(1) - a.at(1), 2)))
  }
  let total = letters.map(l => l.w / 1pt).sum(default: 0.0)
  let m = if cum.last() > 0 { total / cum.last() } else { 1.0 }
  let out = ()
  let s = 0.0
  let j = 0
  for l in letters {
    let c = (s + l.w / 1pt / 2) / m
    while j < cum.len() - 2 and cum.at(j + 1) < c { j += 1 }
    let seg = cum.at(j + 1) - cum.at(j)
    let f = if seg > 0 { calc.min(1.0, calc.max(0.0, (c - cum.at(j)) / seg)) } else { 0.0 }
    let (a, b) = (pts.at(j), pts.at(j + 1))
    let x = (a.at(0) + (b.at(0) - a.at(0)) * f) * m
    let y = (a.at(1) + (b.at(1) - a.at(1)) * f) * m
    let ang = calc.atan2(b.at(0) - a.at(0), b.at(1) - a.at(1))
    out.push((x: x, y: y, a: ang, l: l))
    s += l.w / 1pt
  }
  out
}

#let effect-text(t, palette, fonts) = {
  let R = roles(palette)
  let e = _get(t, "effect", (style: "shadow"))
  let style = _get(e, "style", "shadow")
  let D = EFFECT-DEFAULTS.at(style, default: EFFECT-DEFAULTS.shadow)
  let p = D + _get(e, "params", (:))
  let bx = _get(t, "box", (w: 80, h: 30))
  let (W, H) = (bx.w * 1mm, bx.h * 1mm)
  let runs = _runs(t, R)
  let size = _get(t, "size", none)
  let id = _get(t, "id", "")
  let ink = rgb(R.accent)
  let ol = _col(p.at("outline", default: none), R, none)
  let olw = if ol == none { 0pt } else { _get(p, "outline_w", 0.6) * 1mm }
  let sh = _col(p.at("shadow", default: none), R, none)
  let (sdx, sdy) = (_get(p, "shadow_dx", 0) * 1mm, _get(p, "shadow_dy", 0) * 1mm)
  let colors = if style in ("rainbow", "bounce") {
    let cs = _get(p, "colors", none)
    if cs == none or cs.len() == 0 { R.letters.map(rgb) } else { cs.map(x => _col(x, R, "accent")) }
  } else { none }
  let angle = _get(p, "angle", 0) * 1deg
  box(width: W, height: H, if runs.len() > 0 {
    if style == "burst" {
      let bf = _col(p.burst_fill, R, "sun")
      let bs = _col(p.burst_stroke, R, "ink")
      _poly(_burst-pts(W / 2, H / 2, W / 2 - 0.4mm, H / 2 - 0.4mm, calc.max(5, int(p.spikes)), 0.72, int(p.seed)),
        fill: bf, stroke: _stk(bs, 0.7mm, join: "miter"))
    }
    if style in ("arc", "wave") {
      context {
        let base = if size != none { size } else { 20 }
        let letters = ()
        for r in runs {
          let st = _style(r, base, 1, fonts)
          for ch in r.text.replace("\n", " ").clusters() {
            letters.push((ch: ch, st: st, w: measure(text(..st, ch)).width,
              asc: measure(text(..st, top-edge: "bounds", bottom-edge: "baseline", ch)).height,
              desc: measure(text(..st, top-edge: "baseline", bottom-edge: "bounds", ch)).height,
              fill: if _get(r, "color", none) != none { r.color } else { ink }))
          }
        }
        let placed = _along(letters, _path-units(style, _get(p, "curve", 0), _get(p, "waves", 1.5)))
        // sınır kutusu (döndürülmüş harf dikdörtgenlerinin köşeleri)
        let (x0, y0, x1, y1) = (1e9, 1e9, -1e9, -1e9)
        for q in placed {
          let (hw, a) = (q.l.w / 1pt / 2, q.l.asc / 1pt)
          let d = q.l.desc / 1pt
          for (cx, cy) in ((-hw, -a), (hw, -a), (hw, d), (-hw, d)) {
            let x = q.x + cx * calc.cos(q.a) - cy * calc.sin(q.a)
            let y = q.y + cx * calc.sin(q.a) + cy * calc.cos(q.a)
            x0 = calc.min(x0, x); x1 = calc.max(x1, x); y0 = calc.min(y0, y); y1 = calc.max(y1, y)
          }
        }
        let pad = olw / 1pt * 2
        let (aw, ah) = (W / 1pt - pad - calc.abs(sdx / 1pt), H / 1pt - pad - calc.abs(sdy / 1pt))
        let fitk = calc.min(aw / calc.max(x1 - x0, 0.01), ah / calc.max(y1 - y0, 0.01))
        let k = if size != none { 1.0 } else { fitk }
        if size != none and fitk < 0.999 { metadata((kind: "element-overflow", id: id)) }
        let ox = (W / 1pt - (x1 - x0) * k) / 2 - x0 * k - sdx / 1pt / 2
        let oy = (H / 1pt - (y1 - y0) * k) / 2 - y0 * k - sdy / 1pt / 2
        let draw(dx, dy, paint, stroke) = {
          for q in placed {
            let f = if paint != none { paint } else { q.l.fill }
            place(top + left, dx: (ox + q.x * k) * 1pt + dx, dy: (oy + q.y * k) * 1pt + dy,
              rotate(q.a, origin: top + left, reflow: false, box(width: 0pt, height: 0pt,
                place(top + left, dx: -q.l.w * k / 2, text(..(q.l.st + (size: q.l.st.size * k)), fill: f, stroke: stroke,
                  top-edge: "baseline", bottom-edge: "baseline", q.l.ch)))))
          }
        }
        if sh != none and (sdx != 0pt or sdy != 0pt) { pdf.artifact(draw(sdx, sdy, sh, if ol != none { _stk(sh, olw * 2) } else { none })) }
        if ol != none { pdf.artifact(draw(0pt, 0pt, ol, _stk(ol, olw * 2))) }
        draw(0pt, 0pt, none, none)
      }
    } else {
      // paragraf düzeni: katmanlar aynı dizgiyle üst üste
      let (ax, ay, aw, ah) = if style == "burst" { (W * 0.2, H * 0.28, W * 0.6, H * 0.44) } else { (0pt, 0pt, W, H) }
      let depth = if style == "stacked" { _get(p, "depth", 0.09) } else { 0 }
      let dcol = if style == "stacked" { if sh != none { sh } else { rgb(R.deep) } } else { none }
      let m = olw * 1.2
      let area = (ax + m, ay + m, aw - 2 * m - calc.abs(sdx), ah - 2 * m - calc.abs(sdy))
      let layers-for(big) = {
        let ls = ()
        if style == "stacked" {
          let steps = 7
          for i in range(steps, 0, step: -1) {
            let o = big * depth * i / steps
            ls.push((o, o, dcol, none, if ol != none { _stk(dcol, olw * 2) } else { none }))
          }
        }
        if sh != none and (sdx != 0pt or sdy != 0pt) { ls.push((sdx, sdy, sh, none, if ol != none { _stk(sh, olw * 2) } else { none })) }
        if ol != none { ls.push((0pt, 0pt, ol, none, _stk(ol, olw * 2))) }
        ls.push((0pt, 0pt, none, colors, none))
        ls
      }
      let body = {
        if style == "stacked" {
          // derinlik payı: yazı sol üste kayar, katmanlar sağ alta iner (tek satırda derinlik ≈ yükseklik × depth)
          let (x, y, w2, h2) = area
          let d = h2 * depth * 0.8
          _text-in(runs, (x, y, w2 - d, h2 - d), size, fonts, ink, _align(_get(t, "align", "center")), id,
            layers: layers-for, bounce: false, colors: colors)
        } else {
          _text-in(runs, area, size, fonts, ink, _align(_get(t, "align", "center")), id, layers: layers-for,
            bounce: style == "bounce", colors: colors)
        }
      }
      if angle != 0deg { place(top + left, rotate(angle, origin: center + horizon, reflow: false, box(width: W, height: H, body))) }
      else { body }
    }
  })
}
