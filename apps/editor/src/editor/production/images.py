"""Resim üretimi (book-image, Qwen-Image-2.1): karakter referansları ve sayfa resimleri.

Tutarlılık: her ANA/YAN karakter önce düz zeminde bir kez çizilir (referans). Sayfa resmi, o sayfada
görünen karakterlerin referanslarıyla (en çok 4) düzenleme ucundan istenir; referanssız sayfa ya da
düzenleme ucu hata verirse metinden görsel ucuna düşer (sebep kayda geçer).

Boyut: model resmi piksel bütçesi içinde (EDITOR_IMAGE_PIXELS, varsayılan 1536×1024) en-boy oranını
koruyarak üretir, sonra hedef alanın 300 dpi karşılığına Lanczos ile büyütülür. Ölçüldü 2026-09-24:
ana model aynı kartta açıkken 2,6 MP ve üstü bellek aşımı veriyor, 1,57 MP 46 GB'ta sığıyor. Üretim
çözünürlüğü (`native_dpi`) kayda geçer; ön kontrol 250 dpi altında büyütülmüş resmi bildirir.

Uç: gateway (`book-image` takma adı). EDITOR_IMAGE_URL verilirse doğrudan o sunucu (sınama).
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from ..config import settings
from .art import ArtPlan, Character, Scene

ALIAS = "book-image"
PIXEL_BUDGET = int(os.environ.get("EDITOR_IMAGE_PIXELS", 1536 * 1024))
STEPS = 40
MAX_REFS = 4


def size_for(w_mm: float, h_mm: float, dpi: int = 300) -> tuple[int, int, int]:
    """Modelin üreteceği boyut: (genişlik px, yükseklik px, üretim dpi)."""
    w, h = w_mm / 25.4 * dpi, h_mm / 25.4 * dpi
    scale = min(1.0, (PIXEL_BUDGET / (w * h)) ** 0.5)
    W, H = int(w * scale) // 32 * 32, int(h * scale) // 32 * 32
    return W, H, round(W / (w_mm / 25.4))


def target_px(w_mm: float, h_mm: float, dpi: int = 300) -> tuple[int, int]:
    return round(w_mm / 25.4 * dpi), round(h_mm / 25.4 * dpi)


def upscale(png: bytes, W: int, H: int) -> bytes:
    """Hedef boyuta Lanczos büyütme + hafif keskinleştirme (sulu boya dokusunu bozmayacak kadar)."""
    import io
    from PIL import Image, ImageFilter
    im = Image.open(io.BytesIO(png)).convert("RGB")
    if im.size != (W, H):
        im = im.resize((W, H), Image.Resampling.LANCZOS).filter(ImageFilter.UnsharpMask(radius=1.2, percent=40, threshold=2))
    buf = io.BytesIO()
    im.save(buf, "PNG", optimize=False, compress_level=3)
    return buf.getvalue()


@dataclass
class Render:
    key: str
    path: str
    width: int
    height: int
    dpi: int                   # üretim çözünürlüğü (büyütmeden önce)
    seed: int
    refs: list[str]
    mode: str                  # generate | edit | edit_failed→generate
    seconds: float
    prompt: str
    note: str = ""


class Painter:
    def __init__(self, outdir: Path, plan: ArtPlan, seed: int = 42):
        self.dir = Path(outdir)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.plan = plan
        self.seed = seed
        direct = os.environ.get("EDITOR_IMAGE_URL", "").rstrip("/")
        s = settings()
        self.url = direct or s.gateway_url.rstrip("/")
        self.headers = {} if direct else {"authorization": f"Bearer {s.gateway_key}"}
        self.http = httpx.AsyncClient(timeout=httpx.Timeout(1800.0, connect=10.0))
        self.log: list[Render] = []
        self.refs: dict[str, str] = {}

    @property
    def negative(self) -> str:
        return self.plan.style.avoid + ", blurry, low quality, deformed, extra limbs, watermark"

    def _prompt(self, body: str, chars: list[Character]) -> str:
        who = " ".join(f"{c.name} is {c.species}: {c.look}." for c in chars)
        return f"{body} {who} Style: {self.plan.style.style_prompt} No text or letters anywhere."

    async def _generate(self, prompt: str, W: int, H: int, seed: int) -> bytes:
        body = {"model": ALIAS, "prompt": prompt, "negative_prompt": self.negative, "size": f"{W}x{H}",
                "num_inference_steps": STEPS, "true_cfg_scale": 4.0, "seed": seed, "response_format": "b64_json"}
        r = await self.http.post(f"{self.url}/v1/images/generations", json=body, headers=self.headers)
        r.raise_for_status()
        return base64.b64decode(r.json()["data"][0]["b64_json"])

    async def _edit(self, prompt: str, refs: list[bytes], W: int, H: int, seed: int) -> bytes:
        content = [{"type": "text", "text": prompt}] + [
            {"type": "image_url", "image_url": {"url": "data:image/png;base64," + base64.b64encode(b).decode()}}
            for b in refs]
        params = {"height": H, "width": W, "num_inference_steps": STEPS, "seed": seed,
                  "true_cfg_scale": 4.0, "negative_prompt": self.negative}
        body = {"model": ALIAS, "messages": [{"role": "user", "content": content}], **params, "extra_body": params}
        r = await self.http.post(f"{self.url}/v1/chat/completions", json=body, headers=self.headers)
        r.raise_for_status()
        part = r.json()["choices"][0]["message"]["content"]
        url = part[0]["image_url"]["url"] if isinstance(part, list) else part
        return base64.b64decode(url.split(",", 1)[1])

    def _save(self, key: str, png: bytes) -> str:
        path = self.dir / f"{key}.png"
        path.write_bytes(png)
        return str(path)

    async def character_refs(self) -> dict[str, str]:
        for i, c in enumerate(self.plan.characters):
            t = time.time()
            prompt = self._prompt(f"Character reference sheet: {c.name}, full body, standing, front three-quarter view, "
                                  "neutral friendly expression, plain white background, whole figure visible.", [c])
            png = await self._generate(prompt, 1024, 1024, self.seed + i)
            key = f"karakter-{i:02d}"
            self.refs[c.name] = self._save(key, png)
            self.log.append(Render(key, self.refs[c.name], 1024, 1024, 0, self.seed + i, [], "generate",
                                   round(time.time() - t, 1), prompt, c.name))
        return self.refs

    async def page(self, sc: Scene, w_mm: float, h_mm: float, *, version: int = 1, seed: int | None = None,
                   direction: str = "", base_image: str | None = None, key: str | None = None) -> Render:
        """Bir sayfa resmi. `base_image` verilirse DÜZELTME: o görsel ilk referanstır ve yalnız
        `direction`'da istenen değişir. Verilmezse sahneden ÜRETİM; `direction` editörün yönlendirmesi
        olarak sahneye eklenir. Karakter referansları her iki yolda da eklenir (en çok 4 görsel)."""
        W, H, dpi = size_for(w_mm, h_mm)
        chars = [c for c in self.plan.characters if c.name in sc.characters]
        seed = self.seed + 100 + sc.page if seed is None else seed
        key = key or f"sayfa-{sc.page:02d}"
        key = f"{key}.v{version}"
        t, mode, note = time.time(), "generate", ""
        if base_image:
            prompt = (f"Edit the first reference image: {direction.strip()}. Keep everything else exactly as it is: "
                      f"composition, characters, colors and drawing style. No text or letters anywhere.")
            refs = [base_image] + [self.refs[c.name] for c in chars if c.name in self.refs][:MAX_REFS - 1]
        else:
            body = f"Children's book illustration. {sc.scene} Setting: {sc.setting}."
            if direction.strip():
                body += f" Editor's direction (follow it): {direction.strip()}."
            prompt = self._prompt(body, chars)
            refs = [self.refs[c.name] for c in chars if c.name in self.refs][:MAX_REFS]
        png = None
        if refs:
            try:
                extra = "" if base_image else " Keep each character exactly as in the reference images."
                png = await self._edit(prompt + extra, [Path(r).read_bytes() for r in refs], W, H, seed)
                mode = "fix" if base_image else "edit"
            except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
                if base_image:
                    raise                      # düzeltme referanssız yapılamaz: sessizce yeni çizime düşmez
                mode, note = "edit_failed→generate", str(e)[:300]
        if png is None:
            png = await self._generate(prompt, W, H, seed)
        TW, TH = target_px(w_mm, h_mm)
        png = upscale(png, TW, TH)
        rd = Render(key, self._save(key, png), TW, TH, dpi, seed, refs, mode, round(time.time() - t, 1), prompt, note)
        self.log.append(rd)
        return rd

    async def pages(self, scenes: list[Scene], band_mm: tuple[float, float], full_mm: tuple[float, float],
                    concurrency: int = 1) -> dict[int, str]:
        sem = asyncio.Semaphore(concurrency)

        async def one(sc):
            async with sem:
                return sc.page, await self.page(sc, *(full_mm if sc.kind == "full" else band_mm))

        done = await asyncio.gather(*(one(sc) for sc in scenes))
        return {n: rd.path for n, rd in done}

    def write_log(self, path: Path) -> None:
        path.write_text(json.dumps([asdict(r) for r in self.log], ensure_ascii=False, indent=1))

    async def close(self) -> None:
        await self.http.aclose()
