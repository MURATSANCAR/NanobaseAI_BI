"""Konuşma tanıma modeli. İki aile desteklenir; hangisinin yükleneceği model klasörünün `config.json`'ından okunur:

* `whisper` (openai/whisper-large-v3 ve ince ayarlı Türkçe türevleri),
* `qwen3_asr` (Qwen3-ASR, transformers yerel sürümü).

Seçim ölçümle yapıldı (deploy/tt-gpu/voice-note/OLCUM.md). Torch ve transformers yalnız bu modülde, yükleme anında
içe aktarılır; ses ve metin yardımcıları torch'suz sınanabilir.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any, Optional, Sequence

import numpy as np

from voice_note_service.audio import SR

log = logging.getLogger("voice_note.engine")


class Engine:
    def __init__(self, model_dir: str, *, device: str = "cuda", batch: int = 8, beams: int = 1,
                 mem_fraction: float = 0.0, language: str = "tr"):
        self.model_dir, self.device, self.batch, self.beams, self.language = model_dir, device, max(1, batch), max(1, beams), language
        self.mem_fraction = mem_fraction
        self.family = ""
        self.model: Any = None
        self.proc: Any = None
        self.loaded_at: Optional[float] = None

    def load(self) -> None:
        import torch

        cfg = json.load(open(os.path.join(self.model_dir, "config.json"), encoding="utf-8"))
        mt = str(cfg.get("model_type", ""))
        if self.device.startswith("cuda") and self.mem_fraction > 0:
            # Aynı kartta başka model var: bu süreç payını aşarsa kendisi OOM olur, komşusu değil.
            torch.cuda.set_per_process_memory_fraction(self.mem_fraction, torch.device(self.device).index or 0)
        cpu = self.device == "cpu"
        if mt == "qwen3_asr":
            from transformers import AutoProcessor, Qwen3ASRForConditionalGeneration
            self.dtype = torch.float32 if cpu else torch.bfloat16
            self.proc = AutoProcessor.from_pretrained(self.model_dir)
            self.model = Qwen3ASRForConditionalGeneration.from_pretrained(self.model_dir, dtype=self.dtype).to(self.device).eval()
            self.family = "qwen3_asr"
        elif mt == "whisper":
            from transformers import WhisperForConditionalGeneration, WhisperProcessor
            self.dtype = torch.float32 if cpu else torch.float16
            self.proc = WhisperProcessor.from_pretrained(self.model_dir)
            self.model = WhisperForConditionalGeneration.from_pretrained(self.model_dir, dtype=self.dtype).to(self.device).eval()
            self.model.generation_config.max_length = None
            self.family = "whisper"
        else:
            raise RuntimeError(f"Desteklenmeyen model türü: {mt!r}")
        self.loaded_at = time.time()
        # Isınma: ilk gerçek istek derleme/önbellek süresini ödemesin.
        self.transcribe([np.zeros(SR, dtype=np.float32)])
        log.info("model hazır: %s (%s, %s)", os.path.basename(self.model_dir.rstrip("/")), self.family, self.device)

    def transcribe(self, arrs: Sequence[np.ndarray], context: str = "") -> list[str]:
        out: list[str] = []
        for i in range(0, len(arrs), self.batch):
            out.extend(self._batch(list(arrs[i:i + self.batch]), context))
        return out

    def _batch(self, arrs: list[np.ndarray], context: str) -> list[str]:
        import torch

        with torch.inference_mode():
            if self.family == "qwen3_asr":
                kw: dict[str, Any] = {"language": [self.language] * len(arrs), "sampling_rate": SR}
                if context:
                    kw["prompt"] = [context] * len(arrs)
                inp = self.proc.apply_transcription_request(arrs, **kw).to(self.device, self.dtype)
                ids = self.model.generate(**inp, max_new_tokens=448, num_beams=self.beams, do_sample=False)
                return list(self.proc.decode(ids[:, inp["input_ids"].shape[1]:], return_format="transcription_only"))
            feats = self.proc.feature_extractor(arrs, sampling_rate=SR, return_tensors="pt", return_attention_mask=True)
            gen: dict[str, Any] = {"language": self.language, "task": "transcribe", "num_beams": self.beams, "max_new_tokens": 440}
            if context:
                gen["prompt_ids"] = torch.tensor(self.proc.get_prompt_ids(context[:600]), device=self.device)
            ids = self.model.generate(feats.input_features.to(self.device, self.dtype),
                                      attention_mask=feats.attention_mask.to(self.device), **gen)
            texts = self.proc.batch_decode(ids, skip_special_tokens=True)
            if context:  # istem metni çıktının başında dönebilir
                texts = [t[len(context):] if t.startswith(context) else t for t in (x.strip() for x in texts)]
            return texts

    def memory(self) -> dict[str, float]:
        try:
            import torch
            if self.device.startswith("cuda"):
                return {"reservedGb": round(torch.cuda.memory_reserved() / 1024**3, 2),
                        "peakGb": round(torch.cuda.max_memory_reserved() / 1024**3, 2)}
        except Exception:  # noqa: BLE001
            pass
        return {}
