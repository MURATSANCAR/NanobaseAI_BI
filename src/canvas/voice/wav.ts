/** Tarayıcıda ses → 16 kHz tek kanal 16 bit WAV. Servis her biçimi okuyabilir ama WAV'ı çözmeden okur; köprü de süreyi
 *  başlıktan denetler. 5 dakika ≈ 9,6 MB. Ses yalnız bellekte durur, hiçbir yere yazılmaz. */

export const TARGET_RATE = 16_000;

/** Kanalların ortalaması (stereo kayıt tek kanala). */
export function downmix(channels: Float32Array[]): Float32Array {
  if (channels.length === 0) return new Float32Array(0);
  if (channels.length === 1) return channels[0];
  const n = Math.min(...channels.map((c) => c.length));
  const out = new Float32Array(n);
  for (const c of channels) for (let i = 0; i < n; i++) out[i] += c[i] / channels.length;
  return out;
}

/** Doğrusal yeniden örnekleme (OfflineAudioContext yoksa). Konuşma için yeterli; önce kaba alçak geçiren süzgeç
 *  (kutu ortalaması) uygulanır ki 44,1/48 kHz'ten inerken örtüşme gürültüsü olmasın. */
export function resampleLinear(input: Float32Array, from: number, to: number): Float32Array {
  if (from === to || input.length === 0) return input;
  let src = input;
  const ratio = from / to;
  if (ratio > 1) {
    const k = Math.max(1, Math.round(ratio));
    src = new Float32Array(input.length);
    let acc = 0;
    for (let i = 0; i < input.length; i++) {
      acc += input[i];
      if (i >= k) acc -= input[i - k];
      src[i] = acc / Math.min(i + 1, k);
    }
  }
  const n = Math.max(1, Math.floor(src.length / ratio));
  const out = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const x = i * ratio;
    const j = Math.floor(x);
    const f = x - j;
    const a = src[j] ?? 0;
    const b = src[j + 1] ?? a;
    out[i] = a + (b - a) * f;
  }
  return out;
}

/** PCM 16 bit WAV (RIFF) üretir. */
export function encodeWav(samples: Float32Array, rate = TARGET_RATE): Blob {
  const buf = new ArrayBuffer(44 + samples.length * 2);
  const v = new DataView(buf);
  const str = (o: number, s: string) => {
    for (let i = 0; i < s.length; i++) v.setUint8(o + i, s.charCodeAt(i));
  };
  str(0, 'RIFF');
  v.setUint32(4, 36 + samples.length * 2, true);
  str(8, 'WAVE');
  str(12, 'fmt ');
  v.setUint32(16, 16, true);
  v.setUint16(20, 1, true); // PCM
  v.setUint16(22, 1, true); // tek kanal
  v.setUint32(24, rate, true);
  v.setUint32(28, rate * 2, true);
  v.setUint16(32, 2, true);
  v.setUint16(34, 16, true);
  str(36, 'data');
  v.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const s = Math.max(-1, Math.min(1, samples[i]));
    v.setInt16(44 + i * 2, s < 0 ? s * 0x8000 : s * 0x7fff, true);
  }
  return new Blob([buf], { type: 'audio/wav' });
}

/** WAV başlığından süre (sn). */
export function wavSeconds(bytes: ArrayBuffer): number | null {
  if (bytes.byteLength < 44) return null;
  const v = new DataView(bytes);
  const tag = String.fromCharCode(v.getUint8(0), v.getUint8(1), v.getUint8(2), v.getUint8(3));
  if (tag !== 'RIFF') return null;
  const rate = v.getUint32(24, true);
  const block = v.getUint16(32, true) || 1;
  return rate ? v.getUint32(40, true) / block / rate : null;
}

type AudioCtor = typeof AudioContext;

/** Kaydedilen (webm/ogg/mp4) ya da seçilen ses dosyasını 16 kHz tek kanal WAV'a çevirir. Çözülemezse null (çağıran
 *  özgün dosyayı gönderir; servis kendisi çözer). */
export async function toWav16k(blob: Blob): Promise<{ wav: Blob; seconds: number } | null> {
  const Ctx: AudioCtor | undefined =
    typeof window === 'undefined' ? undefined : window.AudioContext ?? (window as unknown as { webkitAudioContext?: AudioCtor }).webkitAudioContext;
  if (!Ctx) return null;
  const ctx = new Ctx();
  try {
    const decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
    const chans: Float32Array[] = [];
    for (let c = 0; c < decoded.numberOfChannels; c++) chans.push(decoded.getChannelData(c));
    const mono = downmix(chans);
    let out: Float32Array;
    if (typeof OfflineAudioContext !== 'undefined' && decoded.sampleRate !== TARGET_RATE) {
      const frames = Math.max(1, Math.ceil(decoded.duration * TARGET_RATE));
      const off = new OfflineAudioContext(1, frames, TARGET_RATE);
      const src = off.createBufferSource();
      const b = off.createBuffer(1, mono.length, decoded.sampleRate);
      b.getChannelData(0).set(mono);
      src.buffer = b;
      src.connect(off.destination);
      src.start();
      out = (await off.startRendering()).getChannelData(0);
    } else {
      out = resampleLinear(mono, decoded.sampleRate, TARGET_RATE);
    }
    return { wav: encodeWav(out), seconds: out.length / TARGET_RATE };
  } catch {
    return null;
  } finally {
    void ctx.close();
  }
}
