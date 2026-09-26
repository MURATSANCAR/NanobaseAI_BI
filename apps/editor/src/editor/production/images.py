"""Resim üretimi (book-image, Qwen-Image-2.1): karakter referansları ve sayfa resimleri.

Tutarlılık: her ANA/YAN karakter önce düz zeminde bir kez çizilir (referans). Sayfa resmi, o sayfada
görünen karakterlerin referanslarıyla (en çok 4) düzenleme ucundan istenir; referanssız sayfa ya da
düzenleme ucu hata verirse metinden görsel ucuna düşer (sebep kayda geçer).

Boyut: model resmi piksel bütçesi içinde (EDITOR_IMAGE_PIXELS, varsayılan 3 MP) en-boy oranını
koruyarak üretir, sonra hedef alanın 300 dpi karşılığına book-upscale (Real-ESRGAN x4plus) ile büyütülür;
servis açılamazsa Lanczos'a düşer ve not düşülür. Bütçe, görsel modelin
kartı tek başına kullandığı düzene göredir (models.yaml book-image 0.62 payı ana modeli durdurur);
ana model aynı kartta açıkken 2,6 MP ve üstü bellek aşımı verir; tek başına 4,2 MP'de 22 resimden sonra
bellek 92,5 GB'a şişip aştı (ölçüldü 2026-09-24), bu yüzden 3 MP. Aşımda resim yarı çözünürlükte yeniden denenir. Üretim
çözünürlüğü kayda geçer; ön kontrol 250 dpi altında büyütülmüş resmi bildirir.

Seri karakter kartı (characters.py): dizide onaylı kartı olan karakterin istem satırı kartın tarifi ve sabit
renkleriyle yazılır, referansı kartın görselidir; üretilen resim karta karşı denetime yazılır.

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
from .bubbles import wanted as wants_bubbles

ALIAS = "book-image"
UPSCALE_ALIAS = "book-upscale"
PIXEL_BUDGET = int(os.environ.get("EDITOR_IMAGE_PIXELS", 3_000_000))
STEPS = 40
MAX_REFS = 4
FIGURE_PX = (896, 1152)            # serbest figür üretim boyu (~1 MP, dik); 40–60 mm kutuda 500+ dpi
# Çocuk kitabında (bubbles.wanted) konuşma balonları resmin üstüne dizgide basılır: sayfa resmi üst bölgede sade
# bir boşluk bırakır. Düzeltmede (base_image) kompozisyon korunduğu için eklenmez; kapakta balon yoktur.
BUBBLE_SPACE = ("Leave a calm, empty area in the upper part of the picture (plain sky or plain wall, no important "
                "details there) for speech bubbles.")


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
        self._refs: dict[str, str] = {}
        self._cards = None                 # dizinin onaylı karakter kartları (characters.py), ilk kullanımda okunur
        self.bubble_space = wants_bubbles(self.dir.parent / "profile.json")     # iş klasöründeki profil

    @property
    def cards(self):
        """Seri karakter kartları: istemde kartın tarifi ve sabit renkleri, referans olarak kartın görseli."""
        if self._cards is None:
            from .characters import CardSet
            try:
                self._cards = CardSet.for_job(self.dir.parent)
            except Exception:  # noqa: BLE001 - kart okunamazsa işin kendi tarifleriyle çizilir
                self._cards = CardSet()
        return self._cards

    @property
    def refs(self) -> dict[str, str]:
        """Karakter referansları: işin çizdiği referans; onaylı kartın görseli varsa o önce gelir."""
        return {**self._refs, **(self.cards.ref_paths(c.name for c in self.plan.characters) if self.cards else {})}

    @refs.setter
    def refs(self, value: dict[str, str]) -> None:
        self._refs = dict(value)

    @property
    def negative(self) -> str:
        return self.plan.style.avoid + ", blurry, low quality, deformed, extra limbs, watermark"

    def _prompt(self, body: str, chars: list[Character], outfits: dict | None = None) -> str:
        """Karakter: sabit görünüş + bu resimdeki kıyafet (sahnenin seçtiği; yoksa varsayılan)."""
        def wear(c):
            look = c.outfit((outfits or {}).get(c.name))
            return f" Wearing: {look}." if look else ""
        who = " ".join((self.cards.line(c, (outfits or {}).get(c.name)) if self.cards else None)
                       or f"{c.name} is {c.species}: {c.look}.{wear(c)}" for c in chars)
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
        # Parametreler yalnız üst düzeyde: vLLM-Omni aynı alanın extra_body'de de gelmesini 400 ile reddeder.
        body = {"model": ALIAS, "messages": [{"role": "user", "content": content}], **params}
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
            self._refs[c.name] = self._save(key, png)
            self.log.append(Render(key, self._refs[c.name], 1024, 1024, 0, self.seed + i, [], "generate",
                                   round(time.time() - t, 1), prompt, c.name))
        return dict(self._refs)

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
            # Sayfa planında sonradan eklenen sayfanın sahnesi yoktur: tarif yalnız editörün yönlendirmesidir.
            body = "Children's book illustration." + (f" {sc.scene}" if sc.scene else "") + \
                (f" Setting: {sc.setting}." if sc.setting else "")
            if self.bubble_space and sc.kind in ("flow", "full"):
                body += f" {BUBBLE_SPACE}"
            if direction.strip():
                body += f" Editor's direction (follow it): {direction.strip()}."
            prompt = self._prompt(body, chars, sc.outfits)
            refs = [self.refs[c.name] for c in chars if c.name in self.refs][:MAX_REFS]
        extra = "" if base_image else (" Keep each character's face, body and colors exactly as in the reference"
                                       " images; clothing follows the description above.")

        async def draw(W: int, H: int) -> tuple[bytes, str, str]:
            if refs:
                try:
                    return (await self._edit(prompt + extra, [Path(r).read_bytes() for r in refs], W, H, seed),
                            "fix" if base_image else "edit", "")
                except httpx.HTTPStatusError as e:
                    if e.response.status_code >= 500 or base_image:
                        raise                  # bellek aşımı üst katmanda küçültülüp denenir; düzeltme referanssız yapılamaz
                    fell = f"referanslı uç {e.response.status_code}: {e.response.text[:200]}"
                except (httpx.HTTPError, KeyError, IndexError, ValueError) as e:
                    if base_image:
                        raise
                    fell = str(e)[:300]
                return await self._generate(prompt, W, H, seed), "edit_failed→generate", fell
            return await self._generate(prompt, W, H, seed), "generate", ""

        try:
            png, mode, note = await draw(W, H)
        except httpx.HTTPStatusError as e:
            if e.response.status_code < 500:
                raise
            # Görsel model uzun koşuda belleği şişirebiliyor (ölçüldü 2026-09-24: 22 resimden sonra 92,5 GB,
            # tek başına). Aynı resim yarı piksel sayısıyla bir kez daha denenir; olmazsa hata üste çıkar.
            W, H = int(W * 0.707) // 32 * 32, int(H * 0.707) // 32 * 32
            dpi = round(dpi * 0.707)
            png, mode, note = await draw(W, H)
            note = (note + " · " if note else "") + "bellek aşımı: yarı çözünürlükte üretildi"
        TW, TH = target_px(w_mm, h_mm)
        png, how = await self.enlarge(png, TW, TH)
        if how:
            note = (note + " · " if note else "") + how
        rd = Render(key, self._save(key, png), TW, TH, dpi, seed, refs, mode, round(time.time() - t, 1), prompt, note)
        self.log.append(rd)
        from .characters import record
        await record(self, rd, sc, w_mm, h_mm, direction, base_image)    # kartlı karakter varsa denetime yazılır
        return rd

    async def figure(self, what: str, chars: list[Character], key_name: str, key_hex: str, seed: int) -> tuple[bytes, str]:
        """Serbest figür: kitabın üslubunda, düz tek renk zemin üzerinde tek figür (zemin sonra ayıklanır,
        photo.cutout). Karakter seçildiyse referansıyla düzenleme ucundan; referans ucu hata verirse metinden.
        Dönen: (PNG, yol «edit» | «generate» | «edit_failed→generate»)."""
        W, H = FIGURE_PX
        body = (f"A single isolated figure for a children's book: {what}. The whole figure is visible and centered, "
                f"with a wide empty margin on every side. Background: one flat, uniform, solid {key_name} colour "
                f"({key_hex}) everywhere, no gradient, no texture, no cast shadow, no floor, no scenery, nothing else.")
        prompt = self._prompt(body, chars)
        refs = [self.refs[c.name] for c in chars if c.name in self.refs][:MAX_REFS]
        if refs:
            try:
                extra = " Keep each character's face, body and colors exactly as in the reference images."
                return await self._edit(prompt + extra, [Path(r).read_bytes() for r in refs], W, H, seed), "edit"
            except httpx.HTTPStatusError as e:
                if e.response.status_code >= 500:
                    raise
            except (httpx.HTTPError, KeyError, IndexError, ValueError):
                pass
            return await self._generate(prompt, W, H, seed), "edit_failed→generate"
        return await self._generate(prompt, W, H, seed), "generate"

    async def pages(self, scenes: list[Scene], band_mm: tuple[float, float], full_mm: tuple[float, float],
                    concurrency: int = 1) -> dict[int, str]:
        sem = asyncio.Semaphore(concurrency)

        async def one(sc):
            async with sem:
                return sc.page, await self.page(sc, *(full_mm if sc.kind == "full" else band_mm))

        done = await asyncio.gather(*(one(sc) for sc in scenes))
        return {n: rd.path for n, rd in done}

    async def enlarge(self, png: bytes, W: int, H: int) -> tuple[bytes, str]:
        """Hedef ölçüye büyütme: book-upscale (Real-ESRGAN); açılamazsa Lanczos ve sebebi not olarak döner."""
        import io
        from PIL import Image
        if Image.open(io.BytesIO(png)).size == (W, H) or os.environ.get("EDITOR_UPSCALE") == "lanczos":
            return upscale(png, W, H), ""
        try:
            r = await self.http.post(f"{self.url}/v1/images/upscale", headers=self.headers, json={
                "model": UPSCALE_ALIAS, "image": base64.b64encode(png).decode(), "width": W, "height": H})
            r.raise_for_status()
            return base64.b64decode(r.json()["image"]), ""
        except (httpx.HTTPError, KeyError, ValueError) as e:
            return upscale(png, W, H), f"büyütme servisi açılamadı, basit büyütme kullanıldı: {str(e)[:120]}"

    async def release(self) -> str:
        """Görsel modeli hemen kapatır (gateway iç ucu): iş bitince kartı ana modele geri verir, gateway'in
        bekçisi ana modeli kendiliğinden kaldırır. Sınamada (EDITOR_IMAGE_URL) gateway yoktur, bir şey yapmaz."""
        if os.environ.get("EDITOR_IMAGE_URL"):
            return "doğrudan uç: kapatma yok"
        s = settings()
        try:
            for alias in (ALIAS, UPSCALE_ALIAS):
                r = await self.http.post(f"{self.url}/internal/stop/{alias}",
                                         headers={"authorization": f"Bearer {s.gateway_internal_key}"}, timeout=90)
                r.raise_for_status()
            return "görsel model ve büyütücü kapatıldı; ana model geri kalkıyor"
        except httpx.HTTPError as e:
            return f"görsel model kapatılamadı ({e}); boşta kalınca kendisi kapanacak"

    def write_log(self, path: Path) -> None:
        path.write_text(json.dumps([asdict(r) for r in self.log], ensure_ascii=False, indent=1))

    async def close(self) -> None:
        await self.http.aclose()
