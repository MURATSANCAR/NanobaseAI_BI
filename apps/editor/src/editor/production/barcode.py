"""ISBN-13 → EAN-13 barkod (SVG). Kontrol hanesi doğrulanır; yanlış ISBN barkoda dönüşmez.

Ölçü: nominal (%100) modül 0,33 mm, çubuk yüksekliği 22,85 mm; kapakta %80–%100 arası basılır.
"""

from __future__ import annotations

L = ["0001101", "0011001", "0010011", "0111101", "0100011", "0110001", "0101111", "0111011", "0110111", "0001011"]
G = ["0100111", "0110011", "0011011", "0100001", "0011101", "0111001", "0000101", "0010001", "0001001", "0010111"]
R = ["1110010", "1100110", "1101100", "1000010", "1011100", "1001110", "1010000", "1000100", "1001000", "1110100"]
PARITY = ["LLLLLL", "LLGLGG", "LLGGLG", "LLGGGL", "LGLLGG", "LGGLLG", "LGGGLL", "LGLGLG", "LGLGGL", "LGGLGL"]


def digits(isbn: str) -> str:
    d = "".join(c for c in isbn if c.isdigit())
    if len(d) != 13:
        raise ValueError(f"ISBN-13 değil: {isbn!r}")
    check = (10 - sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(d[:12])) % 10) % 10
    if check != int(d[12]):
        raise ValueError(f"ISBN kontrol hanesi yanlış: {isbn!r} (olması gereken {check})")
    return d


def modules(code: str) -> str:
    first, left, right = int(code[0]), code[1:7], code[7:]
    bits = "101"
    for c, p in zip(left, PARITY[first]):
        bits += (L if p == "L" else G)[int(c)]
    bits += "01010"
    for c in right:
        bits += R[int(c)]
    return bits + "101"


def svg(isbn: str, module_mm: float = 0.33, height_mm: float = 22.85, font: str = "Andika") -> str:
    code = digits(isbn)
    bits = modules(code)
    quiet = 11 * module_mm
    w = quiet * 2 + len(bits) * module_mm
    text_h = 3.2
    h = height_mm + text_h + 5.5
    guard = {0, 1, 2, 45, 46, 47, 48, 49, 92, 93, 94}
    rects = []
    for i, b in enumerate(bits):
        if b == "1":
            bh = height_mm + (1.6 if i in guard else 0)
            rects.append(f'<rect x="{quiet + i * module_mm:.3f}" y="4.5" width="{module_mm:.3f}" height="{bh:.3f}"/>')
    y = 4.5 + height_mm + text_h
    fs = 3.0
    num = (f'<text x="{quiet - 1.2:.2f}" y="{y:.2f}" font-size="{fs}" text-anchor="end">{code[0]}</text>'
           f'<text x="{quiet + 24 * module_mm:.2f}" y="{y:.2f}" font-size="{fs}" text-anchor="middle" letter-spacing="0.6">{code[1:7]}</text>'
           f'<text x="{quiet + 71 * module_mm:.2f}" y="{y:.2f}" font-size="{fs}" text-anchor="middle" letter-spacing="0.6">{code[7:]}</text>')
    label = f'<text x="{w / 2:.2f}" y="3.2" font-size="2.6" text-anchor="middle">ISBN {isbn}</text>'
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{w:.2f}mm" height="{h:.2f}mm" viewBox="0 0 {w:.3f} {h:.3f}">'
            f'<rect width="100%" height="100%" fill="#fff"/><g fill="#000" font-family="{font}">{label}{"".join(rects)}{num}</g></svg>')
