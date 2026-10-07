"""İşçi süreçlerinin ortak döngüsü. Sunucu (server.py) her motoru ayrı süreçte çalıştırır: Wan 2.2 ana Python'da
(transformers ≤4.51.3), H3/FastH3/iyileştirme /opt/h3 sanal ortamında (Qwen3-VL için yeni transformers). Motor
değişince süreç kapatılır; GPU ve CPU belleği işletim sistemiyle birlikte boşalır.

Protokol: sunucu stdin'e tek satır JSON yazar {"id", "req": <istek>, "td": <geçici klasör>}; işçi stdout'a tek satır
yanıt verir {"id", "ok": true, "out": {...}} ya da {"id", "ok": false, "status", "error"}. Büyük veri (görsel, ses,
video) geçici klasörde dosyadır. Kütüphanelerin print'leri protokolü bozmasın diye stdout stderr'e çevrilir.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import traceback
from pathlib import Path


class Refused(Exception):
    """İstemcinin düzeltebileceği hata (HTTP 422)."""


def serve(handle) -> None:
    proto = os.fdopen(os.dup(1), "w", buffering=1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    for line in sys.stdin:
        if not line.strip():
            continue
        msg = json.loads(line)
        try:
            out = handle(msg["req"], Path(msg["td"]))
            reply = {"id": msg["id"], "ok": True, "out": out}
        except Refused as e:
            reply = {"id": msg["id"], "ok": False, "status": 422, "error": str(e)}
        except Exception as e:  # noqa: BLE001 — hata metni sunucuya, iz stderr'e
            traceback.print_exc()
            reply = {"id": msg["id"], "ok": False, "status": 500, "error": f"{type(e).__name__}: {e}"[:500]}
        proto.write(json.dumps(reply) + "\n")


def write_mp4(frames_u8, fps: float, out: Path) -> None:
    """[T, H, W, 3] uint8 (numpy) → H.264 mp4, sessiz. Boyut tek sayıysa ffmpeg kırpmasın diye çift yapılır."""
    t, h, w, _ = frames_u8.shape
    h2, w2 = h - h % 2, w - w % 2
    p = subprocess.Popen(["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{w}x{h}",
                          "-r", str(fps), "-i", "-", "-vf", f"crop={w2}:{h2}:0:0", "-c:v", "libx264", "-preset", "slow",
                          "-crf", "16", "-pix_fmt", "yuv420p", "-an", str(out)], stdin=subprocess.PIPE)
    for k in range(t):
        p.stdin.write(frames_u8[k].tobytes())
    p.stdin.close()
    if p.wait() != 0:
        raise RuntimeError("ffmpeg mp4 yazamadı")


def probe(path: Path) -> dict:
    """{width, height, fps, frames} — ffprobe."""
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-count_packets", "-show_entries",
                        "stream=width,height,r_frame_rate,nb_read_packets", "-of", "json", str(path)],
                       capture_output=True, text=True, check=True)
    s = json.loads(r.stdout)["streams"][0]
    num, den = s["r_frame_rate"].split("/")
    return {"width": int(s["width"]), "height": int(s["height"]), "fps": float(num) / float(den or 1),
            "frames": int(s.get("nb_read_packets") or 0)}


def pad_wav(src: Path, seconds: float, out: Path, rate: int) -> None:
    """Ses izini `seconds`'a sessizlikle tamamlar (ya da keser), `rate` Hz mono wav."""
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-af", f"apad,atrim=0:{seconds:.3f}",
                    "-ar", str(rate), "-ac", "1", str(out)], check=True, timeout=120)
