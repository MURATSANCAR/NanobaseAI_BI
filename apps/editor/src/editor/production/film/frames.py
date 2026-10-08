"""İlk kareler (storyboard): her çekimin ilk karesi görsel modelde (gateway `book-image`) çizilir; video modeli bu
kareden başlar. Karakter tutarlılığı referansla sağlanır: dizinin onaylı kartının görseli, kart yoksa filmin kendi
ürettiği karakter referansı (bir kez, `kare/oyuncu-<n>.png`). Çekimde karakter varsa düzenleme ucu (referanslı), yoksa
metinden üretim — images.Painter ile aynı uç sözleşmesi.

Her kare görsel denetçiden geçer (gateway `book-vision-fast`): yazı/harf, bozuk el-yüz, kişi sayısı, tarife uyum.
Geçmeyen kare yeni tohumla yeniden çizilir (en çok `RETRIES`); yine geçmezse editöre «denetimden geçmedi» notuyla
gösterilir. Editör tek kareyi yönlendirmeyle yeniden çizdirebilir (`redo`), sürümler saklanır.
"""

from __future__ import annotations

import base64
import io
import json
from pathlib import Path

import httpx

from .. import images as I
from . import cast as cast_mod
from . import script as script_mod
from . import spec, store

VISION = "book-vision-deep"     # hızlı okuyucu karakter karışıklığını görmüyordu (2026-10-08: 8/8 yanlış «geçti»)
RETRIES = 2
NEGATIVE = ("text, letters, subtitles, watermark, logo, blurry, low quality, deformed hands, extra fingers, "
            "extra limbs, distorted face, duplicate character")
QC_SCHEMA = {"type": "object", "additionalProperties": False,
             "required": ["has_text", "deformed", "characters", "extra_copy", "action_shown"],
             "properties": {"has_text": {"type": "boolean"}, "deformed": {"type": "boolean"},
                            "characters": {"type": "array", "items": {
                                "type": "object", "additionalProperties": False,
                                "required": ["name", "present", "matches"],
                                "properties": {"name": {"type": "string"}, "present": {"type": "boolean"},
                                               "matches": {"type": "boolean"}}}},
                            "extra_copy": {"type": "boolean"}, "action_shown": {"type": "boolean"}}}


def _gateway() -> tuple[str, dict]:
    from ...config import settings
    s = settings()
    return s.gateway_url.rstrip("/"), {"authorization": f"Bearer {s.gateway_key}"}


def _b64(path: str | Path) -> str:
    return base64.b64encode(Path(path).read_bytes()).decode()


async def _generate(http, prompt: str, W: int, H: int, seed: int) -> bytes:
    url, hd = _gateway()
    body = {"model": I.ALIAS, "prompt": prompt, "negative_prompt": NEGATIVE, "size": f"{W}x{H}",
            "num_inference_steps": I.STEPS, "true_cfg_scale": 4.0, "seed": seed, "response_format": "b64_json"}
    r = await http.post(f"{url}/v1/images/generations", json=body, headers=hd)
    r.raise_for_status()
    return base64.b64decode(r.json()["data"][0]["b64_json"])


async def _edit(http, prompt: str, refs: list[str], W: int, H: int, seed: int) -> bytes:
    url, hd = _gateway()
    content = [{"type": "text", "text": prompt}] + [
        {"type": "image_url", "image_url": {"url": "data:image/png;base64," + _b64(p)}} for p in refs[:I.MAX_REFS]]
    body = {"model": I.ALIAS, "messages": [{"role": "user", "content": content}], "height": H, "width": W,
            "num_inference_steps": I.STEPS, "seed": seed, "true_cfg_scale": 4.0, "negative_prompt": NEGATIVE}
    r = await http.post(f"{url}/v1/chat/completions", json=body, headers=hd)
    r.raise_for_status()
    part = r.json()["choices"][0]["message"]["content"]
    u = part[0]["image_url"]["url"] if isinstance(part, list) else part
    return base64.b64decode(u.split(",", 1)[1])


def _jpeg(png: bytes, side: int = 1280) -> str:
    from PIL import Image
    im = Image.open(io.BytesIO(png)).convert("RGB")
    im.thumbnail((side, side))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=90)
    return base64.b64encode(buf.getvalue()).decode()


def qc_result(out: dict, expected: list[str]) -> dict:
    """Denetçinin evet/hayır cevaplarından karar ve Türkçe sorun listesi (karar modelde değil, burada; model
    «problems» alanına temiz denetimleri de yazıyordu, 2026-10-07: 35 karenin 30'u boşuna «geçmedi»)."""
    probs = []
    if out.get("has_text"):
        probs.append("Karede yazı, harf ya da rakam var.")
    if out.get("deformed"):
        probs.append("El, yüz ya da beden bozuk.")
    if out.get("extra_copy"):
        probs.append("Bir karakter karede iki kez çizilmiş.")
    seen = {(c.get("name") or "").casefold(): c for c in out.get("characters", [])}
    for name in expected:
        c = seen.get(name.casefold())
        if c is None or not c.get("present"):
            probs.append(f"{name} karede yok.")
        elif not c.get("matches"):
            probs.append(f"{name} karakter kartındaki gibi değil (saç, giysi ya da yaş).")
    if out.get("action_shown") is False:
        probs.append("Kare, çekimin tarif ettiği anı göstermiyor.")
    return {"ok": not probs, "problems": probs}


