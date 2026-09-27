"""NanobaseAI simgesini PNG olarak çizer ve üst kaynağın marka görsellerinin yerine koyar.

İmaj derlenirken (builder aşaması, `bench build`ten önce) koşar:
    ./env/bin/python apps/nanobase_brand/nanobase_brand/simge.py apps
Simge marka/logo-mark.svg ile aynı geometri: coral→mor degrade, köşe 28/118, beyaz N.
Sunucuda SVG işleyici yok; şekil basit olduğu için Pillow ile çizilir (4× örnekleyip küçültülür).
"""

import re
import shutil
import sys
from pathlib import Path

from PIL import Image, ImageDraw

CORAL = (0xFF, 0x6B, 0x4A)
VIOLET = (0x7C, 0x5C, 0xFF)
# logo-mark.svg'deki N yolu (118×118 kutuda)
N_POINTS = [(34, 88), (34, 30), (46, 30), (72, 67), (72, 30), (84, 30), (84, 88), (72, 88), (46, 51), (46, 88)]
BOX = 118
RADIUS = 28


def mark(size: int, *, rounded: bool = True) -> Image.Image:
	s = size * 4
	# Degrade sol alttan sağ üste (SVG: x1=0 y1=1 → x2=1 y2=0)
	grad = Image.new("RGB", (s, s))
	px = grad.load()
	for y in range(s):
		for x in range(s):
			t = (x + (s - 1 - y)) / (2 * (s - 1))
			px[x, y] = tuple(round(c0 + (c1 - c0) * t) for c0, c1 in zip(CORAL, VIOLET))
	img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
	mask = Image.new("L", (s, s), 0)
	r = RADIUS * s / BOX if rounded else 0
	ImageDraw.Draw(mask).rounded_rectangle((0, 0, s - 1, s - 1), radius=r, fill=255)
	img.paste(grad, (0, 0), mask)
	k = s / BOX
	ImageDraw.Draw(img).polygon([(x * k, y * k) for x, y in N_POINTS], fill=(255, 255, 255, 255))
	return img.resize((size, size), Image.LANCZOS)


def splash(width: int, height: int) -> Image.Image:
	img = Image.new("RGB", (width, height), (247, 250, 252))
	m = mark(max(96, round(min(width, height) * 0.22)))
	img.paste(m, ((width - m.width) // 2, (height - m.height) // 2), m)
	return img


def main(apps: str) -> int:
	root = Path(apps)
	brand = root / "nanobase_brand" / "nanobase_brand" / "public" / "images"
	svg = brand / "logo-mark.svg"
	written = 0

	manifest = root / "helpdesk" / "desk" / "public" / "manifest"
	for f in sorted(manifest.glob("*.png")) + sorted(manifest.glob("*.jpg")):
		if m := re.match(r"apple-splash-(\d+)-(\d+)\.jpg$", f.name):
			splash(int(m[1]), int(m[2])).save(f, quality=90)
		elif m := re.search(r"-(\d+)(?:\.maskable)?\.png$", f.name):
			size = int(m[1])
			# Maskelenebilir simgede köşeyi işletim sistemi keser: tam kare çizilir.
			mark(size, rounded="maskable" not in f.name).save(f)
		else:
			continue
		written += 1

	frappe_images = root / "frappe" / "frappe" / "public" / "images"
	for name in ("frappe-framework-logo.svg", "frappe-favicon.svg", "frappe-comp-logo.svg"):
		if (frappe_images / name).exists():
			shutil.copyfile(svg, frappe_images / name)
			written += 1
	for name, size in (("frappe-framework-logo.png", 256), ("frappe-logo.png", 256)):
		if (frappe_images / name).exists():
			mark(size).save(frappe_images / name)
			written += 1
	mark(512).save(brand / "logo-mark.png")
	written += 1

	helpdesk_desk_png = root / "helpdesk" / "desk" / "public" / "desk.png"
	if helpdesk_desk_png.exists():
		mark(128).save(helpdesk_desk_png)
		written += 1

	print(f"simge: {written} görsel yazıldı")
	return 0 if written else 1


if __name__ == "__main__":
	sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else "apps"))
