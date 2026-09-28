import { describe, expect, it } from 'vitest';
import { appendNote, fmtClock } from './api';
import { downmix, encodeWav, resampleLinear, TARGET_RATE, wavSeconds } from './wav';

describe('sesli not: WAV', () => {
  it('16 kHz tek kanal 16 bit başlık ve süre', async () => {
    const samples = new Float32Array(TARGET_RATE * 2).fill(0.25);
    const wav = encodeWav(samples);
    expect(wav.type).toBe('audio/wav');
    expect(wav.size).toBe(44 + samples.length * 2);
    const buf = await wav.arrayBuffer();
    const v = new DataView(buf);
    expect(String.fromCharCode(...new Uint8Array(buf.slice(0, 4)))).toBe('RIFF');
    expect(String.fromCharCode(...new Uint8Array(buf.slice(8, 12)))).toBe('WAVE');
    expect(v.getUint16(22, true)).toBe(1);
    expect(v.getUint32(24, true)).toBe(16_000);
    expect(v.getUint16(34, true)).toBe(16);
    expect(v.getInt16(44, true)).toBe(8191); // 0,25 × 32767, tamsayıya kesilir
    expect(wavSeconds(buf)).toBeCloseTo(2, 5);
  });

  it('taşan örnek kırpılır (±1)', async () => {
    const v = new DataView(await encodeWav(new Float32Array([2, -3])).arrayBuffer());
    expect(v.getInt16(44, true)).toBe(0x7fff);
    expect(v.getInt16(46, true)).toBe(-0x8000);
  });

  it('WAV olmayan veride süre yok', () => {
    expect(wavSeconds(new ArrayBuffer(10))).toBeNull();
    const ogg = new ArrayBuffer(64);
    new Uint8Array(ogg).set(new TextEncoder().encode('OggS'));
    expect(wavSeconds(ogg)).toBeNull();
  });

  it('48 kHz → 16 kHz: süre korunur, sabit sinyal bozulmaz', () => {
    const one = new Float32Array(48_000).fill(0.5);
    const out = resampleLinear(one, 48_000, 16_000);
    expect(out.length).toBe(16_000);
    expect(out[8000]).toBeCloseTo(0.5, 5);
    expect(resampleLinear(one, 16_000, 16_000)).toBe(one);
  });

  it('stereo tek kanala ortalanır', () => {
    const m = downmix([new Float32Array([1, 0, 1]), new Float32Array([0, 0, -1])]);
    expect(Array.from(m)).toEqual([0.5, 0, 0]);
    expect(downmix([]).length).toBe(0);
  });
});

describe('sesli not: not alanı', () => {
  it('metin nota eklenir, üzerine yazılmaz', () => {
    expect(appendNote('', ' Katalog bırakıldı. ')).toBe('Katalog bırakıldı.');
    expect(appendNote('Müdürle görüşüldü.  \n', 'Katalog bırakıldı.')).toBe('Müdürle görüşüldü.\nKatalog bırakıldı.');
    expect(appendNote('Eski not', '   ')).toBe('Eski not');
  });

  it('kayıt süresi dakika:saniye', () => {
    expect(fmtClock(0)).toBe('0:00');
    expect(fmtClock(7.9)).toBe('0:07');
    expect(fmtClock(300)).toBe('5:00');
    expect(fmtClock(-3)).toBe('0:00');
  });
});