async def review(http, png: bytes, shot: dict, cast_lines: dict[str, str] | None = None) -> dict:
    """Görsel denetçi: her denetim ayrı evet/hayır, her beklenen karakter için «var mı, kartına uyuyor mu»; karar
    `qc_result`'ta. Ulaşılamazsa {"ok": None}: kare kullanılır, ekranda «denetlenemedi»."""
    url, hd = _gateway()
    expected = list(shot.get("characters", []))
    who = "\n".join(f"- {cast_lines[c]}" if cast_lines and c in cast_lines else f"- {c}" for c in expected) or "- (none)"
    ask = ("You check one frame of an animated film before it is animated. Answer each question about THIS image:\n"
           "has_text: is any text, letter, number or watermark visible?\n"
           "deformed: is any hand, face or body clearly deformed or with extra parts?\n"
           f"characters: for EACH of these expected characters give name, present (is this character in the picture?) "
           f"and matches (do hair colour, clothes and apparent age match the description?):\n{who}\n"
           "extra_copy: does any of these characters appear twice, or is there an extra person who looks like one of "
           "them?\n"
           f"action_shown: does the picture show this moment: \"{shot['action_en']}\"?")
    # düşünme AÇIK: kapalıyken derin model de karakter karışıklığını kaçırıyordu; cevap düşünmeden sonra JSON
    body = {"model": VISION, "max_tokens": 6000, "temperature": 0.0,
            "response_format": {"type": "json_schema", "json_schema": {"name": "qc", "schema": QC_SCHEMA,
                                                                        "strict": True}},
            "messages": [{"role": "user", "content": [
                {"type": "text", "text": ask},
                {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64," + _jpeg(png)}}]}]}
    try:
        r = await http.post(f"{url}/v1/chat/completions", json=body, headers=hd, timeout=600)
        r.raise_for_status()
        return qc_result(json.loads(r.json()["choices"][0]["message"]["content"]), expected)
    except Exception:  # noqa: BLE001
        return {"ok": None, "problems": []}

async def _char_refs(http, f: Path, cast: dict, style: str, W: int) -> dict[str, str]:
    """Kartı olmayan oyuncuya bir kez referans çizer (düz zemin, tam boy)."""
    kd = f / "kare"
    out = {}
    for i, m in enumerate(cast["members"]):
        if m.get("ref") and Path(m["ref"]).exists():
            out[m["name"]] = m["ref"]
            continue
        p = kd / f"oyuncu-{i:02d}.png"
        if not p.exists():
            prompt = (f"Character reference sheet of {m['name']}: {m['look_en']} Full body, standing, front "
                      f"three-quarter view, neutral expression, plain white background. Style: "
                      f"{spec.STYLES[style]['en']}. No text.")
            p.write_bytes(await _generate(http, prompt, 1024, 1024, 7000 + i))
        out[m["name"]] = str(p)
    return out


def ref_note(named: list[str], everyone: list[str]) -> str:
    """Referans görsellerin sırası adıyla ve karedeki kişi sayısı. Birden çok karakterli karede model saçı/giysiyi
    karakterler arasında karıştırıyor ve aynı karakteri iki kez çiziyordu (2026-10-08: 8 karede)."""
    order = "; ".join(f"reference image {i} shows {n}" for i, n in enumerate(named, 1))
    people = ", ".join(everyone)
    return (f" Reference images, in order: {order}. Draw each character exactly like their OWN reference image (face, "
            f"hair colour and style, clothes, colours, size); never swap hair or clothes between characters. The picture "
            f"shows exactly {len(everyone)} {'person' if len(everyone) == 1 else 'people'} ({people}); draw each of "
            f"them once, no duplicates, no other people.")


async def render(f: Path, shot: dict, cast: dict, refs: dict[str, str], style: str, seed: int,
                 direction: str = "", http=None) -> tuple[bytes, str]:
    """Tek aday kare (denetimsiz). Karakter kartı varsa kartlarla düzenleme, yoksa düz üretim."""
    W, H = spec.FORMATS[store.meta(f)["format"]]["gen"]
    prompt = spec.shot_prompt(shot, style, cast_mod.card_lines(cast))
    if direction.strip():
        prompt += f" Editor's direction (follow it): {direction.strip()}."
    named = [c for c in shot.get("characters", []) if c in refs][:I.MAX_REFS]
    if named:
        png = await _edit(http, prompt + ref_note(named, shot.get("characters", [])), [refs[c] for c in named],
                          W, H, seed)
    else:
        png = await _generate(http, prompt, W, H, seed)
    return png, prompt


async def draw(f: Path, shot: dict, cast: dict, refs: dict[str, str], style: str, seed: int,
               direction: str = "", http=None) -> tuple[bytes, dict, str]:
    """Tek çekim: çiz, denetle, geçmezse yeni tohumla yeniden (en çok RETRIES). Çok çekimde `build` toplu çalışır."""
    qc, png, prompt = {"ok": None, "problems": []}, b"", ""
    for k in range(RETRIES + 1):
        png, prompt = await render(f, shot, cast, refs, style, seed + k, direction, http)
        qc = await review(http, png, shot, cast_mod.card_lines(cast))
        if qc["ok"] is not False:
            break
    return png, qc, prompt


def best(qcs: list[dict]) -> int:
    """Adaylardan seçilecek olan: ilk geçen; hiçbiri geçmediyse en az sorunlu (eşitlikte ilk)."""
    for i, q in enumerate(qcs):
        if q.get("ok") is not False:
            return i
    return min(range(len(qcs)), key=lambda i: len(qcs[i].get("problems", [])))


async def build(d: Path, f: Path, by: str, progress=lambda n, t, w="": None, only: list[str] | None = None,
                direction: str = "") -> dict:
    store.require(f, "oyuncular")
    m = store.meta(f)
    sc = script_mod.load(f)
    cast = cast_mod.load(f)
    kd = f / "kare"
    kd.mkdir(exist_ok=True)
    rec = store.read(f, "kareler.json") or {"shots": {}}
    store.set_stage(f, "kareler", status="calisiyor")
    shots = [s for s in spec.shots(sc) if not only or s["id"] in only]
    async with httpx.AsyncClient(timeout=httpx.Timeout(1800.0, connect=10.0)) as http:
        refs = await _char_refs(http, f, cast, m["style"], spec.FORMATS[m["format"]]["gen"][0])
        # Toplu: önce bütün adaylar çizilir, sonra hepsi denetlenir. Çizer ve denetçi aynı kartta sırayla
        # duruyor; kare başına sıra değiştirmek her seferinde 2–4 dk yükleme demekti (2026-10-08: 9 dk'da 1 kare).
        pending = []
        for n, s in enumerate(shots, 1):
            progress(n, len(shots), "İlk kareler çiziliyor")
            cur = rec["shots"].setdefault(s["id"], {"versions": [], "selected": None})
            v0 = len(cur["versions"]) + 1
            cands = []
            for k in range(RETRIES + 1):
                png, prompt = await render(f, s, cast, refs, m["style"], 1000 + 37 * n + 101 * v0 + k, direction, http)
                name = f"{s['id']}.v{v0 + k}.png"
                (kd / name).write_bytes(png)
                cands.append((name, png, prompt))
            pending.append((s, cur, v0, cands))
        lines = cast_mod.card_lines(cast)
        for n, (s, cur, v0, cands) in enumerate(pending, 1):
            progress(n, len(pending), "Kareler denetleniyor")
            qcs = [await review(http, png, s, lines) for _, png, _ in cands]
            for k, ((name, _, prompt), qc) in enumerate(zip(cands, qcs)):
                cur["versions"].append({"v": v0 + k, "file": name, "prompt": prompt, "qc": qc, "by": by,
                                        "at": store.now(), **({"direction": direction} if direction else {})})
            cur["selected"] = v0 + best(qcs)
            store.write(f, "kareler.json", rec)
    failed = sum(1 for x in rec["shots"].values() if x["versions"][x["selected"] - 1]["qc"].get("ok") is False)
    store.set_stage(f, "kareler", status="hazir", failed_qc=failed)
    store.log(f, by, "ilk kareler çizildi", count=len(shots), failed_qc=failed)
    return rec


def select(f: Path, shot_id: str, v: int, by: str) -> dict:
    rec = store.read(f, "kareler.json") or {"shots": {}}
    cur = rec["shots"].get(shot_id)
    if not cur or not 1 <= v <= len(cur["versions"]):
        raise store.FilmError("Böyle bir kare sürümü yok.")
    cur["selected"] = v
    store.write(f, "kareler.json", rec)
    store.set_stage(f, "kareler", status="hazir")
    store.log(f, by, "kare seçildi", shot=shot_id, v=v)
    return rec


def selected(f: Path, shot_id: str) -> Path:
    rec = store.read(f, "kareler.json") or {"shots": {}}
    cur = rec["shots"].get(shot_id)
    if not cur or not cur.get("selected"):
        raise store.FilmError(f"{shot_id} çekiminin ilk karesi yok.")
    return f / "kare" / cur["versions"][cur["selected"] - 1]["file"]
